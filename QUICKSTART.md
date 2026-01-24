# Quick Start Guide (5 Minutes)

## Prerequisites

- Raspberry Pi 4 with HiFiBerry DAC+ or Digi+
- USB drive (8GB+) for boot
- Display (9" touchscreen or 4K HDMI TV)
- Computer with Raspberry Pi Imager
- Snapserver running on your network (e.g., 192.168.63.3)

## Step 1: Flash USB (2 minutes)

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Choose **Raspberry Pi OS Lite (64-bit)**
3. Select your USB drive
4. In settings:
   - Enable SSH
   - Set username: `pi`
   - Set password
   - Configure WiFi (SSID and password)
5. Write to USB

## Step 2: First Boot (1 minute)

1. Connect HiFiBerry HAT to Raspberry Pi GPIO
2. Connect display (HDMI)
3. Insert USB drive
4. Power on
5. Wait for boot (~30 seconds)

## Step 3: SSH and Copy Files (1 minute)

From your computer:

```bash
# SSH into Raspberry Pi
ssh pi@raspberrypi.local

# In another terminal, copy project files
scp -r ~/rpi-snapclient-usb pi@raspberrypi.local:/home/pi/
```

## Step 4: Run Setup Script (1 minute)

On the Raspberry Pi:

```bash
cd /home/pi/rpi-snapclient-usb
sudo bash common/scripts/setup.sh
```

**Follow the prompts:**
- Choose configuration: `1` for DAC+ 9" or `2` for Digi+ 4K
- Enter Snapserver IP (default: 192.168.63.3)
- Confirm WiFi settings

The script automatically:
- Installs Docker and dependencies
- Configures HiFiBerry and ALSA
- Sets up cover display
- Creates auto-start services

## Step 5: Reboot

```bash
sudo reboot
```

**After reboot (~30 seconds):**
- Snapclient connects to your Snapserver
- Cover display shows album art
- Audio plays through HiFiBerry

## Verification

```bash
# Check services are running
sudo systemctl status snapclient
sudo systemctl status x11-autostart

# Check Docker containers
sudo docker ps

# You should see:
# - snapclient
# - cover-display
# - metadata-service
# - cover-webserver
```

## Troubleshooting

### No audio
```bash
# Test speakers
speaker-test -t wav -c 2

# Check ALSA devices
aplay -l
```

### Cover display not showing
```bash
# Restart X11
sudo systemctl restart x11-autostart

# Check logs
journalctl -u x11-autostart -f
```

### Snapclient not connecting
```bash
# Check logs
sudo docker logs snapclient

# Verify Snapserver IP
cat /opt/snapclient/.env

# Test connection
ping 192.168.63.3
```

## Configuration

Edit `/opt/snapclient/.env` to change:
- Snapserver IP address
- Port numbers
- Audio device

Then restart:
```bash
cd /opt/snapclient
sudo docker-compose restart
```

## Next Steps

- See **[README.md](README.md)** for full documentation
- Customize cover display: edit `/opt/snapclient/cover-display/public/index.html`
- Add multiple clients for multi-room audio

## Support

Common issues and solutions are in the [README.md](README.md) troubleshooting section.
