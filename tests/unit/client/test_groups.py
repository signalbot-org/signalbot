from collections.abc import Callable

from pytest_mock import MockType

from signalbot._client import SignalAPI
from signalbot._generated import AddMembers, EditGroup, SendMessages, UpdateGroupRequest
from signalbot.groups import GroupEntry, GroupPermissions
from tests.conftest import GROUP_ID

FULL_GROUP_PERMISSIONS = GroupPermissions(
    add_members=AddMembers.EVERY_MEMBER,
    edit_group=EditGroup.EVERY_MEMBER,
    send_messages=SendMessages.EVERY_MEMBER,
)


async def test_get_groups(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    group_entry = GroupEntry(
        admins=[],
        blocked=False,
        description="",
        id=GROUP_ID,
        internal_id="internal-id",
        invite_link="",
        member=True,
        members=[],
        name="Test",
        pending_invites=[],
        pending_requests=[],
        permissions=FULL_GROUP_PERMISSIONS,
    )
    mock_json_response("get", [group_entry.model_dump(by_alias=True)])

    groups = await signal_api.groups.get_all()

    assert groups == [group_entry]


async def test_get_group(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    group_entry = GroupEntry(
        admins=[],
        blocked=False,
        description="",
        id=GROUP_ID,
        internal_id="internal-id",
        invite_link="",
        member=True,
        members=[],
        name="Test",
        pending_invites=[],
        pending_requests=[],
        permissions=FULL_GROUP_PERMISSIONS,
    )
    mock_json_response("get", group_entry.model_dump(by_alias=True))

    group = await signal_api.groups.get(GROUP_ID)

    assert group == group_entry


async def test_update_group(
    signal_api: SignalAPI, mock_json_response: Callable[[str, dict | list], MockType]
):
    mock = mock_json_response("put", {})

    update_group_request = UpdateGroupRequest(name="New Name")
    await signal_api.groups.update(update_group_request, GROUP_ID)

    assert mock.call_count == 1
