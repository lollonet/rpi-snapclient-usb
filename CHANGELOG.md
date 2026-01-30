# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **ALSA FIFO tee causes continuous XRUN** ([#7](https://github.com/lollonet/rpi-snapclient-usb/issues/7))
  - Replaced blocking ALSA `type file` plugin with `type multi` + `snd-aloop` loopback
  - Audio now sent to both DAC and loopback simultaneously — visualizer reads from loopback capture side
  - DAC output is fully decoupled from spectrum analyzer — stalls or pauses in the visualizer cannot cause XRUN
  - Removed `fifo-init` service and `/tmp/audio` FIFO volume from docker-compose
  - Audio-visualizer now reads from ALSA loopback capture (`hw:Loopback,1,0`) via libasound ctypes
  - setup.sh loads `snd-aloop` kernel module and persists via `/etc/modules-load.d/snapclient.conf`

- **fb-display burns 30% CPU** ([#8](https://github.com/lollonet/rpi-snapclient-usb/issues/8))
  - Added adaptive FPS: 20 FPS (spectrum active), 5 FPS (playing, no spectrum), 1 FPS (idle)
  - Skip framebuffer writes entirely when idle and spectrum is not animating
  - Expected CPU reduction: ~95% when idle, ~60-70% during playback

### Added
- **Unified Setup Flow** ([#1](https://github.com/lollonet/rpi-snapclient-usb/pull/1)) - Jan 27
  - Separate HAT selection from display resolution (no longer coupled)
  - Add 6 resolution presets (800x480 to 3840x2160) plus custom option
  - Auto-generate CLIENT_ID from hostname
  - Consolidate all duplicates to `common/` directory
  - Single responsive cover display using viewport units
  - Dynamic boot/config.txt generation based on resolution
  - GPU memory auto-scaled (256MB ≤1080p, 512MB >1080p)

- **mDNS Autodiscovery** ([#2](https://github.com/lollonet/rpi-snapclient-usb/pull/2)) - Jan 27
  - Snapclient auto-discovers Snapserver via `_snapcast._tcp` mDNS
  - No hardcoded hostnames required (SNAPSERVER_HOST now optional)
  - Avahi daemon integration for service discovery

- **Optional Audio Visualizer** (CAVA + WebSocket) - Jan 27
  - Real-time FFT-based equalizer visualization
  - ALSA loopback (snd-aloop) for audio routing
  - WebSocket server streams CAVA data to browser
  - Graceful fallback to CSS animation if unavailable
  - Enable via `AUDIO_VISUALIZER_ENABLED=true` or Docker profile

- **Animated Cover Display** - Jan 27
  - Spinning vinyl record with realistic grooves and red label
  - Animated equalizer bars (9 bars with gradient colors)
  - Pulsing purple glow effect behind vinyl
  - Album art overlays vinyl when available
  - Animations pause when music stops

- **MusicBrainz Integration** (no API key required) - Jan 27
  - Album artwork via Cover Art Archive (fallback after iTunes)
  - Artist images via MusicBrainz → Wikidata → Wikimedia Commons
  - Proper rate limiting (1 req/sec)

### Fixed
- **MPD Metadata Fallback** - Jan 27
  - Query MPD directly when Snapserver has no metadata for pipe streams
  - Parse radio stream "Artist - Title" format from Title field
  - Use station Name as album for radio streams

- **Cover Art Refresh** - Jan 27
  - Cache-busting timestamp added to local artwork URLs
  - Browser no longer serves stale cached artwork images

- **Setup Idempotency** - Jan 27
  - Use markers in config.txt for clean removal on re-run
  - Preserve existing .env settings (Snapserver IP, custom values)
  - Skip Docker install if already present

### Removed
- `dac-plus-9inch/` directory (consolidated to `common/`)
- `digi-plus-4k/` directory (consolidated to `common/`)
- `HAT_DISPLAY` field from HAT configs (display now independent)

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

---

**Note**: Changelog will be automatically generated from conventional commits starting with v1.0.0 using git-cliff.
