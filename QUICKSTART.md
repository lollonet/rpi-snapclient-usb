# Quick Start Guide (Manual Setup)

Get your Raspberry Pi Snapcast client running in 5 minutes.

> **Prefer zero-touch?** See the [Zero-Touch Auto-Install](README.md#zero-touch-auto-install-recommended) in the README — no SSH or terminal needed.

## Prerequisites

- Raspberry Pi 4 (2GB+)
- One of the supported audio HATs (HiFiBerry, IQaudio, Allo, JustBoom) or USB audio device
- USB drive (8GB+)
- Display (any resolution from 800x480 to 4K)
- Computer with Raspberry Pi Imager
- Snapserver running on your network

## Supported Audio HATs

The setup supports: HiFiBerry (DAC+, Digi+, DAC2 HD), IQaudio (DAC+, DigiAMP+, Codec Zero), Allo (Boss, DigiOne), JustBoom (DAC, Digi), and USB Audio.

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

1. Attach your audio HAT to Raspberry Pi GPIO pins (or connect USB audio device)
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
1. **Prompt you to select your audio HAT** (11 options):
   - HiFiBerry DAC+, Digi+, DAC2 HD
   - IQaudio DAC+, DigiAMP+, Codec Zero
   - Allo Boss, DigiOne
   - JustBoom DAC, Digi
   - USB Audio Device
2. **Prompt you to select display resolution** (6 presets + custom):
   - 800x480, 1024x600, 1280x720, 1920x1080, 2560x1440, 3840x2160
   - Or enter custom resolution (e.g., 1366x768)
3. Auto-generate CLIENT_ID from hostname
4. Optionally ask for your Snapserver IP (leave empty for mDNS autodiscovery)
5. Install Docker CE and dependencies
6. Configure audio HAT, ALSA, and boot settings
7. Set up framebuffer display at selected resolution
8. Create systemd services for auto-start

**Note**: The script takes 3-5 minutes. It uses pre-built Docker images from Docker Hub (no building required).

## Step 5: Configure and Reboot

Edit configuration if needed:

```bash
sudo nano /opt/snapclient/.env
```

Example `.env` (automatically configured by setup script):
```bash
SNAPSERVER_HOST=                     # Empty = mDNS autodiscovery
SNAPSERVER_PORT=1704
SNAPSERVER_RPC_PORT=1705
CLIENT_ID=snapclient-raspberrypi    # Auto-generated from hostname
SOUNDCARD=default                   # Routes through DAC + loopback for spectrum
DISPLAY_RESOLUTION=1920x1080        # Auto-set based on selection
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
# Should show: snapclient, audio-visualizer, fb-display (all "healthy")

# Check services
sudo systemctl status snapclient

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

# Apply changes (restart does NOT pick up .env changes)
cd /opt/snapclient
sudo docker compose up -d
```

## Next Steps

- See **[README.md](README.md)** for full documentation
- Customize cover display: `/opt/snapclient/public/`
- Set up additional clients for multiroom audio
- Install MPD control app (MALP, MPDroid, Cantata, etc.)
