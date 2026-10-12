import { Link } from "react-router-dom";
import type { RunSummary } from "../api";
import { Err, Status, short, useGet } from "../common";

export default function Runs() {
  const runs = useGet<RunSummary[]>("/api/runs");
  return (
    <main className="page">
      <div className="page-head">
        <h1>실행</h1>
        <span className="sub">파이프라인 실행과 승인 상태. 실행 제출은 SPEC 작업대에서 고정된 SPEC으로 합니다.</span>
        <button onClick={runs.reload} disabled={runs.loading}>새로 읽기</button>
      </div>
      <Err msg={runs.error} />
      <div className="panel scroll">
        <table>
          <thead>
            <tr><th>실행</th><th>블록</th><th>상태</th><th>종류</th><th>선택 후보</th><th>에이전트 실행</th><th>최종 승인</th><th>RTL Freeze</th><th>승인 대기</th><th>SPEC</th><th>제출</th></tr>
          </thead>
          <tbody>
            {(runs.data ?? []).map((r) => (
              <tr key={r.run_id}>
                <td><Link to={`/runs/${r.run_id}`} className="mono">{r.run_id}</Link></td>
                <td>{r.block}</td>
                <td><Status s={r.status} /></td>
                <td className="small">{r.kind}</td>
                <td className="mono small">{r.chosen ? Object.entries(r.chosen).map(([m, c]) => `${m}:c${c}`).join(", ") : "-"}</td>
                <td className="num">{r.agent_runs}</td>
                <td><Status s={r.approvals?.final_approval?.decision} /></td>
                <td><Status s={r.approvals?.rtl_freeze?.decision} /></td>
                <td className="mono small">{r.pending.join(", ") || "-"}</td>
                <td className="mono small">{short(r.spec_sha256)}</td>
                <td className="small">{r.by}<br /><span className="muted">{r.created}</span></td>
              </tr>
            ))}
            {runs.data?.length === 0 && <tr><td colSpan={11} className="muted">실행이 없습니다.</td></tr>}
          </tbody>
        </table>
      </div>
    </main>
  );
}
