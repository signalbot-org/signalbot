import json
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from signalbot.bot_config import (
    Config,
    InMemoryConfig,
    RedisConfig,
    load_config,
)
from signalbot.client import ConnectionMode


def _connection_mode_representer(dumper: yaml.Dumper, data: ConnectionMode) -> str:
    return dumper.represent_str(data.value)


yaml.add_representer(ConnectionMode, _connection_mode_representer)


class TestLoadConfig:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self._config = Config(
            signal_service="http://localhost:8080",
            phone_number="+1234567890",
        )
        self._dict_config = self._config.model_dump()

    def test_load_config_from_config_object(self):
        loaded = load_config(self._config)
        assert loaded is self._config

    def test_load_config_from_dict(self):
        config = load_config(self._dict_config)
        assert isinstance(config, Config)
        assert config.signal_service == self._config.signal_service
        assert config.phone_number == self._config.phone_number

    def test_load_config_from_dict_with_redis(self):
        self._dict_config["storage"] = {
            "type": "redis",
            "host": "redis_host",
            "port": 6379,
        }
        config = load_config(self._dict_config)
        assert isinstance(config, Config)
        assert isinstance(config.storage, RedisConfig)
        assert config.storage.host == "redis_host"
        assert config.storage.password is None

    def test_load_config_from_dict_with_redis_password(self):
        self._dict_config["storage"] = {
            "type": "redis",
            "host": "redis_host",
            "port": 6379,
            "password": "secret",
        }
        config = load_config(self._dict_config)
        assert isinstance(config, Config)
        assert isinstance(config.storage, RedisConfig)
        assert config.storage.password == "secret"

    @pytest.mark.parametrize("storage", [{}, {"type": "in-memory"}])
    def test_load_config_from_dict_with_in_memory(self, storage: dict):
        self._dict_config["storage"] = storage
        config = load_config(self._dict_config)
        assert isinstance(config.storage, InMemoryConfig)

    @pytest.mark.parametrize(
        "storage",
        [
            {"host": "redis_host"},
            {"database": "bot.db"},
        ],
    )
    def test_load_config_invalid_storage_is_not_in_memory(self, storage: dict):
        self._dict_config["storage"] = storage
        with pytest.raises(ValidationError):
            load_config(self._dict_config)

    def test_load_config_from_json_file(self):
        self._config.retry_interval = 3
        self._config.download_attachments = False

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self._config.model_dump(), f)
            temp_path = Path(f.name)
        try:
            config = load_config(temp_path)
            assert isinstance(config, Config)
            assert config.signal_service == self._config.signal_service
            assert config.phone_number == self._config.phone_number
            assert config.retry_interval == self._config.retry_interval
            assert config.download_attachments == self._config.download_attachments
        finally:
            temp_path.unlink()

    def test_load_config_from_yaml_file(self):
        self._config.retry_interval = 2

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(self._config.model_dump(), f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert isinstance(config, Config)
            assert config.signal_service == self._config.signal_service
            assert config.phone_number == self._config.phone_number
            assert config.retry_interval == self._config.retry_interval
        finally:
            Path(temp_path).unlink()
