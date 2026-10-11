"""P4 스케줄러: 가짜 agent(역할별 정답 파일을 씀)로 SPEC부터 통합까지의 흐름, 재개, 사용량 한도 멈춤을 본다."""
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("cocotb_tools.runner")
if not shutil.which("verilator"):
    pytest.skip("verilator 없음", allow_module_level=True)

from pipeline.agents.roles import Roles  # noqa: E402
from pipeline.agents.runner import AgentConfig  # noqa: E402
from pipeline.ir.model import frozen_l1  # noqa: E402
from pipeline.scheduler.run import Run  # noqa: E402
from pipeline.spec.l1 import block_top_l1  # noqa: E402
from pipeline.spec.parse import load  # noqa: E402
from test_pipeline import ROOT  # noqa: E402

G = ROOT / "tests" / "golden" / "axis_adapter"
SPEC = G / "block_spec.md"
FAKE = str(ROOT / "tests" / "fake_agent.py")


def _files(tmp_path, author_ir=None):
    """Architect: Block Top(axis_adapter) 아래 하위 모듈 axis_adapter_core 하나. Author: golden IR. Verifier: 손으로 쓴 하니스 TB."""
    top, _ = block_top_l1(load(SPEC))
    golden = json.loads((G / "ir" / "axis_adapter.ir.json").read_text())
    core = copy.deepcopy(golden)
    core["module"] = "axis_adapter_core"
    child_l1 = frozen_l1(core)
    top = {**top, "instances": [{"name": "u_core", "module": "axis_adapter_core",
                                 "params": {p["name"]: p["name"] for p in top["params"]}, "domain_map": {"sys": "sys"}}],
           "connections": [{"id": "c_s", "from": "self.s_axis", "to": "u_core.s_axis"},
                           {"id": "c_m", "from": "u_core.m_axis", "to": "self.m_axis"}]}
    tb = tmp_path / "tb.py"
    tb.write_text((G / "harness" / "tb_axis_adapter_h.py").read_text().replace(
        "class Model:\n", "class Model:\n    def legal(self, s, t):\n        return t['s_axis_tkeep'] in (1, 3, 7, 15)\n\n", 1))
    return {
        "Architect": {"out/ir/axis_adapter.ir.json": json.dumps(top), "out/ir/axis_adapter_core.ir.json": json.dumps(child_l1),
                      "out/assumptions.json": json.dumps({"assumptions": ["동작은 하위 모듈 하나(axis_adapter_core)에 둠"]})},
        "Author": {"out/axis_adapter_core.ir.json": json.dumps(author_ir or core)},
        "Verifier": {"out/test_axis_adapter.py": f"@{tb}"},
    }


def _roles(tmp_path, files, mode="roles", author_mode=None):
    env = {"FAKE_MODE": mode, "FAKE_FILES": json.dumps(files), "FAKE_LOG": str(tmp_path / "calls.log")}
    cfg = AgentConfig("fake", "Test", "fake", [sys.executable, FAKE], "m", env=env, timeout_s=120)
    agents = {r: cfg for r in ("architect", "author", "verifier", "repair", "arbiter")}
    if author_mode:
        agents["author"] = AgentConfig("fake-a", "Other", "fake", [sys.executable, FAKE], "m", env={**env, "FAKE_MODE": author_mode})
    return Roles(agents, {"author": 2, "verifier": 2}, {"repair_per_candidate": 2, "agent_retries": 0, "budget_agent_runs": 50})


def _calls(tmp_path):
    p = tmp_path / "calls.log"
    return p.read_text().split() if p.exists() else []


def test_spec_to_rtl_with_fake_agents(tmp_path):
    run = Run(tmp_path / "run", SPEC, _roles(tmp_path, _files(tmp_path)), isolate=False)
    rep = run.execute()
    assert rep["status"] == "pass", json.dumps(rep, ensure_ascii=False)[:2000]
    assert rep["chosen"] == {"axis_adapter_core": 0}
    assert all(c["status"] == "pass" for c in rep["candidates"].values()) and len(rep["candidates"]) == 2
    assert (tmp_path / "run" / "rtl" / "axis_adapter.sv").exists() and (tmp_path / "run" / "rtl" / "axis_adapter_core.sv").exists()
    codes = {r["code"] for r in rep["review"]}
    assert {"ASSUMPTION", "MODEL_FAMILY"} <= codes   # 가짜 agent는 Author와 Verifier가 같은 계열이라 경고가 남음
    assert not codes & {"VERIFIER_DIFF", "VERIFIER_DIFF_SKIPPED", "CANDIDATE_DIFF"}   # 같은 TB, 같은 IR
    assert sorted(_calls(tmp_path)) == ["Architect", "Author", "Author", "Verifier", "Verifier"]


