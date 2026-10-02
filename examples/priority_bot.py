import logging
import os

from signalbot import (
    Config,
    DataMessageContext,
    DataMessageHandler,
    SendMessage,
    SignalBot,
    regex_triggered,
    text_triggered,
)

handler = logging.StreamHandler()

formatter = logging.Formatter(
    "%(asctime)s %(name)s [%(levelname)s] - %(funcName)s - %(message)s"
)
handler.setFormatter(formatter)

logger = logging.getLogger("priority_bot")
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class LogHandler(DataMessageHandler):
    async def handle_data_message(self, context: DataMessageContext) -> None:
        logger.info("Received: %s", context.message.text)


class PingCommand(DataMessageHandler):
    @text_triggered("!ping")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        await context.send(SendMessage(text="pong"))


class UnknownCommand(DataMessageHandler):
    @regex_triggered(r"^!")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        text = f"Unknown command {context.message.text}, try !ping"
        await context.send(SendMessage(text=text))


class EchoFallback(DataMessageHandler):
    async def handle_data_message(self, context: DataMessageContext) -> None:
        await context.send(SendMessage(text=context.message.text))


def register_handlers(bot: SignalBot) -> None:
    bot.register(LogHandler())  # no priority: runs for every message
    # Of the matching handlers with a priority, only the highest one runs
    bot.register(PingCommand(), priority=2)  # !ping
    bot.register(UnknownCommand(), priority=1)  # matches !ping too, but loses
    bot.register(EchoFallback(), priority=0)  # matches everything: the fallback


if __name__ == "__main__":
    bot = SignalBot(
        Config(
            phone_number=os.environ["PHONE_NUMBER"],
        )
    )
    register_handlers(bot)
    bot.start()
