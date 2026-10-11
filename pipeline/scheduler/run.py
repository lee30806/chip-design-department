"""파이프라인 스케줄러. 제어 흐름은 결정론적이고, 에이전트는 작업 단위로 headless 실행한다.

    SPEC 검사 → Block Top L1 → Architect(모듈 트리, 동결) → Verifier 후보(참조 모델, 테스트)와 차분 검사
    → 모듈마다 Author 후보 → 같은 번호 후보끼리 묶어 [Validator → 방출 → E1 → E2(모든 Verifier의 테스트)]
       실패: 분류 → 원인 후보 모듈(불일치 출력을 구동하는 인스턴스)의 Repair(patch) → Validator부터 다시
             (상한, IR 해시 진동 감지. Repair가 형제 모듈을 지목하면 그 모듈의 Repair로 넘김)
             일부 Verifier에서만 실패 → Arbiter (rtl_wrong이면 Repair, test_wrong이면 사람 승인 대기, 모호하면 검토 항목)
    → 묶음 선택(모든 모듈 통과, Repair 적음, lint 적음)과 Author 후보 간 차분 검사 → 통합(E1, E2) → 최종 보고서

상태는 단계마다 `state.json`에 저장한다. 병렬로 도는 후보와 에이전트 작업은 각자 파일(`modules/`, `tasks/`)에 저장한다. 강제로 멈춘 뒤 같은 명령으로 다시 실행하면 끝난 단계와 끝난 에이전트 작업은
건너뛰고 이어서 실행한다. 에이전트 작업 디렉터리는 저장소 밖에 두고 서로 격리한다.

    python3 -m pipeline.scheduler.run <spec.md> --run-dir <dir> [--roles config/roles.json] [--cells <표준 셀.sv>...]
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline.agents import arbiter, architect, author, repair, roles as roles_mod, verifier
from pipeline.agents.task import RUNS, ROOT, QuotaExceeded, TaskResult, run_task
from pipeline.classifier.classify import classify_findings
from pipeline.emitter.sv import emit
from pipeline.ir.model import Module
from pipeline.patch.apply import apply, ir_hash
from pipeline.spec import check as spec_check
from pipeline.spec.l1 import block_top_l1
from pipeline.spec.parse import load as load_spec
from pipeline.tb.gen import harness_source, trace_names
from pipeline.tb.report import mismatch_report
from pipeline.validator.checks import errors, validate
from pipeline.validator.structure import frozen_scope, v11_frozen
from pipeline.verify.run import lint, sim

STUB_CELLS = [ROOT / "pipeline" / "emitter" / "stubs" / "sync_2ff.sv"]


class BudgetExceeded(RuntimeError):
    pass


class Run:
    def __init__(self, run_dir: Path, spec: Path, roles: roles_mod.Roles, cells: list[Path] | None = None,
                 isolate: bool = True, seeds: list[int] | None = None):
        self.dir, self.spec_path, self.roles = Path(run_dir).resolve(), Path(spec).resolve(), roles
        self.cells, self.isolate, self.seeds = cells if cells is not None else STUB_CELLS, isolate, seeds or [1]
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "modules").mkdir(exist_ok=True)
        (self.dir / "tasks").mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.state_path = self.dir / "state.json"
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.event("resume", "저장된 상태에서 이어서 실행")
        else:
            self.state = {"spec": str(self.spec_path), "status": "running", "steps": {}, "review": [], "events": [],
                          "agent_runs": 0}

    # -- 기록 --
    @staticmethod
    def _write(path: Path, obj) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)  # 중간에 멈춰도 상태 파일이 깨지지 않게

    def save(self) -> None:
        with self.lock:
            self._write(self.state_path, self.state)

    def event(self, kind: str, msg: str) -> None:
        with self.lock:
            self.state["events"].append({"t": time.strftime("%H:%M:%S"), "kind": kind, "msg": msg})

    def review(self, code: str, msg: str, where: str = "", source: str = "scheduler") -> None:
        item = {"code": code, "severity": "review", "where": where, "message": msg, "source": source}
        with self.lock:
            if item not in self.state["review"]:
                self.state["review"].append(item)

    def mod_state(self, key: str) -> dict:
        p = self.dir / "modules" / f"{key.replace('/', '__')}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else \
            {"status": "author", "repairs": 0, "hashes": [], "history": []}

    def save_mod(self, key: str, st: dict) -> None:
        self._write(self.dir / "modules" / f"{key.replace('/', '__')}.json", st)

    def modules(self) -> dict[str, dict]:
        return {p.stem.replace("__", "/"): json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((self.dir / "modules").glob("*.json"))}

    def done(self, step: str):
        return self.state["steps"].get(step)

    def finish_step(self, step: str, result) -> None:
        self.state["steps"][step] = result
        self.save()

    # -- 에이전트 작업 (끝난 작업은 다시 실행하지 않음) --
    def agent(self, role: str, task, check) -> TaskResult:
        rec = self.dir / "tasks" / f"{task.name.replace('/', '__')}.json"
        if rec.exists():
            return TaskResult(**json.loads(rec.read_text(encoding="utf-8")))
        with self.lock:
            if self.state["agent_runs"] >= self.roles.limits.get("budget_agent_runs", 10**9):
                raise BudgetExceeded(f"에이전트 실행 예산 {self.roles.limits['budget_agent_runs']}회를 다 씀")
        task.isolate = self.isolate
        work = self.dir / "work" / task.name.replace("/", "__") if not self.isolate else \
            RUNS / self.dir.name / task.name.replace("/", "__")
        res = run_task(self.roles.agents[role], task, work, check=check, retries=self.roles.limits.get("agent_retries", 1),
                       run_root=RUNS if self.isolate else None)
        with self.lock:
            self.state["agent_runs"] += res.attempts
        self._write(rec, res.to_dict())
        self.event("agent", f"{task.name}: {'통과' if res.ok else '실패'} ({res.duration_s}s, {res.attempts}회)")
        self.save()
        return res

    # -- 단계 --
    def step_spec(self) -> bool:
        if (s := self.done("spec")) is not None:
            return s["gate"] == "pass"
        res = spec_check.run(load_spec(self.spec_path))
        for i in res["review"]:
            self.review(i["code"], i["message"], i["where"], i["source"])
        self.finish_step("spec", {"gate": res["gate"], "errors": [i for i in res["issues"] if i["severity"] == "error"]})
        return res["gate"] == "pass"

    def step_architect(self) -> dict | None:
        if (s := self.done("architect")) is not None:
            return s
        top_l1, _ = block_top_l1(load_spec(self.spec_path))
        res = self.agent("architect", architect.make_task("architect", top_l1, self.spec_path), architect.check(top_l1))
        if not res.ok:
            self.finish_step("architect", None)
            return None
        top_ir, children, assumptions = architect.read_tree(Path(res.workdir), top_l1["module"])
        for a in assumptions:
            self.review("ASSUMPTION", a, "architect", "architect")
        lib = {n: Module(c) for n, c in children.items()} | {top_ir["module"]: Module(top_ir)}
        tree = {"top": top_ir, "children": children, "frozen": frozen_scope(lib), "assumptions": assumptions}
        (self.dir / "ir").mkdir(exist_ok=True)
        for n, ir in [(top_ir["module"], top_ir), *children.items()]:
            (self.dir / "ir" / f"{n}.l1.json").write_text(json.dumps(ir, ensure_ascii=False, indent=1), encoding="utf-8")
        self.finish_step("architect", tree)
        return tree

    def step_verifiers(self, top_ir: dict) -> list[str]:
        """Verifier 후보들의 테스트 파일. Block Top의 L1만 준다 (L2, L3, RTL은 없음)."""
        if (s := self.done("verifiers")) is not None:
            return s
        l1 = {k: top_ir[k] for k in ("module", "role", "params", "domains", "ports") if k in top_ir}
        names = [f"verifier/v{k}" for k in range(self.roles.counts.get("verifier", 1))]
        with ThreadPoolExecutor(len(names)) as ex:
            results = list(ex.map(lambda n: self.agent("verifier", verifier.make_task(n, l1, self.spec_path),
                                                       verifier.check(l1)), names))
        tbs = [r.outputs[verifier.out_rel(l1["module"])] for r in results if r.ok]
        for w in self.roles.warnings():
            self.review("MODEL_FAMILY", w, "roles")
        if len(tbs) >= 2:
            hdir = self.dir / "harness"
            hdir.mkdir(exist_ok=True)
            (hdir / f"{l1['module']}_harness.py").write_text(harness_source(Module(l1)), encoding="utf-8")
            try:
                diff = verifier_diff(tbs, l1, harness_dir=hdir)
            except ImportError as e:
                diff = None
                self.review("VERIFIER_DIFF_SKIPPED", f"참조 모델을 불러올 수 없어 Verifier 간 차분 검사를 못 함: {e}", "verifier")
            if diff:
                self.review("VERIFIER_DIFF", f"참조 모델끼리 같은 입력에 다른 출력을 냄: {diff}. SPEC 모호함 또는 한쪽 모델 오류",
                            "verifier")
        self.finish_step("verifiers", tbs)
        return tbs

    # -- 검증 --
    def verify(self, lib: dict[str, dict], top: str, tbs: list[str], tag: str) -> dict:
        """방출 → E1 → E2(Verifier 테스트마다). 결과와 실패 리포트를 돌려준다."""
        out = self.dir / "verify" / tag
        rtl = out / "rtl"
        rtl.mkdir(parents=True, exist_ok=True)
        mods = {n: Module(r) for n, r in lib.items()}
        files, maps = list(self.cells), {}
        for n, m in mods.items():
            e = emit(m, mods)
            (rtl / f"{n}.sv").write_text(e.text, encoding="utf-8")
            files.append(rtl / f"{n}.sv")
            maps[n] = e.sourcemap
        roles = {n: m.role for n, m in mods.items()}
        e1 = lint(files, top)
        e1c = classify_findings(e1.findings, maps, roles)
        top_m = mods[top]
        hdir, tdir = out / "harness", out / "verify_only"
        hdir.mkdir(exist_ok=True)
        tdir.mkdir(exist_ok=True)
        (hdir / f"{top}_harness.py").write_text(harness_source(top_m), encoding="utf-8")
        (tdir / f"{top}_trace.json").write_text(json.dumps(trace_names(top_m, mods)), encoding="utf-8")
        e2 = []
        for k, tb in enumerate(tbs):
            r = sim(files, top, Path(tb).stem, Path(tb).parent, out / f"sim_v{k}", seeds=self.seeds, harness_dir=hdir,
                    trace=tdir / f"{top}_trace.json")
            res_dir = out / f"sim_v{k}" / "tb_out" / str(self.seeds[0])
            e2.append({"verifier": k, "ok": r.ok, "findings": [{"test": f.test, "rule": f.rule, "message": f.message[:300]}
                                                               for f in r.findings], "out": str(res_dir)})
        return {"e1": [{"type": c.type, "node": c.node, "module": c.module, "message": c.message[:200]} for c in e1c],
                "e2": e2, "ok": all(x["ok"] for x in e2) and not any(c.type == "lint_fragment" for c in e1c)}

    @staticmethod
    def result_name(out: Path, tests: list[str]) -> str | None:
        """실패한 cocotb 테스트의 결과 파일 이름. 결과 파일은 하니스의 name을 따르므로 함수 이름과 다를 수 있다.
        함수 이름이나 `test_`를 뗀 이름이 없으면 실패가 기록된 첫 결과 파일."""
        for t in tests:
            for n in (t, t.removeprefix("test_")):
                if (out / f"{n}.result.json").exists():
                    return n
        for res in sorted(out.glob("*.result.json")):
            r = json.loads(res.read_text())
            if r.get("scoreboard") or r.get("protocol") or r.get("properties"):
                return res.name.removesuffix(".result.json")
        return None

    def failure_report(self, lib: dict, top: str, v: dict) -> dict:
        out = Path(v["out"])
        test = self.result_name(out, [f["test"] for f in v["findings"] if f["test"]])
        if test is None:
            return {"classified": v["findings"], "report": None}
        mods = {n: Module(r) for n, r in lib.items()}
        rep = mismatch_report(mods[top], json.loads((out / f"{test}.result.json").read_text()),
                              json.loads((out / f"{test}.trace.json").read_text()),
                              self.spec_path.read_text(encoding="utf-8"), mods)
        return {"classified": [{"type": "sim_mismatch" if f["rule"] in ("AssertionError", "T1_INIT") else "tb_error",
                                "test": f["test"], "message": f["message"]} for f in v["findings"]], "report": rep}

    def author_step(self, mod: str, c: int, tree: dict) -> dict:
        """후보 하나의 Author. 상태는 modules[mod][c]에 저장."""
        key = f"{mod}/c{c}"
        st = self.mod_state(key)
        if "ir" in st or st["status"] != "author":
            return st
        l1 = tree["children"][mod]
        res = self.agent("author", author.make_task(f"author/{mod}/c{c}", l1, self.spec_path), author.check(l1))
        if not res.ok:
            st.update(status="failed", reason=f"Author 실패: {res.errors[:3]}")
        else:
            st["ir"] = json.loads(Path(res.outputs[author.out_rel(mod)]).read_text(encoding="utf-8"))
        self.save_mod(key, st)
        return st

    @staticmethod
    def culprit(tree: dict, mods: list[str], failure: dict, e1: list[dict]) -> str:
        """실패의 원인 후보 모듈: 불일치 출력을 구동하는 인스턴스의 모듈, 없으면 lint 조각 오류가 난 모듈."""
        inst = {i["name"]: i["module"] for i in tree["top"].get("instances", [])}
        for node in ((failure.get("report") or {}).get("fanin") or {}).get("nodes", []):
            if node.startswith("instances/") and inst.get(node.split("/", 1)[1]) in mods:
                return inst[node.split("/", 1)[1]]
        for x in e1:
            if x.get("type") == "lint_fragment" and x.get("module") in mods:
                return x["module"]
        return mods[0]

    def candidate_loop(self, c: int, mods: list[str], tree: dict, tbs: list[str]) -> dict[str, dict]:
        """c번 후보 묶음: 모듈마다 c번 Author 후보를 모아 Block Top에서 함께 검증한다 (하위 모듈이 하나면 그 후보 하나).
        실패면 Arbiter/Repair. Repair는 원인 후보 모듈 하나에 넘기고, 그 Repair가 형제 모듈을 지목하면 그 모듈로 넘긴다."""
        keys = {m: f"{m}/c{c}" for m in mods}
        sts = {m: self.mod_state(k) for m, k in keys.items()}

        def save_all(**upd):
            for m in mods:
                sts[m].update(**upd)
                self.save_mod(keys[m], sts[m])

        if all(st["status"] in ("pass", "failed", "waiting_approval", "interface_change") for st in sts.values()):
            return sts
        if bad := [m for m in mods if "ir" not in sts[m]]:
            for m in mods:
                if m not in bad:
                    sts[m].update(status="failed", reason=f"같은 묶음의 Author 실패: {bad}")
                self.save_mod(keys[m], sts[m])
            return sts
        top_ir, children = tree["top"], tree["children"]
        gname = mods[0] if len(mods) == 1 else top_ir["module"]
        limit = self.roles.limits.get("repair_per_candidate", 5)
        while True:
            total = sum(st["repairs"] for st in sts.values())
            lib = {top_ir["module"]: top_ir, **{n: (sts[n]["ir"] if n in sts else ch) for n, ch in children.items()}}
            v11 = v11_frozen({n: Module(r) for n, r in lib.items()}, tree["frozen"])
            if v11:
                save_all(status="failed", reason=f"동결 위반: {[str(i) for i in v11]}")
                break
            vres = self.verify(lib, top_ir["module"], tbs, f"{gname}_c{c}_r{total}")
            last = {"ok": vres["ok"], "e1": len(vres["e1"]), "e2": [{k: x[k] for k in ("verifier", "ok")} for x in vres["e2"]]}
            for st in sts.values():
                st["last_verify"] = last
            if vres["ok"]:
                save_all(status="pass", lint=len(vres["e1"]), outputs=[x["out"] for x in vres["e2"]])
                break
            failed = [x for x in vres["e2"] if not x["ok"]]
            if failed and len(failed) < len(vres["e2"]):
                # 한 Verifier에서만 실패: 그 Verifier의 오류일 수 있으므로 Arbiter가 판정한다
                v = failed[0]
                rep = self.failure_report(lib, top_ir["module"], v)
                ares = self.agent("arbiter", arbiter.make_task(f"arbiter/{gname}/c{c}/r{total}", self.spec_path,
                                                               rep["report"] or rep, Path(tbs[v["verifier"]])),
                                  arbiter.check(self.spec_path))
                verdict = json.loads(Path(ares.outputs[arbiter.OUT]).read_text())["verdict"] if ares.ok else "spec_ambiguous"
                for st in sts.values():
                    st.setdefault("arbiter", []).append(verdict)
                if verdict == "test_wrong":
                    self.review("EXPECTATION_CHANGE", f"{gname} 후보 {c}: Verifier {v['verifier']}의 기댓값 수정 제안 (사람 승인 대기)",
                                str(ares.workdir), "arbiter")
                    save_all(status="waiting_approval")
                    break
                if verdict == "spec_ambiguous":
                    self.review("SPEC_AMBIGUOUS", f"{gname} 후보 {c}: Verifier 사이 해석이 갈림", str(ares.workdir), "arbiter")
                    save_all(status="waiting_approval")
                    break
            fail_v = failed[0] if failed else {"findings": [], "out": ""}
            failure = self.failure_report(lib, top_ir["module"], fail_v) if failed else {"classified": vres["e1"], "report": None}
            if any(x.get("type") == "tb_error" for x in failure["classified"]) and not any(
                    x.get("type") == "sim_mismatch" for x in failure["classified"]):
                self.review("TB_ERROR", f"{gname} 후보 {c}: 테스트 실행 오류 (Verifier가 고쳐야 함)", fail_v.get("out", ""))
                save_all(status="failed", reason="TB 실행 오류")
                break
            mod, tried, stop = self.culprit(tree, mods, failure, vres["e1"]), [], None
            while stop is None:
                st = sts[mod]
                tried.append(mod)
                if st["repairs"] >= limit:
                    stop = dict(status="failed", reason=f"{mod}: Repair 상한 {limit}회")
                    break
                block = None if len(mods) == 1 else {
                    "top": top_ir["module"], "instances": top_ir.get("instances", []), "connections": top_ir.get("connections", []),
                    "siblings": {n: children[n] for n in mods if n != mod}}
                rres = self.agent("repair", repair.make_task(f"repair/{mod}/c{c}/r{st['repairs']}", st["ir"], self.spec_path,
                                                             failure, st["history"], block),
                                  repair.check(st["ir"], siblings=set(block["siblings"]) if block else None))
                st["repairs"] += 1
                self.save_mod(keys[mod], st)
                if not rres.ok:
                    stop = dict(status="failed", reason=f"{mod}: Repair 실패: {rres.errors[:3]}")
                    break
                patches = json.loads(Path(rres.outputs[repair.OUT]).read_text())
                if (reason := repair.interface_change(patches)) is not None:
                    self.review("INTERFACE_CHANGE", f"{mod} 후보 {c}: Repair가 L1 변경을 요청함: {reason}", rres.workdir, "repair")
                    stop = dict(status="interface_change")
                    break
                if (sus := repair.suspect(patches)) is not None:
                    # 자식 모듈 원인 의심: 지목된 형제 모듈의 Repair로 넘긴다. 이번 실패에서 이미 거친 모듈이면 사람에게 넘긴다
                    self.event("suspect", f"{mod} → {sus[0]}: {sus[1][:200]}")
                    if sus[0] in tried:
                        self.review("CHILD_SUSPECT_LOOP", f"{gname} 후보 {c}: Repair들이 서로 원인을 넘김 ({tried + [sus[0]]})",
                                    rres.workdir, "repair")
                        stop = dict(status="failed", reason="원인 모듈을 정하지 못함")
                        break
                    mod = sus[0]
                    continue
                new = apply(st["ir"], patches)
                h = ir_hash(new.ir)
                if h in st["hashes"]:
                    self.review("OSCILLATION", f"{mod} 후보 {c}: 같은 IR로 돌아옴 (진동). 사람에게 넘김", rres.workdir)
                    stop = dict(status="failed", reason=f"{mod}: 진동")
                    break
                st["hashes"].append(h)
                st["history"] += patches
                st["ir"] = new.ir
                self.save_mod(keys[mod], st)
                break
            if stop is not None:
                save_all(**stop)
                break
        return sts

    def step_modules(self, tree: dict, tbs: list[str]) -> dict[str, dict]:
        """모듈마다 Author 후보를 병렬로 돌리고, 같은 번호 후보끼리 묶어 검증한 뒤 묶음을 고른다.
        자식부터(여기서는 Block Top의 자식 한 단계)."""
        mods = [n for n, c in tree["children"].items() if c.get("role") == "module"]
        n = self.roles.counts.get("author", 1)
        jobs = [(m, c) for m in mods for c in range(n)]
        with ThreadPoolExecutor(max(1, len(jobs))) as ex:
            list(ex.map(lambda mc: self.author_step(mc[0], mc[1], tree), jobs))
        with ThreadPoolExecutor(max(1, n)) as ex:
            list(ex.map(lambda c: self.candidate_loop(c, mods, tree, tbs), range(n)))
        allst = self.modules()
        # 묶음 c는 모든 모듈의 c번 후보가 함께 통과해야 쓸 수 있다
        ok = sorted([(sum(allst[f"{m}/c{c}"]["repairs"] for m in mods), sum(allst[f"{m}/c{c}"].get("lint", 0) for m in mods), c)
                     for c in range(n) if all(allst[f"{m}/c{c}"]["status"] == "pass" for m in mods)])
        chosen = {}
        if not ok:
            for m in mods:
                self.review("MODULE_FAILED", f"{m}: 통과한 후보가 없음 "
                                             f"({[allst[f'{m}/c{c}'].get('reason') or allst[f'{m}/c{c}']['status'] for c in range(n)]})", m)
        else:
            chosen = {m: ok[0][2] for m in mods}
            passed = [c for _, _, c in ok]
            if len(passed) >= 2:
                diff = candidate_diff([allst[f"{mods[0]}/c{c}"]["outputs"] for c in passed])
                if diff:
                    self.review("CANDIDATE_DIFF", f"{', '.join(mods)}: 통과한 후보들이 같은 테스트에서 다른 출력을 냄 ({diff}). "
                                                  "테스트에 구멍이 있음. Verifier에게 돌려 보강", ", ".join(mods))
        self.state["chosen"] = chosen
        self.save()
        return chosen

    def step_integrate(self, tree: dict, chosen: dict, tbs: list[str]) -> dict:
        lib = {tree["top"]["module"]: tree["top"]}
        for n, ch in tree["children"].items():
            lib[n] = self.modules()[f"{n}/c{chosen[n]}"]["ir"] if n in chosen else ch
        final = self.verify(lib, tree["top"]["module"], tbs, "integration")
        rtl = self.dir / "rtl"
        rtl.mkdir(exist_ok=True)
        mods = {n: Module(r) for n, r in lib.items()}
        for n, m in mods.items():
            (rtl / f"{n}.sv").write_text(emit(m, mods).text, encoding="utf-8")
            (self.dir / "ir" / f"{n}.ir.json").write_text(json.dumps(lib[n], ensure_ascii=False, indent=1), encoding="utf-8")
        self.finish_step("integration", {"ok": final["ok"], "e1": final["e1"], "e2": [{k: x[k] for k in ("verifier", "ok")} for x in final["e2"]]})
        return final

    def execute(self) -> dict:
        try:
            if not self.step_spec():
                self.state["status"] = "spec_rejected"
                return self.report()
            tree = self.step_architect()
            if tree is None:
                self.state["status"] = "failed"
                self.review("ARCHITECT_FAILED", "Architect가 모듈 트리를 만들지 못함")
                return self.report()
            tbs = self.step_verifiers(tree["top"])
            if not tbs:
                self.state["status"] = "failed"
                self.review("VERIFIER_FAILED", "쓸 수 있는 Verifier 테스트가 없음")
                return self.report()
            chosen = self.step_modules(tree, tbs)
            mods = [n for n, c in tree["children"].items() if c.get("role") == "module"]
            if len(chosen) < len(mods):
                waiting = any(st["status"] == "waiting_approval" for st in self.modules().values())
                self.state["status"] = "waiting_approval" if waiting else "failed"
                return self.report()
            final = self.step_integrate(tree, chosen, tbs)
            self.state["status"] = "pass" if final["ok"] else "failed"
        except BudgetExceeded as e:
            self.state["status"] = "budget_exceeded"
            self.review("BUDGET", str(e))
        except QuotaExceeded as e:
            # 끝난 단계와 작업은 저장되어 있다. 한도가 풀린 뒤 같은 명령으로 이어서 실행한다.
            self.state["status"] = "paused_quota"
            self.event("quota", str(e))
        return self.report()

    def report(self) -> dict:
        st = self.state
        rep = {"status": st["status"], "spec": st["spec"], "agent_runs": st["agent_runs"], "chosen": st.get("chosen"),
               "candidates": {k: {x: v.get(x) for x in ("status", "repairs", "lint", "reason", "arbiter")}
                              for k, v in self.modules().items()},
               "integration": st["steps"].get("integration"), "review": st["review"], "events": st["events"]}
        self.save()
        (self.dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return rep


def _load_model(tb: str, harness_dir: Path | None = None):
    import importlib.util

    for p in (harness_dir, Path(tb).parent):
        if p and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(f"vm_{abs(hash(tb))}", tb)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Model()


def verifier_diff(tbs: list[str], l1: dict, n: int = 300, seed: int = 7, harness_dir: Path | None = None) -> str | None:
    """참조 모델들에 같은 무작위 입력을 넣어 기대 출력을 비교한다 (Verifier 간 차분 검사)."""
    from pipeline.tb.gen import harness_config, signal_widths

    cfg = harness_config(Module(l1))
    widths = signal_widths(l1)
    ins = [b for b in cfg["bundles"] if not b["dut_drives"]]
    if not ins:
        return None
    try:
        models = [_load_model(t, harness_dir) for t in tbs]
    except Exception as e:  # 모델을 읽을 수 없으면 차분 검사를 할 수 없음
        raise ImportError(str(e)) from e
    rng = random.Random(seed)
    for i in range(n):
        b = rng.choice(ins)
        txn = {d: rng.getrandbits(widths.get(d, 8)) for d in b["data"]}
        outs = []
        for m in models:
            if hasattr(m, "legal") and not m.legal(b["name"], dict(txn)):
                outs.append(None)
                continue
            try:
                outs.append([(o[0], o[1]) for o in (m.on_input(b["name"], dict(txn)) or [])])
            except Exception as e:
                outs.append(f"예외 {type(e).__name__}")
        real = [o for o in outs if o is not None]
        if len({json.dumps(o, sort_keys=True, default=str) for o in real}) > 1:
            return f"입력 {i}번째 {b['name']} {txn}: {real}"
    return None


def candidate_diff(outputs: list[list[str]]) -> str | None:
    """후보마다 같은 Verifier 테스트에서 낸 실제 출력 트랜잭션을 비교한다."""
    base = outputs[0]
    for other in outputs[1:]:
        for a_dir, b_dir in zip(base, other):
            for res in sorted(Path(a_dir).glob("*.result.json")):
                b = Path(b_dir) / res.name
                if not b.exists():
                    continue
                oa, ob = json.loads(res.read_text()).get("outputs"), json.loads(b.read_text()).get("outputs")
                if oa != ob:
                    return f"{res.name.removesuffix('.result.json')}"
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="파이프라인 실행 (SPEC → RTL)")
    ap.add_argument("spec")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--roles", default=str(ROOT / "config" / "roles.json"))
    ap.add_argument("--cells", nargs="*")
    args = ap.parse_args(argv)
    run = Run(Path(args.run_dir), Path(args.spec), roles_mod.load(args.roles), [Path(c) for c in args.cells] if args.cells else None)
    rep = run.execute()
    print(json.dumps({k: rep[k] for k in ("status", "agent_runs", "chosen", "candidates")}, ensure_ascii=False, indent=1))
    return 0 if rep["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
