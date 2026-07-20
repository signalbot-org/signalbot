from __future__ import annotations

from typing import Any

from anyio import Path
from pydantic import (
    BaseModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from signalbot.utils.attachment_base64 import attachment_to_base64
from signalbot.utils.pydantic_anyio_path import PydanticPath


class LinkPreview(BaseModel):
    """
    LinkPreview

    Attributes:
        description: The description of the link preview.
        title: The title of the link preview.
        url: The URL of the link preview.
        thumbnail : The thumbnail of the link preview. This can be a Path or a base64
            encoded string of the image content.
    """

    description: str
    title: str
    url: str
    thumbnail: PydanticPath | str

    @model_serializer(mode="wrap")
    def serialize_model(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = handler(self)
        if info.context and info.context.get("mode") == "sendv2":
            base64_thumbnail = payload.get("thumbnail")
            if isinstance(self.thumbnail, Path):
                base64_thumbnail = attachment_to_base64(self.thumbnail)
            payload["base64_thumbnail"] = base64_thumbnail
            payload.pop("thumbnail", None)

        return payload
