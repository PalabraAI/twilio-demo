import asyncio
import logging

from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


transcription_websockets: set[WebSocket] = set()


async def broadcast_transcription(role: str, original_text: str, translated_text: str, lang: str, action: str):
    """Sends the transcription to all connected web clients."""
    message = {
        'type': 'transcription',
        'role': role,
        'original_text': original_text,
        'translated_text': translated_text,
        'original_language': lang,
        'action': action,  # One of "update", "replace", "new"
        'timestamp': asyncio.get_event_loop().time(),
    }

    disconnected_websockets = set()
    for ws in transcription_websockets:
        try:
            await ws.send_json(message)
        except Exception as e:
            logging.error(f'Error sending transcription to web client: {e}')
            disconnected_websockets.add(ws)

    # Remove disconnected clients
    transcription_websockets.difference_update(disconnected_websockets)
