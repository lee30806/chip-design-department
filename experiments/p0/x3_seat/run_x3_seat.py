"""X3: OpenRig Seat(runtime: claude-code)가 로컬 모델로 동작하는지 확인한다.

확인 항목
  1. 세션이 시작되고 메시지에 응답함
  2. 작업 디렉터리 안에서 파일을 씀 (도구 사용)
  3. 다른 Seat에 메시지를 보냄 (Seat → Seat, rig send)
  4. 데몬을 재시작한 뒤 응답함
  5. tmux까지 내린 뒤 rig up으로 복원하고 응답함

데몬, tmux, 모델 연결은 호출한 셸의 환경 변수를 따른다. Seat는 데몬 환경을 물려받는다.
  HOME, OPENRIG_HOME, OPENRIG_PORT, TMUX_TMPDIR      격리 (사용자 설정을 건드리지 않음)
  ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY             로컬 모델 서버 (Anthropic Messages 호환)
  CLAUDE_CODE_MAX_CONTEXT_TOKENS                    모델 서버의 컨텍스트 길이와 같게
  DISABLE_AUTOUPDATER=1                             폐쇄망에서 자동 업데이트 호출을 막음

  python3 experiments/p0/x3_seat/run_x3_seat.py --rig experiments/p0/x3_seat/rig/rig.yaml --out results/x3.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path

LEAD, ENG = "design-lead@x3-rig", "design-eng@x3-rig"


def rig(*args: str, timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["rig", *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def screen(session: str) -> str:
    return rig("capture", session, "--lines", "200", timeout=60).stdout


def wait_for(session: str, token: str, timeout_s: float) -> float | None:
    """화면에 token이 나올 때까지 기다린다. 걸린 초를 돌려준다.
    token은 보낸 질문에 그대로 들어 있지 않은 문자열이어야 한다 (질문이 줄바꿈되어도 오인하지 않도록)."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if token in screen(session):
            return round(time.time() - t0, 1)
        time.sleep(10)
    return None


def ask(session: str, text: str) -> None:
    rig("send", session, text, "--raw", timeout=120)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rig", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=900, help="항목마다 응답을 기다리는 최대 초")
    args = ap.parse_args()
    rig_path = Path(args.rig).resolve()
    work = rig_path.parent / "work"
    res: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def save():
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))

    rig("daemon", "start", "--no-kernel", timeout=120)
    up = rig("up", str(rig_path), "--non-interruptive", "--yes", timeout=600)
    res["up"] = up.returncode == 0
    save()

    tok = f"ACK-{uuid.uuid4().hex[:6]}"
    ask(LEAD, f"연결 확인입니다. 명령은 실행하지 말고, 토큰 {tok} 앞에 OK- 를 붙인 한 줄로만 답하세요.")
    res["1_reply_s"] = wait_for(LEAD, f"OK-{tok}", args.timeout)
    save()

    fname, content = f"x3_{uuid.uuid4().hex[:6]}.txt", f"W-{uuid.uuid4().hex[:6]}"
    ask(ENG, f"작업 디렉터리에 {fname} 파일을 만들고 내용으로 {content} 한 줄만 쓰세요. 다 쓰면 DONE 뒤에 하이픈과 파일 내용을 붙여 답하세요.")
    res["2_tool_s"] = wait_for(ENG, f"DONE-{content}", args.timeout)
    res["2_file_ok"] = (work / fname).exists() and content in (work / fname).read_text()
    save()

    ping = f"PING-{uuid.uuid4().hex[:6]}"
    ask(LEAD, f"bash로 다음 명령 하나만 실행하세요: rig send {ENG} \"{ping}\" --raw  실행했으면 SENT 뒤에 하이픈과 보낸 문자열을 붙여 답하세요.")
    res["3_sent_s"] = wait_for(LEAD, f"SENT-{ping}", args.timeout)
    res["3_eng_received"] = ping in screen(ENG)
    save()

    rig("daemon", "stop", timeout=120)
    rig("daemon", "start", "--no-kernel", timeout=120)
    tok = f"ACK-{uuid.uuid4().hex[:6]}"
    ask(LEAD, f"데몬 재시작 확인입니다. 토큰 {tok} 앞에 OK- 를 붙인 한 줄로만 답하세요.")
    res["4_after_daemon_restart_s"] = wait_for(LEAD, f"OK-{tok}", args.timeout)
    save()

    rig("down", "x3-rig", timeout=300)
    subprocess.run(["tmux", "kill-server"], capture_output=True)
    rig("up", "x3-rig", "--yes", timeout=600)
    tok = f"ACK-{uuid.uuid4().hex[:6]}"
    ask(LEAD, f"복원 확인입니다. 이 대화에서 앞서 보낸 PING 토큰의 6자리 16진수 부분을 거꾸로 쓰고(모르면 NONE), 다음 줄에 토큰 {tok} 앞에 OK- 를 붙여 쓰세요.")
    res["5_after_restore_s"] = wait_for(LEAD, f"OK-{tok}", args.timeout)
    res["5_remembers_ping"] = ping.split("-")[1][::-1] in screen(LEAD)  # 대화 이력이 복원됐는지
    res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save()
    rig("down", "x3-rig", timeout=300)
    rig("daemon", "stop", timeout=120)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
