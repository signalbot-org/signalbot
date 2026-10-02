---
title: How it works
---

Signalbot moves messages in two directions: **incoming** messages arrive over a websocket and are
routed to your code, **outgoing** messages are sent by your code through an HTTP API. This page
shows how the pieces fit together.

## Architecture

### Incoming

```mermaid
%%{init: {"flowchart": {"useMaxWidth": false}}}%%
flowchart LR
    WS(["signal-cli-rest-api<br/>websocket"]) --> Parse["parse()"]
    Parse --> Queue[["dispatch queue"]]
    Queue --> Handler["Handler.handle_xxx()"]
    Handler --> Context(["Context"])
```

### Outgoing

```mermaid
%%{init: {"flowchart": {"useMaxWidth": false}}}%%
flowchart LR
    Call(["context.send(), .react(), ..."]) --> Actions["*Actions"]
    Actions --> Client["HTTP client"]
    Client --> HTTP(["signal-cli-rest-api<br/>HTTP endpoint"])
```

- **Incoming**: The internal pipeline reads the websocket, an internal `parse()` turns the raw JSON into a
  [`ReceivedMessage`][signalbot.messages.ReceivedMessage], dispatches it to the matching
  `Handler` and [`Context`][signalbot.context.Context] subclass before
  your `handle_xxx` method runs.
- **Outgoing**: calling a method on `context` (or directly on `bot.messages` / `bot.reactions` /
  ...) resolves the recipient, builds a request object, and sends it through an internal HTTP client to `signal-cli-rest-api`.

## Registration

Before any of this runs, handlers need to be registered with the bot — typically once at startup,
e.g. `bot.register(PingHandler())`. The `bot.register()` just stores the handler and its filters;
nothing is invoked yet. From then on, every incoming message is checked against each registered
handler's filters and trigger decorator (`@text_triggered`, `@regex_triggered`,
`@reaction_triggered`), and every handler that matches is invoked with a fresh `Context`.
Registration is the opening step of the walk-through below (steps 1-2).

### Exclusive handlers

By default every matching handler runs, so a handler without a trigger also sees the messages
another handler already answered. Registering handlers with a `priority` makes them exclusive: of
the exclusive handlers that match a message, only the one with the highest priority runs, the first
registered one on ties. Handlers without a priority still run alongside it.

```python
bot.register(LogHandler())  # no trigger, not exclusive: every message
bot.register(PingHandler(), priority=1)  # @text_triggered("!ping")
bot.register(EchoHandler(), priority=0)  # no trigger: everything that isn't !ping
```

Here `!ping` runs `LogHandler` and `PingHandler`, and any other message runs `LogHandler` and
`EchoHandler`. The consumers run the selected handlers concurrently, so don't rely on one finishing
before another starts.

Exclusivity is decided before any handler runs, from the contact and group filters, the `f` filter
and the trigger decorators. A handler that matches but then does nothing in `handle_xxx` still
counts as having handled the message.

See the [handler priorities example](examples/05_priority_bot.md) for a complete bot.

## Following one message end to end

Take a bot with a single handler:

```python
class PingHandler(DataMessageHandler):
    @text_triggered("!ping")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        await context.send(SendMessage(text="pong"))
```

```mermaid
%%{init: {"sequence": {"useMaxWidth": false}}}%%
sequenceDiagram
    participant Author as Bot author code
    participant Bot as SignalBot
    participant API as signal-cli-rest-api
    participant Pipeline as MessagePipeline
    participant Handler as PingHandler
    participant Context as DataMessageContext

    Author->>Bot: bot.register(PingHandler())
    Bot->>Pipeline: store handler + filters
    Note over Pipeline: bot.start() → resolve_handlers()

    API-->>Pipeline: websocket push: raw "!ping" envelope
    Pipeline->>Pipeline: parse() → DataMessage
    Pipeline->>Pipeline: filters and @text_triggered("!ping") match? dispatch lookup
    Pipeline->>Handler: handle_data_message(DataMessageContext(bot, message))
    Handler->>Context: context.send(SendMessage(text="pong"))
    Context->>Bot: bot.messages.send(message, recipient)
    Bot-->>API: HTTP POST /v2/send
    API-->>Author: "pong" delivered to the chat
```

Every incoming message type has its own `Handler`/`Context` pair and dispatch entry (see the table
in [Extending signalbot](06_extending.md#new-incoming-message)) — this walk-through uses
`DataMessage` because it's the most common case, but reactions, typing indicators, remote deletes,
and group updates all follow the same shape.
