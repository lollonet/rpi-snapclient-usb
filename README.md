# Raspberry Pi Snapclient with HiFiBerry & Cover Display

Complete setup for Raspberry Pi 4 as Snapcast client with HiFiBerry DAC and visual cover art display.

## Features

- 🎵 **Snapcast Audio**: Multi-room synchronized audio playback
- 🎨 **Cover Display**: Beautiful full-screen album art with track info
- 🎛️ **HiFiBerry Support**: DAC+ (analog) or Digi+ (S/PDIF) configurations
- 📺 **Dual Display Options**: 9" touchscreen or 4K HDMI TV
- 🐳 **Docker-based**: Easy deployment and updates
- 🔄 **Auto-start**: Boots directly into music player mode

## Hardware Requirements

### Common Components
- Raspberry Pi 4 (2GB+ recommended for cover display)
- USB drive (8GB+ for boot)
- Power supply (official 3A recommended)
- MicroSD card (for initial flashing only)

### Configuration 1: DAC+ with 9" Screen
- **HiFiBerry DAC+** (or DAC+ Pro)
- **9" display** (1024x600 recommended)
- Analog output to speakers/amplifier

### Configuration 2: Digi+ with 4K TV
- **HiFiBerry Digi+** (or Digi+ Pro)
- **4K HDMI TV** (3840x2160)
- S/PDIF digital output to receiver/DAC

## Quick Start

See **[QUICKSTART.md](QUICKSTART.md)** for 5-minute setup instructions.

### 1. Flash Raspberry Pi OS

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Select **Raspberry Pi OS Lite (64-bit)**
3. Flash to your USB drive
4. Enable SSH in settings before flashing

### 2. Configure WiFi

Before first boot, edit `common/config/wpa_supplicant.conf.template`:

```bash
network={
    ssid="YOUR_WIFI_SSID"
    psk="YOUR_WIFI_PASSWORD"
}
```

Copy to the boot partition after flashing.

### 3. First Boot

1. Connect HiFiBerry HAT to GPIO pins
2. Connect display (HDMI for both configs, or DSI for 9" screen)
3. Insert USB drive and power on
4. Wait for boot and SSH access

### 4. Run Setup

```bash
# SSH into Raspberry Pi
ssh pi@raspberrypi.local

# Copy project files (from your computer)
scp -r ~/rpi-snapclient-usb pi@raspberrypi.local:/home/pi/

# On Raspberry Pi, run setup
cd /home/pi/rpi-snapclient-usb
sudo bash common/scripts/setup.sh
```

The script will:
- Ask which configuration (DAC+ 9" or Digi+ 4K)
- Install Docker and dependencies
- Configure HiFiBerry and ALSA
- Set up cover display with X11
- Create systemd services for auto-start
- Configure WiFi if needed

### 5. Configure Snapserver

Edit `/opt/snapclient/.env`:

```bash
SNAPSERVER_HOST=192.168.63.3    # Your Snapserver IP
SNAPSERVER_PORT=1704
SNAPSERVER_RPC_PORT=1705
```

### 6. Reboot

```bash
sudo reboot
```

After reboot, the system will automatically:
- Start snapclient and connect to your server
- Launch X11 with cover display
- Show album art and track info on screen

## Project Structure

```
rpi-snapclient-usb/
├── dac-plus-9inch/           # HiFiBerry DAC+ with 9" screen
│   ├── docker-compose.yml    # Docker services
│   ├── .env.example          # Configuration template
│   ├── boot/                 # Boot config for DAC+
│   ├── config/               # ALSA config
│   └── cover-display/        # HTML + metadata service
│
├── digi-plus-4k/             # HiFiBerry Digi+ with 4K TV
│   ├── docker-compose.yml    # Docker services (4K optimized)
│   ├── .env.example          # Configuration template
│   ├── boot/                 # Boot config for Digi+ 4K
│   ├── config/               # ALSA config
│   └── cover-display/        # HTML + metadata service (4K)
│
├── common/                   # Shared files
│   ├── scripts/setup.sh      # Installation script
│   └── config/               # WiFi templates
│
├── README.md                 # This file
└── QUICKSTART.md             # 5-minute setup guide
```

## Cover Display

The cover display automatically:
- Polls Snapserver for metadata every 2 seconds
- Downloads and displays album artwork
- Shows track title, artist, and album
- Adapts to screen resolution (1024x600 or 3840x2160)

### Customization

Edit `cover-display/public/index.html` to customize:
- Colors and gradients
- Font sizes and styles
- Animation effects
- Polling interval

## Troubleshooting

### Snapclient not connecting

```bash
# Check snapclient status
sudo docker ps
sudo docker logs snapclient

# Verify Snapserver IP
cat /opt/snapclient/.env

# Test network connectivity
ping 192.168.63.3
```

### No audio output

```bash
# List audio devices
aplay -l

# Test HiFiBerry
speaker-test -t wav -c 2

# Check ALSA config
cat /etc/asound.conf
```

### Cover display not showing

```bash
# Check X11 service
sudo systemctl status x11-autostart

# Check display environment
echo $DISPLAY

# View X11 logs
journalctl -u x11-autostart -f

# Manually test Chromium
DISPLAY=:0 chromium-browser --kiosk http://localhost:8080
```

### Docker containers not starting

```bash
# Check Docker service
sudo systemctl status docker

# View all containers
sudo docker ps -a

# Rebuild containers
cd /opt/snapclient
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

## Advanced Configuration

### Change Audio Device

Edit `docker-compose.yml`:

```yaml
environment:
  - SNAPCLIENT_OPTS=--hostID myhost --host 192.168.63.3 --soundcard hw:0,0
```

### Adjust Cover Display Size (9" only)

Edit `docker-compose.yml`:

```yaml
environment:
  - CHROMIUM_FLAGS=--window-size=800,480 --window-position=0,0
```

### Enable SSH After Boot

```bash
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Add Static IP

Edit `/etc/dhcpcd.conf`:

```bash
interface wlan0
static ip_address=192.168.63.100/24
static routers=192.168.63.1
static domain_name_servers=192.168.63.1 8.8.8.8
```

## Snapserver Configuration

For metadata and artwork to work, your Snapserver needs to provide this information. Configure your audio source (Mopidy, MPD, etc.) to send metadata.

Example Mopidy `snapserver.conf`:

```ini
[stream]
source = pipe:///tmp/snapfifo?name=Mopidy&mode=read&sampleformat=48000:16:2
```

## Updates

### Update Snapclient

```bash
cd /opt/snapclient
sudo docker-compose pull
sudo docker-compose up -d
```

### Update Cover Display

```bash
cd /opt/snapclient/cover-display
# Edit files
sudo docker-compose build metadata-service
sudo docker-compose up -d
```

## System Maintenance

### View Logs

```bash
# Snapclient logs
sudo docker logs -f snapclient

# Metadata service logs
sudo docker logs -f metadata-service

# System logs
journalctl -xe
```

### Performance Monitoring

```bash
# CPU/Memory usage
htop

# Docker stats
sudo docker stats
```

## Additional Resources

- **Snapcast**: https://github.com/badaix/snapcast
- **HiFiBerry**: https://www.hifiberry.com/docs/
- **Raspberry Pi OS**: https://www.raspberrypi.com/documentation/

## Support

For issues:
1. Check troubleshooting section above
2. Review Docker logs
3. Verify hardware connections
4. Ensure Snapserver is reachable and configured

## License

This project configuration is provided as-is for personal use.

Components use their respective licenses:
- Snapcast: GPL-3.0
- Docker images: Various (check each image)
- Chromium: BSD-style license
