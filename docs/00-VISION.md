# Vision

## Project Identity

**Name**: rpi-snapclient-usb
**Author**: Claudio Loletti
**License**: MIT
**Repository**: [github.com/lollonet/rpi-snapclient-usb](https://github.com/lollonet/rpi-snapclient-usb)

## Mission

Turn any Raspberry Pi with an audio HAT into a turnkey multiroom audio endpoint with visual feedback — album art, track metadata, and real-time spectrum analysis on a framebuffer display.

## Problem Statement

Setting up a Snapcast client on a Raspberry Pi requires:
- Manual ALSA configuration for each audio HAT
- Docker setup with correct device mappings and capabilities
- Display configuration for framebuffer rendering
- Metadata service integration for cover art and track info
- Network discovery for the Snapcast server

Each of these steps is error-prone and undocumented for non-technical users. The result is that Snapcast's excellent synchronized audio goes underutilized because the client-side setup is too complex.

## Target Audience

DIY audiophile and home automation community — specifically Snapcast and HiFiBerry users who want a polished, zero-configuration audio endpoint. The project bridges the gap between Snapcast's server capabilities (handled by [snapMULTI](https://github.com/lollonet/snapMULTY)) and consumer-grade ease of use on the client side.

## Design Principles

1. **Auto-detection first**: HATs detected from EEPROM, server found via mDNS, resolution read from framebuffer. No manual configuration required.
2. **Appliance behavior**: Flash SD, power on, music plays. No SSH needed for normal operation.
3. **Visual quality**: Album art, spectrum analyzer, and metadata display rival commercial audio players.
4. **Resilience**: Read-only filesystem protects the SD card. Services auto-restart. Power loss is safe.
5. **Minimal footprint**: Three Docker containers, resource-limited per Pi model. Runs on 2GB Pi 4.

## Relationship to snapMULTI

This project is the **client component** of the snapMULTI ecosystem:

```
snapMULTI (server)          rpi-snapclient-usb (client)
├── Snapserver              ├── Snapclient (audio)
├── MPD / Spotify / AirPlay ├── Audio Visualizer (spectrum)
├── Metadata Service ──────>├── FB Display (cover art + UI)
└── myMPD (web UI)          └── Auto-detection + installer
```

snapMULTI includes this repo as a git submodule at `client/`. The unified installer (`prepare-sd.sh`) can deploy server, client, or both on the same Pi.

## Success Criteria

- Zero-touch install completes in under 10 minutes
- Audio plays within 30 seconds of boot
- Cover art and metadata appear without user configuration
- System survives unexpected power loss without corruption
