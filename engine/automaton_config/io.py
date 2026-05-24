"""TOML config I/O for .automaton/config.toml."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any, Final

from automaton_config.errors import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = (
    "CONFIG_DIR",
    "CONFIG_FILENAME",
    "read",
    "read_file",
    "write",
    "write_file",
)

CONFIG_DIR: Final = ".automaton"
CONFIG_FILENAME: Final = "config.toml"


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


def read(root: Path) -> dict[str, Any]:
    """Read .automaton/config.toml from project root. Return {} if absent."""
    return read_file(root / CONFIG_DIR / CONFIG_FILENAME)


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


def write(root: Path, data: dict[str, Any]) -> None:
    """Write .automaton/config.toml at project root."""
    write_file(root / CONFIG_DIR / CONFIG_FILENAME, data)


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
