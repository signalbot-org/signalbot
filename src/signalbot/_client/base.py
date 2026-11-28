from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

import aiohttp
import aiohttp.http_exceptions

if TYPE_CHECKING:
    from signalbot.auth import Authentication
    from signalbot.errors import SignalAPIError


class ConnectionMode(StrEnum):
    """Protocol strategy for connecting to `signal-cli-rest-api`."""

    HTTPS_ONLY = "https_only"
    """Always use HTTPS/WSS."""
    HTTP_ONLY = "http_only"
    """Always use HTTP/WS."""
    AUTO = "auto"
    """Start with HTTPS/WSS and fallback to HTTP/WS if unavailable."""


HEALTH_CHECK_GOOD_STATUS = 204


class BaseURIs:
    def __init__(
        self, signal_service: str, phone_number: str, *, use_https: bool = True
    ) -> None:
        self.signal_service = signal_service
        self.phone_number = phone_number
        self._use_https = use_https

    @property
    def use_https(self) -> bool:
        return self._use_https

    @use_https.setter
    def use_https(self, use_https: bool) -> None:
        self._use_https = use_https

    @property
    def https_or_http(self) -> str:
        return "https" if self.use_https else "http"

    @property
    def wss_or_ws(self) -> str:
        return "wss" if self.use_https else "ws"

    def http_uri(self, path: str) -> str:
        return f"{self.https_or_http}://{self.signal_service}{path}"

    def ws_uri(self, path: str) -> str:
        return f"{self.wss_or_ws}://{self.signal_service}{path}"


class SectionURIs:
    """Base for a section's `*URIs` class: holds the shared `BaseURIs`."""

    def __init__(self, base: BaseURIs) -> None:
        self._base = base


UrisT = TypeVar("UrisT", bound=SectionURIs)

_TRANSPORT_ERRORS: tuple[type[Exception], ...] = (
    aiohttp.ClientError,
    aiohttp.http_exceptions.HttpProcessingError,
)

HttpVerb = Literal["get", "post", "put", "delete"]


class SessionManager:
    """Lazily creates and shares a single `aiohttp.ClientSession` across all
    section clients of a `SignalAPI` instance, so requests reuse connections
    instead of opening a new session per call.

    The session is created on first use (inside a coroutine, as aiohttp
    requires) and lives until `close()` is called.
    """

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def get(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
        self._session = None


class BaseClient(Generic[UrisT]):
    """Shared HTTP helpers for a `signal-cli-rest-api` section client.

    Generic over its section's `*URIs` type (e.g. `ContactsClient` holds a
    `ContactsURIs`).
    """

    def __init__(
        self, uris: UrisT, auth: Authentication | None, sessions: SessionManager
    ) -> None:
        self._uris = uris
        self._auth = auth
        self._sessions = sessions

    def _add_auth(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._auth is not None:
            self._auth.write_header(headers)
        return headers

    async def _request(
        self,
        verb: HttpVerb,
        uri: str,
        *,
        error_cls: type[SignalAPIError],
        payload: str | None = None,
    ) -> aiohttp.ClientResponse:
        """Issue a request and raise `error_cls` on any transport failure."""
        headers = self._add_auth()
        session = await self._sessions.get()
        try:
            method = getattr(session, verb)
            resp: aiohttp.ClientResponse = await method(
                uri, headers=headers, data=payload
            )
            resp.raise_for_status()
        except _TRANSPORT_ERRORS as exc:
            raise error_cls(str(exc)) from exc
        else:
            return resp
