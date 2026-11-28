from anyio import Path

from signalbot.attachments import Attachment


async def test_local_path_points_into_signal_api_attachment_dir():
    attachment = Attachment(local_filename="abc.png", isVoiceNote=False)

    path = await attachment.local_path()

    assert path == await Path.home() / ".local/share/signal-api/attachments/abc.png"


async def test_local_path_is_none_when_not_downloaded():
    assert await Attachment(isVoiceNote=False).local_path() is None
