"""Interactive command-line workflow."""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, load_config
from .discogs_service import DiscogsError, DiscogsService
from .models import (
    AlbumSelection,
    ReleaseMatch,
    SpotifyAlbumMatch,
    SpotifyPlaylist,
    Track,
)
from .sheets_service import SheetsError, SheetsService
from .spotify_service import SpotifyError, SpotifyService, SpotifyUserClient

DEFAULT_PLAYLIST_NAME = "Penguin Jazz Guide"


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
            f"({only.year_display}, {only.country_display}; "
            f"catalog: {', '.join(only.catalog_numbers) or 'Unknown'})"
        )
        answer = _prompt("Use this release? [Y/n] ").lower()
        return only if answer in ("", "y", "yes") else None

    print(f"\nFound {len(matches)} matches:")
    for index, match in enumerate(matches, start=1):
        print(
            f"  {index}. {match.album_name} "
            f"[{match.year_display}, {match.country_display}; "
            f"catalog: {', '.join(match.catalog_numbers) or 'Unknown'}]"
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
    match = _lookup_spotify_album(config, artist, album)
    return match.url if match else None


def _lookup_spotify_album(config, artist: str, album: str) -> SpotifyAlbumMatch | None:
    """Find and select a Spotify album, or return None if unavailable."""
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
        artist_last_name = artist.rsplit(maxsplit=1)[-1]
        try_last_name = _prompt(
            "\nNo exact Spotify album found. Try the album title and "
            f"artist last name ({artist_last_name})? [y/N] "
        ).lower()
        if try_last_name in ("y", "yes"):
            try:
                matches = spotify.search_albums_by_last_name(artist_last_name, album)
            except SpotifyError as exc:
                print(
                    f"Spotify lookup failed; continuing without URL: {exc}",
                    file=sys.stderr,
                )
                return None

    if not matches:
        try_title = _prompt(
            "No Spotify album found with the artist last name. "
            "Try the album title only? [y/N] "
        ).lower()
        if try_title in ("y", "yes"):
            try:
                matches = spotify.search_albums_by_title(album)
            except SpotifyError as exc:
                print(
                    f"Spotify lookup failed; continuing without URL: {exc}",
                    file=sys.stderr,
                )
                return None

    if not matches:
        print("\nNo Spotify album found; continuing without Spotify URL.")
        return None

    chosen = _choose_spotify_album(matches)
    if chosen is None:
        print("Continuing without Spotify URL.")
        return None
    return chosen


def _confirm_track_counts(discogs_count: int, spotify_count: int) -> bool:
    """Return True if the counts match or the user accepts the mismatch."""
    if discogs_count == spotify_count:
        return True
    print(
        f"\nWarning: Discogs lists {discogs_count} track(s) but Spotify has "
        f"{spotify_count}. These may be different editions of the album."
    )
    answer = _prompt("Add this album anyway? [y/N] ").lower()
    return answer in ("y", "yes")


def _spotify_track_count(config, album_id: str) -> int | None:
    """Count tracks on a Spotify album, or return None if unavailable."""
    try:
        spotify = SpotifyService(config.spotify_client_id, config.spotify_client_secret)
        return len(spotify.get_album_tracks(album_id))
    except SpotifyError as exc:
        print(
            f"Could not fetch Spotify tracks; skipping track count check: {exc}",
            file=sys.stderr,
        )
        return None


def _choose_playlist(playlists: list[SpotifyPlaylist]) -> SpotifyPlaylist | None:
    """Pick an existing playlist or name a new one.

    A new playlist is returned with an empty ``id``; the caller creates it only
    after the user confirms, so cancelling never leaves an empty playlist.
    """
    if playlists:
        print(f"\nYour playlists ({len(playlists)}):")
        for index, playlist in enumerate(playlists, start=1):
            print(f"  {index}. {playlist.name} [{playlist.item_count_display} items]")
    else:
        print("\nYou have no playlists you can add to.")

    while True:
        answer = _prompt(
            "Select a playlist number, 'n' for a new playlist, or 'q' to cancel: "
        ).lower()
        if answer in ("q", "quit", ""):
            return None
        if answer in ("n", "new"):
            name = _prompt(f"New playlist name [{DEFAULT_PLAYLIST_NAME}]: ")
            return SpotifyPlaylist(id="", name=name or DEFAULT_PLAYLIST_NAME)
        if answer.isdigit() and 1 <= int(answer) <= len(playlists):
            return playlists[int(answer) - 1]
        print("Invalid selection, try again.")


def _add_album_to_playlist(
    config, release: ReleaseMatch, discogs_tracks: list[Track]
) -> int:
    """Find the release on Spotify and add its tracks to a chosen playlist."""
    album = _lookup_spotify_album(config, release.artist, release.album_name)
    if album is None or not album.id:
        print("No Spotify album selected. Nothing added.")
        return 0

    spotify = SpotifyUserClient(
        config.spotify_client_id,
        config.spotify_client_secret,
        redirect_uri=config.spotify_redirect_uri,
        token_cache=config.spotify_token_cache,
    )
    try:
        tracks = spotify.get_album_tracks(album.id)
        if not tracks:
            print("That Spotify album has no tracks. Nothing added.")
            return 0
        playlists = spotify.list_playlists()
    except SpotifyError as exc:
        print(f"Spotify error: {exc}", file=sys.stderr)
        return 1

    print(f"\n{album.name} by {album.artist} — {len(tracks)} track(s):")
    for track in tracks:
        number = f"{track.track_number}. " if track.track_number else ""
        print(f"  {number}{track.name}")

    if not _confirm_track_counts(len(discogs_tracks), len(tracks)):
        print("Cancelled. Nothing added.")
        return 0

    playlist = _choose_playlist(playlists)
    if playlist is None:
        print("Cancelled. Nothing added.")
        return 0

    label = playlist.name if playlist.id else f"new playlist '{playlist.name}'"
    confirm = _prompt(f"\nAdd {len(tracks)} track(s) to {label}? [Y/n] ").lower()
    if confirm not in ("", "y", "yes"):
        print("Cancelled. Nothing added.")
        return 0

    try:
        if not playlist.id:
            playlist = spotify.create_playlist(playlist.name)
        added = spotify.add_to_playlist(playlist.id, [t.uri for t in tracks])
    except SpotifyError as exc:
        print(f"Spotify error: {exc}", file=sys.stderr)
        return 1

    print(f"Added {added} track(s) to {playlist.name}.")
    return 0


def run(config_path: str, playlist: bool = False) -> int:
    try:
        config = load_config(config_path, require_sheets=not playlist)
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

    if playlist:
        return _add_album_to_playlist(config, chosen, tracks)

    if not tracks:
        print("That release has no tracklist on Discogs. Nothing written.")
        return 0

    spotify_album = _lookup_spotify_album(config, chosen.artist, chosen.album_name)
    spotify_url = spotify_album.url if spotify_album else None
    selection = AlbumSelection(
        release=chosen,
        tracks=tracks,
        album_url=spotify_url,
        discogs_url=f"https://www.discogs.com/release/{chosen.id}",
    )
    print(f"\n{chosen.album_name} — {len(tracks)} track(s):")
    if spotify_url:
        print(f"Spotify URL: {spotify_url}")
    for track in tracks:
        position = f"{track.position}. " if track.position else ""
        print(f"  {position}{track.title}")

    if spotify_album and spotify_album.id:
        spotify_count = _spotify_track_count(config, spotify_album.id)
        if spotify_count is not None and not _confirm_track_counts(
            len(tracks), spotify_count
        ):
            print("Cancelled. Nothing written.")
            return 0

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
        description=(
            "Search Discogs for a jazz album and add it to a Google Sheet "
            "or a Spotify playlist."
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.toml",
        help="Path to the TOML config file (default: config.toml).",
    )
    parser.add_argument(
        "-p",
        "--playlist",
        action="store_true",
        help="Add the selected album to a Spotify playlist instead of the sheet.",
    )
    args = parser.parse_args(argv)
    try:
        return run(args.config, playlist=args.playlist)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
