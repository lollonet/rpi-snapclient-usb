#!/usr/bin/env python3
"""Framebuffer display renderer for Raspberry Pi.

Renders album art (left), track info (top-right), and spectrum bars
(bottom-right, 55% height) directly to /dev/fb0.

Performance: static content (art, text) is cached and only redrawn on
metadata change. Spectrum region uses numpy arrays for fast rendering
and a pre-allocated framebuffer write buffer to avoid per-frame allocations.
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
    precompute_fb_colors()
    layout = compute_layout()
    _init_spectrum_buffer()
    logger.info(f"Band count changed to {n}")

# Smoothing coefficients
ATTACK_COEFF = 0.6  # fast attack (higher = faster)
DECAY_COEFF = 0.35  # decay speed (higher = faster)
PEAK_HOLD_S = 1.5   # seconds before peak marker vanishes

# Auto-gain: track running maximum for volume-independent display
AUTO_GAIN_ATTACK = 0.3   # how fast gain rises to new peaks
AUTO_GAIN_DECAY = 0.005  # how slowly gain drops (very slow to avoid pumping)
auto_gain_ref: float = NOISE_FLOOR + 30  # current auto-gain reference level (dBFS)

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

# Cached frames: base_frame has bg+art+text, spectrum_bg is native FB format
base_frame: Image.Image | None = None
base_frame_version: int = -1
spectrum_bg_np: np.ndarray | None = None  # numpy RGB array for alpha blending
spectrum_bg_fb: np.ndarray | None = None  # native FB format (RGB565 or BGRA32)

# Cached volume knob overlay (re-rendered only when volume changes)
_vol_knob_cache: dict = {"vol": None, "muted": None, "img": None, "np": None}

# Cached fonts (loaded once)
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

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


def write_region_to_fb_fast(fb_pixels: np.ndarray, x: int, y: int) -> None:
    """Write a native-format pixel array to the framebuffer at position (x, y).

    Accepts pre-converted pixels: uint16 (h,w) for 16bpp or uint8 (h,w,4) for 32bpp.
    No per-frame RGB→FB conversion needed.
    """
    if fb_mmap is None:
        return

    h, w = fb_pixels.shape[:2]
    bpp_bytes = fb_bpp // 8
    row_bytes = w * bpp_bytes

    for row in range(h):
        offset = (y + row) * fb_stride + x * bpp_bytes
        fb_mmap.seek(offset)
        fb_mmap.write(fb_pixels[row].tobytes())


def write_full_frame(img: Image.Image) -> None:
    """Write a full-screen image to the framebuffer."""
    if fb_mmap is None:
        return
    rgb = np.array(img.convert("RGB"))
    fb_pixels = _rgb_to_fb_native(rgb)
    # Write row by row to handle stride
    h = fb_pixels.shape[0]
    bpp_bytes = fb_bpp // 8
    row_bytes = fb_pixels.shape[1] * bpp_bytes if fb_bpp == 16 else fb_pixels.shape[1] * 4
    if fb_stride == row_bytes:
        fb_mmap.seek(0)
        fb_mmap.write(fb_pixels.tobytes())
    else:
        for row in range(h):
            fb_mmap.seek(row * fb_stride)
            fb_mmap.write(fb_pixels[row].tobytes())


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load font with caching."""
    key = ("bold" if bold else "regular", size)
    if key in _font_cache:
        return _font_cache[key]

    if bold:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
    else:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
    for path in paths:
        if os.path.exists(path):
            font = ImageFont.truetype(path, size)
            _font_cache[key] = font
            return font
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return _get_font(size, bold=False)


def load_bold_font(size: int) -> ImageFont.FreeTypeFont:
    return _get_font(size, bold=True)


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


