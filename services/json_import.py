import json
from typing import List

from models.track import Track


class JsonImportService:
    @staticmethod
    def import_from_file(file_content: str, playlist_name: str = "") -> List[Track]:
        try:
            data = json.loads(file_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ficheiro JSON inválido: {e}")

        # Detect Spotify export format: {"playlist": {"name": "...", "items": [{"track": {...}}]}}
        if isinstance(data, dict) and "playlist" in data:
            playlist = data["playlist"]
            if isinstance(playlist, dict) and "items" in playlist:
                playlist_name = playlist_name or playlist.get("name", "Spotify Export")
                tracks_data = playlist["items"]
                tracks = []
                for i, item in enumerate(tracks_data):
                    track_info = item.get("track") if isinstance(item, dict) else None
                    if not track_info:
                        continue

                    artists = track_info.get("artists", [])
                    artist = artists[0].get("name", "Unknown Artist") if artists else "Unknown Artist"

                    title = track_info.get("title", "")
                    if not title:
                        continue

                    album_info = track_info.get("album", {})
                    album = album_info.get("title", "") if isinstance(album_info, dict) else str(album_info)

                    tracks.append(
                        Track(
                            artist=str(artist),
                            title=str(title),
                            album=str(album),
                            platform="spotify-export",
                            duration_ms=int(track_info.get("durationMs", 0)),
                            source_playlist=playlist_name,
                        )
                    )
                return tracks

        # Standard format
        tracks_data = data.get("tracks", [])
        if not tracks_data:
            if isinstance(data, list):
                tracks_data = data
            else:
                raise ValueError(
                    "Formato JSON não reconhecido. "
                    "Esperado: {\"tracks\": [{\"artist\": \"...\", \"title\": \"...\"}]}"
                )

        tracks = []
        for i, item in enumerate(tracks_data):
            if not isinstance(item, dict):
                continue

            artist = item.get("artist", item.get("artists", ""))
            if isinstance(artist, list):
                artist = artist[0] if artist else "Unknown Artist"

            title = item.get("title", item.get("name", ""))
            if not title:
                continue

            album = item.get("album", "")

            duration = item.get("duration_ms", item.get("duration", 0))
            if isinstance(duration, str):
                try:
                    duration = float(duration)
                except ValueError:
                    duration = 0
            if duration and duration < 1000:
                duration = int(duration * 1000)

            tracks.append(
                Track(
                    artist=str(artist),
                    title=str(title),
                    album=str(album),
                    platform="json",
                    duration_ms=int(duration),
                    source_playlist=playlist_name or f"JSON Import ({i + 1} tracks)",
                )
            )

        return tracks

    @staticmethod
    def export_to_json(
        tracks: List[Track],
        playlist_name: str = "Playlist Mesclada",
        source_playlists: List[str] = None,
    ) -> str:
        if source_playlists is None:
            source_playlists = list(set(t.source_playlist for t in tracks))

        output = {
            "name": playlist_name,
            "tracks": [
                {
                    "artist": t.artist,
                    "name": t.title,
                    "album": t.album,
                    "duration": int(t.duration_ms / 1000) if t.duration_ms else 0,
                    "thumbnail": "",
                }
                for t in tracks
            ],
        }

        return json.dumps(output, indent=2, ensure_ascii=False)
