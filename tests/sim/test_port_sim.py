"""P11 원본 RTL에서 IR과 SPEC 만들기: 시뮬레이션이 필요한 부분 (R4 사이클 등가, R6 트랜잭션 비교, pl.py porteq, 실행기 전체 흐름).

R4와 R6의 '이식 IR'과 '재생성 IR' 자리에는 손으로 쓴 IR(golden, 시험용 원본의 ported/)과 그것을 일부러 틀리게 바꾼 IR을 쓴다.
실행기 시험은 가짜 에이전트(tests/fake_port_agent.py)와 가짜 재생성 함수로 단계 전환만 본다.
"""
import copy
import json
import shutil
import subprocess
import sys

import pytest

pytest.importorskip("cocotb_tools.runner")
if not shutil.which("verilator"):
    pytest.skip("verilator 없음", allow_module_level=True)

from pipeline.agents import porter  # noqa: E402
from pipeline.agents.roles import Roles  # noqa: E402
from pipeline.agents.runner import AgentConfig  # noqa: E402
from pipeline.importer import r1 as r1_mod, r4, r6  # noqa: E402
from pipeline.importer.sources import Inputs, read_filelist  # noqa: E402
from pipeline.scheduler.port import PortRun  # noqa: E402
from pipeline.scheduler.run import STUB_CELLS  # noqa: E402
from test_pipeline import ROOT  # noqa: E402

G = ROOT / "tests" / "golden"
FX = ROOT / "tests" / "fixtures" / "port"
FAST = {"seeds": (1,), "cycles": 600}


def _r1(tmp_path, files, top, params=None, defines=None, incs=None):
    return r1_mod.run(Inputs(files, top, params or {}, incs or [], defines or {}), tmp_path)


def _golden_r1(tmp_path, blk):
    g = json.loads((G / blk / "golden.json").read_text())
    top = "uart" if blk == "uart" else g["runs"][0]["top"]
    files = sorted([G / blk / f for f in g["upstream_rtl"]], key=lambda f: f.stem == top)
    return _r1(tmp_path, files, top, {k: str(v) for k, v in g.get("upstream_params", {}).get(top, {}).items()})


def _lib(dirpath, names):
    return {n: json.loads((dirpath / f"{n}.ir.json").read_text()) for n in names}


def test_r4_golden_adapter_equal_and_mutation(tmp_path):
    r1 = _golden_r1(tmp_path, "axis_adapter")
    lib = _lib(G / "axis_adapter" / "ir", ["axis_adapter"])
    assert r4.run_module("axis_adapter", lib, r1, tmp_path / "r4", STUB_CELLS, **FAST)["status"] == "equal"
    bad = copy.deepcopy(lib)
    text = json.dumps(bad["axis_adapter"])
    assert "m_axis_tlast <= s_axis_tlast_reg;" in text
    bad["axis_adapter"] = json.loads(text.replace("m_axis_tlast <= s_axis_tlast_reg;", "m_axis_tlast <= !s_axis_tlast_reg;", 1))
    res = r4.run_module("axis_adapter", bad, r1, tmp_path / "r4b", STUB_CELLS, **FAST)
    assert res["status"] == "differ" and res["first"]["port"] == "m_axis_tlast"


def test_r4_reset_only_and_hierarchy(tmp_path):
    """uart: 원본의 초기값만 있는 레지스터(txd = 1)를 IR은 리셋으로 옮겨 리셋 구간에서만 다름. 아래에서 위로 비교."""
    r1 = _golden_r1(tmp_path, "uart")
    lib = _lib(G / "uart" / "ir", r1["order"])
    res = r4.run_all(r1["order"], lib, r1, tmp_path / "r4", STUB_CELLS, **FAST)
    assert {n: r["status"] for n, r in res.items()} == {"uart_tx": "reset_only", "uart_rx": "reset_only", "uart": "reset_only"}
    assert res["uart_tx"]["first"]["in_window"]


def test_r4_mixed_sources_two_define_sets(tmp_path):
    files, incs, defs = read_filelist(FX / "mixed" / "files.f")
    for combo, extra in (("default", {}), ("use_sub", {"USE_SUB": "1"})):
        r1 = _r1(tmp_path / combo, files, "mix_top", {}, {**defs, **extra}, incs)
        assert r1["ok"], r1["rejects"]
        lib = _lib(FX / "mixed" / "ported" / combo, r1["order"])
        res = r4.run_all(r1["order"], lib, r1, tmp_path / combo / "r4", STUB_CELLS, **FAST)
        assert {n: r["status"] for n, r in res.items()} == {"acc": "equal", "mix_top": "equal"}, (combo, res)
    lib = _lib(FX / "mixed" / "ported" / "default", r1["order"])   # USE_SUB 원본에 기본 설정 IR: 달라야 함
    res = r4.run_all(r1["order"], lib, r1, tmp_path / "cross", STUB_CELLS, **FAST)
    assert res["acc"]["status"] == "differ" and res["mix_top"]["status"] == "skipped"


