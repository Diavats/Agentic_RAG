// Every call to the PRISM backend lives in this one file.
// It talks to the live Render backend unless NEXT_PUBLIC_API_URL points elsewhere
// (e.g. NEXT_PUBLIC_API_URL=http://localhost:8077 in .env.local for local work).

export const API = process.env.NEXT_PUBLIC_API_URL ?? "https://prism-api-y5op.onrender.com";

// ---------- The shapes the backend sends back (src/trace.py) ----------

export type Domain = "medical" | "financial";

export type Source = {
  id: string;
  text: string;
  score: number;      // hybrid (RRF) score: bigger = better match
  rank: number;       // 1 = best
  source_file: string;
  source_type: string; // "textual" (Word) or "tabular" (spreadsheet row)
  domain: string;
};

export type Citation = { marker: string; source_id: string; resolved: boolean };

export type Trace = {
  question: string;
  routing: { domain: string; method: string; confidence: number | null; margin: number | null; scores: Record<string, number>; latency_ms: number };
  planning: { subqueries: string[]; was_decomposed: boolean; latency_ms: number };
  retrieval: { sources: Source[]; n_candidates: number; latency_ms: number };
  synthesis: { answer: string; citations: Citation[]; latency_ms: number };
  verification: { supported_claims: number; total_claims: number; score: number; latency_ms: number } | null;
  total_latency_ms: number;
};

// The five pipeline steps, in order. They are the five slots on an album page.
export const STAGES = ["routing", "planning", "retrieval", "synthesis", "verification"] as const;
export type Stage = (typeof STAGES)[number];

export type Quota = Record<"question" | "upload", { left: number; limit: number }>;

// ---------- Small helpers ----------

// Turn a failed response into a readable message (FastAPI puts it in "detail").
async function failure(res: Response): Promise<Error> {
  const body = await res.json().catch(() => null);
  const detail = body?.detail;
  return new Error(typeof detail === "string" ? detail : `Something went wrong (${res.status}).`);
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, init);
  if (!res.ok) throw await failure(res);
  return res.json();
}

// ---------- Simple calls ----------

export const health = () => getJson<{ status: string; warm: boolean }>("/health");
export const quota = () => getJson<Quota>("/quota");
export const benchmark = () => getJson<Record<string, any>>("/benchmark");
export const newSession = () => getJson<{ session_id: string }>("/session", { method: "POST" });
export const dropSession = (id: string) => fetch(`${API}/session/${id}`, { method: "DELETE" });

// ---------- Uploads ----------

// Free preview: is this file finance, medical, or neither? (No quota spent.)
export function classify(sessionId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return getJson<{ domain: Domain; scores: Record<string, number> }>(
    `/session/${sessionId}/classify`, { method: "POST", body: form });
}

// The real upload. `domain` is the (possibly corrected) guess.
export function upload(sessionId: string, file: File, domain: Domain) {
  const form = new FormData();
  form.append("file", file);
  form.append("domain", domain);
  return getJson<{ job_id: string; domain: Domain }>(
    `/session/${sessionId}/upload`, { method: "POST", body: form });
}

export type Job = { status: "pending" | "running" | "done" | "failed"; message: string; unit_count: number };
export const job = (sessionId: string, jobId: string) => getJson<Job>(`/session/${sessionId}/job/${jobId}`);

// ---------- Asking, streamed ----------

// Ask a question and call `onStage` each time a pipeline step finishes.
// The backend sends server-sent events: lines like `data: {"stage": ..., "data": ...}`.
export async function askStream(
  question: string,
  sessionId: string | null,
  onStage: (stage: string, data: any) => void,
) {
  const res = await fetch(`${API}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId, verify: true }),
  });
  if (!res.ok || !res.body) throw await failure(res);

  // Read the stream chunk by chunk; each event ends with a blank line.
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = JSON.parse(line.replace(/^data: /, ""));
      onStage(event.stage, event.data);
    }
  }
}
