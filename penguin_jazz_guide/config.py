"""Configuration loading and validation."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config.toml")
DEFAULT_WORKSHEET = "Sheet1"
DEFAULT_COUNTRY_PREFERENCE = ["US", "Japan", "Europe", "UK"]
DEFAULT_SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_SPOTIFY_TOKEN_CACHE = ".spotify_token.json"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass
class Config:
    discogs_token: str
    spotify_client_id: str | None
    spotify_client_secret: str | None
    service_account_file: Path
    spreadsheet_id: str | None
    spreadsheet_name: str | None
    worksheet_name: str
    country_preference: list[str]
    user_agent: str
    spotify_redirect_uri: str = DEFAULT_SPOTIFY_REDIRECT_URI
    spotify_token_cache: Path = Path(DEFAULT_SPOTIFY_TOKEN_CACHE)

    def validate(
        self, require_sheets: bool = True, require_playlists: bool = False
    ) -> None:
        if not self.discogs_token:
            raise ConfigError("Missing 'discogs.token' in config.")
        if bool(self.spotify_client_id) != bool(self.spotify_client_secret):
            raise ConfigError(
                "Provide both 'spotify.client_id' and 'spotify.client_secret', "
                "or omit both to skip Spotify album lookup."
            )
        if require_sheets:
            self.validate_sheets()
        if require_playlists:
            self.validate_playlists()

    def validate_playlists(self) -> None:
        if not self.spotify_client_id or not self.spotify_client_secret:
            raise ConfigError(
                "Adding albums to a playlist requires 'spotify.client_id' and "
                "'spotify.client_secret' in config."
            )

    def validate_sheets(self) -> None:
        if self.service_account_file == Path():
            raise ConfigError("Missing 'google.service_account_file' in config.")
        if not self.service_account_file.exists():
            raise ConfigError(
                f"Service account file not found: {self.service_account_file}"
            )
        if not self.service_account_file.is_file():
            raise ConfigError(
                "Service account path must be a JSON file, not a directory: "
                f"{self.service_account_file}"
            )
        if not os.access(self.service_account_file, os.R_OK):
            raise ConfigError(
                "Service account file is not readable by the current user: "
                f"{self.service_account_file}"
            )
        if not self.spreadsheet_id and not self.spreadsheet_name:
            raise ConfigError(
                "Provide either 'google.spreadsheet_id' or "
                "'google.spreadsheet_name' in config."
            )


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    require_sheets: bool = True,
    require_playlists: bool = False,
) -> Config:
    """Load and validate configuration from a TOML file.

    ``require_sheets`` checks the Google Sheets settings and
    ``require_playlists`` checks the Spotify credentials playlist mode needs.
    """
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Copy config.example.toml to config.toml and fill it in."
        )

    with config_path.open("rb") as fh:
        data = tomllib.load(fh)

    discogs = data.get("discogs", {})
    spotify = data.get("spotify", {})
    google = data.get("google", {})

    service_account_file = google.get("service_account_file", "")
    service_account_path = (
        Path(service_account_file).expanduser() if service_account_file else Path()
    )
    if service_account_path and not service_account_path.is_absolute():
        service_account_path = (config_path.parent / service_account_path).resolve()

    token_cache = Path(
        spotify.get("token_cache", DEFAULT_SPOTIFY_TOKEN_CACHE)
    ).expanduser()
    if not token_cache.is_absolute():
        token_cache = (config_path.parent / token_cache).resolve()

    config = Config(
        discogs_token=discogs.get("token", ""),
        spotify_client_id=spotify.get("client_id") or None,
        spotify_client_secret=spotify.get("client_secret") or None,
        service_account_file=service_account_path,
        spreadsheet_id=google.get("spreadsheet_id") or None,
        spreadsheet_name=google.get("spreadsheet_name") or None,
        worksheet_name=google.get("worksheet_name", DEFAULT_WORKSHEET),
        country_preference=discogs.get("country_preference", DEFAULT_COUNTRY_PREFERENCE),
        user_agent=discogs.get("user_agent", "PenguinJazzGuide/0.1"),
        spotify_redirect_uri=spotify.get(
            "redirect_uri", DEFAULT_SPOTIFY_REDIRECT_URI
        ),
        spotify_token_cache=token_cache,
    )
    config.validate(
        require_sheets=require_sheets, require_playlists=require_playlists
    )
    return config
