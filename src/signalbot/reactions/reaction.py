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


class Reaction(BaseMessageWithGroup):
    """A reaction (emoji) added to, or removed from, a previously sent message."""

    emoji: str | None = None
    is_remove: bool
    target_author: str | None = None
    target_author_number: str | None = None
    target_author_uuid: str | None = None

    @classmethod
    async def _internal_parse(
        cls,
        message_envelope: MessageEnvelope,
        data_message: DataMessage | SyncDataMessage,
        reaction_message: generated.Reaction,
    ) -> Reaction:
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
            timestamp=reaction_message.target_sent_timestamp,
            group_info=group_info,
            emoji=reaction_message.emoji,
            is_remove=reaction_message.is_remove,
            target_author=reaction_message.target_author,
            target_author_number=reaction_message.target_author_number,
            target_author_uuid=reaction_message.target_author_uuid,
        )

    @classmethod
    async def from_message_envelope(cls, message_envelope: MessageEnvelope) -> Reaction:
        if (
            message_envelope.data_message is not None
            and message_envelope.data_message.reaction is not None
        ):
            return await cls._internal_parse(
                message_envelope,
                message_envelope.data_message,
                message_envelope.data_message.reaction,
            )

        if (
            message_envelope.sync_message is not None
            and message_envelope.sync_message.sent_message is not None
            and message_envelope.sync_message.sent_message.reaction is not None
        ):
            return await cls._internal_parse(
                message_envelope,
                message_envelope.sync_message.sent_message,
                message_envelope.sync_message.sent_message.reaction,
            )

        error_msg = "MessageEnvelope does not contain a Reaction"
        raise ValueError(error_msg)
