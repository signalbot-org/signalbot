
Signalbot uses [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) to communicate with Signal.
The first step is to set it up.
Then signalbot can run in its own python environment.

It is also possible to mock having signal-cli-rest-api running.
Check out how in the [mock_chat section](#mock-chat).

## Setup signal-cli-rest-api

1. Install [docker](https://www.docker.com)

1. Run [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) in `normal` mode.
    ```bash
    docker run -p 8080:8080 \
        -v $(pwd)/signal-cli-config:/home/.local/share/signal-cli \
        -e 'MODE=normal' bbernhard/signal-cli-rest-api:latest
    ```

2. Open http://127.0.0.1:8080/v1/qrcodelink?device_name=local to link your account with the signal-cli-rest-api server

3. In your Signal app, open settings and scan the QR code.
The server can now receive and send messages.
The access key will be stored in `$(PWD)/signal-cli-config`.

4. Stop the container and start it again in `json-rpc` mode.
    ```bash
    docker run -p 8080:8080 \
        -v $(pwd)/signal-cli-config:/home/.local/share/signal-cli \
        -e 'MODE=json-rpc' bbernhard/signal-cli-rest-api:latest
    ```

5. The logs should show something like this.
Confirm that the server is running in the correct mode by visiting http://127.0.0.1:8080/v1/about.
    ```
    ...
    time="2022-03-07T13:02:22Z" level=info msg="Found number +491234567890 and added it to jsonrpc2.yml"
    ...
    time="2022-03-07T13:02:24Z" level=info msg="Started Signal Messenger REST API"
    ```


## Setup signalbot

1. Install `signalbot` in your venv of choice.
    ```bash
    pip install signalbot
    ```

2. Save the code below as `bot.py`.

    ```python
    --8<-- "examples/simple_bot.py"
    ```

6. Run the `bot.py` script.

    Pass the following environment variables to make the example run:

    - `SIGNAL_SERVICE`: Address of the signal service without protocol
    - `PHONE_NUMBER`: Phone number of the bot

    ```bash
    export SIGNAL_SERVICE="127.0.0.1:8080"
    export PHONE_NUMBER="+49123456789"
    python bot.py
    ```

    By default, `SignalBot` starts with `HTTPS/WSS` and will fallback to `HTTP/WS` if needed.
    This behaviour can be changed by setting the `connection_mode` in the [Config][signalbot.Config] argument of the bot.

7. The logs should indicate that one "producer" and three "consumers" have started.
The producer checks for new messages sent to the linked account using a web socket connection.
It creates a task for every registered command and the consumers work off the tasks.
If your bot has many blocking function calls, adjust the number of consumers such that the bot stays reactive.
    ```
    <date> signalbot [WARNING] - __init__ - [Bot] Could not initialize Redis and no SQLite DB name was given. In-memory storage will be used. Restarting will delete the storage! Add storage: {'type': 'in-memory'} to the config to silence this error.
    <date> signalbot [INFO] - _detect_groups - [Bot] 3 groups detected
    <date> signalbot [INFO] - _produce - [Bot] Producer #1 started
    <date> signalbot [INFO] - _consume - [Bot] Consumer #1 started
    <date> signalbot [INFO] - _consume - [Bot] Consumer #2 started
    <date> signalbot [INFO] - _consume - [Bot] Consumer #3 started
    ```

8. Send the message `Ping` to the number that the bot is listening to.
The bot (i.e. the linked account) should respond with a `Pong`.
Confirm that the bot received a raw message, that the consumer worked on the message and that a new message has been sent.
    ```
    <date> signalbot [INFO] - _produce - [Raw Message] {"envelope": <raw message dictionary>}
    <date> signalbot [INFO] - _consume_new_item - [Bot] Consumer #2 got new job in 0.00046 seconds
    <date> signalbot [INFO] - _produce - [Raw Message] {"envelope": <raw message dictionary>}
    <date> signalbot [INFO] - send - [Bot] New message 1760797696983 sent:
    Pong
    ```
9. Check the other examples in the [examples section](examples/api_overview.md).


## Mock chat
You can mock receiving and sending messages to speed up development time.
To do so, you can use [signalbot.utils.ChatTestCase](https://github.com/signalbot-org/signalbot/blob/a543f8a967c81325bc83035f68f23561556c11a6/src/signalbot/utils/chat_testing.py#L48) which sets up a "skeleton" bot.
Then, you can send messages using the [@mock_chat](https://github.com/signalbot-org/signalbot/blob/a543f8a967c81325bc83035f68f23561556c11a6/src/signalbot/utils/chat_testing.py#L14) decorator.
You can find an example implementation in [tests/test_chat.py](https://github.com/signalbot-org/signalbot/blob/main/tests/test_chat.py).
