from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from signalbot._utils.retry import rerun_on_exception
from signalbot.context import (
    DataMessageContext,
    GroupUpdateContext,
    ReactionContext,
    ReadyContext,
    RemoteDeleteContext,
    TypingContext,
)
from signalbot.errors import SignalBotError
from signalbot.groups import GroupUpdate
from signalbot.handlers import (
    AnyHandler,
    DataMessageHandler,
    GroupUpdateHandler,
    HandlerList,
    ReactionHandler,
    ReadyHandler,
    RemoteDeleteHandler,
    TypingHandler,
    _message_trigger,
)
from signalbot.messages import (
    DataMessage,
    EditMessage,
    ReceivedMessage,
    RemoteDelete,
    TypingMessage,
    UnknownMessageFormatError,
    parse,
)
from signalbot.messages.errors import ReceiveError
from signalbot.reactions import Reaction

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from signalbot._client import SignalAPI
    from signalbot.bot import SignalBot
    from signalbot.groups import GroupRegistry

# message type -> (handler role, context to build, handler method name to call)
_MESSAGE_DISPATCH: dict[type, tuple[type, type, str]] = {
    DataMessage: (DataMessageHandler, DataMessageContext, "handle_data_message"),
    EditMessage: (DataMessageHandler, DataMessageContext, "handle_data_message"),
    GroupUpdate: (GroupUpdateHandler, GroupUpdateContext, "handle_group_update"),
    RemoteDelete: (RemoteDeleteHandler, RemoteDeleteContext, "handle_remote_delete"),
    TypingMessage: (TypingHandler, TypingContext, "handle_typing"),
    Reaction: (ReactionHandler, ReactionContext, "handle_reaction"),
}


@dataclass(frozen=True)
class _DispatchOptions:
    exclusive: bool = False
    priority: int = 0


