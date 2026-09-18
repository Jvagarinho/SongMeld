import requests
from typing import Optional


class ArtworkService:
    ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

    @staticmethod
    def get_artwork(artist: str, title: str) -> Optional[str]:
        try:
            query = f"{artist} {title}"
            params = {
                "term": query,
                "media": "music",
                "limit": 1,
            }
            response = requests.get(
                ArtworkService.ITUNES_SEARCH_URL,
                params=params,
                timeout=5,
            )
            if response.status_code != 200:
                return None

            data = response.json()
            results = data.get("results", [])
            if results:
                artwork_url = results[0].get("artworkUrl100", "")
                return artwork_url.replace("100x100bb", "600x600bb")
            return None
        except Exception:
            return None
