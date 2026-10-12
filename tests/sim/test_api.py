"""P5 파이프라인 API: 실행 제출과 조회, 환류 네 형태, 영향 모듈 재실행, 교착 방지, HTTP. 가짜 agent를 쓴다."""
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip("cocotb_tools.runner")
if not shutil.which("verilator"):
    pytest.skip("verilator 없음", allow_module_level=True)

from pipeline.api import store as store_mod  # noqa: E402
from pipeline.api.server import serve  # noqa: E402
from pipeline.api.store import ApiError, Store  # noqa: E402
from test_pipeline import ROOT  # noqa: E402
from test_scheduler import FAKE, SPEC, _files  # noqa: E402


def _store(tmp_path, extra=None):
    files = _files(tmp_path)
    files = {"Verifier|개정된 SPEC": {"out/diff_verdict.json": json.dumps({"no_change": True, "reason": "바뀐 문장은 기존 검사와 같음"})},
             **files, "Repair": {"out/patches.json": "[]"}, **(extra or {})}
    env = {"FAKE_MODE": "roles", "FAKE_FILES": json.dumps(files), "FAKE_LOG": str(tmp_path / "calls.log")}
    agents = {"agents": [{"name": "fake", "family": "Test", "runtime": "fake", "command": [sys.executable, FAKE], "model": "m",
                          "env": env, "timeout_s": 120}]}
    (tmp_path / "agents.json").write_text(json.dumps(agents))
    roles = {"agents": str(tmp_path / "agents.json"),
             "roles": {r: {"agent": "fake", "count": 2 if r in ("author", "verifier") else 1}
                       for r in ("architect", "author", "verifier", "repair", "arbiter")},
             "limits": {"repair_per_candidate": 2, "agent_retries": 0, "budget_agent_runs": 50}}
    (tmp_path / "roles.json").write_text(json.dumps(roles))
    return Store(tmp_path / "store", base_roles=tmp_path / "roles.json", isolate=False)


def _wait(st, rid):
    out = st.wait(rid, timeout=600)
    assert out["status"] == "pass", (out, (st.run_dir(rid) / "scheduler.log").read_text()[-3000:])
    return out


def _passed_run(tmp_path, st):
    with pytest.raises(ApiError) as e:
        st.submit(SPEC.read_text(), "kim", "design-lead")   # 실행 제출은 RTL Engineer
    assert e.value.status == 403
    rid = st.submit(SPEC.read_text(), "kim", "rtl-engineer")["run_id"]
    _wait(st, rid)
    return rid


def test_submit_query_and_check_report_feedback(tmp_path):
    st = _store(tmp_path)
    rid = _passed_run(tmp_path, st)
    s = st.status(rid)
    assert s["block"] == "axis_adapter" and s["kind"] == "initial" and s["chosen"] == {"axis_adapter_core": 0}
    assert set(st.modules(rid)) == {"axis_adapter_core/c0", "axis_adapter_core/c1"}
    assert "axis_adapter_core.sv" in st.rtl(rid) and st.report(rid)["status"] == "pass"

    # 검사 실패 리포트: 조각 내부 한 줄, 골격 한 줄
    smap = json.loads((st.run_dir(rid) / "rtl" / "axis_adapter_core.srcmap.json").read_text())
    frag = next(e for e in smap if e.get("fragment") and e["node"].startswith("blocks/"))
    covered = {ln for e in smap if e.get("fragment") for ln in range(e["start"], e["end"] + 1)}
    skel = next(ln for ln in range(1, 400) if ln not in covered)
    report = (f"%Warning-WIDTHTRUNC: rtl/axis_adapter_core.sv:{frag['start']}:3: Operator ASSIGN expects 8 bits\n"
              f"%Warning-DECLFILENAME: rtl/axis_adapter_core.sv:{skel}:8: Filename does not match module\n")
    body = {"form": "check_report", "run_id": rid, "by": "lee", "format": "verilator", "report": report, "source": "Sanity"}
    with pytest.raises(ApiError) as e:
        st.feedback(body, "rtl-engineer")   # 환류는 Design-lead만
    assert e.value.status == 403
    with pytest.raises(ApiError) as e:
        st.feedback({**body, "extra": 1}, "design-lead")   # 스키마에 없는 필드
    assert e.value.status == 400
    rec = st.feedback(body, "design-lead")
    types = sorted(c["type"] for c in rec["classified"])
    assert types == ["lint_fragment", "lint_skeleton"], rec
    assert rec["result"] == "repair" and rec["new_run"]
    assert len(st.generator_bugs()) == 1 and st.generator_bugs()[0]["from_feedback"] == rec["id"]
    new = _wait(st, rec["new_run"])
    assert new["kind"] == "external_repair" and new["lineage"] == {"root": rid, "depth": 1, "parent": rid}
    codes = {r["code"] for r in st.review_items(new["run_id"])}
    assert "EXTERNAL_RECHECK" in codes
    calls = (tmp_path / "calls.log").read_text().split()
    assert calls.count("Author") == 2 and calls.count("Repair") == 1   # 재실행은 다시 쓰지 않고 해당 모듈만 고침
    assert [h["id"] for h in st.history(rid)] == [rec["id"]]


