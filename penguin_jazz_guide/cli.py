"""Interactive command-line workflow."""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, load_config
from .discogs_service import DiscogsError, DiscogsService
from .models import AlbumSelection, ReleaseMatch, SpotifyAlbumMatch
from .sheets_service import SheetsError, SheetsService
from .spotify_service import SpotifyError, SpotifyService


def _prompt(message: str) -> str:
    return input(message).strip()


def _choose_release(matches: list[ReleaseMatch]) -> ReleaseMatch | None:
    """Present matches and return the selected release, or None to cancel."""
    if not matches:
        return None
    if len(matches) == 1:
        only = matches[0]
        print(
            f"\nOne match found: {only.album_name} "
            f"({only.year_display}, {only.country_display})"
        )
        answer = _prompt("Use this release? [Y/n] ").lower()
        return only if answer in ("", "y", "yes") else None

    print(f"\nFound {len(matches)} matches:")
    for index, match in enumerate(matches, start=1):
        print(
            f"  {index}. {match.album_name} "
            f"[{match.year_display}, {match.country_display}]"
        )

    while True:
        answer = _prompt("Select a number (or 'q' to cancel): ").lower()
        if answer in ("q", "quit", ""):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(matches):
            return matches[int(answer) - 1]
        print("Invalid selection, try again.")


def _choose_spotify_album(matches: list[SpotifyAlbumMatch]) -> SpotifyAlbumMatch | None:
    """Present Spotify album matches and return the selected album, or None."""
    if not matches:
        return None
    if len(matches) == 1:
        only = matches[0]
        print(
            f"\nOne Spotify album found: {only.name} by {only.artist} "
            f"({only.release_date_display})"
        )
        answer = _prompt("Use this Spotify URL? [Y/n] ").lower()
        return only if answer in ("", "y", "yes") else None

    print(f"\nFound {len(matches)} Spotify album matches:")
    for index, match in enumerate(matches, start=1):
        print(
            f"  {index}. {match.name} by {match.artist} "
            f"[{match.release_date_display}]"
        )

    while True:
        answer = _prompt("Select a Spotify album number (or 's' to skip): ").lower()
        if answer in ("s", "skip", "q", "quit", ""):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(matches):
            return matches[int(answer) - 1]
        print("Invalid selection, try again.")


def _lookup_spotify_album_url(config, artist: str, album: str) -> str | None:
    """Find an optional Spotify album URL, continuing gracefully if unavailable."""
    if not config.spotify_client_id or not config.spotify_client_secret:
        print("\nSpotify credentials not configured; skipping Spotify lookup.")
        return None

    try:
        spotify = SpotifyService(config.spotify_client_id, config.spotify_client_secret)
        matches = spotify.search_albums(artist, album)
    except SpotifyError as exc:
        print(f"Spotify lookup failed; continuing without URL: {exc}", file=sys.stderr)
        return None

    if not matches:
        print("\nNo Spotify album found; continuing without Spotify URL.")
        return None

    chosen = _choose_spotify_album(matches)
    if chosen is None:
        print("Continuing without Spotify URL.")
        return None
    return chosen.url


def run(config_path: str) -> int:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        discogs = DiscogsService(
            token=config.discogs_token,
            user_agent=config.user_agent,
            country_preference=config.country_preference,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to initialise Discogs client: {exc}", file=sys.stderr)
        return 2

    artist = _prompt("Artist name: ")
    album = _prompt("Album search text: ")
    if not artist or not album:
        print("Both an artist and album are required.", file=sys.stderr)
        return 2

    try:
        matches = discogs.search_releases(artist, album)
    except DiscogsError as exc:
        print(f"Search error: {exc}", file=sys.stderr)
        return 1

    if not matches:
        print("No CD releases found for that artist/album.")
        return 0

    chosen = _choose_release(matches)
    if chosen is None:
        print("Cancelled. Nothing written.")
        return 0

    try:
        tracks = discogs.get_tracklist(chosen.id)
    except DiscogsError as exc:
        print(f"Tracklist error: {exc}", file=sys.stderr)
        return 1

    if not tracks:
        print("That release has no tracklist on Discogs. Nothing written.")
        return 0

    spotify_url = _lookup_spotify_album_url(config, chosen.artist, chosen.album_name)
    selection = AlbumSelection(release=chosen, tracks=tracks, album_url=spotify_url)
    print(f"\n{chosen.album_name} — {len(tracks)} track(s):")
    if spotify_url:
        print(f"Spotify URL: {spotify_url}")
    for track in tracks:
        position = f"{track.position}. " if track.position else ""
        print(f"  {position}{track.title}")

    confirm = _prompt("\nWrite these tracks to the sheet? [Y/n] ").lower()
    if confirm not in ("", "y", "yes"):
        print("Cancelled. Nothing written.")
        return 0

    try:
        sheets = SheetsService.from_config(config)
        written = sheets.append_album(selection)
    except SheetsError as exc:
        print(f"Google Sheets error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {written} row(s) to the sheet.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search Discogs for a jazz album and add it to a Google Sheet."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.toml",
        help="Path to the TOML config file (default: config.toml).",
    )
    args = parser.parse_args(argv)
    try:
        return run(args.config)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
