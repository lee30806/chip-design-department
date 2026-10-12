"""P6 부서 계층: Seat 명단과 rig.yaml, Seat sandbox 프로필, Seat API 클라이언트 권한, 그리고 OpenRig로 올린 rig에서의 완료 기준.

완료 기준 시험(test_rig_*)은 OpenRig를 띄우므로 CHIPDEPT_RIG_TEST=1일 때만 돈다.
    CHIPDEPT_RIG_TEST=1 .venv/bin/python -m pytest tests/test_department.py -s
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

from test_pipeline import ROOT

DEPT = ROOT / "department"
sys.path.insert(0, str(DEPT))
import seatlib  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("sandbox-exec"), reason="macOS sandbox-exec 없음")


def _rig_members() -> dict[str, tuple[str, str]]:
    """rig.yaml의 (pod.member → (runtime, 시작 명령)). 생성한 파일의 들여쓰기 구조를 따라 읽는다."""
    out, pod, member, runtime = {}, None, None, None
    for ln in (DEPT / "rig.yaml").read_text().splitlines():
        if ln.startswith("  - id: "):
            pod = ln.split(": ", 1)[1]
        elif ln.startswith("      - id: "):
            member = ln.split(": ", 1)[1]
        elif ln.startswith("        runtime: "):
            runtime = ln.split(": ", 1)[1]
        elif ln.strip().startswith("value: ") and member:
            out[f"{pod}.{member}"] = (runtime, ln.split(": ", 1)[1].strip('"'))
    return out


def test_roster_matches_rig_spec():
    members = _rig_members()
    roster = {s["id"] for s in seatlib.ROSTER["seats"]}
    assert len(roster) == 15 and set(members) == roster | {"infra.pipeline", "infra.gateway"}
    for m, (runtime, cmd) in members.items():
        assert runtime == "terminal"
        assert cmd == {"infra.pipeline": "exec ./bin/pipeline-server", "infra.gateway": "exec ./bin/gateway-server"}.get(
            m, f"exec ./bin/seat {m}")
    import dept
    if dept.RIG_BIN.exists():
        r = dept.rig("spec", "validate", str(DEPT / "rig.yaml"))
        assert r.returncode == 0 and "valid" in r.stdout, r.stdout + r.stderr
    for s in roster:   # 역할 지침과 공통 규칙
        assert (DEPT / "guidance" / f"{s}.md").exists()
    common = (DEPT / "guidance" / "common.md").read_text()
    assert "IR과 RTL을 직접 고치지 않는다" in common and "환류 양식으로만" in common
    dv = {s["id"] for s in seatlib.ROSTER["seats"] if s.get("verifier_blind")}
    assert dv == {"dv.lead", "dv.vplan", "dv.tb", "dv.checker"}


def _sandboxed(tmp_path, monkeypatch, seat_id, cmd):
    monkeypatch.setenv("CHIPDEPT_DEPT_HOME", str(tmp_path / "dh"))
    monkeypatch.setenv("CHIPDEPT_RUNS", str(tmp_path / "dh" / "runs"))
    monkeypatch.setenv("CHIPDEPT_GATEWAY_HOME", str(tmp_path / "gw"))
    monkeypatch.delenv("CHIPDEPT_STORE", raising=False)
    prof = tmp_path / f"{seat_id}.sb"
    prof.write_text(seatlib.profile(seat_id))
    return subprocess.run(["sandbox-exec", "-f", str(prof), "/bin/sh", "-c", cmd], capture_output=True, text=True).returncode


def test_seat_sandbox_profiles(tmp_path, monkeypatch):
    runs = tmp_path / "dh" / "runs" / "r1" / "verifier__v0" / "out"
    rtl = tmp_path / "dh" / "store" / "runs" / "x" / "rtl"
    for d in (runs, rtl, tmp_path / "dh" / "seats" / "dv-tb", tmp_path / "dh" / "seats" / "design-rtl"):
        d.mkdir(parents=True)
    (runs / "test_x.py").write_text("verifier test")
    (rtl / "x.sv").write_text("module x; endmodule")
    sb = lambda s, c: _sandboxed(tmp_path, monkeypatch, s, c)  # noqa: E731
    # DV는 파이프라인 Verifier 산출물과 실행 디렉터리를 읽지 못함. 다른 Seat는 읽을 수 있음
    assert sb("dv.tb", f"cat {runs / 'test_x.py'}") != 0
    assert sb("dv.tb", f"cat {rtl / 'x.sv'}") != 0
    assert sb("design.rtl", f"cat {runs / 'test_x.py'}") == 0
    # 어떤 Seat도 IR, RTL, 실행 상태를 쓰지 못함
    for s in ("design.lead", "design.rtl", "lead.chip", "pi.synth"):
        assert sb(s, f"echo x >> {rtl / 'x.sv'}") != 0
        assert sb(s, f"echo x > {runs / 'p.py'}") != 0
    # 자기 worktree만 쓰기, 저장소 원본과 다른 Seat의 worktree는 거부
    assert sb("design.rtl", f"echo x > {tmp_path / 'dh' / 'seats' / 'design-rtl' / 'f'}") == 0
    assert sb("design.rtl", f"echo x > {tmp_path / 'dh' / 'seats' / 'dv-tb' / 'f'}") != 0
    assert sb("design.rtl", f"echo x > {ROOT / 'pipeline' / 'zz_should_not_exist.py'}") != 0
    assert not (ROOT / "pipeline" / "zz_should_not_exist.py").exists()
    assert sb("design.rtl", f"head -1 {ROOT / 'ARCHITECTURE.md'}") == 0
    # 게이트웨이 저장소(파이프라인 API 토큰)와 다른 Seat의 API 키는 못 읽음. 자기 키만
    (tmp_path / "gw").mkdir(exist_ok=True)
    (tmp_path / "gw" / "api_token").write_text("secret")
    (tmp_path / "dh" / "keys").mkdir(parents=True, exist_ok=True)
    for k in ("design.rtl", "design.lead"):
        (tmp_path / "dh" / "keys" / f"{k}.key").write_text(k)
    assert sb("design.rtl", f"cat {tmp_path / 'dh' / 'keys' / 'design.rtl.key'}") == 0
    assert sb("design.rtl", f"cat {tmp_path / 'dh' / 'keys' / 'design.lead.key'}") != 0
    assert sb("design.lead", f"cat {tmp_path / 'gw' / 'api_token'}") != 0


def test_deptctl_hides_write_commands_by_role():
    def run(role, *args):
        env = {**os.environ, "CHIPDEPT_SEAT_ROLE": role, "CHIPDEPT_SEAT": "x", "CHIPDEPT_API": "http://127.0.0.1:9"}
        return subprocess.run([sys.executable, str(DEPT / "bin" / "deptctl"), *args], capture_output=True, text=True, env=env)
    r = run("rtl-engineer", "feedback", "body.json")
    assert r.returncode == 2 and "Design-lead" in r.stderr
    assert run("none", "submit", "spec.md").returncode == 2
    r = run("design-lead", "decide", "x", "E1")   # 승인은 사람(승인자)만
    assert r.returncode == 2 and "승인자" in r.stderr
    assert "feedback" in run("design-lead", "--help").stdout and "feedback" not in run("rtl-engineer", "--help").stdout


# -- 완료 기준: OpenRig로 올린 rig --

RIG_TEST = os.environ.get("CHIPDEPT_RIG_TEST") == "1"
rig_only = pytest.mark.skipif(not RIG_TEST, reason="CHIPDEPT_RIG_TEST=1일 때만 (OpenRig를 띄움)")


@pytest.fixture(scope="module")
def rig_up(tmp_path_factory):
    import dept
    sys.path.insert(0, str(ROOT / "tests" / "sim"))
    from test_scheduler import FAKE, _files

    if not dept.RIG_BIN.exists():
        pytest.skip("OpenRig 없음")
    tmp = tmp_path_factory.mktemp("dept")
    prefix = f"test-seat-{uuid.uuid4().hex[:6]}/"
    env_keep = {k: os.environ.get(k) for k in ("CHIPDEPT_DEPT_HOME", "CHIPDEPT_RUNS", "CHIPDEPT_STORE", "CHIPDEPT_API_PORT",
                                               "CHIPDEPT_SEAT_BRANCH_PREFIX", "CHIPDEPT_GATEWAY_HOME", "CHIPDEPT_GATEWAY_PORT")}
    os.environ.update(CHIPDEPT_DEPT_HOME=str(tmp / "dh"), CHIPDEPT_RUNS=str(tmp / "dh" / "runs"),
                      CHIPDEPT_STORE=str(tmp / "dh" / "store"), CHIPDEPT_API_PORT="8741", CHIPDEPT_SEAT_BRANCH_PREFIX=prefix,
                      CHIPDEPT_GATEWAY_HOME=str(tmp / "gw"), CHIPDEPT_GATEWAY_PORT="8751")
    # 파이프라인 API 서버는 가짜 agent로 (에이전트 하나가 6초씩 걸려 실행이 30초 넘게 진행됨)
    files = _files(tmp)
    agents = {"agents": [{"name": "fake", "family": "Test", "runtime": "fake", "command": [sys.executable, FAKE], "model": "m",
                          "env": {"FAKE_MODE": "roles", "FAKE_FILES": json.dumps(files), "FAKE_DELAY": "6"}, "timeout_s": 120}]}
    (tmp / "agents.json").write_text(json.dumps(agents))
    roles = {"agents": str(tmp / "agents.json"),
             "roles": {r: {"agent": "fake", "count": 2 if r in ("author", "verifier") else 1}
                       for r in ("architect", "author", "verifier", "repair", "arbiter")},
             "limits": {"repair_per_candidate": 2, "agent_retries": 0, "budget_agent_runs": 50}}
    (tmp / "roles.json").write_text(json.dumps(roles))
    try:
        out = dept.up("shell", f"--roles {tmp / 'roles.json'} --no-isolate")
        assert out["up"] == 0, out
        for s in ("design.rtl", "design.lead", "dv.tb", "lead.chip"):
            assert dept.wait_ready(s), (s, dept.capture(s)[-1500:])
        (tmp / "spec_id").write_text(_frozen_spec(tmp))
        yield dept, tmp
    finally:
        _cleanup(dept, tmp, prefix, env_keep)


def _frozen_spec(tmp) -> str:
    """사람 계정(설계, 승인자)으로 SPEC 작업 공간을 만들고 고정한다. Seat는 고정된 SPEC으로만 실행을 제출한다."""
    from gateway.clients import OpenRig, Pipeline
    from gateway.service import Gateway

    deadline = time.time() + 60
    while time.time() < deadline:   # 파이프라인 API와 게이트웨이가 뜰 때까지
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://127.0.0.1:8741/runs", timeout=2)
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://127.0.0.1:8751/", timeout=2)
            break
        except OSError:
            time.sleep(1)
    gw = Gateway(tmp / "gw", Pipeline("http://127.0.0.1:8741", (tmp / "gw" / "api_token").read_text().strip()),
                 OpenRig("http://127.0.0.1:9"), tmp / "dh" / "store")
    des = gw.accounts.add_user("des", "설계", ["design"], ["design_lead"], password="x")
    apr = gw.accounts.add_user("apr", "승인자", ["approver"], password="x")
    s = gw.specs.create("axis_adapter", "block_spec.md", (ROOT / "tests" / "golden" / "axis_adapter" / "block_spec.md").read_bytes(),
                        des["username"])
    for q in s["checks"]["questions"]:
        gw.specs.answer(s["id"], q["key"], "확인함", des["username"])
    gw.specs.request_freeze(s["id"], des["username"])
    gw.decide(apr, "spec_freeze", s["id"], "approved")
    return s["id"]


def _cleanup(dept, tmp, prefix, env_keep):
    dept.down()
    for wt in (tmp / "dh" / "seats").glob("*"):
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(wt)], capture_output=True)
    subprocess.run(["git", "-C", str(ROOT), "worktree", "prune"], capture_output=True)
    for b in subprocess.run(["git", "-C", str(ROOT), "branch", "--list", f"{prefix}*", "--format=%(refname:short)"],
                            capture_output=True, text=True).stdout.split():
        subprocess.run(["git", "-C", str(ROOT), "branch", "-D", b], capture_output=True)
    for k, v in env_keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@rig_only
def test_rig_permission_violations_fail(rig_up):
    dept, tmp = rig_up
    spec_id = (tmp / "spec_id").read_text()
    rc, out = dept.run("design.rtl", f"deptctl submit {spec_id}")
    assert rc == 0, out
    rid = json.loads(out[out.index("{"):])["run_id"]
    # Seat가 게이트웨이를 건너 파이프라인 API에 직접 쓰기 요청을 보내면 역할을 밝혀도 거부 (게이트웨이 토큰 없음)
    rc, out = dept.run("design.rtl", "curl -s -o /dev/null -w 'HTTP%{http_code}' -X POST -H 'X-Role: design-lead' "
                                     "-d '{\"form\":\"generator_bug\",\"by\":\"x\",\"description\":\"x\"}' http://127.0.0.1:8741/feedback")
    assert "HTTP401" in out, out
    # 게이트웨이 토큰과 다른 Seat의 API 키는 못 읽음
    rc, out = dept.run("design.rtl", f"cat {tmp / 'gw' / 'api_token'}")
    assert rc != 0 and "operation not permitted" in out.lower(), out
    rc, out = dept.run("design.rtl", f"cat {tmp / 'dh' / 'keys' / 'design.lead.key'}")
    assert rc != 0 and "operation not permitted" in out.lower(), out
    # 격리 실행이면 RUNS/<실행>/, 시험(가짜 agent, 격리 없음)이면 STORE/runs/<실행>/work/ 아래에 생긴다. DV는 둘 다 못 읽음
    def find():
        return sorted([*(tmp / "dh" / "runs" / rid).glob("verifier__v*/out/test_*.py"),
                       *(tmp / "dh" / "store" / "runs" / rid / "work").glob("verifier__v*/out/test_*.py")])
    deadline = time.time() + 300
    while not find() and time.time() < deadline:
        time.sleep(2)
    tests = find()
    assert tests, "Verifier 테스트가 생기지 않음"
    rtl_dir = tmp / "dh" / "store" / "runs" / rid
    # DV Seat가 파이프라인 Verifier 테스트를 읽으려 하면 거부
    rc, out = dept.run("dv.tb", f"cat {tests[0]}")
    assert rc != 0 and "operation not permitted" in out.lower(), out
    # Seat가 파이프라인 저장소(IR, RTL, 실행 상태)에 쓰려 하면 거부
    for s in ("design.rtl", "design.lead", "lead.chip"):
        rc, out = dept.run(s, f"echo x >> {rtl_dir / 'state.json'}")
        assert rc != 0 and "operation not permitted" in out.lower(), (s, out)
    # 저장소 원본도 쓰지 못함. 자기 worktree에서는 작업하고 커밋할 수 있음
    rc, out = dept.run("design.rtl", f"echo x >> {ROOT / 'ARCHITECTURE.md'}")
    assert rc != 0, out
    rc, out = dept.run("design.rtl", "echo note > notes.txt && git add notes.txt && git -c user.name=t -c user.email=t@t "
                                     "commit -qm note && git log --oneline -1")
    assert rc == 0 and "note" in out, out
    # 환류 제출은 Design-lead에게만 보임
    rc, out = dept.run("design.rtl", "deptctl feedback x.json")
    assert rc == 2 and "Design-lead" in out, out
    rc, out = dept.run("dv.tb", "deptctl status " + rid)   # DV도 게이트웨이로 실행을 봄
    assert rc == 0 and rid in out, out
    rc, out = dept.run("design.lead", "deptctl decide x E1")   # Seat는 승인하지 못함
    assert rc == 2, out
    rig_up[1].joinpath("rid").write_text(rid)


@rig_only
def test_rig_seat_reset_does_not_affect_running_pipeline(rig_up):
    dept, tmp = rig_up
    rc, out = dept.run("design.rtl", f"deptctl submit {(tmp / 'spec_id').read_text()}")   # 새 실행 (앞 시험의 실행은 끝났을 수 있음)
    assert rc == 0, out
    rid = json.loads(out[out.index("{"):])["run_id"]
    rc, out = dept.run("design.rtl", f"deptctl status {rid}")
    st = json.loads(out[out.index("{"):])
    assert st["process"] == "running", st   # 진행 중인 실행
    before = st["agent_runs"]
    pane = lambda s: dept.tmux("display-message", "-p", "-t", dept.seatlib.session(s), "#{pane_pid}").stdout.strip()  # noqa: E731
    old = {s: pane(s) for s in ("design.rtl", "lead.chip")}
    # Seat 세션 초기화: 실행을 낸 RTL Engineer와 파이프라인 API 서버 노드까지
    for s in ("design.rtl", "lead.chip"):
        r = dept.reset(s)
        assert r["rc"] == 0, r
        assert dept.wait_ready(s) and pane(s) != old[s]   # 새 세션
    for node in ("infra-pipeline", "infra-gateway"):
        r = dept.rig("seat", "launch", f"{node}@{dept.RIG}", "--stop", "--fresh", "--reason", "reset test")
        assert r.returncode == 0, r.stdout + r.stderr
    assert dept.wait_ready("design.rtl")
    # 초기화된 Seat에서 같은 실행을 다시 보고, 실행은 끝까지 감
    deadline = time.time() + 600
    while time.time() < deadline:
        rc, out = dept.run("design.rtl", f"deptctl status {rid}")
        if rc == 0 and "{" in out:
            st = json.loads(out[out.index("{"):])
            if st["process"] == "stopped":
                break
        time.sleep(5)
    assert st["status"] == "pass" and st["agent_runs"] >= before, st


@rig_only
def test_rig_snapshot_restore(rig_up):
    """복구 절차: rig down --snapshot 뒤 rig up <이름>으로 토폴로지를 되살린다. 실행 상태는 저장소에 남아 있다."""
    dept, tmp = rig_up
    runs_before = json.loads(dept.run("design.rtl", "deptctl runs")[1] or "[]")
    r = dept.snapshot_down()
    assert r["rc"] == 0, r
    assert dept.tmux("has-session", "-t", dept.seatlib.session("design.rtl")).returncode != 0
    r = dept.recover()   # 앞 시험에서 Seat를 새로 띄웠으므로 스냅숏 대신 rig.yaml로 되살아날 수 있음
    assert r["rc"] == 0, r
    for s in ("design.rtl", "dv.tb", "lead.chip"):
        assert dept.wait_ready(s), (s, dept.capture(s)[-800:])
    deadline = time.time() + 60
    while time.time() < deadline:
        rc, out = dept.run("design.rtl", "deptctl runs")
        if rc == 0:
            break
        time.sleep(2)
    assert rc == 0 and [x["run_id"] for x in json.loads(out)] == [x["run_id"] for x in runs_before]
    rc, out = dept.run("dv.tb", f"ls {tmp / 'dh' / 'store'}")   # 복구된 Seat에도 sandbox가 다시 걸림
    assert rc != 0 and "operation not permitted" in out.lower(), out


def test_seat_trusts_own_worktree_in_agy_settings(tmp_path):
    """agent 모드 Seat는 자기 worktree를 agy 신뢰 목록에 넣는다 (다른 설정은 그대로, 중복 없이)."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("seat_entry", str(DEPT / "bin" / "seat"))
    spec = importlib.util.spec_from_loader("seat_entry", loader)
    seat = importlib.util.module_from_spec(spec)
    loader.exec_module(seat)
    cfg = tmp_path / ".gemini" / "antigravity-cli" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"model": "x", "trustedWorkspaces": ["/a"]}))
    wt = tmp_path / "seats" / "dv-tb"
    assert seat.trust_worktree(wt, tmp_path) is True
    assert seat.trust_worktree(wt, tmp_path) is False
    assert json.loads(cfg.read_text()) == {"model": "x", "trustedWorkspaces": ["/a", str(wt)]}
    cfg.write_text("{broken")
    assert seat.trust_worktree(wt, tmp_path) is False and cfg.read_text() == "{broken"   # 깨진 설정은 건드리지 않음
