"""`lang: py` IR의 사이클 단위 실행기 (설계 모델).

Python 조각을 SV와 같은 의미로 실행한다. 판정은 늘 방출한 RTL의 시뮬레이션으로 하고, 이 실행기는 두 가지에 쓴다.
- 번역기 검사: 같은 자극에서 이 실행기와 RTL의 출력을 사이클마다 비교한다 (`pipeline/verify/pyequiv.py`).
- RTL 전 빠른 실행: 하니스 없이 설계 모델을 바로 돌려 본다.

의미 (부호 없는 값만):
- 식의 폭은 번역기와 같은 규칙(`pyfrag.Widths`, IEEE 1800 규칙에 정수 리터럴은 문맥 폭을 따름)으로 계산한다.
- `comb`는 blocking, `seq`와 `fsm`은 클럭 에지에서 한꺼번에 갱신(non-blocking)한다. 리셋이 있는 `seq`는 리셋 중에
  리셋값을 넣는다. 비동기 리셋은 리셋이 걸린 동안 바로 리셋값을 유지한다.
- 조합 논리는 값이 더 바뀌지 않을 때까지 되풀이해 계산한다 (조합 루프는 Validator V6이 막음).
- 클럭 도메인이 여럿이면 `step(도메인 집합)`으로 그 시각에 상승 에지가 있는 최상위 도메인을 한꺼번에 진행한다
  (같은 시각의 에지는 RTL의 non-blocking처럼 에지 직전 값으로 계산해 함께 갱신). 에지 시각은 부르는 쪽이 정한다
  (`schedule`). `step()`은 모든 도메인을 함께 진행한다.
- 추가 동기 리셋은 에지에서 주 리셋 다음으로 리셋값을 넣는다. `reset.synchronize` 도메인은 `rst_sync` 셀을 거친 리셋을 쓴다.
- 표준 셀(`cdc_sync`의 `2ff`/`gray`/`pulse`, `cdc_fifo`, `rst_sync`)은 `pipeline/emitter/stubs/`의 RTL과 같은 의미로
  실행한다. 셀 내부 레지스터는 `<인스턴스 경로>u_<id>.<레지스터>`로 값 표에 둔다.

지원 범위: `comb`/`seq`/`fsm`/`memory`(inferred)/`cdc_sync`/`cdc_fifo` 블록, 인스턴스와 연결(계층). struct, signed는 아직 없다.
메모리 워드는 `<이름>[<주소>]` 키로 값 표에 둔다 (쓴 적 없는 워드는 0).
조각이 SV인 모듈(`lang: sv`)은 동작 블록이 셀과 메모리뿐일 때만(구조만 있는 Block Top) 실행할 수 있다.
"""
from __future__ import annotations

import ast

from pipeline.ir.model import Module
from pipeline.ir.pyfrag import FragError, Widths, mask, operand_w, parse_body, parse_expr, parse_literal, type_width, w_val


class SimError(Exception):
    pass


CELLS = ("cdc_sync", "cdc_fifo")


def _bin2gray(v: int) -> int:
    return v ^ (v >> 1)


def _gray2bin(g: int) -> int:
    b = 0
    while g:
        b ^= g
        g >>= 1
    return b


