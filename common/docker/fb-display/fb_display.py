#!/usr/bin/env python3
"""Framebuffer display renderer for Raspberry Pi.

Renders album art, track info, and real-time spectrum analyzer
directly to /dev/fb0 without X11.
"""

import asyncio
import io
import json
import logging
import mmap
import os
import signal
import struct
import sys
import time

import numpy as np
import requests
import websockets
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Display configuration
DISPLAY_RESOLUTION = os.environ.get("DISPLAY_RESOLUTION", "1024x600")
METADATA_URL = "http://localhost:8080/metadata.json"
WS_PORT = int(os.environ.get("VISUALIZER_WS_PORT", "8081"))
FB_DEVICE = "/dev/fb0"

# Parse resolution
WIDTH, HEIGHT = (int(x) for x in DISPLAY_RESOLUTION.split("x"))

# Colors (matching browser theme)
BG_COLOR_TOP = (10, 10, 10)
BG_COLOR_BOTTOM = (22, 33, 62)
TEXT_COLOR = (255, 255, 255)
ARTIST_COLOR = (179, 179, 179)
ALBUM_COLOR = (136, 136, 136)
BAR_COLORS = [
    (102, 126, 234),  # blue
    (118, 75, 162),   # purple
    (240, 147, 251),  # pink
]

# Spectrum state
NUM_BANDS = 32
bands = np.zeros(NUM_BANDS, dtype=np.float32)
display_bands = np.zeros(NUM_BANDS, dtype=np.float32)

# Metadata state
current_metadata: dict | None = None
metadata_changed = True

# Framebuffer info
fb_fd = None
fb_mmap = None
fb_stride = 0
fb_bpp = 32


def get_fb_info() -> tuple[int, int, int, int]:
    """Read framebuffer geometry from sysfs."""
    fb_path = "/sys/class/graphics/fb0"
    try:
        with open(f"{fb_path}/virtual_size") as f:
            vw, vh = f.read().strip().split(",")
        with open(f"{fb_path}/bits_per_pixel") as f:
            bpp = int(f.read().strip())
        with open(f"{fb_path}/stride") as f:
            stride = int(f.read().strip())
        return int(vw), int(vh), bpp, stride
    except FileNotFoundError:
        # Fallback to configured resolution
        return WIDTH, HEIGHT, 32, WIDTH * 4


def open_framebuffer() -> tuple:
    """Open and memory-map the framebuffer device."""
    global fb_fd, fb_mmap, fb_stride, fb_bpp

    fb_w, fb_h, fb_bpp, fb_stride = get_fb_info()
    logger.info(f"Framebuffer: {fb_w}x{fb_h}, {fb_bpp}bpp, stride={fb_stride}")

    fd = os.open(FB_DEVICE, os.O_RDWR)
    size = fb_stride * fb_h
    fb_mmap = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
    fb_fd = fd
    fb_stride = fb_stride

    return fb_mmap, fb_stride, fb_bpp


def write_frame(img: Image.Image) -> None:
    """Write a Pillow Image to the framebuffer."""
    if fb_mmap is None:
        return

    # Convert to BGRA for framebuffer (most Linux FBs use BGRA)
    if fb_bpp == 32:
        rgba = img.convert("RGBA")
        r, g, b, a = rgba.split()
        bgra = Image.merge("RGBA", (b, g, r, a))
        raw = bgra.tobytes()
    elif fb_bpp == 16:
        # RGB565
        rgb = np.array(img.convert("RGB"), dtype=np.uint16)
        r = (rgb[:, :, 0] >> 3) & 0x1F
        g = (rgb[:, :, 1] >> 2) & 0x3F
        b = (rgb[:, :, 2] >> 3) & 0x1F
        rgb565 = (r << 11) | (g << 5) | b
        raw = rgb565.astype(np.uint16).tobytes()
    else:
        return

    fb_mmap.seek(0)
    fb_mmap.write(raw)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a TTF font, falling back to default."""
    font_paths = [
        "/app/fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linear interpolation between two RGB colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def create_background() -> Image.Image:
    """Create gradient background image."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        color = lerp_color(BG_COLOR_TOP, BG_COLOR_BOTTOM, t)
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return img


def get_bar_color(t: float) -> tuple:
    """Get spectrum bar color at position t (0-1)."""
    if t < 0.5:
        return lerp_color(BAR_COLORS[0], BAR_COLORS[1], t * 2)
    return lerp_color(BAR_COLORS[1], BAR_COLORS[2], (t - 0.5) * 2)


