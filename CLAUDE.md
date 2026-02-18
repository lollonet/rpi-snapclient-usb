# CLAUDE.md — rpi-snapclient-usb

Raspberry Pi Snapcast client with auto-detection, Docker services, and framebuffer display.

## Architecture

```
common/
├── docker-compose.yml          # All services, profiles: framebuffer | browser
├── .env.example                # Full config reference
├── docker/
│   ├── snapclient/             # Core audio client (ALSA → Snapserver)
│   ├── metadata-service/       # Track info via WebSocket (port 8082)
│   ├── audio-visualizer/       # FFT spectrum via WebSocket (port 8081)
│   └── fb-display/             # Framebuffer renderer (/dev/fb0)
├── scripts/setup.sh            # Main installer (--auto supported)
├── public/                     # Web UI assets
└── audio-hats/                 # HAT overlay configs
install/snapclient.conf         # User-facing config defaults
prepare-sd.sh                   # SD card auto-install prep
```

## Key Rules

### mDNS Discovery
Use `_snapcast._tcp` (port 1704), **never** `_snapcast-ctrl._tcp`. RPC port = streaming_port + 1.

### Auto-Detection First
- Audio HAT: EEPROM at `/proc/device-tree/hat/product`, fallback to ALSA card names, then USB
- Snapserver: mDNS discovery, never hardcode IP
- Display resolution: `DISPLAY_RESOLUTION` env var optional; auto-detect from framebuffer, capped at 1920×1080

### Read-Only Filesystem
- Enabled by default (`ENABLE_READONLY=true`)
- Docker **must** use `fuse-overlayfs` storage driver — kernel overlay2 fails on overlayfs root
- `ro-mode.sh enable/disable/status` manages it; requires reboot
- Use `--no-readonly` flag on setup.sh to skip

### Display Rendering
- `fb_display.py` bind-mounted into container (live updates without image rebuild)
- Resolution scaling: renders at internal res, scales to actual FB on output
- Bottom bar: logo (left), date+time (center), volume knob (right)
- **Song Progress Bar**: elapsed/duration for file playback, uses local clock for smooth updates
- Timezone: mount `/etc/localtime` and `/etc/timezone` into container
- Install progress screen: `video=HDMI-A-1:800x600@60` in cmdline.txt (KMS ignores hdmi_group/hdmi_mode); remove after install

### Metadata Service
- Polls Snapserver JSON-RPC every 2s, pushes to clients via WebSocket (port 8082)
- Extracts `position` and `duration` from Snapserver MPRIS properties
- fb-display uses local clock between updates for smooth progress bar animation
- Artwork: embedded MPD → iTunes → MusicBrainz → Radio-Browser (for stations)
- **Known limitation**: mDNS discovery runs once at startup; no failover or re-discovery if the connected server goes down. Set `SNAPSERVER_HOST` explicitly to pin to a specific server

### Spectrum Analyzer
- Third-octave default: 31 bands (ISO 266), 20 Hz–20 kHz
- Half-octave option: 21 bands, set `BAND_MODE=half-octave`
- Band count auto-detected by display from first WebSocket message

### Deployment
- **SD card**: `prepare-sd.sh` patches firstrun for auto-install
- **Live update**: rsync changed files + `docker compose up -d --force-recreate`
- Bind-mounted files: `fb_display.py`, `visualizer.py`, `metadata-service.py` — no image rebuild needed
- Device hosts: `snapdigi` (192.168.63.5), `snapvideo` — SSH user `claudio`

### Git & CI
- Pre-push hook runs shellcheck, bash syntax, HAT config validation
- Docker images: `ghcr.io/lollonet/rpi-snapclient-usb[-*]:latest` + `nginx:alpine` (ARM64 only)
- Branch naming: `feature/<desc>` or `fix/<desc>`, always use PRs
