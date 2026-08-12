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


def mock_chat(*messages: str) -> Callable[[AsyncTestMethod], AsyncTestMethod]:
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
            await self.signal_bot._async_post_init()
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
    ) -> str:
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
        return json.dumps(message)

    @classmethod
    def new_reaction_message(cls, emoji: str) -> str:
        timestamp = int(time.time() * 1000)
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
    def new_message(cls, text: str) -> str:
        timestamp = int(time.time() * 1000)
        new_uuid = str(uuid.uuid4())
        return cls._sent_message_envelope(
            timestamp=timestamp, new_uuid=new_uuid, message=text
        )


class ReceiveMock(MagicMock):
    def define(self, messages: Sequence[str]) -> None:
        json_messages = [ChatTestCase.new_message(m) for m in messages]
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
        self.return_value = SendMessageResponse(timestamp="1638715559464")


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
            version="0.100.0",
            versions=["v1"],
        )


class CheckSignalServiceMock(AsyncMock):
    def __init__(self, **kwargs: str) -> None:
        super().__init__(**kwargs)
        self.return_value = True


class DummyHandler(DataMessageHandler):
    async def handle_data_message(self, context: DataMessageContext) -> None:
        pass
