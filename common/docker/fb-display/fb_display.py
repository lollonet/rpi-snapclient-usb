#!/usr/bin/env python3
"""Framebuffer display renderer for Raspberry Pi.

Renders two side-by-side panels (album art + rainbow spectrum)
with slim track info below, directly to /dev/fb0.
"""

import asyncio
import colorsys
import io
import logging
import mmap
import os
import signal
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

# Colors
BG_TOP = (10, 10, 10)
BG_BOTTOM = (22, 33, 62)
TEXT_COLOR = (255, 255, 255)
ARTIST_COLOR = (179, 179, 179)
ALBUM_COLOR = (153, 153, 153)
DIM_COLOR = (85, 85, 85)
PANEL_BG = (17, 17, 17)

# Spectrum state
NUM_BANDS = 32
bands = np.zeros(NUM_BANDS, dtype=np.float32)
display_bands = np.zeros(NUM_BANDS, dtype=np.float32)

# Metadata state
current_metadata: dict | None = None
cached_artwork: Image.Image | None = None
cached_artwork_url: str = ""

# Framebuffer
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
        return WIDTH, HEIGHT, 32, WIDTH * 4


def open_framebuffer() -> None:
    """Open and memory-map the framebuffer device."""
    global fb_fd, fb_mmap, fb_stride, fb_bpp

    fb_w, fb_h, fb_bpp, fb_stride = get_fb_info()
    logger.info(f"Framebuffer: {fb_w}x{fb_h}, {fb_bpp}bpp, stride={fb_stride}")

    fd = os.open(FB_DEVICE, os.O_RDWR)
    size = fb_stride * fb_h
    fb_mmap = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
    fb_fd = fd


def write_frame(img: Image.Image) -> None:
    """Write a Pillow Image to the framebuffer."""
    if fb_mmap is None:
        return

    if fb_bpp == 32:
        rgba = img.convert("RGBA")
        r, g, b, a = rgba.split()
        bgra = Image.merge("RGBA", (b, g, r, a))
        raw = bgra.tobytes()
    elif fb_bpp == 16:
        rgb = np.array(img.convert("RGB"), dtype=np.uint16)
        r_ch = (rgb[:, :, 0] >> 3) & 0x1F
        g_ch = (rgb[:, :, 1] >> 2) & 0x3F
        b_ch = (rgb[:, :, 2] >> 3) & 0x1F
        rgb565 = (r_ch << 11) | (g_ch << 5) | b_ch
        raw = rgb565.astype(np.uint16).tobytes()
    else:
        return

    fb_mmap.seek(0)
    fb_mmap.write(raw)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a TTF font, falling back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_bold_font(size: int) -> ImageFont.FreeTypeFont:
    """Load bold TTF font."""
    bold_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in bold_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return load_font(size)


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linear interpolation between two RGB colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def rainbow_color(i: int, total: int) -> tuple[int, int, int]:
    """Get rainbow color for bar index (hue 0-300 degrees)."""
    hue = (i / total) * (300 / 360)  # 0 to 300 degrees
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.85)
    return (int(r * 255), int(g * 255), int(b * 255))


