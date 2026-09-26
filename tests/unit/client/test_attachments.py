import base64
from collections.abc import Callable

import aiohttp
import pytest
from pytest_mock import MockerFixture, MockType

from signalbot._client import SignalAPI
from signalbot.attachments import Attachment
from tests.unit.client.conftest import HTTP_OK


async def test_download_attachment(signal_api: SignalAPI, mocker: MockerFixture):
    mock = mocker.patch("aiohttp.ClientSession.get", new_callable=mocker.AsyncMock)
    content_mock = mocker.AsyncMock(return_value=b"file content")
    mock.return_value = mocker.AsyncMock(
        spec=aiohttp.ClientResponse,
        status=HTTP_OK,
        content=mocker.Mock(read=content_mock),
    )

    attachment = Attachment(local_filename="my-file.png", isVoiceNote=False)
    result = await signal_api.attachments.download(attachment)

    assert result == base64.b64encode(b"file content").decode("utf-8")


async def test_delete_attachment(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    mock = mock_json_response("delete", {})

    attachment = Attachment(local_filename="my-file.png", isVoiceNote=False)
    await signal_api.attachments.delete(attachment)

    assert mock.call_count == 1


async def test_delete_attachment_without_local_filename_raises(signal_api: SignalAPI):
    attachment = Attachment(local_filename=None, isVoiceNote=False)

    with pytest.raises(ValueError, match="no local filename"):
        await signal_api.attachments.delete(attachment)
