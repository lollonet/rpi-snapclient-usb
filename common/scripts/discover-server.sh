#!/usr/bin/env bash
# Discover snapserver via mDNS and populate SNAPSERVER_HOST in .env.
# Boot mode:  runs as ExecStartPre (no args) — skips if host already set.
# Watch mode: runs periodically (--watch) — re-discovers and restarts client if IP changed.
set -euo pipefail

ENV_FILE="/opt/snapclient/.env"
WATCH_MODE=false
[[ "${1:-}" == "--watch" ]] && WATCH_MODE=true

current=$(grep "^SNAPSERVER_HOST=" "$ENV_FILE" 2>/dev/null | cut -d= -f2) || true

# "Both" mode: local snapserver always wins — no discovery needed
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^snapserver$'; then
    if [[ "$current" != "127.0.0.1" ]]; then
        sed -i "s|^SNAPSERVER_HOST=.*|SNAPSERVER_HOST=127.0.0.1|" "$ENV_FILE" 2>/dev/null \
            || echo "SNAPSERVER_HOST=127.0.0.1" >> "$ENV_FILE"
        $WATCH_MODE && cd /opt/snapclient && docker compose restart snapclient 2>/dev/null || true
    fi
    echo "snapclient-discover: local snapserver detected, using 127.0.0.1"
    exit 0
fi

# Boot mode: skip if SNAPSERVER_HOST is already set (user configured explicit IP)
if ! $WATCH_MODE && [[ -n "$current" ]]; then
    echo "snapclient-discover: SNAPSERVER_HOST=$current (configured)"
    exit 0
fi

# Discover via mDNS
if command -v avahi-browse &>/dev/null; then
    host=$(timeout 10 avahi-browse -rpt _snapcast._tcp 2>/dev/null \
        | awk -F';' '/^=/ && $3=="IPv4" {print $8; exit}') || true
    if [[ -n "$host" ]] && [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        if [[ "$host" != "$current" ]]; then
            sed -i "s|^SNAPSERVER_HOST=.*|SNAPSERVER_HOST=${host}|" "$ENV_FILE"
            echo "snapclient-discover: server moved $current -> $host"
            $WATCH_MODE && cd /opt/snapclient && docker compose restart snapclient 2>/dev/null || true
        fi
        exit 0
    fi
fi

echo "snapclient-discover: no snapserver found, keeping $current"
