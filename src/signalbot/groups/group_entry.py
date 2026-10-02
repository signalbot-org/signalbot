from signalbot._generated import GroupEntry as GeneratedGroupEntry
from signalbot.groups.group_permissions import GroupPermissions


class GroupEntry(GeneratedGroupEntry):
    """A group the bot is a member of, as returned by `GroupRegistry`."""

    # Narrowed to a wrapped type; rationale in
    # docs/contributing/04_new_signal_cli_rest_api.md.
    permissions: GroupPermissions  # pyright: ignore[reportIncompatibleVariableOverride]
