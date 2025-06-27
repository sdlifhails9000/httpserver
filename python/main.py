from http import HTTPStatus

import httpserver

server = httpserver.HttpServer(1234)
server.set_static_root("/static", "./static")

@server.route_handler("/")
def index(_: httpserver.HttpRequest) -> httpserver.HttpResponse:
    f = open("index.html", "rb")
    content = f.read()
    print(content)
    return httpserver.HttpResponse(content, HTTPStatus.OK)

@server.route_handler("/hello")
def hello(_: httpserver.HttpRequest) -> httpserver.HttpResponse:
    return httpserver.HttpResponse(b"bruh" , HTTPStatus.OK)

@server.error_handler(HTTPStatus.NOT_FOUND)
def notfound() -> bytes:
    return b"<h1>Not<br>Found</h1>"

server.run()
