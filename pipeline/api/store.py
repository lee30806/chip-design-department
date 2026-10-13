"""파이프라인 API의 저장소: 실행 제출과 조회, 사람 결정, 환류 처리, 이력, 교착 방지.

부서 계층과는 세 인터페이스(실행 제출, 상태와 결과 조회, 환류)로만 만난다. RTL이나 IR을 직접 고치는 경로는 없다.

    <store>/runs/<run_id>/        스케줄러 실행 디렉터리 (state.json 등) + meta.json, roles.json, spec.md, seed.json, scheduler.log
    <store>/feedback.jsonl        환류 이력 (실행 ID, 요구사항 ID, 제출자, 결과)
    <store>/generator_bugs.jsonl  생성기 버그 (LLM으로 보내지 않음. Emitter 템플릿을 사람이 고침)
    <store>/notifications.jsonl   사람에게 알릴 것 (교착 방지로 멈춤, 인터페이스 변경 필요 등)
    <store>/config.json           설정 변경 환류로 바뀐 설정. 다음에 제출하는 실행부터 반영

실행은 별도 프로세스(`python -m pipeline.scheduler.run`)로 돌린다. 멈추거나 승인을 기다리면 `resume`으로 같은 실행을 이어 간다.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from pipeline.agents.runner import load_agents
from pipeline.classifier.classify import classify_findings
from pipeline.feedback import reports, spec_diff
from pipeline.scheduler import approve

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = Path(os.environ.get("CHIPDEPT_STORE", ROOT / "build" / "store"))
FEEDBACK_SCHEMA = json.loads((ROOT / "schema" / "feedback.schema.json").read_text(encoding="utf-8"))
RERUN_LIMIT = 3            # 같은 Block Top에서 환류에 따른 재실행이 이만큼 되면 멈추고 알린다
STALL_HOURS = 24.0         # 이 시간 동안 진행(상태 파일 갱신)이 없으면 멈추고 알린다

# 역할별 권한 (P7 게이트웨이에서 인증을 붙이기 전까지 요청이 밝힌 역할로 판단)
ROLES_SUBMIT = {"rtl-engineer", "chip-lead"}
ROLES_FEEDBACK = {"design-lead"}
ROLES_DECIDE = {"rtl-engineer", "chip-lead", "design-lead"}
ROLES_LEAD_DECIDE = {"design-lead"}          # Repair 충돌: 고칠 모듈 지정 또는 Architect 재구성
ROLES_SPEC_APPROVE = {"chip-lead", "rtl-engineer"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _require(role: str | None, allowed: set[str], what: str) -> None:
    if role not in allowed:
        raise ApiError(403, f"{what}은(는) {sorted(allowed)} 역할만 할 수 있음 (요청 역할: {role})")


class Store:
    def __init__(self, root: Path = DEFAULT_STORE, python: str = sys.executable, base_roles: Path | None = None,
                 isolate: bool = True):
        self.root = Path(root).resolve()
        self.isolate = isolate   # False는 가짜 agent를 쓰는 시험에서만
        (self.root / "runs").mkdir(parents=True, exist_ok=True)
        self.python = python
        self.base_roles = Path(base_roles or ROOT / "config" / "roles.json")
        self.lock = threading.Lock()
        self.procs: dict[str, subprocess.Popen] = {}

    # -- 파일 --
    def run_dir(self, run_id: str) -> Path:
        d = self.root / "runs" / run_id
        if not (d / "meta.json").exists():
            raise ApiError(404, f"없는 실행: {run_id}")
        return d

    def meta(self, run_id: str) -> dict:
        return json.loads((self.run_dir(run_id) / "meta.json").read_text(encoding="utf-8"))

    def _save_meta(self, run_id: str, meta: dict) -> None:
        p = self.root / "runs" / run_id / "meta.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)

    def _append(self, name: str, rec: dict) -> None:
        with self.lock, open(self.root / name, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _read_jsonl(self, name: str) -> list[dict]:
        p = self.root / name
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []

    def notify(self, kind: str, message: str, run_id: str | None = None) -> dict:
        rec = {"at": _now(), "kind": kind, "run_id": run_id, "message": message}
        self._append("notifications.jsonl", rec)
        return rec

    def config(self) -> dict:
        p = self.root / "config.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    # -- 실행 제출 --
    def _roles_for(self, config: dict) -> dict:
        """기본 역할 설정에 설정 변경(저장소 설정 → 제출 설정 순)을 덮는다."""
        base = json.loads(self.base_roles.read_text(encoding="utf-8"))
        agents = base["agents"]
        base["agents"] = str((self.base_roles.parent.parent / agents).resolve()) if not Path(agents).is_absolute() else agents
        for cfg in (self.config(), config):
            if "author_count" in cfg:
                base["roles"]["author"]["count"] = cfg["author_count"]
            if "author_langs" in cfg:   # Author 후보마다 조각 언어 (sv, py)
                base["roles"]["author"]["langs"] = cfg["author_langs"]
            if "verifier_count" in cfg:
                base["roles"]["verifier"]["count"] = cfg["verifier_count"]
            for k in ("budget_agent_runs", "repair_per_candidate"):
                if k in cfg:
                    base["limits"][k] = cfg[k]
            for role, agent in (cfg.get("agents") or {}).items():
                if role not in base["roles"]:
                    raise ApiError(400, f"모르는 역할: {role}")
                base["roles"][role]["agent"] = agent
        known = {a.name for a in load_agents(Path(base["agents"]))}
        unknown = sorted({c["agent"] for c in base["roles"].values()} - known)
        if unknown:
            raise ApiError(400, f"agents 파일에 없는 에이전트: {unknown}")
        return base

    def submit(self, spec_text: str, by: str, role: str | None, config: dict | None = None, cells: list[str] | None = None,
               start: bool = True, _parent: str | None = None, _kind: str = "initial", _seed: dict | None = None) -> dict:
        """실행 제출: SPEC 원문과 설정(모델, 후보 개수, 예산)을 받고 실행 ID를 돌려준다."""
        if _parent is None:
            _require(role, ROLES_SUBMIT, "실행 제출")
        config = config or {}
        from pipeline.spec.parse import parse
        try:
            module = parse(spec_text).module or "block"
        except Exception as e:  # SPEC 형식 오류도 실행에서 SPEC 검사로 걸리지만, 이름은 여기서 필요하다
            raise ApiError(400, f"SPEC을 읽을 수 없음: {e}")
        run_id = f"{module}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
        d = self.root / "runs" / run_id
        d.mkdir(parents=True)
        (d / "spec.md").write_text(spec_text, encoding="utf-8")
        roles = self._roles_for(config)
        (d / "roles.json").write_text(json.dumps(roles, ensure_ascii=False, indent=1), encoding="utf-8")
        parent_meta = self.meta(_parent) if _parent else None
        lineage = {"root": parent_meta["lineage"]["root"] if parent_meta else run_id,
                   "depth": parent_meta["lineage"]["depth"] + 1 if parent_meta else 0, "parent": _parent}
        meta = {"run_id": run_id, "block": module, "by": by, "created": _now(), "spec_sha256": _sha(d / "spec.md"),
                "config": config, "cells": cells or (parent_meta or {}).get("cells") or [], "kind": _kind,
                "lineage": lineage, "pid": None, "halted": None}
        if _seed:
            (d / "seed.json").write_text(json.dumps(_seed, ensure_ascii=False, indent=1), encoding="utf-8")
        self._save_meta(run_id, meta)
        if start:
            self.start(run_id)
        return self.status(run_id)

    def start(self, run_id: str) -> dict:
        """실행(또는 이어서 실행)을 별도 프로세스로 시작한다."""
        d, meta = self.run_dir(run_id), self.meta(run_id)
        if meta.get("halted"):
            raise ApiError(409, f"멈춘 실행: {meta['halted']}")
        if self._alive(meta):
            raise ApiError(409, "이미 실행 중")
        cmd = [self.python, "-m", "pipeline.scheduler.run", str(d / "spec.md"), "--run-dir", str(d), "--roles", str(d / "roles.json")]
        if meta.get("cells"):
            cmd += ["--cells", *meta["cells"]]
        if (d / "seed.json").exists():
            cmd += ["--seed", str(d / "seed.json")]
        if not self.isolate:
            cmd.append("--no-isolate")
        log = open(d / "scheduler.log", "a", encoding="utf-8")
        # 새 세션 + 표준 입력 없음: API 서버(또는 그 터미널)를 다시 시작해도 실행은 영향을 받지 않는다
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                env={**{k: v for k, v in os.environ.items() if k != "PYTHONHOME"}, "PYTHONPATH": str(ROOT)})
        self.procs[run_id] = proc
        meta["pid"], meta["started"] = proc.pid, _now()
        self._save_meta(run_id, meta)
        return {"run_id": run_id, "pid": proc.pid}

    def _alive(self, meta: dict) -> bool:
        proc = self.procs.get(meta["run_id"])
        if proc is not None:
            return proc.poll() is None
        pid = meta.get("pid")
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def wait(self, run_id: str, timeout: float | None = None) -> dict:
        proc = self.procs.get(run_id)
        if proc is not None:
            proc.wait(timeout)
        return self.status(run_id)

    # -- 조회 --
    def _state(self, run_id: str) -> dict:
        p = self.run_dir(run_id) / "state.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def status(self, run_id: str) -> dict:
        meta, st = self.meta(run_id), self._state(run_id)
        alive = self._alive(meta)
        status = meta["halted"] and "halted" or st.get("status") or ("starting" if alive else "not_started")
        if status == "running" and not alive:
            status = "stopped"   # 프로세스가 끝났는데 상태가 실행 중: 강제로 멈춘 것. resume으로 이어 간다
        return {"run_id": run_id, "block": meta["block"], "status": status, "process": "running" if alive else "stopped",
                "kind": meta["kind"], "lineage": meta["lineage"], "created": meta["created"], "by": meta["by"],
                "spec_sha256": meta["spec_sha256"], "agent_runs": st.get("agent_runs", 0), "chosen": st.get("chosen"),
                "halted": meta.get("halted"),
                "pending": [p["id"] for p in approve.pending(self.run_dir(run_id))] if st else []}

    def runs(self) -> list[dict]:
        return [self.status(p.name) for p in sorted((self.root / "runs").iterdir()) if (p / "meta.json").exists()]

    def modules(self, run_id: str) -> dict:
        d = self.run_dir(run_id) / "modules"
        return {p.stem.replace("__", "/"): {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                                            if k not in ("ir", "hashes", "history")}
                for p in sorted(d.glob("*.json"))} if d.exists() else {}

    def review_items(self, run_id: str) -> list[dict]:
        return self._state(run_id).get("review", [])

    def report(self, run_id: str) -> dict:
        p = self.run_dir(run_id) / "report.json"
        if not p.exists():
            raise ApiError(404, "보고서가 아직 없음")
        return json.loads(p.read_text(encoding="utf-8"))

    def rtl(self, run_id: str) -> dict:
        """최종 RTL (통과한 실행만). 읽기 전용으로 내준다."""
        if self.status(run_id)["status"] != "pass":
            raise ApiError(409, "통과한 실행만 RTL을 내줌")
        d = self.run_dir(run_id) / "rtl"
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.sv"))}

    # -- 사람 결정 (기댓값 수정안, Repair 충돌) --
    def pending(self, run_id: str) -> list[dict]:
        return approve.pending(self.run_dir(run_id))

    def decide(self, run_id: str, ids: list[str], decision: str, by: str, role: str | None, note: str = "",
               resume: bool = True, module: str | None = None) -> list[dict]:
        kinds = {p["kind"] for p in self.pending(run_id) if p["id"] in ids}
        if "repair_conflict" in kinds:
            _require(role, ROLES_LEAD_DECIDE, "Repair 충돌 결정")
        if not kinds or kinds - {"repair_conflict"}:
            _require(role, ROLES_DECIDE, "기댓값 수정 결정")
        try:
            out = approve.decide(self.run_dir(run_id), ids, decision, by, note, module=module)
        except ValueError as e:
            raise ApiError(400, str(e))
        if resume and not self.pending(run_id) and not self._alive(self.meta(run_id)):
            self.start(run_id)
        return out

    # -- 환류 --
    def feedback(self, body: dict, role: str | None) -> dict:
        """환류 네 형태. 스키마를 검사하고 Design-lead의 제출만 받는다. 모든 환류는 이력에 남는다."""
        _require(role, ROLES_FEEDBACK, "환류 제출")
        err = best_match(Draft202012Validator(FEEDBACK_SCHEMA).iter_errors(body))
        if err is not None:
            raise ApiError(400, f"환류 형식 오류: {err.message}")
        fid = f"F{len(self._read_jsonl('feedback.jsonl')) + 1:04d}"
        rec = {"id": fid, "at": _now(), "form": body["form"], "by": body["by"], "run_id": body.get("run_id"),
               "note": body.get("note")}
        handler = {"check_report": self._fb_check_report, "spec_change": self._fb_spec_change,
                   "generator_bug": self._fb_generator_bug, "config_change": self._fb_config_change}[body["form"]]
        rec |= handler(body, fid)
        self._append("feedback.jsonl", rec)
        return rec

    def history(self, run_id: str | None = None) -> list[dict]:
        recs = self._read_jsonl("feedback.jsonl")
        if run_id is None:
            return recs
        root = self.meta(run_id)["lineage"]["root"]
        ids = {r["run_id"] for r in self.runs() if r["lineage"]["root"] == root}
        return [r for r in recs if r.get("run_id") in ids or r.get("new_run") in ids]

    def _reruns(self, root: str) -> int:
        return sum(1 for r in self.runs() if r["lineage"]["root"] == root and r["kind"] != "initial")

    def _rerun_allowed(self, run_id: str, why: str) -> None:
        """교착 방지: 같은 Block Top에서 환류에 따른 재실행이 RERUN_LIMIT회에 이르면 멈추고 알린다."""
        meta = self.meta(run_id)
        n = self._reruns(meta["lineage"]["root"])
        if n >= RERUN_LIMIT:
            self.notify("rerun_limit", f"{meta['block']}: 환류 재실행이 {n}회에 이름. 더 돌리지 않고 사람에게 넘김 ({why})", run_id)
            raise ApiError(409, f"재실행 상한 {RERUN_LIMIT}회에 이름. 사람 검토가 필요함")

    def _finished(self, run_id: str) -> None:
        if self.status(run_id)["status"] != "pass":
            raise ApiError(409, "통과한 실행에만 환류를 받음")

    def _fb_check_report(self, body: dict, fid: str) -> dict:
        run_id = body["run_id"]
        self._finished(run_id)
        try:
            findings = reports.parse_named(body["format"], body["report"])
        except reports.FormatError as e:
            raise ApiError(400, str(e))
        d = self.run_dir(run_id)
        maps = {p.name.removesuffix(".srcmap.json"): json.loads(p.read_text(encoding="utf-8"))
                for p in (d / "rtl").glob("*.srcmap.json")}
        roles = {p.name.removesuffix(".ir.json"): json.loads(p.read_text(encoding="utf-8")).get("role", "module")
                 for p in (d / "ir").glob("*.ir.json")}
        cls = classify_findings(findings, maps, roles)
        to_repair: dict[str, list[dict]] = {}
        out = {"format": body["format"], "source": body.get("source"), "findings": len(findings), "classified": []}
        for c in cls:
            item = {"type": c.type, "route": c.route, "module": c.module, "node": c.node, "message": c.message[:300]}
            out["classified"].append(item)
            if c.route == "repair" and c.module:
                to_repair.setdefault(c.module, []).append(item)
            elif c.type == "lint_skeleton":
                self._append("generator_bugs.jsonl", {"at": _now(), "from_feedback": fid, "run_id": run_id, "module": c.module,
                                                      "message": c.message, "status": "open"})
            elif c.type == "interface_change":
                self.notify("interface_change", f"{c.module}: 외부 리포트를 고치려면 L1 변경이 필요함 ({c.message[:200]})", run_id)
        if to_repair:
            self._rerun_allowed(run_id, f"검사 실패 리포트 {fid}")
            new = self.submit((d / "spec.md").read_text(encoding="utf-8"), body["by"], None, self.meta(run_id)["config"],
                              _parent=run_id, _kind="external_repair",
                              _seed={"parent": str(d), "kind": "external_repair", "failures": to_repair})
            out["new_run"] = new["run_id"]
        out["result"] = "repair" if to_repair else ("generator_bug" if any(c.type == "lint_skeleton" for c in cls) else "no_action")
        return out

    def _fb_spec_change(self, body: dict, fid: str) -> dict:
        """SPEC 개정은 사람 승인 뒤 반영한다. 여기서는 영향을 계산해 승인 대기로 둔다."""
        run_id = body["run_id"]
        self._finished(run_id)
        d = self.run_dir(run_id)
        pend = self.root / "spec_changes" / fid
        pend.mkdir(parents=True)
        (pend / "spec.md").write_text(body["spec"], encoding="utf-8")
        try:
            sd = spec_diff.diff(d / "spec.md", pend / "spec.md")
        except Exception as e:
            raise ApiError(400, f"새 SPEC을 읽을 수 없음: {e}")
        return {"status": "pending_approval", "reason": body["reason"], "source": body.get("source"),
                "reqs": spec_diff.affected_reqs(sd), "spec_diff": sd, "spec_sha256": _sha(pend / "spec.md")}

    def decide_spec_change(self, fid: str, decision: str, by: str, role: str | None, note: str = "") -> dict:
        """SPEC 변경 요청 승인. 승인하면 L1이 같으면 영향 모듈만 다시, 다르면 처음부터 다시 실행한다."""
        _require(role, ROLES_SPEC_APPROVE, "SPEC 변경 승인")
        recs = self._read_jsonl("feedback.jsonl")
        rec = next((r for r in recs if r["id"] == fid and r["form"] == "spec_change"), None)
        if rec is None:
            raise ApiError(404, f"없는 SPEC 변경 요청: {fid}")
        if any(r.get("decides") == fid for r in recs):
            raise ApiError(409, f"이미 결정된 요청: {fid}")
        if decision not in ("approved", "rejected"):
            raise ApiError(400, "결정은 approved 또는 rejected")
        out = {"id": f"{fid}-D", "at": _now(), "form": "spec_change_decision", "decides": fid, "decision": decision, "by": by,
               "note": note, "run_id": rec["run_id"], "reqs": rec["reqs"]}
        if decision == "approved":
            self._rerun_allowed(rec["run_id"], f"SPEC 변경 {fid}")
            parent = self.run_dir(rec["run_id"])
            new_spec = (self.root / "spec_changes" / fid / "spec.md").read_text(encoding="utf-8")
            # 영향은 결정할 때 다시 계산한다 (요청 뒤 SPEC 해석이 바뀌었을 수 있음)
            sd = spec_diff.diff(parent / "spec.md", self.root / "spec_changes" / fid / "spec.md")
            out["reqs"], out["spec_diff"] = spec_diff.affected_reqs(sd), sd
            if spec_diff.full_rerun(sd):
                new = self.submit(new_spec, by, None, self.meta(rec["run_id"])["config"], _parent=rec["run_id"], _kind="spec_change_full")
            else:
                new = self.submit(new_spec, by, None, self.meta(rec["run_id"])["config"], _parent=rec["run_id"], _kind="spec_change",
                                  _seed={"parent": str(parent), "kind": "spec_change", "old_spec": str(parent / "spec.md"),
                                         "spec_diff": sd})
            out["new_run"] = new["run_id"]
        self._append("feedback.jsonl", out)
        return out

    def _fb_generator_bug(self, body: dict, fid: str) -> dict:
        self._append("generator_bugs.jsonl", {"at": _now(), "from_feedback": fid, "run_id": body.get("run_id"),
                                              "message": body["description"], "evidence": body.get("evidence"), "status": "open"})
        return {"result": "generator_bug", "description": body["description"]}

    def _fb_config_change(self, body: dict, fid: str) -> dict:
        self._roles_for(body["config"])   # 모르는 역할 등은 여기서 거부
        cfg = self.config() | body["config"]
        (self.root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"result": "config_changed", "config": cfg}

    def generator_bugs(self) -> list[dict]:
        return self._read_jsonl("generator_bugs.jsonl")

    def notifications(self) -> list[dict]:
        return self._read_jsonl("notifications.jsonl")

    # -- 교착 방지 --
    def watchdog(self, stall_hours: float = STALL_HOURS, now: float | None = None) -> list[dict]:
        """진행(상태 파일 갱신)이 stall_hours 동안 없는 실행을 멈추고 알린다."""
        now = now or time.time()
        out = []
        for r in self.runs():
            if r["status"] in ("pass", "failed", "halted", "spec_rejected"):
                continue
            d = self.run_dir(r["run_id"])
            last = max((p.stat().st_mtime for p in [d / "state.json", d / "meta.json"] if p.exists()), default=now)
            if now - last < stall_hours * 3600:
                continue
            meta = self.meta(r["run_id"])
            if self._alive(meta) and meta.get("pid"):
                try:
                    os.killpg(meta["pid"], signal.SIGTERM)
                except OSError:
                    pass
            meta["halted"] = f"{stall_hours:g}시간 동안 진행 없음"
            self._save_meta(r["run_id"], meta)
            out.append(self.notify("stalled", f"{meta['block']}: {meta['halted']} (상태 {r['status']}). 멈추고 사람에게 넘김",
                                   r["run_id"]))
        return out
