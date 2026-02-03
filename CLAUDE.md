# Project Requirements

## mDNS Discovery

**MUST use `_snapcast._tcp` for Snapserver discovery**, not `_snapcast-ctrl._tcp`.

- Snapserver advertises streaming service on `_snapcast._tcp` (port 1704)
- RPC/control port = streaming_port + 1 (1705)
- The `_snapcast-ctrl._tcp` service is NOT advertised by default

## Auto-Detection

Always prefer auto-detection over hardcoded values:
- Audio HAT: detect via EEPROM (`/proc/device-tree/hat/product`)
- Snapserver: discover via mDNS, never hardcode IP
- Display resolution: use user config, not hardcoded defaults

## Install Progress Screen

- Resolution: 800x600 via `video=HDMI-A-1:800x600@60` in cmdline.txt
- KMS driver ignores `hdmi_group`/`hdmi_mode` - must use cmdline.txt `video=` param
- Remove video param after install so final boot uses native resolution
