#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "Raspberry Pi Snapclient Setup Script"
echo "With Audio HAT and Cover Display Support"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo bash setup.sh"
    exit 1
fi

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
COMMON_DIR="$PROJECT_DIR/common"

# ============================================
# Step 1: Select Audio HAT
# ============================================
echo "Select your audio HAT:"
echo "1) HiFiBerry DAC+"
echo "2) HiFiBerry Digi+"
echo "3) HiFiBerry DAC2 HD"
echo "4) IQaudio DAC+"
echo "5) IQaudio DigiAMP+"
echo "6) IQaudio Codec Zero"
echo "7) Allo Boss DAC"
echo "8) Allo DigiOne"
echo "9) JustBoom DAC"
echo "10) JustBoom Digi"
echo "11) USB Audio Device"
read -rp "Enter choice [1-11]: " hat_choice

# Validate input
if [[ ! "$hat_choice" =~ ^([1-9]|1[01])$ ]]; then
    echo "Invalid choice. Please enter a number between 1 and 11."
    exit 1
fi

case "$hat_choice" in
    1) HAT_CONFIG="hifiberry-dac" ;;
    2) HAT_CONFIG="hifiberry-digi" ;;
    3) HAT_CONFIG="hifiberry-dac2hd" ;;
    4) HAT_CONFIG="iqaudio-dac" ;;
    5) HAT_CONFIG="iqaudio-digiamp" ;;
    6) HAT_CONFIG="iqaudio-codec" ;;
    7) HAT_CONFIG="allo-boss" ;;
    8) HAT_CONFIG="allo-digione" ;;
    9) HAT_CONFIG="justboom-dac" ;;
    10) HAT_CONFIG="justboom-digi" ;;
    11) HAT_CONFIG="usb-audio" ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

# Load HAT configuration
# shellcheck source=/dev/null
source "$COMMON_DIR/audio-hats/$HAT_CONFIG.conf"

echo "Selected HAT: $HAT_NAME"
echo ""

# ============================================
# Step 2: Select Display Resolution
# ============================================
echo "Select your display resolution:"
echo "1) 800x480   (Small touchscreen)"
echo "2) 1024x600  (9-inch display)"
echo "3) 1280x720  (720p HD)"
echo "4) 1920x1080 (1080p Full HD)"
echo "5) 2560x1440 (1440p QHD)"
echo "6) 3840x2160 (4K UHD)"
echo "7) Custom    (Enter WIDTHxHEIGHT)"
read -rp "Enter choice [1-7]: " resolution_choice

# Validate input
if [[ ! "$resolution_choice" =~ ^[1-7]$ ]]; then
    echo "Invalid choice. Please enter a number between 1 and 7."
    exit 1
fi

case "$resolution_choice" in
    1) DISPLAY_RESOLUTION="800x480" ;;
    2) DISPLAY_RESOLUTION="1024x600" ;;
    3) DISPLAY_RESOLUTION="1280x720" ;;
    4) DISPLAY_RESOLUTION="1920x1080" ;;
    5) DISPLAY_RESOLUTION="2560x1440" ;;
    6) DISPLAY_RESOLUTION="3840x2160" ;;
    7)
        read -rp "Enter resolution (e.g., 1366x768): " DISPLAY_RESOLUTION
        if [[ ! "$DISPLAY_RESOLUTION" =~ ^[0-9]+x[0-9]+$ ]]; then
            echo "Invalid format. Use WIDTHxHEIGHT (e.g., 1366x768)"
            exit 1
        fi
        ;;
esac

echo "Selected resolution: $DISPLAY_RESOLUTION"
echo ""

# ============================================
# Step 3: Auto-generate Client ID from hostname
# ============================================
CLIENT_ID="snapclient-$(hostname)"
echo "Client ID: $CLIENT_ID"
echo ""

# ============================================
# Step 4: Install Dependencies
# ============================================
INSTALL_DIR="/opt/snapclient"

echo "Installing system dependencies..."

# Detect chromium package name (chromium on Debian, chromium-browser on older Raspberry Pi OS)
if apt-cache show chromium > /dev/null 2>&1; then
    CHROMIUM_PKG="chromium"
elif apt-cache show chromium-browser > /dev/null 2>&1; then
    CHROMIUM_PKG="chromium-browser"
