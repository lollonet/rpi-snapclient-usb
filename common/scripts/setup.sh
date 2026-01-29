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

# Markers for idempotent config.txt edits
CONFIG_MARKER_START="# --- SNAPCLIENT SETUP START ---"
CONFIG_MARKER_END="# --- SNAPCLIENT SETUP END ---"

# ============================================
# Step 1: Select Audio HAT
# ============================================
show_hat_options() {
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
}

validate_choice() {
    local choice="$1"
    local max="$2"
    if [[ ! "$choice" =~ ^[1-9]$|^1[01]$ ]] || [ "$choice" -gt "$max" ]; then
        echo "Invalid choice. Please enter a number between 1 and $max."
        exit 1
    fi
}

get_hat_config() {
    local choice="$1"
    case "$choice" in
        1) echo "hifiberry-dac" ;;
        2) echo "hifiberry-digi" ;;
        3) echo "hifiberry-dac2hd" ;;
        4) echo "iqaudio-dac" ;;
        5) echo "iqaudio-digiamp" ;;
        6) echo "iqaudio-codec" ;;
        7) echo "allo-boss" ;;
        8) echo "allo-digione" ;;
        9) echo "justboom-dac" ;;
        10) echo "justboom-digi" ;;
        11) echo "usb-audio" ;;
        *) echo "Invalid choice"; exit 1 ;;
    esac
}

show_hat_options
read -rp "Enter choice [1-11]: " hat_choice
validate_choice "$hat_choice" 11
HAT_CONFIG=$(get_hat_config "$hat_choice")

# Load HAT configuration
# shellcheck source=/dev/null
source "$COMMON_DIR/audio-hats/$HAT_CONFIG.conf"

echo "Selected HAT: $HAT_NAME"
echo ""

# ============================================
# Step 2: Select Display Resolution
# ============================================
show_resolution_options() {
    echo "Select your display resolution:"
    echo "1) 800x480   (Small touchscreen)"
    echo "2) 1024x600  (9-inch display)"
    echo "3) 1280x720  (720p HD)"
    echo "4) 1920x1080 (1080p Full HD)"
    echo "5) 2560x1440 (1440p QHD)"
    echo "6) 3840x2160 (4K UHD)"
    echo "7) Custom    (Enter WIDTHxHEIGHT)"
}

get_resolution() {
    local choice="$1"
    case "$choice" in
        1) echo "800x480" ;;
        2) echo "1024x600" ;;
        3) echo "1280x720" ;;
        4) echo "1920x1080" ;;
        5) echo "2560x1440" ;;
        6) echo "3840x2160" ;;
        7)
            read -rp "Enter resolution (e.g., 1366x768): " custom_resolution
            if [[ ! "$custom_resolution" =~ ^[0-9]+x[0-9]+$ ]]; then
                echo "Invalid format. Use WIDTHxHEIGHT (e.g., 1366x768)"
                exit 1
            fi
            # Validate reasonable bounds (320-7680 width, 240-4320 height)
            local width height
            width="${custom_resolution%x*}"
            height="${custom_resolution#*x}"
            if (( width < 320 || width > 7680 || height < 240 || height > 4320 )); then
                echo "Invalid resolution. Width must be 320-7680, height must be 240-4320."
                exit 1
            fi
            echo "$custom_resolution"
            ;;
        *) echo "Invalid choice"; exit 1 ;;
    esac
}

show_resolution_options
read -rp "Enter choice [1-7]: " resolution_choice
validate_choice "$resolution_choice" 7
DISPLAY_RESOLUTION=$(get_resolution "$resolution_choice")

echo "Selected resolution: $DISPLAY_RESOLUTION"
echo ""

# ============================================
# Step 3: Select Display Mode
# ============================================
echo "Select display mode:"
echo "1) Browser (X11 + Chromium) — recommended"
echo "2) Framebuffer (direct rendering, no X11)"
read -rp "Enter choice [1-2]: " display_mode_choice

case "${display_mode_choice:-1}" in
    2) DISPLAY_MODE="framebuffer" ;;
    *) DISPLAY_MODE="browser" ;;
esac

echo "Display mode: $DISPLAY_MODE"
echo ""

