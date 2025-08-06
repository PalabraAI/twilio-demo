import asyncio
import base64
import copy
import json
import logging
import os
import queue
import uuid
from contextlib import asynccontextmanager

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, APIRouter, Request, Response
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('twilio').setLevel(logging.WARNING)


def create_app() -> FastAPI:
    app =  FastAPI(
        title="Twilio demo",
        version="0.0.1",
        redoc_url=None,
        debug=True,
        docs_url="/demo/docs",
        openapi_url=f"/demo/openapi.json",
    )
    api_router = APIRouter(prefix="/demo")
    app.include_router(api_router)

    return app


app = create_app()
client_settings = {
    "input_stream": {
        "content_type": "audio",
        "source": {
            "type": "ws",
            "format": "pcm_s16le",
            "sample_rate": 24_000,
            "channels": 1,
        },
    },
    "output_stream": {
        "content_type": "audio",
        "target": {"type": "ws", "format": "pcm_s16le", "sample_rate": 24_000, "channels": 1},
    },
    "pipeline": {
        "preprocessing": {},
        "transcription": {
            "source_language": "en",
            "detectable_languages": ["ru", "en"],
            "asr_model": "auto",
            "segment_confirmation_silence_threshold": 0.7,
              "sentence_splitter": {
                "enabled": True,
              },
            "verification": {
                "auto_transcription_correction": False,
                "transcription_correction_style": None,
            },
        },
        "translations": [
            {
                "target_language": "ru",
                "translate_partial_transcriptions": False,
            },
        ],
    },
}
operator_settings = copy.deepcopy(client_settings)
operator_settings["pipeline"]["translations"][0]["target_language"] = "en"
operator_settings["pipeline"]["transcription"]["source_language"] = "ru"

host = 'reduces-obesity-brochure-scenic.trycloudflare.com'


async def create_session(client_id: str, client_secret: str) -> dict:
    url = "https://api.palabra.ai/session-storage/session"
    headers = {"ClientId": client_id, "ClientSecret": client_secret}
    payload = {"data": {"subscriber_count": 0, "publisher_can_subscribe": True}}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


async def convert_mulaw_to_pcm(input_bytes: bytes) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-f", "mulaw",           # формат входа
        "-ar", "8000",           # sample rate входа
        "-ac", "1",              # mono вход
        "-i", "pipe:0",          # stdin
        "-f", "s16le",           # формат выхода (raw PCM)
        "-ar", "24000",          # sample rate выхода
        "-ac", "1",              # mono выход
        "pipe:1",                # stdout
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL  # можно временно отключить для тишины
    )

    stdout_data, _ = await process.communicate(input=input_bytes)

    if process.returncode != 0:
        raise RuntimeError("ffmpeg conversion failed")

    return stdout_data


async def convert_pcm_to_mulaw(input_bytes: bytes) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-f", "s16le",           # raw PCM input
        "-ar", "24000",          # исходный sample rate
        "-ac", "1",              # mono
        "-i", "pipe:0",          # stdin
        "-f", "mulaw",           # формат вывода
        "-ar", "8000",           # выходной sample rate
        "-ac", "1",              # mono
        "pipe:1",                # stdout
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )

    stdout_data, _ = await process.communicate(input=input_bytes)

    if process.returncode != 0:
        raise RuntimeError("ffmpeg reverse conversion failed")

    return stdout_data


