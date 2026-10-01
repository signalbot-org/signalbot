from __future__ import annotations

import functools
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from signalbot._generated import (
    AddMembers,
    EditGroup,
    SendMessageResponse,
    SendMessages,
)
from signalbot.bot import SignalBot
from signalbot.general.about import About
from signalbot.groups.group_entry import GroupEntry
from signalbot.groups.group_permissions import GroupPermissions
from signalbot.handlers import DataMessageHandler

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from signalbot.context import DataMessageContext

AsyncTestMethod = Callable[..., Awaitable[None]]


class Envelope(str):
    """A raw signal-cli-rest-api JSON envelope, exactly as received over the
    websocket.

    [mock_chat][signalbot.test_utils.mock_chat] and
    [ReceiveMock.define][signalbot.test_utils.ReceiveMock.define] feed an
    `Envelope` to the bot untouched, whereas a plain `str` is treated as the text
    of a group message and wrapped with
    [ChatTestCase.new_message][signalbot.test_utils.ChatTestCase.new_message].
    Build envelopes with the `ChatTestCase.new_*` classmethods, or wrap your own
    JSON with `Envelope(json.dumps(...))`.
    """

    __slots__ = ()


class _TimestampClock:
    """Millisecond timestamps that never repeat, even within the same
    millisecond, so messages built back to back can be told apart."""

    def __init__(self) -> None:
        self._last = 0

    def __call__(self) -> int:
        self._last = max(int(time.time() * 1000), self._last + 1)
        return self._last


_new_timestamp = _TimestampClock()


def mock_chat(*messages: str) -> Callable[[AsyncTestMethod], AsyncTestMethod]:
    """Run the bot on `messages` before the decorated `ChatTestCase` test runs.

    Each message is either an [Envelope][signalbot.test_utils.Envelope], fed to
    the bot as-is, or a plain `str`, which becomes a group text message (see
    [ChatTestCase.new_message][signalbot.test_utils.ChatTestCase.new_message]).

    Before the test body runs, the signal-cli-rest-api calls are stubbed, the bot
    is initialised (ready handlers run, but no background producer/consumer
    tasks are started) and every message is dispatched to the registered
    handlers, which run to completion one at a time. The test body then inspects
    the stubs, e.g. `self.send_mock.results()`.
    """

    def decorator_chat(func: AsyncTestMethod) -> AsyncTestMethod:
        @functools.wraps(func)
        async def wrapper_chat(
            self: ChatTestCase,
            mocker: MockerFixture,
            *args: object,
            **kwargs: object,
        ) -> None:
            self.react_mock = mocker.patch(
                "signalbot._client.reactions.ReactionsClient.react",
                new_callable=ReactMock,
            )
            self.send_mock = mocker.patch(
                "signalbot._client.messages.MessagesClient.send",
                new_callable=SendMock,
            )
            receive_mock = mocker.patch(
                "signalbot._client.messages.MessagesClient.receive",
                new_callable=ReceiveMock,
            )
            mocker.patch(
                "signalbot._client.groups.GroupsClient.get_all",
                new_callable=GetAllMock,
            )
            mocker.patch(
                "signalbot._client.general.GeneralClient.about",
                new_callable=AboutMock,
            )
            mocker.patch(
                "signalbot._client.SignalAPI.check_signal_service",
                new_callable=CheckSignalServiceMock,
            )

            receive_mock.define(messages)
            await self.signal_bot._async_init()
            await self.run_bot()

            return await func(self, mocker, *args, **kwargs)

        return wrapper_chat

    return decorator_chat


