"""P4: 작업 실행기, 역할 설정, 에이전트 도구 CLI."""
import json
import subprocess
import sys
from pathlib import Path

from pipeline.agents.runner import AgentConfig
from pipeline.agents.task import Task, prepare, run_task
from test_pipeline import LIB, ROOT

FAKE = str(ROOT / "tests" / "fake_agent.py")


def _cfg(mode, **env):
    return AgentConfig("fake", "Test", "fake", [sys.executable, FAKE], "m", env={"FAKE_MODE": mode, **env}, timeout_s=120)


def _task(**kw):
    return Task("author", "author/x/c0", "과제", inputs={"input.txt": "원본"}, tools=False, outputs=["out/result.txt"],
                isolate=False, **kw)  # 가짜 agent는 저장소 안의 파이썬과 스크립트를 쓰므로 격리 없이


def test_task_collects_outputs_and_records(tmp_path):
    r = run_task(_cfg("task_write"), _task(), tmp_path / "w")
    assert r.ok and r.outputs == {"out/result.txt": str(tmp_path / "w" / "out" / "result.txt")} and r.violations == []
    rec = json.loads((tmp_path / "w" / ".task.json").read_text())
    assert rec["role"] == "author" and rec["runs"][0]["returncode"] == 0


def test_task_rejects_writes_outside_scope(tmp_path):
    r = run_task(_cfg("task_escape"), _task(), tmp_path / "w")
    assert not r.ok and r.violations == ["수정: input.txt"]


def test_task_retries_with_check_errors(tmp_path):
    def check(work):
        return [] if (work / "out" / "result.txt").read_text() == "good" else ["결과가 bad임"]

    r = run_task(_cfg("task_retry"), _task(), tmp_path / "w", check=check, retries=1)
    assert r.ok and r.attempts == 2 and r.runs[0]["errors"] == ["결과가 bad임"]
    r = run_task(_cfg("task_retry"), _task(), tmp_path / "w2", check=lambda w: ["항상 실패"], retries=0)
    assert not r.ok and r.attempts == 1 and r.errors == ["항상 실패"]


def test_missing_output_is_an_error(tmp_path):
    r = run_task(_cfg("crash"), _task(), tmp_path / "w")
    assert not r.ok and r.missing == ["out/result.txt"]


def test_roles_warn_on_same_family():
    from pipeline.agents.roles import load

    roles = load()
    assert roles.agents["author"].model == "gemini-3.8-flash-high" and roles.counts["author"] == 2
    assert roles.warnings() and "Gemini" in roles.warnings()[0]


# ---------------------------------------------------------------- 도구 CLI (작업 디렉터리에 설치된 사본)
def _installed(tmp_path):
    w = tmp_path / "w"
    raw = LIB["pkt_parser"].raw
    l1 = {k: raw[k] for k in ("module", "role", "params", "domains", "ports")}
    prepare(Task("author", "t", "x", inputs={"in/ir.json": json.dumps(raw), "in/l1.json": json.dumps(l1),
                                              "in/spec.md": (ROOT / "examples/i3c_basic_controller/spec.md").read_text()}), w)
    return w


