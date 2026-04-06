"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { getHttpApiBase, getWsBase } from "@/lib/api-base";
import { isOfflineDemoActive, readOfflineDemoPayload } from "@/lib/offline-demo";

type ActionFeedItem = {
  action_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  agent_id: string;
  decision: string;
  risk_score: number;
  mode: string;
  timestamp: string;
};

const API_BASE = getHttpApiBase();
const WS_BASE = getWsBase();

function relTime(iso: string, _tick = 0): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function borderForDecision(d: string) {
  if (d === "block") return "border-l-red-500";
  if (d === "allow" || d === "approve") return "border-l-emerald-500";
  return "border-l-amber-400";
}

export default function LiveFeedPage() {
  const [actions, setActions] = useState<ActionFeedItem[]>([]);
  const [offlineSample, setOfflineSample] = useState(false);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected" | "error" | "reconnecting">(
    "connecting",
  );
  const [filter, setFilter] = useState<"all" | "block" | "shadow" | "allow">("all");
  const [soundOn, setSoundOn] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const prevBlocked = useRef(0);
  const attemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && isOfflineDemoActive()) {
      const payload = readOfflineDemoPayload();
      if (payload) {
        const sorted = [...payload.audit].sort(
          (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
        );
        setActions(sorted);
        setStatus("connected");
        setOfflineSample(true);
      }
      return () => {};
    }

    let cancelled = false;

    function scheduleReconnect() {
      if (cancelled) return;
      attemptRef.current += 1;
      const delay = Math.min(30_000, 800 * 2 ** Math.min(attemptRef.current, 6));
      setStatus("reconnecting");
      timerRef.current = setTimeout(connect, delay);
    }

    function connect() {
      if (cancelled) return;
      timerRef.current = null;
      if (attemptRef.current === 0) setStatus("connecting");
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      const ws = new WebSocket(`${WS_BASE}/ws/actions`);
      wsRef.current = ws;
      ws.onopen = () => {
        if (cancelled) return;
        attemptRef.current = 0;
        setStatus("connected");
      };
      ws.onclose = () => {
        if (cancelled) return;
        setStatus("disconnected");
        scheduleReconnect();
      };
      ws.onerror = () => {
        if (cancelled) return;
        setStatus("error");
      };
      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as ActionFeedItem;
          setActions((prev) => [parsed, ...prev].slice(0, 50));
        } catch {
          /* ignore */
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    };
  }, []);

  const [timeTick, setTimeTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTimeTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const blocked = actions.filter((a) => a.decision === "block").length;
    if (soundOn && blocked > prevBlocked.current) {
      try {
        const ctx = new AudioContext();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.connect(g);
        g.connect(ctx.destination);
        o.frequency.value = 880;
        g.gain.value = 0.05;
        o.start();
        setTimeout(() => {
          o.stop();
          void ctx.close();
        }, 120);
      } catch {
        /* ignore */
      }
    }
    prevBlocked.current = blocked;
  }, [actions, soundOn]);

  const filtered = useMemo(() => {
    if (filter === "all") return actions;
    if (filter === "allow") return actions.filter((a) => a.decision === "allow" || a.decision === "approve");
    return actions.filter((a) => a.decision === filter);
  }, [actions, filter]);

  const chips: { id: typeof filter; label: string }[] = [
    { id: "all", label: "All" },
    { id: "block", label: "Blocked" },
    { id: "shadow", label: "Shadowed" },
    { id: "allow", label: "Allowed" },
  ];

  return (
    <div className="page-enter space-y-6 pb-12">
      <PageHeader
        title="Live feed"
        subtitle={
          offlineSample ? "Sample actions (browser demo — no WebSocket)" : "Real-time WebSocket stream"
        }
        breadcrumbs={[{ label: "Live Feed" }]}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setFilter(c.id)}
              className={`rounded-full px-4 py-1.5 text-xs font-semibold uppercase tracking-wide transition ${
                filter === c.id
                  ? "bg-[#ca8a04] text-[#0a0805] shadow-lg shadow-amber-950/40"
                  : "border border-[#2e2918] bg-[#100e08] text-[#8a8270] hover:border-[#eab308]/40"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-[#8a8270]">
          <input type="checkbox" checked={soundOn} onChange={(e) => setSoundOn(e.target.checked)} className="rounded" />
          Sound on block
        </label>
      </div>

      <div className="glass-card flex flex-wrap items-center gap-3 px-4 py-3">
        <span className="relative flex h-3 w-3">
          {status === "connected" ? (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500" />
            </>
          ) : (
            <span className="relative inline-flex h-3 w-3 rounded-full bg-amber-500" />
          )}
        </span>
        <span
          className={`text-sm font-bold uppercase tracking-wide ${
            status === "connected" ? "text-emerald-400" : "text-amber-200"
          }`}
        >
          {status === "connected"
            ? "CONNECTED"
            : status === "connecting"
              ? "Connecting…"
              : status === "reconnecting"
                ? "Reconnecting…"
                : status.toUpperCase()}
        </span>
        <span className="text-xs text-[#8a8270]">{WS_BASE}/ws/actions</span>
      </div>

      <div ref={listRef} className="glass-card max-h-[calc(100vh-280px)] space-y-3 overflow-y-auto p-4">
        {filtered.length === 0 && actions.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
            <div className="relative h-32 w-32">
              <div className="absolute inset-0 animate-pulse rounded-full bg-gradient-to-br from-[#ca8a04]/35 to-amber-900/25 blur-xl" />
              <div className="relative flex h-full w-full items-center justify-center rounded-full border border-[#2e2918] bg-[#100e08] text-4xl">
                ⚡
              </div>
            </div>
            <div className="max-w-md space-y-2">
              <p className="flex items-center justify-center gap-2 text-lg font-medium text-[#f0f6fc]">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                </span>
                Waiting for agent actions…
              </p>
              <p className="text-sm text-[#8a8270]">
                No actions yet. Run the demo to see Agentiva in action:
              </p>
              <code className="block rounded-lg border border-[#2e2918] bg-[#060504] px-3 py-2 text-left font-mono text-xs text-[#fde047]">
                python demo/paybot_demo.py
              </code>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-[#8a8270]">No items match this filter.</p>
        ) : (
          filtered.map((action) => {
            const pct = Math.max(0, Math.min(100, Math.round(action.risk_score * 100)));
            const open = expanded === action.action_id;
            return (
              <article
                key={action.action_id}
                className={`glass-card glass-card-hover rounded-xl border-l-4 p-4 ${borderForDecision(
                  action.decision,
                )}`}
                style={{ animation: "slide-in-right 230ms ease-out both" }}
              >
                <button type="button" className="w-full text-left" onClick={() => setExpanded(open ? null : action.action_id)}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="text-base font-bold text-[#f0f6fc]">{action.tool_name}</p>
                      <span className="inline-block rounded-full bg-[#21262d] px-2 py-0.5 font-mono text-[11px] text-[#fde047]">
                        {action.agent_id}
                      </span>
                    </div>
                    <div className="text-right">
                      <DecisionPill decision={action.decision} />
                      <p className="mt-1 text-xs text-[#8a8270]">{relTime(action.timestamp, timeTick)}</p>
                    </div>
                  </div>
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between text-xs text-[#8a8270]">
                      <span>Risk</span>
                      <span className="font-mono">{action.risk_score.toFixed(2)}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#21262d]">
                      <div
                        className={`h-2 rounded-full ${pct > 70 ? "bg-red-500" : pct >= 40 ? "bg-amber-500" : "bg-emerald-500"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </button>
                {open ? (
                  <pre className="mt-3 max-h-48 overflow-auto rounded-lg border border-[#2e2918] bg-[#060504] p-3 font-mono text-xs text-[#c9d1d9]">
                    {JSON.stringify(action.arguments, null, 2)}
                  </pre>
                ) : null}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}

function DecisionPill({ decision }: { decision: string }) {
  const d = decision.toLowerCase();
  const cls =
    d === "block"
      ? "bg-red-500/20 text-red-200 ring-red-500/40"
      : d === "allow" || d === "approve"
        ? "bg-emerald-500/20 text-emerald-200 ring-emerald-500/40"
        : "bg-amber-500/20 text-amber-200 ring-amber-500/40";
  const label =
    d === "block" ? "BLOCK" : d === "allow" || d === "approve" ? "ALLOW" : d === "shadow" ? "SHADOW" : decision.toUpperCase();
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ring-1 ${cls}`}>
      {label}
    </span>
  );
}