class ChatTestCase:
    signal_service = "127.0.0.1:8080"
    phone_number = "+49123456789"

    group_internal_id = "Mg8LQTdaZJs8+LJCrtQgblqHx+xI2dX9JJ8hVA2kqt8="
    group_name = "Test"
    group_id = "group.OyZzqio1xDmYiLsQ1VsqRcUFOU4tK2TcECmYt2KeozHJwglMBHAPS7jlkrm="
    config = MappingProxyType(
        {
            "signal_service": signal_service,
            "phone_number": phone_number,
            "storage": {"type": "in-memory"},
        }
    )

    # Populated by `mock_chat` once a test is decorated with it.
    send_mock: SendMock
    react_mock: ReactMock

    def setup(self) -> None:
        self.signal_bot = SignalBot(ChatTestCase.config)

    async def run_bot(self) -> None:
        producer_id = 1337
        handler_id = 4444
        pipeline = self.signal_bot._pipeline
        await pipeline._produce(producer_id)
        while pipeline._q.qsize() > 0:
            await pipeline._consume_new_item(handler_id)

    @classmethod
    def _sent_message_envelope(
        cls, *, timestamp: int, new_uuid: str, **sent_message_body: object
    ) -> Envelope:
        message = {
            "account": ChatTestCase.phone_number,
            "envelope": {
                "source": ChatTestCase.phone_number,
                "sourceNumber": ChatTestCase.phone_number,
                "sourceUuid": new_uuid,
                "sourceName": "some_source_name",
                "sourceDevice": 1,
                "timestamp": timestamp,
                "serverReceivedTimestamp": timestamp,
                "serverDeliveredTimestamp": timestamp,
                "syncMessage": {
                    "sentMessage": {
                        "timestamp": timestamp,
                        "expiresInSeconds": 0,
                        "viewOnce": False,
                        "mentions": [],
                        "attachments": [],
                        "contacts": [],
                        "groupInfo": {
                            "groupId": ChatTestCase.group_internal_id,
                            "type": "DELIVER",
                            "revision": 1,
                        },
                        "destination": None,
                        "destinationNumber": None,
                        "destinationUuid": None,
                        **sent_message_body,
                    },
                },
            },
        }
        return Envelope(json.dumps(message))

    @classmethod
    def _received_envelope(
        cls, *, source_uuid: str, timestamp: int, **envelope_body: object
    ) -> Envelope:
        """An envelope received from another account (not a sync message), so it
        is a direct message to the bot unless its body carries `groupInfo`."""
        message = {
            "account": ChatTestCase.phone_number,
            "envelope": {
                "source": source_uuid,
                "sourceNumber": None,
                "sourceUuid": source_uuid,
                "sourceName": "some_source_name",
                "sourceDevice": 1,
                "timestamp": timestamp,
                "serverReceivedTimestamp": timestamp,
                "serverDeliveredTimestamp": timestamp,
                **envelope_body,
            },
        }
        return Envelope(json.dumps(message))

    @classmethod
    def new_reaction_message(cls, emoji: str) -> Envelope:
        """A reaction with `emoji`, sent in the test group by the bot's own
        account."""
        timestamp = _new_timestamp()
        new_uuid = str(uuid.uuid4())
        return cls._sent_message_envelope(
            timestamp=timestamp,
            new_uuid=new_uuid,
            message=None,
            reaction={
                "emoji": emoji,
                "targetAuthor": ChatTestCase.phone_number,
                "targetAuthorNumber": ChatTestCase.phone_number,
                "targetAuthorUuid": new_uuid,
                "targetSentTimestamp": timestamp,
                "isRemove": False,
            },
        )

    @classmethod
    def new_message(cls, text: str) -> Envelope:
        """A text message sent in the test group (`ChatTestCase.group_id`) by the
        bot's own account.

        This is what `mock_chat` turns plain `str` messages into.
        """
        timestamp = _new_timestamp()
        new_uuid = str(uuid.uuid4())
        return cls._sent_message_envelope(
            timestamp=timestamp, new_uuid=new_uuid, message=text
        )

    @classmethod
    def new_private_message(  # noqa: PLR0913
        cls,
        text: str | None,
        *,
        source_uuid: str | None = None,
        timestamp: int | None = None,
        quote: dict | None = None,
        attachments: list[dict] | None = None,
        view_once: bool = False,
    ) -> Envelope:
        """A direct (one-on-one) message to the bot, so `message.is_private()` is
        true and it reaches handlers registered with `groups=False`.

        Args:
            text: The message text.
            source_uuid: The sender's uuid; a random uuid4 if `None`.
            timestamp: The message timestamp in milliseconds; a fresh, unique one
                if `None`. Pass it explicitly to refer to this message later
                (e.g. from `new_edit_message` or `new_remote_delete`).
            quote: The quoted message in signal-cli's raw format, e.g.
                `{"id": <quoted timestamp>, "author": ..., "authorUuid": ...,
                "text": ...}`.
            attachments: Attachments in signal-cli's raw format, e.g.
                `{"id": ..., "contentType": "image/png", "isVoiceNote": False}`.
            view_once: Whether the message is a view-once message.
        """
        if timestamp is None:
            timestamp = _new_timestamp()
        data_message: dict[str, object] = {
            "timestamp": timestamp,
            "message": text,
            "expiresInSeconds": 0,
            "viewOnce": view_once,
        }
        if quote is not None:
            data_message["quote"] = quote
        if attachments is not None:
            data_message["attachments"] = attachments
        return cls._received_envelope(
            source_uuid=source_uuid or str(uuid.uuid4()),
            timestamp=timestamp,
            dataMessage=data_message,
        )

    @classmethod
    def new_edit_message(
        cls,
        text: str,
        *,
        source_uuid: str,
        target_sent_timestamp: int,
        timestamp: int | None = None,
    ) -> Envelope:
        """A direct message from `source_uuid` editing their earlier message sent
        at `target_sent_timestamp`; it is received as an
        [EditMessage][signalbot.messages.EditMessage] by `DataMessageHandler`s.

        Args:
            text: The new text of the message.
            source_uuid: The sender's uuid, i.e. the author of the edited message.
            target_sent_timestamp: The timestamp of the message being edited.
            timestamp: The timestamp of the edit; a fresh, unique one if `None`.
        """
        if timestamp is None:
            timestamp = _new_timestamp()
        return cls._received_envelope(
            source_uuid=source_uuid,
            timestamp=timestamp,
            editMessage={
                "targetSentTimestamp": target_sent_timestamp,
                "dataMessage": {
                    "timestamp": timestamp,
                    "message": text,
                    "expiresInSeconds": 0,
                    "viewOnce": False,
                },
            },
        )

    @classmethod
    def new_remote_delete(
        cls,
        *,
        source_uuid: str,
        target_sent_timestamp: int,
        timestamp: int | None = None,
    ) -> Envelope:
        """A direct message from `source_uuid` deleting their earlier message sent
        at `target_sent_timestamp`; it is received by `RemoteDeleteHandler`s as a
        [RemoteDelete][signalbot.messages.RemoteDelete] whose `timestamp` is
        `target_sent_timestamp`.

        Args:
            source_uuid: The sender's uuid, i.e. the author of the deleted message.
            target_sent_timestamp: The timestamp of the message being deleted.
            timestamp: The timestamp of the delete itself; a fresh, unique one if
                `None`.
        """
        if timestamp is None:
            timestamp = _new_timestamp()
        return cls._received_envelope(
            source_uuid=source_uuid,
            timestamp=timestamp,
            dataMessage={
                "timestamp": timestamp,
                "expiresInSeconds": 0,
                "viewOnce": False,
                "remoteDelete": {"timestamp": target_sent_timestamp},
            },
        )


