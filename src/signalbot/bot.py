from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import TYPE_CHECKING

from packaging.version import Version

from signalbot._actions import (
    AttachmentActions,
    ContactActions,
    GeneralActions,
    GroupActions,
    MessageActions,
    PollActions,
    ReactionActions,
    ReceiptActions,
)
from signalbot._bot_init import build_components
from signalbot._pipeline import MessagePipeline
from signalbot._recipients import RecipientResolver
from signalbot._utils.retry import rerun_on_exception
from signalbot.bot_config import Config, load_config
from signalbot.errors import SignalBotError
from signalbot.groups import GroupRegistry
from signalbot.logger import _initialize_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from signalbot.handlers import AnyHandler, HandlerList
    from signalbot.messages import ReceivedMessage
    from signalbot.storage import RedisStorage, SQLiteStorage

MIN_SIGNAL_CLI_REST_API_VERSION = Version("0.100.0")
"""
The minimum required version of `signal-cli-rest-api` for this version of `signalbot`.
"""


class SignalBot:
    """
    SignalBot is the main class for the bot. It provides methods to register handlers,
    start the bot, and interact with messages.
    """

    config: Config
    """The configuration for the bot."""
    groups: GroupRegistry
    """Cache of the groups the bot is a member of, with lookup helpers. Only
    populated after [SignalBot.start()][signalbot.bot.SignalBot.start] is called
    and [SignalBot.init_task][signalbot.bot.SignalBot.init_task] is done.
    Group actions are available via `groups.actions`."""
    messages: MessageActions
    """Send, edit, or delete messages, and manage typing indicators."""
    polls: PollActions
    """Create polls."""
    reactions: ReactionActions
    """React to messages."""
    receipts: ReceiptActions
    """Send read/viewed receipts."""
    contacts: ContactActions
    """Update contact metadata."""
    attachments: AttachmentActions
    """Delete local attachment copies."""
    general: GeneralActions
    """Miscellaneous `signal-cli-rest-api` info."""
    storage: SQLiteStorage | RedisStorage
    """The storage backend used by the bot."""
    scheduler: AsyncIOScheduler
    """The scheduler for running scheduled tasks."""
    init_task: asyncio.Task | None
    """The initialization async task for the bot.

    Warning:
        Only available after [SignalBot.start()][signalbot.bot.SignalBot.start]
        is called.
    """

    def __init__(self, config: Config | Mapping | Path | str) -> None:
        """Initialization for the SignalBot.

        Args:
            config: the configuration for the bot.

        Example config:
        ```python
        {
            phone_number: "+49123456789"
        }
        ```
        """
        self.config = load_config(config)
        self._logger = _initialize_logger(self.config.logging_level)

        self.init_task = None
        self._shutdown_task: asyncio.Task | None = None

        components = build_components(self.config, self._logger)
        self._signal = components.signal
        self._event_loop = components.event_loop
        self.scheduler = components.scheduler
        self.storage = components.storage

        self._init_actions()

    def _init_actions(self) -> None:
        self.groups = GroupRegistry(self._signal, self._logger)
        self.groups.actions = GroupActions(self._signal, self.groups, self._logger)
        self._recipients = RecipientResolver(self.groups)
        self._pipeline = MessagePipeline(self, self._signal, self.groups, self._logger)

        self.messages = MessageActions(
            self._signal, self._recipients, self._logger, self.config.phone_number
        )
        self.polls = PollActions(self._signal, self._recipients, self._logger)
        self.reactions = ReactionActions(
            self._signal, self._recipients, self._logger, self.config.phone_number
        )
        self.receipts = ReceiptActions(self._signal, self._recipients, self._logger)
        self.contacts = ContactActions(self._signal, self._recipients, self._logger)
        self.attachments = AttachmentActions(
            self._signal, self._recipients, self._logger
        )
        self.general = GeneralActions(self._signal, self._recipients, self._logger)

    @property
    def handlers(self) -> HandlerList:
        """A list of registered handlers with their filters.

        Warning:
            Only available after [SignalBot.start()][signalbot.bot.SignalBot.start]
            is called and [SignalBot.init_task][signalbot.bot.SignalBot.init_task]
            is done."""
        return self._pipeline.handlers

    def register(
        self,
        handler: AnyHandler,
        *,
        contacts: list[str] | bool = True,
        groups: list[str] | bool = True,
        f: Callable[[ReceivedMessage], bool] | None = None,
    ) -> None:
        """Register a handler with optional contact/group filters.

        Args:
            handler: Handler instance to register.
            contacts: Allowed contacts or True for all.
            groups: Allowed groups or True for all.
            f: Optional function to further filter messages.
        """
        self._pipeline.register(handler, contacts=contacts, groups=groups, f=f)

    async def _async_post_init(self) -> None:
        await self._check_signal_service()
        await self._check_signal_cli_rest_api_version()
        await self._check_signal_cli_rest_api_mode()
        await self.groups.refresh()
        await self._pipeline.resolve_handlers()
        await self._pipeline.run_ready_handlers()
        await self._pipeline.start()

    async def _check_signal_service(self) -> None:
        while (await self._signal.check_signal_service()) is False:
            self._logger.error(
                "Cannot connect to the signal-cli-rest-api service, retrying"
            )
            await asyncio.sleep(self.config.retry_interval)

    async def _check_signal_cli_rest_api_version(self) -> None:
        version = (await self.general.about()).version

        # `unset` version is for preview versions of signal-cli-rest-api
        if version == "unset":
            self._logger.warning(
                "signal-cli-rest-api version is unset; skipping compatibility check",
            )
            return

        if Version(version) < MIN_SIGNAL_CLI_REST_API_VERSION:
            error_msg = f"Incompatible signal-cli-rest-api version, found {version}"
            error_msg += f", minimum required is {MIN_SIGNAL_CLI_REST_API_VERSION}"
            raise RuntimeError(error_msg)

    async def _check_signal_cli_rest_api_mode(self) -> None:
        mode = (await self.general.about()).mode
        if mode != "json-rpc":
            error_msg = (
                f"Wrong signal-cli-rest-api mode, found '{mode}', expected 'json-rpc'"
            )
            raise RuntimeError(error_msg)

    def start(self, *, run_forever: bool = True) -> None:
        """Start the bot event loop and scheduler.

        Args:
            run_forever: Whether to start the event loop or only add the task to it.
        """
        self.init_task = self._event_loop.create_task(
            rerun_on_exception(self._async_post_init, logger=self._logger),
        )

        if run_forever:
            self._install_sigint_sigterm_handlers()
            self.scheduler.start()

            self._event_loop.run_forever()

    def _install_sigint_sigterm_handlers(self) -> None:
        """On SIGINT/SIGTERM, gracefully stop without leaving dangling tasks."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            # add_signal_handler is unsupported on some platforms (e.g. Windows)
            with contextlib.suppress(NotImplementedError):
                self._event_loop.add_signal_handler(sig, self.request_stop)

    def request_stop(self) -> None:
        """Schedule [SignalBot.stop()][signalbot.bot.SignalBot.stop] without
        blocking the caller.

        The non-blocking way to trigger shutdown from within a message
        handler; see [SignalBot.stop()][signalbot.bot.SignalBot.stop] for why
        calling it directly also works, just not without blocking the handler
        until shutdown completes.
        """
        # Keep a hard reference to the task so it isn't garbage-collected mid-run
        self._shutdown_task = self._event_loop.create_task(self.stop())

    async def close(self) -> None:
        """Close the shared HTTP session.

        Warning:
            Not safe to call while the pipeline's producer/consumer tasks may
            still be making requests through this session — it pulls the
            connection out from under them mid-request.
            [SignalBot.stop()][signalbot.bot.SignalBot.stop] avoids this by
            cancelling and awaiting those tasks first; call this directly only
            once you know none of them are still running.
        """
        await self._signal.close()

    async def stop(self) -> None:
        """Gracefully stop the bot: cancel background tasks, close the shared
        HTTP session, and stop the event loop started by
        [SignalBot.start()][signalbot.bot.SignalBot.start].
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self._pipeline.stop()
        await self.close()
        self._event_loop.stop()

    async def wait_until_ready(self) -> None:
        """Wait until the bot has finished connecting and is ready to send messages."""
        if self.init_task is None:
            error_msg = "Bot is not initialized yet, call .start() first"
            raise SignalBotError(error_msg)

        await self.init_task
