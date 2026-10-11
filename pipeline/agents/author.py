"""Author 에이전트: 동결된 L1과 SPEC 해당 부분을 받아 자기 모듈의 L2, L3를 쓴다.

볼 수 있는 것: SPEC, 동결된 L1, (자식 모듈이 있으면) 자식의 L1, IR 안내서와 일반 예시. 다른 후보의 산출물은 보지 못한다.
쓸 수 있는 것: `out/<module>.ir.json` 하나.
종료 게이트: Validator V1~V10 통과와 동결 L1 일치. 실패하면 오류를 붙여 재시도한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.agents.task import ROOT, Task
from pipeline.ir.model import Module, frozen_l1
from pipeline.validator.checks import errors, validate

GUIDE = ROOT / "pipeline" / "agents" / "prompts" / "ir_guide.md"
EXAMPLES = [ROOT / "tests" / "fixtures" / "pkt_parser.ir.json", ROOT / "tests" / "fixtures" / "pkt_rx_top.ir.json"]

TASK = """\
# 과제: {module} 모듈의 IR 작성

너는 RTL 생성 파이프라인의 Author 에이전트다. 동결된 L1을 받아 이 모듈의 동작(L2, L3)을 IR로 쓴다.

## 입력
- `l1.json`: 동결된 L1 (module, role, params, domains, ports){children}
- `spec.md`: SPEC. 이 모듈의 동작은 5~7번 섹션의 요구사항을 따른다. 9번 섹션의 구현 제약도 지킨다
- `guide.md`: IR 작성 안내. 먼저 읽는다
- `examples/`: 다른 모듈의 IR 예시 (형식 참고용)

## 할 일
1. `guide.md`를 읽는다.
2. L1을 그대로 포함하고 L2(types, signals, 출력 포트의 kind/reset)와 L3(blocks)를 채운 IR 전체를 `{out}`에 JSON으로 쓴다.
3. `python3 tools/pl.py validate {out} --l1 l1.json{lib_arg}`가 `"ok": true`가 될 때까지 고친다.

## 규칙
- `{out}` 외의 파일은 만들거나 고치지 않는다.
- SPEC에 없는 동작을 지어내지 않는다. SPEC이 정하지 않은 세부는 단순한 쪽을 고른다.
"""


def out_rel(module: str) -> str:
    return f"out/{module}.ir.json"


def make_task(name: str, l1: dict, spec: str | Path, children: dict[str, dict] | None = None) -> Task:
    module = l1["module"]
    inputs: dict = {"l1.json": json.dumps(l1, ensure_ascii=False, indent=1), "spec.md": Path(spec),
                    "guide.md": GUIDE}
    for e in EXAMPLES:
        inputs[f"examples/{e.name}"] = e
    for cname, cl1 in (children or {}).items():
        inputs[f"lib/{cname}.ir.json"] = json.dumps(cl1, ensure_ascii=False, indent=1)
    text = TASK.format(module=module, out=out_rel(module),
                       children="\n- `lib/`: 인스턴스로 쓰는 자식 모듈의 L1" if children else "",
                       lib_arg=" --lib lib" if children else "")
    return Task("author", name, text, inputs=inputs, outputs=[out_rel(module)], write_scope=["out/"])


def check(l1: dict, children: dict[str, dict] | None = None):
    """종료 게이트: 저장소의 Validator(작업 디렉터리의 사본이 아님)와 원본 L1로 판정한다."""
    def _check(work: Path) -> list[str]:
        try:
            raw = json.loads((work / out_rel(l1["module"])).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return [f"IR을 읽을 수 없음: {e}"]
        lib = {n: Module(c) for n, c in (children or {}).items()}
        errs = [str(i) for i in errors(validate(Module(raw), lib))]
        mine, frozen = frozen_l1(raw), frozen_l1(l1)
        errs += [f"[동결] {k}: 동결된 L1과 다름" for k in frozen if mine.get(k) != frozen.get(k)]
        return errs
    return _check
