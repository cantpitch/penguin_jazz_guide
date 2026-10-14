from types import SimpleNamespace

from penguin_jazz_guide import cli
from penguin_jazz_guide.models import (
    ReleaseMatch,
    SpotifyAlbumMatch,
    SpotifyPlaylist,
    SpotifyTrack,
    Track,
)


def spotify_match() -> SpotifyAlbumMatch:
    return SpotifyAlbumMatch(
        name="Kind Of Blue",
        artist="Miles Davis",
        release_date="1959-08-17",
        url="https://open.spotify.com/album/abc",
    )


def test_spotify_lookup_uses_last_name_after_exact_search_fails(monkeypatch):
    calls = []

    class FakeSpotifyService:
        def __init__(self, client_id, client_secret):
            pass

        def search_albums(self, artist, album):
            calls.append(("exact", artist, album))
            return []

        def search_albums_by_last_name(self, artist_last_name, album):
            calls.append(("last_name", artist_last_name, album))
            return [spotify_match()]

    answers = iter(["y", ""])
    monkeypatch.setattr(cli, "SpotifyService", FakeSpotifyService)
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))
    config = SimpleNamespace(
        spotify_client_id="client-id", spotify_client_secret="client-secret"
    )

    result = cli._lookup_spotify_album_url(config, "Miles Davis", "Kind Of Blue")

    assert result == "https://open.spotify.com/album/abc"
    assert calls == [
        ("exact", "Miles Davis", "Kind Of Blue"),
        ("last_name", "Davis", "Kind Of Blue"),
    ]


def test_spotify_lookup_uses_title_after_last_name_search_fails(monkeypatch):
    calls = []

    class FakeSpotifyService:
        def __init__(self, client_id, client_secret):
            pass

        def search_albums(self, artist, album):
            calls.append(("exact", artist, album))
            return []

        def search_albums_by_last_name(self, artist_last_name, album):
            calls.append(("last_name", artist_last_name, album))
            return []

        def search_albums_by_title(self, album):
            calls.append(("title", album))
            return [spotify_match()]

    answers = iter(["y", "y", ""])
    monkeypatch.setattr(cli, "SpotifyService", FakeSpotifyService)
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))
    config = SimpleNamespace(
        spotify_client_id="client-id", spotify_client_secret="client-secret"
    )

    result = cli._lookup_spotify_album_url(config, "Miles Davis", "Kind Of Blue")

    assert result == "https://open.spotify.com/album/abc"
    assert calls == [
        ("exact", "Miles Davis", "Kind Of Blue"),
        ("last_name", "Davis", "Kind Of Blue"),
        ("title", "Kind Of Blue"),
    ]


def test_choose_playlist_selects_existing(monkeypatch):
    playlists = [SpotifyPlaylist(id="p1", name="Bop"), SpotifyPlaylist(id="p2", name="Cool")]
    monkeypatch.setattr(cli, "_prompt", lambda message: "2")

    assert cli._choose_playlist(playlists) == playlists[1]


def test_choose_playlist_new_uses_default_name(monkeypatch):
    answers = iter(["n", ""])
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))

    chosen = cli._choose_playlist([])

    assert chosen == SpotifyPlaylist(id="", name=cli.DEFAULT_PLAYLIST_NAME)


class FakeUserClient:
    instances = []

    def __init__(self, client_id, client_secret, redirect_uri, token_cache):
        self.created = []
        self.added = []
        FakeUserClient.instances.append(self)

    def get_album_tracks(self, album_id):
        return [SpotifyTrack(1, "So What", "spotify:track:a")]

    def list_playlists(self):
        return [SpotifyPlaylist(id="p1", name="Bop")]

    def create_playlist(self, name):
        self.created.append(name)
        return SpotifyPlaylist(id="new-id", name=name)

    def add_to_playlist(self, playlist_id, uris):
        self.added.append((playlist_id, uris))
        return len(uris)


def _playlist_config():
    return SimpleNamespace(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_redirect_uri="http://127.0.0.1:8888/callback",
        spotify_token_cache="cache.json",
    )


def _release():
    return ReleaseMatch(
        id=1, title="Miles Davis - Kind Of Blue", artist="Miles Davis",
        year=1997, country="US",
    )


def _discogs_tracks(count):
    return [Track(position=str(i), title=f"Track {i}") for i in range(1, count + 1)]


def test_confirm_track_counts_match_does_not_prompt(monkeypatch):
    def fail(message):
        raise AssertionError("should not prompt")

    monkeypatch.setattr(cli, "_prompt", fail)

    assert cli._confirm_track_counts(5, 5) is True


def test_confirm_track_counts_mismatch_defaults_to_no(monkeypatch):
    monkeypatch.setattr(cli, "_prompt", lambda message: "")

    assert cli._confirm_track_counts(5, 7) is False


def test_confirm_track_counts_mismatch_accepted(monkeypatch):
    monkeypatch.setattr(cli, "_prompt", lambda message: "y")

    assert cli._confirm_track_counts(5, 7) is True


def test_add_album_to_playlist_mismatch_declined_adds_nothing(monkeypatch):
    album = spotify_match()
    album.id = "album1"
    answers = iter(["n"])
    FakeUserClient.instances.clear()
    monkeypatch.setattr(cli, "_lookup_spotify_album", lambda *args: album)
    monkeypatch.setattr(cli, "SpotifyUserClient", FakeUserClient)
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))

    result = cli._add_album_to_playlist(_playlist_config(), _release(), _discogs_tracks(2))

    assert result == 0
    client = FakeUserClient.instances[0]
    assert client.created == []
    assert client.added == []


def test_add_album_to_playlist_mismatch_accepted_adds(monkeypatch):
    album = spotify_match()
    album.id = "album1"
    answers = iter(["y", "1", "y"])
    FakeUserClient.instances.clear()
    monkeypatch.setattr(cli, "_lookup_spotify_album", lambda *args: album)
    monkeypatch.setattr(cli, "SpotifyUserClient", FakeUserClient)
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))

    result = cli._add_album_to_playlist(_playlist_config(), _release(), _discogs_tracks(2))

    assert result == 0
    assert FakeUserClient.instances[0].added == [("p1", ["spotify:track:a"])]


def test_add_album_to_new_playlist_creates_after_confirm(monkeypatch):
    album = spotify_match()
    album.id = "album1"
    answers = iter(["n", "Modal", "y"])
    FakeUserClient.instances.clear()
    monkeypatch.setattr(cli, "_lookup_spotify_album", lambda *args: album)
    monkeypatch.setattr(cli, "SpotifyUserClient", FakeUserClient)
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))

    assert cli._add_album_to_playlist(_playlist_config(), _release(), _discogs_tracks(1)) == 0

    client = FakeUserClient.instances[0]
    assert client.created == ["Modal"]
    assert client.added == [("new-id", ["spotify:track:a"])]


def test_add_album_to_playlist_cancel_creates_nothing(monkeypatch):
    album = spotify_match()
    album.id = "album1"
    answers = iter(["n", "Modal", "n"])
    FakeUserClient.instances.clear()
    monkeypatch.setattr(cli, "_lookup_spotify_album", lambda *args: album)
    monkeypatch.setattr(cli, "SpotifyUserClient", FakeUserClient)
    monkeypatch.setattr(cli, "_prompt", lambda message: next(answers))

    assert cli._add_album_to_playlist(_playlist_config(), _release(), _discogs_tracks(1)) == 0

    client = FakeUserClient.instances[0]
    assert client.created == []
    assert client.added == []
