# Signal Bot Framework

[![PyPI Downloads](https://img.shields.io/pypi/dm/signalbot?label=Downloads
)](https://pypistats.org/packages/signalbot)
[![Version](https://img.shields.io/pypi/v/signalbot?logo=python&logoColor=white&label=PyPI)](https://pypi.python.org/pypi/signalbot)
[![License](https://img.shields.io/pypi/l/signalbot.svg?label=License)](https://pypi.python.org/pypi/signalbot)
[![CI](https://github.com/signalbot-org/signalbot/actions/workflows/ci.yaml/badge.svg)](https://github.com/signalbot-org/signalbot/actions/workflows/ci.yaml)
[![codecov](https://codecov.io/gh/signalbot-org/signalbot/graph/badge.svg?token=N3ZA5MTU2P)](https://codecov.io/gh/signalbot-org/signalbot)

Python package to build your own Signal bots.

> [!IMPORTANT]
> Signalbot v2 is being developed at  https://github.com/signalbot-org/signalbot/tree/v2.0.
> Feedback on the direction is welcomed in https://github.com/signalbot-org/signalbot/issues/234

## Installation

See the [getting started](https://signalbot-org.github.io/signalbot/latest/getting_started) section in the documentation.

## Minimal bot

This is what a minimal bot using signalbot looks like:

```python
import os
import logging
from signalbot import SignalBot, Config, Command, Context, triggered, enable_console_logging


class PingCommand(Command):
    @triggered("Ping")
    async def handle(self, context: Context) -> None:
        await context.send("Pong")


if __name__ == "__main__":
    enable_console_logging(logging.INFO)

    bot = SignalBot(
        Config(
            signal_service=os.environ["SIGNAL_SERVICE"],
            phone_number=os.environ["PHONE_NUMBER"],
        )
    )
    bot.register(PingCommand()) # Run the command for all contacts and groups
    bot.start()
```

## Help

See the [documentation](https://signalbot-org.github.io/signalbot/) for more details.
