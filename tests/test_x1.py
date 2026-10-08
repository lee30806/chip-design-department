import json
import sys
from pathlib import Path

import pytest

from common.agent import AgentConfig, run_agent
from x1_structured_output import run_x1

FAKE = str(Path(__file__).resolve().parent / "fake_agent.py")


def agent(mode, **kw):
    return AgentConfig(name=f"fake-{mode}", family="F", runtime="fake",
                       command=[sys.executable, FAKE, "{prompt}"], env={"FAKE_MODE": mode}, **kw)


def test_good_agent_passes_and_uses_validator(tmp_path):
    r = run_x1.run_trial(agent("good"), tmp_path / "w", retry=1)
    assert r["first"]["ok"] and r["final"]["ok"] and r["attempts"] == 1
    assert r["validator_calls"] == 1 and r["scope_violations"] == [] and r["exit_ok"]


def test_retry_feeds_errors_into_new_task(tmp_path):
    r = run_x1.run_trial(agent("bad_then_good"), tmp_path / "w", retry=1)
    assert not r["first"]["ok"] and r["final"]["ok"] and r["attempts"] == 2
    assert r["validator_calls"] == 0


def test_write_outside_scope_is_reported(tmp_path):
    r = run_x1.run_trial(agent("touch_l1"), tmp_path / "w", retry=0)
    assert r["final"]["ok"]  # 결과 파일 자체는 정상
    assert r["scope_violations"] == ["수정: l1.json"]


def test_crash_and_missing_command_are_failures(tmp_path):
    r = run_x1.run_trial(agent("crash"), tmp_path / "w", retry=0)
    assert not r["exit_ok"] and not r["out_exists"] and not r["final"]["ok"]
    missing = AgentConfig(name="x", family="F", runtime="x", command=["no-such-agent-binary"])
    (tmp_path / "m").mkdir()
    assert run_agent(missing, tmp_path / "m", "t").returncode == 127


def test_timeout(tmp_path):
    slow = AgentConfig(name="s", family="F", runtime="x", timeout_s=0.5,
                       command=[sys.executable, "-c", "import time; time.sleep(5)"])
    (tmp_path / "s").mkdir()
    run = run_agent(slow, tmp_path / "s", "t")
    assert run.timed_out and not run.exit_ok


def test_command_template_substitution(tmp_path):
    echo = AgentConfig(name="e", family="F", runtime="x", model="M1",
                       command=[sys.executable, "-c", "import sys; print(sys.argv[1:])", "{model}", "{prompt_file}", "{workdir}"])
    (tmp_path / "e").mkdir()
    run = run_agent(echo, tmp_path / "e", "t")
    assert "M1" in run.stdout_tail and "TASK.md" in run.stdout_tail and str(tmp_path / "e") in run.stdout_tail


def test_validator_cli_detects_l1_change_separately_from_schema(tmp_path):
    from x1_structured_output.validate_ir import check_file
    w = tmp_path / "w"
    run_x1.prepare_workdir(w)
    ir = json.loads(json.dumps(run_x1.FIXTURE))
    ir["params"][0]["default"] = "8'h5A"
    (w / "out" / "a.json").write_text(json.dumps(ir))
    r = check_file(w / "out" / "a.json", w)
    assert r["schema_ok"] and not r["l1_frozen"] and not r["ok"]


def test_main_writes_summary(tmp_path):
    cfg = vars(agent("good"))
    (tmp_path / "agents.json").write_text(json.dumps({"agents": [{"_note": "x", **cfg}]}))
    assert run_x1.main(["--agents", str(tmp_path / "agents.json"), "--trials", "2", "--out", str(tmp_path)]) == 0
    summary = next(tmp_path.glob("x1-*/summary.md")).read_text(encoding="utf-8")
    assert "| fake-good | fake | F | 2 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |" in summary


def test_example_config_loads():
    from common.agent import load_agents
    agents = load_agents(Path(__file__).resolve().parents[1] / "experiments" / "p0" / "agents.example.json")
    assert {a.runtime for a in agents} == {"pi", "codex", "claude-code"}
