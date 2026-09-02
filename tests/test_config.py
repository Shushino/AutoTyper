from __future__ import annotations

import json
from pathlib import Path

import pytest

from autotype.config import (
    AppSettings,
    ConfigError,
    DEFAULT_SETTINGS,
    default_config_path,
    load_settings,
    save_settings,
)


def _write_config(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_default_config_path_uses_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert default_config_path() == tmp_path / "AutoTyper" / "config.json"


def test_missing_default_config_file_can_be_ignored(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert load_settings(default_config_path(), allow_missing=True) is None


def test_valid_config_loading_uses_file_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write_config(
        path,
        {
            "version": 1,
            "profile": "careful",
            "speed": 110,
            "typo_rate": 0.05,
            "countdown": 2,
            "progress": True,
        },
    )

    settings = load_settings(path)

    assert settings == AppSettings(profile="careful", speed=110.0, typo_rate=0.05, countdown=2.0, progress=True)


def test_partial_config_uses_built_in_defaults_for_unspecified_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write_config(
        path,
        {
            "version": 1,
            "speed": 88.5,
        },
    )

    settings = load_settings(path)

    assert settings == AppSettings(
        profile=DEFAULT_SETTINGS.profile,
        speed=88.5,
        typo_rate=DEFAULT_SETTINGS.typo_rate,
        countdown=DEFAULT_SETTINGS.countdown,
        progress=DEFAULT_SETTINGS.progress,
    )


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write_config(path, {"version": 1, "unexpected": True})

    with pytest.raises(ConfigError, match="Unknown configuration keys"):
        load_settings(path)


def test_unsupported_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write_config(path, {"version": 2})

    with pytest.raises(ConfigError, match="Unsupported configuration version"):
        load_settings(path)


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ConfigError, match="Malformed configuration file"):
        load_settings(path)


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ({"version": 1, "speed": "fast"}, "Invalid value for speed"),
        ({"version": 1, "typo_rate": 0.5}, "typo_rate"),
        ({"version": 1, "countdown": -1}, "countdown"),
        ({"version": 1, "progress": "true"}, "progress"),
        ({"version": 1, "profile": 123}, "Profile must be a string"),
        ({"version": 1, "profile": "experimental"}, "Invalid profile"),
    ],
)
def test_invalid_types_and_ranges_are_rejected(tmp_path: Path, payload: dict[str, object], expected_message: str) -> None:
    path = tmp_path / "config.json"
    _write_config(path, payload)

    with pytest.raises(ConfigError, match=expected_message):
        load_settings(path)


def test_save_settings_writes_versioned_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    settings = AppSettings(profile="precise", speed=110.0, typo_rate=0.05, countdown=3.0, progress=True)

    save_settings(path, settings)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": 1,
        "profile": "precise",
        "speed": 110.0,
        "typo_rate": 0.05,
        "countdown": 3.0,
        "progress": True,
    }
