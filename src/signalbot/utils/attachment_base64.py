import base64

from signalbot.utils.pydantic_anyio_path import PydanticPath


async def attachment_to_base64(attachment: PydanticPath) -> str:
    # Add these extra metadata for better handling of the attachments.
    # This follows the RFC 2397.
    # data:<MIME-TYPE>;filename=<FILENAME>;base64,<BASE64 ENCODED DATA>
    async with await attachment.open("rb") as f:
        return str(base64.b64encode(await f.read()), encoding="utf-8")
