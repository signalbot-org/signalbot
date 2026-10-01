from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ParamSpec, TypeAlias, TypeVar
from weakref import WeakKeyDictionary

from signalbot.context import (
    DataMessageContext,
    ReactionContext,
)
from signalbot.messages import DataMessage, ReceivedMessage
from signalbot.reactions import Reaction

T = TypeVar("T")
P = ParamSpec("P")

MessagePredicate: TypeAlias = Callable[[ReceivedMessage], bool]

# The message predicate of every handler method decorated with a trigger decorator,
# so the pipeline can check it before queuing the handler (see `_message_trigger`).
_TRIGGERS: WeakKeyDictionary[Callable[..., Any], MessagePredicate] = WeakKeyDictionary()


def _register_trigger(
    wrapper: Callable[..., Any],
    func: Callable[..., Any],
    predicate: MessagePredicate,
) -> None:
    """Records `predicate` as the trigger of `wrapper`. When decorators are stacked,
    `func` is the inner decorator's wrapper, and both triggers must match."""
    inner = _TRIGGERS.get(func)
    if inner is None:
        _TRIGGERS[wrapper] = predicate
    else:
        _TRIGGERS[wrapper] = lambda message: predicate(message) and inner(message)


def _message_trigger(handler: object, method_name: str) -> MessagePredicate | None:
    """The trigger of `handler`'s `method_name`, None if it isn't decorated with a
    trigger decorator."""
    method = getattr(type(handler), method_name, None)
    if method is None:
        return None
    return _TRIGGERS.get(method)


if TYPE_CHECKING:
    from types import CoroutineType

    from signalbot.context import (
        GroupUpdateContext,
        ReadyContext,
        RemoteDeleteContext,
        TypingContext,
    )


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

    def matches(message: ReceivedMessage) -> bool:
        if not isinstance(message, DataMessage) or message.text is None:
            return False
        text = message.text
        return any(re.search(pattern, text) for pattern in by)

    def decorator_regex_triggered(
        func: Callable[P, CoroutineType[Any, Any, T]],
    ) -> Callable[P, CoroutineType[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper_regex_triggered(
            *args: P.args, **kwargs: P.kwargs
        ) -> T | None:
            context = args[1]
            if not isinstance(context, DataMessageContext):
                error_msg = "regex_triggered decorator can only be used with "
                error_msg += "DataMessageHandler.handle_data_message."
                raise TypeError(error_msg)

            if not matches(context.message):
                return None
            return await func(*args, **kwargs)

        _register_trigger(wrapper_regex_triggered, func, matches)
        return wrapper_regex_triggered

    return decorator_regex_triggered


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

    by_words = by if case_sensitive else [t.lower() for t in by]

    def matches(message: ReceivedMessage) -> bool:
        if not isinstance(message, DataMessage) or message.text is None:
            return False
        text = message.text if case_sensitive else message.text.lower()
        return text in by_words

    def decorator_triggered(
        func: Callable[P, CoroutineType[Any, Any, T]],
    ) -> Callable[P, CoroutineType[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper_triggered(*args: P.args, **kwargs: P.kwargs) -> T | None:
            context = args[1]
            if not isinstance(context, DataMessageContext):
                error_msg = "text_triggered decorator can only be used with "
                error_msg += "DataMessageHandler.handle_data_message."
                raise TypeError(error_msg)

            if not matches(context.message):
                return None
            return await func(*args, **kwargs)

        _register_trigger(wrapper_triggered, func, matches)
        return wrapper_triggered

    return decorator_triggered


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

    def decorator_reaction_triggered(
        func: Callable[P, CoroutineType[Any, Any, T]],
    ) -> Callable[P, CoroutineType[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper_reaction_triggered(
            *args: P.args, **kwargs: P.kwargs
        ) -> T | None:
            context = args[1]
            if not isinstance(context, ReactionContext):
                error_msg = "reaction_triggered decorator can only be used with "
                error_msg += "ReactionHandler.handle_reaction."
                raise TypeError(error_msg)

            if not matches(context.message):
                return None
            return await func(*args, **kwargs)

        _register_trigger(wrapper_reaction_triggered, func, matches)

        return wrapper_reaction_triggered

    return decorator_reaction_triggered


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
