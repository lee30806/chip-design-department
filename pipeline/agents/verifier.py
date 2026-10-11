"""Verifier 에이전트: SPEC과 동결된 L1만 보고 참조 모델, 속성, 시나리오를 쓴다.

볼 수 있는 것: SPEC, 동결된 L1, L1에서 생성한 하니스, 테스트벤치 안내서. L2, L3, RTL은 입력에 없다 (격리).
쓸 수 있는 것: `out/test_<module>.py` 하나 (cocotb 테스트 모듈, `Model` 클래스 포함).
종료 게이트: 파이썬 문법, `Model.on_input`이 무작위 입력에서 예외 없이 돌 것, cocotb 테스트가 둘 이상일 것.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from pipeline.agents.task import ROOT, Task
from pipeline.ir.model import Module
from pipeline.tb.gen import harness_source

GUIDE = ROOT / "pipeline" / "agents" / "prompts" / "tb_guide.md"

TASK = """\
# 과제: {module} 모듈의 참조 모델과 테스트 작성

너는 RTL 생성 파이프라인의 Verifier 에이전트다. RTL은 볼 수 없다. SPEC과 인터페이스(L1)만 보고, RTL이 SPEC을
지키는지 판정할 참조 모델과 테스트를 쓴다.

## 입력
- `spec.md`: SPEC. 5~7번 섹션의 요구사항, 8번 섹션의 예시 시나리오
- `l1.json`: 동결된 L1 (포트, 번들, 도메인, 파라미터)
- `harness/{module}_harness.py`: L1에서 생성한 하니스 (읽기만)
- `tb_guide.md`: 테스트벤치 작성 안내. 먼저 읽는다

## 할 일
1. `tb_guide.md`를 읽는다.
2. `{out}`에 cocotb 테스트 모듈을 쓴다. `Model` 클래스(참조 모델)와 `@cocotb.test()` 테스트 함수를 둘 이상 둔다.
   하니스는 `from {module}_harness import make`로 가져온다.
3. SPEC의 요구사항 ID를 기대 출력, 속성, `cover_protocol` 중 하나 이상으로 모두 실행한다. 8번 섹션의 시나리오는 directed 테스트로 쓴다.
4. `python3 tools/pl.py model {out} l1.json`이 `"ok": true`가 될 때까지 고친다.

## 규칙
- `{out}` 외의 파일은 만들거나 고치지 않는다.
- SPEC이 정하지 않은 동작(미정의)은 검사하지 않는다.
"""


def out_rel(module: str) -> str:
    return f"out/test_{module}.py"


def make_task(name: str, l1: dict, spec: str | Path) -> Task:
    module = l1["module"]
    inputs = {"spec.md": Path(spec), "l1.json": json.dumps(l1, ensure_ascii=False, indent=1), "tb_guide.md": GUIDE,
              f"harness/{module}_harness.py": harness_source(Module(l1))}
    return Task("verifier", name, TASK.format(module=module, out=out_rel(module)), inputs=inputs,
                outputs=[out_rel(module)], write_scope=["out/"])


def check(l1: dict):
    module = l1["module"]

    def _check(work: Path) -> list[str]:
        src = (work / out_rel(module)).read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            return [f"문법 오류: {e}"]
        tests = [f.name for f in ast.walk(tree) if isinstance(f, ast.AsyncFunctionDef)
                 and any("cocotb.test" in ast.unparse(d) for d in f.decorator_list)]
        errs = [] if len(tests) >= 2 else [f"cocotb 테스트가 둘 이상 있어야 함 (지금 {len(tests)}개)"]
        if not any(isinstance(n, ast.ClassDef) and n.name == "Model" for n in ast.walk(tree)):
            errs.append("Model 클래스가 없음")
            return errs
        # 하니스 import는 모델 단독 실행에서 필요 없으므로, 하니스 디렉터리를 경로에 넣고 실행한다
        p = subprocess.run([sys.executable, str(ROOT / "pipeline" / "agents" / "pl.py"), "model", str(work / out_rel(module)),
                            str(work / "l1.json")], capture_output=True, text=True, cwd=work / "harness",
                           env={"PYTHONPATH": str(work / "harness"), "PATH": "/usr/bin:/bin", "PL_NO_LOG": "1"}, timeout=120)
        try:
            res = json.loads(p.stdout)
        except json.JSONDecodeError:
            return errs + [f"모델 단독 실행 실패: {(p.stderr or p.stdout)[-500:]}"]
        if not res.get("ok"):
            errs.append(f"모델 단독 실행에서 예외: {res.get('error')}")
        return errs
    return _check
