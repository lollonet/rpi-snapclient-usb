# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Security
- Replaced hardcoded private IPs with placeholder hostnames
- Docker compose now fails explicitly if SNAPSERVER_HOST not set

## [0.1.0] - Historical

Initial release with basic HiFiBerry support (DAC+ and Digi+ only).

---

**Note**: Changelog will be automatically generated from conventional commits starting with v1.0.0 using git-cliff.
