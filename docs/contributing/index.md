---
title: Contributing
---

Contributions are welcome.

The first step to contribute is to install the package in editable mode.
For any changes, check that the tests still pass as detailed below.

### Local development

1. Clone the [repository](https://github.com/signalbot-org/signalbot).
2. Install [uv](https://docs.astral.sh/uv/).
3. Create a venv and install signalbot with its dependencies in it (including extra dependencies to be able to run the examples)
    ```bash
    uv sync --group examples
    ```

    * You can install signalbot as an editable depedency in another repository (e.g. your own bot repository) like so
    ```
    uv add --editable ../signalbot
    ```

4. Install the prek hook for linting and formatting
    ```bash
    uv run prek install
    ```

### Unit Testing

The tests can be executed with

```bash
uv run pytest
```

### Extending signalbot

Adding support for a new Signal message type touches a small, predictable set of files. Start with
the [Architecture](01_architecture.md) page to see how the layers fit together, then follow the
checklist for the direction you are adding:

- [New incoming messages](02_incoming_messages.md): a message pushed by signal-cli-rest-api that
  signalbot parses and dispatches to a handler.
- [New outgoing messages](03_outgoing_messages.md): a bot author call that turns into an HTTP
  request against a signal-cli-rest-api endpoint.

Supporting a newer signal-cli-rest-api release? See
[Upgrading to a new signal-cli-rest-api version](04_new_signal_cli_rest_api.md).

### Serving the documentation locally

1. Install the docs dependencies
    ```bash
    uv sync --group docs
    ```
2. Run the zensical serve command
    ```bash
    uv run zensical serve
    ```
