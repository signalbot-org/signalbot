from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from signalbot.link_previews import LinkPreview
from signalbot.quote import Quote
from signalbot.reaction import Reaction

if TYPE_CHECKING:
    from signalbot.api import SignalAPI


class MessageType(Enum):
    """Enum representing the type of a Signal message.

    Attributes:
        SYNC_MESSAGE: Message received in a linked device
        DATA_MESSAGE: Message received in a primary device
        EDIT_MESSAGE: Message received is an edit of a previous message
        DELETE_MESSAGE: Message received is a remote delete of a previous message
        READ_MESSAGE: User read some messages
        GROUP_UPDATE_MESSAGE: An update has been made to a group
        REACTION_MESSAGE: Message received is a reaction to a previous message
        CONTACT_SYNC_MESSAGE: Message received is a contact sync
    """

    SYNC_MESSAGE = auto()  # Message received in a linked device
    DATA_MESSAGE = auto()  # Message received in a primary device
    EDIT_MESSAGE = auto()  # Message received is an edit of a previous message
    DELETE_MESSAGE = auto()  # Message received is a remote delete of a previous message
    READ_MESSAGE = auto()  # User read some messages
    GROUP_UPDATE_MESSAGE = auto()  # An update has been made to a group
    REACTION_MESSAGE = auto()  # Message received is a reaction to a previous message
    CONTACT_SYNC_MESSAGE = auto()  # Message received is a contact sync


