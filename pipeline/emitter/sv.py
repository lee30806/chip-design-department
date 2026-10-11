"""IR에서 SystemVerilog를 결정론적으로 방출한다 (최소 Emitter, v0).

- 클럭과 리셋 포트는 domains에서 만든다. `seq` 블록의 `always_ff`와 리셋 분기는 Emitter가 씌운다.
- `fsm`은 상태 레지스터 `<state_name>_q`와 next-state 로직으로 방출한다.
- `cdc_sync`는 프로젝트 표준 동기화 셀 인스턴스로 방출한다. 셀 이름과 포트는 P0 자료로 확정할 때까지
  `sync_2ff (clk, rst_n, d, q)`를 가정한다.
- 인스턴스의 클럭과 리셋은 `domain_map`으로만 연결한다.
- 노드마다 `// @ir <노드>` 주석을 달고, 소스맵(노드 → 줄 범위)을 함께 낸다.
  IR 값이 그대로 놓인 줄(조각 본문, 전이 조건, 신호 타입, 리셋값, 포트 선언, 연결로 정해진 핀)은
  `fragment: true`인 세부 항목으로 따로 적는다. Classifier는 이 항목으로 lint 에러가 조각 안인지 골격인지 가른다.

`external` 모듈은 방출하지 않고 등록된 RTL 파일(`rtl_files`)을 파일 목록에 그대로 넣는다.
`top`과 `block_top`에는 SDC 골격(`sdc.py`)을 함께 낸다.
`memory` 블록은 아직 방출하지 않는다 (매크로 래퍼 규약을 받은 뒤 포트 형식을 확정).

    python3 -m pipeline.emitter.sv <ir...> -o <dir>   # <모듈>.sv, .srcmap.json, .sdc, filelist.f
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
    sourcemap: list[dict] = field(default_factory=list)  # {"node", "start", "end"[, "fragment"]} (1부터 센 줄 번호)


class _Writer:
    def __init__(self):
        self.lines: list[str] = []
        self.map: list[dict] = []

    def line(self, s: str = "", frag: str | None = None) -> None:
        """frag를 주면 이 줄(들)을 LLM이 쓴 노드 `frag`의 내용으로 소스맵에 적는다."""
        start = len(self.lines) + 1
        self.lines.extend(s.split("\n"))
        if frag:
            self.map.append({"node": frag, "start": start, "end": len(self.lines), "fragment": True})

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


def _seq(w: _Writer, m: Module, dom: dict, resets: list[tuple[str, str, str]], body: str, body_node: str | None) -> None:
    """resets: (이름, 리셋값, 리셋값이 온 노드)."""
    w.line(f"  always_ff @({_sensitivity(dom)}) begin")
    if resets:
        w.line(f"    if ({_reset_cond(dom)}) begin")
        width = max(len(n) for n, _, _ in resets)
        for name, val, src in resets:
            w.line(f"      {name.ljust(width)} <= {val};", frag=src)
        w.line("    end else begin")
        w.line(_indent(body, 6), frag=body_node)
        w.line("    end")
    else:
        w.line(_indent(body, 4), frag=body_node)
    w.line("  end")


def _fsm(w: _Writer, m: Module, b: dict) -> None:
    dom = m.domains[b["domain"]]
    q, d = f'{b["state_name"]}_q', f'{b["state_name"]}_d'
    _seq(w, m, dom, [(q, b["reset_state"], f'blocks/{b["id"]}/reset_state')], f"{q} <= {d};", None)
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
            w.line(f'        {kw} ({t["cond"]}) {d} = {t["to"]};  // @ir {t["id"]}',
                   frag=f'blocks/{b["id"]}/transitions/{t["id"]}')
        w.line("      end")
    w.line("      default: ;")
    w.line("    endcase")
    w.line("  end")


def _instance_nets(m: Module, library: dict[str, Module]) -> tuple[dict[tuple[str, str], tuple[str, str]], list[tuple[str, str, str]]]:
    """(인스턴스, 자식 포트) → (부모 쪽 넷 이름, 연결 id). 인스턴스끼리 잇는 넷은 새 wire로 선언한다."""
    from pipeline.validator.checks import _endpoint_ports  # 같은 끝점 해석을 쓴다

    nets: dict[tuple[str, str], tuple[str, str]] = {}
    wires: list[tuple[str, str, str]] = []
    for c in m.connections:
        ends = [_endpoint_ports(m, c[k], library) for k in ("from", "to")]
        if not all(ends):
            raise EmitError(f'connections/{c["id"]}: 끝점을 해석할 수 없음 (Validator V2를 먼저 통과해야 함)')
        owners = [c[k].split(".", 1)[0] for k in ("from", "to")]
        for (da, na), (db, nb) in zip(*ends):
            if owners[0] == "self" or owners[1] == "self":
                self_name = na if owners[0] == "self" else nb
                inst, port = (owners[1], nb) if owners[0] == "self" else (owners[0], na)
                nets[(inst, port)] = (self_name, c["id"])
            else:
                # 출력 쪽 인스턴스 포트 이름으로 wire를 만든다.
                src_i, src_p = (owners[0], na) if da == "output" else (owners[1], nb)
                net = f"{src_i}_{src_p}"
                child = library[next(i["module"] for i in m.instances if i["name"] == src_i)]
                wires.append((child.port(src_p).type, net, c["id"]))
                nets[(owners[0], na)] = (net, c["id"])
                nets[(owners[1], nb)] = (net, c["id"])
    return nets, wires


def emit(m: Module, library: dict[str, Module] | None = None) -> Emitted:
    if m.role == "external":
        raise EmitError(f"{m.name}: external 모듈은 방출하지 않음. rtl_files를 그대로 참조함")
    library = {**(library or {}), m.name: m}
    w = _Writer()
    w.line(f"// Generated from IR module '{m.name}'. Do not edit; change the IR and re-emit.")
    if m.params:
        params = ",\n".join(f'  parameter {p["type"]} {p["name"]} = {p["default"]}' for p in m.params)
        w.line(f"module {m.name} #(\n{params}\n) (")
    else:
        w.line(f"module {m.name} (")
    for i, p in enumerate(m.ports):
        src = f"domains/{p.domain}" if p.derived else f"ports/{p.bundle or p.name}"
        w.line(f"  {p.dir.ljust(6)} {p.type} {p.name}" + ("," if i < len(m.ports) - 1 else ""), frag=src)
    w.line(");")

    for t in m.types:
        with w.node(f'types/{t["name"]}'):
            if t["kind"] == "enum":
                base = f'{t["base"]} ' if t.get("base") else ""
                w.line(f'  typedef enum {base}{{{", ".join(t["members"])}}} {t["name"]};', frag=f'types/{t["name"]}')
            else:
                fields = " ".join(f'{f["type"]} {f["name"]};' for f in t["fields"])
                w.line(f'  typedef struct packed {{ {fields} }} {t["name"]};', frag=f'types/{t["name"]}')
    for s in m.signals:
        w.line(f"  {_decl(s.type, s.name)}", frag=f"signals/{s.name}")
    for b in m.blocks:
        if b["kind"] == "fsm":
            w.line(f'  {b["state_type"]} {b["state_name"]}_q, {b["state_name"]}_d;')

    nets, wires = _instance_nets(m, library) if m.instances else ({}, [])
    for type_, name, cid in wires:
        w.line(f"  {_decl(type_, name)}", frag=f"connections/{cid}")
    w.line()

    storage = m.storage()
    for b in m.blocks:
        node = f'blocks/{b["id"]}'
        with w.node(node):
            if b["kind"] == "comb":
                w.line("  always_comb begin")
                w.line(_indent(b["body"], 4), frag=f"{node}/body")
                w.line("  end")
            elif b["kind"] == "seq":
                resets = [(n, storage[n].reset, f'{"ports" if storage[n].origin == "port" else "signals"}/{n}')
                          for n in b["writes"] if storage[n].reset is not None]
                _seq(w, m, m.domains[b["domain"]], resets, b["body"], f"{node}/body")
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
        conns: list[tuple[str, str | None]] = []  # (핀 연결, 그 줄을 정한 노드)
        for cd, dom in child.domains.items():
            pd = m.domains[inst["domain_map"][cd]]
            conns.append((f'.{dom["clock"]}({pd["clock"]})', None))
            conns.append((f'.{dom["reset"]["port"]}({pd["reset"]["port"]})', None))
        for p in child.ports:
            if not p.derived:
                net, cid = nets.get((inst["name"], p.name), ("", None))
                # 연결이 없는 핀은 연결을 추가해서 고친다.
                conns.append((f'.{p.name}({net})', f"connections/{cid}" if cid else "connections"))
        prm = ", ".join(f".{k}({v})" for k, v in inst.get("params", {}).items())
        with w.node(f'instances/{inst["name"]}'):
            head = f'  {child.name} #({prm}) {inst["name"]} (' if prm else f'  {child.name} {inst["name"]} ('
            w.line(head)
            for i, (c, src) in enumerate(conns):
                w.line("    " + c + ("," if i < len(conns) - 1 else ""), frag=src)
            w.line("  );")
        w.line()
    w.line("endmodule")
    return Emitted(m.name, "\n".join(w.lines) + "\n", w.map)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IR → SystemVerilog 방출")
    ap.add_argument("ir", nargs="+", help="IR JSON 파일들 (인스턴스가 참조하는 모듈도 함께)")
    ap.add_argument("-o", "--out", required=True, help="출력 디렉터리")
    ap.add_argument("--cells", nargs="*", default=[], help="표준 셀 RTL (동기화 셀 등). 파일 목록 맨 앞에 넣음")
    args = ap.parse_args(argv)
    from pipeline.emitter.sdc import emit_sdc

    lib = load_library(args.ir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cells = [str(Path(c).resolve()) for c in args.cells]
    externals: list[str] = []
    files: list[str] = []
    for m in lib.values():
        if m.role == "external":
            externals += [str((m.path.parent / f).resolve()) for f in m.raw.get("rtl_files", [])]
            continue
        e = emit(m, lib)
        (out / f"{m.name}.sv").write_text(e.text, encoding="utf-8")
        (out / f"{m.name}.srcmap.json").write_text(json.dumps(e.sourcemap, indent=1), encoding="utf-8")
        files.append(str((out / f"{m.name}.sv").resolve()))
        if m.role in ("top", "block_top"):
            (out / f"{m.name}.sdc").write_text(emit_sdc(m, lib), encoding="utf-8")
        print(out / f"{m.name}.sv")
    # 표준 셀, 외부 RTL, 방출 파일 순. 모두 절대 경로라 어디서 -f로 읽어도 된다. 중복은 한 번만.
    (out / "filelist.f").write_text("\n".join(dict.fromkeys(cells + externals + files)) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
