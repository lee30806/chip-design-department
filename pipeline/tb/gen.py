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


def signal_widths(raw: dict) -> dict[str, int]:
    """L1 포트 신호의 비트 폭. 파라미터 기본값으로 계산하고, 계산할 수 없으면 8로 둔다."""
    import re
    params = {p["name"]: int(p["default"]) for p in raw.get("params", []) if str(p["default"]).isdigit()}
    out = {}
    for p in raw["ports"]:
        for s in p.get("signals", [p]):
            m = re.search(r"\[(.+?):(.+?)\]", s["type"])
            if not m:
                out[s["name"]] = 1
                continue
            try:
                out[s["name"]] = (eval(m.group(1), {"__builtins__": {}}, params)
                                  - eval(m.group(2), {"__builtins__": {}}, params) + 1)
            except Exception:
                out[s["name"]] = 8
    return out


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
    # 분주 도메인: 하니스가 기준 클럭 주기(ps) × 분주비로 맞춰 상승 에지를 정렬한다
    clock_sync = {d["name"]: (d["sync_to"]["domain"], d["sync_to"]["div"]) for d in m.domains.values() if d.get("sync_to")}
    extra_resets = {d["name"]: [(x["port"], 0 if x["active"] == "low" else 1) for x in d["reset"]["extra"]]
                    for d in m.domains.values() if d["reset"].get("extra")}
    bundles, outputs, inputs = [], [], []
    for p in m.raw["ports"]:
        if "bundle" in p:
            bundles.append(_bundle(p))
        elif p["dir"] == "output":
            outputs.append({"name": p["name"], "domain": p["domain"], "width": 1 if _width1(p["type"]) else 0})
        else:
            inputs.append(p["name"])
    port_domains = {p.name: p.domain for p in m.ports if not p.derived}
    cfg = {"module": m.name, "clocks": clocks, "resets": resets, "bundles": bundles, "outputs": outputs,
           "inputs": inputs, "port_domains": port_domains}
    if clock_sync:   # 단일 클럭 블록의 하니스는 예전과 같게 둔다
        cfg["clock_sync"] = clock_sync
    if extra_resets:
        cfg["extra_resets"] = extra_resets
    return cfg


def trace_names(m: Module, library: dict[str, Module] | None = None) -> dict:
    """트레이스 설정. names: 신호 → 도메인 (포트, 내부 신호, FSM 상태. 도메인이 없는 wire는 모든 도메인 표본에서 읽음).
    library가 있으면 인스턴스 포트도 `<인스턴스>.<포트>`로 넣는다 (Block Top에서 원인 모듈을 좁히려고).
    outputs: DUT 출력 포트. Verify가 시드별 결과를 비교할 때(T1) 쓴다.
    qualifiers: DUT가 내는 번들의 data 출력 → 그 번들의 valid. valid가 0인 사이클의 data 값은 비교하지 않는다.
    domains: 클럭 도메인. 둘 이상이면 T1은 사이클 비교를 하지 않는다 (시드에 따라 도메인 사이 위상이 바뀜)."""
    names = {p.name: p.domain for p in m.ports if not p.derived}
    for s in m.signals + m.state_regs():
        names[s.name] = s.domain if s.kind == "reg" else None
    for inst in m.instances if library else []:
        child = library.get(inst["module"])
        for p in child.ports if child else []:
            if not p.derived:
                names[f'{inst["name"]}.{p.name}'] = inst.get("domain_map", {}).get(p.domain)
    qual = {}
    for p in m.raw["ports"]:
        if "bundle" in p and p.get("protocol") == "valid_ready" and p.get("role") == "source":
            b = _bundle(p)
            qual.update({d: b["valid"] for d in b["data"]})
    return {"names": names, "outputs": [p.name for p in m.ports if p.dir == "output"], "qualifiers": qual,
            "domains": sorted(m.domains)}


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
