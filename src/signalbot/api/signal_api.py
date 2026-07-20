from __future__ import annotations

import base64
from enum import Enum
from typing import TYPE_CHECKING

import aiohttp
import websockets

from signalbot.api.generated import (
    About,
    CreatePollResponse,
    GroupEntry,
    RemoteDeleteResponse,
    SendMessageResponse,
    SendMessageV2,
)
from signalbot.api.requests.send_message import await_items_in_payload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from signalbot.api.generated import (
        Attachment,
        CreatePollRequest,
        RemoteDeleteRequest,
    )
    from signalbot.api.generated.api import (
        Receipt,
        SendReactionRequest,
        TypingIndicatorRequest,
    )
    from signalbot.api.requests import (
        UpdateContactRequest,
        UpdateGroupRequest,
    )
    from signalbot.api.requests.send_message import (
        SendMessage,
        SendMessageMultiple,
    )
    from signalbot.auth import Authentication


class ConnectionMode(str, Enum):
    """Protocol strategy for connecting to `signal-cli-rest-api`.

    Attributes:
        HTTPS_ONLY: Always use HTTPS/WSS.
        HTTP_ONLY: Always use HTTP/WS.
        AUTO: Start with HTTPS/WSS and fallback to HTTP/WS if unavailable.
    """

    HTTPS_ONLY = "https_only"
    HTTP_ONLY = "http_only"
    AUTO = "auto"


HEALTH_CHECK_GOOD_STATUS = 204


