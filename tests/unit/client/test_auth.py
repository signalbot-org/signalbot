import base64

import aiohttp
from pytest_mock import MockerFixture

from signalbot._client import SignalAPI
from signalbot._generated import SendMessageV2
from signalbot.auth import Authentication, BasicAuthentication, BearerAuthentication
from tests.conftest import GROUP_ID, PHONE_NUMBER, SIGNAL_SERVICE
from tests.unit.client.conftest import HTTP_OK


async def _send_and_capture_auth_header(
    mocker: MockerFixture, auth: Authentication | None
) -> str | None:
    signal_api = SignalAPI(SIGNAL_SERVICE, PHONE_NUMBER, auth=auth)

    json_mock = mocker.AsyncMock(return_value=[{"timestamp": "1638715559464"}])
    mock_session = mocker.AsyncMock()
    mock_session.post.return_value = mocker.AsyncMock(
        spec=aiohttp.ClientResponse,
        status=HTTP_OK,
        json=json_mock,
    )
    mocker.patch("aiohttp.ClientSession", return_value=mock_session)

    data_message = SendMessageV2(
        message="Hello World!",
        number=PHONE_NUMBER,
        recipients=[GROUP_ID],
    )
    resp = await signal_api.messages.send(data_message)

    assert resp[0].timestamp == "1638715559464"

    _, kwargs = mock_session.post.call_args
    return kwargs["headers"].get("Authorization")


async def test_send_with_basic_auth(mocker: MockerFixture):
    username = "user"
    password = "pw"
    credentials = f"{username}:{password}".encode()
    credential_string = base64.b64encode(credentials).decode("utf-8")

    auth = BasicAuthentication(username=username, password=password)
    auth_header = await _send_and_capture_auth_header(mocker, auth)

    assert auth_header == f"Basic {credential_string}"


async def test_send_with_bearer_auth(mocker: MockerFixture):
    token = "token"

    auth = BearerAuthentication(token=token)
    auth_header = await _send_and_capture_auth_header(mocker, auth)

    assert auth_header == f"Bearer {token}"


async def test_send_without_auth(mocker: MockerFixture):
    auth_header = await _send_and_capture_auth_header(mocker, None)

    assert auth_header is None
