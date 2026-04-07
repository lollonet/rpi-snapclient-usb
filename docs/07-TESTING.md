**Status: Reflects implementation as of v0.2.19**

# Testing

## Test Suite

### Unit Tests (pytest)

Located in `tests/`. Run with:

```bash
uvx --with numpy --with pillow --with websockets --with requests pytest tests/ -v
```

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_fb_display.py` | 82 | Layout, pixel format conversion, scaling, color, badges, timing, spectrum, metadata handling, version display, mDNS discovery |
| `test_visualizer.py` | 27 | FFT, band computation, smoothing, WebSocket broadcast |

### Test Categories

| Category | Examples |
|----------|---------|
| Pixel format | 32bpp BGRA (LE), XRGB (BE), 16bpp RGB565 |
| Layout | Key presence, art fits screen, spectrum below info, bar width |
| Audio badges | FLAC, MP3, WAV, DSD; lossless/hires/lossy coloring |
| Timing | Format time (seconds, minutes, hours), progress bar elapsed |
| Spectrum | Idle wave shape, active detection threshold |
| Scaling | Same-res no-op, 2x scale, dtype preservation |
| Color | Lerp, rainbow gradient |
| Metadata handling | server_info dispatch, normal track update, invalid JSON |
| Version display | Both versions, client-only, server-only, neither, "unknown" filter |
| mDNS discovery | Discover snapservers, failover, no-result handling |

### Shell Tests

| Script | Run By | Tests | Checks |
|--------|--------|-------|--------|
| `test_hat_configs.sh` | Pre-push hook, CI | 15 | HAT config file format, required fields, count (15) |
| `test_entrypoint.sh` | CI | 22 | MIXER validation (11), ALSA buffer validation (11) |
| `test_resource_profiles.sh` | CI | — | Resource profile detection logic |
| shellcheck | Pre-push hook, CI | — | All `.sh` files pass shellcheck |
| bash syntax | Pre-push hook, CI | — | `bash -n` on all scripts |

### Current Test Status

Python tests are **not yet integrated into CI** — they run locally during development but CI only runs shell tests and linting. This is a known gap.

## CI Pipeline

```
PR opened / push
    │
    ├── Lint job
    │   ├── shellcheck (all .sh)
    │   ├── hadolint (Dockerfiles)
    │   └── HAT config validation
    │
    ├── Test job
    │   ├── Shell test validation
    │   └── Resource profile tests
    │
    └── Claude Code Review
        └── Automated review with severity levels
```

### Review Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| CRITICAL | Security vulnerability, data loss | Blocks merge |
| HIGH | Wrong behavior, silent failure | Should fix before merge |
| MEDIUM | CI gap, dead code, missing coverage | Fix before release |
| LOW | Style, naming, minor improvements | Optional |

## Manual Verification

After deployment, verify using the [Post-Install Verification Checklist](../README.md#post-install-verification):

1. Docker services running and healthy
2. Audio device detected (`aplay -l`)
3. Snapserver connection established
4. Display rendering (framebuffer logs)
5. Spectrum analyzer active (port 8081 logs)
6. Read-only filesystem status

## Test Coverage Areas

### Well-Covered
- Pixel format conversion (LE + BE, 16bpp + 32bpp)
- Layout computation across resolutions
- Audio badge generation and coloring
- Time formatting and progress calculation
- Spectrum smoothing and idle detection

### Known Gaps
- Python tests not in CI pipeline
- No integration tests (would require real ALSA loopback + framebuffer)
- No end-to-end metadata subscription test
- Setup script testing is syntax-only (no functional tests)
- No performance benchmarks in CI