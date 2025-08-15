import asyncio
import multiprocessing as mp
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from logging import getLogger
from queue import Empty
from typing import Any, List, Sequence, Tuple, Type

logger = getLogger(__name__)


class BaseWorkerProcess(ABC):
    def __init__(self, input_queue: mp.Queue, output_queue: mp.Queue):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.init_worker()

    @abstractmethod
    def init_worker(self):
        raise NotImplementedError

    def run(self) -> None:
        while True:
            item: Any = self.input_queue.get()
            if item is None:
                logger.info('%s exiting...', mp.current_process().name)
                break

            batch: Sequence[Tuple[str, Any]] = item if isinstance(item, list) else [item]

            for task_id, payload in batch:
                try:
                    result = self.handle(payload)
                    self.output_queue.put((task_id, result, None))
                except Exception as exc:
                    self.output_queue.put((task_id, None, str(exc)))

    @abstractmethod
    def handle(self, payload: Any) -> Any:
        raise NotImplementedError


class AsyncProcessManager:
    def __init__(
        self,
        worker_cls: Type[BaseWorkerProcess],
        processes: int = 1,
        threadpool_size: int = 16,
    ) -> None:
        if processes < 1:
            raise ValueError('`processes` must be >= 1')

        self.input_queue: mp.Queue = mp.Queue()
        self.output_queue: mp.Queue = mp.Queue()
        self.executor = ThreadPoolExecutor(max_workers=threadpool_size)
        self.loop = asyncio.get_event_loop()
        self.futures: dict[str, asyncio.Future[Any]] = {}
        self.worker_cls = worker_cls

        self.procs: list[mp.Process] = []
        for idx in range(processes):
            p = mp.Process(
                name=f'{worker_cls.__name__}-{idx}',
                target=self.start_worker,
                args=(worker_cls, self.input_queue, self.output_queue),
                daemon=True,
            )
            p.start()
            self.procs.append(p)

        self.output_task = self.loop.create_task(self.poll_output())

    @staticmethod
    def start_worker(
        worker_cls: Type[BaseWorkerProcess],
        in_q: mp.Queue,
        out_q: mp.Queue,
    ) -> None:
        worker = worker_cls(in_q, out_q)
        worker.run()

    async def submit(self, data: Any) -> Any:
        task_id = uuid.uuid4().hex
        fut = self.loop.create_future()
        self.futures[task_id] = fut
        self.input_queue.put((task_id, data))
        return await fut

    async def submit_many(
        self,
        data: List[Any],
        batch_size: int = 32,
    ) -> List[Any]:
        if batch_size < 1:
            raise ValueError('`batch_size` must be >= 1')

        pending_futures: List[asyncio.Future[Any]] = []

        for idx in range(0, len(data), batch_size):
            batch_items = data[idx : idx + batch_size]

            queued_batch: List[Tuple[str, Any]] = []
            for payload in batch_items:
                task_id = uuid.uuid4().hex
                fut = self.loop.create_future()
                self.futures[task_id] = fut
                pending_futures.append(fut)
                queued_batch.append((task_id, payload))

            self.input_queue.put(queued_batch)

        return await asyncio.gather(*pending_futures)

    async def close(self) -> None:
        logger.info('Closing process manager: %s', self.worker_cls.__name__)
        for _ in self.procs:
            self.input_queue.put(None)

        self.output_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.output_task

        for proc in self.procs:
            proc.join(timeout=1)
        logger.info('All processes joined: %s', self.worker_cls.__name__)

        for fut in self.futures.values():
            if not fut.done():
                fut.set_exception(asyncio.CancelledError())
        self.futures.clear()

    async def poll_output(self) -> None:
        while True:
            try:
                while True:
                    try:
                        item = self.output_queue.get_nowait()
                        self.handle_item(item)
                    except Empty:
                        break

                item = await self.loop.run_in_executor(None, self.output_queue.get)
                self.handle_item(item)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning('Polling loop failed with:\n', exc_info=e)

    def handle_item(self, item: Tuple[str, Any, str | None]) -> None:
        task_id, result, error = item
        fut = self.futures.pop(task_id, None)
        if fut is None:
            return
        if error:
            fut.set_exception(RuntimeError(error))
        else:
            fut.set_result(result)

    def __del__(self) -> None:
        for _ in self.procs:
            self.input_queue.put_nowait(None)

        for p in self.procs:
            if p.is_alive():
                p.terminate()
