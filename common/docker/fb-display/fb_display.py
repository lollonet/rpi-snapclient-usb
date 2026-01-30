#!/usr/bin/env python3
"""Framebuffer display renderer for Raspberry Pi.

Renders album art (left), track info (top-right), and spectrum bars
(bottom-right, 55% height) directly to /dev/fb0.

Spectrum: 19 half-octave bands in dBFS, matching visualizer.py output.

Performance: static content (art, text) is cached and only redrawn on
metadata change. Only the spectrum region is redrawn each frame (~20 FPS).
"""

import asyncio
import colorsys
import io
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
METADATA_URL = "http://localhost:8080/metadata.json"
WS_PORT = int(os.environ.get("VISUALIZER_WS_PORT", "8081"))
FB_DEVICE = "/dev/fb0"
TARGET_FPS = 20

# Resolution: read from FB sysfs at startup, env var is fallback only
_fallback_res = os.environ.get("DISPLAY_RESOLUTION", "1024x600")
WIDTH, HEIGHT = (int(x) for x in _fallback_res.split("x"))

# Colors
BG_TOP = (10, 10, 10)
BG_BOTTOM = (22, 33, 62)
TEXT_COLOR = (255, 255, 255)
ARTIST_COLOR = (179, 179, 179)
ALBUM_COLOR = (153, 153, 153)
DIM_COLOR = (85, 85, 85)
PANEL_BG = (17, 17, 17)

# Spectrum state — NUM_BANDS auto-detected from first WS message
NUM_BANDS = 19  # default, updated on first WS message
NOISE_FLOOR = -72.0  # dBFS
REF_LEVEL = 0.0  # dBFS
DB_RANGE = REF_LEVEL - NOISE_FLOOR  # 72 dB

bands = np.full(NUM_BANDS, NOISE_FLOOR, dtype=np.float64)
display_bands = np.full(NUM_BANDS, NOISE_FLOOR, dtype=np.float64)
peak_bands = np.zeros(NUM_BANDS, dtype=np.float64)
peak_time = np.zeros(NUM_BANDS, dtype=np.float64)


def resize_bands(n: int) -> None:
    """Resize all band arrays and recompute layout when NUM_BANDS changes."""
    global NUM_BANDS, bands, display_bands, peak_bands, peak_time, layout
    if n == NUM_BANDS:
        return
    NUM_BANDS = n
    bands = np.full(n, NOISE_FLOOR, dtype=np.float64)
    display_bands = np.full(n, NOISE_FLOOR, dtype=np.float64)
    peak_bands = np.zeros(n, dtype=np.float64)
    peak_time = np.zeros(n, dtype=np.float64)
    precompute_colors()
    layout = compute_layout()
    logger.info(f"Band count changed to {n}")

# Smoothing coefficients
ATTACK_COEFF = 0.6  # fast attack (higher = faster)
DECAY_COEFF = 0.15  # slow decay (lower = slower)
PEAK_HOLD_S = 2.0
PEAK_FALL_DB = 0.5  # dB per frame

# Metadata state
current_metadata: dict | None = None
metadata_version: int = 0  # bumped on change
cached_artwork: Image.Image | None = None
cached_artwork_url: str = ""

# Framebuffer
fb_fd = None
fb_mmap = None
fb_stride = 0
fb_bpp = 32

# Cached frames: base_frame has bg+art+text, spectrum_bg has just the spectrum area background
base_frame: Image.Image | None = None
base_frame_version: int = -1
spectrum_bg: Image.Image | None = None

# Layout geometry (computed once in compute_layout)
layout: dict = {}


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
    global fb_fd, fb_mmap, fb_stride, fb_bpp, WIDTH, HEIGHT

    fb_w, fb_h, fb_bpp, fb_stride = get_fb_info()
    WIDTH, HEIGHT = fb_w, fb_h
    logger.info(f"Framebuffer: {WIDTH}x{HEIGHT}, {fb_bpp}bpp, stride={fb_stride}")

    fd = os.open(FB_DEVICE, os.O_RDWR)
    size = fb_stride * fb_h
    fb_mmap = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
    fb_fd = fd