# Pre-create background and fonts
background = create_background()
font_title = load_font(max(16, HEIGHT // 15))
font_artist = load_font(max(14, HEIGHT // 20))
font_album = load_font(max(12, HEIGHT // 25))


def render_frame() -> Image.Image:
    """Render a complete frame with metadata, art, and spectrum."""
    img = background.copy()
    draw = ImageDraw.Draw(img)

    # Layout
    art_size = int(min(WIDTH * 0.4, HEIGHT * 0.6))
    art_x = int(WIDTH * 0.08)
    art_y = int((HEIGHT - art_size) * 0.35)

    text_x = art_x + art_size + int(WIDTH * 0.05)
    text_max_w = WIDTH - text_x - int(WIDTH * 0.05)

    spectrum_h = int(HEIGHT * 0.15)
    spectrum_y = HEIGHT - spectrum_h - int(HEIGHT * 0.05)

    # Draw album art
    meta = current_metadata
    if meta and meta.get("playing") and meta.get("title"):
        artwork_url = meta.get("artwork") or meta.get("artist_image")
        if artwork_url:
            try:
                full_url = artwork_url
                if artwork_url.startswith("/"):
                    full_url = f"http://localhost:8080{artwork_url}"
                resp = requests.get(full_url, timeout=3)
                if resp.status_code == 200:
                    art_img = Image.open(io.BytesIO(resp.content))
                    art_img = art_img.resize((art_size, art_size), Image.LANCZOS)
                    img.paste(art_img, (art_x, art_y))
            except Exception:
                pass

        # Track info
        title_y = art_y + int(art_size * 0.15)
        draw.text((text_x, title_y), meta.get("title", ""),
                  fill=TEXT_COLOR, font=font_title)

        artist = meta.get("artist", "")
        if artist:
            draw.text((text_x, title_y + font_title.size + 10), artist,
                      fill=ARTIST_COLOR, font=font_artist)

        album = meta.get("album", "")
        if album:
            draw.text((text_x, title_y + font_title.size + font_artist.size + 20),
                      album, fill=ALBUM_COLOR, font=font_album)
    else:
        # No music playing
        msg = "No Music Playing"
        bbox = draw.textbbox((0, 0), msg, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((WIDTH - tw) // 2, HEIGHT // 2 - font_title.size),
                  msg, fill=(102, 102, 102), font=font_title)

    # Draw spectrum bars
    bar_area_w = int(WIDTH * 0.84)
    bar_area_x = int(WIDTH * 0.08)
    gap = max(1, bar_area_w // (NUM_BANDS * 8))
    bar_w = (bar_area_w - gap * (NUM_BANDS - 1)) // NUM_BANDS
    max_bar_h = spectrum_h

    for i in range(NUM_BANDS):
        # Smooth interpolation
        display_bands[i] += (bands[i] - display_bands[i]) * 0.3
        val = display_bands[i] / 100.0
        bar_h = max(1, int(val * max_bar_h))

        x = bar_area_x + i * (bar_w + gap)
        y = spectrum_y + spectrum_h - bar_h

        # Gradient bar (approximate with a single color per bar based on height ratio)
        t = val
        color = get_bar_color(t)
        draw.rectangle([x, y, x + bar_w, spectrum_y + spectrum_h], fill=color)

        # Rounded top (small circle)
        if bar_h > 3:
            r = min(bar_w // 2, 3)
            draw.ellipse([x, y - r, x + bar_w, y + r], fill=color)

    return img


async def spectrum_ws_reader() -> None:
    """Connect to spectrum WebSocket and update band values."""
    ws_url = f"ws://localhost:{WS_PORT}"
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info(f"Connected to spectrum WebSocket: {ws_url}")
                async for message in ws:
                    values = message.split(";")
                    for i in range(min(NUM_BANDS, len(values))):
                        try:
                            bands[i] = float(values[i])
                        except ValueError:
                            pass
        except Exception as e:
            logger.debug(f"Spectrum WS error: {e}")
            await asyncio.sleep(5)


async def metadata_poller() -> None:
    """Poll metadata endpoint periodically."""
    global current_metadata, metadata_changed
    while True:
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(METADATA_URL, timeout=3)
            )
            if resp.status_code == 200:
                data = resp.json()
                if data != current_metadata:
                    current_metadata = data
                    metadata_changed = True
        except Exception:
            pass
        await asyncio.sleep(2)


async def render_loop() -> None:
    """Main render loop at ~30 FPS for spectrum, slower for static content."""
    frame_interval = 1.0 / 30
    while True:
        start = time.monotonic()

        frame = await asyncio.get_event_loop().run_in_executor(
            None, render_frame
        )
        await asyncio.get_event_loop().run_in_executor(
            None, write_frame, frame
        )

        elapsed = time.monotonic() - start
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


async def main() -> None:
    """Start all tasks."""
    logger.info(f"Starting framebuffer display: {WIDTH}x{HEIGHT}")
    logger.info(f"  Metadata: {METADATA_URL}")
    logger.info(f"  Spectrum WS port: {WS_PORT}")
    logger.info(f"  Framebuffer: {FB_DEVICE}")

    open_framebuffer()

    await asyncio.gather(
        render_loop(),
        spectrum_ws_reader(),
        metadata_poller(),
    )


def cleanup(signum: int | None = None, frame=None) -> None:
    """Clean up on exit."""
    if fb_mmap:
        fb_mmap.close()
    if fb_fd:
        os.close(fb_fd)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup(None, None)
