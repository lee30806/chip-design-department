"""Seat 터미널 중계 (읽기 전용). Web UI의 WebSocket을 OpenRig 데몬의 터미널 WebSocket(`/api/terminal/<세션>`)에 잇는다.

데몬 → 브라우저: 터미널 출력(텍스트 프레임)을 그대로 넘긴다.
브라우저 → 데몬: 스크롤(`{"type": "scroll", "offset": n}`)만 넘기고 키 입력(`keys`, `text`)은 버린다.
데몬의 터미널 WebSocket은 웹 UI가 켜져 있을 때만 있다 (`OPENRIG_UI_ENABLED=1`).
WebSocket(RFC 6455)은 표준 라이브러리로 필요한 만큼만 구현한다: 조각 프레임 합치기, ping/pong, close.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
from urllib.parse import quote, urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TEXT, BINARY, CLOSE, PING, PONG, CONT = 0x1, 0x2, 0x8, 0x9, 0xA, 0x0
MAX_MSG = 4 * 1024 * 1024


class WsError(Exception):
    pass


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


def _read_exact(f, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise WsError("연결이 끊김")
    return b


def read_message(f) -> tuple[int, bytes]:
    """메시지 하나(조각이면 합쳐서). 제어 프레임은 그대로 돌려준다."""
    op, buf = None, b""
    while True:
        h = _read_exact(f, 2)
        fin, opcode, masked, n = h[0] & 0x80, h[0] & 0x0F, h[1] & 0x80, h[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", _read_exact(f, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", _read_exact(f, 8))[0]
        if n > MAX_MSG or len(buf) + n > MAX_MSG:
            raise WsError("메시지가 너무 큼")
        mask = _read_exact(f, 4) if masked else None
        data = _read_exact(f, n)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if opcode >= 0x8:
            return opcode, data
        if opcode != CONT:
            op = opcode
        buf += data
        if fin:
            return op if op is not None else TEXT, buf


def frame(opcode: int, data: bytes, masked: bool) -> bytes:
    """브라우저로 가는 프레임은 마스크하지 않고, 클라이언트(게이트웨이 → 데몬)로 보내는 프레임은 마스크한다."""
    n = len(data)
    head = bytes([0x80 | opcode])
    mbit = 0x80 if masked else 0
    if n < 126:
        head += bytes([mbit | n])
    elif n < 1 << 16:
        head += bytes([mbit | 126]) + struct.pack(">H", n)
    else:
        head += bytes([mbit | 127]) + struct.pack(">Q", n)
    if not masked:
        return head + data
    mask = os.urandom(4)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))


class Peer:
    """한쪽 WebSocket 끝. masked=True면 클라이언트 쪽(보내는 프레임을 마스크)."""

    def __init__(self, rfile, wfile, masked: bool, sock: socket.socket | None = None):
        self.rfile, self.wfile, self.masked, self.sock = rfile, wfile, masked, sock
        self.lock = threading.Lock()

    def send(self, opcode: int, data: bytes) -> None:
        with self.lock:
            self.wfile.write(frame(opcode, data, self.masked))
            self.wfile.flush()

    def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            self.send(CLOSE, struct.pack(">H", code) + reason.encode()[:120])
        except OSError:
            pass


def connect(base: str, session: str, token: str | None = None, timeout: float = 10) -> Peer:
    """데몬 터미널 WebSocket에 클라이언트로 붙는다."""
    u = urlsplit(base)
    if u.scheme != "http":
        raise WsError(f"지원하지 않는 데몬 주소: {base}")
    host, port = u.hostname or "127.0.0.1", u.port or 80
    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode()
    path = f"/api/terminal/{quote(session, safe='')}"
    lines = [f"GET {path} HTTP/1.1", f"Host: {host}:{port}", "Upgrade: websocket", "Connection: Upgrade",
             f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
    if token:
        lines.append(f"Authorization: Bearer {token}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    rfile = sock.makefile("rb")
    status = rfile.readline().decode("latin-1").strip()
    headers = {}
    while (line := rfile.readline().decode("latin-1").strip()):
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    if " 101 " not in status + " " or headers.get("sec-websocket-accept") != accept_key(key):
        sock.close()
        raise WsError(f"데몬 터미널에 붙지 못함: {status or '응답 없음'} (데몬의 웹 UI가 꺼져 있으면 OPENRIG_UI_ENABLED=1로 다시 시작)")
    sock.settimeout(None)
    return Peer(rfile, sock.makefile("wb"), masked=True, sock=sock)


def _allowed_upstream(data: bytes) -> bytes | None:
    """브라우저가 보낸 것 중 스크롤만 데몬에 넘긴다 (읽기 전용)."""
    try:
        msg = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(msg, dict) and msg.get("type") == "scroll" and isinstance(msg.get("offset"), int) and 0 <= msg["offset"] <= 100000:
        return json.dumps({"type": "scroll", "offset": msg["offset"]}).encode()
    return None


def relay(browser: Peer, daemon: Peer) -> None:
    """양쪽 중 하나가 닫힐 때까지 중계한다. 호출한 스레드가 데몬 → 브라우저를 맡는다."""
    done = threading.Event()

    def up():
        try:
            while not done.is_set():
                op, data = read_message(browser.rfile)
                if op == CLOSE:
                    break
                if op == PING:
                    browser.send(PONG, data)
                elif op == TEXT and (fwd := _allowed_upstream(data)):
                    daemon.send(TEXT, fwd)
        except (WsError, OSError):
            pass
        done.set()
        daemon.close()
        _shutdown(daemon)

    t = threading.Thread(target=up, daemon=True)
    t.start()
    code, reason = 1000, ""
    try:
        while not done.is_set():
            op, data = read_message(daemon.rfile)
            if op == CLOSE:
                if len(data) >= 2:
                    code, reason = struct.unpack(">H", data[:2])[0], data[2:].decode("utf-8", "replace")
                break
            if op == PING:
                daemon.send(PONG, data)
            elif op in (TEXT, BINARY):
                browser.send(op, data)
    except (WsError, OSError):
        code, reason = 1011, "데몬 터미널 연결이 끊김"
    if not done.is_set():
        done.set()
        browser.close(code if code not in (1005, 1006) else 1000, reason)
    _shutdown(daemon)
    t.join(timeout=5)


def _shutdown(p: Peer) -> None:
    if p.sock is not None:
        try:
            p.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
