import os
import re
import json
import hashlib
import secrets
import urllib.parse
import base64
from typing import List, Optional

import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, CacheFileHandler

from models.track import Track

SCOPES = "playlist-read-private playlist-read-collaborative"
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTH_URL = "https://accounts.spotify.com/authorize"


class SpotifyService:
    def __init__(self, client_id: str = "", client_secret: str = "", redirect_uri: str = ""):
        self.client_id = client_id or os.environ.get("SPOTIFY_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8501")
        self._sp: Optional[spotipy.Spotify] = None
        self._user_sp: Optional[spotipy.Spotify] = None
        self._code_verifier = ""

    def _get_cache_dir(self) -> str:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _get_token_path(self) -> str:
        return os.path.join(self._get_cache_dir(), "spotify_pkce_token.json")

    def _get_verifier_path(self) -> str:
        return os.path.join(self._get_cache_dir(), "spotify_pkce_verifier.txt")

    def _get_client_credentials(self) -> spotipy.Spotify:
        if self._sp is None:
            if not self.client_id or not self.client_secret:
                raise ValueError(
                    "Spotify Client ID e Client Secret são necessários. "
                    "Configure as variáveis de ambiente SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET."
                )
            auth_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            self._sp = spotipy.Spotify(auth_manager=auth_manager)
        return self._sp

    @staticmethod
    def _generate_pkce_pair() -> tuple:
        verifier = secrets.token_urlsafe(64)[:128]
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def get_auth_url(self) -> str:
        verifier, challenge = self._generate_pkce_pair()

        verifier_path = self._get_verifier_path()
        with open(verifier_path, "w") as f:
            f.write(verifier)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    def handle_callback(self, code: str) -> bool:
        try:
            verifier_path = self._get_verifier_path()
            if not os.path.exists(verifier_path):
                return False
            with open(verifier_path, "r") as f:
                code_verifier = f.read().strip()

            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "code_verifier": code_verifier,
            }
            response = requests.post(TOKEN_URL, data=payload)

            if response.status_code != 200:
                error_log = os.path.join(self._get_cache_dir(), "spotify_error.log")
                with open(error_log, "w") as f:
                    f.write(f"Status: {response.status_code}\n")
                    f.write(f"Response: {response.text}\n")
                    f.write(f"Redirect URI: {self.redirect_uri}\n")
                return False

            token_data = response.json()
            token_data["expires_at"] = (
                __import__("time").time() + token_data.get("expires_in", 3600)
            )

            token_path = self._get_token_path()
            with open(token_path, "w") as f:
                json.dump(token_data, f)

            if os.path.exists(verifier_path):
                os.remove(verifier_path)

            self._create_sp_from_token(token_data)
            return True
        except Exception as e:
            error_log = os.path.join(self._get_cache_dir(), "spotify_error.log")
            with open(error_log, "w") as f:
                f.write(f"Exception: {str(e)}\n")
            return False

    def _create_sp_from_token(self, token_data: dict):
        auth_manager = spotipy.oauth2.SpotifyOAuth.__new__(spotipy.oauth2.SpotifyOAuth)
        auth_manager.access_token = token_data.get("access_token")
        auth_manager.refresh_token = token_data.get("refresh_token")
        auth_manager.token_info = token_data
        auth_manager.is_token_expired = lambda: __import__("time").time() > token_data.get("expires_at", 0)
        auth_manager.get_access_token = lambda: token_data.get("access_token")

        self._user_sp = spotipy.Spotify(auth_manager=auth_manager)
        self._user_sp._session.headers["Authorization"] = f"Bearer {token_data.get('access_token')}"

    def _load_cached_token(self) -> Optional[dict]:
        token_path = self._get_token_path()
        if not os.path.exists(token_path):
            return None
        try:
            with open(token_path, "r") as f:
                token_data = json.load(f)
            if __import__("time").time() > token_data.get("expires_at", 0):
                if token_data.get("refresh_token"):
                    return self._refresh_token(token_data)
                return None
            return token_data
        except Exception:
            return None

    def _refresh_token(self, token_data: dict) -> Optional[dict]:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "client_id": self.client_id,
        }
        response = requests.post(TOKEN_URL, data=payload)
        if response.status_code != 200:
            return None
        new_data = response.json()
        new_data["refresh_token"] = token_data["refresh_token"]
        new_data["expires_at"] = __import__("time").time() + new_data.get("expires_in", 3600)
        token_path = self._get_token_path()
        with open(token_path, "w") as f:
            json.dump(new_data, f)
        return new_data

    def is_user_authenticated(self) -> bool:
        token_data = self._load_cached_token()
        if token_data:
            self._create_sp_from_token(token_data)
            return True
        return False

    def logout(self):
        token_path = self._get_token_path()
        if os.path.exists(token_path):
            os.remove(token_path)
        self._user_sp = None

    @staticmethod
    def extract_playlist_id(url: str) -> Optional[str]:
        patterns = [
            r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)",
            r"spotify:playlist:([a-zA-Z0-9]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_playlist_info(self, playlist_url: str, use_user_auth: bool = False) -> dict:
        sp = self._get_user_client() if use_user_auth else self._get_client_credentials()
        playlist_id = self.extract_playlist_id(playlist_url)
        if not playlist_id:
            raise ValueError(
                f"URL inválida: {playlist_url}\n"
                "Formato esperado: https://open.spotify.com/playlist/..."
            )
        playlist = sp.playlist(playlist_id, fields="name,description,tracks.total")
        return {
            "id": playlist_id,
            "name": playlist["name"],
            "description": playlist.get("description", ""),
            "total_tracks": playlist["tracks"]["total"],
        }

    def get_playlist_tracks(self, playlist_url: str, playlist_name: str = "", use_user_auth: bool = False) -> List[Track]:
        sp = self._get_user_client() if use_user_auth else self._get_client_credentials()
        playlist_id = self.extract_playlist_id(playlist_url)
        if not playlist_id:
            raise ValueError(f"URL inválida: {playlist_url}")

        if not playlist_name:
            info = self.get_playlist_info(playlist_url, use_user_auth)
            playlist_name = info["name"]

        tracks = []
        results = sp.playlist_items(
            playlist_id,
            fields="items.track(name,artists,album,name,duration_ms,id,album.images),next",
            additional_types=("track",),
        )

        while results:
            for item in results["items"]:
                if item is None or item.get("track") is None:
                    continue
                track_data = item["track"]
                if track_data.get("is_local"):
                    continue

                artists = track_data.get("artists", [])
                artist_name = artists[0]["name"] if artists else "Unknown Artist"

                album_data = track_data.get("album", {})
                album_name = album_data.get("name", "")

                thumbnail = ""
                images = album_data.get("images", [])
                if images:
                    thumbnail = images[0].get("url", "")

                tracks.append(
                    Track(
                        artist=artist_name,
                        title=track_data.get("name", ""),
                        album=album_name,
                        platform="spotify",
                        duration_ms=track_data.get("duration_ms", 0),
                        spotify_id=track_data.get("id", ""),
                        source_playlist=playlist_name,
                        thumbnail=thumbnail,
                    )
                )

            if results.get("next"):
                results = sp.next(results)
            else:
                break

        return tracks

    def get_user_playlists(self) -> List[dict]:
        sp = self._get_user_client()
        playlists = []
        results = sp.current_user_playlists(limit=50)

        while results:
            for playlist in results["items"]:
                playlists.append({
                    "id": playlist["id"],
                    "name": playlist["name"],
                    "tracks_total": playlist["tracks"]["total"],
                    "owner": playlist["owner"]["display_name"],
                    "public": playlist["public"],
                    "url": playlist["external_urls"]["spotify"],
                })
            if results.get("next"):
                results = sp.next(results)
            else:
                break

        return playlists

    def _get_user_client(self) -> spotipy.Spotify:
        if self._user_sp is None:
            if not self.client_id:
                raise ValueError("Spotify Client ID é necessário.")
            token_data = self._load_cached_token()
            if token_data:
                self._create_sp_from_token(token_data)
        return self._user_sp

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)
