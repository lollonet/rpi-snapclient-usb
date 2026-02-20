#!/usr/bin/env bash
set -euo pipefail

# ============================================
# Auto mode: --auto [config_file]
# Reads settings from config file, skips all prompts.
# HAT auto-detection via EEPROM when AUDIO_HAT=auto.
#
# Optional flags:
#   --no-readonly  Disable read-only filesystem (default: enabled)
# ============================================
AUTO_MODE=false
AUTO_CONFIG=""
ENABLE_READONLY=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --auto)
            AUTO_MODE=true
            AUTO_CONFIG="${2:-}"
            shift 2 || shift
            ;;
        --read-only)
            ENABLE_READONLY=true
            shift
            ;;
        --no-readonly)
            ENABLE_READONLY=false
            shift
            ;;
        *) shift ;;
    esac
done

if [ "$AUTO_MODE" = true ]; then
    if [ -n "$AUTO_CONFIG" ] && [ -f "$AUTO_CONFIG" ]; then
        # Validate config path (prevent path traversal and injection)
        if [[ ! "$AUTO_CONFIG" =~ ^[a-zA-Z0-9_./-]+$ ]]; then
            echo "Error: Invalid characters in config path: $AUTO_CONFIG"
            exit 1
        fi
        # Reject path traversal attempts
        if [[ "$AUTO_CONFIG" == *".."* ]]; then
            echo "Error: Path traversal not allowed in config path: $AUTO_CONFIG"
            exit 1
        fi
        # Resolve to absolute path and verify it exists
        AUTO_CONFIG_REAL=$(realpath -e "$AUTO_CONFIG" 2>/dev/null) || {
            echo "Error: Config file not found: $AUTO_CONFIG"
            exit 1
        }
        # shellcheck source=/dev/null
        source "$AUTO_CONFIG_REAL"
    fi
    # Defaults for auto mode (can be overridden by config file)
    AUDIO_HAT="${AUDIO_HAT:-auto}"
    DISPLAY_RESOLUTION="${DISPLAY_RESOLUTION:-}"
    BAND_MODE="${BAND_MODE:-third-octave}"
    SNAPSERVER_HOST="${SNAPSERVER_HOST:-}"
    # ENABLE_READONLY: command line --read-only takes precedence, then config file
    if [[ "$ENABLE_READONLY" != "true" ]]; then
        ENABLE_READONLY="${ENABLE_READONLY:-false}"
    fi
fi

echo "========================================="
echo "Raspberry Pi Snapclient Setup Script"
echo "With Audio HAT and Cover Display Support"
if [ "$AUTO_MODE" = true ]; then
    echo "  Mode: AUTO (non-interactive)"
fi
echo "========================================="
echo ""

# ============================================
# Progress display (auto mode only)
# ============================================
# Use monotonic counter instead of SECONDS (clock may be wrong on first boot)
PROGRESS_START_MONO=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
PROGRESS_ANIM_PID=""

STEP_NAMES=("System dependencies" "Docker CE" "Audio HAT config"
            "ALSA loopback" "Boot settings" "Docker environment"
            "Security hardening" "Systemd service" "Pulling images"
            "Read-only filesystem")

# Weights reflect actual duration (Pull=40%, Docker=33%, Deps=12%, RO=5%, rest=10%)
STEP_WEIGHTS=(12 33 2 2 2 2 2 3 37 5)

# Log file for capturing output to display
PROGRESS_LOG="/tmp/snapclient-progress.log"
: > "$PROGRESS_LOG"  # Clear/create log file

