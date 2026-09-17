from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from rapidfuzz import fuzz

from models.track import Track
from utils.normalization import normalize_track_key, normalize_text


@dataclass
class DuplicateGroup:
    tracks: List[Track]
    similarity_score: float = 0.0
    keep_indices: List[int] = field(default_factory=list)

    @property
    def artist(self) -> str:
        return self.tracks[0].artist if self.tracks else ""

    @property
    def title(self) -> str:
        return self.tracks[0].title if self.tracks else ""

    @property
    def sources(self) -> List[str]:
        return list(set(t.source_playlist for t in self.tracks))


class PlaylistMerger:
    def __init__(self, similarity_threshold: float = 85.0):
        self.similarity_threshold = similarity_threshold

    def _get_track_key(self, track: Track) -> Tuple[str, str]:
        return (normalize_text(track.artist), normalize_text(track.title))

    def _compare_tracks(self, key1: Tuple[str, str], key2: Tuple[str, str]) -> float:
        artist_sim = fuzz.ratio(key1[0], key2[0])
        title_sim = fuzz.ratio(key1[1], key2[1])
        return (artist_sim + title_sim) / 2

    def find_duplicates(self, tracks: List[Track]) -> List[DuplicateGroup]:
        if not tracks:
            return []

        track_keys = [(self._get_track_key(t), t) for t in tracks]
        visited = set()
        duplicates = []

        for i, (key_i, track_i) in enumerate(track_keys):
            if i in visited:
                continue

            group_tracks = [track_i]
            group_indices = [i]

            for j, (key_j, track_j) in enumerate(track_keys):
                if j <= i or j in visited:
                    continue

                similarity = self._compare_tracks(key_i, key_j)
                if similarity >= self.similarity_threshold:
                    group_tracks.append(track_j)
                    group_indices.append(j)
                    visited.add(j)

            if len(group_tracks) > 1:
                duplicates.append(
                    DuplicateGroup(
                        tracks=group_tracks,
                        similarity_score=100.0,
                        keep_indices=[0],
                    )
                )
                visited.add(i)

        return duplicates

    def merge(
        self,
        all_tracks: List[Track],
        duplicates_to_remove: Optional[List[DuplicateGroup]] = None,
    ) -> List[Track]:
        if duplicates_to_remove is None:
            duplicates = self.find_duplicates(all_tracks)
        else:
            duplicates = duplicates_to_remove

        tracks_to_remove = set()
        for dup_group in duplicates:
            for idx in dup_group.keep_indices:
                pass
            for i, track in enumerate(dup_group.tracks):
                if i not in dup_group.keep_indices:
                    tracks_to_remove.add(id(track))

        merged = [t for t in all_tracks if id(t) not in tracks_to_remove]
        return merged

    def get_stats(
        self, all_tracks: List[Track], merged_tracks: List[Track]
    ) -> dict:
        sources = {}
        for t in all_tracks:
            src = t.source_playlist or t.platform
            sources[src] = sources.get(src, 0) + 1

        platforms = {}
        for t in all_tracks:
            platforms[t.platform] = platforms.get(t.platform, 0) + 1

        return {
            "total_before": len(all_tracks),
            "total_after": len(merged_tracks),
            "removed": len(all_tracks) - len(merged_tracks),
            "sources": sources,
            "platforms": platforms,
        }
