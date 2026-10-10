"""X6: 게이트웨이 → OpenRig → Seat 대화 왕복.

게이트웨이가 할 일을 OpenRig CLI로 흉내 낸다. 모델은 직접 부르지 않는다.
  1. 보낸 사람(이름, 역할)과 메시지 ID를 본문 머리에 붙여 `rig send`로 Seat에 보낸다.
  2. `rig transcript --tail`을 주기적으로 읽어 Seat의 답(`ACK <메시지 ID> <이름>`)을 찾는다.
  3. 두 사람이 같은 Seat에 거의 동시에 보내는 경우도 시험한다.
  4. `rig ps --nodes -A --json`에서 Seat 상태(agentActivity)를 읽을 수 있는지 본다.

`rig send`는 보낸 쪽 Seat 환경 변수로 From을 정하므로, Seat가 아닌 게이트웨이가 보내면
보낸 사람이 표시되지 않는다. 그래서 사람의 신원은 본문 머리에 직접 붙인다.

사용 예
  python3 experiments/p0/x6_chat_roundtrip/run_x6.py --seats design-lead@chip,rtl-eng@chip --trials 3
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PROBE = """[Web UI] 보낸 사람: {name} ({role}) · 메시지 ID: {mid}
연결 확인 메시지입니다. 이 메시지에 대한 답의 첫 줄을 정확히 `ACK {mid} {name}` 으로 쓰고, 다른 작업은 하지 마세요."""

# --raw: OpenRig 봉투(From/To, 답장 안내) 없이 보내고, 답은 화면에 쓰라고 명시한다.
PROBE_RAW = PROBE + "\n답은 rig send 등 명령으로 보내지 말고 이 대화 화면에 직접 쓰세요. Web UI가 화면을 읽습니다."


class Rig:
    def __init__(self, binary: str, timeout_s: float = 30, raw: bool = False):
        self.binary, self.timeout_s, self.raw = binary, timeout_s, raw

    def run(self, *args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([self.binary, *args], capture_output=True, text=True,
                                  timeout=self.timeout_s, stdin=subprocess.DEVNULL)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return subprocess.CompletedProcess([self.binary, *args], 127, "", str(e))

    def send(self, session: str, text: str) -> tuple[bool, str]:
        p = self.run("send", session, text, "--json", *(["--raw"] if self.raw else []))
        return p.returncode == 0, (p.stdout + p.stderr)[-500:]

    def transcript(self, session: str, lines: int = 400) -> str:
        p = self.run("transcript", session, "--tail", str(lines))
        return p.stdout if p.returncode == 0 else ""

    def nodes(self) -> list[dict] | None:
        # Seat 바깥에서 부르면 "현재 rig"가 없으므로 -A로 전체를 본다.
        p = self.run("ps", "--nodes", "-A", "--json")
        if p.returncode != 0:
            return None
        try:
            data = json.loads(p.stdout)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else data.get("nodes") or data.get("data")


def wait_ack(rig: Rig, session: str, mid: str, timeout_s: float, poll_s: float) -> tuple[str | None, float]:
    """transcript에서 `ACK <mid> <이름>`을 찾을 때까지 기다린다. (찾은 이름, 걸린 시간)."""
    t0 = time.monotonic()
    pat = re.compile(rf"ACK {re.escape(mid)} ([A-Za-z0-9_]+)")
    while time.monotonic() - t0 < timeout_s:
        # 보낸 본문에도 `ACK <mid> <이름>`이 들어 있으므로, 안내 문장이 아닌 줄만 본다.
        for line in rig.transcript(session).splitlines():
            m = pat.search(line)
            if m and "첫 줄을 정확히" not in line:
                return m.group(1), time.monotonic() - t0
        time.sleep(poll_s)
    return None, time.monotonic() - t0


def one_trial(rig: Rig, session: str, name: str, role: str, timeout_s: float, poll_s: float) -> dict:
    mid = uuid.uuid4().hex[:8]
    sent, info = rig.send(session, (PROBE_RAW if rig.raw else PROBE).format(name=name, role=role, mid=mid))
    row = {"session": session, "sender": name, "role": role, "mid": mid, "sent": sent, "send_info": info}
    if not sent:
        return {**row, "acked": False, "sender_ok": False, "latency_s": None}
    who, dt = wait_ack(rig, session, mid, timeout_s, poll_s)
    return {**row, "acked": who is not None, "sender_ok": who == name, "latency_s": round(dt, 1)}


def concurrent_trial(rig: Rig, session: str, timeout_s: float, poll_s: float) -> list[dict]:
    senders = [("alice", "설계"), ("bob", "검증")]
    out: list[dict] = []
    threads = [threading.Thread(target=lambda n=n, r=r: out.append(one_trial(rig, session, n, r, timeout_s, poll_s)))
               for n, r in senders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rig", default="rig", help="OpenRig CLI 경로")
    ap.add_argument("--seats", required=True, help="쉼표로 구분한 Seat 세션 이름")
    ap.add_argument("--trials", type=int, default=3, help="Seat별 단일 전송 횟수")
    ap.add_argument("--timeout", type=float, default=300, help="답을 기다리는 최대 초")
    ap.add_argument("--poll", type=float, default=5)
    ap.add_argument("--raw", action="store_true", help="OpenRig 봉투 없이 보내고 화면에 답하라고 지시")
    ap.add_argument("--out", default=str(ROOT / "experiments" / "p0" / "results"))
    args = ap.parse_args(argv)

    rig = Rig(args.rig, raw=args.raw)
    seats = args.seats.split(",")
    out_dir = Path(args.out) / f"x6-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes = rig.nodes()
    status_ok = bool(nodes) and all(
        any(n.get("canonicalSessionName") == s and (n.get("agentActivity") or {}).get("state") for n in nodes) for s in seats)

    rows: list[dict] = []
    for s in seats:
        for i in range(args.trials):
            rows.append({"kind": "single", **one_trial(rig, s, "tester", "관리자", args.timeout, args.poll)})
            print(f"[{s}] single {i + 1}/{args.trials} {'ACK' if rows[-1]['acked'] else 'NO-ACK'}", file=sys.stderr)
        rows += [{"kind": "concurrent", **r} for r in concurrent_trial(rig, s, args.timeout, args.poll)]
        print(f"[{s}] concurrent done", file=sys.stderr)
    (out_dir / "trials.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def pct(xs):
        return f"{100 * sum(xs) / len(xs):.0f}%" if xs else "-"

    lines = [f"# X6 결과 ({time.strftime('%Y-%m-%d %H:%M')}, {'raw' if args.raw else '봉투'} 모드)", "",
             f"Seat 상태 조회(`rig ps --nodes -A --json`의 agentActivity): {'가능' if status_ok else '불가 또는 일부 누락'}", "",
             "| Seat | 종류 | 시도 | 전송 성공 | 답 수신 | 보낸 사람 구분 | 평균 지연(s) |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for s in seats:
        for kind in ("single", "concurrent"):
            m = [r for r in rows if r["session"] == s and r["kind"] == kind]
            lat = [r["latency_s"] for r in m if r["acked"]]
            lines.append(f"| {s} | {kind} | {len(m)} | {pct([r['sent'] for r in m])} | {pct([r['acked'] for r in m])} | "
                         f"{pct([r['sender_ok'] for r in m])} | {sum(lat) / len(lat):.1f} |" if lat else
                         f"| {s} | {kind} | {len(m)} | {pct([r['sent'] for r in m])} | {pct([r['acked'] for r in m])} | "
                         f"{pct([r['sender_ok'] for r in m])} | - |")
    summary = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
