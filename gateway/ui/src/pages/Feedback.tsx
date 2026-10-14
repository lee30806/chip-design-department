import { useState } from "react";
import { api, can, type RunSummary } from "../api";
import { Err, useAction, useGet, useUser } from "../common";

const FORMS = {
  check_report: "검사 실패 리포트",
  spec_change: "SPEC 변경 요청",
  generator_bug: "생성기 버그 리포트",
  config_change: "설정 변경",
} as const;
type Form = keyof typeof FORMS;

type GenBug = { id: string; at: string; message: string; module?: string; run_id?: string | null; status: string;
  history?: { at: string; by: string; status: string; note: string }[] };
const BUG_STATUS: Record<string, string> = { open: "열림", fixed: "고침", wontfix: "고치지 않음" };

function GeneratorBugs() {
  const user = useUser();
  const bugs = useGet<GenBug[]>("/api/generator-bugs");
  const act = useAction();
  const [note, setNote] = useState<Record<string, string>>({});
  const set = async (id: string, status: string) => {
    const r = await act.run(() => api.post(`/api/generator-bugs/${id}`, { status, note: note[id] ?? "" }));
    if (r) bugs.reload();
  };
  return (
    <section className="panel scroll">
      <h2>생성기 버그</h2>
      <p className="small muted">골격(조각 밖) lint 에러와 생성기 버그 리포트. LLM에 보내지 않고 Emitter를 사람이 고칩니다. 처리 상태는 Design-lead가 바꿉니다.</p>
      <Err msg={bugs.error || act.error} />
      <table><thead><tr><th>ID</th><th>언제</th><th>실행</th><th>내용</th><th>상태</th><th></th></tr></thead><tbody>
        {(bugs.data ?? []).slice().reverse().map((b) => (
          <tr key={b.id}><td className="mono">{b.id}</td><td className="small">{b.at}</td><td className="mono small">{b.run_id ?? "-"}</td>
            <td className="small">{b.module ? `${b.module}: ` : ""}{b.message}
              {(b.history ?? []).map((h, i) => <div key={i} className="muted">{h.at} {h.by}: {BUG_STATUS[h.status] ?? h.status} {h.note}</div>)}</td>
            <td className="small">{BUG_STATUS[b.status] ?? b.status}</td>
            <td>{can.feedback(user) && (
              <div className="row">
                <input placeholder="메모" value={note[b.id] ?? ""} onChange={(e) => setNote({ ...note, [b.id]: e.target.value })} />
                {Object.keys(BUG_STATUS).filter((k) => k !== b.status).map((k) =>
                  <button key={k} disabled={act.busy} onClick={() => set(b.id, k)}>{BUG_STATUS[k]}</button>)}
              </div>)}</td></tr>
        ))}
        {bugs.data?.length === 0 && <tr><td colSpan={6} className="muted">생성기 버그가 없습니다.</td></tr>}
      </tbody></table>
    </section>
  );
}

type History = { id: string; at: string; form: string; by: string; run_id: string | null; result?: string; status?: string; new_run?: string };

