#!/bin/sh
set -e

# Default values (SNAPSERVER_HOST empty = mDNS autodiscovery)
SNAPSERVER_PORT="${SNAPSERVER_PORT:-1704}"
HOST_ID="${HOST_ID:-snapclient}"
SOUNDCARD="${SOUNDCARD:-default}"
ALSA_BUFFER_TIME="${ALSA_BUFFER_TIME:-200}"
ALSA_FRAGMENTS="${ALSA_FRAGMENTS:-6}"

# Validate numeric values and enforce sane bounds
case "${ALSA_BUFFER_TIME}" in
    ''|*[!0-9]*) echo "Invalid ALSA_BUFFER_TIME, using default 200"; ALSA_BUFFER_TIME=200 ;;
esac
if [ "${ALSA_BUFFER_TIME}" -lt 50 ] || [ "${ALSA_BUFFER_TIME}" -gt 2000 ]; then
    echo "ALSA_BUFFER_TIME out of range (50-2000), using default 200"
    ALSA_BUFFER_TIME=200
fi

case "${ALSA_FRAGMENTS}" in
    ''|*[!0-9]*) echo "Invalid ALSA_FRAGMENTS, using default 6"; ALSA_FRAGMENTS=6 ;;
esac
if [ "${ALSA_FRAGMENTS}" -lt 2 ] || [ "${ALSA_FRAGMENTS}" -gt 16 ]; then
    echo "ALSA_FRAGMENTS out of range (2-16), using default 6"
    ALSA_FRAGMENTS=6
fi

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

# Only add ALSA buffer tuning for ALSA devices (hw: or plughw:)
case "${SOUNDCARD}" in
    hw:*|plughw:*)
        echo "  ALSA buffer: ${ALSA_BUFFER_TIME}ms, ${ALSA_FRAGMENTS} fragments"
        CMD="${CMD} --player alsa:buffer_time=${ALSA_BUFFER_TIME}:fragments=${ALSA_FRAGMENTS}"
        ;;
esac

if [ -n "${SNAPSERVER_HOST}" ]; then
    CMD="${CMD} --host ${SNAPSERVER_HOST} --port ${SNAPSERVER_PORT}"
fi

# Start snapclient
exec ${CMD} "$@"
