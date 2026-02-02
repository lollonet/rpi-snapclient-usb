#!/usr/bin/env bash
# prepare-sd.sh — Prepare an SD card for Snapclient auto-install.
#
# Copies project files to the Pi OS boot partition and patches
# firstrun.sh (Bullseye) or user-data (Bookworm+) so our installer
# runs automatically on first boot.
#
# Usage:
#   ./prepare-sd.sh                        # auto-detect boot partition
#   ./prepare-sd.sh /Volumes/bootfs        # macOS
#   ./prepare-sd.sh /media/$USER/bootfs    # Linux
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Auto-detect boot partition ──────────────────────────────────────
detect_boot() {
    # macOS
    if [ -d "/Volumes/bootfs" ]; then
        echo "/Volumes/bootfs"
        return
    fi
    # Linux: common mount points
    for base in "/media/$USER" "/media" "/mnt"; do
        if [ -d "$base/bootfs" ]; then
            echo "$base/bootfs"
            return
        fi
    done
    return 1
}

BOOT="${1:-}"
if [ -z "$BOOT" ]; then
    if BOOT=$(detect_boot); then
        echo "Auto-detected boot partition: $BOOT"
    else
        echo "ERROR: Could not find boot partition."
        echo ""
        echo "Usage: $0 <path-to-boot-partition>"
        echo "  macOS:  $0 /Volumes/bootfs"
        echo "  Linux:  $0 /media/\$USER/bootfs"
        exit 1
    fi
fi

# ── Validate ────────────────────────────────────────────────────────
if [ ! -d "$BOOT" ]; then
    echo "ERROR: $BOOT is not a directory."
    exit 1
fi

if [ ! -f "$BOOT/config.txt" ] && [ ! -f "$BOOT/cmdline.txt" ]; then
    echo "ERROR: $BOOT does not look like a Raspberry Pi boot partition."
    echo "       (missing config.txt and cmdline.txt)"
    exit 1
fi

# ── Copy project files ──────────────────────────────────────────────
DEST="$BOOT/snapclient"
echo "Copying project files to $DEST ..."

mkdir -p "$DEST"

# Copy install files (config, firstboot, README)
cp "$SCRIPT_DIR/install/snapclient.conf" "$DEST/"
cp "$SCRIPT_DIR/install/firstboot.sh"    "$DEST/"
cp "$SCRIPT_DIR/install/README.txt"      "$DEST/"

# Copy project files
for item in docker-compose.yml .env.example audio-hats docker public scripts; do
    if [ -e "$SCRIPT_DIR/common/$item" ]; then
        cp -r "$SCRIPT_DIR/common/$item" "$DEST/"
    fi
done

echo "  Copied $(du -sh "$DEST" | cut -f1) to boot partition."

# ── Patch boot scripts ──────────────────────────────────────────────
FIRSTRUN="$BOOT/firstrun.sh"
USERDATA="$BOOT/user-data"
HOOK='bash /boot/firmware/snapclient/firstboot.sh'

if [[ -f "$FIRSTRUN" ]]; then
    # Legacy Pi Imager (Bullseye): patch firstrun.sh
    if grep -qF "firstboot.sh" "$FIRSTRUN"; then
        echo "firstrun.sh already patched, skipping."
    else
        echo "Patching firstrun.sh to chain snapclient installer ..."
        if grep -q '^rm -f.*firstrun\.sh' "$FIRSTRUN"; then
            sed -i.bak '/^rm -f.*firstrun\.sh/i\
# Snapclient auto-install\
'"$HOOK"'\
' "$FIRSTRUN"
            rm -f "${FIRSTRUN}.bak"
        else
            sed -i.bak '/^exit 0/i\
# Snapclient auto-install\
'"$HOOK"'\
' "$FIRSTRUN"
            rm -f "${FIRSTRUN}.bak"
        fi
        echo "  firstrun.sh patched."
    fi
elif [[ -f "$USERDATA" ]]; then
    # Modern Pi Imager (Bookworm+): patch cloud-init user-data
    if grep -qF "firstboot.sh" "$USERDATA"; then
        echo "user-data already patched, skipping."
    else
        echo "Patching user-data to run snapclient installer on first boot ..."
        if grep -q '^runcmd:' "$USERDATA"; then
            # Append to existing runcmd section
            sed -i.bak '/^runcmd:/a\  - [bash, /boot/firmware/snapclient/firstboot.sh]' "$USERDATA"
            rm -f "${USERDATA}.bak"
        else
            printf '\nruncmd:\n  - [bash, /boot/firmware/snapclient/firstboot.sh]\n' >> "$USERDATA"
        fi
        echo "  user-data patched."
    fi
else
    echo ""
    echo "NOTE: No firstrun.sh or user-data found on boot partition."
    echo "  After booting, SSH into the Pi and run:"
    echo "    sudo bash /boot/firmware/snapclient/firstboot.sh"
    echo ""
fi

# ── Done ────────────────────────────────────────────────────────────
echo ""
echo "=== SD card ready! ==="
echo ""
echo "Next steps:"
echo "  1. (Optional) Edit $DEST/snapclient.conf to customize settings"
echo "  2. Eject the SD card and insert it into the Raspberry Pi"
echo "  3. Power on — installation takes ~5 minutes, then auto-reboots"
echo ""
