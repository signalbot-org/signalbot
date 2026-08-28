import base64
import json

import aiohttp
import pytest
from pytest_mock import MockerFixture

from signalbot._client import SignalAPI
from signalbot.groups import GroupUpdate
from signalbot.messages import (
    DataMessage,
    EditMessage,
    RemoteDelete,
    TypingMessage,
    UnknownMessageFormatError,
    parse,
)
from signalbot.reactions import Reaction

ACCOUNT = "+49987654321"
SOURCE = "+490123456789"
DESTINATION = "+49000111222"
TIMESTAMP = 1632576001632
TEXT = "Uhrzeit"
GROUP_ID = "<groupid>"


def envelope(
    *,
    account: str = ACCOUNT,
    source: str = SOURCE,
    timestamp: int = TIMESTAMP,
    server_received_timestamp: int | None = None,
    server_delivered_timestamp: int | None = None,
    **body: object,
) -> str:
    """Build a raw signal-cli-rest-api envelope JSON string, with sensible
    defaults for the top-level fields shared by every message type. `body`
    supplies the type-specific key (e.g. `dataMessage=...`, `syncMessage=...`).
    """
    return json.dumps(
        {
            "account": account,
            "envelope": {
                "source": source,
                "sourceNumber": source,
                "sourceUuid": "<uuid>",
                "sourceName": "<name>",
                "sourceDevice": 1,
                "timestamp": timestamp,
                "serverReceivedTimestamp": server_received_timestamp
                if server_received_timestamp is not None
                else timestamp,
                "serverDeliveredTimestamp": server_delivered_timestamp
                if server_delivered_timestamp is not None
                else timestamp,
                **body,
            },
        }
    )


RAW_SYNC_MESSAGE = envelope(
    syncMessage={
        "sentMessage": {
            "timestamp": TIMESTAMP,
            "message": TEXT,
            "expiresInSeconds": 0,
            "viewOnce": False,
            "mentions": [],
            "attachments": [],
            "contacts": [],
            "groupInfo": {"groupId": GROUP_ID, "type": "DELIVER", "revision": 1},
            "destination": None,
            "destinationNumber": None,
            "destinationUuid": None,
        }
    }
)

RAW_SYNC_MESSAGE_PRIVATE_CONVERSATION = envelope(
    syncMessage={
        "sentMessage": {
            "destination": DESTINATION,
            "destinationNumber": DESTINATION,
            "destinationUuid": "<uuid>",
            "timestamp": TIMESTAMP,
            "message": TEXT,
            "expiresInSeconds": 0,
            "isExpirationUpdate": False,
            "viewOnce": False,
        }
    }
)

RAW_DATA_MESSAGE = envelope(
    dataMessage={
        "timestamp": TIMESTAMP,
        "message": TEXT,
        "expiresInSeconds": 0,
        "viewOnce": False,
        "mentions": [],
        "attachments": [],
        "contacts": [],
        "groupInfo": {"groupId": GROUP_ID, "type": "DELIVER", "revision": 1},
    }
)

RAW_REACTION_MESSAGE = envelope(
    source="<source>",
    syncMessage={
        "sentMessage": {
            "timestamp": TIMESTAMP,
            "message": None,
            "expiresInSeconds": 0,
            "viewOnce": False,
            "reaction": {
                "emoji": "👍",
                "targetAuthor": "<target>",
                "targetAuthorNumber": "<target>",
                "targetAuthorUuid": "<uuid>",
                "targetSentTimestamp": TIMESTAMP,
                "isRemove": False,
            },
            "mentions": [],
            "attachments": [],
            "contacts": [],
            "groupInfo": {"groupId": GROUP_ID, "type": "DELIVER", "revision": 1},
            "destination": None,
            "destinationNumber": None,
            "destinationUuid": None,
        }
    },
)

RAW_REACTION_SYNC_MESSAGE_MESSAGE_PRIVATE_CONVERSATION = envelope(
    syncMessage={
        "sentMessage": {
            "destination": DESTINATION,
            "destinationNumber": DESTINATION,
            "destinationUuid": "<uuid>",
            "timestamp": TIMESTAMP,
            "message": None,
            "expiresInSeconds": 0,
            "isExpirationUpdate": False,
            "viewOnce": False,
            "reaction": {
                "emoji": "👍",
                "targetAuthor": "<target>",
                "targetAuthorNumber": "<target>",
                "targetAuthorUuid": "<uuid>",
                "targetSentTimestamp": TIMESTAMP,
                "isRemove": False,
            },
        }
    },
)

RAW_EDIT_MESSAGE = envelope(
    timestamp=1632576001700,
    editMessage={
        "targetSentTimestamp": TIMESTAMP,
        "dataMessage": {
            "timestamp": 1632576001700,
            "message": "Uhrzeit!",
            "expiresInSeconds": 0,
            "viewOnce": False,
        },
    },
)

