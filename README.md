# Raspberry Pi Snapcast Client with HiFiBerry & Cover Display

Docker-based Snapcast client for Raspberry Pi with HiFiBerry DACs, featuring synchronized multiroom audio and visual cover art display.

## Multiroom Audio Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       MULTIROOM AUDIO SETUP                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌────────────────────────────────────────────────────────────────┐     │
│   │                    SERVER (Single Host)                        │     │
│   │  ┌─────────────────┐    ┌────────────────────────────────────┐ │     │
│   │  │  MPD            │───▶│  Snapserver                        │ │     │
│   │  │  - Local files  │    │  - Streams to all clients          │ │     │
│   │  │  - Playlists    │FIFO│  - Ports configured via .env       │ │     │
│   │  │  - Metadata     │    │  - Synchronized playback           │ │     │
│   │  └─────────────────┘    └────────────────────────────────────┘ │     │
│   └────────────────────────────────────────────────────────────────┘     │
│                                    │                                     │
│                          Network (WiFi/Ethernet)                         │
│                                    │                                     │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                                ▼                                │    │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│   │  │ Pi Client 1 │  │ Pi Client 2 │  │ Pi Client N │              │    │
│   │  │ Living Room │  │ Bedroom     │  │ Kitchen     │              │    │
│   │  │ HiFiBerry   │  │ HiFiBerry   │  │ HiFiBerry   │              │    │
│   │  │ DAC+/Digi+  │  │ DAC+/Digi+  │  │ DAC+/Digi+  │              │    │
│   │  │ + Display   │  │ + Display   │  │ (optional)  │              │    │
│   │  └─────────────┘  └─────────────┘  └─────────────┘              │    │
│   │                                                                 │    │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│   │  │   Mobile    │  │   Desktop   │  │   Smart TV  │              │    │
│   │  │ Phone/Tablet│  │ PC/Mac      │  │ Android TV  │              │    │
│   │  │ Snapclient  │  │ Snapclient  │  │ Snapclient  │              │    │
│   │  └─────────────┘  └─────────────┘  └─────────────┘              │    │
│   │                    SNAPCAST CLIENTS                             │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│   ┌────────────────────────────────────────────────────────────────┐     │
│   │                      CONTROL APPS                              │     │
│   │  Mobile (Recommended):        Desktop:                         │     │
│   │  - MALP (Android)             - Cantata                        │     │
│   │  - MPDroid                    - GMPC                           │     │
│   │  - MPoD (iOS)                 - Sonata                         │     │
│   │  - Rigelian (iOS)             - Persephone (macOS)             │     │
│   └────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Note**: Mobile apps are more mature and feature-rich for MPD control. This project provides the Raspberry Pi client implementation shown above.

## Features

- 🎵 **Synchronized Audio**: Multi-room playback via Snapcast
- 🎨 **Cover Display**: Full-screen album art with track metadata (MPD embedded art → iTunes → MusicBrainz)
- ⏱️ **Song Progress Bar**: Elapsed/duration time with visual progress for file playback (uses local clock for smooth updates)
- 📊 **Real-Time Spectrum Analyzer**: dBFS FFT visualizer with half/third-octave bands, auto-gain normalization
- 😴 **Standby Screen**: Retro hi-fi artwork with breathing animation when idle
- 🔍 **mDNS Autodiscovery**: Snapserver found automatically — no IP configuration needed
- 🎛️ **Multiple Audio HATs**: Support for 10 popular Raspberry Pi audio HATs + USB audio
- 📺 **Flexible Display**: Direct framebuffer rendering, 6 resolution presets (800x480 to 4K)
- ⚡ **Zero-Touch Install**: Flash SD, power on, auto-detects HAT with visual progress display
- 🐳 **Docker-based**: Pre-built images for easy deployment
- 🔄 **Auto-start**: Systemd services for automatic startup
- 🔒 **Security Hardened**: Input validation, SSRF protection, granular capabilities
- 💾 **Read-Only Filesystem**: SD card protection with overlayfs, enabled by default (preserves SD card lifespan)
- 📡 **WebSocket Metadata**: Real-time track info push to display (no polling from clients)
- 📊 **Resource Limits**: Auto-detected CPU/memory limits based on Pi RAM