# Render progress display to tty1 (top: progress, bottom: log output)
render_progress() {
    local step=$1 pct=$2 elapsed=$3 spinner=${4:-}
    local total=${#STEP_NAMES[@]}

    [[ -c /dev/tty1 ]] || return

    # Clamp pct to 0-100 for safety
    (( pct < 0 )) && pct=0
    (( pct > 100 )) && pct=100

    # Build progress bar (50 chars wide)
    local bar_width=50
    local filled=$(( pct * bar_width / 100 ))
    local empty=$(( bar_width - filled ))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done

    # Get last 10 lines of log for output area (wider: 64 chars)
    local log_lines=""
    if [[ -f "$PROGRESS_LOG" ]]; then
        log_lines=$(tail -10 "$PROGRESS_LOG" 2>/dev/null | cut -c1-64 || true)
    fi

    {
        printf '\033[2J\033[H'
        printf '\n'
        printf '  ┌──────────────────────────────────────────────────────────────────┐\n'
        printf '  │                     \033[1mSnapclient Auto-Install\033[0m                      │\n'
        printf '  └──────────────────────────────────────────────────────────────────┘\n'
        printf '\n'
        printf '  \033[36m⏱  Elapsed: %02d:%02d\033[0m\n\n' $((elapsed/60)) $((elapsed%60))
        printf '  \033[33m%s\033[0m %3d%% %s\n\n' "$bar" "$pct" "$spinner"
        for i in $(seq 1 "$total"); do
            local name="${STEP_NAMES[$((i-1))]}"
            if (( i < step )); then   printf '  \033[32m✓\033[0m %s\n' "$name"
            elif (( i == step )); then printf '  \033[33m▶\033[0m %s\n' "$name"
            else                       printf '  ○ %s\n' "$name"
            fi
        done
        printf '\n'
        printf '  ┌───────────────────────────── Output ─────────────────────────────┐\n'
        # Print log lines (pad to 64 chars with 1-char margins)
        if [[ -n "$log_lines" ]]; then
            while IFS= read -r line; do
                printf '  │ \033[90m%-64s\033[0m │\n' "$line"
            done <<< "$log_lines"
        fi
        # Fill remaining lines to make consistent height (10 lines)
        local line_count
        line_count=$(printf '%s' "$log_lines" | grep -c '^') || line_count=0
        for ((i=line_count; i<10; i++)); do
            printf '  │ %-64s │\n' ""
        done
        printf '  └──────────────────────────────────────────────────────────────────┘\n'
        printf '\n'
        # Nerdy digital clock at bottom
        local clock_time
        clock_time=$(date '+%H:%M:%S')
        printf '  \033[90m┌──────────────────────────────────────────────────────────────────┐\033[0m\n'
        printf '  \033[90m│\033[0m  \033[36m░█▀▀░█░░░█▀█░█▀▀░█░█\033[0m   \033[1;37m⏰ %s\033[0m   \033[36m█░█░█▀▀░█▀█░█░░░█▀▀░\033[0m  \033[90m│\033[0m\n' "$clock_time"
        printf '  \033[90m│\033[0m  \033[36m░█░░░█░░░█░█░█░░░█▀▄\033[0m                 \033[36m█▀▄░█▀▀░█▀█░█░░░▀▀█░\033[0m  \033[90m│\033[0m\n'
        printf '  \033[90m│\033[0m  \033[36m░▀▀▀░▀▀▀░▀▀▀░▀▀▀░▀░▀\033[0m                 \033[36m▀░▀░▀▀▀░▀░▀░▀▀▀░▀▀▀░\033[0m  \033[90m│\033[0m\n'
        printf '  \033[90m└──────────────────────────────────────────────────────────────────┘\033[0m\n'
    } > /dev/tty1
}

# Helper to log output for display
log_progress() {
    echo "$*" >> "$PROGRESS_LOG"
}

# Start background animation for long-running steps
start_progress_animation() {
    [[ "$AUTO_MODE" != true ]] && return
    local step=$1 base_pct=$2 step_weight=$3

    # Kill any existing animation
    stop_progress_animation

    # Start background process that updates display every second
    (
        local spinners=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
        local spin_idx=0
        local step_start
        step_start=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)

        while true; do
            local now_mono elapsed step_elapsed pct_in_step current_pct
            now_mono=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
            elapsed=$(( now_mono - PROGRESS_START_MONO ))
            step_elapsed=$(( now_mono - step_start ))

            # Gradually fill the step's portion (ease-out curve)
            # Max out at 90% of step weight to leave room for completion
            if (( step_elapsed < 300 )); then
                pct_in_step=$(( step_weight * step_elapsed * 9 / 3000 ))
            else
                pct_in_step=$(( step_weight * 9 / 10 ))
            fi
            current_pct=$(( base_pct + pct_in_step ))

            render_progress "$step" "$current_pct" "$elapsed" "${spinners[$spin_idx]}"
            spin_idx=$(( (spin_idx + 1) % 10 ))
            sleep 1
        done
    ) &
    PROGRESS_ANIM_PID=$!
}

stop_progress_animation() {
    if [[ -n "$PROGRESS_ANIM_PID" ]]; then
        kill "$PROGRESS_ANIM_PID" 2>/dev/null || true
        wait "$PROGRESS_ANIM_PID" 2>/dev/null || true
        PROGRESS_ANIM_PID=""
    fi
}

