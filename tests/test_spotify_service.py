import json
from unittest.mock import MagicMock

import pytest
import requests

from penguin_jazz_guide.spotify_service import SpotifyError, SpotifyService


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


def test_search_albums_returns_matches(monkeypatch):
    post = MagicMock(return_value=FakeResponse({"access_token": "token"}))
    get = MagicMock(
        return_value=FakeResponse(
            {
                "albums": {
                    "items": [
                        {
                            "name": "Kind Of Blue",
                            "artists": [{"name": "Miles Davis"}],
                            "release_date": "1959-08-17",
                            "external_urls": {
                                "spotify": "https://open.spotify.com/album/abc"
                            },
                        }
                    ]
                }
            }
        )
    )
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)

    service = SpotifyService("client-id", "client-secret")
    matches = service.search_albums("Miles Davis", "Kind Of Blue")

    assert len(matches) == 1
    assert matches[0].name == "Kind Of Blue"
    assert matches[0].artist == "Miles Davis"
    assert matches[0].url == "https://open.spotify.com/album/abc"
    get.assert_called_once()
    _, kwargs = get.call_args
    assert kwargs["params"]["q"] == 'artist:"Miles Davis" album:"Kind Of Blue"'


def test_search_albums_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        MagicMock(return_value=FakeResponse({"access_token": "token"})),
    )
    monkeypatch.setattr(
        requests, "get", MagicMock(return_value=FakeResponse({"albums": {"items": []}}))
    )

    service = SpotifyService("client-id", "client-secret")
    assert service.search_albums("Artist", "Album") == []


def test_search_albums_by_last_name_uses_album_and_last_name(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        MagicMock(return_value=FakeResponse({"access_token": "token"})),
    )
    get = MagicMock(return_value=FakeResponse({"albums": {"items": []}}))
    monkeypatch.setattr(requests, "get", get)

    service = SpotifyService("client-id", "client-secret")
    assert service.search_albums_by_last_name("Davis", "Kind Of Blue") == []

    _, kwargs = get.call_args
    assert kwargs["params"]["q"] == 'artist:"Davis" album:"Kind Of Blue"'


def test_search_albums_by_title_uses_only_album(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        MagicMock(return_value=FakeResponse({"access_token": "token"})),
    )
    get = MagicMock(return_value=FakeResponse({"albums": {"items": []}}))
    monkeypatch.setattr(requests, "get", get)

    service = SpotifyService("client-id", "client-secret")
    assert service.search_albums_by_title("Kind Of Blue") == []

    _, kwargs = get.call_args
    assert kwargs["params"]["q"] == 'album:"Kind Of Blue"'


def test_missing_access_token_raises(monkeypatch):
    monkeypatch.setattr(requests, "post", MagicMock(return_value=FakeResponse({})))

    service = SpotifyService("client-id", "client-secret")
    with pytest.raises(SpotifyError, match="access_token"):
        service.search_albums("Artist", "Album")


def test_search_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        MagicMock(return_value=FakeResponse({"access_token": "token"})),
    )
    monkeypatch.setattr(
        requests,
        "get",
        MagicMock(return_value=FakeResponse({}, requests.HTTPError("boom"))),
    )

    service = SpotifyService("client-id", "client-secret")
    with pytest.raises(SpotifyError, match="Spotify album search failed"):
        service.search_albums("Artist", "Album")


def test_service_get_album_tracks_follows_pagination(monkeypatch):
    post = MagicMock(return_value=FakeResponse({"access_token": "token"}))
    get = MagicMock(
        side_effect=[
            FakeResponse(
                {
                    "items": [{"track_number": 1, "name": "So What", "uri": "u:a"}],
                    "next": "https://api.spotify.com/v1/albums/abc/tracks?offset=1",
                }
            ),
            FakeResponse(
                {
                    "items": [{"track_number": 2, "name": "Freddie", "uri": "u:b"}],
                    "next": None,
                }
            ),
        ]
    )
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)

    tracks = SpotifyService("id", "secret").get_album_tracks("abc")

    assert [t.name for t in tracks] == ["So What", "Freddie"]
    assert get.call_args_list[0].args == (
        "https://api.spotify.com/v1/albums/abc/tracks",
    )
    assert get.call_args_list[1].kwargs["params"] is None


def _user_client(tmp_path, token=None):
    from penguin_jazz_guide.spotify_service import SpotifyUserClient

    cache = tmp_path / "token.json"
    if token is not None:
        cache.write_text(json.dumps(token))
    return SpotifyUserClient(
        "client-id",
        "client-secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        token_cache=cache,
        open_browser=MagicMock(),
    )


class FakeApiResponse(FakeResponse):
    content = b"{}"


def _valid_token():
    return {"access_token": "user-token", "refresh_token": "r", "expires_at": 9e12}


def test_list_playlists_filters_to_editable(monkeypatch, tmp_path):
    responses = {
        "https://api.spotify.com/v1/me": {"id": "me"},
        "https://api.spotify.com/v1/me/playlists": {
            "items": [
                {"id": "p1", "name": "Mine", "owner": {"id": "me"}, "items": {"total": 3}},
                {"id": "p2", "name": "Theirs", "owner": {"id": "x"}},
                {"id": "p3", "name": "Collab", "owner": {"id": "x"},
                 "collaborative": True, "tracks": {"total": 7}},
            ],
            "next": None,
        },
    }
    request = MagicMock(side_effect=lambda method, url, **kw: FakeApiResponse(responses[url]))
    monkeypatch.setattr(requests, "request", request)

    playlists = _user_client(tmp_path, _valid_token()).list_playlists()

    assert [(p.id, p.item_count) for p in playlists] == [("p1", 3), ("p3", 7)]
    _, kwargs = request.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer user-token"


def test_add_to_playlist_batches_by_100(monkeypatch, tmp_path):
    request = MagicMock(return_value=FakeApiResponse({"snapshot_id": "s"}))
    monkeypatch.setattr(requests, "request", request)
    uris = [f"spotify:track:{i}" for i in range(150)]

    added = _user_client(tmp_path, _valid_token()).add_to_playlist("p1", uris)

    assert added == 150
    assert request.call_count == 2
    first, second = request.call_args_list
    assert first.args == ("POST", "https://api.spotify.com/v1/playlists/p1/items")
    assert len(first.kwargs["json"]["uris"]) == 100
    assert len(second.kwargs["json"]["uris"]) == 50


def test_get_album_tracks(monkeypatch, tmp_path):
    payload = {
        "items": [{"track_number": 1, "name": "So What", "uri": "spotify:track:a"}],
        "next": None,
    }
    monkeypatch.setattr(requests, "request", MagicMock(return_value=FakeApiResponse(payload)))

    tracks = _user_client(tmp_path, _valid_token()).get_album_tracks("album1")

    assert [(t.track_number, t.name, t.uri) for t in tracks] == [
        (1, "So What", "spotify:track:a")
    ]


def test_expired_token_is_refreshed_and_cached(monkeypatch, tmp_path):
    post = MagicMock(
        return_value=FakeResponse({"access_token": "fresh", "expires_in": 3600})
    )
    request = MagicMock(return_value=FakeApiResponse({"id": "me"}))
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "request", request)
    client = _user_client(
        tmp_path, {"access_token": "old", "refresh_token": "r", "expires_at": 0}
    )

    client._current_user_id()

    assert post.call_args.kwargs["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "r",
    }
    cached = json.loads(client.token_cache.read_text())
    assert cached["access_token"] == "fresh"
    assert cached["refresh_token"] == "r"
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer fresh"
