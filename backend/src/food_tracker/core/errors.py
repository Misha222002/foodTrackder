from typing import Any

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any]
    requestId: str


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
