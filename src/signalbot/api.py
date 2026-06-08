from __future__ import annotations

import base64
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

import aiohttp
import websockets

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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
                    yield raw_message

        except Exception as e:
            raise ReceiveMessagesError from e

    async def send(  # noqa: C901, PLR0913
        self,
        receiver: str,
        message: str,
        *,
        base64_attachments: list | None = None,
        link_preview: dict[str, Any] | None = None,
        quote_author: str | None = None,
        quote_mentions: list | None = None,
        quote_message: str | None = None,
        quote_timestamp: int | None = None,
        mentions: list[dict[str, Any]] | None = None,
        text_mode: str | None = None,
        edit_timestamp: int | None = None,
        view_once: bool = False,
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.send_rest_uri()
        if base64_attachments is None:
            base64_attachments = []

        payload = {
            "base64_attachments": base64_attachments,
            "message": message,
            "number": self.phone_number,
            "recipients": [receiver],
        }
        headers = self._add_auth()

        if quote_author:
            payload["quote_author"] = quote_author
        if quote_mentions:
            payload["quote_mentions"] = quote_mentions
        if quote_message:
            payload["quote_message"] = quote_message
        if quote_timestamp:
            payload["quote_timestamp"] = quote_timestamp
        if mentions:
            payload["mentions"] = mentions
        if text_mode:
            payload["text_mode"] = text_mode
        if edit_timestamp:
            payload["edit_timestamp"] = edit_timestamp
        if link_preview:
            payload["link_preview"] = link_preview
        if view_once:
            payload["view_once"] = True

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
            KeyError,
        ) as exc:
            raise SendMessageError from exc

    async def poll(
        self,
        receiver: str,
        question: str,
        answers: list[str],
        *,
        allow_multiple_selections: bool = False,
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.poll_rest_uri()
        payload = {
            "recipient": receiver,
            "question": question,
            "answers": answers,
            "allow_multiple_selections": allow_multiple_selections,
        }
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
            KeyError,
        ) as exc:
            raise SendMessageError from exc

    async def react(
        self,
        recipient: str,
        reaction: str,
        target_author: str,
        timestamp: int,
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.react_rest_uri()
        payload = {
            "recipient": recipient,
            "reaction": reaction,
            "target_author": target_author,
            "timestamp": timestamp,
        }
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ReactionError from exc

    async def receipt(
        self,
        recipient: str,
        receipt_type: Literal["read", "viewed"],
        timestamp: int,
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.receipts_rest_uri()
        payload = {
            "recipient": recipient,
            "receipt_type": receipt_type,
            "timestamp": timestamp,
        }
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.post(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ReactionError from exc

    async def start_typing(self, receiver: str) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.typing_indicator_uri()
        payload = {
            "recipient": receiver,
        }
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.put(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise StartTypingError from exc

    async def stop_typing(self, receiver: str) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.typing_indicator_uri()
        payload = {
            "recipient": receiver,
        }
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.delete(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise StopTypingError from exc

    async def get_groups(self) -> list[dict[str, Any]]:
        uri = self._signal_api_uris.groups_uri()
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return await resp.json()
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise GroupsError from exc

    async def get_group(self, group_id: str) -> dict[str, Any]:
        uri = self._signal_api_uris.group_id_uri(group_id)
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return await resp.json()
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise GroupsError from exc

    async def get_attachment(self, attachment_id: str) -> str:
        uri = f"{self._signal_api_uris.attachment_rest_uri()}/{attachment_id}"
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

    async def delete_attachment(self, attachment_id: str) -> str:
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
        receiver: str,
        expiration_in_seconds: int | None = None,
        name: str | None = None,
    ) -> None:
        uri = self._signal_api_uris.contacts_uri()
        payload = {"recipient": receiver}
        headers = self._add_auth()

        if expiration_in_seconds is not None:
            payload["expiration_in_seconds"] = expiration_in_seconds

        if name is not None:
            payload["name"] = name

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.put(uri, json=payload)
                resp.raise_for_status()
                return resp
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise ContactUpdateError from exc

    async def update_group(
        self,
        group_id: str,
        base64_avatar: str | None = None,
        description: str | None = None,
        expiration_in_seconds: int | None = None,
        name: str | None = None,
    ) -> None:
        uri = self._signal_api_uris.group_id_uri(group_id)
        payload = {}
        headers = self._add_auth()

        if base64_avatar is not None:
            payload["base64_avatar"] = base64_avatar

        if description is not None:
            payload["description"] = description

        if expiration_in_seconds is not None:
            payload["expiration_time"] = expiration_in_seconds

        if name is not None:
            payload["name"] = name

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.put(uri, json=payload)
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

    async def get_signal_cli_about(self) -> dict[str, Any]:
        uri = self._signal_api_uris.about_rest_uri()
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(uri)
                resp.raise_for_status()
                return await resp.json()
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as exc:
            raise AboutError from exc

    async def get_signal_cli_rest_api_version(self) -> str:
        return (await self.get_signal_cli_about())["version"]

    async def get_signal_cli_rest_api_mode(self) -> str:
        return (await self.get_signal_cli_about())["mode"]

    async def remote_delete(
        self, receiver: str, timestamp: int
    ) -> aiohttp.ClientResponse:
        uri = self._signal_api_uris.remote_delete_uri()
        payload = {
            "recipient": receiver,
            "timestamp": timestamp,
        }
        headers = self._add_auth()

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.delete(uri, json=payload)
                resp.raise_for_status()
                return resp
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
