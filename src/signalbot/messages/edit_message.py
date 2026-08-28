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
        return cls(
            server_delivered_timestamp=data_message.server_delivered_timestamp,
            server_received_timestamp=data_message.server_received_timestamp,
            source_device=data_message.source_device,
            source=data_message.source,
            source_name=data_message.source_name,
            source_number=data_message.source_number,
            source_uuid=data_message.source_uuid,
            group_info=data_message.group_info,
            attachments=data_message.attachments,
            expires_in_seconds=data_message.expires_in_seconds,
            mentions=data_message.mentions,
            text=data_message.text,
            previews=data_message.previews,
            base64_previews=data_message.base64_previews,
            quote=data_message.quote,
            sticker=data_message.sticker,
            text_styles=data_message.text_styles,
            timestamp=data_message.timestamp,
            view_once=data_message.view_once,
            target_sent_timestamp=target_sent_timestamp,
        )

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
