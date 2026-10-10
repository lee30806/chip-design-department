"""Validator V6~V11: 래치와 루프, 리셋, 도메인, FSM, 계층, 동결.

V1~V5를 통과한 IR만 받는다고 가정한다. 동결(V11)은 모듈 하나가 아니라 설계 전체(라이브러리) 단위다.
"""
from __future__ import annotations

import hashlib
import json

import pyslang

from pipeline.ir.model import Module
from pipeline.validator.checks import Issue, _block_usage, _endpoint_ports


# ---------------------------------------------------------------- 공통: 조합 경로
def _ids(node) -> set[str]:
    out: set[str] = set()

    def visit(n):
        if str(getattr(n, "kind", "")).endswith(("IdentifierName", "IdentifierSelectName")):
            out.add(n.identifier.valueText)
        return pyslang.VisitAction.Advance

    node.visit(visit)
    return out


def assign_deps(body: str) -> dict[str, set[str]]:
    """comb 조각의 대입 대상별 의존 신호: 오른쪽 식의 신호와 블록 안 조건식(if, case)의 신호.

    조건식은 블록 전체에서 모아 모든 대입에 붙인다(보수적). 블록 단위 reads→writes보다 정밀해서,
    `s_ready = 1'b1`처럼 입력에 의존하지 않는 대입에는 경로를 만들지 않는다.
    """
    t = pyslang.SyntaxTree.fromText(f"module __d; always_comb begin\n{body}\nend endmodule")
    conds: set[str] = set()
    assigns: list[tuple[str, set[str]]] = []

    def visit(n):
        k = str(getattr(n, "kind", ""))
        if k.endswith("ConditionalStatement"):
            conds.update(_ids(n.predicate))
        elif k.endswith("CaseStatement"):
            conds.update(_ids(n.expr))
        elif k.endswith(("SyntaxKind.AssignmentExpression", "NonblockingAssignmentExpression")):
            left = n.left
            lhs = left.identifier.valueText if hasattr(left, "identifier") else next(iter(_ids(left)), None)
            if lhs:
                assigns.append((lhs, _ids(n.right)))
        return pyslang.VisitAction.Advance

    t.root.visit(visit)
    deps: dict[str, set[str]] = {}
    for lhs, rhs in assigns:
        deps.setdefault(lhs, set()).update(rhs | conds)
    return deps


def _comb_edges(m: Module, library: dict[str, Module]) -> dict[str, set[str]]:
    """조합 의존 그래프: 읽는 신호 → 쓰는 신호. 인스턴스는 자식의 입력→출력 조합 경로로 관통한다."""
    edges: dict[str, set[str]] = {}
    for b in m.blocks:
        if b["kind"] == "comb":
            for w, deps in assign_deps(b["body"]).items():
                for r in deps & set(b["reads"]):
                    edges.setdefault(r, set()).add(w)
    for inst in m.instances:
        child = library.get(inst["module"])
        if not child:
            continue
        paths = comb_paths(child, library)
        nets = _inst_nets(m, inst["name"], library)
        for i, o in paths:
            if i in nets and o in nets:
                edges.setdefault(nets[i], set()).add(nets[o])
    return edges


def _inst_nets(m: Module, inst: str, library: dict[str, Module]) -> dict[str, str]:
    """인스턴스 포트 → 부모 쪽 이름 (self 끝점만, 인스턴스끼리는 `<inst>_<port>`)."""
    out: dict[str, str] = {}
    for c in m.connections:
        ends = [_endpoint_ports(m, c[k], library) for k in ("from", "to")]
        owners = [c[k].split(".", 1)[0] for k in ("from", "to")]
        if not all(ends) or inst not in owners:
            continue
        for (da, na), (db, nb) in zip(*ends):
            mine, other, other_owner = (na, nb, owners[1]) if owners[0] == inst else (nb, na, owners[0])
            mine_dir = da if owners[0] == inst else db
            out[mine] = other if other_owner == "self" else (f"{inst}_{mine}" if mine_dir == "output" else f"{other_owner}_{other}")
    return out


