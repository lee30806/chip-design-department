"""Validator V1~V5와 전체 실행 진입점.

모든 오류는 IR 노드 경로(예: `blocks/k_cnt`, `signals/byte_cnt`)를 가진다.
V6~V11은 `structure.py`에 있다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pyslang
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from pipeline.ir.model import Module
from pipeline.validator import probe

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schema" / "ir.schema.json").read_text(encoding="utf-8"))
_SCHEMA_V = Draft202012Validator(SCHEMA)

# IEEE 1800-2017 예약어 중 식별자로 쓰기 쉬운 것들
SV_KEYWORDS = set("""
alias always always_comb always_ff always_latch and assert assign assume automatic before begin bind bins binsof bit
break buf bufif0 bufif1 byte case casex casez cell chandle checker class clocking cmos config const constraint context
continue cover covergroup coverpoint cross deassign default defparam design disable dist do edge else end endcase
endchecker endclass endclocking endconfig endfunction endgenerate endgroup endinterface endmodule endpackage
endprimitive endprogram endproperty endspecify endsequence endtable endtask enum event eventually expect export extends
extern final first_match for force foreach forever fork forkjoin function generate genvar global highz0 highz1 if iff
ifnone ignore_bins illegal_bins implements implies import incdir include initial inout input inside instance int
integer interconnect interface intersect join join_any join_none large let liblist library local localparam logic
longint macromodule matches medium modport module nand negedge nettype new nexttime nmos nor noshowcancelled not
notif0 notif1 null or output package packed parameter pmos posedge primitive priority program property protected
pull0 pull1 pulldown pullup pulsestyle_ondetect pulsestyle_onevent pure rand randc randcase randsequence rcmos real
realtime ref reg reject_on release repeat restrict return rnmos rpmos rtran rtranif0 rtranif1 s_always s_eventually
s_nexttime s_until s_until_with scalared sequence shortint shortreal showcancelled signed small soft solve specify
specparam static string strong strong0 strong1 struct super supply0 supply1 sync_accept_on sync_reject_on table
tagged task this throughout time timeprecision timeunit tran tranif0 tranif1 tri tri0 tri1 triand trior trireg type
typedef union unique unique0 unsigned until until_with untyped use uwire var vectored virtual void wait wait_order
wand weak weak0 weak1 while wildcard wire with within wor xnor xor
""".split())


@dataclass(frozen=True)
class Issue:
    stage: str
    node: str
    message: str
    severity: str = "error"  # error | warning

    def __str__(self) -> str:
        tag = self.stage if self.severity == "error" else f"{self.stage} 경고"
        return f"[{tag}] {self.node}: {self.message}"


def _pick_branch_error(e):
    """oneOf 갈래 중 `kind`(또는 다른 const 식별 필드)가 맞는 갈래의 오류를 고른다."""
    branches: dict = {}
    for sub in e.context:
        branches.setdefault(sub.relative_schema_path[0], []).append(sub)
    matching = [errs for errs in branches.values()
                if not any(x.validator == "const" and len(x.relative_path) == 1 for x in errs)]
    if len(matching) == 1:
        return best_match(matching[0])
    return best_match(e.context)


# ---------------------------------------------------------------- V1
def v1_schema(m: Module) -> list[Issue]:
    out = []
    for e in sorted(_SCHEMA_V.iter_errors(m.raw), key=lambda e: list(map(str, e.absolute_path))):
        # oneOf 실패는 메시지에 노드 전체가 찍히므로, 가장 가까운 하위 오류로 바꿔 보고한다.
        if e.validator in ("oneOf", "anyOf") and e.context:
            e = _pick_branch_error(e)
        node = "/".join(map(str, e.absolute_path)) or "(root)"
        out.append(Issue("V1", node, e.message if len(e.message) < 160 else e.message[:157] + "..."))
    if out:
        return out  # 형식이 틀리면 이름 검사는 의미가 없다

    names: dict[str, str] = {}

    def claim(name: str, node: str) -> None:
        if name in SV_KEYWORDS:
            out.append(Issue("V1", node, f"SV 예약어는 이름으로 쓸 수 없음: {name}"))
        if name in names:
            out.append(Issue("V1", node, f"이름 중복: {name} (먼저 쓰인 곳: {names[name]})"))
        else:
            names[name] = node

    for p in m.params:
        claim(p["name"], f'params/{p["name"]}')
    for d in m.domains.values():
        claim(d["name"], f'domains/{d["name"]}')
    for port in m.ports:
        if not port.derived:
            claim(port.name, f"ports/{port.name}")
    for name in {p.name for p in m.ports if p.derived}:
        if name not in names:
            claim(name, f"domains/{name}")
    for b in m.bundles:
        claim(b, f"ports/{b}")
    for t in m.types:
        claim(t["name"], f'types/{t["name"]}')
        for mem in t.get("members", []):
            claim(mem, f'types/{t["name"]}/{mem}')
    for s in m.signals:
        claim(s.name, f"signals/{s.name}")
    for s in m.state_regs():
        claim(s.name, f"blocks/{s.name}")
    for i in m.instances:
        claim(i["name"], f'instances/{i["name"]}')
    ids: set[str] = set()
    for b in m.blocks:
        for nid in [b["id"]] + [t["id"] for t in b.get("transitions", [])]:
            if nid in ids:
                out.append(Issue("V1", f"blocks/{b['id']}", f"id 중복: {nid}"))
            ids.add(nid)
    for c in m.connections:
        if c["id"] in ids:
            out.append(Issue("V1", f'connections/{c["id"]}', f'id 중복: {c["id"]}'))
        ids.add(c["id"])
    return out


# ---------------------------------------------------------------- V2
def _endpoint_ports(m: Module, ep: str, library: dict[str, Module]) -> list[tuple[str, str]] | None:
    """끝점을 (포트 방향, 신호 이름) 목록으로 펼친다. 해석할 수 없으면 None."""
    owner, name = ep.split(".", 1)
    if owner == "self":
        if name in m.bundles:
            return [(s["dir"], s["name"]) for s in m.bundles[name]["signals"]]
        port = m.port(name)
        if port:
            return [(port.dir, port.name)]
        if name in {s.name for s in m.signals}:
            return [("signal", name)]
        return None
    inst = next((i for i in m.instances if i["name"] == owner), None)
    child = library.get(inst["module"]) if inst else None
    if not child:
        return None
    if name in child.bundles:
        return [(s["dir"], s["name"]) for s in child.bundles[name]["signals"]]
    port = child.port(name)
    return [(port.dir, port.name)] if port and not port.derived else None


def v2_refs(m: Module, library: dict[str, Module]) -> list[Issue]:
    out: list[Issue] = []
    doms = set(m.domains)

    def dom(d, node):
        if d is not None and d not in doms:
            out.append(Issue("V2", node, f"정의되지 않은 도메인: {d}"))

    for port in m.ports:
        if not port.derived:
            dom(port.domain, f"ports/{port.bundle or port.name}")
    for s in m.signals:
        dom(s.domain, f"signals/{s.name}")
    readable, storage = m.readable(), m.storage()
    for b in m.blocks:
        node = f'blocks/{b["id"]}'
        if b["kind"] in ("seq", "fsm", "memory"):
            dom(b.get("domain"), node)
        if b["kind"] == "cdc_sync":
            dom(b["dst_domain"], node)
            dom(b["src_domain"], node)
            for k, pool in (("src", readable), ("dst", storage)):
                if b[k] not in pool:
                    out.append(Issue("V2", node, f"{k}가 가리키는 신호가 없음: {b[k]}"))
        for r in b.get("reads", []):
            if r not in readable:
                out.append(Issue("V2", node, f"reads의 신호가 없음: {r}"))
        for w in b.get("writes", []):
            if w not in storage:
                out.append(Issue("V2", node, f"writes의 신호가 없음 (출력 포트 또는 내부 신호여야 함): {w}"))
        if b["kind"] == "fsm":
            if b["state_type"] not in m.type_names():
                out.append(Issue("V2", node, f'정의되지 않은 타입: {b["state_type"]}'))
            members = next((set(t["members"]) for t in m.types if t["name"] == b["state_type"] and t["kind"] == "enum"), set())
            for st in [b["reset_state"]] + [x for t in b["transitions"] for x in (t["from"], t["to"])]:
                if members and st not in members:
                    out.append(Issue("V2", node, f"상태 타입에 없는 상태: {st}"))
    for inst in m.instances:
        node = f'instances/{inst["name"]}'
        child = library.get(inst["module"])
        if not child:
            out.append(Issue("V2", node, f'라이브러리에 없는 모듈: {inst["module"]}'))
            continue
        for k in inst.get("params", {}):
            if k not in {p["name"] for p in child.params}:
                out.append(Issue("V2", node, f'{inst["module"]}에 없는 파라미터: {k}'))
        for cd, pd in inst["domain_map"].items():
            if cd not in child.domains:
                out.append(Issue("V2", node, f'{inst["module"]}에 없는 도메인: {cd}'))
            dom(pd, node)
        for cd in child.domains:
            if cd not in inst["domain_map"]:
                out.append(Issue("V2", node, f"domain_map에 자식 도메인이 빠짐: {cd}"))
    for c in m.connections:
        node = f'connections/{c["id"]}'
        ends = [_endpoint_ports(m, c[k], library) for k in ("from", "to")]
        for k, e in zip(("from", "to"), ends):
            if e is None:
                out.append(Issue("V2", node, f"끝점을 해석할 수 없음: {c[k]}"))
        if all(ends) and len(ends[0]) != len(ends[1]):
            out.append(Issue("V2", node, f"양쪽 신호 개수가 다름: {len(ends[0])} vs {len(ends[1])}"))
    return out


# ---------------------------------------------------------------- V3, V4
_FORBIDDEN = {"DelayControl": "지연(#)", "ProceduralForceStatement": "force", "ProceduralReleaseStatement": "release",
              "ProceduralAssignStatement": "procedural assign", "ProceduralDeassignStatement": "deassign"}


def _block_usage(node) -> tuple[set[str], set[str], set[str], list[str]]:
    """(쓰는 이름, 읽는 이름, 대입 종류, 금지 구문) — 구문 트리에서 직접 뽑는다."""
    lhs_starts: set[int] = set()
    writes, reads, kinds, forbidden = set(), set(), set(), []

    def visit(n):
        k = str(getattr(n, "kind", "")).removeprefix("SyntaxKind.")
        if k in ("AssignmentExpression", "NonblockingAssignmentExpression"):
            kinds.add("nonblocking" if k.startswith("Nonblocking") else "blocking")
            lhs_starts.add(n.left.sourceRange.start.offset)
        elif k in ("IdentifierName", "IdentifierSelectName"):
            name = n.identifier.valueText
            (writes if n.sourceRange.start.offset in lhs_starts else reads).add(name)
        elif k in _FORBIDDEN:
            forbidden.append(_FORBIDDEN[k])
        return pyslang.VisitAction.Advance

    node.visit(visit)
    return writes, reads, kinds, forbidden


def v3_v4(m: Module, library: dict[str, Module]) -> list[Issue]:
    pr = probe.build(m, library)
    tree, diags = probe.compile_probe(pr)
    out = [Issue(d.stage, d.node, d.message) for d in diags]
    blocks = {f'blocks/{b["id"]}': b for b in m.blocks}
    sm = tree.sourceManager
    signal_names = m.readable()

    def visit(n):
        k = str(getattr(n, "kind", "")).removeprefix("SyntaxKind.")
        if k not in ("AlwaysCombBlock", "AlwaysFFBlock"):
            return pyslang.VisitAction.Advance
        line = sm.getLineNumber(n.sourceRange.start)
        _, node = pr.nodes[line - 1]
        b = blocks.get(node)
        if b is None:
            return pyslang.VisitAction.Skip
        writes, reads, kinds, forbidden = _block_usage(n.statement)
        for f in forbidden:
            out.append(Issue("V4", node, f"금지 구문: {f}"))
        if b["kind"] == "seq" and "blocking" in kinds:
            out.append(Issue("V4", node, "seq 블록에 blocking 대입(=)이 있음. non-blocking(<=)만 허용"))
        if b["kind"] == "comb" and "nonblocking" in kinds:
            out.append(Issue("V4", node, "comb 블록에 non-blocking 대입(<=)이 있음. blocking(=)만 허용"))
        declared_w, declared_r = set(b["writes"]), set(b["reads"])
        if writes != declared_w:
            extra, missing = sorted(writes - declared_w), sorted(declared_w - writes)
            out.append(Issue("V4", node, f"실제 쓰기와 writes가 다름 (선언 밖 쓰기: {extra}, 쓰지 않은 선언: {missing})"))
        undeclared = sorted((reads & signal_names) - declared_r)
        if undeclared:
            out.append(Issue("V4", node, f"reads에 없는 신호를 읽음: {undeclared}"))
        return pyslang.VisitAction.Skip

    tree.root.visit(visit)
    # FSM 조건식도 reads 안에서만 읽어야 한다.
    for b in m.blocks:
        if b["kind"] != "fsm":
            continue
        for tr in b["transitions"]:
            t = pyslang.SyntaxTree.fromText(f"module __c; wire w = ({tr['cond']}); endmodule")
            _, reads, _, _ = _block_usage(t.root)
            undeclared = sorted((reads & signal_names) - set(b["reads"]))
            if undeclared:
                out.append(Issue("V4", f'blocks/{b["id"]}/transitions/{tr["id"]}', f"reads에 없는 신호를 읽음: {undeclared}"))
    return out


# ---------------------------------------------------------------- V5
def v5_drivers(m: Module, library: dict[str, Module]) -> list[Issue]:
    out: list[Issue] = []
    writers: dict[str, list[tuple[str, dict | None]]] = {}

    def add(name, node, block=None):
        writers.setdefault(name, []).append((node, block))

    for b in m.blocks:
        node = f'blocks/{b["id"]}'
        if b["kind"] in ("comb", "seq"):
            for w in b["writes"]:
                add(w, node, b)
        elif b["kind"] == "fsm":
            add(f'{b["state_name"]}_q', node, b)
        elif b["kind"] == "cdc_sync":
            add(b["dst"], node, b)
    for c in m.connections:
        ends = [_endpoint_ports(m, c[k], library) for k in ("from", "to")]
        if not all(ends):
            continue  # V2가 보고함
        for (da, na), (db, nb) in zip(*ends, strict=False):
            # 같은 위치의 두 신호 중 값을 내는 쪽이 다른 쪽을 구동한다.
            a_self, b_self = c["from"].startswith("self."), c["to"].startswith("self.")
            src_a = (da == "input") if a_self else (da == "output")
            src_b = (db == "input") if b_self else (db == "output")
            if src_a == src_b and "signal" not in (da, db):
                out.append(Issue("V5", f'connections/{c["id"]}', f"{na}와 {nb}의 방향이 맞지 않음"))
                continue
            sink, sink_self = (nb, b_self) if (src_a or db == "signal") else (na, a_self)
            if sink_self:
                add(sink, f'connections/{c["id"]}')
    storage = m.storage()
    for p in m.ports:
        if p.dir == "input" and p.name in writers:
            out.append(Issue("V5", f"ports/{p.bundle or p.name}", f"입력 포트에 쓰기: {p.name}"))
    for name, s in storage.items():
        ws = writers.get(name, [])
        node = f"ports/{name}" if s.origin == "port" else (f"signals/{name}" if s.origin == "signal" else f"blocks/{name}")
        if len(ws) == 0:
            out.append(Issue("V5", node, f"구동하는 곳이 없음: {name}"))
        elif len(ws) > 1:
            out.append(Issue("V5", node, f"구동하는 곳이 여러 개: {name} ← {[w for w, _ in ws]}"))
        else:
            wnode, blk = ws[0]
            if s.kind == "reg":
                if blk is None or blk["kind"] not in ("seq", "fsm"):
                    out.append(Issue("V5", node, f"reg는 seq 블록 하나만 쓸 수 있음: {name} ← {wnode}"))
                elif s.domain != blk.get("domain"):
                    out.append(Issue("V5", node, f'reg의 도메인({s.domain})과 쓰는 블록의 도메인({blk.get("domain")})이 다름'))
            elif blk is not None and blk["kind"] == "seq":
                out.append(Issue("V5", node, f"wire를 seq 블록이 씀: {name} ← {wnode}"))
    return out


def validate(m: Module, library: dict[str, Module] | None = None, upto: int = 10) -> list[Issue]:
    """모듈 하나에 V1부터 upto 단계(최대 10)까지 실행한다.

    V1~V5는 앞 단계에서 오류가 나면 뒤 단계를 건너뛴다. V6~V10은 서로 독립이라 함께 실행한다.
    V11(동결)은 설계 전체 단위라 `structure.v11_frozen`으로 따로 부른다.
    """
    from pipeline.validator import structure as st

    library = {**(library or {}), m.name: m}
    out = v1_schema(m)
    if out or upto < 2:
        return out
    out = v2_refs(m, library)
    if out or upto < 3:
        return out
    out = v3_v4(m, library)
    if out or upto < 5:
        return out
    out = v5_drivers(m, library)
    if out or upto < 6:
        return out
    stages = [(6, lambda: st.v6_latch_loop(m, library)), (7, lambda: st.v7_reset(m)),
              (8, lambda: st.v8_domain(m, library)), (9, lambda: st.v9_fsm(m)),
              (10, lambda: st.v10_hierarchy(m, library))]
    st._PATH_CACHE.clear()
    for n, f in stages:
        if n <= upto:
            out += f()
    return out


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]
