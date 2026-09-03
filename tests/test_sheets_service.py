from unittest.mock import MagicMock

import gspread
import pytest

from penguin_jazz_guide.config import Config
from penguin_jazz_guide.models import AlbumSelection, ReleaseMatch, Track
from penguin_jazz_guide.sheets_service import HEADER, SheetsError, SheetsService


def make_selection():
    release = ReleaseMatch(
        id=1,
        title="Miles Davis - Kind Of Blue",
        artist="Miles Davis",
        year=1959,
        country="US",
    )
    tracks = [Track("A1", "So What"), Track("A2", "Freddie Freeloader")]
    return AlbumSelection(release=release, tracks=tracks)


def make_config(service_account):
    return Config(
        discogs_token="discogs-token",
        spotify_client_id=None,
        spotify_client_secret=None,
        service_account_file=service_account,
        spreadsheet_id="sheet-id",
        spreadsheet_name=None,
        worksheet_name="Sheet1",
        country_preference=["US"],
        user_agent="test",
    )


def test_build_rows_one_per_track():
    rows = SheetsService.build_rows(make_selection())
    assert rows == [
        ["", "Miles Davis", "Kind Of Blue", "So What", ""],
        ["", "Miles Davis", "Kind Of Blue", "Freddie Freeloader", ""],
    ]


def test_build_rows_puts_album_url_on_first_track_only():
    selection = make_selection()
    selection.album_url = "https://open.spotify.com/album/abc"
    rows = SheetsService.build_rows(selection)
    assert rows[0][4] == "https://open.spotify.com/album/abc"
    assert rows[1][4] == ""


def test_build_rows_empty_tracks():
    selection = AlbumSelection(
        release=ReleaseMatch(1, "X", "Artist", 1960, "US"), tracks=[]
    )
    assert SheetsService.build_rows(selection) == []


def test_ensure_header_writes_when_empty():
    worksheet = MagicMock()
    worksheet.row_values.return_value = []
    service = SheetsService(worksheet)
    service.ensure_header()
    worksheet.update.assert_called_once_with([HEADER], "A1")


def test_ensure_header_skips_when_present():
    worksheet = MagicMock()
    worksheet.row_values.return_value = HEADER
    service = SheetsService(worksheet)
    service.ensure_header()
    worksheet.update.assert_not_called()


def test_append_album_appends_rows():
    worksheet = MagicMock()
    service = SheetsService(worksheet)
    count = service.append_album(make_selection())
    assert count == 2
    worksheet.append_rows.assert_called_once()
    args, kwargs = worksheet.append_rows.call_args
    assert len(args[0]) == 2
    assert kwargs["value_input_option"] == "USER_ENTERED"


def test_append_album_no_tracks_writes_nothing():
    worksheet = MagicMock()
    service = SheetsService(worksheet)
    selection = AlbumSelection(
        release=ReleaseMatch(1, "X", "Artist", 1960, "US"), tracks=[]
    )
    assert service.append_album(selection) == 0
    worksheet.append_rows.assert_not_called()


def test_from_config_explains_empty_spreadsheet_not_found(monkeypatch, tmp_path):
    service_account = tmp_path / "sa.json"
    service_account.write_text('{"client_email": "svc@example.iam.gserviceaccount.com"}')
    config = make_config(service_account)

    client = MagicMock()
    client.open_by_key.side_effect = gspread.exceptions.SpreadsheetNotFound()
    monkeypatch.setattr(gspread, "service_account", MagicMock(return_value=client))

    with pytest.raises(SheetsError) as exc_info:
        SheetsService.from_config(config)

    message = str(exc_info.value)
    assert "spreadsheet not found or not shared" in message
    assert "svc@example.iam.gserviceaccount.com" in message
    assert "sheet-id" in message


def test_from_config_includes_exception_type_when_message_is_blank(
    monkeypatch, tmp_path
):
    service_account = tmp_path / "sa.json"
    service_account.write_text("{}")
    config = make_config(service_account)

    class BlankError(Exception):
        def __str__(self):
            return ""

    monkeypatch.setattr(gspread, "service_account", MagicMock(side_effect=BlankError()))

    with pytest.raises(SheetsError) as exc_info:
        SheetsService.from_config(config)

    assert "failed to load service account credentials" in str(exc_info.value)
    assert "BlankError" in str(exc_info.value)


def test_from_config_explains_service_account_permission_error(
    monkeypatch, tmp_path
):
    service_account = tmp_path / "sa.json"
    service_account.write_text("{}")
    config = make_config(service_account)

    monkeypatch.setattr(
        gspread, "service_account", MagicMock(side_effect=PermissionError())
    )

    with pytest.raises(SheetsError) as exc_info:
        SheetsService.from_config(config)

    message = str(exc_info.value)
    assert "cannot read service account JSON file" in message
    assert str(service_account) in message
    assert "PermissionError" in message


def test_from_config_explains_spreadsheet_permission_error(monkeypatch, tmp_path):
    service_account = tmp_path / "sa.json"
    service_account.write_text('{"client_email": "svc@example.iam.gserviceaccount.com"}')
    config = make_config(service_account)

    client = MagicMock()
    client.open_by_key.side_effect = PermissionError()
    monkeypatch.setattr(gspread, "service_account", MagicMock(return_value=client))

    with pytest.raises(SheetsError) as exc_info:
        SheetsService.from_config(config)

    message = str(exc_info.value)
    assert "Google denied access to the spreadsheet" in message
    assert "svc@example.iam.gserviceaccount.com" in message
    assert "Editor access" in message
    assert "sheet-id" in message
