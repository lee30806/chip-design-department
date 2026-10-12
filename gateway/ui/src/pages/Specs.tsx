import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, can, type Spec } from "../api";
import { Err, Status, short, useAction, useGet, useUser } from "../common";

type SpecRow = Pick<Spec, "id" | "name" | "source_kind" | "status" | "created_by" | "created" | "frozen_sha">;

export default function Specs() {
  const user = useUser();
  const list = useGet<SpecRow[]>("/api/specs");
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const act = useAction();
  const upload = async () => {
    if (!file) return;
    const buf = new Uint8Array(await file.arrayBuffer());
    let bin = "";
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    const s = await act.run(() => api.post<Spec>("/api/specs", { name: name || file.name, filename: file.name, content_b64: btoa(bin) }));
    if (s) nav(`/specs/${s.id}`);
  };
  return (
    <main className="page">
      <div className="page-head">
        <h1>SPEC 작업대</h1>
        <span className="sub">원본과 변환 결과를 대조하고, 검사 질문에 답한 뒤 고정을 요청합니다. 고정은 승인자가 승인함에서 합니다.</span>
      </div>
      {can.design(user) && (
        <section className="panel row">
          <label>이름<input id="spec-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="블록 이름" /></label>
          <label>원본 (PDF 또는 Markdown)<input id="spec-file" type="file" accept=".pdf,.md,.markdown,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          <button className="primary" disabled={!file || act.busy} onClick={upload}>{act.busy ? "변환 중…" : "올리고 변환"}</button>
          <Err msg={act.error} />
        </section>
      )}
      <Err msg={list.error} />
      <div className="panel scroll">
        <table>
          <thead><tr><th>SPEC</th><th>원본</th><th>상태</th><th>고정된 버전</th><th>만든 사람</th></tr></thead>
          <tbody>
            {(list.data ?? []).map((s) => (
              <tr key={s.id}>
                <td><Link to={`/specs/${s.id}`}>{s.name}</Link><div className="mono small muted">{s.id}</div></td>
                <td>{s.source_kind.toUpperCase()}</td><td><Status s={s.status} /></td>
                <td className="mono small">{short(s.frozen_sha)}</td><td className="small">{s.created_by}<br /><span className="muted">{s.created}</span></td>
              </tr>
            ))}
            {list.data?.length === 0 && <tr><td colSpan={5} className="muted">작업 공간이 없습니다. 원본을 올려 시작합니다.</td></tr>}
          </tbody>
        </table>
      </div>
    </main>
  );
}
