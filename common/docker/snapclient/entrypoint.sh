#!/bin/sh
set -e

# Default values
SNAPSERVER_HOST="${SNAPSERVER_HOST:-192.168.63.3}"
SNAPSERVER_PORT="${SNAPSERVER_PORT:-1704}"
HOST_ID="${HOST_ID:-snapclient-digi-4k}"
SOUNDCARD="${SOUNDCARD:-default}"

echo "Starting snapclient on Raspberry Pi 4..."
echo "  Server: ${SNAPSERVER_HOST}:${SNAPSERVER_PORT}"
echo "  Host ID: ${HOST_ID}"
echo "  Soundcard: ${SOUNDCARD}"

# Start snapclient
exec /usr/bin/snapclient \
    --host "${SNAPSERVER_HOST}" \
    --port "${SNAPSERVER_PORT}" \
    --hostID "${HOST_ID}" \
    --soundcard "${SOUNDCARD}" \
    "$@"
