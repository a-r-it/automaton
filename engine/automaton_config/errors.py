"""Config error types."""

from __future__ import annotations

__all__ = ("ConfigError",)


class ConfigError(Exception):
    """Raised on malformed TOML, unsupported value types, or missing required config."""

    def __init__(self, *, key: str, reason: str) -> None:
        self.key = key
        self.reason = reason
        super().__init__(f"{key}: {reason}")
