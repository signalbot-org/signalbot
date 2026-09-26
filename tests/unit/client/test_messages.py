from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture, MockType

from signalbot._client import SignalAPI
from signalbot._client.messages import ReceiveError, SendError
from signalbot._generated import (
    CreatePollRequest,
    RemoteDeleteRequest,
    SendMessageV2,
    TypingIndicatorRequest,
)
from tests.conftest import GROUP_ID, PHONE_NUMBER
from tests.unit.client.conftest import HTTP_OK


async def test_send(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    expected_timestamp = "1638715559464"
    mock_json_response("post", [{"timestamp": expected_timestamp}])

    data_message = SendMessageV2(
        message="Hello World!",
        number=PHONE_NUMBER,
        recipients=[GROUP_ID],
    )
    resp = await signal_api.messages.send(data_message)

    assert len(resp) == 1
    assert resp[0].timestamp == expected_timestamp


async def test_send_parses_recipient_errors(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    mock_json_response(
        "post",
        [
            {
                "timestamp": "1638715559464",
                "errors": {
                    "recipients": [
                        {"number": PHONE_NUMBER, "reason": "Unregistered user"}
                    ]
                },
            }
        ],
    )

    data_message = SendMessageV2(
        message="Hello World!",
        number=PHONE_NUMBER,
        recipients=[PHONE_NUMBER],
    )
    [resp] = await signal_api.messages.send(data_message)

    assert resp.errors is not None
    assert resp.errors.recipients is not None
    assert resp.errors.recipients[0].number == PHONE_NUMBER
    assert resp.errors.recipients[0].reason == "Unregistered user"


async def test_poll(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    mock_json_response("post", {"timestamp": "1774791959123"})

    create_poll_request = CreatePollRequest(
        recipient=GROUP_ID,
        question="How much is the fish?",
        answers=["hyper hyper", "3,80 DM"],
        allow_multiple_selections=False,
    )
    resp = await signal_api.polls.create(create_poll_request)

    assert resp.timestamp == "1774791959123"


async def test_send_error_includes_failure_reason(
    signal_api: SignalAPI,
    mock_error_response: Callable[[str, int, str], MockType],
):
    mock_error_response("post", 400, "Bad Request")

    data_message = SendMessageV2(
        message="Hello World!",
        number=PHONE_NUMBER,
        recipients=[GROUP_ID],
    )

    with pytest.raises(SendError) as exc_info:
        await signal_api.messages.send(data_message)

    assert str(exc_info.value) != ""
    assert "400" in str(exc_info.value)
    assert "Bad Request" in str(exc_info.value)


async def test_receive_error_includes_failure_reason(
    signal_api: SignalAPI, mocker: MockerFixture
):
    mock = mocker.patch("websockets.connect")
    mock.return_value.__aenter__.side_effect = OSError("Connection refused")

    with pytest.raises(ReceiveError) as exc_info:
        async for _ in signal_api.messages.receive():
            pass

    assert str(exc_info.value) != ""
    assert "Connection refused" in str(exc_info.value)


async def test_receive(signal_api: SignalAPI, mocker: MockerFixture):
    messages = ['{"id": 1}', '{"id": 2}']
    mock_iterator = mocker.AsyncMock()
    mock_iterator.__aiter__.return_value = messages
    mock = mocker.patch("websockets.connect")
    mock.return_value.__aenter__.return_value = mock_iterator

    results = [raw_message async for raw_message in signal_api.messages.receive()]

    assert results == messages


async def test_remote_delete(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    expected_timestamp = "1638715559464"
    mock_json_response("delete", {"timestamp": expected_timestamp})

    remote_delete_request = RemoteDeleteRequest(
        recipient=PHONE_NUMBER, timestamp=1638715559464
    )
    resp = await signal_api.messages.remote_delete(remote_delete_request)

    assert resp.timestamp == expected_timestamp


async def test_start_typing(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    mock = mock_json_response("put", {})

    request = TypingIndicatorRequest(recipient=PHONE_NUMBER)
    resp = await signal_api.messages.start_typing(request)

    assert mock.call_count == 1
    assert resp.status == HTTP_OK


async def test_stop_typing(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    mock = mock_json_response("delete", {})

    request = TypingIndicatorRequest(recipient=PHONE_NUMBER)
    resp = await signal_api.messages.stop_typing(request)

    assert mock.call_count == 1
    assert resp.status == HTTP_OK
