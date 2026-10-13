// 게이트웨이 API. 쿠키 세션을 쓰고, 쓰기 요청에는 요청 위조 방지 헤더(X-CDD)를 붙인다.

export type User = {
  username: string;
  display: string;
  roles: string[];
  caps: string[];
  kind: "human" | "seat";
  seat?: string | null;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: method === "POST" ? { "Content-Type": "application/json", "X-CDD": "1" } : {},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, (data && data.error) || res.statusText);
  return data as T;
}

export const api = {
  get: <T>(path: string) => call<T>("GET", path),
  post: <T>(path: string, body: unknown = {}) => call<T>("POST", path, body),
};

export type ReviewItem = { code: string; severity: string; where: string; message: string; source: string };

export type RunSummary = {
  run_id: string;
  block: string;
  status: string;
  process: string;
  kind: string;
  created: string;
  by: string;
  spec_sha256: string;
  agent_runs: number;
  chosen: Record<string, number> | null;
  pending: string[];
  spec_id?: string | null;
  approvals?: { final_approval: Approval | null; rtl_freeze: Approval | null };
};

export type Approval = {
  id: number;
  kind: string;
  target: string;
  decision: string;
  by: string;
  roles: string;
  at: string;
  spec_sha: string | null;
  run_id: string | null;
  reqs: string[];
  note: string | null;
  extra: Record<string, unknown>;
};

export type Candidate = {
  c: number;
  status: string;
  repairs: number;
  lint: number | null;
  reason: string | null;
  arbiter: string[] | null;
  last_verify: { ok: boolean; e1: number; e2: { verifier: number; ok: boolean }[] } | null;
  pending?: string | null;
};

export type RunDetail = {
  run_id: string;
  status: string;
  top: { module: string; instances: { name: string; module: string }[]; connections: { id: string; from: string; to: string }[] };
  children: { module: string; role: string; instance: string | null; ports: string[]; candidates: Candidate[] }[];
  chosen: Record<string, number> | null;
  review: ReviewItem[];
  review_counts: Record<string, number>;
  failures: { candidate: string; status: string; reason: string | null; last_verify: Candidate["last_verify"] }[];
  tasks: { name: string; role: string; agent: string; ok: boolean; attempts: number; duration_s: number }[];
  events: { t: string; kind: string; msg: string }[];
  tb_history: { verifier: number; from: string; to: string }[];
  pending: { id: string; reqs: string[]; reason: string; proposal: string }[];
};

export type SrcEntry = { node: string; start: number; end: number; fragment?: boolean };
export type RtlFile = { text: string; srcmap: SrcEntry[]; ir: Record<string, unknown> | null };

export type TaskDetail = {
  task: string;
  role: string;
  agent: string;
  ok: boolean;
  duration_s: number;
  errors: string[];
  task_md: string | null;
  output_text: Record<string, string>;
  runs: { attempt: number; returncode: number | null; timed_out: boolean; duration_s: number; stdout_tail: string; stderr_tail?: string }[];
};

export type SpecQuestion = ReviewItem & { key: string; answer: { answer: string; by: string; at: string } | null };

export type Spec = {
  id: string;
  name: string;
  source_kind: "pdf" | "md";
  status: "draft" | "freeze_requested" | "frozen";
  created_by: string;
  created: string;
  frozen_sha: string | null;
  sha: string;
  markdown: string;
  original_markdown: string | null;
  pages: number;
  versions: { sha: string; by: string; at: string; note: string | null }[];
  figures: { n: number; page: number | null; caption: string | null; has_wavejson: boolean }[];
  checks: { gate: string; requirements?: number; issues: ReviewItem[]; questions: SpecQuestion[] };
};

export type PendingItem = {
  kind: string;
  target: string;
  title: string;
  run_id?: string;
  spec_sha?: string | null;
  reqs?: string[] | null;
  detail?: Record<string, unknown>;
};

export const can = {
  approve: (u: User) => u.kind === "human" && u.roles.includes("approver"),
  design: (u: User) => u.roles.includes("design"),
  feedback: (u: User) => u.roles.includes("design") && u.caps.includes("design_lead"),
  signoffDv: (u: User) => u.roles.includes("verification"),
  signoffPi: (u: User) => u.roles.includes("implementation"),
  admin: (u: User) => u.roles.includes("admin"),
};

export const KIND_LABEL: Record<string, string> = {
  spec_freeze: "SPEC 고정",
  final_approval: "최종 승인",
  rtl_freeze: "RTL Freeze",
  expectation_change: "기댓값 변경",
  spec_change: "SPEC 변경 요청",
  repair_conflict: "Repair 충돌",
};

export const ROLE_LABEL: Record<string, string> = {
  admin: "관리자",
  design: "설계",
  verification: "검증",
  implementation: "구현",
  approver: "승인자",
};