class SimpleWebSocket:
    client_sid = None
    operator_sid = None

    def __init__(self, url: str, token: str, call_session, settings: dict, role: str):
        self.url = f"{url}?token={token}"
        self.ws = None
        self.call_session = call_session

        if role == 'client':
            self.source_ws = call_session.source_websocket
            self.target_ws = call_session.target_websocket
        else:
            self.source_ws = call_session.target_websocket
            self.target_ws = call_session.source_websocket
        self.settings = settings
        self.role = role

        self._palabra_receive_task = None
        self._twilio_receive_task = None
        self._running = False
        self._cleanup_lock = asyncio.Lock()

    async def run(self):
        """Run the WebSocket connection with proper cleanup."""
        try:
            self.ws = await websockets.connect(self.url, ping_interval=5, ping_timeout=30)
            # print("🔌 WebSocket connected")

            await self.send({"message_type": "set_task", "data": self.settings})
            await asyncio.sleep(3)

            self._running = True
            self._palabra_receive_task = asyncio.create_task(self._receive_from_palabra())
            self._twilio_receive_task = asyncio.create_task(self._receive_from_twilio())

            await asyncio.gather(
                self._palabra_receive_task, 
                self._twilio_receive_task,
                return_exceptions=True
            )
        except Exception as e:
            print(f"WebSocket run error: {e}")
        finally:
            await self.close()

    async def _receive_from_twilio(self):
        """Receive audio data from Twilio and send it to the Palabra API."""
        buffer = bytearray()
        buffer_size = int(8_000 * 0.320)

        try:
            async for message in self.source_ws.iter_text():
                if not self._running:
                    break
                    
                data = json.loads(message)
                # print("Received data from Twilio", data)
                if data['event'] == 'media':
                    audio_data = data['media']['payload']
                    audio_data = base64.b64decode(audio_data)
                    buffer += audio_data

                    if len(buffer) >= buffer_size:
                        chunk = buffer[:buffer_size]
                        buffer = buffer[buffer_size:]

                        try:
                            audio_data = await convert_mulaw_to_pcm(chunk)
                            message = {
                                "message_type": "input_audio_data",
                                "data": {"data": base64.b64encode(audio_data).decode("utf-8")},
                            }
                            await self.send(message)
                        except Exception as e:
                            print(f"Audio conversion error: {e}")
                elif data['event'] == 'start':
                    stream_sid = data['start']['streamSid']
                    if self.role == 'client':
                        print(f"Incoming client stream has started {stream_sid}")
                        self.call_session.client_sid = stream_sid
                    else:
                        print(f"Incoming operator stream has started {stream_sid}")
                        self.call_session.operator_sid = stream_sid
        except WebSocketDisconnect:
            print("Client disconnected.")
        except Exception as e:
            print(f"Error in _receive_from_twilio: {e}")
        finally:
            # Process remaining buffer data
            if buffer and self._running:
                try:
                    audio_data = await convert_mulaw_to_pcm(bytes(buffer))
                    message = {
                        "message_type": "input_audio_data",
                        "data": {"data": base64.b64encode(audio_data).decode("utf-8")},
                    }
                    await self.send(message)
                except Exception as e:
                    print(f"Error processing remaining buffer: {e}")

    async def _receive_from_palabra(self):
        """Receive loop with proper error handling and cleanup."""

        while self.ws:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=60)
                data = json.loads(msg)
                if isinstance(data.get("data"), str):
                    data["data"] = json.loads(data["data"])

                # print("*" * 80)
                # print(data)
                # print("*" * 80)

                msg_type = data.get("message_type")
                if msg_type == "current_task":
                    print("📝 Task confirmed")
                elif msg_type == "output_audio_data":
                    # Handle TTS audio
                    transcription_data = data.get("data", {})
                    audio_b64 = transcription_data.get("data", "")

                    if audio_b64:
                        try:
                            audio_data = base64.b64decode(audio_b64)
                            audio_data = await convert_pcm_to_mulaw(audio_data)

                            audio_payload = base64.b64encode(audio_data).decode('utf-8')

                            stream_sid = self.call_session.operator_sid if self.role == 'client' else self.call_session.client_sid

                            assert stream_sid is not None, "streamSid must be set"
                            logging.info(f"Sending data from {self.role} with stream sid {stream_sid}")

                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload,
                                }
                            }

                            # if self.target_ws.client_state == WebSocketState.DISCONNECTED:
                            #     break
                            print("Sending data to Twilio")
                            await self.target_ws.send_json(audio_delta)
                        except Exception as e:
                            print(f"Audio decode error: {e!r}")
                elif "transcription" in msg_type:
                    transcription = data.get("data", {}).get("transcription", {})
                    text = transcription.get("text", "")
                    lang = transcription.get("language", "")
                    if text:
                        part = msg_type == "partial_transcription"
                        print(
                            f"\r\033[K{'💬' if part else '✅'} [{lang}] {text}",
                            end="" if part else "\n",
                            flush=True,
                        )
            except websockets.exceptions.ConnectionClosed:
                print("📡 WebSocket connection closed")
                break
            except asyncio.TimeoutError:
                print("📡 WebSocket receive timeout")
                continue
            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                break

    async def send(self, message: dict):
        """Send message with proper connection state checking."""
        if self.ws:
            try:
                await self.ws.send(json.dumps(message))
            except Exception as e:
                print(f"Error sending message: {e}")
                await self.close()

    async def close(self):
        """Proper cleanup of all resources."""
        async with self._cleanup_lock:
            if not self._running:
                return

            # TODO: set end task

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
            if self.ws:
                try:
                    await self.ws.close()
                except Exception as e:
                    print(f"Error closing Palabra WebSocket: {e}")
                    
            if self.twilio_ws:
                try:
                    await self.twilio_ws.close()
                except Exception as e:
                    print(f"Error closing Twilio WebSocket: {e}")
                    
            print("🔌 WebSocket connections closed")