_PATH_CACHE: dict[tuple[str, int], set[tuple[str, str]]] = {}


def comb_paths(m: Module, library: dict[str, Module]) -> set[tuple[str, str]]:
    """모듈의 (입력 포트, 출력 포트) 조합 경로 요약."""
    key = (m.name, id(m))
    if key in _PATH_CACHE:
        return _PATH_CACHE[key]
    ins = [p.name for p in m.ports if p.dir == "input" and not p.derived]
    outs = {p.name for p in m.ports if p.dir == "output"}
    if m.role == "external":
        declared = m.raw.get("comb_paths")
        res = {(c["from"], c["to"]) for c in declared} if declared is not None else {(i, o) for i in ins for o in outs}
    else:
        edges = _comb_edges(m, library)
        res = set()
        for i in ins:
            seen, stack = set(), [i]
            while stack:
                n = stack.pop()
                for nxt in edges.get(n, ()):
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            res |= {(i, o) for o in seen & outs}
    _PATH_CACHE[key] = res
    return res


# ---------------------------------------------------------------- V6
def _top_level_items(body: str):
    t = pyslang.SyntaxTree.fromText(f"module __v6; always_comb begin\n{body}\nend endmodule")
    found = []

    def visit(n):
        if str(getattr(n, "kind", "")).endswith("AlwaysCombBlock"):
            found.extend(n.statement.items)
            return pyslang.VisitAction.Skip
        return pyslang.VisitAction.Advance

    t.root.visit(visit)
    return found


def v6_latch_loop(m: Module, library: dict[str, Module]) -> list[Issue]:
    out: list[Issue] = []
    for b in m.blocks:
        if b["kind"] != "comb":
            continue
        first: dict[str, bool] = {}  # 신호 → 처음 쓰는 최상위 문장이 무조건 전체 대입인지
        for item in _top_level_items(b["body"]):
            writes, _, _, _ = _block_usage(item)
            plain = None
            if str(item.kind).endswith("ExpressionStatement") and str(item.expr.kind).endswith("AssignmentExpression") \
                    and str(item.expr.left.kind).endswith("IdentifierName"):
                plain = item.expr.left.identifier.valueText
            for w in writes:
                first.setdefault(w, w == plain)
        for w in b["writes"]:
            if not first.get(w, False):
                out.append(Issue("V6", f'blocks/{b["id"]}', f"래치 위험: {w}에 본문 최상위의 무조건 대입이 먼저 있어야 함"))
    # 조합 루프
    edges = _comb_edges(m, library)
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(n: str) -> list[str] | None:
        color[n] = 1
        stack.append(n)
        for nxt in sorted(edges.get(n, ())):
            if color.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if color.get(nxt) is None:
                cyc = dfs(nxt)
                if cyc:
                    return cyc
        stack.pop()
        color[n] = 2
        return None

    for n in sorted(edges):
        if color.get(n) is None:
            cyc = dfs(n)
            if cyc:
                out.append(Issue("V6", f"signals/{cyc[0]}", f"조합 루프: {' → '.join(cyc)}"))
                break
    return out


# ---------------------------------------------------------------- V7
def v7_reset(m: Module) -> list[Issue]:
    out: list[Issue] = []
    storage = m.storage()
    for b in m.blocks:
        if b["kind"] == "seq":
            has = {w: storage[w].reset is not None for w in b["writes"] if w in storage}
            if len(set(has.values())) > 1:
                out.append(Issue("V7", f'blocks/{b["id"]}', f"리셋 유무가 섞임: 있음 {sorted(k for k, v in has.items() if v)}, "
                                                            f"없음 {sorted(k for k, v in has.items() if not v)}"))
    return out


# ---------------------------------------------------------------- V8
ASYNC = "<async>"