else
    echo "Warning: Could not find chromium package, skipping"
    CHROMIUM_PKG=""
fi

apt-get update
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    alsa-utils \
    xinit \
    x11-xserver-utils \
    xserver-xorg \
    ${CHROMIUM_PKG:+$CHROMIUM_PKG} \
    openbox \
    git

# Install Docker CE (official repository)
echo "Installing Docker CE from official repository..."

# Remove conflicting Debian packages first
apt-get remove -y docker.io docker-compose docker-buildx containerd runc 2>/dev/null || true

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker service
systemctl enable docker
systemctl start docker

echo "System dependencies installed"
echo ""

# ============================================
# Step 5: Setup Installation Directory
# ============================================
echo "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/public"

# Copy configuration files from common/
cp "$COMMON_DIR/docker-compose.yml" "$INSTALL_DIR/"
cp "$COMMON_DIR/.env.example" "$INSTALL_DIR/.env"
cp -r "$COMMON_DIR/docker" "$INSTALL_DIR/"

echo "Files copied to $INSTALL_DIR"
echo ""

# ============================================
# Step 6: Configure ALSA
# ============================================
echo "Configuring ALSA for $HAT_NAME..."

# Generate ALSA configuration from HAT settings
cat > /etc/asound.conf << EOF
# ALSA configuration for $HAT_NAME
# Generated by setup script

pcm.!default {
    type hw
    card $HAT_CARD_NAME
    device 0
}

ctl.!default {
    type hw
    card $HAT_CARD_NAME
}

# Digital output settings for $HAT_TYPE
pcm.audiohat {
    type hw
    card $HAT_CARD_NAME
    device 0
    format $HAT_FORMAT
    rate $HAT_RATE
}

# Dmix for concurrent audio streams (optional)
pcm.dmixer {
    type dmix
    ipc_key 1024
    slave {
        pcm "hw:$HAT_CARD_NAME,0"
        period_time 0
        period_size 1024
        buffer_size 8192
        rate $HAT_RATE
        format $HAT_FORMAT
    }
    bindings {
        0 0
        1 1
    }
}

# Asymmetric configuration
pcm.asymed {
    type asym
    playback.pcm "dmixer"
}

# Sample rate converter
defaults.pcm.rate_converter "samplerate_best"
EOF

echo "ALSA configured for $HAT_NAME (card: $HAT_CARD_NAME)"
echo ""

# ============================================
# Step 7: Configure Boot Settings
# ============================================
echo "Configuring boot settings..."
BOOT_CONFIG=""
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

if [ -n "$BOOT_CONFIG" ]; then
    # Backup original config
    cp "$BOOT_CONFIG" "${BOOT_CONFIG}.backup.$(date +%Y%m%d)"

    # Append audio HAT configuration
    echo "" >> "$BOOT_CONFIG"
    echo "# Audio HAT Configuration: $HAT_NAME (added by setup script)" >> "$BOOT_CONFIG"

    # Add device tree overlay for HAT (skip if USB audio)
    if [ -n "$HAT_OVERLAY" ]; then
        echo "dtoverlay=$HAT_OVERLAY" >> "$BOOT_CONFIG"
    fi

    # Disable onboard audio
    echo "dtparam=audio=off" >> "$BOOT_CONFIG"

    # Extract display width from resolution
    DISPLAY_WIDTH="${DISPLAY_RESOLUTION%x*}"

    # Display-specific configuration based on resolution
    echo "" >> "$BOOT_CONFIG"
    echo "# Display Configuration (${DISPLAY_RESOLUTION})" >> "$BOOT_CONFIG"

    if [ "$DISPLAY_WIDTH" -gt 1920 ]; then
        # High resolution (>1080p)
        echo "gpu_mem=512" >> "$BOOT_CONFIG"
        echo "hdmi_enable_4kp60=1" >> "$BOOT_CONFIG"
        echo "hdmi_force_hotplug=1" >> "$BOOT_CONFIG"
    else
        # Standard resolution (<=1080p)
        echo "gpu_mem=256" >> "$BOOT_CONFIG"
    fi

    # Video acceleration
    echo "dtoverlay=vc4-kms-v3d" >> "$BOOT_CONFIG"
    echo "max_framebuffers=2" >> "$BOOT_CONFIG"

    echo "Boot configuration updated (backup saved)"
