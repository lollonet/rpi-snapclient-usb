#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "Raspberry Pi Snapclient Setup Script"
echo "With HiFiBerry and Cover Display Support"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  Please run as root: sudo bash setup.sh"
    exit 1
fi

# Detect configuration
echo "Which configuration are you setting up?"
echo "1) HiFiBerry DAC+ with 9\" screen"
echo "2) HiFiBerry Digi+ with 4K HDMI"
read -rp "Enter choice [1 or 2]: " config_choice

case "$config_choice" in
    1)
        CONFIG_DIR="dac-plus-9inch"
        CONFIG_NAME="DAC+ (9\" screen)"
        ;;
    2)
        CONFIG_DIR="digi-plus-4k"
        CONFIG_NAME="Digi+ (4K HDMI)"
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo "✓ Selected configuration: $CONFIG_NAME"
echo ""

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
INSTALL_DIR="/opt/snapclient"

echo "📦 Installing system dependencies..."

# Detect chromium package name (chromium on Debian, chromium-browser on older Raspberry Pi OS)
if apt-cache show chromium > /dev/null 2>&1; then
    CHROMIUM_PKG="chromium"
elif apt-cache show chromium-browser > /dev/null 2>&1; then
    CHROMIUM_PKG="chromium-browser"
else
    echo "⚠️  Warning: Could not find chromium package, skipping"
    CHROMIUM_PKG=""
fi

apt-get update
apt-get install -y \
    docker.io \
    docker-compose \
    alsa-utils \
    xinit \
    x11-xserver-utils \
    xserver-xorg \
    ${CHROMIUM_PKG:+$CHROMIUM_PKG} \
    openbox \
    git \
    curl

# Enable Docker service
systemctl enable docker
systemctl start docker

echo "✓ System dependencies installed"
echo ""

echo "📁 Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
cd "$PROJECT_DIR/$CONFIG_DIR"

# Copy configuration files
cp docker-compose.yml "$INSTALL_DIR/"
cp .env.example "$INSTALL_DIR/.env"
cp -r config "$INSTALL_DIR/"
cp -r boot "$INSTALL_DIR/"
cp -r cover-display "$INSTALL_DIR/"

echo "✓ Files copied to $INSTALL_DIR"
echo ""

echo "🎵 Configuring ALSA for HiFiBerry..."
cp "$INSTALL_DIR/config/asound.conf" /etc/asound.conf

echo "✓ ALSA configured"
echo ""

echo "📺 Configuring boot settings..."
BOOT_CONFIG=""
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

if [ -n "$BOOT_CONFIG" ]; then
    # Backup original config
    cp "$BOOT_CONFIG" "${BOOT_CONFIG}.backup.$(date +%Y%m%d)"

    # Append HiFiBerry configuration
    echo "" >> "$BOOT_CONFIG"
    echo "# HiFiBerry Configuration (added by setup script)" >> "$BOOT_CONFIG"
    cat "$INSTALL_DIR/boot/config.txt" >> "$BOOT_CONFIG"

    echo "✓ Boot configuration updated (backup saved)"
else
    echo "⚠️  Could not find boot config file. Please manually copy $INSTALL_DIR/boot/config.txt"
fi
echo ""

echo "📡 Configuring WiFi..."
WIFI_CONFIG="/etc/wpa_supplicant/wpa_supplicant.conf"

if [ -f "$PROJECT_DIR/common/config/wpa_supplicant.conf.template" ]; then
    if [ ! -f "$WIFI_CONFIG" ] || ! grep -q "YOUR_WIFI_SSID" "$WIFI_CONFIG"; then
        read -rp "Configure WiFi now? (y/n): " configure_wifi

        if [ "$configure_wifi" = "y" ]; then
            read -rp "Enter WiFi SSID: " wifi_ssid
            read -rsp "Enter WiFi Password: " wifi_password
            echo ""

            sed "s/YOUR_WIFI_SSID/$wifi_ssid/g; s/YOUR_WIFI_PASSWORD/$wifi_password/g" \
                "$PROJECT_DIR/common/config/wpa_supplicant.conf.template" > "$WIFI_CONFIG"

            echo "✓ WiFi configured"
        else
            echo "⚠️  Please configure WiFi manually later"
        fi
    else
        echo "✓ WiFi already configured"
    fi
fi
echo ""

echo "🐳 Setting up Docker containers..."
cd "$INSTALL_DIR"

# Configure snapserver host
read -rp "Enter Snapserver IP address [192.168.63.3]: " snapserver_ip
snapserver_ip=${snapserver_ip:-192.168.63.3}

sed -i "s/SNAPSERVER_HOST=.*/SNAPSERVER_HOST=$snapserver_ip/" "$INSTALL_DIR/.env"

echo "✓ Docker configuration ready"
echo ""

echo "🖥️  Setting up X11 auto-start for cover display..."

# Configure Xwrapper to allow any user to start X server
echo "allowed_users=anybody" > /etc/X11/Xwrapper.config

# Detect the actual user (who invoked sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo ~"$REAL_USER")

# Set display size based on configuration
if [ "$CONFIG_DIR" = "dac-plus-9inch" ]; then
    DISPLAY_SIZE="1024,600"
else
    DISPLAY_SIZE="3840,2160"
fi

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
chromium --kiosk --window-size=$DISPLAY_SIZE --window-position=0,0 \\
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

echo "✓ X11 auto-start configured"
echo ""

echo "🚀 Creating systemd service for Docker containers..."

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
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable snapclient.service

echo "✓ Systemd service created and enabled"
echo ""

echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "Configuration: $CONFIG_NAME"
echo "Installation directory: $INSTALL_DIR"
echo "Snapserver: $snapserver_ip"
echo ""
echo "📝 Next steps:"
echo "1. Review configuration in $INSTALL_DIR/.env"
echo "2. Reboot the system: sudo reboot"
echo "3. After reboot, check services:"
echo "   - sudo systemctl status snapclient"
echo "   - sudo systemctl status x11-autostart"
echo "   - sudo docker ps"
echo ""
echo "🎵 The snapclient will start automatically on boot"
echo "📺 Cover display will show on the connected screen"
echo ""
