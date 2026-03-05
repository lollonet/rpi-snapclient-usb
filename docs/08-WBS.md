# Work Breakdown Structure & Roadmap

## Current State (v0.2.1)

### Completed Features

| Feature | Version | Status |
|---------|---------|--------|
| Snapclient audio playback | v0.1.0 | Stable |
| Album art + metadata display | v0.1.0 | Stable |
| Real-time spectrum analyzer | v0.1.0 | Stable |
| 11 audio HAT support | v0.1.0 | Stable |
| Zero-touch SD install | v0.1.0 | Stable |
| Read-only filesystem | v0.1.3 | Stable |
| Song progress bar | v0.1.8 | Stable |
| Source label + format badge | v0.1.8 | Stable |
| Non-root containers | v0.1.7 | Stable |
| Centralized metadata (server-side) | v0.2.0 | Stable |
| Big-endian support (PowerPC) | v0.2.1 | Stable |
| mDNS discovery on boot | v0.2.1 | Stable |
| Unified SNAPSERVER_HOST | v0.2.1 | Stable |

## Roadmap

### Multi-Display Layout Templates (Planned)

Aspect-ratio-specific layout templates to optimize the display for different screen geometries.

| Task | Description | Complexity |
|------|-------------|-----------|
| Define layout profiles | Map aspect ratios (16:9, 4:3, ~16:10) to layout parameters | Medium |
| Auto-detect aspect ratio | Compute ratio from framebuffer dimensions, select best template | Low |
| 4:3 template | Optimize for 1024x768 (iBook, old monitors) — taller spectrum, smaller art | Medium |
| 16:10 template | Optimize for 1024x600 (common touchscreens) | Medium |
| 16:9 template | Current layout, formalize as default | Low |
| Portrait mode | Vertical layout for rotated displays | High |

### Potential Future Work

| Area | Description | Priority |
|------|-------------|----------|
| Pi 5 validation | Test on Pi 5 hardware, update compatibility matrix | Medium |
| Pi Zero 2 W audio-only | Headless mode without display containers | Low |
| Touch controls | Volume/transport via touchscreen (partially implemented in v0.1.5) | Low |
| OTA updates | Pull new images and restart without SSH | Low |
| Multi-language | Localized setup script prompts | Low |

## Quality Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Unit tests | 94 (67 display + 27 visualizer) | 100+ |
| HAT configs validated | 11/11 | 11/11 |
| Shell scripts passing shellcheck | All | All |
| CI pipeline | lint + test + review | Same |
| Supported platforms | ARM64 + PowerPC | + Pi 5 |
