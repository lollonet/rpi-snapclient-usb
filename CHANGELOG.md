# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.5] - 2026-02-18

### Added
- **MIT License** - Added MIT license to project

### Changed
- **Python 3.13** - Upgraded all Python Docker images from 3.11-slim to 3.13-slim (metadata-service, audio-visualizer, fb-display)
- **CI Parallelization** - All 4 Docker image builds now run in parallel (removed sequential dependencies). Deployed 4 self-hosted runners on raspy for faster builds (~3 min vs ~12 min)
- **Documentation Updates** - Synced README, CLAUDE.md, and CHANGELOG with current project state
- **Code Architecture** ([#36](https://github.com/lollonet/rpi-snapclient-usb/pull/36)) - Consolidated code duplication across three areas:
  - Removed dead font wrapper functions (simplified API)
  - Extracted generic `websocket_client_loop()` utility (85% duplication eliminated)
  - Consolidated MPD greeting pattern into reusable helper (3 duplicate patterns eliminated)

### Fixed
- **Error Handling and Logging** ([#35](https://github.com/lollonet/rpi-snapclient-usb/pull/35)) - Improved error visibility:
  - Log MPD binary size parsing failures instead of silently passing
  - Separate network/IO errors from unexpected errors in MPD operations
  - Log malformed JSON from Snapserver with sample data for debugging
  - Escalate framebuffer write failures from warning to error level
- **Python 3.9 Compatibility** - Replace Python 3.10+ union type hints (`callable | None`) with `Optional[Callable]` for older Python versions
- **Documentation Default Values** - Corrected default values in documentation to match setup.sh behavior:
  - `ENABLE_READONLY=true` (was incorrectly documented as false in .env.example)
  - `DISPLAY_MODE=framebuffer` (was incorrectly documented as browser in .env.example)
  - `BAND_MODE=third-octave` default (CLAUDE.md incorrectly stated half-octave as default)
- **Documentation Accuracy** - Fixed README and CLAUDE.md inconsistencies found during 10-pass review:
  - Standardized Docker image naming across all docs
  - Added Docker Compose v2+ requirement
  - Clarified read-only filesystem is enabled by default

## [0.1.4] - 2026-02-11

### Added
- **Song Progress Bar** - Display elapsed/duration time with visual progress bar for file playback. Uses Snapserver MPRIS properties (position, duration) with local clock for smooth updates

### Changed
- **Touch Controls Reverted** - Touch screen controls removed pending UX redesign. Will return in a future release

### Fixed
- **Snapserver Artwork SSRF** - Allow artwork downloads from Snapserver host (was blocked by private IP protection)
- **Control Command Logging** - Improved logging for debugging control commands

## [0.1.3] - 2026-02-10

### Added
- **Touch Screen Controls** ([#34](https://github.com/lollonet/rpi-snapclient-usb/pull/34)) - Tap to toggle play/pause, swipe up/down for volume control. Gracefully degrades on non-touch displays

### Fixed
- **Spectrum DC offset** - Remove DC component before FFT to prevent false 20 Hz activity during speech/radio content
- **Metadata thread safety** - Add lock for socket operations to prevent JSON-RPC stream corruption when control commands arrive during polling
- **Touch volume sensitivity** - Scale swipe distance by screen height and cap at ±10 per gesture for more predictable control
- **evdev build dependencies** - Add gcc, libc-dev, linux-libc-dev to fb-display Dockerfile for evdev compilation
- **Metadata stale connection** ([#31](https://github.com/lollonet/rpi-snapclient-usb/pull/31)) - Add 10s socket timeout and 30s staleness threshold to detect half-open TCP connections to snapserver
- **Spectrum analyzer accuracy** ([#32](https://github.com/lollonet/rpi-snapclient-usb/pull/32)) - Increase FFT size to 8192 for better low-frequency resolution (5.4 Hz/bin), tune smoothing for smoother visuals

## [0.1.1] - 2026-02-07

### Added
- **SnapForge Branding** ([#30](https://github.com/lollonet/rpi-snapclient-usb/pull/30)) - Brand text logo displayed next to icon in bottom bar
- **Read-Only Root Filesystem** ([#25](https://github.com/lollonet/rpi-snapclient-usb/pull/25)) - SD card protection using raspi-config overlayfs, enabled by default. Includes Docker fuse-overlayfs storage driver and `ro-mode` helper script
- **WebSocket Metadata Push** - Metadata service pushes updates via WebSocket instead of HTTP polling, reducing latency

### Changed
- **Bottom Bar Redesign** ([#27](https://github.com/lollonet/rpi-snapclient-usb/pull/27)) - Logo (left), date+time (center), enlarged volume knob (right). Clock shows `Thu 05 Feb · HH:MM:SS` format
- **Read-only filesystem enabled by default** - Use `--no-readonly` flag to disable

### Fixed
- **ARM64 ctypes** ([#30](https://github.com/lollonet/rpi-snapclient-usb/pull/30)) - Add argtypes/restype for snd_pcm_readi to prevent 64-bit return value truncation on RPi 4/5
- **Spectrum range** ([#27](https://github.com/lollonet/rpi-snapclient-usb/pull/27)) - Extended from 20Hz–10kHz to full 20Hz–20kHz (21 bands)
- **Persistent TCP** ([#26](https://github.com/lollonet/rpi-snapclient-usb/pull/26)) - Metadata service uses single connection to snapserver instead of reconnecting each poll
- **Dead code cleanup** ([#29](https://github.com/lollonet/rpi-snapclient-usb/pull/29)) - Remove stale comments, unused variables, duplicate changelog headings
- **RO-mode status detection** - Fix overlayroot mount detection in status check
- **Visualizer healthcheck** - Use process check instead of TCP connect to avoid WebSocket error spam

### Security
- **CSP Header** ([#30](https://github.com/lollonet/rpi-snapclient-usb/pull/30)) - Add Content-Security-Policy meta tag to web UI for defense-in-depth

### Documentation
- **CLAUDE.md rewrite** ([#28](https://github.com/lollonet/rpi-snapclient-usb/pull/28)) - Architecture map and operational rules

## [0.1.0] - 2026-02-05

Initial release with core feature set.

### Features

- **11 Audio HATs Supported** - HiFiBerry (DAC+, Digi+, DAC2 HD), IQaudio (DAC+, DigiAMP+, Codec Zero), Allo (Boss, DigiOne), JustBoom (DAC, Digi), USB Audio
- **HAT Auto-Detection** - Reads EEPROM at `/proc/device-tree/hat/product`, falls back to ALSA card names, then USB
- **mDNS Autodiscovery** - Snapserver found via `_snapcast._tcp` mDNS, no IP configuration needed
- **Zero-Touch Install** - Flash SD, copy files with `prepare-sd.sh`, boot Pi, wait 5 minutes
- **Install Progress Display** - Visual progress on HDMI during install (800x600)
- **Cover Display** - Full-screen album art with track metadata on framebuffer or browser
- **Artwork Sources** - MPD embedded → iTunes (validated) → MusicBrainz/Cover Art Archive → Radio-Browser
- **Real-Time Spectrum Analyzer** - dBFS FFT with half-octave (21) or third-octave (31) bands
- **Auto-Gain Normalization** - Spectrum reflects shape regardless of volume, with volume indicator
- **Standby Screen** - Retro VU meter artwork with breathing animation when idle
- **Adaptive FPS** - 20 FPS (spectrum), 5 FPS (playing), 1 FPS (idle) to save CPU
- **Digital Clock** - Nerdy retro-style clock on install progress and framebuffer display
- **Container Healthchecks** - All services with `condition: service_healthy` dependencies
- **Resource Limits** - Auto-detected CPU/memory limits based on Pi RAM (2GB/4GB/8GB profiles)

### Security

- **Input Validation** - Shell metacharacter rejection, path traversal prevention
- **SSRF Protection** - URL scheme validation, DNS resolution, private IP blocking (IPv4 + IPv6)
- **Granular Capabilities** - Specific caps (SYS_NICE, IPC_LOCK) instead of privileged mode
- **Hardened tmpfs** - All mounts use `noexec,nosuid,nodev` flags
- **MPD Protocol Hardening** - Control char rejection, socket timeouts, binary size limits
- **Thread Safety** - Locks for shared state, bounds validation, type-safe operations

### Technical

- **ALSA Loopback** - `snd-aloop` decouples DAC from spectrum analyzer, prevents XRUN
- **Buffer Tuning** - 150ms buffer, 4 fragments for underrun prevention
- **Docker-based** - Pre-built ARM64 images on GHCR
- **Systemd Services** - Auto-start on boot
- **CI/CD** - Shellcheck, Hadolint, HAT config tests, Docker builds on tags
