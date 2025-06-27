from httpserver.core import HttpRequest, HttpResult
from http import HTTPMethod
from io import BufferedReader
from enum import Enum
from socket import error, timeout

class RequestLineState(Enum):
    BEGIN = 1
    METHOD = 2
    SPACE_BEFORE_RESOURCE = 3
    RESOURCE = 4
    SPACE_AFTER_RESOURCE = 5
    H = 6
    HT = 7
    HTT = 8
    HTTP = 9
    BEFORE_VERSION = 10
    MAJOR_VERSION = 11
    AFTER_MAJOR = 12
    MINOR_VERSION = 13
    SPACE_AFTER_VERSION = 14
    ALMOST_DONE = 15

class FieldState(Enum):
    BEGIN = 1
    KEY = 2
    COLON = 3
    VALUE = 4
    NEXT_FIELD = 5
    ALMOST_DONE = 6

def parse_request(reader: BufferedReader, request: HttpRequest) -> HttpResult:
    body = bytearray()

    ### Parse request line.
    if (result := _parse_request_line(reader, request)) != HttpResult.OK:
        return result

    ### Parse fields
    if (result := _parse_fields(reader, request)) != HttpResult.OK:
        return result

    ### Get body
    while True:
        try:
            data = reader.read(8192)
            if not data:
                break

            body += data
        except (timeout, error):
            break

    request.body = bytes(body)

    return HttpResult.OK


def _parse_request_line(reader: BufferedReader, request: HttpRequest) -> HttpResult:
    state = RequestLineState.BEGIN
    buffer = bytearray()
    total_read = 0
    MAX_REQUEST_LINE = 8192

    while True:
        c = None
        try:
            c = reader.read(1)
            if not c:
                return HttpResult.PARTIAL_REQUEST
        except (timeout, error):
            return HttpResult.PARTIAL_REQUEST

        total_read += 1
        if total_read > MAX_REQUEST_LINE:
            print("Massive request line.")
            return HttpResult.MALFORMED_REQUEST

        match state:
            case RequestLineState.BEGIN:
                if not c.isalpha():
                    return HttpResult.MALFORMED_REQUEST
                
                buffer += c
                state = RequestLineState.METHOD
            
            case RequestLineState.METHOD:
                if c == b" ":
                    state = RequestLineState.SPACE_BEFORE_RESOURCE

                    method_str = buffer.decode("ascii")

                    if method_str not in HTTPMethod.__members__:
                        return HttpResult.MALFORMED_REQUEST

                    request.method = HTTPMethod[method_str]
                    buffer.clear()
                    continue

                if not c.isalpha():
                    return HttpResult.MALFORMED_REQUEST
                
                buffer += c
            
            case RequestLineState.SPACE_BEFORE_RESOURCE:
                if c != b"/":
                    return HttpResult.MALFORMED_REQUEST
                
                buffer += c
                state = RequestLineState.RESOURCE
            
            case RequestLineState.RESOURCE:
                if c == b" ":
                    state = RequestLineState.SPACE_AFTER_RESOURCE
                    request.resource = buffer.decode("ascii")
                    buffer.clear()
                    continue

                buffer += c
            
            case RequestLineState.SPACE_AFTER_RESOURCE:
                if c != b"H":
                    return HttpResult.MALFORMED_REQUEST
                
                state = RequestLineState.H
            
            case RequestLineState.H:
                if c != b"T":
                    return HttpResult.MALFORMED_REQUEST
                
                state = RequestLineState.HT
            
            case RequestLineState.HT:
                if c != b"T":
                    return HttpResult.MALFORMED_REQUEST
                
                state = RequestLineState.HTT

            case RequestLineState.HTT:
                if c != b"P":
                    return HttpResult.MALFORMED_REQUEST
                
                state = RequestLineState.HTTP

            case RequestLineState.HTTP:
                if c != b"/":
                    return HttpResult.MALFORMED_REQUEST
                
                state = RequestLineState.BEFORE_VERSION
            
            case RequestLineState.BEFORE_VERSION:
                if not c.isdigit():
                    return HttpResult.MALFORMED_REQUEST

                buffer += c
                state = RequestLineState.MAJOR_VERSION

            case RequestLineState.MAJOR_VERSION:
                if c == b".":
                    state = RequestLineState.AFTER_MAJOR
                    request.version["major"] = int(buffer.decode("ascii"))
                    buffer.clear()
                    continue

                if not c.isdigit():
                    return HttpResult.MALFORMED_REQUEST
                
                buffer += c

            case RequestLineState.AFTER_MAJOR:
                if not c.isdigit():
                    return HttpResult.MALFORMED_REQUEST

                buffer += c
                state = RequestLineState.MINOR_VERSION

            case RequestLineState.MINOR_VERSION:
                if c == b" ":
                    state = RequestLineState.SPACE_AFTER_VERSION
                    request.version["minor"] = int(buffer.decode("ascii"))
                    buffer.clear()
                    continue
                elif c == b"\r":
                    state = RequestLineState.ALMOST_DONE
                    request.version["minor"] = int(buffer.decode("ascii"))
                    buffer.clear()
                    continue
                
                if not c.isdigit():
                    return HttpResult.MALFORMED_REQUEST

                buffer += c

            case RequestLineState.SPACE_AFTER_VERSION:
                if c == b" ":
                    continue
                
                if c == b"\r":
                    state = RequestLineState.ALMOST_DONE
                else:
                    return HttpResult.MALFORMED_REQUEST

            case RequestLineState.ALMOST_DONE:
                if c == b"\n":
                    return HttpResult.OK
                else:
                    return HttpResult.MALFORMED_REQUEST

            case _:
                assert False, f"Invalid or unhandled request line state: {state}"


