import { useState } from "react";
import { api } from "../api";
import { Err, useAction, useGet, useUser } from "../common";

type RoleCfg = { agent: string; count: number; langs?: string[] };
type SettingsInfo = {
  base: unknown;
  overrides: Record<string, unknown>;
  effective: { roles: Record<string, RoleCfg>; limits: Record<string, number> };
  agents: { name: string; family: string; runtime: string; model: string }[];
};

const LIMIT_LABEL: Record<string, string> = {
  repair_per_candidate: "후보당 Repair 상한", arbiter_after_repeats: "반복 실패 Arbiter 기준(Repair 횟수)",
  agent_retries: "에이전트 재시도", budget_agent_runs: "실행당 에이전트 예산",
};

export default function Settings() {
  const s = useGet<SettingsInfo>("/api/settings");
  const user = useUser();
  const canChange = user.roles.includes("design") && user.caps.includes("design_lead");
  const [form, setForm] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const act = useAction();
  const x = s.data;
  const agentOf = (n: string) => x?.agents.find((a) => a.name === n);
  const submit = async () => {
    const config: Record<string, unknown> = {};
    for (const k of ["author_count", "verifier_count", "budget_agent_runs", "repair_per_candidate"]) {
      if (form[k]) config[k] = Number(form[k]);
    }
    if (form.author_langs) config.author_langs = form.author_langs.split(",").map((v) => v.trim()).filter(Boolean);
    const r = await act.run(() => api.post("/api/feedback", { form: "config_change", config, ...(note ? { note } : {}) }));
    if (r) { setForm({}); setNote(""); s.reload(); }
  };
  return (
    <main className="page">
      <div className="page-head">
        <h1>설정</h1>
        <span className="sub">역할별 coding agent와 모델, 후보 수, 상한과 예산. 바꾸면 다음에 제출하는 실행부터 반영됩니다 (설정 변경 환류).</span>
        <button onClick={s.reload}>새로 읽기</button>
      </div>
      <Err msg={s.error} />
      {x && (
        <>
          <section className="panel scroll">
            <h2>역할</h2>
            <table>
              <thead><tr><th>역할</th><th>에이전트</th><th>런타임</th><th>모델</th><th>계열</th><th>수</th><th>조각 언어</th></tr></thead>
              <tbody>
                {Object.entries(x.effective.roles).map(([role, c]) => (
                  <tr key={role}><td>{role}</td><td className="mono small">{c.agent}</td><td className="small">{agentOf(c.agent)?.runtime ?? "-"}</td>
                    <td className="mono small">{agentOf(c.agent)?.model ?? "-"}</td><td className="small">{agentOf(c.agent)?.family ?? "-"}</td>
                    <td className="num">{c.count}</td><td className="small">{c.langs?.join(", ") ?? "-"}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <h2>상한과 예산</h2>
            <ul className="small">
              {Object.entries(x.effective.limits).map(([k, v]) => <li key={k}>{LIMIT_LABEL[k] ?? k}: <b>{v}</b></li>)}
            </ul>
            <p className="small muted">설정 변경으로 덮은 값: {Object.keys(x.overrides).length ? JSON.stringify(x.overrides) : "없음"}</p>
          </section>
          {canChange ? (
            <section className="panel stack">
              <h2>설정 변경 (Design-lead)</h2>
              <div className="row">
                {[["author_count", "Author 후보 수"], ["verifier_count", "Verifier 수"], ["repair_per_candidate", "Repair 상한"], ["budget_agent_runs", "에이전트 예산"]].map(([k, label]) => (
                  <label key={k} className="small">{label}<input type="number" min={1} value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>
                ))}
                <label className="small">조각 언어 (sv, py)<input value={form.author_langs ?? ""} placeholder="sv, py" onChange={(e) => setForm({ ...form, author_langs: e.target.value })} /></label>
              </div>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="바꾸는 이유" />
              <Err msg={act.error} />
              <div><button className="primary" disabled={act.busy || !Object.values(form).some(Boolean)} onClick={submit}>설정 변경 제출</button></div>
            </section>
          ) : <p className="small muted">설정 변경은 Design-lead(설계 역할과 design_lead 능력)만 냅니다.</p>}
        </>
      )}
    </main>
  );
}