# ============================================
# Step 3b: Select Spectrum Band Resolution
# ============================================
echo "Select spectrum analyzer band resolution:"
echo "1) Half-octave (19 bands) — recommended"
echo "2) Third-octave (31 bands)"
read -rp "Enter choice [1-2]: " band_mode_choice

case "${band_mode_choice:-1}" in
    2) BAND_MODE="third-octave" ;;
    *) BAND_MODE="half-octave" ;;
esac

echo "Band mode: $BAND_MODE"
echo ""

# ============================================
# Step 4: Auto-generate Client ID from hostname
# ============================================
CLIENT_ID="snapclient-$(hostname)"
echo "Client ID: $CLIENT_ID"
echo ""

# ============================================
# Step 5: Install Dependencies
# ============================================
INSTALL_DIR="/opt/snapclient"

echo "Installing system dependencies..."

# Base packages (always needed)
BASE_PACKAGES="ca-certificates curl gnupg alsa-utils avahi-daemon git"

if [ "$DISPLAY_MODE" = "browser" ]; then
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
    # shellcheck disable=SC2086
    apt-get install -y \
        $BASE_PACKAGES \
        xinit \
        x11-xserver-utils \
        xserver-xorg \
        ${CHROMIUM_PKG:+$CHROMIUM_PKG} \
        openbox
else
    # Framebuffer mode: no X11 packages needed
    apt-get update
    # shellcheck disable=SC2086
    apt-get install -y $BASE_PACKAGES
fi

# Install Docker CE (official repository) - skip if already installed
if command -v docker &> /dev/null && docker --version | grep -q "Docker version"; then
    echo "Docker CE already installed, skipping installation..."
else
    echo "Installing Docker CE from official repository..."

    # Remove conflicting Debian packages first
    apt-get remove -y docker.io docker-compose docker-buildx containerd runc 2>/dev/null || true

    # Only download GPG key if not already present
    if [ ! -f /etc/apt/keyrings/docker.asc ]; then
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
    fi

    # Only add repo if not already present
    if [ ! -f /etc/apt/sources.list.d/docker.list ]; then
        echo \
          "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
          $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
          tee /etc/apt/sources.list.d/docker.list > /dev/null
        apt-get update
    fi

    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Enable Docker service (idempotent)
systemctl enable docker
systemctl start docker

# Enable Avahi for mDNS autodiscovery (idempotent)
systemctl enable avahi-daemon
systemctl start avahi-daemon

echo "System dependencies installed"
echo ""

# ============================================
# Step 6: Setup Installation Directory
# ============================================
echo "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/public"

# Copy docker-compose.yml (always update to latest)
cp "$COMMON_DIR/docker-compose.yml" "$INSTALL_DIR/"

# Copy .env only if it doesn't exist (preserve user settings)
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "Creating new .env from template..."
    cp "$COMMON_DIR/.env.example" "$INSTALL_DIR/.env"
else
    echo "Preserving existing .env configuration..."
fi

# Copy docker build files (always update to latest)
cp -r "$COMMON_DIR/docker" "$INSTALL_DIR/"

# Copy public files including index.html
cp "$COMMON_DIR/public/index.html" "$INSTALL_DIR/public/"

echo "Files copied to $INSTALL_DIR"
echo ""

# ============================================
# Step 7: Configure ALSA with Loopback for Spectrum Analyzer
# ============================================
echo "Configuring ALSA for $HAT_NAME..."

# Load snd-aloop kernel module for ALSA loopback device
echo "Setting up ALSA loopback for spectrum analyzer..."
modprobe snd-aloop
if ! grep -q "snd-aloop" /etc/modules-load.d/snapclient.conf 2>/dev/null; then
    mkdir -p /etc/modules-load.d
    echo "snd-aloop" >> /etc/modules-load.d/snapclient.conf
fi

# Remove legacy FIFO tmpfs mount if present (from previous versions)
if grep -q "/tmp/audio" /etc/fstab 2>/dev/null; then
    sed -i '\|/tmp/audio|d' /etc/fstab
    echo "Removed legacy FIFO tmpfs mount from /etc/fstab"
fi

