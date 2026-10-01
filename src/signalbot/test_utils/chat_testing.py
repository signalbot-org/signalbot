from __future__ import annotations

import functools
import itertools
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from unittest.mock import DEFAULT, AsyncMock, MagicMock

from signalbot._generated import (
    AddMembers,
    EditGroup,
    RemoteDeleteResponse,
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

    from signalbot._generated import (
        RemoteDeleteRequest,
        SendMessageV2,
        SendReactionRequest,
    )
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

    Before the test body runs, the signal-cli-rest-api calls are stubbed (see the
    `*_mock` attributes on `ChatTestCase`), the bot
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
            self.receipts_mock = mocker.patch(
                "signalbot._client.receipts.ReceiptsClient.send",
                new_callable=AsyncMock,
            )
            self.start_typing_mock = mocker.patch(
                "signalbot._client.messages.MessagesClient.start_typing",
                new_callable=AsyncMock,
            )
            self.stop_typing_mock = mocker.patch(
                "signalbot._client.messages.MessagesClient.stop_typing",
                new_callable=AsyncMock,
            )
            self.remote_delete_mock = mocker.patch(
                "signalbot._client.messages.MessagesClient.remote_delete",
                new_callable=RemoteDeleteMock,
            )
            self.download_attachment_mock = mocker.patch(
                "signalbot._client.attachments.AttachmentsClient.download",
                new_callable=AsyncMock,
                return_value="",
            )

            receive_mock.define(messages)
            await self.signal_bot._async_init()
            await self.run_bot()

            return await func(self, mocker, *args, **kwargs)

        return wrapper_chat

    return decorator_chat


class ChatTestCase:
    """Base class for testing handlers against a mocked signal-cli-rest-api.

    Call `setup()` from a fixture, register handlers on `self.signal_bot` and
    decorate test methods with [mock_chat][signalbot.test_utils.mock_chat].
    Messages come from the test group (`group_id`, `group_name`) unless built
    with one of the private `new_*` classmethods.
    """

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
    """Stub for sending messages (`bot.messages.send`, `context.send`, ...)."""
    react_mock: ReactMock
    """Stub for sending reactions."""
    remote_delete_mock: RemoteDeleteMock
    """Stub for deleting sent messages (`bot.messages.remote_delete`)."""
    receipts_mock: AsyncMock
    """Stub for sending read/viewed receipts; called with a `Receipt` request."""
    start_typing_mock: AsyncMock
    """Stub for showing the typing indicator."""
    stop_typing_mock: AsyncMock
    """Stub for hiding the typing indicator."""
    download_attachment_mock: AsyncMock
    """Stub for downloading received attachments; returns empty base64 content."""

    signal_bot: SignalBot
    """The bot `mock_chat` feeds messages to; set by `setup()`."""

    def make_bot(self) -> SignalBot:
        """Build the bot under test; called by `setup()`.

        Override it when the bot is built by your own code, e.g. an application
        object that creates its `SignalBot` internally, and return that
        `SignalBot` (keeping a reference to the wrapper on `self` if tests need
        it). Use `self.config` for a configuration pointing at the mocked
        service. Assigning `self.signal_bot` directly works too.
        """
        return SignalBot(ChatTestCase.config)

    def setup(self) -> None:
        """Create the bot under test as `self.signal_bot` (see `make_bot`).

        Call it from a fixture, then register handlers on `self.signal_bot`.
        """
        self.signal_bot = self.make_bot()

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
    def _first_args(self) -> list[Any]:
        return [call.args[0] for call in self.call_args_list]


class SendMock(_FirstArgResultsMock):
    """Stub for sending messages.

    Each call returns one response per recipient, each with a fresh, strictly
    increasing timestamp (`FIRST_TIMESTAMP`, then +1 per response), so the
    [SentMessage][signalbot.messages.SentMessage]s a handler gets back can be
    told apart, e.g. to match later edits, remote deletes or quotes. Setting
    `return_value` explicitly overrides this.
    """

    FIRST_TIMESTAMP = 1638715559464

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._timestamps = itertools.count(self.FIRST_TIMESTAMP)
        self.side_effect = self._respond

    def _respond(self, data_message: SendMessageV2) -> object:
        if self._mock_return_value is not DEFAULT:
            return DEFAULT
        return [
            SendMessageResponse(timestamp=str(next(self._timestamps)))
            for _ in data_message.recipients or [None]
        ]

    def results(self) -> list[SendMessageV2]:
        """The message request passed to each send, in call order."""
        return self._first_args()


class ReactMock(_FirstArgResultsMock):
    """Stub for sending reactions."""

    def results(self) -> list[SendReactionRequest]:
        """The reaction request passed to each call, in call order."""
        return self._first_args()


class RemoteDeleteMock(_FirstArgResultsMock):
    """Stub for deleting sent messages.

    Each call returns a fresh, strictly increasing timestamp (`FIRST_TIMESTAMP`,
    then +1 per call). Setting `return_value` explicitly overrides this.
    """

    FIRST_TIMESTAMP = 1638715600000

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._timestamps = itertools.count(self.FIRST_TIMESTAMP)
        self.side_effect = self._respond

    def _respond(self, _remote_delete_request: RemoteDeleteRequest) -> object:
        if self._mock_return_value is not DEFAULT:
            return DEFAULT
        return RemoteDeleteResponse(timestamp=str(next(self._timestamps)))

    def results(self) -> list[RemoteDeleteRequest]:
        """The delete request passed to each call, in call order."""
        return self._first_args()


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
