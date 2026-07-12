from __future__ import annotations

import asyncio
import copy
import itertools
import logging
import re
import time
import traceback
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

import phonenumbers
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from packaging.version import Version

from signalbot.api import ReceiveMessagesError, SignalAPI
from signalbot.auth import BasicAuthentication, BearerAuthentication
from signalbot.bot_config import (
    BasicAuth,
    BearerAuth,
    Config,
    InMemoryConfig,
    RedisConfig,
    SQLiteConfig,
    load_config,
)
from signalbot.command import Command
from signalbot.context import Context
from signalbot.message import Message, MessageType, UnknownMessageFormatError
from signalbot.storage import RedisStorage, SQLiteStorage

if TYPE_CHECKING:
    from pathlib import Path

    from signalbot.link_previews import LinkPreview

CommandList: TypeAlias = list[
    tuple[
        Command,
        list[str] | bool,
        list[str] | bool,
        Callable[[Message], bool] | None,
    ]
]

LOGGER_NAME = "signalbot"
"""
The logger name used by signalbot.
"""

MIN_SIGNAL_CLI_REST_API_VERSION = Version("0.95.0")
"""
The minimum required version of `signal-cli-rest-api` for this version of `signalbot`.
"""


def enable_console_logging(level: int = logging.WARNING) -> None:
    """Enable console logging for the signalbot logger.

    Args:
        level: Logging level for the logger.
    """
    handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(asctime)s %(name)s [%(levelname)s] - %(funcName)s - %(message)s"
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    logger.setLevel(level)