def test_resume_after_interruption(tmp_path, monkeypatch):
    files = _files(tmp_path)
    run = Run(tmp_path / "run", SPEC, _roles(tmp_path, files), isolate=False)
    monkeypatch.setattr(Run, "step_modules", lambda self, *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        run.execute()
    assert sorted(_calls(tmp_path)) == ["Architect", "Verifier", "Verifier"]
    monkeypatch.undo()
    rep = Run(tmp_path / "run", SPEC, _roles(tmp_path, files), isolate=False).execute()   # 새 프로세스처럼 상태 파일에서 시작
    assert rep["status"] == "pass"
    assert sorted(_calls(tmp_path)) == ["Architect", "Author", "Author", "Verifier", "Verifier"]   # 끝난 작업은 다시 부르지 않음
    assert any(e["kind"] == "resume" for e in rep["events"])


def test_quota_pauses_and_frozen_change_is_rejected(tmp_path):
    rep = Run(tmp_path / "q", SPEC, _roles(tmp_path, _files(tmp_path), author_mode="quota"), isolate=False).execute()
    assert rep["status"] == "paused_quota"
    core = json.loads(_files(tmp_path)["Author"]["out/axis_adapter_core.ir.json"])
    core["ports"][0]["signals"][0]["type"] = "logic [15:0]"   # 동결된 L1을 바꿈
    rep = Run(tmp_path / "f", SPEC, _roles(tmp_path, _files(tmp_path, core)), isolate=False).execute()
    assert rep["status"] == "failed"
    assert all("Author 실패" in (c["reason"] or "") for c in rep["candidates"].values())


def _out_module() -> dict:
    """M쪽 폭의 valid/ready를 그대로 넘기는 모듈 (하위 모듈이 둘인 트리 시험용)."""
    names = ["tdata", "tkeep", "tvalid", "tready", "tlast", "tid", "tdest", "tuser"]
    types = {"tdata": "logic [M_DATA_WIDTH-1:0]", "tkeep": "logic [M_KEEP_WIDTH-1:0]", "tid": "logic [ID_WIDTH-1:0]",
             "tdest": "logic [DEST_WIDTH-1:0]", "tuser": "logic [USER_WIDTH-1:0]"}

    def sig(side, n, d):
        s = {"name": f"{side}_axis_{n}", "dir": d, "type": types.get(n, "logic")}
        return {**s, "kind": "wire"} if d == "output" else s
    ports = [{"bundle": "s_axis", "protocol": "valid_ready", "role": "sink", "domain": "sys",
              "signals": [sig("s", n, "output" if n == "tready" else "input") for n in names]},
             {"bundle": "m_axis", "protocol": "valid_ready", "role": "source", "domain": "sys",
              "signals": [sig("m", n, "input" if n == "tready" else "output") for n in names]}]
    outs = [n for n in names if n != "tready"]
    body = "\n".join([f"m_axis_{n} = s_axis_{n};" for n in outs] + ["s_axis_tready = m_axis_tready;"])
    return {"module": "axis_adapter_out", "role": "module",
            "params": [{"name": p, "type": "int", "default": d} for p, d in
                       (("M_DATA_WIDTH", "8"), ("M_KEEP_WIDTH", "1"), ("ID_WIDTH", "8"), ("DEST_WIDTH", "8"), ("USER_WIDTH", "1"))],
            "domains": [{"name": "sys", "clock": "clk", "edge": "pos", "reset": {"port": "rst", "active": "high", "async": False}}],
            "ports": ports, "types": [], "signals": [],
            "blocks": [{"id": "k_pass", "kind": "comb", "reads": [f"s_axis_{n}" for n in outs] + ["m_axis_tready"],
                        "writes": [f"m_axis_{n}" for n in outs] + ["s_axis_tready"], "body": body}]}


def _files2(tmp_path, core_ir=None, repair=None):
    """하위 모듈 둘: axis_adapter_core(golden) → axis_adapter_out(그대로 넘김). 출력을 구동하는 것은 out."""
    f = _files(tmp_path)
    top = json.loads(f["Architect"]["out/ir/axis_adapter.ir.json"])
    core = json.loads(f["Author"]["out/axis_adapter_core.ir.json"])
    out = _out_module()
    top["instances"].append({"name": "u_out", "module": "axis_adapter_out",
                             "params": {p: p for p in ("M_DATA_WIDTH", "M_KEEP_WIDTH", "ID_WIDTH", "DEST_WIDTH", "USER_WIDTH")},
                             "domain_map": {"sys": "sys"}})
    top["connections"] = [{"id": "c_s", "from": "self.s_axis", "to": "u_core.s_axis"},
                          {"id": "c_mid", "from": "u_core.m_axis", "to": "u_out.s_axis"},
                          {"id": "c_m", "from": "u_out.m_axis", "to": "self.m_axis"}]
    f["Architect"]["out/ir/axis_adapter.ir.json"] = json.dumps(top)
    f["Architect"]["out/ir/axis_adapter_out.ir.json"] = json.dumps(frozen_l1(out))
    f["Author"] = {"out/axis_adapter_core.ir.json": json.dumps(core_ir or core), "out/axis_adapter_out.ir.json": json.dumps(out)}
    if repair is not None:
        f["Repair"] = {"out/patches.json": json.dumps(repair)}
    return f


def test_two_modules_verified_together(tmp_path):
    rep = Run(tmp_path / "run", SPEC, _roles(tmp_path, _files2(tmp_path)), isolate=False).execute()
    assert rep["status"] == "pass", json.dumps(rep, ensure_ascii=False)[:3000]
    assert rep["chosen"] == {"axis_adapter_core": 0, "axis_adapter_out": 0}
    assert len(rep["candidates"]) == 4 and all(c["status"] == "pass" for c in rep["candidates"].values())
    assert sorted(_calls(tmp_path)) == ["Architect"] + ["Author"] * 4 + ["Verifier"] * 2


def test_repair_goes_to_driver_then_suspected_sibling(tmp_path):
    sys.path.insert(0, str(ROOT / "tests" / "golden"))
    from bugs import BUGS

    core = json.loads(_files(tmp_path)["Author"]["out/axis_adapter_core.ir.json"])
    BUGS["adapter_shift"][1](core)
    # Repair는 항상 core를 지목한다: 출력 구동 모듈(out)의 Repair → core의 Repair. core가 자신을 지목하면 게이트가 거부
    files = _files2(tmp_path, core, [{"op": "suspect_module", "module": "axis_adapter_core", "reason": "데이터가 core에서 틀림"}])
    rep = Run(tmp_path / "run", SPEC, _roles(tmp_path, files), isolate=False).execute()
    assert rep["status"] == "failed"
    assert all("형제 모듈이 아님: axis_adapter_core" in c["reason"] for c in rep["candidates"].values())
    sus = [e["msg"] for e in rep["events"] if e["kind"] == "suspect"]
    assert sum(m.startswith("axis_adapter_out → axis_adapter_core") for m in sus) == 2   # 묶음 둘 다 out에서 시작
    agents = [e["msg"].split(":")[0] for e in rep["events"] if e["kind"] == "agent" and e["msg"].startswith("repair/")]
    assert sorted(agents) == ["repair/axis_adapter_core/c0/r0", "repair/axis_adapter_core/c1/r0",
                              "repair/axis_adapter_out/c0/r0", "repair/axis_adapter_out/c1/r0"]
    # 불일치 리포트의 팬인은 인스턴스 입력을 거쳐 형제 모듈로 이어지고, 인스턴스 포트 값이 트레이스에 있다
    fail = json.loads((tmp_path / "run" / "work" / "repair__axis_adapter_out__c0__r0" / "failure.json").read_text())
    assert fail["report"]["fanin"]["nodes"] == ["instances/u_out", "instances/u_core"]
    assert "u_out.s_axis_tdata" in fail["report"]["fanin"]["values"][-1]
