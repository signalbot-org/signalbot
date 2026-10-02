---
title: New outgoing messages
---

An outgoing message starts as a bot author's call and turns into an HTTP request against a
[signal-cli-rest-api](https://bbernhard.github.io/signal-cli-rest-api/) endpoint (see
[Architecture](01_architecture.md#outgoing)). Adding support for a new one touches a small,
predictable set of files.

The steps below are not exhaustive, so find the closest existing action and follow its shape.

## Naming

Every outgoing action follows the same name chain from the wire request to the bot author's
call site. Match it when adding a new one:

| Generated request        | Request class                                       | Actions method                               | Context shortcut                                                                                                                  |
| ------------------------ | --------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `SendMessageV2`          | [`SendMessage`][signalbot.messages.SendMessage]     | `bot.messages.send`                          | [`Context.send`][signalbot.context.Context.send]                                                                                  |
| `RemoteDeleteRequest`    | built inline                                        | `bot.messages.remote_delete`                 | [`DataMessageContext.remote_delete`][signalbot.context.DataMessageContext.remote_delete]                                          |
| `TypingIndicatorRequest` | built inline                                        | `bot.messages.start_typing` / `.stop_typing` | [`Context.start_typing`][signalbot.context.Context.start_typing] / [`Context.stop_typing`][signalbot.context.Context.stop_typing] |
| `SendReactionRequest`    | built inline                                        | `bot.reactions.react`                        | [`DataMessageContext.react`][signalbot.context.DataMessageContext.react]                                                          |
| `Receipt`                | built inline                                        | `bot.receipts.send`                          | [`DataMessageContext.send_receipt`][signalbot.context.DataMessageContext.send_receipt]                                            |
| `UpdateGroupRequest`     | [`UpdateGroup`][signalbot.groups.UpdateGroup]       | `bot.groups.actions.update`                  | [`Context.update_group`][signalbot.context.Context.update_group]                                                                  |
| `CreatePollRequest`      | [`CreatePoll`][signalbot.polls.CreatePoll]          | `bot.polls.create`                           | [`Context.create_poll`][signalbot.context.Context.create_poll]                                                                    |
| `UpdateContactRequest`   | [`UpdateContact`][signalbot.contacts.UpdateContact] | `bot.contacts.update`                        | [`Context.update_contact`][signalbot.context.Context.update_contact]                                                              |

Naming patterns to follow:

- **Generated request → request class drops the `Request` suffix.** `UpdateGroupRequest` →
  `UpdateGroup`, `CreatePollRequest` → `CreatePoll`, `UpdateContactRequest` → `UpdateContact`.
  `SendMessageV2`.
- **Context shortcut = the Actions method's bare verb, unless that verb is already taken.**
  [`Context`][signalbot.context.Context] flattens every domain's actions into one namespace, so
  a verb already used by another action gets qualified with its noun to disambiguate; otherwise
  it stays bare. `remote_delete`, `react`, `start_typing`/`stop_typing` all carry over unchanged
  from their `bot.<noun>.<verb>` call. `send` is already claimed by
  [`Context.send`][signalbot.context.Context.send] (messages), so receipts' `send` becomes
  [`send_receipt`][signalbot.context.DataMessageContext.send_receipt] instead. `update` is used
  by both groups and contacts, so neither gets the bare name — both keep the noun
  (`update_group`, `update_contact`).
- `GroupActions` attaches at `bot.groups.actions`, not directly on the bot — `bot.groups` is
  already the [`GroupRegistry`][signalbot.groups.GroupRegistry] cache, so `GroupActions` nests
  underneath it instead of taking a top-level `bot.<noun>` name of its own.

## Steps

1. **Find the endpoint** in the
   [signal-cli-rest-api Swagger docs](https://bbernhard.github.io/signal-cli-rest-api/) — note its
   HTTP verb, path, and request/response JSON shape.

2. **Find or generate the wire models** in
   [`src/signalbot/_generated/api/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/_generated/api)
   (request) and
   [`src/signalbot/_generated/data/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/_generated/data)
   (response). If the endpoint or shape is missing, it is missing from upstream — get it added there
   and regenerate the models, as described in
   [New signal-cli-rest-api version](04_new_signal_cli_rest_api.md#generated-models).

3. **Write the domain-facing request model** that a bot author actually constructs, in the relevant
   top-level package (e.g. `src/signalbot/polls/`). Pick the shape based on whether every field is
   knowable at construction time:

   - **Straight subclass of the generated request** — `class X(GeneratedXRequest): """..."""` — when
     nothing needs to be filled in later. Narrowing a field to a wrapped type is fine here too, under
     the same rule as for incoming messages (see
     [Wrapped types](04_new_signal_cli_rest_api.md#wrapped-types)):
     additive narrowing is sound, mark it with
     `# pyright: ignore[reportIncompatibleVariableOverride]`.
   - **Standalone `BaseModel` with a `to_generated()` method** when a field the wire format requires
     won't be known until later — most commonly `recipient`/`group_id_or_name`. Don't put it on the
     model as `str | None`; leave it off the model entirely and thread it through as a required
     parameter instead: on `to_generated()` if the wire model needs it (follow
     [`SendMessage`][signalbot.messages.SendMessage] in
     [`send_message.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/messages/send_message.py),
     [`UpdateContact`][signalbot.contacts.UpdateContact], or
     [`CreatePoll`][signalbot.polls.CreatePoll]/[`CreatedPoll`][signalbot.polls.CreatedPoll] in
     [`poll.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/polls/poll.py)),
     or straight onto the `*Actions` method alone if it's only ever used to resolve a separate id and
     never touches the wire model (follow [`UpdateGroup`][signalbot.groups.UpdateGroup] /
     `GroupActions.update`, where `group_id_or_name` resolves to a `group_id` URL path segment and
     never appears in the request body). Either way, a
     [`Context`][signalbot.context.Context] convenience method fills the parameter in from the
     received message.

4. **Add a client method** in the relevant
   [`src/signalbot/_client/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/_client)
   file (or a new file for a new API section): add a URI method on the `*URIs` class (pattern:
   `MessagesURIs.remote_delete_uri()`) and a method on the `*Client` class, **typed to accept the
   generated request model**, that builds the
   payload with `model_dump_json(exclude_none=True, by_alias=True)`, calls
   `self._request(verb, uri, error_cls=..., payload=...)`, and parses the response (pattern:
   `MessagesClient.remote_delete` in
   [`src/signalbot/_client/messages.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/_client/messages.py)).
   Define a dedicated `*Error(`[`SignalAPIError`][signalbot.SignalAPIError]`)` class alongside it.

5. **Expose it on `SignalAPI`** if it's a new
   section
   ([`src/signalbot/_client/signal_api.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/_client/signal_api.py))
   — existing sections (`.messages`, `.reactions`, `.groups`, ...) already route to their client class.

6. **Add a method on the matching `*Actions` class** in
   [`src/signalbot/_actions/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/_actions)
   (pattern:
   [`MessageActions.remote_delete`][signalbot._actions.MessageActions.remote_delete]
   in
   [`src/signalbot/_actions/messages.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/_actions/messages.py)):
   resolve any recipient via `self._recipients.resolve(...)`, convert to the wire request — call
   `.to_generated()` on the domain model if it has one (pattern:
   [`PollActions.create`][signalbot._actions.PollActions.create]), or construct the generated model
   directly for simple cases that never needed a domain wrapper (pattern:
   `MessageActions.remote_delete` building a `RemoteDeleteRequest` inline) — call the client method, log
   via `self._logger.info(...)`, and return a friendly domain-level result if useful (e.g.
   [`SentMessage`][signalbot.messages.SentMessage]).

7. **Wire it up if it's a new Actions class** — instantiate and attach it to
   [`SignalBot`][signalbot.bot.SignalBot] in `SignalBot._init_actions()` in
   [`src/signalbot/bot.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/bot.py)
   next to `self.messages`/`self.reactions`/etc.

8. **Add a [`Context`][signalbot.context.Context] convenience method** in
   [`src/signalbot/context/context.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/context/context.py)
   if handlers should be able to call it directly — follow how
   [`context.react(...)`][signalbot.context.DataMessageContext.react] /
   `context.send(...)` delegate to the Actions layer. This is usually exactly where the deferred
   parameter from step 3 gets filled in, by passing it straight through as an extra argument (e.g.
   `self.bot.polls.create(create_poll_request, received_message.source_or_group_id())`).

9. **Write a test** for the new `Actions` method (mock/stub `SignalAPI`, assert the right client method
   and payload) — check
   [`tests/unit`](https://github.com/signalbot-org/signalbot/tree/main/tests/unit) for the existing
   pattern for `_actions/*` classes.

10. **Write an example** command/handler under
   [`examples/commands/`](https://github.com/signalbot-org/signalbot/tree/main/examples/commands) or
   [`examples/handlers/`](https://github.com/signalbot-org/signalbot/tree/main/examples/handlers) that
   calls the new action (pattern:
   [`examples/commands/reaction.py`](https://github.com/signalbot-org/signalbot/blob/main/examples/commands/reaction.py)),
   registered in one of the example bots.

11. **Add a new page to the docs** under
   [`docs/examples/`](https://github.com/signalbot-org/signalbot/tree/main/docs/examples), under the
   section of the bot that you are editing.
