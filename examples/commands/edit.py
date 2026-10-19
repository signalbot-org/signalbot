import asyncio

from signalbot import (
    DataMessageContext,
    DataMessageHandler,
    EditMessage,
    SendMessage,
    text_triggered,
)


class EditCommand(DataMessageHandler):
    def help_message(self) -> str:
        return "edit: ✏️ Edit a message."

    @text_triggered("edit")
    async def handle_data_message(self, context: DataMessageContext) -> None:
        sent_message = await context.send(
            SendMessage(text="This message will be edited in two seconds.")
        )
        await asyncio.sleep(2)
        await context.edit(
            SendMessage(text="This message has been edited."),
            sent_message,
        )


class EditNotifierHandler(DataMessageHandler):
    """`EditMessage` is a `DataMessage` subclass, so edits are dispatched to the
    same `handle_data_message` method as regular messages — check `isinstance`
    to tell them apart.
    """

    def help_message(self) -> str:
        return "Message edited: 📝 Notifies when someone edits a message."

    async def handle_data_message(self, context: DataMessageContext) -> None:
        if not isinstance(context.message, EditMessage):
            return

        await context.send(
            SendMessage(text=f"You edited your message to: {context.message.text}")
        )
