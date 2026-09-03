"""Configuration loading and validation."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config.toml")
DEFAULT_WORKSHEET = "Sheet1"
DEFAULT_COUNTRY_PREFERENCE = ["US", "Japan", "Europe", "UK"]


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

    def validate(self) -> None:
        if not self.discogs_token:
            raise ConfigError("Missing 'discogs.token' in config.")
        if bool(self.spotify_client_id) != bool(self.spotify_client_secret):
            raise ConfigError(
                "Provide both 'spotify.client_id' and 'spotify.client_secret', "
                "or omit both to skip Spotify album lookup."
            )
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


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load and validate configuration from a TOML file."""
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
    )
    config.validate()
    return config
