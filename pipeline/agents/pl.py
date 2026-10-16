"""에이전트용 도구 CLI. 작업 디렉터리의 `tools/pl.py`로 놓이고, 같은 디렉터리의 파이프라인 사본을 쓴다.

    python3 tools/pl.py validate <ir.json> [--l1 l1.json] [--lib <IR 디렉터리>]   # Validator 사전 실행 (+ 동결 L1 대조)
    python3 tools/pl.py patch <ir.json> <patches.json> [--lib <dir>]             # patch 사전 실행 (적용하지 않고 검사만)
    python3 tools/pl.py emit <ir.json> [--lib <dir>]                             # 방출될 SV 보기
    python3 tools/pl.py fanin <ir.json> <신호...>                                # 출력의 팬인 노드와 신호
    python3 tools/pl.py trace <trace.json> <신호...> [--from N --to M]           # 시뮬레이션 트레이스 값 조회
    python3 tools/pl.py spec <spec.md> <요구사항 ID...>                          # SPEC 구절 조회
    python3 tools/pl.py harness <l1.json> -o <dir>                               # L1에서 cocotb 하니스 생성
    python3 tools/pl.py model <model.py> <l1.json> [--n 200]                     # 참조 모델 단독 실행 (무작위 입력)
    python3 tools/pl.py pysim <ir.json> [--lib <dir>] [--stim stim.json] [--cycles 20]  # lang: py 설계 모델 실행 (RTL 없이)
    python3 tools/pl.py porteq <ir.json> [--lib <dir>] --ref <원본 묶음>             # P11 원본 RTL과 사이클 비교 (R4)
    python3 tools/pl.py spec_gate <spec.md> --tables tables.md --top <모듈>          # P11 SPEC 게이트 (검사 + 2~4절 왕복)

결과는 JSON으로 낸다. 호출 기록은 `.tools.log`에 남는다 (도구 사용 측정용. PL_NO_LOG=1이면 남기지 않음).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # 작업 디렉터리에 __pycache__를 남기지 않는다
HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1]):
    if (p / "pipeline" / "validator").is_dir():
        sys.path.insert(0, str(p))
        break



def _lib(d: str | None):
    from pipeline.ir.model import load_library
    return load_library(sorted(Path(d).glob("*.ir.json"))) if d else {}


def _load_ir(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(a) -> dict:
    from pipeline.ir.model import Module
    from pipeline.validator.checks import errors, validate

    try:
        raw = _load_ir(a.ir)
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "errors": [f"IR을 읽을 수 없음: {e}"]}
    issues = validate(Module(raw), _lib(a.lib))
    errs = [str(i) for i in errors(issues)]
    if a.l1:
        from pipeline.ir.model import frozen_l1

        mine, frozen = frozen_l1(raw), frozen_l1(_load_ir(a.l1))
        errs += [f"[동결] {k}: 동결된 L1과 다름 (출력 포트의 kind와 reset, local 파라미터만 정할 수 있음)"
                 for k in frozen if mine.get(k) != frozen.get(k)]
    return {"ok": not errs, "errors": errs[:20], "warnings": [str(i) for i in issues if i.severity != "error"][:10]}


def cmd_patch(a) -> dict:
    from pipeline.ir.model import Module
    from pipeline.patch.apply import apply, ir_hash
    from pipeline.validator.checks import errors, validate

    res = apply(_load_ir(a.ir), json.loads(Path(a.patches).read_text(encoding="utf-8")))
    out = {"ok": res.ok, "rejected": res.rejected, "errors": [], "ir_hash": ir_hash(res.ir)}
    if res.ok:
        out["errors"] = [str(i) for i in errors(validate(Module(res.ir), _lib(a.lib)))][:20]
        out["ok"] = not out["errors"]
    return out


def cmd_emit(a) -> dict:
    from pipeline.emitter.sv import emit
    from pipeline.ir.model import Module

    return {"sv": emit(Module(_load_ir(a.ir)), _lib(a.lib)).text}


def cmd_fanin(a) -> dict:
    from pipeline.ir.model import Module
    from pipeline.tb.report import fanin

    nodes, sigs = fanin(Module(_load_ir(a.ir)), a.signals)
    return {"nodes": nodes, "signals": sigs}


def cmd_trace(a) -> dict:
    t = json.loads(Path(a.trace).read_text(encoding="utf-8"))
    rows = [{"domain": e["domain"], "cycle": e["cycle"], **{s: e["values"].get(s) for s in a.signals}}
            for e in t if a.lo <= e["cycle"] <= a.hi]
    return {"rows": rows[:400]}


def cmd_spec(a) -> dict:
    from pipeline.spec.parse import load

    s = load(a.spec)
    return {"requirements": [{"id": r.id, "level": r.level, "text": r.text, "line": r.line}
                             for i in a.ids if (r := s.requirement(i))],
            "unknown": [i for i in a.ids if not s.requirement(i)]}


def cmd_harness(a) -> dict:
    from pipeline.ir.model import Module
    from pipeline.tb.gen import harness_source

    m = Module(_load_ir(a.l1))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{m.name}_harness.py").write_text(harness_source(m), encoding="utf-8")
    return {"harness": str(out / f"{m.name}_harness.py")}


def cmd_model(a) -> dict:
    """참조 모델을 시뮬레이터 없이 돌려 본다: 입력 번들마다 무작위 트랜잭션을 넣고 예외가 없는지 본다.
    값은 신호 폭에 맞춘다. 모델에 legal(stream, txn)이 있으면 SPEC 밖의 입력(미정의)은 건너뛴다."""
    from pipeline.ir.model import Module
    from pipeline.tb.gen import harness_config, signal_widths

    raw = _load_ir(a.l1)
    cfg = harness_config(Module(raw))
    spec = importlib.util.spec_from_file_location("model_under_test", a.model)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(a.model).parent))
    spec.loader.exec_module(mod)
    model = mod.Model()
    rng = random.Random(a.seed)
    ins = [b for b in cfg["bundles"] if not b["dut_drives"]]
    widths = signal_widths(raw)

    out_counts: dict[str, int] = {}
    skipped = 0
    try:
        for _ in range(a.n):
            b = rng.choice(ins)
            txn = {d: rng.getrandbits(widths.get(d, 8)) for d in b["data"]}
            if hasattr(model, "legal") and not model.legal(b["name"], txn):
                skipped += 1
                continue
            for o in model.on_input(b["name"], txn) or []:
                out_counts[o[0]] = out_counts.get(o[0], 0) + 1
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "inputs": a.n - skipped, "skipped": skipped, "expected_outputs": out_counts}


def cmd_pysim(a) -> dict:
    """lang: py IR의 설계 모델을 사이클마다 실행한다. stim은 사이클마다 입력 값 dict의 목록이고, 빠진 입력은 0,
    리셋 포트를 주지 않으면 첫 2사이클만 주 리셋을 건다 (추가 리셋은 풀어 둠). 사이클마다 입력과 출력(에지 직전 값)을 낸다.
    도메인이 여럿이면 행 하나가 상승 에지가 있는 시각 하나이고, 행에 시각(t_ps)과 그때 오르는 도메인(rising)을 함께 낸다."""
    import random

    from pipeline.ir.model import Module
    from pipeline.ir.pysim import PySim, SimError

    m = Module(_load_ir(a.ir))
    if m.lower_errors:
        return {"ok": False, "errors": [f"{n}: {e}" for n, e in m.lower_errors]}
    try:
        sim = PySim(m, _lib(a.lib))
    except SimError as e:
        return {"ok": False, "errors": [str(e)]}
    resets = {}   # 리셋 포트 → 활성 값 (주 리셋만 처음 2행 동안 걸고, 추가 리셋은 풀어 둠)
    for d in m.domains.values():
        if not d.get("reset"):
            continue
        resets.setdefault(d["reset"]["port"], (0 if d["reset"]["active"] == "low" else 1, True))
        for x in d["reset"].get("extra", []):
            resets.setdefault(x["port"], (0 if x["active"] == "low" else 1, False))
    stim = json.loads(Path(a.stim).read_text(encoding="utf-8")) if a.stim else None
    rng = random.Random(a.seed)
    # 도메인이 여럿이면 행 하나가 상승 에지가 있는 시각 하나다 (주기는 freq_mhz, 없으면 10ns. 분주 도메인은 기준 주기 × 분주비)
    multi = len(m.domains) > 1
    if multi:
        from pipeline.ir.pysim import schedule
        per = {n: round(1e6 / d["freq_mhz"]) if d.get("freq_mhz") else 10000 for n, d in m.domains.items()}
        per.update({n: per[m.clock_root(n)[0]] * m.clock_root(n)[1] for n in m.domains})
        n_rows = len(stim) if stim else a.cycles
        events = schedule(per, max(per.values()) * n_rows)[:n_rows]
    rows = []
    for c in range(len(stim) if stim else a.cycles):
        vals = {n: (stim[c].get(n, 0) if stim else rng.getrandbits(w)) for n, w in sim.inputs().items()}
        for rport, (act, main) in resets.items():
            if not stim or rport not in stim[c]:
                vals[rport] = act if main and c < 2 else 1 - act
        sim.set(vals)
        sim.settle()
        if multi:
            t_ps, rising = events[c]
            rows.append({"cycle": c, "t_ps": t_ps, "rising": sorted(rising), "in": vals, "out": sim.outputs()})
            sim.step(rising)
        else:
            rows.append({"cycle": c, "in": vals, "out": sim.outputs()})
            sim.step()
    return {"ok": True, "cycles": rows}


def cmd_porteq(a) -> dict:
    """원본 RTL과 IR에서 방출한 RTL을 같은 자극으로 돌려 출력을 사이클 단위로 비교한다 (P11 R4와 같은 판정, 시드 하나)."""
    from pipeline.importer import r4
    from pipeline.scheduler.run import STUB_CELLS

    try:
        raw = _load_ir(a.ir)
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "errors": [f"IR을 읽을 수 없음: {e}"]}
    ref = Path(a.ref).resolve()
    r1 = json.loads((ref / "ref.json").read_text(encoding="utf-8"))
    r1["units"] = [str(ref / u) for u in r1["units"]]
    r1["wrapped"] = [str(ref / u) for u in r1["wrapped"]]
    r1["headers"] = [str(ref / h) for h in r1["headers"]]
    lib = {n: json.loads(p.read_text(encoding="utf-8")) for n, p in
           ((p.name.removesuffix(".ir.json"), p) for p in sorted(Path(a.lib).glob("*.ir.json")))} if a.lib else {}
    lib[raw["module"]] = raw
    res = r4.run_module(raw["module"], lib, r1, Path(".porteq").resolve(), STUB_CELLS, seeds=(a.seed,), cycles=a.cycles)
    out = {"ok": res["status"] in ("equal", "reset_only"), "status": res["status"]}
    for k in ("first", "txn", "error", "mode", "seed"):
        if res.get(k) is not None:
            out[k] = res[k]
    if res["status"] == "differ":
        out["hint"] = ("first: 원본(ref)과 IR(ir)의 값이 처음 다른 도메인, 사이클(그 도메인 클럭 기준, 0부터), 포트. "
                       "mode=reset이면 중간에 리셋을 넣는 자극. 리셋 직후 차이는 in_window=true")
    return out


def cmd_spec_gate(a) -> dict:
    """SPEC 검사 게이트와, SPEC 2~4절에서 만든 L1이 tables.md의 L1과 같은지."""
    from pipeline.agents.spec_writer import gate
    from pipeline.spec.l1 import block_top_l1
    from pipeline.spec.parse import parse

    tables = Path(a.tables).read_text(encoding="utf-8")
    want, _ = block_top_l1(parse(f"# {a.top} SPEC\n\n" + tables))
    errs = gate(Path(a.spec), want)
    return {"ok": not errs, "errors": errs[:30]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="에이전트 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate"); p.add_argument("ir"); p.add_argument("--l1"); p.add_argument("--lib")
    p = sub.add_parser("patch"); p.add_argument("ir"); p.add_argument("patches"); p.add_argument("--lib")
    p = sub.add_parser("emit"); p.add_argument("ir"); p.add_argument("--lib")
    p = sub.add_parser("fanin"); p.add_argument("ir"); p.add_argument("signals", nargs="+")
    p = sub.add_parser("trace"); p.add_argument("trace"); p.add_argument("signals", nargs="+")
    p.add_argument("--from", dest="lo", type=int, default=0); p.add_argument("--to", dest="hi", type=int, default=10**9)
    p = sub.add_parser("spec"); p.add_argument("spec"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("harness"); p.add_argument("l1"); p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("model"); p.add_argument("model"); p.add_argument("l1")
    p.add_argument("--n", type=int, default=200); p.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("pysim"); p.add_argument("ir"); p.add_argument("--lib"); p.add_argument("--stim")
    p.add_argument("--cycles", type=int, default=20); p.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("porteq"); p.add_argument("ir"); p.add_argument("--lib"); p.add_argument("--ref", required=True)
    p.add_argument("--seed", type=int, default=1); p.add_argument("--cycles", type=int, default=800)
    p = sub.add_parser("spec_gate"); p.add_argument("spec"); p.add_argument("--tables", required=True); p.add_argument("--top", required=True)
    a = ap.parse_args(argv)
    res = globals()[f"cmd_{a.cmd}"](a)
    import os

    try:
        if os.environ.get("PL_NO_LOG"):  # 종료 게이트가 부를 때는 기록하지 않음 (에이전트의 도구 사용만 셈)
            raise OSError
        with (Path.cwd() / ".tools.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "cmd": a.cmd, "ok": res.get("ok", True)}) + "\n")
    except OSError:
        pass
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
