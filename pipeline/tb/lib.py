"""cocotb 하니스 라이브러리 (사람이 검증하는 부분). 생성된 하니스 설정과 Verifier의 참조 모델이 이것을 쓴다.

한 사이클의 순서 (도메인마다, 리셋을 푼 하강 에지가 사이클 0):
  1. 하강 에지: 드라이버가 입력을 바꾼다.
  2. ReadOnly: 표본기가 정해진 순서(입력 모니터 → 출력 모니터 → 프로토콜 체커 → 속성 → 트레이스)로 값을 읽는다.
  3. 다음 상승 에지에서 DUT가 그 값을 받는다. 2에서 valid && ready였던 번들은 그 에지에서 전송이 일어난다.
표본을 한 코루틴에서 정해진 순서로 읽으므로 기댓값과 실제값의 도착 순서가 실행마다 같다.

참조 모델(Verifier 작성)의 규약:
    class Model:
        def on_input(self, stream: str, txn: dict) -> list[tuple[str, dict] | tuple[str, dict, str]]
입력 번들의 전송마다 불리고, 기대하는 출력 (stream, txn[, 요구사항 ID 또는 ID 목록]) 목록을 돌려준다.
모델에 `streams`(집합)가 있으면 그 출력만 스코어보드로 비교한다. 없으면 모든 출력 번들과 단독 출력을 비교한다.
상태 출력처럼 모델이 예측하지 않는 출력은 streams에서 빼고 속성(T4)으로 본다.
출력 stream은 출력 번들 이름이거나 단독 출력 이름이다. 1비트 단독 출력은 1인 사이클마다, 여러 비트 단독 출력은
값이 바뀔 때마다 트랜잭션 하나가 된다.

Verify 툴은 환경 변수로 결과 위치를 준다.
  TB_OUT    결과 디렉터리. 첫 불일치(mismatch.json), 트레이스(trace.json)를 쓴다.
  TB_TRACE  트레이스할 내부 신호 목록(JSON). Verifier는 이 파일을 보지 못한다.
"""
from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly


def _handle(dut, name: str):
    """`u_x.port`처럼 인스턴스 아래 신호도 찾는다."""
    for part in name.split("."):
        dut = getattr(dut, part)
    return dut


def _int(h) -> int | None:
    try:
        return int(h.value)
    except ValueError:  # X/Z (4-state 시뮬레이터)
        return None


class ValidReadyDriver:
    """DUT가 sink인 번들에 트랜잭션을 넣는다. valid를 올리고 ready가 보일 때까지 유지한다."""

    def __init__(self, dut, b: dict):
        self.valid, self.ready = getattr(dut, b["valid"]), getattr(dut, b["ready"])
        self.data = {n: getattr(dut, n) for n in b["data"]}
        self.queue: deque = deque()
        self.cur = None
        self.idle = 0

    def reset(self) -> None:
        self.valid.value = 0
        for h in self.data.values():
            h.value = 0

    def send(self, txn: dict, idle: int = 0) -> None:
        self.queue.append((idle, txn))

    @property
    def busy(self) -> bool:
        return bool(self.queue) or self.cur is not None or self.idle > 0

    def on_falling(self) -> None:
        if self.cur is None and self.idle == 0 and self.queue:
            self.idle, self.cur = self.queue.popleft()
        if self.idle > 0:
            self.idle -= 1
            self.valid.value = 0
            return
        if self.cur is None:
            self.valid.value = 0
            return
        self.valid.value = 1
        for n, v in self.cur.items():
            self.data[n].value = v

    def on_sample(self) -> None:
        if self.cur is not None and self.idle == 0 and _int(self.valid) == 1 and _int(self.ready) == 1:
            self.cur = None


class ReadyDriver:
    """DUT가 source인 번들의 ready를 구동한다. pattern은 사이클마다 돌려 쓰는 ready 값 목록."""

    def __init__(self, dut, b: dict, pattern=(1,)):
        self.ready, self.pattern, self.i = getattr(dut, b["ready"]), list(pattern), 0

    def reset(self) -> None:
        self.ready.value = 0

    busy = False

    def on_falling(self) -> None:
        self.ready.value = self.pattern[self.i % len(self.pattern)]
        self.i += 1

    def on_sample(self) -> None:
        pass


class ValidReadyMonitor:
    def __init__(self, dut, b: dict, sink):
        self.name, self.sink, self.domain = b["name"], sink, b["domain"]
        self.valid, self.ready = getattr(dut, b["valid"]), getattr(dut, b["ready"])
        self.data = {n: getattr(dut, n) for n in b["data"]}

    def sample(self, cycle: int) -> None:
        if _int(self.valid) == 1 and _int(self.ready) == 1:
            self.sink(self.name, {n: _int(h) for n, h in self.data.items()}, cycle, self.domain)