class SignalBot:
    """
    SignalBot is the main class for the bot. It provides methods to register commands,
    start the bot, and interact with messages.

    Attributes:
        config (Config): The configuration for the bot.
        commands: A list of registered commands with their filters.
            Only available after `.start()` is called and `init_task` is done.
        groups (list): A list of groups the bot is a member of.
            Only available after `.start()` is called and `init_task` is done.
        storage (SQLiteStorage | RedisStorage): The storage backend used by the bot.
        scheduler (AsyncIOScheduler): The scheduler for running scheduled tasks.
        init_task: The initialization async task for the bot.
            Only available after `.start()` is called.
    """

    def __init__(self, config: Config | Mapping | Path | str) -> None:
        """Initilization for the SignalBot.

        Args:
            config: the configuration for the bot.

        Example config:
        ```python
        {
            signal_service: "127.0.0.1:8080",
            phone_number: "+49123456789"
        }
        ```
        """
        self._logger = logging.getLogger(LOGGER_NAME)

        self.config = load_config(config)

        if isinstance(self.config.auth, BasicAuth):
            auth = BasicAuthentication(
                self.config.auth.username, self.config.auth.password
            )
        elif isinstance(self.config.auth, BearerAuth):
            auth = BearerAuthentication(self.config.auth.token)
        else:
            if self.config.auth is not None:
                error_msg = f"Unsupported auth type '{self.config.auth}', "
                error_msg += "no authentication will be used."
                self._logger.warning(error_msg)
            auth = None

        self._commands_to_be_registered: CommandList = []  # populated by .register()
        self.commands: CommandList = []  # populated by .start()

        self.groups = []  # populated by .start()
        self._groups_by_id = {}
        self._groups_by_internal_id = {}
        self._groups_by_name = defaultdict(list)

        self.init_task: None | asyncio.Task = None

        try:
            self._signal = SignalAPI(
                self.config.signal_service,
                self.config.phone_number,
                auth,
                self.config.download_attachments,
                self.config.connection_mode,
            )
        except KeyError:
            raise SignalBotError("Could not initialize SignalAPI with given config")  # noqa: B904, EM101, TRY003

        try:
            self._event_loop = asyncio.get_event_loop()
        except RuntimeError:
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)

        self._q = asyncio.Queue()

        self._produce_tasks: set[asyncio.Task] = set()
        self._consume_tasks: set[asyncio.Task] = set()

        try:
            self.scheduler = AsyncIOScheduler(event_loop=self._event_loop)
        except Exception as e:  # noqa: BLE001
            raise SignalBotError(f"Could not initialize scheduler: {e}")  # noqa: B904, EM102, TRY003

        if isinstance(self.config.storage, SQLiteConfig):
            self.storage = SQLiteStorage(
                self.config.storage.sqlite_db,
                check_same_thread=self.config.storage.check_same_thread,
            )
            self._logger.info("sqlite storage initilized")
        elif isinstance(self.config.storage, RedisConfig):
            self.storage = RedisStorage(
                self.config.storage.redis_host,
                self.config.storage.redis_port,
                self.config.storage.redis_password,
            )
            self._logger.info("redis storage initilized")
        elif isinstance(self.config.storage, InMemoryConfig):
            self.storage = SQLiteStorage()
            self._logger.info("in-memory storage initilized")
        else:
            self.storage = SQLiteStorage()
            self._logger.warning(
                " Using in-memory storage."
                " Restarting will delete the storage!"
                " Add storage: {'type': 'in-memory'}"
                " to the config to silence this error.",
            )

    def get_group(self, internal_id: str) -> dict[str, Any] | None:
        if internal_id in self._groups_by_internal_id:
            return copy.deepcopy(self._groups_by_internal_id[internal_id])
        return None

    def register(
        self,
        command: Command,
        contacts: list[str] | bool = True,  # noqa: FBT001, FBT002
        groups: list[str] | bool = True,  # noqa: FBT001, FBT002
        f: Callable[[Message], bool] | None = None,
    ) -> None:
        """Register a command with optional contact/group filters.

        Args:
            command: Command instance to register.
            contacts: Allowed contacts or True for all.
            groups: Allowed groups or True for all.
            f: Optional function to further filter messages.
        """
        command.bot = self
        command.setup()
        self._commands_to_be_registered.append((command, contacts, groups, f))

    async def _resolve_commands(self) -> None:
        self.commands = []
        for command, contacts, groups, f in self._commands_to_be_registered:
            group_ids = None

            if isinstance(groups, bool):
                group_ids = groups

            if isinstance(groups, list):
                group_ids = []
                for group in groups:
                    group_id = self._resolve_group_receiver(group)
                    if group_id is not None:
                        group_ids.append(group_id)
                    else:
                        error_msg = f"[Bot] [{command.__class__.__name__}] '{group}' "
                        error_msg += "is not a valid group name or id"
                        self._logger.warning(error_msg)

            self.commands.append((command, contacts, group_ids, f))

    async def _async_post_init(self) -> None:
        await self._check_signal_service()
        await self._check_signal_cli_rest_api_version()
        await self._check_signal_cli_rest_api_mode()
        await self._detect_groups()
        await self._resolve_commands()
        await self._create_produce_consume_messages_tasks()

    async def _check_signal_service(self) -> None:
        while (await self._signal.check_signal_service()) is False:
            self._logger.error(
                "Cannot connect to the signal-cli-rest-api service, retrying"
            )
            await asyncio.sleep(self.config.retry_interval)

    async def _check_signal_cli_rest_api_version(self) -> None:
        version = await self.signal_cli_rest_api_version()

        # `unset` version is for preview versions of signal-cli-rest-api
        if version == "unset":
            self._logger.warning(
                "signal-cli-rest-api version is unset; skipping compatibility check",
            )
            return

        if Version(version) < MIN_SIGNAL_CLI_REST_API_VERSION:
            error_msg = f"Incompatible signal-cli-rest-api version, found {version}"
            error_msg += f", minimum required is {MIN_SIGNAL_CLI_REST_API_VERSION}"
            raise RuntimeError(error_msg)

    async def _check_signal_cli_rest_api_mode(self) -> None:
        mode = await self.signal_cli_rest_api_mode()
        if mode != "json-rpc":
            error_msg = (
                f"Wrong signal-cli-rest-api mode, found '{mode}', expected 'json-rpc'"
            )
            raise RuntimeError(error_msg)

    def _store_reference_to_task(
        self,
        task: asyncio.Task,
        task_set: set[asyncio.Task],
    ) -> None:
        # Keep a hard reference to the tasks, fixes Ruff's RUF006 rule
        task_set.add(task)
        task.add_done_callback(task_set.discard)

    def start(self, run_forever: bool = True) -> None:  # noqa: FBT001, FBT002
        """Start the bot event loop and scheduler.

        Args:
            run_forever: Whether to start the event loop or only add the task to it.
        """
        self.init_task = self._event_loop.create_task(
            self._rerun_on_exception(self._async_post_init),
        )

        if run_forever:
            self.scheduler.start()

            self._event_loop.run_forever()

    async def signal_cli_rest_api_version(self) -> str:
        """Return the signal-cli-rest-api version."""
        return await self._signal.get_signal_cli_rest_api_version()

    async def signal_cli_rest_api_mode(self) -> str:
        """Return the signal-cli-rest-api mode."""
        return await self._signal.get_signal_cli_rest_api_mode()

    async def send(  # noqa: PLR0913
        self,
        receiver: str,
        text: str,
        *,
        base64_attachments: list | None = None,
        link_preview: LinkPreview | None = None,
        quote_author: str | None = None,
        quote_mentions: list | None = None,
        quote_message: str | None = None,
        quote_timestamp: int | None = None,
        mentions: (
            list[dict[str, Any]] | None
        ) = None,  # [{ "author": "uuid" , "start": 0, "length": 1 }]
        edit_timestamp: int | None = None,
        text_mode: str | None = None,
        view_once: bool = False,
    ) -> int:
        """Send or edit a message.

        Args:
            receiver: The recipient of the message.
            text: The content of the message.
            base64_attachments: List of attachments encoded in base64.
            link_preview: Link previews to be sent with the message.
            quote_author: The author of the quoted message, required if quote_message is
                set.
            quote_mentions: List of mentioned users in the quoted message, required if
                quote_message is set.
            quote_message: The content of the quoted message, required if quote_message
                is set.
            quote_timestamp: The timestamp of the quoted message, required if
                quote_message is set.
            mentions: List of dictionary of mentions, it has the format
                `[{ "author": "uuid" , "start": 0, "length": 1 }]`.
            edit_timestamp: The timestamp of the message to edit, if not set a new
                message will be sent.
            text_mode: The text mode of the message, can be "normal" or "styled".
            view_once: Whether the message should be view once or not.

        Returns:
            The timestamp of the sent or edited message.
        """
        receiver = self._resolve_receiver(receiver)
        link_preview_raw = link_preview.model_dump() if link_preview else None

        resp = await self._signal.send(
            receiver,
            text,
            base64_attachments=base64_attachments,
            link_preview=link_preview_raw,
            quote_author=quote_author,
            quote_mentions=quote_mentions,
            quote_message=quote_message,
            quote_timestamp=quote_timestamp,
            mentions=mentions,
            text_mode=text_mode,
            edit_timestamp=edit_timestamp,
            view_once=view_once,
        )
        resp_payload = await resp.json()
        timestamp = int(resp_payload["timestamp"])
        self._logger.info(f"[Bot] New message {timestamp} sent:\n{text}")  # noqa: G004

        return timestamp

    async def poll(
        self,
        receiver: str,
        question: str,
        answers: list[str],
        *,
        allow_multiple_selections: bool = False,
    ) -> int:
        """Create a poll.

        Args:
            receiver: The recipient of the message.
            question: The poll question.
            answers: List of answer options for the poll.
            allow_multiple_selections: Whether multiple answers can be selected.

        Returns:
            The timestamp the poll was created.
        """
        receiver = self._resolve_receiver(receiver)

        resp = await self._signal.poll(
            receiver,
            question,
            answers,
            allow_multiple_selections=allow_multiple_selections,
        )
        resp_payload = await resp.json()
        timestamp = int(resp_payload["timestamp"])
        self._logger.info("[Bot] New poll created:\n%s", question)

        return timestamp

    async def react(self, message: Message, emoji: str) -> None:
        """React to a message with an emoji.

        Args:
            message: The message to react to.
            emoji: Emoji reaction value.
        """
        # TODO: check that emoji is really an emoji  # noqa: TD002, TD003
        recipient = message.recipient()
        recipient = self._resolve_receiver(recipient)
        target_author = message.source
        timestamp = message.timestamp
        await self._signal.react(recipient, emoji, target_author, timestamp)
        self._logger.info(f"[Bot] New reaction: {emoji}")  # noqa: G004

    async def receipt(
        self,
        message: Message,
        receipt_type: Literal["read", "viewed"],
    ) -> None:
        """Send a read or viewed receipt for a message if supported.

        Args:
            message: The message to acknowledge.
            receipt_type: Receipt type to send.
        """
        if message.group is not None:
            self._logger.warning("[Bot] Receipts are not supported for groups")
            return

        recipient = self._resolve_receiver(message.recipient())
        await self._signal.receipt(recipient, receipt_type, message.timestamp)
        self._logger.info(f"[Bot] Receipt: {receipt_type}")  # noqa: G004

    async def start_typing(self, receiver: str) -> None:
        """Send a typing indicator to a receiver.

        Args:
            receiver: Message recipient.
        """
        receiver = self._resolve_receiver(receiver)
        await self._signal.start_typing(receiver)

    async def stop_typing(self, receiver: str) -> None:
        """Stop a typing indicator for a receiver.

        Args:
            receiver: Message recipient.
        """
        receiver = self._resolve_receiver(receiver)
        await self._signal.stop_typing(receiver)

    async def update_contact(
        self,
        receiver: str,
        expiration_in_seconds: int | None = None,
        name: str | None = None,
    ) -> None:
        """Update a contact's metadata.

        Args:
            receiver: Contact identifier.
            expiration_in_seconds: Expiration timer in seconds.
            name: Contact display name.
        """
        receiver = self._resolve_receiver(receiver)
        await self._signal.update_contact(
            receiver,
            expiration_in_seconds=expiration_in_seconds,
            name=name,
        )

    async def update_group(
        self,
        group_id: str,
        base64_avatar: str | None = None,
        description: str | None = None,
        expiration_in_seconds: int | None = None,
        name: str | None = None,
    ) -> None:
        """Update a group's metadata.

        Args:
            group_id: Group identifier or name.
            base64_avatar: Base64-encoded avatar.
            description: Group description.
            expiration_in_seconds: Expiration timer in seconds.
            name: Group display name.
        """
        group_id = self._resolve_receiver(group_id)
        await self._signal.update_group(
            group_id,
            base64_avatar=base64_avatar,
            description=description,
            expiration_in_seconds=expiration_in_seconds,
            name=name,
        )

    async def remote_delete(self, receiver: str, timestamp: int) -> int:
        """Delete a previously sent message.

        Args:
            receiver: Recipient identifier.
            timestamp: Timestamp of the message to delete.

        Returns:
            The timestamp of the delete action.
        """
        receiver = self._resolve_receiver(receiver)

        resp = await self._signal.remote_delete(
            receiver,
            timestamp=timestamp,
        )
        resp_payload = await resp.json()
        ret_timestamp = int(resp_payload["timestamp"])
        self._logger.info(f"[Bot] Deleted message with timestamp {timestamp}")  # noqa: G004

        return ret_timestamp

    async def delete_attachment(self, attachment_filename: str) -> None:
        """Delete an attachment from local storage.

        Args:
            attachment_filename: File name to delete.
        """
        await self._signal.delete_attachment(attachment_filename)

    async def _detect_groups(self) -> None:
        # reset group lookups to avoid stale data
        self.groups = await self._signal.get_groups()

        self._groups_by_id: dict[str, dict[str, Any]] = {}
        self._groups_by_internal_id: dict[str, dict[str, Any]] = {}
        self._groups_by_name: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for group in self.groups:
            self._groups_by_id[group["id"]] = group
            self._groups_by_internal_id[group["internal_id"]] = group
            self._groups_by_name[group["name"]].append(group)

        self._logger.info(f"[Bot] {len(self.groups)} groups detected")  # noqa: G004

    async def _update_group(self, group_internal_id: str) -> None:
        # look up group that requires update
        group = await self._signal.get_group(
            self._groups_by_internal_id[group_internal_id]["id"]
        )

        current_group_name = self._groups_by_internal_id[group_internal_id][
            "name"
        ]  # group name may have been updated
        self._groups_by_name[current_group_name] = [
            g
            for g in self._groups_by_name[current_group_name]
            if g["id"] != group["id"]
        ]
        self.groups = [
            group if g["internal_id"] == group_internal_id else g for g in self.groups
        ]
        self._groups_by_id[group["id"]] = group
        self._groups_by_internal_id[group["internal_id"]] = group
        self._groups_by_name[group["name"]].append(group)

        self._logger.info("[Bot] Group updated")

    async def _process_updates(self, message: Message) -> None:
        # Update groups if message is from an unknown group
        if (
            message.is_group()
            and self._groups_by_internal_id.get(message.group) is None
        ):
            await self._detect_groups()

        if message.type == MessageType.GROUP_UPDATE_MESSAGE:
            await self._update_group(message.updated_group_id)

    def _resolve_receiver(self, receiver: str) -> str:
        if self._is_phone_number(receiver):
            return receiver

        if self._is_valid_uuid(receiver):
            return receiver

        if self._is_username(receiver):
            return receiver

        group_id = self._resolve_group_receiver(receiver)
        if group_id is not None:
            return group_id

        raise SignalBotError("Cannot resolve receiver.")  # noqa: EM101, TRY003

    def _resolve_group_receiver(self, group_id_or_name: str) -> str | None:
        group = self._groups_by_id.get(group_id_or_name)
        if group is not None:
            return group["id"]

        if self._is_group_id(group_id_or_name):
            error_msg = f"[Bot] Group with id '{group_id_or_name}' not found. There "
            error_msg += "is a typo in id or the bot is not a member of the group."
            self._logger.warning(error_msg)
            return group_id_or_name

        group = self._groups_by_internal_id.get(group_id_or_name)
        if group is not None:
            return group["id"]

        group = self._get_group_by_name(group_id_or_name)
        if group is not None:
            return group["id"]

        return None

    def _is_phone_number(self, phone_number: str) -> bool:
        try:
            parsed_number = phonenumbers.parse(phone_number, region=None)
            return phonenumbers.is_valid_number(parsed_number)
        except phonenumbers.phonenumberutil.NumberParseException:
            return False

    def _is_valid_uuid(self, receiver_uuid: str) -> bool:
        try:
            uuid.UUID(str(receiver_uuid))
            return True  # noqa: TRY300
        except ValueError:
            return False

    def _is_username(self, receiver_username: str) -> bool:  # noqa: PLR0911
        """
        Check if username has correct format, as described in
        https://support.signal.org/hc/en-us/articles/6712070553754-Phone-Number-Privacy-and-Usernames#username_req
        Additionally, cannot have more than 9 digits and the digits cannot be 00.
        """
        split_username = receiver_username.split(".")
        if len(split_username) == 2:  # noqa: PLR2004
            characters = split_username[0]
            digits = split_username[1]
            if len(characters) < 3 or len(characters) > 32:  # noqa: PLR2004
                return False
            if not re.match(r"^[A-Za-z\d_]+$", characters):
                return False
            if len(digits) < 2 or len(digits) > 9:  # noqa: PLR2004
                return False
            try:
                digits = int(digits)
                if digits == 0:  # noqa: SIM103
                    return False
                return True  # noqa: TRY300
            except ValueError:
                return False
        else:
            return False

    def _is_group_id(self, group_id: str) -> bool:
        """Check if group_id has the right format, e.g.

              random string                                              length 66
              ↓                                                          ↓
        group.OyZzqio1xDmYiLsQ1VsqRcUFOU4tK2TcECmYt2KeozHJwglMBHAPS7jlkrm=
        ↑                                                                ↑
        prefix                                                           suffix
        """
        if group_id is None:
            return False

        return re.match(r"^group\.[a-zA-Z0-9]{59}=$", group_id)

    def _is_internal_id(self, internal_id: str) -> bool:
        if internal_id is None:
            return False
        return internal_id[-1] == "="

    def _get_group_by_name(self, group_name: str) -> dict[str, Any] | None:
        groups = self._groups_by_name.get(group_name)
        if groups is not None:
            if len(groups) > 1:
                error_msg = f"[Bot] There is more than one group named '{group_name}',"
                error_msg += " using the first one."
                self._logger.warning(error_msg)
            return groups[0]
        return None

    # see https://stackoverflow.com/questions/55184226/catching-exceptions-in-individual-tasks-and-restarting-them
    async def _rerun_on_exception(self, coro, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        """Restart coroutine by waiting an exponential time deplay"""
        max_sleep = 5 * 60  # sleep for at most 5 mins until rerun
        reset = 3 * 60  # reset after 3 minutes running successfully
        init_sleep = 1  # always start with sleeping for 1 second

        next_sleep = init_sleep
        while True:
            start_t = int(time.monotonic())  # seconds

            try:
                return await coro(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                traceback.print_exc()

            end_t = int(time.monotonic())  # seconds

            if end_t - start_t < reset:
                sleep_t = next_sleep
                next_sleep = min(max_sleep, next_sleep * 2)  # double sleep time
            else:
                next_sleep = init_sleep  # reset sleep time
                sleep_t = next_sleep

            self._logger.warning(f"Restarting coroutine in {sleep_t} seconds")  # noqa: G004
            await asyncio.sleep(sleep_t)

    async def _create_produce_consume_messages_tasks(
        self,
        producers: int = 1,
        consumers: int = 3,
    ) -> None:
        for task in itertools.chain(self._consume_tasks, self._produce_tasks):
            task.cancel()

        self._produce_tasks.clear()

        for n in range(1, producers + 1):
            produce_task = self._rerun_on_exception(self._produce, n)
            produce_task = asyncio.create_task(produce_task)
            self._store_reference_to_task(produce_task, self._produce_tasks)

        self._consume_tasks.clear()

        for n in range(1, consumers + 1):
            consume_task = self._rerun_on_exception(self._consume, n)
            consume_task = asyncio.create_task(consume_task)
            self._store_reference_to_task(consume_task, self._consume_tasks)

    async def _produce(self, name: int) -> None:
        self._logger.info(f"[Bot] Producer #{name} started")  # noqa: G004
        try:
            async for raw_message in self._signal.receive():
                self._logger.info(f"[Raw Message] {raw_message}")  # noqa: G004

                try:
                    message = await Message.parse(self._signal, raw_message)
                except UnknownMessageFormatError:
                    continue

                await self._process_updates(message)

                await self._ask_commands_to_handle(message)

        except ReceiveMessagesError as e:
            # TODO: retry strategy  # noqa: TD002, TD003
            raise SignalBotError(f"Cannot receive messages: {e}")  # noqa: B904, EM102, TRY003

    def _should_react_for_contact(
        self,
        message: Message,
        contacts: list[str] | bool,  # noqa: FBT001
        group_ids: list[str] | bool,  # noqa: FBT001
    ) -> bool:
        """Is the command activated for a certain chat or group?"""
        # Case 1: Private message
        if message.is_private():
            # a) registered for all numbers
            if isinstance(contacts, bool) and contacts:
                return True

            # b) whitelisted numbers
            if isinstance(contacts, list) and message.source in contacts:
                return True

        # Case 2: Group message
        if message.is_group():
            # a) registered for all groups
            if isinstance(group_ids, bool) and group_ids:
                return True

            # b) whitelisted group ids
            group_id = self._groups_by_internal_id.get(message.group, {}).get("id")
            if isinstance(group_ids, list) and group_id and group_id in group_ids:
                return True

        return False

    def _should_react_for_lambda(
        self,
        message: Message,
        f: Callable[[Message], bool] | None = None,
    ) -> bool:
        if f is None:
            return True

        return f(message)

    async def _ask_commands_to_handle(self, message: Message) -> None:
        for command, contacts, group_ids, f in self.commands:
            if not self._should_react_for_contact(message, contacts, group_ids):
                continue

            if not self._should_react_for_lambda(message, f):
                continue

            await self._q.put((command, message, time.perf_counter()))

    async def _consume(self, name: int) -> None:
        self._logger.info(f"[Bot] Consumer #{name} started")  # noqa: G004
        while True:
            try:
                await self._consume_new_item(name)
            except Exception:  # noqa: BLE001, PERF203, S112
                continue

    async def _consume_new_item(self, name: int) -> None:
        command, message, t = await self._q.get()
        now = time.perf_counter()
        self._logger.info(
            f"[Bot] Consumer #{name} got new job in {now - t:0.5f} seconds"  # noqa: G004
        )

        # handle Command
        try:
            context = Context(self, message)
            await command.handle(context)
        except Exception:
            self._logger.exception(f"[{command.__class__.__name__}]")  # noqa: G004
            raise

        # done
        self._q.task_done()


class SignalBotError(Exception):
    pass