RAW_EDIT_MESSAGE_SYNC_MESSAGE_PRIVATE_CONVERSATION = envelope(
    timestamp=1632576001700,
    syncMessage={
        "sentMessage": {
            "destination": DESTINATION,
            "destinationNumber": DESTINATION,
            "destinationUuid": "<uuid>",
            "editMessage": {
                "targetSentTimestamp": TIMESTAMP,
                "dataMessage": {
                    "timestamp": 1632576001700,
                    "message": "Uhrzeit!",
                    "expiresInSeconds": 0,
                    "isExpirationUpdate": False,
                    "viewOnce": False,
                },
            },
        }
    },
)

RAW_TYPING_MESSAGE = envelope(
    typingMessage={"action": "STARTED", "timestamp": TIMESTAMP, "groupId": None}
)

RAW_USER_CHAT_MESSAGE = envelope(
    dataMessage={
        "timestamp": TIMESTAMP,
        "message": TEXT,
        "expiresInSeconds": 0,
        "viewOnce": False,
    }
)

LOCAL_FILENAME = "1qeCjjWOOo9Gxv8pfdCw.png"

RAW_ATTACHMENT_MESSAGE = envelope(
    dataMessage={
        "timestamp": TIMESTAMP,
        "message": TEXT,
        "expiresInSeconds": 0,
        "viewOnce": False,
        "attachments": [
            {
                "contentType": "image/png",
                "filename": "image.png",
                "id": LOCAL_FILENAME,
                "size": 12005,
            }
        ],
    }
)

RAW_PREVIEW_NO_IMAGE_MESSAGE = envelope(
    dataMessage={
        "timestamp": TIMESTAMP,
        "message": "https://example.com is nice",
        "expiresInSeconds": 0,
        "viewOnce": False,
        "previews": [
            {
                "url": "https://example.com",
                "title": "Example.com - Super example",
                "description": "",
                "image": None,
            }
        ],
    }
)

REMOTE_DELETE_TIMESTAMP = 1632576001600

RAW_REMOTE_DELETE_DATA_MESSAGE = envelope(
    dataMessage={
        "timestamp": TIMESTAMP,
        "message": None,
        "expiresInSeconds": 0,
        "viewOnce": False,
        "remoteDelete": {"timestamp": REMOTE_DELETE_TIMESTAMP},
        "groupInfo": {"groupId": GROUP_ID, "type": "DELIVER", "revision": 1},
    }
)

RAW_REMOTE_DELETE_SYNC_MESSAGE = envelope(
    syncMessage={
        "sentMessage": {
            "timestamp": TIMESTAMP,
            "message": None,
            "expiresInSeconds": 0,
            "viewOnce": False,
            "remoteDelete": {"timestamp": REMOTE_DELETE_TIMESTAMP},
            "mentions": [],
            "attachments": [],
            "contacts": [],
            "groupInfo": {"groupId": GROUP_ID, "type": "DELIVER", "revision": 1},
            "destination": None,
            "destinationNumber": None,
            "destinationUuid": None,
        }
    }
)

RAW_REMOTE_DELETE_SYNC_MESSAGE_PRIVATE_CONVERSATION = envelope(
    syncMessage={
        "sentMessage": {
            "destination": DESTINATION,
            "destinationNumber": DESTINATION,
            "destinationUuid": "<uuid>",
            "timestamp": TIMESTAMP,
            "message": None,
            "expiresInSeconds": 0,
            "isExpirationUpdate": False,
            "viewOnce": False,
            "remoteDelete": {"timestamp": REMOTE_DELETE_TIMESTAMP},
        }
    }
)

RAW_GROUP_UPDATE_MESSAGE = envelope(
    timestamp=1768100104294,
    server_received_timestamp=1768100103544,
    server_delivered_timestamp=1768100103588,
    dataMessage={
        "timestamp": 1768100104294,
        "message": None,
        "expiresInSeconds": 86400,
        "isExpirationUpdate": False,
        "viewOnce": False,
        "groupInfo": {
            "groupId": GROUP_ID,
            "groupName": "<name>",
            "revision": 100,
            "type": "UPDATE",
        },
    },
)

RAW_UNKNOWN_MESSAGE = envelope()


# Own Message


async def test_parse_source_own_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_SYNC_MESSAGE)
    assert message.source == SOURCE


async def test_parse_timestamp_own_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_SYNC_MESSAGE)
    assert message.timestamp == TIMESTAMP


async def test_parse_type_own_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_SYNC_MESSAGE)
    assert isinstance(message, DataMessage)


async def test_parse_text_own_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_SYNC_MESSAGE)
    assert isinstance(message, DataMessage)
    assert message.text == TEXT


async def test_parse_group_own_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_SYNC_MESSAGE)
    assert isinstance(message, DataMessage)
    assert message.group_info is not None
    assert message.group_info.group_id == GROUP_ID


async def test_parse_private_conversation_own_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_SYNC_MESSAGE_PRIVATE_CONVERSATION)
    assert isinstance(message, DataMessage)
    assert message.text == TEXT
    assert message.source == DESTINATION
    assert message.source_number == DESTINATION


# Foreign Messages


async def test_parse_source_foreign_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_DATA_MESSAGE)
    assert message.timestamp == TIMESTAMP


async def test_parse_timestamp_foreign_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_DATA_MESSAGE)
    assert message.source_number == SOURCE


