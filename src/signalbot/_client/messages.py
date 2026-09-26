from __future__ import annotations

from typing import TYPE_CHECKING

import websockets

from signalbot._client.base import BaseClient, SectionURIs
from signalbot._generated import RemoteDeleteResponse, SendMessageResponse
from signalbot.errors import SignalAPIError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import aiohttp

    from signalbot._generated import (
        RemoteDeleteRequest,
        SendMessageV2,
        TypingIndicatorRequest,
    )


class MessagesURIs(SectionURIs):
    def receive_ws_uri(self) -> str:
        return self._base.ws_uri(f"/v1/receive/{self._base.phone_number}")

    def send_uri(self) -> str:
        return self._base.http_uri("/v2/send")

    def typing_indicator_uri(self) -> str:
        return self._base.http_uri(f"/v1/typing-indicator/{self._base.phone_number}")

    def remote_delete_uri(self) -> str:
        return self._base.http_uri(f"/v1/remote-delete/{self._base.phone_number}")


class MessagesClient(BaseClient[MessagesURIs]):
    async def receive(self) -> AsyncIterator[str]:
        headers = self._add_auth()

        try:
            uri = self._uris.receive_ws_uri()
            self.connection = websockets.connect(uri, additional_headers=headers)
            async with self.connection as websocket:
                async for raw_message in websocket:
                    yield str(raw_message)

        except Exception as e:
            raise ReceiveError(str(e)) from e

    async def send(
        self,
        data_message: SendMessageV2,
    ) -> SendMessageResponse:
        uri = self._uris.send_uri()
        payload = data_message.model_dump_json(exclude_none=True, by_alias=True)
        resp = await self._request("post", uri, error_cls=SendError, payload=payload)
        response = await resp.json()
        if isinstance(response, list):
            # Newer API versions wrap the shared send timestamp in an array.
            if len(response) != 1:
                msg = f"Expected exactly one send timestamp, got {len(response)}"
                raise SendError(msg)
            response = response[0]
        return SendMessageResponse.model_validate(response)

    async def start_typing(
        self, typing_request: TypingIndicatorRequest
    ) -> aiohttp.ClientResponse:
        uri = self._uris.typing_indicator_uri()
        payload = typing_request.model_dump_json(exclude_none=True, by_alias=True)
        return await self._request(
            "put", uri, error_cls=StartTypingError, payload=payload
        )

    async def stop_typing(
        self, typing_request: TypingIndicatorRequest
    ) -> aiohttp.ClientResponse:
        uri = self._uris.typing_indicator_uri()
        payload = typing_request.model_dump_json(exclude_none=True, by_alias=True)
        return await self._request(
            "delete", uri, error_cls=StopTypingError, payload=payload
        )

    async def remote_delete(
        self, remote_delete_request: RemoteDeleteRequest
    ) -> RemoteDeleteResponse:
        uri = self._uris.remote_delete_uri()
        payload = remote_delete_request.model_dump_json(
            exclude_none=True, by_alias=True
        )
        resp = await self._request(
            "delete", uri, error_cls=RemoteDeleteError, payload=payload
        )
        return RemoteDeleteResponse.model_validate(await resp.json())


class ReceiveError(SignalAPIError):
    """Raised when the receive websocket connection fails or is interrupted."""


class SendError(SignalAPIError):
    """Raised when the API rejects a message send request."""


class TypingError(SignalAPIError):
    """Base class for errors updating a typing indicator."""


class StartTypingError(TypingError):
    """Raised when the API rejects a request to start a typing indicator."""


class StopTypingError(TypingError):
    """Raised when the API rejects a request to stop a typing indicator."""


class RemoteDeleteError(SignalAPIError):
    """Raised when the API rejects a remote-delete request."""