progress() {
    [[ "$AUTO_MODE" != true ]] && return
    local step=$1 msg="$2"
    local total=${#STEP_NAMES[@]}

    # Stop any running animation
    stop_progress_animation

    # Elapsed time from monotonic uptime (immune to clock changes)
    local now_mono
    now_mono=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
    local elapsed=$(( now_mono - PROGRESS_START_MONO ))

    # Calculate weighted percentage (sum weights of COMPLETED steps)
    # step=1 means starting step 1, nothing completed yet → 0%
    # step=2 means step 1 done → weight[0]
    local weight_sum=0 total_weight=0
    for ((i=0; i<total; i++)); do
        total_weight=$(( total_weight + STEP_WEIGHTS[i] ))
        if (( i < step - 1 )); then
            weight_sum=$(( weight_sum + STEP_WEIGHTS[i] ))
        fi
    done
    local pct=$(( weight_sum * 100 / total_weight ))

    # One-line summary to stdout (goes to log via firstboot redirect)
    echo "=== Step $step/$total: $msg ($((elapsed/60))m$((elapsed%60))s) ==="

    # Render to tty1
    render_progress "$step" "$pct" "$elapsed"
}

progress_complete() {
    [[ "$AUTO_MODE" != true ]] && return

    # Stop any running animation
    stop_progress_animation

    local total=${#STEP_NAMES[@]}
    local now_mono
    now_mono=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
    local elapsed=$(( now_mono - PROGRESS_START_MONO ))

    [[ -c /dev/tty1 ]] || return

    local bar=""
    for ((i=0; i<50; i++)); do bar+="█"; done

    {
        printf '\033[2J\033[H'
        printf '\n'
        printf '  ┌──────────────────────────────────────────────────────────────────┐\n'
        printf '  │                     \033[1mSnapclient Auto-Install\033[0m                      │\n'
        printf '  └──────────────────────────────────────────────────────────────────┘\n'
        printf '\n'
        printf '  \033[36m⏱  Elapsed: %02d:%02d\033[0m\n\n' $((elapsed/60)) $((elapsed%60))
        printf '  \033[32m%s\033[0m 100%%\n\n' "$bar"
        for i in $(seq 1 "$total"); do
            printf '  \033[32m✓\033[0m %s\n' "${STEP_NAMES[$((i-1))]}"
        done
        printf '\n'
        printf '  \033[32m✓ Installation complete!\033[0m\n'
        printf '\n'
        printf '  ┌───────────────────────────── Output ─────────────────────────────┐\n'
        printf '  │ \033[32m%-64s\033[0m │\n' "All steps completed successfully"
        printf '  │ \033[32m%-64s\033[0m │\n' "System will reboot shortly..."
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  │ %-64s │\n' ""
        printf '  └──────────────────────────────────────────────────────────────────┘\n'
        printf '\n'
        # Nerdy completion clock
        local clock_time
        clock_time=$(date '+%H:%M:%S')
        printf '  \033[90m┌─────────────────────────────────────────────────────────────────────┐\033[0m\n'
        printf '  \033[90m│\033[0m  \033[32m░█▀▄░█▀█░█▀█░█▀▀░█\033[0m   \033[1;32m✓ %s\033[0m   \033[32m█░█▀▀░█░░░█░░░█░█░█▀█░\033[0m  \033[90m│\033[0m\n' "$clock_time"
        printf '  \033[90m│\033[0m  \033[32m░█░█░█░█░█░█░█▀▀░▀\033[0m               \033[32m░░█▀▀░█░░░█░░░█▀█░█▀▀░\033[0m  \033[90m│\033[0m\n'
        printf '  \033[90m│\033[0m  \033[32m░▀▀░░▀▀▀░▀░▀░▀▀▀░▀\033[0m               \033[32m░░▀░░░▀▀▀░▀▀▀░▀░▀░▀░░░\033[0m  \033[90m│\033[0m\n'
        printf '  \033[90m└─────────────────────────────────────────────────────────────────────┘\033[0m\n'
    } > /dev/tty1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo bash setup.sh"
    exit 1
fi

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
COMMON_DIR="$PROJECT_DIR/common"
# Fallback: if common/ doesn't exist, check if the install dir has audio-hats
# (happens when running from /opt/snapclient/scripts/ via firstboot)
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
if [[ ! -d "$COMMON_DIR" ]]; then
    if [[ -d "$INSTALL_DIR/audio-hats" ]]; then
        COMMON_DIR="$INSTALL_DIR"
    elif [[ -d "$PROJECT_DIR/audio-hats" ]]; then
        COMMON_DIR="$PROJECT_DIR"
    fi
fi

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

detect_hat() {
    # Detect audio HAT automatically.
    # 1. Pi firmware reads HAT EEPROM at boot → /proc/device-tree/hat/product
    # 2. Fallback: check ALSA card names via aplay -l
    # 3. Final fallback: USB audio
    local hat_product=""

    if [ -f /proc/device-tree/hat/product ]; then
        hat_product=$(tr -d '\0' < /proc/device-tree/hat/product)
        # Log detected product for debugging
        echo "EEPROM product: '$hat_product'" >&2
        # Match EEPROM strings - patterns based on Volumio dacs.json and real devices
        # Order matters: more specific patterns first
        case "$hat_product" in
            # HiFiBerry (EEPROM: "DAC 2 HD", "HiFiBerry DAC+", "Digi+", etc.)
            *DAC*2*HD*)                                  echo "hifiberry-dac2hd" ; return ;;
            Digi+*|*Digi\ +*|*HiFiBerry*Digi*)          echo "hifiberry-digi"   ; return ;;
            *HiFiBerry*DAC*|DAC+*|*DAC\ +*)             echo "hifiberry-dac"    ; return ;;
            # IQaudio/Raspberry Pi (EEPROM: "Pi-DigiAMP+", "Pi-CodecZero", "Raspberry Pi DAC Plus")
            *Pi-DigiAMP*|*DigiAMP*)                     echo "iqaudio-digiamp"  ; return ;;
            *Pi-Codec*|*CodecZero*|*Codec*Zero*)        echo "iqaudio-codec"    ; return ;;
            *Raspberry*Pi*DAC*|*IQaudio*DAC*|*IQaudIO*) echo "iqaudio-dac"      ; return ;;
            # Allo (EEPROM varies)
            *Boss*|*BOSS*)                              echo "allo-boss"        ; return ;;
            *DigiOne*|*Allo*Digi*)                      echo "allo-digione"     ; return ;;
            # JustBoom (EEPROM: "JustBoom DAC HAT", "JustBoom Digi HAT")
            *JustBoom*Digi*)                            echo "justboom-digi"    ; return ;;
            *JustBoom*DAC*|*JustBoom*Amp*)              echo "justboom-dac"     ; return ;;
        esac
        echo "Warning: Unknown HAT product '$hat_product', falling back to USB" >&2
    fi

    if command -v aplay &>/dev/null; then
        local cards
        cards=$(aplay -l 2>/dev/null || true)
        case "$cards" in
            *sndrpihifiberry*)  echo "hifiberry-dac"  ; return ;;
            *IQaudIODAC*)       echo "iqaudio-dac"    ; return ;;
            *IQaudIOCODEC*)     echo "iqaudio-codec"  ; return ;;
            *BossDAC*)          echo "allo-boss"      ; return ;;
            *sndallodigione*)   echo "allo-digione"   ; return ;;
            *sndrpijustboom*)   echo "justboom-dac"   ; return ;;
        esac
    fi

    echo "usb-audio"
}

