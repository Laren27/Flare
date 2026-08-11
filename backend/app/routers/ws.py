"""Real-time channel -- `WS /ws/{user_id}` (Ch. 14, Ch. 16).

Authentication happens in the first frame, not the URL. Browsers cannot set an
`Authorization` header on a WebSocket handshake, and the usual workaround --
`?token=...` -- writes a bearer credential into every access log, proxy log and
browser history entry it passes through. Instead the socket is accepted, the
client must send `{"type": "auth", "token": "..."}` within AUTH_TIMEOUT_SECONDS,
and anything else closes the connection (ADR-022).

The path `user_id` is not trusted on its own: it must match the `sub` of the
presented token, or the connection is refused. Without that check the endpoint
as specified in Chapter 14 would let any authenticated user receive another
user's alerts.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.services import auth as auth_service
from app.services.websocket_manager import registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

AUTH_TIMEOUT_SECONDS = 5.0
AUTH_MESSAGE_TYPE = "auth"


async def authenticate(websocket: WebSocket, user_id: int) -> bool:
    """Consume the first frame and verify it. Closes the socket on any failure."""
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="auth timeout")
        return False
    except (WebSocketDisconnect, ValueError):
        return False

    if not isinstance(message, dict) or message.get("type") != AUTH_MESSAGE_TYPE:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="auth frame expected")
        return False

    try:
        claims = auth_service.decode_access_token(str(message.get("token", "")))
    except auth_service.InvalidToken:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return False

    if claims.user_id != user_id:
        # Refusing the mismatch is the whole reason this check exists.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="token/path mismatch")
        return False

    return True


@router.websocket("/ws/{user_id}")
async def realtime_channel(websocket: WebSocket, user_id: int) -> None:
    await websocket.accept()

    if not await authenticate(websocket, user_id):
        return

    await registry.connect(user_id, websocket)
    await websocket.send_json({"type": "auth_ok", "user_id": user_id})
    logger.info("user %s connected", user_id)

    try:
        # Nothing is read from responders yet -- accept and decline are HTTP
        # endpoints in week 4. The loop exists to keep the socket open and to
        # notice the disconnect.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        registry.disconnect(user_id, websocket)
        logger.info("user %s disconnected", user_id)
