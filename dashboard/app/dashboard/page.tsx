"use client";

import { useEffect, useMemo, useState } from "react";

type AuditEntry = {
  action_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  agent_id: string;
  decision: string;
  risk_score: number;
  mode: string;
  mandatory?: boolean;
  timestamp: string;
};

type ShadowReport = {
  total_actions: number;
  by_tool: Record<string, number>;
  by_decision: Record<string, number>;
  avg_risk_score: number;
};

const API_BASE = "http://localhost:8000";

export default function DashboardOverviewPage() {
  const [report, setReport] = useState<ShadowReport | null>(null);
  const [recentActions, setRecentActions] = useState<AuditEntry[]>([]);
  const [mode, setMode] = useState("shadow");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      const [reportRes, auditRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/report`),
        fetch(`${API_BASE}/api/v1/audit?limit=10`),
        fetch(`${API_BASE}/health`),
      ]);

      if (!reportRes.ok || !auditRes.ok || !healthRes.ok) {
        throw new Error("Failed to load dashboard data");
      }

      const reportJson = (await reportRes.json()) as ShadowReport;
      const auditJson = (await auditRes.json()) as AuditEntry[];
      const healthJson = (await healthRes.json()) as { mode: string };

      setReport(reportJson);
      setRecentActions(auditJson);
      setMode(healthJson.mode);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const nextMode = useMemo(() => {
    if (mode === "shadow") return "live";
    if (mode === "live") return "approval";
    return "shadow";
  }, [mode]);

  async function toggleMode() {
    const response = await fetch(`${API_BASE}/api/v1/mode/${nextMode}`, { method: "POST" });
    if (response.ok) {
      setMode(nextMode);
    }
  }

  const decisions = report?.by_decision ?? {};
  const blockRate = report?.total_actions
    ? (decisions.block ?? 0) / report.total_actions
    : 0;
  const showTuningBanner = !loading && report && blockRate > 0.4;

  return (
    <div className="space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm text-[#8b949e]">Preview deployments for AI agents</p>
          <h2 className="text-3xl font-semibold text-[#f0f6fc]">Overview</h2>
        </div>
        <button
          onClick={toggleMode}
          className="rounded-md border border-[#30363d] bg-[#161b22] px-4 py-2 text-sm text-[#c9d1d9] hover:bg-[#1f2630]"
        >
          Mode: {mode} (Switch to {nextMode})
        </button>
      </header>

      {error && <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-300">{error}</div>}

      {showTuningBanner && (
        <button
          type="button"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("agentshield:openChat", {
                detail: { message: "help me tune policies" },
              }),
            )
          }
          className="w-full rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-left text-amber-200 hover:bg-amber-500/15"
        >
          <div className="text-sm font-semibold">High block rate detected. Click here for policy tuning help.</div>
          <div className="mt-1 text-xs text-amber-200/80">
            Block rate: {Math.round(blockRate * 100)}%
          </div>
        </button>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-[#30363d] bg-[#161b22] p-4">
          <p className="text-sm text-[#8b949e]">Total Intercepted</p>
          <p className="mt-2 text-3xl font-semibold text-[#f0f6fc]">{report?.total_actions ?? 0}</p>
        </div>
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
          <p className="text-sm text-amber-300">Shadow</p>
          <p className="mt-2 text-3xl font-semibold text-amber-200">{decisions.shadow ?? 0}</p>
        </div>
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4">
          <p className="text-sm text-red-300">Block</p>
          <p className="mt-2 text-3xl font-semibold text-red-200">{decisions.block ?? 0}</p>
        </div>
        <div className="rounded-xl border border-green-500/40 bg-green-500/10 p-4">
          <p className="text-sm text-green-300">Allow</p>
          <p className="mt-2 text-3xl font-semibold text-green-200">{decisions.allow ?? 0}</p>
        </div>
      </section>

      <section className="rounded-xl border border-[#30363d] bg-[#161b22] p-4">
        <h3 className="mb-4 text-lg font-medium text-[#f0f6fc]">Recent Actions</h3>
        {loading ? (
          <p className="text-[#8b949e]">Loading...</p>
        ) : recentActions.length === 0 ? (
          <p className="text-[#8b949e]">No actions yet.</p>
        ) : (
          <ul className="space-y-2">
            {recentActions.map((action) => (
              <li key={action.action_id} className="rounded-lg border border-[#30363d] bg-[#0d1117] p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[#f0f6fc]">{action.tool_name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase text-[#8b949e]">{action.decision}</span>
                    {action.mandatory ? (
                      <span className="rounded bg-[#e1a400]/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#f2cc60] ring-1 ring-[#e1a400]/30">
                        MANDATORY
                      </span>
                    ) : null}
                  </div>
                </div>
                <p className="mt-1 text-xs text-[#8b949e]">{new Date(action.timestamp).toLocaleString()}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