# Map AUDIO_HAT config name (e.g. "usb") to .conf filename
resolve_hat_config_name() {
    local name="$1"
    case "$name" in
        usb|usb-audio)  echo "usb-audio" ;;
        *)              echo "$name" ;;
    esac
}

if [ "$AUTO_MODE" = true ]; then
    # Auto mode: detect or use configured HAT
    if [ "$AUDIO_HAT" = "auto" ]; then
        AUDIO_HAT=$(detect_hat)
        echo "Auto-detected HAT: $AUDIO_HAT"
    fi
    HAT_CONFIG=$(resolve_hat_config_name "$AUDIO_HAT")
else
    show_hat_options
    read -rp "Enter choice [1-11]: " hat_choice
    validate_choice "$hat_choice" 11
    HAT_CONFIG=$(get_hat_config "$hat_choice")
fi

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

if [ "$AUTO_MODE" = true ]; then
    echo "Resolution: ${DISPLAY_RESOLUTION:-auto}"
else
    show_resolution_options
    read -rp "Enter choice [1-7]: " resolution_choice
    validate_choice "$resolution_choice" 7
    DISPLAY_RESOLUTION=$(get_resolution "$resolution_choice")
    echo "Selected resolution: $DISPLAY_RESOLUTION"
fi
echo ""

# ============================================
# Step 3: Select Spectrum Band Resolution
# ============================================
if [ "$AUTO_MODE" = true ]; then
    echo "Band mode: $BAND_MODE"
else
    echo "Select spectrum analyzer band resolution:"
    echo "1) Third-octave (31 bands) — recommended"
    echo "2) Half-octave (21 bands)"
    read -rp "Enter choice [1-2]: " band_mode_choice

    case "${band_mode_choice:-1}" in
        2) BAND_MODE="half-octave" ;;
        *) BAND_MODE="third-octave" ;;
    esac

    echo "Band mode: $BAND_MODE"
fi
echo ""

# ============================================
# Step 3c: Read-Only Filesystem Option
# ============================================
if [ "$AUTO_MODE" = true ]; then
    echo "Read-only mode: $ENABLE_READONLY"
else
    echo "Enable read-only filesystem? (protects SD card from corruption)"
    echo "  - All writes go to RAM, lost on reboot"
    echo "  - Requires 'sudo ro-mode disable' for updates"
    read -rp "Enable read-only mode? [Y/n]: " readonly_choice

    case "${readonly_choice:-y}" in
        [Nn]|[Nn][Oo]) ENABLE_READONLY=false ;;
        *) ENABLE_READONLY=true ;;
    esac

    echo "Read-only mode: $ENABLE_READONLY"
