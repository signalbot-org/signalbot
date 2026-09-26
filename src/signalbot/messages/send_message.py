from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self, cast

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    model_validator,
)

from signalbot._generated import SendMessageV2, TextMode
from signalbot._utils.attachment_base64 import attachment_to_base64
from signalbot._utils.pydantic_anyio_path import PydanticPath
from signalbot.messages.link_preview import LinkPreview
from signalbot.messages.message_mention import MessageMention

if TYPE_CHECKING:
    from signalbot._generated import LinkPreviewType
    from signalbot._generated import MessageMention as GeneratedMessageMention


def _as_generated_mentions(
    mentions: list[MessageMention] | None,
) -> list[GeneratedMessageMention] | None:
    # `MessageMention` adds no fields over the generated type it wraps, so this
    # is safe; list is invariant, so the type checker can't see that on its own.
    return cast("list[GeneratedMessageMention] | None", mentions)


async def _resolve_base64_attachments(
    send_message: BaseSendMessage,
) -> list[str] | None:
    base64_attachments = list(send_message.base64_attachments or [])
    if send_message.attachments:
        base64_attachments += await asyncio.gather(
            *(attachment_to_base64(path) for path in send_message.attachments)
        )
    return base64_attachments or None


async def _resolve_link_preview(
    link_preview: LinkPreview | None,
) -> LinkPreviewType | None:
    if link_preview is None:
        return None
    return await link_preview.to_generated()


def _check_link_preview_url_in_text(send_message: BaseSendMessage) -> None:
    if send_message.link_preview is not None and (
        send_message.text is None
        or send_message.link_preview.url not in send_message.text
    ):
        error_msg = (
            "If the link_preview is included, the URL must be present in the text."
        )
        raise ValueError(error_msg)


class BaseSendMessage(BaseModel):
    """Fields shared by every outgoing message, regardless of recipient shape."""

    base64_attachments: list[str] | None = None
    attachments: list[PydanticPath] | None = None
    edit_timestamp: int | None = None
    link_preview: LinkPreview | None = None
    mentions: list[MessageMention] | None = None
    text: str | None = Field(
        default=None,
        serialization_alias="message",
        validation_alias=AliasChoices("message", "text"),
    )
    notify_self: bool | None = None
    quote_author: str | None = None
    quote_mentions: list[MessageMention] | None = None
    quote_text: str | None = None
    quote_timestamp: int | None = None
    sticker: str | None = None
    text_mode: TextMode | None = None
    view_once: bool | None = None

    @model_validator(mode="after")
    def check_link_preview_url_in_text(self) -> Self:
        _check_link_preview_url_in_text(self)
        return self


class SendMessage(BaseSendMessage):
    """A message to send to one or more recipients (contacts or groups)."""

    async def to_generated(self, number: str, recipients: list[str]) -> SendMessageV2:
        base64_attachments = await _resolve_base64_attachments(self)
        link_preview = await _resolve_link_preview(self.link_preview)

        return SendMessageV2(
            base64_attachments=base64_attachments,
            edit_timestamp=self.edit_timestamp,
            link_preview=link_preview,
            mentions=_as_generated_mentions(self.mentions),
            message=self.text or "",
            notify_self=self.notify_self,
            number=number,
            quote_author=self.quote_author,
            quote_mentions=_as_generated_mentions(self.quote_mentions),
            quote_message=self.quote_text,
            quote_timestamp=self.quote_timestamp,
            recipients=recipients,
            sticker=self.sticker,
            text_mode=self.text_mode,
            view_once=self.view_once,
        )


class SentMessage(BaseSendMessage):
    """A record of a message after it was successfully sent to one recipient."""

    recipient: str
    timestamp: int

    @classmethod
    def from_send_message(
        cls, send_message: SendMessage, recipient: str, timestamp: int
    ) -> SentMessage:
        return cls.model_construct(
            **send_message.model_dump(), recipient=recipient, timestamp=timestamp
        )

    @classmethod
    def from_send_message_multiple(
        cls, send_message: SendMessage, recipients: list[str], timestamps: list[int]
    ) -> list[SentMessage]:
        return [
            cls.from_send_message(send_message, recipient, timestamp)
            for recipient, timestamp in zip(recipients, timestamps, strict=True)
        ]
