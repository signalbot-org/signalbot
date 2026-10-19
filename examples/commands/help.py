from typing import Protocol, runtime_checkable

from examples.commands.edit import EditNotifierHandler
from signalbot import (
    DataMessageContext,
    DataMessageHandler,
    SendMessage,
    SignalBot,
    text_triggered,
)


@runtime_checkable
class HasHelpMessage(Protocol):
    def help_message(self) -> str: ...


def build_help_messages(bot: SignalBot) -> tuple[str, str]:
    commands = []
    handlers = []
    for registered, _, _, _ in bot.handlers:
        if not isinstance(registered, HasHelpMessage):
            continue
        if isinstance(registered, DataMessageHandler) and not isinstance(
            registered, EditNotifierHandler
        ):
            commands.append(registered.help_message())
        else:
            handlers.append(registered.help_message())

    command_sections = []
    if commands:
        entries = "\n".join(f"  {entry}" for entry in commands)
        command_sections.append(f"Commands:\n{entries}")

    handler_sections = []
    if handlers:
        entries = "\n".join(f"  {entry}" for entry in handlers)
        handler_sections.append(f"Handlers:\n{entries}")

    return "\n".join(command_sections), "\n".join(handler_sections)


class HelpCommand(DataMessageHandler):
    def help_message(self) -> str:
        return "help: 🆘 Shows information about available commands."

    @text_triggered("help")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        commands_msg, handlers_msg = build_help_messages(context.bot)
        await context.send(SendMessage(text=commands_msg))
        await context.send(SendMessage(text=handlers_msg))
