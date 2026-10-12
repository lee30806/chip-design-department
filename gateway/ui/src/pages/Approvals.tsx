import { useState } from "react";
import { Link } from "react-router-dom";
import { api, can, KIND_LABEL, type Approval, type PendingItem } from "../api";
import { Err, Status, short, useAction, useGet, useUser } from "../common";

export default function Approvals() {
  const user = useUser();
  const pending = useGet<PendingItem[]>("/api/approvals/pending");
  const records = useGet<Approval[]>("/api/approvals");
  const [tab, setTab] = useState<"pending" | "records">("pending");
  const reload = () => { pending.reload(); records.reload(); };
  return (
    <main className="page">
      <div className="page-head">
        <h1>승인함</h1>
        <span className="sub">{can.approve(user) ? "승인자로 결정합니다. 모든 결정은 기록에 남습니다." : "승인과 반려는 승인자 역할만 합니다. 이 화면에서는 볼 수만 있습니다."}</span>
        <button onClick={reload}>새로 읽기</button>
      </div>
      <div className="tabs">
        <button className={tab === "pending" ? "on" : ""} onClick={() => setTab("pending")}>대기 ({pending.data?.length ?? 0})</button>
        <button className={tab === "records" ? "on" : ""} onClick={() => setTab("records")}>승인 기록 ({records.data?.length ?? 0})</button>
      </div>
      <Err msg={pending.error || records.error} />
      {tab === "pending" && (
        <div className="stack">
          {(pending.data ?? []).map((p) => <PendingCard key={`${p.kind}:${p.target}`} item={p} canDecide={can.approve(user)} done={reload} />)}
          {pending.data?.length === 0 && <p className="muted">기다리는 항목이 없습니다.</p>}
        </div>
      )}
      {tab === "records" && (
        <div className="panel scroll">
          <table>
            <thead><tr><th>#</th><th>종류</th><th>대상</th><th>결정</th><th>누가</th><th>언제</th><th>SPEC 버전</th><th>실행</th><th>요구사항</th><th>메모</th></tr></thead>
            <tbody>
              {(records.data ?? []).map((a) => (
                <tr key={a.id}>
                  <td className="num">{a.id}</td><td>{KIND_LABEL[a.kind] ?? a.kind}</td><td className="mono small">{a.target}</td>
                  <td><Status s={a.decision} /></td><td>{a.by}<div className="small muted">{a.roles}</div></td><td className="small">{a.at}</td>
                  <td className="mono small">{short(a.spec_sha)}</td>
                  <td className="mono small">{a.run_id ? <Link to={`/runs/${a.run_id}`}>{a.run_id}</Link> : "-"}</td>
                  <td className="mono small">{a.reqs.join(", ") || "-"}</td><td className="small">{a.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function PendingCard({ item, canDecide, done }: { item: PendingItem; canDecide: boolean; done: () => void }) {
  const [note, setNote] = useState("");
  const act = useAction();
  const d = item.detail ?? {};
  const decide = async (decision: string) => {
    if (await act.run(() => api.post("/api/approvals", { kind: item.kind, target: item.target, decision, note }))) done();
  };
  const blocked = item.kind === "rtl_freeze" && !d.ready;
  return (
    <div className={`card stack k-${item.kind}`}>
      <div className="row">
        <b>{KIND_LABEL[item.kind] ?? item.kind}</b>
        <span>{item.title}</span>
        {item.run_id && <Link className="mono small" to={`/runs/${item.run_id}`}>{item.run_id}</Link>}
        {item.kind === "spec_freeze" && <Link className="small" to={`/specs/${item.target}`}>SPEC 보기</Link>}
        <span className="mono small muted">SPEC {short(item.spec_sha)}</span>
        {item.reqs && item.reqs.length > 0 && <span className="mono small">{item.reqs.join(", ")}</span>}
      </div>
      {item.kind === "expectation_change" && (
        <div className="small stack">
          <div>Verifier {String(d.verifier)} · 후보 묶음 c{String(d.c)}</div>
          <div><b>판정 이유</b> {String(d.reason ?? "")}</div>
          <div><b>수정안</b> {String(d.proposal ?? "")}</div>
        </div>
      )}
      {item.kind === "spec_change" && (
        <div className="small stack">
          <div><b>이유</b> {String(d.reason ?? "")} <span className="muted">({String(d.by ?? "")}, {String(d.source ?? "")})</span></div>
          <pre className="small">{JSON.stringify(d.spec_diff, null, 1)}</pre>
        </div>
      )}
      {item.kind === "rtl_freeze" && (
        <div className="small">판정: DV {String((d.signoffs as Record<string, { decision: string }>)?.dv?.decision ?? "없음")} · PI {String((d.signoffs as Record<string, { decision: string }>)?.pi?.decision ?? "없음")}
          {blocked && <span className="err"> · 두 판정이 모두 pass여야 승인할 수 있음</span>}</div>
      )}
      {canDecide && (
        <div className="row">
          <input id={`note-${item.kind}-${item.target}`} style={{ flex: 1, minWidth: 200 }} value={note} onChange={(e) => setNote(e.target.value)} placeholder="메모 (반려 사유 등)" />
          <button className="primary" disabled={act.busy || blocked} onClick={() => decide("approved")}>승인</button>
          <button className="danger" disabled={act.busy} onClick={() => decide("rejected")}>반려</button>
        </div>
      )}
      <Err msg={act.error} />
    </div>
  );
}
