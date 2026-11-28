from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from signalbot import DataMessageHandler, SignalBotError
from signalbot.groups import GroupEntry
from signalbot.test_utils import ChatTestCase
from tests.conftest import GROUP_ID, GROUP_INTERNAL_ID
from tests.unit.conftest import TestCommon

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture, MockType

    from signalbot.context import DataMessageContext

# Same shape as GROUP_ID (`_is_group_id` matches it) but a different value, so
# it's never in the registry's cache.
UNKNOWN_GROUP_ID = GROUP_ID[:6] + "X" + GROUP_ID[7:]


class TestGetter(TestCommon):
    def test_null_group(self):
        assert not self.signal_bot.groups.get("none")

    async def test_get_group(
        self,
        mock_receive: Callable[[list[str]], None],
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        class GroupInspector(DataMessageHandler):
            def __init__(self):
                super().__init__()
                self.found_group = None

            async def handle_data_message(self, context: DataMessageContext) -> None:
                assert context.message.group_info is not None
                assert context.message.group_info.group_id is not None
                self.found_group = context.bot.groups.get(
                    context.message.group_info.group_id
                )

        mock_receive([ChatTestCase.new_message("Message 1")])
        mock_get_all_groups([fake_group])

        inspector = GroupInspector()
        self.signal_bot.register(inspector)

        await self.signal_bot._pipeline.resolve_handlers()

        await self.signal_bot._pipeline._produce(1337)

        await self.signal_bot._pipeline._consume_new_item(1337)

        expected_group = GroupEntry.model_validate(fake_group)
        assert inspector.found_group == expected_group
        assert inspector.found_group is not expected_group


class TestResolve(TestCommon):
    async def test_resolve_known_group_id(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_get_all_groups([fake_group])
        await self.signal_bot.groups.refresh()

        assert self.signal_bot.groups.resolve(GROUP_ID) == GROUP_ID

    async def test_resolve_group_id_shaped_but_unknown_returns_none(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        """A string with the shape of a group id but absent from the cache
        must resolve to None, not be handed back unverified - otherwise a
        typo'd or stale id would silently look "resolved" to callers."""
        mock_get_all_groups([fake_group])
        await self.signal_bot.groups.refresh()

        assert self.signal_bot.groups.resolve(UNKNOWN_GROUP_ID) is None

    async def test_recipient_resolver_rejects_unknown_group_shaped_id(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_get_all_groups([fake_group])
        await self.signal_bot.groups.refresh()

        with pytest.raises(SignalBotError):
            self.signal_bot._recipients.resolve(UNKNOWN_GROUP_ID)


SECOND_GROUP_ID = GROUP_ID[:6] + "Y" + GROUP_ID[7:]


def _second_group(fake_group: dict, **overrides: object) -> dict:
    return {
        **fake_group,
        "id": SECOND_GROUP_ID,
        "internal_id": "second-internal-id",
        **overrides,
    }


class TestContainer(TestCommon):
    async def test_iter_len_getitem_contains(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_get_all_groups([fake_group, _second_group(fake_group, name="second")])
        groups = self.signal_bot.groups

        await groups.refresh()

        assert len(groups) == 2
        assert [g.id for g in groups] == [GROUP_ID, SECOND_GROUP_ID]
        assert groups[1].name == "second"
        assert GROUP_INTERNAL_ID in groups
        assert GROUP_ID not in groups  # membership is by internal id
        assert groups.get_id(GROUP_INTERNAL_ID) == GROUP_ID
        assert groups.get_id("unknown") is None


class TestResolveByName(TestCommon):
    async def test_resolve_by_internal_id_and_name(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_get_all_groups([fake_group])
        await self.signal_bot.groups.refresh()

        assert self.signal_bot.groups.resolve(GROUP_INTERNAL_ID) == GROUP_ID
        assert self.signal_bot.groups.resolve(fake_group["name"]) == GROUP_ID
        assert self.signal_bot.groups.resolve("no such group") is None

    async def test_duplicate_names_warn_and_use_the_first(
        self,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
        caplog: pytest.LogCaptureFixture,
    ):
        mock_get_all_groups([fake_group, _second_group(fake_group)])
        await self.signal_bot.groups.refresh()

        with caplog.at_level(logging.WARNING):
            resolved = self.signal_bot.groups.resolve(fake_group["name"])

        assert resolved == GROUP_ID
        assert "more than one group named" in caplog.text


class TestRefreshOne(TestCommon):
    @pytest.fixture
    def renamed(self, mocker: MockerFixture, fake_group: dict) -> MockType:
        """Make the API return the cached test group under a new name."""
        return mocker.patch.object(
            self.signal_bot._signal.groups,
            "get",
            new_callable=mocker.AsyncMock,
            return_value=GroupEntry.model_validate({**fake_group, "name": "renamed"}),
        )

    async def test_rename_updates_lookups(
        self,
        renamed: MockType,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_get_all_groups([fake_group])
        groups = self.signal_bot.groups
        await groups.refresh()

        await groups.refresh_one(GROUP_INTERNAL_ID)

        renamed.assert_awaited_once_with(GROUP_ID)
        assert groups.get(GROUP_INTERNAL_ID) == renamed.return_value
        assert groups.resolve("renamed") == GROUP_ID
        # Regression: used to raise IndexError on the now-empty name bucket
        assert groups.resolve(fake_group["name"]) is None

    async def test_rename_keeps_other_groups_with_the_old_name(
        self,
        renamed: MockType,
        mock_get_all_groups: Callable[[list[dict]], None],
        fake_group: dict,
    ):
        mock_get_all_groups([fake_group, _second_group(fake_group)])
        groups = self.signal_bot.groups
        await groups.refresh()

        await groups.refresh_one(GROUP_INTERNAL_ID)

        assert groups.resolve(fake_group["name"]) == SECOND_GROUP_ID
