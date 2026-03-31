**Status: Reflects implementation as of v0.2.19**

# Vision

## Project Identity

**Name**: snapclient-pi
**Author**: Claudio Loletti
**License**: MIT
**Repository**: Component of [snapMULTI](https://github.com/lollonet/snapMULTI) (included as git submodule at `client/`)

## Mission

Turn any Raspberry Pi with an audio HAT into a turnkey multiroom audio endpoint with visual feedback — album art, track metadata, and real-time spectrum analysis on a framebuffer display. This is the **client component** of the snapMULTI multiroom audio appliance ecosystem.

## Problem Statement

Setting up a Snapcast client on a Raspberry Pi requires:
- Manual ALSA configuration for each audio HAT
- Docker setup with correct device mappings and capabilities
- Display configuration for framebuffer rendering
- Metadata service integration for cover art and track info
- Network discovery for the Snapcast server

Each of these steps is error-prone and undocumented for non-technical users. The result is that Snapcast's excellent synchronized audio goes underutilized because the client-side setup is too complex.

## Target Audience

DIY audiophile and home automation community — specifically Snapcast and HiFiBerry users who want a polished, zero-configuration audio endpoint. The project bridges the gap between Snapcast's server capabilities (handled by [snapMULTI](https://github.com/lollonet/snapMULTI)) and consumer-grade ease of use on the client side.

## Design Principles

1. **Auto-detection first**: HATs detected from EEPROM, server found via mDNS, resolution read from framebuffer. No manual configuration required.
2. **Appliance behavior**: Flash SD, power on, music plays. No SSH needed for normal operation.
3. **Visual quality**: Album art, spectrum analyzer, and metadata display rival commercial audio players.
4. **Resilience**: Read-only filesystem protects the SD card. Services auto-restart. Power loss is safe.
5. **Minimal footprint**: Three Docker containers, resource-limited per Pi model. Runs on 2GB Pi 4.

## Relationship to snapMULTI

This project is the **client component** of the snapMULTI multiroom audio appliance:

```
snapMULTI (server)                    snapclient-pi (client)
├── Snapserver (audio streaming)      ├── Snapclient (audio output)
├── MPD / Spotify / AirPlay / Tidal   ├── Audio Visualizer (spectrum analysis)
├── Metadata Service (centralized) ───>├── FB Display (cover art + metadata)
└── myMPD (web control)               └── Auto-detection + installer
```

snapMULTI includes this repo as a git submodule at `client/`. The unified installer (`prepare-sd.sh`) can deploy:
1. **Audio Player** (client only)
2. **Music Server** (server only)
3. **Server + Player** (both on same Pi)

## Success Criteria

- ✅ Zero-touch install completes in under 10 minutes
- ✅ Audio plays within 30 seconds of boot
- ✅ Cover art and metadata appear without user configuration
- ✅ System survives unexpected power loss without corruption