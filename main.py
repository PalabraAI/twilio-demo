import logging
import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.websockets import WebSocket, WebSocketDisconnect
from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, Play, VoiceResponse

from bridge import AudioBridge
from settings import host, role_settings
from transcription import transcription_websockets
from utils.audio import BaseWorkerProcess, MixingWorker, MulawToPcmWorker
from utils.calls import CallSession, get_free_operator_number, make_call_to_operator, verify_twilio_signature
from utils.worker import AsyncProcessManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('twilio').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app) -> None:
    app.process_managers: dict[str, BaseWorkerProcess] = {}
    app.process_managers['mixer'] = AsyncProcessManager(MixingWorker, processes=2)
    app.process_managers['mulaw_to_pcm'] = AsyncProcessManager(MulawToPcmWorker, processes=2)
    app.http_client = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(keepalive_timeout=300),
        headers={
            'ClientId': os.getenv('PALABRA_CLIENT_ID'),
            'ClientSecret': os.getenv('PALABRA_CLIENT_SECRET'),
        },
    )
    app.twilio_client = Client(
        os.getenv('TWILIO_ACCOUNT_SID'),
        os.getenv('TWILIO_AUTH_TOKEN'),
        http_client=AsyncTwilioHttpClient(timeout=300),
    )
    app.twilio_validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))

    try:
        yield
    finally:
        for manager in app.process_managers.values():
            await manager.close()

        await app.http_client.close()
        await app.twilio_client.http_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title='Twilio demo',
        version='0.0.1',
        redoc_url=None,
        docs_url='/demo/docs',
        openapi_url='/demo/openapi.json',
        lifespan=lifespan,
    )

    app.mount('/static', StaticFiles(directory='static'), name='static')
    app.templates = Jinja2Templates(directory='templates')
    api_router = APIRouter(prefix='/demo')
    app.include_router(api_router)

    return app


app = create_app()
session_store: dict[str, CallSession] = {}


@app.post('/twiml/client', dependencies=[Depends(verify_twilio_signature)])
async def twiml_handler(request: Request):
    form_data = await request.form()
    from_number = form_data.get('From')
    session = CallSession(from_number, get_free_operator_number())
    session.client_sid = form_data.get('CallSid')
    session_store[session.session_id] = session

    await make_call_to_operator(app.twilio_client, session)

    twiml_response = VoiceResponse()
    twiml_response.say('Please wait for connection')
    twiml_response.append(Play('https://api.twilio.com/cowbell.mp3', loop=1))

    return Response(content=str(twiml_response), media_type='application/xml')


@app.post('/voice/callback/{session_id}', dependencies=[Depends(verify_twilio_signature)])
async def voice_callback(request: Request, session_id: str):
    """Handle outbound target language calls"""
    form_data = await request.form()
    call_sid = form_data.get('CallSid')
    from_number = form_data.get('From')
    to_number = form_data.get('To')
    call_status = form_data.get('CallStatus')

    logging.info(f'Outbound target call from {from_number} to {to_number} with SID: {call_sid}, Status: {call_status}')
    if call_status != 'in-progress':
        raise HTTPException(
            status_code=500,
            detail=f'Call with SID {call_sid} has unexpected status: {call_status}',
        )

    call_session = session_store.get(session_id)
    if not call_session:
        raise HTTPException(
            status_code=404,
            detail=f'Call session with ID {session_id} was not found',
        )

    call_session.operator_sid = call_sid

    twiml_client_response = VoiceResponse()
    connect = Connect(
        action=f'https://{host}/voice/disconnect/client/{session_id}',
    )
    connect.stream(url=f'wss://{host}/voice/client/{session_id}')
    twiml_client_response.append(connect)

    twiml_operator_response = VoiceResponse()
    connect = Connect(
        action=f'https://{host}/voice/disconnect/operator/{session_id}',
    )
    connect.stream(url=f'wss://{host}/voice/operator/{session_id}')
    twiml_operator_response.append(connect)

    # Both client and operator are successfully connected to the Twilio, so start streaming
    await app.twilio_client.calls(call_session.client_sid).update_async(twiml=str(twiml_client_response))
    await app.twilio_client.calls(call_session.operator_sid).update_async(twiml=str(twiml_operator_response))

    return Response(status_code=200)


@app.post('/voice/disconnect/{role}/{session_id}', dependencies=[Depends(verify_twilio_signature)])
async def voice_disconnect(request: Request, role: str, session_id: str):
    """Handle call termination."""

    call_session = session_store.get(session_id)
    if not call_session:
        raise HTTPException(
            status_code=404,
            detail=f'Call session with ID {session_id} was not found',
        )

    if call_session.completed:
        del session_store[session_id]
        return Response(status_code=200)

    if role == 'client':
        await app.twilio_client.calls(call_session.operator_sid).update_async(status='completed')
    else:
        await app.twilio_client.calls(call_session.client_sid).update_async(status='completed')

    call_session.completed = True
    return Response(status_code=200)


@app.websocket('/voice/{role}/{session_id}')
async def handle_media_stream(websocket: WebSocket, role: str, session_id: str):
    """Handle WebSocket connections between Twilio and OpenAI."""

    call_session = session_store.get(session_id)

    if call_session is None:
        raise HTTPException(
            status_code=404,
            detail=f'Call session with ID {session_id} was not found',
        )

    if role == 'client':
        call_session.source_websocket = websocket
    else:
        call_session.target_websocket = websocket

    logging.info(f'{role} connected')
    await websocket.accept()

    # Wait shortly until streaming starts for both speakers
    await call_session.barrier.wait()

    assert call_session.target_websocket is not None, 'Target websocket must be set'
    assert call_session.source_websocket is not None, 'Source websocket must be set'

    bridge = AudioBridge(app, call_session, role, role_settings[role])
    await bridge.run()
    await bridge.close()


@app.get('/transcription', response_class=HTMLResponse)
async def transcription_page(request: Request):
    """Real-time transcription display page"""
    return app.templates.TemplateResponse(name='transcription.html', request=request)


@app.websocket('/transcription-ws')
async def transcription_websocket(websocket: WebSocket):
    """WebSocket used to deliver transcriptions to the web interface"""

    await websocket.accept()
    transcription_websockets.add(websocket)

    try:
        # Hold open connection
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        transcription_websockets.discard(websocket)
    except Exception as e:
        logging.error(f'Error in transcription WebSocket: {e}')
        transcription_websockets.discard(websocket)


def main():
    uvicorn.run(
        app,
        host='0.0.0.0',
        loop='uvloop',
        port=int(os.getenv('PORT')),
    )


if __name__ == '__main__':
    main()
