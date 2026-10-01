"""Tests for the `signalbot.test_utils` chat harness itself."""

import asyncio

import pytest
from pytest_mock import MockerFixture

from signalbot import DataMessageContext, DataMessageHandler
from signalbot.messages import SendMessage
from signalbot.test_utils import ChatTestCase, mock_chat


class SlowEchoCommand(DataMessageHandler):
    """Yields to the event loop before replying, giving any stray background
    pipeline a chance to deliver the same message a second time."""

    def __init__(self) -> None:
        self.calls = 0

    async def handle_data_message(self, context: DataMessageContext):
        self.calls += 1
        await asyncio.sleep(0.01)
        await context.send(SendMessage(text=f"echo {context.message.text}"))


class TestNoDoubleDelivery(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.handler = SlowEchoCommand()
        self.signal_bot.register(self.handler)

    @mock_chat("one", "two")
    async def test_awaiting_handler_runs_once_per_message(self, mocker: MockerFixture):
        await asyncio.sleep(0.05)
        assert self.handler.calls == 2
        assert self.send_mock.call_count == 2
        assert [sent.message for sent in self.send_mock.results()] == [
            "echo one",
            "echo two",
        ]
        assert self.signal_bot._pipeline._produce_tasks == set()
        assert self.signal_bot._pipeline._consume_tasks == set()
