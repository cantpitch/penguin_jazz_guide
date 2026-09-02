import pytest

from penguin_jazz_guide.config import Config, ConfigError, load_config


def write_config(tmp_path, body: str):
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_load_config_valid(tmp_path):
    sa = tmp_path / "sa.json"
    sa.write_text("{}")
    path = write_config(
        tmp_path,
        f"""
[discogs]
token = "abc"
country_preference = ["US", "Japan"]

[google]
service_account_file = "{sa}"
spreadsheet_id = "sheet123"
worksheet_name = "Data"
""",
    )
    config = load_config(path)
    assert config.discogs_token == "abc"
    assert config.spreadsheet_id == "sheet123"
    assert config.worksheet_name == "Data"
    assert config.country_preference == ["US", "Japan"]


def test_service_account_path_resolves_relative_to_config(tmp_path):
    sa = tmp_path / "service_account.json"
    sa.write_text("{}")
    path = write_config(
        tmp_path,
        """
[discogs]
token = "abc"

[google]
service_account_file = "service_account.json"
spreadsheet_id = "sheet123"
""",
    )
    config = load_config(path)
    assert config.service_account_file == sa


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.toml")


def test_missing_token_raises(tmp_path):
    sa = tmp_path / "sa.json"
    sa.write_text("{}")
    path = write_config(
        tmp_path,
        f"""
[discogs]
token = ""

[google]
service_account_file = "{sa}"
spreadsheet_id = "s"
""",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_spreadsheet_target_raises(tmp_path):
    sa = tmp_path / "sa.json"
    sa.write_text("{}")
    path = write_config(
        tmp_path,
        f"""
[discogs]
token = "abc"

[google]
service_account_file = "{sa}"
""",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_service_account_file_raises(tmp_path):
    path = write_config(
        tmp_path,
        """
[discogs]
token = "abc"

[google]
service_account_file = "does_not_exist.json"
spreadsheet_id = "s"
""",
    )
    with pytest.raises(ConfigError):
        load_config(path)
