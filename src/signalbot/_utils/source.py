from typing import NamedTuple

from signalbot._generated import MessageEnvelope


class Source(NamedTuple):
    source: str | None
    number: str | None
    uuid: str | None


def parse_source_from_envelope(
    message_envelope: MessageEnvelope,
) -> Source:
    if (
        message_envelope.sync_message is not None
        and message_envelope.sync_message.sent_message is not None
        and message_envelope.sync_message.sent_message.group_info is None
    ):
        destination = message_envelope.sync_message.sent_message.destination
        destination_number = (
            message_envelope.sync_message.sent_message.destination_number
        )
        destination_uuid = message_envelope.sync_message.sent_message.destination_uuid
        return Source(destination, destination_number, destination_uuid)

    source = message_envelope.source
    source_number = message_envelope.source_number
    source_uuid = message_envelope.source_uuid
    return Source(source, source_number, source_uuid)
