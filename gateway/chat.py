"""Seat 대화 중계 (P9 Web UI 3차). 게이트웨이 → OpenRig 데몬 → Seat 화면. 모델은 직접 부르지 않는다.

P0 X6에서 정한 방식:
- 봉투 모드는 쓰지 않는다 (Seat가 답장 안내를 보고 명령으로 답하려 함). 봉투 없이(raw) 보낸다.
- `rig send`의 From은 보낸 Seat의 환경으로 정해져 게이트웨이가 보내면 비므로, 보낸 사람과 메시지 ID를 본문 머리에 붙인다.
- 답은 화면(capture)에서 메시지 ID 표지로 찾는다. 화면은 터미널 폭에서 줄이 바뀌므로 짧은 표지를 쓴다.
  보내는 본문에는 표지를 그대로 쓰지 않고 말로만 설명한다 (보낸 본문을 답으로 오인하지 않게).

종류: 대화(chat)는 사람이면 누구나 어느 Seat에나. 작업 지시(instruction)는 lead Seat에만, 설계 역할이나 승인자만.
Seat 계정(kind=seat)은 보낼 수 없다 (Seat끼리는 OpenRig로 직접 대화한다).
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

from gateway.clients import OpenRig, UpstreamError
from gateway.db import DB, now
from gateway.perms import Forbidden

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = """
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT, mid TEXT UNIQUE NOT NULL, seat TEXT NOT NULL, username TEXT NOT NULL, display TEXT NOT NULL,
  roles TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, sent_at TEXT NOT NULL, status TEXT NOT NULL,
  reply TEXT, replied_at TEXT, error TEXT);
"""
KIND_LABEL = {"chat": "대화", "instruction": "작업 지시"}
INSTRUCT_ROLES = {"design", "approver"}
PENDING = ("sent", "replying")

BODY = """[Web UI] 보낸 사람: {display} ({username}, {roles}) · 메시지 ID: {mid} · 종류: {kind}
{text}

(Web UI가 이 화면을 읽어 답을 보여 줍니다. rig send 같은 명령으로 답하지 말고 화면에 직접 쓰세요. 답의 첫 줄에는 메시지 ID를 대괄호로 감싸 쓰고, 마지막 줄에는 메시지 ID 뒤에 한 칸 띄고 '끝'을 붙여 대괄호로 감싸 쓰세요.)"""


def seats_roster() -> dict[str, dict]:
    raw = json.loads((ROOT / "department" / "seats.json").read_text(encoding="utf-8"))
    return {s["id"]: {**s, "rig": raw["rig"]} for s in raw["seats"]}


def is_lead(seat_id: str) -> bool:
    return seat_id.endswith(".lead") or seat_id == "lead.chip"


def session_of(seat: dict) -> str:
    """Seat id(pod.member) → OpenRig 세션 이름 (pod-member@rig)."""
    pod, member = seat["id"].split(".", 1)
    return f"{pod}-{member}@{seat['rig']}"


_DECOR = re.compile(r"^[\s│┃|>●⏺•*-]+")


def extract_reply(screen: str, mid: str) -> tuple[str | None, bool]:
    """화면에서 답을 찾는다. (답 본문, 끝 표지까지 왔는지). 시작 표지가 없으면 (None, False).
    같은 표지가 여러 번 보이면 마지막 것을 쓴다 (Seat가 답을 다시 쓴 경우)."""
    lines = screen.splitlines()
    start = max((i for i, ln in enumerate(lines) if f"[{mid}]" in ln), default=None)
    if start is None:
        return None, False
    body = []
    for ln in lines[start + 1:]:
        if f"[{mid} 끝]" in ln:
            return "\n".join(body).strip(), True
        body.append(_DECOR.sub("", ln).rstrip())
    return "\n".join(body).strip(), False


class Chat:
    def __init__(self, db: DB, openrig: OpenRig):
        self.db, self.openrig = db, openrig
        self.db.conn.executescript(SCHEMA)

    def _seat(self, seat_id: str) -> dict:
        roster = seats_roster()
        if seat_id not in roster:
            raise Forbidden(f"없는 Seat: {seat_id}")
        return roster[seat_id]

    def send(self, user: dict, seat_id: str, text: str, kind: str = "chat") -> dict:
        seat = self._seat(seat_id)
        if user.get("kind") != "human":
            raise Forbidden("Seat 계정은 Web UI 대화를 보낼 수 없음 (Seat끼리는 OpenRig로 직접 대화)")
        if kind not in KIND_LABEL:
            raise Forbidden(f"종류는 {list(KIND_LABEL)} 중 하나")
        if kind == "instruction":
            if not is_lead(seat_id):
                raise Forbidden("작업 지시는 lead Seat에만 보냄")
            if not set(user["roles"]) & INSTRUCT_ROLES:
                raise Forbidden(f"작업 지시에는 {sorted(INSTRUCT_ROLES)} 역할이 필요함")
        text = text.strip()
        if not text:
            raise Forbidden("빈 메시지")
        mid = "M" + secrets.token_hex(3)
        body = BODY.format(display=user["display"], username=user["username"], roles=",".join(user["roles"]), mid=mid,
                           kind=KIND_LABEL[kind], text=text)
        status, error = "sent", None
        try:
            self.openrig.send(session_of(seat), body)
        except UpstreamError as e:
            status, error = "failed", str(e)
        self.db.x("INSERT INTO chat (mid, seat, username, display, roles, kind, text, sent_at, status, error) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (mid, seat_id, user["username"], user["display"], ",".join(user["roles"]), kind, text, now(), status, error))
        self.db.audit(user["username"], "seat_message", {"seat": seat_id, "mid": mid, "kind": kind, "status": status})
        return self.get(mid)

    def get(self, mid: str) -> dict:
        return self.db.one("SELECT * FROM chat WHERE mid=?", (mid,))

    def messages(self, seat_id: str) -> list[dict]:
        """그 Seat의 대화. 아직 답을 다 받지 못한 메시지는 화면을 한 번 읽어 답을 채운다."""
        seat = self._seat(seat_id)
        waiting = self.db.q("SELECT * FROM chat WHERE seat=? AND status IN (?, ?)", (seat_id, *PENDING))
        if waiting:
            try:
                screen = self.openrig.capture(session_of(seat))
            except UpstreamError:
                screen = ""
            for m in waiting:
                reply, done = extract_reply(screen, m["mid"])
                if reply is None:
                    continue
                self.db.x("UPDATE chat SET reply=?, status=?, replied_at=? WHERE mid=?",
                          (reply, "replied" if done else "replying", now() if done else None, m["mid"]))
        return self.db.q("SELECT * FROM chat WHERE seat=? ORDER BY id", (seat_id,))
