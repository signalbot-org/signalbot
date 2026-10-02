---
title: Handler priorities
---

This bot showcases [exclusive handlers](../02_concepts.md#exclusive-handlers): registering handlers with a `priority` so that only the highest priority one that matches a message answers it.

- `!ping` matches `PingCommand`, `UnknownCommand` and `EchoFallback`; `PingCommand` has the highest priority, so the bot replies `pong`.
- `!foo` matches `UnknownCommand` and `EchoFallback`; the bot replies `Unknown command !foo, try !ping`.
- `hello` only matches `EchoFallback`, so the bot echoes `hello`.

`LogHandler` is registered without a priority, so it logs every message alongside whichever exclusive handler answers it.

``` python
--8<-- "examples/priority_bot.py"
```
