"""File I/O for .automaton/config.toml — the sole source of plugin config."""

from __future__ import annotations

import json
import tomllib
from typing import TYPE_CHECKING, Any

from scripts.core.constants import AUTOMATON_CONFIG_DIR, AUTOMATON_CONFIG_FILENAME
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
    """Read .automaton/config.toml from root. Return {} if absent."""
    config_file = root / AUTOMATON_CONFIG_DIR / AUTOMATON_CONFIG_FILENAME
    if not config_file.exists():
        return {}
    try:
        with config_file.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            key=AUTOMATON_CONFIG_FILENAME,
            reason=f"invalid TOML: {exc}",
        ) from exc


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
    """Write .automaton/config.toml. Creates directory if absent."""
    config_dir = root / AUTOMATON_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / AUTOMATON_CONFIG_FILENAME).write_text(
        _render_config(
            enabled=enabled,
            wiki=wiki,
            daily=daily,
            sources=sources,
            after_hour=after_hour,
        ),
        encoding="utf-8",
    )


def update_enabled(root: Path, *, enabled: bool) -> bool:
    """Toggle enabled field in .automaton/config.toml.

    Returns True if state changed. Raises ConfigError if config.toml is absent.
    Preserves all other fields (paths, compile).
    """
    config_dir = root / AUTOMATON_CONFIG_DIR
    config_file = config_dir / AUTOMATON_CONFIG_FILENAME
    if not config_file.exists():
        raise ConfigError(
            key=AUTOMATON_CONFIG_FILENAME,
            reason="not found — run `automaton:wiki setup` first",
        )
    try:
        with config_file.open("rb") as f:
            raw: dict[str, Any] = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            key=AUTOMATON_CONFIG_FILENAME,
            reason=f"invalid TOML: {exc}",
        ) from exc
    current = bool(raw.get("enabled", False))
    if current == enabled:
        return False
    raw["enabled"] = enabled
    config_file.write_text(_render_raw_config(raw), encoding="utf-8")
    return True


def _render_config(
    *,
    enabled: bool,
    wiki: str,
    daily: str,
    sources: str,
    after_hour: int,
) -> str:
    return (
        f"enabled = {str(enabled).lower()}\n"
        "\n"
        "[paths]\n"
        f'wiki = "{wiki}"\n'
        f'daily = "{daily}"\n'
        f'sources = "{sources}"\n'
        "\n"
        "[compile]\n"
        f"after_hour = {after_hour}\n"
    )


def _render_raw_config(data: dict[str, Any]) -> str:
    """Serialize flat + one-level-table dict to TOML. Top-level scalars first."""
    lines: list[str] = []
    for key, val in data.items():
        if not isinstance(val, dict):
            lines.append(_toml_scalar_line(key, val))
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append("")
            lines.append(f"[{key}]")
            for k, v in val.items():
                lines.append(_toml_scalar_line(k, v))
    return "\n".join(lines) + "\n"


def _toml_scalar_line(key: str, val: Any) -> str:
    if isinstance(val, bool):
        return f"{key} = {str(val).lower()}"
    if isinstance(val, int):
        return f"{key} = {val}"
    if isinstance(val, float):
        return f"{key} = {val}"
    return f"{key} = {json.dumps(str(val))}"