# Generate ALSA config with multi plugin (DAC + loopback simultaneously)
# The multi plugin sends audio to both the hardware DAC and a loopback device.
# The spectrum analyzer reads from the loopback capture side independently —
# if it stalls or falls behind, the DAC output is completely unaffected.
cat > /etc/asound.conf << EOF
# ALSA configuration for $HAT_NAME with spectrum analyzer
# Generated by setup script
# Audio is sent to both DAC and loopback simultaneously via multi plugin.
# The loopback feeds the spectrum analyzer without blocking the DAC.

pcm.multi_out {
    type multi
    slaves {
        a { pcm "hw:$HAT_CARD_NAME,0" channels 2 }
        b { pcm "hw:Loopback,0,0" channels 2 }
    }
    bindings {
        0 { slave a channel 0 }
        1 { slave a channel 1 }
        2 { slave b channel 0 }
        3 { slave b channel 1 }
    }
}

pcm.!default {
    type plug
    slave {
        pcm "multi_out"
        channels 4
    }
    ttable {
        0.0 1
        1.1 1
        0.2 1
        1.3 1
    }
}

ctl.!default {
    type hw
    card $HAT_CARD_NAME
}

defaults.pcm.rate_converter "samplerate_best"
EOF

echo "ALSA configured for $HAT_NAME (card: $HAT_CARD_NAME)"
echo "  - Audio loopback enabled for spectrum analyzer (snd-aloop)"
echo ""

# ============================================
# Step 8: Configure Boot Settings (Idempotent)
# ============================================
echo "Configuring boot settings..."
BOOT_CONFIG=""
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

if [ -n "$BOOT_CONFIG" ]; then
    # Backup original config (only once per day)
    BACKUP_FILE="${BOOT_CONFIG}.backup.$(date +%Y%m%d)"
    if [ ! -f "$BACKUP_FILE" ]; then
        cp "$BOOT_CONFIG" "$BACKUP_FILE"
        echo "Backup created: $BACKUP_FILE"
    fi

    # Remove any previous snapclient setup section (idempotent)
    if grep -q "$CONFIG_MARKER_START" "$BOOT_CONFIG"; then
        echo "Removing previous snapclient configuration..."
        sed -i "/$CONFIG_MARKER_START/,/$CONFIG_MARKER_END/d" "$BOOT_CONFIG"
    fi

    # Extract display width from resolution
    DISPLAY_WIDTH="${DISPLAY_RESOLUTION%x*}"

    # Build new configuration block
    {
        echo ""
        echo "$CONFIG_MARKER_START"
        echo "# Audio HAT: $HAT_NAME"
        echo "# Display: ${DISPLAY_RESOLUTION}"
        echo "# Generated: $(date -Iseconds)"
        echo ""

        # Add device tree overlay for HAT (skip if USB audio)
        if [ -n "$HAT_OVERLAY" ]; then
            echo "dtoverlay=$HAT_OVERLAY"
        fi

        # Disable onboard audio
        echo "dtparam=audio=off"

        # GPU memory based on resolution
        if [ "$DISPLAY_WIDTH" -gt 1920 ]; then
            echo "gpu_mem=512"
            echo "hdmi_enable_4kp60=1"
            echo "hdmi_force_hotplug=1"
        else
            echo "gpu_mem=256"
        fi

        # Video acceleration (only if not already in base config)
        if ! grep -q "^dtoverlay=vc4-kms-v3d" "$BOOT_CONFIG" 2>/dev/null; then
            echo "dtoverlay=vc4-kms-v3d"
            echo "max_framebuffers=2"
        fi

        echo "$CONFIG_MARKER_END"
    } >> "$BOOT_CONFIG"

    echo "Boot configuration updated"
else
    echo "Warning: Could not find boot config file"
fi
echo ""

# ============================================
# Step 9: Configure Docker Environment
# ============================================
echo "Configuring Docker environment..."
cd "$INSTALL_DIR"

