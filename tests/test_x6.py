import os
import stat
import sys
from pathlib import Path

import pytest

from x6_chat_roundtrip import run_x6

FAKE = Path(__file__).resolve().parent / "fake_rig.py"


@pytest.fixture
def rig_bin(tmp_path, monkeypatch):
    b = tmp_path / "rig"
    b.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    b.chmod(b.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_RIG_DIR", str(tmp_path))
    monkeypatch.setenv("FAKE_RIG_SEATS", "lead@t,eng@t")
    return str(b)


def summary(tmp_path):
    return next(tmp_path.glob("x6-*/summary.md")).read_text(encoding="utf-8")


def test_roundtrip_with_sender_and_concurrency(tmp_path, rig_bin):
    assert run_x6.main(["--rig", rig_bin, "--seats", "lead@t,eng@t", "--trials", "2",
                        "--poll", "0.05", "--out", str(tmp_path)]) == 0
    s = summary(tmp_path)
    assert "Seat 상태 조회(`rig ps --nodes -A --json`의 agentActivity): 가능" in s
    assert "| lead@t | single | 2 | 100% | 100% | 100% |" in s
    assert "| eng@t | concurrent | 2 | 100% | 100% | 100% |" in s


def test_probe_text_itself_is_not_mistaken_for_reply(tmp_path, rig_bin, monkeypatch):
    monkeypatch.setenv("FAKE_RIG_MODE", "silent")
    rig = run_x6.Rig(rig_bin)
    r = run_x6.one_trial(rig, "lead@t", "alice", "설계", timeout_s=0.3, poll_s=0.05)
    assert r["sent"] and not r["acked"]


def test_wrong_sender_is_detected(tmp_path, rig_bin, monkeypatch):
    monkeypatch.setenv("FAKE_RIG_MODE", "wrong_sender")
    r = run_x6.one_trial(run_x6.Rig(rig_bin), "lead@t", "alice", "설계", timeout_s=1, poll_s=0.05)
    assert r["acked"] and not r["sender_ok"]


def test_missing_cli_is_a_failure_not_a_crash(tmp_path):
    rig = run_x6.Rig(str(tmp_path / "no-such-rig"))
    assert rig.nodes() is None
    assert rig.send("lead@t", "hi")[0] is False


def test_raw_mode_passes_flag_and_screen_instruction(tmp_path, rig_bin):
    log = tmp_path / "args.log"
    b = tmp_path / "rig2"
    b.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\nexec {sys.executable} {FAKE} \"$@\"\n")
    b.chmod(0o755)
    r = run_x6.one_trial(run_x6.Rig(str(b), raw=True), "lead@t", "alice", "설계", timeout_s=1, poll_s=0.05)
    assert r["acked"] and "--raw" in log.read_text() and "화면에 직접" in log.read_text()
