from pathlib import Path as PathlibPath

from anyio import Path as AnyIOPath

from signalbot.messages import LinkPreview, SendMessage


async def test_send_message_serializes_as_sendv2_with_single_recipient(
    tmp_path: PathlibPath,
):
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("payload")

    message = SendMessage(
        attachments=[AnyIOPath(attachment)],
    )

    result = await message.to_generated("+49123456789", ["group-1"])

    assert result.number == "+49123456789"
    assert result.message == ""
    assert result.recipients == ["group-1"]
    assert result.base64_attachments == ["cGF5bG9hZA=="]


async def test_send_message_serializes_as_sendv2_with_multiple_recipients(
    tmp_path: PathlibPath,
):
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("payload")

    message = SendMessage(
        attachments=[AnyIOPath(attachment)],
        text="Hello World!",
    )

    result = await message.to_generated("+49123456789", ["group-1", "group-2"])

    assert result.number == "+49123456789"
    assert result.message == "Hello World!"
    assert result.recipients == ["group-1", "group-2"]
    assert result.base64_attachments == ["cGF5bG9hZA=="]


async def test_send_message_link_preview_with_base64_thumbnail():
    # A long base64 string must not be mistaken for a path, opening it fails
    thumbnail = "cGF5bG9hZA==" * 100
    message = SendMessage(
        text="https://example.com",
        link_preview=LinkPreview(
            description="",
            title="Example",
            url="https://example.com",
            thumbnail=thumbnail,
        ),
    )

    result = await message.to_generated("+49123456789", ["group-1"])

    assert result.link_preview is not None
    assert result.link_preview.base64_thumbnail == thumbnail


async def test_send_message_link_preview_with_thumbnail_path(tmp_path: PathlibPath):
    thumbnail = tmp_path / "thumbnail.png"
    thumbnail.write_text("payload")
    message = SendMessage(
        text="https://example.com",
        link_preview=LinkPreview(
            description="",
            title="Example",
            url="https://example.com",
            thumbnail=AnyIOPath(thumbnail),
        ),
    )

    result = await message.to_generated("+49123456789", ["group-1"])

    assert result.link_preview is not None
    assert result.link_preview.base64_thumbnail == "cGF5bG9hZA=="
