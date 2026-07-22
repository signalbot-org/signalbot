# Bot config

## Main configuration

The configuration of the bot can be specified in several ways.

### Config

Create a [Config][signalbot.Config] instance:

```python
from signalbot import SignalBot, Config, ConnectionMode

config = Config(
    signal_service="http://localhost:8080",
    phone_number="+1234567890",
)

bot = SignalBot(config)
bot.start()
```

### Dictionary

Create a python dictionary:

```python
from signalbot import SignalBot, Config

config = {
    "signal_service": "http://localhost:8080",
    "phone_number": "+1234567890",
}

bot = SignalBot(config)
bot.start()
```

### Yaml file

Create a YAML configuration file:

```yaml title="config.yml"
signal_service: "http://localhost:8080"
phone_number: "+1234567890"
```

Then load it:

```python
from signalbot import SignalBot

bot = SignalBot("config.yml")
bot.start()
```

### Json file

Create a JSON configuration file:

```json title="config.json"
{
	"signal_service": "http://localhost:8080",
	"phone_number": "+1234567890"
}
```

Then load it:

```python
from signalbot import SignalBot

bot = SignalBot("config.json")
bot.start()
```

## Storage type options

There are also several storage backends that can be used to handle data persistance.

### In-memory

Stores data in memory only.
Data is lost when the bot restarts.
Useful for development and testing.

```yaml title="config.yml"
signal_service: "http://localhost:8080"
phone_number: "+1234567890"
storage:
  type: "in-memory"
```

### SQLite

Persists data to a local SQLite database.
See the [SQLiteStorage][signalbot.storage.SQLiteStorage] API reference for details.

```yaml title="config.yml"
signal_service: "http://localhost:8080"
phone_number: "+1234567890"
storage:
  type: "sqlite"
  sqlite_db: "./data/bot.db"
```

### Redis

Persists data to Redis database.
See the [RedisStorage][signalbot.storage.RedisStorage] API reference for details.

```yaml title="config.yml"
signal_service: "http://localhost:8080"
phone_number: "+1234567890"
storage:
  type: "redis"
  redis_host: "localhost"
  redis_port: 6379
```

## Authentication

Enables usage of an auth-enabled `signal-cli-rest-api` instance (behind a proxy).

### User and password
Username and password based authentication using the [BasicAuth][signalbot.BasicAuth] class.

```python
from signalbot import BasicAuth, Config, ConnectionMode, SignalBot

config = Config(
    signal_service="http://localhost:8080",
    phone_number="+1234567890",
    auth=BasicAuth(username="user", password="password"),
)

bot = SignalBot(config)
bot.start()
```

### Token
Token based authentication using the [BearerAuth][signalbot.BearerAuth] class.

```python
from signalbot import BearerAuth, Config, ConnectionMode, SignalBot

config = Config(
    signal_service="http://localhost:8080",
    phone_number="+1234567890",
    auth=BearerAuth(token="token")
)

bot = SignalBot(config)
bot.start()
```
