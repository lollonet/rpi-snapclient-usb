#!/bin/sh
set -e

# Default values (SNAPSERVER_HOST empty = mDNS autodiscovery)
SNAPSERVER_PORT="${SNAPSERVER_PORT:-1704}"
HOST_ID="${HOST_ID:-snapclient}"
SOUNDCARD="${SOUNDCARD:-default}"
ALSA_BUFFER_TIME="${ALSA_BUFFER_TIME:-150}"
ALSA_FRAGMENTS="${ALSA_FRAGMENTS:-4}"

# Validate numeric values and enforce sane bounds
case "${ALSA_BUFFER_TIME}" in
    ''|*[!0-9]*) echo "Invalid ALSA_BUFFER_TIME, using default 150"; ALSA_BUFFER_TIME=150 ;;
esac
if [ "${ALSA_BUFFER_TIME}" -lt 50 ] || [ "${ALSA_BUFFER_TIME}" -gt 2000 ]; then
    echo "ALSA_BUFFER_TIME out of range (50-2000), using default 150"
    ALSA_BUFFER_TIME=150
fi

case "${ALSA_FRAGMENTS}" in
    ''|*[!0-9]*) echo "Invalid ALSA_FRAGMENTS, using default 4"; ALSA_FRAGMENTS=4 ;;
esac
if [ "${ALSA_FRAGMENTS}" -lt 2 ] || [ "${ALSA_FRAGMENTS}" -gt 16 ]; then
    echo "ALSA_FRAGMENTS out of range (2-16), using default 4"
    ALSA_FRAGMENTS=4
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

# Apply ALSA buffer tuning for all ALSA output to reduce underruns
echo "  ALSA buffer: ${ALSA_BUFFER_TIME}ms, ${ALSA_FRAGMENTS} fragments"
CMD="${CMD} --player alsa:buffer_time=${ALSA_BUFFER_TIME}:fragments=${ALSA_FRAGMENTS}"

if [ -n "${SNAPSERVER_HOST}" ]; then
    CMD="${CMD} --host ${SNAPSERVER_HOST} --port ${SNAPSERVER_PORT}"
fi

# Start snapclient
exec ${CMD} "$@"
