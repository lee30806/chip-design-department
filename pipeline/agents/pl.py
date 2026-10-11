"""에이전트용 도구 CLI. 작업 디렉터리의 `tools/pl.py`로 놓이고, 같은 디렉터리의 파이프라인 사본을 쓴다.

    python3 tools/pl.py validate <ir.json> [--l1 l1.json] [--lib <IR 디렉터리>]   # Validator 사전 실행 (+ 동결 L1 대조)
    python3 tools/pl.py patch <ir.json> <patches.json> [--lib <dir>]             # patch 사전 실행 (적용하지 않고 검사만)
    python3 tools/pl.py emit <ir.json> [--lib <dir>]                             # 방출될 SV 보기
    python3 tools/pl.py fanin <ir.json> <신호...>                                # 출력의 팬인 노드와 신호
    python3 tools/pl.py trace <trace.json> <신호...> [--from N --to M]           # 시뮬레이션 트레이스 값 조회
    python3 tools/pl.py spec <spec.md> <요구사항 ID...>                          # SPEC 구절 조회
    python3 tools/pl.py harness <l1.json> -o <dir>                               # L1에서 cocotb 하니스 생성
    python3 tools/pl.py model <model.py> <l1.json> [--n 200]                     # 참조 모델 단독 실행 (무작위 입력)

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
