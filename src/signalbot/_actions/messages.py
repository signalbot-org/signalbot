from __future__ import annotations

from typing import TYPE_CHECKING

from signalbot._actions.base import BotActionsBase
from signalbot._generated import RemoteDeleteRequest, TypingIndicatorRequest
from signalbot.messages import SentMessage

if TYPE_CHECKING:
    import logging

    from signalbot._client import SignalAPI
    from signalbot._generated import SendMessageResponse
    from signalbot._recipients import RecipientResolver
    from signalbot.messages import SendMessage


class MessageActions(BotActionsBase):
    def __init__(
        self,
        signal: SignalAPI,
        recipients: RecipientResolver,
        logger: logging.Logger,
        phone_number: str,
    ) -> None:
        super().__init__(signal, recipients, logger)
        self._phone_number = phone_number

    async def send(
        self,
        message: SendMessage,
        recipient: str,
    ) -> SentMessage:
        """Send or edit a message.

        Args:
            message: The message to send.
            recipient: The contact or group to send the message to.

        Returns:
            A SentMessage instance.
        """
        recipient = self._recipients.resolve(recipient)

        send_message_v2 = await message.to_generated(self._phone_number, [recipient])
        [send_message_response] = await self._signal.messages.send(send_message_v2)
        timestamp = int(send_message_response.timestamp)
        self._logger.info("[Bot] New message %s sent:\n%s", timestamp, message.text)
        self._log_send_errors(send_message_response)

        return SentMessage.from_send_message(message, recipient, timestamp)

    async def send_multiple(
        self,
        message: SendMessage,
        recipients: list[str],
    ) -> list[SentMessage]:
        """Send one message to multiple recipients.

        `recipients` must be either one or more 1:1 contacts, or a single
        group. Any other combination (mixing contacts and groups, or more
        than one group) is rejected: no message is sent and a warning is
        logged.

        Args:
            message: The message to send.
            recipients: The contacts or groups to send the message to.

        Returns:
            A list of SentMessage instances, one per recipient. Empty if
            `recipients` was not a valid combination.
        """
        recipients = [self._recipients.resolve(recipient) for recipient in recipients]

        if not self._is_valid_send_multiple_recipients(recipients):
            self._logger.warning(
                "[Bot] send_multiple requires either one or more 1:1 recipients "
                "or a single group, not %s",
                recipients,
            )
            return []

        send_message_v2 = await message.to_generated(self._phone_number, recipients)
        send_message_responses = await self._signal.messages.send(send_message_v2)
        timestamps = [int(response.timestamp) for response in send_message_responses]

        self._logger.info("[Bot] New message %s sent:\n%s", timestamps, message.text)
        for send_message_response in send_message_responses:
            self._log_send_errors(send_message_response)

        return SentMessage.from_send_message_multiple(message, recipients, timestamps)

    def _log_send_errors(self, send_message_response: SendMessageResponse) -> None:
        """Warn about recipients the message could not be delivered to."""
        errors = send_message_response.errors
        if errors is None or errors.recipients is None:
            return

        for error in errors.recipients:
            self._logger.warning(
                "[Bot] Message %s not delivered to %s: %s",
                send_message_response.timestamp,
                error.number or error.uuid or error.username,
                error.reason,
            )

    @staticmethod
    def _is_valid_send_multiple_recipients(recipients: list[str]) -> bool:
        """Valid combinations are one or more 1:1 contacts, or a single group."""
        group_count = sum(
            1 for recipient in recipients if recipient.startswith("group.")
        )
        contact_count = len(recipients) - group_count
        return (group_count == 0 and contact_count >= 1) or (
            group_count == 1 and contact_count == 0
        )

    async def edit(
        self, new_message: SendMessage, original_message: SentMessage
    ) -> SentMessage:
        """Edit a message.

        Args:
            new_message: The message to send.
            original_message: The original message to edit.

        Returns:
            A SentMessage instance.
        """
        new_message.edit_timestamp = original_message.timestamp
        return await self.send(new_message, original_message.recipient)

    async def remote_delete(
        self,
        sent_message: SentMessage,
    ) -> int:
        """Delete a previously sent message.

        Args:
            sent_message: The message to delete.

        Returns:
            The timestamp of the delete action.
        """
        remote_delete_request = RemoteDeleteRequest(
            recipient=self._recipients.resolve(sent_message.recipient),
            timestamp=sent_message.timestamp,
        )

        remote_delete_response = await self._signal.messages.remote_delete(
            remote_delete_request
        )
        ret_timestamp = int(remote_delete_response.timestamp)
        self._logger.info(
            "[Bot] Deleted message with timestamp %s",
            sent_message.timestamp,
        )

        return ret_timestamp

    async def start_typing(self, recipient: str) -> None:
        """Send a typing indicator to a recipient.

        Args:
            recipient: Message recipient.
        """
        recipient = self._recipients.resolve(recipient)
        await self._signal.messages.start_typing(
            TypingIndicatorRequest(recipient=recipient)
        )

    async def stop_typing(self, recipient: str) -> None:
        """Stop a typing indicator for a recipient.

        Args:
            recipient: Message recipient.
        """
        recipient = self._recipients.resolve(recipient)
        await self._signal.messages.stop_typing(
            TypingIndicatorRequest(recipient=recipient)
        )