def write_region_to_fb(img: Image.Image, x: int, y: int) -> None:
    """Write a sub-image to the framebuffer at position (x, y).

    Only writes the lines covered by the image, not the full screen.
    """
    if fb_mmap is None:
        return

    w, h = img.size
    bpp_bytes = fb_bpp // 8

    if fb_bpp == 16:
        rgb = np.array(img.convert("RGB"), dtype=np.uint16)
        r_ch = (rgb[:, :, 0] >> 3) & 0x1F
        g_ch = (rgb[:, :, 1] >> 2) & 0x3F
        b_ch = (rgb[:, :, 2] >> 3) & 0x1F
        pixels = ((r_ch << 11) | (g_ch << 5) | b_ch).astype(np.uint16)
        for row in range(h):
            offset = (y + row) * fb_stride + x * bpp_bytes
            fb_mmap.seek(offset)
            fb_mmap.write(pixels[row].tobytes())
    elif fb_bpp == 32:
        rgba = img.convert("RGBA")
        r, g, b, a = rgba.split()
        bgra = Image.merge("RGBA", (b, g, r, a))
        raw = np.array(bgra)
        for row in range(h):
            offset = (y + row) * fb_stride + x * bpp_bytes
            fb_mmap.seek(offset)
            fb_mmap.write(raw[row].tobytes())


def write_full_frame(img: Image.Image) -> None:
    """Write a full-screen image to the framebuffer."""
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


# Pre-computed rainbow colors
BAR_COLORS: list[tuple[int, int, int]] = []
PEAK_COLORS: list[tuple[int, int, int]] = []


def precompute_colors() -> None:
    """Pre-compute rainbow colors for all bands."""
    global BAR_COLORS, PEAK_COLORS
    BAR_COLORS = [rainbow_color(i, NUM_BANDS) for i in range(NUM_BANDS)]
    PEAK_COLORS = []
    for i in range(NUM_BANDS):
        hue = (i / NUM_BANDS) * (300 / 360)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.95, 0.95)
        PEAK_COLORS.append((int(r * 255), int(g * 255), int(b * 255)))


def create_background() -> Image.Image:
    """Create gradient background image."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        color = lerp_color(BG_TOP, BG_BOTTOM, t)
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return img


def compute_layout() -> dict:
    """Compute all layout geometry once."""
    outer_gap = int(min(WIDTH, HEIGHT) * 0.025)
    container_w = int(WIDTH * 0.92)
    container_h = int(HEIGHT * 0.85)
    start_x = (WIDTH - container_w) // 2
    start_y = (HEIGHT - container_h) // 2

    art_size = min(int(container_w * 0.46), container_h)
    art_x = start_x
    art_y = start_y + (container_h - art_size) // 2

    right_x = art_x + art_size + outer_gap
    right_w = container_w - art_size - outer_gap
    right_y = art_y
    right_h = art_size

    spec_h = int(right_h * 0.55)
    spec_y = right_y + right_h - spec_h
    info_h = right_h - spec_h - outer_gap
    info_y = right_y

    pad = int(right_w * 0.06)
    bar_area_w = right_w - pad * 2
    bar_area_h = spec_h - pad * 2
    bar_gap = max(1, int(bar_area_w * 0.008))
    bar_w = (bar_area_w - bar_gap * (NUM_BANDS - 1)) // NUM_BANDS
    bar_base_y = spec_y + spec_h - pad

    return {
        "art_x": art_x, "art_y": art_y, "art_size": art_size,
        "right_x": right_x, "right_w": right_w,
        "right_y": right_y, "right_h": right_h,
        "spec_y": spec_y, "spec_h": spec_h,
        "info_y": info_y, "info_h": info_h,
        "outer_gap": outer_gap,
        "pad": pad, "bar_area_w": bar_area_w, "bar_area_h": bar_area_h,
        "bar_gap": bar_gap, "bar_w": bar_w, "bar_base_y": bar_base_y,
    }


def fit_font(text: str, max_width: int, base_size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Return the largest font size (down to 10px) that fits text within max_width."""
    loader = load_bold_font if bold else load_font
    for size in range(base_size, 9, -1):
        font = loader(size)
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
    return loader(10)


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


