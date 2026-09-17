from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Track:
    artist: str
    title: str
    album: str = ""
    platform: str = ""
    duration_ms: int = 0
    spotify_id: str = ""
    source_playlist: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(
            artist=data.get("artist", ""),
            title=data.get("title", ""),
            album=data.get("album", ""),
            platform=data.get("platform", ""),
            duration_ms=data.get("duration_ms", 0),
            spotify_id=data.get("spotify_id", ""),
            source_playlist=data.get("source_playlist", ""),
        )

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000 if self.duration_ms else 0

    @property
    def display_duration(self) -> str:
        if not self.duration_ms:
            return "--:--"
        total_seconds = int(self.duration_ms / 1000)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
