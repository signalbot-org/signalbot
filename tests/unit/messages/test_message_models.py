"""Edge cases of the received-message domain models: parse paths not exercised by
`test_message.py`, malformed envelopes, and `DataMessage.to_send_message`."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

import pytest

from signalbot._generated import GroupInfo as GeneratedGroupInfo
from signalbot._generated import Message
from signalbot.attachments import Attachment
from signalbot.groups import GroupUpdate
from signalbot.groups.group_update import GroupUpdateInfo
from signalbot.messages import (
    DataMessage,
    EditMessage,
    RemoteDelete,
    TypingMessage,
    UnknownMessageFormatError,
    parse,
)
from signalbot.messages.data_message_content import Mention, Quote
from signalbot.messages.link_preview import Preview
from signalbot.messages.typing_message import TypingAction
from signalbot.reactions import Reaction
from tests.unit.conftest import PRIVATE_NUMBER, PRIVATE_UUID, make_data_message
from tests.unit.messages.test_message import GROUP_ID, SOURCE, TIMESTAMP, envelope

if TYPE_CHECKING:
    from pathlib import Path

    from signalbot._client import SignalAPI
    from signalbot._generated import MessageEnvelope


def _message_envelope(**body: object) -> MessageEnvelope:
    raw = json.loads(envelope())
    raw["envelope"].update(body)
    return Message.model_validate(raw).envelope


GROUP_UPDATE_INFO = {
    "groupId": GROUP_ID,
    "groupName": "group name",
    "revision": 2,
    "type": "UPDATE",
}


class TestParse:
    async def test_sync_message_without_sent_message_is_unknown(
        self, signal_api: SignalAPI
    ):
        raw = envelope(syncMessage={"readMessages": []})

        with pytest.raises(UnknownMessageFormatError):
            await parse(signal_api, raw)

    async def test_reaction_received_from_another_account(self, signal_api: SignalAPI):
        raw = envelope(
            dataMessage={
                "timestamp": TIMESTAMP,
                "reaction": {
                    "emoji": "🔥",
                    "targetAuthor": PRIVATE_NUMBER,
                    "targetAuthorNumber": PRIVATE_NUMBER,
                    "targetAuthorUuid": PRIVATE_UUID,
                    "targetSentTimestamp": 1234,
                    "isRemove": True,
                },
            }
        )

        message = await parse(signal_api, raw)

        assert isinstance(message, Reaction)
        assert message.emoji == "🔥"
        assert message.is_remove is True
        assert message.timestamp == 1234
        assert message.source_number == SOURCE

    async def test_group_typing_message(self, signal_api: SignalAPI):
        raw = envelope(
            typingMessage={
                "action": "STOPPED",
                "groupId": GROUP_ID,
                "timestamp": TIMESTAMP,
            }
        )

        message = await parse(signal_api, raw)

        assert isinstance(message, TypingMessage)
        assert message.action == TypingAction.STOPPED
        assert message.is_group()
        assert not message.is_private()
        assert message.source_or_group_id() == GROUP_ID


@pytest.mark.parametrize(
    "from_envelope",
    [
        pytest.param(
            DataMessage.from_message_envelope,
            id="DataMessage",
        ),
        pytest.param(
            EditMessage.from_message_envelope,
            id="EditMessage",
        ),
        pytest.param(
            lambda env, _: RemoteDelete.from_message_envelope(env), id="RemoteDelete"
        ),
        pytest.param(
            lambda env, _: TypingMessage.from_message_envelope(env),
            id="TypingMessage",
        ),
        pytest.param(lambda env, _: Reaction.from_message_envelope(env), id="Reaction"),
    ],
)
async def test_from_envelope_without_matching_body_raises(
    signal_api: SignalAPI, from_envelope
):
    empty = _message_envelope()

    with pytest.raises(ValueError, match="MessageEnvelope does not contain"):
        await from_envelope(empty, signal_api)


def _typing_message(
    source_uuid: str | None = None, source_number: str | None = None
) -> TypingMessage:
    return TypingMessage(
        action=TypingAction.STARTED,
        timestamp=1,
        server_delivered_timestamp=1,
        server_received_timestamp=1,
        source_uuid=source_uuid,
        source_number=source_number,
    )


async def test_sync_edit_without_data_message_raises(signal_api: SignalAPI):
    env = _message_envelope(
        syncMessage={
            "sentMessage": {
                "timestamp": TIMESTAMP,
                "editMessage": {"targetSentTimestamp": TIMESTAMP},
            }
        }
    )

    with pytest.raises(ValueError, match="does not contain an EditMessage"):
        await EditMessage.from_message_envelope(env, signal_api)


class TestTypingMessage:
    async def test_missing_action_raises(self):
        env = _message_envelope(typingMessage={"timestamp": TIMESTAMP})

        with pytest.raises(ValueError, match="missing required field: action"):
            await TypingMessage.from_message_envelope(env)

    @pytest.mark.parametrize(
        ("source_uuid", "source_number", "expected"),
        [
            (PRIVATE_UUID, PRIVATE_NUMBER, PRIVATE_UUID),
            (None, PRIVATE_NUMBER, PRIVATE_NUMBER),
        ],
    )
    def test_source_or_group_id_prefers_uuid(
        self, source_uuid: str | None, source_number: str | None, expected: str
    ):
        message = _typing_message(source_uuid=source_uuid, source_number=source_number)

        assert message.source_or_group_id() == expected

    def test_source_or_group_id_without_source_raises(self):
        message = _typing_message()

        with pytest.raises(ValueError, match="does not contain a source"):
            message.source_or_group_id()


class TestBaseMessageWithGroupSource:
    def test_falls_back_to_source_number(self):
        message = make_data_message(source_uuid=None)

        assert message.source_or_group_id() == PRIVATE_NUMBER

    def test_without_source_raises(self):
        message = make_data_message(source_uuid=None, source_number=None)

        with pytest.raises(ValueError, match="does not contain a source"):
            message.source_or_group_id()


class TestGroupUpdate:
    @pytest.mark.parametrize(
        ("overrides", "error"),
        [
            ({"groupId": None}, "group_id cannot be None"),
            ({"groupName": None}, "group_name cannot be None"),
            ({"type": "DELIVER"}, "Expected type 'UPDATE', got 'DELIVER'"),
        ],
    )
    def test_from_base_rejects_incomplete_info(self, overrides: dict, error: str):
        group_info = GeneratedGroupInfo.model_validate(
            {**GROUP_UPDATE_INFO, **overrides}
        )

        with pytest.raises(ValueError, match=error):
            GroupUpdateInfo.from_base(group_info)

    def test_from_sync_message(self):
        env = _message_envelope(
            syncMessage={
                "sentMessage": {"timestamp": TIMESTAMP, "groupInfo": GROUP_UPDATE_INFO}
            }
        )

        message = GroupUpdate.from_message_envelope(env)

        assert message.group_info.group_name == "group name"
        assert message.group_info.revision == 2
        assert message.is_group()
        assert not message.is_private()
        assert message.source_or_group_id() == GROUP_ID

    def test_data_message_without_group_info_raises(self):
        env = _message_envelope(dataMessage={"timestamp": TIMESTAMP})

        with pytest.raises(ValueError, match="does not contain group_info"):
            GroupUpdate.from_message_envelope(env)

    def test_envelope_without_message_raises(self):
        with pytest.raises(ValueError, match="does not contain group_info"):
            GroupUpdate.from_message_envelope(_message_envelope())


class TestToSendMessage:
    def test_text_only(self):
        send = make_data_message(text="hello", view_once=True).to_send_message()

        assert send.text == "hello"
        assert send.view_once is True
        assert send.base64_attachments is None
        assert send.link_preview is None
        assert send.mentions is None
        assert send.quote_timestamp is None

    def test_attachments_use_base64_content_or_read_the_local_file(
        self, tmp_path: Path
    ):
        local_file = tmp_path / "attachment.bin"
        local_file.write_bytes(b"from disk")
        message = make_data_message(
            attachments=[
                Attachment(base64_content="aW5saW5l", isVoiceNote=False),
                Attachment(local_filename=str(local_file), isVoiceNote=False),
            ]
        )

        send = message.to_send_message()

        assert send.base64_attachments == [
            "aW5saW5l",
            base64.b64encode(b"from disk").decode(),
        ]

    def test_attachment_without_content_raises(self):
        message = make_data_message(attachments=[Attachment(isVoiceNote=False)])

        with pytest.raises(ValueError, match="local_filename or base64 content"):
            message.to_send_message()

    def test_preview_with_thumbnail_becomes_link_preview(self):
        url = "https://example.com"
        message = make_data_message(
            text=f"see {url}",
            previews=[Preview(url=url, title="Example", base64_thumbnail="dGh1bWI=")],
        )

        link_preview = message.to_send_message().link_preview

        assert link_preview is not None
        assert link_preview.url == url
        assert link_preview.title == "Example"
        assert link_preview.description == ""
        assert link_preview.thumbnail == "dGh1bWI="

    def test_preview_without_thumbnail_is_dropped(self):
        url = "https://example.com"
        message = make_data_message(
            text=f"see {url}", previews=[Preview(url=url, title="Example")]
        )

        assert message.to_send_message().link_preview is None

    def test_mentions_and_quote_are_carried_over(self):
        mention = Mention(start=0, length=1, uuid=PRIVATE_UUID)
        uuidless = Mention(start=2, length=1, number=PRIVATE_NUMBER)
        message = make_data_message(
            text="@ @",
            mentions=[mention, uuidless],
            quote=Quote(
                id=99, author=PRIVATE_NUMBER, text="original", mentions=[mention]
            ),
        )

        send = message.to_send_message()

        # mentions without a uuid can't be addressed when sending, so are dropped
        assert send.mentions is not None
        assert [(m.author, m.start, m.length) for m in send.mentions] == [
            (PRIVATE_UUID, 0, 1)
        ]
        assert send.quote_timestamp == 99
        assert send.quote_author == PRIVATE_NUMBER
        assert send.quote_text == "original"
        assert send.quote_mentions is not None
        assert [m.author for m in send.quote_mentions] == [PRIVATE_UUID]
