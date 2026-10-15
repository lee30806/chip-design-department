import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { api } from "../api";
import { Err, useAction, useGet, useUser } from "../common";

type SeatsInfo = { available: boolean; error?: string; rig?: Record<string, unknown> | null; nodes?: Record<string, unknown>[] };
type Msg = { mid: string; seat: string; username: string; display: string; kind: string; text: string; sent_at: string;
  status: string; reply: string | null; replied_at: string | null; error: string | null };

const pick = (o: Record<string, unknown>, ...keys: string[]) => {
  for (const k of keys) if (o[k] !== undefined && o[k] !== null) return String(o[k]);
  return "-";
};
const activity = (n: Record<string, unknown>) => String((n.agentActivity as Record<string, unknown> | undefined)?.state ?? pick(n, "status", "state"));
const isLead = (id: string) => id.endsWith(".lead") || id === "lead.chip";
const STATUS: Record<string, string> = { sent: "보냄 (답 기다림)", replying: "답 쓰는 중", replied: "답함", failed: "보내지 못함" };

function Chat({ seat }: { seat: string }) {
  const user = useUser();
  const msgs = useGet<Msg[]>(`/api/seats/${seat}/messages`);
  const [text, setText] = useState("");
  const [kind, setKind] = useState("chat");
  const act = useAction();
  const canInstruct = isLead(seat) && (user.roles.includes("design") || user.roles.includes("approver"));
  const waiting = (msgs.data ?? []).some((m) => m.status === "sent" || m.status === "replying");
  useEffect(() => {   // 답을 기다리는 동안 5초마다 화면을 다시 읽는다
    if (!waiting) return;
    const t = setInterval(msgs.reload, 5000);
    return () => clearInterval(t);
  }, [waiting, msgs.reload]);
  if (user.kind !== "human") return <p className="small muted">Seat 계정은 Web UI 대화를 쓰지 않습니다.</p>;
  return (
    <section className="panel stack">
      <h2>{seat} 와 대화</h2>
      <p className="small muted">게이트웨이가 OpenRig로 Seat 화면에 보내고, Seat가 화면에 쓴 답을 읽어 보여 줍니다. 보낸 사람과 메시지 ID가 함께 갑니다.</p>
      <Err msg={msgs.error} />
      <div className="stack chat">
        {(msgs.data ?? []).map((m) => (
          <div key={m.mid} className="msg">
            <div className="small muted">{m.sent_at} · {m.display} · {m.kind === "instruction" ? "작업 지시" : "대화"} · {m.mid} · {STATUS[m.status] ?? m.status}</div>
            <div className="mine">{m.text}</div>
            {m.reply && <pre className="reply small">{m.reply}</pre>}
            {m.error && <div className="err small">{m.error}</div>}
          </div>
        ))}
        {msgs.data?.length === 0 && <p className="small muted">아직 대화가 없습니다.</p>}
      </div>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={kind === "instruction" ? "lead에게 줄 작업 지시" : "질문이나 메시지"} />
      <div className="row">
        {canInstruct && (
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="chat">대화</option>
            <option value="instruction">작업 지시</option>
          </select>
        )}
        <button className="primary" disabled={act.busy || !text.trim()}
          onClick={async () => { const r = await act.run(() => api.post(`/api/seats/${seat}/messages`, { text, kind })); if (r) { setText(""); msgs.reload(); } }}>보내기</button>
        <button onClick={msgs.reload}>답 다시 읽기</button>
      </div>
      <Err msg={act.error} />
    </section>
  );
}

// 데몬이 Seat 화면을 고정 크기(90x27)로 맞추므로 xterm도 같은 크기로 둔다
const COLS = 90, ROWS = 27;

