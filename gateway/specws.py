"""SPEC 작업대: 원본(PDF 또는 Markdown)과 변환 결과의 대조, 원본 파형과 WaveJSON 렌더링의 대조, 검사 질문 답하기, SPEC 고정 요청.

- PDF는 `pipeline.spec.pdf`로 Markdown으로 바꾸고, 그림 캡션의 위치를 기억한다. 원본 쪽과 그림은 PNG로 잘라 보여 준다.
- WaveJSON은 그림마다 붙인다(비전 coding agent의 변환 결과를 붙이거나 사람이 고침). `pipeline.spec.wavejson.render`로 그려 원본 그림 옆에 둔다.
- 변환 결과를 고치면 새 판(sha)이 된다. 고정된 SPEC은 고치지 못하고, 바꾸려면 SPEC 변경 요청을 낸다.
- 검사는 `pipeline.spec.check`. 질문(미정의 동작, 열린 질문, 경고, LLM 질문)에 모두 답해야 고정을 요청할 수 있다.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from pathlib import Path

from gateway.db import DB, now


class SpecError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _qkey(item: dict) -> str:
    return hashlib.sha256(f"{item.get('code')}|{item.get('where')}|{item.get('message')}".encode()).hexdigest()[:12]


class Specs:
    def __init__(self, db: DB, home: Path):
        self.db, self.home = db, Path(home)

    def dir(self, spec_id: str) -> Path:
        return self.home / "specs" / spec_id

    def row(self, spec_id: str) -> dict:
        r = self.db.one("SELECT * FROM specs WHERE id=?", (spec_id,))
        if not r:
            raise SpecError(404, f"없는 SPEC 작업 공간: {spec_id}")
        return r

    def current(self, spec_id: str) -> dict:
        return self.db.one("SELECT sha, markdown, by, at, note FROM spec_versions WHERE spec_id=? ORDER BY rowid DESC LIMIT 1",
                           (spec_id,))

    # -- 만들기와 고치기 --
    def create(self, name: str, filename: str, content: bytes, by: str) -> dict:
        kind = "pdf" if filename.lower().endswith(".pdf") else "md"
        if kind == "md" and not filename.lower().endswith((".md", ".markdown", ".txt")):
            raise SpecError(400, "원본은 PDF나 Markdown이어야 함 (Word는 사내 양식을 받으면 지원)")
        spec_id = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(name or filename).stem)[:40].strip("-") or "spec"
        spec_id = f"{spec_id}-{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"
        d = self.dir(spec_id)
        d.mkdir(parents=True)
        orig = d / ("original.pdf" if kind == "pdf" else "original.md")
        orig.write_bytes(content)
        figures = []
        if kind == "pdf":
            from pipeline.spec.pdf import convert
            try:
                r = convert(orig)
            except Exception as e:
                raise SpecError(400, f"PDF를 변환할 수 없음: {e}")
            md, figures = r["markdown"], r["figures"]
            (d / "convert_report.json").write_text(json.dumps(r["report"], ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            md = content.decode("utf-8", errors="replace")
        self.db.x("INSERT INTO specs (id, name, source_kind, status, created_by, created) VALUES (?,?,?,?,?,?)",
                  (spec_id, name or filename, kind, "draft", by, now()))
        self.db.x("INSERT INTO spec_versions (spec_id, sha, markdown, by, at, note) VALUES (?,?,?,?,?,?)",
                  (spec_id, sha(md), md, by, now(), "변환 결과" if kind == "pdf" else "원본"))
        for f in figures:
            self.db.x("INSERT INTO spec_figures (spec_id, n, page, caption, bbox) VALUES (?,?,?,?,?)",
                      (spec_id, f["number"], f["page"], f["caption"], json.dumps(list(f["bbox"]))))
        self.db.audit(by, "spec_create", {"spec": spec_id, "kind": kind})
        return self.get(spec_id)

    def update_markdown(self, spec_id: str, markdown: str, by: str, note: str = "") -> dict:
        r = self.row(spec_id)
        if r["status"] == "frozen":
            raise SpecError(409, "고정된 SPEC은 고칠 수 없음. 바꾸려면 SPEC 변경 요청을 냄")
        h = sha(markdown)
        if h != self.current(spec_id)["sha"]:
            # 예전 판과 같은 내용으로 되돌리면 그 판을 지우고 최신으로 다시 넣는다 (판의 순서 = 행 순서)
            self.db.x("DELETE FROM spec_versions WHERE spec_id=? AND sha=?", (spec_id, h))
            self.db.x("INSERT INTO spec_versions (spec_id, sha, markdown, by, at, note) VALUES (?,?,?,?,?,?)",
                      (spec_id, h, markdown, by, now(), note))
        if r["status"] == "freeze_requested":
            self.db.x("UPDATE specs SET status='draft', freeze_requested_sha=NULL WHERE id=?", (spec_id,))
        self.db.audit(by, "spec_edit", {"spec": spec_id, "sha": h})
        return self.get(spec_id)

    def set_wavejson(self, spec_id: str, n: int, text: str, by: str) -> dict:
        from pipeline.spec.waveform import lint_wavejson
        from pipeline.spec.wavejson import parse_wavejson

        if self.row(spec_id)["status"] == "frozen":
            raise SpecError(409, "고정된 SPEC은 고칠 수 없음")
        if not self.db.one("SELECT 1 FROM spec_figures WHERE spec_id=? AND n=?", (spec_id, n)):
            self.db.x("INSERT INTO spec_figures (spec_id, n) VALUES (?,?)", (spec_id, n))
        try:
            wj = parse_wavejson(text)
        except Exception as e:
            raise SpecError(400, f"WaveJSON을 읽을 수 없음: {e}")
        errs = lint_wavejson(wj)
        if errs:
            raise SpecError(400, f"WaveJSON 형식 오류: {errs}")
        self.db.x("UPDATE spec_figures SET wavejson=? WHERE spec_id=? AND n=?", (json.dumps(wj, ensure_ascii=False), spec_id, n))
        (self.dir(spec_id) / f"wave{n}.png").unlink(missing_ok=True)
        self.db.audit(by, "spec_wavejson", {"spec": spec_id, "figure": n})
        return self.get(spec_id)

    # -- 조회 --
    def checks(self, spec_id: str) -> dict:
        from pipeline.spec.check import run
        from pipeline.spec.parse import parse

        md = self.current(spec_id)["markdown"]
        try:
            res = run(parse(md))
        except Exception as e:
            return {"gate": "fail", "issues": [{"code": "PARSE", "severity": "error", "where": "spec", "message": str(e)}],
                    "questions": []}
        answers = {a["qkey"]: a for a in self.db.q("SELECT * FROM spec_answers WHERE spec_id=?", (spec_id,))}
        qs = []
        for item in res["review"]:
            k = _qkey(item)
            qs.append({**item, "key": k, "answer": answers.get(k)})
        return {"gate": res["gate"], "requirements": res["requirements"],
                "issues": [i for i in res["issues"] if i["severity"] == "error"], "questions": qs}

    def get(self, spec_id: str) -> dict:
        r = self.row(spec_id)
        cur = self.current(spec_id)
        figs = [{"n": f["n"], "page": f["page"], "caption": f["caption"], "has_wavejson": f["wavejson"] is not None}
                for f in self.db.q("SELECT * FROM spec_figures WHERE spec_id=? ORDER BY n", (spec_id,))]
        versions = self.db.q("SELECT sha, by, at, note FROM spec_versions WHERE spec_id=? ORDER BY rowid", (spec_id,))
        pages = 0
        if r["source_kind"] == "pdf":
            import pymupdf
            pages = pymupdf.open(self.dir(spec_id) / "original.pdf").page_count
        return {**r, "sha": cur["sha"], "markdown": cur["markdown"], "versions": versions, "figures": figs, "pages": pages,
                "checks": self.checks(spec_id),
                "original_markdown": (self.dir(spec_id) / "original.md").read_text(encoding="utf-8", errors="replace")
                if r["source_kind"] == "md" else None}

    def list(self) -> list[dict]:
        return self.db.q("SELECT id, name, source_kind, status, created_by, created, frozen_sha FROM specs ORDER BY created DESC")

    # -- 그림 --
    def page_png(self, spec_id: str, page: int) -> bytes:
        import pymupdf
        if self.row(spec_id)["source_kind"] != "pdf":
            raise SpecError(404, "PDF 원본이 아님")
        out = self.dir(spec_id) / f"page{page}.png"
        if not out.exists():
            doc = pymupdf.open(self.dir(spec_id) / "original.pdf")
            if not 1 <= page <= doc.page_count:
                raise SpecError(404, f"없는 쪽: {page}")
            doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(out)
        return out.read_bytes()

    def figure_png(self, spec_id: str, n: int) -> bytes:
        from pipeline.spec.waveform import extract_figure

        f = self.db.one("SELECT * FROM spec_figures WHERE spec_id=? AND n=?", (spec_id, n))
        if not f or f["page"] is None:
            raise SpecError(404, "원본 그림이 없음 (Markdown 원본이거나 캡션을 찾지 못함)")
        out = self.dir(spec_id) / f"fig{n}.png"
        if not out.exists():
            try:
                extract_figure(self.dir(spec_id) / "original.pdf", f["page"], json.loads(f["bbox"])[1], out)
            except ValueError as e:
                raise SpecError(404, str(e))
        return out.read_bytes()

    def wave_png(self, spec_id: str, n: int) -> bytes:
        from pipeline.spec.wavejson import render

        f = self.db.one("SELECT wavejson FROM spec_figures WHERE spec_id=? AND n=?", (spec_id, n))
        if not f or not f["wavejson"]:
            raise SpecError(404, "이 그림의 WaveJSON이 없음")
        out = self.dir(spec_id) / f"wave{n}.png"
        if not out.exists():
            render(json.loads(f["wavejson"]), out)
        return out.read_bytes()

    def wavejson(self, spec_id: str, n: int) -> str | None:
        f = self.db.one("SELECT wavejson FROM spec_figures WHERE spec_id=? AND n=?", (spec_id, n))
        return f["wavejson"] if f else None

    # -- 질문과 고정 요청 --
    def answer(self, spec_id: str, qkey: str, answer: str, by: str) -> dict:
        if self.row(spec_id)["status"] == "frozen":
            raise SpecError(409, "고정된 SPEC")
        q = next((x for x in self.checks(spec_id)["questions"] if x["key"] == qkey), None)
        if q is None:
            raise SpecError(404, "지금 판에 없는 질문")
        if not answer.strip():
            raise SpecError(400, "답이 비어 있음")
        self.db.x("INSERT OR REPLACE INTO spec_answers (spec_id, qkey, question, answer, by, at) VALUES (?,?,?,?,?,?)",
                  (spec_id, qkey, q["message"], answer.strip(), by, now()))
        self.db.audit(by, "spec_answer", {"spec": spec_id, "q": qkey})
        return self.get(spec_id)

    def request_freeze(self, spec_id: str, by: str) -> dict:
        r = self.row(spec_id)
        if r["status"] != "draft":
            raise SpecError(409, f"지금 상태({r['status']})에서는 고정을 요청할 수 없음")
        c = self.checks(spec_id)
        if c["gate"] != "pass":
            raise SpecError(409, f"SPEC 검사 오류가 남아 있음: {[i['message'][:80] for i in c['issues'][:3]]}")
        open_q = [q for q in c["questions"] if not q["answer"]]
        if open_q:
            raise SpecError(409, f"답하지 않은 질문 {len(open_q)}개")
        self.db.x("UPDATE specs SET status='freeze_requested', freeze_requested_sha=? WHERE id=?",
                  (self.current(spec_id)["sha"], spec_id))
        self.db.audit(by, "spec_freeze_request", {"spec": spec_id})
        return self.get(spec_id)
