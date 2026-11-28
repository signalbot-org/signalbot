from pytest_mock import MockerFixture

from signalbot._client.base import SessionManager


async def test_session_is_created_once_and_reused(mocker: MockerFixture):
    session_cls = mocker.patch("aiohttp.ClientSession")
    sessions = SessionManager()

    first = await sessions.get()
    second = await sessions.get()

    assert first is second
    session_cls.assert_called_once_with()


async def test_close_closes_the_session_and_a_new_one_is_created_after(
    mocker: MockerFixture,
):
    session_cls = mocker.patch("aiohttp.ClientSession")
    close = session_cls.return_value.close = mocker.AsyncMock()
    sessions = SessionManager()
    await sessions.get()

    await sessions.close()
    await sessions.close()  # closing twice is a no-op

    close.assert_awaited_once()
    await sessions.get()
    assert session_cls.call_count == 2
