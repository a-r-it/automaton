"""File I/O for .automaton/mnemic/config.toml — delegates to automaton_config."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import automaton_config
from automaton_config.errors import ConfigError as _EngineConfigError

from scripts.core.errors import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = (
    "read_config_toml",
    "read_enabled",
    "update_enabled",
    "write_config",
)


def read_config_toml(root: Path) -> dict[str, Any]:
    """Read .automaton/mnemic/config.toml from root. Return {} if absent."""
    try:
        return automaton_config.read(root)
    except _EngineConfigError as exc:
        raise ConfigError(key=str(exc.key), reason=exc.reason) from exc


def read_enabled(root: Path) -> bool:
    """Return enabled field from config.toml. False if file absent."""
    return bool(read_config_toml(root).get("enabled", False))


def write_config(
    root: Path,
    *,
    wiki: str,
    daily: str,
    sources: str,
    after_hour: int,
    enabled: bool,
) -> None:
    """Write .automaton/mnemic/config.toml with wiki-specific structure."""
    data: dict[str, Any] = {
        "enabled": enabled,
        "paths": {"wiki": wiki, "daily": daily, "sources": sources},
        "compile": {"after_hour": after_hour},
    }
    automaton_config.write(root, data)


def update_enabled(root: Path, *, enabled: bool) -> bool:
    """Toggle enabled in the project-scope .automaton/mnemic/config.toml.

    Reads and writes the project scope only — never bakes user-scope
    overrides into the project file. Returns True if state changed.
    Raises ConfigError if the project config is absent.
    """
    try:
        raw = automaton_config.read_project(root)
    except _EngineConfigError as exc:
        raise ConfigError(key=str(exc.key), reason=exc.reason) from exc

    if not raw:
        raise ConfigError(
            key=automaton_config.CONFIG_FILENAME,
            reason="not found — run `mnemic:wiki setup` first",
        )

    current = bool(raw.get("enabled", False))
    if current == enabled:
        return False
    raw["enabled"] = enabled
    automaton_config.write(root, raw)
    return True