def signal_domains(m: Module, library: dict[str, Module]) -> tuple[dict[str, set[str]], list[Issue]]:
    """신호별 도메인 집합. wire는 팬인에서 유도한다."""
    out: list[Issue] = []
    dom: dict[str, set[str]] = {}
    for p in m.ports:
        if p.dir == "input" and not p.derived:
            dom[p.name] = {p.domain or ASYNC}
    for name, s in m.storage().items():
        if s.kind == "reg":
            dom[name] = {s.domain}
    for b in m.blocks:
        if b["kind"] == "cdc_sync":
            dom[b["dst"]] = {b["dst_domain"]}
    for inst in m.instances:
        child = library.get(inst["module"])
        if not child:
            continue
        for port, net in _inst_nets(m, inst["name"], library).items():
            cp = child.port(port)
            if cp and cp.dir == "output":
                dom[net] = {inst["domain_map"].get(cp.domain, cp.domain) if cp.domain else ASYNC}
    combs = [b for b in m.blocks if b["kind"] == "comb"]
    for _ in range(len(combs) + 1):  # 고정점까지 전파
        changed = False
        for b in combs:
            src: set[str] = set()
            for r in b["reads"]:
                src |= dom.get(r, set())
            for w in b["writes"]:
                if not src <= dom.get(w, set()):
                    dom[w] = dom.get(w, set()) | src
                    changed = True
        if not changed:
            break
    return dom, out


def v8_domain(m: Module, library: dict[str, Module]) -> list[Issue]:
    dom, out = signal_domains(m, library)
    storage = m.storage()
    for name, ds in sorted(dom.items()):
        s = storage.get(name)
        if s and s.kind != "reg" and len(ds - {None}) > 1:
            out.append(Issue("V8", f"signals/{name}", f"wire에 여러 도메인이 섞임: {sorted(ds)}"))
    for b in m.blocks:
        node = f'blocks/{b["id"]}'
        reads = list(b.get("reads", []))
        if b["kind"] in ("seq", "fsm"):
            for r in reads:
                ds = dom.get(r, set())
                if ASYNC in ds:
                    out.append(Issue("V8", node, f"비동기 신호는 cdc_sync의 src로만 읽을 수 있음: {r}"))
                elif ds and ds != {b["domain"]}:
                    out.append(Issue("V8", node, f'다른 도메인 신호를 읽음: {r} ({sorted(ds)}), 블록 도메인 {b["domain"]}'))
        elif b["kind"] == "comb":
            for r in reads:
                if ASYNC in dom.get(r, set()):
                    out.append(Issue("V8", node, f"비동기 신호는 cdc_sync의 src로만 읽을 수 있음: {r}"))
    return out


# ---------------------------------------------------------------- V9
def v9_fsm(m: Module) -> list[Issue]:
    out: list[Issue] = []
    for b in m.blocks:
        if b["kind"] != "fsm":
            continue
        node = f'blocks/{b["id"]}'
        members = next(t["members"] for t in m.types if t["name"] == b["state_type"])
        nxt: dict[str, set[str]] = {}
        for t in b["transitions"]:
            nxt.setdefault(t["from"], set()).add(t["to"])
        seen, stack = {b["reset_state"]}, [b["reset_state"]]
        while stack:
            for s in nxt.get(stack.pop(), ()):
                if s not in seen:
                    seen.add(s)
                    stack.append(s)
        for s in members:
            if s not in seen:
                out.append(Issue("V9", node, f"리셋 상태에서 도달할 수 없는 상태: {s}"))
            if s in seen and s not in nxt:
                out.append(Issue("V9", node, f"나가는 전이가 없는 상태: {s}", severity="warning"))
    return out


