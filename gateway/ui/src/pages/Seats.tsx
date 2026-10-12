import { Err, useGet } from "../common";

type SeatsInfo = { available: boolean; error?: string; rig?: Record<string, unknown> | null; nodes?: Record<string, unknown>[] };

const pick = (o: Record<string, unknown>, ...keys: string[]) => {
  for (const k of keys) if (o[k] !== undefined && o[k] !== null) return String(o[k]);
  return "-";
};

export default function Seats() {
  const seats = useGet<SeatsInfo>("/api/seats");
  const d = seats.data;
  return (
    <main className="page">
      <div className="page-head">
        <h1>Seat</h1>
        <span className="sub">OpenRig 데몬에서 읽은 부서 계층의 Seat 상태 (조회만).</span>
        <button onClick={seats.reload}>새로 읽기</button>
      </div>
      <Err msg={seats.error} />
      {d && !d.available && <p className="panel">OpenRig 데몬에 연결할 수 없습니다. {d.error}</p>}
      {d?.available && !d.rig && <p className="panel">chip-dept rig가 올라와 있지 않습니다.</p>}
      {d?.available && d.rig && (
        <div className="panel scroll">
          <table>
            <thead><tr><th>Seat</th><th>세션</th><th>런타임</th><th>상태</th></tr></thead>
            <tbody>
              {(d.nodes ?? []).map((n, i) => (
                <tr key={i}>
                  <td className="mono">{pick(n, "logicalId", "logical_id", "id")}</td>
                  <td className="mono small">{pick(n, "sessionName", "session_name", "canonicalSessionName")}</td>
                  <td className="small">{pick(n, "runtime")}</td>
                  <td className="small">{pick(n, "status", "state", "lifecycle")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
