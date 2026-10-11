"""L1에서 cocotb 하니스를 생성한다.

- `<module>_harness.py`: L1(도메인, 포트, 번들)만으로 만든 하니스 설정. Verifier가 테스트에서 import한다.
- `<module>_trace.json`: 트레이스할 내부 신호(L2)와 도메인. Verify 툴만 쓰고 Verifier에게는 주지 않는다.

    python3 -m pipeline.tb.gen <ir.json> -o <하니스 dir> --trace-out <Verify 전용 dir>

트레이스 파일은 Verifier에게 주는 디렉터리와 다른 곳에 써야 한다.

번들 프로토콜은 지금 `valid_ready`만 안다 (표준 프로토콜 목록은 P0 자료로 확정).
번들 안의 신호 이름은 `..._valid`, `..._ready`로 끝나는 것이 각각 valid, ready이고 나머지가 data다.
"""
from __future__ import annotations

import argparse
import json
import pprint
import sys
from pathlib import Path

from pipeline.ir.model import Module, load

DEFAULT_PERIOD_NS = 10.0


class GenError(Exception):
    pass


def _width1(type_: str) -> bool:
    return type_.strip() in ("logic", "bit", "reg", "wire")


def _bundle(p: dict) -> dict:
    if p["protocol"] != "valid_ready":
        raise GenError(f'ports/{p["bundle"]}: 하니스가 모르는 프로토콜 {p["protocol"]}')
    if p["role"] not in ("source", "sink"):
        raise GenError(f'ports/{p["bundle"]}: valid_ready의 role은 source 또는 sink ({p["role"]})')
    names = [s["name"] for s in p["signals"]]
    valid = [n for n in names if n.endswith("valid")]
    ready = [n for n in names if n.endswith("ready")]
    if len(valid) != 1 or len(ready) != 1:
        raise GenError(f'ports/{p["bundle"]}: valid와 ready 신호를 하나씩 찾지 못함 ({names})')
    return {"name": p["bundle"], "protocol": p["protocol"], "domain": p["domain"], "dut_drives": p["role"] == "source",
            "valid": valid[0], "ready": ready[0], "data": [n for n in names if n not in (valid[0], ready[0])]}


def harness_config(m: Module) -> dict:
    """L1만 읽는다."""
    clocks = {d["name"]: (d["clock"], round(1000.0 / d["freq_mhz"], 3) if d.get("freq_mhz") else DEFAULT_PERIOD_NS)
              for d in m.domains.values()}
    resets = {d["name"]: (d["reset"]["port"], 0 if d["reset"]["active"] == "low" else 1) for d in m.domains.values()}
    bundles, outputs, inputs = [], [], []
    for p in m.raw["ports"]:
        if "bundle" in p:
            bundles.append(_bundle(p))
        elif p["dir"] == "output":
            outputs.append({"name": p["name"], "domain": p["domain"], "width": 1 if _width1(p["type"]) else 0})
        else:
            inputs.append(p["name"])
    port_domains = {p.name: p.domain for p in m.ports if not p.derived}
    return {"module": m.name, "clocks": clocks, "resets": resets, "bundles": bundles, "outputs": outputs,
            "inputs": inputs, "port_domains": port_domains}


def trace_names(m: Module) -> dict:
    """트레이스 설정. names: 신호 → 도메인 (포트, 내부 신호, FSM 상태. 도메인이 없는 wire는 모든 도메인 표본에서 읽음).
    outputs: DUT 출력 포트. Verify가 시드별 결과를 비교할 때(T1) 쓴다."""
    names = {p.name: p.domain for p in m.ports if not p.derived}
    for s in m.signals + m.state_regs():
        names[s.name] = s.domain if s.kind == "reg" else None
    return {"names": names, "outputs": [p.name for p in m.ports if p.dir == "output"]}


def harness_source(m: Module) -> str:
    cfg = pprint.pformat(harness_config(m), width=110, sort_dicts=False)
    return (f'"""Generated from IR L1 of \'{m.name}\'. Do not edit; change the IR and regenerate."""\n'
            "from pipeline.tb.lib import Harness\n\n"
            f"CFG = {cfg}\n\n\n"
            "def make(dut, model=None, *, name):\n"
            "    \"\"\"name은 테스트 이름. 결과 파일 이름이 된다.\"\"\"\n"
            "    return Harness(dut, CFG, model, name=name)\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="L1 → cocotb 하니스")
    ap.add_argument("ir")
    ap.add_argument("-o", "--out", required=True, help="하니스 디렉터리 (Verifier에게 줌)")
    ap.add_argument("--trace-out", required=True, help="트레이스 설정 디렉터리 (Verify만 씀)")
    args = ap.parse_args(argv)
    m = load(args.ir)
    out, tout = Path(args.out), Path(args.trace_out)
    if out.resolve() == tout.resolve():
        ap.error("--trace-out은 -o와 다른 디렉터리여야 함 (L2 이름이 Verifier에게 보이지 않도록)")
    out.mkdir(parents=True, exist_ok=True)
    tout.mkdir(parents=True, exist_ok=True)
    (out / f"{m.name}_harness.py").write_text(harness_source(m), encoding="utf-8")
    (tout / f"{m.name}_trace.json").write_text(json.dumps(trace_names(m), indent=1), encoding="utf-8")
    print(out / f"{m.name}_harness.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
