from . import parsing, core
from http import HTTPStatus
from collections.abc import Callable
from pathlib import Path

import socket
import threading

type RouteHandler = Callable[[core.HttpRequest], core.HttpResponse]
type ErrorHandler = Callable[[], bytes]
type Deco = Callable[[RouteHandler], RouteHandler]


class HttpServer:
    """
    ### Description
    A class that represent a simple http web server.

    ### Methods
    - **run**: starts listening for connections forever until a keyboard interrupt is detected.
    - **add_route_handler**: Adds a handler for the given route.
    - **add_error_handler**: Adds a handler for the given error code.
    - **error_handler**: Decorator for error handler.
    - **route_handler**: Decorator for route handler.
    - **set_static_root**: Sets the root for the static dir.
    """

    SOCK_TYPE = socket.SOCK_STREAM
    ADDRESS_FAM = socket.AF_INET
    TRANSPORT_PROTO = socket.IPPROTO_TCP
    BACKLOG = 100

    LOCALHOST = "127.0.0.1"
    NOT_LOCALHOST = "0.0.0.0"

    def __init__(self, port: int, is_localhost: bool = False):
        self.address = (self.LOCALHOST if  is_localhost else self.NOT_LOCALHOST, port)

        self.listener_sock = socket.socket(self.ADDRESS_FAM, self.SOCK_TYPE, self.TRANSPORT_PROTO)
        self.listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_sock.bind(self.address)
        self.listener_sock.listen(self.BACKLOG)

        self.static_prefix = ""
        self.static_path = None

        self.thread_pool: list[threading.Thread] = []

        self.route_handlers: dict[str, RouteHandler] = {}
        self.error_handlers: dict[HTTPStatus, ErrorHandler] = {
            HTTPStatus.BAD_REQUEST: lambda: b"",
            HTTPStatus.FORBIDDEN: lambda: b"",
            HTTPStatus.NOT_FOUND: lambda: b""
        }

    def run(self):
        print(f"Listening on {self.address}")
        try:
            while True:
                new_thread = threading.Thread(None, self._client_handler,
                                              args=self.listener_sock.accept())
                new_thread.daemon = True
                new_thread.start()
                
                self.thread_pool.append(new_thread)
        except KeyboardInterrupt:
            print("CTRL+C pressed.")

            for t in self.thread_pool:
                t.join()
            
            self.listener_sock.shutdown(0)
            self.listener_sock.close()

    def _client_handler(self, connection: socket.socket, addr: tuple[str, int]):
        connection.settimeout(0.1)
        buffered_wrapper = connection.makefile("rb")

        print(f"Connection from {addr}")

        #### Get request
        request = core.HttpRequest()
        match parsing.parse_request(buffered_wrapper, request):
            case core.HttpResult.OK:
                buffered_wrapper.close()
            case core.HttpResult.MALFORMED_REQUEST | core.HttpResult.PARTIAL_REQUEST:
                body = self.error_handlers[HTTPStatus.BAD_REQUEST]()
                connection.close()
                buffered_wrapper.close()
                return

        #### Handle request
        response: core.HttpResponse = core.HttpResponse(b"", HTTPStatus.OK)

        # Handle static resource.
        if request.resource.startswith(self.static_prefix):
            header, body = b"", b""
            try:
                path = Path.joinpath(
                    self.static_path, request.resource[len(self.static_prefix)+1:] # type: ignore
                ).resolve().relative_to(self.static_path) # type: ignore
                
                response.code = HTTPStatus.OK
                response.body = path.read_bytes()
            except FileNotFoundError:
                response.code = HTTPStatus.NOT_FOUND
                response.body = self.error_handlers[HTTPStatus.NOT_FOUND]()                
            except ValueError:
                response.code = HTTPStatus.FORBIDDEN                
                response.body = self.error_handlers[HTTPStatus.FORBIDDEN]()
            finally:
                header, body = response.to_bytes()
                connection.sendall(header + body)
                connection.close()
                return

        handler: RouteHandler | None = self.route_handlers.get(request.resource, None)

        if handler == None:
            response.code = HTTPStatus.NOT_FOUND
            response.body = self.error_handlers[HTTPStatus.NOT_FOUND]()                
        else:
            response = handler(request)

        #### Send response
        header, body = response.to_bytes()
        connection.sendall(header + body)
        connection.close()

    def add_route_handler(self, route: str, handler: RouteHandler):
        self.route_handlers[route] = handler

    def add_error_handler(self, code: HTTPStatus, handler: ErrorHandler):
        if not code.is_server_error or not code.is_client_error:
            # TODO Add error handling
            pass

        self.error_handlers[code] = handler

    def set_static_root(self, prefix: str, path: str):
        self.static_path = Path(path).resolve()
        self.static_prefix = prefix

    def route_handler(self, route: str) -> Deco:
        def decorator(f: RouteHandler) -> RouteHandler:
            self.add_route_handler(route, f)
            return f

        return decorator

    def error_handler(self, code: HTTPStatus):
        def decorator(f: ErrorHandler):
            self.add_error_handler(code, f)
            return f

        return decorator
