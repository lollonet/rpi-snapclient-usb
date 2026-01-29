#!/usr/bin/env python3
"""Real-time octave-band spectrum analyzer.

Reads raw PCM from ALSA FIFO, computes FFT, groups into octave bands,
outputs dBFS values via WebSocket. No autosens, no normalization —
absolute levels referenced to 0 dBFS (16-bit full scale = 32768).

Output format: "dBFS_1;dBFS_2;...;dBFS_N" per frame.
Values are in dBFS (negative, e.g. -12;-25;-40;...).
Silence = -inf, clamped to NOISE_FLOOR.
"""

import asyncio
import fcntl
import logging
import os
import signal
import sys

import numpy as np
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Audio parameters (must match snapclient output)
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit
FRAME_SIZE = CHANNELS * SAMPLE_WIDTH

# FFT parameters
FFT_SIZE = 4096  # ~85ms window at 48kHz — good frequency resolution for low bands
HOP_SIZE = 1600  # ~33ms hop = 30 FPS update rate
BYTES_PER_READ = HOP_SIZE * FRAME_SIZE
TARGET_FPS = 30

# Half-octave bands: center frequencies
# 19 bands from 20 Hz to 10 kHz, each spanning center/2^(1/4) to center*2^(1/4)
BAND_CENTERS = [
    20, 28, 40, 57, 80, 113, 160, 226, 320, 453,
    640, 894, 1250, 1768, 2500, 3536, 5000, 7071, 10000,
]
NUM_BANDS = len(BAND_CENTERS)

# Display range
NOISE_FLOOR = -72.0  # dBFS — below this = silence (16-bit theoretical = -96)
REF_LEVEL = 0.0  # dBFS — top of display

# FIFO
AUDIO_FIFO = os.environ.get("AUDIO_FIFO", "/tmp/audio/stream.fifo")
WS_PORT = int(os.environ.get("VISUALIZER_WS_PORT", "8081"))
F_SETPIPE_SZ = 1031
PIPE_BUF_SIZE = 65536  # 64KB — ~0.3s buffer, keeps latency low

# Smoothing: fast attack, slow decay (in dB domain)
ATTACK_COEFF = 0.4  # lower = faster attack (0 = instant)
DECAY_COEFF = 0.85  # higher = slower decay

clients: set = set()
prev_db: np.ndarray = np.full(NUM_BANDS, NOISE_FLOOR, dtype=np.float64)
audio_ring: np.ndarray = np.zeros(FFT_SIZE, dtype=np.float32)


def compute_band_bins() -> list[tuple[int, int]]:
    """Compute FFT bin ranges for each half-octave band.

    Each half-octave band spans [center/2^(1/4), center*2^(1/4)].
    Bins are combined (summed power) within each band.
    """
    freq_bins = np.fft.rfftfreq(FFT_SIZE, d=1.0 / SAMPLE_RATE)
    quarter_octave = 2.0 ** 0.25  # ≈ 1.1892
    edges = []
    for center in BAND_CENTERS:
        lo_freq = center / quarter_octave
        hi_freq = center * quarter_octave
        lo_bin = int(np.searchsorted(freq_bins, lo_freq))
        hi_bin = int(np.searchsorted(freq_bins, hi_freq))
        hi_bin = max(hi_bin, lo_bin + 1)  # at least 1 bin
        edges.append((lo_bin, hi_bin))
    return edges


BAND_BINS = compute_band_bins()
WINDOW = np.hanning(FFT_SIZE).astype(np.float32)
# Window correction factor for power (Hanning window)
WINDOW_POWER_CORR = 1.0 / np.mean(WINDOW ** 2)


