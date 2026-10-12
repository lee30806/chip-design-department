import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, can, KIND_LABEL, type RtlFile, type RunDetail as Detail, type RunSummary, type TaskDetail } from "../api";
import { Err, Status, short, useAction, useGet, useUser } from "../common";

type RunInfo = RunSummary & {
  signoffs: { kind: string; decision: string; by: string; at: string; note: string }[];
  approvals: { id: number; kind: string; decision: string; by: string; at: string; note: string | null; spec_sha: string | null }[];
};

const TABS = ["개요", "모듈", "검토 항목", "실패 분류", "RTL", "에이전트 작업"] as const;

export default function RunDetail() {
  const { id } = useParams();
  const info = useGet<RunInfo>(`/api/runs/${id}`);
  const detail = useGet<Detail>(`/api/runs/${id}/detail`);
  const [tab, setTab] = useState<(typeof TABS)[number]>("개요");
  return (
    <main className="page">
      <div className="page-head">
        <h1 className="mono">{id}</h1>
        <Status s={info.data?.status} />
        <span className="sub">읽기 전용. 고칠 것은 환류 양식으로 요청합니다.</span>
        <button onClick={() => { info.reload(); detail.reload(); }}>새로 읽기</button>
      </div>
      <Err msg={info.error || detail.error} />
      <div className="tabs" role="tablist">
        {TABS.map((t) => <button key={t} role="tab" className={t === tab ? "on" : ""} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      {info.data && detail.data && (
        <>
          {tab === "개요" && <Overview info={info.data} detail={detail.data} reload={info.reload} />}
          {tab === "모듈" && <Modules detail={detail.data} />}
          {tab === "검토 항목" && <Review detail={detail.data} />}
          {tab === "실패 분류" && <Failures detail={detail.data} />}
          {tab === "RTL" && <Rtl runId={id!} />}
          {tab === "에이전트 작업" && <Tasks runId={id!} detail={detail.data} />}
        </>
      )}
    </main>
  );
}

function Overview({ info, detail, reload }: { info: RunInfo; detail: Detail; reload: () => void }) {
  const user = useUser();
  return (
    <div className="grid2">
      <section className="panel stack">
        <h2>실행</h2>
        <table><tbody>
          <tr><th>블록</th><td>{info.block}</td></tr>
          <tr><th>종류</th><td>{info.kind} {info.kind !== "initial" && <span className="muted small">(환류 재실행)</span>}</td></tr>
          <tr><th>SPEC 버전</th><td className="mono">{short(info.spec_sha256)}</td></tr>
          <tr><th>제출</th><td>{info.by} · {info.created}</td></tr>
          <tr><th>에이전트 실행</th><td className="num">{info.agent_runs}</td></tr>
          <tr><th>선택</th><td className="mono">{info.chosen ? JSON.stringify(info.chosen) : "-"}</td></tr>
          <tr><th>검토 항목</th><td className="small">{Object.entries(detail.review_counts).map(([k, n]) => `${k} ${n}`).join(" · ") || "-"}</td></tr>
          <tr><th>테스트 교체</th><td className="small">{detail.tb_history.length}회</td></tr>
        </tbody></table>
      </section>
      <section className="panel stack">
        <h2>승인과 판정</h2>
        <table><thead><tr><th>종류</th><th>결정</th><th>누가</th><th>언제</th><th>SPEC</th></tr></thead><tbody>
          {info.approvals.map((a) => (
            <tr key={a.id}><td>{KIND_LABEL[a.kind] ?? a.kind}</td><td><Status s={a.decision} /></td><td>{a.by}</td>
              <td className="small">{a.at}</td><td className="mono small">{short(a.spec_sha)}</td></tr>
          ))}
          {info.approvals.length === 0 && <tr><td colSpan={5} className="muted">아직 없음</td></tr>}
        </tbody></table>
        <h3>RTL Freeze 판정</h3>
        <table><tbody>
          {["dv", "pi"].map((k) => {
            const s = info.signoffs.find((x) => x.kind === k);
            return <tr key={k}><th>{k === "dv" ? "DV 검증 완료" : "PI 구현 가능성"}</th>
              <td>{s ? <><Status s={s.decision} /> <span className="small">{s.by} · {s.at}</span></> : <span className="muted">없음</span>}</td></tr>;
          })}
        </tbody></table>
        {(can.signoffDv(user) || can.signoffPi(user)) && <Signoff runId={info.run_id} kind={can.signoffDv(user) ? "dv" : "pi"} done={reload} />}
      </section>
    </div>
  );
}

function Signoff({ runId, kind, done }: { runId: string; kind: "dv" | "pi"; done: () => void }) {
  const [note, setNote] = useState("");
  const act = useAction();
  const send = async (decision: string) => {
    if (await act.run(() => api.post(`/api/runs/${runId}/signoff`, { kind, decision, note }))) done();
  };
  return (
    <div className="stack">
      <label>{kind === "dv" ? "DV 검증 완료 판정" : "PI 구현 가능성 판정"} 근거
        <textarea id={`signoff-${kind}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <div className="row">
        <button className="primary" disabled={act.busy} onClick={() => send("pass")}>pass</button>
        <button className="danger" disabled={act.busy} onClick={() => send("fail")}>fail</button>
      </div>
      <Err msg={act.error} />
    </div>
  );
}

function Modules({ detail }: { detail: Detail }) {
  return (
    <div className="stack">
      <section className="panel">
        <h2>Block Top <span className="mono">{detail.top.module}</span></h2>
        <p className="small muted">인스턴스 {detail.top.instances.length}개, 연결 {detail.top.connections.length}개</p>
        <div className="scroll"><table><thead><tr><th>인스턴스</th><th>모듈</th><th>포트</th><th>후보</th></tr></thead><tbody>
          {detail.children.map((m) => (
            <tr key={m.module}>
              <td className="mono">{m.instance ?? "-"}</td>
              <td className="mono">{m.module}{detail.chosen?.[m.module] !== undefined && <span className="pill s-pass" style={{ marginLeft: 6 }}>c{detail.chosen[m.module]} 선택</span>}</td>
              <td className="mono small">{m.ports.join(", ")}</td>
              <td>
                <table><thead><tr><th>후보</th><th>상태</th><th>Repair</th><th>lint</th><th>검증</th><th>Arbiter</th><th>사유</th></tr></thead><tbody>
                  {m.candidates.map((c) => (
                    <tr key={c.c}><td className="mono">c{c.c}</td><td><Status s={c.status} /></td><td className="num">{c.repairs}</td>
                      <td className="num">{c.lint ?? "-"}</td>
                      <td className="small" style={{ whiteSpace: "nowrap" }}>{c.last_verify ? c.last_verify.e2.map((v) => `V${v.verifier} ${v.ok ? "통과" : "실패"}`).join(", ") : "-"}</td>
                      <td className="small">{c.arbiter?.join(", ") ?? "-"}</td><td className="small">{c.reason ?? (c.pending ? `승인 대기 ${c.pending}` : "")}</td></tr>
                  ))}
                </tbody></table>
              </td>
            </tr>
          ))}
        </tbody></table></div>
      </section>
      <section className="panel">
        <h2>진행 기록</h2>
        <div className="scroll" style={{ maxHeight: 360 }}><table><tbody>
          {detail.events.slice().reverse().map((e, i) => <tr key={i}><td className="mono small">{e.t}</td><td className="small">{e.kind}</td><td className="small">{e.msg}</td></tr>)}
        </tbody></table></div>
      </section>
    </div>
  );
}

function Review({ detail }: { detail: Detail }) {
  const [code, setCode] = useState("");
  const items = detail.review.filter((r) => !code || r.code === code);
  return (
    <section className="panel stack">
      <div className="row">
        <h2 style={{ margin: 0 }}>검토 항목</h2>
        <select id="review-code" value={code} onChange={(e) => setCode(e.target.value)}>
          <option value="">전체 ({detail.review.length})</option>
          {Object.entries(detail.review_counts).map(([k, n]) => <option key={k} value={k}>{k} ({n})</option>)}
        </select>
      </div>
      <div className="scroll"><table><thead><tr><th>코드</th><th>출처</th><th>위치</th><th>내용</th></tr></thead><tbody>
        {items.map((r, i) => <tr key={i}><td className="mono small">{r.code}</td><td className="small">{r.source}</td>
          <td className="mono small" style={{ maxWidth: 220, overflowWrap: "anywhere" }}>{r.where}</td><td className="small">{r.message}</td></tr>)}
      </tbody></table></div>
    </section>
  );
}

function Failures({ detail }: { detail: Detail }) {
  return (
    <section className="panel stack">
      <h2>실패 분류</h2>
      {detail.failures.length === 0 && <p className="muted">마지막 검증에서 실패한 후보가 없습니다.</p>}
      <div className="scroll"><table><thead><tr><th>후보</th><th>상태</th><th>사유</th><th>lint 조각 오류 수</th><th>Verifier 결과</th></tr></thead><tbody>
        {detail.failures.map((f) => (
          <tr key={f.candidate}><td className="mono">{f.candidate}</td><td><Status s={f.status} /></td><td className="small">{f.reason ?? "-"}</td>
            <td className="num">{f.last_verify?.e1 ?? "-"}</td>
            <td className="small">{f.last_verify?.e2.map((v) => `V${v.verifier} ${v.ok ? "통과" : "실패"}`).join(", ") ?? "-"}</td></tr>
        ))}
      </tbody></table></div>
      {detail.pending.length > 0 && (
        <>
          <h3>기댓값 수정안 (승인 대기 포함 전체)</h3>
          {detail.pending.map((p) => <div key={p.id} className="card"><b className="mono">{p.id}</b> {p.reqs?.join(", ")}<p className="small">{p.reason}</p><p className="small muted">수정안: {p.proposal}</p></div>)}
        </>
      )}
    </section>
  );
}

function Rtl({ runId }: { runId: string }) {
  const rtl = useGet<Record<string, RtlFile>>(`/api/runs/${runId}/rtl`);
  const files = Object.keys(rtl.data ?? {});
  const [file, setFile] = useState<string | null>(null);
  const [line, setLine] = useState<number | null>(null);
  const cur = file ?? files.find((f) => f.includes("_")) ?? files[0];
  const f = cur ? rtl.data?.[cur] : undefined;
  const node = useMemo(() => {
    if (!f || line === null) return null;
    const hits = f.srcmap.filter((e) => e.start <= line && line <= e.end);
    const frags = hits.filter((e) => e.fragment);
    const pick = (frags.length ? frags : hits).sort((a, b) => a.end - a.start - (b.end - b.start))[0];
    return pick ?? null;
  }, [f, line]);
  const irNode = useMemo(() => {
    if (!node || !f?.ir) return null;
    const [section, ...rest] = node.node.split("/");
    let cur: unknown = (f.ir as Record<string, unknown>)[section];
    for (const k of rest) {
      if (Array.isArray(cur)) cur = cur.find((x) => x && (x.id === k || x.name === k || x.bundle === k));
      else if (cur && typeof cur === "object") cur = (cur as Record<string, unknown>)[k];
    }
    return cur;
  }, [node, f]);
  if (rtl.error) return <Err msg={rtl.error} />;
  if (!f) return <p className="muted">RTL이 아직 없습니다 (통합 단계 뒤에 생김).</p>;
  const fragLines = new Set(f.srcmap.filter((e) => e.fragment && !isL1(e.node)).flatMap((e) => Array.from({ length: e.end - e.start + 1 }, (_, i) => e.start + i)));
  return (
    <div className="grid2" style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr)" }}>
      <section className="panel stack">
        <div className="row">
          {files.map((n) => <button key={n} className={n === cur ? "primary" : ""} onClick={() => { setFile(n); setLine(null); }}>{n}</button>)}
        </div>
        <p className="small muted">줄을 누르면 그 줄을 만든 IR 노드를 보여 줍니다. 칠한 줄은 에이전트가 쓴 동작(Repair 대상)이고, 나머지는 동결된 인터페이스(L1)와 생성기 골격입니다.</p>
        <div className="code" role="grid" aria-label={cur}>
          {f.text.split("\n").map((t, i) => {
            const n = i + 1;
            const cls = `${fragLines.has(n) ? "frag" : ""} ${line === n ? "sel" : ""}`;
            return [<div key={`l${n}`} className={`ln ${cls}`} onClick={() => setLine(n)}>{n}</div>,
              <div key={`t${n}`} className={`tx ${cls}`} onClick={() => setLine(n)}>{t || " "}</div>];
          })}
        </div>
      </section>
      <section className="panel stack" style={{ alignSelf: "start", position: "sticky", top: 64 }}>
        <h2>IR 노드</h2>
        {!node && <p className="muted small">줄을 고르세요.</p>}
        {node && (
          <>
            <div className="mono">{node.node}</div>
            <div className="small">{!node.fragment ? "골격 (생성기. 위반이면 생성기 버그)" : isL1(node.node) ? "동결된 인터페이스 L1 (바꾸려면 인터페이스 변경)" : "동작 조각 (Author/Repair가 씀. Repair 대상)"} · {node.start}~{node.end}행</div>
            <pre className="panel" style={{ maxHeight: "50vh", overflow: "auto" }}>{JSON.stringify(irNode, null, 1)}</pre>
          </>
        )}
      </section>
    </div>
  );
}

const L1_SECTIONS = new Set(["module", "role", "params", "domains", "power_domains", "ports", "instances"]);
const isL1 = (node: string) => L1_SECTIONS.has(node.split("/")[0]);

function Tasks({ runId, detail }: { runId: string; detail: Detail }) {
  const [name, setName] = useState<string | null>(null);
  const task = useGet<TaskDetail>(name ? `/api/runs/${runId}/tasks/${name}` : null);
  return (
    <div className="grid2" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,2fr)" }}>
      <section className="panel scroll">
        <table><thead><tr><th>작업</th><th>에이전트</th><th>결과</th><th>시간</th></tr></thead><tbody>
          {detail.tasks.map((t) => (
            <tr key={t.name} onClick={() => setName(t.name)} style={{ cursor: "pointer", background: t.name === name ? "var(--sunken)" : undefined }}>
              <td className="mono small">{t.name}</td><td className="small">{t.agent}</td><td><Status s={t.ok ? "ok" : "failed"} /></td>
              <td className="num small">{t.duration_s}s · {t.attempts}회</td></tr>
          ))}
        </tbody></table>
      </section>
      <section className="panel stack">
        {!name && <p className="muted">작업을 고르세요.</p>}
        <Err msg={task.error} />
        {task.data && (
          <>
            <h2 className="mono">{task.data.task}</h2>
            {task.data.errors?.length > 0 && <div className="err small">{task.data.errors.join(" / ")}</div>}
            <details open><summary>과제 (TASK.md)</summary><pre className="small">{task.data.task_md}</pre></details>
            {Object.entries(task.data.output_text).map(([k, v]) => (
              <details key={k}><summary className="mono">{k}</summary><pre className="small">{v}</pre></details>
            ))}
            <h3>Transcript (시도별 표준 출력 끝부분)</h3>
            {task.data.runs?.map((r) => (
              <div key={r.attempt} className="card">
                <div className="small muted">시도 {r.attempt} · 종료 코드 {String(r.returncode)} · {r.duration_s}s{r.timed_out ? " · 시간 초과" : ""}</div>
                <pre className="small">{r.stdout_tail || r.stderr_tail}</pre>
              </div>
            ))}
          </>
        )}
      </section>
    </div>
  );
}
