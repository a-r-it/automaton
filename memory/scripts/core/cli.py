"""@cli_main decorator + CliContext injection.

Scaffold:
    preflight? -> parse argv -> load config -> setup logger -> build ctx ->
    run fn(ctx) -> catch WikiError -> emit single-stderr artifact -> exit code.

Error semantics:
    WikiError raised in body/factories:  render + payload + err.exit_code
    KeyboardInterrupt:                   return ExitCode.INTERRUPTED (130)
    SystemExit from argparse parse_args: bubbles (canonical Python CLI API)
    SystemExit from body:                FORBIDDEN -- enforced by
                                         test_no_sys_exit_in_commands.py
    Any other Exception:                 bubbles with full traceback
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Protocol

from scripts.core.config import Config, load_config
from scripts.core.errors import WikiError, render
from scripts.core.exit_codes import ExitCode
from scripts.core.logging import (
    LogMode,
    resolve_log_mode,
    setup_logger,
    write_error_payload,
)

__all__ = ("CliContext", "CliContextP", "cli_main")


type ParserFactory = Callable[[], argparse.ArgumentParser]
type ConfigFactory = Callable[[], Config]
type LoggerFactory = Callable[[str, LogMode], logging.Logger]
type Preflight = Callable[[], ExitCode]

type SyncCommand = Callable[["CliContextP"], ExitCode]
type AsyncCommand = Callable[["CliContextP"], Awaitable[ExitCode]]
type AnyCommand = SyncCommand | AsyncCommand


class EntrypointP(Protocol):
    """Structural signature of the `main` callable produced by @cli_main.

    Encodes the `argv=None` default so `sys.exit(main())` (no args) is
    well-typed — a plain ``Callable[[list[str] | None], int]`` return
    annotation cannot carry default-argument information and would force
    every migrated entrypoint to write `sys.exit(main(None))`.
    """

    def __call__(self, argv: list[str] | None = None, /) -> int: ...


class CliContextP(Protocol):
    """Structural view of CliContext for body-function parameter typing.

    Attributes are exposed as read-only properties so the frozen
    ``CliContext`` dataclass satisfies the protocol (mypy rejects
    assignable-attribute protocols against frozen dataclasses).

    Test fixtures MUST construct via ``CliContext(args=..., config=...,
    log=...)`` directly. ``types.SimpleNamespace`` does NOT structurally
    satisfy this Protocol under mypy strict — SimpleNamespace attributes
    are writable, conflicting with the read-only property members here.
    """

    @property
    def args(self) -> argparse.Namespace: ...
    @property
    def config(self) -> Config: ...
    @property
    def log(self) -> logging.Logger: ...


@dataclass(frozen=True, slots=True)
class CliContext:
    """Concrete per-invocation context injected into the decorated body."""

    args: argparse.Namespace
    config: Config
    log: logging.Logger


def cli_main(
    *,
    name: str,
    parser_factory: ParserFactory,
    config_factory: ConfigFactory = load_config,
    logger_factory: LoggerFactory = setup_logger,
    preflight: Preflight | None = None,
) -> Callable[[AnyCommand], EntrypointP]:
    """Wrap an entrypoint with the standard CLI scaffold."""

    def decorate(
        fn: AnyCommand,
    ) -> EntrypointP:
        if iscoroutinefunction(fn):
            # iscoroutinefunction is a TypeGuard (Python 3.12+) that narrows
            # the AnyCommand union to its AsyncCommand arm.
            async_fn: AsyncCommand = fn

            @functools.wraps(fn)
            def async_wrapper(argv: list[str] | None = None) -> int:
                return asyncio.run(
                    _async_run(
                        async_fn,
                        argv,
                        name=name,
                        parser_factory=parser_factory,
                        config_factory=config_factory,
                        logger_factory=logger_factory,
                        preflight=preflight,
                    ),
                )

            return async_wrapper

        # Sync arm: iscoroutinefunction is a TypeGuard that narrows the
        # positive branch to AsyncCommand, but mypy does not propagate the
        # negated narrowing to the fall-through, so we coerce explicitly.
        sync_fn: SyncCommand = fn  # type: ignore[assignment]

        @functools.wraps(fn)
        def sync_wrapper(argv: list[str] | None = None) -> int:
            return _sync_run(
                sync_fn,
                argv,
                name=name,
                parser_factory=parser_factory,
                config_factory=config_factory,
                logger_factory=logger_factory,
                preflight=preflight,
            )

        return sync_wrapper

    return decorate


# --- Internal runners -------------------------------------------------


def _sync_run(
    fn: SyncCommand,
    argv: list[str] | None,
    *,
    name: str,
    parser_factory: ParserFactory,
    config_factory: ConfigFactory,
    logger_factory: LoggerFactory,
    preflight: Preflight | None,
) -> int:
    if preflight is not None:
        pf = preflight()
        if pf is not ExitCode.OK:
            return int(pf)
    mode = resolve_log_mode()
    log = logger_factory(name, mode)
    try:
        args = parser_factory().parse_args(argv)
        config = config_factory()
        ctx = CliContext(args=args, config=config, log=log)
        return int(fn(ctx))
    except WikiError as err:
        return _report_error(err, mode)
    except KeyboardInterrupt:
        return int(ExitCode.INTERRUPTED)


async def _async_run(
    fn: AsyncCommand,
    argv: list[str] | None,
    *,
    name: str,
    parser_factory: ParserFactory,
    config_factory: ConfigFactory,
    logger_factory: LoggerFactory,
    preflight: Preflight | None,
) -> int:
    if preflight is not None:
        pf = preflight()
        if pf is not ExitCode.OK:
            return int(pf)
    mode = resolve_log_mode()
    log = logger_factory(name, mode)
    try:
        args = parser_factory().parse_args(argv)
        config = config_factory()
        ctx = CliContext(args=args, config=config, log=log)
        return int(await fn(ctx))
    except WikiError as err:
        return _report_error(err, mode)
    except KeyboardInterrupt:
        return int(ExitCode.INTERRUPTED)


def _report_error(err: WikiError, mode: LogMode) -> int:
    """Emit exactly ONE artifact to stderr (human text OR JSON payload)."""
    human = render(err)
    if mode is LogMode.HUMAN:
        # Best-effort: exit code alone signals failure if stderr is dead.
        with contextlib.suppress(OSError, ValueError):
            print(human, file=sys.stderr)
    else:
        write_error_payload(err, human=human, stream=sys.stderr)
    return int(err.exit_code)
