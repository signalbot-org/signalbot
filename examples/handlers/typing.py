from signalbot import SendMessage, TypingAction, TypingContext, TypingHandler


class TypingIndicatorHandler(TypingHandler):
    """Notifies when someone starts typing. Starts disabled; toggle it with the
    `enable-typing-indicator` / `disable-typing-indicator` commands in
    `examples/commands/typing.py`.
    """

    def __init__(self) -> None:
        self.enabled = False
        self._verb_msg = {
            TypingAction.STARTED: "started",
            TypingAction.STOPPED: "stopped",
        }

    def help_message(self) -> str:
        return "Typing indicator received: ⌨️ Notifies when someone starts typing."

    async def handle_typing(self, context: TypingContext) -> None:
        if not self.enabled:
            return

        verb = self._verb_msg[context.message.action]
        await context.send(
            SendMessage(text=f"{context.message.source_name} {verb} typing")
        )
