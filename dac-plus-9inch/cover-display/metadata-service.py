#!/usr/bin/env python3
"""
Snapcast Metadata Service
Fetches metadata from MPD server and serves it as JSON for cover display
"""

import json
import time
import socket
import os
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnapcastMetadataService:
    def __init__(self, snapserver_host: str, snapserver_port: int, client_id: str):
        self.snapserver_host = snapserver_host
        self.snapserver_port = snapserver_port
        self.client_id = client_id
        self.output_file = Path("/app/public/metadata.json")
        self.current_metadata = {}
        self.artwork_cache = {}  # Cache artwork URLs to avoid repeated API calls

    def connect_to_snapserver(self) -> Optional[socket.socket]:
        """Connect to Snapserver JSON-RPC interface"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.snapserver_host, self.snapserver_port))
            logger.info(f"Connected to Snapserver at {self.snapserver_host}:{self.snapserver_port}")
            return sock
        except Exception as e:
            logger.error(f"Failed to connect to Snapserver: {e}")
            return None

    def send_rpc_request(self, sock: socket.socket, method: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Send JSON-RPC request and get response"""
        try:
            request = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {}
            }

            sock.sendall((json.dumps(request) + "\r\n").encode())

            # Read response in chunks until we get the complete JSON (terminated by \r\n)
            response_bytes = b""
            while True:
                chunk = sock.recv(4096)
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

    def get_server_status(self, sock: socket.socket) -> Optional[Dict]:
        """Get full server status including all clients and streams"""
        return self.send_rpc_request(sock, "Server.GetStatus")

    def get_mpd_metadata(self) -> Dict[str, Any]:
        """Fetch current track metadata from MPD server"""
        try:
            # Connect to MPD
            mpd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            mpd_sock.settimeout(3)
            mpd_sock.connect((self.snapserver_host, 6600))

            # Read MPD greeting
            mpd_sock.recv(1024)

            # Send currentsong command
            mpd_sock.sendall(b"currentsong\n")

            # Read response
            response = b""
            while True:
                chunk = mpd_sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"OK\n" in response or b"ACK" in response:
                    break

            mpd_sock.close()

            # Parse MPD response
            metadata = {}
            lines = response.decode('utf-8', errors='replace').split('\n')

            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key == 'title':
                        metadata['title'] = value
                    elif key == 'artist':
                        metadata['artist'] = value
                    elif key == 'album':
                        metadata['album'] = value
                    elif key == 'file':
                        metadata['file'] = value

            # Check if playing
            mpd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            mpd_sock.settimeout(3)
            mpd_sock.connect((self.snapserver_host, 6600))
            mpd_sock.recv(1024)
            mpd_sock.sendall(b"status\n")

            response = b""
            while True:
                chunk = mpd_sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"OK\n" in response or b"ACK" in response:
                    break

            mpd_sock.close()

            playing = False
            for line in response.decode('utf-8', errors='replace').split('\n'):
                if line.startswith('state:'):
                    state = line.split(':', 1)[1].strip()
                    playing = state == 'play'
                    break

            return {
                "playing": playing,
                "title": metadata.get("title", ""),
                "artist": metadata.get("artist", ""),
                "album": metadata.get("album", ""),
                "artwork": "",
                "file": metadata.get("file", "")
            }

        except Exception as e:
            logger.error(f"Failed to get MPD metadata: {e}")
            return {"playing": False}

    def extract_metadata_for_client(self, status: Dict) -> Dict[str, Any]:
        """Extract metadata for our specific client"""
        try:
            # Find our client in the server status
            for group in status.get("result", {}).get("server", {}).get("groups", []):
                for client in group.get("clients", []):
                    if client.get("host", {}).get("name") == self.client_id:
                        # Get the stream this client is connected to
                        stream_id = group.get("stream_id")

                        # Find metadata for this stream
                        for stream in status.get("result", {}).get("server", {}).get("streams", []):
                            if stream.get("id") == stream_id:
                                metadata = stream.get("properties", {}).get("metadata", {})

                                return {
                                    "playing": stream.get("status") == "playing",
                                    "title": metadata.get("title", ""),
                                    "artist": metadata.get("artist", ""),
                                    "album": metadata.get("album", ""),
                                    "artwork": metadata.get("artUrl", ""),
                                    "stream_id": stream_id
                                }

            return {"playing": False}

        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {"playing": False}

    def fetch_album_artwork(self, artist: str, album: str) -> str:
        """Fetch album artwork URL from external API"""
        if not artist or not album:
            return ""

        # Check cache first
        cache_key = f"{artist}|{album}"
        if cache_key in self.artwork_cache:
            return self.artwork_cache[cache_key]

        try:
            # Try iTunes Search API first (no auth required)
            query = urllib.parse.quote(f"{artist} {album}")
            url = f"https://itunes.apple.com/search?term={query}&media=music&entity=album&limit=1"

            req = urllib.request.Request(url, headers={'User-Agent': 'SnapcastMetadataService/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                if data.get('resultCount', 0) > 0:
                    # Get the high-res artwork (replace 100x100 with 600x600)
                    artwork_url = data['results'][0].get('artworkUrl100', '')
                    if artwork_url:
                        artwork_url = artwork_url.replace('100x100', '600x600')
                        self.artwork_cache[cache_key] = artwork_url
                        logger.info(f"Found artwork for {artist} - {album}")
                        return artwork_url

        except Exception as e:
            logger.debug(f"iTunes API failed: {e}")

        # Cache empty result to avoid repeated failed lookups
        self.artwork_cache[cache_key] = ""
        return ""

    def write_metadata(self, metadata: Dict):
        """Write metadata to JSON file"""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Updated metadata: {metadata.get('title', 'No title')} - {metadata.get('artist', 'No artist')}")

        except Exception as e:
            logger.error(f"Failed to write metadata: {e}")

    def run(self):
        """Main service loop"""
        logger.info(f"Starting Snapcast Metadata Service (MPD polling mode)")

        while True:
            try:
                # Get metadata directly from MPD
                metadata = self.get_mpd_metadata()

                # Fetch album artwork if playing and we don't have it cached
                if metadata.get('playing') and metadata.get('artist') and metadata.get('album'):
                    if not metadata.get('artwork'):
                        artwork_url = self.fetch_album_artwork(metadata['artist'], metadata['album'])
                        metadata['artwork'] = artwork_url

                if metadata != self.current_metadata:
                    self.current_metadata = metadata
                    self.write_metadata(metadata)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            time.sleep(2)  # Poll every 2 seconds


if __name__ == "__main__":
    snapserver_host = os.environ.get("SNAPSERVER_HOST", "192.168.63.3")
    snapserver_port = int(os.environ.get("SNAPSERVER_PORT", "1705"))
    client_id = os.environ.get("CLIENT_ID", "snapclient-dac-9inch")

    service = SnapcastMetadataService(snapserver_host, snapserver_port, client_id)
    service.run()
