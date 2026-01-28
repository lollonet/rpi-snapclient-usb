#!/usr/bin/env python3
"""Audio visualizer using CAVA and WebSocket."""

import asyncio
import logging
import os
import subprocess
import signal
import sys
from pathlib import Path

import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CAVA_FIFO = "/tmp/cava.fifo"
CAVA_CONFIG = "/app/cava-config"
WS_PORT = int(os.environ.get("VISUALIZER_WS_PORT", "8081"))
MAX_CONSECUTIVE_ERRORS = 10

clients: set[websockets.WebSocketServerProtocol] = set()
cava_process: subprocess.Popen[bytes] | None = None
consecutive_errors = 0


async def broadcast(data: str) -> None:
    """Send data to all connected WebSocket clients."""
    if clients:
        await asyncio.gather(
            *[client.send(data) for client in clients],
            return_exceptions=True
        )


def _setup_cava() -> None:
    """Initialize CAVA process and FIFO"""
    global cava_process

    # Create FIFO if it doesn't exist
    fifo_path = Path(CAVA_FIFO)
    if not fifo_path.exists():
        os.mkfifo(CAVA_FIFO)

    # Start CAVA
    cava_process = subprocess.Popen(
        ["cava", "-p", CAVA_CONFIG],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    logger.info(f"CAVA started (PID: {cava_process.pid})")

async def _read_fifo_lines() -> str | None:
    """Read a single line from CAVA FIFO"""
    try:
        loop = asyncio.get_event_loop()
        with open(CAVA_FIFO, "r") as fifo:
            while True:
                line = await loop.run_in_executor(None, fifo.readline)
                if not line:
                    return None  # FIFO closed

                # CAVA outputs semicolon-separated values: "val1;val2;val3;...;\n"
                values = line.strip().rstrip(";")
                if values:
                    return values
    except FileNotFoundError:
        await asyncio.sleep(0.1)
        return None

async def read_cava() -> None:
    """Read CAVA output from FIFO and broadcast to clients."""
    global consecutive_errors
    _setup_cava()

    while True:
        try:
            values = await _read_fifo_lines()
            if values:
                await broadcast(values)
                consecutive_errors = 0  # Reset on success
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error reading CAVA (attempt {consecutive_errors}): {e}")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.critical(f"CAVA failed {MAX_CONSECUTIVE_ERRORS} times consecutively, check ALSA loopback configuration")
                consecutive_errors = 0  # Reset to allow continued attempts

            await asyncio.sleep(1)


async def websocket_handler(websocket: websockets.WebSocketServerProtocol) -> None:
    """Handle WebSocket connections."""
    clients.add(websocket)
    remote = websocket.remote_address
    logger.info(f"Client connected: {remote}")

    try:
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        logger.info(f"Client disconnected: {remote}")


async def main() -> None:
    """Start WebSocket server and CAVA reader."""
    logger.info(f"Starting audio visualizer on port {WS_PORT}")

    # Start WebSocket server
    async with websockets.serve(websocket_handler, "0.0.0.0", WS_PORT):
        # Start CAVA reader
        await read_cava()


def cleanup(signum: int | None = None, frame = None) -> None:
    """Clean up on exit."""
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
