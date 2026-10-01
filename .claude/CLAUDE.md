# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Signalbot is a Python framework for building Signal bots. It talks to Signal via
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) (run in `json-rpc` mode), receiving
messages over a websocket and sending them over HTTP. This is the `v2.0` branch (v2 rewrite in progress,
pre-release: `version = "2.0.0.dev1"`); `main` still ships v1.

## Commands

Use `uv run <cmd>` for everything (never activate `.venv` directly).

```bash
uv sync --all-groups               # install every dep group (dev+examples+docs) — use this locally, don't
                                    # flip between --group flags mid-session (CI itself only uses --group examples)

uv run pytest                                              # run all tests
uv run pytest tests/unit/test_bot.py                       # single file
uv run pytest tests/unit/test_bot.py::test_name -v          # single test
uv run pytest --cov=src/signalbot --cov-branch --cov-report=xml   # with coverage (matches CI)

uv run prek install    # one-time: install git hooks (ruff-check --fix, ruff-format, ty, yamlfix, uv-lock)
uv run prek run --all-files   # run all lint/format/type-check hooks manually
uv run ty check         # type check only

uv run zensical serve            # serve docs locally
uv run zensical build --clean    # build docs (always pass --clean; build via zensical, not mkdocs)

uv run datamodel-codegen --profile signal-cli-rest-api   # regenerate src/signalbot/_generated/
```

CI (`.github/workflows/ci.yaml`) runs `prek` (all hooks) and `pytest --cov` on every push to `main` and every PR.

## Architecture

### Message flow is bidirectional and file-organized by direction

- **Incoming**: `signal-cli-rest-api` pushes over websocket → `MessagePipeline._produce` (`_pipeline.py`) reads
  raw JSON → `signalbot.messages.parser.parse()` turns it into a typed `ReceivedMessage` → dispatched to a
  queue → `MessagePipeline._consume` pulls jobs and invokes the matching handler method.
- **Outgoing**: bot author code calls a method on one of the `*Actions` classes (`bot.messages`, `bot.reactions`,
  `bot.polls`, ...) → resolves recipients → builds a wire request → calls a method on `SignalAPI` (`_client/`)
  → HTTP request to `signal-cli-rest-api`.

**Extending either direction is a well-defined, multi-file checklist — read
[`docs/06_extending.md`](docs/06_extending.md) before adding a new incoming message type or outgoing action.**
It names every file that needs to change, in order.

### Layering, roughly innermost to outermost

