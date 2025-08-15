import audioop
import logging
import os
from typing import Any

import numpy as np

from .worker import BaseWorkerProcess

logger = logging.getLogger(__name__)


def convert_mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
    return audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, None)[0]


class MulawToPcmWorker(BaseWorkerProcess):
    def init_worker(self):
        self.pid = os.getpid()
        logger.info('[MulawToPcmWorker instance started] PID=%s', self.pid)

    def handle(self, mulaw_bytes: bytes) -> bytes:
        pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
        return audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, None)[0]


class MixingWorker(BaseWorkerProcess):
    def init_worker(self):
        self.pid = os.getpid()
        logger.info('[MixingWorker instance started] PID=%s', self.pid)

    def handle(self, payload: dict[str, Any]) -> bytes:
        chunk1 = payload['chunk1']
        chunk2 = payload.get('chunk2')
        vol_a = payload.get('vol_a', 0.5)
        vol_b = payload.get('vol_b', 0.5)
        pcm_a = np.frombuffer(chunk1, dtype=np.int16).astype(np.int32)

        if chunk2 is None:
            # Mixing with silence
            mixed = pcm_a * vol_a
            mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
            mixed_8k = audioop.ratecv(mixed.tobytes(), 2, 1, 24000, 8000, None)[0]
            return audioop.lin2ulaw(mixed_8k, 2)

        pcm_b = np.frombuffer(chunk2, dtype=np.int16).astype(np.int32)

        target_len = max(len(pcm_a), len(pcm_b))
        if len(pcm_a) < target_len:
            pcm_a = np.pad(pcm_a, (0, target_len - len(pcm_a)), 'constant')
        if len(pcm_b) < target_len:
            pcm_b = np.pad(pcm_b, (0, target_len - len(pcm_b)), 'constant')

        mixed = (pcm_a * vol_a + pcm_b * vol_b) / (vol_a + vol_b)
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
        mixed_8k = audioop.ratecv(mixed.tobytes(), 2, 1, 24000, 8000, None)[0]

        return audioop.lin2ulaw(mixed_8k, 2)