class OutputMonitor:
    """단독 출력. 1비트는 1인 사이클마다, 여러 비트는 값이 바뀔 때마다 트랜잭션."""

    def __init__(self, dut, o: dict, sink):
        self.name, self.sink, self.h, self.pulse = o["name"], sink, getattr(dut, o["name"]), o["width"] == 1
        self.domain = o["domain"]
        self.last = None

    def sample(self, cycle: int) -> None:
        v = _int(self.h)
        if (self.pulse and v == 1) or (not self.pulse and v != self.last and self.last is not None):
            self.sink(self.name, {self.name: v}, cycle, self.domain)
        self.last = v


class ValidReadyChecker:
    """T2. DUT가 source인 번들: valid가 올라간 뒤 ready를 볼 때까지 valid와 data를 유지해야 한다."""

    def __init__(self, dut, b: dict):
        self.name, self.domain = b["name"], b["domain"]
        self.valid, self.ready = getattr(dut, b["valid"]), getattr(dut, b["ready"])
        self.data = {n: getattr(dut, n) for n in b["data"]}
        self.pending = None
        self.violations: list[dict] = []
        self.handshakes = 0

    def sample(self, cycle: int) -> None:
        v, r = _int(self.valid), _int(self.ready)
        d = {n: _int(h) for n, h in self.data.items()}
        if self.pending is not None:
            if v != 1:
                self.violations.append({"cycle": cycle, "domain": self.domain, "bundle": self.name,
                                        "rule": "valid가 ready 전에 내려감"})
            elif d != self.pending:
                self.violations.append({"cycle": cycle, "domain": self.domain, "bundle": self.name,
                                        "rule": "ready 전에 data가 바뀜",
                                        "before": self.pending, "after": d})
        self.pending = d if v == 1 and r != 1 else None
        self.handshakes += int(v == 1 and r == 1)


class Scoreboard:
    """T3. stream마다 기댓값과 실제값을 순서대로 비교하고 첫 불일치를 남긴다.

    기댓값과 실제값 중 먼저 온 쪽은 기다린다. 참조 모델은 입력을 더 받아야 출력을 알 수 있는 경우가 있어서
    (프레임 끝에서 결정되는 값 등) 실제 출력이 기댓값보다 먼저 올 수 있다. 끝까지 짝이 없는 쪽은 finish에서
    missing(기댓값만 있음)이나 unexpected(실제값만 있음)로 보고한다.
    """

    def __init__(self):
        self.expected: dict[str, deque] = {}
        self.actual: dict[str, deque] = {}
        self.seen: dict[str, list] = {}   # 스트림별 실제 출력 전부 (후보 간 차분 검사용)
        self.matched = 0
        self.reqs: set[str] = set()   # 기댓값이 맞은 요구사항 ID (T5)
        self.first: dict | None = None

    def expect(self, stream: str, txn: dict, req: str | None = None, cycle: int | None = None,
               domain: str | None = None) -> None:
        e = (txn, req, cycle, domain)
        if self.actual.get(stream):
            self._compare(stream, e, self.actual[stream].popleft())
        else:
            self.expected.setdefault(stream, deque()).append(e)

    @property
    def pending(self) -> bool:
        """실제 출력을 기다리는 기댓값이 있음."""
        return any(self.expected.values())

    def got(self, stream: str, txn: dict, cycle: int, domain: str | None = None) -> None:
        self.seen.setdefault(stream, []).append(txn)
        a = (txn, cycle, domain)
        if self.expected.get(stream):
            self._compare(stream, self.expected[stream].popleft(), a)
        else:
            self.actual.setdefault(stream, deque()).append(a)

    def _compare(self, stream: str, e: tuple, a: tuple) -> None:
        exp, req, ecycle, edom = e
        txn, cycle, dom = a
        if exp != txn:
            self._fail({"kind": "mismatch", "stream": stream, "expected": exp, "got": txn, "cycle": cycle,
                        "domain": dom, "req": req, "expected_since": ecycle, "expected_domain": edom})
        else:
            self.matched += 1
            if req:
                self.reqs.update([req] if isinstance(req, str) else req)

    def leftover(self) -> None:
        """짝이 없는 기댓값(missing)과 실제값(unexpected). 사이클이 이른 것을 먼저 본다."""
        recs = []
        for stream, q in self.expected.items():
            if q:
                exp, req, ecycle, edom = q[0]
                recs.append({"kind": "missing", "stream": stream, "expected": exp, "got": None, "cycle": ecycle,
                             "domain": edom, "req": req, "expected_since": ecycle, "expected_domain": edom})
        for stream, q in self.actual.items():
            if q:
                txn, cycle, dom = q[0]
                recs.append({"kind": "unexpected", "stream": stream, "expected": None, "got": txn, "cycle": cycle,
                             "domain": dom})
        for r in sorted(recs, key=lambda r: (r["cycle"] if r["cycle"] is not None else 0, r["stream"])):
            self._fail(r)

    def _fail(self, rec: dict) -> None:
        if self.first is None:
            self.first = rec


