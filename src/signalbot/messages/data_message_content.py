from __future__ import annotations

from pydantic import Field

from signalbot._generated import Mention as GeneratedMention
from signalbot._generated import Quote as GeneratedQuote
from signalbot._generated import QuotedAttachment as GeneratedQuotedAttachment
from signalbot._generated import Sticker as GeneratedSticker
from signalbot._generated import TextStyle as GeneratedTextStyle
from signalbot.attachments import Attachment


class Mention(GeneratedMention):
    """A mention in a received message."""


class TextStyle(GeneratedTextStyle):
    """A text style range in a received message."""


class Sticker(GeneratedSticker):
    """A sticker attached to a received message."""


class QuotedAttachment(GeneratedQuotedAttachment):
    """An attachment on the message a received message quotes."""

    # Narrowed to a wrapped type; rationale in
    # docs/contributing/04_new_signal_cli_rest_api.md.
    thumbnail: Attachment | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class Quote(GeneratedQuote):
    """The quoted message a received message replies to."""

    # Fields below are narrowed to wrapped types; rationale in
    # docs/contributing/04_new_signal_cli_rest_api.md.
    attachments: list[QuotedAttachment] | None = None  # pyright: ignore[reportIncompatibleVariableOverride]
    mentions: list[Mention] | None = None  # pyright: ignore[reportIncompatibleVariableOverride]
    text_styles: list[TextStyle] | None = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default=None, alias="textStyles"
    )
