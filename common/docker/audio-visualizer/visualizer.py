#!/usr/bin/env python3
"""Real-time spectrum analyzer using ALSA FIFO and numpy FFT."""

import asyncio
import fcntl
import logging
import os
import signal
import struct
import sys

import numpy as np
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Audio parameters (must match snapclient output)
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit
FRAME_SIZE = CHANNELS * SAMPLE_WIDTH  # 4 bytes per frame

# FFT parameters
FFT_SIZE = 2048  # ~42ms window at 48kHz
FRAMES_PER_READ = FFT_SIZE
BYTES_PER_READ = FRAMES_PER_READ * FRAME_SIZE
NUM_BANDS = 32
MIN_FREQ = 60
MAX_FREQ = 16000
TARGET_FPS = 30

# FIFO
AUDIO_FIFO = os.environ.get("AUDIO_FIFO", "/tmp/audio/stream.fifo")
WS_PORT = int(os.environ.get("VISUALIZER_WS_PORT", "8081"))
F_SETPIPE_SZ = 1031
PIPE_BUF_SIZE = 1048576  # 1MB

# Smoothing
SMOOTHING = 0.7  # 0 = no smoothing, 1 = frozen

clients: set[websockets.WebSocketServerProtocol] = set()
prev_bands: np.ndarray = np.zeros(NUM_BANDS)


def compute_band_edges() -> list[tuple[int, int]]:
    """Compute log-spaced frequency band edges mapped to FFT bin indices."""
    freq_bins = np.fft.rfftfreq(FFT_SIZE, d=1.0 / SAMPLE_RATE)
    log_min = np.log10(MIN_FREQ)
    log_max = np.log10(MAX_FREQ)
    band_freqs = np.logspace(log_min, log_max, NUM_BANDS + 1)

    edges = []
    for i in range(NUM_BANDS):
        lo = int(np.searchsorted(freq_bins, band_freqs[i]))
        hi = int(np.searchsorted(freq_bins, band_freqs[i + 1]))
        hi = max(hi, lo + 1)  # At least 1 bin per band
        edges.append((lo, hi))
    return edges


BAND_EDGES = compute_band_edges()
WINDOW = np.hanning(FFT_SIZE).astype(np.float32)


def analyze_pcm(data: bytes) -> str | None:
    """Convert raw PCM bytes to spectrum band values."""
    global prev_bands

    # Parse 16-bit signed stereo PCM
    num_samples = len(data) // SAMPLE_WIDTH
    if num_samples < FFT_SIZE * CHANNELS:
        return None

    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)

    # Mix stereo to mono (interleaved L,R,L,R...)
    if CHANNELS == 2:
        mono = (samples[0::2] + samples[1::2]) * 0.5
    else:
        mono = samples

    # Take last FFT_SIZE samples
    mono = mono[-FFT_SIZE:]

    # Apply window and normalize
    windowed = mono * WINDOW / 32768.0

    # FFT
    spectrum = np.abs(np.fft.rfft(windowed))

    # Group into bands
    bands = np.zeros(NUM_BANDS, dtype=np.float32)
    for i, (lo, hi) in enumerate(BAND_EDGES):
        bands[i] = np.mean(spectrum[lo:hi]) if lo < len(spectrum) else 0

    # Convert to dB scale, normalize to 0-100
    bands = np.maximum(bands, 1e-10)
    db = 20 * np.log10(bands)
    # Map roughly -60dB..0dB to 0..100
    normalized = np.clip((db + 60) * (100.0 / 60.0), 0, 100)

    # Smoothing
    smoothed = prev_bands * SMOOTHING + normalized * (1 - SMOOTHING)
    prev_bands = smoothed

    # Format as semicolon-separated integers
    values = ";".join(str(int(v)) for v in smoothed)
    return values


async def broadcast(data: str) -> None:
    """Send spectrum data to all connected WebSocket clients."""
    if not clients:
        return
    dead = set()
    for client in clients:
        try:
            await client.send(data)
        except Exception:
            dead.add(client)
    clients.difference_update(dead)


async def read_fifo_and_broadcast() -> None:
    """Read raw PCM from ALSA FIFO, compute FFT, broadcast."""
    frame_interval = 1.0 / TARGET_FPS

    while True:
        try:
            logger.info(f"Opening FIFO: {AUDIO_FIFO}")
            fd = os.open(AUDIO_FIFO, os.O_RDONLY)

            # Maximize pipe buffer
            try:
                fcntl.fcntl(fd, F_SETPIPE_SZ, PIPE_BUF_SIZE)
                logger.info(f"Pipe buffer set to {PIPE_BUF_SIZE} bytes")
            except OSError:
                logger.warning("Could not set pipe buffer size")

            logger.info("FIFO opened, reading audio data...")

            with os.fdopen(fd, "rb", buffering=0) as fifo:
                while True:
                    start = asyncio.get_event_loop().time()

                    # Read PCM data (blocking in executor to not block event loop)
                    data = await asyncio.get_event_loop().run_in_executor(
                        None, fifo.read, BYTES_PER_READ
                    )

                    if not data:
                        logger.warning("FIFO closed (EOF), reopening...")
                        break

                    # Analyze and broadcast
                    result = analyze_pcm(data)
                    if result:
                        await broadcast(result)

                    # Maintain target FPS
                    elapsed = asyncio.get_event_loop().time() - start
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

        except FileNotFoundError:
            logger.warning(f"FIFO not found: {AUDIO_FIFO}, retrying in 2s...")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error reading FIFO: {e}, retrying in 2s...")
            await asyncio.sleep(2)


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
    """Start WebSocket server and FIFO reader."""
    logger.info(f"Starting spectrum analyzer on port {WS_PORT}")
    logger.info(f"  FIFO: {AUDIO_FIFO}")
    logger.info(f"  FFT size: {FFT_SIZE}, bands: {NUM_BANDS}")
    logger.info(f"  Frequency range: {MIN_FREQ}-{MAX_FREQ} Hz")
    logger.info(f"  Target FPS: {TARGET_FPS}")

    async with websockets.serve(websocket_handler, "0.0.0.0", WS_PORT):
        await read_fifo_and_broadcast()


def cleanup(signum: int | None = None, frame=None) -> None:
    """Clean up on exit."""
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup(None, None)
