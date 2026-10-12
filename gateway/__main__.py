"""게이트웨이 CLI.

    python3 -m gateway init --admin <이름>                      처음 설정: DB, 파이프라인 API 토큰, 관리자 (비밀번호는 표준 입력)
    python3 -m gateway user add <이름> --roles design,approver [--caps design_lead] [--display "..."]   (비밀번호는 표준 입력)
    python3 -m gateway user list
    python3 -m gateway seats [--keys-dir DIR]                   department/seats.json의 Seat 계정과 API 키 만들기
    python3 -m gateway serve [--host 127.0.0.1] [--port 8750]

설정 (환경 변수)
    CHIPDEPT_GATEWAY_HOME   DB와 SPEC 작업 공간 (기본 ~/.cache/chip-design-department/gateway)
    CHIPDEPT_API            파이프라인 API (기본 http://127.0.0.1:8740). 토큰은 <home>/api_token
    CHIPDEPT_STORE          파이프라인 저장소 (실행 상세를 읽음. 기본 ~/.cache/chip-design-department/dept/store)
    OPENRIG_URL             OpenRig 데몬 (기본 http://127.0.0.1:7533)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from gateway.clients import OpenRig, Pipeline
from gateway.service import Gateway

CACHE = Path.home() / ".cache" / "chip-design-department"
ROOT = Path(__file__).resolve().parents[1]

# Seat 계정의 역할 (승인자는 없음: 승인은 사람만)
SEAT_ROLES = {"lead": ["design"], "design": ["design"], "dv": ["verification"], "pi": ["implementation"]}


def home() -> Path:
    return Path(os.environ.get("CHIPDEPT_GATEWAY_HOME", CACHE / "gateway"))


def token_path() -> Path:
    return home() / "api_token"


def make_gateway() -> Gateway:
    tok = token_path().read_text(encoding="utf-8").strip() if token_path().exists() else None
    store = Path(os.environ.get("CHIPDEPT_STORE", CACHE / "dept" / "store"))
    return Gateway(home(), Pipeline(os.environ.get("CHIPDEPT_API", "http://127.0.0.1:8740"), tok),
                   OpenRig(os.environ.get("OPENRIG_URL", "http://127.0.0.1:7533")), store)


def _password(prompt: str) -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    a, b = getpass.getpass(prompt), getpass.getpass("한 번 더: ")
    if a != b:
        raise SystemExit("비밀번호가 다름")
    return a


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m gateway", description="게이트웨이")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("--admin", required=True)
    s = sub.add_parser("user")
    us = s.add_subparsers(dest="ucmd", required=True)
    a = us.add_parser("add")
    a.add_argument("username")
    a.add_argument("--roles", required=True)
    a.add_argument("--caps", default="")
    a.add_argument("--display")
    us.add_parser("list")
    s = sub.add_parser("seats")
    s.add_argument("--keys-dir", type=Path, default=Path(os.environ.get("CHIPDEPT_DEPT_HOME", CACHE / "dept")) / "keys")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8750)
    a = ap.parse_args(argv)
    gw = make_gateway()
    if a.cmd == "init":
        if not token_path().exists():
            token_path().write_text(secrets.token_urlsafe(32), encoding="utf-8")
            token_path().chmod(0o600)
        if gw.accounts.user(a.admin) is None:
            gw.accounts.add_user(a.admin, a.admin, ["admin"], password=_password(f"{a.admin} 비밀번호: "))
        print(json.dumps({"home": str(home()), "api_token": str(token_path()), "admin": a.admin}, ensure_ascii=False))
    elif a.cmd == "user" and a.ucmd == "add":
        u = gw.accounts.add_user(a.username, a.display or a.username, [r for r in a.roles.split(",") if r],
                                 [c for c in a.caps.split(",") if c], _password(f"{a.username} 비밀번호: "))
        print(json.dumps(u, ensure_ascii=False))
    elif a.cmd == "user":
        print(json.dumps(gw.accounts.users(), ensure_ascii=False, indent=1))
    elif a.cmd == "seats":
        if not token_path().exists():   # 파이프라인 API 서버가 이 토큰으로 게이트웨이의 쓰기 요청만 받는다
            token_path().parent.mkdir(parents=True, exist_ok=True)
            token_path().write_text(secrets.token_urlsafe(32), encoding="utf-8")
            token_path().chmod(0o600)
        roster = json.loads((ROOT / "department" / "seats.json").read_text(encoding="utf-8"))
        a.keys_dir.mkdir(parents=True, exist_ok=True)
        made = []
        for st in roster["seats"]:
            name = "seat-" + st["id"].replace(".", "-")
            if gw.accounts.user(name) is None:
                caps = ["design_lead"] if st["id"] == "design.lead" else []
                gw.accounts.add_user(name, st["label"], SEAT_ROLES[st["id"].split(".")[0]], caps, kind="seat", seat=st["id"])
            key_file = a.keys_dir / f"{st['id']}.key"
            if not key_file.exists():
                key_file.write_text(gw.accounts.new_api_key(name), encoding="utf-8")
                key_file.chmod(0o600)
                made.append(st["id"])
        print(json.dumps({"keys_dir": str(a.keys_dir), "new_keys": made}, ensure_ascii=False))
    else:
        from gateway.server import serve
        httpd = serve(gw, a.host, a.port)
        print(f"게이트웨이: http://{a.host}:{a.port} (저장소 {home()})", flush=True)
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