fi
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

progress 1 "Installing system dependencies..."
log_progress "apt-get update"
start_progress_animation 1 0 12  # Animate during apt-get

# Base packages (always needed)
BASE_PACKAGES="ca-certificates curl gnupg alsa-utils avahi-daemon git"

apt-get update
log_progress "apt-get install: ca-certificates curl gnupg..."
log_progress "apt-get install: alsa-utils avahi-daemon git..."
# shellcheck disable=SC2086
apt-get install -y $BASE_PACKAGES
log_progress "System packages installed"

progress 2 "Installing Docker CE..."
log_progress "Checking Docker installation..."
start_progress_animation 2 12 35  # Animate during long Docker install

# Install Docker CE (official repository) - skip if already installed
if command -v docker &> /dev/null && docker --version | grep -q "Docker version"; then
    log_progress "Docker CE already installed, skipping"
else
    log_progress "Removing conflicting packages..."
    # Remove conflicting Debian packages first
    apt-get remove -y docker.io docker-compose docker-buildx containerd runc 2>/dev/null || true

    # Only download GPG key if not already present
    if [ ! -f /etc/apt/keyrings/docker.asc ]; then
        log_progress "Downloading Docker GPG key..."
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
    fi

    # Only add repo if not already present
    if [ ! -f /etc/apt/sources.list.d/docker.list ]; then
        log_progress "Adding Docker apt repository..."
        echo \
          "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
          $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
          tee /etc/apt/sources.list.d/docker.list > /dev/null
        apt-get update
    fi

    log_progress "apt-get install: docker-ce docker-ce-cli..."
    log_progress "apt-get install: containerd.io docker-compose-plugin..."
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

log_progress "systemctl enable docker"
systemctl enable docker
systemctl start docker

log_progress "systemctl enable avahi-daemon"
systemctl enable avahi-daemon
systemctl start avahi-daemon

log_progress "timedatectl set-ntp true"
timedatectl set-ntp true 2>/dev/null || true

log_progress "Docker and system services ready"
echo ""

# ============================================
# Step 6: Setup Installation Directory
# ============================================
echo "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/public"

# Copy project files (skip if source == destination, e.g. firstboot installs)
if [[ "$(cd "$COMMON_DIR" 2>/dev/null && pwd)" != "$(cd "$INSTALL_DIR" 2>/dev/null && pwd)" ]]; then
    cp "$COMMON_DIR/docker-compose.yml" "$INSTALL_DIR/"
    cp -r "$COMMON_DIR/docker" "$INSTALL_DIR/"
    cp "$COMMON_DIR/public/index.html" "$INSTALL_DIR/public/"
fi

# Copy .env only if it doesn't exist (preserve user settings)
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    echo "Creating new .env from template..."
    cp "$COMMON_DIR/.env.example" "$INSTALL_DIR/.env"
else
    echo "Preserving existing .env configuration..."
fi

echo "Files copied to $INSTALL_DIR"
echo ""

# ============================================
# Step 7: Configure ALSA with Loopback for Spectrum Analyzer
# ============================================
progress 3 "Configuring audio HAT..."

# Load snd-aloop kernel module for ALSA loopback device
progress 4 "Setting up ALSA loopback..."
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
progress 5 "Updating boot settings..."
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

    # Remove temporary setup display section from prepare-sd.sh (legacy)
    if grep -q "SNAPCLIENT SETUP DISPLAY" "$BOOT_CONFIG"; then
        echo "Removing temporary setup display settings..."
        sed -i '/# --- SNAPCLIENT SETUP DISPLAY ---/,/# --- SNAPCLIENT SETUP DISPLAY END ---/d' "$BOOT_CONFIG"
    fi

    # Remove temporary video= parameter from cmdline.txt (KMS mode)
    CMDLINE=""
    if [ -f /boot/firmware/cmdline.txt ]; then
        CMDLINE="/boot/firmware/cmdline.txt"
    elif [ -f /boot/cmdline.txt ]; then
        CMDLINE="/boot/cmdline.txt"
    fi
    if [ -n "$CMDLINE" ] && grep -q "video=HDMI-A-1:800x600" "$CMDLINE"; then
        echo "Removing temporary 800x600 video parameter..."
        sed -i 's/ video=HDMI-A-1:800x600@60//' "$CMDLINE"
    fi

    # Extract display width from resolution (default to 0 for autodiscovery mode)
    DISPLAY_WIDTH="${DISPLAY_RESOLUTION%x*}"
    DISPLAY_WIDTH="${DISPLAY_WIDTH:-0}"

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

    # Disable fbcon on fb0 so the kernel console doesn't overwrite
    # the framebuffer display (maps console to nonexistent vt9)
    CMDLINE=""
    if [ -f /boot/firmware/cmdline.txt ]; then
        CMDLINE="/boot/firmware/cmdline.txt"
    elif [ -f /boot/cmdline.txt ]; then
        CMDLINE="/boot/cmdline.txt"
    fi
    if [ -n "$CMDLINE" ] && ! grep -q "fbcon=map:9" "$CMDLINE"; then
        sed -i 's/$/ fbcon=map:9/' "$CMDLINE"
        echo "Disabled fbcon on fb0 (cmdline.txt updated)"
    fi

    # Enable cgroup memory controller for Docker resource limits
    # Required for cgroups v2 on newer kernels (Bookworm+/Trixie)
    if [ -n "$CMDLINE" ] && ! grep -q "cgroup_enable=memory" "$CMDLINE"; then
        sed -i 's/$/ cgroup_enable=memory cgroup_memory=1/' "$CMDLINE"
        echo "Enabled cgroup memory controller (cmdline.txt updated)"
    fi
