from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, NamedTuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from signalbot._client import SignalAPI
from signalbot.auth import BasicAuthentication, BearerAuthentication
from signalbot.bot_config import (
    BasicAuthConfig,
    BearerAuthConfig,
    InMemoryConfig,
    RedisConfig,
    SQLiteConfig,
)
from signalbot.errors import SignalBotError
from signalbot.storage import RedisStorage, SQLiteStorage

if TYPE_CHECKING:
    import logging

    from signalbot.bot_config import Config


class BotComponents(NamedTuple):
    """Runtime components resolved from `Config`, before being attached to a
    `SignalBot` instance.
    """

    signal: SignalAPI
    event_loop: asyncio.AbstractEventLoop
    scheduler: AsyncIOScheduler
    storage: SQLiteStorage | RedisStorage


def _resolve_auth(config: Config) -> BasicAuthentication | BearerAuthentication | None:
    if isinstance(config.auth, BasicAuthConfig):
        return BasicAuthentication(config.auth.username, config.auth.password)
    if isinstance(config.auth, BearerAuthConfig):
        return BearerAuthentication(config.auth.token)
    return None


def _build_signal_api(config: Config) -> SignalAPI:
    return SignalAPI(
        config.signal_service,
        config.phone_number,
        _resolve_auth(config),
        download_attachments=config.download_attachments,
        connection_mode=config.connection_mode,
    )


def _build_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        return event_loop


def _build_scheduler(event_loop: asyncio.AbstractEventLoop) -> AsyncIOScheduler:
    try:
        return AsyncIOScheduler(event_loop=event_loop)
    except (TypeError, ValueError, LookupError) as e:
        error_msg = f"Could not initialize scheduler: {e}"
        raise SignalBotError(error_msg) from e


def _build_storage(
    config: Config, logger: logging.Logger
) -> SQLiteStorage | RedisStorage:
    if isinstance(config.storage, SQLiteConfig):
        storage = SQLiteStorage(
            config.storage.db,
            check_same_thread=config.storage.check_same_thread,
        )
        logger.info("sqlite storage initialized")
    elif isinstance(config.storage, RedisConfig):
        storage = RedisStorage(
            config.storage.host,
            config.storage.port,
            config.storage.password,
        )
        logger.info("redis storage initialized")
    elif isinstance(config.storage, InMemoryConfig):
        storage = SQLiteStorage()
        logger.info("in-memory storage initialized")
    else:
        storage = SQLiteStorage()
        logger.warning(
            " Using in-memory storage."
            " Restarting will delete the storage!"
            " Add storage: {'type': 'in-memory'}"
            " to the config to silence this error.",
        )
    return storage


def build_components(config: Config, logger: logging.Logger) -> BotComponents:
    """Resolve `config` into the components a `SignalBot` attaches to itself.

    A pure function of `config` (plus logging as a side effect): it does not
    read or mutate any `SignalBot` instance, so it can be constructed and
    tested independently of one.
    """
    event_loop = _build_event_loop()
    return BotComponents(
        signal=_build_signal_api(config),
        event_loop=event_loop,
        scheduler=_build_scheduler(event_loop),
        storage=_build_storage(config, logger),
    )
