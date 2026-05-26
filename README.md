# Signal Bot Framework

Python package to build your own Signal bots.

## Getting Started

Install it with `pip install signalbot`.

Below you can find a minimal example on how to use the package.
Save it as `bot.py`.
There is also a bigger example in the [example folder](https://github.com/filipre/signalbot/tree/master/example).

```python
import os
import logging
from signalbot import SignalBot, Command, Context, triggered, enable_console_logging


class PingCommand(Command):
    @triggered("Ping")
    async def handle(self, c: Context) -> None:
        await c.send("Pong")


if __name__ == "__main__":
    enable_console_logging(logging.INFO)

    bot = SignalBot({
        "signal_service": os.environ["SIGNAL_SERVICE"],
        "phone_number": os.environ["PHONE_NUMBER"]
    })
    bot.register(PingCommand()) # Run the command for all contacts and groups
    bot.start()
```

Please check out https://github.com/bbernhard/signal-cli-rest-api#getting-started to learn about [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) and [signal-cli](https://github.com/AsamK/signal-cli). A good first step is to make the example above work.

1. Run signal-cli-rest-api in `normal` mode first.
```bash
docker run -p 8080:8080 \
    -v $(pwd)/signal-cli-config:/home/.local/share/signal-cli \
    -e 'MODE=normal' bbernhard/signal-cli-rest-api:latest
```

2. Open http://127.0.0.1:8080/v1/qrcodelink?device_name=local to link your account with the signal-cli-rest-api server

3. In your Signal app, open settings and scan the QR code. The server can now receive and send messages. The access key will be stored in `$(PWD)/signal-cli-config`.

4. Restart the server in `json-rpc` mode.
```bash
docker run -p 8080:8080 \
    -v $(pwd)/signal-cli-config:/home/.local/share/signal-cli \
    -e 'MODE=json-rpc' bbernhard/signal-cli-rest-api:latest
```

5. The logs should show something like this. You can also confirm that the server is running in the correct mode by visiting http://127.0.0.1:8080/v1/about.
```
...
time="2022-03-07T13:02:22Z" level=info msg="Found number +491234567890 and added it to jsonrpc2.yml"
...
time="2022-03-07T13:02:24Z" level=info msg="Started Signal Messenger REST API"
```

6. Install `signalbot` and start your python script. You need to pass following environment variables to make the example run:
- `SIGNAL_SERVICE`: Address of the signal service without protocol, e.g. `127.0.0.1:8080`
- `PHONE_NUMBER`: Phone number of the bot, e.g. `+49123456789`

```bash
export SIGNAL_SERVICE="127.0.0.1:8080"
export PHONE_NUMBER="+49123456789"
pip install signalbot
python bot.py
```

7. The logs should indicate that one "producer" and three "consumers" have started. The producer checks for new messages sent to the linked account using a web socket connection. It creates a task for every registered command and the consumers work off the tasks. In case you are working with many blocking function calls, you may need to adjust the number of consumers such that the bot stays reactive.
```
<date> signalbot [WARNING] - __init__ - [Bot] Could not initialize Redis and no SQLite DB name was given. In-memory storage will be used. Restarting will delete the storage! Add storage: {'type': 'in-memory'} to the config to silence this error.
<date> signalbot [INFO] - _detect_groups - [Bot] 3 groups detected
<date> signalbot [INFO] - _produce - [Bot] Producer #1 started
<date> signalbot [INFO] - _consume - [Bot] Consumer #1 started
<date> signalbot [INFO] - _consume - [Bot] Consumer #2 started
<date> signalbot [INFO] - _consume - [Bot] Consumer #3 started
```

8. Send the message `Ping` (case sensitive) to the number that the bot is listening to. The bot (i.e. the linked account) should respond with a `Pong`. Confirm that the bot received a raw message, that the consumer worked on the message and that a new message has been sent.
```
<date> signalbot [INFO] - _produce - [Raw Message] {"envelope": <raw message dictionary>}
<date> signalbot [INFO] - _consume_new_item - [Bot] Consumer #2 got new job in 0.00046 seconds
<date> signalbot [INFO] - _produce - [Raw Message] {"envelope": <raw message dictionary>}
<date> signalbot [INFO] - send - [Bot] New message 1760797696983 sent:
Pong
```

## Classes and API

*Documentation work in progress. Feel free to open an issue for questions.*

The package provides methods to easily listen for incoming messages and responding or reacting on them. It also provides a class to develop new commands which then can be registered within the bot.

### Signalbot

- `bot.register(command, contacts=True, groups=True)`: Register a new command, listen in all contacts and groups, same as `bot.register(command)`
- `bot.register(command, contacts=False, groups=["Hello World"])`: Only listen in the "Hello World" group
- `bot.register(command, contacts=["+49123456789"], groups=False)`: Only respond to one contact
- `bot.start()`: Start the bot
- `bot.send(receiver, text)`: Send a new message
- `bot.react(message, emoji)`: React to a message
- `bot.start_typing(receiver)`: Start typing
- `bot.stop_typing(receiver)`: Stop typing
- `bot.send(receiver, text, edit_timestamp=timestamp)`: Edit a previously sent message
- `bot.remote_delete(receiver, timestamp)`: Delete a previously sent message
- `bot.receipt(message, receipt_type)`: Mark a message as read
- `bot.update_group(group_id, avatar, description, expiration, name)`: Change group settings
- `bot.delete_attachment(attachment_filename)`: Delete the local copy of an attachment
- `bot.scheduler`: APScheduler > AsyncIOScheduler, see [here](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html?highlight=AsyncIOScheduler#apscheduler.schedulers.asyncio.AsyncIOScheduler)

### Persistent storage

By default the `bot.storage` is in-memory.
Any changes are lost when the bot is stopped or reseted.
For persistent storage to disk, check the SQLite or Redis storage in `storage.py`.

To use Redis with password authentication, add `redis_password` to the storage config:

```python
config = {
    "storage": {
        "redis_host": "redis",
        "redis_port": 6379,
        "redis_password": "your_password",
    },
}
```

### Command

To implement your own commands, you need to inherent `Command` and overwrite following methods:

- `setup(self)`: Start any task that requires to send messages already, optional
- `handle(self, c: Context)`: Handle an incoming message. By default, any command will read any incoming message. `Context` can be used to easily send (`c.send(text)`), reply (`c.reply(text)`), react (`c.react(emoji)`), edit (`c.edit(text, timestamp)`) and to type in a group (`c.start_typing()` and `c.stop_typing()`). You can use the `@triggered` decorator to listen for specific commands, the `@regex_triggered` decorator to listen for regular expressions, or you can inspect `c.message.text`.

### Logging

The logger name for the library is `"signalbot"`.
It does not have any handlers attached, for convenience the `enable_console_logging(level)` function is provided.

### Unit Testing

*Note: deprecated, the plan is to switch to pytest eventually*

The tests can be executed with

```bash
poetry run python -m unittest discover --start-directory ./tests
```

In many cases, we can mock receiving and sending messages to speed up development time. To do so, you can use `signalbot.utils.ChatTestCase` which sets up a "skeleton" bot. Then, you can send messages using the `@chat` decorator in `signalbot.utils` like this:
```python
class PingChatTest(ChatTestCase):
    def setUp(self):
        # initialize self.singal_bot
        super().setUp()
        # all that is left to do is to register the commands that you want to test
        self.signal_bot.register(PingCommand())

    @chat("ping", "ping")
    async def test_ping(self, query, replies, reactions):
        self.assertEqual(replies.call_count, 2)
        for recipient, message in replies.results():
            self.assertEqual(recipient, ChatTestCase.group_secret)
            self.assertEqual(message, "pong")
```
In `signalbot.utils`, check out `ReceiveMessagesMock`, `SendMessagesMock` and `ReactMessageMock` to learn more about their API.

## Troubleshooting

- Check that you linked your account successfully
- Is the API server running in `json-rpc` mode?
- Can you receive messages using `wscat` (websockets) and send messages using `curl` (http)?
- Do you see incoming messages in the API logs?
- Do you see the "raw" messages in the bot's logs?
- Do you see "consumers" picking up jobs and handling incoming messages?
- Do you see the response in the bot's logs?

## Local development

```bash
poetry install
poetry run pre-commit install
```

## Real world bot examples

There are many real world examples of bot implementations using this library.
Check the whole list at https://github.com/filipre/signalbot/network/dependents

## Other Projects

There are a few other projects similar to this one. You may want to check them out and see if they fit your needs.

|Project|Description|Language|Maintained|
|-------|:---------:|:------:|:------:|
|https://github.com/AsamK/signal-cli|A CLI and D-Bus interface for Signal|Java|✅|
|https://github.com/bbernhard/pysignalclirestapi|Python Wrapper for REST API|Python|✅|
|https://github.com/bbernhard/signal-cli-rest-api|REST API Wrapper for Signal CLI|Go|✅|
|https://github.com/signal-bot/signal-bot|Bot Framework using Signal CLI|Python|❌|
|https://github.com/signalapp/libsignal-service-java|Signal Library|Java|❌|
|https://github.com/aaronetz/signal-bot|Bot Framework|Java|❌|
|https://gitlab.com/signald/signald|A socket interface for Signal|Java|❌|
|https://codeberg.org/lazlo/semaphore|signald Library / Bot Framework|Python|❌|
|https://git.sr.ht/~nicoco/aiosignald|signald Library / Bot Framework|Python|❌|
|https://gitlab.com/stavros/pysignald|signald Library / Bot Framework|Python|❌|
|https://gitlab.com/signald/signald-go|signald Library|Go|❌|
