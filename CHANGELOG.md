# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Unified Setup Flow** ([#1](https://github.com/lollonet/rpi-snapclient-usb/pull/1))
  - Separate HAT selection from display resolution (no longer coupled)
  - Add 6 resolution presets (800x480 to 3840x2160) plus custom option
  - Auto-generate CLIENT_ID from hostname
  - Consolidate all duplicates to `common/` directory
  - Single responsive cover display using viewport units
  - Dynamic boot/config.txt generation based on resolution
  - GPU memory auto-scaled (256MB ≤1080p, 512MB >1080p)

### Added
- **Animated Cover Display**
  - Spinning vinyl record with realistic grooves and red label
  - Animated equalizer bars (9 bars with gradient colors)
  - Pulsing purple glow effect behind vinyl
  - Album art overlays vinyl when available
  - Animations pause when music stops

- **MusicBrainz Integration** (no API key required)
  - Album artwork via Cover Art Archive (fallback after iTunes)
  - Artist images via MusicBrainz → Wikidata → Wikimedia Commons
  - Proper rate limiting (1 req/sec)

### Fixed
- **Setup Idempotency** - Running setup.sh multiple times now produces consistent results
  - Use markers in config.txt for clean removal on re-run
  - Preserve existing .env settings (Snapserver IP, custom values)
  - Copy index.html to public/ directory
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