function SeatTerminal({ seat }: { seat: string }) {
  const user = useUser();
  const box = useRef<HTMLDivElement>(null);
  const sock = useRef<WebSocket | null>(null);
  const [state, setState] = useState("연결 중");
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!box.current || user.kind !== "human") return;
    const term = new Terminal({ cols: COLS, rows: ROWS, disableStdin: true, scrollback: 0, cursorBlink: false, fontSize: 12,
      fontFamily: getComputedStyle(document.documentElement).getPropertyValue("--mono") || "monospace" });
    term.open(box.current);
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/seats/${encodeURIComponent(seat)}/terminal`);
    sock.current = ws;
    let off = 0;
    const scroll = (n: number) => {
      off = n;
      setOffset(n);
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "scroll", offset: n }));
    };
    term.attachCustomWheelEventHandler((ev) => {   // 휠은 xterm이 아니라 데몬의 화면 기록을 넘긴다
      const next = Math.max(0, off + (ev.deltaY < 0 ? 3 : -3));
      if (next !== off) scroll(next);
      ev.preventDefault();
      return false;
    });
    setState("연결 중");
    setOffset(0);
    ws.onopen = () => setState("실시간");
    ws.onmessage = (e) => { if (typeof e.data === "string") term.write(e.data); };
    ws.onclose = (e) => setState(e.reason ? `끊김: ${e.reason}` : e.code === 1006 ? "연결할 수 없음 (OpenRig 데몬의 웹 UI가 꺼져 있거나 Seat 세션이 없음)" : "끊김");
    return () => { ws.close(); term.dispose(); sock.current = null; };
  }, [seat, attempt, user.kind]);
  if (user.kind !== "human") return <p className="small muted">Seat 계정은 Web UI 터미널을 쓰지 않습니다.</p>;
  return (
    <section className="panel stack">
      <h2>{seat} 터미널</h2>
      <p className="small muted">OpenRig 데몬이 보내는 Seat 화면을 그대로 보여 줍니다. 읽기 전용이라 키 입력은 Seat에 가지 않습니다. 휠로 이전 화면을 봅니다.</p>
      <div className="row small">
        <span className="pill">{offset > 0 ? `${offset}줄 위` : state}</span>
        {offset > 0 && <button onClick={() => { setOffset(0); sock.current?.send(JSON.stringify({ type: "scroll", offset: 0 })); }}>실시간으로</button>}
        <button onClick={() => setAttempt((a) => a + 1)}>다시 연결</button>
      </div>
      <div className="term" ref={box} />
    </section>
  );
}

export default function Seats() {
  const seats = useGet<SeatsInfo>("/api/seats");
  const [sel, setSel] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "term">("chat");
  const d = seats.data;
  const seatNodes = (d?.nodes ?? []).filter((n) => !pick(n, "logicalId", "logical_id", "id").startsWith("infra."));
  return (
    <main className="page">
      <div className="page-head">
        <h1>Seat</h1>
        <span className="sub">OpenRig 데몬에서 읽은 부서 계층의 Seat 상태, 터미널(읽기 전용)과 대화. 작업 지시는 lead Seat에만 보냅니다.</span>
        <button onClick={seats.reload}>새로 읽기</button>
      </div>
      <Err msg={seats.error} />
      {d && !d.available && <p className="panel">OpenRig 데몬에 연결할 수 없습니다. {d.error}</p>}
      {d?.available && !d.rig && <p className="panel">chip-dept rig가 올라와 있지 않습니다.</p>}
      {d?.available && d.rig && (
        <div className="panel scroll">
          <table>
            <thead><tr><th>Seat</th><th>런타임</th><th>활동</th><th></th></tr></thead>
            <tbody>
              {seatNodes.map((n, i) => {
                const id = pick(n, "logicalId", "logical_id", "id");
                return (
                  <tr key={i} className={id === sel ? "on" : ""}>
                    <td className="mono">{id}{isLead(id) && <span className="pill">lead</span>}</td>
                    <td className="small">{pick(n, "runtime")}</td>
                    <td className="small">{activity(n)}</td>
                    <td><div className="row">
                      <button onClick={() => { setSel(id); setView("term"); }}>터미널</button>
                      <button onClick={() => { setSel(id); setView("chat"); }}>대화</button>
                    </div></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {sel && view === "term" && <SeatTerminal key={sel} seat={sel} />}
      {sel && view === "chat" && <Chat key={sel} seat={sel} />}
    </main>
  );
}
