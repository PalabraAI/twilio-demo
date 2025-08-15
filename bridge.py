import asyncio
import base64
import json
import logging
from typing import Any

import aiohttp
import websockets
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from transcription import broadcast_transcription
from utils.audio import convert_mulaw_to_pcm
from utils.calls import CallSession

logger = logging.getLogger(__name__)


class AudioBridge:
    def __init__(self, app, call_session: CallSession, role: str, settings: dict):
        self.app = app
        self.http_session: aiohttp.ClientSession = app.http_client
        self.call_session: CallSession = call_session
        self.settings: dict[str, Any] = settings
        self.role: str = role

        if role == 'client':
            self.source_ws: WebSocket = call_session.source_websocket
            self.target_ws: WebSocket = call_session.target_websocket
        else:
            self.source_ws: WebSocket = call_session.target_websocket
            self.target_ws: WebSocket = call_session.source_websocket

        self._running = False
        self.palabra_ws = None
        self.palabra_session_id: str | None = None
        self._palabra_receive_task: asyncio.Task | None = None
        self._twilio_receive_task: asyncio.Task | None = None
        self._cleanup_lock = asyncio.Lock()
        self.original_audio_queue = asyncio.Queue()
        self.translated_audio_queue = asyncio.Queue()
        self.block_size = 960  # in bytes for pcm_s16le 24 khz with 20 ms

        # Transcription and translation state
        self.last_original_transcription = ''
        self.last_language = ''
        self.last_translated_transcription = ''

    async def _create_palabra_session(self) -> dict:
        url = 'https://api.palabra.ai/session-storage/session'
        payload = {'data': {'subscriber_count': 0, 'publisher_can_subscribe': True}}

        response = await self.http_session.post(url, json=payload)
        response.raise_for_status()

        return await response.json()

    async def _delete_palabra_session(self):
        if self.palabra_session_id:
            url = f'https://api.palabra.ai/session-storage/sessions/{self.palabra_session_id}'
            response = await self.http_session.delete(url)
            response.raise_for_status()

            self.palabra_session_id = None

    async def run(self):
        """Run the WebSocket connection with proper cleanup."""
        try:
            session = await self._create_palabra_session()
            self.palabra_session_id = session['data']['id']
            ws_url = session['data']['ws_url']
            publisher = session['data']['publisher']
            url = f'{ws_url}?token={publisher}'

            self.palabra_ws = await websockets.connect(url, ping_interval=3, ping_timeout=60)
            logger.info('Palabra websocket connected for role %s', self.role)
            await self.send({'message_type': 'set_task', 'data': self.settings})

            self._running = True
            self._palabra_receive_task = asyncio.create_task(self._receive_from_palabra())
            self._twilio_receive_task = asyncio.create_task(self._receive_from_twilio())
            self._sender_task = asyncio.create_task(self._sender())

            await asyncio.gather(
                self._palabra_receive_task,
                self._twilio_receive_task,
                self._sender_task,
                return_exceptions=True,
            )
        except Exception as e:
            logger.warning('WebSocket run error: %s', e)
        finally:
            await self.close()

    async def _receive_from_twilio(self):
        """Receive audio data from Twilio and send it to the Palabra API."""
        buffer = bytearray()
        buffer_size = int(8_000 * 0.320)  # 320 ms of mulaw chunks

        try:
            async for message in self.source_ws.iter_text():
                if not self._running:
                    break

                data = json.loads(message)
                if data['event'] == 'media':
                    audio_data = data['media']['payload']
                    audio_data = base64.b64decode(audio_data)
                    buffer += audio_data

                    audio_data = convert_mulaw_to_pcm(audio_data)
                    self.original_audio_queue.put_nowait(audio_data)

                    if len(buffer) >= buffer_size:
                        chunk = buffer[:buffer_size]
                        buffer = buffer[buffer_size:]

                        try:
                            audio_data = await self.app.process_managers['mulaw_to_pcm'].submit(chunk)
                            message = {
                                'message_type': 'input_audio_data',
                                'data': {'data': base64.b64encode(audio_data).decode('utf-8')},
                            }
                            await self.send(message)
                        except Exception as e:
                            logger.error(f'Audio conversion error: {e!r}')
                elif data['event'] == 'start':
                    stream_sid = data['start']['streamSid']
                    if self.role == 'client':
                        logger.info(f'Incoming client stream has started {stream_sid}')
                        self.call_session.client_stream_sid = stream_sid
                        self.call_session.client_stream_sid_event.set()
                    else:
                        logger.info(f'Incoming operator stream has started {stream_sid}')
                        self.call_session.operator_stream_sid = stream_sid
                        self.call_session.operator_stream_sid_event.set()
        except WebSocketDisconnect:
            logger.info('Client disconnected.')
        except Exception as e:
            logger.error(f'Error in _receive_from_twilio: {e}')
        finally:
            # Process remaining buffer data
            if buffer and self._running:
                try:
                    audio_data = await self.app.process_managers['mulaw_to_pcm'].submit(bytes(buffer))
                    # audio_data = await convert_mulaw_to_pcm(bytes(buffer))
                    message = {
                        'message_type': 'input_audio_data',
                        'data': {'data': base64.b64encode(audio_data).decode('utf-8')},
                    }

                    for i in range(0, len(audio_data), self.block_size):
                        self.original_audio_queue.put_nowait(audio_data[i : i + self.block_size])

                    await self.send(message)
                except Exception as e:
                    logger.error(f'Error processing remaining buffer: {e}')

    async def _receive_from_palabra(self):
        """Receive loop with proper error handling and cleanup."""

        while self.palabra_ws:
            try:
                msg = await asyncio.wait_for(self.palabra_ws.recv(), timeout=60)
                data = json.loads(msg)
                if isinstance(data.get('data'), str):
                    data['data'] = json.loads(data['data'])

                msg_type = data.get('message_type')
                if msg_type == 'current_task':
                    logger.info('Task confirmed')
                elif msg_type == 'output_audio_data':
                    # Handle TTS audio
                    transcription_data = data.get('data', {})
                    audio_b64 = transcription_data.get('data', '')

                    if audio_b64:
                        try:
                            audio_data = base64.b64decode(audio_b64)

                            for i in range(0, len(audio_data), self.block_size):
                                self.translated_audio_queue.put_nowait(audio_data[i : i + self.block_size])
                        except Exception as e:
                            logger.error(f'Audio decode error: {e!r}')
                elif 'transcription' in msg_type:
                    transcription = data.get('data', {}).get('transcription', {})
                    text = transcription.get('text', '')
                    lang = transcription.get('language', '')

                    if text:
                        if msg_type == 'translated_transcription':
                            # Replace content with original and translation
                            await broadcast_transcription(
                                self.role, self.last_original_transcription, text, self.last_language, 'replace'
                            )
                            self.last_original_transcription = ''
                            self.last_language = ''

                        elif msg_type == 'partial_transcription':
                            if not self.last_original_transcription:
                                action = 'new'
                            else:
                                action = 'update'

                            self.last_original_transcription = text
                            self.last_language = lang
                            await broadcast_transcription(self.role, text, '', lang, action)

                        elif msg_type == 'validated_transcription':
                            # Update current div
                            self.last_original_transcription = text
                            self.last_language = lang
                            await broadcast_transcription(self.role, text, '', lang, 'update')
            except websockets.exceptions.ConnectionClosed:
                logger.info('WebSocket connection closed')
                break
            except asyncio.TimeoutError:
                logger.info('WebSocket receive timeout')
                continue
            except Exception as e:
                logger.error(f'WebSocket error: {e}')
                break

    async def _sender(self):
        await self.call_session.client_stream_sid_event.wait()
        await self.call_session.operator_stream_sid_event.wait()

        while True:
            try:
                original_chunk = await self.original_audio_queue.get()

                try:
                    translated_chunk = self.translated_audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    translated_chunk = None

                audio_data = await self.app.process_managers['mixer'].submit(
                    {
                        'chunk1': original_chunk,
                        'chunk2': translated_chunk,
                        'vol_a': 0.3,
                        'vol_b': 0.7,
                    }
                )

                audio_payload = base64.b64encode(audio_data).decode('utf-8')
                stream_sid = (
                    self.call_session.operator_stream_sid
                    if self.role == 'client'
                    else self.call_session.client_stream_sid
                )
                assert stream_sid is not None, 'streamSid must be set'

                audio_delta = {
                    'event': 'media',
                    'streamSid': stream_sid,
                    'media': {
                        'payload': audio_payload,
                    },
                }
                if self.target_ws.client_state == WebSocketState.DISCONNECTED:
                    logger.info('target speaker was disconnected')
                    await self.close()
                    break

                await self.target_ws.send_json(audio_delta)
            except Exception as e:
                logger.error('Failed during sender: %s', e)

    async def send(self, message: dict):
        """Send message with proper connection state checking."""
        if self.palabra_ws:
            try:
                await self.palabra_ws.send(json.dumps(message))
            except Exception as e:
                logger.error('Error sending message: %s', e)
                await self.close()
        else:
            raise RuntimeError('impossible')

    async def close(self):
        """Proper cleanup of all resources."""
        async with self._cleanup_lock:
            if not self._running:
                return

            self._running = False

            # Cancel running tasks
            if self._palabra_receive_task and not self._palabra_receive_task.done():
                self._palabra_receive_task.cancel()
                try:
                    await self._palabra_receive_task
                except asyncio.CancelledError:
                    pass

            if self._twilio_receive_task and not self._twilio_receive_task.done():
                self._twilio_receive_task.cancel()
                try:
                    await self._twilio_receive_task
                except asyncio.CancelledError:
                    pass

            # Close WebSocket connections
            if self.palabra_ws:
                await self.send(
                    {
                        'message_type': 'end_task',
                        'data': {'force': False},
                    }
                )

                try:
                    await self.palabra_ws.close()
                except Exception as e:
                    logger.error('Error closing Palabra WebSocket: %s', e)

            # Delete Palabra session
            await self._delete_palabra_session()

            logger.info('WebSocket connections closed')
