#!/usr/bin/env python3
"""
Snapcast Metadata Service
Fetches metadata from Snapserver JSON-RPC and serves it as JSON for cover display.
Supports all sources: MPD, AirPlay, Spotify, etc.

Pushes metadata changes via WebSocket to connected clients (fb-display).
"""

import asyncio
import html
import ipaddress
import json
import logging
import os
import socket
import hashlib
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import websockets
from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

# WebSocket server state
WS_PORT = int(os.environ.get("METADATA_WS_PORT", "8082"))
_MAIN_LOOP_MAX_ERRORS = 30
ws_clients: set = set()
_service_instance: "SnapcastMetadataService | None" = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def discover_snapserver(timeout: int = 10) -> tuple[str, int] | None:
    """Discover Snapserver via mDNS, returns (host, rpc_port) or None."""
    result: tuple[str, int] | None = None

    def on_service_state_change(zeroconf: Zeroconf, service_type: str,
                                name: str, state_change: ServiceStateChange) -> None:
        nonlocal result
        if state_change is ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info and info.parsed_addresses():
                host = info.parsed_addresses()[0]
                # Streaming port is advertised; RPC port is streaming + 1
                rpc_port = (info.port or 1704) + 1
                logger.info(f"Discovered Snapserver via mDNS: {host}:{rpc_port}")
                result = (host, rpc_port)

    zc = Zeroconf()
    browser = ServiceBrowser(zc, "_snapcast._tcp.local.", handlers=[on_service_state_change])

    deadline = time.time() + timeout
    while result is None and time.time() < deadline:
        time.sleep(0.2)

    browser.cancel()
    zc.close()
    return result


