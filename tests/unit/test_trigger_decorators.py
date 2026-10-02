from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from signalbot.context import DataMessageContext, ReactionContext
from signalbot.handlers import (
    _message_trigger,
    reaction_triggered,
    regex_triggered,
    text_triggered,
)
from signalbot.reactions import Reaction
from tests.unit.conftest import PRIVATE_NUMBER, make_data_message

if TYPE_CHECKING:
    from signalbot.messages import DataMessage


def _data_message(text: str | None) -> DataMessage:
    return make_data_message(text=text)


def _reaction(emoji: str) -> Reaction:
    return Reaction(
        server_delivered_timestamp=1,
        server_received_timestamp=1,
        timestamp=1,
        source_number=PRIVATE_NUMBER,
        emoji=emoji,
        is_remove=False,
    )


class _TextHandler:
    @text_triggered("hello")
    async def handle_data_message(self, context: DataMessageContext) -> str:
        return "called"


class _RegexHandler:
    @regex_triggered(r"\d+")
    async def handle_data_message(self, context: DataMessageContext) -> str:
        return "called"


class _ReactionHandler:
    @reaction_triggered("👍")
    async def handle_reaction(self, context: ReactionContext) -> str:
        return "called"


class TestTextTriggeredGuards:
    async def test_raises_when_used_on_non_data_message_context(self):
        handler = _TextHandler()
        wrong_context = cast("DataMessageContext", object())

        with pytest.raises(TypeError, match="text_triggered decorator"):
            await handler.handle_data_message(wrong_context)

    async def test_skips_without_raising_when_message_has_no_text(self, mocker):
        handler = _TextHandler()
        bot = mocker.Mock()
        context = DataMessageContext(bot, _data_message(text=None))

        result = await handler.handle_data_message(context)

        assert result is None

    async def test_calls_through_when_text_matches(self, mocker):
        handler = _TextHandler()
        bot = mocker.Mock()
        context = DataMessageContext(bot, _data_message(text="hello"))

        result = await handler.handle_data_message(context)

        assert result == "called"


class TestRegexTriggeredGuards:
    async def test_raises_when_used_on_non_data_message_context(self):
        handler = _RegexHandler()
        wrong_context = cast("DataMessageContext", object())

        with pytest.raises(TypeError, match="regex_triggered decorator"):
            await handler.handle_data_message(wrong_context)

    async def test_skips_without_raising_when_message_has_no_text(self, mocker):
        handler = _RegexHandler()
        bot = mocker.Mock()
        context = DataMessageContext(bot, _data_message(text=None))

        result = await handler.handle_data_message(context)

        assert result is None

    async def test_calls_through_when_regex_matches(self, mocker):
        handler = _RegexHandler()
        bot = mocker.Mock()
        context = DataMessageContext(bot, _data_message(text="room 404"))

        result = await handler.handle_data_message(context)

        assert result == "called"


class TestReactionTriggeredGuards:
    async def test_raises_when_used_on_non_reaction_context(self):
        handler = _ReactionHandler()
        wrong_context = cast("ReactionContext", object())

        with pytest.raises(TypeError, match="reaction_triggered decorator"):
            await handler.handle_reaction(wrong_context)

    async def test_skips_non_matching_emoji_without_raising(self, mocker):
        handler = _ReactionHandler()
        bot = mocker.Mock()
        context = ReactionContext(bot, _reaction("😂"))

        result = await handler.handle_reaction(context)

        assert result is None

    async def test_calls_through_on_matching_emoji(self, mocker):
        handler = _ReactionHandler()
        bot = mocker.Mock()
        context = ReactionContext(bot, _reaction("👍"))

        result = await handler.handle_reaction(context)

        assert result == "called"


class TestDispatchTriggers:
    """The decorators record their trigger so the pipeline can check it before
    queuing the handler."""

    def test_text_trigger(self):
        trigger = _message_trigger(_TextHandler(), "handle_data_message")
        assert trigger is not None
        assert trigger(_data_message("HELLO"))
        assert not trigger(_data_message("hello there"))
        assert not trigger(_data_message(None))
        assert not trigger(_reaction("👍"))

    def test_regex_trigger(self):
        trigger = _message_trigger(_RegexHandler(), "handle_data_message")
        assert trigger is not None
        assert trigger(_data_message("call 112"))
        assert not trigger(_data_message("no digits"))

    def test_reaction_trigger(self):
        trigger = _message_trigger(_ReactionHandler(), "handle_reaction")
        assert trigger is not None
        assert trigger(_reaction("👍"))
        assert not trigger(_reaction("👎"))
        assert not trigger(_data_message("👍"))

    def test_undecorated_methods_have_no_trigger(self):
        class Plain:
            async def handle_data_message(self, context: DataMessageContext) -> None:
                pass

        assert _message_trigger(Plain(), "handle_data_message") is None
        assert _message_trigger(Plain(), "handle_reaction") is None