# ---------------------------------------------------------------- V10
def v10_hierarchy(m: Module, library: dict[str, Module]) -> list[Issue]:
    out: list[Issue] = []
    dom, _ = signal_domains(m, library)
    driven: dict[tuple[str, str], int] = {}
    for c in m.connections:
        node = f'connections/{c["id"]}'
        ends = [_endpoint_ports(m, c[k], library) for k in ("from", "to")]
        owners = [c[k].split(".", 1)[0] for k in ("from", "to")]
        names = [c[k].split(".", 1)[1] for k in ("from", "to")]
        if not all(ends):
            continue
        # 번들 호환: 프로토콜이 같고, 부모-자식은 같은 역할, 인스턴스끼리는 반대 역할
        bundles = []
        for o, n in zip(owners, names):
            mod = m if o == "self" else library[next(i["module"] for i in m.instances if i["name"] == o)]
            bundles.append(mod.bundles.get(n))
        if all(bundles):
            ba, bb = bundles
            if ba["protocol"] != bb["protocol"]:
                out.append(Issue("V10", node, f'번들 프로토콜이 다름: {ba["protocol"]} vs {bb["protocol"]}'))
            same_role = "self" in owners
            if (ba["role"] == bb["role"]) != same_role:
                want = "같아야" if same_role else "반대여야"
                out.append(Issue("V10", node, f'번들 역할이 {want} 함: {ba["role"]} vs {bb["role"]}'))
        elif any(bundles):
            out.append(Issue("V10", node, "번들과 단독 포트를 연결함"))
        # 인스턴스 입력은 정확히 한 번 연결
        for o, e in zip(owners, ends):
            if o != "self":
                for d, n in e:
                    if d == "input":
                        driven[(o, n)] = driven.get((o, n), 0) + 1
        # 도메인 교차: 양쪽 클럭이 다르면 수신 측이 비동기 포트여야 함
        for (da, na), (db, nb) in zip(*ends):
            def port_dom(owner, d, n):
                if owner == "self":
                    return next(iter(dom.get(n, {None})), None)
                inst = next(i for i in m.instances if i["name"] == owner)
                cp = library[inst["module"]].port(n)
                return inst["domain_map"].get(cp.domain) if cp.domain else ASYNC
            pa, pb = port_dom(owners[0], da, na), port_dom(owners[1], db, nb)
            if ASYNC not in (pa, pb) and None not in (pa, pb) and pa != pb:
                out.append(Issue("V10", node, f"도메인이 다른 연결({na}: {pa}, {nb}: {pb})은 동기화 셀을 거치거나 수신 측이 비동기 포트여야 함"))
    for inst in m.instances:
        child = library.get(inst["module"])
        if not child:
            continue
        for p in child.ports:
            if p.dir == "input" and not p.derived:
                n = driven.get((inst["name"], p.name), 0)
                if n != 1:
                    out.append(Issue("V10", f'instances/{inst["name"]}', f"입력 {p.name}의 연결 수가 {n} (정확히 1이어야 함)"))
    return out


# ---------------------------------------------------------------- V11
def frozen_scope(library: dict[str, Module]) -> dict[str, str]:
    """동결 범위의 해시: 모든 모듈의 L1과 인스턴스 목록, top/block_top의 연결과 동기화 셀."""
    out: dict[str, str] = {}
    for name, m in sorted(library.items()):
        parts = {
            "l1": {k: m.raw.get(k) for k in ("module", "role", "params", "domains", "power_domains", "ports")},
            "instances": m.raw.get("instances", []),
        }
        if m.role in ("top", "block_top"):
            parts["connections"] = m.raw.get("connections", [])
            parts["cdc_sync"] = [b for b in m.blocks if b["kind"] == "cdc_sync"]
        for k, v in parts.items():
            out[f"{name}/{k}"] = hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
    return out


def v11_frozen(library: dict[str, Module], baseline: dict[str, str]) -> list[Issue]:
    now = frozen_scope(library)
    out = [Issue("V11", k, "동결 범위가 바뀜") for k in sorted(set(now) | set(baseline)) if now.get(k) != baseline.get(k)]
    return out