@pytest.mark.parametrize("name,top,mod", [("pp", "pp_top", "pp_core"), ("od", "od_top", "od_ctrl")])
def test_r4_inout_pad_model(tmp_path, name, top, mod):
    r1 = _r1(tmp_path, [FX / "inout" / f"{name}.v"], top)
    lib = _lib(FX / "inout" / "ported", r1["order"])
    res = r4.run_all(r1["order"], lib, r1, tmp_path / "r4", STUB_CELLS, **FAST)
    assert {n: r["status"] for n, r in res.items()} == {mod: "equal", top: "equal"}
    if name == "pp":   # 나눈 포트를 가진 하위 모듈도 원본처럼 합쳐 비교하므로 틀리면 잡힘
        bad = copy.deepcopy(lib)
        bad[mod]["blocks"][0]["body"] = bad[mod]["blocks"][0]["body"].replace("~pad_oe", "pad_oe")
        assert r4.run_module(mod, bad, r1, tmp_path / "r4b", STUB_CELLS, **FAST)["status"] == "differ"


def test_r6_compare_and_minimize(tmp_path):
    r1 = _golden_r1(tmp_path, "axis_cobs_decode")
    ir = _lib(G / "axis_cobs_decode" / "ir", ["axis_cobs_decode"])["axis_cobs_decode"]
    seeds = (("steady", 1), ("reset", 3))
    res = r6.run(ir, {"axis_cobs_decode": ir}, r1, tmp_path / "eq", STUB_CELLS, cycles=800, seeds=seeds)
    assert res["status"] == "equal" and res["timing"][0]["delta_max"] == 0
    bad = json.loads(json.dumps(ir).replace("m_axis_tuser <= m_axis_tuser_int;", "m_axis_tuser <= !m_axis_tuser_int;", 1))
    res = r6.run(ir, {"axis_cobs_decode": bad}, r1, tmp_path / "bad", STUB_CELLS, cycles=800, seeds=seeds, budget=12)
    assert res["status"] == "differ"
    j = r6.judge_input(res)
    assert j["difference"]["stream"] == "m_axis" and "s_axis" in j["inputs"]


