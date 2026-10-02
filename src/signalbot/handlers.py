from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ParamSpec, TypeAlias, TypeVar

from signalbot.context import (
    DataMessageContext,
    ReactionContext,
)
from signalbot.messages import DataMessage, ReceivedMessage
from signalbot.reactions import Reaction

T = TypeVar("T")
P = ParamSpec("P")

MessagePredicate: TypeAlias = Callable[[ReceivedMessage], bool]

# Attribute holding the message predicate of a handler method decorated with a
# trigger decorator, so the pipeline can check it before queuing the handler (see
# `_message_trigger`). `functools.wraps` copies it to any decorator stacked on top.
_TRIGGER_ATTR = "_signalbot_trigger"


def _message_trigger(handler: object, method_name: str) -> MessagePredicate | None:
    """The trigger of `handler`'s `method_name`, None if it isn't decorated with a
    trigger decorator."""
    method = getattr(type(handler), method_name, None)
    return getattr(method, _TRIGGER_ATTR, None)


if TYPE_CHECKING:
    from types import CoroutineType

    from signalbot.context import (
        GroupUpdateContext,
        ReadyContext,
        RemoteDeleteContext,
        TypingContext,
    )


def _trigger_decorator(
    name: str,
    context_type: type[DataMessageContext | ReactionContext],
    handler_method: str,
    matches: MessagePredicate,
) -> Callable[
    [Callable[P, CoroutineType[Any, Any, T]]],
    Callable[P, CoroutineType[Any, Any, T | None]],
]:
    """Builds the trigger decorator `name`, which only calls the decorated
    `handler_method` when the message `matches`."""

    def decorator(
        func: Callable[P, CoroutineType[Any, Any, T]],
    ) -> Callable[P, CoroutineType[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
            context = args[1]
            if not isinstance(context, context_type):
                error_msg = f"{name} decorator can only be used with {handler_method}."
                raise TypeError(error_msg)

            if not matches(context.message):
                return None
            return await func(*args, **kwargs)

        # When trigger decorators are stacked, `functools.wraps` copied the inner
        # trigger onto `wrapper`, and both must match
        inner: MessagePredicate | None = getattr(wrapper, _TRIGGER_ATTR, None)
        trigger = matches if inner is None else lambda m: matches(m) and inner(m)
        setattr(wrapper, _TRIGGER_ATTR, trigger)
        return wrapper

    return decorator


def regex_triggered(
    *by: str | re.Pattern[str],
) -> Callable[
    [Callable[P, CoroutineType[Any, Any, T]]],
    Callable[P, CoroutineType[Any, Any, T | None]],
]:
    """Decorator to trigger a handler if the message text matches any of the provided
    regex patterns.

    Args:
        *by: A variable number of strings or compiled regex patterns to match the
            message text against.
    """
    patterns = [re.compile(pattern) for pattern in by]

    def matches(message: ReceivedMessage) -> bool:
        if not isinstance(message, DataMessage) or message.text is None:
            return False
        text = message.text
        return any(pattern.search(text) for pattern in patterns)

    return _trigger_decorator(
        "regex_triggered",
        DataMessageContext,
        "DataMessageHandler.handle_data_message",
        matches,
    )


def text_triggered(
    *by: str, case_sensitive: bool = False
) -> Callable[
    [Callable[P, CoroutineType[Any, Any, T]]],
    Callable[P, CoroutineType[Any, Any, T | None]],
]:
    """Decorator to trigger a handler if the message text matches any of the provided
    strings.

    Args:
        *by: A variable number of strings to match the message text against.
        case_sensitive: Whether the matching should be case sensitive.
    """
    by_words = frozenset(by if case_sensitive else (t.lower() for t in by))

    def matches(message: ReceivedMessage) -> bool:
        if not isinstance(message, DataMessage) or message.text is None:
            return False
        text = message.text if case_sensitive else message.text.lower()
        return text in by_words

    return _trigger_decorator(
        "text_triggered",
        DataMessageContext,
        "DataMessageHandler.handle_data_message",
        matches,
    )


def reaction_triggered(
    *by: str,
) -> Callable[
    [Callable[P, CoroutineType[Any, Any, T]]],
    Callable[P, CoroutineType[Any, Any, T | None]],
]:
    """Decorator to trigger a handler when a reaction is received.

    Args:
        *by: Optional emoji strings to filter on. If empty, triggers on any reaction.
    """

    def matches(message: ReceivedMessage) -> bool:
        return isinstance(message, Reaction) and (not by or message.emoji in by)

    return _trigger_decorator(
        "reaction_triggered",
        ReactionContext,
        "ReactionHandler.handle_reaction",
        matches,
    )


class DataMessageHandler(ABC):
    """Abstract base class for text, attachments and stickers messages.
    It handles both original messages and edited messages.

    To create a handler, subclass this class and implement `handle_data_message`.
    Then, register the handler with the bot using `bot.register(HandlerSubclass())`.
    """

    @abstractmethod
    async def handle_data_message(self, context: DataMessageContext) -> None:
        """Method to handle a data or edit message.
        This method must be implemented by subclasses to define the behavior of the
            handler.
        Args:
            context: Chat context containing the received message and other information.
                `context.message` is an `EditMessage` (a `DataMessage` subclass)
                when the message is an edit of a previously sent message.
        """


class GroupUpdateHandler(ABC):
    """Abstract base class for reacting to group update events.

    Subclass this and implement `handle_group_update`, then register the
    instance with the bot using `bot.register(...)`.
    """

    @abstractmethod
    async def handle_group_update(self, context: GroupUpdateContext) -> None:
        """Method to handle a group update message.
        This method must be implemented by subclasses to define the behavior of the
            handler.
        Args:
            context: Chat context containing the received message and other information.
        """


class RemoteDeleteHandler(ABC):
    """Abstract base class for reacting to remote delete events.

    Subclass this and implement `handle_remote_delete`, then register the instance
    with the bot using `bot.register(...)`.
    """

    @abstractmethod
    async def handle_remote_delete(self, context: RemoteDeleteContext) -> None:
        """Method to handle a remote delete message.
        This method must be implemented by subclasses to define the behavior of the
            handler.
        Args:
            context: Chat context containing the received message and other information.
        """


class TypingHandler(ABC):
    """Abstract base class for reacting to typing indicator events.

    Subclass this and implement `handle_typing`, then register the instance
    with the bot using `bot.register(...)`.
    """

    @abstractmethod
    async def handle_typing(self, context: TypingContext) -> None:
        """Method to handle a typing message.
        This method must be implemented by subclasses to define the behavior of the
            handler.
        Args:
            context: Chat context containing the received message and other information.
        """


class ReactionHandler(ABC):
    """Abstract base class for reacting to reaction events.

    Subclass this and implement `handle_reaction`, then register the instance with
    the bot using `bot.register(...)`.
    """

    @abstractmethod
    async def handle_reaction(self, context: ReactionContext) -> None:
        """Method to handle a reaction.
        This method must be implemented by subclasses to define the behavior of the
            handler.
        Args:
            context: Chat context containing the received message and other information.
        """


class ReadyHandler(ABC):
    """Abstract base class for reacting to the bot becoming ready.

    Subclass this and implement `handle_ready`, then register the instance with
    the bot using `bot.register(...)`. `handle_ready` is called exactly once, after
    the bot has finished connecting and resolving groups, but before it starts
    processing incoming messages.
    """

    @abstractmethod
    async def handle_ready(self, context: ReadyContext) -> None:
        """Method to handle the bot becoming ready.
        This method must be implemented by subclasses to define the behavior of the
            handler.
        Args:
            context: Context giving access to the bot.
        """


AnyHandler: TypeAlias = (
    DataMessageHandler
    | GroupUpdateHandler
    | RemoteDeleteHandler
    | TypingHandler
    | ReactionHandler
    | ReadyHandler
)
"""Union of all concrete `Handler` ABCs that can be passed to `SignalBot.register`."""

HandlerList: TypeAlias = list[
    tuple[
        AnyHandler,
        list[str] | bool,  # contacts
        list[str] | bool,  # groups
        Callable[[ReceivedMessage], bool] | None,  # lambda filter
    ]
]
"""A list of registered handlers together with their contact/group/lambda filters,
as tracked internally by `SignalBot`.
"""