else
    echo "ERROR: Could not find boot config (config.txt)."
    echo "  Audio HAT overlay and display settings cannot be applied."
    echo "  Expected /boot/firmware/config.txt or /boot/config.txt"
    exit 1
fi
echo ""

# ============================================
# Step 9: Detect Hardware Profile & Configure Docker
# ============================================
progress 6 "Configuring Docker environment..."

# Detect hardware and set appropriate resource limits
detect_resource_profile() {
    # Get total RAM in MB
    local mem_mb
    mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)

    # Fallback to medium profile if detection failed (0 or very low = likely error)
    if (( mem_mb < 256 )); then
        echo "medium"
        return
    fi

    # Determine profile based on RAM
    if (( mem_mb < 2048 )); then
        # Pi Zero 2 W, Pi 3, <2GB RAM
        echo "low"
    elif (( mem_mb < 4096 )); then
        # Pi 4 2GB, 2-4GB RAM
        echo "medium"
    else
        # Pi 4 4GB+, Pi 5, 8GB+ RAM
        echo "high"
    fi
}

# Set resource limits based on profile
set_resource_limits() {
    local profile=$1

    case "$profile" in
        low)
            # Minimal: Pi Zero 2 W, Pi 3
            SNAPCLIENT_MEM_LIMIT="96M"
            SNAPCLIENT_MEM_RESERVE="48M"
            SNAPCLIENT_CPU_LIMIT="0.5"
            VISUALIZER_MEM_LIMIT="128M"
            VISUALIZER_MEM_RESERVE="64M"
            VISUALIZER_CPU_LIMIT="0.5"
            FBDISPLAY_MEM_LIMIT="128M"
            FBDISPLAY_MEM_RESERVE="64M"
            FBDISPLAY_CPU_LIMIT="0.5"
            ;;
        medium)
            # Standard: Pi 4 2GB
            SNAPCLIENT_MEM_LIMIT="128M"
            SNAPCLIENT_MEM_RESERVE="64M"
            SNAPCLIENT_CPU_LIMIT="0.5"
            VISUALIZER_MEM_LIMIT="256M"
            VISUALIZER_MEM_RESERVE="128M"
            VISUALIZER_CPU_LIMIT="1.0"
            FBDISPLAY_MEM_LIMIT="256M"
            FBDISPLAY_MEM_RESERVE="128M"
            FBDISPLAY_CPU_LIMIT="1.0"
            ;;
        high)
            # Performance: Pi 4 4GB+, Pi 5
            SNAPCLIENT_MEM_LIMIT="192M"
            SNAPCLIENT_MEM_RESERVE="96M"
            SNAPCLIENT_CPU_LIMIT="1.0"
            VISUALIZER_MEM_LIMIT="384M"
            VISUALIZER_MEM_RESERVE="192M"
            VISUALIZER_CPU_LIMIT="2.0"
            FBDISPLAY_MEM_LIMIT="384M"
            FBDISPLAY_MEM_RESERVE="192M"
            FBDISPLAY_CPU_LIMIT="2.0"
            ;;
    esac
}

# Detect and apply resource profile
RESOURCE_PROFILE=$(detect_resource_profile)
set_resource_limits "$RESOURCE_PROFILE"
echo "Hardware profile: $RESOURCE_PROFILE ($(awk '/MemTotal/ {printf "%.1fGB RAM", $2/1024/1024}' /proc/meminfo), $(nproc) cores)"

cd "$INSTALL_DIR"

