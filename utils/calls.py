import asyncio
import logging
import os
import uuid

from fastapi import HTTPException, Request
from starlette.websockets import WebSocket
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Play, VoiceResponse

from settings import host


class CallSession:
    def __init__(self, source_phone_number: str, target_phone_number: str):
        self.session_id = str(uuid.uuid4())
        self.source_websocket: WebSocket | None = None
        self.target_websocket: WebSocket | None = None
        self.source_phone_number = source_phone_number
        self.target_phone_number = target_phone_number
        self.barrier = asyncio.Barrier(2)
        self.client_stream_sid = None
        self.operator_stream_sid = None
        self.client_sid = None
        self.operator_sid = None
        self.client_stream_sid_event = asyncio.Event()
        self.operator_stream_sid_event = asyncio.Event()
        self.completed = False

        self._intermediate_number = os.getenv('TWILIO_NUMBER')


def get_free_operator_number() -> str:
    return os.getenv('OPERATOR_NUMBER')


async def make_call_to_operator(twilio_client: Client, session: CallSession):
    twiml_response = VoiceResponse()
    twiml_response.say('Please wait for connection')
    twiml_response.append(Play('https://api.twilio.com/cowbell.mp3', loop=1))

    call = await twilio_client.calls.create_async(
        to=session.target_phone_number,
        from_=session._intermediate_number,
        twiml=str(twiml_response),
        status_callback=f'https://{host}/voice/callback/{session.session_id}',
        status_callback_event=['answered'],
        status_callback_method='POST',
    )

    logging.info(f'Call SID to operator: {call.sid}')


async def verify_twilio_signature(request: Request):
    validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))
    signature = request.headers.get('X-Twilio-Signature', '')
    payload = await request.form()

    if not validator.validate(str(request.url), payload, signature):
        raise HTTPException(status_code=403, detail='Invalid Twilio signature')
