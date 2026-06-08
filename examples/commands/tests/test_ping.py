import pytest
from pytest_mock import MockerFixture

from examples.commands.ping import PingCommand
from signalbot.utils import ChatTestCase, mock_chat


class TestPingChatTest(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup(self):
        super().setup()
        self.signal_bot.register(PingCommand())

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings(
        "ignore:There is no current event loop:DeprecationWarning"
    )
    @mock_chat("ping")
    async def test_ping(self, mocker: MockerFixture, *args: object, **kwargs: object):  # noqa: ARG002
        replies = self.signal_bot._signal.send
        assert replies.call_count == 1
        assert len(replies.results()) == 1
        for recipient, message in replies.results():
            assert recipient == ChatTestCase.group_id
            assert message == "pong"
