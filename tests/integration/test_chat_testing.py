"""Tests for the `signalbot.test_utils` chat harness itself."""

import asyncio

import pytest
from pytest_mock import MockerFixture

from signalbot import (
    DataMessageContext,
    DataMessageHandler,
    RemoteDeleteContext,
    RemoteDeleteHandler,
)
from signalbot._client import SignalAPI
from signalbot.messages import (
    DataMessage,
    EditMessage,
    ReceivedMessage,
    RemoteDelete,
    SendMessage,
    parse,
)
from signalbot.test_utils import ChatTestCase, Envelope, mock_chat

SENDER_UUID = "11111111-1111-1111-1111-111111111111"


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


class RecordingHandler(DataMessageHandler, RemoteDeleteHandler):
    def __init__(self) -> None:
        self.received: list[ReceivedMessage] = []

    async def handle_data_message(self, context: DataMessageContext):
        self.received.append(context.message)

    async def handle_remote_delete(self, context: RemoteDeleteContext):
        self.received.append(context.message)


class TestEnvelopeBuilders:
    def test_builders_return_envelopes(self):
        assert isinstance(ChatTestCase.new_message("hi"), Envelope)
        assert isinstance(ChatTestCase.new_reaction_message("👍"), Envelope)
        assert isinstance(ChatTestCase.new_private_message("hi"), Envelope)

    async def test_private_message(self, signal_api: SignalAPI):
        quote = {
            "id": 1234,
            "author": SENDER_UUID,
            "authorUuid": SENDER_UUID,
            "text": "original",
        }
        envelope = ChatTestCase.new_private_message(
            "hi", source_uuid=SENDER_UUID, timestamp=42, quote=quote, view_once=True
        )
        message = await parse(signal_api, envelope)

        assert type(message) is DataMessage
        assert message.is_private()
        assert message.text == "hi"
        assert message.source_uuid == SENDER_UUID
        assert message.timestamp == 42
        assert message.view_once is True
        assert message.quote is not None
        assert message.quote.id == 1234
        assert message.quote.author_uuid == SENDER_UUID
        assert message.quote.text == "original"

    async def test_private_message_attachments(self, signal_api: SignalAPI):
        signal_api.download_attachments = False
        attachment = {"id": "abc.png", "contentType": "image/png", "isVoiceNote": False}
        envelope = ChatTestCase.new_private_message(None, attachments=[attachment])
        message = await parse(signal_api, envelope)

        assert type(message) is DataMessage
        assert message.text is None
        assert message.attachments is not None
        assert message.attachments[0].local_filename == "abc.png"

    async def test_private_message_random_sender(self, signal_api: SignalAPI):
        first = await parse(signal_api, ChatTestCase.new_private_message("a"))
        second = await parse(signal_api, ChatTestCase.new_private_message("b"))
        assert first.source_uuid != second.source_uuid
        assert isinstance(first, DataMessage)
        assert isinstance(second, DataMessage)
        assert first.timestamp != second.timestamp

    async def test_edit_message(self, signal_api: SignalAPI):
        envelope = ChatTestCase.new_edit_message(
            "edited", source_uuid=SENDER_UUID, target_sent_timestamp=42, timestamp=43
        )
        message = await parse(signal_api, envelope)

        assert type(message) is EditMessage
        assert message.is_private()
        assert message.text == "edited"
        assert message.source_uuid == SENDER_UUID
        assert message.target_sent_timestamp == 42
        assert message.timestamp == 43

    async def test_remote_delete(self, signal_api: SignalAPI):
        envelope = ChatTestCase.new_remote_delete(
            source_uuid=SENDER_UUID, target_sent_timestamp=42
        )
        message = await parse(signal_api, envelope)

        assert type(message) is RemoteDelete
        assert message.is_private()
        assert message.source_uuid == SENDER_UUID
        assert message.timestamp == 42


class TestPrivateChat(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.private = RecordingHandler()
        self.group = RecordingHandler()
        self.signal_bot.register(self.private, contacts=True, groups=False)
        self.signal_bot.register(self.group, contacts=False, groups=True)

    @mock_chat(
        ChatTestCase.new_private_message("hello", source_uuid=SENDER_UUID),
        "group hello",
    )
    async def test_private_and_group_messages(self, mocker: MockerFixture):
        assert [type(m) for m in self.private.received] == [DataMessage]
        assert self.private.received[0].source_uuid == SENDER_UUID
        assert [type(m) for m in self.group.received] == [DataMessage]
        assert isinstance(self.group.received[0], DataMessage)
        assert self.group.received[0].text == "group hello"

    @mock_chat(
        ChatTestCase.new_private_message(
            "original", source_uuid=SENDER_UUID, timestamp=100
        ),
        ChatTestCase.new_edit_message(
            "edited", source_uuid=SENDER_UUID, target_sent_timestamp=100
        ),
        ChatTestCase.new_remote_delete(
            source_uuid=SENDER_UUID, target_sent_timestamp=100
        ),
    )
    async def test_edit_and_remote_delete(self, mocker: MockerFixture):
        assert [type(m) for m in self.private.received] == [
            DataMessage,
            EditMessage,
            RemoteDelete,
        ]
        edit = self.private.received[1]
        assert isinstance(edit, EditMessage)
        assert edit.text == "edited"
        assert edit.target_sent_timestamp == 100
        assert self.private.received[2].timestamp == 100
        assert self.group.received == []
