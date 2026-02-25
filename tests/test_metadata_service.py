"""Tests for metadata-service (pure logic, no network)."""

import sys
import os
import socket
from unittest.mock import MagicMock

import pytest

# Add metadata-service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common", "docker", "metadata-service"))

# Stub zeroconf and websockets before import (not available in test env)
sys.modules.setdefault("zeroconf", MagicMock())
sys.modules.setdefault("websockets", MagicMock())
sys.modules.setdefault("websockets.exceptions", MagicMock())

import importlib
metadata_service = importlib.import_module("metadata-service")
SnapcastMetadataService = metadata_service.SnapcastMetadataService


class TestReadMpdResponse:
    """Test _read_mpd_response handles socket edge cases."""

    def _make_service(self) -> SnapcastMetadataService:
        return SnapcastMetadataService("127.0.0.1", 1705, "test-client")

    def test_normal_ok_response(self):
        sock = MagicMock(spec=socket.socket)
        sock.recv.return_value = b"state: play\nOK\n"
        svc = self._make_service()
        result = svc._read_mpd_response(sock)
        assert result == b"state: play\nOK\n"
        sock.recv.assert_called_once_with(1024)

    def test_ack_response(self):
        sock = MagicMock(spec=socket.socket)
        sock.recv.return_value = b"ACK [50@0] {play} No such song\n"
        svc = self._make_service()
        result = svc._read_mpd_response(sock)
        assert b"ACK" in result

    def test_empty_recv_breaks_loop(self):
        """Empty recv (b'') means connection closed — must not loop forever."""
        sock = MagicMock(spec=socket.socket)
        sock.recv.return_value = b""
        svc = self._make_service()
        result = svc._read_mpd_response(sock)
        assert result == b""
        # Should have called recv exactly once, then broken out
        sock.recv.assert_called_once_with(1024)

    def test_partial_then_ok(self):
        """Multi-chunk response: partial data followed by OK."""
        sock = MagicMock(spec=socket.socket)
        sock.recv.side_effect = [b"Title: Test\n", b"Artist: Foo\nOK\n"]
        svc = self._make_service()
        result = svc._read_mpd_response(sock)
        assert result == b"Title: Test\nArtist: Foo\nOK\n"
        assert sock.recv.call_count == 2

    def test_partial_then_connection_closed(self):
        """Partial data followed by connection close returns what was read."""
        sock = MagicMock(spec=socket.socket)
        sock.recv.side_effect = [b"Title: Test\n", b""]
        svc = self._make_service()
        result = svc._read_mpd_response(sock)
        assert result == b"Title: Test\n"
        assert sock.recv.call_count == 2


class TestDetectCodec:
    """Test codec detection from file path and audio format."""

    def test_flac_extension(self):
        assert SnapcastMetadataService._detect_codec("music/song.flac", "") == "FLAC"

    def test_mp3_extension(self):
        assert SnapcastMetadataService._detect_codec("song.mp3", "") == "MP3"

    def test_http_url_returns_radio(self):
        assert SnapcastMetadataService._detect_codec("http://stream.example.com/radio", "") == "RADIO"

    def test_https_url_returns_radio(self):
        assert SnapcastMetadataService._detect_codec("https://stream.example.com/live", "") == "RADIO"

    def test_pcm_float_format(self):
        assert SnapcastMetadataService._detect_codec("pipe:///tmp/snapfifo", "48000:f:2") == "PCM"

    def test_unknown_extension(self):
        assert SnapcastMetadataService._detect_codec("file.xyz", "") == "XYZ"

    def test_no_extension(self):
        assert SnapcastMetadataService._detect_codec("noext", "") == ""


class TestParseAudioFormat:
    """Test MPD audio format string parsing."""

    def test_standard_format(self):
        rate, bits = SnapcastMetadataService._parse_audio_format("44100:16:2")
        assert rate == 44100
        assert bits == 16

    def test_float_format(self):
        rate, bits = SnapcastMetadataService._parse_audio_format("48000:f:2")
        assert rate == 48000
        assert bits == 32

    def test_empty_string(self):
        rate, bits = SnapcastMetadataService._parse_audio_format("")
        assert rate == 0
        assert bits == 0

    def test_hi_res(self):
        rate, bits = SnapcastMetadataService._parse_audio_format("192000:24:2")
        assert rate == 192000
        assert bits == 24

    def test_malformed_single_component(self):
        rate, bits = SnapcastMetadataService._parse_audio_format("44100")
        assert rate == 0
        assert bits == 0
