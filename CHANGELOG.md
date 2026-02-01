# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Auto-Gain Spectrum with Volume Indicator** ([#12](https://github.com/lollonet/rpi-snapclient-usb/pull/12)) - Feb 1
  - Volume-independent bars: auto-gain normalization reflects spectral shape regardless of playback volume
  - Volume indicator (Vol NN% / MUTE) displayed top-right of spectrum panel
  - Metadata service now exposes `volume` and `muted` from Snapcast client config

- **Real-Time dBFS Spectrum Analyzer** ([#6](https://github.com/lollonet/rpi-snapclient-usb/pull/6)) - Feb 1
  - Custom FFT spectrum analyzer replacing CAVA: reads PCM from ALSA loopback, computes dBFS via numpy (4096-point, Hanning window), broadcasts over WebSocket
  - Configurable band resolution: `BAND_MODE` env var supports `half-octave` (19 bands) and `third-octave` (31 bands, ISO 266)
  - Two-panel framebuffer layout: album art left, info top-right, spectrum bottom-right
  - Dynamic font sizing for long titles, auto-detect resolution from sysfs

- **Zero-Touch Auto-Install** ([#6](https://github.com/lollonet/rpi-snapclient-usb/pull/6)) - Feb 1
  - `prepare-sd.sh` copies project files to boot partition and patches Pi Imager's `firstrun.sh`
  - `install/firstboot.sh` runs once on first boot, chains `setup.sh --auto`
  - `install/snapclient.conf` with sensible defaults (`AUDIO_HAT=auto`, 1080p, framebuffer, half-octave)
  - HAT auto-detection via EEPROM (`/proc/device-tree/hat/product`) with ALSA and USB fallbacks

- **Claude Code GitHub Integration** ([#5](https://github.com/lollonet/rpi-snapclient-usb/pull/5)) - Jan 30
  - GitHub Actions workflow for Claude Code AI-assisted code review

- **dBFS Spectrum with Half-Octave Bands** ([#4](https://github.com/lollonet/rpi-snapclient-usb/pull/4)) - Jan 29
  - 19 half-octave bands (20–10000 Hz) with absolute dBFS levels
  - Framebuffer renderer optimized: partial spectrum redraw only (CPU 100% → ~48%)
  - Silence gate: 1 LSB RMS threshold with immediate ring buffer clear

- **Optional Audio Visualizer** (CAVA + WebSocket) - Jan 27
  - Real-time FFT-based equalizer visualization
  - ALSA loopback (snd-aloop) for audio routing
  - WebSocket server streams data to browser
  - Graceful fallback to CSS animation if unavailable

- **Animated Cover Display** - Jan 27
  - Spinning vinyl record with realistic grooves and red label
  - Animated equalizer bars (9 bars with gradient colors)
  - Pulsing purple glow effect behind vinyl
  - Album art overlays vinyl when available

- **MusicBrainz Integration** (no API key required) - Jan 27
  - Album artwork via Cover Art Archive (fallback after iTunes)
  - Artist images via MusicBrainz → Wikidata → Wikimedia Commons
  - Proper rate limiting (1 req/sec)

- **mDNS Autodiscovery** ([#2](https://github.com/lollonet/rpi-snapclient-usb/pull/2)) - Jan 27
  - Snapclient auto-discovers Snapserver via `_snapcast._tcp` mDNS
  - No hardcoded hostnames required (SNAPSERVER_HOST now optional)
  - Avahi daemon integration for service discovery

- **Unified Setup Flow** ([#1](https://github.com/lollonet/rpi-snapclient-usb/pull/1)) - Jan 27
  - Separate HAT selection from display resolution
  - 6 resolution presets (800x480 to 3840x2160) plus custom option
  - Auto-generate CLIENT_ID from hostname
  - Consolidate all duplicates to `common/` directory
  - GPU memory auto-scaled (256MB ≤1080p, 512MB >1080p)

### Changed
- **Vanishing Peak Markers** ([#12](https://github.com/lollonet/rpi-snapclient-usb/pull/12)) - Feb 1
  - Faster decay (0.15 → 0.35): bars fall ~2x faster
  - Peaks vanish instantly after 1.5s hold instead of gradually falling

- **CI: Self-Hosted ARM64 Runner** - Jan 30
  - Replaced x86_64 GitHub Actions with manual aarch64 binary installs for shellcheck and hadolint
  - Docker image builds triggered only on version tags

### Fixed
- **ALSA Buffer Underrun** ([#13](https://github.com/lollonet/rpi-snapclient-usb/pull/13), closes [#9](https://github.com/lollonet/rpi-snapclient-usb/issues/9)) - Feb 1
  - Add `--player alsa:buffer_time=200:fragments=6` to snapclient launch command
  - Configurable via `ALSA_BUFFER_TIME` and `ALSA_FRAGMENTS` env vars
  - Numeric validation with sane bounds (50-2000ms, 2-16 fragments)
  - Only applied for ALSA devices (hw:/plughw:), not default/pulse

- **ALSA FIFO Tee Causes XRUN** ([#10](https://github.com/lollonet/rpi-snapclient-usb/pull/10), closes [#7](https://github.com/lollonet/rpi-snapclient-usb/issues/7)) - Jan 30
  - Replaced blocking ALSA `type file` plugin with `type multi` + `snd-aloop` loopback
  - DAC output fully decoupled from spectrum analyzer — stalls cannot cause XRUN
  - Audio-visualizer reads from ALSA loopback capture via libasound ctypes

- **fb-display Burns 30% CPU** ([#11](https://github.com/lollonet/rpi-snapclient-usb/pull/11), closes [#8](https://github.com/lollonet/rpi-snapclient-usb/issues/8)) - Jan 30
  - Adaptive FPS: 20 FPS (spectrum active), 5 FPS (playing, no spectrum), 1 FPS (idle)
  - Skip framebuffer writes entirely when idle

- **Visualizer 5s Startup Delay** ([#12](https://github.com/lollonet/rpi-snapclient-usb/pull/12)) - Feb 1
  - Explicit ALSA capture buffer (133ms vs 10.9s default)

- **Framebuffer Display Fixes** ([#6](https://github.com/lollonet/rpi-snapclient-usb/pull/6)) - Feb 1
  - Recompute layout on band count change
  - Disable fbcon via `fbcon=map:9` to prevent console overwriting framebuffer

- **FIFO Mount** ([#4](https://github.com/lollonet/rpi-snapclient-usb/pull/4)) - Jan 29
  - Replaced Docker tmpfs volume with host bind mount for ALSA file plugin

- **MPD Metadata Fallback** - Jan 27
  - Query MPD directly when Snapserver has no metadata for pipe streams
  - Parse radio stream "Artist - Title" format

- **Cover Art Refresh** - Jan 27
  - Cache-busting timestamp prevents stale cached artwork

- **Setup Idempotency** - Jan 27
  - Markers in config.txt for clean removal on re-run
  - Preserve existing .env settings

### Security
- **SSRF Hardening** ([#12](https://github.com/lollonet/rpi-snapclient-usb/pull/12)) - Feb 1
  - URL scheme validation + DNS resolution + private IP blocking for artwork downloads
  - Total transfer timeout (15s) for artwork downloads
  - Station name length limit (200 chars)

- **Thread Safety** ([#12](https://github.com/lollonet/rpi-snapclient-usb/pull/12)) - Feb 1
  - `threading.Lock` for band array access (resize vs render race condition)
  - RGB565 type safety: cast to uint16 before bit-shift operations
  - Framebuffer bounds validation before writes

### Removed
- `dac-plus-9inch/` directory (consolidated to `common/`)
- `digi-plus-4k/` directory (consolidated to `common/`)
- `fifo-init` service and FIFO volumes (replaced by ALSA loopback)

## [1.0.0] - 2026-01-26

### Added
- Support for 11 audio HATs (HiFiBerry, IQaudio, Allo, JustBoom, USB Audio)
- Interactive HAT selection menu in setup script
- Multi-architecture Docker builds (ARM64 + AMD64)
- Comprehensive CI/CD pipeline with GitHub Actions
- Pre-push git hooks for local CI validation
- Dynamic ALSA configuration based on selected HAT
- Cover display with metadata service
- PR workflow with branch protection

### Changed
- Removed hardcoded IP addresses from all configuration files
- Consolidated Docker build to single source (`common/docker/snapclient/`)
- Updated documentation with architecture diagrams
- Enhanced input validation in setup script

### Fixed
- ALSA card name inconsistency (now uses card name instead of card number)
- Dead code cleanup (removed unused snapclient directories)
- Shellcheck warnings in all scripts
- Docker build failures with ca-certificates
- CI workflow issues with git-cliff and SHA tags

### Security
- Replaced hardcoded private IPs with placeholder hostnames
- Docker compose now fails explicitly if SNAPSERVER_HOST not set

## [0.1.0] - Historical

Initial release with basic HiFiBerry support (DAC+ and Digi+ only).
