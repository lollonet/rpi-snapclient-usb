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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnapcastMetadataService:
    def __init__(self, snapserver_host: str, snapserver_port: int, client_id: str):
        self.snapserver_host = snapserver_host
        self.snapserver_port = snapserver_port
        self.client_id = client_id
        self.output_file = Path("/app/public/metadata.json")
        self.current_metadata: dict[str, Any] = {}
        self.artwork_cache: dict[str, str] = {}
        self.artist_image_cache: dict[str, str] = {}
        self.user_agent = "SnapcastMetadataService/1.0 (https://github.com/lollonet/rpi-snapclient-usb)"

    def connect_to_snapserver(self) -> socket.socket | None:
        """Connect to Snapserver JSON-RPC interface"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.snapserver_host, self.snapserver_port))
            return sock
        except Exception as e:
            logger.error(f"Failed to connect to Snapserver: {e}")
            return None

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
            client_stream_id = None

            for group in server.get("groups", []):
                for client in group.get("clients", []):
                    # Match by client ID or hostname
                    client_host_name = client.get("host", {}).get("name", "")
                    client_config_name = client.get("config", {}).get("name", "")
                    client_id_value = client.get("id", "")

                    if (self.client_id in [client_host_name, client_config_name, client_id_value] or
                        client_host_name in self.client_id or
                        self.client_id in client_host_name):
                        client_stream_id = group.get("stream_id")
                        logger.debug(f"Found client {self.client_id} on stream {client_stream_id}")
                        break
                if client_stream_id:
                    break

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

                    return {
                        "playing": stream.get("status") == "playing",
                        "title": meta.get("title", ""),
                        "artist": artist,
                        "album": meta.get("album", ""),
                        "artwork": artwork,
                        "stream_id": client_stream_id,
                        "source": stream.get("id", "")
                    }

            return {"playing": False}

        except Exception as e:
            logger.error(f"Error getting Snapserver metadata: {e}")
            return {"playing": False}
        finally:
            sock.close()

    def fetch_musicbrainz_artwork(self, artist: str, album: str) -> str:
        """Fetch album artwork from MusicBrainz/Cover Art Archive"""
        try:
            query = urllib.parse.quote(f'artist:"{artist}" AND release:"{album}"')
            url = f"https://musicbrainz.org/ws/2/release/?query={query}&fmt=json&limit=1"

            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                releases = data.get('releases', [])
                if releases:
                    mbid = releases[0].get('id')
                    if mbid:
                        return f"https://coverartarchive.org/release/{mbid}/front-500"

        except Exception as e:
            logger.debug(f"MusicBrainz API failed: {e}")

        return ""

    def fetch_artist_image(self, artist: str) -> str:
        """Fetch artist image from MusicBrainz -> Wikidata -> Wikimedia Commons"""
        if not artist:
            return ""

        if artist in self.artist_image_cache:
            return self.artist_image_cache[artist]

        try:
            query = urllib.parse.quote(f'artist:"{artist}"')
            url = f"https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json&limit=1"

            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                artists = data.get('artists', [])
                if not artists:
                    self.artist_image_cache[artist] = ""
                    return ""

                artist_mbid = artists[0].get('id')
                if not artist_mbid:
                    self.artist_image_cache[artist] = ""
                    return ""

            time.sleep(1.1)  # MusicBrainz rate limit

            url = f"https://musicbrainz.org/ws/2/artist/{artist_mbid}?inc=url-rels&fmt=json"
            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                relations = data.get('relations', [])
                wikidata_id = None
                for rel in relations:
                    if rel.get('type') == 'wikidata':
                        wikidata_url = rel.get('url', {}).get('resource', '')
                        if wikidata_url:
                            wikidata_id = wikidata_url.split('/')[-1]
                            break

                if not wikidata_id:
                    self.artist_image_cache[artist] = ""
                    return ""

            time.sleep(1.1)
            url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                entity = data.get('entities', {}).get(wikidata_id, {})
                claims = entity.get('claims', {})

                image_claims = claims.get('P18', [])
                if image_claims:
                    image_name = image_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                    if image_name:
                        image_name = image_name.replace(' ', '_')
                        md5 = hashlib.md5(image_name.encode()).hexdigest()
                        image_url = f"https://upload.wikimedia.org/wikipedia/commons/thumb/{md5[0]}/{md5[0:2]}/{urllib.parse.quote(image_name)}/500px-{urllib.parse.quote(image_name)}"

                        if image_name.lower().endswith('.svg'):
                            image_url += '.png'

                        self.artist_image_cache[artist] = image_url
                        logger.info(f"Found artist image for {artist}")
                        return image_url

        except Exception as e:
            logger.debug(f"Artist image fetch failed: {e}")

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
        try:
            query = urllib.parse.quote(f"{artist} {album}")
            url = f"https://itunes.apple.com/search?term={query}&media=music&entity=album&limit=1"

            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                if data.get('resultCount', 0) > 0:
                    artwork_url = data['results'][0].get('artworkUrl100', '')
                    if artwork_url:
                        artwork_url = artwork_url.replace('100x100', '600x600')
                        self.artwork_cache[cache_key] = artwork_url
                        logger.info(f"Found iTunes artwork for {artist} - {album}")
                        return artwork_url

        except Exception as e:
            logger.debug(f"iTunes API failed: {e}")

        # Fallback to MusicBrainz
        try:
            artwork_url = self.fetch_musicbrainz_artwork(artist, album)
            if artwork_url:
                self.artwork_cache[cache_key] = artwork_url
                logger.info(f"Found MusicBrainz artwork for {artist} - {album}")
                return artwork_url
        except Exception as e:
            logger.debug(f"MusicBrainz artwork failed: {e}")

        self.artwork_cache[cache_key] = ""
        return ""

    def write_metadata(self, metadata: dict) -> None:
        """Write metadata to JSON file"""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Updated: {metadata.get('title', 'N/A')} - {metadata.get('artist', 'N/A')} [{metadata.get('source', 'N/A')}]")

        except Exception as e:
            logger.error(f"Failed to write metadata: {e}")

    def run(self) -> None:
        """Main service loop"""
        logger.info(f"Starting Snapcast Metadata Service")
        logger.info(f"  Snapserver: {self.snapserver_host}:{self.snapserver_port}")
        logger.info(f"  Client ID: {self.client_id}")

        while True:
            try:
                # Get metadata from Snapserver JSON-RPC
                metadata = self.get_metadata_from_snapserver()

                # Fetch album artwork if playing and not already provided
                if metadata.get('playing') and metadata.get('artist'):
                    if metadata.get('album') and not metadata.get('artwork'):
                        artwork_url = self.fetch_album_artwork(metadata['artist'], metadata['album'])
                        metadata['artwork'] = artwork_url

                    # Fetch artist image for fallback
                    artist_image = self.fetch_artist_image(metadata['artist'])
                    metadata['artist_image'] = artist_image

                if metadata != self.current_metadata:
                    self.current_metadata = metadata
                    self.write_metadata(metadata)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            time.sleep(2)


if __name__ == "__main__":
    snapserver_host = os.environ.get("SNAPSERVER_HOST", "")
    if not snapserver_host:
        logger.error("SNAPSERVER_HOST environment variable is required")
        raise SystemExit(1)

    snapserver_port = int(os.environ.get("SNAPSERVER_PORT", "1705"))

    client_id = os.environ.get("CLIENT_ID")
    if not client_id:
        logger.error("CLIENT_ID environment variable is required")
        raise SystemExit(1)

    service = SnapcastMetadataService(snapserver_host, snapserver_port, client_id)
    service.run()
