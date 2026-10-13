"""파이프라인 API의 CLI. HTTP API와 같은 일을 저장소에 바로 한다.

    python3 -m pipeline.api serve [--host 127.0.0.1] [--port 8740]
    python3 -m pipeline.api submit <spec.md> --by <이름> [--role rtl-engineer] [--config '{"author_count": 2}'] [--cells ...]
    python3 -m pipeline.api runs | status <id> | review <id> | report <id> | pending <id> | history [<id>]
    python3 -m pipeline.api resume <id>
    python3 -m pipeline.api decide <id> <E1>... --decision approved|rejected --by <이름> [--role rtl-engineer] [--note ...]
    python3 -m pipeline.api feedback <body.json> [--role design-lead]
    python3 -m pipeline.api spec-decide <F0001> --decision approved|rejected --by <이름> [--role chip-lead]
    python3 -m pipeline.api watchdog [--hours 24]

저장소 위치는 --store 또는 CHIPDEPT_STORE (기본 build/store).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.api.store import DEFAULT_STORE, ApiError, Store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pipeline.api", description="파이프라인 API")
    ap.add_argument("--store", type=Path, default=DEFAULT_STORE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8740)
    s.add_argument("--roles", type=Path, help="역할 설정 (기본 config/roles.json)")
    s.add_argument("--no-isolate", action="store_true", help="에이전트를 격리하지 않음 (가짜 agent를 쓰는 시험 전용)")
    s.add_argument("--token-file", type=Path, help="게이트웨이 토큰 파일. 있으면 쓰기 요청은 이 토큰이 있어야 함 (CHIPDEPT_API_TOKEN도 됨)")
    s = sub.add_parser("submit")
    s.add_argument("spec", type=Path)
    s.add_argument("--by", required=True)
    s.add_argument("--role", default="rtl-engineer")
    s.add_argument("--config", default="{}")
    s.add_argument("--cells", nargs="*")
    for name in ("status", "review", "report", "pending", "resume", "modules"):
        sub.add_parser(name).add_argument("run_id")
    sub.add_parser("runs")
    sub.add_parser("history").add_argument("run_id", nargs="?")
    s = sub.add_parser("decide")
    s.add_argument("run_id")
    s.add_argument("ids", nargs="+")
    s.add_argument("--decision", required=True, choices=["approved", "rejected", "repair", "architect"])
    s.add_argument("--module", help="repair 결정에서 고칠 모듈")
    s.add_argument("--by", required=True)
    s.add_argument("--role", default="rtl-engineer")
    s.add_argument("--note", default="")
    s = sub.add_parser("feedback")
    s.add_argument("body", type=Path)
    s.add_argument("--role", default="design-lead")
    s = sub.add_parser("spec-decide")
    s.add_argument("fid")
    s.add_argument("--decision", required=True, choices=["approved", "rejected"])
    s.add_argument("--by", required=True)
    s.add_argument("--role", default="chip-lead")
    s.add_argument("--note", default="")
    s = sub.add_parser("watchdog")
    s.add_argument("--hours", type=float, default=24.0)
    a = ap.parse_args(argv)
    store = Store(a.store, base_roles=getattr(a, "roles", None), isolate=not getattr(a, "no_isolate", False))
    try:
        if a.cmd == "serve":
            from pipeline.api.server import serve
            import os
            token = a.token_file.read_text(encoding="utf-8").strip() if a.token_file else os.environ.get("CHIPDEPT_API_TOKEN")
            httpd = serve(store, a.host, a.port, token=token or None)
            print(f"파이프라인 API: http://{a.host}:{a.port} (저장소 {store.root})", flush=True)
            httpd.serve_forever()
            return 0
        out = {
            "submit": lambda: store.submit(a.spec.read_text(encoding="utf-8"), a.by, a.role, json.loads(a.config), a.cells),
            "runs": store.runs, "status": lambda: store.status(a.run_id), "review": lambda: store.review_items(a.run_id),
            "report": lambda: store.report(a.run_id), "pending": lambda: store.pending(a.run_id),
            "modules": lambda: store.modules(a.run_id), "resume": lambda: store.start(a.run_id),
            "history": lambda: store.history(a.run_id),
            "decide": lambda: store.decide(a.run_id, a.ids, a.decision, a.by, a.role, a.note, module=a.module),
            "feedback": lambda: store.feedback(json.loads(a.body.read_text(encoding="utf-8")), a.role),
            "spec-decide": lambda: store.decide_spec_change(a.fid, a.decision, a.by, a.role, a.note),
            "watchdog": lambda: store.watchdog(a.hours),
        }[a.cmd]()
    except ApiError as e:
        print(json.dumps({"error": str(e), "status": e.status}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
