# Raspberry Pi Snapcast Client with HiFiBerry & Cover Display

Docker-based Snapcast client for Raspberry Pi with HiFiBerry DACs, featuring synchronized multiroom audio and visual cover art display.

## Multiroom Audio Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       MULTIROOM AUDIO SETUP                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌────────────────────────────────────────────────────────────────┐     │
│   │                    SERVER (Single Host)                         │     │
│   │  ┌─────────────────┐    ┌────────────────────────────────────┐ │     │
│   │  │  MPD            │───▶│  Snapserver                        │ │     │
│   │  │  - Local files  │    │  - Streams to all clients          │ │     │
│   │  │  - Playlists    │FIFO│  - Ports configured via .env       │ │     │
│   │  │  - Metadata     │    │  - Synchronized playback           │ │     │
│   │  └─────────────────┘    └────────────────────────────────────┘ │     │
│   └────────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                          Network (WiFi/Ethernet)                         │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                                ▼                                │    │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │    │
│   │  │ Pi Client 1 │  │ Pi Client 2 │  │ Pi Client N │             │    │
│   │  │ Living Room │  │ Bedroom     │  │ Kitchen     │             │    │
│   │  │ HiFiBerry   │  │ HiFiBerry   │  │ HiFiBerry   │             │    │
│   │  │ DAC+/Digi+  │  │ DAC+/Digi+  │  │ DAC+/Digi+  │             │    │
│   │  │ + Display   │  │ + Display   │  │ (optional)  │             │    │
│   │  └─────────────┘  └─────────────┘  └─────────────┘             │    │
│   │                                                                 │    │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │    │
│   │  │📱 Mobile    │  │💻 Desktop   │  │📺 Smart TV  │             │    │
│   │  │ Phone/Tablet│  │ PC/Mac      │  │ Android TV  │             │    │
│   │  │ Snapclient  │  │ Snapclient  │  │ Snapclient  │             │    │
│   │  └─────────────┘  └─────────────┘  └─────────────┘             │    │
│   │                    SNAPCAST CLIENTS                             │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│   ┌────────────────────────────────────────────────────────────────┐     │
│   │                      CONTROL APPS                               │     │
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
- 🎛️ **HiFiBerry Support**: DAC+ (analog) and Digi+ (S/PDIF) configurations
- 📺 **Display Options**: 9" touchscreen or 4K HDMI TV
- 🐳 **Docker-based**: Pre-built images for easy deployment
- 🔄 **Auto-start**: Systemd services for automatic startup

## Hardware Requirements

### Configuration 1: DAC+ with 9" Screen
- Raspberry Pi 4 (2GB+)
- HiFiBerry DAC+ or DAC+ Pro
- 9" display (1024x600)
- USB drive (8GB+ for boot)
- Analog output to speakers/amplifier

### Configuration 2: Digi+ with 4K TV
- Raspberry Pi 4 (2GB+)
- HiFiBerry Digi+ or Digi+ Pro
- 4K HDMI display (3840x2160)
- USB drive (8GB+ for boot)
- S/PDIF output to receiver/DAC

## Quick Setup

See **[QUICKSTART.md](QUICKSTART.md)** for detailed 5-minute setup instructions.

### Summary

1. Flash Raspberry Pi OS Lite (64-bit) to USB drive
2. Enable SSH and WiFi in Raspberry Pi Imager settings
3. Boot Pi with HiFiBerry HAT attached
4. Copy project files and run `sudo bash common/scripts/setup.sh`
5. Configure `.env` with your Snapserver IP and reboot

The setup script installs Docker CE, configures HiFiBerry and ALSA, sets up the cover display, and creates systemd services for auto-start.

## Project Structure

```
rpi-snapclient-usb/
├── dac-plus-9inch/           # HiFiBerry DAC+ with 9" screen
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── boot/config.txt
│   ├── config/asound.conf
│   └── cover-display/
│       ├── metadata-service/
│       └── public/index.html
│
├── digi-plus-4k/             # HiFiBerry Digi+ with 4K TV
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── boot/config.txt
│   ├── config/asound.conf
│   └── cover-display/
│       ├── metadata-service/
│       └── public/index.html
│
├── common/
│   └── scripts/setup.sh      # Main installation script
│
└── docs/
    └── archive/              # Historical documentation
```

## Configuration

After installation, configure your Snapserver connection in `/opt/snapclient/.env`:

```bash
# Snapserver connection
SNAPSERVER_HOST=your.server.ip
SNAPSERVER_PORT=1704
SNAPSERVER_RPC_PORT=1705

# Client identification
CLIENT_ID=snapclient-living-room

# Audio device
SOUNDCARD=hw:sndrpihifiberry,0
```

Then restart services:
```bash
cd /opt/snapclient
sudo docker-compose restart
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
sudo docker-compose pull
sudo docker-compose up -d
```

## Resources

- **Snapcast**: https://github.com/badaix/snapcast
- **HiFiBerry**: https://www.hifiberry.com/docs/
- **Raspberry Pi OS**: https://www.raspberrypi.com/documentation/
- **MPD Clients**: https://www.musicpd.org/clients/

## Notes

- The setup script installs **Docker CE** (official Docker Community Edition), not the Debian `docker.io` package
- ALSA configuration uses card name `sndrpihifiberry` instead of hardcoded card numbers for reliability
- Cover display polls the Snapserver metadata API every 2 seconds
- All configuration is done via `.env` files - no hardcoded IP addresses in the code
