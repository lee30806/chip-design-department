import { Link } from "react-router-dom";
import { Err, Status, useGet } from "../common";

type Dash = {
  runs: Record<string, number>;
  active: { run_id: string; block: string; status: string; agent_runs: number; lineage_agent_runs?: number; pending: string[]; created: string }[];
  pending: Record<string, number>;
  notifications: { at: string; kind: string; run_id: string | null; message: string }[];
  generator_bugs_open: number;
  seats: { available: boolean; states: Record<string, number> };
};

const KIND: Record<string, string> = {
  spec_freeze: "SPEC 고정", final_approval: "최종 승인", rtl_freeze: "RTL Freeze", expectation_change: "기댓값 변경",
  spec_change: "SPEC 변경 요청", repair_conflict: "Repair 충돌",
};

export default function Dashboard() {
  const d = useGet<Dash>("/api/dashboard");
  const x = d.data;
  return (
    <main className="page">
      <div className="page-head">
        <h1>대시보드</h1>
        <span className="sub">실행, 승인 대기, 알림, 생성기 버그, Seat 상태를 한눈에 봅니다.</span>
        <button onClick={d.reload} disabled={d.loading}>새로 읽기</button>
      </div>
      <Err msg={d.error} />
      {x && (
        <>
          <div className="tiles">
            <Link to="/runs" className="tile panel"><b>{Object.values(x.runs).reduce((a, b) => a + b, 0)}</b><span>실행</span>
              <small>{Object.entries(x.runs).map(([k, v]) => `${k} ${v}`).join(" · ") || "-"}</small></Link>
            <Link to="/approvals" className="tile panel"><b>{Object.values(x.pending).reduce((a, b) => a + b, 0)}</b><span>승인함 대기</span>
              <small>{Object.entries(x.pending).map(([k, v]) => `${KIND[k] ?? k} ${v}`).join(" · ") || "-"}</small></Link>
            <Link to="/feedback" className="tile panel"><b>{x.generator_bugs_open}</b><span>열린 생성기 버그</span><small>환류 화면에서 처리</small></Link>
            <Link to="/seats" className="tile panel"><b>{x.seats.available ? Object.values(x.seats.states).reduce((a, b) => a + b, 0) : "-"}</b>
              <span>Seat</span><small>{x.seats.available ? Object.entries(x.seats.states).map(([k, v]) => `${k} ${v}`).join(" · ") : "OpenRig 연결 안 됨"}</small></Link>
          </div>
          <section className="panel scroll">
            <h2>진행 중인 실행</h2>
            <table>
              <thead><tr><th>실행</th><th>블록</th><th>상태</th><th>에이전트 실행</th><th>계보 합계</th><th>승인 대기</th><th>제출</th></tr></thead>
              <tbody>
                {x.active.map((r) => (
                  <tr key={r.run_id}>
                    <td><Link to={`/runs/${r.run_id}`} className="mono">{r.run_id}</Link></td>
                    <td>{r.block}</td><td><Status s={r.status} /></td>
                    <td className="num">{r.agent_runs}</td><td className="num">{r.lineage_agent_runs ?? "-"}</td>
                    <td className="mono small">{r.pending.join(", ") || "-"}</td><td className="small muted">{r.created}</td>
                  </tr>
                ))}
                {x.active.length === 0 && <tr><td colSpan={7} className="muted">진행 중인 실행이 없습니다.</td></tr>}
              </tbody>
            </table>
          </section>
          <section className="panel scroll">
            <h2>최근 알림</h2>
            <table>
              <thead><tr><th>시각</th><th>종류</th><th>실행</th><th>내용</th></tr></thead>
              <tbody>
                {x.notifications.map((n, i) => (
                  <tr key={i}><td className="small muted">{n.at}</td><td className="small">{n.kind}</td>
                    <td className="mono small">{n.run_id ? <Link to={`/runs/${n.run_id}`}>{n.run_id}</Link> : "-"}</td>
                    <td className="small">{n.message}</td></tr>
                ))}
                {x.notifications.length === 0 && <tr><td colSpan={4} className="muted">알림이 없습니다.</td></tr>}
              </tbody>
            </table>
          </section>
        </>
      )}
    </main>
  );
}
