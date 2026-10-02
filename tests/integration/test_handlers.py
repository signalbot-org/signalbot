from dataclasses import dataclass

import pytest
from pytest_mock import MockerFixture

from signalbot import (
    DataMessageContext,
    DataMessageHandler,
    ReactionContext,
    ReactionHandler,
    reaction_triggered,
    regex_triggered,
    text_triggered,
)
from signalbot.messages import SendMessage
from signalbot.test_utils import (
    ChatTestCase,
    GetAllMock,
    ReceiveMock,
    SendMock,
    mock_chat,
)


class TriggeredCommand(DataMessageHandler):
    @text_triggered("Alpha", "Beta")
    async def handle_data_message(self, context: DataMessageContext):
        await context.send(SendMessage(text="Base trigger"))


class TriggeredCaseSensitiveCommand(DataMessageHandler):
    @text_triggered("Alpha", "Beta", case_sensitive=True)
    async def handle_data_message(self, context: DataMessageContext):
        await context.send(SendMessage(text="Base trigger"))


class ReactionTriggeredCommand(ReactionHandler):
    @reaction_triggered()
    async def handle_reaction(self, context: ReactionContext):
        await context.send(SendMessage(text="Reactions trigger"))


class ReactionFilteredCommand(ReactionHandler):
    @reaction_triggered("👍", "❤️")
    async def handle_reaction(self, context: ReactionContext):
        await context.send(SendMessage(text="Specific reactions trigger"))


class RegexTriggeredCommand(DataMessageHandler):
    @regex_triggered(r"\w+@\w+\.\w+", r"\d{3}-\d{3}-\d{4}")
    async def handle_data_message(self, context: DataMessageContext):
        await context.send(SendMessage(text="I am triggered by regular expressions"))


@dataclass
class SendReceiveGetGroupsMocks:
    send_mock: SendMock
    receive_mock: ReceiveMock
    get_groups_mock: GetAllMock


class TestCommon(ChatTestCase):
    def mock_send_receive_get_groups(
        self, mocker: MockerFixture
    ) -> SendReceiveGetGroupsMocks:
        send_mock = mocker.patch(
            "signalbot._client.messages.MessagesClient.send",
            new_callable=SendMock,
        )
        receive_mock = mocker.patch(
            "signalbot._client.messages.MessagesClient.receive",
            new_callable=ReceiveMock,
        )
        get_groups_mock = mocker.patch(
            "signalbot._client.groups.GroupsClient.get_all",
            new_callable=GetAllMock,
        )
        return SendReceiveGetGroupsMocks(send_mock, receive_mock, get_groups_mock)


