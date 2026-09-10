from __future__ import annotations

import json
import os
import tempfile
import warnings
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .behaviour.profiles import get_profile
from .keybindings import parse_hotkey_binding, risky_binding_reason, same_binding


CONFIG_SCHEMA_VERSION = 2
DEFAULT_PROFILE = "natural"
DEFAULT_SPEED = 40.0
DEFAULT_TYPO_RATE = 0.0
DEFAULT_COUNTDOWN = 5.0
DEFAULT_PROGRESS = False
DEFAULT_PAUSE_KEY = "PAUSE"
DEFAULT_STOP_KEY = "CTRL+PAUSE"


class ConfigError(ValueError):
    """Raised when persisted configuration cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class HotkeyConfig:
    pause_key: str = DEFAULT_PAUSE_KEY
    stop_key: str = DEFAULT_STOP_KEY

    def __post_init__(self) -> None:
        try:
            pause = parse_hotkey_binding(self.pause_key)
            stop = parse_hotkey_binding(self.stop_key)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        if same_binding(pause, stop):
            raise ConfigError("pause_key and stop_key must be different")
        for name, binding in (("pause", pause), ("stop", stop)):
            reason = risky_binding_reason(binding)
            if reason is not None:
                warnings.warn(
                    f"Risky {name} hotkey {getattr(self, name + '_key')!r}: {reason}. "
                    "The binding is allowed, but keyboard-mode polling cannot distinguish it from matching generated input.",
                    RuntimeWarning,
                    stacklevel=2,
                )


@dataclass(frozen=True, slots=True)
class AppSettings:
    profile: str = DEFAULT_PROFILE
    speed: float = DEFAULT_SPEED
    typo_rate: float = DEFAULT_TYPO_RATE
    countdown: float = DEFAULT_COUNTDOWN
    progress: bool = DEFAULT_PROGRESS
    hotkeys: HotkeyConfig = HotkeyConfig()

    def __post_init__(self) -> None:
        _validate_profile(self.profile)
        _validate_positive_number("speed", self.speed)
        _validate_typo_rate(self.typo_rate)
        _validate_non_negative_number("countdown", self.countdown)
        _validate_bool("progress", self.progress)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "version": CONFIG_SCHEMA_VERSION,
            "profile": self.profile,
            "speed": self.speed,
            "typo_rate": self.typo_rate,
            "countdown": self.countdown,
            "progress": self.progress,
            "hotkeys": {
                "pause": self.hotkeys.pause_key,
                "stop": self.hotkeys.stop_key,
            },
        }

    def with_overrides(self, **overrides: object) -> "AppSettings":
        return replace(self, **overrides)


@dataclass(frozen=True, slots=True)
class TypingConfig:
    words_per_minute: float = 40.0
    countdown_seconds: float = 5.0
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        if self.words_per_minute <= 0:
            raise ValueError("words_per_minute must be positive")
        if self.countdown_seconds < 0:
            raise ValueError("countdown_seconds must be non-negative")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")

    @property
    def seconds_per_character(self) -> float:
        return 60.0 / (self.words_per_minute * 5.0)


def default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ConfigError("APPDATA is not set; cannot resolve the default AutoTyper config path")
    return Path(appdata) / "AutoTyper" / "config.json"


def load_settings(path: Path, *, allow_missing: bool = False) -> AppSettings | None:
    resolved = path.expanduser()
    if not resolved.exists():
        if allow_missing:
            return None
        raise ConfigError(f"Configuration file does not exist: {resolved}")
    if not resolved.is_file():
        raise ConfigError(f"Configuration path is not a file: {resolved}")

    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Malformed configuration file {resolved}: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read configuration file: {resolved}") from exc

    return _settings_from_mapping(payload, source=resolved)


def save_settings(path: Path, settings: AppSettings) -> None:
    resolved = path.expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=resolved.parent,
            prefix=f"{resolved.name}.",
            suffix=".tmp",
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(settings.to_json_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, resolved)
    except OSError as exc:
        raise ConfigError(f"Could not write configuration file: {resolved}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _settings_from_mapping(payload: Any, *, source: Path) -> AppSettings:
    if not isinstance(payload, Mapping):
        raise ConfigError(f"Configuration file must contain a JSON object: {source}")

    version = payload.get("version")
    _validate_version(version, source=source)

    allowed_keys = {"version", "profile", "speed", "typo_rate", "countdown", "progress"}
    if version == 2:
        allowed_keys.add("hotkeys")
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        raise ConfigError(f"Unknown configuration keys in {source}: {', '.join(unknown_keys)}")

    settings = DEFAULT_SETTINGS
    if "profile" in payload:
        settings = settings.with_overrides(profile=_parse_profile(payload["profile"], source=source))
    if "speed" in payload:
        settings = settings.with_overrides(speed=_parse_positive_number("speed", payload["speed"], source=source))
    if "typo_rate" in payload:
        settings = settings.with_overrides(typo_rate=_parse_typo_rate(payload["typo_rate"], source=source))
    if "countdown" in payload:
        settings = settings.with_overrides(countdown=_parse_non_negative_number("countdown", payload["countdown"], source=source))
    if "progress" in payload:
        settings = settings.with_overrides(progress=_parse_bool("progress", payload["progress"], source=source))
    if version == 2 and "hotkeys" in payload:
        settings = settings.with_overrides(hotkeys=_parse_hotkeys(payload["hotkeys"], source=source))

    return settings


def _validate_version(version: Any, *, source: Path) -> None:
    if isinstance(version, bool) or not isinstance(version, int):
        raise ConfigError(f"Configuration version must be an integer in {source}")
    if version not in {1, 2}:
        raise ConfigError(f"Unsupported configuration version in {source}: {version}")


def _parse_hotkeys(value: Any, *, source: Path) -> HotkeyConfig:
    if not isinstance(value, Mapping):
        raise ConfigError(f"Invalid value for hotkeys in {source}: expected an object")
    unknown_keys = sorted(set(value) - {"pause", "stop"})
    if unknown_keys:
        raise ConfigError(f"Unknown hotkey keys in {source}: {', '.join(unknown_keys)}")
    try:
        return HotkeyConfig(
            pause_key=value.get("pause", DEFAULT_PAUSE_KEY),
            stop_key=value.get("stop", DEFAULT_STOP_KEY),
        )
    except (ConfigError, TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid hotkeys in {source}: {exc}") from exc


def _parse_profile(value: Any, *, source: Path) -> str:
    _validate_profile(value, source=source)
    return str(value)


def _parse_positive_number(name: str, value: Any, *, source: Path) -> float:
    _validate_positive_number(name, value, source=source)
    return float(value)


def _parse_non_negative_number(name: str, value: Any, *, source: Path) -> float:
    _validate_non_negative_number(name, value, source=source)
    return float(value)


def _parse_typo_rate(value: Any, *, source: Path) -> float:
    _validate_typo_rate(value, source=source)
    return float(value)


def _parse_bool(name: str, value: Any, *, source: Path) -> bool:
    _validate_bool(name, value, source=source)
    return bool(value)


def _validate_profile(value: Any, *, source: Path | None = None) -> None:
    if not isinstance(value, str):
        location = f" in {source}" if source is not None else ""
        raise ConfigError(f"Profile must be a string{location}")
    try:
        get_profile(value)
    except ValueError as exc:
        location = f" in {source}" if source is not None else ""
        raise ConfigError(f"Invalid profile{location}: {value!r}") from exc


def _validate_positive_number(name: str, value: Any, *, source: Path | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _config_type_error(name, "a positive number", source)
    if float(value) <= 0:
        raise _config_range_error(name, "must be greater than 0", source)


def _validate_non_negative_number(name: str, value: Any, *, source: Path | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _config_type_error(name, "a non-negative number", source)
    if float(value) < 0:
        raise _config_range_error(name, "must be greater than or equal to 0", source)


def _validate_typo_rate(value: Any, *, source: Path | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _config_type_error("typo_rate", "a number between 0.0 and 0.10", source)
    numeric = float(value)
    if numeric < 0 or numeric > 0.10:
        raise _config_range_error("typo_rate", "must be between 0.0 and 0.10", source)


def _validate_bool(name: str, value: Any, *, source: Path | None = None) -> None:
    if not isinstance(value, bool):
        raise _config_type_error(name, "a boolean", source)


def _config_type_error(name: str, expected: str, source: Path | None) -> ConfigError:
    location = f" in {source}" if source is not None else ""
    return ConfigError(f"Invalid value for {name}{location}: expected {expected}")


def _config_range_error(name: str, message: str, source: Path | None) -> ConfigError:
    location = f" in {source}" if source is not None else ""
    return ConfigError(f"Invalid value for {name}{location}: {message}")


DEFAULT_SETTINGS = AppSettings()