export default function Feedback() {
  const user = useUser();
  const runs = useGet<RunSummary[]>("/api/runs");
  const formats = useGet<Record<string, string>>("/api/feedback/formats");
  const history = useGet<History[]>("/api/feedback");
  const [form, setForm] = useState<Form>("check_report");
  const [f, setF] = useState<Record<string, string>>({});
  const act = useAction();
  const [result, setResult] = useState<unknown>(null);
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const passed = (runs.data ?? []).filter((r) => r.status === "pass");
  const body = (): Record<string, unknown> => {
    const b: Record<string, unknown> = { form };
    if (form === "check_report") Object.assign(b, { run_id: f.run_id, format: f.format, report: f.report, source: f.source || undefined });
    if (form === "spec_change") Object.assign(b, { run_id: f.run_id, spec: f.spec, reason: f.reason, source: f.source || undefined });
    if (form === "generator_bug") Object.assign(b, { description: f.description, evidence: f.evidence || undefined, run_id: f.run_id || undefined });
    if (form === "config_change") {
      const cfg: Record<string, number> = {};
      for (const k of ["author_count", "verifier_count", "budget_agent_runs", "repair_per_candidate"]) if (f[k]) cfg[k] = Number(f[k]);
      Object.assign(b, { config: cfg });
    }
    if (f.note) b.note = f.note;
    return b;
  };
  const runSelect = (required: boolean) => (
    <label>대상 실행 {required ? "" : "(선택)"}
      <select id="fb-run" value={f.run_id ?? ""} onChange={set("run_id")}>
        <option value="">고르기</option>
        {passed.map((r) => <option key={r.run_id} value={r.run_id}>{r.run_id}</option>)}
      </select>
    </label>
  );
  return (
    <main className="page">
      <div className="page-head">
        <h1>환류</h1>
        <span className="sub">수정 요구는 네 가지 양식으로만 냅니다. 자유 텍스트로 수정을 요청하는 경로는 없습니다. 제출은 Design-lead만 합니다.</span>
      </div>
      {!can.feedback(user) && <p className="panel small">이 계정은 환류를 제출할 수 없습니다. 요구는 Design-lead에게 전달합니다.</p>}
      <section className="panel stack">
        <div className="tabs">
          {(Object.keys(FORMS) as Form[]).map((k) => <button key={k} className={k === form ? "on" : ""} onClick={() => { setForm(k); setResult(null); act.setError(null); }}>{FORMS[k]}</button>)}
        </div>
        {form === "check_report" && (
          <>
            {runSelect(true)}
            <label>리포트 양식 (config/report_formats)
              <select id="fb-format" value={f.format ?? ""} onChange={set("format")}>
                <option value="">고르기</option>
                {Object.entries(formats.data ?? {}).map(([k, d]) => <option key={k} value={k} title={d}>{k}</option>)}
              </select>
            </label>
            <label>발생원<input id="fb-source" value={f.source ?? ""} onChange={set("source")} placeholder="Sanity, 합성, LEC" /></label>
            <label>리포트 원문<textarea id="fb-report" rows={10} value={f.report ?? ""} onChange={set("report")} /></label>
          </>
        )}
        {form === "spec_change" && (
          <>
            {runSelect(true)}
            <label>발생원
              <select id="fb-source2" value={f.source ?? ""} onChange={set("source")}>
                <option value="">고르기</option><option value="dv_bug">DV 기능 버그 (예시 시나리오로 더함)</option><option value="sta">STA 구조 변경</option><option value="other">기타</option>
              </select>
            </label>
            <label>이유 (요구사항 ID와 SPEC 문장으로)<textarea id="fb-reason" rows={3} value={f.reason ?? ""} onChange={set("reason")} /></label>
            <label>개정한 SPEC 전문 (Markdown)<textarea id="fb-spec" rows={14} value={f.spec ?? ""} onChange={set("spec")} /></label>
          </>
        )}
        {form === "generator_bug" && (
          <>
            {runSelect(false)}
            <label>설명 (골격 코드의 어떤 위반인지)<textarea id="fb-desc" rows={3} value={f.description ?? ""} onChange={set("description")} /></label>
            <label>근거 (리포트나 코드 조각)<textarea id="fb-evidence" rows={6} value={f.evidence ?? ""} onChange={set("evidence")} /></label>
          </>
        )}
        {form === "config_change" && (
          <div className="row">
            <label>Author 후보 수<input id="fb-ac" type="number" min={1} max={4} value={f.author_count ?? ""} onChange={set("author_count")} /></label>
            <label>Verifier 수<input id="fb-vc" type="number" min={1} max={4} value={f.verifier_count ?? ""} onChange={set("verifier_count")} /></label>
            <label>에이전트 실행 예산<input id="fb-budget" type="number" min={1} value={f.budget_agent_runs ?? ""} onChange={set("budget_agent_runs")} /></label>
            <label>후보당 Repair 상한<input id="fb-repair" type="number" min={1} value={f.repair_per_candidate ?? ""} onChange={set("repair_per_candidate")} /></label>
          </div>
        )}
        <label>메모 (선택)<input id="fb-note" value={f.note ?? ""} onChange={set("note")} /></label>
        <div className="row">
          <button className="primary" disabled={!can.feedback(user) || act.busy}
            onClick={async () => { const r = await act.run(() => api.post("/api/feedback", body())); if (r) { setResult(r); history.reload(); } }}>제출</button>
          <Err msg={act.error} />
        </div>
        {result !== null && <pre className="panel small">{JSON.stringify(result, null, 1)}</pre>}
      </section>
      <section className="panel scroll">
        <h2>환류 이력</h2>
        <table><thead><tr><th>ID</th><th>언제</th><th>형태</th><th>누가</th><th>실행</th><th>결과</th><th>새 실행</th></tr></thead><tbody>
          {(history.data ?? []).slice().reverse().map((h) => (
            <tr key={h.id}><td className="mono">{h.id}</td><td className="small">{h.at}</td><td className="small">{FORMS[h.form as Form] ?? h.form}</td><td>{h.by}</td>
              <td className="mono small">{h.run_id ?? "-"}</td><td className="small">{h.result ?? h.status ?? "-"}</td><td className="mono small">{h.new_run ?? "-"}</td></tr>
          ))}
        </tbody></table>
      </section>
      <GeneratorBugs />
    </main>
  );
}
