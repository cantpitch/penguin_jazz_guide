"""Spotify album search via the Client Credentials flow."""

from __future__ import annotations

import requests

from .models import SpotifyAlbumMatch

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"


class SpotifyError(Exception):
    """Raised when Spotify lookup fails."""


class SpotifyService:
    """Search Spotify albums using app credentials."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None

    def search_albums(
        self, artist: str, album: str, limit: int = 10
    ) -> list[SpotifyAlbumMatch]:
        """Search Spotify for albums matching the selected Discogs release."""
        token = self._get_access_token()
        query = f'artist:"{artist}" album:"{album}"'
        try:
            response = requests.get(
                SEARCH_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={"q": query, "type": "album", "limit": limit},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SpotifyError(f"Spotify album search failed: {exc}") from exc

        data = response.json()
        items = data.get("albums", {}).get("items", [])
        return [_album_from_item(item) for item in items if item.get("external_urls")]

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        try:
            response = requests.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SpotifyError(f"Spotify authentication failed: {exc}") from exc

        token = response.json().get("access_token")
        if not token:
            raise SpotifyError("Spotify authentication failed: response did not include access_token.")
        self._access_token = token
        return token


def _album_from_item(item: dict) -> SpotifyAlbumMatch:
    artists = item.get("artists", [])
    artist = artists[0].get("name", "") if artists else ""
    return SpotifyAlbumMatch(
        name=item.get("name", ""),
        artist=artist,
        release_date=item.get("release_date") or None,
        url=item.get("external_urls", {}).get("spotify", ""),
    )