1. `src/signalbot/_generated/` — models generated from signal-cli-rest-api's Swagger/JSON-Schema
   (`_generated/api` = requests, `_generated/data`/`_generated/receive` = responses/incoming). **Never
   hand-edit** — rerun `datamodel-codegen` instead (see `_generated/README.md`).
   `signalbot._generated` types must never leak through the public API, even nested inside a field —
   enforced by `tests/unit/test_public_api_surface.py`. Every top-level domain package (`messages/`,
   `groups/`, `polls/`, `reactions/`, `attachments/`, `contacts/`) wraps the generated type it needs in a
   thin domain subclass (docstring at minimum; real fields/methods only when wire data alone isn't enough).
2. `src/signalbot/_client/` — one file per API section (`messages.py`, `groups.py`, `polls.py`, ...), each
   with a `*URIs` class (endpoint paths) and a `*Client` class (typed to accept generated request models,
   serializes with `model_dump_json(exclude_none=True, by_alias=True)`, calls `self._request(...)`). All
   wired together on `SignalAPI` (`_client/signal_api.py`), internal only — not part of the public
   API surface (`signalbot.client` only re-exports `ConnectionMode`).
3. `src/signalbot/_actions/` — one `*Actions` class per API section (`MessageActions`, `GroupActions`, ...),
   attached to `SignalBot` in `_bot_init.py` as `bot.messages`, `bot.polls`, etc. (`GroupActions` is the
   exception, nested at `bot.groups.actions` since `bot.groups` is already the `GroupRegistry` cache).
   Resolves recipients via `RecipientResolver` (`_recipients.py`), converts domain requests to generated
   ones, calls the client, logs, returns a friendly domain-level result.
4. `src/signalbot/context/` — one `*Context` class per incoming message kind (`DataMessageContext`,
   `ReactionContext`, ...), passed into handler methods. Wraps the `SignalBot` + received message and exposes
   convenience methods (`context.send(...)`, `context.react(...)`) that delegate to the Actions layer, filling
   in fields only knowable once a message has been received (e.g. `recipient`).
5. `src/signalbot/handlers.py` — one `*Handler` ABC per message kind (`DataMessageHandler`,
   `ReactionHandler`, ...) with a single abstract `handle_xxx(self, context)` method that bot authors
   subclass, plus trigger decorators (`text_triggered`, `regex_triggered`, `reaction_triggered`) that filter
   before calling through. Each decorator also records its message predicate (`_TRIGGERS`), which the
   pipeline checks at dispatch time.
6. `src/signalbot/_pipeline.py` — `_MESSAGE_DISPATCH` is the single map tying a parsed message type to
   `(HandlerABC, ContextClass, "handle_method_name")`. Nothing reaches a handler without an entry here.
   `_dispatch_to_handlers` only queues handlers of the right role whose filters and trigger match; of the
   matching `exclusive=True` handlers only the highest `priority` one (then first registered) is queued.
7. `src/signalbot/bot.py` (`SignalBot`) — top-level object bot authors construct. `_bot_init.py` builds the
   shared `SignalAPI` client, event loop, scheduler (APScheduler), and storage backend;
   `SignalBot._init_actions()` wires up the `*Actions` instances and the `MessagePipeline`.

### Runtime model

`SignalBot.start()` schedules `_async_post_init` (`_async_init` checks `signal-cli-rest-api` connectivity/version/mode,
refreshes the group cache, runs `ReadyHandler`s; then it starts the pipeline) and runs the asyncio event loop.
The pipeline runs 1 producer task (reads the websocket, parses, dispatches to a queue) and N consumer tasks
(default 3; pull from the queue, invoke the handler) — tune consumer count based on how blocking handler code
is. Both producer and consumer loops are wrapped in `rerun_on_exception` (`_utils/retry.py`) so an uncaught
exception restarts the loop rather than killing the bot.

### Public API surface

`src/signalbot/__init__.py`'s `__all__` is the supported public API; everything else (leading-underscore
modules/packages like `_pipeline.py`, `_actions/`, `_client/`, `_generated/`) is internal. Domain packages
(`messages/`, `groups/`, `polls/`, `reactions/`, `receipts/`, `contacts/`, `attachments/`, `context/`) export
their own public types via their own `__init__.py`.

### Testing

- `tests/unit/` mirrors package structure; `tests/integration/test_handlers.py` covers end-to-end dispatch.
- No fixture files for message envelopes — tests build raw envelope JSON inline (see
  `tests/unit/messages/test_message.py`), call `parse(signal, raw_json_str)`, and assert on the result.
- `signalbot.test_utils.ChatTestCase` + `@mock_chat` (`src/signalbot/test_utils/chat_testing.py`) let a bot
  author unit-test handlers without a real `signal-cli-rest-api` — send/receive are mocked. See
  `examples/commands/tests/test_ping.py` for the pattern; this is also shipped to downstream users.
  `ChatTestCase.new_private_message`/`new_edit_message`/`new_remote_delete` build raw `Envelope`s for
  non-group messages; `tests/integration/test_chat_testing.py` tests the harness itself.
- `asyncio_mode = "auto"` (pytest.ini via `pyproject.toml`) — async test functions don't need
  `@pytest.mark.asyncio`.

### Ruff

`select = ["ALL"]` with a small ignore list (see `pyproject.toml`). Notable per-path exceptions: tests relax
annotation/assert/private-access rules; `_generated/**` is exempt from line-length and is banned from being
imported directly outside `_generated` itself (import from `signalbot._generated` instead, per
`flake8-tidy-imports.banned-api`); `test_utils/**` may access private attributes (that's its job for
downstream test suites).
