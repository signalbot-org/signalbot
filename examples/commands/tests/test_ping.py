import pytest
from pytest_mock import MockerFixture

from examples.commands.ping import PingCommand
from signalbot import ChatTestCase, mock_chat

USER = "11111111-1111-1111-1111-111111111111"


class TestPingChatTest(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(PingCommand())

    @mock_chat("ping")
    async def test_ping(self, mocker: MockerFixture, *args: object, **kwargs: object):
        replies = self.send_mock
        assert replies.call_count == 1
        assert len(replies.results()) == 1
        for sent in replies.results():
            assert sent.recipients == [ChatTestCase.group_id]
            assert sent.message == "pong"

    @mock_chat(
        ChatTestCase.new_private_message("pin", source_uuid=USER, timestamp=1),
        ChatTestCase.new_edit_message(
            "ping", source_uuid=USER, target_sent_timestamp=1
        ),
    )
    async def test_edited_ping(
        self, mocker: MockerFixture, *args: object, **kwargs: object
    ):
        sent = self.send_mock.results()
        assert [message.message for message in sent] == ["pong"]
        assert sent[0].recipients == [USER]
