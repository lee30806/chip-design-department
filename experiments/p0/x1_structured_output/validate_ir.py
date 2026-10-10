"""모듈 IR 검사 CLI. X1 작업 디렉터리에 tools/validate_ir.py로 복사되어 agent가 직접 실행한다.

    python3 tools/validate_ir.py out/pkt_parser.ir.json

파이프라인의 실제 Validator(V1~V10)로 검사하고, 동결된 L1(l1.json)이 바뀌었는지도 본다.
작업 디렉터리에서는 tools/pipeline에 복사된 Validator를 쓰고, 저장소에서는 저장소의 pipeline을 쓴다.
결과는 JSON으로 출력하고, 호출 기록은 .validate.log에 남긴다(도구 사용 여부 측정용).
pyslang과 jsonschema가 필요하다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # 작업 디렉터리에 __pycache__를 남기지 않는다
HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[2] if len(HERE.parents) > 2 else HERE):
    if (p / "pipeline" / "validator").is_dir():
        sys.path.insert(0, str(p))
        break

from pipeline.ir.model import Module  # noqa: E402
from pipeline.validator.checks import errors, validate  # noqa: E402

FROZEN_KEYS = ("module", "role", "params", "domains", "ports")


def check_ir(ir: object, frozen_l1: dict, library: dict | None = None) -> dict:
    if not isinstance(ir, dict):
        return {"ok": False, "valid": False, "l1_frozen": False, "errors": ["최상위가 JSON 객체가 아님"], "warnings": []}
    try:
        issues = validate(Module(ir), library or {})
    except Exception as e:  # Validator 자체가 처리하지 못한 형태
        issues_err, warns = [f"검사 중 예외: {type(e).__name__}: {e}"], []
    else:
        issues_err = [str(i) for i in errors(issues)]
        warns = [str(i) for i in issues if i.severity != "error"]
    changed = [k for k in FROZEN_KEYS if ir.get(k) != frozen_l1.get(k)]
    errs = issues_err + [f"[동결] {k}: 동결된 L1과 다름" for k in changed]
    return {"ok": not errs, "valid": not issues_err, "l1_frozen": not changed, "errors": errs[:10], "warnings": warns[:10]}


def check_file(path: Path, root: Path, frozen: dict | None = None) -> dict:
    """frozen을 주지 않으면 root의 l1.json을 쓴다. 채점은 agent가 고칠 수 없는 원본을 넘겨야 한다."""
    if frozen is None:
        frozen = json.loads((root / "l1.json").read_text(encoding="utf-8"))
    if not path.exists():
        return {"ok": False, "valid": False, "l1_frozen": False, "errors": [f"파일 없음: {path}"], "warnings": []}
    try:
        ir = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"ok": False, "valid": False, "l1_frozen": False, "errors": [f"JSON 파싱 실패: {e}"], "warnings": []}
    return check_ir(ir, frozen)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 tools/validate_ir.py <ir.json>", file=sys.stderr)
        return 2
    root = Path.cwd()
    result = check_file(Path(sys.argv[1]), root)
    with (root / ".validate.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "ok": result["ok"]}) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