class CallSession:
    def __init__(self, source_phone_number: str, target_phone_number: str):
        self.session_id = str(uuid.uuid4())
        self.target_call_sid: str | None = None  # Outbound call SID
        self.source_websocket: WebSocket | None = None  # Incoming caller's WebSocket
        self.target_websocket: WebSocket | None = None  # Outbound caller's WebSocket
        self.source_phone_number = source_phone_number  # Incoming caller's phone
        self.target_phone_number = target_phone_number  # Outbound caller's phone
        self.source_language = ""  # Default source language
        self.target_language = ""  # Default target language
        self.source_tts_provider = "ElevenLabs"  # Default source TTS provider
        self.source_voice = ""  # Default source voice
        self.target_tts_provider = "ElevenLabs"  # Default target TTS provider
        self.target_voice = ""  # Default target voice
        self.host = None  # Request host for WebSocket URLs
        self.play_waiting_music = True  # Flag to control waiting music
        self.connect = asyncio.Event()
        self.barrier = asyncio.Barrier(2)
        self.client_sid = None
        self.operator_sid = None

        self._intermediate_number = "+18584625392"


session_store: dict[str, CallSession] = {}

def _get_free_operator_number() -> str:
    return "+48503182422"


@app.api_route("/twiml/client", methods=["POST"])
async def twiml_handler(request: Request):
    form_data = await request.form()
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    session = CallSession(from_number, _get_free_operator_number())
    session_store[session.session_id] = session

    # TwiML ответ для A с Media Stream
    response = VoiceResponse()
    # response.start().stream(
    #     name="A",
    #     url=f"wss://9a80ca68f10b.ngrok-free.app/media-stream"
    # )
    connect = Connect()
    connect.stream(url=f'wss://{host}/voice/client/{session.session_id}')
    response.append(connect)

    # Запускаем вызов B с Media Stream
    # await make_call_to_b(session_id)

    return Response(content=str(response), media_type="application/xml")


async def make_call_to_operator(session: CallSession):
    http_client = AsyncTwilioHttpClient()
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), http_client=http_client)

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f'wss://{host}/voice/operator/{session.session_id}')
    response.append(connect)

    call = await client.calls.create_async(
        to=session.target_phone_number,
        from_=session._intermediate_number,
        twiml=str(response),
        status_callback=f"https://{host}/voice/callback/{session.session_id}",
        status_callback_event=["answered"],
        status_callback_method="POST",
    )

    logging.info(f"Call SID to B: {call.sid}")


@app.post("/voice/callback/{session_id}")
async def voice_callback(request: Request, session_id: str):
    """Handle outbound target language calls"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    call_status = form_data.get("CallStatus")

    logging.info(f"Outbound target call from {from_number} to {to_number} with SID: {call_sid}, Status: {call_status}")

    if call_status == "in-progress":
        call_session = session_store.get(session_id)

        if call_session:
            call_session.connect.set()

    return Response(status_code=200)


@app.websocket("/voice/{role}/{session_id}")
async def handle_media_stream(websocket: WebSocket, role: str, session_id: str):
    """Handle WebSocket connections between Twilio and OpenAI."""

    call_session = session_store.get(session_id)

    if call_session is None:
        logging.error(f"Session {session_id} not found!")
        return

    if role == "client":
        call_session.source_websocket = websocket
        await make_call_to_operator(call_session)
    else:
        call_session.target_websocket = websocket

    logging.info("Client connected")
    await websocket.accept()

    await call_session.connect.wait()
    await call_session.barrier.wait()

    session = await create_session(
        os.getenv("PALABRA_CLIENT_ID"), os.getenv("PALABRA_CLIENT_SECRET")
    )
    ws_url = session["data"]["ws_url"]
    publisher = session["data"]["publisher"]

    assert call_session.target_websocket is not None, "Target websocket must be set"
    assert call_session.source_websocket is not None, "Source websocket must be set"

    # Send settings and wait
    if role == 'client':
        ws = SimpleWebSocket(ws_url, publisher, call_session, client_settings, 'client')
    else:
        ws = SimpleWebSocket(ws_url, publisher, call_session, operator_settings, 'operator')

    await ws.run()
    await ws.close()


if __name__ == "__main__":
    # app = create_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        loop="uvloop",
        port=7839,
    )