class Harness:
    def __init__(self, dut, cfg: dict, model=None, *, name: str):
        self.dut, self.cfg, self.model, self.name = dut, cfg, model, name
        self.sb = Scoreboard()
        self.cycle = {d: 0 for d in cfg["clocks"]}
        self.drivers: dict[str, object] = {}
        self.samplers: dict[str, list] = {d: [] for d in cfg["clocks"]}  # 도메인별, 정해진 순서
        self.checkers: list[ValidReadyChecker] = []
        self.properties: list[tuple[str, str, object, str | None]] = []
        self.prop_fail: list[dict] = []
        self.prop_evals = 0
        self.protocol_reqs: dict[str, str] = {}
        self.trace: list[dict] = []
        self._trace_names = self._load_trace_names()
        ins = [b for b in cfg["bundles"] if not b["dut_drives"]]
        outs = [b for b in cfg["bundles"] if b["dut_drives"]]
        for b in ins:
            self.drivers[b["name"]] = ValidReadyDriver(dut, b)
            self.samplers[b["domain"]].append(ValidReadyMonitor(dut, b, self._on_input))
        # 참조 모델이 없으면(속성과 프로토콜만 보는 테스트) 출력을 스코어보드로 보내지 않는다.
        streams = getattr(model, "streams", None)
        if model is not None:
            for b in outs:
                if streams is None or b["name"] in streams:
                    self.samplers[b["domain"]].append(ValidReadyMonitor(dut, b, self._on_output))
            for o in cfg["outputs"]:
                if o["domain"] in self.samplers and (streams is None or o["name"] in streams):
                    self.samplers[o["domain"]].append(OutputMonitor(dut, o, self._on_output))
        for b in outs:
            self.drivers[b["name"]] = ReadyDriver(dut, b)
        for b in outs:
            c = ValidReadyChecker(dut, b)
            self.checkers.append(c)
            self.samplers[b["domain"]].append(c)

    @staticmethod
    def _load_trace_names() -> dict:
        p = os.environ.get("TB_TRACE")
        return json.loads(Path(p).read_text())["names"] if p and Path(p).exists() else {}

    # -- 테스트가 쓰는 API --
    async def start(self, reset_cycles: int = 3) -> None:
        for d, (port, period) in self.cfg["clocks"].items():
            # 주기는 ps 단위의 짝수로 맞춘다 (cocotb Clock은 반주기가 정수여야 함). 예: 90.9MHz → 11002ps
            ps = max(2, round(period * 1000 / 2) * 2)
            cocotb.start_soon(Clock(getattr(self.dut, port), ps, unit="ps").start())
        for drv in self.drivers.values():
            drv.reset()
        for name in self.cfg["inputs"]:
            getattr(self.dut, name).value = 0
        for d, (port, active) in self.cfg["resets"].items():
            getattr(self.dut, port).value = active
        for d, (clk, _) in self.cfg["clocks"].items():
            await ClockCycles(getattr(self.dut, clk), reset_cycles)
        for d in self.cfg["clocks"]:
            await FallingEdge(getattr(self.dut, self.cfg["clocks"][d][0]))
            getattr(self.dut, self.cfg["resets"][d][0]).value = 1 - self.cfg["resets"][d][1]
            # 리셋을 푼 바로 그 사이클부터 표본을 읽는다. 리셋이 빠진 레지스터의 초기값이 여기서 보인다(T1).
            cocotb.start_soon(self._loop(d))

    def send(self, bundle: str, txn: dict, idle: int = 0) -> None:
        self.drivers[bundle].send(txn, idle)

    def set_ready(self, bundle: str, pattern) -> None:
        self.drivers[bundle].pattern = list(pattern)

    def cover_protocol(self, bundle: str, req: str) -> None:
        """T2 체커가 이 번들의 전송을 한 번 이상 검사했으면 req를 실행된 요구사항으로 센다 (T5)."""
        self.protocol_reqs[bundle] = req

    def add_property(self, name: str, domain: str, fn, req: str | None = None) -> None:
        """T4. fn(sample: dict[str, int], cycle) -> None 또는 실패 사유 문자열. sample은 L1 포트 값 (그 도메인의 리셋 포트 포함, 클럭 제외)."""
        self.properties.append((name, domain, fn, req))

    async def drain(self, extra: int = 5, timeout: int = 10000) -> None:
        """입력 드라이버가 비고 기다리던 출력이 모두 올 때까지(최대 timeout 사이클) 기다린 뒤, 모든 도메인에서
        extra 사이클을 더 돈다. 끝까지 오지 않은 출력은 finish()가 missing으로 보고한다."""
        clk = getattr(self.dut, next(iter(self.cfg["clocks"].values()))[0])
        for _ in range(timeout):
            if not any(d.busy for d in self.drivers.values()) and not self.sb.pending:
                break
            await FallingEdge(clk)
        for d, (port, _) in self.cfg["clocks"].items():
            start = self.cycle[d]
            while self.cycle[d] < start + extra:
                await FallingEdge(getattr(self.dut, port))
        await FallingEdge(clk)

    def finish(self) -> None:
        """결과를 TB_OUT에 쓰고, 실패가 있으면 AssertionError를 던진다."""
        self.sb.leftover()
        out = os.environ.get("TB_OUT")
        problems = []
        if self.sb.first:
            f = self.sb.first
            problems.append(f'T3 {f["kind"]} on {f["stream"]} at cycle {f["cycle"]}: expected={f["expected"]} got={f["got"]}')
        for c in self.checkers:
            problems += [f'T2 {v["bundle"]} at cycle {v["cycle"]}: {v["rule"]}' for v in c.violations[:1]]
        problems += [f'T4 {p["property"]} at cycle {p["cycle"]}: {p["reason"]}' for p in self.prop_fail[:1]]
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            # 실행된 요구사항: 기댓값이 맞은 것과, 한 번이라도 평가된 속성의 요구사항 (T5)
            reqs = (self.sb.reqs | {req for _, _, _, req in self.properties if req and self.prop_evals}
                    | {r for c in self.checkers if (r := self.protocol_reqs.get(c.name)) and c.handshakes})
            reqs = sorted(reqs)
            rec = {"test": self.name, "scoreboard": self.sb.first, "matched": self.sb.matched, "reqs": reqs,
                   "outputs": self.sb.seen,
                   "protocol": [v for c in self.checkers for v in c.violations], "properties": self.prop_fail}
            name = _safe(self.name)
            (Path(out) / f"{name}.result.json").write_text(json.dumps(rec, indent=1))
            (Path(out) / f"{name}.trace.json").write_text(json.dumps(self.trace))
        assert not problems, "; ".join(problems)

    # -- 내부 --
    def _on_input(self, stream: str, txn: dict, cycle: int, domain: str) -> None:
        if self.model is None:
            return
        for e in self.model.on_input(stream, txn) or []:
            self.sb.expect(e[0], e[1], e[2] if len(e) > 2 else None, cycle, domain)

    def _on_output(self, stream: str, txn: dict, cycle: int, domain: str) -> None:
        self.sb.got(stream, txn, cycle, domain)

    async def _loop(self, domain: str) -> None:
        clk = getattr(self.dut, self.cfg["clocks"][domain][0])
        drivers = [d for n, d in self.drivers.items() if self._domain_of(n) == domain]
        # 속성 표본에는 그 도메인의 리셋 포트도 넣는다 (테스트가 중간에 리셋을 걸면 체커가 알아야 함). 클럭은 넣지 않는다.
        ports = [n for n, dom in self.cfg["port_domains"].items() if dom == domain] + [self.cfg["resets"][domain][0]]
        traced = [n for n, dom in self._trace_names.items() if dom in (domain, None)]
        first = True
        while True:
            if not first:
                await FallingEdge(clk)
            first = False
            for d in drivers:
                d.on_falling()
            await ReadOnly()
            c = self.cycle[domain]
            for d in drivers:
                d.on_sample()
            for s in self.samplers[domain]:
                s.sample(c)
            if self.properties:
                sample = {n: _int(getattr(self.dut, n)) for n in ports}
                for name, dom, fn, req in self.properties:
                    if dom == domain:
                        self.prop_evals += 1
                        r = fn(sample, c)
                        if r:
                            self.prop_fail.append({"property": name, "cycle": c, "domain": domain, "reason": r, "req": req})
            if traced:
                self.trace.append({"domain": domain, "cycle": c,
                                   "values": {n: _int(_handle(self.dut, n)) for n in traced}})
            self.cycle[domain] = c + 1

    def _domain_of(self, bundle: str) -> str:
        return next(b["domain"] for b in self.cfg["bundles"] if b["name"] == bundle)


def _safe(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in s)
