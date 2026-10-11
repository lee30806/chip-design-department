"""Architect 에이전트: SPEC과 Block Top L1을 받아 모듈 트리를 정하고 인터페이스를 동결한다.

볼 수 있는 것: SPEC, SPEC 표에서 만든 Block Top의 L1, IR 안내서.
쓸 수 있는 것: `out/ir/<모듈>.ir.json`(Block Top은 L1 + instances + connections, 하위 모듈은 L1만), `out/assumptions.json`.
종료 게이트: Block Top의 L1이 바뀌지 않음, Block Top이 V1~V10 통과(하위 모듈 L1을 라이브러리로), 하위 모듈 L1이 V1~V3 통과,
             가정 목록이 있음.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.agents.task import ROOT, Task
from pipeline.ir.model import Module, frozen_l1
from pipeline.validator.checks import errors, validate

GUIDE = ROOT / "pipeline" / "agents" / "prompts" / "ir_guide.md"
EXAMPLE_TOP = ROOT / "tests" / "fixtures" / "pkt_rx_top.ir.json"
EXAMPLE_MOD = ROOT / "tests" / "fixtures" / "pkt_parser.ir.json"

TASK = """\
# 과제: {top} Block Top의 모듈 트리와 인터페이스 정하기

너는 RTL 생성 파이프라인의 Architect 에이전트다. SPEC을 하위 모듈로 나누고 각 모듈의 인터페이스(L1)를 정한다.
동작(L2, L3)은 쓰지 않는다. 그건 Author가 모듈마다 쓴다.

## 입력
- `spec.md`: 고정된 SPEC
- `block_top.json`: SPEC 2~4번 섹션 표에서 만든 Block Top의 L1 (바꾸지 않는다)
- `guide.md`: IR 작성 안내 (role, 번들, 도메인, 연결 규칙)
- `examples/`: Block Top(`pkt_rx_top`)과 하위 모듈(`pkt_parser`) IR 예시

## 할 일
1. 모듈 트리를 정한다. Block Top(role `block_top`)은 동작 블록을 가질 수 없고(동기화 셀 `cdc_sync`만 가능), 인스턴스와 연결만 가진다.
   그래서 동작은 모두 하위 모듈(role `module`)에 둔다. 모듈은 Author가 하나씩 따로 쓰므로 너무 크지도 잘게 쪼개지도 않게 나눈다.
2. 하위 모듈마다 L1(module, role, params, domains, ports)만 있는 IR을 `out/ir/<모듈>.ir.json`에 쓴다.
3. Block Top IR을 `out/ir/{top}.ir.json`에 쓴다. `block_top.json`의 L1을 그대로 두고 `instances`(파라미터 바인딩, domain_map)와
   `connections`를 더한다. 번들은 프로토콜이 같으면 번들 이름으로 한 번에 잇는다 (예: `self.s_axis` → `u_core.s_axis`).
4. SPEC에서 정하지 않아 네가 정한 것(모듈 경계, 하위 모듈 사이 프로토콜, 지연 배분 등)을 `out/assumptions.json`에
   `{{"assumptions": ["...", ...]}}`로 쓴다.
5. `python3 tools/pl.py validate out/ir/{top}.ir.json --lib out/ir`가 `"ok": true`가 될 때까지 고친다.
   하위 모듈은 아직 동작이 없으므로 `validate`로 검사하지 않는다.

## 규칙
- `out/` 밖의 파일은 만들거나 고치지 않는다.
- 클럭과 리셋은 `domain_map`으로만 연결한다.
"""


def make_task(name: str, block_top_l1: dict, spec: str | Path) -> Task:
    inputs = {"spec.md": Path(spec), "block_top.json": json.dumps(block_top_l1, ensure_ascii=False, indent=1),
              "guide.md": GUIDE, "examples/pkt_rx_top.ir.json": EXAMPLE_TOP, "examples/pkt_parser.ir.json": EXAMPLE_MOD}
    top = block_top_l1["module"]
    return Task("architect", name, TASK.format(top=top), inputs=inputs,
                outputs=[f"out/ir/{top}.ir.json", "out/assumptions.json"], write_scope=["out/"])


def read_tree(work: Path, top: str) -> tuple[dict, dict[str, dict], list[str]]:
    """(Block Top IR, 하위 모듈 L1, 가정 목록)."""
    irs = {}
    for p in sorted((work / "out" / "ir").glob("*.ir.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        irs[raw.get("module", p.stem.removesuffix(".ir"))] = raw
    assumptions = json.loads((work / "out" / "assumptions.json").read_text(encoding="utf-8")).get("assumptions", [])
    top_ir = irs.pop(top)
    return top_ir, irs, assumptions


def check(block_top_l1: dict):
    top = block_top_l1["module"]

    def _check(work: Path) -> list[str]:
        try:
            top_ir, children, assumptions = read_tree(work, top)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            return [f"결과를 읽을 수 없음: {e}"]
        errs = []
        if top_ir.get("role") != "block_top":
            errs.append(f"{top}의 role이 block_top이 아님")
        mine, frozen = frozen_l1(top_ir), frozen_l1(block_top_l1)
        errs += [f"[동결] {top}.{k}: Block Top L1과 다름" for k in frozen if mine.get(k) != frozen.get(k)]
        lib = {n: Module(c) for n, c in children.items()}
        for n, c in children.items():
            if c.get("role") not in ("module", "external"):
                errs.append(f"{n}: 하위 모듈의 role은 module 또는 external")
            errs += [f"{n}: {i}" for i in errors(validate(Module(c), lib, upto=3))]
        errs += [f"{top}: {i}" for i in errors(validate(Module(top_ir), lib))]
        used = {i["module"] for i in top_ir.get("instances", [])}
        errs += [f"쓰이지 않는 하위 모듈: {n}" for n in children if n not in used]
        if not assumptions:
            errs.append("가정 목록이 비어 있음 (SPEC이 정하지 않아 정한 것을 적음)")
        return errs
    return _check
