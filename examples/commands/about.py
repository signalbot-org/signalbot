from signalbot import (
    DataMessageContext,
    DataMessageHandler,
    SendMessage,
    text_triggered,
)
from signalbot import (
    __version__ as signalbot_version,
)


class AboutCommand(DataMessageHandler):
    def help_message(self) -> str:
        return "about: 📋 Show signal-cli-rest-api version information."

    @text_triggered("about")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        about = await context.bot.general.about()
        text = (
            "Versions:\n"
            f"\tsignalbot: {signalbot_version}\n"
            f"\tsignal-cli-rest-api: {about.version}"
        )
        await context.send(SendMessage(text=text))