# Read current snapserver from .env if exists (empty = autodiscovery)
current_snapserver=$(grep "^SNAPSERVER_HOST=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "")

if [ "$AUTO_MODE" = true ]; then
    snapserver_ip="${SNAPSERVER_HOST:-$current_snapserver}"
    echo "Snapserver: ${snapserver_ip:-autodiscovery (mDNS)}"
else
    [ -z "$current_snapserver" ] && echo "Current: mDNS autodiscovery" || echo "Current Snapserver: $current_snapserver"
    # Configure snapserver host (empty = autodiscovery via mDNS)
    read -rp "Enter Snapserver IP/hostname (or press Enter for autodiscovery): " snapserver_ip
    snapserver_ip=${snapserver_ip:-$current_snapserver}
fi

# Always use "default" ALSA device — asound.conf routes it through multi_out
# (DAC + loopback for spectrum analyzer). Direct hw: would bypass the loopback.
SOUNDCARD_VALUE="default"

# Docker Compose profile: always framebuffer (direct /dev/fb0 rendering)
DOCKER_COMPOSE_PROFILES="framebuffer"

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
    ["BAND_MODE"]="$BAND_MODE"
    ["COMPOSE_PROFILES"]="$DOCKER_COMPOSE_PROFILES"
    # Server metadata connection (cover art + track info served by snapMULTI server)
    # Empty = mDNS autodiscovery (same as SNAPSERVER_HOST)
    ["METADATA_HOST"]="${snapserver_ip}"
    ["METADATA_HTTP_PORT"]="8083"
    # Resource limits (auto-detected)
    ["SNAPCLIENT_MEM_LIMIT"]="$SNAPCLIENT_MEM_LIMIT"
    ["SNAPCLIENT_MEM_RESERVE"]="$SNAPCLIENT_MEM_RESERVE"
    ["SNAPCLIENT_CPU_LIMIT"]="$SNAPCLIENT_CPU_LIMIT"
    ["VISUALIZER_MEM_LIMIT"]="$VISUALIZER_MEM_LIMIT"
    ["VISUALIZER_MEM_RESERVE"]="$VISUALIZER_MEM_RESERVE"
    ["VISUALIZER_CPU_LIMIT"]="$VISUALIZER_CPU_LIMIT"
    ["FBDISPLAY_MEM_LIMIT"]="$FBDISPLAY_MEM_LIMIT"
    ["FBDISPLAY_MEM_RESERVE"]="$FBDISPLAY_MEM_RESERVE"
    ["FBDISPLAY_CPU_LIMIT"]="$FBDISPLAY_CPU_LIMIT"
)

for key in "${!env_vars[@]}"; do
    update_env_var "$key" "${env_vars[$key]}"
done

echo "Docker configuration ready"
echo "  - Snapserver: ${snapserver_ip:-autodiscovery}"
echo "  - Client ID: $CLIENT_ID"
echo "  - Soundcard: $SOUNDCARD_VALUE"
echo "  - Resolution: ${DISPLAY_RESOLUTION:-auto}"
echo "  - Band mode: $BAND_MODE"
echo "  - Resource profile: $RESOURCE_PROFILE"
echo ""

# ============================================
# Step 10: Configure Display
# ============================================
echo "Framebuffer mode: display rendering handled by fb-display Docker container"

# Disable X11 autostart if it was previously enabled (from older browser mode)
if systemctl is-enabled x11-autostart.service 2>/dev/null; then
    systemctl disable x11-autostart.service
    echo "  Disabled previous X11 autostart service"
fi
echo ""

# ============================================
# Step 10: Security Hardening
# ============================================
progress 7 "Security hardening..."
log_progress "Applying security settings..."

# Verify cgroup memory controller is configured (set in boot settings)
if [ -f "/boot/firmware/cmdline.txt" ]; then
    CMDLINE="/boot/firmware/cmdline.txt"
elif [ -f "/boot/cmdline.txt" ]; then
    CMDLINE="/boot/cmdline.txt"
else
    CMDLINE=""
fi

if [ -n "$CMDLINE" ] && grep -q "cgroup_enable=memory" "$CMDLINE"; then
    echo "✓ cgroup memory controller enabled (resource limits)"
    log_progress "cgroup memory: enabled"
else
    echo "⚠ cgroup memory controller not in cmdline (limits may not work)"
    log_progress "cgroup memory: not configured"
fi

# Verify docker-compose.yml has security settings
if grep -q "no-new-privileges" "$INSTALL_DIR/docker-compose.yml" 2>/dev/null; then
    echo "✓ Container security options configured"
    log_progress "Container security: configured"
else
    echo "⚠ Container security options not found in docker-compose.yml"
fi

# Verify read_only and tmpfs settings
if grep -q "read_only: true" "$INSTALL_DIR/docker-compose.yml" 2>/dev/null; then
    echo "✓ Read-only containers configured"
    log_progress "Read-only mode: enabled"
fi

echo ""

