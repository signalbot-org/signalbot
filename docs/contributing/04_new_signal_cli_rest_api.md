---
title: New signal-cli-rest-api version
---

Upgrading to a new signal-cli-rest-api version means regenerating the [generated models](#generated-models) and fixing whatever changed.
The version signalbot currently targets is in [`MIN_SIGNAL_CLI_REST_API_VERSION`][signalbot.MIN_SIGNAL_CLI_REST_API_VERSION].
Each signalbot release targets one schema version and refuses to start against an older
signal-cli-rest-api version.

## Generated models

The models in
[`src/signalbot/_generated/`](https://github.com/signalbot-org/signalbot/tree/main/src/signalbot/_generated)
are generated with `datamodel-codegen` from upstream
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)'s own swagger schema, stored
in
[`src/signalbot/_generated/json_schema/signal-cli-rest-api.json`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/_generated/json_schema/signal-cli-rest-api.json).
Don't hand-add fields or models to `_generated`: if a field or endpoint is missing, it is missing
upstream. Open an issue or a PR against that repo, and once it is released follow the steps below
to pull the updated schema in.

## Steps

1. **Update the schema and regenerate the models**, following
   [`src/signalbot/_generated/README.md`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/_generated/README.md).
   Fields that need renaming go in the `aliases.json` and `serialization-aliases.json` files next to
   the schema.

2. **Review the generated diff.** Look for new, removed or renamed models and fields, fields that
   became required, and changed response types.

3. **Fix the code that uses the changed models.** Run `uv run ty check` to find the breakages in
   the domain packages, `_client/` and `_actions/`. If a public type now exposes a new generated
   type, wrap it as described in
   [Wrapped types](#wrapped-types).
   New endpoints or message types are better added in their own PR, following
   [New incoming messages](02_incoming_messages.md) or [New outgoing messages](03_outgoing_messages.md).

4. **Bump [`MIN_SIGNAL_CLI_REST_API_VERSION`][signalbot.MIN_SIGNAL_CLI_REST_API_VERSION]** in
   [`bot.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/bot.py) to the new
   version.

5. **Update the mocks.** The chat testing mocks in
   [`src/signalbot/test_utils/chat_testing.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/test_utils/chat_testing.py)
   report a signal-cli-rest-api version (`AboutMock`) and build API responses, so update the
   version and any response whose shape changed. Do the same for the fixtures and raw JSON in
   [`tests/unit`](https://github.com/signalbot-org/signalbot/tree/main/tests/unit), e.g. a new
   required field in `fake_group` in
   [`tests/unit/conftest.py`](https://github.com/signalbot-org/signalbot/blob/main/tests/unit/conftest.py).

## Wrapped types

No `signalbot._generated` type may appear on the public API, directly or nested inside a field —
[`tests/unit/test_public_api_surface.py`](https://github.com/signalbot-org/signalbot/blob/main/tests/unit/test_public_api_surface.py)
enforces this. Each domain package wraps the generated types it exposes:

- If nothing about a generated type needs to change, it still gets a thin domain subclass with a
  docstring — `class GroupInfo(GeneratedGroupInfo): """..."""` — even with zero added fields. The
  generated tree is produced from a bare JSON schema and carries no docstrings of its own, so this
  subclass is the only place that documentation exists, and it's what gets rendered under
  [Reference](../reference/messages.md).
- Real fields or methods are added only when the domain type needs state or behavior the wire
  format doesn't have — pattern:
  [`Attachment.base64_content`][signalbot.attachments.Attachment] in
  [`src/signalbot/attachments/attachment.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/attachments/attachment.py).
- If a container field then needs to point at one of these wrapped types instead of the generated
  type it replaces, that's a genuine override of the generated base class. pyright flags this as
  `reportIncompatibleVariableOverride` because narrowing a mutable attribute's type in a subclass is
  unsound in general — but it's sound here: every wrapped type is a strict superset of the generated
  type it replaces (same fields, same validation, plus extra), and pydantic validates the value
  against the narrower type on construction, so nothing bypasses it. Annotate the field with a bare
  `# pyright: ignore[reportIncompatibleVariableOverride]` — the rationale above is why.
  See `GroupEntry.permissions` in
  [`src/signalbot/groups/group_entry.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/groups/group_entry.py)
  or `Quote.attachments` in
  [`src/signalbot/messages/data_message_content.py`](https://github.com/signalbot-org/signalbot/blob/main/src/signalbot/messages/data_message_content.py)
  for the pattern.
