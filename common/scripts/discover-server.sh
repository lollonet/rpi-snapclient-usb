#!/usr/bin/env bash
# Monitor snapserver IP and restart snapclient if the server moves.
# Boot mode:  runs as ExecStartPre (no args) — sets localhost for "both" mode.
# Watch mode: runs periodically (--watch) — restarts client if server IP changed.
#
# SNAPSERVER_HOST in .env is left empty (mDNS autodiscovery via snapclient).
# Only "both" mode sets SNAPSERVER_HOST=127.0.0.1 (local server always wins).
set -euo pipefail

ENV_FILE="/opt/snapclient/.env"
LAST_IP_FILE="/run/snapclient-server-ip"
WATCH_MODE=false
[[ "${1:-}" == "--watch" ]] && WATCH_MODE=true

# "Both" mode: local snapserver always wins
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^snapserver$'; then
    current=$(grep "^SNAPSERVER_HOST=" "$ENV_FILE" 2>/dev/null | cut -d= -f2) || true
    if [[ "$current" != "127.0.0.1" ]]; then
        echo "snapclient-discover: local snapserver detected, switching to 127.0.0.1"
        if $WATCH_MODE; then
            if cd /opt/snapclient && docker compose restart snapclient 2>/dev/null; then
                sed -i "s|^SNAPSERVER_HOST=.*|SNAPSERVER_HOST=127.0.0.1|" "$ENV_FILE" 2>/dev/null \
                    || echo "SNAPSERVER_HOST=127.0.0.1" >> "$ENV_FILE"
            else
                echo "snapclient-discover: restart failed, will retry next cycle"
                exit 0
            fi
        else
            sed -i "s|^SNAPSERVER_HOST=.*|SNAPSERVER_HOST=127.0.0.1|" "$ENV_FILE" 2>/dev/null \
                || echo "SNAPSERVER_HOST=127.0.0.1" >> "$ENV_FILE"
        fi
    else
        echo "snapclient-discover: local snapserver, using 127.0.0.1"
    fi
    exit 0
fi

# Clear any hardcoded SNAPSERVER_HOST — clients should always use mDNS autodiscovery.
# Old installs may have an IP written by a previous discover-server.sh version.
current=$(grep "^SNAPSERVER_HOST=" "$ENV_FILE" 2>/dev/null | cut -d= -f2) || true
if [[ -n "$current" && "$current" != "127.0.0.1" ]]; then
    sed -i "s|^SNAPSERVER_HOST=.*|SNAPSERVER_HOST=|" "$ENV_FILE" 2>/dev/null || true
    echo "snapclient-discover: cleared hardcoded SNAPSERVER_HOST=$current (using mDNS)"
    if $WATCH_MODE; then
        cd /opt/snapclient && docker compose restart snapclient 2>/dev/null || true
    fi
fi

# Watch mode: detect server IP changes and restart snapclient
if $WATCH_MODE && command -v avahi-browse &>/dev/null; then
    host=$(timeout 10 avahi-browse -rpt _snapcast._tcp 2>/dev/null \
        | awk -F';' '/^=/ && $3=="IPv4" {print $8; exit}') || true
    last=$(cat "$LAST_IP_FILE" 2>/dev/null) || true

    if [[ -n "$host" ]] && [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        if [[ -n "$last" && "$host" != "$last" ]]; then
            echo "snapclient-discover: server moved $last -> $host, restarting client"
            if cd /opt/snapclient && docker compose restart snapclient 2>/dev/null; then
                echo "$host" > "$LAST_IP_FILE"
            else
                echo "snapclient-discover: restart failed, will retry next cycle"
            fi
        else
            echo "$host" > "$LAST_IP_FILE"
        fi
    else
        echo "snapclient-discover: no snapserver found via mDNS"
    fi
    exit 0
fi

echo "snapclient-discover: boot mode, snapclient will use mDNS autodiscovery"
