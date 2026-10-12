"""P7 게이트웨이: 인증, 역할 권한, 승인 다섯 가지(승인자만, 모두 기록), SPEC 작업대, 실행 상세, 환류 양식.
파이프라인 API는 가짜 agent와 게이트웨이 토큰으로 띄우고, 게이트웨이는 실제 HTTP(쿠키, API 키)로 부른다."""
import base64
import http.cookiejar
import json
import shutil
import threading
import urllib.error
import urllib.request

import pytest

pytest.importorskip("cocotb_tools.runner")
if not shutil.which("verilator"):
    pytest.skip("verilator 없음", allow_module_level=True)

from gateway.clients import OpenRig, Pipeline  # noqa: E402
from gateway.server import serve as gw_serve  # noqa: E402
from gateway.service import Gateway  # noqa: E402
from pipeline.api.server import serve as api_serve  # noqa: E402
from test_api import _store  # noqa: E402
from test_scheduler import SPEC, _files_wrong_v1  # noqa: E402

TOKEN = "gw-token"
USERS = {"admin": (["admin"], []), "des": (["design"], ["design_lead"]), "dsg": (["design"], []),
         "ver": (["verification"], []), "imp": (["implementation"], []), "apr": (["approver"], [])}


class Client:
    def __init__(self, base):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                              urllib.request.ProxyHandler({}))
        self.key = None

    def call(self, method, path, body=None, csrf=True):
        h = {"Content-Type": "application/json", **({"X-CDD": "1"} if csrf else {}),
             **({"Authorization": f"Bearer {self.key}"} if self.key else {})}
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.op.open(req, timeout=60) as r:
                data = r.read()
                return r.status, (json.loads(data) if r.headers.get_content_type() == "application/json" else data)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def login(self, name):
        code, out = self.call("POST", "/api/login", {"username": name, "password": f"pw-{name}"})
        assert code == 200, out
        return self


