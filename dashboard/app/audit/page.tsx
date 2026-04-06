"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { getHttpApiBase } from "@/lib/api-base";
import { filterOfflineAudit, isOfflineDemoActive, readOfflineDemoPayload } from "@/lib/offline-demo";
import { toast } from "@/components/toast-host";

type AuditEntry = {
  action_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  agent_id: string;
  decision: string;
  risk_score: number;
  mode: string;
  timestamp: string;
};

type AgentAuditSummary = {
  agent_id: string;
  display_name: string;
  total_actions: number;
  blocked_actions: number;
  last_active: string | null;
};

const API_BASE = getHttpApiBase();
const PAGE_SIZE = 20;

function buildFilterParams(toolName: string, decision: string, minRisk: string, agentId: string) {
  const params = new URLSearchParams();
  if (toolName) params.set("tool_name", toolName);
  if (decision) params.set("decision", decision);
  if (minRisk) params.set("min_risk", minRisk);
  if (agentId) params.set("agent_id", agentId);
  return params;
}

function buildExportQuery(exportStart: string, exportEnd: string) {
  const params = new URLSearchParams();
  if (exportStart) {
    params.set("start", new Date(`${exportStart}T00:00:00.000Z`).toISOString());
  }
  if (exportEnd) {
    params.set("end", new Date(`${exportEnd}T23:59:59.999Z`).toISOString());
  }
  return params.toString();
}

function riskBadgeClass(score: number) {
  if (score > 0.7) return "bg-red-500/20 text-red-200 ring-red-500/40";
  if (score >= 0.4) return "bg-amber-500/20 text-amber-200 ring-amber-500/40";
  return "bg-emerald-500/20 text-emerald-200 ring-emerald-500/40";
}

function riskDot(score: number) {
  if (score > 0.7) return "bg-red-400";
  if (score >= 0.4) return "bg-amber-400";
  return "bg-emerald-400";
}

function decisionPill(decision: string) {
  const d = (decision || "").toLowerCase();
  if (d === "block") return "bg-red-500/15 text-red-100 ring-red-500/40";
  if (d === "allow" || d === "approve") return "bg-emerald-500/15 text-emerald-100 ring-emerald-500/35";
  if (d === "shadow") return "bg-amber-500/15 text-amber-100 ring-amber-500/40";
  return "bg-slate-500/15 text-slate-200 ring-slate-500/35";
}

function decisionLabel(decision: string) {
  return (decision || "unknown").toUpperCase();
}

function actionPath(args: Record<string, unknown>): string {
  const p = args?.path ?? args?.file ?? args?.filepath;
  return typeof p === "string" && p.trim() ? p.trim() : "—";
}

