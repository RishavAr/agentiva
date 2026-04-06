/**
 * Browser-only sample data when the Python API is unreachable (e.g. hosted dashboard on Vercel).
 * Mirrors the shape of /api/v1/report, /api/v1/audit, /api/v1/agents, etc.
 */

const STORAGE_KEY = "agentiva_offline_demo_v1";

export type OfflineAuditEntry = {
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

export type OfflineShadowReport = {
  total_actions: number;
  by_tool: Record<string, number>;
  by_decision: Record<string, number>;
  avg_risk_score: number;
};

export type OfflineAgentRow = {
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

export type OfflineAgentSummary = {
  agent_id: string;
  display_name: string;
  total_actions: number;
  blocked_actions: number;
  last_active: string | null;
};

export type OfflineDemoPayload = {
  audit: OfflineAuditEntry[];
  report: OfflineShadowReport;
  agents: OfflineAgentRow[];
  summaries: OfflineAgentSummary[];
  health: { mode: string; risk_threshold: number };
};

function mergeReport(prev: OfflineShadowReport | null, row: OfflineAuditEntry): OfflineShadowReport {
  const base: OfflineShadowReport = prev ?? {
    total_actions: 0,
    by_tool: {},
    by_decision: {},
    avg_risk_score: 0,
  };
  const dec = row.decision;
  const tool = row.tool_name;
  const by_decision = { ...base.by_decision, [dec]: (base.by_decision[dec] ?? 0) + 1 };
  const by_tool = { ...base.by_tool, [tool]: (base.by_tool[tool] ?? 0) + 1 };
  const total = base.total_actions + 1;
  const sum = base.avg_risk_score * base.total_actions + row.risk_score;
  return {
    total_actions: total,
    by_tool,
    by_decision,
    avg_risk_score: total ? sum / total : 0,
  };
}

function buildPayload(): OfflineDemoPayload {
  const t0 = Date.now();
  const iso = (offsetMs: number) => new Date(t0 - offsetMs).toISOString();

  const audit: OfflineAuditEntry[] = [
    {
      action_id: "offline-demo-1",
      tool_name: "send_email",
      arguments: { to: "x@evil.com", subject: "customer data" },
      agent_id: "demo-agent-1",
      decision: "block",
      risk_score: 0.94,
      mode: "shadow",
      timestamp: iso(120_000),
    },
    {
      action_id: "offline-demo-2",
      tool_name: "send_email",
      arguments: { to: "ally@yourcompany.com", subject: "Standup notes" },
      agent_id: "demo-agent-1",
      decision: "allow",
      risk_score: 0.14,
      mode: "shadow",
      timestamp: iso(110_000),
    },
    {
      action_id: "offline-demo-3",
      tool_name: "read_customer_data",
      arguments: { fields: "ssn" },
      agent_id: "demo-agent-1",
      decision: "block",
      risk_score: 0.97,
      mode: "shadow",
      timestamp: iso(95_000),
    },
    {
      action_id: "offline-demo-4",
      tool_name: "read_customer_data",
      arguments: { fields: "name" },
      agent_id: "demo-agent-1",
      decision: "shadow",
      risk_score: 0.48,
      mode: "shadow",
      timestamp: iso(80_000),
    },
    {
      action_id: "offline-demo-5",
      tool_name: "update_database",
      arguments: { query: "SELECT 1" },
      agent_id: "demo-agent-1",
      decision: "shadow",
      risk_score: 0.52,
      mode: "shadow",
      timestamp: iso(65_000),
    },
    {
      action_id: "offline-demo-6",
      tool_name: "create_ticket",
      arguments: { title: "Bug" },
      agent_id: "demo-agent-1",
      decision: "allow",
      risk_score: 0.18,
      mode: "shadow",
      timestamp: iso(50_000),
    },
  ];

  let report: OfflineShadowReport | null = null;
  for (const row of audit) {
    report = mergeReport(report, row);
  }
  if (!report) {
    report = { total_actions: 0, by_tool: {}, by_decision: {}, avg_risk_score: 0 };
  }

  const blocked = audit.filter((a) => a.decision === "block").length;
  const agents: OfflineAgentRow[] = [
    {
      id: "demo-agent-1",
      name: "Demo Agent",
      owner: "demo@agentiva.local",
      reputation_score: 0.82,
      total_actions: audit.length,
      blocked_actions: blocked,
      status: "active",
      last_active: audit[0]?.timestamp ?? null,
      allowed_tools: [
        "send_email",
        "read_customer_data",
        "update_database",
        "call_external_api",
        "create_ticket",
      ],
    },
  ];

  const summaries: OfflineAgentSummary[] = [
    {
      agent_id: "demo-agent-1",
      display_name: "Demo Agent",
      total_actions: audit.length,
      blocked_actions: blocked,
      last_active: audit[0]?.timestamp ?? null,
    },
  ];

  return {
    audit,
    report,
    agents,
    summaries,
    health: { mode: "shadow", risk_threshold: 0.7 },
  };
}

export function isOfflineDemoActive(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) != null;
  } catch {
    return false;
  }
}

export function readOfflineDemoPayload(): OfflineDemoPayload | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as OfflineDemoPayload;
    if (!parsed?.audit || !Array.isArray(parsed.audit)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function seedOfflineDemo(): OfflineDemoPayload {
  const payload = buildPayload();
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      /* ignore quota */
    }
  }
  return payload;
}

export function clearOfflineDemo(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Client-side audit list filtering to mirror dashboard filters (hosted / offline). */
export function filterOfflineAudit(
  entries: OfflineAuditEntry[],
  toolName: string,
  decision: string,
  minRisk: string,
  agentId: string,
): OfflineAuditEntry[] {
  let out = entries;
  const tn = toolName.trim().toLowerCase();
  if (tn) {
    out = out.filter((e) => e.tool_name.toLowerCase().includes(tn));
  }
  const dec = decision.trim().toLowerCase();
  if (dec) {
    out = out.filter((e) => e.decision.toLowerCase() === dec);
  }
  if (minRisk.trim()) {
    const min = Number(minRisk);
    if (!Number.isNaN(min)) {
      out = out.filter((e) => e.risk_score >= min);
    }
  }
  const aid = agentId.trim();
  if (aid) {
    out = out.filter((e) => e.agent_id === aid);
  }
  return out;
}