def analyze_pcm(new_samples: np.ndarray) -> str | None:
    """Compute octave-band levels in dBFS from PCM samples.

    Uses overlap-add: new_samples are appended to a ring buffer,
    and FFT is computed over the full FFT_SIZE window.
    """
    global prev_db, audio_ring

    # Check for silence on NEW samples (not ring buffer — which has old data)
    # Threshold 1 LSB RMS ≈ -90 dBFS — only pure digital silence
    rms_new = np.sqrt(np.mean(new_samples ** 2))
    if rms_new < 1.0:
        audio_ring[:] = 0.0  # clear ring buffer too
        prev_db[:] = NOISE_FLOOR
        return ";".join(str(round(v, 1)) for v in prev_db)

    # Shift ring buffer and append new samples
    n = len(new_samples)
    if n >= FFT_SIZE:
        audio_ring[:] = new_samples[-FFT_SIZE:]
    else:
        audio_ring = np.roll(audio_ring, -n)
        audio_ring[-n:] = new_samples

    # Normalize to [-1.0, 1.0] (0 dBFS = 32768)
    normalized = audio_ring / 32768.0

    # Apply window
    windowed = normalized * WINDOW

    # FFT — power spectrum (V²)
    spectrum = np.abs(np.fft.rfft(windowed)) ** 2

    # Apply window power correction
    spectrum *= WINDOW_POWER_CORR

    # Normalize by FFT size² (Parseval's theorem)
    spectrum /= (FFT_SIZE ** 2)

    # For each octave band: sum power across bins, convert to dBFS
    band_db = np.full(NUM_BANDS, NOISE_FLOOR, dtype=np.float64)
    for i, (lo, hi) in enumerate(BAND_BINS):
        if lo < len(spectrum):
            # Sum power in band (energy in bandwidth)
            band_power = np.sum(spectrum[lo:hi])
            if band_power > 0:
                # Convert to dBFS (power): 10*log10 because it's already V²
                db = 10.0 * np.log10(band_power)
                band_db[i] = max(db, NOISE_FLOOR)

    # Asymmetric smoothing in dB domain
    for i in range(NUM_BANDS):
        if band_db[i] > prev_db[i]:
            # Attack: fast rise
            prev_db[i] += (band_db[i] - prev_db[i]) * (1.0 - ATTACK_COEFF)
        else:
            # Decay: slow fall
            prev_db[i] += (band_db[i] - prev_db[i]) * (1.0 - DECAY_COEFF)

    # Format: dBFS values rounded to 1 decimal
    return ";".join(str(round(v, 1)) for v in prev_db)


async def broadcast(data: str) -> None:
    """Send data to all connected WebSocket clients."""
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
    """Read raw PCM from ALSA FIFO, compute spectrum, broadcast."""
    frame_interval = 1.0 / TARGET_FPS

    while True:
        try:
            logger.info(f"Opening FIFO: {AUDIO_FIFO}")
            fd = os.open(AUDIO_FIFO, os.O_RDONLY)

            try:
                fcntl.fcntl(fd, F_SETPIPE_SZ, PIPE_BUF_SIZE)
            except OSError:
                logger.warning("Could not set pipe buffer size")

            logger.info("FIFO opened, reading audio data...")

            with os.fdopen(fd, "rb", buffering=0) as fifo:
                while True:
                    start = asyncio.get_event_loop().time()

                    data = await asyncio.get_event_loop().run_in_executor(
                        None, fifo.read, BYTES_PER_READ
                    )

                    if not data:
                        logger.warning("FIFO closed (EOF), reopening...")
                        prev_db[:] = NOISE_FLOOR
                        zero_msg = ";".join(
                            str(NOISE_FLOOR) for _ in range(NUM_BANDS)
                        )
                        await broadcast(zero_msg)
                        break

                    # Parse 16-bit stereo PCM, mix to mono
                    samples = np.frombuffer(data, dtype=np.int16).astype(
                        np.float32
                    )
                    if CHANNELS == 2 and len(samples) >= 2:
                        mono = (samples[0::2] + samples[1::2]) * 0.5
                    else:
                        mono = samples

                    result = analyze_pcm(mono)
                    if result:
                        await broadcast(result)

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


async def websocket_handler(websocket) -> None:
    """Handle WebSocket connections."""
    clients.add(websocket)
    logger.info(f"Client connected: {websocket.remote_address}")
    try:
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        logger.info(f"Client disconnected: {websocket.remote_address}")


async def main() -> None:
    """Start WebSocket server and FIFO reader."""
    logger.info(f"Starting spectrum analyzer on port {WS_PORT}")
    logger.info(f"  FIFO: {AUDIO_FIFO}")
    logger.info(f"  FFT size: {FFT_SIZE} ({FFT_SIZE / SAMPLE_RATE * 1000:.0f}ms)")
    logger.info(f"  Bands: {NUM_BANDS} half-octave ({BAND_CENTERS[0]}-{BAND_CENTERS[-1]} Hz)")
    logger.info(f"  Range: {NOISE_FLOOR} to {REF_LEVEL} dBFS")
    logger.info(f"  Target FPS: {TARGET_FPS}")

    async with websockets.serve(websocket_handler, "0.0.0.0", WS_PORT):
        await read_fifo_and_broadcast()


def cleanup(signum=None, frame=None):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup()
