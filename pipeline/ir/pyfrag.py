"""Python 동작 조각 → SV 조각 (모듈 `"lang": "py"`).

동작 조각은 IR 슬롯(`comb`/`seq`의 `body`, `fsm` 전이의 `cond`) 안에 그대로 둔다. Python 파일 하나에서 IR을
뽑지 않는다. 그래서 소스맵은 SV 줄 → (IR 노드, 조각 안의 Python 줄) 한 번으로 끝난다.

조각은 Python 문법을 빌린 사이클 단위 기술이다. CPython으로 실행하지 않고, 이 번역기가 SV로 옮기고
`pysim`이 같은 의미로 실행한다. 두 쪽은 이 파일의 폭 규칙(`Widths`)을 함께 쓴다.

허용하는 것:
- 문장: `x = e`, `x[i] = e`, `x[hi:lo] = e`, `x op= e`(+ - & | ^ << >>), `if/elif/else`, `for i in range(a[, b])`,
  `pass`, 설명 문자열. `comb`에서는 blocking(`=`), `seq`에서는 non-blocking(`<=`)으로 옮긴다.
- 식: 신호, 상수(파라미터, enum 멤버), 정수, True/False, + - * & | ^ ~ << >>, 비교 하나(== != < <= > >=),
  and/or/not, `a if c else b`, `x[i]`, `x[hi:lo]`(SV처럼 양 끝 포함, 상수 범위).
- 도움 함수: `cat(a, b, ...)` → `{a, b}`, `rep(n, x)` → `{n{x}}`, `u(w, v)` → 폭 w의 상수,
  `any_bits(x)` → `|x`, `all_bits(x)` → `&x`, `parity(x)` → `^x`.

의미 (부호 없는 값만):
- 폭은 IEEE 1800 규칙을 따른다. + - * & | ^ ~ 와 조건식은 문맥 폭(대입 대상과 피연산자 중 가장 넓은 폭)으로 계산하고,
  비교는 두 피연산자 중 넓은 폭, 시프트의 오른쪽, 연결 원소, 비트 선택, 축약, 논리 연산의 피연산자는 자기 폭이다.
- 단, 정수 리터럴은 폭이 없고 문맥 폭을 따른다 (SV의 32비트 규칙과 다름). 문맥 폭에 맞지 않는 리터럴은 오류다.
  연결 안의 정수는 폭을 정할 수 없으므로 `u(폭, 값)`으로 쓴다.
- 번역기는 모든 확장과 절단을 캐스트(`16'(a)`)로 적어, 방출한 SV에 암묵적 폭 변환이 없다.

문장 하나는 SV 문장 하나(블록은 begin/end 포함)로만 옮긴다. 문장 사이의 최적화나 재배치는 하지 않는다 (합성이 한다).
`reads`와 `writes`는 AST에서 계산한다.
"""
from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field

HELPERS = {"cat", "rep", "u", "any_bits", "all_bits", "parity"}
_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^",
        ast.LShift: "<<", ast.RShift: ">>"}
_CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
_REDUCE = {"any_bits": "|", "all_bits": "&", "parity": "^"}
LOOP_W = 32   # 반복 변수 (SV int)
_LIT = re.compile(r"^(\d+)?'([sS])?([bBoOdDhH])([0-9a-fA-F_xXzZ?]+)$")


class FragError(Exception):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(f"Python 조각 {line}번째 줄: {message}" if line else message)
        self.line = line


def mask(w: int) -> int:
    return (1 << w) - 1


# -- IR의 상수와 타입 --
def parse_literal(s: str, width: int, consts: dict[str, int]) -> int:
    """리셋값과 파라미터 기본값 같은 SV 상수: `8'hA5`, `1'b0`, `'0`, `'1`, 10진수, 상수 이름."""
    s = str(s).strip()
    if s in ("'0", "'b0"):
        return 0
    if s == "'1":
        return mask(width)
    if s in consts:
        return consts[s] & mask(width)
    if re.fullmatch(r"\d+", s):
        return int(s) & mask(width)
    m = _LIT.match(s)
    if not m:
        raise FragError(f"상수를 읽을 수 없음: {s}")
    base = {"b": 2, "o": 8, "d": 10, "h": 16}[m.group(3).lower()]
    digits = re.sub(r"[xXzZ?]", "0", m.group(4).replace("_", ""))
    return int(digits, base) & mask(width)


