"""Data models for releases and tracks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReleaseMatch:
    """A candidate release returned from a Discogs search."""

    id: int
    title: str
    artist: str
    year: int | None
    country: str | None
    formats: list[str] = field(default_factory=list)

    @property
    def album_name(self) -> str:
        """Album title without the leading 'Artist - ' prefix, if present."""
        if self.artist and self.title.startswith(f"{self.artist} - "):
            return self.title[len(self.artist) + 3 :]
        if " - " in self.title:
            return self.title.split(" - ", 1)[1]
        return self.title

    @property
    def year_display(self) -> str:
        return str(self.year) if self.year else "Unknown"

    @property
    def country_display(self) -> str:
        return self.country or "Unknown"


@dataclass
class Track:
    """A single track on a release."""

    position: str
    title: str


@dataclass
class AlbumSelection:
    """A chosen release together with its resolved track listing."""

    release: ReleaseMatch
    tracks: list[Track]
    album_url: str | None = None


@dataclass
class SpotifyAlbumMatch:
    """A candidate album returned from Spotify search."""

    name: str
    artist: str
    release_date: str | None
    url: str

    @property
    def release_date_display(self) -> str:
        return self.release_date or "Unknown"
