"""X1: coding agent가 스키마에 맞는 IR 파일을 내는 비율과 검사 도구를 쓰는 비율.

과제는 Author 에이전트의 실제 일과 같은 형태다. 작업 디렉터리에 동결된 L1, SPEC 요구사항,
스키마, 검사 도구를 두고 coding agent를 headless로 실행한다. agent는 out/pkt_parser.ir.json을
써야 한다. 기능의 정확성은 보지 않는다. 결과 파일, 스키마, 동결 범위, 도구 사용, 쓰기 범위만 본다.

trial마다 새 작업 디렉터리를 만들고, 검사가 실패하면 오류를 담은 새 TASK.md로
--retry 회까지 다시 실행한다(Classifier의 "스키마 위반 → 같은 에이전트 재시도").

사용 예
  python3 experiments/p0/x1_structured_output/run_x1.py \
      --agents experiments/p0/agents.json --trials 10
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.agent import AgentConfig, load_agents, run_agent, scope_violations, snapshot  # noqa: E402
from x1_structured_output.validate_ir import check_file  # noqa: E402

ROOT = HERE.parents[2]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "pkt_parser.ir.json").read_text(encoding="utf-8"))
FROZEN_L1 = {k: FIXTURE[k] for k in ("module", "role", "params", "domains", "ports")}
SCHEMA = json.loads((ROOT / "schema" / "ir.schema.json").read_text(encoding="utf-8"))
OUT_REL = "out/pkt_parser.ir.json"

SPEC = """\
## 5. 기능 요구사항
- FR-01 (필수) s_valid가 1이고 s_data가 SYNC_BYTE와 같으면, 다음 사이클부터 헤더 바이트를 기다린다.
- FR-02 (필수) 헤더 바이트는 sync 바이트 다음에 s_valid가 1인 첫 바이트이며, 값은 페이로드 길이 N이다. N의 허용 범위는 1~255이고 0은 미정의이다.
- FR-03 (필수) 페이로드 바이트 N개 중 마지막 바이트를 받은 다음 사이클에 pkt_valid를 1사이클 동안 1로 만든다.
- FR-04 (필수) s_ready는 항상 1이다.
- FR-05 (필수) 마지막 페이로드 바이트를 받으면 다시 sync 바이트를 기다린다.

## 9. 구현 제약
- 상태 머신은 fsm 블록으로 작성한다. 상태는 IDLE, HEADER, PAYLOAD이다.
"""

TASK = f"""\
# 과제: pkt_parser 모듈의 IR 작성

너는 RTL 생성 파이프라인의 Author 에이전트다.

## 입력
- `l1.json`: 동결된 L1 (module, role, params, domains, ports)
- `spec.md`: 이 모듈의 SPEC 요구사항
- `schema/ir.schema.json`: IR JSON Schema

## 할 일
1. L1을 한 글자도 바꾸지 않고 포함하고, L2(types, signals)와 L3(blocks)를 채운 모듈 IR 전체를 `{OUT_REL}`에 JSON으로 쓴다.
2. 다 쓰면 `python3 tools/validate_ir.py {OUT_REL}`로 검사한다. `"ok": true`가 나올 때까지 고친다.

## 규칙
- `{OUT_REL}` 외의 파일은 만들거나 고치지 않는다.
- comb와 seq 블록의 body는 SystemVerilog 조각이다. seq에는 non-blocking(<=)만, comb에는 blocking(=)만 쓴다.
- 클럭, 리셋, sensitivity list, 리셋 분기는 쓰지 않는다. Emitter가 만든다.
- fsm 블록의 상태 레지스터는 `<state_name>_q` 이름으로 다른 블록이 읽을 수 있다.
"""

RETRY = """
## 이전 시도의 검사 결과
`{out}`이 검사를 통과하지 못했다. 아래 오류를 고쳐라.

