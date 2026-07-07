"""TOML config I/O for .automaton/<plugin>/config.toml (user <- project layered)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final

from automaton_config.errors import ConfigError

__all__ = (
    "CONFIG_DIR",
    "CONFIG_FILENAME",
    "DEFAULT_PLUGIN",
    "read",
    "read_file",
    "read_project",
    "write",
    "write_file",
)

CONFIG_DIR: Final = ".automaton"
CONFIG_FILENAME: Final = "config.toml"
DEFAULT_PLUGIN: Final = "mnemic"


def read_file(path: Path) -> dict[str, Any]:
    """Read any TOML file. Return {} if absent.

    Raises ConfigError on malformed TOML.
    """
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            key=str(path),
            reason=f"invalid TOML: {exc}",
        ) from exc


def read_project(root: Path, plugin: str = DEFAULT_PLUGIN) -> dict[str, Any]:
    """Read only the project-scope config (no user overlay). Return {} if absent."""
    return read_file(root / _rel(plugin))


def read(root: Path, plugin: str = DEFAULT_PLUGIN) -> dict[str, Any]:
    """Read layered config: user (~) overlaid by project (root). Project wins.

    Both scopes live at ``<scope>/.automaton/<plugin>/config.toml``. Returns
    {} when neither scope file exists. Raises ConfigError when a key is a
    table in one scope and a scalar in the other.
    """
    user = read_file(Path.home() / _rel(plugin))
    project = read_file(root / _rel(plugin))
    return _deep_merge(user, project)


def write_file(path: Path, data: dict[str, Any]) -> None:
    """Serialize dict to TOML file. Creates parent dirs if absent.

    Supported value types: str, bool, int, float.
    Tables: one level of dict[str, scalar].
    Raises ConfigError on unsupported types.
    """
    lines: list[str] = []
    for key, val in data.items():
        if not isinstance(val, dict):
            lines.append(_scalar_line(key, val))
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append("")
            lines.append(f"[{key}]")
            for k, v in val.items():
                _reject_unsupported(k, v)
                lines.append(_scalar_line(k, v))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write(root: Path, data: dict[str, Any], plugin: str = DEFAULT_PLUGIN) -> None:
    """Write the project-scope config."""
    write_file(root / _rel(plugin), data)


def _rel(plugin: str) -> Path:
    return Path(CONFIG_DIR) / plugin / CONFIG_FILENAME


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, val in override.items():
        cur = out.get(key)
        if key in out and isinstance(cur, dict) != isinstance(val, dict):
            raise ConfigError(key=key, reason="type conflict between user and project config")
        if isinstance(val, dict) and isinstance(cur, dict):
            out[key] = _deep_merge(cur, val)
        else:
            out[key] = val
    return out


def _scalar_line(key: str, val: Any) -> str:
    _reject_unsupported(key, val)
    if isinstance(val, bool):
        return f"{key} = {str(val).lower()}"
    if isinstance(val, int):
        return f"{key} = {val}"
    if isinstance(val, float):
        return f"{key} = {val}"
    return f'{key} = "{val}"'


def _reject_unsupported(key: str, val: Any) -> None:
    if isinstance(val, dict):
        raise ConfigError(
            key=key,
            reason=f"nested dicts not supported, got dict at {key!r}",
        )
    if not isinstance(val, str | bool | int | float):
        raise ConfigError(
            key=key,
            reason=f"unsupported type {type(val).__name__!r} for key {key!r}",
        )
