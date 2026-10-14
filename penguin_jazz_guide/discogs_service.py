"""Discogs API access: searching releases and fetching tracklists."""

from __future__ import annotations

import discogs_client

from .models import ReleaseMatch, Track

CD_FORMAT = "CD"


class DiscogsError(Exception):
    """Raised when a Discogs API interaction fails."""


def _extract_format_names(raw_formats) -> list[str]:
    names: list[str] = []
    for fmt in raw_formats or []:
        if isinstance(fmt, dict):
            name = fmt.get("name")
            if name:
                names.append(name)
        elif isinstance(fmt, str):
            names.append(fmt)
    return names


def _extract_catalog_numbers(raw_catalog_numbers) -> list[str]:
    if not raw_catalog_numbers:
        return []
    if isinstance(raw_catalog_numbers, (list, tuple)):
        return [str(value) for value in raw_catalog_numbers if value]
    return [str(raw_catalog_numbers)]


def _catalog_numbers_from_release(release) -> list[str]:
    raw_catalog_numbers = getattr(release, "catno", None)
    if raw_catalog_numbers is None:
        data = getattr(release, "data", None)
        if isinstance(data, dict):
            raw_catalog_numbers = data.get("catno")
    return _extract_catalog_numbers(raw_catalog_numbers)


def _country_rank(country: str | None, preference: list[str]) -> int:
    if not country:
        return len(preference) + 1
    for index, preferred in enumerate(preference):
        if country.lower() == preferred.lower():
            return index
    return len(preference)


class DiscogsService:
    """Thin wrapper over python3-discogs-client focused on CD releases."""

    def __init__(self, token: str, user_agent: str, country_preference: list[str]):
        self.country_preference = country_preference
        self.client = discogs_client.Client(user_agent, user_token=token)

    def search_releases(
        self, artist: str, album: str, limit: int = 25
    ) -> list[ReleaseMatch]:
        """Search for CD releases matching an artist and album title."""
        try:
            results = self.client.search(
                album,
                artist=artist,
                type="release",
                format=CD_FORMAT,
            )
        except Exception as exc:  # noqa: BLE001 - surface a clear domain error
            raise DiscogsError(f"Discogs search failed: {exc}") from exc

        matches: list[ReleaseMatch] = []
        for release in results:
            if len(matches) >= limit:
                break
            try:
                formats = _extract_format_names(getattr(release, "formats", None))
                if formats and not any(f.upper() == CD_FORMAT for f in formats):
                    continue
                matches.append(
                    ReleaseMatch(
                        id=release.id,
                        title=getattr(release, "title", "") or "",
                        artist=self._primary_artist(release),
                        year=getattr(release, "year", None) or None,
                        country=getattr(release, "country", None) or None,
                        formats=formats,
                        catalog_numbers=_catalog_numbers_from_release(release),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                raise DiscogsError(f"Failed to read a search result: {exc}") from exc

        return self.sort_by_preference(matches)

    def sort_by_preference(self, matches: list[ReleaseMatch]) -> list[ReleaseMatch]:
        """Sort matches by country preference, then by year (oldest first)."""
        return sorted(
            matches,
            key=lambda m: (
                _country_rank(m.country, self.country_preference),
                m.year if m.year else 9999,
            ),
        )

    def get_tracklist(self, release_id: int) -> list[Track]:
        """Fetch and normalise the tracklist for a release."""
        try:
            release = self.client.release(release_id)
            raw_tracks = release.tracklist
        except Exception as exc:  # noqa: BLE001
            raise DiscogsError(
                f"Failed to fetch tracklist for release {release_id}: {exc}"
            ) from exc

        tracks: list[Track] = []
        for item in raw_tracks or []:
            title = getattr(item, "title", None)
            if not title:
                continue
            tracks.append(
                Track(position=getattr(item, "position", "") or "", title=title)
            )
        return tracks

    @staticmethod
    def _primary_artist(release) -> str:
        artists = getattr(release, "artists", None)
        if artists:
            name = getattr(artists[0], "name", None)
            if name:
                return name
        title = getattr(release, "title", "") or ""
        # Discogs search titles are often "Artist - Album".
        if " - " in title:
            return title.split(" - ", 1)[0]
        return ""
