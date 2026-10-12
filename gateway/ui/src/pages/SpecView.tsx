import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, can, type Spec } from "../api";
import { Err, Status, short, useAction, useGet, useUser } from "../common";

export default function SpecView() {
  const { id } = useParams();
  const user = useUser();
  const spec = useGet<Spec>(`/api/specs/${id}`);
  const s = spec.data;
  const editable = can.design(user) && s?.status !== "frozen";
  const [md, setMd] = useState("");
  const [page, setPage] = useState(1);
  const act = useAction();
  const nav = useNavigate();
  useEffect(() => {
    if (s) setMd(s.markdown);
  }, [s?.sha]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!s) return <main className="page"><Err msg={spec.error} /></main>;
  const save = async () => {
    const r = await act.run(() => api.post<Spec>(`/api/specs/${id}/markdown`, { markdown: md, note: "작업대에서 고침" }));
    if (r) spec.setData(r);
  };
  const openQ = s.checks.questions.filter((q) => !q.answer).length;
  return (
    <main className="page">
      <div className="page-head">
        <h1>{s.name}</h1>
        <Status s={s.status} />
        <span className="sub mono">현재 {short(s.sha)}{s.frozen_sha && ` · 고정 ${short(s.frozen_sha)}`}</span>
      </div>
      <section className="panel row">
        <span>검사 <Status s={s.checks.gate === "pass" ? "pass" : "failed"} /></span>
        <span className="small">요구사항 {s.checks.requirements ?? "-"}개 · 질문 {s.checks.questions.length}개 (답하지 않음 {openQ}개)</span>
        {can.design(user) && s.status === "draft" && (
          <button className="primary" disabled={act.busy || s.checks.gate !== "pass" || openQ > 0}
            onClick={async () => { const r = await act.run(() => api.post<Spec>(`/api/specs/${id}/freeze-request`)); if (r) spec.setData(r); }}>
            고정 요청</button>
        )}
        {s.status === "freeze_requested" && <span className="small">승인자의 SPEC 고정 승인을 기다립니다.</span>}
        {can.design(user) && s.status === "frozen" && (
          <button className="primary" disabled={act.busy}
            onClick={async () => { const r = await act.run(() => api.post<{ run_id: string }>("/api/runs", { spec_id: id })); if (r) nav(`/runs/${r.run_id}`); }}>
            이 SPEC으로 실행 제출</button>
        )}
        <Err msg={act.error} />
      </section>
      {s.checks.issues.length > 0 && (
        <section className="panel"><h2>검사 오류</h2>
          <ul>{s.checks.issues.map((i, k) => <li key={k} className="small"><span className="mono">{i.code}</span> {i.where}: {i.message}</li>)}</ul></section>
      )}
      <div className="grid2">
        <section className="panel stack">
          <h2>원본</h2>
          {s.source_kind === "pdf" ? (
            <>
              <div className="row">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}>이전 쪽</button>
                <span className="small">{page} / {s.pages}</span>
                <button disabled={page >= s.pages} onClick={() => setPage(page + 1)}>다음 쪽</button>
              </div>
              <div className="imgbox"><img src={`/api/specs/${id}/page/${page}.png`} alt={`원본 ${page}쪽`} /></div>
            </>
          ) : (
            <pre className="small" style={{ maxHeight: "70vh", overflow: "auto" }}>{s.original_markdown}</pre>
          )}
        </section>
        <section className="panel stack">
          <h2>변환 결과 (Markdown)</h2>
          <textarea id="spec-md" rows={30} value={md} readOnly={!editable} onChange={(e) => setMd(e.target.value)} />
          {editable && <div className="row"><button className="primary" disabled={act.busy || md === s.markdown} onClick={save}>새 버전으로 저장</button>
            <span className="small muted">저장하면 고정 요청이 풀립니다.</span></div>}
          <details><summary className="small">버전 {s.versions.length}개</summary>
            <table><tbody>{s.versions.map((v) => <tr key={v.sha}><td className="mono small">{short(v.sha)}</td><td className="small">{v.by}</td><td className="small">{v.at}</td><td className="small">{v.note}</td></tr>)}</tbody></table>
          </details>
        </section>
      </div>
      <Waveforms spec={s} editable={editable} onChange={spec.setData} />
      <Questions spec={s} editable={can.design(user) && s.status !== "frozen"} onChange={spec.setData} />
    </main>
  );
}