## Supported Audio HATs

| HAT | Type | Output |
|-----|------|--------|
| **HiFiBerry DAC+** | Analog | Line out, headphones |
| **HiFiBerry Digi+** | S/PDIF | Digital coax/optical |
| **HiFiBerry DAC2 HD** | Analog HD | High-res line out |
| **IQaudio DAC+** | Analog | Line out |
| **IQaudio DigiAMP+** | Analog+Amp | Speaker terminals |
| **IQaudio Codec Zero** | Analog | Line in/out |
| **Allo Boss DAC** | Analog | High-res line out |
| **Allo DigiOne** | S/PDIF | Digital coax/optical |
| **JustBoom DAC** | Analog | Line out, headphones |
| **JustBoom Digi** | S/PDIF | Digital coax/optical |
| **USB Audio** | Varies | Any USB DAC/soundcard |

## Hardware Requirements

### Common Components
- Raspberry Pi 4 (2GB+)
- USB drive (8GB+ for boot)
- Display: 9" touchscreen (1024x600) or 4K HDMI TV (3840x2160)
- One of the supported audio HATs listed above, or a USB audio device

### Compatibility Matrix

#### Raspberry Pi Models

| Model | Status | Notes |
|-------|--------|-------|
| Pi 4 (2GB) | Tested | Medium resource profile |
| Pi 4 (4GB) | Tested | High resource profile |
| Pi 4 (8GB) | Tested | High resource profile |
| Pi 5 | Untested | Should work, high profile |
| Pi 3B+ | Untested | Low resource profile |
| Pi Zero 2 W | Untested | Low resource profile, no framebuffer display |

#### Displays

| Display | Resolution | Notes |
|---------|-----------|-------|
| Official 7" touchscreen | 800x480 | Tested |
| 9" HDMI touchscreen | 1024x600 | Tested |
| HDMI monitor 1080p | 1920x1080 | Tested |
| 4K HDMI TV | 3840x2160 | Render capped at 1920x1080, scaled |

## Zero-Touch Auto-Install (Recommended)

The easiest way to get started — no SSH, no terminal needed.

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager
   - Configure WiFi and hostname in the Imager settings
2. Re-insert SD card in your computer
3. Run `./prepare-sd.sh` (auto-detects boot partition), or manually copy `install/` folder as `snapclient/` to the boot partition
4. Eject SD card, insert in Pi, power on
5. Wait ~5 minutes — Pi auto-detects your audio HAT, installs everything, and reboots

> **HAT auto-detection**: The Pi reads your HAT's EEPROM at boot (`/proc/device-tree/hat/product`) — no configuration needed for any of the 11 supported HATs. Falls back to USB audio if no HAT is found.

> **Custom settings**: Edit `snapclient/snapclient.conf` on the boot partition before step 4 to override defaults (resolution, display mode, band mode, snapserver host).

| File | Purpose |
|------|---------|
| `prepare-sd.sh` | Copies files to boot partition, patches `firstrun.sh` |
| `install/snapclient.conf` | Config with sensible defaults (`AUDIO_HAT=auto`) |
| `install/firstboot.sh` | Auto-runs on first boot, chains `setup.sh --auto` |
| `install/README.txt` | 5-line quick reference |

## Manual Setup

For advanced users who prefer interactive control, see **[QUICKSTART.md](QUICKSTART.md)**.

### Summary

1. Flash Raspberry Pi OS Lite (64-bit) to USB drive
2. Enable SSH and WiFi in Raspberry Pi Imager settings
3. Boot Pi with your audio HAT attached
4. Copy project files and run `sudo bash common/scripts/setup.sh`
5. Select your audio HAT (11 options) and display resolution (6 presets + custom)
6. Optionally enter Snapserver IP (or leave empty for mDNS autodiscovery) and reboot

