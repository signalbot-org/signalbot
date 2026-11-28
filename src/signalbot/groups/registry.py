from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from collections.abc import Iterator

    from signalbot._actions import GroupActions
    from signalbot._client import SignalAPI
    from signalbot.groups.group_entry import GroupEntry


class GroupRegistry:
    """List-like cache of the groups the bot is a member of, with lookup helpers.

    To update a group's metadata, use `actions` (`bot.groups.actions`) instead.
    """

    actions: GroupActions
    """Update group metadata. Set by `SignalBot._init_actions()`."""

    def __init__(self, signal: SignalAPI, logger: logging.Logger) -> None:
        self._signal = signal
        self._logger = logger

        self._by_id: dict[str, GroupEntry] = {}
        self._by_internal_id: dict[str, GroupEntry] = {}
        self._by_name: defaultdict[str, list[GroupEntry]] = defaultdict(list)

    def __iter__(self) -> Iterator[GroupEntry]:
        return iter(self._by_internal_id.values())

    def __len__(self) -> int:
        return len(self._by_internal_id)

    def __getitem__(self, index: int) -> GroupEntry:
        return list(self._by_internal_id.values())[index]

    def __contains__(self, internal_id: str) -> bool:
        return internal_id in self._by_internal_id

    def get(self, internal_id: str) -> GroupEntry | None:
        """Look up a cached group by its internal id, without hitting the network.

        Args:
            internal_id: The group's internal id, as used by `__iter__`,
                `__getitem__`, and `refresh()`/`refresh_one()`.

        Returns:
            The cached `GroupEntry`, or `None` if it isn't in the cache.
        """
        if internal_id in self._by_internal_id:
            return copy.deepcopy(self._by_internal_id[internal_id])
        return None

    def get_id(self, internal_id: str) -> str | None:
        """Look up a group's canonical id by its internal id, without copying
        the full `GroupEntry`. For hot-path callers (e.g. per-message,
        per-handler dispatch checks) that only need the id.

        Args:
            internal_id: The group's internal id.

        Returns:
            The group's canonical id, or `None` if it isn't in the cache.
        """
        group = self._by_internal_id.get(internal_id)
        return group.id if group is not None else None

    def resolve(self, group_id_or_name: str) -> str | None:
        group = self._by_id.get(group_id_or_name)
        if group is not None:
            return group.id

        if self._is_group_id(group_id_or_name):
            error_msg = f"[Bot] Group with id '{group_id_or_name}' not found. There "
            error_msg += "is a typo in id or the bot is not a member of the group."
            self._logger.warning(error_msg)
            return None

        group = self._by_internal_id.get(group_id_or_name)
        if group is not None:
            return group.id

        group = self._get_by_name(group_id_or_name)
        if group is not None:
            return group.id

        return None

    async def refresh(self) -> None:
        # reset group lookups to avoid stale data
        groups = await self._signal.groups.get_all()

        self._by_id = {}
        self._by_internal_id = {}
        self._by_name = defaultdict(list)
        for group in groups:
            self._by_id[group.id] = group
            self._by_internal_id[group.internal_id] = group
            self._by_name[group.name].append(group)

        self._logger.info("[Bot] %s groups detected", len(self._by_internal_id))

    async def refresh_one(self, group_internal_id: str) -> None:
        # look up group that requires update
        group = await self._signal.groups.get(
            self._by_internal_id[group_internal_id].id
        )

        current_group_name = self._by_internal_id[group_internal_id].name
        # group name may have been updated
        self._by_name[current_group_name] = [
            g for g in self._by_name[current_group_name] if g.id != group.id
        ]
        self._by_id[group.id] = group
        self._by_internal_id[group.internal_id] = group
        self._by_name[group.name].append(group)

        self._logger.info("[Bot] Group updated")

    def _get_by_name(self, group_name: str) -> GroupEntry | None:
        groups = self._by_name.get(group_name)
        if groups:
            if len(groups) > 1:
                error_msg = f"[Bot] There is more than one group named '{group_name}',"
                error_msg += " using the first one."
                self._logger.warning(error_msg)
            return groups[0]
        return None

    def _is_group_id(self, group_id: str) -> bool:
        """Check if group_id has the right format, e.g.

              random string                                              length 66
              ↓                                                          ↓
        group.OyZzqio1xDmYiLsQ1VsqRcUFOU4tK2TcECmYt2KeozHJwglMBHAPS7jlkrm=
        ↑                                                                ↑
        prefix                                                           suffix
        """
        return re.match(r"^group\.[a-zA-Z0-9]{59}=$", group_id) is not None
