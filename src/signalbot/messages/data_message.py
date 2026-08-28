from __future__ import annotations

import base64
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from signalbot._generated import TextMode
from signalbot._utils.generated_conversion import from_generated, from_generated_list
from signalbot._utils.source import parse_source_from_envelope
from signalbot.attachments import Attachment
from signalbot.events import BaseMessageWithGroup, GroupInfo
from signalbot.messages.data_message_content import Mention, Quote, Sticker, TextStyle
from signalbot.messages.link_preview import LinkPreview, Preview
from signalbot.messages.message_mention import MessageMention
from signalbot.messages.send_message import SendMessage

if TYPE_CHECKING:
    from signalbot import _generated as generated
    from signalbot._client import SignalAPI
    from signalbot._generated import (
        MessageEnvelope,
        SyncDataMessage,
    )


class DataMessage(BaseMessageWithGroup):
    attachments: list[Attachment] | None = None
    expires_in_seconds: int | None = None
    mentions: list[Mention] | None = None
    text: str | None = None
    previews: list[Preview] | None = None
    base64_previews: list[str] | None = None
    quote: Quote | None = None
    sticker: Sticker | None = None
    text_styles: list[TextStyle] | None = None
    timestamp: int
    view_once: bool | None = None

    @classmethod
    async def _download_attachments(
        cls, signal: SignalAPI, attachments: list[Attachment]
    ) -> list[str | None]:
        return [
            await signal.attachments.download(attachment)
            if attachment.local_filename is not None
            else None
            for attachment in attachments
        ]

    @classmethod
    async def _download_thumbnails(
        cls, signal: SignalAPI, link_previews: list[Preview]
    ) -> list[str | None]:
        return [
            await signal.attachments.download(link_preview.image)
            if link_preview.image is not None
            and link_preview.image.local_filename is not None
            else None
            for link_preview in link_previews
        ]

    @classmethod
    async def _internal_parse(
        cls,
        message_envelope: MessageEnvelope,
        data_message: generated.DataMessage | SyncDataMessage,
        signal: SignalAPI,
    ) -> DataMessage:
        attachments = from_generated_list(Attachment, data_message.attachments)
        link_previews = from_generated_list(Preview, data_message.previews)

        timestamp = (
            data_message.timestamp
            if data_message.timestamp is not None
            else message_envelope.timestamp
        )

        mentions = from_generated_list(Mention, data_message.mentions)
        quote = from_generated(Quote, data_message.quote)
        sticker = from_generated(Sticker, data_message.sticker)
        text_styles = from_generated_list(TextStyle, data_message.text_styles)
        group_info = from_generated(GroupInfo, data_message.group_info)
        source = parse_source_from_envelope(message_envelope)

        received_data_message = DataMessage(
            server_delivered_timestamp=message_envelope.server_delivered_timestamp,
            server_received_timestamp=message_envelope.server_received_timestamp,
            source=source.source,
            source_device=message_envelope.source_device,
            source_name=message_envelope.source_name,
            source_number=source.number,
            source_uuid=source.uuid,
            group_info=group_info,
            timestamp=timestamp,
            attachments=attachments,
            expires_in_seconds=data_message.expires_in_seconds,
            mentions=mentions,
            text=data_message.message,
            previews=link_previews,
            quote=quote,
            sticker=sticker,
            text_styles=text_styles,
            view_once=data_message.view_once,
        )

        if (
            received_data_message.attachments is not None
            and signal.download_attachments
        ):
            base64_contents = await cls._download_attachments(
                signal, received_data_message.attachments
            )
            for i, base64_content in enumerate(base64_contents):
                received_data_message.attachments[i].base64_content = base64_content

        if received_data_message.previews is not None and signal.download_attachments:
            base64_contents = await cls._download_thumbnails(
                signal, received_data_message.previews
            )
            for i, base64_content in enumerate(base64_contents):
                received_data_message.previews[i].base64_thumbnail = base64_content

        return received_data_message

    @classmethod
    async def from_message_envelope(
        cls, message_envelope: MessageEnvelope, signal: SignalAPI
    ) -> DataMessage:
        if message_envelope.data_message is not None:
            return await cls._internal_parse(
                message_envelope, message_envelope.data_message, signal
            )

        if (
            message_envelope.sync_message is not None
            and message_envelope.sync_message.sent_message is not None
        ):
            return await cls._internal_parse(
                message_envelope, message_envelope.sync_message.sent_message, signal
            )

        error_msg = "MessageEnvelope does not contain a DataMessage"
        raise ValueError(error_msg)

    def _to_send_mentions(
        self, mentions: list[Mention] | None
    ) -> list[MessageMention] | None:
        if mentions is None:
            return None

        return [
            MessageMention(
                author=mention.uuid,
                length=mention.length,
                start=mention.start,
            )
            for mention in mentions
            if mention.uuid is not None
        ]

    def to_send_message(self) -> SendMessage:
        """Convert the received message to a SendMessage that can be sent using the
            API.

        Returns:
            A SendMessage object that can be sent using the API.
        """
        copy = deepcopy(self)
        base_64_attachments = None
        if copy.attachments is not None:
            base_64_attachments = []
            for attachment in copy.attachments:
                if attachment.base64_content is None:
                    if attachment.local_filename is None:
                        error_msg = "Attachment does not contain a "
                        error_msg += "local_filename or base64 content"
                        raise ValueError(error_msg)

                    with Path(attachment.local_filename).open("rb") as f:
                        base64_content = str(
                            base64.b64encode(f.read()), encoding="utf-8"
                        )
                else:
                    base64_content = attachment.base64_content
                base_64_attachments.append(base64_content)

        link_preview = None
        if copy.previews is not None and len(copy.previews) > 0:
            preview = copy.previews[0]
            if (
                preview.base64_thumbnail is not None
                and preview.title is not None
                and preview.url is not None
            ):
                link_preview = LinkPreview(
                    description=preview.description or "",
                    title=preview.title,
                    url=preview.url,
                    thumbnail=preview.base64_thumbnail,
                )

        text_style = None
        if copy.text_styles is not None and len(copy.text_styles) > 0:
            text_style = TextMode(copy.text_styles[0].style)

        return SendMessage(
            base64_attachments=base_64_attachments,
            edit_timestamp=None,
            link_preview=link_preview,
            mentions=self._to_send_mentions(copy.mentions),
            text=copy.text or "",
            notify_self=None,
            quote_author=copy.quote.author if copy.quote is not None else None,
            quote_mentions=self._to_send_mentions(copy.quote.mentions)
            if copy.quote is not None
            else None,
            quote_text=copy.quote.text if copy.quote is not None else None,
            quote_timestamp=copy.quote.id if copy.quote is not None else None,
            # sticker=copy.sticker, # Not clear how to send stickers yet
            text_mode=text_style,
            view_once=copy.view_once,
        )
