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
        requests, "post", MagicMock(return_value=FakeResponse({"access_token": "token"}))
    )
    monkeypatch.setattr(
        requests, "get", MagicMock(return_value=FakeResponse({"albums": {"items": []}}))
    )

    service = SpotifyService("client-id", "client-secret")
    assert service.search_albums("Artist", "Album") == []


def test_missing_access_token_raises(monkeypatch):
    monkeypatch.setattr(requests, "post", MagicMock(return_value=FakeResponse({})))

    service = SpotifyService("client-id", "client-secret")
    with pytest.raises(SpotifyError, match="access_token"):
        service.search_albums("Artist", "Album")


def test_search_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        requests, "post", MagicMock(return_value=FakeResponse({"access_token": "token"}))
    )
    monkeypatch.setattr(
        requests,
        "get",
        MagicMock(return_value=FakeResponse({}, requests.HTTPError("boom"))),
    )

    service = SpotifyService("client-id", "client-secret")
    with pytest.raises(SpotifyError, match="Spotify album search failed"):
        service.search_albums("Artist", "Album")
