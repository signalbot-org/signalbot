import asyncio

import aiohttp
import pytest
from packaging.version import InvalidVersion
from pytest_mock import MockerFixture

from signalbot import (
    MIN_SIGNAL_CLI_REST_API_VERSION,
    Command,
    ConnectionMode,
    SignalAPI,
    SignalBot,
)
from signalbot.context import Context
from signalbot.utils import DummyCommand


class TestCommon:
    signal_service = "127.0.0.1:8080"
    phone_number = "+49123456789"
    group_id = "group.OyZzqio1xDmYiLsQ1VsqRcUFOU4tK2TcECmYt2KeozHJwglMBHAPS7jlkrm="
    internal_id = "Mg8LQTdaZJs8+LJCrtQgblqHx+xI2dX9JJ8hVA2kqt8="

    @pytest.fixture(autouse=True)
    def setup(self):
        config = {
            "signal_service": self.signal_service,
            "phone_number": self.phone_number,
            "storage": {"type": "in-memory"},
        }
        self.signal_bot = SignalBot(config)


class TestProducer(TestCommon):
    @pytest.mark.asyncio
    async def test_produce(self, mocker: MockerFixture):
        # Two messages
        message1 = '{"envelope":{"source":"+4901234567890","sourceNumber":"+4901234567890","sourceUuid":"asdf","sourceName":"name","sourceDevice":1,"timestamp":1633169000000,"syncMessage":{"sentMessage":{"timestamp":1633169000000,"message":"Message 1","expiresInSeconds":0,"viewOnce":false,"mentions":[],"attachments":[],"contacts":[],"groupInfo":{"groupId":"Mg8LQTdaZJs8+LJCrtQgblqHx+xI2dX9JJ8hVA2kqt8=","type":"DELIVER"},"destination":null,"destinationNumber":null,"destinationUuid":null}}}}'  # noqa: E501
        message2 = '{"envelope":{"source":"+4901234567890","sourceNumber":"+4901234567890","sourceUuid":"asdf","sourceName":"name","sourceDevice":1,"timestamp":1633169000000,"syncMessage":{"sentMessage":{"timestamp":1633169000000,"message":"Message 2","expiresInSeconds":0,"viewOnce":false,"mentions":[],"attachments":[],"contacts":[],"groupInfo":{"groupId":"Mg8LQTdaZJs8+LJCrtQgblqHx+xI2dX9JJ8hVA2kqt8=","type":"DELIVER"},"destination":null,"destinationNumber":null,"destinationUuid":null}}}}'  # noqa: E501
        messages = [message1, message2]
        mock_iterator = mocker.AsyncMock()
        mock_iterator.__aiter__.return_value = messages
        mock = mocker.patch("websockets.connect")
        mock.return_value.__aenter__.return_value = mock_iterator

        group_mock = mocker.AsyncMock()
        group_mock.return_value = [
            {
                "name": "mocked group",
                "id": self.group_id,
                "internal_id": self.internal_id,
            },
        ]
        get_group_mock = mocker.patch(
            "aiohttp.ClientSession.get", new_callable=mocker.AsyncMock
        )
        get_group_mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            status_code=200,
            json=group_mock,
        )

        self.signal_bot._q = asyncio.Queue()
        self.signal_bot._signal = SignalAPI(
            self.signal_service,
            self.phone_number,
        )

        # Any two commands
        self.signal_bot.register(DummyCommand())
        self.signal_bot.register(DummyCommand())
        await self.signal_bot._resolve_commands()

        await self.signal_bot._produce(1337)

        assert self.signal_bot._q.qsize() == 4  # noqa: PLR2004


class TestGetter(TestCommon):
    def test_null_group(self):
        assert not self.signal_bot.get_group("none")

    @pytest.mark.asyncio
    async def test_get_group(self, mocker: MockerFixture):
        class GroupInspector(Command):
            def __init__(self):  # noqa: ANN204
                self.found_group = None

            async def handle(self, context: Context) -> None:
                self.found_group = self.bot.get_group(context.message.group)

        message = '{"envelope":{"source":"+4901234567890","sourceNumber":"+4901234567890","sourceUuid":"asdf","sourceName":"name","sourceDevice":1,"timestamp":1633169000000,"syncMessage":{"sentMessage":{"timestamp":1633169000000,"message":"Message 1","expiresInSeconds":0,"viewOnce":false,"mentions":[],"attachments":[],"contacts":[],"groupInfo":{"groupId":"Mg8LQTdaZJs8+LJCrtQgblqHx+xI2dX9JJ8hVA2kqt8=","type":"DELIVER"},"destination":null,"destinationNumber":null,"destinationUuid":null}}}}'  # noqa: E501
        messages = [message]
        mock_iterator = mocker.AsyncMock()
        mock_iterator.__aiter__.return_value = messages
        mock = mocker.patch("websockets.connect")
        mock.return_value.__aenter__.return_value = mock_iterator

        group_mock = mocker.AsyncMock()
        fake_group = {
            "name": "mocked group",
            "id": self.group_id,
            "internal_id": self.internal_id,
        }
        group_mock.return_value = [fake_group]
        get_group_mock = mocker.patch(
            "aiohttp.ClientSession.get", new_callable=mocker.AsyncMock
        )
        get_group_mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            status_code=200,
            json=group_mock,
        )

        self.signal_bot._q = asyncio.Queue()
        self.signal_bot._signal = SignalAPI(
            self.signal_service,
            self.phone_number,
        )

        inspector = GroupInspector()
        self.signal_bot.register(inspector)

        await self.signal_bot._resolve_commands()

        await self.signal_bot._produce(1337)

        await self.signal_bot._consume_new_item(1337)

        assert inspector.found_group == fake_group
        assert inspector.found_group is not fake_group


