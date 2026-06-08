import base64

import aiohttp
import pytest
from pytest_mock import MockerFixture

from signalbot import ConnectionMode, SignalAPI
from signalbot.api import HEALTH_CHECK_GOOD_STATUS, HealthCheckError
from signalbot.auth import Authentication, BasicAuthentication, BearerAuthentication


class TestAPI:
    signal_service = "127.0.0.1:8080"
    phone_number = "+49123456789"

    group_id = "group.OyZzqio1xDmYiLsQ1VsqRcUFOU4tK2TcECmYt2KeozHJwglMBHAPS7jlkrm="

    @pytest.fixture(autouse=True)
    def setup(self):
        self.signal_api = SignalAPI(self.signal_service, self.phone_number)

    @pytest.mark.asyncio
    async def test_send(self, mocker: MockerFixture):
        status_code = 201
        mock2 = mocker.AsyncMock()
        mock2.return_value = {"timestamp": "1638715559464"}

        mock = mocker.patch("aiohttp.ClientSession.post", new_callable=mocker.AsyncMock)
        mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            status_code=status_code,
            json=mock2,
        )

        receiver = self.group_id
        message = "Hello World!"
        resp = await self.signal_api.send(receiver, message)

        assert resp.status_code == status_code

    @pytest.mark.asyncio
    async def test_poll(self, mocker: MockerFixture):
        status_code = 201
        mock2 = mocker.AsyncMock()
        mock2.return_value = {"timestamp": "1774791959123"}

        mock = mocker.patch("aiohttp.ClientSession.post", new_callable=mocker.AsyncMock)
        mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            status_code=status_code,
            json=mock2,
        )

        receiver = self.group_id
        question = "How much is the fish?"
        answers = ["hyper hyper", "3,80 DM"]
        resp = await self.signal_api.poll(receiver, question, answers)

        assert resp.status_code == status_code

    @pytest.mark.asyncio
    async def test_receive(self, mocker: MockerFixture):
        message1 = '{"envelope":{"source":"+4901234567890","sourceNumber":"+4901234567890","sourceUuid":"asdf","sourceName":"name","sourceDevice":1,"timestamp":1633169000000,"syncMessage":{"sentMessage":{"timestamp":1633169000000,"message":"Message 1","expiresInSeconds":0,"viewOnce":false,"mentions":[],"attachments":[],"contacts":[],"groupInfo":{"groupId":"group1","type":"DELIVER"},"destination":null,"destinationNumber":null,"destinationUuid":null}}}}'  # noqa: E501
        message2 = '{"envelope":{"source":"+4901234567890","sourceNumber":"+4901234567890","sourceUuid":"asdf","sourceName":"name","sourceDevice":1,"timestamp":1633169000000,"syncMessage":{"sentMessage":{"timestamp":1633169000000,"message":"Message 2","expiresInSeconds":0,"viewOnce":false,"mentions":[],"attachments":[],"contacts":[],"groupInfo":{"groupId":"group1","type":"DELIVER"},"destination":null,"destinationNumber":null,"destinationUuid":null}}}}'  # noqa: E501
        messages = [message1, message2]
        mock_iterator = mocker.AsyncMock()
        mock_iterator.__aiter__.return_value = messages
        mock = mocker.patch("websockets.connect")
        mock.return_value.__aenter__.return_value = mock_iterator

        results = [raw_message async for raw_message in self.signal_api.receive()]

        assert len(results) == len(messages)
        for i, _ in enumerate(results):
            assert messages[i] == results[i]

    def test_receive_uri(self):
        expected_uri = f"wss://{self.signal_service}/v1/receive/{self.phone_number}"
        actual_uri = self.signal_api._signal_api_uris.receive_ws_uri()
        assert actual_uri == expected_uri

    def test_send_uri(self):
        expected_uri = f"https://{self.signal_service}/v2/send"
        actual_uri = self.signal_api._signal_api_uris.send_rest_uri()
        assert actual_uri == expected_uri

    def test_poll_uri(self):
        expected_uri = f"https://{self.signal_service}/v1/polls/{self.phone_number}"
        actual_uri = self.signal_api._signal_api_uris.poll_rest_uri()
        assert actual_uri == expected_uri

    def test_attachment_rest_uri(self):
        expected_uri = f"https://{self.signal_service}/v1/attachments"
        actual_uri = self.signal_api._signal_api_uris.attachment_rest_uri()
        assert actual_uri == expected_uri

    @pytest.mark.asyncio
    async def test_check_signal_service_prefers_configured_protocol(
        self, mocker: MockerFixture
    ):
        signal_api = SignalAPI(
            self.signal_service,
            self.phone_number,
            connection_mode=ConnectionMode.HTTP_ONLY,
        )

        health_check_mock = mocker.patch.object(
            signal_api, "health_check", new_callable=mocker.AsyncMock
        )
        health_check_mock.return_value = mocker.Mock(status=HEALTH_CHECK_GOOD_STATUS)

        is_healthy = await signal_api.check_signal_service()

        assert is_healthy is True
        assert signal_api._signal_api_uris.use_https is False

    @pytest.mark.asyncio
    async def test_check_signal_service_https_only_uses_secure_protocol(
        self, mocker: MockerFixture
    ):
        signal_api = SignalAPI(
            self.signal_service,
            self.phone_number,
            connection_mode=ConnectionMode.HTTPS_ONLY,
        )

        health_check_mock = mocker.patch.object(
            signal_api, "health_check", new_callable=mocker.AsyncMock
        )
        health_check_mock.return_value = mocker.Mock(status=HEALTH_CHECK_GOOD_STATUS)

        is_healthy = await signal_api.check_signal_service()

        assert is_healthy is True
        assert health_check_mock.call_count == 1
        assert signal_api._signal_api_uris.use_https is True

    @pytest.mark.asyncio
    async def test_check_signal_service_does_not_fallback_if_protocol_configured(
        self, mocker: MockerFixture
    ):
        signal_api = SignalAPI(
            self.signal_service,
            self.phone_number,
            connection_mode=ConnectionMode.HTTP_ONLY,
        )

        health_check_mock = mocker.patch.object(
            signal_api, "health_check", new_callable=mocker.AsyncMock
        )
        health_check_mock.side_effect = HealthCheckError()

        is_healthy = await signal_api.check_signal_service()

        assert is_healthy is False
        assert health_check_mock.call_count == 1
        assert signal_api._signal_api_uris.use_https is False

    @pytest.mark.asyncio
    async def test_check_signal_service_falls_back_to_other_protocol_in_auto_mode(
        self, mocker: MockerFixture
    ):
        signal_api = SignalAPI(self.signal_service, self.phone_number)

        health_check_mock = mocker.patch.object(
            signal_api, "health_check", new_callable=mocker.AsyncMock
        )
        health_check_mock.side_effect = [
            HealthCheckError(),
            mocker.Mock(status=HEALTH_CHECK_GOOD_STATUS),
        ]

        is_healthy = await signal_api.check_signal_service()

        assert is_healthy is True
        assert signal_api._signal_api_uris.use_https is False

    @pytest.mark.asyncio
    async def test_check_signal_service_auto_succeeds_without_fallback(
        self, mocker: MockerFixture
    ):
        signal_api = SignalAPI(
            self.signal_service,
            self.phone_number,
            connection_mode=ConnectionMode.AUTO,
        )

        health_check_mock = mocker.patch.object(
            signal_api, "health_check", new_callable=mocker.AsyncMock
        )
        health_check_mock.return_value = mocker.Mock(status=HEALTH_CHECK_GOOD_STATUS)

        is_healthy = await signal_api.check_signal_service()

        assert is_healthy is True
        assert health_check_mock.call_count == 1
        assert signal_api._signal_api_uris.use_https is True

    async def _send_with_auth_helper(
        self, mocker: MockerFixture, auth: Authentication | None
    ) -> None:
        signal_api = SignalAPI(self.signal_service, self.phone_number, auth=auth)

        status_code = 201
        mock2 = mocker.AsyncMock()
        mock2.return_value = {"timestamp": "1638715559464"}

        mock_session = mocker.AsyncMock()
        mock_session.post.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            status_code=status_code,
            json=mock2,
        )

        mock = mocker.patch("aiohttp.ClientSession")
        mock.return_value.__aenter__.return_value = mock_session

        receiver = self.group_id
        message = "Hello World!"

        resp = await signal_api.send(receiver, message)

        _, kwargs = mock.call_args

        assert resp.status_code == status_code
        return kwargs["headers"].get("Authorization")

    @pytest.mark.asyncio
    async def test_send_with_basic_auth(self, mocker: MockerFixture):
        username = "user"
        password = "pw"  # noqa: S105

        credentials = f"{username}:{password}".encode()
        credential_string = base64.b64encode(credentials).decode("utf-8")

        auth = BasicAuthentication(username=username, password=password)

        auth_header = await self._send_with_auth_helper(mocker, auth)

        assert auth_header == f"Basic {credential_string}"

    @pytest.mark.asyncio
    async def test_send_with_bearer_auth(self, mocker: MockerFixture):
        token = "token"  # noqa: S105

        auth = BearerAuthentication(token=token)

        auth_header = await self._send_with_auth_helper(mocker, auth)

        assert auth_header == f"Bearer {token}"

    @pytest.mark.asyncio
    async def test_send_without_auth(self, mocker: MockerFixture):
        auth_header = await self._send_with_auth_helper(mocker, None)

        assert auth_header is None
