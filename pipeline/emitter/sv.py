"""IR에서 SystemVerilog를 결정론적으로 방출한다 (최소 Emitter, v0).

- 클럭과 리셋 포트는 domains에서 만든다. `seq` 블록의 `always_ff`와 리셋 분기는 Emitter가 씌운다.
- `fsm`은 상태 레지스터 `<state_name>_q`와 next-state 로직으로 방출한다.
- `cdc_sync`는 프로젝트 표준 동기화 셀 인스턴스로 방출한다. 셀 이름과 포트는 P0 자료로 확정할 때까지
  `sync_2ff (clk, rst_n, d, q)`를 가정한다.
- 인스턴스의 클럭과 리셋은 `domain_map`으로만 연결한다.
- 노드마다 `// @ir <노드>` 주석을 달고, 소스맵(노드 → 줄 범위)을 함께 낸다.

`memory` 블록은 아직 방출하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.ir.model import Module, load_library

SYNC_CELL = {"module": "sync_2ff", "clk": "clk", "rst": "rst_n", "d": "d", "q": "q"}


class EmitError(Exception):
    pass


@dataclass
class Emitted:
    module: str
    text: str
    sourcemap: list[dict] = field(default_factory=list)  # {"node", "start", "end"} (1부터 센 줄 번호)


class _Writer:
    def __init__(self):
        self.lines: list[str] = []
        self.map: list[dict] = []

    def line(self, s: str = "") -> None:
        self.lines.extend(s.split("\n"))

    def node(self, node: str):
        w = self

        class _Ctx:
            def __enter__(self):
                w.line(f"  // @ir {node}")
                self.start = len(w.lines) + 1

            def __exit__(self, *exc):
                w.map.append({"node": node, "start": self.start, "end": len(w.lines)})

        return _Ctx()


def _decl(type_: str, name: str) -> str:
    """`logic [7:0]` 같은 타입 문자열과 이름으로 선언문을 만든다."""
    return f"{type_} {name};"


def _reset_cond(dom: dict) -> str:
    r = dom["reset"]
    return f'!{r["port"]}' if r["active"] == "low" else r["port"]


def _sensitivity(dom: dict) -> str:
    edge = "posedge" if dom["edge"] == "pos" else "negedge"
    s = f'{edge} {dom["clock"]}'
    r = dom["reset"]
    if r["async"]:
        s += f' or {"negedge" if r["active"] == "low" else "posedge"} {r["port"]}'
    return s


def _indent(body: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + ln.strip() for ln in body.strip().split("\n"))


def _seq(w: _Writer, m: Module, dom: dict, resets: list[tuple[str, str]], body: str) -> None:
    w.line(f"  always_ff @({_sensitivity(dom)}) begin")
    if resets:
        w.line(f"    if ({_reset_cond(dom)}) begin")
        width = max(len(n) for n, _ in resets)
        for name, val in resets:
            w.line(f"      {name.ljust(width)} <= {val};")
        w.line("    end else begin")
        w.line(_indent(body, 6))
        w.line("    end")
    else:
        w.line(_indent(body, 4))
    w.line("  end")


def _fsm(w: _Writer, m: Module, b: dict) -> None:
    dom = m.domains[b["domain"]]
    q, d = f'{b["state_name"]}_q', f'{b["state_name"]}_d'
    _seq(w, m, dom, [(q, b["reset_state"])], f"{q} <= {d};")
    w.line("  always_comb begin")
    w.line(f"    {d} = {q};")
    w.line(f"    case ({q})")
    by_from: dict[str, list[dict]] = {}
    for t in b["transitions"]:
        by_from.setdefault(t["from"], []).append(t)
    for st, trs in by_from.items():
        w.line(f"      {st}: begin")
        for i, t in enumerate(trs):  # 배열 순서가 우선순위
            kw = "if" if i == 0 else "else if"
            w.line(f'        {kw} ({t["cond"]}) {d} = {t["to"]};  // @ir {t["id"]}')
        w.line("      end")
    w.line("      default: ;")
    w.line("    endcase")
    w.line("  end")


def _instance_nets(m: Module, library: dict[str, Module]) -> tuple[dict[tuple[str, str], str], list[tuple[str, str]]]:
    """(인스턴스, 자식 포트) → 부모 쪽 넷 이름. 인스턴스끼리 잇는 넷은 새 wire로 선언한다."""
    from pipeline.validator.checks import _endpoint_ports  # 같은 끝점 해석을 쓴다

    nets: dict[tuple[str, str], str] = {}
    wires: list[tuple[str, str]] = []
    for c in m.connections:
        ends = [_endpoint_ports(m, c[k], library) for k in ("from", "to")]
        if not all(ends):
            raise EmitError(f'connections/{c["id"]}: 끝점을 해석할 수 없음 (Validator V2를 먼저 통과해야 함)')
        owners = [c[k].split(".", 1)[0] for k in ("from", "to")]
        for (da, na), (db, nb) in zip(*ends):
            if owners[0] == "self" or owners[1] == "self":
                self_name = na if owners[0] == "self" else nb
                inst, port = (owners[1], nb) if owners[0] == "self" else (owners[0], na)
                nets[(inst, port)] = self_name
            else:
                # 출력 쪽 인스턴스 포트 이름으로 wire를 만든다.
                src_i, src_p = (owners[0], na) if da == "output" else (owners[1], nb)
                net = f"{src_i}_{src_p}"
                child = library[next(i["module"] for i in m.instances if i["name"] == src_i)]
                wires.append((child.port(src_p).type, net))
                nets[(owners[0], na)] = net
                nets[(owners[1], nb)] = net
    return nets, wires


def emit(m: Module, library: dict[str, Module] | None = None) -> Emitted:
    library = {**(library or {}), m.name: m}
    w = _Writer()
    w.line(f"// Generated from IR module '{m.name}'. Do not edit; change the IR and re-emit.")
    ports = [p for p in m.ports]
    plist = ",\n".join(f"  {p.dir.ljust(6)} {p.type} {p.name}" for p in ports)
    if m.params:
        params = ",\n".join(f'  parameter {p["type"]} {p["name"]} = {p["default"]}' for p in m.params)
        w.line(f"module {m.name} #(\n{params}\n) (\n{plist}\n);")
    else:
        w.line(f"module {m.name} (\n{plist}\n);")

    for t in m.types:
        with w.node(f'types/{t["name"]}'):
            if t["kind"] == "enum":
                base = f'{t["base"]} ' if t.get("base") else ""
                w.line(f'  typedef enum {base}{{{", ".join(t["members"])}}} {t["name"]};')
            else:
                fields = " ".join(f'{f["type"]} {f["name"]};' for f in t["fields"])
                w.line(f'  typedef struct packed {{ {fields} }} {t["name"]};')
    for s in m.signals:
        w.line(f"  {_decl(s.type, s.name)}")
    for b in m.blocks:
        if b["kind"] == "fsm":
            w.line(f'  {b["state_type"]} {b["state_name"]}_q, {b["state_name"]}_d;')

    nets, wires = _instance_nets(m, library) if m.instances else ({}, [])
    for type_, name in wires:
        w.line(f"  {_decl(type_, name)}")
    w.line()

    storage = m.storage()
    for b in m.blocks:
        node = f'blocks/{b["id"]}'
        with w.node(node):
            if b["kind"] == "comb":
                w.line("  always_comb begin")
                w.line(_indent(b["body"], 4))
                w.line("  end")
            elif b["kind"] == "seq":
                resets = [(n, storage[n].reset) for n in b["writes"] if storage[n].reset is not None]
                _seq(w, m, m.domains[b["domain"]], resets, b["body"])
            elif b["kind"] == "fsm":
                _fsm(w, m, b)
            elif b["kind"] == "cdc_sync":
                dom = m.domains[b["dst_domain"]]
                c = SYNC_CELL
                w.line(f'  {c["module"]} u_{b["id"]} (.{c["clk"]}({dom["clock"]}), .{c["rst"]}({dom["reset"]["port"]}), '
                       f'.{c["d"]}({b["src"]}), .{c["q"]}({b["dst"]}));')
            else:
                raise EmitError(f"{node}: v0 Emitter는 {b['kind']} 블록을 방출하지 않음")
        w.line()

    for inst in m.instances:
        child = library[inst["module"]]
        conns: list[str] = []
        for cd, dom in child.domains.items():
            pd = m.domains[inst["domain_map"][cd]]
            conns.append(f'.{dom["clock"]}({pd["clock"]})')
            conns.append(f'.{dom["reset"]["port"]}({pd["reset"]["port"]})')
        for p in child.ports:
            if not p.derived:
                conns.append(f'.{p.name}({nets.get((inst["name"], p.name), "")})')
        prm = ", ".join(f".{k}({v})" for k, v in inst.get("params", {}).items())
        with w.node(f'instances/{inst["name"]}'):
            head = f'  {child.name} #({prm}) {inst["name"]} (' if prm else f'  {child.name} {inst["name"]} ('
            w.line(head + "\n" + ",\n".join("    " + c for c in conns) + "\n  );")
        w.line()
    w.line("endmodule")
    return Emitted(m.name, "\n".join(w.lines) + "\n", w.map)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IR → SystemVerilog 방출")
    ap.add_argument("ir", nargs="+", help="IR JSON 파일들 (인스턴스가 참조하는 모듈도 함께)")
    ap.add_argument("-o", "--out", required=True, help="출력 디렉터리")
    args = ap.parse_args(argv)
    lib = load_library(args.ir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for m in lib.values():
        e = emit(m, lib)
        (out / f"{m.name}.sv").write_text(e.text, encoding="utf-8")
        (out / f"{m.name}.srcmap.json").write_text(json.dumps(e.sourcemap, indent=1), encoding="utf-8")
        print(out / f"{m.name}.sv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
