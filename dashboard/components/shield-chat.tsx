"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageCircle, Send, Shield, X } from "lucide-react";

const API_BASE = "http://localhost:8000";

type ChatPayload = {
  answer: string;
  data: unknown;
  follow_up_suggestions: string[];
  mode?: string;
};

function DataBlock({ data }: { data: unknown }) {
  if (data == null) return null;
  if (typeof data === "string") {
    return <p className="mt-2 text-sm text-[#8b949e]">{data}</p>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <p className="mt-2 text-sm text-[#8b949e]">(empty)</p>;
    }
    const first = data[0];
    if (typeof first === "string") {
      return (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-[#c9d1d9]">
          {data.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      );
    }
    if (typeof first === "object" && first !== null) {
      const keys = Object.keys(first as object);
      return (
        <div className="mt-2 max-h-52 overflow-auto rounded border border-[#30363d]">
          <table className="w-full min-w-[260px] text-left text-xs">
            <thead className="sticky top-0 bg-[#0d1117] text-[#8b949e]">
              <tr>
                {keys.map((k) => (
                  <th key={k} className="px-2 py-1.5 font-medium">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data as Record<string, unknown>[]).map((row, i) => (
                <tr key={i} className="border-t border-[#30363d]">
                  {keys.map((k) => (
                    <td
                      key={k}
                      className="max-w-[140px] break-words px-2 py-1 font-mono text-[11px] text-[#c9d1d9]"
                    >
                      {typeof row[k] === "object" && row[k] !== null
                        ? JSON.stringify(row[k])
                        : String(row[k] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
  }
  if (typeof data === "object") {
    return (
      <pre className="mt-2 max-h-52 overflow-auto rounded border border-[#30363d] bg-[#0d1117] p-2 text-[11px] leading-relaxed text-[#c9d1d9]">
        {JSON.stringify(data, null, 2)}
      </pre>
    );
  }
  return <span className="text-sm">{String(data)}</span>;
}

type UserMsg = { id: string; role: "user"; text: string };
type AssistantMsg = {
  id: string;
  role: "assistant";
  answer: string;
  data: unknown;
  follow_up_suggestions: string[];
  mode?: string;
};
type Msg = UserMsg | AssistantMsg;

export function ShieldChatPanel() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [streaming, setStreaming] = useState<{
    full: string;
    pos: number;
    data: unknown;
    suggestions: string[];
    mode: string;
  } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/chat/capabilities`)
      .then((r) => r.json() as Promise<{ llm_enabled: boolean }>)
      .then((b) => setLlmEnabled(b.llm_enabled))
      .catch(() => setLlmEnabled(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming, loading, open]);

  useEffect(() => {
    if (!streaming) return;
    if (streaming.pos >= streaming.full.length) {
      const id = crypto.randomUUID();
      setMessages((m) => [
        ...m,
        {
          id,
          role: "assistant",
          answer: streaming.full,
          data: streaming.data,
          follow_up_suggestions: streaming.suggestions,
          mode: streaming.mode,
        },
      ]);
      setStreaming(null);
      return;
    }
    const t = window.setTimeout(() => {
      setStreaming((s) => (s ? { ...s, pos: s.pos + 2 } : null));
    }, 12);
    return () => clearTimeout(t);
  }, [streaming]);

  const busy = loading || !!streaming;

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      setInput("");
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", text: trimmed }]);
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed }),
        });
        if (!res.ok) {
          throw new Error(await res.text());
        }
        const payload = (await res.json()) as ChatPayload;
        setStreaming({
          full: payload.answer,
          pos: 0,
          data: payload.data,
          suggestions: payload.follow_up_suggestions ?? [],
          mode: payload.mode ?? "basic",
        });
      } catch (e) {
        setMessages((m) => [
          ...m,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            answer: `Something went wrong: ${e instanceof Error ? e.message : "request failed"}`,
            data: {},
            follow_up_suggestions: ["Give me a session summary"],
            mode: "basic",
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [busy]
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`fixed bottom-6 right-6 z-[60] flex h-14 w-14 items-center justify-center rounded-full bg-[#3b82f6] text-white shadow-lg transition hover:bg-[#2563eb] focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-[#0d1117] ${
          open ? "pointer-events-none scale-0 opacity-0" : "scale-100 opacity-100"
        }`}
        aria-label="Open AgentShield chat"
      >
        <MessageCircle className="h-7 w-7" strokeWidth={2} />
      </button>

      <div
        className={`fixed bottom-0 right-0 z-[70] flex max-h-[min(92vh,720px)] w-full flex-col rounded-t-2xl border border-[#30363d] bg-[#161b22] shadow-2xl transition-transform duration-300 ease-out sm:bottom-6 sm:right-6 sm:max-w-md ${
          open ? "translate-y-0" : "translate-y-[110%] pointer-events-none"
        }`}
        aria-hidden={!open}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[#30363d] px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#238636]/20">
              <Shield className="h-5 w-5 text-[#3fb950]" />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-[#f0f6fc]">AgentShield</p>
                {llmEnabled !== null && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                      llmEnabled
                        ? "bg-[#1f6feb]/25 text-[#58a6ff] ring-1 ring-[#1f6feb]/40"
                        : "bg-[#30363d] text-[#8b949e]"
                    }`}
                  >
                    {llmEnabled ? "AI-powered" : "Basic"}
                  </span>
                )}
              </div>
              <p className="text-xs text-[#8b949e]">Ask about agents &amp; policy</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md p-2 text-[#8b949e] hover:bg-[#30363d] hover:text-[#f0f6fc]"
            aria-label="Close chat"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
          {messages.length === 0 && !streaming && !loading && (
            <p className="text-sm text-[#8b949e]">
              Ask why actions were blocked, request a session summary, or explore risky behavior.
            </p>
          )}
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[#1f6feb] px-3 py-2 text-sm text-white">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex gap-2">
                <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#21262d]">
                  <Shield className="h-4 w-4 text-[#3fb950]" />
                </div>
                <div className="flex max-w-[90%] flex-col rounded-2xl rounded-bl-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#c9d1d9]">
                  {m.mode === "ai-powered" && (
                    <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-[#58a6ff]">
                      AI-powered
                    </p>
                  )}
                  <p className="whitespace-pre-wrap">{m.answer}</p>
                  <DataBlock data={m.data} />
                  {m.follow_up_suggestions.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {m.follow_up_suggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => void send(s)}
                          disabled={busy}
                          className="rounded-full border border-[#30363d] bg-[#161b22] px-2.5 py-1 text-left text-xs text-[#58a6ff] hover:border-[#1f6feb] hover:bg-[#21262d] disabled:opacity-50"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          )}
          {streaming && (
            <div className="flex gap-2">
              <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#21262d]">
                <Shield className="h-4 w-4 text-[#3fb950]" />
              </div>
              <div className="max-w-[90%] rounded-2xl rounded-bl-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#c9d1d9]">
                {streaming.mode === "ai-powered" && (
                  <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-[#58a6ff]">
                    AI-powered
                  </p>
                )}
                <p className="whitespace-pre-wrap">
                  {streaming.full.slice(0, streaming.pos)}
                  {streaming.pos < streaming.full.length ? (
                    <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-[#58a6ff]" />
                  ) : null}
                </p>
              </div>
            </div>
          )}
          {loading && !streaming && (
            <p className="text-sm italic text-[#8b949e]">Thinking…</p>
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={onSubmit} className="shrink-0 border-t border-[#30363d] p-3">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask AgentShield…"
              className="min-w-0 flex-1 rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2.5 text-sm text-[#f0f6fc] placeholder:text-[#484f58] focus:border-[#1f6feb] focus:outline-none focus:ring-1 focus:ring-[#1f6feb]"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="flex shrink-0 items-center justify-center rounded-lg bg-[#238636] px-3 py-2 text-white hover:bg-[#2ea043] disabled:opacity-40"
              aria-label="Send message"
            >
              <Send className="h-5 w-5" />
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