function Waveforms({ spec, editable, onChange }: { spec: Spec; editable: boolean; onChange: (s: Spec) => void }) {
  const [n, setN] = useState<number>(spec.figures[0]?.n ?? 1);
  const [text, setText] = useState("");
  const [stamp, setStamp] = useState(0);
  const act = useAction();
  const fig = spec.figures.find((f) => f.n === n);
  useEffect(() => {
    api.get<{ wavejson: string | null }>(`/api/specs/${spec.id}/wavejson/${n}`).then((r) => setText(r.wavejson ?? "")).catch(() => setText(""));
  }, [spec.id, n, stamp]);
  return (
    <section className="panel stack">
      <h2>타이밍 다이어그램 대조</h2>
      <p className="small muted">원본 그림과, WaveJSON을 다시 그린 그림을 나란히 놓고 대조합니다. WaveJSON은 비전 에이전트의 변환 결과를 붙이거나 고칩니다.</p>
      <div className="row">
        {spec.figures.map((f) => <button key={f.n} className={f.n === n ? "primary" : ""} onClick={() => setN(f.n)}>그림 {f.n}{f.has_wavejson ? "" : " (WaveJSON 없음)"}</button>)}
        {editable && <button onClick={() => setN(Math.max(0, ...spec.figures.map((f) => f.n)) + 1)}>그림 추가</button>}
      </div>
      {fig?.caption && <div className="small">{fig.page}쪽 · {fig.caption}</div>}
      <div className="grid2">
        <div className="imgbox">{fig?.page ? <img src={`/api/specs/${spec.id}/figure/${n}.png`} alt={`원본 그림 ${n}`} /> : <span className="muted small">원본 그림 없음</span>}</div>
        <div className="imgbox">{fig?.has_wavejson ? <img src={`/api/specs/${spec.id}/wave/${n}.png?v=${stamp}`} alt={`WaveJSON 그림 ${n}`} /> : <span className="muted small">WaveJSON 없음</span>}</div>
      </div>
      <textarea id="wavejson" rows={6} value={text} readOnly={!editable} onChange={(e) => setText(e.target.value)} placeholder='{signal: [{name: "clk", wave: "p..."}]}' />
      {editable && <div className="row"><button className="primary" disabled={act.busy || !text.trim()}
        onClick={async () => { const r = await act.run(() => api.post<Spec>(`/api/specs/${spec.id}/wavejson/${n}`, { wavejson: text })); if (r) { onChange(r); setStamp(stamp + 1); } }}>
        WaveJSON 저장</button><Err msg={act.error} /></div>}
    </section>
  );
}

function Questions({ spec, editable, onChange }: { spec: Spec; editable: boolean; onChange: (s: Spec) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const act = useAction();
  return (
    <section className="panel stack">
      <h2>검사 질문</h2>
      <p className="small muted">미정의 동작, 열린 질문, 검사 경고, LLM 검사 질문입니다. 모두 답해야 고정을 요청할 수 있습니다. 답은 SPEC 고정 승인 자료가 됩니다.</p>
      <Err msg={act.error} />
      {spec.checks.questions.map((q) => (
        <div key={q.key} className="card stack">
          <div className="small"><span className="mono">{q.code}</span> · {q.where} · {q.source}</div>
          <div>{q.message}</div>
          {q.answer && <div className="small">답: {q.answer.answer} <span className="muted">({q.answer.by}, {q.answer.at})</span></div>}
          {editable && (
            <div className="row">
              <input id={`ans-${q.key}`} style={{ flex: 1, minWidth: 200 }} value={draft[q.key] ?? ""} placeholder={q.answer ? "답 고치기" : "답"}
                onChange={(e) => setDraft({ ...draft, [q.key]: e.target.value })} />
              <button disabled={act.busy || !(draft[q.key] ?? "").trim()}
                onClick={async () => { const r = await act.run(() => api.post<Spec>(`/api/specs/${spec.id}/answers`, { key: q.key, answer: draft[q.key] })); if (r) { onChange(r); setDraft({ ...draft, [q.key]: "" }); } }}>
                저장</button>
            </div>
          )}
        </div>
      ))}
      {spec.checks.questions.length === 0 && <p className="muted">질문이 없습니다.</p>}
    </section>
  );
}
