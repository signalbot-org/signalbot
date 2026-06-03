from __future__ import annotations

import base64
from typing import Protocol

class Authentication(Protocol):
    @property
    def header(self) -> str: ...

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
        credentials = base64.b64encode(f"{self.username}:{self.password}")
        return f"Basic {credentials}"
