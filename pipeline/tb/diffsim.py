"""후보 간 차분 시뮬레이션의 cocotb 테스트. 같은 무작위 자극을 후보마다 넣고 출력 트랜잭션을 기록한다.

자극은 DUT 응답과 무관하게 시드로 정한다: 입력 트랜잭션 순서, 사이클마다의 valid 의도, 출력 ready, 리셋, 단독 입력(pause 등).
그래서 지연이 달라도 SPEC을 지키는 두 후보는 같은 입력 순서를 받고 같은 출력 순서를 낸다.

- steady: 처음 리셋 뒤에는 리셋을 넣지 않는다. 출력 트랜잭션 순서 전체를 비교한다.
- reset: 중간에 리셋을 넣고, 마지막 리셋 뒤 쉬었다가 프로브 트랜잭션을 보낸다.

두 모드 모두 출력 트랜잭션 순서 전체를 비교한다. 리셋 때 흘러가던 데이터의 처리도 SPEC이 정할 수 있기 때문이다.
차이가 SPEC이 정하지 않은 동작에서 났는지는 Verifier가 판단한다.

설정 `cycle_trace`가 참이면 도메인마다 사이클별로 그 도메인의 모든 출력 포트 값을 `cycles`에 기록한다 (P11 R4의
원본 RTL과 방출 RTL 사이클 비교. 자극이 DUT 응답과 무관하므로 두 RTL을 따로 돌려도 같은 입력을 받는다).
`fixed`({포트: 값})를 주면 그 단독 입력은 무작위 대신 그 값으로 둔다.

설정은 환경 변수 DIFF_CFG(JSON 파일), 결과는 DIFF_OUT(JSON 파일)이다. 비교는 `compare`가 한다.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

try:
    import cocotb
    from cocotb.clock import Clock
    from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
except ImportError:  # compare만 쓸 때 (cocotb 없이)
    cocotb = None


def _int(h):
    try:
        return int(h.value)
    except ValueError:
        return None


def _bursts(rng, n, values, weights, maxlen):
    out = []
    while len(out) < n:
        out += [rng.choices(values, weights)[0]] * rng.randint(1, maxlen)
    return out[:n]


def load_model(path: str | None, harness_dir: str | None = None):
    """Verifier 테스트의 참조 모델 (legal로 SPEC 밖 입력을 거르려고)."""
    if not path:
        return None
    import importlib.util
    for d in (harness_dir, str(Path(path).parent)):
        if d and d not in sys.path:
            sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("diff_model", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Model()


def make_plan(cfg: dict) -> dict:
    """자극 계획. 도메인마다 사이클별 리셋, 출력 ready, 단독 입력, 입력 valid 의도와 입력 트랜잭션 순서."""
    h, widths, mode, seed = cfg["harness"], cfg["widths"], cfg["mode"], cfg["seed"]
    cycles, drain = cfg["cycles"], cfg["drain"]
    model = load_model(cfg.get("model"), cfg.get("harness_dir"))
    ins = [b for b in h["bundles"] if not b["dut_drives"]]
    outs = [b for b in h["bundles"] if b["dut_drives"]]
    txn_rng = random.Random(seed * 7919 + 1)

    def next_txn(b):
        for _ in range(100):
            t = {d: txn_rng.getrandbits(widths.get(d, 8)) for d in b["data"]}
            if model is None or not hasattr(model, "legal") or model.legal(b["name"], dict(t)):
                return t
        return t

    probe_at = cycles - 400 if mode == "reset" else None   # 프로브 300사이클 뒤 남은 100사이클과 drain 동안 다 나온다
    plan = {"probe_at": probe_at, "total": cycles + drain, "drain": drain,
            "queues": {b["name"]: [next_txn(b) for _ in range(cycles)] for b in ins},   # 입력 트랜잭션 순서 (모든 후보에 같음)
            "probes": {b["name"]: [next_txn(b) for _ in range(400)] for b in ins},      # 프로브 구간은 처음부터 이 순서로
            "domains": {}}
    for k, d in enumerate(sorted(h["clocks"])):
        rng = random.Random(seed * 1000 + k)
        reset = [1] * INIT_RESET + [0] * (cycles + drain - INIT_RESET)
        if mode == "reset" and d in h["resets"]:
            c = INIT_RESET + 50
            while c < cycles - 300:
                if rng.random() < 1 / 250:
                    for j in range(rng.randint(1, 8)):
                        reset[c + j] = 1
                    c += 10
                c += 1
        dp = {"reset": reset,
              "ready": {b["name"]: _bursts(rng, cycles, [1, 0], [0.6, 0.4], 60) + [1] * drain for b in outs if b["domain"] == d},
              "single": {x: _bursts(rng, cycles, [0, 1], [0.75, 0.25], 200) + [0] * drain
                         for x in h["inputs"] if h["port_domains"].get(x) == d},
              "valid": {b["name"]: [int(rng.random() < 0.7) for _ in range(cycles)] + [0] * drain for b in ins if b["domain"] == d}}
        if probe_at is not None:   # 프로브 구간: 리셋 없음, ready=1, 단독 입력 0, 입력은 프로브 300사이클만
            for c in range(probe_at - 100, cycles):
                dp["reset"][c] = 0
                for o in dp["ready"].values():
                    o[c] = 1
                for x in dp["single"].values():
                    x[c] = 0
                for i in dp["valid"].values():
                    i[c] = int(probe_at <= c < probe_at + 300)
        plan["domains"][d] = dp
    return plan


INIT_RESET = 10
_NEUTRAL = {"reset": 0, "ready": 1, "single": 0}
_ACTIVE = {"reset": 1, "ready": 0, "single": 1}


def episodes(plan: dict) -> list[dict]:
    """줄일 수 있는 자극 사건: 리셋 펄스(처음 리셋 제외), 출력 ready=0 구간, 단독 입력=1 구간."""
    out = []
    for d, dp in plan["domains"].items():
        series = [("reset", "reset", dp["reset"])] + [("ready", n, v) for n, v in dp["ready"].items()] + \
                 [("single", n, v) for n, v in dp["single"].items()]
        for kind, name, vals in series:
            c = INIT_RESET if kind == "reset" else 0
            while c < len(vals):
                if vals[c] == _ACTIVE[kind]:
                    e = c
                    while e < len(vals) and vals[e] == _ACTIVE[kind]:
                        e += 1
                    out.append({"domain": d, "kind": kind, "name": name, "start": c, "len": e - c})
                    c = e
                else:
                    c += 1
    return out


def without(plan: dict, eps: list[dict]) -> dict:
    """사건들을 지운(중립 값으로 바꾼) 계획."""
    p = json.loads(json.dumps(plan))
    for e in eps:
        dp = p["domains"][e["domain"]]
        vals = dp["reset"] if e["kind"] == "reset" else dp[e["kind"]][e["name"]]
        for c in range(e["start"], e["start"] + e["len"]):
            vals[c] = _NEUTRAL[e["kind"]]
    return p


def truncate(plan: dict, upto: int) -> dict:
    """upto 사이클 뒤의 자극을 없애고(리셋 없음, ready=1, 단독 입력 0, 새 입력 없음) drain만 남긴다."""
    p = json.loads(json.dumps(plan))
    total = min(p["total"], upto + p["drain"])
    p["total"] = total
    if p["probe_at"] is not None and p["probe_at"] >= upto:
        p["probe_at"] = None
    for dp in p["domains"].values():
        for kind in ("reset", "ready", "single", "valid"):
            seq = [dp["reset"]] if kind == "reset" else list(dp[kind].values())
            for vals in seq:
                for c in range(upto, len(vals)):
                    vals[c] = 0 if kind == "valid" else _NEUTRAL[kind]
                del vals[total:]
    return p


def describe(plan: dict, h: dict) -> list[str]:
    """사람과 Verifier가 읽을 자극 요약 (사건을 시간순으로)."""
    ready_port = {b["name"]: b["ready"] for b in h["bundles"]}
    lines = []
    for e in sorted(episodes(plan), key=lambda e: (e["start"], e["domain"])):
        if e["kind"] == "reset":
            port, active = h["resets"][e["domain"]]
            what = f"{port}={active} (리셋)"
        elif e["kind"] == "ready":
            what = f"{ready_port[e['name']]}=0 (출력 backpressure)"
        else:
            what = f"{e['name']}=1"
        lines.append(f"{e['domain']} 도메인 사이클 {e['start']}~{e['start'] + e['len'] - 1} ({e['len']}사이클): {what}")
    return lines


if cocotb is not None:
    @cocotb.test()
    async def diff_stimulus(dut):
        cfg = json.loads(Path(os.environ["DIFF_CFG"]).read_text())
        h = cfg["harness"]
        plan = cfg.get("plan") or make_plan(cfg)
        probe_at = plan["probe_at"]
        ins = [b for b in h["bundles"] if not b["dut_drives"]]
        outs = [b for b in h["bundles"] if b["dut_drives"]]
        doms = sorted(h["clocks"])
        rec = {"outputs": {b["name"]: [] for b in outs}, "inputs": {b["name"]: 0 for b in ins}, "events": [],
               "resets": {d: [] for d in doms}, "probe_at": probe_at}
        fixed = cfg.get("fixed", {})
        trace_ports = {}
        if cfg.get("cycle_trace"):
            rec["cycles"] = {d: [] for d in doms}
            for d in doms:
                names = [o["name"] for o in h["outputs"] if o["domain"] == d]
                for b in h["bundles"]:
                    if b["domain"] == d:
                        names += [b["valid"], *b["data"]] if b["dut_drives"] else [b["ready"]]
                trace_ports[d] = names
        started = set()
        for d in doms:
            clk, period = h["clocks"][d]
            ps = max(2, round(period * 1000 / 2) * 2)   # 하니스와 같이 ps 단위 짝수 주기
            if clk not in started:   # 클럭 포트를 함께 쓰는 도메인 (같은 클럭, 예: 하강 에지 도메인)
                started.add(clk)
                cocotb.start_soon(Clock(getattr(dut, clk), ps, unit="ps").start())
        neg = set(h.get("neg_edge", ()))

        async def run(d):
            p, clk = plan["domains"][d], getattr(dut, h["clocks"][d][0])
            edge = RisingEdge if d in neg else FallingEdge   # 입력을 바꾸는 에지 (하니스와 같음)
            rport, ractive = h["resets"].get(d, (None, 1))
            dins = [b for b in ins if b["domain"] == d]
            douts = [b for b in outs if b["domain"] == d]
            idx = {b["name"]: 0 for b in dins}
            cur = {b["name"]: None for b in dins}
            q = {b["name"]: plan["queues"][b["name"]] for b in dins}
            prev = {}
            for c in range(plan["total"]):
                await edge(clk)
                drv = {}
                if rport:
                    drv[rport] = ractive if p["reset"][c] else 1 - ractive
                for x, vals in p["single"].items():
                    drv[x] = fixed.get(x, vals[c])
                for b in douts:
                    drv[b["ready"]] = p["ready"][b["name"]][c]
                for b in dins:
                    n = b["name"]
                    if probe_at is not None and c == probe_at:
                        q[n], idx[n], cur[n] = plan["probes"][n], 0, None
                    if p["reset"][c] and not (plan.get("valid_in_reset") and c >= INIT_RESET):
                        cur[n] = None   # refsim은 테스트를 되풀이하므로 처음 리셋 뒤의 리셋 사이클에도 기록된 valid를 낸다
                    elif cur[n] is None and p["valid"][n][c] and idx[n] < len(q[n]):
                        cur[n] = q[n][idx[n]]
                        idx[n] += 1
                    drv[b["valid"]] = 1 if cur[n] is not None else 0
                    for k2, v in (cur[n] or {}).items():
                        drv[k2] = v
                for k2, v in drv.items():
                    getattr(dut, k2).value = v
                    if prev.get(k2) != v and k2 in (rport, *p["single"], *[b["ready"] for b in douts]):
                        rec["events"].append([d, c, k2, v])
                    prev[k2] = v
                if p["reset"][c] and (c == 0 or not p["reset"][c - 1]):
                    rec["resets"][d].append(c)
                await ReadOnly()
                for b in dins:
                    if cur[b["name"]] is not None and _int(getattr(dut, b["valid"])) == 1 and _int(getattr(dut, b["ready"])) == 1:
                        rec["inputs"][b["name"]] += 1
                        cur[b["name"]] = None
                for b in douts:
                    if _int(getattr(dut, b["valid"])) == 1 and _int(getattr(dut, b["ready"])) == 1:
                        rec["outputs"][b["name"]].append([d, c, {n: _int(getattr(dut, n)) for n in b["data"]}])
                if d in trace_ports:
                    rec["cycles"][d].append({n: _int(getattr(dut, n)) for n in trace_ports[d]})

        tasks = [cocotb.start_soon(run(d)) for d in doms]
        for t in tasks:
            await t
        Path(os.environ["DIFF_OUT"]).write_text(json.dumps(rec))


def compare(a: dict, b: dict) -> dict | None:
    """두 후보의 기록을 비교해 첫 차이를 돌려준다. 같으면 None."""
    for stream in a["outputs"]:
        xa, xb = a["outputs"][stream], b["outputs"][stream]
        for i, (ta, tb) in enumerate(zip(xa, xb)):
            if ta[2] != tb[2]:
                return {"stream": stream, "kind": "data", "index": i, "a": ta, "b": tb, "a_prev": xa[max(0, i - 3):i],
                        "b_prev": xb[max(0, i - 3):i]}
        if len(xa) != len(xb):
            n = min(len(xa), len(xb))
            return {"stream": stream, "kind": "count", "index": n, "a_count": len(xa), "b_count": len(xb),
                    "a": xa[n] if len(xa) > n else None, "b": xb[n] if len(xb) > n else None,
                    "a_prev": xa[max(0, n - 3):n], "b_prev": xb[max(0, n - 3):n]}
    return None