def schedule(periods: dict[str, int], until: int) -> list[tuple[int, set[str]]]:
    """도메인별 주기(ps)로 시각 0부터 until까지의 상승 에지: [(시각, 그 시각에 오르는 도메인)]. 모든 클럭이 시각 0에 함께 오른다."""
    times: dict[int, set[str]] = {}
    for d, per in periods.items():
        for k in range(until // per + 1):
            times.setdefault(k * per, set()).add(d)
    return sorted(times.items())


class _Scope:
    """모듈 인스턴스 하나의 이름 공간. 신호는 `prefix + 이름`으로 시뮬레이터 전체 표에 있다."""

    def __init__(self, sim: "PySim", m: Module, prefix: str, params: dict[str, str]):
        self.sim, self.m, self.prefix = sim, m, prefix
        if m.lang != "py" and any(b["kind"] not in ("memory", *CELLS) for b in m.blocks):
            raise SimError(f"{m.name}: SV 조각 모듈은 실행할 수 없음 (lang: py만)")
        for b in m.blocks:
            if b["kind"] not in ("comb", "seq", "fsm", "memory", *CELLS):
                raise SimError(f'{m.name}: 실행기가 아직 모르는 블록 {b["kind"]}')
        try:
            self.wd = Widths.of(m.source_raw, params)
        except FragError as e:
            raise SimError(f"{m.name}: {e}") from None
        self.consts, self.width = self.wd.consts, self.wd.width
        storage = m.storage()
        # 실행할 블록: 원문(Python)을 다시 파싱해 쓴다
        src = {b["id"]: b for b in m.source_raw.get("blocks", [])}
        self.combs: list[list[ast.stmt]] = []
        self.seqs: list[tuple[str, list[ast.stmt], list[tuple[str, int]]]] = []
        self.fsms: list[tuple[str, str, int, dict[int, list[tuple[ast.expr, int]]]]] = []
        self.cells: list[dict] = []
        for b in m.blocks:
            sb = src.get(b["id"], b)
            if b["kind"] == "comb":
                self.combs.append(parse_body(sb["body"]))
            elif b["kind"] == "memory":
                continue
            elif b["kind"] in CELLS:
                self.cells.append(b)
            elif b["kind"] == "seq":
                resets = [(n, parse_literal(storage[n].reset, self.width[n], self.consts))
                          for n in b["writes"] if storage[n].reset is not None]
                self.seqs.append((b["domain"], parse_body(sb["body"]), resets))
            else:
                trs: dict[int, list[tuple[ast.expr, int]]] = {}
                for t in sb["transitions"]:
                    trs.setdefault(self.consts[t["from"]], []).append((parse_expr(t["cond"]), self.consts[t["to"]]))
                self.fsms.append((b["domain"], f'{b["state_name"]}_q', self.consts[b["reset_state"]], trs))
        for n, w in self.width.items():
            sim.width[prefix + n] = w
            sim.val.setdefault(prefix + n, 0)

    # -- 식 (번역기와 같은 폭 규칙: pyfrag.Widths) --
    def _w(self, n: ast.expr, env: dict[str, int]) -> int:
        return self.wd.self_w(n, env)

    def _ci(self, n: ast.expr, env: dict[str, int]) -> int:
        return self.wd.const(n, env)

    def wid(self, n: str) -> int:
        """신호 폭. 메모리 워드(`mem[3]`)는 워드 폭."""
        return self.width[n] if n in self.width else w_val(self.wd.mems[n.split("[")[0]], self.consts)

    def word(self, n: ast.Subscript, env: dict[str, int]) -> str | None:
        """메모리 워드 키 (`mem[3]`). 주소가 깊이를 넘으면 None."""
        name = n.value.id
        i = self.ev(n.slice, env, operand_w(self._w(n.slice, env)))
        return f"{name}[{i}]" if i < self.wd.depth[name] else None

    def _get(self, name: str, env: dict[str, int]) -> int:
        if name in env:
            return env[name]
        if name in self.consts:
            return self.consts[name]
        return self.sim.val[self.prefix + name]

    def ev(self, n: ast.expr, env: dict[str, int], ctx: int) -> int:
        """문맥 폭 ctx로 계산한 값 (ctx 비트로 자름)."""
        m = mask(ctx)
        if isinstance(n, ast.Name):
            return self._get(n.id, env) & m
        if isinstance(n, ast.Constant):
            return int(n.value) & m
        if isinstance(n, ast.BinOp):
            if isinstance(n.op, (ast.LShift, ast.RShift)):
                a = self.ev(n.left, env, ctx)
                b = self.ev(n.right, env, operand_w(self._w(n.right, env)))
                return (a << b if isinstance(n.op, ast.LShift) else a >> b) & m
            a, b = self.ev(n.left, env, ctx), self.ev(n.right, env, ctx)
            r = {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b, ast.BitAnd: a & b, ast.BitOr: a | b,
                 ast.BitXor: a ^ b}[type(n.op)]
            return r & m
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.Not):
                return int(not self.truth(n.operand, env)) & m
            v = self.ev(n.operand, env, ctx)
            if isinstance(n.op, ast.Invert):
                return ~v & m
            if isinstance(n.op, ast.USub):
                return -v & m
            return v
        if isinstance(n, ast.BoolOp):
            vals = (self.truth(v, env) for v in n.values)
            return int(all(vals) if isinstance(n.op, ast.And) else any(vals)) & m
        if isinstance(n, ast.Compare):
            w = operand_w(max(self._w(n.left, env), self._w(n.comparators[0], env)))
            a, b = self.ev(n.left, env, w), self.ev(n.comparators[0], env, w)
            r = {ast.Eq: a == b, ast.NotEq: a != b, ast.Lt: a < b, ast.LtE: a <= b, ast.Gt: a > b,
                 ast.GtE: a >= b}[type(n.ops[0])]
            return int(r) & m
        if isinstance(n, ast.IfExp):
            return self.ev(n.body if self.truth(n.test, env) else n.orelse, env, ctx)
        if isinstance(n, ast.Subscript):
            if n.value.id in self.wd.mems:
                k = self.word(n, env)
                return self.sim.val.get(self.prefix + k, 0) & m if k else 0
            base = self._get(n.value.id, env)
            if isinstance(n.slice, ast.Slice):
                hi, lo = self._ci(n.slice.lower, env), self._ci(n.slice.upper, env)
                return (base >> lo) & mask(hi - lo + 1) & m
            i = self.ev(n.slice, env, operand_w(self._w(n.slice, env)))
            return (base >> i) & 1 & m
        if isinstance(n, ast.Call):
            f, a = n.func.id, n.args
            if f == "u":
                return self._ci(a[1], env) & m
            if f == "cat":
                r = 0
                for x in a:
                    w = self._w(x, env)
                    r = (r << w) | self.ev(x, env, w)
                return r & m
            if f == "rep":
                w = self._w(a[1], env)
                v = self.ev(a[1], env, w)
                r = 0
                for _ in range(self._ci(a[0], env)):
                    r = (r << w) | v
                return r & m
            w = operand_w(self._w(a[0], env))
            v = self.ev(a[0], env, w)
            r = {"any_bits": int(v != 0), "all_bits": int(v == mask(w)), "parity": bin(v).count("1") & 1}[f]
            return r & m
        raise SimError(f"식을 실행할 수 없음: {ast.dump(n)[:80]}")

    def truth(self, n: ast.expr, env: dict[str, int]) -> bool:
        return bool(self.ev(n, env, operand_w(self._w(n, env))))

    # -- 문장 --
    def run(self, body: list[ast.stmt], env: dict[str, int], write) -> None:
        """write(이름, 새 값 함수): comb는 바로, seq는 모아 두었다가 에지에서 쓴다."""
        for s in body:
            if isinstance(s, (ast.Assign, ast.AugAssign)):
                t = s.targets[0] if isinstance(s, ast.Assign) else s.target
                if isinstance(s, ast.AugAssign):
                    val_node = ast.BinOp(left=t, op=s.op, right=s.value)
                    val_node.left = ast.Name(t.id, ast.Load()) if isinstance(t, ast.Name) else \
                        ast.Subscript(t.value, t.slice, ast.Load())
                else:
                    val_node = s.value
                self.assign(t, val_node, env, write)
            elif isinstance(s, ast.If):
                self.run(s.body if self.truth(s.test, env) else s.orelse, env, write)
            elif isinstance(s, ast.For):
                args = [self._ci(a, env) for a in s.iter.args]
                lo, hi = (args[0], args[1]) if len(args) == 2 else (0, args[0])
                for i in range(lo, hi):
                    self.run(s.body, {**env, s.target.id: i}, write)
            # pass와 설명 문자열은 아무것도 하지 않음

    def assign(self, t: ast.expr, val: ast.expr, env: dict[str, int], write) -> None:
        if isinstance(t, ast.Name):
            w = self.width[t.id]
            v = self.ev(val, env, max(w, self._w(val, env))) & mask(w)
            write(t.id, lambda old: v)
            return
        name = t.value.id
        if name in self.wd.mems:
            k = self.word(t, env)
            w = self.wid(name + "[0]")
            v = self.ev(val, env, max(w, self._w(val, env))) & mask(w)
            if k:   # 깊이를 넘는 주소에 쓰기는 무시 (SV와 같음)
                write(k, lambda old: v)
            return
        if isinstance(t.slice, ast.Slice):
            hi, lo = self._ci(t.slice.lower, env), self._ci(t.slice.upper, env)
        else:
            hi = lo = self.ev(t.slice, env, operand_w(self._w(t.slice, env)))
        w = hi - lo + 1
        v = self.ev(val, env, max(w, self._w(val, env))) & mask(w)
        write(name, lambda old: (old & ~(mask(w) << lo)) | (v << lo))

    def comb(self) -> None:
        val = self.sim.val

        def write(n, f):
            k = self.prefix + n
            val[k] = f(val.get(k, 0)) & mask(self.wid(n))
        for body in self.combs:
            self.run(body, {}, write)

    def edge(self, pending: dict[str, int], rising: set[str]) -> None:
        val = self.sim.val
        for dom, body, resets in self.seqs:
            if self.sim.dom_of[(self.prefix, dom)] not in rising:
                continue
            if resets and self.sim.reset_branch(self, dom):
                for n, r in resets:
                    pending[self.prefix + n] = r
                continue

            def write(n, f):
                k = self.prefix + n
                pending[k] = f(pending.get(k, val.get(k, 0))) & mask(self.wid(n))
            self.run(body, {}, write)
        for dom, q, reset, trs in self.fsms:
            k = self.prefix + q
            if self.sim.dom_of[(self.prefix, dom)] not in rising:
                continue
            if self.sim.reset_branch(self, dom):
                pending[k] = reset
                continue
            for cond, to in trs.get(val[k], []):
                if self.truth(cond, {}):
                    pending[k] = to
                    break

    def async_reset(self) -> None:
        for dom, _, resets in self.seqs:
            if resets and self.sim.async_reset_active(self, dom):
                for n, r in resets:
                    self.sim.val[self.prefix + n] = r
        for dom, q, reset, _ in self.fsms:
            if self.sim.async_reset_active(self, dom):
                self.sim.val[self.prefix + q] = reset