def test_porteq_tool(tmp_path):
    r1 = _golden_r1(tmp_path / "r1", "axis_cobs_decode")
    work = tmp_path / "w"
    porter.make_ref_dir(r1, work / "ref")
    shutil.copy(G / "axis_cobs_decode" / "ir" / "axis_cobs_decode.ir.json", work / "m.ir.json")
    r = subprocess.run([sys.executable, str(ROOT / "pipeline" / "agents" / "pl.py"), "porteq", "m.ir.json", "--ref", "ref",
                        "--cycles", "500"], cwd=work, capture_output=True, text=True, env={"PL_NO_LOG": "1", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    out = json.loads(r.stdout)
    assert out["ok"] and out["status"] == "equal", r.stdout + r.stderr


def test_port_runner_flow_with_fake_agents(tmp_path, monkeypatch):
    """start → R2 대기 → answer → resume: Porter(첫 시도 틀림 → R4 차이 → 고치기) → SpecWriter → R6(1차 차이 → 판정 spec_gap
    → SPEC 고치기 → 2차 같음) → 묶음."""
    blk = "axis_cobs_decode"
    cfg = AgentConfig("fake", "Test", "fake", [sys.executable, str(ROOT / "tests" / "fake_port_agent.py")], "m",
                      env={"FAKE_PORTED": str(G / blk / "ir"), "FAKE_SPEC_BASE": str(G / blk / "block_spec.md"),
                           "FAKE_BAD_FIRST": "m_axis_tuser <= m_axis_tuser_int;=>m_axis_tuser <= !m_axis_tuser_int;"}, timeout_s=120)
    roles = Roles({"porter": cfg, "spec_writer": cfg, "arbiter": cfg}, {}, {"agent_retries": 0, "porter_fix": 2, "spec_revise": 2})
    good = json.loads((G / blk / "ir" / f"{blk}.ir.json").read_text())
    bad = json.loads(json.dumps(good).replace("m_axis_tuser <= m_axis_tuser_int;", "m_axis_tuser <= !m_axis_tuser_int;", 1))
    calls = []

    def regen(spec, regen_dir):
        calls.append(spec.read_text())
        return "pass", {blk: bad if len(calls) == 1 else good}, [], 0

    run_dir = tmp_path / "run"
    pr = PortRun(run_dir)
    st = pr.start(Inputs([G / blk / "upstream" / "rtl" / f"{blk}.v"], blk))
    assert st["stage"] == "r2" and st["status"] == "waiting_user"
    qs = {q["id"] for q in st["questions"]}
    assert "freq.sys" in qs and f"proto.{blk}.s_axis" in qs
    out = pr.answer({"freq.sys": "100"})
    assert out["unanswered"]
    ans = {q: ("ok" if q.startswith("review") else "valid_ready") for q in qs if q != "freq.sys"}
    out = PortRun(run_dir).answer(ans)
    assert out["errors"] == [] and out["stage"] == "r3"
    pr = PortRun(run_dir, roles, isolate=False, regen_fn=regen, r4_kw=FAST,
                 r6_kw={"cycles": 800, "seeds": (("steady", 1),), "budget": 8})
    st = pr.resume()
    assert st["status"] == "pass", st
    assert st["modules"][blk] == {"status": "equal", "attempts": 2}
    rounds = pr.state["r6"]["rounds"]
    assert [r["compare"] for r in rounds] == ["differ", "equal"] and rounds[0]["verdict"]["verdict"] == "spec_gap"
    assert "FAKE-99" in calls[1] and "FAKE-99" not in calls[0]
    pkg = run_dir / "package"
    assert (pkg / "spec.md").exists() and (pkg / "ir" / f"{blk}.ir.json").exists() and (pkg / "harness" / f"{blk}_harness.py").exists()
    g = json.loads((pkg / "golden.json").read_text())
    assert g["r4"] == {blk: "equal"} and len(g["r6"]) == 2


def test_pipeline_inout_block_top_harness_and_diffsim(tmp_path):
    """일반 파이프라인이 inout Block Top을 다룸: 생성 하니스(패드 모델 뷰)와 패드 래퍼 top으로 E2 시뮬레이션, run_diffsim."""
    from pipeline.scheduler.run import emit_lib, run_diffsim
    from pipeline.tb.gen import harness_source, pad_top
    from pipeline.verify.run import sim
    from pipeline.ir.model import Module

    lib = _lib(FX / "inout" / "ported", ["od_ctrl", "od_top"])
    files, _ = emit_lib(lib, tmp_path / "rtl", STUB_CELLS)
    (tmp_path / "h").mkdir()
    (tmp_path / "h" / "od_top_harness.py").write_text(harness_source(Module(lib["od_top"])))
    pads, top = pad_top(lib["od_top"], tmp_path / "pad")
    assert top == "od_top_pad_top"
    r = sim([*files, *pads], top, "tb_od_top_h", ROOT / "tests" / "sim", tmp_path / "build", harness_dir=tmp_path / "h")
    assert r.ok, [f.message for f in r.findings]
    rec = run_diffsim(files, lib["od_top"], "reset", 1, tmp_path / "diff")
    assert rec is not None and rec["probe_at"] is not None


@pytest.mark.parametrize("name,top,mods", [("comb/cr", "cr_top", ["dec", "pipe", "cr_top"]), ("rsync/rs", "rs_top", ["rs_core", "rs_top"])])
def test_r4_comb_noreset_and_reset_sync(tmp_path, name, top, mods):
    """조합 모듈(가상 클럭 래퍼로 모듈 단위 비교), 리셋 없는 도메인, top의 리셋 동기화기(reset.synchronize)."""
    r1 = _r1(tmp_path, [FX / f"{name}.v"], top)
    assert r1["ok"], r1
    lib = _lib(FX / name.split("/")[0] / "ported", r1["order"])
    res = r4.run_all(r1["order"], lib, r1, tmp_path / "r4", STUB_CELLS, **FAST)
    assert {n: r["status"] for n, r in res.items()} == {m: "equal" for m in mods}
    if name.startswith("comb"):
        bad = copy.deepcopy(lib)
        bad["dec"]["blocks"][0]["body"] = bad["dec"]["blocks"][0]["body"].replace("1'b1", "1'b0")
        assert r4.run_module("dec", bad, r1, tmp_path / "r4b", STUB_CELLS, **FAST)["status"] == "differ"
