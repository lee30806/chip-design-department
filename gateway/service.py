"""게이트웨이 업무: 승인함과 승인 기록, 실행 제출과 상세, 판정, 환류, Seat 상태.

승인 다섯 가지는 모두 승인자(approver) 역할의 사람만 결정하고, 결정마다 누가, 언제, SPEC 버전, 실행 ID, 요구사항 ID를 남긴다.

| 승인 | 대상 | 조건 | 결과 |
| --- | --- | --- | --- |
| SPEC 고정 (spec_freeze) | SPEC 작업 공간 | 설계가 고정을 요청함 (검사 통과, 질문 모두 답함) | 그 판(sha)이 고정됨. 실행 제출은 고정된 판으로만 |
| 최종 승인 (final_approval) | 실행 | 실행이 통과함 | |
| RTL Freeze (rtl_freeze) | 실행 | 최종 승인됨 + DV 검증 완료 판정과 PI 구현 가능성 판정이 모두 pass | |
| 기댓값 변경 (expectation_change) | 실행의 승인 대기 항목 (E1 등) | 파이프라인이 Arbiter의 test_wrong을 등록함 | 파이프라인에 결정을 넘기고 실행을 이어 감 |
| SPEC 변경 요청 (spec_change) | 환류 (F0001 등) | Design-lead가 SPEC 변경 요청을 냄 | 파이프라인에 결정을 넘김. 승인이면 영향 모듈만(또는 처음부터) 다시 실행 |

Repair 충돌(repair_conflict)은 승인이 아니라 Design-lead의 결정이다 (design_lead 능력, Seat도 가능). 형제 모듈의 Repair들이 실패 원인을
서로 넘기면 파이프라인이 등록하고, lead가 고칠 모듈을 지정(decision `repair`, `module`)하거나 Architect 재구성(`architect`)을 요청한다.
결정은 승인 기록에 같이 남는다.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from gateway.auth import Accounts
from gateway.clients import OpenRig, Pipeline, UpstreamError
from gateway.db import DB, now
from gateway.perms import APPROVAL_KINDS, LEAD_KINDS, Forbidden, require
from gateway.specws import SpecError, Specs

ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_SCHEMA = json.loads((ROOT / "schema" / "feedback.schema.json").read_text(encoding="utf-8"))


class Conflict(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Gateway:
    def __init__(self, home: Path, pipeline: Pipeline, openrig: OpenRig, store_dir: Path | None = None, provider=None):
        self.home = Path(home)
        self.db = DB(self.home / "gateway.db")
        self.accounts = Accounts(self.db, provider)
        self.specs = Specs(self.db, self.home)
        self.pipeline, self.openrig = pipeline, openrig
        self.store_dir = Path(store_dir) if store_dir else None

    # -- 실행 --
    def runs(self) -> list[dict]:
        out = []
        gw = {r["run_id"]: r for r in self.db.q("SELECT * FROM runs")}
        for r in self.pipeline.get("/runs"):
            out.append({**r, "spec_id": (gw.get(r["run_id"]) or {}).get("spec_id"), "approvals": self._run_approvals(r["run_id"])})
        return out

    def _run_approvals(self, run_id: str) -> dict:
        rows = self.db.q("SELECT kind, decision, by, at FROM approvals WHERE run_id=? ORDER BY id", (run_id,))
        return {k: next((r for r in reversed(rows) if r["kind"] == k), None) for k in ("final_approval", "rtl_freeze")}

    def run(self, run_id: str) -> dict:
        st = self.pipeline.get(f"/runs/{run_id}")
        st["signoffs"] = self.db.q("SELECT kind, decision, by, at, note FROM signoffs WHERE run_id=?", (run_id,))
        st["approvals"] = self.db.q("SELECT * FROM approvals WHERE run_id=? ORDER BY id", (run_id,))
        st["spec_id"] = (self.db.one("SELECT spec_id FROM runs WHERE run_id=?", (run_id,)) or {}).get("spec_id")
        return st

    def _run_dir(self, run_id: str) -> Path:
        if not self.store_dir:
            raise Conflict(404, "파이프라인 저장소 위치를 모름 (--store)")
        d = (self.store_dir / "runs" / run_id).resolve()
        if d.parent != (self.store_dir / "runs").resolve() or not d.exists():
            raise Conflict(404, f"없는 실행: {run_id}")
        return d

    def run_detail(self, run_id: str) -> dict:
        """실행 상세 (읽기 전용): 모듈 트리와 상태, 후보별 진행, 검토 항목, 실패 분류, 에이전트 작업 목록."""
        d = self._run_dir(run_id)
        state = json.loads((d / "state.json").read_text(encoding="utf-8")) if (d / "state.json").exists() else {}
        tree = (state.get("steps") or {}).get("architect") or {}
        top = tree.get("top") or {}
        mods = self.pipeline.get(f"/runs/{run_id}/modules")
        children = []
        for name, l1 in (tree.get("children") or {}).items():
            cands = {k.split("/c")[1]: v for k, v in mods.items() if k.split("/c")[0] == name}
            children.append({"module": name, "role": l1.get("role"), "instance": next(
                (i["name"] for i in top.get("instances", []) if i["module"] == name), None),
                "ports": [p.get("bundle") or p.get("name") for p in l1.get("ports", [])],
                "candidates": [{"c": int(c), "status": v.get("status"), "repairs": v.get("repairs"), "lint": v.get("lint"),
                                "reason": v.get("reason"), "arbiter": v.get("arbiter"), "last_verify": v.get("last_verify"),
                                "pending": v.get("pending")} for c, v in sorted(cands.items())]})
        failures = []
        for k, v in mods.items():
            if v.get("reason") or (v.get("last_verify") and not v["last_verify"].get("ok")):
                failures.append({"candidate": k, "status": v.get("status"), "reason": v.get("reason"),
                                 "last_verify": v.get("last_verify")})
        tasks = []
        for p in sorted((d / "tasks").glob("*.json")):
            t = json.loads(p.read_text(encoding="utf-8"))
            tasks.append({"name": p.stem, "role": t.get("role"), "agent": t.get("agent"), "ok": t.get("ok"),
                          "attempts": t.get("attempts"), "duration_s": t.get("duration_s")})
        review = state.get("review", [])
        by_code: dict[str, int] = {}
        for r in review:
            by_code[r["code"]] = by_code.get(r["code"], 0) + 1
        return {"run_id": run_id, "status": state.get("status"), "top": {"module": top.get("module"),
                                                                          "instances": top.get("instances", []),
                                                                          "connections": top.get("connections", [])},
                "children": children, "chosen": state.get("chosen"), "review": review, "review_counts": by_code,
                "failures": failures, "tasks": tasks, "events": state.get("events", [])[-200:],
                "steps": {k: v for k, v in (state.get("steps") or {}).items() if k.startswith(("integration", "candidate_diffsim"))},
                "tb_history": state.get("tb_history", []), "pending": state.get("pending", [])}

    def run_rtl(self, run_id: str) -> dict:
        """최종 RTL과 소스맵 (줄 → IR 노드)."""
        d = self._run_dir(run_id) / "rtl"
        out = {}
        for sv in sorted(d.glob("*.sv")) if d.exists() else []:
            sm = d / (sv.stem + ".srcmap.json")
            ir = self._run_dir(run_id) / "ir" / (sv.stem + ".ir.json")
            out[sv.name] = {"text": sv.read_text(encoding="utf-8"),
                            "srcmap": json.loads(sm.read_text(encoding="utf-8")) if sm.exists() else [],
                            "ir": json.loads(ir.read_text(encoding="utf-8")) if ir.exists() else None}
        for f in sorted(d.glob("*.sdc")) if d.exists() else []:
            out[f.name] = {"text": f.read_text(encoding="utf-8"), "srcmap": [], "ir": None}
        return out

    def task(self, run_id: str, name: str) -> dict:
        """에이전트 작업 하나: 과제, 출력, 시도별 transcript(실행기의 표준 출력 끝부분)."""
        p = (self._run_dir(run_id) / "tasks" / f"{name}.json")
        if p.parent.resolve() != (self._run_dir(run_id) / "tasks").resolve() or not p.exists():
            raise Conflict(404, f"없는 작업: {name}")
        t = json.loads(p.read_text(encoding="utf-8"))
        wd = Path(t.get("workdir", ""))
        task_md = (wd / "TASK.md").read_text(encoding="utf-8") if (wd / "TASK.md").exists() else None
        outputs = {}
        for rel, path in (t.get("outputs") or {}).items():
            fp = Path(path)
            if fp.exists() and fp.stat().st_size < 300_000:
                outputs[rel] = fp.read_text(encoding="utf-8", errors="replace")
        return {**t, "task_md": task_md, "output_text": outputs}

    def submit_run(self, user: dict, spec_id: str, config: dict | None = None) -> dict:
        require(user, "submit_run")
        s = self.specs.row(spec_id)
        if s["status"] != "frozen":
            raise Conflict(409, "고정된 SPEC으로만 실행을 제출함 (승인함에서 SPEC 고정 승인)")
        md = self.db.one("SELECT markdown FROM spec_versions WHERE spec_id=? AND sha=?", (spec_id, s["frozen_sha"]))["markdown"]
        out = self.pipeline.post("/runs", {"spec": md, "by": user["username"], "config": config or {}}, "submit")
        self.db.x("INSERT INTO runs (run_id, spec_id, spec_sha, by, at) VALUES (?,?,?,?,?)",
                  (out["run_id"], spec_id, s["frozen_sha"], user["username"], now()))
        self.db.audit(user["username"], "run_submit", {"run": out["run_id"], "spec": spec_id, "sha": s["frozen_sha"]})
        return out

    def signoff(self, user: dict, run_id: str, kind: str, decision: str, note: str = "") -> dict:
        """RTL Freeze의 재료: DV 검증 완료 판정(verification), PI 구현 가능성 판정(implementation)."""
        if kind not in ("dv", "pi") or decision not in ("pass", "fail"):
            raise Conflict(400, "kind는 dv 또는 pi, decision은 pass 또는 fail")
        require(user, "signoff_dv" if kind == "dv" else "signoff_pi")
        fa = self._run_approvals(run_id)["final_approval"]
        if not fa or fa["decision"] != "approved":
            raise Conflict(409, "최종 승인된 실행에만 판정을 남김")
        self.db.x("INSERT OR REPLACE INTO signoffs (run_id, kind, decision, by, at, note) VALUES (?,?,?,?,?,?)",
                  (run_id, kind, decision, user["username"], now(), note))
        self.db.audit(user["username"], "signoff", {"run": run_id, "kind": kind, "decision": decision})
        return self.run(run_id)

    # -- 승인함 --
    def pending(self) -> list[dict]:
        items = []
        for s in self.db.q("SELECT * FROM specs WHERE status='freeze_requested'"):
            items.append({"kind": "spec_freeze", "target": s["id"], "title": s["name"], "spec_sha": s["freeze_requested_sha"],
                          "detail": {"requested_by": s["created_by"]}})
        try:
            runs = self.pipeline.get("/runs")
        except UpstreamError:
            runs = []
        for r in runs:
            ap = self._run_approvals(r["run_id"])
            if r["status"] == "pass" and ap["final_approval"] is None:
                items.append({"kind": "final_approval", "target": r["run_id"], "title": r["block"], "run_id": r["run_id"],
                              "spec_sha": r.get("spec_sha256")})
            elif ap["final_approval"] and ap["final_approval"]["decision"] == "approved" and ap["rtl_freeze"] is None:
                so = {x["kind"]: x for x in self.db.q("SELECT * FROM signoffs WHERE run_id=?", (r["run_id"],))}
                items.append({"kind": "rtl_freeze", "target": r["run_id"], "title": r["block"], "run_id": r["run_id"],
                              "spec_sha": r.get("spec_sha256"), "detail": {"signoffs": so,
                                                                            "ready": all(so.get(k, {}).get("decision") == "pass"
                                                                                         for k in ("dv", "pi"))}})
            for p in r.get("pending") or []:
                full = next((x for x in self.pipeline.get(f"/runs/{r['run_id']}/pending") if x["id"] == p), {})
                kind = full.get("kind", "expectation_change")
                keys = ("group", "c", "mods", "chain", "claims", "first_failure", "spec") if kind == "repair_conflict" else \
                    ("verifier", "group", "c", "also", "reason", "proposal", "first_failure")
                items.append({"kind": kind, "target": f"{r['run_id']}:{p}", "title": f"{r['block']} {p}",
                              "run_id": r["run_id"], "spec_sha": r.get("spec_sha256"), "reqs": full.get("reqs"),
                              "detail": {k: full.get(k) for k in keys}})
        try:
            fb = self.pipeline.get("/feedback")
        except UpstreamError:
            fb = []
        decided = {r.get("decides") for r in fb}
        for r in fb:
            if r.get("form") == "spec_change" and r.get("status") == "pending_approval" and r["id"] not in decided:
                items.append({"kind": "spec_change", "target": r["id"], "title": f"SPEC 변경 요청 {r['id']}", "run_id": r.get("run_id"),
                              "spec_sha": r.get("spec_sha256"), "reqs": r.get("reqs"),
                              "detail": {k: r.get(k) for k in ("reason", "source", "by", "spec_diff", "spec_check")}})
        return items

    def decide(self, user: dict, kind: str, target: str, decision: str, note: str = "", module: str | None = None) -> dict:
        """승인과 반려는 승인자 역할의 사람만, Repair 충돌은 Design-lead(design_lead 능력)만 한다. 모든 결정을 기록한다."""
        if kind in LEAD_KINDS:
            require(user, "feedback")
            if decision not in ("repair", "architect"):
                raise Conflict(400, "Repair 충돌의 decision은 repair(고칠 모듈 지정, module 필요) 또는 architect(Architect 재구성)")
        else:
            require(user, "approve")
            if kind not in APPROVAL_KINDS:
                raise Conflict(400, f"모르는 승인 종류: {kind} ({APPROVAL_KINDS + LEAD_KINDS})")
            if decision not in ("approved", "rejected"):
                raise Conflict(400, "decision은 approved 또는 rejected")
        item = next((i for i in self.pending() if i["kind"] == kind and i["target"] == target), None)
        if item is None:
            raise Conflict(409, f"승인함에 없는 항목: {kind} {target} (이미 결정했거나 조건이 안 됨)")
        extra = {}
        if kind == "spec_freeze":
            s = self.specs.row(target)
            if decision == "approved":
                if self.specs.current(target)["sha"] != s["freeze_requested_sha"]:
                    raise Conflict(409, "요청 뒤에 SPEC이 바뀜. 다시 요청해야 함")
                self.db.x("UPDATE specs SET status='frozen', frozen_sha=? WHERE id=?", (s["freeze_requested_sha"], target))
            else:
                self.db.x("UPDATE specs SET status='draft', freeze_requested_sha=NULL WHERE id=?", (target,))
        elif kind == "rtl_freeze" and decision == "approved" and not item["detail"]["ready"]:
            raise Conflict(409, "DV 검증 완료 판정과 PI 구현 가능성 판정이 모두 pass여야 RTL Freeze를 승인함")
        elif kind == "expectation_change":
            run_id, eid = target.split(":", 1)
            extra["pipeline"] = self.pipeline.post(f"/runs/{run_id}/decisions",
                                                   {"ids": [eid], "decision": decision, "by": user["username"], "note": note}, "decide")
        elif kind == "repair_conflict":
            run_id, eid = target.split(":", 1)
            extra["pipeline"] = self.pipeline.post(f"/runs/{run_id}/decisions",
                                                   {"ids": [eid], "decision": decision, "module": module, "by": user["username"],
                                                    "note": note}, "lead_decide")
            if module:
                extra["module"] = module
        elif kind == "spec_change":
            extra["pipeline"] = self.pipeline.post(f"/feedback/{target}/decision",
                                                   {"decision": decision, "by": user["username"], "note": note}, "spec_decide")
        rid = self.db.x("INSERT INTO approvals (kind, target, decision, by, roles, at, spec_sha, run_id, reqs, note, extra) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (kind, target, decision, user["username"], ",".join(user["roles"]), now(), item.get("spec_sha"),
                         item.get("run_id"), json.dumps(item.get("reqs") or []), note, json.dumps(extra, ensure_ascii=False)))
        self.db.audit(user["username"], "approval", {"id": rid, "kind": kind, "target": target, "decision": decision})
        return self.approval(rid)

    def approval(self, aid: int) -> dict:
        r = self.db.one("SELECT * FROM approvals WHERE id=?", (aid,))
        r["reqs"] = json.loads(r["reqs"] or "[]")
        r["extra"] = json.loads(r["extra"] or "{}")
        return r

    def approvals(self) -> list[dict]:
        return [self.approval(r["id"]) for r in self.db.q("SELECT id FROM approvals ORDER BY id DESC")]

    # -- 환류 --
    def feedback(self, user: dict, body: dict) -> dict:
        """환류 양식. 형태 네 가지의 스키마만 받는다 (자유 텍스트로 수정을 요청하는 경로는 없음). Design-lead만."""
        require(user, "feedback")
        body = {**body, "by": user["username"]}
        err = best_match(Draft202012Validator(FEEDBACK_SCHEMA).iter_errors(body))
        if err is not None:
            raise Conflict(400, f"환류 양식 오류: {err.message}")
        out = self.pipeline.post("/feedback", body, "feedback")
        self.db.audit(user["username"], "feedback", {"id": out.get("id"), "form": body["form"], "run": body.get("run_id")})
        return out

    def seats(self) -> dict:
        return self.openrig.seats()


__all__ = ["Gateway", "Conflict", "Forbidden", "SpecError", "UpstreamError"]
