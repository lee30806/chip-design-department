"""파이프라인 HTTP API (표준 라이브러리만 씀). 역할은 `X-Role` 헤더로 밝힌다.

게이트웨이 토큰을 정하면(`serve(token=...)`, CLI `--token-file`, 환경 변수 CHIPDEPT_API_TOKEN) 쓰기 요청(POST)은
`X-Gateway-Token`이 맞을 때만 받는다. 사람과 Seat의 인증과 역할은 게이트웨이(`gateway/`)가 맡고, 여기는 게이트웨이를 믿는다.
조회(GET)는 토큰 없이도 된다.

| 메서드 | 경로 | 내용 |
| --- | --- | --- |
| POST | /runs | 실행 제출 `{"spec": SPEC 원문, "by", "config"?, "cells"?}` → 실행 상태 (역할: rtl-engineer, chip-lead) |
| GET | /runs, /runs/{id} | 실행 목록, 상태 |
| GET | /runs/{id}/modules, /review-items, /report, /pending, /rtl, /history | 모듈별 상태, 검토 항목, 최종 보고서, 승인 대기, 최종 RTL, 환류 이력 |
| POST | /runs/{id}/resume | 멈춘 실행을 이어서 실행 |
| POST | /runs/{id}/decisions | 결정. 기댓값 수정안 `{"ids", "decision": approved/rejected, "by", "note"?}`, Repair 충돌(design-lead) `{"ids", "decision": repair/architect, "module"?, "by", "note"?}` |
| POST | /runs/{id}/feedback, /feedback | 환류 네 형태 (역할: design-lead). 스키마는 schema/feedback.schema.json |
| POST | /feedback/{id}/decision | SPEC 변경 요청 승인 `{"decision", "by", "note"?}` (역할: chip-lead, rtl-engineer) |
| GET | /feedback, /generator-bugs, /notifications, /config | 환류 이력, 생성기 버그, 알림, 현재 설정 |
| POST | /watchdog | 진행 없는 실행 점검 |
"""
from __future__ import annotations

import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline.api.store import ApiError, Store

MAX_BODY = 16 * 1024 * 1024


def make_handler(store: Store, token: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "chipdept-pipeline/0.1"

        def log_message(self, fmt, *args):   # 기본 stderr 로그는 끈다 (조회가 잦음)
            pass

        def _send(self, status: int, obj) -> None:
            data = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError(413, "본문이 너무 큼")
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError as e:
                raise ApiError(400, f"JSON이 아님: {e}")
            if not isinstance(body, dict):
                raise ApiError(400, "본문은 JSON 객체여야 함")
            return body

        def _route(self, method: str):
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            role = self.headers.get("X-Role")
            m = re.fullmatch(r"/runs/([\w.-]+)(?:/([\w-]+))?", path)
            if method == "GET":
                if path == "/runs":
                    return store.runs()
                if m:
                    rid, sub = m.groups()
                    return {None: store.status, "modules": store.modules, "review-items": store.review_items,
                            "report": store.report, "pending": store.pending, "rtl": store.rtl,
                            "history": store.history}.get(sub, lambda _: (_ for _ in ()).throw(ApiError(404, "없는 경로")))(rid)
                fixed = {"/feedback": store.history, "/generator-bugs": store.generator_bugs,
                         "/notifications": store.notifications, "/config": store.config}
                if path in fixed:
                    return fixed[path]()
                raise ApiError(404, "없는 경로")
            if token is not None and not hmac.compare_digest(self.headers.get("X-Gateway-Token") or "", token):
                raise ApiError(401, "쓰기 요청은 게이트웨이를 거쳐야 함 (X-Gateway-Token)")
            body = self._body()
            if path == "/runs":
                if not body.get("spec") or not body.get("by"):
                    raise ApiError(400, "spec(원문)과 by가 필요함")
                return store.submit(body["spec"], body["by"], role, body.get("config"), body.get("cells"))
            if path == "/watchdog":
                return store.watchdog()
            if path == "/feedback":
                return store.feedback(body, role)
            fm = re.fullmatch(r"/feedback/([\w-]+)/decision", path)
            if fm:
                return store.decide_spec_change(fm.group(1), body.get("decision", ""), body.get("by", ""), role, body.get("note", ""))
            if m:
                rid, sub = m.groups()
                if sub == "resume":
                    return store.start(rid)
                if sub == "decisions":
                    return store.decide(rid, body.get("ids") or [], body.get("decision", ""), body.get("by", ""), role,
                                        body.get("note", ""), module=body.get("module"))
                if sub == "feedback":
                    return store.feedback({**body, "run_id": rid} if body.get("form") in ("check_report", "spec_change") else body, role)
            raise ApiError(404, "없는 경로")

        def _handle(self, method: str) -> None:
            try:
                self._send(200, self._route(method))
            except ApiError as e:
                self._send(e.status, {"error": str(e)})
            except Exception as e:   # 서버는 계속 돈다
                self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def serve(store: Store, host: str = "127.0.0.1", port: int = 8740, watchdog_every_s: float = 3600,
          token: str | None = None) -> ThreadingHTTPServer:
    """서버를 만든다. 호출한 쪽이 serve_forever()를 부른다. 진행 없는 실행은 watchdog_every_s마다 점검한다."""
    httpd = ThreadingHTTPServer((host, port), make_handler(store, token))

    def tick():
        store.watchdog()
        t = threading.Timer(watchdog_every_s, tick)
        t.daemon = True
        t.start()
    if watchdog_every_s:
        t = threading.Timer(watchdog_every_s, tick)
        t.daemon = True
        t.start()
    return httpd
