"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { getHttpApiBase } from "@/lib/api-base";
import { isOfflineDemoActive, readOfflineDemoPayload } from "@/lib/offline-demo";
import { toast } from "@/components/toast-host";
import { Check, Copy, Pencil, Trash2, X } from "lucide-react";

type Agent = {
  id: string;
  name: string;
  owner: string;
  reputation_score: number;
  total_actions: number;
  blocked_actions: number;
  status: string;
  last_active?: string | null;
  allowed_tools?: string[];
};
type AuditEntry = {
  action_id: string;
  tool_name: string;
  agent_id: string;
  decision: string;
  risk_score: number;
  timestamp: string;
};

const API_BASE = getHttpApiBase();

const TOOL_OPTIONS = [
  "send_email",
  "send_slack_message",
  "create_jira_ticket",
  "update_database",
  "call_external_api",
  "read_customer_data",
  "transfer_funds",
  "run_shell_command",
] as const;

const FRAMEWORK_OPTIONS = [
  { label: "LangChain", value: "langchain" },
  { label: "CrewAI", value: "crewai" },
  { label: "OpenAI Agents", value: "openai" },
  { label: "MCP", value: "mcp" },
  { label: "Custom", value: "custom" },
] as const;

function repColor(score: number) {
  if (score >= 0.7) return "from-emerald-500 to-teal-400";
  if (score >= 0.4) return "from-amber-500 to-yellow-400";
  return "from-red-500 to-orange-400";
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerPhase, setRegisterPhase] = useState<"form" | "success">("form");
  const [submitting, setSubmitting] = useState(false);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formFramework, setFormFramework] = useState<string>("custom");
  const [formTools, setFormTools] = useState<string[]>([]);
  const [formMaxRisk, setFormMaxRisk] = useState(0.8);
  const [nameErr, setNameErr] = useState("");
  const [successApiKey, setSuccessApiKey] = useState("");
  const [successAgentName, setSuccessAgentName] = useState("");
  const [copiedKey, setCopiedKey] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [agentAudit, setAgentAudit] = useState<Record<string, AuditEntry[]>>({});
  const [editAgent, setEditAgent] = useState<Agent | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTools, setEditTools] = useState<string[]>([]);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    try {
      if (typeof window !== "undefined" && isOfflineDemoActive()) {
        const payload = readOfflineDemoPayload();
        if (payload) {
          setAgents(
            payload.agents.map((a) => ({
              id: a.id,
              name: a.name,
              owner: a.owner,
              reputation_score: a.reputation_score,
              total_actions: a.total_actions,
              blocked_actions: a.blocked_actions,
              status: a.status,
              last_active: a.last_active ?? null,
              allowed_tools: a.allowed_tools,
            })),
          );
          return;
        }
      }
      const response = await fetch(`${API_BASE}/api/v1/agents`);
      if (response.ok) {
        setAgents((await response.json()) as Agent[]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    const agentId = new URLSearchParams(window.location.search).get("agent");
    if (!agentId) return;
    setExpandedId(agentId);
    void fetchAgentAudit(agentId);
  }, []);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("register") === "1") {
      setRegisterOpen(true);
    }
  }, []);

  function toggleTool(tool: string) {
    setFormTools((prev) => (prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]));
  }

  function validate(): boolean {
    if (!formName.trim()) {
      setNameErr("Name is required");
      return false;
    }
    setNameErr("");
    return true;
  }

  function resetRegisterForm() {
    setRegisterPhase("form");
    setFormName("");
    setFormDescription("");
    setFormFramework("custom");
    setFormTools([]);
    setFormMaxRisk(0.8);
    setNameErr("");
    setSuccessApiKey("");
    setSuccessAgentName("");
    setCopiedKey(false);
  }

  function closeRegisterModal() {
    setRegisterOpen(false);
    resetRegisterForm();
  }

  async function copyApiKey() {
    if (!successApiKey) return;
    try {
      await navigator.clipboard.writeText(successApiKey);
      setCopiedKey(true);
      toast("API key copied", "success");
      setTimeout(() => setCopiedKey(false), 2000);
    } catch {
      toast("Could not copy", "error");
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/agents/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formName.trim(),
          description: formDescription.trim(),
          framework: formFramework,
          allowed_tools: formTools.length ? formTools : ["send_email"],
          max_risk_tolerance: formMaxRisk,
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || res.statusText);
      }
      const data = (await res.json()) as { api_key: string; name: string };
      setSuccessApiKey(data.api_key);
      setSuccessAgentName(data.name);
      setRegisterPhase("success");
      await loadAgents();
      toast("Agent registered — save your API key", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Registration failed", "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function killSwitch(agentId: string) {
    if (!confirm("Deactivate this agent?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/agents/${encodeURIComponent(agentId)}/deactivate`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await res.text());
      await loadAgents();
      toast("Agent deactivated", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed", "error");
    }
  }

  async function fetchAgentAudit(agentId: string) {
    if (agentAudit[agentId]) return;
    const r = await fetch(`${API_BASE}/api/v1/audit?agent_id=${encodeURIComponent(agentId)}&limit=120`);
    if (!r.ok) return;
    const rows = (await r.json()) as AuditEntry[];
    setAgentAudit((p) => ({ ...p, [agentId]: rows }));
  }

  async function removeAgent(agentId: string) {
    if (!confirm("Delete this agent?")) return;
    try {
      const r = await fetch(`${API_BASE}/api/v1/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
      if (!r.ok) throw new Error(await r.text());
      toast("Agent deleted", "success");
      setExpandedId((p) => (p === agentId ? null : p));
      await loadAgents();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Delete failed", "error");
    }
  }

  async function saveEdit() {
    if (!editAgent) return;
    try {
      const r = await fetch(`${API_BASE}/api/v1/agents/${encodeURIComponent(editAgent.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName.trim(),
          description: editDescription.trim(),
          allowed_tools: editTools,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      toast("Agent updated", "success");
      setEditAgent(null);
      await loadAgents();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Update failed", "error");
    }
  }

  return (
    <div className="page-enter space-y-8 pb-12">
      <PageHeader
        title="Agents"
        subtitle="Registry & reputation"
        breadcrumbs={[{ label: "Agents" }]}
        actions={
          <button
            type="button"
            onClick={() => {
              resetRegisterForm();
              setRegisterOpen(true);
            }}
            className="rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-900/30 transition hover:brightness-110"
          >
            Register agent
          </button>
        }
      />

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-48 animate-pulse rounded-2xl bg-[#100e08]" />
          ))}
        </div>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[#2e2918] bg-[#060504]/50 py-20 text-center">
          <div className="mb-4 flex h-24 w-24 items-center justify-center rounded-2xl bg-gradient-to-br from-[#ca8a04]/35 to-amber-900/25 text-4xl">
            🤖
          </div>
          <p className="text-lg font-medium text-[#f0f6fc]">No agents yet</p>
          <p className="mt-2 max-w-md text-sm text-[#8b949e]">
            Register an agent to track reputation, actions, and kill-switch access.
          </p>
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          {agents.map((agent) => (
            <article
              key={agent.id}
              className="glass-card glass-card-hover group cursor-pointer p-5"
              onClick={() => {
                const next = expandedId === agent.id ? null : agent.id;
                setExpandedId(next);
                if (next) void fetchAgentAudit(agent.id);
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-[#f0f6fc]">{agent.name}</h3>
                  <p className="font-mono text-xs text-[#fde047]">{agent.id}</p>
                </div>
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                    agent.status === "active"
                      ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40"
                      : "bg-zinc-600/30 text-zinc-300 ring-1 ring-zinc-500/40"
                  }`}
                >
                  {agent.status}
                </span>
              </div>
              <div className="mt-3 flex justify-end gap-1">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditAgent(agent);
                    setEditName(agent.name);
                    setEditDescription("");
                    setEditTools(agent.allowed_tools ?? []);
                  }}
                  className="rounded p-1.5 text-[#8b949e] hover:bg-[#21262d] hover:text-[#f0f6fc]"
                  aria-label="Edit agent"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    void removeAgent(agent.id);
                  }}
                  className="rounded p-1.5 text-[#8b949e] hover:bg-red-500/20 hover:text-red-300"
                  aria-label="Delete agent"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-4">
                <div className="mb-1 flex justify-between text-xs text-[#8b949e]">
                  <span>Reputation</span>
                  <span className="font-mono">{Number(agent.reputation_score).toFixed(2)}</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-[#21262d]">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${repColor(Number(agent.reputation_score))}`}
                    style={{ width: `${Math.min(100, Number(agent.reputation_score) * 100)}%` }}
                  />
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-2 text-xs text-[#8b949e]">
                <div>
                  <dt>Total actions</dt>
                  <dd className="font-mono text-[#c9d1d9]">{agent.total_actions}</dd>
                </div>
                <div>
                  <dt>Blocked</dt>
                  <dd className="font-mono text-[#c9d1d9]">{agent.blocked_actions}</dd>
                </div>
                <div className="col-span-2">
                  <dt>Last active</dt>
                  <dd className="text-[#c9d1d9]">
                    {agent.last_active ? new Date(agent.last_active).toLocaleString() : "—"}
                  </dd>
                </div>
              </dl>
              <div className="mt-4 flex justify-end border-t border-[#2e2918] pt-4">
                <button
                  type="button"
                  onClick={() => killSwitch(agent.id)}
                  disabled={agent.status === "deactivated"}
                  className="rounded-lg bg-red-600/90 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Kill switch
                </button>
              </div>
              {expandedId === agent.id ? (
                <div className="mt-4 border-t border-[#2e2918] pt-4 text-xs text-[#8b949e]">
                  {(() => {
                    const rows = agentAudit[agent.id] ?? [];
                    const last20 = rows.slice(0, 20);
                    const blockRate = rows.length ? (rows.filter((r) => r.decision === "block").length / rows.length) * 100 : 0;
                    const toolCounts = new Map<string, number>();
                    const trend = new Map<string, number>();
                    for (const r of rows) {
                      toolCounts.set(r.tool_name, (toolCounts.get(r.tool_name) ?? 0) + 1);
                      const d = new Date(r.timestamp);
                      const k = `${d.getMonth() + 1}/${d.getDate()}`;
                      trend.set(k, (trend.get(k) ?? 0) + r.risk_score);
                    }
                    const topTools = [...toolCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
                    const trendText = [...trend.entries()]
                      .slice(-6)
                      .map(([k, v]) => `${k}:${(v).toFixed(1)}`)
                      .join(" | ");
                    return (
                      <div className="space-y-3">
                        <p className="text-[#c9d1d9]">
                          Block rate: <span className="font-mono">{blockRate.toFixed(1)}%</span>
                        </p>
                        <p>Most common tools: {topTools.map(([t, c]) => `${t} (${c})`).join(", ") || "—"}</p>
                        <p>Risk trend: {trendText || "No trend data yet"}</p>
                        <div>
                          <p className="mb-1 text-[#c9d1d9]">Last 20 actions</p>
                          {last20.length === 0 ? (
                            <p>No actions yet.</p>
                          ) : (
                            <ul className="space-y-1">
                              {last20.map((r) => (
                                <li key={r.action_id} className="flex items-center justify-between rounded border border-[#2e2918] bg-[#060504] px-2 py-1">
                                  <span>{r.tool_name}</span>
                                  <span className="font-mono">{r.decision} · {Number(r.risk_score).toFixed(2)}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}

      {registerOpen ? (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="glass-card relative max-h-[90vh] w-full max-w-lg overflow-y-auto p-6 shadow-2xl">
            <button
              type="button"
              className="absolute right-4 top-4 rounded-lg p-2 text-[#8b949e] transition hover:bg-[#21262d] hover:text-white"
              onClick={closeRegisterModal}
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
            {registerPhase === "form" ? (
              <>
                <h3 className="pr-10 text-lg font-semibold text-[#f0f6fc]">Register new agent</h3>
                <p className="mt-1 text-sm text-[#8b949e]">
                  Creates an entry in the Agentiva registry and issues a one-time API key.
                </p>
                <form onSubmit={handleRegister} className="mt-6 space-y-5">
                  <div>
                    <label htmlFor="agent-name" className="block text-sm font-medium text-[#c9d1d9]">
                      Agent name <span className="text-red-400">*</span>
                    </label>
                    <input
                      id="agent-name"
                      type="text"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-[#f0f6fc] focus:border-[#eab308] focus:outline-none focus:ring-1 focus:ring-[#ca8a04]"
                      placeholder="e.g. Sales outreach bot"
                      required
                    />
                    {nameErr ? <p className="mt-1 text-xs text-red-400">{nameErr}</p> : null}
                  </div>
                  <div>
                    <label htmlFor="agent-desc" className="block text-sm font-medium text-[#c9d1d9]">
                      Description
                    </label>
                    <textarea
                      id="agent-desc"
                      value={formDescription}
                      onChange={(e) => setFormDescription(e.target.value)}
                      rows={2}
                      className="mt-1 w-full resize-none rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-sm text-[#f0f6fc] focus:border-[#eab308] focus:outline-none focus:ring-1 focus:ring-[#ca8a04]"
                      placeholder="Optional — what does this agent do?"
                    />
                  </div>
                  <div>
                    <label htmlFor="agent-framework" className="block text-sm font-medium text-[#c9d1d9]">
                      Your stack
                    </label>
                    <p id="agent-framework-hint" className="mt-0.5 text-xs text-[#8b949e]">
                      Optional — pick what you use so we can surface the right integration examples. Not tied to how Agentiva runs.
                    </p>
                    <select
                      id="agent-framework"
                      aria-describedby="agent-framework-hint"
                      value={formFramework}
                      onChange={(e) => setFormFramework(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-[#f0f6fc] focus:border-[#eab308] focus:outline-none focus:ring-1 focus:ring-[#ca8a04]"
                    >
                      {FRAMEWORK_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <span className="block text-sm font-medium text-[#c9d1d9]">Allowed tools</span>
                    <div className="mt-2 max-h-40 space-y-2 overflow-y-auto rounded-lg border border-[#2e2918] bg-[#060504] p-3">
                      {TOOL_OPTIONS.map((tool) => (
                        <label key={tool} className="flex cursor-pointer items-center gap-2 text-sm text-[#c9d1d9]">
                          <input
                            type="checkbox"
                            checked={formTools.includes(tool)}
                            onChange={() => toggleTool(tool)}
                            className="rounded border-[#2e2918]"
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
                      <span className="font-mono text-sm text-[#fde047]">{formMaxRisk.toFixed(2)}</span>
                    </div>
                    <input
                      id="max-risk"
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={formMaxRisk}
                      onChange={(e) => setFormMaxRisk(Number(e.target.value))}
                      className="mt-2 w-full accent-[#eab308]"
                    />
                  </div>
                  <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
                    <button
                      type="button"
                      onClick={closeRegisterModal}
                      className="rounded-lg border border-[#2e2918] px-4 py-2 text-sm font-medium text-[#c9d1d9] hover:bg-[#21262d]"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submitting}
                      className="rounded-lg bg-[#238636] px-4 py-2 text-sm font-semibold text-white hover:bg-[#2ea043] disabled:opacity-50"
                    >
                      {submitting ? "Registering…" : "Register"}
                    </button>
                  </div>
                </form>
              </>
            ) : (
              <div className="space-y-5 pt-1">
                <h3 className="pr-10 text-lg font-semibold text-[#f0f6fc]">Agent registered</h3>
                <p className="text-sm text-[#8b949e]">
                  <span className="font-medium text-[#c9d1d9]">{successAgentName}</span> is ready. Save your API key —
                  you won&apos;t see it again.
                </p>
                <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-200/90">Your API key</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <code className="min-w-0 flex-1 break-all rounded-lg bg-[#060504] px-3 py-2 font-mono text-sm text-[#fde047]">
                      {successApiKey}
                    </code>
                    <button
                      type="button"
                      onClick={() => void copyApiKey()}
                      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-[#2e2918] bg-[#1a170f] px-3 py-2 text-xs font-semibold text-[#faf6e8] hover:bg-[#2e2918]"
                    >
                      {copiedKey ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                      {copiedKey ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-[#8b949e]">Add to your code</p>
                  <pre className="mt-2 overflow-x-auto rounded-lg border border-[#2e2918] bg-[#060504] p-3 font-mono text-[11px] leading-relaxed text-[#c9d1d9]">
                    {`from agentiva import Agentiva

shield = Agentiva(api_key="${successApiKey}", mode="shadow")
tools = shield.protect([your_existing_tools])`}
                  </pre>
                </div>
                <button
                  type="button"
                  onClick={closeRegisterModal}
                  className="w-full rounded-lg bg-[#238636] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#2ea043]"
                >
                  Done
                </button>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {editAgent ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="glass-card w-full max-w-md p-5">
            <h3 className="text-lg font-semibold text-[#f0f6fc]">Edit agent</h3>
            <div className="mt-4 space-y-3">
              <div>
                <label className="block text-sm text-[#c9d1d9]">Name</label>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-[#f0f6fc]"
                />
              </div>
              <div>
                <label className="block text-sm text-[#c9d1d9]">Description</label>
                <textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-[#f0f6fc]"
                />
              </div>
              <div>
                <label className="block text-sm text-[#c9d1d9]">Allowed tools</label>
                <div className="mt-2 max-h-36 space-y-1 overflow-y-auto rounded-lg border border-[#2e2918] bg-[#060504] p-2">
                  {TOOL_OPTIONS.map((tool) => (
                    <label key={tool} className="flex items-center gap-2 text-xs text-[#c9d1d9]">
                      <input
                        type="checkbox"
                        checked={editTools.includes(tool)}
                        onChange={() =>
                          setEditTools((prev) => (prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]))
                        }
                      />
                      <span className="font-mono">{tool}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setEditAgent(null)} className="rounded-lg border border-[#2e2918] px-3 py-2 text-sm text-[#c9d1d9]">Cancel</button>
              <button type="button" onClick={() => void saveEdit()} className="rounded-lg bg-[#238636] px-3 py-2 text-sm font-semibold text-white">Save</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
