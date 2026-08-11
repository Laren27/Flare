"""A single synthetic WebSocket responder -- ADR-016.

Logs in over HTTP, opens the real-time channel, completes the first-frame
authentication of ADR-022, and prints every alert it receives. Importable as
well as runnable: `sim/scenarios/` drives many of these concurrently, which is
what makes the ADR-010 concurrency claim provable at all -- no human can produce
a sub-50ms acceptance race by hand.

    python sim/responder_client.py --phone +919900000000
    python sim/responder_client.py --all --limit 20
"""

import argparse
import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# websockets: the client half of the protocol uvicorn already speaks server-side.
# Needed because ADR-016 makes synthetic responders core scope, and a synthetic
# responder is by definition a WebSocket client.
import websockets

DEFAULT_API = "http://127.0.0.1:8000"
PASSWORD = "sim-responder-pw"


def login(api: str, phone: str, password: str = PASSWORD) -> str:
    request = urllib.request.Request(f"{api}/auth/login", method="POST")
    request.add_header("Content-Type", "application/json")
    body = json.dumps({"phone": phone, "password": password}).encode()
    try:
        with urllib.request.urlopen(request, body) as response:
            return json.load(response)["access_token"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"login failed for {phone}: {exc.code} {exc.read().decode()}") from exc


def me(api: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(f"{api}/auth/me")
    request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


@dataclass
class SyntheticResponder:
    """One connected responder. Records what it receives so scenarios can assert."""

    phone: str
    api: str = DEFAULT_API
    label: str = ""
    user_id: int | None = None
    alerts: list[dict[str, Any]] = field(default_factory=list)
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    verbose: bool = True

    @property
    def ws_url(self) -> str:
        base = self.api.replace("http://", "ws://").replace("https://", "wss://")
        return f"{base}/ws/{self.user_id}"

    async def run(self, stop: asyncio.Event | None = None) -> None:
        """Connect, authenticate, then receive until told to stop."""
        loop = asyncio.get_running_loop()
        # urllib is blocking; keep it off the event loop so many responders can
        # start concurrently rather than serialising on each other's logins.
        token = await loop.run_in_executor(None, login, self.api, self.phone)
        profile = await loop.run_in_executor(None, me, self.api, token)
        self.user_id = profile["id"]
        self.label = self.label or profile["name"]

        async with websockets.connect(self.ws_url) as socket:
            await socket.send(json.dumps({"type": "auth", "token": token}))

            ack = json.loads(await socket.recv())
            if ack.get("type") != "auth_ok":
                raise RuntimeError(f"{self.label}: authentication refused: {ack}")

            self.connected.set()
            if self.verbose:
                print(f"  [{self.label}] connected as user {self.user_id}")

            await self._receive_until(socket, stop)

    async def _receive_until(self, socket, stop: asyncio.Event | None) -> None:
        while True:
            if stop is not None and stop.is_set():
                return
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=0.25)
            except TimeoutError:
                continue
            except websockets.ConnectionClosed:
                return

            message = json.loads(raw)
            if message.get("type") == "sos_alert":
                self.alerts.append(message)
                if self.verbose:
                    print(
                        f"  [{self.label}] ALERT sos={message['sos_id']} "
                        f"{message['distance_m']}m wave={message['wave_number']} "
                        f"desc={message.get('description')!r}"
                    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic responder clients.")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--phone", help="single responder to connect as")
    parser.add_argument("--all", action="store_true", help="connect every seeded responder")
    parser.add_argument("--limit", type=int, default=10, help="cap for --all")
    args = parser.parse_args()

    if args.all:
        phones = [f"+9199{index:06d}" for index in range(args.limit)]
    elif args.phone:
        phones = [args.phone]
    else:
        parser.error("pass --phone or --all")

    responders = [SyntheticResponder(phone=phone, api=args.api) for phone in phones]
    print(f"connecting {len(responders)} responder(s); Ctrl-C to stop")

    try:
        await asyncio.gather(*(r.run() for r in responders))
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    asyncio.run(main())
