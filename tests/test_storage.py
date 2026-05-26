import sys
from types import ModuleType
from unittest.mock import MagicMock, patch


def _make_mock_redis_module():
    """Return a fake redis module with a Redis class."""
    mock_redis_mod = ModuleType("redis")
    mock_redis_mod.Redis = MagicMock()
    return mock_redis_mod


class TestRedisStorage:
    def test_init_without_password(self):
        mock_redis_mod = _make_mock_redis_module()
        with patch.dict(sys.modules, {"redis": mock_redis_mod}):
            # Re-import so the module picks up the mocked redis
            import importlib

            import signalbot.storage as storage_mod

            importlib.reload(storage_mod)
            storage_mod.RedisStorage(host="localhost", port=6379)
            mock_redis_mod.Redis.assert_called_once_with(
                host="localhost", port=6379, db=0, password=None
            )

    def test_init_with_password(self):
        mock_redis_mod = _make_mock_redis_module()
        with patch.dict(sys.modules, {"redis": mock_redis_mod}):
            import importlib

            import signalbot.storage as storage_mod

            importlib.reload(storage_mod)
            storage_mod.RedisStorage(host="localhost", port=6379, password="secret")
            mock_redis_mod.Redis.assert_called_once_with(
                host="localhost", port=6379, db=0, password="secret"
            )