class SnapcastMetadataService:
    def __init__(self, snapserver_host: str, snapserver_port: int, client_id: str):
        self.snapserver_host = snapserver_host
        self.snapserver_port = snapserver_port
        self.client_id = client_id
        self.stream_id: str | None = None  # Set when client is found
        self.mpd_host = snapserver_host  # MPD usually on same host as snapserver
        self.mpd_port = 6600
        self.output_file = Path("/app/public/metadata.json")
        self.current_metadata: dict[str, Any] = {}
        self.artwork_cache: dict[str, str] = {}
        self.artist_image_cache: dict[str, str] = {}
        self.user_agent = os.environ.get("USER_AGENT", "SnapcastMetadataService/1.0")
        self._mpd_was_connected = False
        self._failed_downloads: dict[str, float] = {}
        self._snap_sock: socket.socket | None = None
        self._snap_buffer: bytes = b""
        self._snap_lock = threading.Lock()  # Protect socket from concurrent access
        self._last_snap_response: float = 0.0
        self._snap_stale_threshold: float = 30.0  # Force reconnect if no response in 30s

    # Cache eviction limits
    _CACHE_MAX_ARTWORK = 500
    _CACHE_MAX_ARTIST = 200
    _CACHE_MAX_FAILED = 200
    _FAILED_DOWNLOAD_TTL = 300.0  # 5 min before retrying failed downloads

    def _trim_cache(self, cache: dict, max_size: int) -> None:
        """Evict oldest half of cache when it exceeds max_size."""
        if len(cache) >= max_size:
            keys = list(cache.keys())
            for k in keys[:len(keys) // 2]:
                del cache[k]

    def _create_socket_connection(self, host: str, port: int, timeout: int = 5, log_errors: bool = True) -> socket.socket | None:
        """Create a socket connection with standard settings."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            return sock
        except Exception as e:
            if log_errors:
                logger.error(f"Failed to connect to {host}:{port}: {e}")
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            return None

    def _get_snap_socket(self) -> socket.socket | None:
        """Return persistent Snapserver socket, connecting if needed."""
        if self._snap_sock is not None:
            return self._snap_sock
        self._snap_sock = self._create_socket_connection(
            self.snapserver_host, self.snapserver_port
        )
        if self._snap_sock:
            # Set recv timeout to detect stale connections (half-open sockets)
            self._snap_sock.settimeout(10.0)
            self._last_snap_response = time.monotonic()
            logger.info(f"Connected to snapserver {self.snapserver_host}:{self.snapserver_port}")
        return self._snap_sock

    def _close_snap_socket(self) -> None:
        """Close persistent Snapserver socket and reset buffer."""
        if self._snap_sock is not None:
            try:
                self._snap_sock.close()
            except Exception:
                pass
            self._snap_sock = None
            self._snap_buffer = b""

    def _read_mpd_response(self, sock: socket.socket) -> bytes:
        """Read MPD response until OK or ACK"""
        response = b""
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break  # connection closed
            response += chunk
            if b"OK\n" in chunk or b"ACK" in chunk:
                break
        return response

    def _parse_mpd_response(self, response: bytes) -> dict[str, str]:
        """Parse MPD response into key-value pairs"""
        lines = response.decode('utf-8', errors='replace').split('\n')
        return {
            key: value for line in lines
            if ': ' in line
            for key, value in [line.split(': ', 1)]
        }

    def _read_mpd_greeting(self, sock: socket.socket, validate: bool = False) -> bool:
        """Read MPD greeting from socket.

        Args:
            sock: Connected MPD socket
            validate: If True, validate greeting starts with 'OK MPD'

        Returns:
            True if greeting valid (or validation skipped), False if invalid
        """
        try:
            greeting = sock.recv(1024)
            if validate and not greeting.startswith(b"OK MPD"):
                return False
            return True
        except (socket.error, socket.timeout):
            return False

    @staticmethod
    def _detect_codec(file_path: str, audio_fmt: str) -> str:
        """Detect codec from file extension or audio format string."""
        is_url = file_path.startswith(("http://", "https://"))

        # URLs are always radio/stream — return RADIO
        if is_url:
            return "RADIO"

        codec_map = {
            "flac": "FLAC", "wav": "WAV", "aiff": "AIFF", "aif": "AIFF",
            "mp3": "MP3", "ogg": "OGG", "opus": "OPUS",
            "m4a": "AAC", "aac": "AAC", "mp4": "AAC",
            "wma": "WMA", "ape": "APE", "wv": "WV", "dsf": "DSD", "dff": "DSD",
        }
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext in codec_map:
            return codec_map[ext]
        # Fallback: check if floating-point PCM (MPD 'f' format)
        if audio_fmt and ":f:" in audio_fmt:
            return "PCM"
        return ext.upper() if ext else ""

    @staticmethod
    def _parse_audio_format(audio_fmt: str) -> tuple[int, int]:
        """Parse MPD audio format string like '48000:16:2' or '48000:f:2'.

        Returns (sample_rate_hz, bit_depth). bit_depth=0 for float.
        """
        if not audio_fmt:
            return 0, 0
        parts = audio_fmt.split(":")
        if len(parts) < 2:
            return 0, 0
        try:
            sample_rate = int(parts[0])
            bits_str = parts[1]
            if bits_str == "f":
                bit_depth = 32  # float = 32-bit
            else:
                bit_depth = int(bits_str)
        except (ValueError, IndexError):
            return 0, 0
        return sample_rate, bit_depth

    def _extract_radio_metadata(self, title: str, artist: str, song: dict[str, str]) -> tuple[str, str, str]:
        """Extract artist/title from radio stream format and determine album"""
        if not artist and ' - ' in title:
            parts = title.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else title

        album = html.unescape(song.get('Album', '') or song.get('Name', ''))
        return title, artist, album

    def get_mpd_metadata(self) -> dict[str, Any]:
        """Get metadata directly from MPD"""
        sock = self._create_socket_connection(self.mpd_host, self.mpd_port, log_errors=False)
        if not sock:
            if self._mpd_was_connected:
                logger.warning(f"MPD connection lost (host={self.mpd_host}, port={self.mpd_port})")
                self._mpd_was_connected = False
            return {"playing": False, "source": "MPD"}

        try:
            if not self._mpd_was_connected:
                logger.info(f"MPD connected (host={self.mpd_host}, port={self.mpd_port})")
                self._mpd_was_connected = True

            # Read MPD greeting
            if not self._read_mpd_greeting(sock):
                return {"playing": False, "source": "MPD"}

            # Get status
            sock.sendall(b"status\n")
            status = self._parse_mpd_response(self._read_mpd_response(sock))

            if status.get('state', 'stop') != 'play':
                return {"playing": False, "source": "MPD"}

            # Parse playback time fields for progress display
            elapsed = float(status.get('elapsed', 0))
            duration = float(status.get('duration', 0))

            # Get current song
            sock.sendall(b"currentsong\n")
            song = self._parse_mpd_response(self._read_mpd_response(sock))

            title, artist, album = self._extract_radio_metadata(
                html.unescape(song.get('Title', '')),
                html.unescape(song.get('Artist', '')),
                song
            )

            # Extract audio format info
            audio_fmt = status.get('audio', '') or song.get('Format', '')
            file_path = song.get('file', '')
            bitrate_str = status.get('bitrate', '')
            bitrate = int(bitrate_str) if bitrate_str else 0
            codec = self._detect_codec(file_path, audio_fmt)
            sample_rate, bit_depth = self._parse_audio_format(audio_fmt)

            return {
                "playing": True,
                "title": title,
                "artist": artist,
                "album": album,
                "artwork": "",
                "stream_id": "MPD",
                "source": "MPD",
                "codec": codec,
                "bitrate": bitrate,
                "sample_rate": sample_rate,
                "bit_depth": bit_depth,
                "file": file_path,
                "station_name": song.get("Name", ""),
                "elapsed": int(elapsed),
                "duration": int(duration),
            }

        except Exception as e:
            if self._mpd_was_connected:
                logger.warning(f"MPD query failed (host={self.mpd_host}, port={self.mpd_port}): {e}")
                self._mpd_was_connected = False
            return {"playing": False, "source": "MPD"}
        finally:
            sock.close()

    _MAX_MPD_ARTWORK_BYTES = 10_000_000  # 10 MB

    @staticmethod
    def _image_extension(data: bytes) -> str:
        """Detect image format from magic bytes."""
        if len(data) >= 8 and data[:8] == b'\x89PNG\r\n\x1a\n':
            return ".png"
        if len(data) >= 3 and data[:3] == b'GIF':
            return ".gif"
        if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return ".webp"
        return ".jpg"  # default (JPEG, or unknown)

    def fetch_mpd_artwork(self, file_path: str) -> str:
        """Fetch embedded cover art from MPD via readpicture command.

        Returns local path (e.g. '/artwork_<hash>.ext') or empty string.
        """
        if not file_path:
            return ""

        # Check cache — use file_path as key (check all extensions)
        art_hash = hashlib.md5(f"mpd:{file_path}".encode()).hexdigest()
        for ext in (".jpg", ".png", ".gif", ".webp"):
            cached = self.output_file.parent / f"artwork_{art_hash}{ext}"
            if cached.exists() and cached.stat().st_size > 0:
                return f"/artwork_{art_hash}{ext}"

        sock = self._create_socket_connection(self.mpd_host, self.mpd_port, log_errors=False)
        if not sock:
            return ""

        try:
            sock.settimeout(10)  # 10s timeout for all recv() calls

            # Read and validate MPD greeting
            if not self._read_mpd_greeting(sock, validate=True):
                return ""

            # Escape per MPD protocol to prevent command injection
            # Reject paths with control characters (newlines, tabs, nulls)
            if any(c in file_path for c in '\n\r\t\x00'):
                logger.warning("Rejected file path with control characters")
                return ""
            safe_path = file_path.replace('\\', '\\\\').replace('"', '\\"')

            image_data = b""
            offset = 0

            while True:
                cmd = f'readpicture "{safe_path}" {offset}\n'
                sock.sendall(cmd.encode())

                # Read header lines until 'binary: N' or OK/ACK
                header = b""
                while b"binary:" not in header and b"OK\n" not in header and b"ACK" not in header:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return ""  # connection closed
                    header += chunk

                if b"ACK" in header or b"binary:" not in header:
                    break

                # Parse binary size from header
                bin_size = 0
                for line in header.split(b"\n"):
                    if line.startswith(b"binary: "):
                        try:
                            bin_size = int(line.split(b": ", 1)[1])
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse MPD binary size from line: {line[:50]!r}: {e}")
                            bin_size = 0
                        break
                else:
                    break

                if bin_size <= 0 or bin_size > self._MAX_MPD_ARTWORK_BYTES:
                    break

                # Locate binary data: find the 'binary: N\n' line end in raw bytes
                bin_marker = f"binary: {bin_size}\n".encode()
                marker_pos = header.find(bin_marker)
                if marker_pos < 0:
                    break
                remaining = header[marker_pos + len(bin_marker):]

                # Read exactly bin_size bytes of binary data
                while len(remaining) < bin_size:
                    chunk = sock.recv(min(8192, bin_size - len(remaining)))
                    if not chunk:
                        return ""  # connection closed mid-transfer
                    remaining += chunk

                # Enforce total size limit before appending
                if len(image_data) + bin_size > self._MAX_MPD_ARTWORK_BYTES:
                    logger.warning(f"MPD artwork exceeded size limit ({self._MAX_MPD_ARTWORK_BYTES} bytes)")
                    return ""

                image_data += remaining[:bin_size]
                offset += bin_size

                # Read trailing '\nOK\n'
                trail = remaining[bin_size:]
                while b"OK\n" not in trail:
                    chunk = sock.recv(1024)
                    if not chunk:
                        return ""  # connection lost
                    trail += chunk

            if len(image_data) > 0:
                ext = self._image_extension(image_data)
                local_path = self.output_file.parent / f"artwork_{art_hash}{ext}"
                # Atomic write: temp file + rename to prevent partial reads
                tmp_path = local_path.parent / (local_path.name + ".tmp")
                with open(tmp_path, 'wb') as f:
                    f.write(image_data)
                tmp_path.rename(local_path)
                logger.info(f"Got MPD artwork ({len(image_data)} bytes) for {file_path}")
                return f"/artwork_{art_hash}{ext}"

            return ""

        except (socket.error, socket.timeout, OSError) as e:
            logger.warning(f"MPD readpicture network/IO failed: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error in MPD readpicture: {e}")
            return ""
        finally:
            sock.close()

    def send_rpc_request(self, sock: socket.socket, method: str, params: dict | None = None) -> dict | None:
        """Send JSON-RPC request and return matching response.

        Uses a persistent buffer to handle unsolicited Snapcast notifications
        (messages without "id") that arrive on the persistent connection.
        """
        request = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        try:
            sock.sendall((json.dumps(request) + "\r\n").encode())
        except (OSError, socket.error) as e:
            logger.warning(f"Failed to send RPC request: {e}")
            return None

        while True:
            # Process complete messages already in the buffer
            while b"\r\n" in self._snap_buffer:
                line, self._snap_buffer = self._snap_buffer.split(b"\r\n", 1)
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode('utf-8', errors='replace'))
                except json.JSONDecodeError as e:
                    logger.warning(f"Malformed JSON from Snapserver: {line[:100]!r}: {e}")
                    continue
                if "id" in msg:
                    self._last_snap_response = time.monotonic()
                    return msg  # Our response
                # else: unsolicited notification — discard

            # Need more data from the socket
            try:
                chunk = sock.recv(8192)
                if not chunk:
                    return None  # Connection closed
                self._snap_buffer += chunk
            except socket.timeout:
                logger.warning("Snapserver socket timeout - connection stale")
                return None
            except (OSError, socket.error) as e:
                logger.warning(f"Snapserver socket error: {e}")
                return None

    def get_metadata_from_snapserver(self) -> dict[str, Any]:
        """Get metadata from Snapserver JSON-RPC for our client's stream.

        Uses a persistent socket. On failure, reconnects once before giving up.
        Forces reconnect if no successful response in _snap_stale_threshold seconds.
        Thread-safe: uses _snap_lock to prevent concurrent socket access.
        """
        with self._snap_lock:
            # Check for stale connection and force reconnect
            if (self._snap_sock is not None and
                    self._last_snap_response > 0 and
                    time.monotonic() - self._last_snap_response > self._snap_stale_threshold):
                logger.warning(f"Snapserver connection stale ({self._snap_stale_threshold}s), reconnecting")
                self._close_snap_socket()

            sock = self._get_snap_socket()
            if not sock:
                return {"playing": False}

            try:
                status = self.send_rpc_request(sock, "Server.GetStatus")
                if not status:
                    # Connection dead — retry once
                    self._close_snap_socket()
                    sock = self._get_snap_socket()
                    if not sock:
                        return {"playing": False}
                    status = self.send_rpc_request(sock, "Server.GetStatus")
                if not status:
                    self._close_snap_socket()
                    return {"playing": False}

                # Find our client and its stream
                server = status.get("result", {}).get("server", {})
                client_stream_id, volume_info = self._find_client_stream(server)

                if not client_stream_id:
                    logger.warning(f"Client {self.client_id} not found in server status")
                    return {"playing": False}

                # Find metadata for this stream
                for stream in server.get("streams", []):
                    if stream.get("id") == client_stream_id:
                        props = stream.get("properties", {})
                        meta = props.get("metadata", {})

                        # Handle artist which can be a string or list
                        artist = meta.get("artist", "")
                        if isinstance(artist, list):
                            artist = ", ".join(artist)

                        # Get artwork URL - prefer artUrl, fall back to artData
                        artwork = meta.get("artUrl", "")
                        # Fix internal snapcast URLs to use actual server IP
                        if artwork and "://snapcast:" in artwork:
                            artwork = artwork.replace("://snapcast:", f"://{self.snapserver_host}:")

                        # Extract audio format from stream URI query params
                        uri_query = stream.get("uri", {}).get("query", {})
                        snap_codec = uri_query.get("codec", "")
                        snap_fmt = uri_query.get("sampleformat", "")
                        sample_rate, bit_depth = self._parse_audio_format(snap_fmt)

                        # Extract position/duration from stream properties (MPRIS)
                        position = props.get("position", 0)
                        duration = meta.get("duration", 0)

                        return {
                            "playing": stream.get("status") == "playing",
                            "title": meta.get("title", ""),
                            "artist": artist,
                            "album": meta.get("album", ""),
                            "artwork": artwork,
                            "stream_id": client_stream_id,
                            "source": stream.get("id", ""),
                            "volume": volume_info.get("percent", 100),
                            "muted": volume_info.get("muted", False),
                            "codec": snap_codec.upper() if snap_codec else "",
                            "sample_rate": sample_rate,
                            "bit_depth": bit_depth,
                            "elapsed": int(position),
                            "duration": int(duration),
                        }

                return {"playing": False}

            except Exception as e:
                logger.error(f"Error getting Snapserver metadata: {e}")
                self._close_snap_socket()
                return {"playing": False}

    def _find_client_stream(self, server: dict) -> tuple[str | None, dict]:
        """Find the stream ID and volume info for our client.

        Returns (stream_id, volume_info) where volume_info has
        'percent' (0-100) and 'muted' (bool) keys.
        """
        for group in server.get("groups", []):
            for client in group.get("clients", []):
                if self._is_matching_client(client):
                    stream_id = group.get("stream_id")
                    volume = client.get("config", {}).get("volume", {"percent": 100, "muted": False})
                    logger.debug(f"Found client {self.client_id} on stream {stream_id}")
                    return stream_id, volume
        return None, {}

    def _is_matching_client(self, client: dict) -> bool:
        """Check if client matches our client ID"""
        client_identifiers = [
            client.get("host", {}).get("name", ""),
            client.get("config", {}).get("name", ""),
            client.get("id", "")
        ]

        return any(
            self.client_id == identifier or
            self.client_id in identifier or
            identifier in self.client_id
            for identifier in client_identifiers
            if identifier
        )

    def set_client_volume(self, volume: int) -> bool:
        """Set volume for this client (0-100). Thread-safe."""
        with self._snap_lock:
            # Check for stale connection and force reconnect
            if (self._snap_sock is not None and
                    self._last_snap_response > 0 and
                    time.monotonic() - self._last_snap_response > self._snap_stale_threshold):
                logger.debug("Stale connection detected in set_client_volume, reconnecting")
                self._close_snap_socket()

            sock = self._get_snap_socket()
            if not sock:
                return False

            # Get client ID from snapserver
            status = self.send_rpc_request(sock, "Server.GetStatus")
            if not status:
                return False

            server = status.get("result", {}).get("server", {})
            snap_client_id = None
            for group in server.get("groups", []):
                for client in group.get("clients", []):
                    if self._is_matching_client(client):
                        snap_client_id = client.get("id")
                        break
                if snap_client_id:
                    break

            if not snap_client_id:
                logger.warning(f"Client {self.client_id} not found for volume control")
                return False

            volume = max(0, min(100, volume))
            params = {
                "id": snap_client_id,
                "volume": {"percent": volume, "muted": False}
            }

            response = self.send_rpc_request(sock, "Client.SetVolume", params)
            if response and "result" in response:
                logger.info(f"Set client volume to {volume}%")
                return True
            return False

    def adjust_volume(self, delta: int) -> bool:
        """Adjust volume by delta (-100 to +100)."""
        current = self.current_metadata.get("volume", 50)
        new_volume = max(0, min(100, current + delta))
        return self.set_client_volume(new_volume)

    def toggle_playback(self) -> bool:
        """Toggle play/pause on the stream via MPD."""
        # Snapcast doesn't have native play/pause control
        # Try MPD if available (most common source)
        sock = self._create_socket_connection(self.mpd_host, self.mpd_port, log_errors=False)
        if not sock:
            logger.debug("MPD not available for playback toggle")
            return False

        try:
            # Read MPD greeting
            if not self._read_mpd_greeting(sock):
                return False

            # Get current status
            sock.sendall(b"status\n")
            status = self._parse_mpd_response(self._read_mpd_response(sock))

            state = status.get('state', 'stop')
            if state == 'play':
                sock.sendall(b"pause 1\n")
                logger.info("MPD: paused")
            else:
                sock.sendall(b"play\n")
                logger.info("MPD: playing")

            self._read_mpd_response(sock)
            return True

        except Exception as e:
            logger.warning(f"MPD playback toggle failed: {e}")
            return False
        finally:
            sock.close()

    async def handle_control_command(self, message: str) -> None:
        """Handle control commands from display clients."""
        try:
            cmd = json.loads(message)
            cmd_type = cmd.get("cmd")
            logger.info(f"Received control command: {cmd_type} - {cmd}")

            if cmd_type == "toggle_play":
                await asyncio.get_event_loop().run_in_executor(
                    None, self.toggle_playback
                )
            elif cmd_type == "volume":
                delta = cmd.get("delta", 0)
                if delta:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.adjust_volume, delta
                    )
            elif cmd_type == "seek":
                # Seek not supported by Snapcast for most stream types
                logger.debug(f"Seek command ignored: {cmd.get('delta')}")
            else:
                logger.debug(f"Unknown control command: {cmd_type}")
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid control command JSON: {e}")
        except (socket.error, OSError) as e:
            logger.warning(f"Control command network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected control command error: {e}")

    def _make_api_request(self, url: str, timeout: int = 5) -> dict | None:
        """Make an API request and return JSON response"""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            logger.debug(f"API request failed for {url}: {e}")
            return None

    def fetch_radio_logo(self, station_name: str, stream_url: str) -> str:
        """Fetch radio station logo from Radio-Browser API.

        Searches by station name, prefers entries with a favicon and
        matching stream URL domain.
        """
        if not station_name or len(station_name) > 200:
            return ""
        self._trim_cache(self.artwork_cache, self._CACHE_MAX_ARTWORK)

        cache_key = f"radio|{station_name}"
        if cache_key in self.artwork_cache:
            return self.artwork_cache[cache_key]

        # Clean station name: strip bitrate/codec suffixes like "(320k aac)"
        clean_name = station_name
        for sep in ("(", "[", "-"):
            if sep in clean_name:
                candidate = clean_name.split(sep)[0].strip()
                if len(candidate) >= 3:
                    clean_name = candidate

        query = urllib.parse.quote(clean_name)
        url = f"https://de1.api.radio-browser.info/json/stations/byname/{query}?limit=20&order=votes&reverse=true"
        data = self._make_api_request(url)
        if not data or not isinstance(data, list):
            self.artwork_cache[cache_key] = ""
            return ""

        # Extract domain from stream URL for matching
        stream_domain = ""
        if stream_url:
            try:
                stream_domain = urllib.parse.urlparse(stream_url).netloc.split(":")[0]
                # Strip subdomain (stream-uk1.radioparadise.com -> radioparadise.com)
                parts = stream_domain.split(".")
                if len(parts) > 2:
                    stream_domain = ".".join(parts[-2:])
            except Exception:
                pass

        # Score entries: prefer favicon + URL domain match + votes
        best_url = ""
        best_score = -1
        for entry in data:
            favicon = entry.get("favicon", "")
            if not favicon:
                continue
            score = entry.get("votes", 0)
            # Bonus for matching stream domain
            entry_url = entry.get("url_resolved", "") or entry.get("url", "")
            if stream_domain and stream_domain in entry_url:
                score += 10000
            if score > best_score:
                best_score = score
                best_url = favicon

        if best_url:
            logger.info(f"Found radio logo for '{station_name}': {best_url}")
        self.artwork_cache[cache_key] = best_url
        return best_url

    def fetch_musicbrainz_artwork(self, artist: str, album: str) -> str:
        """Fetch album artwork from MusicBrainz/Cover Art Archive"""
        query = urllib.parse.quote(f'artist:"{artist}" AND release:"{album}"')
        url = f"https://musicbrainz.org/ws/2/release/?query={query}&fmt=json&limit=1"

        data = self._make_api_request(url)
        if not data:
            return ""

        releases = data.get('releases', [])
        if releases and (mbid := releases[0].get('id')):
            return f"https://coverartarchive.org/release/{mbid}/front-500"

        return ""

    def _get_wikidata_id_from_relations(self, relations: list) -> str | None:
        """Extract Wikidata ID from MusicBrainz relations"""
        for rel in relations:
            if rel.get('type') == 'wikidata':
                wikidata_url = rel.get('url', {}).get('resource', '')
                if wikidata_url:
                    return wikidata_url.split('/')[-1]
        return None

    def _build_wikimedia_image_url(self, image_name: str) -> str:
        """Build Wikimedia Commons image URL with proper formatting"""
        image_name = image_name.replace(' ', '_')
        md5 = hashlib.md5(image_name.encode()).hexdigest()
        base_url = f"https://upload.wikimedia.org/wikipedia/commons/thumb/{md5[0]}/{md5[0:2]}/{urllib.parse.quote(image_name)}/500px-{urllib.parse.quote(image_name)}"

        if image_name.lower().endswith('.svg'):
            base_url += '.png'

        return base_url

    def fetch_artist_image(self, artist: str) -> str:
        """Fetch artist image from MusicBrainz -> Wikidata -> Wikimedia Commons"""
        self._trim_cache(self.artist_image_cache, self._CACHE_MAX_ARTIST)
        if not artist or artist in self.artist_image_cache:
            return self.artist_image_cache.get(artist, "")

        # Step 1: Get artist MBID from MusicBrainz
        query = urllib.parse.quote(f'artist:"{artist}"')
        url = f"https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json&limit=1"

        data = self._make_api_request(url)
        if not data or not (artists := data.get('artists', [])):
            self.artist_image_cache[artist] = ""
            return ""

        artist_mbid = artists[0].get('id')
        if not artist_mbid:
            self.artist_image_cache[artist] = ""
            return ""

        time.sleep(1.1)  # MusicBrainz rate limit

        # Step 2: Get Wikidata ID from artist relations
        url = f"https://musicbrainz.org/ws/2/artist/{artist_mbid}?inc=url-rels&fmt=json"
        data = self._make_api_request(url)
        if not data:
            self.artist_image_cache[artist] = ""
            return ""

        wikidata_id = self._get_wikidata_id_from_relations(data.get('relations', []))
        if not wikidata_id:
            self.artist_image_cache[artist] = ""
            return ""

        time.sleep(1.1)

        # Step 3: Get image from Wikidata
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
        data = self._make_api_request(url)
        if not data:
            self.artist_image_cache[artist] = ""
            return ""

        entity = data.get('entities', {}).get(wikidata_id, {})
        image_claims = entity.get('claims', {}).get('P18', [])

        if image_claims and (image_name := image_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', '')):
            image_url = self._build_wikimedia_image_url(image_name)
            self.artist_image_cache[artist] = image_url
            logger.info(f"Found artist image for {artist}")
            return image_url

        self.artist_image_cache[artist] = ""
        return ""

    def fetch_album_artwork(self, artist: str, album: str) -> str:
        """Fetch album artwork URL from external APIs"""
        if not artist or not album:
            return ""
        self._trim_cache(self.artwork_cache, self._CACHE_MAX_ARTWORK)

        cache_key = f"{artist}|{album}"
        if cache_key in self.artwork_cache:
            return self.artwork_cache[cache_key]

        # Try iTunes Search API first
        artwork_url = self._fetch_itunes_artwork(artist, album)
        if artwork_url:
            self.artwork_cache[cache_key] = artwork_url
            logger.info(f"Found iTunes artwork for {artist} - {album}")
            return artwork_url

        # Fallback to MusicBrainz
        artwork_url = self.fetch_musicbrainz_artwork(artist, album)
        if artwork_url:
            self.artwork_cache[cache_key] = artwork_url
            logger.info(f"Found MusicBrainz artwork for {artist} - {album}")
            return artwork_url

        self.artwork_cache[cache_key] = ""
        return ""

    def _fetch_itunes_artwork(self, artist: str, album: str) -> str:
        """Fetch artwork from iTunes Search API"""
        query = urllib.parse.quote(f"{artist} {album}")
        url = f"https://itunes.apple.com/search?term={query}&media=music&entity=album&limit=10"

        data = self._make_api_request(url)
        if not data or data.get('resultCount', 0) == 0:
            return ""

        # Find the result whose album name matches the requested album.
        # Accept exact match or edition variants like "Ten (Remastered)".
        album_lower = album.lower().strip()
        artist_lower = artist.lower().strip()
        for result in data['results']:
            name = result.get('collectionName', '').lower().strip()
            result_artist = result.get('artistName', '').lower().strip()
            # Album must match exactly or start with the album name (edition suffix)
            album_ok = name == album_lower or name.startswith(album_lower + " (")
            # Artist must match exactly (case-insensitive)
            artist_ok = artist_lower == result_artist
            if album_ok and artist_ok:
                artwork_url = result.get('artworkUrl100', '')
                return artwork_url.replace('100x100', '600x600') if artwork_url else ""

        # No match — skip iTunes, let MusicBrainz handle it
        return ""


    _MAX_ARTWORK_BYTES = 10_000_000  # 10 MB

    def download_artwork(self, url: str) -> str:
        """Download artwork and save locally, return local path"""
        if not url:
            return ""

        # TTL-based retry: transient errors don't permanently blacklist URLs
        if url in self._failed_downloads:
            if time.monotonic() - self._failed_downloads[url] < self._FAILED_DOWNLOAD_TTL:
                return ""
            del self._failed_downloads[url]
        if len(self._failed_downloads) > self._CACHE_MAX_FAILED:
            now = time.monotonic()
            self._failed_downloads = {
                k: v for k, v in self._failed_downloads.items()
                if now - v < self._FAILED_DOWNLOAD_TTL
            }

        # Validate URL scheme to prevent SSRF (file://, ftp://, etc.)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            logger.warning(f"Rejected artwork URL with scheme: {parsed.scheme}")
            self._failed_downloads[url] = time.monotonic()
            return ""

        # Block private/loopback IPs to prevent SSRF to internal services.
        # Exception: allow Snapserver host (trusted internal service for artwork).
        # Note: TOCTOU gap exists between DNS check and urlopen; all external
        # artwork URLs use HTTPS where TLS cert validation prevents rebinding.
        try:
            is_snapserver = parsed.hostname == self.snapserver_host
            blocked_addr = None

            for family, _, _, _, sockaddr in socket.getaddrinfo(
                parsed.hostname or "", None, socket.AF_UNSPEC
            ):
                addr = sockaddr[0]
                ip = ipaddress.ip_address(addr)
                if (ip.is_private or ip.is_loopback or ip.is_link_local or
                        ip.is_multicast or ip.is_reserved):
                    if is_snapserver:
                        logger.debug(f"Allowing artwork from Snapserver: {addr}")
                    else:
                        blocked_addr = addr
                        break

            if blocked_addr:
                logger.warning(f"Blocked artwork download to restricted IP: {blocked_addr}")
                self._failed_downloads[url] = time.monotonic()
                return ""
        except (socket.gaierror, ValueError, OSError) as e:
            logger.warning(f"Cannot resolve artwork host {parsed.hostname}: {e}")
            self._failed_downloads[url] = time.monotonic()
            return ""

        try:
            # Generate filename from URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()
            local_path = self.output_file.parent / f"artwork_{url_hash}.jpg"

            # Skip if already downloaded and has content
            if local_path.exists() and local_path.stat().st_size > 0:
                return f"/artwork_{url_hash}.jpg"

            # Download the image with chunked reading, size limit, and total timeout
            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = b""
                dl_start = time.monotonic()
                while len(data) < self._MAX_ARTWORK_BYTES:
                    if time.monotonic() - dl_start > 15:
                        logger.warning("Artwork download total timeout (15s)")
                        self._failed_downloads[url] = time.monotonic()
                        return ""
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    data += chunk

                if len(data) >= self._MAX_ARTWORK_BYTES:
                    logger.warning(f"Artwork exceeded size limit ({self._MAX_ARTWORK_BYTES} bytes)")
                    self._failed_downloads[url] = time.monotonic()
                    return ""

                if len(data) > 0:
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    logger.info(f"Downloaded artwork ({len(data)} bytes) to {local_path}")
                    return f"/artwork_{url_hash}.jpg"
                else:
                    logger.warning("Downloaded empty artwork")
                    self._failed_downloads[url] = time.monotonic()
                    return ""

        except Exception as e:
            logger.error(f"Failed to download artwork: {e}")
            self._failed_downloads[url] = time.monotonic()
            # Remove incomplete file
            try:
                local_path.unlink(missing_ok=True)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up incomplete artwork file {local_path}: {cleanup_error}")
            return ""  # Don't fall back to broken URL

    # Fields that fluctuate and should not trigger a "metadata changed" event
    _VOLATILE_FIELDS = {"bitrate", "artwork", "artist_image", "elapsed"}

    def _metadata_changed(self, new: dict, old: dict) -> bool:
        """Check if metadata changed, ignoring volatile fields like bitrate."""
        if not old:
            return True
        for key in set(new.keys()) | set(old.keys()):
            if key in self._VOLATILE_FIELDS:
                continue
            if new.get(key) != old.get(key):
                return True
        return False

    # Internal fields not written to output JSON
    _INTERNAL_FIELDS = {"file", "station_name"}

    def _output_metadata(self, metadata: dict) -> dict:
        """Strip internal fields before writing to JSON."""
        return {k: v for k, v in metadata.items() if k not in self._INTERNAL_FIELDS}

    def _write_metadata_quiet(self, metadata: dict) -> None:
        """Write metadata to JSON without logging (for volatile-only updates)."""
        try:
            with open(self.output_file, 'w') as f:
                json.dump(self._output_metadata(metadata), f, indent=2)
        except Exception as e:
            logger.debug(f"Quiet write failed: {e}")

    def write_metadata(self, metadata: dict) -> None:
        """Write metadata to JSON file"""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_file, 'w') as f:
                json.dump(self._output_metadata(metadata), f, indent=2)

            title = metadata.get('title', '')
            artist = metadata.get('artist', '')
            if title or artist:
                logger.info(f"Updated: {title or 'N/A'} - {artist or 'N/A'} [{metadata.get('source', 'N/A')}]")
            else:
                logger.debug(f"Updated metadata (no track info) [{metadata.get('source', 'N/A')}]")

        except Exception as e:
            logger.error(f"Failed to write metadata: {e}")

    async def run_async(self) -> None:
        """Async main loop with WebSocket broadcast."""
        global _service_instance
        _service_instance = self

        logger.info(f"Starting Snapcast Metadata Service (async)")
        logger.info(f"  Snapserver: {self.snapserver_host}:{self.snapserver_port}")
        logger.info(f"  MPD fallback: {self.mpd_host}:{self.mpd_port}")
        logger.info(f"  Client ID: {self.client_id}")
        logger.info(f"  WebSocket port: {WS_PORT}")

        # Start WebSocket server
        ws_server = await websockets.serve(ws_handler, "0.0.0.0", WS_PORT)
        logger.info(f"WebSocket server started on port {WS_PORT} (bidirectional control enabled)")

        # Run metadata polling in executor (blocking I/O)
        loop = asyncio.get_event_loop()
        consecutive_errors = 0

        while True:
            try:
                # Run blocking metadata fetch in thread pool
                metadata = await loop.run_in_executor(
                    None, self.get_metadata_from_snapserver
                )

                # If stream is MPD, always query MPD for richer metadata
                if metadata.get('source') == 'MPD':
                    mpd_meta = await loop.run_in_executor(
                        None, self.get_mpd_metadata
                    )
                    if mpd_meta.get('playing'):
                        mpd_meta["volume"] = metadata.get("volume", 100)
                        mpd_meta["muted"] = metadata.get("muted", False)
                        if not mpd_meta.get("title") and mpd_meta.get("station_name"):
                            mpd_meta["title"] = mpd_meta["station_name"]
                        metadata = mpd_meta
                        logger.debug("Using MPD metadata")

                # Fetch artwork (blocking calls in executor)
                if metadata.get('playing'):
                    artwork_url = metadata.get('artwork', '')
                    is_radio = metadata.get('codec') == 'RADIO'

                    if not artwork_url and metadata.get('source') == 'MPD' and not is_radio:
                        mpd_art = await loop.run_in_executor(
                            None, self.fetch_mpd_artwork, metadata.get('file', '')
                        )
                        if mpd_art:
                            metadata['artwork'] = mpd_art
                            artwork_url = None

                    if not artwork_url and not metadata.get('artwork'):
                        if is_radio and metadata.get('station_name'):
                            artwork_url = await loop.run_in_executor(
                                None, self.fetch_radio_logo,
                                metadata['station_name'], metadata.get('file', '')
                            )
                        elif metadata.get('artist') and metadata.get('album'):
                            artwork_url = await loop.run_in_executor(
                                None, self.fetch_album_artwork,
                                metadata['artist'], metadata['album']
                            )

                    if artwork_url:
                        local_art = await loop.run_in_executor(
                            None, self.download_artwork, artwork_url
                        )
                        metadata['artwork'] = local_art

                    if not metadata.get('artwork') and is_radio and metadata.get('station_name'):
                        logo_url = await loop.run_in_executor(
                            None, self.fetch_radio_logo,
                            metadata['station_name'], metadata.get('file', '')
                        )
                        if logo_url:
                            local_art = await loop.run_in_executor(
                                None, self.download_artwork, logo_url
                            )
                            metadata['artwork'] = local_art

                    if not metadata.get('artwork') and is_radio:
                        metadata['artwork'] = '/default-radio.png'

                    if not is_radio and metadata.get('artist'):
                        artist_image = await loop.run_in_executor(
                            None, self.fetch_artist_image, metadata['artist']
                        )
                        metadata['artist_image'] = artist_image

                # Check for changes and broadcast
                if self._metadata_changed(metadata, self.current_metadata):
                    new_title = metadata.get("title", "")
                    new_artist = metadata.get("artist", "")
                    old_title = self.current_metadata.get("title", "")
                    old_artist = self.current_metadata.get("artist", "")
                    if (new_title or new_artist) and (new_title, new_artist) != (old_title, old_artist):
                        self._failed_downloads.clear()
                    self.current_metadata = metadata
                    self.write_metadata(metadata)
                    # Broadcast to WebSocket clients
                    await broadcast_metadata(metadata)
                else:
                    volatile_changed = any(
                        metadata.get(f) != self.current_metadata.get(f)
                        for f in self._VOLATILE_FIELDS
                    )
                    if volatile_changed:
                        self.current_metadata = metadata
                        self._write_metadata_quiet(metadata)
                        # Broadcast volatile updates too (volume changes)
                        await broadcast_metadata(metadata)

                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= _MAIN_LOOP_MAX_ERRORS:
                    logger.critical(
                        f"Main loop: {consecutive_errors} consecutive errors, exiting"
                    )
                    raise SystemExit(1)
                logger.error(
                    f"Main loop error ({consecutive_errors}/{_MAIN_LOOP_MAX_ERRORS}): {e}"
                )

            await asyncio.sleep(2)


async def ws_handler(websocket, path=None):
    """Handle WebSocket connections and control commands."""
    ws_clients.add(websocket)
    client_addr = websocket.remote_address
    logger.info(f"WebSocket client connected: {client_addr}")

    try:
        # Keep connection alive and process incoming control commands
        async for message in websocket:
            if _service_instance and message:
                await _service_instance.handle_control_command(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected: {client_addr}")


async def broadcast_metadata(metadata: dict) -> None:
    """Broadcast metadata to all connected WebSocket clients."""
    if not ws_clients:
        return

    # Strip internal fields (reuse class constant)
    output = {k: v for k, v in metadata.items()
              if k not in SnapcastMetadataService._INTERNAL_FIELDS}
    message = json.dumps(output)

    # Send to all clients concurrently (single copy to avoid mismatch)
    clients_snapshot = list(ws_clients)
    tasks = [client.send(message) for client in clients_snapshot]
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for client, result in zip(clients_snapshot, results):
            if isinstance(result, Exception):
                ws_clients.discard(client)


if __name__ == "__main__":
    # Clear stale metadata from previous session to avoid showing wrong cover on startup
    stale_metadata = Path("/app/public/metadata.json")
    if stale_metadata.exists():
        try:
            stale_metadata.unlink()
            logger.info("Cleared stale metadata.json from previous session")
        except OSError as e:
            logger.warning(f"Could not clear stale metadata: {e}")

    snapserver_host = os.environ.get("SNAPSERVER_HOST", "")
    snapserver_port = int(os.environ.get("SNAPSERVER_PORT", "1705"))

    if not snapserver_host:
        logger.info("SNAPSERVER_HOST not set, discovering via mDNS...")
        while True:
            discovered = discover_snapserver()
            if discovered:
                snapserver_host, snapserver_port = discovered
                break
            logger.warning("Snapserver not found via mDNS, retrying in 10s...")
            time.sleep(10)

    client_id = os.environ.get("CLIENT_ID")
    if not client_id:
        logger.error("CLIENT_ID environment variable is required")
        raise SystemExit(1)

    service = SnapcastMetadataService(snapserver_host, snapserver_port, client_id)

    # Run async version with WebSocket server
    asyncio.run(service.run_async())