# Read current snapserver from .env if exists (empty = autodiscovery)
current_snapserver=$(grep "^SNAPSERVER_HOST=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "")
[ -z "$current_snapserver" ] && echo "Current: mDNS autodiscovery" || echo "Current Snapserver: $current_snapserver"

# Configure snapserver host (empty = autodiscovery via mDNS)
read -rp "Enter Snapserver IP/hostname (or press Enter for autodiscovery): " snapserver_ip
snapserver_ip=${snapserver_ip:-$current_snapserver}

# Update SOUNDCARD value based on HAT
if [ "$HAT_CARD_NAME" = "USB" ]; then
    SOUNDCARD_VALUE="default"
else
    SOUNDCARD_VALUE="hw:$HAT_CARD_NAME,0"
fi

# Build Docker Compose profiles based on display mode
if [ "$DISPLAY_MODE" = "framebuffer" ]; then
    DOCKER_COMPOSE_PROFILES="framebuffer"
else
    DOCKER_COMPOSE_PROFILES=""
fi

# Update .env with all settings (idempotent - works on existing or new file)
update_env_var() {
    local key="$1"
    local value="$2"
    local file="$INSTALL_DIR/.env"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# Update all environment variables
declare -A env_vars=(
    ["SNAPSERVER_HOST"]="$snapserver_ip"
    ["CLIENT_ID"]="$CLIENT_ID"
    ["SOUNDCARD"]="$SOUNDCARD_VALUE"
    ["DISPLAY_RESOLUTION"]="$DISPLAY_RESOLUTION"
    ["DISPLAY_MODE"]="$DISPLAY_MODE"
    ["BAND_MODE"]="$BAND_MODE"
    ["COMPOSE_PROFILES"]="$DOCKER_COMPOSE_PROFILES"
)

for key in "${!env_vars[@]}"; do
    update_env_var "$key" "${env_vars[$key]}"
done

echo "Docker configuration ready"
echo "  - Snapserver: ${snapserver_ip:-autodiscovery}"
echo "  - Client ID: $CLIENT_ID"
echo "  - Soundcard: $SOUNDCARD_VALUE"
echo "  - Resolution: $DISPLAY_RESOLUTION"
echo "  - Display mode: $DISPLAY_MODE"
echo "  - Band mode: $BAND_MODE"
echo ""

# ============================================
# Step 10: Configure Display Auto-start
# ============================================
if [ "$DISPLAY_MODE" = "browser" ]; then
    echo "Setting up X11 auto-start for cover display..."

    # Configure Xwrapper to allow any user to start X server
    echo "allowed_users=anybody" > /etc/X11/Xwrapper.config

    # Detect the actual user (who invoked sudo)
    REAL_USER="${SUDO_USER:-$USER}"
    REAL_HOME=$(eval echo ~"$REAL_USER")

    # Validate and convert resolution to comma-separated for chromium
    if [[ ! "$DISPLAY_RESOLUTION" =~ ^[0-9]+x[0-9]+$ ]]; then
        echo "Error: Invalid DISPLAY_RESOLUTION format: $DISPLAY_RESOLUTION"
        exit 1
    fi
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
else
    echo "Framebuffer mode: X11 not needed"
    echo "  Display rendering is handled by fb-display Docker container"

    # Disable X11 autostart if it was previously enabled
    if systemctl is-enabled x11-autostart.service 2>/dev/null; then
        systemctl disable x11-autostart.service
        echo "  Disabled previous X11 autostart service"
    fi
fi
echo ""

# ============================================
# Step 11: Create Systemd Service for Docker
# ============================================
echo "Creating systemd service for Docker containers..."

# Docker Compose profiles are handled via COMPOSE_PROFILES in .env
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
echo "  - Display mode: $DISPLAY_MODE"
echo "  - Band mode: $BAND_MODE"
echo "  - Client ID: $CLIENT_ID"
echo "  - Snapserver: ${snapserver_ip:-autodiscovery (mDNS)}"
echo "  - Install dir: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "1. Review configuration in $INSTALL_DIR/.env"
echo "2. Reboot the system: sudo reboot"
echo "3. After reboot, check services:"
echo "   - sudo systemctl status snapclient"
if [ "$DISPLAY_MODE" = "browser" ]; then
echo "   - sudo systemctl status x11-autostart"
fi
echo "   - sudo docker ps"
echo ""
echo "The snapclient will start automatically on boot"
if [ "$DISPLAY_MODE" = "browser" ]; then
echo "Cover display will show on the connected screen via Chromium"
else
echo "Cover display will render directly to framebuffer (/dev/fb0)"
fi
echo ""
