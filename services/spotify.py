import os
import re
import json
import hashlib
import secrets
import urllib.parse
from typing import List, Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth, CacheFileHandler

from models.track import Track

SCOPES = "playlist-read-private playlist-read-collaborative"


class SpotifyService:
    def __init__(self, client_id: str = "", client_secret: str = "", redirect_uri: str = "http://localhost:8501"):
        self.client_id = client_id or os.environ.get("SPOTIFY_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri
        self._sp: Optional[spotipy.Spotify] = None
        self._user_sp: Optional[spotipy.Spotify] = None

    def _get_cache_handler(self) -> CacheFileHandler:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "spotify_token")
        return CacheFileHandler(cache_path=cache_path)

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

    def _get_user_client(self) -> spotipy.Spotify:
        if self._user_sp is None:
            if not self.client_id or not self.client_secret:
                raise ValueError(
                    "Spotify Client ID e Client Secret são necessários."
                )
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=SCOPES,
                cache_handler=self._get_cache_handler(),
                open_browser=False,
            )
            self._user_sp = spotipy.Spotify(auth_manager=auth_manager)
        return self._user_sp

    def get_auth_url(self) -> str:
        auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=SCOPES,
            cache_handler=self._get_cache_handler(),
            open_browser=False,
        )
        return auth_manager.get_authorize_url()

    def handle_callback(self, code: str) -> bool:
        try:
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=SCOPES,
                cache_handler=self._get_cache_handler(),
                open_browser=False,
            )
            auth_manager.get_access_token(code, as_dict=False, check_cache=False)
            self._user_sp = spotipy.Spotify(auth_manager=auth_manager)
            return True
        except Exception:
            return False

    def is_user_authenticated(self) -> bool:
        try:
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=SCOPES,
                cache_handler=self._get_cache_handler(),
                open_browser=False,
            )
            token = auth_manager.get_cached_token()
            return token is not None and not auth_manager.is_token_expired(token)
        except Exception:
            return False

    def logout(self):
        cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".cache",
            "spotify_token"
        )
        if os.path.exists(cache_path):
            os.remove(cache_path)
        if os.path.exists(cache_path + "-user"):
            os.remove(cache_path + "-user")
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

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)
