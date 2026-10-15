"""Seat 터미널 보기: 게이트웨이가 Web UI의 WebSocket을 OpenRig 데몬의 터미널 WebSocket에 읽기 전용으로 잇는다.
가짜 데몬은 붙으면 화면 한 줄을 보내고, 받은 프레임을 기록하고, 스크롤을 받으면 그 화면을 보낸다."""
import base64
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_gateway import Client, env  # noqa: F401  (fixture)

from gateway import termws
from gateway.clients import OpenRig


class FakeDaemon:
    def __init__(self):
        self.got, self.paths, self.auth = [], [], []
        d = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                d.paths.append(self.path)
                d.auth.append(self.headers.get("Authorization"))
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", termws.accept_key(self.headers["Sec-WebSocket-Key"]))
                self.end_headers()
                self.wfile.flush()
                self.close_connection = True
                peer = termws.Peer(self.rfile, self.wfile, masked=False)
                peer.send(termws.TEXT, "\x1b[2J세션 화면".encode())
                try:
                    while True:
                        op, data = termws.read_message(self.rfile)
                        if op == termws.CLOSE:
                            break
                        d.got.append(json.loads(data))
                        peer.send(termws.TEXT, f"scroll {d.got[-1]['offset']}".encode())
                except termws.WsError:
                    pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


@pytest.fixture
def daemon(env):  # noqa: F811
    d = FakeDaemon()
    env["gw"].openrig = OpenRig(d.url, token="tt")
    yield d
    d.srv.shutdown()


def _cookie(c: Client) -> str:
    jar = next(h for h in c.op.handlers if hasattr(h, "cookiejar")).cookiejar
    return next(f"cdd_session={k.value}" for k in jar if k.name == "cdd_session")


def _open(base: str, seat: str, cookie: str | None, origin: str | None = "same"):
    """브라우저처럼 WebSocket을 연다. (상태 줄, 소켓 파일 또는 None)"""
    host = base.split("//", 1)[1]
    s = socket.create_connection(tuple([host.split(":")[0], int(host.split(":")[1])]), timeout=10)
    lines = [f"GET /api/seats/{seat}/terminal HTTP/1.1", f"Host: {host}", "Upgrade: websocket", "Connection: Upgrade",
             f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}", "Sec-WebSocket-Version: 13"]
    if origin:
        lines.append(f"Origin: {'http://' + host if origin == 'same' else origin}")
    if cookie:
        lines.append(f"Cookie: {cookie}")
    s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    f = s.makefile("rb")
    status = f.readline().decode()
    while f.readline().strip():
        pass
    return status, s, f


def test_terminal_relay_is_read_only(env, daemon):  # noqa: F811
    status, s, f = _open(env["base"], "design.rtl", _cookie(env["c"]["ver"]))
    assert " 101 " in status, status
    assert daemon.paths == ["/api/terminal/design-rtl%40chip-dept"] and daemon.auth == ["Bearer tt"]
    assert termws.read_message(f) == (termws.TEXT, "\x1b[2J세션 화면".encode())
    w = s.makefile("wb")
    for msg in ({"type": "keys", "keys": ["C-c"]}, {"type": "text", "text": "rm -rf /"}, {"type": "scroll", "offset": 6}):
        w.write(termws.frame(termws.TEXT, json.dumps(msg).encode(), masked=True))
    w.flush()
    assert termws.read_message(f) == (termws.TEXT, b"scroll 6")
    assert daemon.got == [{"type": "scroll", "offset": 6}]   # 키 입력은 데몬에 가지 않음
    w.write(termws.frame(termws.CLOSE, b"\x03\xe8", masked=True))
    w.flush()
    s.close()
    for _ in range(50):
        if env["gw"].db.q("SELECT * FROM audit WHERE action='seat_terminal_view'"):
            break
        time.sleep(0.05)
    a = env["gw"].db.q("SELECT * FROM audit WHERE action='seat_terminal_view'")
    assert a[0]["username"] == "ver" and json.loads(a[0]["detail"]) == {"seat": "design.rtl"}


def test_terminal_refusals(env, daemon):  # noqa: F811
    base, cookie = env["base"], _cookie(env["c"]["ver"])
    assert " 401 " in _open(base, "design.rtl", None)[0]                                   # 로그인 없음
    assert " 403 " in _open(base, "design.rtl", cookie, origin="http://evil.example")[0]   # 다른 출처
    assert " 403 " in _open(base, "nope.x", cookie)[0]                                     # 없는 Seat
    key = env["gw"].accounts.new_api_key("seat-design-lead")
    host = base.split("//", 1)[1]
    s = socket.create_connection((host.split(":")[0], int(host.split(":")[1])), timeout=10)
    s.sendall((f"GET /api/seats/design.rtl/terminal HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\nSec-WebSocket-Version: 13\r\n"
               f"Authorization: Bearer {key}\r\n\r\n").encode())
    assert " 403 " in s.makefile("rb").readline().decode()                                # Seat 계정
    env["gw"].openrig = OpenRig("http://127.0.0.1:9")
    assert " 502 " in _open(base, "design.rtl", cookie)[0]                                 # 데몬이 없음
    assert daemon.got == []


def test_accept_key_matches_rfc6455_example():
    assert termws.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
