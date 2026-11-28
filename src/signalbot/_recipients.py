from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

import phonenumbers

from signalbot.errors import SignalBotError

if TYPE_CHECKING:
    from signalbot.groups import GroupRegistry


class RecipientResolver:
    """Resolves a phone number, UUID, username, or group ID/name into the
    UUID or group ID.
    """

    def __init__(self, groups: GroupRegistry) -> None:
        self._groups = groups

    def resolve(self, recipient: str) -> str:
        if self._is_phone_number(recipient):
            return recipient

        if self._is_valid_uuid(recipient):
            return recipient

        if self._is_username(recipient):
            return recipient

        group_id = self._groups.resolve(recipient)
        if group_id is not None:
            return group_id

        raise SignalBotError.cannot_resolve_recipient()

    def _is_phone_number(self, phone_number: str) -> bool:
        try:
            parsed_number = phonenumbers.parse(phone_number, region=None)
            return phonenumbers.is_valid_number(parsed_number)
        except phonenumbers.phonenumberutil.NumberParseException:
            return False

    def _is_valid_uuid(self, recipient_uuid: str) -> bool:
        try:
            uuid.UUID(str(recipient_uuid))
        except ValueError:
            return False
        else:
            return True

    # 3-32 ASCII letters/digits/underscores, a dot, then 2-9 ASCII digits that
    # aren't all zeros
    _USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,32}\.(?!0+$)[0-9]{2,9}")

    def _is_username(self, recipient_username: str) -> bool:
        """
        Check if username has correct format, as described in
        https://support.signal.org/hc/en-us/articles/6712070553754-Phone-Number-Privacy-and-Usernames#username_req
        Additionally, cannot have more than 9 digits and the digits cannot be 00.
        """
        return self._USERNAME_PATTERN.fullmatch(recipient_username) is not None
