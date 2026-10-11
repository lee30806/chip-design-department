"""golden 블록: 생성 하니스 + 참조 모델로 T1~T5 회귀, 버그를 넣었을 때 불일치 리포트가 원인 노드를 포함하는지."""
import json
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("cocotb_tools.runner")
if not shutil.which("verilator"):
    pytest.skip("verilator 없음", allow_module_level=True)

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
sys.path.insert(0, str(GOLDEN))
import run_golden  # noqa: E402

from pipeline.classifier.classify import TYPES  # noqa: E402,F401
from pipeline.ir.model import Module, load_library  # noqa: E402
from pipeline.tb.report import mismatch_report  # noqa: E402

BLOCKS = ["axis_adapter", "axis_async_fifo", "axis_cobs_decode"]


@pytest.mark.parametrize("block", BLOCKS)
def test_harness_t1_to_t5(tmp_path, block):
    r = run_golden.run_harness(block, tmp_path)
    assert r["ok"], r["failed"]
    assert r["T3_matched"] > 0 and r["T2"] == 0 and r["T4"] == 0 and r["T1"] == "pass"
    assert r["T5"]["requirements"]["missed"] == []
    assert r["T5"]["verilator"]["line"]["ratio"] > 0.75


def _blk(raw, bid):
    return next(b for b in raw["blocks"] if b["id"] == bid)


def _tr(raw, bid, tid):
    return next(t for t in _blk(raw, bid)["transitions"] if t["id"] == tid)


BUGS = {
    # FSM 전이 조건: 세그먼트 길이를 하나 틀리게 셈
    "cobs_transition": ("axis_cobs_decode",
                        lambda r: _tr(r, "k_fsm", "t_seg_next").update(cond=_tr(r, "k_fsm", "t_seg_next")["cond"].replace("8'd1", "8'd2")),
                        "blocks/k_fsm/transitions/t_seg_next"),
    # datapath: 출력 바이트를 잘못된 레인에서 꺼냄
    "adapter_shift": ("axis_adapter",
                      lambda r: _blk(r, "k_data").update(body=_blk(r, "k_data")["body"].replace(
                          "s_axis_tdata_reg <= s_axis_tdata_reg >> SEG_DATA_WIDTH;", "s_axis_tdata_reg <= s_axis_tdata_reg >> (SEG_DATA_WIDTH * 2);")),
                      "blocks/k_data"),
    # 다중 클럭: 출력 필드 위치를 틀림
    "fifo_slice": ("axis_async_fifo",
                   lambda r: _blk(r, "k_m_comb").update(body=_blk(r, "k_m_comb")["body"].replace(
                       "m_axis_tid = m_axis_pipe_reg1[ID_OFFSET +: ID_WIDTH];", "m_axis_tid = m_axis_pipe_reg1[ID_OFFSET+1 +: ID_WIDTH];")),
                   "blocks/k_m_comb"),
}


@pytest.mark.parametrize("bug", sorted(BUGS))
def test_injected_bug_report_contains_cause(tmp_path, bug):
    block, mutate, cause = BUGS[bug]
    r = run_golden.run_harness(block, tmp_path, mutate=mutate, seeds=[1], coverage=False)
    assert not r["ok"]
    failed = [f["test"] for f in r["findings"] if f["test"]]
    assert failed, r["failed"]
    cfg = json.loads((GOLDEN / block / "golden.json").read_text())
    lib = load_library([GOLDEN / block / f for f in cfg["ir"]])
    raw = json.loads(json.dumps(lib[block].raw))
    mutate(raw)
    out = Path(r["out"])
    rep = mismatch_report(Module(raw), json.loads((out / f"{failed[0]}.result.json").read_text()),
                          json.loads((out / f"{failed[0]}.trace.json").read_text()),
                          (GOLDEN / block / "spec.md").read_text(), lib)
    assert cause in rep["fanin"]["nodes"] + rep["fanin"]["fsm_transitions"], rep["fanin"]["nodes"]
    assert rep["spec"]["clauses"], rep["first_failure"]
    assert rep["fanin"]["values"]
