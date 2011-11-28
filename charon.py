#!/usr/bin/env python
# coding: utf-8

import re
import http.client
import logging

logging.basicConfig(level=logging.DEBUG)

from tornado.httputil import HTTPHeaders
from tornado import httpserver, httpclient, ioloop
from tornado.options import define, options, parse_command_line



define("port", default=8888, help="run on the given port", type=int)


def httprequest_repr(self):
    args = ",".join("%s=%r" % i for i in self.__dict__.items())
    return "%s(%s)" % (self.__class__.__name__, args)

httpclient.HTTPRequest.__repr__ = httprequest_repr

fetch = httpclient.AsyncHTTPClient(
    max_clients=1000
).fetch


ignored_client_headers = set([
    "Accept-Encoding",
    "Proxy-Connection",
])

ignored_headers = set([
    "Content-Encoding",
    "Transfer-Encoding",
    "Vary",
])


def clean_uri(request):
    proxy_uri_prefix = 'http://' + request.host + '/'
    if request.uri.lower().startswith(proxy_uri_prefix.lower()):
        uri = request.uri[len(proxy_uri_prefix):]
    else:
        uri = request.uri
    return uri.lstrip('/')


class DefaultHandler:

    def __init__(self, request):

        self.request = request

        url = request.protocol + '://' + request.host + '/' + clean_uri(request)

        logging.info("%d - got request - %s %s", id(self), request.method, url)

        headers = HTTPHeaders()

        for i in request.headers.keys():
            if i not in ignored_client_headers:
                headers[i] = request.headers[i]

        req = httpclient.HTTPRequest(
            url, method=request.method, headers=headers,
            body=request.body, allow_nonstandard_methods=True,
            follow_redirects=False,
            request_timeout=600.,
            connect_timeout=600.
        )

        logging.debug("Sending request: %s", req)

        fetch(req, callback=self.on_fetch)

    def on_fetch(self, response):

        logging.debug("Got response: %s", response)

        self.response = response

        if response.code not in http.client.responses:
            resp = "HTTP/1.1 %d %s" % (500, http.client.responses[500])
            self.request.write(resp.encode('ascii'))
        else:
            self.request.write(self.compose_response())
        self.request.finish()
        logging.info("%d - finished request", id(self))

    def compose_response(self):

        headers = HTTPHeaders()

        for i in self.response.headers:
            if i not in ignored_headers:
                headers[i] = self.response.headers[i]

        if self.response.body is not None:
            headers['Content-Length'] = str(len(self.response.body))

        lines = []

        lines.append("HTTP/1.1 %d %s" % (
            self.response.code,
            http.client.responses[self.response.code]
        ))

        for k, v in headers.get_all():
            lines.append(k + ": " + v)

        head = "\r\n".join(lines) + "\r\n\r\n"
        head = head.encode("ascii")

        if isinstance(self.response.body, bytes):
            return head + self.response.body
        else:
            assert self.response.body is None
            return head


class Rule:

    def __init__(self, handler, host=r'.*', uri=r'.*', methods=['GET', 'POST', 'PUT', 'DELETE']):
        self.handler = handler
        self.host = re.compile(host)
        self.methods = set(methods)
        self.uri = re.compile(uri)

    def check(self, request):
        if self.host.match(request.host) is None:
            return False
        if request.method not in self.methods:
            return False
        return self.uri.match(clean_uri(request)) is not None

rules = [Rule(DefaultHandler)]

try:
    from custom_rules import custom_rules
    rules = custom_rules + rules
except ImportError:
    pass


def handle_request(request):
    logging.debug("Got request: %s", request)
    for rule in rules:
        if rule.check(request):
            rule.handler(request)
            break


if __name__ == "__main__":
    parse_command_line()
    http_server = httpserver.HTTPServer(handle_request)
    http_server.listen(options.port)
    ioloop.IOLoop.instance().start()
