"use client";

import { useEffect, useState } from "react";

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

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);

  async function loadAgents() {
    const response = await fetch(`${API_BASE}/api/v1/agents`);
    if (response.ok) {
      setAgents((await response.json()) as Agent[]);
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadAgents();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  async function deactivate(agentId: string) {
    await fetch(`${API_BASE}/api/v1/agents/${agentId}/deactivate`, { method: "POST" });
    await loadAgents();
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-[#8b949e]">Agent registry and reputation</p>
        <h2 className="text-3xl font-semibold text-[#f0f6fc]">Agents</h2>
      </header>

      <div className="overflow-hidden rounded-xl border border-[#30363d] bg-[#161b22]">
        <table className="min-w-full text-sm">
          <thead className="bg-[#0d1117] text-left text-[#8b949e]">
            <tr>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Owner</th>
              <th className="px-4 py-3">Reputation</th>
              <th className="px-4 py-3">Actions</th>
              <th className="px-4 py-3">Blocked</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Kill Switch</th>
            </tr>
          </thead>
          <tbody>
            {agents.length === 0 ? (
              <tr>
                <td className="px-4 py-3 text-[#8b949e]" colSpan={7}>
                  No agents registered.
                </td>
              </tr>
            ) : (
              agents.map((agent) => (
                <tr key={agent.id} className="border-t border-[#30363d]">
                  <td className="px-4 py-3 text-[#f0f6fc]">{agent.name}</td>
                  <td className="px-4 py-3">{agent.owner}</td>
                  <td className="px-4 py-3">{agent.reputation_score.toFixed(2)}</td>
                  <td className="px-4 py-3">{agent.total_actions}</td>
                  <td className="px-4 py-3">{agent.blocked_actions}</td>
                  <td className="px-4 py-3">{agent.status}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => deactivate(agent.id)}
                      className="rounded-md border border-red-500/50 bg-red-500/10 px-3 py-1 text-red-300 hover:bg-red-500/20"
                      disabled={agent.status === "deactivated"}
                    >
                      Deactivate
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
