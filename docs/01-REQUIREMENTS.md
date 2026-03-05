# Requirements

## Functional Requirements

### FR-01: Audio Playback

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.1 | Receive synchronized audio from Snapserver over TCP (port 1704) | Must |
| FR-01.2 | Output audio via ALSA to any of the 11 supported HATs or USB DAC | Must |
| FR-01.3 | Support hardware and software mixer modes | Must |
| FR-01.4 | Route audio to both DAC and ALSA loopback simultaneously (for spectrum) | Must |
| FR-01.5 | Auto-discover Snapserver via mDNS (`_snapcast._tcp`) | Must |
| FR-01.6 | Buffer tuning via `ALSA_BUFFER_TIME` and `ALSA_FRAGMENTS` | Should |

### FR-02: Spectrum Analyzer

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-02.1 | Capture audio from ALSA loopback device | Must |
| FR-02.2 | Compute FFT spectrum (8192-point) at 44100 Hz sample rate | Must |
| FR-02.3 | Support third-octave (31 bands) and half-octave (21 bands) modes | Must |
| FR-02.4 | Broadcast dBFS spectrum data via WebSocket (port 8081) | Must |
| FR-02.5 | Apply attack/decay smoothing for visual quality | Should |
| FR-02.6 | Deduplicate identical frames during silence | Should |
| FR-02.7 | Work on both little-endian (ARM) and big-endian (PowerPC) platforms | Must |

### FR-03: Framebuffer Display

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-03.1 | Render album art, track metadata, and spectrum to `/dev/fb0` | Must |
| FR-03.2 | Display source name, title, artist, album | Must |
| FR-03.3 | Show format badge (codec, sample rate, bit depth) | Must |
| FR-03.4 | Animate song progress bar with local clock interpolation | Must |
| FR-03.5 | Show volume knob, date/time, and branding in bottom bar | Must |
| FR-03.6 | Display standby screen with breathing animation when idle | Must |
| FR-03.7 | Auto-detect resolution from framebuffer, cap at 1920x1080 | Must |
| FR-03.8 | Scale render output to actual framebuffer dimensions | Must |
| FR-03.9 | Support 16bpp (RGB565) and 32bpp (BGRA/XRGB) framebuffers | Must |
| FR-03.10 | Connect to metadata service via WebSocket and HTTP | Must |

### FR-04: Installation & Setup

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-04.1 | Zero-touch install via SD card (`prepare-sd.sh` + `firstboot.sh`) | Must |
| FR-04.2 | Auto-detect audio HAT from EEPROM, ALSA, or USB | Must |
| FR-04.3 | Interactive setup mode with HAT and resolution selection | Must |
| FR-04.4 | Generate `.env` and ALSA configuration from selections | Must |
| FR-04.5 | Install Docker CE with Compose v2 plugin | Must |
| FR-04.6 | Pull pre-built Docker images (never build on Pi) | Must |
| FR-04.7 | Support both firstrun.sh (Bullseye) and cloud-init (Bookworm+) boot paths | Must |
| FR-04.8 | Discover snapserver via mDNS on every boot (`discover-server.sh`) | Must |

### FR-05: Metadata Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-05.1 | Subscribe to metadata service with `CLIENT_ID` via WebSocket (port 8082) | Must |
| FR-05.2 | Receive track info pushes (title, artist, album, duration, position, state) | Must |
| FR-05.3 | Fetch cover art via HTTP (port 8083) | Must |
| FR-05.4 | Derive `METADATA_HOST` from `SNAPSERVER_HOST` (same server) | Must |
| FR-05.5 | Auto-reconnect on WebSocket disconnection | Must |

## Non-Functional Requirements

### NFR-01: Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01.1 | Boot to audio playback | < 30 seconds |
| NFR-01.2 | Display frame rate | >= 15 FPS |
| NFR-01.3 | Spectrum latency (capture to display) | < 100ms |
| NFR-01.4 | Memory usage (all containers) | < 512MB total |
| NFR-01.5 | CPU usage at idle | < 15% |

### NFR-02: Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-02.1 | Survive unexpected power loss | No corruption |
| NFR-02.2 | Auto-restart on container crash | < 10 seconds |
| NFR-02.3 | Circuit breaker on persistent failures | Exit after 30-50 errors |
| NFR-02.4 | Reconnect to metadata on server restart | Automatic |

### NFR-03: Security

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-03.1 | Containers run as non-root (uid 1000) | All 3 containers |
| NFR-03.2 | Read-only container filesystems | All 3 containers |
| NFR-03.3 | Minimal capabilities (`CAP_DROP: ALL` + specific adds) | All 3 containers |
| NFR-03.4 | No secrets in repository | Enforced |
| NFR-03.5 | Input validation in setup scripts | All user input |
| NFR-03.6 | Artwork URLs constrained to metadata server | fb-display |

### NFR-04: Compatibility

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-04.1 | Raspberry Pi 4 (2/4/8 GB) | Tested |
| NFR-04.2 | Raspberry Pi 5 | Untested (should work) |
| NFR-04.3 | Raspberry Pi 3B+ | Untested (low profile) |
| NFR-04.4 | 11 audio HATs + USB audio | Tested |
| NFR-04.5 | Resolutions 800x480 to 3840x2160 | Tested |
| NFR-04.6 | Big-endian platforms (PowerPC) | Tested (native, no Docker) |
