"""P9 Web UI 2·3차의 게이트웨이 쪽: 대시보드, 환류 관리(생성기 버그, 실행 버림), 리포트, 설정, Seat 대화 중계.
대화 중계는 가짜 OpenRig 데몬(보낸 텍스트를 기록하고 화면에 Seat의 답을 붙여 돌려줌)으로 본다."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_api import _passed_run
from test_gateway import Client, env  # noqa: F401  (fixture)

from gateway.clients import OpenRig


class FakeRig:
    """POST /api/transport/send 를 기록하고, capture에는 보낸 본문과 (reply가 있으면) Seat의 답을 붙여 돌려준다."""

    def __init__(self, reply="확인했습니다.\n작업을 시작합니다."):
        self.sent, self.reply = [], reply
        rig = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/transport/send":
                    rig.sent.append(body)
                    out = {"ok": True}
                else:
                    screen = []
                    for s in rig.sent:
                        if s["session"] != body["session"]:
                            continue
                        screen += s["text"].splitlines()
                        mid = re.search(r"메시지 ID: (M[0-9a-f]+)", s["text"]).group(1)
                        if rig.reply is not None:   # TUI 장식(●)과 함께 Seat가 쓴 답
                            screen += [f"● [{mid}]", *rig.reply.splitlines(), f"[{mid} 끝]"]
                    out = {"ok": True, "content": "\n".join(screen)}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


@pytest.fixture
def rig(env):  # noqa: F811
    r = FakeRig()
    env["gw"].openrig = env["gw"].chat.openrig = OpenRig(r.url)
    yield r
    r.srv.shutdown()


def test_seat_chat_roundtrip_and_permissions(env, rig):  # noqa: F811
    c = env["c"]
    code, m = c["ver"].call("POST", "/api/seats/design.rtl/messages", {"text": "인터페이스 질문입니다"})
    assert code == 200 and m["status"] == "sent", m
    sent = rig.sent[0]
    assert sent["session"] == "design-rtl@chip-dept"
    assert "보낸 사람: ver" in sent["text"] and f"메시지 ID: {m['mid']}" in sent["text"]
    assert f"[{m['mid']}]" not in sent["text"]   # 표지는 말로만 설명 (보낸 본문을 답으로 오인하지 않게)
    code, msgs = c["ver"].call("GET", "/api/seats/design.rtl/messages")
    assert msgs[-1]["status"] == "replied" and msgs[-1]["reply"] == "확인했습니다.\n작업을 시작합니다."
    # 작업 지시: lead Seat에만, 설계 역할이나 승인자만
    assert c["des"].call("POST", "/api/seats/design.rtl/messages", {"text": "x", "kind": "instruction"})[0] == 403
    assert c["ver"].call("POST", "/api/seats/design.lead/messages", {"text": "x", "kind": "instruction"})[0] == 403
    code, m = c["des"].call("POST", "/api/seats/design.lead/messages", {"text": "crc 블록 RTL Freeze 준비", "kind": "instruction"})
    assert code == 200 and "종류: 작업 지시" in rig.sent[-1]["text"]
    assert c["des"].call("POST", "/api/seats/nope.x/messages", {"text": "x"})[0] == 403
    # Seat 계정은 Web UI 대화를 보낼 수 없음
    seat = Client(env["base"])
    seat.key = env["gw"].accounts.new_api_key("seat-design-lead")
    assert seat.call("POST", "/api/seats/design.rtl/messages", {"text": "x"}, csrf=False)[0] == 403
    audit = env["gw"].db.q("SELECT * FROM audit WHERE action='seat_message'")
    assert len(audit) == 2


def test_partial_reply_and_unreachable_rig(env, rig):  # noqa: F811
    c = env["c"]
    rig.reply = None   # 아직 답이 없음
    code, m = c["des"].call("POST", "/api/seats/pi.lead/messages", {"text": "STA 결과는?"})
    assert c["des"].call("GET", "/api/seats/pi.lead/messages")[1][-1]["status"] == "sent"
    env["gw"].openrig = env["gw"].chat.openrig = OpenRig("http://127.0.0.1:9")   # 데몬이 없음
    code, m = c["des"].call("POST", "/api/seats/pi.lead/messages", {"text": "다시"})
    assert code == 200 and m["status"] == "failed" and m["error"]


def test_dashboard_generator_bugs_settings_report(env, tmp_path):  # noqa: F811
    c, st = env["c"], env["st"]
    rid = _passed_run(tmp_path, st)
    st.feedback({"form": "generator_bug", "by": "des", "description": "always_ff 골격의 리셋 극성"}, "design-lead")
    code, d = c["ver"].call("GET", "/api/dashboard")
    assert code == 200 and d["runs"].get("pass") == 1 and d["generator_bugs_open"] == 1 and not d["seats"]["available"]
    bugs = c["ver"].call("GET", "/api/generator-bugs")[1]
    assert bugs[0]["id"] == "G1" and bugs[0]["status"] == "open"
    assert c["dsg"].call("POST", "/api/generator-bugs/G1", {"status": "fixed"})[0] == 403   # design_lead 능력 없음
    code, b = c["des"].call("POST", "/api/generator-bugs/G1", {"status": "fixed", "note": "Emitter 템플릿 고침"})
    assert code == 200 and b["status"] == "fixed" and b["history"][-1]["by"] == "des"
    assert c["des"].call("POST", "/api/generator-bugs/G1", {"status": "done"})[0] == 400
    assert c["ver"].call("GET", "/api/dashboard")[1]["generator_bugs_open"] == 0
    code, s = c["ver"].call("GET", "/api/settings")
    assert code == 200 and s["effective"]["roles"]["author"]["count"] >= 1 and s["agents"]
    code, r = c["ver"].call("GET", f"/api/runs/{rid}/report")
    assert code == 200 and r["status"] == "pass" and r["pipeline_report"]["status"] == "pass"
    code, md = c["ver"].call("GET", f"/api/runs/{rid}/report.md")
    assert code == 200 and md.decode().startswith("# 실행 보고서: axis_adapter") and "## 후보" in md.decode()
    assert c["dsg"].call("POST", f"/api/runs/{rid}/discard", {"reason": "x"})[0] == 403
    assert c["des"].call("POST", f"/api/runs/{rid}/discard", {"reason": "x"})[0] == 409   # 처음 실행은 상한에 안 들어감
