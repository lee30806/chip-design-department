"""coding agent를 headless로 한 번 실행한다.

파이프라인과 같은 방식이다. 스케줄러(여기서는 실험 스크립트)는 모델 API를 부르지 않는다.
작업 디렉터리에 과제 파일과 도구를 두고 coding agent 프로세스를 띄운 뒤,
종료되면 정해진 경로의 결과 파일을 회수해 검사한다.

런타임마다 headless 실행 방법이 다르므로 명령은 설정 파일의 템플릿으로 받는다.
템플릿 자리표시자: {prompt} {prompt_file} {workdir} {model}
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

KICKOFF = "작업 디렉터리의 TASK.md를 읽고 지시대로 수행하라. 끝나면 종료하라."


@dataclass
class AgentConfig:
    name: str                   # 결과 표에 쓸 이름
    family: str                 # 모델 계열 (Author/Verifier 계열 중복 판단용)
    runtime: str                # pi, codex, claude-code 등
    command: list[str]          # 실행 명령 템플릿
    model: str = ""
    env: dict[str, str] = field(default_factory=dict)
    vision: bool = False        # 이미지 파일을 읽을 수 있는 구성인지
    timeout_s: float = 1800


def load_agents(path: str | Path) -> list[AgentConfig]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # "_"로 시작하는 키는 설명용 메모로 보고 무시한다.
    return [AgentConfig(**{k: v for k, v in a.items() if not k.startswith("_")}) for a in raw["agents"]]


@dataclass
class AgentRun:
    returncode: int | None
    timed_out: bool
    duration_s: float
    stdout_tail: str
    stderr_tail: str

    @property
    def exit_ok(self) -> bool:
        return not self.timed_out and self.returncode == 0


def run_agent(cfg: AgentConfig, workdir: Path, task: str) -> AgentRun:
    """TASK.md를 쓰고 agent를 workdir에서 실행한다."""
    prompt_file = workdir / "TASK.md"
    prompt_file.write_text(task, encoding="utf-8")
    subs = {"prompt": KICKOFF, "prompt_file": str(prompt_file), "workdir": str(workdir), "model": cfg.model}
    cmd = [part.format(**subs) for part in cfg.command]
    env = {**os.environ, **cfg.env}

    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True,
                           timeout=cfg.timeout_s, stdin=subprocess.DEVNULL)
        rc, timed_out, out, err = p.returncode, False, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, timed_out = None, True
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    except FileNotFoundError as e:
        rc, timed_out, out, err = 127, False, "", str(e)
    return AgentRun(rc, timed_out, time.monotonic() - t0, out[-4000:], err[-4000:])


def snapshot(root: Path, exclude: tuple[str, ...]) -> dict[str, str]:
    """root 아래 파일의 해시. exclude로 시작하는 상대 경로와 숨김 최상위 항목은 뺀다."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or rel.startswith(exclude) or rel.split("/")[0].startswith("."):
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def scope_violations(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """쓰기 범위 밖에서 생기거나 바뀌거나 지워진 파일."""
    changed = [f"수정: {k}" for k in before if k in after and before[k] != after[k]]
    removed = [f"삭제: {k}" for k in before if k not in after]
    added = [f"추가: {k}" for k in after if k not in before]
    return changed + removed + added