class TestSignalApiProtocolConfig:
    signal_service = "127.0.0.1:8080"
    phone_number = "+49123456789"

    def test_connection_mode_defaults_to_auto(self):
        signal_bot = SignalBot(
            {
                "signal_service": self.signal_service,
                "phone_number": self.phone_number,
                "storage": {"type": "in-memory"},
            }
        )

        assert signal_bot._signal.connection_mode == ConnectionMode.AUTO
        assert signal_bot._signal._signal_api_uris.use_https is True

    def test_connection_mode_can_be_set_to_http_only(self):
        signal_bot = SignalBot(
            {
                "signal_service": self.signal_service,
                "phone_number": self.phone_number,
                "storage": {"type": "in-memory"},
                "connection_mode": ConnectionMode.HTTP_ONLY,
            }
        )

        assert signal_bot._signal.connection_mode == ConnectionMode.HTTP_ONLY
        assert signal_bot._signal._signal_api_uris.use_https is False

    def test_connection_mode_can_be_set_to_https_only(self):
        signal_bot = SignalBot(
            {
                "signal_service": self.signal_service,
                "phone_number": self.phone_number,
                "storage": {"type": "in-memory"},
                "connection_mode": ConnectionMode.HTTPS_ONLY,
            }
        )

        assert signal_bot._signal.connection_mode == ConnectionMode.HTTPS_ONLY
        assert signal_bot._signal._signal_api_uris.use_https is True


@pytest.mark.asyncio
class TestSignalApiVersionCheck(TestCommon):
    async def test_new_version_is_okay(self, mocker: MockerFixture):
        version_mock = mocker.patch.object(
            self.signal_bot,
            "signal_cli_rest_api_version",
            new_callable=mocker.AsyncMock,
        )
        version_mock.return_value = str(MIN_SIGNAL_CLI_REST_API_VERSION)

        await self.signal_bot._check_signal_cli_rest_api_version()

        version_mock.return_value = f"{MIN_SIGNAL_CLI_REST_API_VERSION.major + 1}.0.0"
        await self.signal_bot._check_signal_cli_rest_api_version()

    async def test_unset_version(self, mocker: MockerFixture):
        version_mock = mocker.patch.object(
            self.signal_bot,
            "signal_cli_rest_api_version",
            new_callable=mocker.AsyncMock,
        )
        version_mock.return_value = "unset"

        await self.signal_bot._check_signal_cli_rest_api_version()

    async def test_old_version_raises_runtime_error(self, mocker: MockerFixture):
        version_mock = mocker.patch.object(
            self.signal_bot,
            "signal_cli_rest_api_version",
            new_callable=mocker.AsyncMock,
        )
        prev_version = f"{MIN_SIGNAL_CLI_REST_API_VERSION.major}."
        prev_version += f"{MIN_SIGNAL_CLI_REST_API_VERSION.minor - 1}.0"
        version_mock.return_value = prev_version

        with pytest.raises(
            RuntimeError, match="Incompatible signal-cli-rest-api version"
        ):
            await self.signal_bot._check_signal_cli_rest_api_version()

    async def test_invalid_version(self, mocker: MockerFixture):
        version_mock = mocker.patch.object(
            self.signal_bot,
            "signal_cli_rest_api_version",
            new_callable=mocker.AsyncMock,
        )
        version_mock.return_value = "abc"

        with pytest.raises(InvalidVersion, match="Invalid version: 'abc'"):
            await self.signal_bot._check_signal_cli_rest_api_version()


class TestUsernameValidation(TestCommon):
    def test_valid_username(self):
        valid_usernames = [
            "Usr.99",
            "UserName.99",
            "username.999999999",
            "UserName99.99",
            "_Use_rName99_.99",
            "usernameeeeeeeeeeeeeeeeeeeeeeeee.999999999",
        ]
        for valid_username in valid_usernames:
            assert self.signal_bot._is_username(valid_username)

    def test_invalid_username(self):
        invalid_usernames = [
            "Us.99",
            "Usr.9",
            ".UserName99",
            ".UserName.99",
            "UserName99",
            "UserName99.",
            "username.9999999999",
            "user@name.999",
            "UserName99.0",
            "UserName99.00",
            "UserName99.000000000",
            ".usernameeeeeeeeeeeeeeeeeeeeeeeeee.99",
        ]
        for invalid_username in invalid_usernames:
            assert not self.signal_bot._is_username(invalid_username)


