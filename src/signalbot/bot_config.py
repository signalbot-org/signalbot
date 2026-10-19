from __future__ import annotations

from collections.abc import Mapping
from logging import WARNING
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from signalbot.client import ConnectionMode


class RedisConfig(BaseModel):
    """The configuration for the
    [RedisStorage](storage.md#signalbot.storage.RedisStorage) backend.
    """

    type: Literal["redis"] = Field(
        default="redis", description="The type of storage. Defaults to `redis`."
    )
    host: str = Field(description="The hostname of the Redis server.")
    port: int = Field(description="The port number of the Redis server.")
    password: str | None = Field(
        default=None, description="The password for Redis authentication."
    )


class SQLiteConfig(BaseModel):
    """The configuration for the
    [SQLiteStorage](storage.md#signalbot.storage.SQLiteStorage) backend.
    """

    type: Literal["sqlite"] = Field(
        default="sqlite", description="The type of storage. Defaults to `sqlite`."
    )
    db: str | Path = Field(description="The path to the SQLite database file.")
    check_same_thread: bool = Field(
        default=True,
        description="Whether to check the same thread when accessing the database.",
    )


class InMemoryConfig(BaseModel):
    """The configuration for the in-memory storage backend, which defaults to
    [SQLiteStorage](storage.md#signalbot.storage.SQLiteStorage) with memory storage.
    """

    # Without it, any storage config that is not valid for another backend, e.g. one
    # with a typo, would silently fall back to the in-memory storage
    model_config = ConfigDict(extra="forbid")

    type: Literal["in-memory"] = Field(
        default="in-memory", description="The type of storage. Defaults to `in-memory`."
    )


class BasicAuthConfig(BaseModel):
    """The configuration for username and password based authentication."""

    type: Literal["basic"] = Field(
        default="basic", description="The type of authentication. Defaults to `basic`."
    )
    username: str = Field(description="The username for the authentication.")
    password: str = Field(description="The password used for authentication.")


class BearerAuthConfig(BaseModel):
    """The configuration for token based authentication."""

    type: Literal["bearer"] = Field(
        default="bearer",
        description="The type of authentication. Defaults to `bearer`.",
    )
    token: str = Field(description="The token used for authentication.")


class Config(BaseModel):
    """The configuration for SignalBot."""

    phone_number: str = Field(description="The phone number of the bot.")
    signal_service: str = Field(
        default="localhost:8080",
        description="The URL of the `signal-cli-rest-api` service to connect to, "
        "without protocol.",
    )
    auth: BasicAuthConfig | BearerAuthConfig | None = Field(
        default=None,
        description="The authentication config used for http requests.",
    )
    storage: RedisConfig | SQLiteConfig | InMemoryConfig | None = Field(
        default=None, description="The configuration for the storage backend to use."
    )
    retry_interval: int = Field(
        default=1,
        description="The interval in seconds to wait before retrying a failed "
        "connection to the signal service.",
    )
    download_attachments: bool = Field(
        default=True,
        description="Whether to download attachments from messages.",
    )
    connection_mode: ConnectionMode = Field(
        default=ConnectionMode.AUTO,
        description="The connection mode to use when connecting to the Signal service.",
    )
    logging_level: int = Field(
        default=WARNING, description="The logging level for the bot."
    )


def load_config(config: Config | Mapping | Path | str) -> Config:
    """Coerce a `Config`, mapping, or path to a JSON/YAML file into a `Config`.

    Args:
        config: An already-built `Config`, a mapping of config fields, or a
            path (or path string) to a `.json`, `.yaml`, or `.yml` file.

    Returns:
        The resulting `Config`.

    Raises:
        ValueError: If `config` is a path with an unsupported suffix, or is
            none of the accepted types.
    """
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
