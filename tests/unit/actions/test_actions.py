"""Unit tests for the `*Actions` classes other than `MessageActions` (see
`test_message_actions.py`).

Each test wires an action class to a mocked `SignalAPI` and asserts on the wire
request it hands to the client.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from signalbot import SignalBotError
from signalbot._actions.attachments import AttachmentActions
from signalbot._actions.contacts import ContactActions
from signalbot._actions.groups import GroupActions
from signalbot._actions.reactions import ReactionActions
from signalbot._actions.receipts import ReceiptActions
from signalbot.attachments import Attachment
from signalbot.contacts import UpdateContact
from signalbot.groups import UpdateGroup
from signalbot.messages import SentMessage
from signalbot.receipts import ReceiptType
from tests.conftest import GROUP_ID, PHONE_NUMBER
from tests.unit.conftest import (
    PRIVATE_NUMBER,
    PRIVATE_UUID,
    make_data_message,
    make_group_data_message,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

LOGGER = logging.getLogger("test")


@pytest.fixture
def signal(mocker: MockerFixture):
    signal = mocker.Mock()
    signal.attachments.delete = mocker.AsyncMock()
    signal.contacts.update = mocker.AsyncMock()
    signal.groups.update = mocker.AsyncMock()
    signal.messages.send = mocker.AsyncMock()
    signal.reactions.react = mocker.AsyncMock()
    signal.receipts.send = mocker.AsyncMock()
    return signal


@pytest.fixture
def recipients(mocker: MockerFixture):
    """A resolver that maps every recipient to itself, except group internal
    ids, which it maps to `GROUP_ID` (like the real one does for a known group)."""
    recipients = mocker.Mock()
    recipients.resolve.side_effect = lambda recipient: (
        recipient if recipient in (PRIVATE_NUMBER, PRIVATE_UUID) else GROUP_ID
    )
    return recipients


class TestAttachmentActions:
    async def test_delete_forwards_the_attachment(self, signal, recipients):
        attachment = Attachment(local_filename="a.png", isVoiceNote=False)

        await AttachmentActions(signal, recipients, LOGGER).delete(attachment)

        signal.attachments.delete.assert_awaited_once_with(attachment)


class TestContactActions:
    async def test_update_resolves_recipient_and_sends_request(
        self, signal, recipients
    ):
        actions = ContactActions(signal, recipients, LOGGER)

        await actions.update(UpdateContact(name="Alice"), PRIVATE_NUMBER)

        recipients.resolve.assert_called_once_with(PRIVATE_NUMBER)
        [request] = signal.contacts.update.await_args.args
        assert request.recipient == PRIVATE_NUMBER
        assert request.name == "Alice"


class TestGroupActions:
    async def test_update_sends_request_to_resolved_group(
        self, signal, mocker: MockerFixture
    ):
        groups = mocker.Mock()
        groups.resolve.return_value = GROUP_ID
        actions = GroupActions(signal, groups, LOGGER)

        await actions.update(UpdateGroup(name="New name"), "Old name")

        groups.resolve.assert_called_once_with("Old name")
        request, group_id = signal.groups.update.await_args.args
        assert group_id == GROUP_ID
        assert request.name == "New name"

    async def test_update_unknown_group_raises_without_sending(
        self, signal, mocker: MockerFixture
    ):
        groups = mocker.Mock()
        groups.resolve.return_value = None
        actions = GroupActions(signal, groups, LOGGER)

        with pytest.raises(SignalBotError):
            await actions.update(UpdateGroup(name="New name"), "nope")

        signal.groups.update.assert_not_awaited()


class TestReactionActions:
    @pytest.fixture
    def actions(self, signal, recipients) -> ReactionActions:
        return ReactionActions(signal, recipients, LOGGER, phone_number=PHONE_NUMBER)

    async def test_react_to_own_sent_message_targets_the_bot(self, actions, signal):
        sent = SentMessage(text="hi", recipient=PRIVATE_NUMBER, timestamp=42)

        await actions.react(sent, "👍")

        [request] = signal.reactions.react.await_args.args
        assert request.recipient == PRIVATE_NUMBER
        assert request.target_author == PHONE_NUMBER
        assert request.timestamp == 42
        assert request.reaction == "👍"

    async def test_react_to_private_message_targets_the_sender(
        self, actions, signal, recipients
    ):
        await actions.react(make_data_message(timestamp=7), "🎉")

        [request] = signal.reactions.react.await_args.args
        assert request.recipient == PRIVATE_UUID
        assert request.target_author == PRIVATE_UUID
        assert request.timestamp == 7
        # private recipients are already uuids/numbers, no resolution needed
        recipients.resolve.assert_not_called()

    async def test_react_to_group_message_resolves_group_and_targets_sender(
        self, actions, signal
    ):
        await actions.react(make_group_data_message(), "🎉")

        [request] = signal.reactions.react.await_args.args
        assert request.recipient == GROUP_ID
        assert request.target_author == PRIVATE_UUID

    async def test_react_to_group_message_falls_back_to_source_number(
        self, actions, signal
    ):
        await actions.react(make_group_data_message(source_uuid=None), "🎉")

        [request] = signal.reactions.react.await_args.args
        assert request.target_author == PRIVATE_NUMBER

    async def test_react_to_group_message_without_source_raises(self, actions, signal):
        message = make_group_data_message(source_uuid=None, source_number=None)

        with pytest.raises(ValueError, match="without source uuid"):
            await actions.react(message, "🎉")

        signal.reactions.react.assert_not_awaited()

    async def test_react_to_private_message_without_source_raises(
        self, actions, signal
    ):
        message = make_data_message(source_uuid=None, source_number=None)

        with pytest.raises(ValueError, match="does not contain a source"):
            await actions.react(message, "🎉")

        signal.reactions.react.assert_not_awaited()


class TestReceiptActions:
    async def test_send_receipt_for_private_message(self, signal, recipients):
        actions = ReceiptActions(signal, recipients, LOGGER)

        await actions.send(make_data_message(timestamp=9), ReceiptType.READ)

        [request] = signal.receipts.send.await_args.args
        assert request.recipient == PRIVATE_UUID
        assert request.receipt_type == ReceiptType.READ
        assert request.timestamp == 9

    async def test_group_receipts_are_skipped_with_a_warning(
        self, signal, recipients, caplog: pytest.LogCaptureFixture
    ):
        actions = ReceiptActions(signal, recipients, LOGGER)

        with caplog.at_level(logging.WARNING):
            await actions.send(make_group_data_message(), ReceiptType.READ)

        signal.receipts.send.assert_not_awaited()
        assert "not supported for groups" in caplog.text
