import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, ApiError, ROLE_LABEL, type User } from "./api";
import { Err, UserContext, useAction } from "./common";
import Approvals from "./pages/Approvals";
import Feedback from "./pages/Feedback";
import RunDetail from "./pages/RunDetail";
import Runs from "./pages/Runs";
import Seats from "./pages/Seats";
import SpecView from "./pages/SpecView";
import Specs from "./pages/Specs";

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const act = useAction();
  return (
    <form
      className="panel login stack"
      onSubmit={async (e) => {
        e.preventDefault();
        const u = await act.run(() => api.post<User>("/api/login", { username, password }));
        if (u) onLogin(u);
      }}
    >
      <h1>Chip Design Department</h1>
      <p className="muted small">게이트웨이에 로그인합니다. 계정은 관리자가 만듭니다.</p>
      <label>
        사용자 이름
        <input id="login-user" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label>
        비밀번호
        <input id="login-pw" type="password" autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)} />
      </label>
      <Err msg={act.error} />
      <button className="primary" disabled={act.busy || !username || !password}>로그인</button>
    </form>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useEffect(() => {
    api.get<User>("/api/me").then(setUser).catch((e) => setUser(e instanceof ApiError && e.status === 401 ? null : null));
  }, []);
  if (user === undefined) return null;
  if (user === null) return <Login onLogin={setUser} />;
  const nav = [
    ["/runs", "실행"],
    ["/specs", "SPEC 작업대"],
    ["/approvals", "승인함"],
    ["/feedback", "환류"],
    ["/seats", "Seat"],
  ];
  return (
    <UserContext.Provider value={user}>
      <header className="top">
        <span className="brand">Chip Design Department<small>게이트웨이</small></span>
        <nav className="nav">
          {nav.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
          ))}
        </nav>
        <span className="who">
          <span><b>{user.username}</b>{user.display !== user.username && ` (${user.display})`}</span>
          <span>{user.roles.map((r) => ROLE_LABEL[r] ?? r).join(", ")}</span>
          {user.caps.includes("design_lead") && " · Design-lead"}
          <button onClick={async () => { await api.post("/api/logout"); setUser(null); }}>로그아웃</button>
        </span>
      </header>
      <Routes>
        <Route path="/" element={<Navigate to="/runs" replace />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/runs/:id" element={<RunDetail />} />
        <Route path="/specs" element={<Specs />} />
        <Route path="/specs/:id" element={<SpecView />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/feedback" element={<Feedback />} />
        <Route path="/seats" element={<Seats />} />
        <Route path="*" element={<div className="page">없는 화면입니다.</div>} />
      </Routes>
    </UserContext.Provider>
  );
}
