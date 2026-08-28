from __future__ import annotations

from typing import TYPE_CHECKING

from signalbot._utils.generated_conversion import from_generated
from signalbot._utils.source import parse_source_from_envelope
from signalbot.events import BaseMessageWithGroup, GroupInfo

if TYPE_CHECKING:
    from signalbot import _generated as generated
    from signalbot._generated import (
        DataMessage,
        MessageEnvelope,
        SyncDataMessage,
    )


class RemoteDelete(BaseMessageWithGroup):
    """Notification that a previously sent message was deleted by its sender."""

    @classmethod
    async def _internal_parse(
        cls,
        message_envelope: MessageEnvelope,
        data_message: DataMessage | SyncDataMessage,
        remote_delete: generated.RemoteDelete,
    ) -> RemoteDelete:
        group_info = from_generated(GroupInfo, data_message.group_info)
        source = parse_source_from_envelope(message_envelope)
        return cls(
            server_delivered_timestamp=message_envelope.server_delivered_timestamp,
            server_received_timestamp=message_envelope.server_received_timestamp,
            source=source.source,
            source_device=message_envelope.source_device,
            source_name=message_envelope.source_name,
            source_number=source.number,
            source_uuid=source.uuid,
            timestamp=remote_delete.timestamp,
            group_info=group_info,
        )

    @classmethod
    async def from_message_envelope(
        cls, message_envelope: MessageEnvelope
    ) -> RemoteDelete:
        if (
            message_envelope.data_message is not None
            and message_envelope.data_message.remote_delete is not None
        ):
            return await cls._internal_parse(
                message_envelope,
                message_envelope.data_message,
                message_envelope.data_message.remote_delete,
            )

        if (
            message_envelope.sync_message is not None
            and message_envelope.sync_message.sent_message is not None
            and message_envelope.sync_message.sent_message.remote_delete is not None
        ):
            return await cls._internal_parse(
                message_envelope,
                message_envelope.sync_message.sent_message,
                message_envelope.sync_message.sent_message.remote_delete,
            )

        error_msg = "MessageEnvelope does not contain a RemoteDelete"
        raise ValueError(error_msg)