# ============================================
# Step 11: Create Systemd Service for Docker
# ============================================
progress 8 "Creating systemd service..."
log_progress "Creating snapclient.service..."

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
# Step 12: Pre-pull container images
# ============================================
progress 9 "Pulling container images..."
start_progress_animation 9 60 40  # Animate during long image pull

cd "$INSTALL_DIR"
log_progress "docker compose pull: snapclient"
log_progress "docker compose pull: audio-visualizer"
log_progress "docker compose pull: fb-display"
if ! docker compose pull 2>&1; then
    stop_progress_animation
    log_progress "ERROR: Failed to pull container images"
    echo ""
    echo "ERROR: Failed to pull container images."
    echo "  Without images the system cannot start."
    echo "  Check network connectivity and try: docker compose pull"
    exit 1
fi
log_progress "All images pulled successfully"
echo ""

# ============================================
# Step 13: Configure Read-Only Filesystem (optional)
# ============================================
if [[ "${ENABLE_READONLY:-false}" == "true" ]]; then
    progress 10 "Configuring read-only filesystem..."
    log_progress "Installing fuse-overlayfs..."

    # Install fuse-overlayfs for Docker compatibility with overlayfs root
    apt-get install -y fuse-overlayfs

    # Check if Docker is already using fuse-overlayfs (idempotent)
    current_driver=$(docker info --format '{{.Driver}}' 2>/dev/null || echo "none")
    if [[ "$current_driver" != "fuse-overlayfs" ]]; then
        # Switch storage driver (requires wiping existing data)
        log_progress "Switching Docker storage driver to fuse-overlayfs..."
        systemctl stop docker

        # Configure Docker to use fuse-overlayfs storage driver
        # (required because overlay2 doesn't work on overlayfs root)
        mkdir -p /etc/docker
        cp "$COMMON_DIR/docker/daemon.json" /etc/docker/daemon.json

        # Clear existing Docker data (incompatible with new storage driver)
        log_progress "Clearing Docker data (storage driver change)..."
        rm -rf /var/lib/docker/*

        # Restart Docker
        log_progress "Restarting Docker..."
        systemctl start docker

        # Re-pull images (storage was cleared)
        log_progress "Re-pulling container images..."
        cd "$INSTALL_DIR"
        if ! docker compose pull 2>&1; then
            log_progress "ERROR: Failed to re-pull images after storage driver change"
            echo "ERROR: Failed to pull images after storage driver change."
            echo "  Previous images were wiped. The system cannot start without them."
            echo "  Check network connectivity and try: docker compose pull"
            exit 1
        fi
    else
        log_progress "Docker already using fuse-overlayfs, skipping reconfiguration..."
    fi

    # Install ro-mode helper script
    log_progress "Installing ro-mode helper..."
    install -m 755 "$COMMON_DIR/scripts/ro-mode.sh" /usr/local/bin/ro-mode

    # Enable overlayfs (takes effect after reboot)
    log_progress "Enabling overlayfs..."
    raspi-config nonint do_overlayfs 0

    echo "Read-only filesystem configured"
    echo "  - Docker storage driver: fuse-overlayfs"
    echo "  - Helper script: /usr/local/bin/ro-mode"
    echo "  - Status: Will activate after reboot"
    echo ""
    echo "To temporarily disable for updates:"
    echo "  sudo ro-mode disable && sudo reboot"
    echo ""
else
    echo "Read-only filesystem: skipped (ENABLE_READONLY=false)"
fi
echo ""

# ============================================
# Setup Complete
# ============================================
progress_complete

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Configuration Summary:"
echo "  - Audio HAT: $HAT_NAME"
echo "  - Resolution: ${DISPLAY_RESOLUTION:-auto}"
echo "  - Band mode: $BAND_MODE"
echo "  - Client ID: $CLIENT_ID"
echo "  - Snapserver: ${snapserver_ip:-autodiscovery (mDNS)}"
echo "  - Resource profile: $RESOURCE_PROFILE"
echo "  - Read-only mode: ${ENABLE_READONLY:-false}"
echo "  - Install dir: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "1. Review configuration in $INSTALL_DIR/.env"
echo "2. Reboot the system: sudo reboot"
echo "3. After reboot, check services:"
echo "   - sudo systemctl status snapclient"
echo "   - sudo docker ps"
echo ""
echo "The snapclient will start automatically on boot"
echo "Cover display will render directly to framebuffer (/dev/fb0)"
if [[ "${ENABLE_READONLY:-false}" == "true" ]]; then
echo ""
echo "Read-only mode is enabled. After reboot:"
echo "  - Root filesystem will be read-only (protected from corruption)"
echo "  - Use 'sudo ro-mode status' to verify"
echo "  - Use 'sudo ro-mode disable && sudo reboot' for updates"
fi
echo ""
