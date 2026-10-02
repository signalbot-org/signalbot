from __future__ import annotations

from typing import TYPE_CHECKING

from signalbot.messages.data_message import DataMessage

if TYPE_CHECKING:
    from signalbot._client import SignalAPI
    from signalbot._generated import MessageEnvelope


class EditMessage(DataMessage):
    """A DataMessage that replaces an earlier message the sender previously sent."""

    target_sent_timestamp: int

    @classmethod
    async def from_data_message(
        cls, data_message: DataMessage, target_sent_timestamp: int
    ) -> EditMessage:
        # Iterating the model reads the fields without going through their getters,
        # so copying the deprecated `source` field doesn't warn
        return cls(**dict(data_message), target_sent_timestamp=target_sent_timestamp)

    @classmethod
    async def from_message_envelope(
        cls, message_envelope: MessageEnvelope, signal: SignalAPI
    ) -> EditMessage:
        if (
            message_envelope.edit_message is not None
            and message_envelope.edit_message.data_message is not None
        ):
            data_message = await cls._internal_parse(
                message_envelope, message_envelope.edit_message.data_message, signal
            )
            return await cls.from_data_message(
                data_message=data_message,
                target_sent_timestamp=message_envelope.edit_message.target_sent_timestamp,
            )

        if (
            message_envelope.sync_message is not None
            and message_envelope.sync_message.sent_message is not None
            and message_envelope.sync_message.sent_message.edit_message is not None
            and message_envelope.sync_message.sent_message.edit_message.data_message
            is not None
        ):
            edit_message = message_envelope.sync_message.sent_message.edit_message
            if edit_message.data_message is not None:
                data_message = await cls._internal_parse(
                    message_envelope, edit_message.data_message, signal
                )

                return await cls.from_data_message(
                    data_message=data_message,
                    target_sent_timestamp=edit_message.target_sent_timestamp,
                )

        error_msg = "MessageEnvelope does not contain an EditMessage"
        raise ValueError(error_msg)
