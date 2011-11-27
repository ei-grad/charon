#!/usr/bin/env python
# coding: utf-8

import logging
from functools import partial
import http.client

from tornado.httputil import HTTPHeaders

HTTPHeaders._normalize_name = lambda x: x

from tornado import httpserver, httpclient, ioloop


def httprequest_repr(self):
    args = ",".join("%s=%r" % i for i in self.__dict__.items())
    return "%s(%s)" % (self.__class__.__name__, args)

httpclient.HTTPRequest.__repr__ = httprequest_repr

logging.basicConfig(level=logging.DEBUG)

fetch = httpclient.AsyncHTTPClient().fetch


def handle_request(request):
    logging.info("Got request: %s", request)
    url = request.protocol + '://' + request.host
    proxy_uri_prefix = 'http://' + request.host
    if request.uri.lower().startswith(proxy_uri_prefix.lower()):
        url = url + request.uri[len(proxy_uri_prefix):]
    else:
        url = url + request.uri

    headers = HTTPHeaders()

    for i in request.headers.keys():
        if i not in ignored_client_headers:
            headers[i] = request.headers[i]

    req = httpclient.HTTPRequest(
        url, method=request.method, headers=headers,
        body=request.body, allow_nonstandard_methods=True,
        follow_redirects=False
    )

    logging.debug("Sending request: %s", req)

    fetch(req, callback=partial(handle_response, request))


ignored_client_headers = set([
    "Accept-Encoding",
    "Proxy-Connection",
])

ignored_headers = set([
    "Content-Encoding",
    "Transfer-Encoding",
    "Vary",
])

replace_headers = {
    #'Connection': 'close',
}

def handle_response(request, response):

    logging.info("Got response: %s", response)

    if response.code not in http.client.responses:
        request.finish()
        return

    lines = []

    lines.append("HTTP/1.1 %d %s" % (
        response.code, http.client.responses[response.code]))

    headers = HTTPHeaders()
    for i in response.headers:
        if i not in ignored_headers:
            headers[i] = response.headers[i]

    if len(response.body):
        headers['Content-Length'] = str(len(response.body))

    for k, v in headers.get_all():
        if k in replace_headers:
            v = replace_headers[k]
        lines.append(k + ": " + v)

    head = "\r\n".join(lines) + "\r\n\r\n"

    if isinstance(response.body, str):
        body = response.body
    else:
        try:
            body = response.body.decode('utf-8')
        except:
            try:
                body = response.body.decode('cp1251')
            except:
                body = '<encoded>'
    logging.info("Sending response:\n%s", head + body)

    data = head.encode('utf-8')
    if response.body:
        data = data + response.body
    request.write(data)
    request.finish()


if __name__ == "__main__":
    http_server = httpserver.HTTPServer(handle_request)
    http_server.listen(8888)
    ioloop.IOLoop.instance().start()