def _rgb_to_fb_native(rgb_array: np.ndarray) -> np.ndarray:
    """Convert RGB numpy array to native FB pixel format array.

    Returns uint16 (h,w) for 16bpp or uint8 (h,w,4) for 32bpp.
    """
    if fb_bpp == 16:
        r = rgb_array[:, :, 0].astype(np.uint16)
        g = rgb_array[:, :, 1].astype(np.uint16)
        b = rgb_array[:, :, 2].astype(np.uint16)
        return (((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)).astype(np.uint16)
    else:
        h, w = rgb_array.shape[:2]
        bgra = np.empty((h, w, 4), dtype=np.uint8)
        bgra[:, :, 0] = rgb_array[:, :, 2]
        bgra[:, :, 1] = rgb_array[:, :, 1]
        bgra[:, :, 2] = rgb_array[:, :, 0]
        bgra[:, :, 3] = 255
        return bgra


def _rgb_tuple_to_fb(r: int, g: int, b: int) -> int | tuple:
    """Convert a single RGB tuple to native FB pixel value."""
    if fb_bpp == 16:
        return int(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    return (b, g, r, 255)


# Pre-computed bar/peak colors in native FB format (populated after FB init)
BAR_COLORS_FB: list = []
PEAK_COLORS_FB: list = []


def precompute_fb_colors() -> None:
    """Pre-compute bar/peak colors in native FB pixel format."""
    global BAR_COLORS_FB, PEAK_COLORS_FB
    BAR_COLORS_FB = [_rgb_tuple_to_fb(*c) for c in BAR_COLORS]
    PEAK_COLORS_FB = [_rgb_tuple_to_fb(*c) for c in PEAK_COLORS]


def _init_spectrum_buffer() -> None:
    """Initialize pre-allocated spectrum numpy buffer after layout is known."""
    global spectrum_bg_np, spectrum_bg_fb
    L = layout
    if not L:
        return
    spectrum_bg_np = None  # will be set from base frame
    spectrum_bg_fb = None  # will be set from base frame


def fit_font(text: str, max_width: int, base_size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Return the largest font size (down to 10px) that fits text within max_width."""
    for size in range(base_size, 9, -1):
        font = _get_font(size, bold)
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
    return _get_font(10, bold)


def _format_audio_badge(meta: dict) -> str:
    """Build audio format badge text from metadata."""
    codec = meta.get("codec", "")
    if not codec:
        return ""

    sample_rate = meta.get("sample_rate", 0)
    bit_depth = meta.get("bit_depth", 0)
    bitrate = meta.get("bitrate", 0)

    # Lossless codecs: show sample rate and bit depth
    lossless = codec in ("FLAC", "WAV", "AIFF", "APE", "WV", "PCM", "DSD")

    parts = [codec]
    if lossless and sample_rate:
        if sample_rate >= 1000:
            parts.append(f"{sample_rate / 1000:.0f}kHz" if sample_rate % 1000 == 0
                         else f"{sample_rate / 1000:.1f}kHz")
        else:
            parts.append(f"{sample_rate}Hz")
        if bit_depth:
            parts.append(f"{bit_depth}bit")
    elif bitrate:
        parts.append(f"{bitrate}kbps")
    elif sample_rate:
        if sample_rate >= 1000:
            parts.append(f"{sample_rate / 1000:.0f}kHz" if sample_rate % 1000 == 0
                         else f"{sample_rate / 1000:.1f}kHz")

    return " ".join(parts)


# Badge colors by quality tier
_BADGE_COLOR_LOSSLESS = (100, 200, 120)   # green — lossless
_BADGE_COLOR_HD = (120, 160, 255)          # blue — hi-res
_BADGE_COLOR_LOSSY = (170, 140, 100)       # amber — lossy


def _format_badge_color(meta: dict) -> tuple[int, int, int]:
    """Pick badge color based on codec quality tier."""
    codec = meta.get("codec", "")
    sample_rate = meta.get("sample_rate", 0)
    lossless = codec in ("FLAC", "WAV", "AIFF", "APE", "WV", "PCM", "DSD")

    if lossless and sample_rate > 48000:
        return _BADGE_COLOR_HD  # hi-res
    if lossless:
        return _BADGE_COLOR_LOSSLESS
    return _BADGE_COLOR_LOSSY


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

        ft_title = fit_font(title, max_text_w, base_title_size, bold=True) if title else None
        ft_artist = fit_font(artist, max_text_w, base_detail_size) if artist else None
        ft_album = fit_font(album, max_text_w, base_detail_size) if album else None

        # Audio format badge
        fmt_text = _format_audio_badge(meta) if meta else ""
        badge_size = max(10, HEIGHT // 36)

        line_gap = 4
        total_h = 0
        if ft_title:
            total_h += ft_title.size
        if ft_artist:
            total_h += ft_artist.size + line_gap
        if ft_album:
            total_h += ft_album.size + line_gap // 2
        if fmt_text:
            total_h += badge_size + line_gap

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
            text_y += ft_album.size + line_gap

        # Audio format badge (e.g. "FLAC 48kHz/16bit" or "MP3 320kbps")
        if fmt_text:
            ft_badge = _get_font(badge_size)
            bbox = draw.textbbox((0, 0), fmt_text, font=ft_badge)
            tw = bbox[2] - bbox[0]
            draw.text((text_right - tw, text_y), fmt_text,
                      fill=_format_badge_color(meta), font=ft_badge)
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


def extract_spectrum_bg() -> None:
    """Extract the spectrum region from base frame in both RGB and native FB format."""
    global spectrum_bg_np, spectrum_bg_fb
    L = layout
    region = base_frame.crop((
        L["right_x"], L["spec_y"],
        L["right_x"] + L["right_w"], L["spec_y"] + L["spec_h"],
    ))
    spectrum_bg_np = np.array(region.convert("RGB"), dtype=np.uint8)
    spectrum_bg_fb = _rgb_to_fb_native(spectrum_bg_np)


def _render_volume_knob(vol: int, muted: bool) -> Image.Image:
    """Render the volume knob as a small RGBA image. Cached."""
    L = layout
    radius = max(12, L["spec_h"] // 14)
    size = radius * 2 + 4
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    ring_w = max(2, radius // 5)

    # Background ring (dark)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=(50, 50, 50), width=ring_w,
    )

    # Filled arc proportional to volume
    if not muted and vol > 0:
        sweep = vol / 100.0 * 360
        draw.arc(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            start=135, end=135 + sweep,
            fill=ARTIST_COLOR, width=ring_w,
        )

    # Volume text centered inside (smaller font)
    vol_text = "M" if muted else str(vol)
    vol_font = _get_font(max(8, int(radius * 0.7)))
    bbox = draw.textbbox((0, 0), vol_text, font=vol_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw // 2, cy - th // 2 - bbox[1]),
        vol_text,
        fill=ARTIST_COLOR if not muted else (200, 60, 60),
        font=vol_font,
    )
    return img


def _get_volume_knob() -> Image.Image | None:
    """Get cached volume knob image, re-rendering only when volume changes."""
    meta = current_metadata
    if not meta:
        return None
    vol = meta.get("volume")
    muted = meta.get("muted", False)
    if vol is None:
        return None
    vol = max(0, min(100, vol))

    if vol == _vol_knob_cache["vol"] and muted == _vol_knob_cache["muted"]:
        return _vol_knob_cache["np"]

    img = _render_volume_knob(vol, muted)
    knob_np = np.array(img)
    _vol_knob_cache["vol"] = vol
    _vol_knob_cache["muted"] = muted
    _vol_knob_cache["img"] = img
    _vol_knob_cache["np"] = knob_np
    return knob_np


def render_spectrum() -> np.ndarray:
    """Render spectrum bars in native FB format (RGB565 or BGRA32).

    Works directly in framebuffer pixel format to avoid per-frame RGB→RGB565
    conversion (~10ms saved on Pi 4).
    """
    global auto_gain_ref, display_bands, peak_bands, peak_time

    L = layout
    now = time.monotonic()

    # Start from clean spectrum background in native FB format
    buf = spectrum_bg_fb.copy()

    pad = L["pad"]
    bar_area_h = L["bar_area_h"]
    bar_gap = L["bar_gap"]
    bar_w = L["bar_w"]
    bar_base_y = L["spec_h"] - pad  # relative to region

    # Auto-gain: find current peak across all bands
    current_max = float(np.max(bands))
    if current_max > auto_gain_ref:
        auto_gain_ref += (current_max - auto_gain_ref) * AUTO_GAIN_ATTACK
    else:
        auto_gain_ref += (current_max - auto_gain_ref) * AUTO_GAIN_DECAY
    min_ref = NOISE_FLOOR + 20
    auto_gain_ref = max(auto_gain_ref, min_ref)
    gain_range = max(auto_gain_ref - NOISE_FLOOR, 1.0)

    # Vectorized asymmetric smoothing
    attack_mask = bands > display_bands
    alpha = np.where(attack_mask, ATTACK_COEFF, DECAY_COEFF)
    display_bands += (bands - display_bands) * alpha

    # Map dBFS to 0..1 (vectorized)
    db_vals = np.maximum(display_bands, NOISE_FLOOR)
    fractions = np.clip((db_vals - NOISE_FLOOR) / gain_range, 0.0, 1.0)

    # Peak hold — vectorized
    new_peak_mask = fractions >= peak_bands
    peak_bands[new_peak_mask] = fractions[new_peak_mask]
    peak_time[new_peak_mask] = now
    expired_mask = (~new_peak_mask) & ((now - peak_time) > PEAK_HOLD_S)
    peak_bands[expired_mask] = 0

    marker_h = max(2, bar_w // 12)

    # Draw bars (this loop is necessary for array slice writes but body is minimal)
    for i in range(NUM_BANDS):
        fraction = fractions[i]
        bx = pad + i * (bar_w + bar_gap)

        if fraction < 0.01 and peak_bands[i] < 0.01:
            continue

        if fraction >= 0.01:
            bar_h = max(2, int(fraction * bar_area_h))
            by = max(0, bar_base_y - bar_h)
            if fb_bpp == 16:
                buf[by:bar_base_y, bx:bx + bar_w] = BAR_COLORS_FB[i]
            else:
                buf[by:bar_base_y, bx:bx + bar_w, :] = BAR_COLORS_FB[i]

        if peak_bands[i] > 0.01:
            peak_h = int(peak_bands[i] * bar_area_h)
            peak_y = max(0, bar_base_y - peak_h)
            if fb_bpp == 16:
                buf[peak_y:peak_y + marker_h, bx:bx + bar_w] = PEAK_COLORS_FB[i]
            else:
                buf[peak_y:peak_y + marker_h, bx:bx + bar_w, :] = PEAK_COLORS_FB[i]

    # Composite volume knob — blend in RGB, convert only the small knob region
    knob_np = _get_volume_knob()
    if knob_np is not None:
        kh, kw = knob_np.shape[:2]
        kx = L["right_w"] - pad // 2 - kw
        ky = max(0, pad // 2 - kh // 4)
        ky2 = min(ky + kh, buf.shape[0])
        kx2 = min(kx + kw, buf.shape[1])
        kh_clip = ky2 - ky
        kw_clip = kx2 - kx
        if kh_clip > 0 and kw_clip > 0:
            # Alpha-blend in RGB space using the RGB background
            alpha = knob_np[:kh_clip, :kw_clip, 3:4].astype(np.float32) / 255.0
            rgb_k = knob_np[:kh_clip, :kw_clip, :3].astype(np.float32)
            bg_rgb = spectrum_bg_np[ky:ky2, kx:kx2].astype(np.float32)
            blended = (rgb_k * alpha + bg_rgb * (1.0 - alpha)).astype(np.uint8)
            # Convert only the small knob region to native FB format
            knob_fb = _rgb_to_fb_native(blended)
            buf[ky:ky2, kx:kx2] = knob_fb

    return buf


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
                # Ignore volatile fields (bitrate) for change detection
                old_stable = {k: v for k, v in (current_metadata or {}).items()
                              if k != "bitrate"}
                new_stable = {k: v for k, v in data.items() if k != "bitrate"}
                if new_stable != old_stable:
                    current_metadata = data
                    metadata_version += 1
                else:
                    current_metadata = data  # update bitrate silently
        except Exception:
            pass
        await asyncio.sleep(2)


def is_spectrum_active() -> bool:
    """Check if any spectrum band has meaningful signal above noise floor."""
    threshold = NOISE_FLOOR + 3.0
    return bool(np.any(bands > threshold))


async def render_loop() -> None:
    """Main render loop with adaptive FPS."""
    global base_frame, base_frame_version, spectrum_bg_np

    FPS_ACTIVE = 20
    FPS_QUIET = 5
    FPS_IDLE = 1

    prev_spectrum_active = False

    while True:
        start = time.monotonic()

        # Rebuild base frame if metadata changed
        if base_frame_version != metadata_version:
            base_frame = await asyncio.get_event_loop().run_in_executor(
                None, render_base_frame
            )
            extract_spectrum_bg()
            base_frame_version = metadata_version
            await asyncio.get_event_loop().run_in_executor(
                None, write_full_frame, base_frame
            )
            logger.info("Base frame updated (metadata changed)")

        if spectrum_bg_np is None or spectrum_bg_fb is None:
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

        # Render spectrum as numpy array and write directly to FB
        spec_rgb = await asyncio.get_event_loop().run_in_executor(
            None, render_spectrum
        )
        await asyncio.get_event_loop().run_in_executor(
            None, write_region_to_fb_fast,
            spec_rgb, layout["right_x"], layout["spec_y"],
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
    precompute_fb_colors()
    _init_spectrum_buffer()

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
