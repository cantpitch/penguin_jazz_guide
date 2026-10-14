"""Spotify album search and playlist management.

Album search uses the Client Credentials flow. Playlist access needs a
logged-in user, so :class:`SpotifyUserClient` uses the Authorization Code flow
with a local loopback redirect and caches the resulting tokens on disk.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .models import SpotifyAlbumMatch, SpotifyPlaylist, SpotifyTrack

TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
API_URL = "https://api.spotify.com/v1"
SEARCH_URL = f"{API_URL}/search"
PLAYLIST_SCOPES = (
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-private playlist-modify-public"
)
# Spotify accepts at most 100 URIs per "add items to playlist" request.
PLAYLIST_ADD_BATCH_SIZE = 100


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
        return self._search_albums(f'artist:"{artist}" album:"{album}"', limit)

    def search_albums_by_last_name(
        self, artist_last_name: str, album: str, limit: int = 10
    ) -> list[SpotifyAlbumMatch]:
        """Search Spotify using an album title and the artist's last name."""
        return self._search_albums(
            f'artist:"{artist_last_name}" album:"{album}"', limit
        )

    def search_albums_by_title(
        self, album: str, limit: int = 10
    ) -> list[SpotifyAlbumMatch]:
        """Search Spotify using only an album title."""
        return self._search_albums(f'album:"{album}"', limit)

    def get_album_tracks(self, album_id: str) -> list[SpotifyTrack]:
        """Return every track on a Spotify album."""
        return _fetch_album_tracks(self._get_json, album_id)

    def _get_json(self, url: str, params: dict | None) -> dict:
        token = self._get_access_token()
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SpotifyError(f"Spotify request failed: {exc}") from exc
        return response.json()

    def _search_albums(self, query: str, limit: int) -> list[SpotifyAlbumMatch]:
        """Execute an album search for a prepared Spotify query."""
        token = self._get_access_token()
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
            raise SpotifyError(
                "Spotify authentication failed: response did not include access_token."
            )
        self._access_token = token
        return token


def _fetch_album_tracks(
    get_json: Callable[[str, dict | None], dict], album_id: str
) -> list[SpotifyTrack]:
    """Page through an album's tracks using the given GET-and-decode function."""
    tracks = []
    url: str | None = f"{API_URL}/albums/{album_id}/tracks"
    params: dict | None = {"limit": 50}
    while url:
        data = get_json(url, params)
        for item in data.get("items", []):
            if item and item.get("uri"):
                tracks.append(
                    SpotifyTrack(
                        track_number=item.get("track_number"),
                        name=item.get("name", ""),
                        uri=item["uri"],
                    )
                )
        url = data.get("next")
        params = None  # "next" already carries the query string
    return tracks


def _album_from_item(item: dict) -> SpotifyAlbumMatch:
    artists = item.get("artists", [])
    artist = artists[0].get("name", "") if artists else ""
    return SpotifyAlbumMatch(
        name=item.get("name", ""),
        artist=artist,
        release_date=item.get("release_date") or None,
        url=item.get("external_urls", {}).get("spotify", ""),
        id=item.get("id", ""),
    )