@dataclass
class Message:
    """Class representing a Signal message.

    Attributes:
        source: The phone number or UUID of the sender of the message.
        source_number: The phone number of the sender of the message.
            This is `None` for signal contacts where the phone number was not exchanged.
        source_uuid: The UUID of the sender of the message.
        timestamp: The timestamp of when the message was sent.
        type: The type of the message.
        text: The text content of the message.
        base64_attachments: A list of attachments in the message, encoded as base64
            strings.
        attachments_local_filenames: A list of local filenames for the attachments in
            the message.
        view_once: A boolean indicating whether the message is a view-once message.
        link_previews: A list of `LinkPreview` objects representing the link previews in
            the message.
        group: The UUID of the group chat the message was sent in, or `None` if the
            message was sent in a user chat.
        reaction: A `Reaction` object if the message is a reaction, or `None`.
        mentions: A list of UUIDs of users mentioned in the message.
        quote: An object representing the quoted message if the message is a
            quote.
        read_messages: A list of dictionaries representing the messages that have been
            read if the message is a `MessageType.READ_MESSAGE`
        target_sent_timestamp: The timestamp of the original message that was edited, if
            the message is a `MessageType.EDIT_MESSAGE`.
        remote_delete_timestamp: The timestamp of the original message that was deleted,
            the message is a `MessageType.DELETE_MESSAGE`.
        updated_group_id: The UUID of the group that was updated, if the message is a
            `MessageType.GROUP_UPDATE_MESSAGE`.
        raw_message: The raw JSON string of the message as received from the Signal API.
    """

    source: str
    source_number: str | None
    source_uuid: str
    timestamp: int
    type: MessageType
    text: str
    base64_attachments: list[str] = field(default_factory=list)
    attachments_local_filenames: list[str] = field(default_factory=list)
    view_once: bool = False
    link_previews: list[LinkPreview] = field(default_factory=list)
    group: str | None = None
    reaction: Reaction | None = None
    mentions: list[str] = field(default_factory=list)
    quote: Quote | None = None
    read_messages: list[dict] | None = None
    target_sent_timestamp: int | None = None
    remote_delete_timestamp: int | None = None
    updated_group_id: str | None = None
    raw_message: str | None = None

    def recipient(self) -> str:
        """Get the recipient of the message, which is either the group ID for group
            chats or the source ID for user chats.

        Returns:
            The recipient ID of the message.
        """
        # Case 1: Group chat
        if self.group:
            return self.group  # internal ID

        # Case 2: User chat
        return self.source

    def is_private(self) -> bool:
        """Check if the message is a private (one-on-one) message.


        Returns:
            True if the message is a private (one-on-one) message, False otherwise.
        """
        return not bool(self.group)

    def is_group(self) -> bool:
        """Check if the message is a group message.

        Returns:
            True if the message is a group message, False otherwise.
        """
        return bool(self.group)

    @staticmethod
    def _extract_sync_message(envelope: dict) -> tuple[MessageType, dict, int]:
        target_sent_timestamp = None
        sync_message = envelope["syncMessage"]

        if sync_message == {}:
            raise UnknownMessageFormatError

        if "readMessages" in sync_message:
            message_type = MessageType.READ_MESSAGE
            data_message = {
                "message": "",
                "readMessages": sync_message["readMessages"],
            }
        elif "type" in sync_message:
            if sync_message["type"] == "CONTACTS_SYNC":
                message_type = MessageType.CONTACT_SYNC_MESSAGE
                data_message = {"message": ""}
                target_sent_timestamp = envelope.get("timestamp")
            else:
                raise UnknownMessageFormatError
        else:
            message_type = MessageType.SYNC_MESSAGE
            data_message = sync_message["sentMessage"]

        if "editMessage" in data_message:
            message_type = MessageType.EDIT_MESSAGE
            target_sent_timestamp = data_message["editMessage"]["targetSentTimestamp"]
            data_message = data_message["editMessage"]["dataMessage"]

        return (message_type, data_message, target_sent_timestamp)

    @classmethod
    def _extract_message_data(  # nosqa: C901, PLR0912
        cls, envelope: dict
    ) -> tuple[MessageType, dict, int | None, int | None, str | None]:
        """Extract message type, data_message, and timestamps from envelope."""
        target_sent_timestamp = None

        if "syncMessage" in envelope:
            message_type, data_message, target_sent_timestamp = (
                cls._extract_sync_message(envelope)
            )

        elif "dataMessage" in envelope:
            message_type = MessageType.DATA_MESSAGE
            data_message = envelope["dataMessage"]

        elif "editMessage" in envelope:
            message_type = MessageType.EDIT_MESSAGE
            data_message = envelope["editMessage"]["dataMessage"]
            target_sent_timestamp = envelope["editMessage"]["targetSentTimestamp"]

        else:
            raise UnknownMessageFormatError

        remote_delete_timestamp = None
        if "remoteDelete" in data_message:
            message_type = MessageType.DELETE_MESSAGE
            remote_delete_timestamp = data_message["remoteDelete"]["timestamp"]

        if "reaction" in data_message:
            message_type = MessageType.REACTION_MESSAGE

        updated_group_id = None
        if (
            "groupInfo" in data_message
            and data_message["groupInfo"]["type"] == "UPDATE"
        ):
            message_type = MessageType.GROUP_UPDATE_MESSAGE
            updated_group_id = data_message["groupInfo"]["groupId"]

        return (
            message_type,
            data_message,
            target_sent_timestamp,
            remote_delete_timestamp,
            updated_group_id,
        )

    @classmethod
    async def parse(cls, signal: SignalAPI, raw_message_str: str) -> Message:
        """Parse a raw JSON message string from the Signal API into a Message object.

        Args:
            signal: An instance of the `SignalAPI` class, used to fetch attachments and
                link previews if necessary.
            raw_message_str: The raw JSON string of the message as received from the
                Signal API.

        Returns:
            A `Message` object representing the parsed message.

        Raises:
            UnknownMessageFormatError: If the message format is unrecognized or if
                required fields are missing.
        """
        try:
            raw_message = json.loads(raw_message_str)
        except Exception as exc:
            raise UnknownMessageFormatError from exc

        envelope = raw_message["envelope"]
        # General attributes
        try:
            source = envelope["source"]
            source_uuid = envelope["sourceUuid"]
            timestamp = envelope["timestamp"]
        except Exception as exc:
            raise UnknownMessageFormatError from exc

        source_number = envelope.get("sourceNumber")

        (
            message_type,
            data_message,
            target_sent_timestamp,
            remote_delete_timestamp,
            updated_group_id,
        ) = cls._extract_message_data(envelope)

        text = cls._parse_data_message(data_message)
        group = cls._parse_group_information(data_message)
        reaction = cls._parse_reaction(data_message)
        mentions = cls._parse_mentions(data_message)
        quote = cls._parse_quote(data_message)
        read_messages = data_message.get("readMessages")

        base64_attachments, attachments_local_filenames, link_previews = [], [], []
        view_once = False
        if signal.download_attachments:
            base64_attachments = await cls._parse_attachments(signal, data_message)
            attachments_local_filenames = cls._parse_attachments_local_filenames(
                data_message,
            )
            link_previews = await cls._parse_previews(signal, data_message)
            view_once = data_message.get("viewOnce", False)

        return cls(
            source,
            source_number,
            source_uuid,
            timestamp,
            message_type,
            text,
            base64_attachments=base64_attachments,
            attachments_local_filenames=attachments_local_filenames,
            view_once=view_once,
            link_previews=link_previews,
            group=group,
            reaction=reaction,
            mentions=mentions,
            quote=quote,
            read_messages=read_messages,
            target_sent_timestamp=target_sent_timestamp,
            remote_delete_timestamp=remote_delete_timestamp,
            updated_group_id=updated_group_id,
            raw_message=raw_message_str,
        )

    @classmethod
    async def _parse_attachments(
        cls, signal: SignalAPI, data_message: dict
    ) -> list[str]:
        if "attachments" not in data_message:
            return []

        return [
            await signal.get_attachment(attachment["id"])
            for attachment in data_message["attachments"]
        ]

    @classmethod
    def _parse_attachments_local_filenames(cls, data_message: dict) -> list[str]:
        if "attachments" not in data_message:
            return []

        # The ["id"] is the local filename and the ["filename"] is the remote filename
        return [attachment["id"] for attachment in data_message["attachments"]]

    @classmethod
    def _parse_data_message(cls, data_message: dict) -> str:
        try:
            return data_message["message"]
        except KeyError as exc:
            raise UnknownMessageFormatError from exc

    @classmethod
    def _parse_group_information(cls, message: dict) -> str | None:
        try:
            return message["groupInfo"]["groupId"]
        except KeyError:
            return None

    @classmethod
    def _parse_mentions(cls, data_message: dict) -> list:
        try:
            return data_message["mentions"]
        except KeyError:
            return []

    @classmethod
    def _parse_reaction(cls, message: dict) -> Reaction | None:
        try:
            return Reaction.model_validate(message["reaction"])
        except (KeyError, ValueError):
            return None

    @classmethod
    def _parse_quote(cls, message: dict) -> Quote | None:
        try:
            return Quote.model_validate(message["quote"])
        except KeyError:
            return None

    def __str__(self) -> str:
        if self.text is None:
            return ""
        return self.text

    @classmethod
    async def _parse_previews(cls, signal: SignalAPI, data_message: dict) -> list:
        parsed_previews = []
        try:
            for preview in data_message["previews"]:
                img = preview["image"]
                img_id = None
                if isinstance(img, dict):
                    img_id = img["id"]

                base64_thumbnail = None
                if img_id:
                    base64_thumbnail = await signal.get_attachment(img_id)

                parsed_previews.append(
                    LinkPreview(
                        base64_thumbnail=base64_thumbnail,
                        title=preview["title"],
                        description=preview["description"],
                        url=preview["url"],
                        id=img_id,
                    ),
                )
        except KeyError:
            return []

        return parsed_previews


class UnknownMessageFormatError(Exception):
    """Exception raised when a message with an unknown format is encountered."""
