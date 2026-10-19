import asyncio

from examples.handlers import TypingIndicatorHandler
from signalbot import (
    DataMessageContext,
    DataMessageHandler,
    SendMessage,
    text_triggered,
)


class TypingCommand(DataMessageHandler):
    def help_message(self) -> str:
        return "typing: ⌨️ Demonstrates typing indicator for a few seconds."

    @text_triggered("typing")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        await context.start_typing()
        seconds = 5
        await asyncio.sleep(seconds)
        await context.stop_typing()
        await context.send(SendMessage(text=f"Typed for {seconds}s"))


class TypingIndicatorToggleCommand(DataMessageHandler):
    """Turns `TypingIndicatorHandler`'s notifications on or off. Needs a reference
    to that handler's instance, so it's constructed with it in `examples/bot.py`.
    """

    def __init__(self, typing_indicator_handler: TypingIndicatorHandler) -> None:
        self._typing_indicator_handler = typing_indicator_handler

    def help_message(self) -> str:
        return (
            "enable-typing-indicator / disable-typing-indicator: ⌨️ Turns the "
            "typing indicator handler on or off (starts disabled)."
        )

    @text_triggered("enable-typing-indicator", "disable-typing-indicator")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        text = context.message.text
        if text is None:
            return

        enable = text.strip().lower() == "enable-typing-indicator"
        self._typing_indicator_handler.enabled = enable
        state = "enabled" if enable else "disabled"
        await context.send(SendMessage(text=f"Typing indicator handler {state}"))
