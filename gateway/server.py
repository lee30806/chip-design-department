"""게이트웨이 HTTP 서버 (표준 라이브러리). `/api/*`는 JSON API, 그 밖은 Web UI 정적 파일(`gateway/ui/dist`).

인증: 사람은 로그인 세션 쿠키(`cdd_session`, HttpOnly, SameSite=Strict), Seat와 서비스 계정은 `Authorization: Bearer <API 키>`.
쿠키로 인증한 쓰기 요청은 `X-CDD: 1` 헤더가 있어야 한다 (다른 사이트가 보내는 요청 위조를 막음).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from gateway import termws
from gateway.auth import SESSION_S
from gateway.chat import session_of
from gateway.perms import Forbidden, require
from gateway.service import Conflict, Gateway, SpecError, UpstreamError

UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"
MAX_BODY = 64 * 1024 * 1024


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def make_handler(gw: Gateway, ui_dist: Path = UI_DIST, secure_cookie: bool = False):
    class Handler(BaseHTTPRequestHandler):
        server_version = "chipdept-gateway/0.1"

        def log_message(self, fmt, *args):
            pass

        # -- 응답 --
        def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, obj, headers: dict | None = None) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", headers)

        # -- 요청 --
        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise HttpError(413, "본문이 너무 큼")
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                raise HttpError(400, "JSON이 아님")
            if not isinstance(body, dict):
                raise HttpError(400, "본문은 JSON 객체여야 함")
            return body

        def _session_token(self) -> str | None:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c["cdd_session"].value if "cdd_session" in c else None

        def _user(self, write: bool) -> dict:
            auth = self.headers.get("Authorization") or ""
            if auth.startswith("Bearer "):
                u = gw.accounts.from_api_key(auth[7:].strip())
                if not u:
                    raise HttpError(401, "API 키가 맞지 않음")
                return u
            u = gw.accounts.from_session(self._session_token())
            if not u:
                raise HttpError(401, "로그인이 필요함")
            if write and self.headers.get("X-CDD") != "1":
                raise HttpError(403, "X-CDD 헤더가 없는 쓰기 요청 (요청 위조 방지)")
            return u

        # -- 라우팅 --
        def _api(self, method: str, path: str):
            if method == "POST" and path == "/api/login":
                b = self._body()
                token = gw.accounts.login(str(b.get("username", "")), str(b.get("password", "")))
                if not token:
                    raise HttpError(401, "사용자 이름이나 비밀번호가 맞지 않음")
                cookie = f"cdd_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_S}" + ("; Secure" if secure_cookie else "")
                return 200, gw.accounts.from_session(token), {"Set-Cookie": cookie}
            if method == "POST" and path == "/api/logout":
                if (t := self._session_token()):
                    gw.accounts.logout(t)
                return 200, {"ok": True}, {"Set-Cookie": "cdd_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"}
            u = self._user(method == "POST")
            require(u, "view")
            b = self._body() if method == "POST" else {}
            seg = [unquote(s) for s in path.split("/")[2:]]
            m = lambda pat: re.fullmatch(pat, "/".join(seg))  # noqa: E731
            if method == "GET":
                if seg == ["me"]:
                    return 200, u
                if seg == ["runs"]:
                    return 200, gw.runs()
                if (r := m(r"runs/([\w.-]+)")):
                    return 200, gw.run(r[1])
                if (r := m(r"runs/([\w.-]+)/detail")):
                    return 200, gw.run_detail(r[1])
                if (r := m(r"runs/([\w.-]+)/rtl")):
                    return 200, gw.run_rtl(r[1])
                if (r := m(r"runs/([\w.-]+)/tasks/([\w.-]+)")):
                    return 200, gw.task(r[1], r[2])
                if seg == ["specs"]:
                    return 200, gw.specs.list()
                if (r := m(r"specs/([\w-]+)")):
                    return 200, gw.specs.get(r[1])
                if (r := m(r"specs/([\w-]+)/(page|figure|wave)/(\d+)\.png")):
                    fn = {"page": gw.specs.page_png, "figure": gw.specs.figure_png, "wave": gw.specs.wave_png}[r[2]]
                    return 200, ("image/png", fn(r[1], int(r[3])))
                if (r := m(r"specs/([\w-]+)/wavejson/(\d+)")):
                    return 200, {"wavejson": gw.specs.wavejson(r[1], int(r[2]))}
                if seg == ["approvals", "pending"]:
                    return 200, gw.pending()
                if seg == ["approvals"]:
                    return 200, gw.approvals()
                if seg == ["feedback"]:
                    return 200, gw.pipeline.get("/feedback")
                if seg == ["feedback", "schema"]:
                    from gateway.service import FEEDBACK_SCHEMA
                    return 200, FEEDBACK_SCHEMA
                if seg == ["feedback", "formats"]:
                    from pipeline.feedback.reports import formats
                    return 200, {k: v.get("description", "") for k, v in formats().items()}
                if seg == ["seats"]:
                    return 200, gw.seats()
                if (r := m(r"seats/([\w.]+)/messages")):
                    return 200, gw.chat.messages(r[1])
                if seg == ["dashboard"]:
                    return 200, gw.dashboard()
                if seg == ["generator-bugs"]:
                    return 200, gw.generator_bugs()
                if seg == ["settings"]:
                    return 200, gw.settings()
                if (r := m(r"runs/([\w.-]+)/report")):
                    return 200, gw.report(r[1])
                if (r := m(r"runs/([\w.-]+)/report\.md")):
                    md = gw.report_markdown(r[1])
                    return 200, ("text/markdown; charset=utf-8", md.encode("utf-8")), {
                        "Content-Disposition": f'attachment; filename="{r[1]}-report.md"'}
                if seg == ["users"]:
                    require(u, "manage_users")
                    return 200, gw.accounts.users()
                if seg == ["audit"]:
                    require(u, "view_audit")
                    return 200, gw.db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 500")
                raise HttpError(404, "없는 경로")
            # POST
            if seg == ["runs"]:
                return 200, gw.submit_run(u, str(b.get("spec_id", "")), b.get("config"))
            if (r := m(r"seats/([\w.]+)/messages")):
                return 200, gw.chat.send(u, r[1], str(b.get("text", "")), str(b.get("kind", "chat")))
            if (r := m(r"generator-bugs/(G\d+)")):
                return 200, gw.update_generator_bug(u, r[1], str(b.get("status", "")), str(b.get("note", "")))
            if (r := m(r"runs/([\w.-]+)/discard")):
                return 200, gw.discard_run(u, r[1], str(b.get("reason", "")))
            if (r := m(r"runs/([\w.-]+)/signoff")):
                return 200, gw.signoff(u, r[1], str(b.get("kind", "")), str(b.get("decision", "")), str(b.get("note", "")))
            if seg == ["specs"]:
                require(u, "spec_edit")
                try:
                    content = base64.b64decode(b.get("content_b64", ""), validate=True)
                except Exception:
                    raise HttpError(400, "content_b64가 base64가 아님")
                return 200, gw.specs.create(str(b.get("name", "")), str(b.get("filename", "")), content, u["username"])
            if (r := m(r"specs/([\w-]+)/markdown")):
                require(u, "spec_edit")
                return 200, gw.specs.update_markdown(r[1], str(b.get("markdown", "")), u["username"], str(b.get("note", "")))
            if (r := m(r"specs/([\w-]+)/wavejson/(\d+)")):
                require(u, "spec_edit")
                return 200, gw.specs.set_wavejson(r[1], int(r[2]), str(b.get("wavejson", "")), u["username"])
            if (r := m(r"specs/([\w-]+)/answers")):
                require(u, "spec_edit")
                return 200, gw.specs.answer(r[1], str(b.get("key", "")), str(b.get("answer", "")), u["username"])
            if (r := m(r"specs/([\w-]+)/freeze-request")):
                require(u, "spec_edit")
                return 200, gw.specs.request_freeze(r[1], u["username"])
            if seg == ["approvals"]:
                return 200, gw.decide(u, str(b.get("kind", "")), str(b.get("target", "")), str(b.get("decision", "")),
                                      str(b.get("note", "")), module=b.get("module"))
            if seg == ["feedback"]:
                return 200, gw.feedback(u, b)
            if seg == ["users"]:
                require(u, "manage_users")
                nu = gw.accounts.add_user(str(b.get("username", "")), str(b.get("display") or b.get("username", "")),
                                          list(b.get("roles") or []), list(b.get("caps") or []), b.get("password") or None)
                gw.db.audit(u["username"], "user_add", {"user": nu["username"], "roles": nu["roles"]})
                return 200, nu
            if (r := m(r"users/([\w.@-]+)/apikey")):
                require(u, "manage_users")
                key = gw.accounts.new_api_key(r[1])
                gw.db.audit(u["username"], "apikey_issue", {"user": r[1]})
                return 200, {"username": r[1], "api_key": key}
            raise HttpError(404, "없는 경로")

        def _terminal(self, seat_id: str) -> None:
            """Seat 터미널 보기 (WebSocket, 읽기 전용). 사람 계정만. 다른 사이트의 페이지가 붙지 못하게 Origin이 Host와 같아야 한다."""
            if (self.headers.get("Upgrade") or "").lower() != "websocket" or not self.headers.get("Sec-WebSocket-Key"):
                raise HttpError(400, "WebSocket 요청이 아님")
            origin = self.headers.get("Origin")
            if origin is not None and urlsplit(origin).netloc != (self.headers.get("Host") or ""):
                raise HttpError(403, "다른 출처에서 온 터미널 요청")
            u = self._user(False)
            require(u, "view")
            if u.get("kind") != "human":
                raise Forbidden("Seat 계정은 Web UI 터미널을 쓰지 않음")
            seat = gw.chat._seat(seat_id)
            try:
                daemon = termws.connect(gw.openrig.base, session_of(seat), gw.openrig.token)
            except (termws.WsError, OSError) as e:
                raise HttpError(502, str(e))
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", termws.accept_key(self.headers["Sec-WebSocket-Key"]))
            self.end_headers()
            self.wfile.flush()
            self.close_connection = True
            gw.db.audit(u["username"], "seat_terminal_view", {"seat": seat_id})
            termws.relay(termws.Peer(self.rfile, self.wfile, masked=False), daemon)

        def _static(self, path: str) -> None:
            if not ui_dist.exists():
                return self._send(200, "Web UI가 빌드되지 않음: cd gateway/ui && npm ci && npm run build".encode(),
                                  "text/plain; charset=utf-8")
            p = (ui_dist / path.lstrip("/")).resolve()
            if not str(p).startswith(str(ui_dist.resolve())) or not p.is_file():
                p = ui_dist / "index.html"   # 화면 경로는 단일 페이지 앱이 처리
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, p.read_bytes(), ctype)

        def _handle(self, method: str) -> None:
            path = self.path.split("?", 1)[0]
            if not path.startswith("/api/"):
                return self._static(path)
            try:
                if method == "GET" and (r := re.fullmatch(r"/api/seats/([\w.]+)/terminal", path)):
                    return self._terminal(r[1])
                res = self._api(method, path.rstrip("/"))
                status, body = res[0], res[1]
                headers = res[2] if len(res) > 2 else None
                if isinstance(body, tuple):
                    self._send(status, body[1], body[0], headers)
                else:
                    self._json(status, body, headers)
            except (HttpError, Conflict, SpecError, UpstreamError) as e:
                self._json(e.status, {"error": str(e)})
            except Forbidden as e:
                self._json(403, {"error": str(e)})
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def serve(gw: Gateway, host: str = "127.0.0.1", port: int = 8750, ui_dist: Path = UI_DIST,
          secure_cookie: bool = False) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(gw, ui_dist, secure_cookie))


__all__ = ["serve", "make_handler", "threading"]
