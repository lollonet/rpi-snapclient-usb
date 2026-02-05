# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **fb-display bottom bar redesign** - Logo (left), date+time (center), enlarged volume knob (right). Volume knob moved from spectrum panel to bottom bar. Clock now shows `Thu 05 Feb · HH:MM:SS` format
- **Read-only filesystem enabled by default** - SD card protection is now on by default in both auto and interactive mode. Use `--no-readonly` flag to disable

### Fixed
- **Spectrum only covered 20 Hz–10 kHz** - Half-octave band centers extended from 19 bands (20–10000 Hz) to 21 bands (20–20000 Hz), covering the full audible range

### Added
- **Read-Only Root Filesystem** - SD card protection using raspi-config overlayfs, enabled by default. Disable with `--no-readonly` flag. Includes Docker fuse-overlayfs storage driver and `ro-mode` helper script for easy enable/disable
- **WebSocket Metadata Push** ([9e168fb](https://github.com/lollonet/rpi-snapclient-usb/commit/9e168fb)) - Metadata service now pushes updates via WebSocket instead of HTTP polling, reducing latency and network overhead

### Fixed (continued)
- **fb-display OOM on high-res framebuffers** - Render at internal resolution (from `DISPLAY_RESOLUTION` or auto-capped at 1920x1080) and scale to actual framebuffer. Prevents OOM kills on 4K displays with low memory limits. `DISPLAY_RESOLUTION` is now optional; leave empty to auto-detect
- **Visualizer Healthcheck** ([f4a25ab](https://github.com/lollonet/rpi-snapclient-usb/commit/f4a25ab)) - Use process check instead of TCP connect to avoid spamming WebSocket error logs
- **Dead Code Removal** ([b771304](https://github.com/lollonet/rpi-snapclient-usb/commit/b771304)) - Remove unused `metadata_queue` variable from metadata service

### Maintenance
- **CI Cache Fix** ([a202721](https://github.com/lollonet/rpi-snapclient-usb/commit/a202721)) - Remove GHA cache from fb-display job to fix transient build failures

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
