"""`lang: py` IR의 사이클 단위 실행기 (설계 모델).

Python 조각을 SV와 같은 의미로 실행한다. 판정은 늘 방출한 RTL의 시뮬레이션으로 하고, 이 실행기는 두 가지에 쓴다.
- 번역기 검사: 같은 자극에서 이 실행기와 RTL의 출력을 사이클마다 비교한다 (`pipeline/verify/pyequiv.py`).
- RTL 전 빠른 실행: 하니스 없이 설계 모델을 바로 돌려 본다.

의미 (부호 없는 값만):
- 식의 폭은 번역기와 같은 규칙(`pyfrag.Widths`, IEEE 1800 규칙에 정수 리터럴은 문맥 폭을 따름)으로 계산한다.
- `comb`는 blocking, `seq`와 `fsm`은 클럭 에지에서 한꺼번에 갱신(non-blocking)한다. 리셋이 있는 `seq`는 리셋 중에
  리셋값을 넣는다. 비동기 리셋은 리셋이 걸린 동안 바로 리셋값을 유지한다.
- 조합 논리는 값이 더 바뀌지 않을 때까지 되풀이해 계산한다 (조합 루프는 Validator V6이 막음).

지원 범위: 도메인 하나, `comb`/`seq`/`fsm` 블록, 인스턴스와 연결(계층). `memory`, `cdc_sync`, struct, signed는 아직 없다.
조각이 SV인 모듈(`lang: sv`)은 동작 블록이 없을 때만(구조만 있는 Block Top) 실행할 수 있다.
"""
from __future__ import annotations

import ast

from pipeline.ir.model import Module
from pipeline.ir.pyfrag import FragError, Widths, mask, operand_w, parse_body, parse_expr, parse_literal, type_width


class SimError(Exception):
    pass


class _Scope:
    """모듈 인스턴스 하나의 이름 공간. 신호는 `prefix + 이름`으로 시뮬레이터 전체 표에 있다."""

    def __init__(self, sim: "PySim", m: Module, prefix: str, params: dict[str, str]):
        self.sim, self.m, self.prefix = sim, m, prefix
        if m.lang != "py" and any(b["kind"] != "memory" for b in m.blocks):
            raise SimError(f"{m.name}: SV 조각 모듈은 실행할 수 없음 (lang: py만)")
        for b in m.blocks:
            if b["kind"] not in ("comb", "seq", "fsm"):
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
        for b in m.blocks:
            sb = src.get(b["id"], b)
            if b["kind"] == "comb":
                self.combs.append(parse_body(sb["body"]))
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
            val[k] = f(val[k]) & mask(self.width[n])
        for body in self.combs:
            self.run(body, {}, write)

    def edge(self, pending: dict[str, int]) -> None:
        val = self.sim.val
        for dom, body, resets in self.seqs:
            if resets and self.sim.in_reset(self, dom):
                for n, r in resets:
                    pending[self.prefix + n] = r
                continue

            def write(n, f):
                k = self.prefix + n
                pending[k] = f(pending.get(k, val[k])) & mask(self.width[n])
            self.run(body, {}, write)
        for dom, q, reset, trs in self.fsms:
            k = self.prefix + q
            if self.sim.in_reset(self, dom):
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
        if len(top.domains) != 1:
            raise SimError(f"{top.name}: 실행기는 아직 클럭 도메인 하나만 실행함 ({sorted(top.domains)})")
        self.scopes: list[_Scope] = []
        self.links: list[tuple[str, str]] = []   # (받는 쪽, 주는 쪽): 연결은 조합 복사
        self.reset_of: dict[tuple[str, str], str] = {}  # (prefix, 도메인) → 최상위 리셋 포트
        self.max_comb_iter = max_comb_iter
        self._build(top, "", {}, {d: d for d in top.domains})
        for p in top.ports:
            if p.derived:   # 최상위 클럭과 리셋
                self.width[p.name] = 1
                self.val.setdefault(p.name, 0)

    def _build(self, m: Module, prefix: str, params: dict[str, str], dmap: dict[str, str]) -> None:
        from pipeline.emitter.sv import _instance_nets

        sc = _Scope(self, m, prefix, params)
        self.scopes.append(sc)
        for d in m.domains:
            self.reset_of[(prefix, d)] = dmap[d]
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
            self._build(child, cp, prm,
                        {cd: dmap[inst["domain_map"][cd]] for cd in child.domains})
            for p in child.ports:
                if p.derived:
                    continue
                net = nets.get((inst["name"], p.name))
                if net is None:
                    continue
                parent = prefix + net[0]
                self.links.append((cp + p.name, parent) if p.dir == "input" else (parent, cp + p.name))

    # -- 리셋 --
    def _reset_port(self, sc: _Scope, dom: str) -> tuple[str, dict]:
        top_dom = self.reset_of[(sc.prefix, dom)]
        d = self.top.domains[top_dom]
        return d["reset"]["port"], d["reset"]

    def in_reset(self, sc: _Scope, dom: str) -> bool:
        port, r = self._reset_port(sc, dom)
        v = self.val.get(port, 0)
        return v == (0 if r["active"] == "low" else 1)

    def async_reset_active(self, sc: _Scope, dom: str) -> bool:
        return self._reset_port(sc, dom)[1]["async"] and self.in_reset(sc, dom)

    # -- 실행 --
    def set(self, values: dict[str, int]) -> None:
        for k, v in values.items():
            self.val[k] = v & mask(self.width.get(k, 1))

    def settle(self) -> None:
        """비동기 리셋과 조합 논리를 값이 바뀌지 않을 때까지 계산한다."""
        for _ in range(self.max_comb_iter):
            before = dict(self.val)
            for sc in self.scopes:
                sc.async_reset()
            for dst, src in self.links:
                self.val[dst] = self.val[src] & mask(self.width[dst])
            for sc in self.scopes:
                sc.comb()
            if self.val == before:
                return
        raise SimError("조합 논리가 수렴하지 않음 (조합 루프)")

    def step(self) -> None:
        """클럭 상승 에지 하나. 에지 직전 값으로 다음 상태를 계산해 한꺼번에 갱신한다."""
        self.settle()
        pending: dict[str, int] = {}
        for sc in self.scopes:
            sc.edge(pending)
        self.val.update(pending)
        self.settle()

    def outputs(self) -> dict[str, int]:
        return {p.name: self.val[p.name] for p in self.top.ports if p.dir == "output"}

    def inputs(self) -> dict[str, int]:
        """최상위 입력 포트와 폭 (클럭 제외, 리셋 포함)."""
        clocks = {d["clock"] for d in self.top.domains.values()}
        return {p.name: self.width[p.name] for p in self.top.ports if p.dir == "input" and p.name not in clocks}


def supported(top: Module, library: dict[str, Module]) -> str | None:
    """실행할 수 없으면 이유, 있으면 None."""
    try:
        PySim(top, library)
    except (SimError, KeyError) as e:
        return str(e)
    return None
