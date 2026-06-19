"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

// ── Types ─────────────────────────────────────────────────────────────────────

type Dataset = { id: string; name: string };
type Column  = { name: string; type: string };
type Table   = { table_name: string; filename: string; n_rows: number; n_cols: number; columns: Column[] };
type ChartSpec = { data: unknown[]; layout: Record<string, unknown> };
type Msg = { role: "user" | "assistant"; text: string; runId?: string; chartSpec?: ChartSpec };

type SessionInfo = {
  id: string; title: string; dataset_id: string | null; dataset_name?: string;
  run_count: number; total_input_tokens: number; total_output_tokens: number;
  total_cost_usd: number; created_at: string; last_active_at: string;
  runs?: RunRow[];
};

type RunRow = {
  id: string; goal: string; status: string; answer: string; iterations: number;
  input_tokens: number; output_tokens: number; cost_usd: number; created_at: string;
};

type SpanRow = {
  id: string; name: string; kind: string; duration_ms: number;
  attributes: Record<string, unknown>;
};

type NumStat  = { type: "numeric"; min: number | null; max: number | null; avg: number | null; null_count: number };
type CatStat  = { type: "categorical"; top_values: [string | null, number][] };
type ColStat  = NumStat | CatStat;
type DashData = { id: string; name: string; tables: Table[]; col_stats: Record<string, Record<string, ColStat>> };

// ── Helpers ───────────────────────────────────────────────────────────────────

async function getJSON(path: string) {
  const r = await fetch(`${API}${path}`);
  return r.json();
}

