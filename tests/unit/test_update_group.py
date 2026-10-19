from pathlib import Path as PathlibPath

from anyio import Path as AnyIOPath

from signalbot.groups import UpdateGroup


async def test_update_group_with_base64_avatar():
    # A long base64 string must not be mistaken for a path, opening it fails
    avatar = "cGF5bG9hZA==" * 100

    result = await UpdateGroup(avatar=avatar).to_generated()

    assert result.base64_avatar == avatar


async def test_update_group_with_avatar_path(tmp_path: PathlibPath):
    avatar = tmp_path / "avatar.png"
    avatar.write_text("payload")

    result = await UpdateGroup(avatar=AnyIOPath(avatar)).to_generated()

    assert result.base64_avatar == "cGF5bG9hZA=="
