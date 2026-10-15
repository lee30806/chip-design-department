"""부서 계층 운영: 격리된 OpenRig 환경에서 rig를 올리고 내리고, Seat를 초기화하고, Seat에 명령을 보낸다.

    python3 department/dept.py up [--mode agent|shell] [--api-args "..."]
    python3 department/dept.py down | status
    python3 department/dept.py snapshot-down | recover      스냅숏을 남기고 내리기, 토폴로지 복구
    python3 department/dept.py reset <pod.member>          Seat 세션 초기화 (stop → clean → launch)
    python3 department/dept.py run <pod.member> <명령>      Seat 셸에 명령을 보내고 출력을 읽음 (shell 모드)
    python3 department/dept.py rig <rig 인자...>            격리 환경으로 rig CLI 실행

OpenRig 데몬은 사용자 설정을 건드리지 않게 HOME, OPENRIG_HOME, tmux 소켓, 포트를 따로 둔다 (P0 X5).
Seat는 데몬의 환경을 물려받으므로, 경로(CHIPDEPT_*)도 여기서 정해 데몬에 넘긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seatlib  # noqa: E402

OPENRIG = Path(os.environ.get("CHIPDEPT_OPENRIG", seatlib.CACHE / "openrig"))
RIG_BIN = OPENRIG / "node_modules" / ".bin" / "rig"
TMUX_TMPDIR = os.environ.get("CHIPDEPT_TMUX_TMPDIR", "/tmp/cdrt")   # macOS Unix 소켓 길이 제한(104자) 때문에 짧게
RIG_SPEC = seatlib.DEPT / "rig.yaml"
RIG = seatlib.ROSTER["rig"]


def env(mode: str | None = None, api_args: str | None = None) -> dict:
    real_home = os.environ.get("CHIPDEPT_REAL_HOME", str(Path.home()))
    # 호출한 프로세스의 파이썬 환경(가상환경, cocotb가 넣은 PYTHONHOME 등)은 데몬과 Seat에 넘기지 않는다
    e = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__")}
    e.update(HOME=str(OPENRIG / "home"), OPENRIG_HOME=str(OPENRIG / "orhome"), TMUX_TMPDIR=TMUX_TMPDIR,
             OPENRIG_PORT=os.environ.get("OPENRIG_PORT", "7533"), DISABLE_AUTOUPDATER="1",
             OPENRIG_UI_ENABLED="1",   # 데몬의 터미널 WebSocket은 웹 UI가 켜져 있을 때만 있음 (게이트웨이 Seat 터미널 보기)
             CHIPDEPT_REAL_HOME=real_home, CHIPDEPT_DEPT_HOME=str(seatlib.dept_home()), CHIPDEPT_STORE=str(seatlib.store()),
             CHIPDEPT_RUNS=str(seatlib.runs()), CHIPDEPT_API_PORT=os.environ.get("CHIPDEPT_API_PORT", "8740"),
             CHIPDEPT_GATEWAY_HOME=str(seatlib.gateway_home()),
             CHIPDEPT_GATEWAY_PORT=os.environ.get("CHIPDEPT_GATEWAY_PORT", "8750"))
    e["CHIPDEPT_API"] = f"http://127.0.0.1:{e['CHIPDEPT_API_PORT']}"
    e["CHIPDEPT_GATEWAY"] = f"http://127.0.0.1:{e['CHIPDEPT_GATEWAY_PORT']}"
    if mode:
        e["CHIPDEPT_SEAT_MODE"] = mode
    if api_args is not None:
        e["CHIPDEPT_API_ARGS"] = api_args
    for d in ("home", "orhome"):
        (OPENRIG / d).mkdir(parents=True, exist_ok=True)
    Path(TMUX_TMPDIR).mkdir(parents=True, exist_ok=True)
    return e


def rig(*args: str, e: dict | None = None, timeout: float = 600) -> subprocess.CompletedProcess:
    if not RIG_BIN.exists():
        raise SystemExit(f"OpenRig가 없음: {RIG_BIN}. 설치: npm install --prefix {OPENRIG} @openrig/cli@0.6.6")
    return subprocess.run([str(RIG_BIN), *args], env=e or env(), capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], env={**os.environ, "TMUX_TMPDIR": TMUX_TMPDIR}, capture_output=True, text=True)


def up(mode: str = "agent", api_args: str | None = None) -> dict:
    """데몬을 이 환경으로 다시 시작하고 rig를 올린다 (Seat는 데몬 환경을 물려받으므로 데몬부터 새로 띄운다)."""
    e = env(mode, api_args)
    # 게이트웨이: 파이프라인 API 토큰과 Seat 계정, Seat별 API 키 (이미 있으면 그대로)
    g = subprocess.run([str(seatlib.REPO / ".venv" / "bin" / "python"), "-m", "gateway", "seats", "--keys-dir", str(seatlib.keys_dir())],
                       cwd=seatlib.REPO, env={**e, "HOME": e["CHIPDEPT_REAL_HOME"]}, capture_output=True, text=True)
    if g.returncode != 0:
        return {"daemon": None, "up": 1, "out": "게이트웨이 준비 실패: " + (g.stdout + g.stderr)[-1500:]}
    rig("daemon", "stop", e=e, timeout=120)
    d = rig("daemon", "start", "--no-kernel", e=e, timeout=120)
    u = rig("up", str(RIG_SPEC), "--yes", e=e, timeout=900) if "--yes" in rig("up", "--help", e=e).stdout else \
        rig("up", str(RIG_SPEC), e=e, timeout=900)
    return {"daemon": d.returncode, "up": u.returncode, "out": (u.stdout + u.stderr)[-3000:]}


def down() -> dict:
    d = rig("down", RIG, "--delete", "--force", timeout=300)
    s = rig("daemon", "stop", timeout=120)
    return {"down": d.returncode, "daemon_stop": s.returncode, "out": (d.stdout + d.stderr)[-2000:]}


def snapshot_down() -> dict:
    """복구 지점을 남기고 내린다 (rig down --snapshot)."""
    r = rig("down", RIG, "--snapshot", timeout=300)
    return {"rc": r.returncode, "out": (r.stdout + r.stderr)[-1500:]}


def recover() -> dict:
    """토폴로지 복구. 최근 스냅숏에서 되살리고, OpenRig가 스냅숏을 쓸 수 없다고 하면(예: Seat를 새로 띄운 뒤라 스냅숏의
    점유자가 옛것) rig.yaml에서 새로 띄운다. Seat의 상태는 세션이 아니라 저장소와 worktree에 있으므로 결과는 같다."""
    r = rig("up", RIG, timeout=900)
    if r.returncode == 0:
        return {"how": "snapshot", "rc": 0}
    f = rig("up", str(RIG_SPEC), timeout=900)
    return {"how": "spec", "rc": f.returncode, "snapshot_error": (r.stdout + r.stderr)[-600:]}


def status() -> str:
    return rig("ps", "--nodes", "--rig", RIG).stdout


def capture(seat_id: str, lines: int = 200) -> str:
    return tmux("capture-pane", "-p", "-J", "-S", f"-{lines}", "-t", seatlib.session(seat_id)).stdout


def wait_for(seat_id: str, pattern: str, timeout: float = 60) -> re.Match | None:
    """화면에 정규식(여러 줄 모드)이 나타날 때까지 기다린다."""
    rx = re.compile(pattern, re.M)
    end = time.time() + timeout
    while time.time() < end:
        m = rx.search(capture(seat_id, 400))
        if m:
            return m
        time.sleep(0.5)
    return None


def run(seat_id: str, command: str, timeout: float = 120) -> tuple[int | None, str]:
    """shell 모드 Seat에 명령을 보내고 (종료 코드, 출력)을 돌려준다.
    표지는 입력 줄에 그대로 나타나지 않게 나눠 쓰고("E""ND"), 출력 줄의 맨 앞에서만 찾는다."""
    tok = uuid.uuid4().hex[:8]
    rig("send", seatlib.session(seat_id), f'echo "B""EGIN-{tok}"; {command}; echo "E""ND-{tok} rc=$?"', "--raw", timeout=60)
    m = wait_for(seat_id, rf"^BEGIN-{tok}$(?s:(.*?))^END-{tok} rc=(\d+)", timeout)
    if m is None:
        return None, capture(seat_id)[-2000:]
    return int(m.group(2)), m.group(1).strip()


def wait_ready(seat_id: str, timeout: float = 90) -> bool:
    """Seat 진입점이 셸까지 왔는지 (shell 모드의 프롬프트 `<seat>> `)."""
    return wait_for(seat_id, rf"^{re.escape(seat_id)}> ", timeout) is not None


def reset(seat_id: str) -> dict:
    """Seat 세션 초기화: 지금 세션을 끝내고 연속성 없이 새 세션으로 띄운다."""
    r = rig("seat", "launch", seatlib.session(seat_id), "--stop", "--fresh", "--reason", "dept reset", timeout=300)
    return {"rc": r.returncode, "out": (r.stdout + r.stderr)[-1500:]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="부서 계층 운영")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("up")
    s.add_argument("--mode", choices=["agent", "shell"], default="agent")
    s.add_argument("--api-args", default=None)
    sub.add_parser("down")
    sub.add_parser("snapshot-down")
    sub.add_parser("recover")
    sub.add_parser("status")
    sub.add_parser("reset").add_argument("seat")
    s = sub.add_parser("run")
    s.add_argument("seat")
    s.add_argument("command")
    s = sub.add_parser("rig")
    s.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.cmd == "up":
        print(json.dumps(up(a.mode, a.api_args), ensure_ascii=False, indent=1))
    elif a.cmd == "down":
        print(json.dumps(down(), ensure_ascii=False, indent=1))
    elif a.cmd == "snapshot-down":
        print(json.dumps(snapshot_down(), ensure_ascii=False))
    elif a.cmd == "recover":
        print(json.dumps(recover(), ensure_ascii=False))
    elif a.cmd == "status":
        print(status())
    elif a.cmd == "reset":
        print(json.dumps(reset(a.seat), ensure_ascii=False))
    elif a.cmd == "run":
        rc, out = run(a.seat, a.command)
        print(out)
        return rc if rc is not None else 1
    else:
        r = rig(*a.args)
        print(r.stdout + r.stderr, end="")
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
