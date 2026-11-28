import asyncio
import signal

import pytest
from packaging.version import InvalidVersion
from pytest_mock import MockerFixture

from signalbot import MIN_SIGNAL_CLI_REST_API_VERSION, ConnectionMode, SignalBot
from tests.conftest import BOT_CONFIG
from tests.unit.conftest import TestCommon


class TestSignalApiProtocolConfig:
    # Async so `SignalBot` reuses pytest's running loop instead of creating
    # (and leaking) a new one
    @pytest.mark.parametrize(
        ("overrides", "expected_mode", "use_https"),
        [
            ({}, ConnectionMode.AUTO, True),
            (
                {"connection_mode": ConnectionMode.HTTP_ONLY},
                ConnectionMode.HTTP_ONLY,
                False,
            ),
            (
                {"connection_mode": ConnectionMode.HTTPS_ONLY},
                ConnectionMode.HTTPS_ONLY,
                True,
            ),
        ],
    )
    async def test_connection_mode(
        self, *, overrides: dict, expected_mode: ConnectionMode, use_https: bool
    ):
        signal_bot = SignalBot({**BOT_CONFIG, **overrides})

        assert signal_bot._signal.connection_mode == expected_mode
        assert signal_bot._signal._uris.use_https is use_https


class TestSignalApiVersionCheck(TestCommon):
    async def test_new_version_is_okay(self, mocker: MockerFixture):
        about_mock = mocker.patch.object(
            self.signal_bot.general,
            "about",
            new_callable=mocker.AsyncMock,
        )
        about_mock.return_value = mocker.Mock(
            version=str(MIN_SIGNAL_CLI_REST_API_VERSION)
        )

        await self.signal_bot._check_signal_cli_rest_api_version()

        about_mock.return_value = mocker.Mock(
            version=f"{MIN_SIGNAL_CLI_REST_API_VERSION.major + 1}.0.0"
        )
        await self.signal_bot._check_signal_cli_rest_api_version()

    async def test_unset_version(self, mocker: MockerFixture):
        about_mock = mocker.patch.object(
            self.signal_bot.general,
            "about",
            new_callable=mocker.AsyncMock,
        )
        about_mock.return_value = mocker.Mock(version="unset")

        await self.signal_bot._check_signal_cli_rest_api_version()

    async def test_old_version_raises_runtime_error(self, mocker: MockerFixture):
        about_mock = mocker.patch.object(
            self.signal_bot.general,
            "about",
            new_callable=mocker.AsyncMock,
        )
        prev_version = f"{MIN_SIGNAL_CLI_REST_API_VERSION.major}."
        prev_version += f"{MIN_SIGNAL_CLI_REST_API_VERSION.minor - 1}.0"
        about_mock.return_value = mocker.Mock(version=prev_version)

        with pytest.raises(
            RuntimeError, match="Incompatible signal-cli-rest-api version"
        ):
            await self.signal_bot._check_signal_cli_rest_api_version()

    async def test_invalid_version(self, mocker: MockerFixture):
        about_mock = mocker.patch.object(
            self.signal_bot.general,
            "about",
            new_callable=mocker.AsyncMock,
        )
        about_mock.return_value = mocker.Mock(version="abc")

        with pytest.raises(InvalidVersion, match="Invalid version: 'abc'"):
            await self.signal_bot._check_signal_cli_rest_api_version()


class TestSignalApiModeCheck(TestCommon):
    async def test_json_rpc_mode_is_okay(self, mocker: MockerFixture):
        mocker.patch.object(
            self.signal_bot.general,
            "about",
            new_callable=mocker.AsyncMock,
            return_value=mocker.Mock(mode="json-rpc"),
        )

        await self.signal_bot._check_signal_cli_rest_api_mode()

    async def test_other_mode_raises_runtime_error(self, mocker: MockerFixture):
        mocker.patch.object(
            self.signal_bot.general,
            "about",
            new_callable=mocker.AsyncMock,
            return_value=mocker.Mock(mode="normal"),
        )

        with pytest.raises(RuntimeError, match="found 'normal', expected 'json-rpc'"):
            await self.signal_bot._check_signal_cli_rest_api_mode()


class TestSignalServiceCheck(TestCommon):
    async def test_retries_until_service_is_reachable(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ):
        check = mocker.patch.object(
            self.signal_bot._signal,
            "check_signal_service",
            new_callable=mocker.AsyncMock,
            side_effect=[False, False, True],
        )
        self.signal_bot.config.retry_interval = 0

        await self.signal_bot._check_signal_service()

        assert check.await_count == 3
        assert "Cannot connect to the signal-cli-rest-api service" in caplog.text


class TestLifecycle(TestCommon):
    async def test_start_without_run_forever_initialises_then_starts_pipeline(
        self, mocker: MockerFixture
    ):
        async_init = mocker.patch.object(
            self.signal_bot, "_async_init", new_callable=mocker.AsyncMock
        )
        pipeline_start = mocker.patch.object(
            self.signal_bot._pipeline, "start", new_callable=mocker.AsyncMock
        )

        self.signal_bot.start(run_forever=False)
        await self.signal_bot.wait_until_ready()

        async_init.assert_awaited_once()
        pipeline_start.assert_awaited_once()
        assert not self.signal_bot.scheduler.running


def test_start_runs_loop_until_request_stop(
    mocker: MockerFixture, standalone_signal_bot: SignalBot
):
    """`start()` blocks in `run_forever()` until something requests a stop,
    here the init task itself (standing in for a "shutdown" handler or SIGTERM).
    """
    bot = standalone_signal_bot
    loop = bot._event_loop
    started: list[bool] = []

    async def fake_post_init() -> None:
        started.append(bot.scheduler.running)
        bot.request_stop()

    mocker.patch.object(bot, "_async_post_init", side_effect=fake_post_init)
    pipeline_stop = mocker.spy(bot._pipeline, "stop")
    close = mocker.spy(bot, "close")

    bot.start()
    # apscheduler defers the actual shutdown to the next loop iteration
    loop.run_until_complete(asyncio.sleep(0))

    assert started == [True]
    assert not bot.scheduler.running
    pipeline_stop.assert_awaited_once()
    close.assert_awaited_once()
    # SIGINT/SIGTERM were routed to `request_stop`
    assert loop.remove_signal_handler(signal.SIGINT)
    assert loop.remove_signal_handler(signal.SIGTERM)


def test_stop_without_running_scheduler(standalone_signal_bot: SignalBot):
    bot = standalone_signal_bot

    bot._event_loop.run_until_complete(bot.stop())

    assert not bot.scheduler.running


def test_signal_handlers_are_skipped_where_unsupported(
    mocker: MockerFixture, standalone_signal_bot: SignalBot
):
    add = mocker.patch.object(
        standalone_signal_bot._event_loop,
        "add_signal_handler",
        side_effect=NotImplementedError,
    )

    standalone_signal_bot._install_sigint_sigterm_handlers()

    assert add.call_count == 2
