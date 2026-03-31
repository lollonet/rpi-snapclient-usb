**Status: Reflects implementation as of v0.2.19**

# Infrastructure

## Docker Images

| Image | Base | Size | Contents |
|-------|------|------|----------|
| `lollonet/snapclient-pi` | Alpine | ~30MB | snapclient binary, entrypoint |
| `lollonet/snapclient-pi-visualizer` | Python 3.13-slim | ~120MB | numpy, websockets, ctypes ALSA |
| `lollonet/snapclient-pi-fb-display` | Python 3.13-slim | ~150MB | numpy, pillow, websockets, requests |

**Platform**: `linux/arm64` (Docker images). Python code also runs natively on other architectures.

**Registry**: Docker Hub. Images are pulled, never built on the Pi.

### Bind-Mounted Files

These files are mounted from the host into containers for live updates without image rebuild:

| File | Container | Purpose |
|------|-----------|---------|
| `visualizer.py` | audio-visualizer | Spectrum analyzer logic |
| `fb_display.py` | fb-display | Display renderer |
| `logo.png` | fb-display | Bottom bar logo |
| `snapforge-text.png` | fb-display | Text logo |
| `entrypoint.sh` | snapclient | Startup script |
| `/etc/asound.conf` | snapclient | ALSA configuration |

## CI/CD

### Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push, PR | Shellcheck, pytest, bash syntax, HAT config validation |
| `docker-build.yml` | Tag `v*` | Build + push 3 Docker images |
| `deploy.yml` | Tag `v*` | Deploy to test devices |
| `release.yml` | Tag `v*` | Create GitHub Release |
| `claude-code-review.yml` | PR | Automated code review |
| `claude.yml` | `@claude` mention | Claude CI helper |

### Build Pipeline

```
Tag v0.2.19 pushed
    │
    ├── build-snapclient ──▶ Docker Hub: lollonet/snapclient-pi:0.2.19, :latest
    ├── build-visualizer ──▶ Docker Hub: lollonet/snapclient-pi-visualizer:0.2.19, :latest
    └── build-fb-display ──▶ Docker Hub: lollonet/snapclient-pi-fb-display:0.2.19, :latest
```

All 3 jobs run in parallel on self-hosted runners.

### Pre-Push Hooks (Local CI)

```
git push
    ├── shellcheck (all .sh files)
    ├── bash syntax check
    ├── HAT config validation
    └── HAT count check (15 expected)
```

Install: `bash scripts/install-hooks.sh`

## Resource Profiles

Auto-detected by `setup.sh` based on Pi RAM:

| Profile | RAM | CPU (snap) | Mem (snap) | CPU (viz) | Mem (viz) | CPU (fb) | Mem (fb) |
|---------|-----|-----------|-----------|----------|----------|---------|---------|
| Minimal | <2GB | 0.5 | 64M | 0.5 | 128M | 0.5 | 192M |
| Standard | 2-4GB | 0.5 | 64M | 1.0 | 128M | 1.0 | 256M |
| Performance | 8GB+ | 1.0 | 96M | 1.5 | 192M | 1.5 | 384M |

## Deployment Methods

### 1. Zero-Touch SD Card (Recommended)

```
Host computer                    Raspberry Pi
┌────────────┐                   ┌────────────────────┐
│ Flash OS   │                   │ Boot               │
│ prepare-sd │──SD card insert──▶│ firstboot.sh       │
│            │                   │ setup.sh --auto    │
└────────────┘                   │ docker pull + up   │
                                 │ reboot             │
                                 └────────────────────┘
```

Boot path: server `prepare-sd.sh` → cloud-init → server `firstboot.sh` → client `setup.sh --auto` → reboot

### 2. Live Update (Development)

```bash
rsync -av common/ pi:/opt/snapclient/
ssh pi "cd /opt/snapclient && sudo docker compose up -d --force-recreate"
```

Bind-mounted files (fb_display.py, visualizer.py) update without image rebuild.

### 3. Manual Setup

```bash
sudo bash common/scripts/setup.sh
# Interactive: select HAT, resolution, server
```

## Systemd Services

On Docker hosts, containers are managed by Docker Compose with `restart: unless-stopped`.

### Boot-Time Services

| Service | Purpose |
|---------|---------|
| `snapclient-display.service` | Run `display-detect.sh` at boot to set `COMPOSE_PROFILES` |
| `snapclient-discover.service` | Run `discover-server.sh` to find Snapserver via mDNS |

Both are oneshot services that run before Docker starts containers.