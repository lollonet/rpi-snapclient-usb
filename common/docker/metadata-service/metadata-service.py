#!/usr/bin/env python3
"""
Snapcast Metadata Service
Fetches metadata from Snapserver JSON-RPC and serves it as JSON for cover display.
Supports all sources: MPD, AirPlay, Spotify, etc.
"""

import json
import time
import socket
import os
import logging
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

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
                port = info.port or 1705
                logger.info(f"Discovered Snapserver via mDNS: {host}:{port}")
                result = (host, port)

    zc = Zeroconf()
    # Snapserver advertises _snapcast-ctrl._tcp for the control/RPC interface
    browser = ServiceBrowser(zc, "_snapcast-ctrl._tcp.local.", handlers=[on_service_state_change])

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
        self.mpd_host = snapserver_host  # MPD usually on same host as snapserver
        self.mpd_port = 6600
        self.output_file = Path("/app/public/metadata.json")
        self.current_metadata: dict[str, Any] = {}
        self.artwork_cache: dict[str, str] = {}
        self.artist_image_cache: dict[str, str] = {}
        self.user_agent = os.environ.get("USER_AGENT", "SnapcastMetadataService/1.0")
        self._mpd_was_connected = False
        self._failed_downloads: set[str] = set()

    def _create_socket_connection(self, host: str, port: int, timeout: int = 5, log_errors: bool = True) -> socket.socket | None:
        """Create a socket connection with standard settings"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            return sock
        except Exception as e:
            if log_errors:
                logger.error(f"Failed to connect to {host}:{port}: {e}")
            return None

    def connect_to_snapserver(self) -> socket.socket | None:
        """Connect to Snapserver JSON-RPC interface"""
        return self._create_socket_connection(self.snapserver_host, self.snapserver_port)

    def _read_mpd_response(self, sock: socket.socket) -> bytes:
        """Read MPD response until OK or ACK"""
        response = b""
        while True:
            chunk = sock.recv(1024)
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

    @staticmethod
    def _detect_codec(file_path: str, audio_fmt: str) -> str:
        """Detect codec from file extension or audio format string."""
        codec_map = {
            "flac": "FLAC", "wav": "WAV", "aiff": "AIFF", "aif": "AIFF",
            "mp3": "MP3", "ogg": "OGG", "opus": "OPUS",
            "m4a": "AAC", "aac": "AAC", "mp4": "AAC",
            "wma": "WMA", "ape": "APE", "wv": "WV", "dsf": "DSD", "dff": "DSD",
        }
        # For URLs, strip query params before extracting extension
        path = file_path.split("?")[0] if "?" in file_path else file_path
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in codec_map:
            return codec_map[ext]
        # For radio streams (URLs), codec is often unknown — return empty
        if file_path.startswith(("http://", "https://")):
            return "RADIO"
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
        except ValueError:
            sample_rate = 0
        bits_str = parts[1]
        if bits_str == "f":
            bit_depth = 32  # float = 32-bit
        else:
            try:
                bit_depth = int(bits_str)
            except ValueError:
                bit_depth = 0
        return sample_rate, bit_depth

    def _extract_radio_metadata(self, title: str, artist: str, song: dict[str, str]) -> tuple[str, str, str]:
        """Extract artist/title from radio stream format and determine album"""
        if not artist and ' - ' in title:
            parts = title.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else title

        album = song.get('Album', '') or song.get('Name', '')
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
            sock.recv(1024)

            # Get status
            sock.sendall(b"status\n")
            status = self._parse_mpd_response(self._read_mpd_response(sock))

            if status.get('state') != 'play':
                return {"playing": False, "source": "MPD"}

            # Get current song
            sock.sendall(b"currentsong\n")
            song = self._parse_mpd_response(self._read_mpd_response(sock))

            title, artist, album = self._extract_radio_metadata(
                song.get('Title', ''),
                song.get('Artist', ''),
                song
            )

            # Extract audio format info
            audio_fmt = status.get('audio', '') or song.get('Format', '')
            file_path = song.get('file', '')
            bitrate = int(status['bitrate']) if status.get('bitrate') else 0
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
            }

        except Exception as e:
            if self._mpd_was_connected:
                logger.warning(f"MPD query failed (host={self.mpd_host}, port={self.mpd_port}): {e}")
                self._mpd_was_connected = False
            return {"playing": False, "source": "MPD"}
        finally:
            sock.close()

    def send_rpc_request(self, sock: socket.socket, method: str, params: dict | None = None) -> dict | None:
        """Send JSON-RPC request and get response"""
        try:
            request = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {}
            }

            sock.sendall((json.dumps(request) + "\r\n").encode())

            response_bytes = b""
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                response_bytes += chunk
                if b"\r\n" in response_bytes:
                    break

            response = response_bytes.decode('utf-8', errors='replace').strip()
            return json.loads(response) if response else None
        except Exception as e:
            logger.error(f"RPC request failed: {e}")
            return None

    def get_metadata_from_snapserver(self) -> dict[str, Any]:
        """Get metadata from Snapserver JSON-RPC for our client's stream"""
        sock = self.connect_to_snapserver()
        if not sock:
            return {"playing": False}

        try:
            status = self.send_rpc_request(sock, "Server.GetStatus")
            if not status:
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
                    }

            return {"playing": False}

        except Exception as e:
            logger.error(f"Error getting Snapserver metadata: {e}")
            return {"playing": False}
        finally:
            sock.close()

    def _find_client_stream(self, server: dict) -> tuple[str | None, dict]:
        """Find the stream ID and volume info for our client.

        Returns (stream_id, volume_info) where volume_info has
        'percent' (0-100) and 'muted' (bool) keys.
        """
        for group in server.get("groups", []):
            for client in group.get("clients", []):
                if self._is_matching_client(client):
                    stream_id = group.get("stream_id")
                    volume = client.get("config", {}).get("volume", {})
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
        url = f"https://itunes.apple.com/search?term={query}&media=music&entity=album&limit=1"

        data = self._make_api_request(url)
        if not data or data.get('resultCount', 0) == 0:
            return ""

        artwork_url = data['results'][0].get('artworkUrl100', '')
        return artwork_url.replace('100x100', '600x600') if artwork_url else ""

    def download_artwork(self, url: str) -> str:
        """Download artwork and save locally, return local path"""
        if not url:
            return ""

        if url in self._failed_downloads:
            return ""

        try:
            # Generate filename from URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()
            local_path = self.output_file.parent / f"artwork_{url_hash}.jpg"

            # Skip if already downloaded and has content
            if local_path.exists() and local_path.stat().st_size > 0:
                return f"/artwork_{url_hash}.jpg"

            # Download the image with chunked reading for reliability
            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = b""
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    data += chunk

                if len(data) > 0:
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    logger.info(f"Downloaded artwork ({len(data)} bytes) to {local_path}")
                    return f"/artwork_{url_hash}.jpg"
                else:
                    logger.warning("Downloaded empty artwork")
                    self._failed_downloads.add(url)
                    return ""

        except Exception as e:
            logger.error(f"Failed to download artwork: {e}")
            self._failed_downloads.add(url)
            # Remove incomplete file
            try:
                local_path.unlink(missing_ok=True)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up incomplete artwork file {local_path}: {cleanup_error}")
            return ""  # Don't fall back to broken URL

    # Fields that fluctuate and should not trigger a "metadata changed" event
    _VOLATILE_FIELDS = {"bitrate"}

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
        except Exception:
            pass

    def write_metadata(self, metadata: dict) -> None:
        """Write metadata to JSON file"""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_file, 'w') as f:
                json.dump(self._output_metadata(metadata), f, indent=2)

            logger.info(f"Updated: {metadata.get('title', 'N/A')} - {metadata.get('artist', 'N/A')} [{metadata.get('source', 'N/A')}]")

        except Exception as e:
            logger.error(f"Failed to write metadata: {e}")

    def run(self) -> None:
        """Main service loop"""
        logger.info(f"Starting Snapcast Metadata Service")
        logger.info(f"  Snapserver: {self.snapserver_host}:{self.snapserver_port}")
        logger.info(f"  MPD fallback: {self.mpd_host}:{self.mpd_port}")
        logger.info(f"  Client ID: {self.client_id}")

        while True:
            try:
                # Get metadata from Snapserver JSON-RPC
                metadata = self.get_metadata_from_snapserver()

                # If stream is MPD and has no metadata, query MPD directly
                if (metadata.get('source') == 'MPD' and
                    metadata.get('playing') and
                    not metadata.get('title')):
                    mpd_meta = self.get_mpd_metadata()
                    if mpd_meta.get('title'):
                        # Preserve volume from Snapserver when using MPD metadata
                        mpd_meta["volume"] = metadata.get("volume", 100)
                        mpd_meta["muted"] = metadata.get("muted", False)
                        # MPD has better codec info (from file ext), keep it
                        metadata = mpd_meta
                        logger.debug("Using MPD metadata (Snapserver had none)")

                # Fetch and download artwork if playing
                if metadata.get('playing'):
                    artwork_url = metadata.get('artwork', '')
                    is_radio = metadata.get('codec') == 'RADIO'

                    if not artwork_url:
                        if is_radio and metadata.get('station_name'):
                            # Radio: fetch station logo
                            artwork_url = self.fetch_radio_logo(
                                metadata['station_name'],
                                metadata.get('file', ''),
                            )
                        elif metadata.get('artist') and metadata.get('album'):
                            # File/stream: fetch album artwork
                            artwork_url = self.fetch_album_artwork(
                                metadata['artist'], metadata['album']
                            )

                    # Download artwork locally for reliable serving
                    if artwork_url:
                        metadata['artwork'] = self.download_artwork(artwork_url)

                    # Fetch artist image for fallback (not for radio)
                    if not is_radio and metadata.get('artist'):
                        artist_image = self.fetch_artist_image(metadata['artist'])
                        metadata['artist_image'] = artist_image

                if self._metadata_changed(metadata, self.current_metadata):
                    self._failed_downloads.clear()
                    self.current_metadata = metadata
                    self.write_metadata(metadata)
                elif metadata.get("bitrate") != self.current_metadata.get("bitrate"):
                    # Bitrate changed but nothing else — update file silently
                    self.current_metadata = metadata
                    self._write_metadata_quiet(metadata)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            time.sleep(2)


if __name__ == "__main__":
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
    service.run()
