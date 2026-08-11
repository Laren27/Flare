"""In-memory registry of live WebSocket connections (Ch. 16).

Maps `user_id -> active connection`. On disconnect the entry is cleared; on
reconnect it is replaced. Deliberately process-local: a production deployment
across multiple instances would need Redis pub/sub, which Chapter 26 names as
Future Scope rather than building here (Rule 004).

The consequence is stated rather than hidden: with more than one worker process,
a responder connected to worker A is invisible to a dispatch running on worker B,
and would be recorded as `no_socket`. The demo runs a single worker.
"""

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionRegistry:
    def __init__(self) -> None:
        self._connections: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Register a socket, replacing any previous one for this user.

        A reconnect before the old socket was reaped would otherwise leave the
        stale entry in place and deliver alerts into a dead connection.
        """
        existing = self._connections.get(user_id)
        if existing is not None and existing is not websocket:
            logger.info("replacing existing connection for user %s", user_id)
            try:
                await existing.close(code=1000)
            except RuntimeError:
                # Already closed from the other end; nothing to clean up.
                pass

        self._connections[user_id] = websocket

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Clear the entry, but only if it still points at this socket.

        Guards the reconnect race: if a newer socket has already replaced this
        one, a late disconnect from the old socket must not evict the new entry.
        """
        if self._connections.get(user_id) is websocket:
            del self._connections[user_id]

    def is_connected(self, user_id: int) -> bool:
        return user_id in self._connections

    @property
    def connected_user_ids(self) -> set[int]:
        return set(self._connections)

    async def send(self, user_id: int, payload: dict[str, Any]) -> bool:
        """Attempt delivery. Returns whether the payload actually went out.

        A failed send drops the connection from the registry -- the socket is
        demonstrably unusable, and leaving it registered would make every
        subsequent dispatch think this responder is reachable.
        """
        websocket = self._connections.get(user_id)
        if websocket is None:
            return False

        try:
            await websocket.send_json(payload)
            return True
        except Exception:
            logger.warning("send failed for user %s; dropping connection", user_id)
            self.disconnect(user_id, websocket)
            return False


# One registry per process, which is the whole design (Ch. 16).
registry = ConnectionRegistry()
