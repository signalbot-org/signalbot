import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from signalbot import SignalBot
from signalbot._client import SignalAPI

SIGNAL_SERVICE = "127.0.0.1:8080"
PHONE_NUMBER = "+49123456789"
GROUP_ID = "group.OyZzqio1xDmYiLsQ1VsqRcUFOU4tK2TcECmYt2KeozHJwglMBHAPS7jlkrm="
GROUP_INTERNAL_ID = "Mg8LQTdaZJs8+LJCrtQgblqHx+xI2dX9JJ8hVA2kqt8="

BOT_CONFIG = {
    "signal_service": SIGNAL_SERVICE,
    "phone_number": PHONE_NUMBER,
    "storage": {"type": "in-memory"},
}


@pytest_asyncio.fixture
async def signal_api() -> AsyncIterator[SignalAPI]:
    api = SignalAPI(SIGNAL_SERVICE, PHONE_NUMBER)
    yield api
    await api.close()


@pytest_asyncio.fixture
async def signal_bot() -> AsyncIterator[SignalBot]:
    bot = SignalBot(BOT_CONFIG)
    yield bot
    await bot.close()


@pytest.fixture
def standalone_signal_bot() -> Iterator[SignalBot]:
    """A bot built outside any running loop, so it owns (and this fixture
    closes) a fresh event loop: for driving `start()`'s `run_forever()`."""
    bot = SignalBot(BOT_CONFIG)
    yield bot
    asyncio.set_event_loop(None)
    bot._event_loop.close()