def const_int(node: ast.expr, consts: dict[str, int] | None = None) -> int:
    """범위, 반복 횟수, 폭 같은 곳의 상수. 정수, 값을 아는 상수 이름, + - * 만."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and consts and node.id in consts:
        return consts[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult):
        a, b = const_int(node.left, consts), const_int(node.right, consts)
        return a + b if isinstance(node.op, ast.Add) else a - b if isinstance(node.op, ast.Sub) else a * b
    raise FragError("상수 정수가 필요함", getattr(node, "lineno", None))


_TYPE = re.compile(r"(?:logic|bit|reg)(?:\s+unsigned)?(?:\s*\[(.+):(.+)\])?")


def type_width(t: str, consts: dict[str, int], enums: dict[str, int]) -> int:
    """타입의 폭 (값으로)."""
    t = t.strip()
    if t in enums:
        return enums[t]
    if t in ("int", "integer"):
        return 32
    m = _TYPE.fullmatch(t)
    if not m:
        raise FragError(f"Python 조각이 모르는 타입: {t} (logic [hi:lo], int, enum만)")
    if m.group(1) is None:
        return 1
    hi, lo = (const_int(ast.parse(x.strip(), mode="eval").body, consts) for x in (m.group(1), m.group(2)))
    return abs(hi - lo) + 1


class Lin:
    """파라미터의 선형식: 계수·이름의 합 + 상수. 폭을 파라미터 식으로 들고 다녀, 방출한 캐스트가 어느 파라미터 값에서도 맞게 한다."""
    __slots__ = ("terms", "const")

    def __init__(self, terms: dict[str, int] | None = None, const: int = 0):
        self.terms = {k: v for k, v in (terms or {}).items() if v}
        self.const = const

    @classmethod
    def of(cls, n: ast.expr, params: set[str], consts: dict[str, int]) -> "Lin":
        """params는 기호로 남길 이름, consts는 값을 아는 그 밖의 상수."""
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            return cls(const=n.value)
        if isinstance(n, ast.Name):
            if n.id in params:
                return cls({n.id: 1})
            if n.id in consts:
                return cls(const=consts[n.id])
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = cls.of(n.operand, params, consts)
            return v.scale(-1) if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub)):
            a, b = cls.of(n.left, params, consts), cls.of(n.right, params, consts)
            return a + b if isinstance(n.op, ast.Add) else a - b
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
            a, b = cls.of(n.left, params, consts), cls.of(n.right, params, consts)
            if a.terms and b.terms:
                raise FragError("폭 식은 파라미터의 일차식만", getattr(n, "lineno", None))
            return b.scale(a.const) if not a.terms else a.scale(b.const)
        raise FragError("폭과 범위는 정수와 파라미터의 + - * 식만", getattr(n, "lineno", None))

    def __add__(self, o: "Lin") -> "Lin":
        t = dict(self.terms)
        for k, v in o.terms.items():
            t[k] = t.get(k, 0) + v
        return Lin(t, self.const + o.const)

    def __sub__(self, o: "Lin") -> "Lin":
        return self + o.scale(-1)

    def scale(self, k: int) -> "Lin":
        return Lin({n: v * k for n, v in self.terms.items()}, self.const * k)

    def value(self, consts: dict[str, int]) -> int:
        return self.const + sum(v * consts[n] for n, v in self.terms.items())

    def key(self) -> tuple:
        return tuple(sorted(self.terms.items())), self.const

    def sv(self) -> str:
        out = ""
        for n, v in sorted(self.terms.items()):
            term = n if abs(v) == 1 else f"{abs(v)}*{n}"
            out += (("-" if v < 0 else "+") if out else ("-" if v < 0 else "")) + term
        if self.const or not out:
            out += (f"+{self.const}" if self.const > 0 else str(self.const)) if out else str(self.const)
        return out


SymW = tuple   # 폭: Lin 여럿의 최댓값 (정규화된 튜플). None은 정수 리터럴 (문맥을 따름)


def w_const(n: int) -> SymW:
    return (Lin(const=n),)


def w_max(*ws: SymW | None) -> SymW | None:
    lins = [x for w in ws if w for x in w]
    if not lins:
        return None
    keep: dict[tuple, Lin] = {}
    for a in lins:
        if any((b - a).terms == {} and (b - a).const > 0 for b in lins):   # 상수만큼 더 큰 것이 있으면 뺀다
            continue
        keep[a.key()] = a
    return tuple(keep[k] for k in sorted(keep))


def w_eq(a: SymW | None, b: SymW | None) -> bool:
    return (a and b and [x.key() for x in a] == [x.key() for x in b]) or (a is None and b is None)


def w_val(w: SymW | None, consts: dict[str, int]) -> int:
    return max(x.value(consts) for x in w) if w else 0


def w_sv(w: SymW) -> str:
    """폭의 SV 상수식. 최댓값은 조건식으로 적는다."""
    out = w[0].sv()
    for x in w[1:]:
        out = f"(({out}) > ({x.sv()}) ? ({out}) : ({x.sv()}))"
    return out


def w_cast(w: SymW) -> str:
    """캐스트 앞에 붙일 폭: 상수면 숫자, 아니면 괄호로 묶은 식."""
    return str(w[0].const) if len(w) == 1 and not w[0].terms else f"({w_sv(w)})"


def operand_sym(w: SymW | None) -> SymW:
    """자기 폭으로 계산하는 자리에서 리터럴만 있는 식의 폭."""
    return w or w_const(32)


def operand_w(w: int) -> int:
    return w or 32


ONE = w_const(1)


@dataclass
class Widths:
    """한 모듈의 이름 → 폭(파라미터 식)과 상수 값. 번역기와 실행기가 같은 규칙(`self_sym`)을 쓴다."""
    sym: dict[str, SymW] = field(default_factory=dict)      # 읽고 쓰는 신호의 폭
    width: dict[str, int] = field(default_factory=dict)     # 그 값 (지금 파라미터에서)
    consts: dict[str, int] = field(default_factory=dict)    # 파라미터와 enum 멤버의 값
    const_sym: dict[str, SymW] = field(default_factory=dict)
    enums: dict[str, int] = field(default_factory=dict)     # enum 타입 → 폭
    params: set[str] = field(default_factory=set)

    def type_sym(self, t: str) -> SymW:
        t = t.strip()
        if t in self.enums:
            return w_const(self.enums[t])
        if t in ("int", "integer"):
            return w_const(32)
        m = _TYPE.fullmatch(t)
        if not m:
            raise FragError(f"Python 조각이 모르는 타입: {t} (logic [hi:lo], int, enum만)")
        if m.group(1) is None:
            return w_const(1)
        hi, lo = (Lin.of(ast.parse(x.strip(), mode="eval").body, self.params, self.consts) for x in (m.group(1), m.group(2)))
        d = hi - lo
        return ((d if d.value(self.consts) >= 0 else d.scale(-1)) + Lin(const=1),)

    @classmethod
    def of(cls, raw: dict, params: dict[str, str] | None = None) -> "Widths":
        w = cls()
        for t in raw.get("types", []):
            if t.get("kind") != "enum":
                raise FragError(f'Python 조각 모듈은 아직 struct 타입을 쓸 수 없음 ({t.get("name")})')
            w.enums[t["name"]] = type_width(t["base"], {}, {}) if t.get("base") else 32
            for i, mem in enumerate(t["members"]):
                w.consts[mem], w.const_sym[mem] = i, w_const(w.enums[t["name"]])
        for p in raw.get("params", []):
            pw = type_width(p["type"], w.consts, w.enums)
            w.consts[p["name"]] = parse_literal((params or {}).get(p["name"], p["default"]), pw, w.consts)
            w.const_sym[p["name"]] = w_const(pw)
            w.params.add(p["name"])
        for p in raw.get("ports", []):
            for s in p.get("signals", [p]):
                w.sym[s["name"]] = w.type_sym(s["type"])
        for s in raw.get("signals", []):
            w.sym[s["name"]] = w.type_sym(s["type"])
        for b in raw.get("blocks", []):
            if b.get("kind") == "fsm":
                w.sym[f'{b["state_name"]}_q'] = w_const(w.enums.get(b["state_type"], 32))
        w.width = {n: w_val(s, w.consts) for n, s in w.sym.items()}
        return w

    def name_sym(self, name: str, loops) -> SymW:
        if name in loops:
            return w_const(LOOP_W)
        if name in self.const_sym:
            return self.const_sym[name]
        if name in self.sym:
            return self.sym[name]
        raise FragError(f"모르는 이름 {name}")

    def self_sym(self, n: ast.expr, loops=()) -> SymW | None:
        """자기 폭 (파라미터 식). 정수 리터럴은 None (문맥을 따름)."""
        if isinstance(n, ast.Name):
            return self.name_sym(n.id, loops)
        if isinstance(n, ast.Constant):
            return w_const(1) if isinstance(n.value, bool) else None
        if isinstance(n, ast.BinOp):
            if isinstance(n.op, (ast.LShift, ast.RShift)):
                return self.self_sym(n.left, loops)
            return w_max(self.self_sym(n.left, loops), self.self_sym(n.right, loops))
        if isinstance(n, ast.UnaryOp):
            return w_const(1) if isinstance(n.op, ast.Not) else self.self_sym(n.operand, loops)
        if isinstance(n, (ast.BoolOp, ast.Compare)):
            return w_const(1)
        if isinstance(n, ast.IfExp):
            return w_max(self.self_sym(n.body, loops), self.self_sym(n.orelse, loops))
        if isinstance(n, ast.Subscript):
            if isinstance(n.slice, ast.Slice):
                hi, lo = (Lin.of(x, self.params, self.consts) for x in (n.slice.lower, n.slice.upper))
                d = hi - lo
                return ((d if d.value(self.consts) >= 0 else d.scale(-1)) + Lin(const=1),)
            return w_const(1)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            f, a = n.func.id, n.args
            if f in ("cat", "rep"):
                parts = a if f == "cat" else a[1:2]
                ws = [self.self_sym(x, loops) for x in parts]
                if any(w is None for w in ws):
                    raise FragError(f"{f} 안의 정수는 u(폭, 값)으로 씀", n.lineno)
                if any(len(w) != 1 for w in ws):
                    raise FragError(f"{f} 원소의 폭이 파라미터의 최댓값에 달림. 원소를 잘라 폭을 정함", n.lineno)
                total = Lin()
                for w in ws:
                    total = total + w[0]
                return (total if f == "cat" else total.scale(const_int(a[0], self.consts)),)
            if f == "u":
                return w_const(const_int(a[0], self.consts))
            return w_const(1)
        raise FragError(f"쓸 수 없는 식 {type(n).__name__}", getattr(n, "lineno", None))

    def self_w(self, n: ast.expr, loops=()) -> int:
        """자기 폭의 값 (지금 파라미터에서). 정수 리터럴은 0."""
        return w_val(self.self_sym(n, loops), self.consts)

    def const(self, n: ast.expr, loops: dict[str, int] | None = None) -> int:
        return const_int(n, {**self.consts, **(loops or {})})


@dataclass
class Lowered:
    sv: str
    lines: list[tuple[int, int, int]] = field(default_factory=list)  # (SV 시작 줄, 끝 줄, Python 줄), 조각 안에서 1부터
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)


def parse_body(src: str) -> list[ast.stmt]:
    try:
        return ast.parse(textwrap.dedent(src).strip("\n")).body
    except SyntaxError as e:
        raise FragError(f"문법 오류: {e.msg}", e.lineno) from None


def parse_expr(src: str) -> ast.expr:
    try:
        return ast.parse(src.strip(), mode="eval").body
    except SyntaxError as e:
        raise FragError(f"문법 오류: {e.msg}", e.lineno) from None


def _lit(v: int, w: SymW, consts: dict[str, int], ln) -> str:
    """폭 w의 상수. 폭이 파라미터 식이면 캐스트로 쓴다 (값이 맞는지는 지금 파라미터 값으로 본다)."""
    n = w_val(w, consts)
    if v < 0 or v > mask(n):
        raise FragError(f"정수 {v}가 폭 {n}에 맞지 않음", ln)
    if len(w) == 1 and not w[0].terms:
        return f"{n}'h{v:X}" if v > 9 else f"{n}'d{v}"
    return f"{w_cast(w)}'({v})"


class _Tr:
    def __init__(self, kind: str, wd: Widths):
        self.kind, self.wd = kind, wd
        self.loops: list[str] = []
        self.reads: dict[str, None] = {}
        self.writes: dict[str, None] = {}
        self.out: list[str] = []
        self.map: list[tuple[int, int, int]] = []

    def sw(self, n: ast.expr) -> SymW | None:
        return self.wd.self_sym(n, self.loops)

    @staticmethod
    def ext(sv: str, w: SymW, ctx: SymW) -> str:
        return sv if w_eq(w, ctx) else f"{w_cast(ctx)}'({sv})"

    # -- 식: ctx 폭으로 계산되는 SV 식 (자기 폭이 정확히 ctx) --
    def expr(self, n: ast.expr, ctx: SymW) -> str:
        ln = getattr(n, "lineno", None)
        if isinstance(n, ast.Name):
            if n.id in HELPERS:
                raise FragError(f"도움 함수 {n.id}는 호출로만 씀", ln)
            if n.id not in self.wd.consts and n.id not in self.loops:
                if n.id not in self.wd.width:
                    raise FragError(f"모르는 이름 {n.id}", ln)
                self.reads[n.id] = None
            return self.ext(n.id, self.sw(n), ctx)
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool):
                return self.ext("1'b1" if n.value else "1'b0", ONE, ctx)
            if isinstance(n.value, int):
                return _lit(n.value, ctx, self.wd.consts, ln)
            raise FragError(f"쓸 수 없는 상수 {n.value!r}", ln)
        if isinstance(n, ast.BinOp):
            op = _BIN.get(type(n.op))
            if op is None:
                raise FragError(f"쓸 수 없는 연산자 {type(n.op).__name__}", ln)
            if op in ("<<", ">>"):
                return f"({self.expr(n.left, ctx)} {op} {self.expr(n.right, operand_sym(self.sw(n.right)))})"
            return f"({self.expr(n.left, ctx)} {op} {self.expr(n.right, ctx)})"
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.Not):
                return self.ext(f"(!{self.expr(n.operand, operand_sym(self.sw(n.operand)))})", ONE, ctx)
            if isinstance(n.op, ast.Invert):
                return f"(~{self.expr(n.operand, ctx)})"
            if isinstance(n.op, ast.USub):
                return f"(-{self.expr(n.operand, ctx)})"
            return self.expr(n.operand, ctx)
        if isinstance(n, ast.BoolOp):
            op = " && " if isinstance(n.op, ast.And) else " || "
            return self.ext("(" + op.join(self.expr(v, operand_sym(self.sw(v))) for v in n.values) + ")", ONE, ctx)
        if isinstance(n, ast.Compare):
            if len(n.ops) != 1 or type(n.ops[0]) not in _CMP:
                raise FragError("비교는 하나씩, == != < <= > >= 만", ln)
            w = operand_sym(w_max(self.sw(n.left), self.sw(n.comparators[0])))
            return self.ext(f"({self.expr(n.left, w)} {_CMP[type(n.ops[0])]} {self.expr(n.comparators[0], w)})", ONE, ctx)
        if isinstance(n, ast.IfExp):
            return f"({self.expr(n.test, operand_sym(self.sw(n.test)))} ? {self.expr(n.body, ctx)} : {self.expr(n.orelse, ctx)})"
        if isinstance(n, ast.Subscript):
            return self.ext(self.subscript(n), self.sw(n), ctx)
        if isinstance(n, ast.Call):
            return self.ext(self.call(n), self.sw(n), ctx)
        raise FragError(f"쓸 수 없는 식 {type(n).__name__}", ln)

    def bound(self, n: ast.expr) -> str:
        """범위 선택 끝과 반복 범위: 상수(정수, 파라미터, 반복 변수)."""
        names = {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
        if names - set(self.wd.consts) - set(self.loops):
            raise FragError("범위의 끝은 상수 (정수, 파라미터, 반복 변수)", getattr(n, "lineno", None))
        if isinstance(n, ast.Constant):
            return str(const_int(n))
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.BinOp) and type(n.op) in (ast.Add, ast.Sub, ast.Mult):
            return f"({self.bound(n.left)} {_BIN[type(n.op)]} {self.bound(n.right)})"
        raise FragError("범위의 끝은 상수식 (+ - * 만)", getattr(n, "lineno", None))

    def subscript(self, n: ast.Subscript, target: bool = False) -> str:
        ln = n.lineno
        if not isinstance(n.value, ast.Name) or n.value.id not in self.wd.width:
            raise FragError("비트 선택은 신호 이름에만", ln)
        base = n.value.id
        if target:
            self.writes[base] = None
        else:
            self.reads[base] = None
        if isinstance(n.slice, ast.Slice):
            s = n.slice
            if s.lower is None or s.upper is None or s.step is not None:
                raise FragError("범위 선택은 x[hi:lo] (양 끝 포함, 상수)", ln)
            if self.loops and ({x.id for x in ast.walk(s) if isinstance(x, ast.Name)} & set(self.loops)):
                raise FragError("범위 선택의 끝에 반복 변수를 쓸 수 없음 (비트 하나씩 x[i]로)", ln)
            return f"{base}[{self.bound(s.lower)}:{self.bound(s.upper)}]"
        idx = n.slice
        if isinstance(idx, ast.Constant) and isinstance(idx.value, int):
            return f"{base}[{idx.value}]"
        return f"{base}[{self.expr(idx, operand_sym(self.sw(idx)))}]"

    def call(self, n: ast.Call) -> str:
        ln = n.lineno
        f = n.func.id if isinstance(n.func, ast.Name) else None
        if f not in HELPERS or n.keywords:
            raise FragError(f"호출할 수 있는 것은 {sorted(HELPERS)} 뿐", ln)
        a = n.args
        if f == "cat":
            if len(a) < 2:
                raise FragError("cat에는 둘 이상", ln)
            self.sw(n)
            return "{" + ", ".join(self.expr(x, self.sw(x)) for x in a) + "}"
        if f == "rep":
            if len(a) != 2:
                raise FragError("rep(횟수, 값)", ln)
            self.sw(n)
            return f"{{{self.wd.const(a[0])}{{{self.expr(a[1], self.sw(a[1]))}}}}}"
        if f == "u":
            if len(a) != 2:
                raise FragError("u(폭, 값)", ln)
            w, v = self.wd.const(a[0]), self.wd.const(a[1])
            if w < 1:
                raise FragError(f"u({w}, {v}): 폭은 1 이상", ln)
            return _lit(v, w_const(w), self.wd.consts, ln)
        if len(a) != 1:
            raise FragError(f"{f}(값)", ln)
        return f"({_REDUCE[f]}{self.expr(a[0], operand_sym(self.sw(a[0])))})"

    # -- 문장 --
    def target(self, t: ast.expr) -> tuple[str, SymW]:
        if isinstance(t, ast.Name):
            if t.id in self.wd.consts or t.id in self.loops or t.id in HELPERS or t.id not in self.wd.width:
                raise FragError(f"{t.id}에는 쓸 수 없음", t.lineno)
            self.writes[t.id] = None
            return t.id, self.wd.sym[t.id]
        if isinstance(t, ast.Subscript):
            return self.subscript(t, target=True), self.sw(t)
        raise FragError("대입 대상은 신호 이름이나 그 비트 선택", getattr(t, "lineno", None))

    def assign(self, t: ast.expr, val: ast.expr, pad: str) -> None:
        op = "=" if self.kind == "comb" else "<="
        lhs, lw = self.target(t)
        ctx = w_max(lw, self.sw(val))
        rhs = self.expr(val, ctx)
        if not w_eq(ctx, lw):
            rhs = f"{w_cast(lw)}'({rhs})"   # 문맥 폭이 대상보다 넓으면 명시적으로 자름
        self.out.append(f"{pad}{lhs} {op} {rhs};")

    def stmts(self, body: list[ast.stmt], depth: int) -> None:
        for s in body:
            start = len(self.out) + 1
            self.stmt(s, depth)
            self.map.append((start, len(self.out), s.lineno))

    def stmt(self, s: ast.stmt, depth: int) -> None:
        pad = "  " * depth
        if isinstance(s, ast.Assign):
            if len(s.targets) != 1:
                raise FragError("대입은 하나씩", s.lineno)
            self.assign(s.targets[0], s.value, pad)
        elif isinstance(s, ast.AugAssign):
            if type(s.op) not in _BIN or isinstance(s.op, ast.Mult):
                raise FragError("x op= e 는 + - & | ^ << >> 만", s.lineno)
            cur = ast.Subscript(s.target.value, s.target.slice, ast.Load()) if isinstance(s.target, ast.Subscript) \
                else ast.Name(getattr(s.target, "id", ""), ast.Load())
            ast.copy_location(cur, s.target)
            self.assign(s.target, ast.copy_location(ast.BinOp(cur, s.op, s.value), s), pad)
        elif isinstance(s, ast.If):
            self.out.append(f"{pad}if ({self.expr(s.test, operand_sym(self.sw(s.test)))}) begin")
            self.stmts(s.body, depth + 1)
            orelse = s.orelse
            while len(orelse) == 1 and isinstance(orelse[0], ast.If):   # elif
                e = orelse[0]
                start = len(self.out) + 1
                self.out.append(f"{pad}end else if ({self.expr(e.test, operand_sym(self.sw(e.test)))}) begin")
                self.map.append((start, start, e.lineno))
                self.stmts(e.body, depth + 1)
                orelse = e.orelse
            if orelse:
                self.out.append(f"{pad}end else begin")
                self.stmts(orelse, depth + 1)
            self.out.append(f"{pad}end")
        elif isinstance(s, ast.For):
            if not (isinstance(s.target, ast.Name) and isinstance(s.iter, ast.Call) and isinstance(s.iter.func, ast.Name)
                    and s.iter.func.id == "range" and 1 <= len(s.iter.args) <= 2 and not s.orelse):
                raise FragError("반복은 for i in range(끝) 또는 range(시작, 끝)만", s.lineno)
            v = s.target.id
            if v in self.wd.consts or v in self.wd.width or v in self.loops:
                raise FragError(f"반복 변수 이름 {v}가 다른 이름과 겹침", s.lineno)
            args = s.iter.args
            lo, hi = (self.bound(args[0]), self.bound(args[1])) if len(args) == 2 else ("0", self.bound(args[0]))
            self.loops.append(v)
            self.out.append(f"{pad}for (int {v} = {lo}; {v} < {hi}; {v}++) begin")
            self.stmts(s.body, depth + 1)
            self.out.append(f"{pad}end")
            self.loops.pop()
        elif isinstance(s, ast.Pass):
            self.out.append(f"{pad};")
        elif isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str):
            text = s.value.value.strip().splitlines()
            self.out.append(f"{pad}// {text[0] if text else ''}")   # 설명 문자열
        else:
            raise FragError(f"쓸 수 없는 문장 {type(s).__name__}", s.lineno)


def lower_body(src: str, kind: str, wd: Widths) -> Lowered:
    """`comb`/`seq` 블록의 Python body → SV body와 줄 대응, reads, writes."""
    tr = _Tr(kind, wd)
    tr.stmts(parse_body(src), 0)
    if not tr.out:
        raise FragError("빈 조각")
    return Lowered("\n".join(tr.out), tr.map, list(tr.reads), list(tr.writes))


def lower_expr(src: str, wd: Widths) -> tuple[str, list[str]]:
    """`fsm` 전이 조건 같은 식 → (SV 식, reads). 자기 폭으로 계산한다."""
    tr = _Tr("comb", wd)
    n = parse_expr(src)
    sv = tr.expr(n, operand_sym(tr.sw(n)))
    return sv, list(tr.reads)


def lower_module(raw: dict) -> tuple[dict, list[tuple[str, str]], dict[str, list[tuple[int, int, int]]]]:
    """`lang: py` 모듈의 IR → SV 조각 IR. (낮춘 IR, [(노드, 오류)], {조각 노드: 줄 대응})

    reads/writes는 계산한 값으로 채운다. 실패한 조각은 원문을 그대로 두고 오류만 적는다 (Validator가 V4로 보고).
    """
    import copy

    out = copy.deepcopy(raw)
    errs: list[tuple[str, str]] = []
    maps: dict[str, list[tuple[int, int, int]]] = {}
    try:
        wd = Widths.of(raw)
    except (FragError, KeyError, TypeError, AttributeError) as e:
        return out, [("types", f"Python 조각의 폭을 정할 수 없음: {e}")], maps
    for b in out.get("blocks", []):
        if not isinstance(b, dict):
            continue
        node = f'blocks/{b.get("id")}'
        try:
            if b.get("kind") in ("comb", "seq") and isinstance(b.get("body"), str):
                lw = lower_body(b["body"], b["kind"], wd)
                b["body"], b["reads"], b["writes"] = lw.sv, lw.reads, lw.writes
                maps[f"{node}/body"] = lw.lines
            elif b.get("kind") == "fsm":
                reads: dict[str, None] = {}
                for tr in b.get("transitions", []):
                    try:
                        tr["cond"], r = lower_expr(tr["cond"], wd)
                    except FragError as e:
                        errs.append((f'{node}/transitions/{tr.get("id")}', str(e)))
                        continue
                    reads.update(dict.fromkeys(r))
                b["reads"] = list(reads)
        except FragError as e:
            errs.append((node, str(e)))
    return out, errs, maps
