from __future__ import annotations

import base64
from typing import Protocol


class Authentication(Protocol):
    @property
    def header(self) -> str: ...

    def write_header(self, headers: dict[str, str]) -> None:
        headers["Authorization"] = self.header


class BasicAuthentication(Authentication):
    def __init__(
        self,
        username: str,
        password: str,
    ) -> None:
        self.username = username
        self.password = password

    @property
    def header(self) -> str:
        credentials = f"{self.username}:{self.password}".encode()
        credential_string = base64.b64encode(credentials).decode("utf-8")
        return f"Basic {credential_string}"


class BearerAuthentication(Authentication):
    def __init__(
        self,
        token: str,
    ) -> None:
        self.token = token

    @property
    def header(self) -> str:
        return f"Bearer {self.token}"