class TestTriggered(TestCommon):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(TriggeredCommand(), contacts=True, groups=True)

    async def test_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["Alpha"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_also_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["Beta"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_not_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["Gamma"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 0


class TestTriggeredCaseSensitive(TestCommon):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(TriggeredCaseSensitiveCommand())

    async def test_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["Alpha"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_not_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["alpha"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 0


class TestRegexTriggered(TestCommon):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(RegexTriggeredCommand())

    async def test_regex_triggered_email(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["potus@whitehouse.tld"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_regex_triggered_phone(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["123-555-1234"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_not_regex_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["11-222"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 0


class TestTriggeredGroups(TestCommon):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()

    async def _test_trigger(self, mocker: MockerFixture, call_count: int) -> None:
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["Alpha"])
        await self.signal_bot.groups.refresh()
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == call_count

    async def test_triggered_name(self, mocker: MockerFixture):
        self.signal_bot.register(TriggeredCommand(), groups=[ChatTestCase.group_name])
        await self._test_trigger(mocker, call_count=1)

    async def test_triggered_id(self, mocker: MockerFixture):
        self.signal_bot.register(TriggeredCommand(), groups=[ChatTestCase.group_id])
        await self._test_trigger(mocker, call_count=1)

    async def test_triggered_internal_id(self, mocker: MockerFixture):
        self.signal_bot.register(
            TriggeredCommand(), groups=[ChatTestCase.group_internal_id]
        )
        await self._test_trigger(mocker, call_count=1)

    async def test_not_triggered_name(self, mocker: MockerFixture):
        self.signal_bot.register(
            TriggeredCommand(), groups=[ChatTestCase.group_name + "a"]
        )
        await self._test_trigger(mocker, call_count=0)

    async def test_not_triggered_id(self, mocker: MockerFixture):
        self.signal_bot.register(
            TriggeredCommand(), groups=[ChatTestCase.group_id + "a"]
        )
        await self._test_trigger(mocker, call_count=0)

    async def test_not_triggered_internal_id(self, mocker: MockerFixture):
        self.signal_bot.register(
            TriggeredCommand(), groups=[ChatTestCase.group_internal_id + "a"]
        )
        await self._test_trigger(mocker, call_count=0)


class TestReactionTriggered(TestCommon):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(ReactionTriggeredCommand(), contacts=True, groups=True)

    async def test_reaction_triggered(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define_raw([ChatTestCase.new_reaction_message("👍")])
        await self.signal_bot.groups.refresh()
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_non_reaction_skipped(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define(["hello"])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 0


class TestReactionFiltered(TestCommon):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(ReactionFilteredCommand(), contacts=True, groups=True)

    async def test_matching_emoji(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define_raw([ChatTestCase.new_reaction_message("👍")])
        await self.signal_bot.groups.refresh()
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 1

    async def test_non_matching_emoji(self, mocker: MockerFixture):
        mocks = self.mock_send_receive_get_groups(mocker)
        mocks.receive_mock.define_raw([ChatTestCase.new_reaction_message("😂")])
        await self.signal_bot._pipeline.resolve_handlers()
        await self.run_bot()
        assert mocks.send_mock.call_count == 0


class SchnickSchnackSchnuckCommand(DataMessageHandler):
    @text_triggered("schnick", "schnack")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        text = context.message.text
        if text == "schnick":
            await context.send(SendMessage(text="schnack"))

        if text == "schnack":
            await context.send(SendMessage(text="schnuck"))


@pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning")
class TestSchnickSchnackSchnuckCommand(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(SchnickSchnackSchnuckCommand())

    @mock_chat("schnick")
    async def test_schnick(
        self,
        mocker: MockerFixture,
        *args: object,
        **kwargs: object,
    ):
        replies = self.send_mock
        assert replies.call_count == 1
        assert len(replies.results()) == 1
        for sent in replies.results():
            assert sent.recipients == [ChatTestCase.group_id]
            assert sent.message == "schnack"

    @mock_chat("schnack")
    async def test_schnack(
        self,
        mocker: MockerFixture,
        *args: object,
        **kwargs: object,
    ):
        replies = self.send_mock
        assert replies.call_count == 1
        assert len(replies.results()) == 1
        for sent in replies.results():
            assert sent.recipients == [ChatTestCase.group_id]
            assert sent.message == "schnuck"


class PingCommand(DataMessageHandler):
    @text_triggered("ping")
    async def handle_data_message(self, context: DataMessageContext):
        await context.send(SendMessage(text="pong"))


class EchoFallback(DataMessageHandler):
    async def handle_data_message(self, context: DataMessageContext):
        await context.send(SendMessage(text=f"echo: {context.message.text}"))


class TestExclusiveCommandsWithFallback(ChatTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixture(self):
        self.setup()
        self.signal_bot.register(PingCommand(), exclusive=True, priority=1)
        self.signal_bot.register(EchoFallback(), exclusive=True)

    @mock_chat("ping")
    async def test_command_does_not_trigger_the_fallback(self, mocker: MockerFixture):
        assert [sent.message for sent in self.send_mock.results()] == ["pong"]

    @mock_chat("hello")
    async def test_fallback_handles_everything_else(self, mocker: MockerFixture):
        assert [sent.message for sent in self.send_mock.results()] == ["echo: hello"]
