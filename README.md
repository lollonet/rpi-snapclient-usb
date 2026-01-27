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
- 🎨 **Cover Display**: Full-screen album art with track metadata
- 🎛️ **Multiple Audio HATs**: Support for 11 popular Raspberry Pi audio HATs
- 📺 **Flexible Resolution**: 6 presets (800x480 to 4K) plus custom resolution support
- 🐳 **Docker-based**: Pre-built images for easy deployment
- 🔄 **Auto-start**: Systemd services for automatic startup

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

## Quick Setup

See **[QUICKSTART.md](QUICKSTART.md)** for detailed 5-minute setup instructions.

### Summary

1. Flash Raspberry Pi OS Lite (64-bit) to USB drive
2. Enable SSH and WiFi in Raspberry Pi Imager settings
3. Boot Pi with your audio HAT attached
4. Copy project files and run `sudo bash common/scripts/setup.sh`
5. Select your audio HAT (11 options) and display resolution (6 presets + custom)
6. Enter Snapserver IP and reboot

The setup script installs Docker CE, automatically configures your audio HAT and ALSA, sets up the cover display for your chosen resolution, and creates systemd services for auto-start. Client ID is automatically generated from hostname.

## Project Structure

```
rpi-snapclient-usb/
├── common/
│   ├── scripts/setup.sh        # Main installation script
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
│       └── metadata-service/   # Cover display metadata service
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

After installation, configure your settings in `/opt/snapclient/.env`:

```bash
# Snapserver connection
SNAPSERVER_HOST=your.server.ip
SNAPSERVER_PORT=1704
SNAPSERVER_RPC_PORT=1705

# Client identification (auto-generated from hostname)
CLIENT_ID=snapclient-raspberrypi

# Audio device (auto-configured based on HAT selection)
SOUNDCARD=hw:sndrpihifiberry,0

# Display resolution (auto-configured)
DISPLAY_RESOLUTION=1920x1080
```

Then restart services:
```bash
cd /opt/snapclient
sudo docker compose restart
```

## Verification

Check that everything is running:

```bash
# Check Docker containers
sudo docker ps
# Should show: snapclient, metadata-service, cover-webserver

# Check snapclient logs
sudo docker logs -f snapclient

# Check systemd services
sudo systemctl status snapclient x11-autostart

# Test audio device
aplay -l
# Should show: sndrpihifiberry

# View cover display (on Pi)
curl http://localhost:8080
```

## Docker Image

This project uses a unified pre-built image:
- **Image**: `ghcr.io/lollonet/rpi-snapclient-usb:latest`
- **Platform**: ARM64 (Raspberry Pi 4)
- **Services**: snapclient, metadata-service, nginx

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

1. Create a feature branch from `dev`
2. Make changes and commit
3. Pre-push hook runs automatically
4. Push and create a PR
5. CI must pass before merge

## Notes

- The setup script installs **Docker CE** (official Docker Community Edition), not the Debian `docker.io` package
- ALSA configuration is automatically generated based on the selected audio HAT
- The script supports 11 different audio HATs with appropriate device tree overlays and card names
- Cover display polls the Snapserver metadata API every 2 seconds
- All configuration is done via `.env` files - no hardcoded IP addresses in the code
- USB audio devices are supported without requiring device tree overlays
