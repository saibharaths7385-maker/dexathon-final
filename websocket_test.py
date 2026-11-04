import asyncio
import json
import os

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException


URL = os.getenv("LAPTOP1_TELEMETRY_WS_URL")
HANDSHAKE = {"type": "hello", "client": "skynex-3d", "protocol": 1}
LISTEN_SECONDS = 15
DISPLAY_FIELDS = ("flight", "propulsion", "environment", "faults", "mission")


def print_received_frame(frame: str | bytes) -> None:
    print("\nSIMULATED DEMO DATA — received WebSocket frame:")
    if isinstance(frame, bytes):
        print(f"Raw frame (bytes): {frame!r}")
    else:
        print(f"Raw frame: {frame}")

    try:
        message = json.loads(frame)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"Invalid JSON: {error}")
        return

    print("Parsed JSON:")
    print(json.dumps(message, indent=2, ensure_ascii=False))

    if isinstance(message, dict):
        for field in DISPLAY_FIELDS:
            if field in message:
                print(f"{field}: {json.dumps(message[field], ensure_ascii=False)}")


async def run_test() -> None:
    if not URL:
        raise RuntimeError(
            "Set LAPTOP1_TELEMETRY_WS_URL to Laptop 1's current Protocol 1 WebSocket URL."
        )
    print(f"SIMULATED DEMO DATA — connecting to {URL}")

    try:
        async with websockets.connect(URL) as websocket:
            await websocket.send(json.dumps(HANDSHAKE))
            print("SIMULATED DEMO DATA — handshake sent.")

            loop = asyncio.get_running_loop()
            deadline = loop.time() + LISTEN_SECONDS
            print(f"SIMULATED DEMO DATA — listening for {LISTEN_SECONDS} seconds.")

            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break

                try:
                    frame = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                except TimeoutError:
                    break
                except ConnectionClosed as error:
                    print(
                        "SIMULATED DEMO DATA — connection closed while listening: "
                        f"code={error.code}, reason={error.reason or 'not provided'}"
                    )
                    break

                print_received_frame(frame)

            print("SIMULATED DEMO DATA — 15-second listening period ended.")
    except (OSError, WebSocketException, TimeoutError) as error:
        print(f"SIMULATED DEMO DATA — WebSocket connection error: {error}")


if __name__ == "__main__":
    asyncio.run(run_test())