async def test_parse_type_foreign_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_DATA_MESSAGE)
    assert isinstance(message, DataMessage)


async def test_parse_text_foreign_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_DATA_MESSAGE)
    assert isinstance(message, DataMessage)
    assert message.text == TEXT


async def test_parse_group_foreign_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_DATA_MESSAGE)
    assert isinstance(message, DataMessage)
    assert message.group_info is not None
    assert message.group_info.group_id == GROUP_ID


async def test_read_reaction(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_REACTION_MESSAGE)
    assert isinstance(message, Reaction)
    assert message.emoji == "👍"
    assert message.timestamp == TIMESTAMP
    assert message.is_remove is False


async def test_read_reaction_private_conversation(signal_api: SignalAPI):
    message = await parse(
        signal_api, RAW_REACTION_SYNC_MESSAGE_MESSAGE_PRIVATE_CONVERSATION
    )
    assert isinstance(message, Reaction)
    assert message.emoji == "👍"
    assert message.timestamp == TIMESTAMP
    assert message.is_remove is False
    assert message.source == DESTINATION
    assert message.source_number == DESTINATION


async def test_remote_delete_data_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_REMOTE_DELETE_DATA_MESSAGE)
    assert isinstance(message, RemoteDelete)
    assert message.timestamp == REMOTE_DELETE_TIMESTAMP
    assert message.group_info is not None
    assert message.group_info.group_id == GROUP_ID


async def test_remote_delete_sync_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_REMOTE_DELETE_SYNC_MESSAGE)
    assert isinstance(message, RemoteDelete)
    assert message.timestamp == REMOTE_DELETE_TIMESTAMP
    assert message.group_info is not None
    assert message.group_info.group_id == GROUP_ID


async def test_remote_delete_sync_message_private_conversation(signal_api: SignalAPI):
    message = await parse(
        signal_api, RAW_REMOTE_DELETE_SYNC_MESSAGE_PRIVATE_CONVERSATION
    )
    assert isinstance(message, RemoteDelete)
    assert message.timestamp == REMOTE_DELETE_TIMESTAMP
    assert message.source == DESTINATION
    assert message.source_number == DESTINATION


async def test_edit_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_EDIT_MESSAGE)
    assert isinstance(message, EditMessage)
    assert message.target_sent_timestamp == TIMESTAMP
    assert message.text == "Uhrzeit!"


async def test_edit_message_private_conversation(signal_api: SignalAPI):
    message = await parse(
        signal_api, RAW_EDIT_MESSAGE_SYNC_MESSAGE_PRIVATE_CONVERSATION
    )
    assert isinstance(message, EditMessage)
    assert message.target_sent_timestamp == TIMESTAMP
    assert message.text == "Uhrzeit!"
    assert message.source == DESTINATION
    assert message.source_number == DESTINATION


async def test_typing_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_TYPING_MESSAGE)
    assert isinstance(message, TypingMessage)
    assert message.timestamp == TIMESTAMP
    assert message.is_private()


async def test_group_update(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_GROUP_UPDATE_MESSAGE)
    assert isinstance(message, GroupUpdate)
    assert message.group_info.group_id == GROUP_ID


async def test_attachments(signal_api: SignalAPI, mocker: MockerFixture):
    attachment_bytes = b"test"

    mock_response = mocker.AsyncMock(spec=aiohttp.ClientResponse)
    mock_response.raise_for_status = mocker.Mock()
    mock_response.content.read = mocker.AsyncMock(return_value=attachment_bytes)

    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.AsyncMock(return_value=mock_response)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mocker.patch("aiohttp.ClientSession", return_value=mock_session)

    message = await parse(signal_api, RAW_ATTACHMENT_MESSAGE)

    assert isinstance(message, DataMessage)
    assert message.attachments is not None
    assert message.attachments[0].base64_content == base64.b64encode(
        attachment_bytes
    ).decode("utf-8")
    assert message.attachments[0].local_filename == LOCAL_FILENAME


# User Chats


async def test_parse_user_chat_message(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_USER_CHAT_MESSAGE)
    assert isinstance(message, DataMessage)
    assert message.source_number == SOURCE
    assert message.text == TEXT
    assert message.timestamp == TIMESTAMP
    assert message.is_private()


async def test_preview_no_image(signal_api: SignalAPI):
    message = await parse(signal_api, RAW_PREVIEW_NO_IMAGE_MESSAGE)
    assert isinstance(message, DataMessage)
    assert isinstance(message.previews, list)
    assert len(message.previews) == 1

    lp = message.previews[0]
    assert lp.base64_thumbnail is None
    assert lp.url == "https://example.com"
    assert lp.title == "Example.com - Super example"
    assert lp.description == ""


async def test_unknown_message_format(signal_api: SignalAPI):
    with pytest.raises(UnknownMessageFormatError):
        await parse(signal_api, RAW_UNKNOWN_MESSAGE)


async def test_unparseable_json_raises(signal_api: SignalAPI):
    with pytest.raises(UnknownMessageFormatError):
        await parse(signal_api, "not json")
