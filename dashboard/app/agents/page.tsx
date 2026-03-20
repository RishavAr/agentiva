"use client";

import { useCallback, useEffect, useState } from "react";

type Agent = {
  id: string;
  name: string;
  owner: string;
  reputation_score: number;
  total_actions: number;
  blocked_actions: number;
  status: string;
  max_risk_tolerance: number;
  allowed_tools: string[];
};

const API_BASE = "http://localhost:8000";

const TOOL_OPTIONS = [
  "send_email",
  "send_slack_message",
  "create_jira_ticket",
  "jira_operation",
  "update_database",
  "call_external_api",
  "read_customer_data",
  "delete_resource",
  "transfer_funds",
  "run_shell_command",
  "git_operation",
  "deploy_application",
  "modify_environment_file",
  "ssh_session",
  "npm_install",
  "read_logs",
  "admin_permission",
] as const;

function reputationBarColor(score: number): string {
  if (score >= 0.7) return "bg-emerald-500";
  if (score >= 0.4) return "bg-amber-400";
  return "bg-red-500";
}

function ReputationBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score * 100));
  const bar = reputationBarColor(score);
  return (
    <div className="flex min-w-[140px] max-w-[200px] items-center gap-2">
      <div className="h-2.5 min-w-[80px] flex-1 overflow-hidden rounded-full bg-[#21262d]">
        <div className={`h-full rounded-full transition-all ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="shrink-0 font-mono text-xs tabular-nums text-[#c9d1d9]">{score.toFixed(2)}</span>
    </div>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formName, setFormName] = useState("");
  const [formOwner, setFormOwner] = useState("");
  const [formTools, setFormTools] = useState<string[]>([]);
  const [formMaxRisk, setFormMaxRisk] = useState(0.8);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/agents`);
      if (response.ok) {
        setAgents((await response.json()) as Agent[]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadAgents();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadAgents]);

  function toggleTool(tool: string) {
    setFormTools((prev) => (prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]));
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!formName.trim() || !formOwner.trim()) return;
    setSubmitting(true);
    try {
      const agent_id = `agent-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
      const res = await fetch(`${API_BASE}/api/v1/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id,
          name: formName.trim(),
          owner: formOwner.trim(),
          allowed_tools: formTools.length ? formTools : ["send_email"],
          max_risk_tolerance: formMaxRisk,
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || res.statusText);
      }
      setRegisterOpen(false);
      setFormName("");
      setFormOwner("");
      setFormTools([]);
      setFormMaxRisk(0.8);
      await loadAgents();
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "Failed to register agent");
    } finally {
      setSubmitting(false);
    }
  }

  async function killSwitch(agentId: string) {
    if (!confirm("Deactivate this agent? It will no longer be allowed to act.")) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/agents/${encodeURIComponent(agentId)}/deactivate`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await res.text());
      await loadAgents();
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "Failed to deactivate");
    }
  }

  return (
    <div className="w-full min-w-0 max-w-full space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-[#8b949e]">Agent registry and reputation</p>
          <h2 className="text-3xl font-semibold text-[#f0f6fc]">Agents</h2>
        </div>
        <button
          type="button"
          onClick={() => setRegisterOpen(true)}
          className="shrink-0 rounded-lg bg-[#238636] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#2ea043]"
        >
          Register Agent
        </button>
      </header>

      {/* Horizontally scrollable on small viewports; full width on large */}
      <div className="w-full min-w-0 overflow-x-auto rounded-xl border border-[#30363d] bg-[#161b22] shadow-inner">
        <table className="w-full min-w-[960px] table-fixed border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#0d1117] text-xs font-semibold uppercase tracking-wide text-[#8b949e]">
            <tr>
              <th className="w-[120px] px-3 py-3 sm:px-4">Agent ID</th>
              <th className="w-[140px] px-3 py-3 sm:px-4">Name</th>
              <th className="w-[160px] px-3 py-3 sm:px-4">Owner</th>
              <th className="w-[220px] px-3 py-3 sm:px-4">Reputation</th>
              <th className="w-[100px] px-3 py-3 sm:px-4">Total actions</th>
              <th className="w-[110px] px-3 py-3 sm:px-4">Blocked</th>
              <th className="w-[100px] px-3 py-3 sm:px-4">Status</th>
              <th className="w-[130px] px-3 py-3 pr-4 sm:px-4">Kill switch</th>
            </tr>
          </thead>
          <tbody className="text-[#e6edf3]">
            {loading ? (
              <tr>
                <td className="px-4 py-8 text-[#8b949e]" colSpan={8}>
                  Loading agents…
                </td>
              </tr>
            ) : agents.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-[#8b949e]" colSpan={8}>
                  No agents registered. Use &quot;Register Agent&quot; to add one.
                </td>
              </tr>
            ) : (
              agents.map((agent) => (
                <tr key={agent.id} className="border-t border-[#30363d] hover:bg-[#1c2128]">
                  <td className="px-3 py-3 font-mono text-xs text-[#79c0ff] sm:px-4">{agent.id}</td>
                  <td className="max-w-[140px] truncate px-3 py-3 font-medium text-[#f0f6fc] sm:px-4" title={agent.name}>
                    {agent.name}
                  </td>
                  <td className="max-w-[160px] truncate px-3 py-3 text-[#c9d1d9] sm:px-4" title={agent.owner}>
                    {agent.owner}
                  </td>
                  <td className="px-3 py-3 sm:px-4">
                    <ReputationBar score={Number(agent.reputation_score)} />
                  </td>
                  <td className="px-3 py-3 font-mono tabular-nums sm:px-4">{agent.total_actions}</td>
                  <td className="px-3 py-3 font-mono tabular-nums sm:px-4">{agent.blocked_actions}</td>
                  <td className="px-3 py-3 sm:px-4">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        agent.status === "active"
                          ? "bg-emerald-500/15 text-emerald-300"
                          : agent.status === "suspended"
                            ? "bg-amber-500/15 text-amber-300"
                            : "bg-red-500/15 text-red-300"
                      }`}
                    >
                      {agent.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 pr-4 sm:px-4">
                    <button
                      type="button"
                      onClick={() => killSwitch(agent.id)}
                      disabled={agent.status === "deactivated"}
                      className="whitespace-nowrap rounded-md bg-red-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Kill Switch
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {registerOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="register-agent-title"
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-[#30363d] bg-[#161b22] p-6 shadow-xl">
            <h3 id="register-agent-title" className="text-lg font-semibold text-[#f0f6fc]">
              Register new agent
            </h3>
            <p className="mt-1 text-sm text-[#8b949e]">Creates an entry in the AgentShield registry.</p>
            <form onSubmit={handleRegister} className="mt-6 space-y-5">
              <div>
                <label htmlFor="agent-name" className="block text-sm font-medium text-[#c9d1d9]">
                  Name
                </label>
                <input
                  id="agent-name"
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="mt-1 w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-[#f0f6fc] placeholder:text-[#484f58] focus:border-[#58a6ff] focus:outline-none focus:ring-1 focus:ring-[#58a6ff]"
                  placeholder="e.g. Sales outreach bot"
                />
              </div>
              <div>
                <label htmlFor="agent-owner" className="block text-sm font-medium text-[#c9d1d9]">
                  Owner email
                </label>
                <input
                  id="agent-owner"
                  type="email"
                  required
                  value={formOwner}
                  onChange={(e) => setFormOwner(e.target.value)}
                  className="mt-1 w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-[#f0f6fc] placeholder:text-[#484f58] focus:border-[#58a6ff] focus:outline-none focus:ring-1 focus:ring-[#58a6ff]"
                  placeholder="owner@company.com"
                />
              </div>
              <div>
                <span className="block text-sm font-medium text-[#c9d1d9]">Allowed tools</span>
                <p className="text-xs text-[#8b949e]">Select one or more tools this agent may invoke.</p>
                <div className="mt-2 max-h-48 space-y-2 overflow-y-auto rounded-md border border-[#30363d] bg-[#0d1117] p-3">
                  {TOOL_OPTIONS.map((tool) => (
                    <label key={tool} className="flex cursor-pointer items-center gap-2 text-sm text-[#c9d1d9]">
                      <input
                        type="checkbox"
                        checked={formTools.includes(tool)}
                        onChange={() => toggleTool(tool)}
                        className="rounded border-[#30363d] bg-[#0d1117] text-[#238636] focus:ring-[#238636]"
                      />
                      <span className="font-mono text-xs">{tool}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <label htmlFor="max-risk" className="text-sm font-medium text-[#c9d1d9]">
                    Max risk tolerance
                  </label>
                  <span className="font-mono text-sm tabular-nums text-[#79c0ff]">{formMaxRisk.toFixed(2)}</span>
                </div>
                <input
                  id="max-risk"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={formMaxRisk}
                  onChange={(e) => setFormMaxRisk(Number(e.target.value))}
                  className="mt-2 h-2 w-full cursor-pointer accent-[#58a6ff]"
                />
                <div className="mt-1 flex justify-between text-xs text-[#8b949e]">
                  <span>0</span>
                  <span>1</span>
                </div>
              </div>
              <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => setRegisterOpen(false)}
                  className="rounded-md border border-[#30363d] px-4 py-2 text-sm font-medium text-[#c9d1d9] hover:bg-[#21262d]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-md bg-[#238636] px-4 py-2 text-sm font-semibold text-white hover:bg-[#2ea043] disabled:opacity-50"
                >
                  {submitting ? "Registering…" : "Register"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