else
    echo "Warning: Could not find boot config file"
fi
echo ""

# ============================================
# Step 8: Configure Docker Environment
# ============================================
echo "Configuring Docker environment..."
cd "$INSTALL_DIR"

# Configure snapserver host
read -rp "Enter Snapserver IP address or hostname [snapserver.local]: " snapserver_ip
snapserver_ip=${snapserver_ip:-snapserver.local}

# Update .env with all settings
sed -i "s/SNAPSERVER_HOST=.*/SNAPSERVER_HOST=$snapserver_ip/" "$INSTALL_DIR/.env"
sed -i "s/CLIENT_ID=.*/CLIENT_ID=$CLIENT_ID/" "$INSTALL_DIR/.env"
sed -i "s/DISPLAY_RESOLUTION=.*/DISPLAY_RESOLUTION=$DISPLAY_RESOLUTION/" "$INSTALL_DIR/.env"

# Update SOUNDCARD in .env based on HAT
if [ "$HAT_CARD_NAME" = "USB" ]; then
    SOUNDCARD_VALUE="default"
else
    SOUNDCARD_VALUE="hw:$HAT_CARD_NAME,0"
fi
sed -i "s|SOUNDCARD=.*|SOUNDCARD=$SOUNDCARD_VALUE|" "$INSTALL_DIR/.env"

echo "Docker configuration ready"
echo "  - Snapserver: $snapserver_ip"
echo "  - Client ID: $CLIENT_ID"
echo "  - Soundcard: $SOUNDCARD_VALUE"
echo "  - Resolution: $DISPLAY_RESOLUTION"
echo ""

# ============================================
# Step 9: Configure X11 Auto-start
# ============================================
echo "Setting up X11 auto-start for cover display..."

# Configure Xwrapper to allow any user to start X server
echo "allowed_users=anybody" > /etc/X11/Xwrapper.config

# Detect the actual user (who invoked sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo ~"$REAL_USER")

# Convert resolution to comma-separated for chromium
CHROMIUM_SIZE="${DISPLAY_RESOLUTION/x/,}"

# Create .xinitrc for automatic X11 startup with Chromium kiosk
cat > "$REAL_HOME/.xinitrc" << EOF
#!/bin/bash
xset s off
xset -dpms
xset s noblank

# Start openbox in background
openbox &

# Wait for Docker containers to be ready
sleep 10

# Launch Chromium in kiosk mode
chromium --kiosk --window-size=$CHROMIUM_SIZE --window-position=0,0 \\
  --start-fullscreen --disable-infobars --disable-session-crashed-bubble \\
  --disable-features=TranslateUI --noerrdialogs --disable-translate \\
  --no-first-run --fast --fast-start --disable-popup-blocking \\
  http://localhost:8080
EOF

chmod +x "$REAL_HOME/.xinitrc"
chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.xinitrc"

# Create systemd service for X11 autostart
cat > /etc/systemd/system/x11-autostart.service << EOF
[Unit]
Description=X11 Autostart for Cover Display
After=network.target docker.service

[Service]
Type=simple
User=$REAL_USER
Environment=DISPLAY=:0
ExecStart=/usr/bin/startx
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable x11-autostart.service

echo "X11 auto-start configured"
echo ""

# ============================================
# Step 10: Create Systemd Service for Docker
# ============================================
echo "Creating systemd service for Docker containers..."

cat > /etc/systemd/system/snapclient.service << EOF
[Unit]
Description=Snapclient Docker Compose Service
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable snapclient.service

echo "Systemd service created and enabled"
echo ""

# ============================================
# Setup Complete
# ============================================
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Configuration Summary:"
echo "  - Audio HAT: $HAT_NAME"
echo "  - Resolution: $DISPLAY_RESOLUTION"
echo "  - Client ID: $CLIENT_ID"
echo "  - Snapserver: $snapserver_ip"
echo "  - Install dir: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "1. Review configuration in $INSTALL_DIR/.env"
echo "2. Reboot the system: sudo reboot"
echo "3. After reboot, check services:"
echo "   - sudo systemctl status snapclient"
echo "   - sudo systemctl status x11-autostart"
echo "   - sudo docker ps"
echo ""
echo "The snapclient will start automatically on boot"
echo "Cover display will show on the connected screen"
echo ""
