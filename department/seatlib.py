"""부서 계층의 Seat 설정: 경로, 명단, Seat별 macOS sandbox 프로필.

OpenRig의 조율은 메시지와 규범이라 접근을 막지 못한다. 그래서 권한은 Seat 프로세스를 OS sandbox로 감싸 강제한다
(Linux 서버에서는 계정 분리나 bubblewrap으로 바꾼다).

| 규칙 | 프로필 |
| --- | --- |
| 어떤 Seat도 IR, RTL, 실행 상태를 쓰지 못함 | 파이프라인 저장소(STORE)와 에이전트 작업(RUNS) 쓰기 거부 |
| Seat는 자기 worktree에서만 작업 | 다른 Seat의 worktree와 저장소 원본 쓰기 거부 (git 메타데이터 `.git`만 허용) |
| DV Seat는 파이프라인 Verifier의 참조 모델과 테스트를 볼 수 없음 | RUNS와 STORE 읽기 거부. 승인된 RTL과 SPEC은 파이프라인 API로만 받음 |
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEPT = Path(__file__).resolve().parent
REPO = DEPT.parent
ROSTER = json.loads((DEPT / "seats.json").read_text(encoding="utf-8"))
CACHE = Path.home() / ".cache" / "chip-design-department"


def dept_home() -> Path:
    return Path(os.environ.get("CHIPDEPT_DEPT_HOME", CACHE / "dept"))


def store() -> Path:
    return Path(os.environ.get("CHIPDEPT_STORE", dept_home() / "store"))


def gateway_home() -> Path:
    return Path(os.environ.get("CHIPDEPT_GATEWAY_HOME", CACHE / "gateway"))


def keys_dir() -> Path:
    return dept_home() / "keys"


def key_file(seat_id: str) -> Path:
    return keys_dir() / f"{seat_id}.key"


def runs() -> Path:
    return Path(os.environ.get("CHIPDEPT_RUNS", CACHE / "runs"))


def seat(seat_id: str) -> dict:
    s = next((x for x in ROSTER["seats"] if x["id"] == seat_id), None)
    if s is None:
        raise KeyError(f"없는 Seat: {seat_id} (있는 것: {[x['id'] for x in ROSTER['seats']]})")
    return s


def session(seat_id: str) -> str:
    pod, member = seat_id.split(".")
    return f"{pod}-{member}@{ROSTER['rig']}"


def worktree(seat_id: str) -> Path:
    return dept_home() / "seats" / seat_id.replace(".", "-")


def _q(p: Path) -> str:
    return json.dumps(str(Path(p).resolve()))


def profile(seat_id: str) -> str:
    """Seat 하나의 sandbox 프로필 (SBPL). 뒤에 오는 규칙이 앞의 규칙보다 우선한다."""
    s = seat(seat_id)
    st, rn, seats_root, own = store(), runs(), dept_home() / "seats", worktree(seat_id)
    gw, keys = gateway_home(), keys_dir()
    for p in (st, rn, seats_root, gw, keys):
        p.mkdir(parents=True, exist_ok=True)
    lines = ["(version 1)", "(allow default)",
             f";; Seat {seat_id} ({s['label']})",
             ";; 파이프라인만 쓰는 곳: 실행 상태, IR, RTL, 에이전트 작업",
             f"(deny file-write* (subpath {_q(st)}))",
             f"(deny file-write* (subpath {_q(rn)}))",
             ";; 저장소 원본과 다른 Seat의 worktree는 쓰지 못함. git 메타데이터와 자기 worktree만 허용",
             f"(deny file-write* (subpath {_q(REPO)}))",
             f"(allow file-write* (subpath {_q(REPO / '.git')}))",
             f"(deny file-write* (subpath {_q(seats_root)}))",
             f"(allow file-write* (subpath {_q(own)}))",
             ";; 게이트웨이 저장소(파이프라인 API 토큰, 계정 DB)와 다른 Seat의 API 키는 읽지 못함. 자기 키만",
             f"(deny file-read* file-write* (subpath {_q(gw)}))",
             f"(deny file-read* file-write* (subpath {_q(keys)}))",
             f"(allow file-read* (literal {_q(key_file(seat_id))}))"]
    if s.get("verifier_blind"):
        lines += [";; DV: 파이프라인 Verifier 산출물과 실행 디렉터리를 읽지 못함 (승인된 RTL과 SPEC은 API로)",
                  f"(deny file-read* (subpath {_q(rn)}))",
                  f"(deny file-read* (subpath {_q(st)}))"]
    return "\n".join(lines) + "\n"
