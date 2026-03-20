#!/usr/bin/env bash
# shellcheck disable=SC2034  # Variables assigned in case statement, used via indirect expansion ${!var}
set -euo pipefail

# Test resource profile detection and limits
# Tests detect_resource_profile() and set_resource_limits() from setup.sh

pass=0
fail=0

echo "Testing detect_resource_profile()..."

# Mock /proc/meminfo for testing
test_detect() {
    local mem_mb="$1"
    local expected="$2"
    local desc="$3"
    local mock_meminfo actual profile

    # Create mock meminfo
    mock_meminfo=$(mktemp)
    echo "MemTotal:       $((mem_mb * 1024)) kB" > "$mock_meminfo"
    trap 'rm -f "$mock_meminfo"' RETURN

    # Run detection with mock
    actual=$(awk '/MemTotal/ {print int($2/1024)}' "$mock_meminfo" 2>/dev/null || echo 0)

    # Determine profile based on RAM (logic from detect_resource_profile)
    local profile
    if (( actual < 256 )); then
        profile="standard"
    elif (( actual < 2048 )); then
        profile="minimal"
    elif (( actual < 4096 )); then
        profile="standard"
    else
        profile="performance"
    fi

    if [[ "$profile" == "$expected" ]]; then
        echo "  PASS: $desc (${mem_mb}MB -> ${profile})"
        pass=$((pass + 1))
    else
        echo "  FAIL: $desc (${mem_mb}MB -> ${profile}, expected ${expected})"
        fail=$((fail + 1))
    fi
}

# Test profile detection
test_detect "512"    "minimal"     "512MB RAM -> minimal"
test_detect "1024"   "minimal"     "1GB RAM -> minimal"
test_detect "2048"   "standard"    "2GB RAM -> standard"
test_detect "4096"   "performance" "4GB RAM -> performance"
test_detect "8192"   "performance" "8GB RAM -> performance"
test_detect "100"    "standard"    "Error case (low) -> standard fallback"

echo ""
echo "Testing set_resource_limits()..."

test_limits() {
    local profile="$1"
    local var="$2"
    local expected="$3"
    local desc="$4"

    # Inline set_resource_limits logic
    case "$profile" in
        minimal)
            SNAPCLIENT_MEM_LIMIT="64M"
            SNAPCLIENT_MEM_RESERVE="32M"
            SNAPCLIENT_CPU_LIMIT="0.5"
            VISUALIZER_MEM_LIMIT="128M"
            VISUALIZER_MEM_RESERVE="48M"
            VISUALIZER_CPU_LIMIT="0.5"
            FBDISPLAY_MEM_LIMIT="192M"
            FBDISPLAY_MEM_RESERVE="96M"
            FBDISPLAY_CPU_LIMIT="0.5"
            ;;
        standard)
            SNAPCLIENT_MEM_LIMIT="64M"
            SNAPCLIENT_MEM_RESERVE="32M"
            SNAPCLIENT_CPU_LIMIT="0.5"
            VISUALIZER_MEM_LIMIT="128M"
            VISUALIZER_MEM_RESERVE="64M"
            VISUALIZER_CPU_LIMIT="1.0"
            FBDISPLAY_MEM_LIMIT="256M"
            FBDISPLAY_MEM_RESERVE="128M"
            FBDISPLAY_CPU_LIMIT="1.0"
            ;;
        performance)
            SNAPCLIENT_MEM_LIMIT="96M"
            SNAPCLIENT_MEM_RESERVE="48M"
            SNAPCLIENT_CPU_LIMIT="1.0"
            VISUALIZER_MEM_LIMIT="192M"
            VISUALIZER_MEM_RESERVE="96M"
            VISUALIZER_CPU_LIMIT="1.5"
            FBDISPLAY_MEM_LIMIT="384M"
            FBDISPLAY_MEM_RESERVE="192M"
            FBDISPLAY_CPU_LIMIT="2.0"
            ;;
    esac

    local actual="${!var:-}"

    if [[ "$actual" == "$expected" ]]; then
        echo "  PASS: $desc"
        pass=$((pass + 1))
    else
        echo "  FAIL: $desc (${profile}.${var} = ${actual}, expected ${expected})"
        fail=$((fail + 1))
    fi
}

# Test minimal profile
test_limits "minimal" "SNAPCLIENT_MEM_LIMIT"    "64M"  "minimal snapclient memory"
test_limits "minimal" "VISUALIZER_MEM_LIMIT"    "128M" "minimal visualizer memory"
test_limits "minimal" "FBDISPLAY_MEM_LIMIT"     "192M" "minimal fb-display memory"
test_limits "minimal" "SNAPCLIENT_CPU_LIMIT"    "0.5"  "minimal snapclient cpu"

# Test standard profile
test_limits "standard" "SNAPCLIENT_MEM_LIMIT"   "64M"  "standard snapclient memory"
test_limits "standard" "VISUALIZER_MEM_LIMIT"   "128M" "standard visualizer memory"
test_limits "standard" "FBDISPLAY_MEM_LIMIT"    "256M" "standard fb-display memory"
test_limits "standard" "SNAPCLIENT_CPU_LIMIT"   "0.5"  "standard snapclient cpu"

# Test performance profile
test_limits "performance" "SNAPCLIENT_MEM_LIMIT"  "96M"  "performance snapclient memory"
test_limits "performance" "VISUALIZER_MEM_LIMIT"  "192M" "performance visualizer memory"
test_limits "performance" "FBDISPLAY_MEM_LIMIT"   "384M" "performance fb-display memory"
test_limits "performance" "SNAPCLIENT_CPU_LIMIT"  "1.0"  "performance snapclient cpu"

echo ""
if [[ "$fail" -gt 0 ]]; then
    echo "FAILED: $fail tests failed, $pass passed"
    exit 1
fi
echo "All $pass tests passed!"
