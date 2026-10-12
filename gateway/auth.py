"""인증. 인증 제공자(AuthProvider)는 사용자 이름과 비밀을 확인하는 일만 하고, 세션과 역할은 게이트웨이가 관리한다.
사내 SSO로 바꿀 때는 AuthProvider 구현 하나를 더하면 된다 (예: 헤더나 토큰을 확인하고 사용자 이름을 돌려줌).

- 자체 계정(LocalAuth): PBKDF2-SHA256 (반복 200,000회, 사용자마다 salt).
- 세션: 무작위 토큰을 쿠키로 주고, DB에는 해시만 둔다 (12시간).
- API 키: Seat와 서비스 계정용. DB에는 해시만 둔다.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Protocol

from gateway.db import DB, now
from gateway.perms import CAPS, ROLES

SESSION_S = 12 * 3600
ITER = 200_000


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ITER).hex()
    return f"pbkdf2_sha256${ITER}${salt}${dk}"


def check_password(pw: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, it, salt, dk = stored.split("$")
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it)).hex()
    return algo == "pbkdf2_sha256" and hmac.compare_digest(got, dk)


class AuthProvider(Protocol):
    name: str

    def authenticate(self, username: str, secret: str) -> str | None:
        """확인되면 사용자 이름, 아니면 None."""


class LocalAuth:
    name = "local"

    def __init__(self, db: DB):
        self.db = db

    def authenticate(self, username: str, secret: str) -> str | None:
        u = self.db.one("SELECT username, pw_hash, disabled, kind FROM users WHERE username=?", (username,))
        if not u or u["disabled"] or u["kind"] != "human":
            check_password(secret, hash_password("x"))   # 없는 사용자도 비슷한 시간이 걸리게
            return None
        return username if check_password(secret, u["pw_hash"]) else None


class Accounts:
    def __init__(self, db: DB, provider: AuthProvider | None = None):
        self.db = db
        self.provider = provider or LocalAuth(db)

    # -- 사용자 --
    def add_user(self, username: str, display: str, roles: list[str], caps: list[str] | None = None, password: str | None = None,
                 kind: str = "human", seat: str | None = None) -> dict:
        bad = [r for r in roles if r not in ROLES] + [c for c in caps or [] if c not in CAPS]
        if bad:
            raise ValueError(f"모르는 역할이나 능력: {bad} (역할 {ROLES}, 능력 {CAPS})")
        if kind == "seat" and "approver" in roles:
            raise ValueError("Seat 계정은 승인자가 될 수 없음 (승인은 사람만)")
        if self.db.one("SELECT 1 FROM users WHERE username=?", (username,)):
            raise ValueError(f"이미 있는 사용자: {username}")
        self.db.x("INSERT INTO users (username, display, roles, caps, kind, seat, pw_hash, created) VALUES (?,?,?,?,?,?,?,?)",
                  (username, display, ",".join(roles), ",".join(caps or []), kind, seat,
                   hash_password(password) if password else None, now()))
        return self.user(username)

    def user(self, username: str) -> dict | None:
        u = self.db.one("SELECT username, display, roles, caps, kind, seat, disabled FROM users WHERE username=?", (username,))
        if u:
            u["roles"] = [r for r in u["roles"].split(",") if r]
            u["caps"] = [c for c in u["caps"].split(",") if c]
            u["disabled"] = bool(u["disabled"])
        return u

    def users(self) -> list[dict]:
        return [self.user(r["username"]) for r in self.db.q("SELECT username FROM users ORDER BY username")]

    def set_password(self, username: str, password: str) -> None:
        self.db.x("UPDATE users SET pw_hash=? WHERE username=?", (hash_password(password), username))

    # -- 세션과 API 키 --
    def login(self, username: str, secret: str) -> str | None:
        name = self.provider.authenticate(username, secret)
        if not name:
            self.db.audit(username, "login_failed")
            return None
        token = secrets.token_urlsafe(32)
        self.db.x("INSERT INTO sessions (token_hash, username, expires) VALUES (?,?,?)", (_h(token), name, time.time() + SESSION_S))
        self.db.audit(name, "login")
        return token

    def logout(self, token: str) -> None:
        self.db.x("DELETE FROM sessions WHERE token_hash=?", (_h(token),))

    def from_session(self, token: str | None) -> dict | None:
        if not token:
            return None
        s = self.db.one("SELECT username, expires FROM sessions WHERE token_hash=?", (_h(token),))
        if not s or s["expires"] < time.time():
            return None
        u = self.user(s["username"])
        return u if u and not u["disabled"] else None

    def new_api_key(self, username: str) -> str:
        key = "cdd_" + secrets.token_urlsafe(32)
        self.db.x("INSERT INTO api_keys (key_hash, username, created) VALUES (?,?,?)", (_h(key), username, now()))
        return key

    def from_api_key(self, key: str | None) -> dict | None:
        if not key:
            return None
        k = self.db.one("SELECT username FROM api_keys WHERE key_hash=?", (_h(key),))
        u = self.user(k["username"]) if k else None
        return u if u and not u["disabled"] else None
