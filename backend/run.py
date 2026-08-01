"""Local development server -- ADR-020.

The event loop has to be chosen at the process entry point: uvicorn creates it
before it imports the application, so no amount of setup inside `app` can
change it. On Windows the default is a ProactorEventLoop, which psycopg's async
mode (ADR-018) cannot use.

    cd backend
    python run.py                 # http://127.0.0.1:8000
    python run.py --reload        # auto-restart on edit
    python run.py --port 9000

On Linux -- where this deploys (Ch. 23) -- SelectorEventLoop is already the
default and `uvicorn app.main:app` works directly. This module exists for
parity, not because production needs it.
"""

import argparse
import asyncio
import sys

import uvicorn

APP = "app.main:app"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FLARE development server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on source changes")
    args = parser.parse_args()

    if args.reload:
        # Reload runs the server in a supervised subprocess, and uvicorn already
        # selects a SelectorEventLoop for that mode on Windows. The startup
        # guard in app.main verifies that rather than trusting it.
        uvicorn.run(APP, host=args.host, port=args.port, reload=True)
        return

    server = uvicorn.Server(uvicorn.Config(APP, host=args.host, port=args.port))

    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        server.run()


if __name__ == "__main__":
    main()