class ReceiveMock(MagicMock):
    def define(self, messages: Sequence[str]) -> None:
        """Make `receive()` yield `messages`: an
        [Envelope][signalbot.test_utils.Envelope] is yielded as-is, a plain `str`
        is wrapped with `ChatTestCase.new_message`."""
        json_messages = [
            m if isinstance(m, Envelope) else ChatTestCase.new_message(m)
            for m in messages
        ]
        mock_iterator = AsyncMock()
        mock_iterator.__aiter__.return_value = json_messages
        self.return_value = mock_iterator

    def define_raw(self, raw_messages: list[str]) -> None:
        mock_iterator = AsyncMock()
        mock_iterator.__aiter__.return_value = raw_messages
        self.return_value = mock_iterator


class _FirstArgResultsMock(AsyncMock):
    def results(self) -> list:
        return [call.args[0] for call in self.call_args_list]


class SendMock(_FirstArgResultsMock):
    def __init__(self, **kwargs: str) -> None:
        super().__init__(**kwargs)
        self.return_value = [SendMessageResponse(timestamp="1638715559464")]


class ReactMock(_FirstArgResultsMock):
    pass


class GetAllMock(AsyncMock):
    def __init__(self, **kwargs: str) -> None:
        super().__init__(**kwargs)
        self.return_value = [
            GroupEntry(
                admins=[],
                blocked=False,
                description="",
                id=ChatTestCase.group_id,
                internal_id=ChatTestCase.group_internal_id,
                invite_link="",
                member=True,
                members=[],
                name=ChatTestCase.group_name,
                pending_invites=[],
                pending_requests=[],
                permissions=GroupPermissions(
                    add_members=AddMembers.EVERY_MEMBER,
                    edit_group=EditGroup.EVERY_MEMBER,
                    send_messages=SendMessages.EVERY_MEMBER,
                ),
            )
        ]


class AboutMock(AsyncMock):
    def __init__(self, **kwargs: str) -> None:
        super().__init__(**kwargs)
        self.return_value = About(
            build=1,
            capabilities={},
            mode="json-rpc",
            version="0.101.0",
            versions=["v1"],
        )


class CheckSignalServiceMock(AsyncMock):
    def __init__(self, **kwargs: str) -> None:
        super().__init__(**kwargs)
        self.return_value = True


class DummyHandler(DataMessageHandler):
    async def handle_data_message(self, context: DataMessageContext) -> None:
        pass
