"""모듈 IR 검사 CLI. X1 작업 디렉터리에 tools/validate_ir.py로 복사되어 agent가 직접 실행한다.

    python3 tools/validate_ir.py out/pkt_parser.ir.json

작업 디렉터리의 schema/ir.schema.json과 l1.json(동결된 L1)을 기준으로 검사하고,
결과를 JSON으로 출력한다. 호출 기록은 .validate.log에 남는다(도구 사용 여부 측정용).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from jsonschema import Draft202012Validator

FROZEN_KEYS = ("module", "role", "params", "domains", "ports")


def check_ir(ir: object, schema: dict, frozen_l1: dict) -> dict:
    if not isinstance(ir, dict):
        return {"ok": False, "schema_ok": False, "l1_frozen": False, "errors": ["최상위가 JSON 객체가 아님"]}
    v = Draft202012Validator(schema)
    schema_errors = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message[:200]}"
                     for e in sorted(v.iter_errors(ir), key=lambda e: list(map(str, e.absolute_path)))]
    changed = [k for k in FROZEN_KEYS if ir.get(k) != frozen_l1.get(k)]
    errors = schema_errors + [f"동결 범위 변경: {k}" for k in changed]
    return {"ok": not errors, "schema_ok": not schema_errors, "l1_frozen": not changed, "errors": errors[:10]}


def check_file(path: Path, root: Path, schema: dict | None = None, frozen: dict | None = None) -> dict:
    """schema와 frozen을 주지 않으면 root의 사본을 쓴다. 채점은 agent가 고칠 수 없는 원본을 넘겨야 한다."""
    if schema is None:
        schema = json.loads((root / "schema" / "ir.schema.json").read_text(encoding="utf-8"))
    if frozen is None:
        frozen = json.loads((root / "l1.json").read_text(encoding="utf-8"))
    if not path.exists():
        return {"ok": False, "schema_ok": False, "l1_frozen": False, "errors": [f"파일 없음: {path}"]}
    try:
        ir = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"ok": False, "schema_ok": False, "l1_frozen": False, "errors": [f"JSON 파싱 실패: {e}"]}
    return check_ir(ir, schema, frozen)


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
