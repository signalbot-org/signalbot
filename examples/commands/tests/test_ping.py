import pytest
from pytest_mock import MockerFixture

from examples.commands.ping import PingCommand
from signalbot import ChatTestCase, mock_chat


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
