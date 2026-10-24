---
title: Overview
---

# Signalbot

A Python framework for Signal bots. You write handlers for the events you care about, like messages or reactions,
and respond by sending your own messages and reactions, or by creating polls. It talks to Signal through
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) and comes with test helpers, so you can
test your bot without a real Signal account.

Here is minimal example of what that looks like:
```python
--8<-- "examples/simple_bot.py"
```

To set it up follow the steps in the [getting started page](01_getting_started.md).
See [How it works](02_concepts.md) for a visual walkthrough of how a message travels from
`signal-cli-rest-api` to your handler and back.

### Methods overview

The bot can do a lot more, here is an overview of the methods available
on the `context` passed into a `Handler`:

| Action | Method |
|---|---|
| Send a new message | [`context.send(SendMessage(text=...))`][signalbot.context.Context.send] |
| Reply, quoting the received message | [`context.reply(SendMessage(text=...))`][signalbot.context.DataMessageContext.reply] \* |
| Edit a previously sent message | [`context.edit(SendMessage(text=...), original_message)`][signalbot.context.DataMessageContext.edit] \* |
| Delete a previously sent message | [`context.remote_delete(sent_message)`][signalbot.context.DataMessageContext.remote_delete] \* |
| React to a message | [`context.react("emoji")`][signalbot.context.DataMessageContext.react] \* |
| Mark a message as read | [`context.send_receipt(ReceiptType.READ)`][signalbot.context.DataMessageContext.send_receipt] \* |
| Delete the local copy of an attachment | [`context.delete_attachment(attachment)`][signalbot.context.DataMessageContext.delete_attachment] \* |
| Start typing | [`context.start_typing()`][signalbot.context.Context.start_typing] |
| Stop typing | [`context.stop_typing()`][signalbot.context.Context.stop_typing] |
| Change group settings | [`context.update_group(UpdateGroup(name=...))`][signalbot.context.Context.update_group] |
| Update a contact | [`context.update_contact(UpdateContact(name=...))`][signalbot.context.Context.update_contact] |
| Create a poll | [`context.create_poll(CreatePoll(question=..., answers=[...]))`][signalbot.context.Context.create_poll] |

\* Only available on [`DataMessageContext`][signalbot.context.DataMessageContext].

A few methods aren't tied to a specific message and only exist on `bot`:

- [bot.register(handler)][signalbot.bot.SignalBot.register]: Register a new handler
- [bot.start()][signalbot.bot.SignalBot.start]: Start the bot
- [bot.scheduler][signalbot.bot.SignalBot.scheduler]: Schedule tasks, see the [scheduler examples](examples/03_bot_with_scheduler.md).
- [bot.storage][signalbot.bot.SignalBot.storage] ([`SQLiteStorage`][signalbot.storage.SQLiteStorage] or
  [`RedisStorage`][signalbot.storage.RedisStorage]): Store and read data on disk with a db.

Every method above can also be called directly on the bot, outside a handler, by supplying
the recipient yourself, e.g. `bot.messages.send(SendMessage(text=...), recipient)`.

## Real world bot examples

There are many real world examples of bot implementations using this library.
Check the whole list at https://github.com/signalbot-org/signalbot/network/dependents
