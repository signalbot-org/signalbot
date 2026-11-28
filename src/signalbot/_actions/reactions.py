from __future__ import annotations

from typing import TYPE_CHECKING

from signalbot._actions.base import BotActionsBase
from signalbot._generated import SendReactionRequest
from signalbot.messages import SentMessage

if TYPE_CHECKING:
    import logging

    from signalbot._client import SignalAPI
    from signalbot._recipients import RecipientResolver
    from signalbot.messages import DataMessage


class ReactionActions(BotActionsBase):
    def __init__(
        self,
        signal: SignalAPI,
        recipients: RecipientResolver,
        logger: logging.Logger,
        phone_number: str,
    ) -> None:
        super().__init__(signal, recipients, logger)
        self._phone_number = phone_number

    async def react(self, message: SentMessage | DataMessage, emoji: str) -> None:
        """React to a message with an emoji.

        Args:
            message: The message to react to.
            emoji: Emoji reaction value.
        """
        if isinstance(message, SentMessage):
            recipient = message.recipient
            target_author = self._phone_number
        else:
            recipient = message.source_or_group_id()
            target_author = message.source_uuid or message.source_number

            if message.is_group():
                recipient = self._recipients.resolve(recipient)

            # Only reachable for group messages: for a private message,
            # `source_or_group_id()` above already raised if there's no source
            if target_author is None:
                error_msg = "Cannot react to group message without source uuid"
                raise ValueError(error_msg)

        reaction_request = SendReactionRequest(
            recipient=recipient,
            reaction=emoji,
            target_author=target_author,
            timestamp=message.timestamp,
        )
        await self._signal.reactions.react(reaction_request)
        self._logger.info("[Bot] New reaction: %s", emoji)