def create_background() -> Image.Image:
    """Create gradient background image."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        color = lerp_color(BG_TOP, BG_BOTTOM, t)
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return img


# Pre-create background and fonts
background = create_background()
font_title = load_bold_font(max(16, HEIGHT // 18))
font_details = load_font(max(12, HEIGHT // 24))


def fetch_artwork(url: str) -> Image.Image | None:
    """Fetch and cache artwork image."""
    global cached_artwork, cached_artwork_url
    if url == cached_artwork_url and cached_artwork is not None:
        return cached_artwork
    try:
        full_url = url
        if url.startswith("/"):
            full_url = f"http://localhost:8080{url}"
        resp = requests.get(full_url, timeout=3)
        if resp.status_code == 200:
            cached_artwork = Image.open(io.BytesIO(resp.content))
            cached_artwork_url = url
            return cached_artwork
    except Exception:
        pass
    return None


def render_frame() -> Image.Image:
    """Render a complete frame: two panels + slim track info."""
    img = background.copy()
    draw = ImageDraw.Draw(img)

    # Layout: two equal squares side by side, centered
    gap = int(WIDTH * 0.02)
    info_h = int(HEIGHT * 0.12)
    available_h = HEIGHT - info_h - gap
    panel_size = min(int((WIDTH - gap * 3) / 2), available_h - gap)
    total_w = panel_size * 2 + gap
    start_x = (WIDTH - total_w) // 2
    start_y = (available_h - panel_size) // 2

    art_x, art_y = start_x, start_y
    spec_x, spec_y = start_x + panel_size + gap, start_y

    # Left panel: album art background
    draw.rounded_rectangle(
        [art_x, art_y, art_x + panel_size, art_y + panel_size],
        radius=8, fill=PANEL_BG
    )

    meta = current_metadata
    is_playing = meta and meta.get("playing") and meta.get("title")

    if is_playing:
        artwork_url = meta.get("artwork") or meta.get("artist_image") or ""
        if artwork_url:
            art_img = fetch_artwork(artwork_url)
            if art_img:
                resized = art_img.resize((panel_size, panel_size), Image.LANCZOS)
                img.paste(resized, (art_x, art_y))
    # (When no artwork, the dark panel shows — matching browser vinyl placeholder)

    # Right panel: spectrum background
    draw.rounded_rectangle(
        [spec_x, spec_y, spec_x + panel_size, spec_y + panel_size],
        radius=8, fill=(10, 10, 15)
    )

    # Draw spectrum bars inside right panel
    pad = int(panel_size * 0.06)
    bar_area_w = panel_size - pad * 2
    bar_area_h = panel_size - pad * 2
    bar_gap = max(1, bar_area_w // (NUM_BANDS * 8))
    bar_w = (bar_area_w - bar_gap * (NUM_BANDS - 1)) // NUM_BANDS
    bar_base_y = spec_y + panel_size - pad

    for i in range(NUM_BANDS):
        display_bands[i] += (bands[i] - display_bands[i]) * 0.3
        val = display_bands[i] / 100.0
        bar_h = max(1, int(val * bar_area_h))

        bx = spec_x + pad + i * (bar_w + bar_gap)
        by = bar_base_y - bar_h

        color = rainbow_color(i, NUM_BANDS)
        draw.rectangle([bx, by, bx + bar_w, bar_base_y], fill=color)

        # Rounded top
        if bar_h > 3:
            r = min(bar_w // 2, 3)
            draw.ellipse([bx, by - r, bx + bar_w, by + r], fill=color)

    # Track info below panels
    info_y = start_y + panel_size + int(gap * 1.5)

    if is_playing:
        title = meta.get("title", "")
        artist = meta.get("artist", "")
        album = meta.get("album", "")

        # Title centered
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((WIDTH - tw) // 2, info_y), title,
                  fill=TEXT_COLOR, font=font_title)

        # Artist — Album on second line
        details = ""
        if artist and album:
            details = f"{artist} \u2014 {album}"
        elif artist:
            details = artist
        elif album:
            details = album

        if details:
            bbox2 = draw.textbbox((0, 0), details, font=font_details)
            dw = bbox2[2] - bbox2[0]
            draw.text(((WIDTH - dw) // 2, info_y + font_title.size + 4),
                      details, fill=ARTIST_COLOR, font=font_details)
    else:
        msg = "No Music Playing"
        bbox = draw.textbbox((0, 0), msg, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((WIDTH - tw) // 2, info_y), msg,
                  fill=DIM_COLOR, font=font_title)

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
    global current_metadata
    while True:
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(METADATA_URL, timeout=3)
            )
            if resp.status_code == 200:
                data = resp.json()
                if data != current_metadata:
                    current_metadata = data
        except Exception:
            pass
        await asyncio.sleep(2)


async def render_loop() -> None:
    """Main render loop at ~30 FPS."""
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
