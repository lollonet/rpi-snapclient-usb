# Quick Start Guide

Get your Raspberry Pi Snapcast client running in 5 minutes.

## Prerequisites

- Raspberry Pi 4 (2GB+)
- HiFiBerry DAC+ or Digi+
- USB drive (8GB+)
- Display (9" screen or 4K HDMI)
- Computer with Raspberry Pi Imager
- Snapserver running on your network

## Step 1: Flash USB Drive

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Select **Raspberry Pi OS Lite (64-bit)**
3. Choose your USB drive as the target
4. Click the gear icon (⚙️) to configure settings:
   - Enable SSH (with password or key)
   - Set username: `pi` (or your choice)
   - Set password
   - Configure WiFi (SSID and password)
   - Set hostname (optional)
5. Click **Write** and wait for completion

## Step 2: First Boot

1. Attach HiFiBerry HAT to Raspberry Pi GPIO pins
2. Connect display:
   - **9" screen**: DSI or HDMI
   - **4K TV**: HDMI
3. Insert USB drive into Raspberry Pi
4. Power on and wait ~30 seconds for boot

## Step 3: Copy Project Files

From your computer:

```bash
# SSH into Raspberry Pi
ssh pi@raspberrypi.local

# From another terminal, copy project files
scp -r ~/rpi-snapclient-usb pi@raspberrypi.local:/home/pi/
```

## Step 4: Run Setup Script

On the Raspberry Pi:

```bash
cd /home/pi/rpi-snapclient-usb
sudo bash common/scripts/setup.sh
```

The script will:
- Prompt you to choose configuration (1=DAC+ 9", 2=Digi+ 4K)
- Ask for your Snapserver IP address
- Install Docker CE and dependencies
- Configure HiFiBerry and ALSA
- Set up cover display with X11
- Create systemd services for auto-start
- Copy files to `/opt/snapclient/`

**Note**: The script takes 3-5 minutes. It does not build Docker images (uses pre-built images from GHCR).

## Step 5: Configure and Reboot

Edit configuration if needed:

```bash
sudo nano /opt/snapclient/.env
```

Example `.env`:
```bash
SNAPSERVER_HOST=192.168.1.100
SNAPSERVER_PORT=1704
SNAPSERVER_RPC_PORT=1705
HOST_ID=snapclient-living-room
SOUNDCARD=hw:sndrpihifiberry,0
```

Reboot:
```bash
sudo reboot
```

## Verification

After reboot (~30 seconds), verify everything is running:

```bash
# Check Docker containers
sudo docker ps
# Should show: snapclient, metadata-service, cover-webserver

# Check services
sudo systemctl status snapclient x11-autostart

# View snapclient logs
sudo docker logs -f snapclient

# Test audio device
aplay -l
```

You should see:
- Album art displayed on screen
- Audio playing through HiFiBerry
- Snapclient connected to your server

## Configuration

To change settings:

```bash
# Edit configuration
sudo nano /opt/snapclient/.env

# Restart services
cd /opt/snapclient
sudo docker-compose restart
```

## Next Steps

- See **[README.md](README.md)** for full documentation
- Customize cover display: `/opt/snapclient/cover-display/public/index.html`
- Set up additional clients for multiroom audio
- Install MPD control app (MALP, MPDroid, Cantata, etc.)
