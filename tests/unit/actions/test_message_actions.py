import logging

import pytest
from pytest_mock import MockerFixture

from signalbot._actions.messages import MessageActions
from signalbot._generated import SendMessageResponse
from signalbot.messages import SendMessage
from tests.conftest import PHONE_NUMBER

RECIPIENT = "+4915112345678"
OTHER_RECIPIENT = "+4915187654321"


def _message_actions(
    mocker: MockerFixture, responses: list[SendMessageResponse]
) -> MessageActions:
    signal = mocker.Mock()
    signal.messages.send = mocker.AsyncMock(return_value=responses)
    recipients = mocker.Mock()
    recipients.resolve.side_effect = lambda recipient: recipient
    return MessageActions(
        signal, recipients, logging.getLogger("test"), phone_number=PHONE_NUMBER
    )


async def test_send_logs_recipient_errors(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    response = SendMessageResponse.model_validate(
        {
            "timestamp": "1638715559464",
            "errors": {
                "recipients": [{"number": RECIPIENT, "reason": "Unregistered user"}]
            },
        }
    )
    actions = _message_actions(mocker, [response])

    with caplog.at_level(logging.WARNING):
        sent = await actions.send(SendMessage(text="Hello"), RECIPIENT)

    assert sent.timestamp == 1638715559464
    assert f"not delivered to {RECIPIENT}: Unregistered user" in caplog.text


async def test_send_without_errors_does_not_warn(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    actions = _message_actions(mocker, [SendMessageResponse(timestamp="1638715559464")])

    with caplog.at_level(logging.WARNING):
        await actions.send(SendMessage(text="Hello"), RECIPIENT)

    assert "not delivered" not in caplog.text


async def test_send_multiple_associates_each_response_with_its_recipient(
    mocker: MockerFixture,
):
    actions = _message_actions(
        mocker,
        [
            SendMessageResponse(timestamp="1638715559464"),
            SendMessageResponse(timestamp="1638715559465"),
        ],
    )

    sent = await actions.send_multiple(
        SendMessage(text="Hello"), [RECIPIENT, OTHER_RECIPIENT]
    )

    assert [(s.recipient, s.timestamp) for s in sent] == [
        (RECIPIENT, 1638715559464),
        (OTHER_RECIPIENT, 1638715559465),
    ]