The setup script installs Docker CE, automatically configures your audio HAT and ALSA, sets up the cover display for your chosen resolution, and creates systemd services for auto-start. Client ID is automatically generated from hostname.

## Project Structure

```
rpi-snapclient-usb/
├── install/                    # Zero-touch auto-install files
│   ├── snapclient.conf         # Config defaults (AUDIO_HAT=auto)
│   ├── firstboot.sh            # First-boot installer (runs once)
│   └── README.txt              # 5-line quick reference
│
├── prepare-sd.sh               # Copy files to SD boot partition
│
├── common/
│   ├── scripts/setup.sh        # Main installation script (--auto mode)
│   ├── docker-compose.yml      # Unified Docker services
│   ├── .env.example            # Environment template
│   ├── audio-hats/             # Audio HAT configurations (11 files)
│   │   ├── hifiberry-dac.conf
│   │   ├── hifiberry-digi.conf
│   │   ├── hifiberry-dac2hd.conf
│   │   ├── iqaudio-*.conf
│   │   ├── allo-*.conf
│   │   ├── justboom-*.conf
│   │   └── usb-audio.conf
│   └── docker/
│       ├── snapclient/         # Snapclient Docker image
│       ├── audio-visualizer/   # Spectrum analyzer (dBFS)
│       └── fb-display/         # Framebuffer display renderer
│
├── scripts/                    # Development scripts
│   ├── ci-local.sh             # Local CI runner
│   └── install-hooks.sh        # Git hooks installer
│
├── tests/                      # Test scripts
│   └── test-hat-configs.sh     # HAT config validation
│
└── .github/workflows/          # CI/CD pipelines
```

## Configuration

The setup script auto-generates `/opt/snapclient/.env` from your selections. See [`common/.env.example`](common/.env.example) for all available settings (server, audio, display, spectrum, resource limits, read-only filesystem).

To change settings after installation:

```bash
sudo nano /opt/snapclient/.env
cd /opt/snapclient
sudo docker compose up -d   # NOT restart — restart doesn't pick up .env changes
```

## Post-Install Verification

Follow these steps in order after installation to confirm everything works.