class SpotifyUserClient:
    """Access the logged-in user's playlists via the Authorization Code flow."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_cache: Path,
        open_browser: Callable[[str], object] = webbrowser.open,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_cache = Path(token_cache)
        self._open_browser = open_browser
        self._token: dict | None = None
        self._user_id: str | None = None

    # -- Public API -----------------------------------------------------

    def list_playlists(self) -> list[SpotifyPlaylist]:
        """Return playlists the current user owns or collaborates on."""
        user_id = self._current_user_id()
        playlists = []
        url: str | None = f"{API_URL}/me/playlists"
        params: dict | None = {"limit": 50}
        while url:
            data = self._request("GET", url, params=params)
            for item in data.get("items", []):
                if not item:
                    continue
                owner_id = (item.get("owner") or {}).get("id")
                if owner_id != user_id and not item.get("collaborative"):
                    continue
                playlists.append(_playlist_from_item(item))
            url = data.get("next")
            params = None  # "next" already carries the query string
        return playlists

    def create_playlist(
        self, name: str, description: str = "", public: bool = False
    ) -> SpotifyPlaylist:
        """Create a playlist for the current user."""
        data = self._request(
            "POST",
            f"{API_URL}/me/playlists",
            json={"name": name, "description": description, "public": public},
        )
        return _playlist_from_item(data)

    def get_album_tracks(self, album_id: str) -> list[SpotifyTrack]:
        """Return every track on a Spotify album."""
        return _fetch_album_tracks(
            lambda url, params: self._request("GET", url, params=params), album_id
        )

    def add_to_playlist(self, playlist_id: str, uris: list[str]) -> int:
        """Append track URIs to a playlist and return how many were added."""
        for start in range(0, len(uris), PLAYLIST_ADD_BATCH_SIZE):
            self._request(
                "POST",
                f"{API_URL}/playlists/{playlist_id}/items",
                json={"uris": uris[start : start + PLAYLIST_ADD_BATCH_SIZE]},
            )
        return len(uris)

    # -- HTTP -----------------------------------------------------------

    def _current_user_id(self) -> str:
        if self._user_id is None:
            user_id = self._request("GET", f"{API_URL}/me").get("id")
            if not user_id:
                raise SpotifyError("Spotify did not return the current user id.")
            self._user_id = user_id
        return self._user_id

    def _request(self, method: str, url: str, **kwargs) -> dict:
        token = self._get_access_token()
        try:
            response = requests.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
                **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SpotifyError(f"Spotify request failed: {exc}") from exc
        if not response.content:
            return {}
        return response.json()

    # -- Auth -----------------------------------------------------------

    def _get_access_token(self) -> str:
        if self._token is None:
            self._token = self._load_cached_token()
        if self._token is None:
            self._token = self._authorize()
            self._save_token(self._token)
        elif self._token.get("expires_at", 0) <= time.time() + 60:
            self._token = self._refresh(self._token)
            self._save_token(self._token)
        return self._token["access_token"]

    def _load_cached_token(self) -> dict | None:
        try:
            token = json.loads(self.token_cache.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(token, dict) or not token.get("access_token"):
            return None
        return token

    def _save_token(self, token: dict) -> None:
        try:
            self.token_cache.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                self.token_cache, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
            with os.fdopen(fd, "w") as fh:
                json.dump(token, fh)
        except OSError as exc:
            raise SpotifyError(
                f"Could not save Spotify token cache {self.token_cache}: {exc}"
            ) from exc

    def _refresh(self, token: dict) -> dict:
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            return self._authorize()
        try:
            new_token = self._token_request(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            )
        except SpotifyError:
            # A revoked or stale refresh token: fall back to a fresh login.
            return self._authorize()
        if not new_token.get("refresh_token"):
            new_token["refresh_token"] = refresh_token
        return new_token

    def _authorize(self) -> dict:
        state = secrets.token_urlsafe(16)
        auth_url = f"{AUTHORIZE_URL}?" + urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": PLAYLIST_SCOPES,
                "state": state,
            }
        )
        print(
            "\nLog in to Spotify to allow playlist access. If your browser does "
            f"not open, visit:\n  {auth_url}"
        )
        self._open_browser(auth_url)
        code = self._wait_for_auth_code(state)
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }
        )

    def _wait_for_auth_code(self, expected_state: str, timeout: int = 300) -> str:
        """Run a one-shot local HTTP server to receive the OAuth redirect."""
        redirect = urlparse(self.redirect_uri)
        result: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != (redirect.path or "/"):
                    self.send_response(404)
                    self.end_headers()
                    return
                query = parse_qs(parsed.query)
                result.update({key: values[0] for key, values in query.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<p>Spotify login complete. You can close this tab and "
                    b"return to the terminal.</p>"
                )

            def log_message(self, *args):
                pass

        try:
            server = HTTPServer(
                (redirect.hostname or "127.0.0.1", redirect.port or 80), Handler
            )
        except OSError as exc:
            raise SpotifyError(
                f"Could not listen on {self.redirect_uri} for the Spotify login: {exc}"
            ) from exc

        deadline = time.monotonic() + timeout
        server.timeout = 1
        with server:
            while not result and time.monotonic() < deadline:
                server.handle_request()

        if not result:
            raise SpotifyError("Timed out waiting for the Spotify login.")
        if result.get("state") != expected_state:
            raise SpotifyError("Spotify login failed: state mismatch.")
        if "error" in result:
            raise SpotifyError(f"Spotify login failed: {result['error']}")
        if not result.get("code"):
            raise SpotifyError("Spotify login failed: no authorization code returned.")
        return result["code"]

    def _token_request(self, data: dict) -> dict:
        try:
            response = requests.post(
                TOKEN_URL,
                data=data,
                auth=(self.client_id, self.client_secret),
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SpotifyError(f"Spotify authentication failed: {exc}") from exc

        payload = response.json()
        if not payload.get("access_token"):
            raise SpotifyError(
                "Spotify authentication failed: response did not include access_token."
            )
        return {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token"),
            "expires_at": time.time() + int(payload.get("expires_in", 3600)),
        }


def _playlist_from_item(item: dict) -> SpotifyPlaylist:
    # Spotify renamed the playlist "tracks" summary to "items" in 2026.
    summary = item.get("items") or item.get("tracks") or {}
    total = summary.get("total") if isinstance(summary, dict) else None
    return SpotifyPlaylist(
        id=item.get("id", ""),
        name=item.get("name", ""),
        item_count=total,
    )
