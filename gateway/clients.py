"""게이트웨이가 부르는 두 서비스: 파이프라인 API와 OpenRig 데몬 API. 모델은 직접 부르지 않는다."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class UpstreamError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _call(url: str, method: str = "GET", body=None, headers: dict | None = None, timeout: float = 30):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 로컬 서비스: 시스템 프록시를 거치지 않음
    try:
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", str(e))
        except Exception:
            msg = str(e)
        raise UpstreamError(e.code, msg)
    except (urllib.error.URLError, OSError) as e:
        raise UpstreamError(502, f"연결할 수 없음: {url} ({e})")


class Pipeline:
    """파이프라인 API. 쓰기 요청에는 게이트웨이 토큰과, 게이트웨이가 정한 파이프라인 역할을 붙인다."""

    # 게이트웨이 권한 → 파이프라인 API가 받는 역할
    ROLE_FOR = {"submit": "rtl-engineer", "feedback": "design-lead", "decide": "chip-lead", "spec_decide": "chip-lead"}

    def __init__(self, base: str, token: str | None):
        self.base, self.token = base.rstrip("/"), token

    def get(self, path: str):
        return _call(self.base + path)

    def post(self, path: str, body: dict, action: str):
        return _call(self.base + path, "POST", body, {"X-Role": self.ROLE_FOR[action], "X-Gateway-Token": self.token or ""})


class OpenRig:
    """OpenRig 데몬 API (조회만. 이후 대화 중계의 기반)."""

    def __init__(self, base: str, rig: str = "chip-dept"):
        self.base, self.rig = base.rstrip("/"), rig

    def seats(self) -> dict:
        try:
            health = _call(self.base + "/healthz", timeout=3)
            ps = _call(self.base + "/api/ps", timeout=10)
        except UpstreamError as e:
            return {"available": False, "error": str(e)}
        rigs = ps if isinstance(ps, list) else ps.get("rigs", [])
        rig = next((r for r in rigs if r.get("name") == self.rig), None)
        nodes = []
        if rig is not None:
            rid = rig.get("rigId") or rig.get("id")
            try:
                got = _call(f"{self.base}/api/rigs/{rid}/nodes", timeout=10)
                nodes = got if isinstance(got, list) else got.get("nodes", [])
            except UpstreamError as e:
                return {"available": True, "health": health, "rig": rig, "error": str(e)}
        return {"available": True, "health": health, "rig": rig, "nodes": nodes}
