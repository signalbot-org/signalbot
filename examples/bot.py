import os

from examples.commands import (
    AboutCommand,
    AttachmentCommand,
    BroadcastCommand,
    CloseCommand,
    DeleteCommand,
    DeleteLocalAttachmentCommand,
    EditCommand,
    EditNotifierHandler,
    HelpCommand,
    LinkPreviewCommand,
    PingCommand,
    PollCommand,
    ReactCommand,
    ReceiptCommand,
    RegexTriggeredCommand,
    ReplyCommand,
    StylesCommand,
    TriggeredCommand,
    TypingCommand,
    TypingIndicatorToggleCommand,
    UpdateContactCommand,
    UpdateGroupCommand,
)
from examples.handlers import (
    DeletionNotifierHandler,
    FilteredReactionHandler,
    GroupUpdateNotifierHandler,
    ReactionDetailsHandler,
    TypingIndicatorHandler,
    WelcomeHandler,
)
from signalbot import Config, SignalBot


def main() -> None:
    phone_number = os.environ["PHONE_NUMBER"]

    # Replace the recipient with your own phone number or group ID to
    # receive the welcome message and the broadcast message.
    contact_phone_number = os.environ.get("CONTACT_PHONE_NUMBER")

    bot = SignalBot(Config(phone_number=phone_number))

    bot.register(WelcomeHandler(recipient=contact_phone_number))

    # By default the handlers are enabled for all contacts and all groups
    bot.register(HelpCommand())
    bot.register(PingCommand())
    bot.register(ReplyCommand())
    bot.register(RegexTriggeredCommand())
    bot.register(ReactCommand())
    bot.register(EditCommand())
    bot.register(EditNotifierHandler())
    bot.register(DeleteCommand())
    bot.register(DeleteLocalAttachmentCommand())
    bot.register(StylesCommand())
    bot.register(LinkPreviewCommand())
    bot.register(CloseCommand())
    bot.register(PollCommand())
    bot.register(ReceiptCommand())
    bot.register(AboutCommand())
    bot.register(ReactionDetailsHandler())
    bot.register(FilteredReactionHandler())
    bot.register(DeletionNotifierHandler())
    bot.register(GroupUpdateNotifierHandler())

    # Disabled by default; toggle it with the enable-typing-indicator /
    # disable-typing-indicator commands.
    typing_indicator_handler = TypingIndicatorHandler()
    bot.register(typing_indicator_handler)
    bot.register(TypingIndicatorToggleCommand(typing_indicator_handler))

    # The handler will only trigger for group messages
    bot.register(AttachmentCommand(), contacts=False)
    bot.register(UpdateGroupCommand(), contacts=False)

    # The handler will only trigger for private messages, since updating a
    # contact's metadata doesn't apply to groups
    bot.register(UpdateContactCommand(), groups=False)

    # Replace with the phone numbers or group IDs that should receive the
    # broadcast message
    broadcast_recipients = [contact_phone_number] if contact_phone_number else []
    bot.register(BroadcastCommand(recipients=broadcast_recipients))

    # The handler will only trigger the group named "My Group"
    bot.register(TypingCommand(), groups=["My Group"], contacts=False)

    # The handler will only trigger for the contact "+490123456789"
    bot.register(TriggeredCommand(), contacts=["+490123456789"], groups=False)

    bot.start()


if __name__ == "__main__":
    main()