### 1. Docker services running

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'
```

Expected: all containers show `Up ... (healthy)`:

```
NAMES              STATUS
fb-display         Up 2 minutes (healthy)
audio-visualizer   Up 2 minutes (healthy)
snapclient         Up 2 minutes (healthy)
```

### 2. Audio device detected

```bash
aplay -l
```

Expected: your HAT or USB device appears (e.g. `card 0: sndrpihifiberry`).

### 3. Snapserver connection

```bash
sudo docker logs snapclient 2>&1 | grep -i "connected to"
```

Expected: `Connected to <server-ip>` message. If missing, check mDNS or set `SNAPSERVER` in `.env`.

### 4. Display rendering

For framebuffer mode, the screen should show cover art or standby artwork. Verify the framebuffer is accessible:

```bash
sudo docker logs fb-display 2>&1 | head -5
```

Expected: `Framebuffer: <width>x<height>, <bpp>bpp, stride=<stride>`.

### 5. Spectrum analyzer

Port 8081 is a WebSocket-only endpoint. Check the container logs:

```bash
sudo docker logs audio-visualizer 2>&1 | tail -5
```

Expected: `Starting spectrum analyzer on port 8081` and periodic data lines when audio is playing.

### 6. Read-only filesystem (if enabled)

```bash
ro-mode status
```

Expected: `Read-only mode: enabled` with overlay active. Use `ro-mode disable && sudo reboot` to make changes.

## Troubleshooting

### Audio

| Problem | Cause | Fix |
|---------|-------|-----|
| No sound output | Wrong ALSA device | Check `SOUNDCARD` in `.env` matches `aplay -l` output. Use `default:CARD=<name>` format |
| Choppy/stuttering | Buffer underrun | Increase `ALSA_BUFFER_TIME` (default 200000) or `ALSA_FRAGMENTS` (default 4) in `.env` |
| Spectrum shows silence | No loopback | Snapclient must output to `default` device, not `hw:` directly |

### Display

| Problem | Cause | Fix |
|---------|-------|-----|
| Black screen | Wrong display mode | Check `DISPLAY_MODE` in `.env` (should be `framebuffer`) |
| Cover art not updating | Stale metadata connection | `sudo docker restart fb-display` |
| Wrong resolution | Override active | Remove `DISPLAY_RESOLUTION` from `.env` to auto-detect from framebuffer |
| Stuck at 800x600 | Install video mode | Remove `video=HDMI-A-1:800x600@60` from `/boot/firmware/cmdline.txt` and reboot |

### Network

| Problem | Cause | Fix |
|---------|-------|-----|
| Snapserver not found | mDNS blocked | Set `SNAPSERVER=<ip>` in `.env`, or check firewall allows port 1704 |
| Metadata disconnects | Server restart | fb-display auto-reconnects; check `SNAPSERVER_HOST` in `.env` points to server |

### Docker

| Problem | Cause | Fix |
|---------|-------|-----|
| Containers won't start | Resource limits | Check `sudo docker stats --no-stream`; reduce limits in `.env` if OOM |
| `docker compose` not found | Old Docker | Run setup.sh again — it installs Docker CE with Compose v2 plugin |
| overlay2 driver fails | Read-only FS | Expected on overlayfs root — setup.sh configures `fuse-overlayfs` automatically |

### Read-Only Filesystem

| Problem | Cause | Fix |
|---------|-------|-----|
| Cannot install/update | Overlay active | `ro-mode disable && sudo reboot`, then make changes |
| Docker data lost on reboot | Expected | Docker volumes are on the overlay; persistent data uses bind mounts |
| `/opt/snapclient` missing | Overlay reset | Re-run setup.sh or restore from backup |

## Docker Image

This project uses pre-built Docker images:
- **Images**: `lollonet/rpi-snapclient-usb-*:latest` (Docker Hub) (snapclient, visualizer, fb-display)
- **Platform**: ARM64 (Raspberry Pi 4)
- **Requires**: Docker Compose v2+ (installed automatically by setup.sh via Docker CE)

All containers run with:
- **Healthchecks** with dependency ordering (fb-display waits for visualizer, etc.)
- **Resource limits** auto-detected based on Pi RAM (2GB/4GB/8GB profiles)
- **Security hardening**: no-new-privileges, capability drops, tmpfs restrictions

Update to latest version:
```bash
cd /opt/snapclient
sudo docker compose pull
sudo docker compose up -d
```

## Resources

- **Snapcast**: https://github.com/badaix/snapcast
- **HiFiBerry**: https://www.hifiberry.com/docs/
- **Raspberry Pi OS**: https://www.raspberrypi.com/documentation/
- **MPD Clients**: https://www.musicpd.org/clients/

## Development

### Git Hooks (Local CI)

Install pre-push hooks to run CI checks locally before pushing:

```bash
bash scripts/install-hooks.sh
```

This installs a pre-push hook that runs:
- Shellcheck (bash linting)
- Hadolint (Dockerfile linting)
- HAT configuration tests
- Syntax validation

To bypass: `git push --no-verify`

### Contributing

1. Create a feature branch from `main`
2. Make changes and commit
3. Pre-push hook runs automatically
4. Push and create a PR
5. CI must pass before merge

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Notes

- The setup script installs **Docker CE** (official Docker Community Edition) with Compose v2 plugin, not the Debian `docker.io` package
- ALSA configuration is automatically generated based on the selected audio HAT
- The script supports 11 different audio HATs with appropriate device tree overlays and card names
- Metadata is served by the snapMULTI server; fb-display connects to it via WebSocket for track info and HTTP for artwork
- All configuration is done via `.env` files - no hardcoded IP addresses in the code
- USB audio devices are supported without requiring device tree overlays
