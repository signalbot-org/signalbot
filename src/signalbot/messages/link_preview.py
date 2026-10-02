from __future__ import annotations

from anyio import Path
from pydantic import BaseModel, Field

from signalbot._generated import LinkPreviewType
from signalbot._generated import Preview as GeneratedPreview
from signalbot._utils.attachment_base64 import attachment_to_base64
from signalbot._utils.pydantic_anyio_path import PydanticPath
from signalbot.attachments import Attachment


class Preview(GeneratedPreview):
    """The preview metadata Signal already generated for a link in a received
    message.
    """

    base64_thumbnail: str | None = None
    # Narrowed to a wrapped type; rationale in
    # docs/contributing/04_new_signal_cli_rest_api.md.
    image: Attachment | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class LinkPreview(BaseModel):
    """A link preview to attach to an outgoing message."""

    description: str = Field(description="The description of the link preview.")
    title: str = Field(description="The title of the link preview.")
    url: str = Field(description="The URL of the link preview.")
    thumbnail: PydanticPath | str = Field(
        description="The thumbnail of the link preview. This can be a Path or a "
        "base64 encoded string of the image content."
    )

    async def to_generated(self) -> LinkPreviewType:
        base64_thumbnail = (
            await attachment_to_base64(self.thumbnail)
            if isinstance(self.thumbnail, Path)
            else self.thumbnail
        )
        return LinkPreviewType(
            base64_thumbnail=base64_thumbnail,
            description=self.description,
            title=self.title,
            url=self.url,
        )
