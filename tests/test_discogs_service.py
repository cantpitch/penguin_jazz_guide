from penguin_jazz_guide.discogs_service import (
    DiscogsService,
    _country_rank,
    _extract_format_names,
)
from penguin_jazz_guide.models import ReleaseMatch


def make_service():
    service = DiscogsService.__new__(DiscogsService)
    service.country_preference = ["US", "Japan", "Europe"]
    return service


def test_extract_format_names_from_dicts():
    formats = [{"name": "CD", "qty": "1"}, {"name": "Album"}]
    assert _extract_format_names(formats) == ["CD", "Album"]


def test_extract_format_names_handles_none():
    assert _extract_format_names(None) == []


def test_country_rank_orders_preference():
    pref = ["US", "Japan", "Europe"]
    assert _country_rank("US", pref) == 0
    assert _country_rank("Japan", pref) == 1
    assert _country_rank("Brazil", pref) == len(pref)
    assert _country_rank(None, pref) == len(pref) + 1


def test_sort_by_preference():
    service = make_service()
    matches = [
        ReleaseMatch(1, "A", "Artist", 1960, "Brazil"),
        ReleaseMatch(2, "B", "Artist", 1959, "Japan"),
        ReleaseMatch(3, "C", "Artist", 1961, "US"),
        ReleaseMatch(4, "D", "Artist", 1958, "US"),
    ]
    ordered = service.sort_by_preference(matches)
    # US first (oldest US first), then Japan, then Brazil.
    assert [m.id for m in ordered] == [4, 3, 2, 1]


def test_album_name_strips_artist_prefix():
    match = ReleaseMatch(1, "Miles Davis - Kind Of Blue", "Miles Davis", 1959, "US")
    assert match.album_name == "Kind Of Blue"


def test_album_name_without_prefix():
    match = ReleaseMatch(1, "Kind Of Blue", "Miles Davis", 1959, "US")
    assert match.album_name == "Kind Of Blue"
