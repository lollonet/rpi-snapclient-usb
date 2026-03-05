# UI/UX Design

## Display Layout

The framebuffer display uses a fixed layout with four main areas:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   ┌──────────┐   ┌──────────────────────────────────────┐   │
│   │          │   │  Source: MPD                          │   │
│   │  Album   │   │  Title: Bohemian Rhapsody             │   │
│   │   Art    │   │  Artist: Queen                        │   │
│   │          │   │  Album: A Night at the Opera          │   │
│   │ (square) │   │                                      │   │
│   │          │   │  ┌──────────────────────┐             │   │
│   │          │   │  │ FLAC · 44.1kHz · 16b │             │   │
│   └──────────┘   └──────────────────────────────────────┘   │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐  │   │
│   │  ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐  │   │
│   │  ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐ ▐  │   │
│   │         SPECTRUM ANALYZER (21 or 31 bands)          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  ━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░  1:23 / 5:54      │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌──────┐        Thu 05 Mar · 14:32:18        ┌────────┐  │
│   │ LOGO │                                     │ VOL 🔊 │  │
│   └──────┘                                     └────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Areas

| Area | Position | Content |
|------|----------|---------|
| Album Art | Top-left | Square cover art, fetched from metadata service |
| Info Panel | Top-right | Source, title, artist, album, format badge |
| Spectrum | Center | Real-time frequency bars (rainbow gradient) |
| Progress Bar | Above bottom bar | Elapsed/total time, filled progress indicator |
| Bottom Bar | Bottom | Logo (left), date+time (center), volume knob (right) |

## Format Badge

Color-coded audio quality indicator:

| Badge Color | Condition | Examples |
|-------------|-----------|---------|
| Green | Lossless, standard rate | FLAC 44.1kHz, WAV 48kHz |
| Blue | Lossless, high-res (>48kHz) | FLAC 96kHz, DSD64 |
| Amber | Lossy codec | MP3 320kbps, AAC, OGG |

Format string: `CODEC · SAMPLE_RATE · BIT_DEPTH` (e.g., `FLAC · 44.1kHz · 16b`)

## Spectrum Analyzer

- Vertical bars with rainbow gradient (red at low frequencies, violet at high)
- Height proportional to dBFS level (60 dB display range)
- Attack/decay smoothing for visual continuity
- Idle wave animation when no audio is playing

## Standby Screen

When no audio is playing for an extended period:
- Retro hi-fi artwork with breathing opacity animation
- Smooth transition from active to standby

## Resolution Handling

| Step | Action |
|------|--------|
| 1 | Read actual framebuffer dimensions from `/dev/fb0` |
| 2 | Use `DISPLAY_RESOLUTION` override if set, else auto-detect |
| 3 | Cap render resolution at 1920x1080 (performance) |
| 4 | Render at internal resolution |
| 5 | Scale output to actual framebuffer dimensions |

### Tested Resolutions

| Display | Resolution | Depth |
|---------|-----------|-------|
| Official 7" touchscreen | 800x480 | 16bpp |
| 9" HDMI touchscreen | 1024x600 | 16bpp |
| HDMI monitor | 1920x1080 | 16bpp/32bpp |
| 4K HDMI TV | 3840x2160 | 32bpp (capped at 1080p render) |

## Pixel Format Support

| Platform | Byte Order | 32bpp Format | 16bpp Format |
|----------|-----------|-------------|-------------|
| ARM (Pi) | Little-endian | BGRA `[B][G][R][X]` | RGB565 |
| PowerPC | Big-endian | XRGB `[X][R][G][B]` | RGB565 |

## Planned: Multi-Display Layout Templates

Future support for aspect-ratio-specific templates:
- 16:9 (standard HDMI)
- 4:3 (legacy displays)
- ~16:10 (1024x600 touchscreens)

Each template would optimize art size, info panel width, and spectrum height for the target ratio.
