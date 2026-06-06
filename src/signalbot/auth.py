from __future__ import annotations

import base64
from typing import Protocol

class Authentication(Protocol):
    @property
    def header(self) -> str: ...

    def write_header(self, headers: Dict[string, string]):
        headers["Authorization"] = self.header

class BasicAuthentication:
    def __init__(
        self,
        username: str,
        password: str,
    ):
        self.username = username
        self.password = password

    @property
    def header(self) -> str:
        credential_bytes = base64.b64encode(f"{self.username}:{self.password}")
        credential_string = str(credential_bytes, encoding="utf-8")
        return f"Basic {credential_string}"

class BearerAuthentication:
    def __init__(
        self,
        token: str,
    ):
        self.token = token

    @property
    def header(self) -> str:
        return f"Bearer {self.token}"
