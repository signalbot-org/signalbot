---
title: New incoming messages
---

An incoming message is pushed by signal-cli-rest-api over the websocket, parsed by signalbot into a
typed object and dispatched to a handler (see [Architecture](01_architecture.md#incoming)).
Adding support for a new one touches a small, predictable set of files.

The steps below are not exhaustive — some message types need extra plumbing (e.g.
[`GroupUpdate`][signalbot.groups.GroupUpdate] also touches the group registry in
[`src/signalbot/groups/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/groups)) —
so find the closest existing example and follow its shape.

## Naming

Every incoming type follows the same name chain from the wire to the handler. Match it when
adding a new one — `Xxx` (wrapped class) → `XxxHandler` → `XxxContext` → `handle_xxx`
(snake_case of `Xxx`):

| Generated class | Wrapped class                                     | Handler ABC                                                     | Context class                                                  | Handler method         |
| --------------- | ------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------- |
| `DataMessage`   | [`DataMessage`][signalbot.messages.DataMessage]   | [`DataMessageHandler`][signalbot.handlers.DataMessageHandler]   | [`DataMessageContext`][signalbot.context.DataMessageContext]   | `handle_data_message`  |
| `Reaction`      | [`Reaction`][signalbot.reactions.Reaction]        | [`ReactionHandler`][signalbot.handlers.ReactionHandler]         | [`ReactionContext`][signalbot.context.ReactionContext]         | `handle_reaction`      |
| `RemoteDelete`  | [`RemoteDelete`][signalbot.messages.RemoteDelete] | [`RemoteDeleteHandler`][signalbot.handlers.RemoteDeleteHandler] | [`RemoteDeleteContext`][signalbot.context.RemoteDeleteContext] | `handle_remote_delete` |
| `TypingMessage` | [`TypingMessage`][signalbot.messages.TypingMessage] | [`TypingHandler`][signalbot.handlers.TypingHandler]           | [`TypingContext`][signalbot.context.TypingContext]             | `handle_typing`        |
| `GroupInfo`     | [`GroupUpdate`][signalbot.groups.GroupUpdate]     | [`GroupUpdateHandler`][signalbot.handlers.GroupUpdateHandler]   | [`GroupUpdateContext`][signalbot.context.GroupUpdateContext]   | `handle_group_update`  |

## Steps

1. **Get a message envelope.** Set a breakpoint in `_parse_main_messages`,
   `_parse_sync_messages`, or `_parse_data_message_variant` in
   [`src/signalbot/messages/parser.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/messages/parser.py)
   — i.e. on the already-validated `message_envelope: MessageEnvelope` object.
   Trigger the message from another Signal client so that it is received by the bot.

2. **Identify the relevant envelope fields.** Check whether the fields exists and are already covered by the
   generated `_generated.receive` models
   ([`src/signalbot/_generated/receive/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/_generated/receive)).
   Decide whether this is a genuinely new type or a variant of `data_message`/`sync_message` — compare
   with `_parse_data_message_variant` in
   [`parser.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/messages/parser.py),
   which already branches on the `reaction`/`remote_delete`/group-update sub-fields of a data message.
   If a field is missing from the generated models, it is missing from upstream — get it added there
   and regenerate the models, as described in
   [New signal-cli-rest-api version](04_new_signal_cli_rest_api.md#generated-models).

3. **Write the parsed message class** with a `from_message_envelope(...)` classmethod, following an
   existing example —
   [`src/signalbot/messages/typing_message.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/messages/typing_message.py)
   for a simple case, or
   [`src/signalbot/reactions/reaction.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/reactions/reaction.py)
   for one that reaches back into the envelope's nested data. Subclass
   [`BaseMessage`][signalbot.events.BaseMessage] or
   [`BaseMessageWithGroup`][signalbot.events.BaseMessageWithGroup] as appropriate.

4. **Wrap any nested `_generated` types your class exposes.** No `signalbot._generated` type may appear
   on the public API, directly or nested inside a field —
   [`tests/unit/test_public_api_surface.py`](https://github.com/signalbot-org/signalbot/blob/main/tests/unit/test_public_api_surface.py)
   will fail your PR if you skip it. Follow the rules in
   [Wrapped types](04_new_signal_cli_rest_api.md#wrapped-types) for
   each generated type your class reaches.

5. **Wire it into the parser.** Add a branch in `_parse_main_messages` and/or `_parse_sync_messages` in
   [`parser.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/messages/parser.py),
   and extend the [`ReceivedMessage`][signalbot.messages.ReceivedMessage] type
   alias.

6. **Write a [`Context`][signalbot.context.Context] class** in
   [`src/signalbot/context/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/context)
   (pattern:
   [`TypingContext`][signalbot.context.TypingContext] in
   [`typing_context.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/context/typing_context.py)),
   and a `Handler` ABC in
   [`src/signalbot/handlers.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/handlers.py)
   (pattern: [`TypingHandler`][signalbot.handlers.TypingHandler]) with one
   abstract `handle_xxx(self, context: ...)` method.

7. **Register the dispatch.** Add an entry to `_MESSAGE_DISPATCH` in
   [`src/signalbot/_pipeline.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/_pipeline.py)
   mapping your new class to `(YourHandler, YourContext, "handle_xxx")`. This is the one place that
   ties parsing to dispatch — nothing reaches a handler without an entry here.

8. **(Optional) Write a trigger decorator** in
   [`handlers.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/handlers.py) if
   handlers for this type commonly filter on a field — follow
   [`reaction_triggered`][signalbot.handlers.reaction_triggered] as the smallest
   example: it checks `isinstance(context, YourContext)`, filters, and calls through.

9. **Write a test.** Follow
   [`tests/unit/messages/test_message.py`](https://github.com/signalbot-org/signalbot/blob/main/tests/unit/messages/test_message.py)'s
   pattern: build the raw envelope JSON inline (this repo doesn't use fixture files for envelopes), call
   [`parse(signal, raw_json_str)`][signalbot.messages.parse], and assert
   `isinstance(result, YourClass)` plus field values. Add dispatch coverage in
   [`tests/unit/test_pipeline.py`](https://github.com/signalbot-org/signalbot/blob/main/tests/unit/test_pipeline.py)
   if relevant.

10. **Write an example handler** under
   [`examples/handlers/`](https://github.com/signalbot-org/signalbot/tree/main/examples/handlers) or
   [`examples/commands/`](https://github.com/signalbot-org/signalbot/tree/main/examples/commands),
   following
   [`examples/commands/reaction.py`](https://github.com/signalbot-org/signalbot/blob/main/examples/commands/reaction.py)
   (`@`[`text_triggered`][signalbot.handlers.text_triggered] +
   [`context.react(...)`][signalbot.context.DataMessageContext.react]) or
   [`examples/handlers/reaction.py`](https://github.com/signalbot-org/signalbot/blob/main/examples/handlers/reaction.py)
   ([`ReactionHandler`][signalbot.handlers.ReactionHandler] +
   `@`[`reaction_triggered`][signalbot.handlers.reaction_triggered]) as templates,
   and register it in one of the example bots
   ([`examples/simple_bot.py`](https://github.com/signalbot-org/signalbot/blob/main/examples/simple_bot.py) /
   [`examples/bot.py`](https://github.com/signalbot-org/signalbot/blob/main/examples/bot.py)) with
   [`bot.register(YourHandler())`][signalbot.bot.SignalBot.register].

11. **Update the docs.** Add the new type to the message types table in
   [How it works](../02_concepts.md#message-types), and add a new page under
   [`docs/examples/`](https://github.com/signalbot-org/signalbot/tree/main/docs/examples), under the
   section of the bot that you are editing.