def test_spec_change_reruns_affected_only_and_rerun_limit(tmp_path, monkeypatch):
    st = _store(tmp_path)
    rid = _passed_run(tmp_path, st)
    text = SPEC.read_text()
    line = next(ln for ln in text.splitlines() if ln.lstrip().startswith("- ADP-01"))
    new_spec = text.replace(line, line + " 개정 문장을 더함.", 1)
    rec = st.feedback({"form": "spec_change", "run_id": rid, "by": "lee", "spec": new_spec, "reason": "DV 버그",
                       "source": "dv_bug"}, "design-lead")
    assert rec["status"] == "pending_approval" and rec["reqs"] == ["ADP-01"] and not rec["spec_diff"]["l1_changed"]
    with pytest.raises(ApiError) as e:
        st.decide_spec_change(rec["id"], "approved", "lee", "design-lead")   # 제출자 역할은 승인할 수 없음
    assert e.value.status == 403
    dec = st.decide_spec_change(rec["id"], "approved", "park", "chip-lead")
    new = _wait(st, dec["new_run"])
    assert new["kind"] == "spec_change"
    calls = (tmp_path / "calls.log").read_text().split()
    assert calls.count("Verifier|개정된_SPEC") == 2 and calls.count("Author") == 2   # 테스트만 맞추고 RTL은 다시 쓰지 않음
    with pytest.raises(ApiError):
        st.decide_spec_change(rec["id"], "approved", "park", "chip-lead")   # 두 번 결정할 수 없음

    # 교착 방지: 같은 Block Top의 재실행 상한
    monkeypatch.setattr(store_mod, "RERUN_LIMIT", 1)
    rec2 = st.feedback({"form": "spec_change", "run_id": rid, "by": "lee", "spec": new_spec, "reason": "다시"}, "design-lead")
    with pytest.raises(ApiError) as e:
        st.decide_spec_change(rec2["id"], "approved", "park", "chip-lead")
    assert e.value.status == 409
    assert st.notifications()[-1]["kind"] == "rerun_limit"


def test_generator_bug_config_change_and_watchdog(tmp_path):
    st = _store(tmp_path)
    st.feedback({"form": "generator_bug", "by": "lee", "description": "always_ff 골격의 리셋 극성"}, "design-lead")
    assert st.generator_bugs()[0]["status"] == "open"
    with pytest.raises(ApiError):
        st.feedback({"form": "config_change", "by": "lee", "config": {"agents": {"nobody": "fake"}}}, "design-lead")
    st.feedback({"form": "config_change", "by": "lee", "config": {"author_count": 1, "budget_agent_runs": 9}}, "design-lead")
    rid = st.submit(SPEC.read_text(), "kim", "rtl-engineer", start=False)["run_id"]
    roles = json.loads((st.run_dir(rid) / "roles.json").read_text())
    assert roles["roles"]["author"]["count"] == 1 and roles["limits"]["budget_agent_runs"] == 9   # 다음 실행부터 반영
    (st.run_dir(rid) / "state.json").write_text(json.dumps({"status": "running", "review": []}))
    old = time.time() - 25 * 3600
    for p in ("state.json", "meta.json"):
        os.utime(st.run_dir(rid) / p, (old, old))
    out = st.watchdog()
    assert [n["run_id"] for n in out] == [rid] and st.status(rid)["status"] == "halted"
    with pytest.raises(ApiError):
        st.start(rid)   # 멈춘 실행은 사람이 풀기 전까지 다시 돌리지 않음


def test_http_api(tmp_path):
    st = _store(tmp_path)
    httpd = serve(st, port=0, watchdog_every_s=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(method, path, body=None, role=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"X-Role": role} if role else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        assert call("GET", "/runs") == (200, [])
        code, out = call("POST", "/runs", {"spec": SPEC.read_text(), "by": "kim"}, "rtl-engineer")
        assert code == 200
        rid = out["run_id"]
        _wait(st, rid)
        assert call("GET", f"/runs/{rid}")[1]["status"] == "pass"
        assert call("GET", f"/runs/{rid}/review-items")[0] == 200
        assert call("GET", f"/runs/{rid}/nothing")[0] == 404
        assert call("POST", "/feedback", {"form": "generator_bug", "by": "lee", "description": "x"})[0] == 403
        assert call("POST", "/feedback", {"form": "nope", "by": "lee"}, "design-lead")[0] == 400
        code, out = call("POST", f"/runs/{rid}/feedback", {"form": "check_report", "by": "lee", "format": "verilator",
                                                            "report": "%Warning-X: elsewhere.sv:3:1: m\n"}, "design-lead")
        assert code == 200 and out["result"] == "generator_bug"   # 방출하지 않은 파일은 사람에게
        assert call("GET", "/feedback")[1][0]["id"] == out["id"]
    finally:
        httpd.shutdown()
