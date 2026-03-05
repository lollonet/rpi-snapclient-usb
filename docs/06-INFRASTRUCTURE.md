# Infrastructure

## Docker Images

| Image | Base | Size | Contents |
|-------|------|------|----------|
| `lollonet/rpi-snapclient-usb` | Alpine | ~30MB | snapclient binary, entrypoint |
| `lollonet/rpi-snapclient-usb-visualizer` | Python 3.13-slim | ~120MB | numpy, websockets, ctypes ALSA |
| `lollonet/rpi-snapclient-usb-fb-display` | Python 3.13-slim | ~150MB | numpy, pillow, websockets, requests |

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
| `ci.yml` | Push, PR | Shellcheck, Hadolint, pytest, bash syntax |
| `docker-build.yml` | Tag `v*` | Build + push 3 Docker images |
| `release.yml` | Tag `v*` | Create GitHub Release |
| `claude-code-review.yml` | PR | Automated code review |
| `claude.yml` | `@claude` mention | Claude CI helper |

### Build Pipeline

```
Tag v0.2.1 pushed
    │
    ├── build-snapclient ──▶ Docker Hub: lollonet/rpi-snapclient-usb:0.2.1, :latest
    ├── build-visualizer ──▶ Docker Hub: lollonet/rpi-snapclient-usb-visualizer:0.2.1, :latest
    └── build-fb-display ──▶ Docker Hub: lollonet/rpi-snapclient-usb-fb-display:0.2.1, :latest
```

All 3 jobs run in parallel on self-hosted runners (`[self-hosted, linux, x64]`).

### Pre-Push Hooks (Local CI)

```
git push
    ├── shellcheck (all .sh files)
    ├── hadolint (Dockerfiles, optional)
    ├── bash syntax check
    ├── HAT config validation
    └── HAT count check (11 expected)
```

Install: `bash scripts/install-hooks.sh`

## Resource Profiles

Auto-detected by `setup.sh` based on Pi RAM:

| Profile | RAM | CPU (snap) | Mem (snap) | CPU (viz) | Mem (viz) | CPU (fb) | Mem (fb) |
|---------|-----|-----------|-----------|----------|----------|---------|---------|
| Low | <2GB | 0.3 | 64M | 0.5 | 128M | 0.5 | 128M |
| Medium | 2-4GB | 0.5 | 128M | 1.0 | 256M | 1.0 | 256M |
| High | 4GB+ | 0.5 | 128M | 1.0 | 256M | 1.0 | 256M |

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

Boot path: `prepare-sd.sh` → firstrun.sh/cloud-init → `firstboot.sh` → `setup.sh --auto` → reboot

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

## Deployment Hosts

| Host | IP | Role | Notes |
|------|-----|------|-------|
| snapvideo | 192.168.63.104 | Server + Client | 1920x1080 32bpp, HiFiBerry |
| snapdigi | 192.168.63.5 | Client only | Often offline |
| ciccio | — | Client (native) | iBook G4 PowerPC, 1024x768 32bpp |

## Systemd Services

On Docker hosts, containers are managed by Docker Compose with `restart: unless-stopped`.

On native hosts (e.g. ciccio), systemd services manage the Python processes directly:
- `audio-visualizer.service` (after snapclient)
- `fb-display.service` (after audio-visualizer)

### Boot-Time mDNS Discovery

`discover-server.sh` runs as a oneshot systemd service before Docker starts:
- Resolves snapserver IP via `avahi-browse -rpt _snapcast._tcp`
- Updates `SNAPSERVER_HOST` in `/opt/snapclient/.env`
- Prevents stale IPs from previous sessions
