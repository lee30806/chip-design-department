"""번역기 검사용 cocotb 테스트 (사람이 검증하는 부분). `pyequiv.check`가 부른다.

같은 무작위 입력(가끔 리셋 포함)을 RTL과 설계 모델 실행기(`pysim`)에 넣고, 하강 에지 뒤 매 사이클 출력을 비교한다.
상승 에지마다 실행기도 한 사이클 진행한다. 첫 불일치를 결과 파일에 쓰고 실패한다.
"""
import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from pipeline.ir.model import Module
from pipeline.ir.pysim import PySim


@cocotb.test()
async def pyequiv(dut):
    cfg = json.loads(Path(os.environ["PYEQUIV_CFG"]).read_text(encoding="utf-8"))
    lib = {n: Module(r) for n, r in cfg["library"].items()}
    top = lib[cfg["top"]]
    sim = PySim(top, lib)
    dom = next(iter(top.domains.values()))
    clk, rport = dom["clock"], dom["reset"]["port"]
    act = 0 if dom["reset"]["active"] == "low" else 1
    rng = random.Random(cfg["seed"])
    ins = sim.inputs()
    outs = [p.name for p in top.ports if p.dir == "output"]

    def drive(c: int) -> None:
        vals = {n: rng.getrandbits(w) for n, w in ins.items() if n != rport}
        vals[rport] = act if c < cfg["reset_cycles"] or rng.random() < cfg["reset_prob"] else 1 - act
        for n, v in vals.items():
            getattr(dut, n).value = v
        sim.set(vals)
        sim.settle()

    drive(0)
    cocotb.start_soon(Clock(getattr(dut, clk), 10, unit="ns").start(start_high=False))
    mismatch = None
    for c in range(cfg["cycles"]):
        await RisingEdge(getattr(dut, clk))
        sim.step()
        await FallingEdge(getattr(dut, clk))
        drive(c + 1)
        await ReadOnly()
        for o in outs:
            got = int(getattr(dut, o).value)
            if got != sim.val[o]:
                mismatch = {"cycle": c, "output": o, "rtl": got, "py": sim.val[o],
                            "inputs": {n: sim.val[n] for n in ins}}
                break
        if mismatch:
            break
    Path(cfg["out"]).write_text(json.dumps({"ok": mismatch is None, "cycles": cfg["cycles"], "mismatch": mismatch},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
    assert mismatch is None, f"RTL과 설계 모델이 다름: {mismatch}"
