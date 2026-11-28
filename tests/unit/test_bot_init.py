from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from signalbot import SignalBotError
from signalbot._bot_init import _build_scheduler, _build_storage, _resolve_auth
from signalbot.auth import BasicAuthentication, BearerAuthentication
from signalbot.bot_config import Config, load_config
from signalbot.storage import RedisStorage, SQLiteStorage
from tests.conftest import PHONE_NUMBER

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

LOGGER = logging.getLogger("test")


def _config(**fields: object) -> Config:
    return load_config({"phone_number": PHONE_NUMBER, **fields})


class TestResolveAuth:
    def test_no_auth(self):
        assert _resolve_auth(_config()) is None

    def test_basic_auth(self):
        config = _config(auth={"type": "basic", "username": "u", "password": "p"})

        auth = _resolve_auth(config)

        assert isinstance(auth, BasicAuthentication)
        assert auth.username == "u"
        assert auth.password == "p"

    def test_bearer_auth(self):
        config = _config(auth={"type": "bearer", "token": "t0ken"})

        auth = _resolve_auth(config)

        assert isinstance(auth, BearerAuthentication)
        assert auth.token == "t0ken"


class TestBuildStorage:
    def test_sqlite(self, tmp_path: Path):
        db = tmp_path / "bot.db"

        storage = _build_storage(_config(storage={"db": str(db)}), LOGGER)

        assert isinstance(storage, SQLiteStorage)
        storage.save("key", "value")
        assert db.exists()

    def test_redis(self, mocker: MockerFixture):
        redis = mocker.patch("redis.Redis")
        config = _config(storage={"host": "redis-host", "port": 6380})

        storage = _build_storage(config, LOGGER)

        assert isinstance(storage, RedisStorage)
        assert redis.call_args.kwargs["host"] == "redis-host"
        assert redis.call_args.kwargs["port"] == 6380

    def test_missing_storage_warns_and_uses_in_memory(
        self, caplog: pytest.LogCaptureFixture
    ):
        with caplog.at_level(logging.WARNING):
            storage = _build_storage(_config(), LOGGER)

        assert isinstance(storage, SQLiteStorage)
        assert "Using in-memory storage" in caplog.text


class TestBuildScheduler:
    def test_scheduler_errors_are_wrapped(self, mocker: MockerFixture):
        # e.g. tzlocal raising ZoneInfoNotFoundError (a LookupError) for a bad TZ
        mocker.patch(
            "signalbot._bot_init.AsyncIOScheduler",
            side_effect=LookupError("No time zone found"),
        )

        with pytest.raises(SignalBotError, match="Could not initialize scheduler"):
            _build_scheduler(mocker.Mock())