class TestRegisterCommand(TestCommon):
    def test_register_one_command(self):
        self.signal_bot.register(DummyCommand())
        assert len(self.signal_bot._commands_to_be_registered) == 1

    def test_register_three_commands(self):
        self.signal_bot.register(DummyCommand())
        self.signal_bot.register(DummyCommand())
        self.signal_bot.register(DummyCommand())
        assert len(self.signal_bot._commands_to_be_registered) == 3  # noqa: PLR2004

    def test_register_calls_setup_of_command(self):
        class SomeTestCommand(Command):
            def __init__(self):  # noqa: ANN204
                self.state = False

            def setup(self):  # noqa: ANN202
                self.state = True

            def handle(self, context: Context):  # noqa: ANN202
                pass

        cmd = SomeTestCommand()
        assert cmd.state is False

        self.signal_bot.register(cmd)
        assert cmd.state is True

    @pytest.mark.asyncio
    async def test_register_single_contact(self):
        user_number = "+49987654321"
        self.signal_bot.register(DummyCommand(), contacts=[user_number])
        await self.signal_bot._resolve_commands()
        assert self.signal_bot.commands[0][1] == [user_number]

    @pytest.mark.asyncio
    async def test_register_multiple_contacts(self):
        user_number1 = "+49987654321"
        user_number2 = "+49987654322"
        user_number3 = "+49987654323"
        self.signal_bot.register(
            DummyCommand(),
            contacts=[user_number1, user_number2, user_number3],
        )
        await self.signal_bot._resolve_commands()
        expected_user_chats = [user_number1, user_number2, user_number3]
        assert self.signal_bot.commands[0][1] == expected_user_chats

    @pytest.mark.asyncio
    async def test_register_multiple_contacts_multiple_commands(self):
        user_number1 = "+49987654321"
        user_number2 = "+49987654322"
        user_number3 = "+49987654323"
        self.signal_bot.register(DummyCommand(), contacts=[user_number1, user_number2])
        self.signal_bot.register(DummyCommand(), contacts=[user_number3])
        await self.signal_bot._resolve_commands()
        expected_user_chats_cmd0 = [user_number1, user_number2]
        expected_user_chats_cmd1 = [user_number3]
        assert self.signal_bot.commands[0][1] == expected_user_chats_cmd0
        assert self.signal_bot.commands[1][1] == expected_user_chats_cmd1


@pytest.mark.asyncio
class TestPoll(TestCommon):
    async def test_poll_with_phone_number(self, mocker: MockerFixture):
        receiver = "+49987654321"
        question = "What's your favorite color?"
        answers = ["Red", "Blue", "Green"]
        timestamp = 1633169000000

        # Mock the SignalAPI.poll method
        poll_mock = mocker.AsyncMock()
        poll_mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            json=mocker.AsyncMock(return_value={"timestamp": timestamp}),
        )
        mocker.patch.object(self.signal_bot._signal, "poll", poll_mock)

        result = await self.signal_bot.poll(receiver, question, answers)

        assert result == timestamp
        poll_mock.assert_called_once_with(
            receiver, question, answers, allow_multiple_selections=False
        )

    async def test_poll_with_group_id(self, mocker: MockerFixture):
        receiver = self.group_id
        question = "What should we do?"
        answers = ["Option A", "Option B"]
        timestamp = 1633169000001

        # Mock the SignalAPI.poll method
        poll_mock = mocker.AsyncMock()
        poll_mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            json=mocker.AsyncMock(return_value={"timestamp": timestamp}),
        )
        mocker.patch.object(self.signal_bot._signal, "poll", poll_mock)

        result = await self.signal_bot.poll(receiver, question, answers)

        assert result == timestamp
        poll_mock.assert_called_once_with(
            receiver,
            question,
            answers,
            allow_multiple_selections=False,
        )

    async def test_poll_with_multiple_selections(self, mocker: MockerFixture):
        receiver = "+49987654321"
        question = "Which colors do you like?"
        answers = ["Red", "Blue", "Green", "Yellow"]
        timestamp = 1633169000002
        allow_multiple = True

        # Mock the SignalAPI.poll method
        poll_mock = mocker.AsyncMock()
        poll_mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            json=mocker.AsyncMock(return_value={"timestamp": timestamp}),
        )
        mocker.patch.object(self.signal_bot._signal, "poll", poll_mock)

        result = await self.signal_bot.poll(
            receiver,
            question,
            answers,
            allow_multiple_selections=allow_multiple,
        )

        assert result == timestamp
        poll_mock.assert_called_once_with(
            receiver,
            question,
            answers,
            allow_multiple_selections=True,
        )