class PySim:
    """설계 모델 실행기. `top`의 포트 이름으로 입력을 넣고 출력을 읽는다. 하위 신호는 `<인스턴스>.<이름>`."""

    def __init__(self, top: Module, library: dict[str, Module] | None = None, max_comb_iter: int = 64):
        self.top = top
        self.library = {**(library or {}), top.name: top}
        self.val: dict[str, int] = {}
        self.width: dict[str, int] = {}
        self.scopes: list[_Scope] = []
        self.links: list[tuple[str, str]] = []   # (받는 쪽, 주는 쪽): 연결은 조합 복사
        self.dom_of: dict[tuple[str, str], str] = {}     # (prefix, 도메인) → 최상위 도메인 (에지가 같음)
        self.rst_src: dict[tuple[str, str], tuple] = {}  # (prefix, 도메인) → ("port", 포트, 활성 값) | ("sync", rst_sync 키)
        self.extra_src: dict[tuple[str, str], list[tuple[str, int]]] = {}   # 추가 동기 리셋: 최상위 (포트, 활성 값)
        self.rst_syncs: dict[str, tuple[str, tuple]] = {}   # rst_sync 키 → (최상위 도메인, 입력 리셋 출처)
        self.max_comb_iter = max_comb_iter
        dmap = {d: d for d in top.domains}
        self._build(top, "", {}, dmap, None)
        for p in top.ports:
            if p.derived:   # 최상위 클럭과 리셋
                self.width[p.name] = 1
                self.val.setdefault(p.name, 0)

    def _build(self, m: Module, prefix: str, params: dict[str, str], dmap: dict[str, str],
               parent: tuple[str, dict[str, str]] | None) -> None:
        """parent: (부모 prefix, 이 모듈 도메인 → 부모 도메인). 최상위는 None."""
        from pipeline.emitter.sv import _instance_nets

        for d, dd in m.domains.items():
            self.dom_of[(prefix, d)] = dmap[d]
            r = dd.get("reset")
            if r is None:   # 리셋 없는 도메인
                self.rst_src[(prefix, d)], self.extra_src[(prefix, d)] = ("none",), []
                continue
            if parent is None:
                src = ("port", r["port"], 0 if r["active"] == "low" else 1)
                self.extra_src[(prefix, d)] = [(x["port"], 0 if x["active"] == "low" else 1) for x in r.get("extra", [])]
            else:
                src = self.rst_src[(parent[0], parent[1][d])]
                self.extra_src[(prefix, d)] = self.extra_src[(parent[0], parent[1][d])]
            if r.get("synchronize"):
                key = f"{prefix}u_rst_sync_{d}"
                self.rst_syncs[key] = (dmap[d], src)
                for reg in ("s1", "out"):
                    self.width[f"{key}.{reg}"] = 1
                    self.val.setdefault(f"{key}.{reg}", 0)
                src = ("sync", key)
            self.rst_src[(prefix, d)] = src
        sc = _Scope(self, m, prefix, params)
        self.scopes.append(sc)
        for b in sc.cells:
            for reg, w in self._cell_regs(sc, b).items():
                self.width[reg] = w
                self.val.setdefault(reg, 0)
        if not m.instances:
            return
        nets, wires = _instance_nets(m, self.library)
        for type_, name, _ in wires:
            self.width[prefix + name] = type_width(type_, sc.consts, sc.wd.enums)
            self.val.setdefault(prefix + name, 0)
        for inst in m.instances:
            child = self.library[inst["module"]]
            cp = f'{prefix}{inst["name"]}.'
            # 인스턴스 파라미터 값은 부모의 상수 이름이거나 SV 상수다
            prm = {k: str(sc.consts[str(v)]) if str(v) in sc.consts else str(v) for k, v in inst.get("params", {}).items()}
            self._build(child, cp, prm, {cd: dmap[inst["domain_map"][cd]] for cd in child.domains},
                        (prefix, dict(inst["domain_map"])))
            for p in child.ports:
                if p.derived:
                    continue
                net = nets.get((inst["name"], p.name))
                if net is None:
                    continue
                parent_net = prefix + net[0]
                self.links.append((cp + p.name, parent_net) if p.dir == "input" else (parent_net, cp + p.name))

    # -- 리셋 --
    def _asserted(self, src: tuple) -> bool:
        if src[0] == "none":
            return False
        if src[0] == "sync":
            return self.val[f"{src[1]}.out"] == 0
        return self.val.get(src[1], 0) == src[2]

    def in_reset(self, sc: _Scope, dom: str) -> bool:
        """주 리셋이 걸려 있는지 (블록 안에서 동기화하는 도메인은 동기화한 리셋)."""
        return self._asserted(self.rst_src[(sc.prefix, dom)])

    def reset_branch(self, sc: _Scope, dom: str) -> bool:
        """에지에서 리셋값을 넣는지: 주 리셋이나 추가 동기 리셋."""
        return self.in_reset(sc, dom) or any(self.val.get(p, 0) == a for p, a in self.extra_src[(sc.prefix, dom)])

    def async_reset_active(self, sc: _Scope, dom: str) -> bool:
        r = sc.m.domains[dom].get("reset")
        return bool(r and r["async"]) and self.in_reset(sc, dom)

    def _reset_ports(self) -> None:
        """하위 모듈의 리셋 포트 값 (comb 조각이 읽음): 연결된 리셋의 값."""
        for sc in self.scopes:
            if not sc.prefix:
                continue
            for d, dd in sc.m.domains.items():
                src, r = self.rst_src[(sc.prefix, d)], dd.get("reset")
                if r is None:
                    continue
                if r.get("synchronize"):   # 이 모듈이 받는 것은 동기화 전 리셋
                    src = self.rst_syncs[f"{sc.prefix}u_rst_sync_{d}"][1]
                if src[0] == "sync":
                    out = self.val[f"{src[1]}.out"]
                    self.val[sc.prefix + r["port"]] = out if r["active"] == "low" else 1 - out
                else:
                    self.val[sc.prefix + r["port"]] = self.val.get(src[1], 0)
                for x, (p, _) in zip(r.get("extra", []), self.extra_src[(sc.prefix, d)]):
                    self.val[sc.prefix + x["port"]] = self.val.get(p, 0)

    # -- 표준 셀 (stubs/의 RTL과 같은 의미) --
    @staticmethod
    def _fifo_a(b: dict) -> int:
        return b["depth"].bit_length() - 1

    def _cell_regs(self, sc: _Scope, b: dict) -> dict[str, int]:
        k = f'{sc.prefix}u_{b["id"]}.'
        if b["kind"] == "cdc_sync" and b["style"] == "pulse":
            return {k + "tog": 1, k + "s1": 1, k + "s2": 1, k + "s3": 1}
        if b["kind"] == "cdc_sync":
            w = sc.wid(b["dst"])
            return {k + "s1": w, k + "q": w}
        a = self._fifo_a(b) + 1
        return {k + r: a for r in ("wbin", "wgray", "rbin", "rgray", "wq1", "wq2", "rq1", "rq2")}

    def _cell_comb(self, sc: _Scope, b: dict) -> None:
        val, k, p = self.val, f'{sc.prefix}u_{b["id"]}.', sc.prefix
        if b["kind"] == "cdc_sync" and b["style"] == "pulse":
            val[p + b["dst"]] = val[k + "s2"] ^ val[k + "s3"]
        elif b["kind"] == "cdc_sync":
            val[p + b["dst"]] = val[k + "q"]
        else:
            a, depth = self._fifo_a(b), b["depth"]
            full = ((val[k + "wbin"] - _gray2bin(val[k + "rq2"])) & mask(a + 1)) == depth
            val[p + b["src"]["ready"]] = int(not full)
            val[p + b["dst"]["valid"]] = int(val[k + "rgray"] != val[k + "wq2"])
            val[p + b["dst"]["data"]] = val.get(f'{k}mem[{val[k + "rbin"] % depth}]', 0)

    def _cell_async(self, sc: _Scope, b: dict) -> None:
        """셀의 리셋은 양쪽 모두 active-low 비동기 (0으로)."""
        k = f'{sc.prefix}u_{b["id"]}.'
        sides = {"src": ("tog",) if b.get("style") == "pulse" else ("wbin", "wgray", "rq1", "rq2"),
                 "dst": ("s1", "s2", "s3") if b.get("style") == "pulse" else
                 ("s1", "q") if b["kind"] == "cdc_sync" else ("rbin", "rgray", "wq1", "wq2")}
        for side, regs in sides.items():
            dom = b[f"{side}_domain"]
            if dom is not None and (side == "dst" or b["kind"] == "cdc_fifo" or b.get("style") == "pulse") \
                    and self.in_reset(sc, dom):
                for r in regs:
                    self.val[k + r] = 0

    def _cell_edge(self, sc: _Scope, b: dict, rising: set[str], pending: dict[str, int]) -> None:
        val, k, p = self.val, f'{sc.prefix}u_{b["id"]}.', sc.prefix
        src_up = b["src_domain"] is not None and self.dom_of[(p, b["src_domain"])] in rising
        dst_up = self.dom_of[(p, b["dst_domain"])] in rising
        src_rst = b["src_domain"] is not None and self.in_reset(sc, b["src_domain"])
        dst_rst = self.in_reset(sc, b["dst_domain"])
        if b["kind"] == "cdc_sync" and b["style"] == "pulse":
            if src_up and not src_rst:
                pending[k + "tog"] = val[k + "tog"] ^ (val[p + b["src"]] & 1)
            if dst_up and not dst_rst:
                pending[k + "s1"], pending[k + "s2"], pending[k + "s3"] = val[k + "tog"], val[k + "s1"], val[k + "s2"]
        elif b["kind"] == "cdc_sync":
            if dst_up and not dst_rst:
                pending[k + "s1"] = val[p + b["src"]] & mask(self.width[k + "s1"])
                pending[k + "q"] = val[k + "s1"]
        else:
            a, depth = self._fifo_a(b), b["depth"]
            if src_up:
                push = val[p + b["src"]["valid"]] and val[p + b["src"]["ready"]]
                if push:   # 메모리 쓰기는 리셋과 무관 (셀 RTL과 같음)
                    pending[f'{k}mem[{val[k + "wbin"] % depth}]'] = val[p + b["src"]["data"]]
                if not src_rst:
                    pending[k + "rq1"], pending[k + "rq2"] = val[k + "rgray"], val[k + "rq1"]
                    if push:
                        nxt = (val[k + "wbin"] + 1) & mask(a + 1)
                        pending[k + "wbin"], pending[k + "wgray"] = nxt, _bin2gray(nxt)
            if dst_up and not dst_rst:
                pending[k + "wq1"], pending[k + "wq2"] = val[k + "wgray"], val[k + "wq1"]
                if val[p + b["dst"]["valid"]] and val[p + b["dst"]["ready"]]:
                    nxt = (val[k + "rbin"] + 1) & mask(a + 1)
                    pending[k + "rbin"], pending[k + "rgray"] = nxt, _bin2gray(nxt)

    # -- 실행 --
    def set(self, values: dict[str, int]) -> None:
        for k, v in values.items():
            self.val[k] = v & mask(self.width.get(k, 1))

    def settle(self) -> None:
        """비동기 리셋과 조합 논리를 값이 바뀌지 않을 때까지 계산한다."""
        for _ in range(self.max_comb_iter):
            before = dict(self.val)
            for key, (_, src) in self.rst_syncs.items():
                if self._asserted(src):
                    self.val[f"{key}.s1"] = self.val[f"{key}.out"] = 0
            for sc in self.scopes:
                sc.async_reset()
                for b in sc.cells:
                    self._cell_async(sc, b)
            self._reset_ports()
            for dst, src in self.links:
                self.val[dst] = self.val[src] & mask(self.width[dst])
            for sc in self.scopes:
                for b in sc.cells:
                    self._cell_comb(sc, b)
                sc.comb()
            if self.val == before:
                return
        raise SimError("조합 논리가 수렴하지 않음 (조합 루프)")

    def step(self, rising: set[str] | None = None) -> None:
        """상승 에지 하나. rising은 이 시각에 에지가 있는 최상위 도메인 (None이면 모두).
        에지 직전 값으로 다음 상태를 계산해 한꺼번에 갱신한다."""
        rising = set(self.top.domains) if rising is None else set(rising)
        self.settle()
        pending: dict[str, int] = {}
        for key, (dom, src) in self.rst_syncs.items():
            if dom in rising and not self._asserted(src):
                pending[f"{key}.s1"], pending[f"{key}.out"] = 1, self.val[f"{key}.s1"]
        for sc in self.scopes:
            sc.edge(pending, rising)
            for b in sc.cells:
                self._cell_edge(sc, b, rising, pending)
        self.val.update(pending)
        self.settle()

    def outputs(self) -> dict[str, int]:
        return {p.name: self.val[p.name] for p in self.top.ports if p.dir == "output"}

    def inputs(self) -> dict[str, int]:
        """최상위 입력 포트와 폭 (클럭 제외, 리셋 포함)."""
        clocks = {d["clock"] for d in self.top.domains.values()}
        return {p.name: self.width[p.name] for p in self.top.ports if p.dir == "input" and p.name not in clocks}

    def input_domains(self) -> dict[str, str | None]:
        """최상위 입력 포트 → 도메인 (비동기 입력은 None). 리셋 포트는 그 리셋을 쓰는 첫 도메인."""
        out = {p.name: p.domain for p in self.top.ports if p.dir == "input" and not p.derived}
        for d in self.top.domains:
            for port in self.top.reset_ports(d):
                out.setdefault(port, d)
        return out


def supported(top: Module, library: dict[str, Module]) -> str | None:
    """실행할 수 없으면 이유, 있으면 None."""
    try:
        PySim(top, library)
    except (SimError, KeyError) as e:
        return str(e)
    return None