function AuditLogContent() {
  const searchParams = useSearchParams();
  const agentFromUrl = searchParams.get("agent") ?? "";

  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [toolName, setToolName] = useState("");
  const [decision, setDecision] = useState("");
  const [minRisk, setMinRisk] = useState("");
  const [agentFilter, setAgentFilter] = useState(agentFromUrl);
  const [agentOptions, setAgentOptions] = useState<AgentAuditSummary[]>([]);
  const [page, setPage] = useState(0);
  const [exportStart, setExportStart] = useState("");
  const [exportEnd, setExportEnd] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => {
    setAgentFilter(agentFromUrl);
    setPage(0);
  }, [agentFromUrl]);

  useEffect(() => {
    void (async () => {
      const offline = readOfflineDemoPayload();
      if (offline) {
        setAgentOptions(offline.summaries);
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/v1/audit/agents/summary`);
        if (res.ok) {
          const j = (await res.json()) as AgentAuditSummary[];
          setAgentOptions(Array.isArray(j) ? j : []);
        }
      } catch {
        setAgentOptions([]);
      }
    })();
  }, []);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    try {
      if (typeof window !== "undefined" && isOfflineDemoActive()) {
        const payload = readOfflineDemoPayload();
        if (payload) {
          const sorted = [...payload.audit].sort(
            (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
          );
          const filtered = filterOfflineAudit(sorted, toolName, decision, minRisk, agentFilter);
          setTotal(filtered.length);
          const slice = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
          setRows(slice as AuditEntry[]);
          return;
        }
      }
      const fp = buildFilterParams(toolName, decision, minRisk, agentFilter);
      const q = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      });
      fp.forEach((v, k) => q.set(k, v));
      const [dataRes, countRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/audit?${q.toString()}`),
        fetch(`${API_BASE}/api/v1/audit/count?${fp.toString()}`),
      ]);
      const json = (await dataRes.json()) as AuditEntry[];
      setRows(Array.isArray(json) ? json : []);
      if (countRes.ok) {
        const c = (await countRes.json()) as { total: number };
        setTotal(typeof c.total === "number" ? c.total : null);
      } else {
        setTotal(null);
      }
    } finally {
      setLoading(false);
    }
  }, [agentFilter, decision, minRisk, page, toolName]);

  useEffect(() => {
    void loadAudit();
  }, [loadAudit]);

  async function onApplyFilters() {
    setPage(0);
    await loadAudit();
  }

  async function downloadEvidenceJson(kind: "soc2" | "hipaa" | "pci", filename: string) {
    const key = `${kind}-json`;
    setExporting(key);
    const q = buildExportQuery(exportStart, exportEnd);
    const path = `${API_BASE}/api/v1/compliance/${kind}/evidence.json${q ? `?${q}` : ""}`;
    try {
      const res = await fetch(path);
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast("Report generated", "success");
    } catch {
      toast("JSON export failed", "error");
    } finally {
      setExporting(null);
    }
  }

  async function downloadPdf(kind: "soc2" | "hipaa" | "pci", filename: string) {
    const key = `${kind}-pdf`;
    setExporting(key);
    const q = buildExportQuery(exportStart, exportEnd);
    const path = `${API_BASE}/api/v1/compliance/${kind}/report${q ? `?${q}` : ""}`;
    try {
      const res = await fetch(path);
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      if (blob.type.includes("json") || blob.size < 100) {
        const t = await blob.text();
        throw new Error(t.slice(0, 200));
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast("Report generated", "success");
    } catch {
      toast("Generating report… falling back to JSON export", "info");
      try {
        const fb = buildExportQuery(exportStart, exportEnd);
        let url = `${API_BASE}/api/v1/compliance/soc2?`;
        if (fb) {
          url += fb;
        } else {
          const end = new Date();
          const start = new Date();
          start.setDate(start.getDate() - 30);
          url += `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`;
        }
        const fallback = await fetch(url);
        if (fallback.ok) {
          const data = await fallback.json();
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `agentiva-compliance-fallback.json`;
          a.click();
          URL.revokeObjectURL(url);
          toast("JSON report downloaded", "success");
        } else {
          toast("Export failed", "error");
        }
      } catch {
        toast("Export failed", "error");
      }
    } finally {
      setExporting(null);
    }
  }

  const startIdx = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const endIdx = page * PAGE_SIZE + rows.length;

  return (
    <div className="page-enter space-y-6 pb-12">
      <PageHeader title="Audit log" subtitle="Searchable history & exportable audit data" breadcrumbs={[{ label: "Audit Log" }]} />

      <section className="glass-card p-5">
        <h3 className="mb-1 text-sm font-semibold text-[#f0f6fc]">Audit log exports</h3>
        <p className="mb-4 text-xs text-[#8b949e]">
          PDF and JSON from persisted <code className="text-[#fde047]">action_logs</code> (framework-themed summaries). Optional date range. Your assessor makes compliance determinations—we supply the trail.
        </p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[#8b949e]">
            Start
            <input
              type="date"
              value={exportStart}
              onChange={(e) => setExportStart(e.target.value)}
              className="rounded-lg border border-[#2e2918] bg-[#060504] px-2 py-1.5 text-sm text-[#f0f6fc]"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[#8b949e]">
            End
            <input
              type="date"
              value={exportEnd}
              onChange={(e) => setExportEnd(e.target.value)}
              className="rounded-lg border border-[#2e2918] bg-[#060504] px-2 py-1.5 text-sm text-[#f0f6fc]"
            />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["soc2", "SOC 2", "agentiva-soc2-report.pdf"],
              ["hipaa", "HIPAA", "agentiva-hipaa-report.pdf"],
              ["pci", "PCI-DSS", "agentiva-pci-report.pdf"],
            ] as const
          ).map(([k, label, file]) => (
            <button
              key={k}
              type="button"
              disabled={!!exporting}
              onClick={() => void downloadPdf(k, file)}
              className="inline-flex items-center gap-2 rounded-xl border border-[#3a3420] bg-[#14110a] px-4 py-2 text-sm font-medium text-[#f0f6fc] transition hover:shadow-lg hover:shadow-amber-950/30 hover:border-[#eab308]/50 disabled:opacity-50"
            >
              {exporting === `${k}-pdf` ? (
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[#8b949e] border-t-transparent" />
              ) : null}
              Export {label} (PDF)
            </button>
          ))}
        </div>
        <p className="mb-2 mt-4 text-xs font-medium text-[#8b949e]">Structured JSON (SOC2 / HIPAA / PCI report styles)</p>
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["soc2", "SOC2", "agentiva-soc2-evidence.json"],
              ["hipaa", "HIPAA", "agentiva-hipaa-evidence.json"],
              ["pci", "PCI-DSS", "agentiva-pci-evidence.json"],
            ] as const
          ).map(([k, label, file]) => (
            <button
              key={`j-${k}`}
              type="button"
              disabled={!!exporting}
              onClick={() => void downloadEvidenceJson(k, file)}
              className="inline-flex items-center gap-2 rounded-xl border border-[#3a3420] bg-[#060504] px-4 py-2 text-sm font-medium text-[#c9d1d9] transition hover:border-[#eab308]/45 disabled:opacity-50"
            >
              {exporting === `${k}-json` ? (
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[#8b949e] border-t-transparent" />
              ) : null}
              Export {label} evidence
            </button>
          ))}
        </div>
      </section>

      <section className="glass-card grid grid-cols-1 gap-3 p-4 md:grid-cols-6">
        <label className="flex flex-col gap-1 text-xs text-[#8b949e] md:col-span-2">
          Filter by agent
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-sm text-[#f0f6fc] outline-none"
          >
            <option value="">All agents</option>
            {agentOptions.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.display_name !== a.agent_id ? `${a.display_name} (${a.agent_id})` : a.agent_id}
              </option>
            ))}
          </select>
        </label>
        <input
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          placeholder="Tool name"
          className="rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-sm outline-none ring-0 focus:border-[#eab308] md:col-span-1"
        />
        <select
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          className="rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-sm outline-none"
        >
          <option value="">All decisions</option>
          <option value="allow">allow</option>
          <option value="shadow">shadow</option>
          <option value="block">block</option>
          <option value="approve">approve</option>
          <option value="pending">pending</option>
        </select>
        <input
          value={minRisk}
          onChange={(e) => setMinRisk(e.target.value)}
          placeholder="Min risk (0-1)"
          className="rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-sm outline-none"
        />
        <button
          type="button"
          onClick={() => void onApplyFilters()}
          className="rounded-lg bg-[#ca8a04] px-3 py-2 text-sm font-medium text-[#0a0805] shadow-lg shadow-amber-950/30 transition hover:bg-[#eab308]"
        >
          Apply filters
        </button>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-[#8b949e]">
        <span>
          {total !== null
            ? `Showing ${startIdx}-${endIdx} of ${total} actions`
            : loading
              ? "Loading…"
              : `Showing ${rows.length} actions`}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-lg border border-[#2e2918] px-3 py-1.5 text-sm transition hover:bg-[#14110a] disabled:opacity-40"
            disabled={page === 0}
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-[#2e2918] px-3 py-1.5 text-sm transition hover:bg-[#14110a] disabled:opacity-40"
            disabled={rows.length < PAGE_SIZE || (total !== null && endIdx >= total)}
          >
            Next
          </button>
        </div>
      </div>

      <section className="glass-card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-[#060504] text-left text-xs font-semibold uppercase tracking-wide text-[#8a8270]">
            <tr>
              <th className="whitespace-nowrap px-4 py-3">Agent</th>
              <th className="px-4 py-3">Tool</th>
              <th className="whitespace-nowrap px-4 py-3">Decision</th>
              <th className="whitespace-nowrap px-4 py-3">Risk</th>
              <th className="min-w-[12rem] px-4 py-3">File / path</th>
              <th className="whitespace-nowrap px-4 py-3">Time</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-[#8b949e]">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-[#facc15]" />
                    Loading audit log…
                  </span>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td className="px-4 py-3 text-[#8b949e]" colSpan={6}>
                  No rows found.
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr
                  key={row.action_id}
                  className={`border-t border-[#2e2918] transition hover:bg-[#15130c] ${i % 2 === 1 ? "bg-[#060504]/80" : ""}`}
                >
                  <td className="max-w-[14rem] px-4 py-3">
                    <span className="font-mono text-xs font-semibold text-[#fde047]" title={row.agent_id}>
                      {row.agent_id}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium text-[#f0f6fc]">{row.tool_name}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-bold tracking-wide ring-1 ${decisionPill(row.decision)}`}
                    >
                      {decisionLabel(row.decision)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-xs ring-1 ${riskBadgeClass(row.risk_score)}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${riskDot(row.risk_score)}`} />
                      {row.risk_score.toFixed(2)}
                    </span>
                  </td>
                  <td className="max-w-xs break-all px-4 py-3 font-mono text-xs text-[#c9d1d9]">
                    {actionPath(row.arguments)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[#8b949e]">{new Date(row.timestamp).toLocaleString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default function AuditPage() {
  return (
    <Suspense
      fallback={
        <div className="page-enter space-y-6 pb-12">
          <PageHeader title="Audit log" subtitle="Loading…" breadcrumbs={[{ label: "Audit Log" }]} />
          <div className="glass-card p-8 text-center text-sm text-[#8b949e]">Loading audit log…</div>
        </div>
      }
    >
      <AuditLogContent />
    </Suspense>
  );
}