def _parse_fields(reader: BufferedReader, request: HttpRequest) -> HttpResult:
    state = FieldState.BEGIN
    key_buffer = bytearray()
    value_buffer = bytearray()    
    total_read = 0
    MAX_FIELD = 8192

    while True:
        c = None
        try:
            c = reader.read(1)
            if not c:
                return HttpResult.PARTIAL_REQUEST
        except (timeout, error):
            return HttpResult.PARTIAL_REQUEST
        
        total_read += 1
        if total_read > MAX_FIELD:
            print("Massive field.")
            return HttpResult.MALFORMED_REQUEST

        match state:
            case FieldState.BEGIN:
                if c == b"\r":
                    state = FieldState.ALMOST_DONE
                    continue

                if not _is_valid_field_name_char(c.decode("ascii")):
                    return HttpResult.MALFORMED_REQUEST
                
                key_buffer += c
                state = FieldState.KEY

            case FieldState.KEY:
                if c == b":":
                    state = FieldState.COLON
                    continue
                
                if not _is_valid_field_name_char(c.decode("ascii")):
                    return HttpResult.MALFORMED_REQUEST

                key_buffer += c
            
            case FieldState.COLON:
                if not _is_valid_field_value_char(c.decode("ascii")):
                    return HttpResult.MALFORMED_REQUEST

                value_buffer += c
                state = FieldState.VALUE

            case FieldState.VALUE:
                if c == b"\r":
                    state = FieldState.NEXT_FIELD
                    continue

                if not _is_valid_field_value_char(c.decode("ascii")):
                    return HttpResult.MALFORMED_REQUEST

                value_buffer += c

            case FieldState.NEXT_FIELD:
                if c != b"\n":
                    return HttpResult.MALFORMED_REQUEST
                
                state = FieldState.BEGIN

                request.fields[key_buffer.decode("ascii").lower()] = value_buffer.decode("ascii").strip()
                key_buffer.clear()
                value_buffer.clear()

            case FieldState.ALMOST_DONE:
                if c != b"\n":
                    return HttpResult.MALFORMED_REQUEST

                return HttpResult.OK

def _is_valid_field_name_char(c: str) -> bool:
    return c.isalnum() or c in "!#$%&'*+-.^_`|~"

def _is_valid_field_value_char(c: str) -> bool:
    code = ord(c)
    return (code == 9 or  # HTAB
            code == 32 or  # Space
            (0x21 <= code <= 0x7E) or  # Printable ASCII
            (0x80 <= code <= 0xFF))  # obs-text