class MessagePipeline:
    """Owns handler registration and the produce/consume queue that dispatches
    incoming messages to registered handlers.
    """

    def __init__(
        self,
        bot: SignalBot,
        signal: SignalAPI,
        groups: GroupRegistry,
        logger: logging.Logger,
    ) -> None:
        self._bot = bot
        self._signal = signal
        self._groups = groups
        self._logger = logger

        self._handlers_to_register: HandlerList = []  # populated by .register()
        self.handlers: HandlerList = []  # populated by .resolve_handlers()
        # Same order as `_handlers_to_register` and `handlers`, kept apart so the public
        # `HandlerList` tuples keep their shape
        self._options_to_register: list[_DispatchOptions] = []
        self._options: list[_DispatchOptions] = []

        self._q: asyncio.Queue[tuple[AnyHandler, ReceivedMessage, float]] = (
            asyncio.Queue()
        )
        self._produce_tasks: set[asyncio.Task] = set()
        self._consume_tasks: set[asyncio.Task] = set()

    def register(  # noqa: PLR0913 -- the filters are keyword only
        self,
        handler: AnyHandler,
        *,
        contacts: list[str] | bool = True,
        groups: list[str] | bool = True,
        f: Callable[[ReceivedMessage], bool] | None = None,
        exclusive: bool = False,
        priority: int = 0,
    ) -> None:
        if priority != 0 and not exclusive:
            error_msg = "priority only applies to exclusive handlers, "
            error_msg += "register the handler with exclusive=True"
            raise ValueError(error_msg)

        self._handlers_to_register.append((handler, contacts, groups, f))
        self._options_to_register.append(_DispatchOptions(exclusive, priority))

    async def resolve_handlers(self) -> None:
        self.handlers = []
        self._options = list(self._options_to_register)
        for handler, contacts, groups, f in self._handlers_to_register:
            group_ids: list[str] | bool
            if isinstance(groups, bool):
                group_ids = groups
            else:
                group_ids = []
                for group in groups:
                    group_id = self._groups.resolve(group)
                    if group_id is not None:
                        group_ids.append(group_id)
                    else:
                        error_msg = f"[Bot] [{handler.__class__.__name__}] '{group}' "
                        error_msg += "is not a valid group name or id"
                        self._logger.warning(error_msg)

            self.handlers.append((handler, contacts, group_ids, f))

    async def run_ready_handlers(self) -> None:
        for handler, *_ in self.handlers:
            if isinstance(handler, ReadyHandler):
                await handler.handle_ready(ReadyContext(self._bot))

    def _store_reference_to_task(
        self,
        task: asyncio.Task,
        task_set: set[asyncio.Task],
    ) -> None:
        # Keep a hard reference to the tasks, fixes Ruff's RUF006 rule
        task_set.add(task)
        task.add_done_callback(task_set.discard)

    async def stop(self) -> None:
        """Cancel all running producer/consumer tasks and wait for them to exit."""
        # Excludes the calling task itself: `stop()` may be invoked from within
        # a handler running on one of these tasks (e.g. a "close" command), and
        # a task cannot cancel-and-await itself without deadlocking.
        current = asyncio.current_task()
        tasks = [
            task
            for task in itertools.chain(self._consume_tasks, self._produce_tasks)
            if task is not current
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def start(
        self,
        producers: int = 1,
        consumers: int = 3,
    ) -> None:
        await self.stop()

        self._produce_tasks.clear()

        for n in range(1, producers + 1):
            produce_task = rerun_on_exception(self._produce, n, logger=self._logger)
            produce_task = asyncio.create_task(produce_task)
            self._store_reference_to_task(produce_task, self._produce_tasks)

        self._consume_tasks.clear()

        for n in range(1, consumers + 1):
            consume_task = rerun_on_exception(self._consume, n, logger=self._logger)
            consume_task = asyncio.create_task(consume_task)
            self._store_reference_to_task(consume_task, self._consume_tasks)

    async def _process_updates(self, message: ReceivedMessage) -> None:
        # Update groups if message is from an unknown group
        if (
            isinstance(message, GroupUpdate | DataMessage)
            and message.group_info is not None
            and message.group_info.group_id is not None
            and message.group_info.group_id not in self._groups
        ):
            await self._groups.refresh()

        if isinstance(message, GroupUpdate):
            await self._groups.refresh_one(message.group_info.group_id)

    async def _produce(self, name: int) -> None:
        self._logger.info("[Bot] Producer #%s started", name)
        try:
            async for raw_message in self._signal.messages.receive():
                self._logger.info("[Raw Message] %s", raw_message)

                try:
                    message = await parse(self._signal, raw_message)
                except UnknownMessageFormatError:
                    continue

                await self._process_updates(message)

                await self._dispatch_to_handlers(message)

        except ReceiveError as e:
            # No retry strategy here: `rerun_on_exception` (see `start()`) already
            # restarts this coroutine from scratch on any uncaught exception.
            error_msg = f"Cannot receive messages: {e}"
            raise SignalBotError(error_msg) from e

    def _should_react_for_contact(
        self,
        message: ReceivedMessage,
        *,
        contacts: list[str] | bool,
        group_ids: list[str] | bool,
    ) -> bool:
        """Is the handler activated for a certain chat or group?"""
        # Case 1: Private message
        if message.is_private():
            # a) registered for all numbers
            if isinstance(contacts, bool) and contacts:
                return True

            # b) whitelisted numbers
            if isinstance(contacts, list) and (
                message.source_number in contacts or message.source_uuid in contacts
            ):
                return True

        # Case 2: Group message
        if message.is_group():
            # a) registered for all groups
            if isinstance(group_ids, bool) and group_ids:
                return True

            # b) whitelisted group ids
            group_id = self._groups.get_id(message.source_or_group_id())
            if isinstance(group_ids, list) and group_id and group_id in group_ids:
                return True

        return False

    def _should_react_for_lambda(
        self,
        message: ReceivedMessage,
        f: Callable[[ReceivedMessage], bool] | None = None,
    ) -> bool:
        if f is None:
            return True

        return f(message)

    def _should_react_for_trigger(
        self,
        handler: AnyHandler,
        message: ReceivedMessage,
        method_name: str,
        f: Callable[[ReceivedMessage], bool] | None,
    ) -> bool:
        """Checks the `f` filter and the trigger decorator of the handler method.

        Both are user code running in the producer: if they raise, the error is
        logged and the handler is skipped instead of losing the message.
        """
        try:
            if not self._should_react_for_lambda(message, f):
                return False
            trigger = _message_trigger(handler, method_name)
            return trigger is None or trigger(message)
        except Exception:
            self._logger.exception(
                "[%s] Filter or trigger raised, skipping the handler",
                handler.__class__.__name__,
            )
            return False

    async def _dispatch_to_handlers(self, message: ReceivedMessage) -> None:
        """Queues every handler that matches `message`. Among the matching exclusive
        handlers only the one with the highest priority is queued, the first
        registered one if several share it."""
        dispatch = _MESSAGE_DISPATCH.get(type(message))
        if dispatch is None:
            self._logger.warning(
                "[Bot] Unknown message type: %s, skipping dispatch", type(message)
            )
            return
        handler_type, _, method_name = dispatch

        # (registration index, handler), queued in registration order
        selected: list[tuple[int, AnyHandler]] = []
        exclusive: tuple[int, int, AnyHandler] | None = (
            None  # (priority, index, handler)
        )
        for index, ((handler, contacts, group_ids, f), options) in enumerate(
            zip(self.handlers, self._options, strict=True)
        ):
            if not isinstance(handler, handler_type):
                continue

            if not self._should_react_for_contact(
                message, contacts=contacts, group_ids=group_ids
            ):
                continue

            if not self._should_react_for_trigger(handler, message, method_name, f):
                continue

            if not options.exclusive:
                selected.append((index, handler))
            elif exclusive is None or options.priority > exclusive[0]:
                exclusive = (options.priority, index, handler)

        if exclusive is not None:
            _, index, handler = exclusive
            selected.append((index, handler))
            selected.sort(key=lambda item: item[0])

        for _, handler in selected:
            await self._q.put((handler, message, time.perf_counter()))

    async def _consume(self, name: int) -> None:
        self._logger.info("[Bot] Consumer #%s started", name)
        while True:
            try:
                await self._consume_new_item(name)
            except Exception:  # noqa: BLE001
                # Handler code is arbitrary user code and `_consume_new_item`
                # already logs the failure; this loop must keep running
                # regardless of what it raises.
                self._logger.debug("[Bot] Consumer #%s recovered, resuming", name)

    async def _invoke_handler(
        self, handler: AnyHandler, message: ReceivedMessage
    ) -> None:
        dispatch = _MESSAGE_DISPATCH.get(type(message))
        if dispatch is None:
            error_msg = f"[Bot] Unknown message type: {type(message)}, "
            error_msg += "skipping handler execution"
            self._logger.warning(error_msg)
            return

        handler_type, context_type, method_name = dispatch
        if isinstance(handler, handler_type):
            method = getattr(handler, method_name)
            await method(context_type(self._bot, message))

    async def _consume_new_item(self, name: int) -> None:
        handler, message, t = await self._q.get()
        now = time.perf_counter()
        self._logger.info(
            "[Bot] Consumer #%s got new job in %0.5f seconds", name, now - t
        )

        try:
            await self._invoke_handler(handler, message)
        except Exception:
            self._logger.exception("[%s]", handler.__class__.__name__)
            raise

        # done
        self._q.task_done()
