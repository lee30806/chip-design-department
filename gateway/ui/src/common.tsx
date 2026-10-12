import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, type User } from "./api";

export const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext)!;

/** GET 한 번과 다시 읽기. 오류는 메시지로 돌려준다. */
export function useGet<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    load();
  }, [load]);
  return { data, error, loading, reload: load, setData };
}

export function Status({ s }: { s: string | null | undefined }) {
  if (!s) return <span className="muted">-</span>;
  const label: Record<string, string> = {
    pass: "통과", failed: "실패", waiting_approval: "승인 대기", running: "실행 중", paused_quota: "사용량 한도",
    halted: "멈춤", stopped: "멈춤", draft: "작성 중", freeze_requested: "고정 요청", frozen: "고정됨",
    approved: "승인", rejected: "반려", spec_rejected: "SPEC 거부", interface_change: "인터페이스 변경",
    budget_exceeded: "예산 초과", starting: "시작 중", not_started: "시작 전",
  };
  return <span className={`pill s-${s}`}>{label[s] ?? s}</span>;
}

export function Err({ msg }: { msg: string | null }) {
  return msg ? <div className="err small" role="alert">{msg}</div> : null;
}

/** 쓰기 요청 버튼: 진행 중 표시와 오류 표시를 맡는다. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run, setError };
}

export function short(sha: string | null | undefined) {
  return sha ? sha.slice(0, 10) : "-";
}
