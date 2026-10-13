"""번역기 검사: `lang: py` 모듈의 설계 모델(`pysim`)과 방출한 RTL을 같은 무작위 자극으로 비교한다.

이 검사가 보는 것은 Python 조각 → SV 번역(과 실행기)이 같은 의미인지다. SPEC 해석이 맞는지는 보지 않는다
(그것은 Verifier 테스트와 DV Pod의 독립 TB가 본다). 그래서 불일치는 Repair로 보내지 않고 생성기 버그로 기록한다.

    python3 -m pipeline.verify.pyequiv <ir.json...> --top <모듈> -o <build_dir> [--cells <셀.sv>...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.ir.model import Module
from pipeline.ir.pysim import supported
from pipeline.verify.run import sim

TB_DIR = Path(__file__).resolve().parent
CYCLES = 2000
RESET_CYCLES = 3
RESET_PROB = 0.01


def check(top: str, library: dict[str, Module], files: list[Path], build_dir: Path, cycles: int = CYCLES,
          seed: int = 1) -> dict:
    """{"ok", "skipped"?, "mismatch"?, "error"?}. 실행기가 모르는 구성이면 건너뛴다 (skipped에 이유)."""
    if (why := supported(library[top], library)) is not None:
        return {"ok": True, "skipped": why}
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    out = build_dir / "pyequiv_result.json"
    out.unlink(missing_ok=True)
    cfg = build_dir / "pyequiv.json"
    cfg.write_text(json.dumps({"top": top, "library": {n: m.source_raw for n, m in library.items()}, "cycles": cycles,
                               "seed": seed, "reset_cycles": RESET_CYCLES, "reset_prob": RESET_PROB, "out": str(out.resolve())},
                              ensure_ascii=False), encoding="utf-8")
    r = sim([Path(f) for f in files], top, "pyequiv_tb", TB_DIR, build_dir, env={"PYEQUIV_CFG": str(cfg.resolve())})
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    return {"ok": False, "error": "; ".join(f.message[:300] for f in r.findings) or "결과 파일이 없음"}


def main(argv: list[str] | None = None) -> int:
    from pipeline.emitter.sv import emit
    from pipeline.ir.model import load_library

    ap = argparse.ArgumentParser(description="번역기 검사 (설계 모델 대 RTL)")
    ap.add_argument("ir", nargs="+")
    ap.add_argument("--top", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--cells", nargs="*", default=[])
    ap.add_argument("--cycles", type=int, default=CYCLES)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    lib = load_library(a.ir)
    out = Path(a.out)
    (out / "rtl").mkdir(parents=True, exist_ok=True)
    files = [Path(c) for c in a.cells]
    for n, m in lib.items():
        (out / "rtl" / f"{n}.sv").write_text(emit(m, lib).text, encoding="utf-8")
        files.append(out / "rtl" / f"{n}.sv")
    res = check(a.top, lib, files, out, a.cycles, a.seed)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
