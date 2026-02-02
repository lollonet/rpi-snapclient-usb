#!/usr/bin/env bash
# Snapclient Auto-Install — runs once on first boot.
# Copies project files from the boot partition to /opt/snapclient,
# runs setup.sh in non-interactive mode, then reboots.
set -euo pipefail

MARKER="/opt/snapclient/.auto-installed"

# Skip if already installed
if [ -f "$MARKER" ]; then
    echo "Snapclient already installed, skipping."
    exit 0
fi

# Detect boot partition path
if [ -d /boot/firmware ]; then
    BOOT="/boot/firmware"
else
    BOOT="/boot"
fi

SNAP_BOOT="$BOOT/snapclient"
INSTALL_DIR="/opt/snapclient"
LOG="/var/log/snapclient-install.log"

# Verify source files exist
if [ ! -d "$SNAP_BOOT" ]; then
    echo "ERROR: $SNAP_BOOT not found on boot partition."
    exit 1
fi

# Log everything
exec > >(tee -a "$LOG") 2>&1

echo "========================================="
echo "Snapclient Auto-Install"
date -Iseconds
echo "========================================="

# Copy project files from boot partition
echo "Copying files to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
# Copy all files including dotfiles (.env.example)
cp -r "$SNAP_BOOT/"* "$INSTALL_DIR/" 2>/dev/null || true
# .??* matches dotfiles without matching . and ..
cp -r "$SNAP_BOOT/".??* "$INSTALL_DIR/" 2>/dev/null || true

# Find config file (boot partition or install dir)
CONFIG=""
if [ -f "$SNAP_BOOT/snapclient.conf" ]; then
    CONFIG="$SNAP_BOOT/snapclient.conf"
elif [ -f "$INSTALL_DIR/snapclient.conf" ]; then
    CONFIG="$INSTALL_DIR/snapclient.conf"
fi

# Run setup in auto mode
echo "Running setup.sh --auto ..."
cd "$INSTALL_DIR"
bash scripts/setup.sh --auto "$CONFIG"

# Mark as installed
touch "$MARKER"

echo "========================================="
echo "Auto-install complete!"
echo "Rebooting in 5 seconds ..."
echo "========================================="

sleep 5
reboot
