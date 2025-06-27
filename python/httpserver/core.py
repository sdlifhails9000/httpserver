from http import HTTPStatus, HTTPMethod # I'm not writing every single method, reason phrase and code down.
from enum import Enum


class HttpResult(Enum):
    OK = 1
    MALFORMED_REQUEST = 2
    PARTIAL_REQUEST = 3

class HttpResponse:
    def __init__(self, body: bytes, code: HTTPStatus, fields: dict[str, str] = {}):
        self.version = { "major": 1, "minor": 1 }
        self.code: HTTPStatus = code
        self.fields = fields
        self.body = body

    def to_bytes(self) -> tuple[bytes, bytes]:
        header = f"HTTP/{self.version['major']}.{self.version['minor']} {self.code.value} {self.code.phrase}\r\n"
        
        for key, value in self.fields.items():
            header += f"{key}: {value}\r\n"

        header += "\r\n"

        return header.encode("iso-8859-1"), self.body

class HttpRequest:
    def __init__(self):
        self.method = HTTPMethod.GET
        self.resource = ""
        self.version = { "major": 1, "minor": 1 }
        self.fields: dict[str, str] = {}
        self.body = bytes()

    def to_bytes(self) -> tuple[bytes, bytes]:
        header = f"{self.method.name} {self.resource} HTTP/{self.version['major']}.{self.version['minor']}\r\n"

        for key, value in self.fields.items():
            header += f"{key}: {value}\r\n"

        header += "\r\n"

        return header.encode("iso-8859-1"), self.body
