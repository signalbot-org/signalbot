from __future__ import annotations

from anyio import Path
from pydantic import AliasChoices, BaseModel, Field

from signalbot._generated import GroupLink, UpdateGroupRequest
from signalbot._utils.attachment_base64 import attachment_to_base64
from signalbot._utils.pydantic_anyio_path import PydanticPath
from signalbot.groups.group_permissions import GroupPermissions


class UpdateGroup(BaseModel):
    """The fields to change on a group. If a field is `None`, it is left unchanged."""

    avatar: str | PydanticPath | None = Field(
        default=None,
        description="The new avatar of the group. This can be a Path or a base64 "
        "encoded string of the image content.",
    )
    description: str | None = Field(
        default=None, description="The new description of the group."
    )
    expiration_in_seconds: int | None = Field(
        default=None,
        serialization_alias="expiration_time",
        validation_alias=AliasChoices("expiration_time", "expiration_in_seconds"),
        description="The new expiration time of the group in seconds.",
    )
    group_link: GroupLink | None = Field(
        default=None,
        description="Enable or disable joining the group via group link.",
    )
    name: str | None = Field(default=None, description="The new name of the group.")
    permissions: GroupPermissions | None = Field(
        default=None, description="The new permissions for the group."
    )

    async def to_generated(self) -> UpdateGroupRequest:
        avatar = self.avatar
        base64_avatar = (
            await attachment_to_base64(avatar) if isinstance(avatar, Path) else avatar
        )
        other_fields = self.model_dump(exclude={"avatar"})
        return UpdateGroupRequest(**other_fields, base64_avatar=base64_avatar)
