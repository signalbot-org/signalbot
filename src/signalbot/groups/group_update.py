from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from signalbot.events import BaseMessage

if TYPE_CHECKING:
    from signalbot import _generated as generated
    from signalbot._generated import DataMessage, MessageEnvelope, SyncDataMessage


class GroupUpdateInfo(BaseModel):
    """The group metadata attached to a group-update event."""

    group_id: str
    group_name: str
    revision: int
    type: Literal["UPDATE"]

    @staticmethod
    def from_base(group_info: generated.GroupInfo) -> GroupUpdateInfo:
        if group_info.group_id is None:
            error_msg = "group_id cannot be None"
            raise ValueError(error_msg)
        if group_info.group_name is None:
            error_msg = "group_name cannot be None"
            raise ValueError(error_msg)

        if group_info.type != "UPDATE":
            error_msg = f"Expected type 'UPDATE', got '{group_info.type}'"
            raise ValueError(error_msg)

        return GroupUpdateInfo(
            group_id=group_info.group_id,
            group_name=group_info.group_name,
            revision=group_info.revision,
            type="UPDATE",
        )


class GroupUpdate(BaseMessage):
    """Notification that a group's metadata (name, members, ...) was updated."""

    group_info: GroupUpdateInfo

    @classmethod
    def _internal_parse(
        cls,
        message_envelope: MessageEnvelope,
        data_message: DataMessage | SyncDataMessage,
    ) -> GroupUpdate:
        if data_message.group_info is None:
            error_msg = "MessageEnvelope does not contain group_info"
            raise ValueError(error_msg)

        group_info = GroupUpdateInfo.from_base(data_message.group_info)

        return cls(
            server_delivered_timestamp=message_envelope.server_delivered_timestamp,
            server_received_timestamp=message_envelope.server_received_timestamp,
            source=message_envelope.source,
            source_device=message_envelope.source_device,
            source_name=message_envelope.source_name,
            source_number=message_envelope.source_number,
            source_uuid=message_envelope.source_uuid,
            timestamp=message_envelope.timestamp,
            group_info=group_info,
        )

    @classmethod
    def from_message_envelope(cls, message_envelope: MessageEnvelope) -> GroupUpdate:
        if message_envelope.data_message is not None:
            return cls._internal_parse(message_envelope, message_envelope.data_message)
        if (
            message_envelope.sync_message is not None
            and message_envelope.sync_message.sent_message is not None
        ):
            return cls._internal_parse(
                message_envelope, message_envelope.sync_message.sent_message
            )

        error_msg = "MessageEnvelope does not contain group_info"
        raise ValueError(error_msg)

    @staticmethod
    def message_envelope_is_group_update(message_envelope: MessageEnvelope) -> bool:
        data_message: DataMessage | SyncDataMessage | None = (
            message_envelope.data_message
        )
        if data_message is None and message_envelope.sync_message is not None:
            # Group updates made from one of the bot's own linked devices
            data_message = message_envelope.sync_message.sent_message
        return (
            data_message is not None
            and data_message.group_info is not None
            and data_message.group_info.type == "UPDATE"
        )

    def is_group(self) -> bool:
        return True

    def is_private(self) -> bool:
        return False

    def source_or_group_id(self) -> str:
        return self.group_info.group_id