{errors}
"""


def prepare_workdir(work: Path) -> None:
    (work / "schema").mkdir(parents=True)
    (work / "tools").mkdir()
    (work / "out").mkdir()
    shutil.copy(ROOT / "schema" / "ir.schema.json", work / "schema" / "ir.schema.json")
    shutil.copy(HERE / "validate_ir.py", work / "tools" / "validate_ir.py")
    (work / "l1.json").write_text(json.dumps(FROZEN_L1, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "spec.md").write_text(SPEC, encoding="utf-8")


def run_trial(cfg: AgentConfig, work: Path, retry: int) -> dict:
    prepare_workdir(work)
    before = snapshot(work, exclude=("out/", "TASK.md"))
    task, attempts, duration, first, runs = TASK, 0, 0.0, None, []
    for attempts in range(1, retry + 2):
        run = run_agent(cfg, work, task)
        duration += run.duration_s
        runs.append({"returncode": run.returncode, "timed_out": run.timed_out,
                     "stdout_tail": run.stdout_tail[-1000:], "stderr_tail": run.stderr_tail[-1000:]})
        # 작업 디렉터리의 사본이 아니라 원본 스키마와 L1로 채점한다.
        res = check_file(work / OUT_REL, work, SCHEMA, FROZEN_L1)
        if first is None:
            first = {**res, "exit_ok": run.exit_ok}
        if res["ok"]:
            break
        task = TASK + RETRY.format(out=OUT_REL, errors="\n".join(f"- {e}" for e in res["errors"]))
    log = work / ".validate.log"
    validator_calls = len(log.read_text().splitlines()) if log.exists() else 0
    violations = scope_violations(before, snapshot(work, exclude=("out/", "TASK.md")))
    return {"first": first, "final": res, "attempts": attempts, "duration_s": duration,
            "exit_ok": all(r["returncode"] == 0 and not r["timed_out"] for r in runs),
            "out_exists": (work / OUT_REL).exists(), "validator_calls": validator_calls,
            "scope_violations": violations, "runs": runs}


def pct(xs: list[bool]) -> str:
    return f"{100 * sum(xs) / len(xs):.0f}%" if xs else "-"


def summarize(rows: list[dict]) -> str:
    out = ["| agent | 런타임 | 계열 | 시도 | 정상 종료 | 결과 파일 | 1회차 통과 | 재시도 포함 통과 | 동결 준수 | 검사 도구 사용 | 범위 밖 쓰기 없음 | 평균 시간(s) |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name in dict.fromkeys(r["agent"] for r in rows):
        m = [r for r in rows if r["agent"] == name]
        out.append(f"| {name} | {m[0]['runtime']} | {m[0]['family']} | {len(m)} | "
                   f"{pct([r['exit_ok'] for r in m])} | {pct([r['out_exists'] for r in m])} | "
                   f"{pct([r['first']['ok'] for r in m])} | {pct([r['final']['ok'] for r in m])} | "
                   f"{pct([r['final']['l1_frozen'] for r in m])} | {pct([r['validator_calls'] > 0 for r in m])} | "
                   f"{pct([not r['scope_violations'] for r in m])} | "
                   f"{statistics.mean(r['duration_s'] for r in m):.0f} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", required=True, help="agent 설정 JSON (agents.example.json 참고)")
    ap.add_argument("--only", help="쉼표로 구분한 agent name만 실행")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--retry", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "experiments" / "p0" / "results"))
    args = ap.parse_args(argv)

    agents = load_agents(args.agents)
    if args.only:
        keep = set(args.only.split(","))
        agents = [a for a in agents if a.name in keep]

    out_dir = Path(args.out) / f"x1-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with (out_dir / "trials.jsonl").open("w", encoding="utf-8") as f:
        for cfg in agents:
            for i in range(args.trials):
                work = out_dir / "work" / cfg.name / f"{i:03d}"
                row = {"agent": cfg.name, "runtime": cfg.runtime, "family": cfg.family, "trial": i,
                       "workdir": str(work), **run_trial(cfg, work, args.retry)}
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                print(f"[{cfg.name}] {i + 1}/{args.trials} {'PASS' if row['final']['ok'] else 'FAIL'}", file=sys.stderr)

    summary = f"# X1 결과 ({time.strftime('%Y-%m-%d %H:%M')})\n\n" + summarize(rows)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"결과: {out_dir} (trial별 작업 디렉터리는 work/ 아래에 남음)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