def _pl(w, *args):
    p = subprocess.run([sys.executable, "tools/pl.py", *args], cwd=w, capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


def test_tools_cli_in_workdir(tmp_path):
    w = _installed(tmp_path)
    assert _pl(w, "validate", "in/ir.json", "--l1", "in/l1.json") == (0, {"ok": True, "errors": [], "warnings": []})
    raw = json.loads((w / "in/ir.json").read_text())
    raw["ports"][1]["reset"] = "1'b1"          # 출력의 리셋값은 Author가 정함 (동결 아님)
    (w / "in/ok.json").write_text(json.dumps(raw))
    assert _pl(w, "validate", "in/ok.json", "--l1", "in/l1.json")[0] == 0
    raw["ports"][1]["type"] = "logic [1:0]"    # 포트 타입은 동결
    (w / "in/bad.json").write_text(json.dumps(raw))
    rc, out = _pl(w, "validate", "in/bad.json", "--l1", "in/l1.json")
    assert rc == 1 and any("[동결] ports" in e for e in out["errors"])
    (w / "in/p.json").write_text(json.dumps([{"op": "set", "target": "ports/pkt_valid", "field": "reset", "value": "1"}]))
    rc, out = _pl(w, "patch", "in/ir.json", "in/p.json")
    assert rc == 1 and out["rejected"]
    out = _pl(w, "spec", "in/spec.md", "TR-07", "FR-99")[1]
    assert out["unknown"] == ["FR-99"] and out["requirements"][0]["text"].startswith("Bus Available")
    assert "blocks/k_cnt" in _pl(w, "fanin", "in/ir.json", "pkt_valid")[1]["nodes"]
    assert "module pkt_parser" in _pl(w, "emit", "in/ir.json")[1]["sv"]
    assert (w / _pl(w, "harness", "in/l1.json", "-o", "out/tb")[1]["harness"]).exists()
    (w / "out/model.py").write_text("class Model:\n    def on_input(self, s, t):\n        return [('pkt_valid', {'pkt_valid': 1})]\n")
    assert _pl(w, "model", "out/model.py", "in/l1.json", "--n", "20")[1] == {"ok": True, "inputs": 20, "skipped": 0, "expected_outputs": {"pkt_valid": 20}}
    (w / "out/bad_model.py").write_text("class Model:\n    def on_input(self, s, t):\n        return 1/0\n")
    assert _pl(w, "model", "out/bad_model.py", "in/l1.json")[1]["ok"] is False
    assert len((w / ".tools.log").read_text().splitlines()) == 10


def test_agent_can_call_tools(tmp_path):
    raw = LIB["pkt_parser"].raw
    t = Task("author", "t", "x", inputs={"in/ir.json": json.dumps(raw)}, outputs=["out/result.txt"], isolate=False)
    r = run_task(_cfg("task_tools"), t, tmp_path / "w")
    assert r.ok and json.loads(Path(r.outputs["out/result.txt"]).read_text())["ok"] is True


# ---------------------------------------------------------------- 격리
import shutil  # noqa: E402

import pytest  # noqa: E402

from pipeline.agents.runner import IsolationUnavailable, isolate, sandbox_profile  # noqa: E402


def test_workdir_inside_repo_is_refused():
    t = Task("author", "t", "x", tools=False)
    with pytest.raises(ValueError):
        run_task(_cfg("task_write"), t, ROOT / "build" / "isolation_test")


@pytest.mark.skipif(not shutil.which("sandbox-exec"), reason="macOS sandbox-exec 없음")
def test_sandbox_blocks_repo_and_sibling_candidates(tmp_path):
    run = tmp_path / "run"
    (run / "author_c1").mkdir(parents=True)
    (run / "author_c1" / "answer.ir.json").write_text("정답")
    me = run / "author_c0"
    me.mkdir()
    cmd = ["/bin/sh", "-c", f"cat {ROOT}/README.md; cat {run}/author_c1/answer.ir.json; echo ok > {me}/w.txt && echo own-ok"]
    p = subprocess.run(isolate(cmd, [ROOT, run], [me]), capture_output=True, text=True)
    assert "own-ok" in p.stdout and "정답" not in p.stdout and p.stderr.count("Operation not permitted") == 2


def test_profile_and_missing_isolation(monkeypatch):
    prof = sandbox_profile([Path("/a")], [Path("/a/b")])
    assert prof.index('(deny file-read* file-write* (subpath "/a"))') < prof.index('(allow file-read* file-write* (subpath "/a/b"))')
    monkeypatch.setattr("pipeline.agents.runner.sys.platform", "linux")
    with pytest.raises(IsolationUnavailable):
        isolate(["true"], [], [])


# ---------------------------------------------------------------- 차분 검사
def test_verifier_and_candidate_diff(tmp_path):
    from pipeline.scheduler.run import candidate_diff, verifier_diff

    raw = LIB["pkt_parser"].raw
    l1 = {k: raw[k] for k in ("module", "role", "params", "domains", "ports")}
    a, b = tmp_path / "va.py", tmp_path / "vb.py"
    a.write_text("class Model:\n    def on_input(self, s, t):\n        return [('pkt_valid', {'pkt_valid': 1})] if t['s_data'] == 0xA5 else []\n")
    b.write_text("class Model:\n    def on_input(self, s, t):\n        return [('pkt_valid', {'pkt_valid': 1})] if t['s_data'] == 0x5A else []\n")
    assert verifier_diff([str(a), str(a)], l1) is None
    assert "s_data" in verifier_diff([str(a), str(b)], l1)
    for name, outs in (("c0", {"m": [{"x": 1}]}), ("c1", {"m": [{"x": 1}]}), ("c2", {"m": [{"x": 2}]})):
        (tmp_path / name).mkdir()
        (tmp_path / name / "t1.result.json").write_text(json.dumps({"outputs": outs}))
    assert candidate_diff([[str(tmp_path / "c0")], [str(tmp_path / "c1")]]) is None
    assert candidate_diff([[str(tmp_path / "c0")], [str(tmp_path / "c2")]]) == "t1"