def render_base_frame() -> Image.Image:
    """Render static content: background, album art, track info.

    Called only when metadata changes.
    """
    bg = create_background()
    draw = ImageDraw.Draw(bg)
    L = layout
    max_text_w = L["right_w"]
    base_title_size = max(16, HEIGHT // 18)
    base_detail_size = max(12, HEIGHT // 24)

    # Left panel: album art
    draw.rounded_rectangle(
        [L["art_x"], L["art_y"],
         L["art_x"] + L["art_size"], L["art_y"] + L["art_size"]],
        radius=8, fill=PANEL_BG,
    )

    meta = current_metadata
    is_playing = meta and meta.get("playing") and meta.get("title")

    if is_playing:
        artwork_url = meta.get("artwork") or meta.get("artist_image") or ""
        if artwork_url:
            art_img = fetch_artwork(artwork_url)
            if art_img:
                resized = art_img.resize(
                    (L["art_size"], L["art_size"]), Image.LANCZOS
                )
                bg.paste(resized, (L["art_x"], L["art_y"]))

    # Right top: track info (right-aligned, font shrinks to fit)
    text_right = L["right_x"] + L["right_w"]
    if is_playing:
        title = meta.get("title", "")
        artist = meta.get("artist", "")
        album = meta.get("album", "")

        # Fit fonts to available width
        ft_title = fit_font(title, max_text_w, base_title_size, bold=True) if title else None
        ft_artist = fit_font(artist, max_text_w, base_detail_size) if artist else None
        ft_album = fit_font(album, max_text_w, base_detail_size) if album else None

        # Compute total text height for vertical centering
        line_gap = 4
        total_h = 0
        if ft_title:
            total_h += ft_title.size
        if ft_artist:
            total_h += ft_artist.size + line_gap
        if ft_album:
            total_h += ft_album.size + line_gap // 2

        text_y = L["info_y"] + (L["info_h"] - total_h) // 2

        if ft_title:
            bbox = draw.textbbox((0, 0), title, font=ft_title)
            tw = bbox[2] - bbox[0]
            draw.text((text_right - tw, text_y), title,
                      fill=TEXT_COLOR, font=ft_title)
            text_y += ft_title.size + line_gap

        if ft_artist:
            bbox = draw.textbbox((0, 0), artist, font=ft_artist)
            tw = bbox[2] - bbox[0]
            draw.text((text_right - tw, text_y), artist,
                      fill=ARTIST_COLOR, font=ft_artist)
            text_y += ft_artist.size + line_gap // 2

        if ft_album:
            bbox = draw.textbbox((0, 0), album, font=ft_album)
            tw = bbox[2] - bbox[0]
            draw.text((text_right - tw, text_y), album,
                      fill=ALBUM_COLOR, font=ft_album)
    else:
        msg = "No Music Playing"
        ft = load_bold_font(base_title_size)
        text_y = L["info_y"] + L["info_h"] // 2 - ft.size // 2
        bbox = draw.textbbox((0, 0), msg, font=ft)
        tw = bbox[2] - bbox[0]
        draw.text((text_right - tw, text_y), msg,
                  fill=DIM_COLOR, font=ft)

    # Spectrum panel background (will be overwritten each frame)
    draw.rounded_rectangle(
        [L["right_x"], L["spec_y"],
         L["right_x"] + L["right_w"], L["spec_y"] + L["spec_h"]],
        radius=6, fill=(10, 10, 15),
    )

    return bg


def extract_spectrum_bg() -> Image.Image:
    """Extract the spectrum region from the base frame as a clean background."""
    L = layout
    return base_frame.crop((
        L["right_x"], L["spec_y"],
        L["right_x"] + L["right_w"], L["spec_y"] + L["spec_h"],
    ))


def render_spectrum() -> Image.Image:
    """Render only the spectrum bars region. Returns a cropped image."""
    L = layout
    now = time.monotonic()

    # Start from clean spectrum background
    img = spectrum_bg.copy()
    draw = ImageDraw.Draw(img)

    # Coordinates are relative to spectrum region (0,0 = top-left of region)
    pad = L["pad"]
    bar_area_h = L["bar_area_h"]
    bar_gap = L["bar_gap"]
    bar_w = L["bar_w"]
    bar_base_y = L["spec_h"] - pad  # relative to region

    for i in range(NUM_BANDS):
        # Asymmetric smoothing in dB domain
        target = bands[i]
        if target > display_bands[i]:
            display_bands[i] += (target - display_bands[i]) * ATTACK_COEFF
        else:
            display_bands[i] += (target - display_bands[i]) * DECAY_COEFF

        # Map dBFS to 0..1
        db_val = max(display_bands[i], NOISE_FLOOR)
        fraction = (db_val - NOISE_FLOOR) / DB_RANGE

        # Peak hold
        if fraction >= peak_bands[i]:
            peak_bands[i] = fraction
            peak_time[i] = now
        elif now - peak_time[i] > PEAK_HOLD_S:
            peak_bands[i] -= PEAK_FALL_DB / DB_RANGE
            if peak_bands[i] < 0:
                peak_bands[i] = 0

        bar_h = 0 if fraction < 0.01 else max(2, int(fraction * bar_area_h))
        bx = pad + i * (bar_w + bar_gap)
        by = bar_base_y - bar_h

        if bar_h == 0 and peak_bands[i] < 0.01:
            continue

        color = BAR_COLORS[i]

        # Bar
        if bar_h > 0:
            draw.rectangle([bx, by, bx + bar_w, bar_base_y], fill=color)
            # Rounded top
            if bar_h > 3:
                r = min(bar_w // 2, 3)
                draw.ellipse([bx, by - r, bx + bar_w, by + r], fill=color)

        # Peak marker
        if peak_bands[i] > 0.01:
            peak_h = int(peak_bands[i] * bar_area_h)
            peak_y = bar_base_y - peak_h
            marker_h = max(2, bar_w // 12)
            draw.rectangle([bx, peak_y, bx + bar_w, peak_y + marker_h],
                           fill=PEAK_COLORS[i])

    return img


async def spectrum_ws_reader() -> None:
    """Connect to spectrum WebSocket and update band dBFS values."""
    ws_url = f"ws://localhost:{WS_PORT}"
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info(f"Connected to spectrum WebSocket: {ws_url}")
                async for message in ws:
                    values = message.split(";")
                    resize_bands(len(values))
                    for i in range(NUM_BANDS):
                        try:
                            v = float(values[i])
                            bands[i] = v if not np.isnan(v) else NOISE_FLOOR
                        except ValueError:
                            bands[i] = NOISE_FLOOR
        except Exception as e:
            logger.debug(f"Spectrum WS error: {e}")
            bands[:] = NOISE_FLOOR
            await asyncio.sleep(5)


async def metadata_poller() -> None:
    """Poll metadata endpoint periodically."""
    global current_metadata, metadata_version
    while True:
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(METADATA_URL, timeout=3)
            )
            if resp.status_code == 200:
                data = resp.json()
                if data != current_metadata:
                    current_metadata = data
                    metadata_version += 1
        except Exception:
            pass
        await asyncio.sleep(2)


def is_spectrum_active() -> bool:
    """Check if any spectrum band has meaningful signal above noise floor."""
    threshold = NOISE_FLOOR + 3.0  # 3 dB above noise floor
    return bool(np.any(bands > threshold))


async def render_loop() -> None:
    """Main render loop with adaptive FPS.

    Full frame redrawn only on metadata change.
    Spectrum region redrawn each tick at adaptive rate:
      - 20 FPS: music playing with active spectrum
      -  5 FPS: music playing, no spectrum data
      -  1 FPS: no music playing (static screen)
    """
    global base_frame, base_frame_version, spectrum_bg

    FPS_ACTIVE = 20    # spectrum animating
    FPS_QUIET = 5      # playing but silent/no spectrum
    FPS_IDLE = 1       # no music at all

    prev_spectrum_active = False

    while True:
        start = time.monotonic()

        # Rebuild base frame if metadata changed
        if base_frame_version != metadata_version:
            base_frame = await asyncio.get_event_loop().run_in_executor(
                None, render_base_frame
            )
            spectrum_bg = extract_spectrum_bg()
            base_frame_version = metadata_version
            # Write full frame once
            await asyncio.get_event_loop().run_in_executor(
                None, write_full_frame, base_frame
            )
            logger.info("Base frame updated (metadata changed)")

        if spectrum_bg is None:
            await asyncio.sleep(0.1)
            continue

        # Determine adaptive FPS
        is_playing = (
            current_metadata
            and current_metadata.get("playing")
            and current_metadata.get("title")
        )
        spectrum_active = is_spectrum_active()

        if is_playing and spectrum_active:
            fps = FPS_ACTIVE
        elif is_playing:
            fps = FPS_QUIET
        else:
            fps = FPS_IDLE

        # Skip spectrum write entirely when idle and nothing is animating
        if not is_playing and not spectrum_active and not prev_spectrum_active:
            await asyncio.sleep(1.0 / fps)
            prev_spectrum_active = False
            continue

        prev_spectrum_active = spectrum_active

        # Render only spectrum region
        spec_img = await asyncio.get_event_loop().run_in_executor(
            None, render_spectrum
        )
        # Write only the spectrum region to FB
        await asyncio.get_event_loop().run_in_executor(
            None, write_region_to_fb,
            spec_img, layout["right_x"], layout["spec_y"],
        )

        elapsed = time.monotonic() - start
        sleep_time = (1.0 / fps) - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


async def main() -> None:
    """Start all tasks."""
    global layout

    logger.info(f"Starting framebuffer display: {WIDTH}x{HEIGHT}")
    logger.info(f"  Metadata: {METADATA_URL}")
    logger.info(f"  Spectrum WS port: {WS_PORT}")
    logger.info(f"  Framebuffer: {FB_DEVICE}")

    open_framebuffer()
    layout = compute_layout()
    precompute_colors()

    logger.info(
        f"  Layout: art={layout['art_size']}px, "
        f"spectrum={layout['right_w']}x{layout['spec_h']}px, "
        f"FPS={TARGET_FPS}"
    )

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
