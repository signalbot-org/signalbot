from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
import pytest

from signalbot._generated import (
    AddMembers,
    EditGroup,
    GroupInfo,
    GroupPermissions,
    SendMessages,
)
from signalbot.messages import DataMessage
from tests.conftest import GROUP_ID, GROUP_INTERNAL_ID

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

    from signalbot import SignalBot

HTTP_OK = 200

FULL_GROUP_PERMISSIONS = GroupPermissions(
    add_members=AddMembers.EVERY_MEMBER,
    edit_group=EditGroup.EVERY_MEMBER,
    send_messages=SendMessages.EVERY_MEMBER,
)

PRIVATE_NUMBER = "+49987654321"
PRIVATE_UUID = "author-uuid"


def make_data_message(**overrides: object) -> DataMessage:
    """Build a minimal private `DataMessage` for unit tests.

    Pass any `DataMessage` field (e.g. `text=`, `mentions=`, `group_info=`)
    via `overrides` to customize it.
    """
    message = DataMessage(
        server_delivered_timestamp=1,
        server_received_timestamp=1,
        timestamp=1,
        source_number=PRIVATE_NUMBER,
        source_uuid=PRIVATE_UUID,
    )
    return message.model_copy(update=overrides) if overrides else message


def make_group_data_message(**overrides: object) -> DataMessage:
    """Same as `make_data_message`, but defaults `group_info` to the shared
    test group (`GROUP_INTERNAL_ID`)."""
    fields: dict[str, object] = {
        "group_info": GroupInfo(groupId=GROUP_INTERNAL_ID, revision=1),
    }
    fields.update(overrides)
    return make_data_message(**fields)


class TestCommon:
    @pytest.fixture(autouse=True)
    def _use_signal_bot(self, signal_bot: SignalBot) -> None:
        self.signal_bot = signal_bot


@pytest.fixture
def fake_group() -> dict:
    return {
        "admins": [],
        "blocked": False,
        "description": "",
        "name": "mocked group",
        "id": GROUP_ID,
        "internal_id": GROUP_INTERNAL_ID,
        "invite_link": "",
        "member": True,
        "members": [],
        "pending_invites": [],
        "pending_requests": [],
        "permissions": FULL_GROUP_PERMISSIONS.model_dump(),
    }


@pytest.fixture
def mock_receive(mocker: MockerFixture) -> Callable[[list[str]], None]:
    def _mock(raw_messages: list[str]) -> None:
        mock_iterator = mocker.AsyncMock()
        mock_iterator.__aiter__.return_value = raw_messages
        mock = mocker.patch("websockets.connect")
        mock.return_value.__aenter__.return_value = mock_iterator

    return _mock


@pytest.fixture
def mock_get_all_groups(mocker: MockerFixture) -> Callable[[list[dict]], None]:
    def _mock(groups: list[dict]) -> None:
        json_mock = mocker.AsyncMock(return_value=groups)
        get_groups_mock = mocker.patch(
            "aiohttp.ClientSession.get", new_callable=mocker.AsyncMock
        )
        get_groups_mock.return_value = mocker.AsyncMock(
            spec=aiohttp.ClientResponse,
            status=HTTP_OK,
            json=json_mock,
        )

    return _mock