@pytest.fixture
def env(tmp_path):
    st = _store(tmp_path)
    api = api_serve(st, port=0, watchdog_every_s=0, token=TOKEN)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    gw = Gateway(tmp_path / "gw", Pipeline(f"http://127.0.0.1:{api.server_address[1]}", TOKEN), OpenRig("http://127.0.0.1:9"),
                 st.root)
    for name, (roles, caps) in USERS.items():
        gw.accounts.add_user(name, name, roles, caps, password=f"pw-{name}")
    gw.accounts.add_user("seat-design-lead", "Design-lead", ["design"], ["design_lead"], kind="seat", seat="design.lead")
    srv = gw_serve(gw, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield {"gw": gw, "st": st, "base": base, "c": {n: Client(base).login(n) for n in USERS}}
    srv.shutdown()
    api.shutdown()


def _md_spec(env, c, text=None):
    code, s = c.call("POST", "/api/specs", {"name": "adapter", "filename": "block_spec.md",
                                             "content_b64": base64.b64encode((text or SPEC.read_text()).encode()).decode()})
    assert code == 200, s
    return s


def _freeze(env, s):
    c = env["c"]
    for q in s["checks"]["questions"]:
        code, s = c["des"].call("POST", f"/api/specs/{s['id']}/answers", {"key": q["key"], "answer": "확인함. 현재 문장대로 둠"})
        assert code == 200, s
    code, s = c["des"].call("POST", f"/api/specs/{s['id']}/freeze-request", {})
    assert code == 200 and s["status"] == "freeze_requested", s
    return s


def _non_approvers_refused(env, kind, target):
    for n in ("admin", "des", "dsg", "ver", "imp"):
        code, out = env["c"][n].call("POST", "/api/approvals", {"kind": kind, "target": target, "decision": "approved"})
        assert code == 403, (n, out)


def test_auth_and_csrf(env):
    c = Client(env["base"])
    assert c.call("GET", "/api/runs")[0] == 401
    assert c.call("POST", "/api/login", {"username": "apr", "password": "wrong"})[0] == 401
    c.login("apr")
    assert c.call("GET", "/api/me")[1]["roles"] == ["approver"]
    assert c.call("POST", "/api/specs", {}, csrf=False)[0] == 403   # 쿠키 인증 쓰기 요청은 X-CDD 필요
    k = Client(env["base"])
    k.key = env["gw"].accounts.new_api_key("seat-design-lead")
    assert k.call("GET", "/api/me", csrf=False)[1]["kind"] == "seat"
    with pytest.raises(ValueError):
        env["gw"].accounts.add_user("seat-x", "x", ["approver"], kind="seat")   # Seat는 승인자가 될 수 없음
    assert env["c"]["des"].call("GET", "/api/users")[0] == 403 and env["c"]["admin"].call("GET", "/api/users")[0] == 200


def test_spec_freeze_run_final_approval_signoffs_rtl_freeze(env):
    c = env["c"]
    assert c["ver"].call("POST", "/api/specs", {"name": "x", "filename": "x.md", "content_b64": ""})[0] == 403
    s = _md_spec(env, c["des"])
    assert s["checks"]["gate"] == "pass" and s["status"] == "draft"
    assert c["des"].call("POST", f"/api/specs/{s['id']}/freeze-request", {})[0] == 409 or not s["checks"]["questions"]
    s = _freeze(env, s)
    assert c["des"].call("POST", "/api/runs", {"spec_id": s["id"]})[0] == 409   # 고정 전에는 제출 불가
    pend = c["apr"].call("GET", "/api/approvals/pending")[1]
    assert [(p["kind"], p["target"]) for p in pend] == [("spec_freeze", s["id"])]
    _non_approvers_refused(env, "spec_freeze", s["id"])
    code, rec = c["apr"].call("POST", "/api/approvals", {"kind": "spec_freeze", "target": s["id"], "decision": "approved",
                                                         "note": "SPEC 고정"})
    assert code == 200 and rec["by"] == "apr" and rec["spec_sha"] == s["sha"] and rec["at"], rec
    assert c["des"].call("POST", f"/api/specs/{s['id']}/markdown", {"markdown": "x"})[0] == 409   # 고정 뒤 수정 불가

    assert c["ver"].call("POST", "/api/runs", {"spec_id": s["id"]})[0] == 403
    code, run = c["des"].call("POST", "/api/runs", {"spec_id": s["id"]})
    assert code == 200, run
    rid = run["run_id"]
    assert env["st"].wait(rid, timeout=600)["status"] == "pass"
    _non_approvers_refused(env, "final_approval", rid)
    assert c["ver"].call("POST", f"/api/runs/{rid}/signoff", {"kind": "dv", "decision": "pass"})[0] == 409   # 최종 승인 전
    code, rec = c["apr"].call("POST", "/api/approvals", {"kind": "final_approval", "target": rid, "decision": "approved"})
    assert code == 200 and rec["run_id"] == rid and rec["spec_sha"] == env["st"].status(rid)["spec_sha256"]
    # RTL Freeze: DV와 PI 판정이 모두 pass여야
    assert c["des"].call("POST", f"/api/runs/{rid}/signoff", {"kind": "dv", "decision": "pass"})[0] == 403
    assert c["ver"].call("POST", f"/api/runs/{rid}/signoff", {"kind": "pi", "decision": "pass"})[0] == 403
    assert c["ver"].call("POST", f"/api/runs/{rid}/signoff", {"kind": "dv", "decision": "pass"})[0] == 200
    _non_approvers_refused(env, "rtl_freeze", rid)
    assert c["apr"].call("POST", "/api/approvals", {"kind": "rtl_freeze", "target": rid, "decision": "approved"})[0] == 409
    assert c["imp"].call("POST", f"/api/runs/{rid}/signoff", {"kind": "pi", "decision": "pass"})[0] == 200
    code, rec = c["apr"].call("POST", "/api/approvals", {"kind": "rtl_freeze", "target": rid, "decision": "approved"})
    assert code == 200, rec
    recs = c["ver"].call("GET", "/api/approvals")[1]
    assert [(r["kind"], r["decision"], r["by"]) for r in recs] == [("rtl_freeze", "approved", "apr"),
                                                                    ("final_approval", "approved", "apr"),
                                                                    ("spec_freeze", "approved", "apr")]
    assert c["apr"].call("POST", "/api/approvals", {"kind": "rtl_freeze", "target": rid, "decision": "approved"})[0] == 409

    # 실행 상세 (읽기 전용)
    d = c["imp"].call("GET", f"/api/runs/{rid}/detail")[1]
    assert d["children"][0]["module"] == "axis_adapter_core" and len(d["children"][0]["candidates"]) == 2
    assert {t["role"] for t in d["tasks"]} >= {"architect", "author", "verifier"}
    rtl = c["imp"].call("GET", f"/api/runs/{rid}/rtl")[1]
    assert any(e.get("fragment") for e in rtl["axis_adapter_core.sv"]["srcmap"]) and rtl["axis_adapter_core.sv"]["ir"]
    t = c["imp"].call("GET", f"/api/runs/{rid}/tasks/architect")[1]
    assert "Architect" in t["task_md"] and t["output_text"]
    audit = c["apr"].call("GET", "/api/audit")[1]
    assert sum(a["action"] == "approval" for a in audit) == 3


def test_feedback_form_and_spec_change_approval(env):
    c = env["c"]
    s = _freeze(env, _md_spec(env, c["des"]))
    c["apr"].call("POST", "/api/approvals", {"kind": "spec_freeze", "target": s["id"], "decision": "approved"})
    rid = c["des"].call("POST", "/api/runs", {"spec_id": s["id"]})[1]["run_id"]
    env["st"].wait(rid, timeout=600)
    text = SPEC.read_text()
    line = next(ln for ln in text.splitlines() if ln.lstrip().startswith("- ADP-01"))
    body = {"form": "spec_change", "run_id": rid, "spec": text.replace(line, line + " 개정.", 1), "reason": "DV 버그"}
    assert c["dsg"].call("POST", "/api/feedback", body)[0] == 403   # 설계 역할이어도 Design-lead만
    assert c["des"].call("POST", "/api/feedback", {"form": "free_text", "text": "고쳐줘"})[0] == 400   # 자유 텍스트 경로 없음
    code, fb = c["des"].call("POST", "/api/feedback", body)
    assert code == 200 and fb["status"] == "pending_approval" and fb["by"] == "des", fb
    _non_approvers_refused(env, "spec_change", fb["id"])
    code, rec = c["apr"].call("POST", "/api/approvals", {"kind": "spec_change", "target": fb["id"], "decision": "approved"})
    assert code == 200 and rec["reqs"] == ["ADP-01"] and rec["extra"]["pipeline"]["new_run"], rec
    assert env["st"].wait(rec["extra"]["pipeline"]["new_run"], timeout=600)["status"] == "pass"


def test_expectation_change_only_by_approver(env, tmp_path):
    # Verifier 1의 테스트에 틀린 속성 → Arbiter test_wrong → 승인 대기 E1, E2
    f = _files_wrong_v1(tmp_path)
    st = env["st"]
    st.base_roles = tmp_path / "roles2.json"
    roles = json.loads((tmp_path / "roles.json").read_text())
    agents = json.loads((tmp_path / "agents.json").read_text())
    agents["agents"][0]["env"]["FAKE_FILES"] = json.dumps(f)
    (tmp_path / "agents2.json").write_text(json.dumps(agents))
    roles["agents"] = str(tmp_path / "agents2.json")
    st.base_roles.write_text(json.dumps(roles))
    c = env["c"]
    s = _freeze(env, _md_spec(env, c["des"]))
    c["apr"].call("POST", "/api/approvals", {"kind": "spec_freeze", "target": s["id"], "decision": "approved"})
    rid = c["des"].call("POST", "/api/runs", {"spec_id": s["id"]})[1]["run_id"]
    assert st.wait(rid, timeout=600)["status"] == "waiting_approval"
    pend = [p for p in c["apr"].call("GET", "/api/approvals/pending")[1] if p["kind"] == "expectation_change"]
    assert len(pend) == 2 and all(p["reqs"] == ["ADP-01"] and p["detail"]["proposal"] for p in pend)
    _non_approvers_refused(env, "expectation_change", pend[0]["target"])
    for p in pend:
        code, rec = c["apr"].call("POST", "/api/approvals", {"kind": "expectation_change", "target": p["target"],
                                                             "decision": "approved", "note": "SPEC에 없는 검사"})
        assert code == 200 and rec["run_id"] == rid and rec["reqs"] == ["ADP-01"], rec
    assert st.wait(rid, timeout=600)["status"] == "pass"   # 마지막 결정 뒤 실행이 이어짐


def test_pdf_spec_figures_and_wavejson(env, tmp_path):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1. Overview", fontsize=16)
    page.draw_rect(pymupdf.Rect(80, 120, 300, 200), color=(0, 0, 0))
    page.insert_text((80, 160), "clk", fontsize=10)
    page.insert_text((80, 220), "Figure 1: Handshake", fontsize=10, fontname="hebo")
    pdf = tmp_path / "s.pdf"
    doc.save(pdf)
    c = env["c"]
    code, s = c["des"].call("POST", "/api/specs", {"name": "pdf spec", "filename": "s.pdf",
                                                    "content_b64": base64.b64encode(pdf.read_bytes()).decode()})
    assert code == 200 and s["source_kind"] == "pdf" and s["pages"] == 1, s
    assert c["ver"].call("GET", f"/api/specs/{s['id']}/page/1.png")[1][:4] == b"\x89PNG"
    if s["figures"]:
        assert c["ver"].call("GET", f"/api/specs/{s['id']}/figure/{s['figures'][0]['n']}.png")[1][:4] == b"\x89PNG"
    assert c["des"].call("POST", f"/api/specs/{s['id']}/wavejson/1", {"wavejson": "{signal: []}"})[0] == 400
    wj = '{signal: [{name: "clk", wave: "p..."}, {name: "valid", wave: "01.0"}]}'
    code, s = c["des"].call("POST", f"/api/specs/{s['id']}/wavejson/1", {"wavejson": wj})
    assert code == 200 and s["figures"][0]["has_wavejson"]
    assert c["ver"].call("GET", f"/api/specs/{s['id']}/wave/1.png")[1][:4] == b"\x89PNG"
    code, s2 = c["des"].call("POST", f"/api/specs/{s['id']}/markdown", {"markdown": s["markdown"] + "\n추가", "note": "수정"})
    assert code == 200 and s2["sha"] != s["sha"] and len(s2["versions"]) == 2


def test_seats_when_openrig_down(env):
    assert env["c"]["ver"].call("GET", "/api/seats")[1]["available"] is False
