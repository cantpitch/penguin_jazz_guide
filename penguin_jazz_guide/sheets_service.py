"""Google Sheets access via gspread service-account auth."""

from __future__ import annotations

import json
from pathlib import Path

import gspread
from google.auth.exceptions import GoogleAuthError
from gspread.exceptions import APIError, SpreadsheetNotFound

from .config import Config
from .models import AlbumSelection

HEADER = ["Listened", "Artist Name", "Album Name", "Song Name", "Album URL"]


class SheetsError(Exception):
    """Raised when a Google Sheets interaction fails."""


class SheetsService:
    """Wrapper over gspread for appending Penguin Jazz Guide rows."""

    def __init__(self, worksheet):
        self.worksheet = worksheet

    @classmethod
    def from_config(cls, config: Config) -> "SheetsService":
        try:
            client = gspread.service_account(filename=str(Path(config.service_account_file)))
        except (FileNotFoundError, IsADirectoryError, PermissionError) as exc:
            raise SheetsError(
                "Failed to open Google Sheet: cannot read service account JSON "
                f"file at {config.service_account_file} ({_format_exception(exc)}). "
                "Verify google.service_account_file points to a readable JSON key "
                "file, not a folder."
            ) from exc
        except GoogleAuthError as exc:
            raise SheetsError(
                "Failed to open Google Sheet: Google authentication failed "
                f"({type(exc).__name__}: {exc}). Verify "
                f"google.service_account_file: {config.service_account_file}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise SheetsError(
                "Failed to open Google Sheet: failed to load service account "
                f"credentials from {config.service_account_file} "
                f"({_format_exception(exc)})."
            ) from exc

        try:
            if config.spreadsheet_id:
                spreadsheet = client.open_by_key(config.spreadsheet_id)
            else:
                spreadsheet = client.open(config.spreadsheet_name)
            worksheet = cls._get_or_create_worksheet(spreadsheet, config.worksheet_name)
        except SpreadsheetNotFound as exc:
            target = _spreadsheet_target(config)
            raise SheetsError(
                "Failed to open Google Sheet: spreadsheet not found or not shared "
                f"with the service account ({target}). Share the sheet with the "
                f"service account ({_service_account_email(config)}), and verify the "
                "spreadsheet id/name in config.toml."
            ) from exc
        except PermissionError as exc:
            target = _spreadsheet_target(config)
            raise SheetsError(
                "Failed to open Google Sheet: Google denied access to the "
                f"spreadsheet ({target}) ({_format_exception(exc)}). Share the "
                f"sheet with the service account ({_service_account_email(config)}), "
                "and confirm it has Editor access."
            ) from exc
        except GoogleAuthError as exc:
            raise SheetsError(
                "Failed to open Google Sheet: Google authentication failed "
                f"({type(exc).__name__}: {exc}). Verify "
                f"google.service_account_file: {config.service_account_file}"
            ) from exc
        except APIError as exc:
            raise SheetsError(
                "Failed to open Google Sheet: Google API error "
                f"({_format_exception(exc)}). Ensure the Google Sheets API and "
                "Google Drive API are enabled for the service account project."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise SheetsError(
                f"Failed to open Google Sheet: {_format_exception(exc)}"
            ) from exc

        service = cls(worksheet)
        service.ensure_header()
        return service

    @staticmethod
    def _get_or_create_worksheet(spreadsheet, name: str):
        try:
            return spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=name, rows=100, cols=len(HEADER))

    def ensure_header(self) -> None:
        """Write the header row if the worksheet is empty."""
        try:
            existing = self.worksheet.row_values(1)
        except Exception as exc:  # noqa: BLE001
            raise SheetsError(f"Failed to read worksheet header: {exc}") from exc
        if not existing:
            self.worksheet.update([HEADER], "A1")

    def append_album(self, selection: AlbumSelection) -> int:
        """Append one row per track. Returns the number of rows written."""
        rows = self.build_rows(selection)
        if not rows:
            return 0
        try:
            self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        except Exception as exc:  # noqa: BLE001
            raise SheetsError(f"Failed to append rows: {exc}") from exc
        return len(rows)

    @staticmethod
    def build_rows(selection: AlbumSelection) -> list[list[str]]:
        """Build sheet rows (Listened, Artist, Album, Song, URL) per track."""
        artist = selection.release.artist
        album = selection.release.album_name
        return [
            [
                "",
                artist,
                album,
                track.title,
                selection.album_url if index == 0 and selection.album_url else "",
            ]
            for index, track in enumerate(selection.tracks)
        ]


def _spreadsheet_target(config: Config) -> str:
    if config.spreadsheet_id:
        return f"spreadsheet_id={config.spreadsheet_id}"
    return f"spreadsheet_name={config.spreadsheet_name}"


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__


def _service_account_email(config: Config) -> str:
    try:
        with Path(config.service_account_file).open("r", encoding="utf-8") as fh:
            email = json.load(fh).get("client_email")
    except (OSError, json.JSONDecodeError):
        email = None
    return email or "client_email from your service account JSON"