class SignalAPI:
    def __init__(  # noqa: ANN204
        self,
        signal_service: str,
        phone_number: str,
        auth: Authentication | None = None,
        download_attachments: bool = True,  # noqa: FBT001, FBT002
        connection_mode: ConnectionMode = ConnectionMode.AUTO,
    ):
        self.phone_number = phone_number
        self.auth = auth
        self.connection_mode = connection_mode
        use_https = connection_mode in (ConnectionMode.HTTPS_ONLY, ConnectionMode.AUTO)
        self._signal_api_uris = SignalAPIURIs(
            signal_service=signal_service,
            phone_number=phone_number,
            use_https=use_https,
        )
        self.download_attachments = download_attachments

    async def receive(self) -> AsyncIterator[str]:
        headers = self._add_auth()

        try:
            uri = self._signal_api_uris.receive_ws_uri()
            self.connection = websockets.connect(
                uri, ping_interval=None, additional_headers=headers
            )
            async with self.connection as websocket:
                async for raw_message in websocket:
                    yield str(raw_message)

        except Exception as e:
            raise ReceiveMessagesError from e

    async def send(
        self,
        data_message: SendMessage | SendMessageMultiple,
    ) -> SendMessageResponse:
        uri = self._signal_api_uris.send_rest_uri()

        data_message.number = self.phone_number
        payload = data_message.model_dump(
            exclude_none=True,
            by_alias=True,
            context={"mode": "sendv2"},
        )
        await await_items_in_payload(payload)

        # Sanity check the custom model_dump before sending it using
        # the original request type
        SendMessageV2.model_validate(payload)

        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, json=payload)
                resp.raise_for_status()
                return SendMessageResponse.model_validate(await resp.json())
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
            KeyError,
        ) as exc:
            raise SendMessageError from exc

    async def poll(
        self,
        create_poll_request: CreatePollRequest,
    ) -> CreatePollResponse:
        uri = self._signal_api_uris.poll_rest_uri()
        payload = create_poll_request.model_dump_json(exclude_none=True, by_alias=True)
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, data=payload)
                resp.raise_for_status()
                return CreatePollResponse.model_validate(await resp.json())
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
            KeyError,
        ) as exc:
            raise SendMessageError from exc

    async def react(
        self,
        reaction_request: SendReactionRequest,
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.react_rest_uri()
        payload = reaction_request.model_dump_json(exclude_none=True, by_alias=True)
        headers = self._add_auth()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, data=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ReactionError from exc

    async def receipt(self, receipt_request: Receipt) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.receipts_rest_uri()
        payload = receipt_request.model_dump_json(exclude_none=True, by_alias=True)
        headers = self._add_auth()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, data=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ReactionError from exc

    async def start_typing(
        self, typing_request: TypingIndicatorRequest
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.typing_indicator_uri()
        payload = typing_request.model_dump_json(exclude_none=True, by_alias=True)
        headers = self._add_auth()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.put(uri, data=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise StartTypingError from exc

    async def stop_typing(
        self, typing_request: TypingIndicatorRequest
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.typing_indicator_uri()
        payload = typing_request.model_dump_json(exclude_none=True, by_alias=True)
        headers = self._add_auth()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.delete(uri, data=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise StopTypingError from exc

    async def get_groups(self) -> list[GroupEntry]:
        uri = self._signal_api_uris.groups_uri()
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return [GroupEntry.model_validate(group) for group in await resp.json()]
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise GroupsError from exc

    async def get_group(self, group_id: str) -> GroupEntry:
        uri = self._signal_api_uris.group_id_uri(group_id)
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return GroupEntry.model_validate(await resp.json())
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise GroupsError from exc

    async def download_attachment(self, attachment: Attachment) -> str:
        uri = (
            f"{self._signal_api_uris.attachment_rest_uri()}/{attachment.local_filename}"
        )
        headers = self._add_auth()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                content = await resp.content.read()
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise GetAttachmentError from exc

        base64_bytes = base64.b64encode(content)
        base64_string = str(base64_bytes, encoding="utf-8")

        return base64_string  # noqa: RET504

    async def delete_attachment(self, attachment: Attachment) -> str:
        attachment_id = attachment.local_filename
        if attachment_id is None:
            error_msg = "Attachment has no local filename"
            raise ValueError(error_msg)

        uri = f"{self._signal_api_uris.attachment_rest_uri()}/{attachment_id}"
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.delete(uri)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise GetAttachmentError from exc

    async def update_contact(
        self,
        update_contact_request: UpdateContactRequest,
    ) -> None:
        uri = self._signal_api_uris.contacts_uri()
        payload = update_contact_request.model_dump_json(
            exclude_none=True, by_alias=True
        )
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.put(uri, data=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ContactUpdateError from exc

    async def update_group(self, update_group_request: UpdateGroupRequest) -> None:
        uri = self._signal_api_uris.group_id_uri(update_group_request.group_id_or_name)
        payload = update_group_request.model_dump_json(exclude_none=True, by_alias=True)
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.put(uri, data=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ContactUpdateError from exc

    async def health_check(self) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.health_check_uri()
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise HealthCheckError from exc

    async def _is_signal_service_available(self) -> bool:
        try:
            return (await self.health_check()).status == HEALTH_CHECK_GOOD_STATUS
        except HealthCheckError:
            return False

    async def check_signal_service(self) -> bool:
        if self.connection_mode != ConnectionMode.AUTO:
            # use_https is already set according to the connection mode
            return await self._is_signal_service_available()

        self._signal_api_uris.use_https = True
        if await self._is_signal_service_available():
            return True

        self._signal_api_uris.use_https = False
        return await self._is_signal_service_available()

    async def get_signal_cli_about(self) -> About:
        uri = self._signal_api_uris.about_rest_uri()
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return About.model_validate(await resp.json())
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise AboutError from exc

    async def remote_delete(
        self, remote_delete_request: RemoteDeleteRequest
    ) -> RemoteDeleteResponse:
        uri = self._signal_api_uris.remote_delete_uri()
        payload = remote_delete_request.model_dump_json(
            exclude_none=True, by_alias=True
        )
        headers = self._add_auth()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.delete(uri, data=payload)
                resp.raise_for_status()
                return RemoteDeleteResponse.model_validate(await resp.json())
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise RemoteDeleteError from exc

    def _add_auth(self, headers: dict[str, str] | None = None) -> dict[str]:
        if headers is None:
            headers = {}
        if self.auth is not None:
            self.auth.write_header(headers)
        return headers


class SignalAPIURIs:
    def __init__(self, signal_service: str, phone_number: str, use_https: bool = True):  # noqa: ANN204, FBT001, FBT002
        self.signal_service = signal_service
        self.phone_number = phone_number
        self.use_https = use_https

    @property
    def https_or_http(self) -> str:
        return "https" if self.use_https else "http"

    @property
    def wss_or_ws(self) -> str:
        return "wss" if self.use_https else "ws"

    def attachment_rest_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/attachments"

    def receive_ws_uri(self) -> str:
        return (
            f"{self.wss_or_ws}://{self.signal_service}/v1/receive/{self.phone_number}"
        )

    def send_rest_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v2/send"

    def poll_rest_uri(self) -> str:
        return (
            f"{self.https_or_http}://{self.signal_service}/v1/polls/{self.phone_number}"
        )

    def react_rest_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/reactions/{self.phone_number}"

    def typing_indicator_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/typing-indicator/{self.phone_number}"

    def groups_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/groups/{self.phone_number}"

    def group_id_uri(self, group_id: str) -> str:
        return self.groups_uri() + "/" + group_id

    def contacts_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/contacts/{self.phone_number}"

    def health_check_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/health"

    def receipts_rest_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/receipts/{self.phone_number}"

    def remote_delete_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/remote-delete/{self.phone_number}"

    def about_rest_uri(self) -> str:
        return f"{self.https_or_http}://{self.signal_service}/v1/about"


class ReceiveMessagesError(Exception):
    pass


class SendMessageError(Exception):
    pass


class TypingError(Exception):
    pass


class StartTypingError(TypingError):
    pass


class StopTypingError(TypingError):
    pass


class ReactionError(Exception):
    pass


class GroupsError(Exception):
    pass


class GetAttachmentError(Exception):
    pass


class ContactUpdateError(Exception):
    pass


class HealthCheckError(Exception):
    pass


class RemoteDeleteError(Exception):
    pass


class SignalServiceConnectionError(Exception):
    pass


class AboutError(Exception):
    pass
