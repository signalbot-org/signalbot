from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from signalbot.api import ConnectionMode


class RedisConfig(BaseModel):
    """
    The configuration for the Redis storage backend.

    Attributes:
        type: The type of storage.
        redis_host: The hostname of the Redis server.
        redis_port: The port number of the Redis server.
        redis_password: The password for Redis authentication. Defaults to `None`.
    """

    type: Literal["redis"] = "redis"
    redis_host: str
    redis_port: int
    redis_password: str | None = None


class SQLiteConfig(BaseModel):
    """
    The configuration for the SQLite storage backend.

    Attributes:
        type: The type of storage.
        sqlite_db: The path to the SQLite database file.
        check_same_thread: Whether to check the same thread when accessing the database.
    """

    type: Literal["sqlite"] = "sqlite"
    sqlite_db: str | Path
    check_same_thread: bool = True


class InMemoryConfig(BaseModel):
    """
    The configuration for the in-memory storage backend.

    Attributes:
        type: The type of storage.
    """

    type: Literal["in-memory"] = "in-memory"


class Config(BaseModel):
    """
    The configuration for SignalBot.

    Attributes:
        signal_service: The URL of the `signal-cli-rest-api` service to connect to.
        phone_number: The phone number of the bot.
        storage: The configuration for the storage backend to use. Defaults to `None`.
        retry_interval: The interval in seconds to wait before retrying a failed
            connection to the signal service.
        download_attachments: Whether to download attachments from messages. Defaults to
            `True`.
        connection_mode: The connection mode to use when connecting to the Signal
            service. Defaults to `ConnectionMode.AUTO`.
    """

    signal_service: str
    phone_number: str

    storage: RedisConfig | SQLiteConfig | InMemoryConfig | None = None
    retry_interval: int = 1
    download_attachments: bool = True
    connection_mode: ConnectionMode = ConnectionMode.AUTO


def load_config(config: Config | Mapping | Path | str) -> Config:
    if isinstance(config, Config):
        return config

    if isinstance(config, Mapping):
        return Config.model_validate(config)

    if isinstance(config, (str, Path)):
        if isinstance(config, str):
            config = Path(config)
        if config.suffix.lower() == ".json":
            with config.open() as f:
                return Config.model_validate_json(f.read())
        if config.suffix.lower() in [".yaml", ".yml"]:
            with config.open() as f:
                data = yaml.safe_load(f)
            return Config.model_validate(data)

    error_msg = f"Invalid config {config}"
    raise ValueError(error_msg)
