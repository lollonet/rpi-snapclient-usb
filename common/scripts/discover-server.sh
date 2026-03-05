#!/usr/bin/env bash
# Discover snapserver via mDNS and populate SNAPSERVER_HOST in .env.
# Runs as ExecStartPre before Docker Compose services start.
set -euo pipefail

ENV_FILE="/opt/snapclient/.env"

# Skip if SNAPSERVER_HOST is already set (user configured explicit IP)
current=$(grep "^SNAPSERVER_HOST=" "$ENV_FILE" 2>/dev/null | cut -d= -f2) || true
if [[ -n "$current" ]]; then
    echo "snapclient-discover: SNAPSERVER_HOST=$current (configured)"
    exit 0
fi

# Discover via mDNS
if command -v avahi-browse &>/dev/null; then
    host=$(timeout 10 avahi-browse -rpt _snapcast._tcp 2>/dev/null \
        | awk -F';' '/^=/ && $3=="IPv4" {print $8; exit}') || true
    if [[ -n "$host" ]] && [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        sed -i "s|^SNAPSERVER_HOST=.*|SNAPSERVER_HOST=${host}|" "$ENV_FILE"
        echo "snapclient-discover: found snapserver at $host"
        exit 0
    fi
fi

echo "snapclient-discover: no snapserver found, using localhost fallback"
