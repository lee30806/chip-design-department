"""Arbiter 에이전트: RTL과 참조 모델(테스트)이 다를 때 어느 쪽이 SPEC과 맞는지 판정한다.

볼 수 있는 것: SPEC, 불일치 리포트(첫 불일치의 기댓값과 실제값, 트레이스, 관련 SPEC 구절), 테스트 파일(모델과 시나리오).
RTL과 IR은 보지 않는다 (판정 기준은 SPEC).
쓸 수 있는 것: `out/verdict.json`.
판정: rtl_wrong(RTL을 Repair로), test_wrong(기댓값 수정안, 사람 승인 필요), spec_ambiguous(검토 항목, 작성자에게 질문).
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.agents.task import Task
from pipeline.spec.parse import load

VERDICTS = {"rtl_wrong", "test_wrong", "spec_ambiguous"}
OUT = "out/verdict.json"

TASK = """\
# 과제: 불일치 판정

너는 RTL 생성 파이프라인의 Arbiter 에이전트다. 시뮬레이션에서 RTL의 출력과 참조 모델의 기댓값이 달랐다.
SPEC을 근거로 어느 쪽이 맞는지 판정한다. RTL 코드는 볼 수 없다. 판정 기준은 SPEC뿐이다.

## 입력
- `spec.md`: SPEC
- `mismatch.json`: 불일치 리포트. `first_failure`의 expected는 참조 모델의 기댓값, got은 RTL의 실제값이다.
  `fsm_trace`, `fanin.values`는 그 시점 전후의 내부 값, `spec.clauses`는 관련 요구사항이다
- `test.py`: 참조 모델과 테스트 시나리오 (기댓값이 어떻게 만들어졌는지)

## 할 일
SPEC 구절을 근거로 판정하고 `{out}`에 아래 JSON을 쓴다.

{{"verdict": "rtl_wrong | test_wrong | spec_ambiguous", "reqs": ["근거 요구사항 ID"], "reason": "SPEC 문장을 인용한 판정 이유",
  "proposal": "test_wrong이면 참조 모델이나 기댓값을 어떻게 고칠지, spec_ambiguous이면 작성자에게 물을 질문"}}

- rtl_wrong: SPEC대로면 기댓값이 맞고 RTL이 틀림
- test_wrong: SPEC대로면 RTL이 맞고 기댓값(참조 모델이나 시나리오)이 틀림. 수정은 사람이 승인한 뒤에 적용된다
- spec_ambiguous: SPEC이 이 경우를 정하지 않았거나 두 해석이 모두 가능함

## 규칙
- `{out}` 외의 파일은 만들거나 고치지 않는다.
"""


def make_task(name: str, spec: str | Path, mismatch: dict, test_file: Path) -> Task:
    inputs = {"spec.md": Path(spec), "mismatch.json": json.dumps(mismatch, ensure_ascii=False, indent=1), "test.py": test_file}
    return Task("arbiter", name, TASK.format(out=OUT), inputs=inputs, tools=False, outputs=[OUT])


def check(spec: str | Path):
    known = {r.id for r in load(spec).requirements}

    def _check(work: Path) -> list[str]:
        try:
            v = json.loads((work / OUT).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return [f"판정을 읽을 수 없음: {e}"]
        errs = []
        if v.get("verdict") not in VERDICTS:
            errs.append(f"verdict는 {sorted(VERDICTS)} 중 하나여야 함")
        reqs = v.get("reqs") or []
        if not reqs:
            errs.append("근거 요구사항(reqs)이 없음")
        errs += [f"SPEC에 없는 요구사항: {r}" for r in reqs if r not in known]
        if not str(v.get("reason", "")).strip():
            errs.append("판정 이유(reason)가 없음")
        if v.get("verdict") in ("test_wrong", "spec_ambiguous") and not str(v.get("proposal", "")).strip():
            errs.append("test_wrong과 spec_ambiguous는 수정안이나 질문(proposal)이 필요함")
        return errs
    return _check
