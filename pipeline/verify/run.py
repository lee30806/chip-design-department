"""Verify: E1 Verilator lint, E2 Verilator sim(cocotb). 결과는 단계와 관계없이 같은 형식으로 낸다.

결과 한 건은 (툴, 규칙, 파일, 줄, 메시지)다. E3(VC SpyGlass)은 사내 실행 템플릿과 리포트 형식이 정해지면
같은 형식으로 추가한다. 파이프라인 밖 툴의 리포트도 이 형식으로 바꿔 Classifier에 넣는다.

    python3 -m pipeline.verify.run lint --top pkt_parser out/*.sv
    python3 -m pipeline.verify.run sim  --top pkt_parser --tests tb_pkt_parser --test-dir tests/sim out/*.sv
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

LINT_ARGS = ["-Wall"]
_VLT = re.compile(r"^%(Warning|Error)(?:-([A-Z0-9_]+))?: (?:(\S+?):(\d+):(?:\d+:)?\s*)?(.*)$")


@dataclass(frozen=True)
class Finding:
    tool: str
    rule: str
    file: str | None
    line: int | None
    message: str
    severity: str = "error"  # error | warning
    test: str | None = None  # sim 결과만: 테스트 이름


@dataclass
class StageResult:
    stage: str               # E1 | E2 | E3
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    log: str = ""            # 툴 출력 (잘라서 보관)

    def to_dict(self) -> dict:
        return {"stage": self.stage, "ok": self.ok, "findings": [asdict(f) for f in self.findings], "log": self.log}


def parse_verilator(text: str, tool: str = "verilator") -> list[Finding]:
    out = []
    for ln in text.splitlines():
        mo = _VLT.match(ln)
        if not mo:
            continue
        kind, rule, file, line, msg = mo.groups()
        if kind == "Error" and not rule and not file and msg.startswith("Exiting due to"):
            continue  # 요약 줄
        out.append(Finding(tool, rule or ("ERROR" if kind == "Error" else "WARNING"), file,
                           int(line) if line else None, msg.strip(), "error" if kind == "Error" else "warning"))
    return out


def lint(files: list[Path], top: str, extra_args: list[str] | None = None) -> StageResult:
    """E1. -Wall 경고도 실패로 본다 (waiver는 쓰지 않는다)."""
    cmd = ["verilator", "--lint-only", *LINT_ARGS, *(extra_args or []), "--top-module", top, *map(str, files)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    findings = parse_verilator(p.stderr + p.stdout)
    if p.returncode != 0 and not findings:
        findings = [Finding("verilator", "TOOL", None, None, (p.stderr or p.stdout).strip()[-2000:])]
    return StageResult("E1", p.returncode == 0 and not findings, findings, (p.stderr + p.stdout)[-20000:])


def parse_cocotb_results(path: Path) -> tuple[int, list[Finding]]:
    """cocotb results.xml → (테스트 수, 실패). 규칙은 예외 타입이다 (AssertionError는 기댓값 불일치)."""
    out, total = [], 0
    for tc in ET.parse(path).getroot().iter("testcase"):
        total += 1
        bad = tc.find("failure")
        if bad is None:
            bad = tc.find("error")
        if bad is None:
            continue
        props = {p.get("name"): p.get("value") for p in tc.iter("property")}
        line = props.get("line")
        out.append(Finding("cocotb", bad.get("type") or "Error", props.get("file"), int(line) if line else None,
                           (bad.get("message") or "").strip(), test=tc.get("name")))
    return total, out


REPO = Path(__file__).resolve().parents[2]
# T1: Verilator는 2-state라 X를 볼 수 없다. 초기값을 시드별로 무작위화해 결과가 달라지는지 본다.
RANDOM_INIT_BUILD = ["-x-assign", "unique", "-x-initial", "unique"]


def sim(files: list[Path], top: str, test_module: str, test_dir: Path, build_dir: Path,
        build_args: list[str] | None = None, seed: int | None = None, seeds: list[int] | None = None,
        harness_dir: Path | None = None, trace: Path | None = None, env: dict[str, str] | None = None,
        timescale: tuple[str, str] | None = None) -> StageResult:
    """E2. cocotb + Verilator. 빌드 실패도 이 단계의 실패로 낸다.

    seeds를 주면 초기값을 무작위화해 시드마다 실행하고(T1, Verilator 시드만 바꾸고 Python random 시드는 seed로 고정), 시드에 따라 실패하는 테스트가 달라지면
    그 자체를 실패(`T1_INIT`)로 낸다. harness_dir는 생성된 하니스가 있는 디렉터리, trace는 내부 신호 목록
    (`<module>_trace.json`)이다. 하니스 결과(첫 불일치, 트레이스)는 `build_dir/tb_out/<시드>/`에 남는다.
    """
    from cocotb_tools.runner import get_runner

    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    build_log = build_dir / "build.log"
    runner = get_runner("verilator")
    try:
        runner.build(sources=[Path(f) for f in files], hdl_toplevel=top, build_dir=build_dir,
                     build_args=[*(build_args or []), *(RANDOM_INIT_BUILD if seeds else [])], always=True,
                     log_file=build_log, timescale=timescale)
    except (Exception, SystemExit):
        text = build_log.read_text(errors="replace") if build_log.exists() else ""
        findings = parse_verilator(text) or [Finding("verilator", "BUILD", None, None, text.strip()[-2000:])]
        return StageResult("E2", False, findings, text[-20000:])
    paths = [str(REPO)] + ([str(Path(harness_dir).resolve())] if harness_dir else [])
    per_seed: dict[int | None, list[Finding]] = {}
    logs = []
    for s in (seeds or [seed]):
        tag = "default" if s is None else str(s)
        results, test_log = build_dir / f"results.{tag}.xml", build_dir / f"test.{tag}.log"
        results.unlink(missing_ok=True)
        env = {**(env or {}), "TB_OUT": str((build_dir / "tb_out" / tag).resolve())}
        if trace:
            env["TB_TRACE"] = str(Path(trace).resolve())
        plus = [f"+verilator+seed+{s}", "+verilator+rand+reset+2"] if seeds else []
        saved = list(sys.path)
        sys.path[:0] = paths  # runner는 PYTHONPATH를 이 프로세스의 sys.path로 정한다
        try:
            # 자극이 시드에 따라 바뀌지 않도록 cocotb(Python random) 시드는 고정한다.
            runner.test(hdl_toplevel=top, test_module=test_module, test_dir=Path(test_dir), build_dir=build_dir,
                        results_xml=str(results), seed=(seed if seed is not None else 1) if seeds else s,
                        log_file=test_log, extra_env=env, plusargs=plus, timescale=timescale)
        except (Exception, SystemExit):
            pass  # 테스트가 실패하면 runner가 예외를 던진다. 판정은 결과 파일로 한다.
        finally:
            sys.path[:] = saved
        logs.append(test_log.read_text(errors="replace")[-20000:] if test_log.exists() else "")
        if not results.exists():
            per_seed[s] = [Finding("cocotb", "NO_RESULTS", None, None, f"결과 파일이 없음 (시뮬레이터 비정상 종료, seed {tag})")]
            continue
        total, findings = parse_cocotb_results(results)
        if total == 0:
            findings = [Finding("cocotb", "NO_TESTS", None, None, f"{test_module}에서 실행된 테스트가 없음")]
        per_seed[s] = findings
    findings = list(dict.fromkeys(f for fs in per_seed.values() for f in fs))
    failed_sets = {frozenset(f.test for f in fs) for fs in per_seed.values()}
    if len(failed_sets) > 1:
        detail = ", ".join(f"seed {s}: {sorted(f.test for f in fs) or '통과'}" for s, fs in per_seed.items())
        findings.insert(0, Finding("cocotb", "T1_INIT", None, None, f"초기값에 따라 결과가 달라짐 ({detail})"))
    elif seeds and trace and len(seeds) > 1:
        diff = _compare_outputs(build_dir / "tb_out", [str(s) for s in seeds], json.loads(Path(trace).read_text())["outputs"])
        if diff:
            findings.insert(0, Finding("cocotb", "T1_INIT", None, None, f"초기값에 따라 출력이 달라짐 ({diff})", test=diff.split(":")[0]))
    return StageResult("E2", not findings, findings, "\n".join(logs)[-20000:])


def _compare_outputs(tb_out: Path, tags: list[str], outputs: list[str]) -> str | None:
    """시드별 트레이스에서 DUT 출력값을 사이클 단위로 비교해 처음 달라진 곳을 돌려준다."""
    base = tb_out / tags[0]
    for f in sorted(base.glob("*.trace.json")):
        ref = json.loads(f.read_text())
        for tag in tags[1:]:
            other = tb_out / tag / f.name
            if not other.exists():
                continue
            oth = json.loads(other.read_text())
            for a, b in zip(ref, oth):
                for o in outputs:
                    if a["values"].get(o) != b["values"].get(o):
                        return (f'{f.name.removesuffix(".trace.json")}: {a["domain"]} cycle {a["cycle"]} {o} = '
                                f'{a["values"].get(o)} (seed {tags[0]}) / {b["values"].get(o)} (seed {tag})')
            if len(ref) != len(oth):
                return (f'{f.name.removesuffix(".trace.json")}: 실행 길이가 다름 '
                        f'({len(ref)} (seed {tags[0]}) / {len(oth)} (seed {tag}))')
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E1 lint / E2 sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("lint")
    a.add_argument("--top", required=True)
    a.add_argument("files", nargs="+")
    b = sub.add_parser("sim")
    b.add_argument("--top", required=True)
    b.add_argument("--tests", required=True, help="cocotb 테스트 모듈 이름")
    b.add_argument("--test-dir", required=True)
    b.add_argument("--build-dir", default="build/sim")
    b.add_argument("--seed", type=int)
    b.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    files = [Path(f) for f in args.files]
    if args.cmd == "lint":
        r = lint(files, args.top)
    else:
        r = sim(files, args.top, args.tests, Path(args.test_dir), Path(args.build_dir), seed=args.seed)
    d = r.to_dict()
    d.pop("log")
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
