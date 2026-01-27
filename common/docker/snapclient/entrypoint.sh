#!/bin/sh
set -e

# Default values (SNAPSERVER_HOST empty = mDNS autodiscovery)
SNAPSERVER_PORT="${SNAPSERVER_PORT:-1704}"
HOST_ID="${HOST_ID:-snapclient}"
SOUNDCARD="${SOUNDCARD:-default}"

echo "Starting snapclient..."
if [ -n "${SNAPSERVER_HOST}" ]; then
    echo "  Server: ${SNAPSERVER_HOST}:${SNAPSERVER_PORT}"
else
    echo "  Server: autodiscovery (mDNS)"
fi
echo "  Host ID: ${HOST_ID}"
echo "  Soundcard: ${SOUNDCARD}"

# Build command - only add --host if explicitly set
CMD="/usr/bin/snapclient --hostID ${HOST_ID} --soundcard ${SOUNDCARD}"

if [ -n "${SNAPSERVER_HOST}" ]; then
    CMD="${CMD} --host ${SNAPSERVER_HOST} --port ${SNAPSERVER_PORT}"
fi

# Start snapclient
exec ${CMD} "$@"
