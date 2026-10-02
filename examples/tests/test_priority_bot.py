import pytest
from pytest_mock import MockerFixture

from examples.priority_bot import register_handlers
from signalbot import ChatTestCase, mock_chat


class TestPriorityBot(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        register_handlers(self.signal_bot)

    @mock_chat("!ping", "!foo", "hello")
    async def test_only_the_highest_priority_handler_replies(
        self, mocker: MockerFixture
    ):
        replies = [sent.message for sent in self.send_mock.results()]
        assert replies == ["pong", "Unknown command !foo, try !ping", "hello"]
