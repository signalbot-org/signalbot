from __future__ import annotations

try:  # noqa: SIM105
    import redis
except ModuleNotFoundError:
    pass

import json
import sqlite3
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class Storage(ABC):
    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    def read(self, key: str) -> Any:  # noqa: ANN401
        pass

    @abstractmethod
    def save(self, key: str, object: Any) -> None:  # noqa: A002, ANN401
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass


class StorageError(Exception):
    pass


class SQLiteStorage(Storage):
    def __init__(self, database: str | Path = ":memory:", **kwargs):  # noqa: ANN003, ANN204
        self._sqlite = sqlite3.connect(database, **kwargs)
        self._sqlite.execute(
            "CREATE TABLE IF NOT EXISTS signalbot (key text unique, value text)",
        )

    def exists(self, key: str) -> bool:
        return self._sqlite.execute(
            "SELECT EXISTS(SELECT 1 FROM signalbot WHERE key = ?)",
            [key],
        ).fetchone()[0]

    def read(self, key: str) -> Any:  # noqa: ANN401
        try:
            result = self._sqlite.execute(
                "SELECT value FROM signalbot WHERE key = ?",
                [key],
            ).fetchone()[0]
            return json.loads(result)
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"SQLite load failed: {e}")  # noqa: B904, EM102, TRY003

    def save(self, key: str, object: Any) -> None:  # noqa: A002, ANN401
        try:
            value = json.dumps(object)
            self._sqlite.execute(
                "INSERT INTO signalbot VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",  # noqa: E501
                [key, value, value],
            )
            self._sqlite.commit()
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"SQLite save failed: {e}")  # noqa: B904, EM102, TRY003

    def delete(self, key: str) -> None:
        try:
            self._sqlite.execute("DELETE FROM signalbot WHERE key = ?", [key])
            self._sqlite.commit()
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"SQLite delete failed: {e}")  # noqa: B904, EM102, TRY003


class RedisStorage(Storage):
    def __init__(self, host: str, port: int, password: str | None = None):  # noqa: ANN204
        self._redis = redis.Redis(host=host, port=port, db=0, password=password)

    def exists(self, key: str) -> bool:
        return self._redis.exists(key)

    def read(self, key: str) -> Any:  # noqa: ANN401
        try:
            result_bytes = self._redis.get(key)
            result_str = result_bytes.decode("utf-8")
            result_dict = json.loads(result_str)
            return result_dict  # noqa: RET504, TRY300
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"Redis load failed: {e}")  # noqa: B904, EM102, TRY003

    def save(self, key: str, object: Any) -> None:  # noqa: A002, ANN401
        try:
            object_str = json.dumps(object)
            self._redis.set(key, object_str)
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"Redis save failed: {e}")  # noqa: B904, EM102, TRY003

    def delete(self, key: str) -> None:
        try:
            self._redis.delete(key)
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"Redis delete failed: {e}")  # noqa: B904, EM102, TRY003
