#!/usr/bin/env python3
"""Audio visualizer using CAVA and WebSocket."""

import asyncio
import os
import subprocess
import signal
import sys
from pathlib import Path

import websockets

CAVA_FIFO = "/tmp/cava.fifo"
CAVA_CONFIG = "/app/cava-config"
WS_PORT = int(os.environ.get("VISUALIZER_WS_PORT", "8081"))

clients: set = set()
cava_process = None


async def broadcast(data: str) -> None:
    """Send data to all connected WebSocket clients."""
    if clients:
        await asyncio.gather(
            *[client.send(data) for client in clients],
            return_exceptions=True
        )


async def read_cava() -> None:
    """Read CAVA output from FIFO and broadcast to clients."""
    # Create FIFO if it doesn't exist
    fifo_path = Path(CAVA_FIFO)
    if not fifo_path.exists():
        os.mkfifo(CAVA_FIFO)

    # Start CAVA
    global cava_process
    cava_process = subprocess.Popen(
        ["cava", "-p", CAVA_CONFIG],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print(f"CAVA started (PID: {cava_process.pid})")

    # Open FIFO for reading (non-blocking via asyncio)
    loop = asyncio.get_event_loop()

    while True:
        try:
            # Open FIFO - this blocks until CAVA writes
            with open(CAVA_FIFO, "r") as fifo:
                while True:
                    line = await loop.run_in_executor(None, fifo.readline)
                    if not line:
                        break  # FIFO closed, reopen

                    # CAVA outputs semicolon-separated values
                    # Format: "val1;val2;val3;...;\n"
                    values = line.strip().rstrip(";")
                    if values:
                        await broadcast(values)
        except FileNotFoundError:
            # FIFO not ready yet, wait
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error reading CAVA: {e}")
            await asyncio.sleep(1)


async def websocket_handler(websocket) -> None:
    """Handle WebSocket connections."""
    clients.add(websocket)
    remote = websocket.remote_address
    print(f"Client connected: {remote}")

    try:
        async for _ in websocket:
            # We don't expect messages from clients, just keep connection alive
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"Client disconnected: {remote}")


async def main() -> None:
    """Start WebSocket server and CAVA reader."""
    print(f"Starting audio visualizer on port {WS_PORT}")

    # Start WebSocket server
    async with websockets.serve(websocket_handler, "0.0.0.0", WS_PORT):
        # Start CAVA reader
        await read_cava()


def cleanup(signum, frame) -> None:
    """Clean up on exit."""
    global cava_process
    if cava_process:
        cava_process.terminate()
        cava_process.wait()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup(None, None)
