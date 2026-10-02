from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import pytest

from signalbot import (
    DataMessageHandler,
    ReactionHandler,
    ReadyHandler,
    reaction_triggered,
    regex_triggered,
    text_triggered,
)
from signalbot.errors import SignalBotError
from signalbot.test_utils import ChatTestCase, DummyHandler
from tests.conftest import GROUP_ID
from tests.unit.conftest import (
    PRIVATE_NUMBER,
    PRIVATE_UUID,
    TestCommon,
    make_data_message,
    make_group_data_message,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from signalbot.context import DataMessageContext, ReactionContext, ReadyContext
    from signalbot.messages import DataMessage, ReceivedMessage


class TestProducer(TestCommon):
    async def test_produce(
        self,
        mock_receive: Callable[[list[str]], None],
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_receive(
            [
                ChatTestCase.new_message("Message 1"),
                ChatTestCase.new_message("Message 2"),
            ]
        )
        mock_get_all_groups([fake_group])

        # Any two commands
        self.signal_bot.register(DummyHandler())
        self.signal_bot.register(DummyHandler())
        await self.signal_bot._pipeline.resolve_handlers()

        await self.signal_bot._pipeline._produce(1337)

        assert self.signal_bot._pipeline._q.qsize() == 4


class TestRegisterHandler(TestCommon):
    def test_register_one_handler(self):
        self.signal_bot.register(DummyHandler())
        assert len(self.signal_bot._pipeline._handlers_to_register) == 1

    def test_register_three_handlers(self):
        self.signal_bot.register(DummyHandler())
        self.signal_bot.register(DummyHandler())
        self.signal_bot.register(DummyHandler())
        assert len(self.signal_bot._pipeline._handlers_to_register) == 3

    async def test_register_single_contact(self):
        user_number = "+49987654321"
        self.signal_bot.register(DummyHandler(), contacts=[user_number])
        await self.signal_bot._pipeline.resolve_handlers()
        assert self.signal_bot.handlers[0][1] == [user_number]

    async def test_register_multiple_contacts(self):
        user_number1 = "+49987654321"
        user_number2 = "+49987654322"
        user_number3 = "+49987654323"
        self.signal_bot.register(
            DummyHandler(),
            contacts=[user_number1, user_number2, user_number3],
        )
        await self.signal_bot._pipeline.resolve_handlers()
        expected_user_chats = [user_number1, user_number2, user_number3]
        assert self.signal_bot.handlers[0][1] == expected_user_chats

    async def test_register_multiple_contacts_multiple_handlers(self):
        user_number1 = "+49987654321"
        user_number2 = "+49987654322"
        user_number3 = "+49987654323"
        self.signal_bot.register(DummyHandler(), contacts=[user_number1, user_number2])
        self.signal_bot.register(DummyHandler(), contacts=[user_number3])
        await self.signal_bot._pipeline.resolve_handlers()
        expected_user_chats_handler0 = [user_number1, user_number2]
        expected_user_chats_handler1 = [user_number3]
        assert self.signal_bot.handlers[0][1] == expected_user_chats_handler0
        assert self.signal_bot.handlers[1][1] == expected_user_chats_handler1


class TrackingReadyHandler(ReadyHandler):
    def __init__(self):
        super().__init__()
        self.contexts: list[ReadyContext] = []

    async def handle_ready(self, context: ReadyContext) -> None:
        self.contexts.append(context)


class TestReadyHandler(TestCommon):
    async def test_run_ready_handlers_calls_handle_ready(self):
        handler = TrackingReadyHandler()
        self.signal_bot.register(handler)
        await self.signal_bot._pipeline.resolve_handlers()

        await self.signal_bot._pipeline.run_ready_handlers()

        assert len(handler.contexts) == 1
        assert handler.contexts[0].bot is self.signal_bot

    async def test_run_ready_handlers_skips_non_ready_handlers(self):
        self.signal_bot.register(DummyHandler())
        await self.signal_bot._pipeline.resolve_handlers()

        # DummyHandler is a DataMessageHandler, not a ReadyHandler, so this must
        # not raise (e.g. from trying to call a non-existent handle_ready).
        await self.signal_bot._pipeline.run_ready_handlers()

    async def test_run_ready_handlers_calls_multiple_handlers_in_registration_order(
        self,
    ):
        calls = []

        class FirstHandler(ReadyHandler):
            async def handle_ready(self, context: ReadyContext) -> None:
                calls.append("first")

        class SecondHandler(ReadyHandler):
            async def handle_ready(self, context: ReadyContext) -> None:
                calls.append("second")

        self.signal_bot.register(FirstHandler())
        self.signal_bot.register(SecondHandler())
        await self.signal_bot._pipeline.resolve_handlers()

        await self.signal_bot._pipeline.run_ready_handlers()

        assert calls == ["first", "second"]

    async def test_wait_until_ready_raises_if_bot_not_started(self):
        with pytest.raises(SignalBotError):
            await self.signal_bot.wait_until_ready()

    async def test_wait_until_ready_awaits_init_task(self):
        async def noop() -> None:
            return None

        self.signal_bot.init_task = asyncio.create_task(noop())

        await self.signal_bot.wait_until_ready()

        assert self.signal_bot.init_task.done()


class TestPipelineStop(TestCommon):
    async def test_stop_is_safe_to_call_from_a_tracked_task(self):
        """A "close" command handler runs on one of the pipeline's own
        consumer tasks. Calling `pipeline.stop()` from there means `stop()`
        would cancel-and-await its own caller unless it excludes the current
        task, which previously caused a `RecursionError` / hang.
        """
        pipeline = self.signal_bot._pipeline

        async def self_stopping_consumer() -> None:
            await pipeline.stop()

        task = asyncio.create_task(self_stopping_consumer())
        pipeline._consume_tasks.add(task)

        await asyncio.wait_for(task, timeout=1)


_private_message = make_data_message
_group_message = make_group_data_message


class TestShouldReactForContact(TestCommon):
    @pytest.mark.parametrize(
        ("message_factory", "contacts", "group_ids", "expected"),
        [
            pytest.param(
                _private_message, True, True, True, id="private-contacts-true"
            ),
            pytest.param(
                _private_message, False, True, False, id="private-contacts-false"
            ),
            pytest.param(
                _private_message,
                [PRIVATE_NUMBER],
                False,
                True,
                id="private-matches-number",
            ),
            pytest.param(
                _private_message, [PRIVATE_UUID], False, True, id="private-matches-uuid"
            ),
            pytest.param(
                _private_message,
                ["+49000000000"],
                False,
                False,
                id="private-no-match",
            ),
            pytest.param(_group_message, True, True, True, id="group-ids-true"),
            pytest.param(_group_message, True, False, False, id="group-ids-false"),
        ],
    )
    def test_should_react_for_contact(
        self,
        message_factory: Callable[[], DataMessage],
        *,
        contacts: list[str] | bool,
        group_ids: list[str] | bool,
        expected: bool,
    ):
        pipeline = self.signal_bot._pipeline
        result = pipeline._should_react_for_contact(
            message_factory(), contacts=contacts, group_ids=group_ids
        )
        assert result is expected

    async def test_group_message_matches_whitelisted_group_id(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        pipeline = self.signal_bot._pipeline
        mock_get_all_groups([fake_group])
        await self.signal_bot.groups.refresh()

        result = pipeline._should_react_for_contact(
            _group_message(), contacts=False, group_ids=[GROUP_ID]
        )

        assert result is True

    def test_group_message_does_not_match_unknown_group(self):
        pipeline = self.signal_bot._pipeline
        # Registry has no entry for the message's group, so `get_id` returns None.
        result = pipeline._should_react_for_contact(
            _group_message(), contacts=False, group_ids=[GROUP_ID]
        )
        assert result is False


class TestShouldReactForLambda(TestCommon):
    def test_no_filter_always_matches(self):
        pipeline = self.signal_bot._pipeline
        assert pipeline._should_react_for_lambda(_private_message(), None) is True

    def test_filter_true_matches(self):
        pipeline = self.signal_bot._pipeline
        result = pipeline._should_react_for_lambda(_private_message(), lambda _: True)
        assert result is True

    def test_filter_false_does_not_match(self):
        pipeline = self.signal_bot._pipeline
        result = pipeline._should_react_for_lambda(_private_message(), lambda _: False)
        assert result is False


class TrackingDataMessageHandler(DataMessageHandler):
    def __init__(self) -> None:
        self.contexts: list[DataMessageContext] = []

    async def handle_data_message(self, context: DataMessageContext) -> None:
        self.contexts.append(context)


class TestConsumeDispatched(TestCommon):
    async def test_consumer_calls_the_handler_with_the_message_context(self):
        pipeline = self.signal_bot._pipeline
        handler = TrackingDataMessageHandler()
        self.signal_bot.register(handler)
        await pipeline.resolve_handlers()
        message = _private_message()

        await pipeline._dispatch_to_handlers(message)
        await pipeline._consume_new_item(1)

        assert len(handler.contexts) == 1
        assert handler.contexts[0].message is message


class TestConsumeResilience(TestCommon):
    async def test_consume_keeps_running_after_a_handler_raises(self):
        pipeline = self.signal_bot._pipeline

        class ExplodingHandler(DataMessageHandler):
            async def handle_data_message(self, context: DataMessageContext) -> None:
                error_msg = "boom"
                raise RuntimeError(error_msg)

        succeeded = asyncio.Event()

        class RecoveringHandler(DataMessageHandler):
            async def handle_data_message(self, context: DataMessageContext) -> None:
                succeeded.set()

        self.signal_bot.register(ExplodingHandler())
        self.signal_bot.register(RecoveringHandler())
        await pipeline.resolve_handlers()
        await pipeline._dispatch_to_handlers(_private_message())

        consume_task = asyncio.create_task(pipeline._consume(1))
        try:
            await asyncio.wait_for(succeeded.wait(), timeout=1)
        finally:
            consume_task.cancel()
            await asyncio.gather(consume_task, return_exceptions=True)

    async def test_consume_new_item_reraises_handler_exceptions(self):
        pipeline = self.signal_bot._pipeline

        class ExplodingHandler(DataMessageHandler):
            async def handle_data_message(self, context: DataMessageContext) -> None:
                error_msg = "boom"
                raise RuntimeError(error_msg)

        self.signal_bot.register(ExplodingHandler())
        await pipeline.resolve_handlers()
        await pipeline._dispatch_to_handlers(_private_message())

        with pytest.raises(RuntimeError, match="boom"):
            await pipeline._consume_new_item(1)


class _Recorder(DummyHandler):
    """Catch-all handler, only used to check which handlers get queued."""

    def __init__(self, name: str) -> None:
        self.name = name


class _Ping(_Recorder):
    @text_triggered("ping")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        pass


class _Digits(_Recorder):
    @regex_triggered(r"\d")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        pass


class _PingWithDigits(_Recorder):
    @text_triggered("ping 1")
    @regex_triggered(r"\d")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        pass


class _ThumbsUp(ReactionHandler):
    @reaction_triggered("👍")
    async def handle_reaction(self, context: ReactionContext) -> None:
        pass


class TestDispatch(TestCommon):
    async def queued_for(self, text: str) -> list[str]:
        """Dispatches a private message with `text` and returns the names of the
        queued handlers, in queue order."""
        pipeline = self.signal_bot._pipeline
        await pipeline.resolve_handlers()
        await pipeline._dispatch_to_handlers(make_data_message(text=text))
        names = []
        while not pipeline._q.empty():
            handler, *_ = pipeline._q.get_nowait()
            names.append(cast("_Recorder", handler).name)
        return names

    async def test_handlers_whose_trigger_does_not_match_are_not_queued(self):
        self.signal_bot.register(_Ping("ping"))
        self.signal_bot.register(_Recorder("all"))

        assert await self.queued_for("ping") == ["ping", "all"]
        assert await self.queued_for("pong") == ["all"]

    async def test_stacked_triggers_must_all_match(self):
        self.signal_bot.register(_PingWithDigits("both"))

        assert await self.queued_for("ping 1") == ["both"]
        assert await self.queued_for("pong 1") == []

    async def test_only_the_first_matching_exclusive_handler_runs(self):
        self.signal_bot.register(_Ping("ping"), priority=0)
        self.signal_bot.register(_Digits("digits"), priority=0)
        self.signal_bot.register(_Recorder("fallback"), priority=0)

        assert await self.queued_for("ping") == ["ping"]
        assert await self.queued_for("call 112") == ["digits"]
        assert await self.queued_for("hello") == ["fallback"]

    async def test_the_highest_priority_wins_regardless_of_registration_order(self):
        self.signal_bot.register(_Recorder("fallback"), priority=-1)
        self.signal_bot.register(_Digits("digits"), priority=0)
        self.signal_bot.register(_Ping("ping"), priority=10)

        assert await self.queued_for("ping") == ["ping"]
        assert await self.queued_for("call 112") == ["digits"]
        assert await self.queued_for("hello") == ["fallback"]

    async def test_non_exclusive_handlers_run_alongside_in_registration_order(self):
        self.signal_bot.register(_Recorder("before"))
        self.signal_bot.register(_Ping("ping"), priority=1)
        self.signal_bot.register(_Recorder("fallback"), priority=0)
        self.signal_bot.register(_Recorder("after"))

        assert await self.queued_for("ping") == ["before", "ping", "after"]
        assert await self.queued_for("hello") == ["before", "fallback", "after"]

    async def test_exclusive_handlers_of_other_message_types_do_not_compete(self):
        self.signal_bot.register(_ThumbsUp(), priority=100)
        self.signal_bot.register(_Recorder("fallback"), priority=0)

        assert await self.queued_for("hello") == ["fallback"]

    async def test_contact_and_lambda_filters_apply_before_exclusivity(self):
        self.signal_bot.register(_Ping("other-contact"), contacts=["+1"], priority=0)
        self.signal_bot.register(_Ping("filtered"), f=lambda _: False, priority=5)
        self.signal_bot.register(_Recorder("fallback"), priority=0)

        assert await self.queued_for("ping") == ["fallback"]

    async def test_raising_filter_skips_only_that_handler(
        self, caplog: pytest.LogCaptureFixture
    ):
        def explode(_message: ReceivedMessage) -> bool:
            error_msg = "boom"
            raise RuntimeError(error_msg)

        self.signal_bot.register(_Recorder("broken"), f=explode, priority=0)
        self.signal_bot.register(_Recorder("ok"))

        with caplog.at_level(logging.ERROR):
            assert await self.queued_for("hello") == ["ok"]
        assert "Filter or trigger raised" in caplog.text

    async def test_unknown_message_type_is_not_dispatched(
        self, caplog: pytest.LogCaptureFixture
    ):
        self.signal_bot.register(_Recorder("all"))
        pipeline = self.signal_bot._pipeline
        await pipeline.resolve_handlers()

        with caplog.at_level(logging.WARNING):
            await pipeline._dispatch_to_handlers(cast("ReceivedMessage", object()))

        assert pipeline._q.empty()
        assert "Unknown message type" in caplog.text