function fmtK(n: number): string {
  if (!n) return "0";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function fmtCost(usd: number): string {
  if (!usd) return "$0";
  if (usd < 0.0001) return "<$0.0001";
  return `~$${usd.toFixed(4)}`;
}

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const KIND_CLS: Record<string, string> = {
  LLM:      "bg-blue-100 text-blue-800",
  TOOL:     "bg-green-100 text-green-800",
  INTERNAL: "bg-slate-100 text-slate-600",
};

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Home() {
  // Datasets
  const [datasets, setDatasets]   = useState<Dataset[]>([]);
  const [selected, setSelected]   = useState<string>(() =>
    typeof window !== "undefined" ? localStorage.getItem("dc_dataset_id") || "" : ""
  );
  const [tables, setTables]       = useState<Table[]>([]);
  const [newName, setNewName]     = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // Chat
  const [goal, setGoal]         = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState("");
  const [streaming, setStreaming] = useState("");
  const [threadId, setThreadId] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("dc_thread_id") || crypto.randomUUID();
    }
    return crypto.randomUUID();
  });
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Tabs
  const [leftTab, setLeftTab]   = useState<"datasets" | "sessions">("datasets");
  const [rightTab, setRightTab] = useState<"chat" | "dashboard" | "traces">("chat");

  // Sessions + traces
  const [sessions, setSessions]       = useState<SessionInfo[]>([]);
  const [currentSess, setCurrentSess] = useState<SessionInfo | null>(null);
  const [traceRuns, setTraceRuns]     = useState<RunRow[]>([]);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runSpans, setRunSpans]       = useState<Record<string, SpanRow[]>>({});

  // Dashboard
  const [dash, setDash]         = useState<DashData | null>(null);
  const [dashBusy, setDashBusy] = useState(false);

  const prevDs = useRef<string>("");  // unused after refactor but kept for safety

  // ── Data loaders ─────────────────────────────────────────────────────────

  const loadDatasets = useCallback(async () => {
    const j = await getJSON("/datasets");
    if (j.ok) {
      setDatasets(j.data);
      // Only fall back to first dataset if nothing is saved in localStorage
      setSelected((cur) => {
        if (cur) return cur;
        const saved = typeof window !== "undefined" ? localStorage.getItem("dc_dataset_id") || "" : "";
        return saved || (j.data[0]?.id ?? "");
      });
    }
  }, []);

  const loadSchema = useCallback(async (id: string) => {
    if (!id) return setTables([]);
    const j = await getJSON(`/datasets/${id}`);
    if (j.ok) setTables(j.data.tables ?? []);
  }, []);

  const loadSessions = useCallback(async () => {
    const j = await getJSON("/sessions");
    if (j.ok) setSessions(j.data);
  }, []);

  const refreshSess = useCallback(async (tid?: string) => {
    const id = tid ?? threadId;
    if (!id) return;
    const j = await getJSON(`/sessions/${id}`);
    if (j.ok) {
      setCurrentSess(j.data);
      setTraceRuns([...(j.data.runs ?? [])].reverse());
    }
  }, [threadId]);

  const loadDash = useCallback(async (dsId: string) => {
    if (!dsId) return;
    setDashBusy(true);
    try {
      const j = await getJSON(`/datasets/${dsId}/summary`);
      setDash(j.ok ? j.data : null);
    } finally { setDashBusy(false); }
  }, []);

  const loadSpans = useCallback(async (runId: string) => {
    if (runSpans[runId]) return;
    const j = await getJSON(`/runs/${runId}/spans`);
    if (j.ok) setRunSpans((p) => ({ ...p, [runId]: j.data }));
  }, [runSpans]);

  // ── Session management ────────────────────────────────────────────────────

  const newSession = useCallback(() => {
    const id = crypto.randomUUID();
    setThreadId(id);
    setMessages([]);
    setCurrentSess(null);
    setTraceRuns([]);
    setExpandedRun(null);
    setRunSpans({});
    setRightTab("chat");
  }, []);

  const switchSession = useCallback((sess: SessionInfo) => {
    setThreadId(sess.id);
    setMessages([]);
    setCurrentSess(sess);
    setTraceRuns([...(sess.runs ?? [])].reverse());
    if (sess.dataset_id) setSelected(sess.dataset_id);
    setLeftTab("datasets");
    setRightTab("chat");
  }, []);

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => { loadDatasets(); }, [loadDatasets]);
  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => { loadSchema(selected); }, [selected, loadSchema]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);
  useEffect(() => { localStorage.setItem("dc_thread_id", threadId); refreshSess(); }, [threadId, refreshSess]);

  useEffect(() => {
    if (selected) localStorage.setItem("dc_dataset_id", selected);
  }, [selected]);

  useEffect(() => {
    if (rightTab === "dashboard" && selected) loadDash(selected);
  }, [rightTab, selected, loadDash]);

  useEffect(() => {
    if (rightTab === "traces") refreshSess();
  }, [rightTab, refreshSess]);

  // ── Dataset management ────────────────────────────────────────────────────

  async function createDataset() {
    if (!newName.trim()) return;
    const r = await fetch(`${API}/datasets`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    const j = await r.json();
    if (j.ok) { setNewName(""); await loadDatasets(); setSelected(j.data.id); }
  }

  async function uploadFile(file: File | undefined) {
    if (!file || !selected) return;
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${API}/datasets/${selected}/files`, { method: "POST", body: fd });
    const j = await r.json();
    if (!j.ok) setError(j.error ?? "upload failed");
    else { await loadSchema(selected); if (rightTab === "dashboard") loadDash(selected); }
    if (fileRef.current) fileRef.current.value = "";
  }

  // ── Chat ──────────────────────────────────────────────────────────────────

  async function ask() {
    const q = goal.trim();
    if (!q || busy) return;
    setBusy(true); setError(""); setStreaming("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setGoal("");

    try {
      const resp = await fetch(`${API}/runs/stream`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ goal: q, dataset_id: selected || null, thread_id: threadId }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "", finalAnswer = "", finalRunId: string | undefined, finalChart: ChartSpec | undefined;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.token) { setStreaming((s) => s + ev.token); }
            else if (ev.done) {
              finalAnswer = ev.answer ?? "";
              finalRunId = ev.run_id;
              if (ev.chart_spec) { try { finalChart = JSON.parse(ev.chart_spec) as ChartSpec; } catch { /* */ } }
              if (ev.thread_id) setThreadId(ev.thread_id);
            } else if (ev.error) { throw new Error(ev.error); }
          } catch { /* */ }
        }
      }

      if (!finalAnswer) finalAnswer = streaming;
      setStreaming("");
      setMessages((m) => [...m, { role: "assistant", text: finalAnswer, runId: finalRunId, chartSpec: finalChart }]);
    } catch {
      // Fallback to non-streaming endpoint
      try {
        const r = await fetch(`${API}/runs`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ goal: q, dataset_id: selected || null, thread_id: threadId }),
        });
        const j = await r.json();
        if (j.ok) {
          const answer = j.data.answer ?? "(no answer)";
          let chartSpec: ChartSpec | undefined;
          if (j.data.chart_spec) { try { chartSpec = JSON.parse(j.data.chart_spec) as ChartSpec; } catch { /* */ } }
          if (j.data.thread_id) setThreadId(j.data.thread_id);
          setMessages((m) => [...m, { role: "assistant", text: answer, runId: j.data.run_id, chartSpec }]);
        } else {
          setError(j.error ?? "run failed");
          setMessages((m) => [...m, { role: "assistant", text: `Error: ${j.error}` }]);
        }
      } catch (e2) { setError(String(e2)); }
      setStreaming("");
    } finally {
      setBusy(false);
      await refreshSess();
      await loadSessions();
    }
  }

  const lastAI = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i;
    return -1;
  })();

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">

      {/* ── Header with always-visible session cost ────────────────────────── */}
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">DataChat</h1>
          <p className="text-sm text-slate-500">Upload datasets · query in plain English · get charts &amp; insights</p>
        </div>
        <div className="shrink-0 rounded-xl border border-slate-200 bg-white px-4 py-2 text-right text-sm shadow-sm">
          <div className="mb-0.5 text-xs text-slate-400">
            Session <span className="font-mono">{threadId.slice(0, 8)}…</span>
            {currentSess?.dataset_name && (
              <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                {currentSess.dataset_name}
              </span>
            )}
          </div>
          {currentSess ? (
            <div className="font-medium">
              <span className="text-slate-700">{fmtK(currentSess.total_input_tokens)}↑ {fmtK(currentSess.total_output_tokens)}↓</span>
              <span className="mx-1.5 text-slate-300">·</span>
              <span className="text-blue-600 font-semibold">{fmtCost(currentSess.total_cost_usd)}</span>
              <span className="mx-1.5 text-slate-300">·</span>
              <span className="text-slate-400">{currentSess.run_count} run{currentSess.run_count !== 1 ? "s" : ""}</span>
            </div>
          ) : (
            <div className="text-slate-400">0↑ 0↓ · $0</div>
          )}
        </div>
      </header>

      <div className="grid gap-5 md:grid-cols-[300px_1fr]">

        {/* ── Left panel ───────────────────────────────────────────────────── */}
        <aside className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="flex border-b border-slate-200">
            {(["datasets", "sessions"] as const).map((t) => (
              <button key={t} onClick={() => setLeftTab(t)}
                className={`flex-1 py-2.5 text-xs font-medium capitalize tracking-wide transition-colors ${
                  leftTab === t
                    ? "border-b-2 border-blue-600 text-blue-600"
                    : "text-slate-500 hover:text-slate-700"
                }`}>
                {t === "sessions"
                  ? `Sessions${sessions.length ? ` (${sessions.length})` : ""}`
                  : "Datasets"}
              </button>
            ))}
          </div>

          <div className="p-4">
            {leftTab === "datasets" ? (
              <>
                <label className="block text-xs text-slate-500 mb-1">Active dataset</label>
                <select aria-label="dataset"
                  className="mb-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
                  value={selected}
                  onChange={(e) => {
                    if (e.target.value !== selected) {
                      setSelected(e.target.value);
                      newSession(); // dataset change = new scoped conversation
                    }
                  }}>
                  {datasets.length === 0 && <option value="">— none yet —</option>}
                  {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>

                <div className="mb-3 flex gap-2">
                  <input aria-label="new dataset name" placeholder="New dataset name"
                    className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                    value={newName} onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") createDataset(); }} />
                  <button onClick={createDataset}
                    className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700">
                    +
                  </button>
                </div>

                <label className="block text-xs text-slate-500 mb-1">Upload CSV / JSON</label>
                <input ref={fileRef} type="file" aria-label="upload file"
                  accept=".csv,.json,.ndjson,.jsonl" disabled={!selected}
                  onChange={(e) => uploadFile(e.target.files?.[0])}
                  className="mb-3 w-full text-sm file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-sm disabled:opacity-40" />

                {tables.length > 0 && (
                  <>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Tables</h3>
                    <ul className="space-y-2 text-sm">
                      {tables.map((t) => (
                        <li key={t.table_name} className="rounded-md bg-slate-50 p-2">
                          <div className="font-medium">
                            {t.table_name}
                            <span className="ml-1 text-slate-400">({t.n_rows.toLocaleString()} rows)</span>
                          </div>
                          <div className="text-xs text-slate-500 mt-0.5">
                            {t.columns.slice(0, 5).map((c) => `${c.name}:${c.type}`).join(" · ")}
                            {t.columns.length > 5 && ` +${t.columns.length - 5}`}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </>
                )}

                <div className="mt-4 border-t border-slate-100 pt-3">
                  <p className="text-xs text-slate-400">
                    Thread <span className="font-mono">{threadId.slice(0, 8)}…</span>
                    <button onClick={newSession} className="ml-2 underline hover:text-slate-600">new</button>
                  </p>
                </div>
              </>
            ) : (
              /* Sessions tab */
              <>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Session history</span>
                  <button onClick={newSession}
                    className="rounded bg-blue-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-blue-500">
                    + New
                  </button>
                </div>
                {sessions.length === 0 ? (
                  <p className="text-sm text-slate-400">No sessions yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {sessions.map((sess) => (
                      <li key={sess.id} onClick={() => switchSession(sess)}
                        className={`cursor-pointer rounded-lg border p-2.5 text-sm transition-colors ${
                          sess.id === threadId
                            ? "border-blue-300 bg-blue-50"
                            : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}>
                        <div className="flex items-start justify-between gap-1">
                          <span className="truncate flex-1 text-xs font-medium text-slate-700">
                            {sess.title || "(untitled)"}
                          </span>
                          {sess.id === threadId && (
                            <span className="shrink-0 rounded bg-blue-600 px-1.5 text-xs text-white">active</span>
                          )}
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">
                          {sess.dataset_name || "—"} · {sess.run_count} run{sess.run_count !== 1 ? "s" : ""}
                        </div>
                        <div className="mt-0.5 flex items-center gap-2 text-xs">
                          <span className="text-slate-600">{fmtK(sess.total_input_tokens)}↑ {fmtK(sess.total_output_tokens)}↓</span>
                          <span className="text-blue-600">{fmtCost(sess.total_cost_usd)}</span>
                          <span className="text-slate-400">{timeAgo(sess.last_active_at)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </aside>

        {/* ── Right panel ──────────────────────────────────────────────────── */}
        <section className="flex min-h-[600px] flex-col rounded-xl border border-slate-200 bg-white overflow-hidden">

          {/* Right tabs */}
          <div className="flex border-b border-slate-200 shrink-0">
            {(["chat", "dashboard", "traces"] as const).map((t) => (
              <button key={t} onClick={() => setRightTab(t)}
                className={`px-5 py-2.5 text-xs font-medium tracking-wide capitalize transition-colors ${
                  rightTab === t
                    ? "border-b-2 border-blue-600 text-blue-600"
                    : "text-slate-500 hover:text-slate-700"
                }`}>
                {t === "traces" && traceRuns.length > 0
                  ? `Traces (${traceRuns.length})`
                  : t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          {/* ── Chat pane ─────────────────────────────────────────────────── */}
          {rightTab === "chat" && (
            <div className="flex flex-1 flex-col p-4">
              <div className="flex-1 overflow-y-auto space-y-3 pr-1 mb-3">
                {messages.length === 0 && !streaming && (
                  <p className="text-sm text-slate-400">
                    {datasets.length === 0
                      ? "Create a dataset and upload a CSV or JSON file to begin."
                      : !selected
                        ? "Select a dataset above, then ask a question."
                        : 'Ask a question about your data — e.g. "Which category has the highest total sales?"'}
                  </p>
                )}
                {messages.map((m, i) => (
                  <div key={i}>
                    <div
                      data-testid={m.role === "assistant" && i === lastAI ? "answer" : undefined}
                      className={
                        m.role === "user"
                          ? "ml-auto max-w-[80%] rounded-lg bg-slate-800 px-3 py-2 text-sm text-white"
                          : "mr-auto max-w-[95%] rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap"
                      }>
                      {m.text}
                      {m.role === "assistant" && m.runId && (
                        <button onClick={() => setRightTab("traces")}
                          className="mt-1 block text-xs text-blue-600 underline">
                          View trace ↗
                        </button>
                      )}
                    </div>
                    {m.chartSpec && (
                      <div className="mr-auto mt-2 max-w-[95%] rounded-lg border border-slate-200 bg-white p-2">
                        <Plot
                          data={m.chartSpec.data as Plotly.Data[]}
                          layout={{ ...m.chartSpec.layout, autosize: true } as Partial<Plotly.Layout>}
                          style={{ width: "100%", height: 320 }}
                          config={{ responsive: true, displayModeBar: false }}
                        />
                      </div>
                    )}
                  </div>
                ))}
                {streaming && (
                  <div className="mr-auto max-w-[95%] rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap">
                    {streaming}
                    <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-slate-500" />
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {error && (
                <div className="mb-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
              )}

              <div className="flex items-end gap-2 border-t border-slate-100 pt-3 shrink-0">
                <textarea aria-label="goal" rows={2}
                  placeholder={
                    datasets.length === 0 ? "Upload a dataset first…"
                    : !selected ? "Select a dataset…"
                    : "Ask a question about your data…"
                  }
                  disabled={datasets.length === 0 || !selected}
                  className="flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
                  value={goal} onChange={(e) => setGoal(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }} />
                <button onClick={ask} disabled={busy || datasets.length === 0 || !selected}
                  className="h-10 rounded-md bg-blue-600 px-5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50">
                  {busy ? "…" : "Run"}
                </button>
              </div>
            </div>
          )}

          {/* ── Dashboard pane ────────────────────────────────────────────── */}
          {rightTab === "dashboard" && (
            <div className="flex-1 overflow-y-auto p-4">
              {!selected ? (
                <p className="text-sm text-slate-400">Select a dataset to see its overview.</p>
              ) : dashBusy ? (
                <p className="text-sm text-slate-400">Loading overview…</p>
              ) : !dash || Object.keys(dash.col_stats).length === 0 ? (
                <p className="text-sm text-slate-400">
                  {dash
                    ? "No tables yet — upload a file to see column statistics."
                    : "Upload a file to see the dataset overview."}
                </p>
              ) : (
                <>
                  <h2 className="mb-1 text-base font-semibold">{dash.name}</h2>
                  <p className="mb-4 text-xs text-slate-500">
                    {dash.tables.reduce((s, t) => s + t.n_rows, 0).toLocaleString()} total rows ·{" "}
                    {dash.tables.length} table{dash.tables.length !== 1 ? "s" : ""}
                  </p>
                  {Object.entries(dash.col_stats).map(([tname, cols]) => (
                    <div key={tname} className="mb-8">
                      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500 border-b border-slate-100 pb-1">
                        {tname}
                      </h3>
                      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {Object.entries(cols).map(([col, stat]) => (
                          <div key={col} className="rounded-lg border border-slate-200 p-3">
                            <div className="mb-2 flex items-center gap-2">
                              <span className="text-xs font-semibold text-slate-700">{col}</span>
                              <span className={`rounded px-1.5 py-0.5 text-xs ${
                                stat.type === "numeric"
                                  ? "bg-purple-100 text-purple-700"
                                  : "bg-amber-100 text-amber-700"
                              }`}>{stat.type}</span>
                            </div>
                            {stat.type === "numeric" ? (
                              <div className="grid grid-cols-3 gap-1 text-center">
                                {([["min", stat.min], ["avg", stat.avg], ["max", stat.max]] as [string, number | null][]).map(
                                  ([label, val]) => (
                                    <div key={label} className="rounded bg-slate-50 py-1.5">
                                      <div className="text-xs text-slate-400">{label}</div>
                                      <div className="text-sm font-semibold text-slate-700">
                                        {val != null ? Number(val).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
                                      </div>
                                    </div>
                                  )
                                )}
                              </div>
                            ) : (
                              <Plot
                                data={[{
                                  type: "bar" as const,
                                  x: stat.top_values.map(([v]) => String(v ?? "(null)")),
                                  y: stat.top_values.map(([, c]) => c),
                                  marker: { color: "#2563eb" },
                                }]}
                                layout={{
                                  height: 160,
                                  margin: { t: 5, b: 55, l: 35, r: 5 },
                                  yaxis: { title: { text: "count", standoff: 5 } },
                                  xaxis: { tickangle: -35 },
                                }}
                                config={{ displayModeBar: false, responsive: true }}
                                style={{ width: "100%" }}
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {/* ── Traces pane ───────────────────────────────────────────────── */}
          {rightTab === "traces" && (
            <div className="flex-1 overflow-y-auto p-4">
              {traceRuns.length === 0 ? (
                <p className="text-sm text-slate-400">
                  No runs in this session yet. Ask a question to see traces.
                </p>
              ) : (
                <ul className="space-y-3">
                  {traceRuns.map((run) => (
                    <li key={run.id} className="rounded-lg border border-slate-200 overflow-hidden">
                      <button className="w-full text-left px-4 py-3 hover:bg-slate-50 transition-colors"
                        onClick={async () => {
                          const next = expandedRun === run.id ? null : run.id;
                          setExpandedRun(next);
                          if (next) await loadSpans(next);
                        }}>
                        <div className="flex items-start justify-between gap-3">
                          <span className="flex-1 truncate text-sm font-medium text-slate-700">{run.goal}</span>
                          <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
                            run.status === "completed" ? "bg-green-100 text-green-700"
                            : run.status === "error"   ? "bg-red-100 text-red-700"
                            : "bg-amber-100 text-amber-700"
                          }`}>{run.status}</span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                          <span>{run.iterations} iter</span>
                          <span className="text-slate-600">{fmtK(run.input_tokens)}↑ {fmtK(run.output_tokens)}↓</span>
                          <span className="text-blue-600 font-medium">{fmtCost(run.cost_usd)}</span>
                          <span>{timeAgo(run.created_at)}</span>
                        </div>
                        {run.answer && (
                          <div className="mt-1 truncate text-xs text-slate-500 italic">{run.answer}</div>
                        )}
                      </button>

                      {expandedRun === run.id && (
                        <div className="border-t border-slate-100 bg-slate-50 px-4 pb-3 pt-2 space-y-1.5">
                          {!runSpans[run.id] ? (
                            <p className="text-xs text-slate-400">Loading spans…</p>
                          ) : runSpans[run.id].length === 0 ? (
                            <p className="text-xs text-slate-400">No spans recorded.</p>
                          ) : (
                            runSpans[run.id].map((sp) => {
                              const tok = ((sp.attributes.tokens ?? {}) as Record<string, number>);
                              return (
                                <div key={sp.id} className="flex flex-wrap items-center gap-2 py-0.5 text-xs">
                                  <span className={`rounded px-1.5 py-0.5 font-medium ${KIND_CLS[sp.kind] ?? "bg-slate-100 text-slate-600"}`}>
                                    {sp.kind}
                                  </span>
                                  <span className="flex-1 truncate font-mono text-slate-600">{sp.name}</span>
                                  <span className="shrink-0 text-slate-400">{sp.duration_ms}ms</span>
                                  {tok.input_tokens != null && (
                                    <span className="shrink-0 text-slate-500">
                                      {fmtK(tok.input_tokens)}↑ {fmtK(tok.output_tokens ?? 0)}↓
                                    </span>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
