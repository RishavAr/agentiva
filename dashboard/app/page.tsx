"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Loader2, Shield } from "lucide-react";

import { getHttpApiBase } from "@/lib/api-base";
import { clearOfflineDemo, seedOfflineDemo } from "@/lib/offline-demo";
import { toast } from "@/components/toast-host";

const API_BASE = getHttpApiBase();

const FRAMEWORKS = ["LangChain", "CrewAI", "OpenAI Agents", "MCP", "Custom"] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [framework, setFramework] = useState<string>("LangChain");
  const [submitting, setSubmitting] = useState(false);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [registeredName, setRegisteredName] = useState("");

  const pingApi = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/v1/bootstrap`);
    } catch {
      /* ignore — onboarding still usable if API is down */
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void pingApi();
  }, [pingApi]);

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      toast("Agent name is required", "error");
      return;
    }
    setSubmitting(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/agents/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          framework,
          allowed_tools: ["send_email", "read_customer_data"],
          max_risk_tolerance: 0.8,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      const j = (await r.json()) as { api_key: string; name: string };
      setApiKey(j.api_key);
      setRegisteredName(j.name);
      setStep(2);
      toast("Agent registered", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Registration failed", "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function runDemo() {
    setSubmitting(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/demo/seed`, { method: "POST" });
      if (r.ok) {
        clearOfflineDemo();
        toast("Fresh demo loaded — the dashboard now shows only this demo run.", "success");
        router.push("/dashboard");
        router.refresh();
        return;
      }
      seedOfflineDemo();
      toast(
        "Loaded sample data in your browser (no Agentiva API). Charts and audit match this demo; connect `agentiva serve` for a live API.",
        "success",
      );
      router.push("/dashboard");
      router.refresh();
    } catch {
      seedOfflineDemo();
      toast(
        "Loaded sample data in your browser (no Agentiva API). Connect the API locally for a full live demo.",
        "success",
      );
      router.push("/dashboard");
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  function copyKey() {
    if (!apiKey) return;
    void navigator.clipboard.writeText(apiKey);
    toast("API key copied", "success");
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#080604] text-[#f8fafc]">
        <Loader2 className="h-10 w-10 animate-spin text-[#eab308]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#080604] px-4 py-12 text-[#f8fafc]">
      <div className="mx-auto max-w-2xl">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#eab308] to-amber-700">
            <Shield className="h-7 w-7 text-white" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b]">Welcome to Agentiva</p>
            <h1 className="text-2xl font-bold tracking-tight">Preview deployments for AI agents</h1>
          </div>
        </div>

        <div className="mb-8 flex flex-wrap gap-2 text-sm text-[#64748b]">
          {[1, 2, 3].map((s) => (
            <span
              key={s}
              className={`rounded-full px-3 py-1 ${step >= s ? "bg-[#eab308]/20 text-[#fde68a]" : "bg-[#14110a]"}`}
            >
              Step {s}
            </span>
          ))}
          <span className="rounded-full bg-[#14110a] px-3 py-1">Demo</span>
        </div>

        {step === 1 && (
          <section className="rounded-2xl border border-white/10 bg-[#14110a]/80 p-6 backdrop-blur">
            <h2 className="text-lg font-semibold">Register your first agent</h2>
            <p className="mt-1 text-sm text-[#64748b]">You’ll get an API key to use in your code.</p>
            <form onSubmit={onRegister} className="mt-6 space-y-4">
              <div>
                <label className="text-sm font-medium text-[#94a3b8]">Agent name *</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-[#080604] px-3 py-2.5 text-[#f8fafc] outline-none ring-[#eab308] focus:ring-2"
                  placeholder="e.g. Support copilot"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-[#94a3b8]">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-[#080604] px-3 py-2.5 text-[#f8fafc] outline-none focus:ring-2 focus:ring-[#eab308]"
                  placeholder="What does this agent do?"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-[#94a3b8]">Your stack</label>
                <p id="stack-hint" className="mt-0.5 text-xs text-[#64748b]">
                  Optional label for docs and examples — Agentiva wraps tools the same way regardless.
                </p>
                <select
                  value={framework}
                  onChange={(e) => setFramework(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-[#080604] px-3 py-2.5 text-[#f8fafc] outline-none focus:ring-2 focus:ring-[#eab308]"
                  aria-describedby="stack-hint"
                >
                  {FRAMEWORKS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-xl bg-[#eab308] py-3 font-semibold text-white transition hover:bg-[#ca8a04] disabled:opacity-50"
              >
                {submitting ? "Creating…" : "Create agent & generate API key"}
              </button>
            </form>
          </section>
        )}

        {step === 2 && apiKey && (
          <section className="space-y-6">
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5">
              <h2 className="font-semibold text-amber-100">Your API key</h2>
              <p className="mt-1 text-sm text-amber-200/80">Save this key — you won’t see it again.</p>
              <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl bg-[#080604] px-4 py-3 font-mono text-sm text-[#f8fafc]">
                <span className="break-all">{apiKey}</span>
                <button
                  type="button"
                  onClick={copyKey}
                  className="ml-auto flex shrink-0 items-center gap-1 rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium hover:bg-white/20"
                >
                  <Copy className="h-3.5 w-3.5" /> Copy
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#14110a]/80 p-6">
              <h3 className="font-semibold">Add Agentiva to your code</h3>
              <p className="mt-1 text-sm text-[#64748b]">With your API key:</p>
              <pre className="mt-3 overflow-x-auto rounded-xl bg-[#080604] p-4 text-left text-xs leading-relaxed text-[#94a3b8]">
                {`from agentiva import Agentiva

shield = Agentiva(api_key="${apiKey}", mode="shadow")
tools = shield.protect([your_existing_tools])`}
              </pre>
              <p className="mt-4 text-sm text-[#64748b]">Or use without an API key for local development:</p>
              <pre className="mt-3 overflow-x-auto rounded-xl bg-[#080604] p-4 text-left text-xs leading-relaxed text-[#94a3b8]">
                {`from agentiva import Agentiva

shield = Agentiva(mode="shadow")
tools = shield.protect([your_existing_tools])`}
              </pre>
              <button
                type="button"
                onClick={() => setStep(3)}
                className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-[#eab308] py-3 font-semibold text-white hover:bg-[#ca8a04]"
              >
                Next <Check className="h-4 w-4" />
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="rounded-2xl border border-white/10 bg-[#14110a]/80 p-8 text-center">
            <h2 className="text-xl font-semibold">Start your agent</h2>
            <p className="mt-2 text-sm text-[#64748b]">
              When <span className="font-medium text-[#94a3b8]">{registeredName || name}</span> sends its first action,
              you’ll see it on the Overview.
            </p>
            <button
              type="button"
              onClick={() => router.push("/dashboard")}
              className="mt-8 w-full rounded-xl bg-emerald-600 py-3 font-semibold text-white hover:bg-emerald-500"
            >
              I’ve added the code — show me the dashboard
            </button>
          </section>
        )}

        <div className="mt-10 rounded-2xl border border-dashed border-white/15 bg-[#14110a]/40 p-6 text-center">
          <p className="text-sm font-medium text-[#94a3b8]">Or try the demo first</p>
          <p className="mt-1 text-xs text-[#64748b]">
            Clears existing audit data, then loads a fresh demo so the dashboard matches only this run.
          </p>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void runDemo()}
            className="mt-4 rounded-xl border border-[#eab308]/50 bg-[#eab308]/15 px-6 py-2.5 text-sm font-semibold text-[#fde68a] transition hover:bg-[#eab308]/25 disabled:opacity-50"
          >
            Run demo with sample data
          </button>
        </div>

        <p className="mt-10 text-center text-sm text-[#64748b]">
          <Link href="/marketing" className="text-[#eab308] hover:underline">
            Marketing site
          </Link>
          {" · "}
          <a
            href="https://github.com/RishavAr/agentiva/blob/main/README.md"
            target="_blank"
            rel="noreferrer"
            className="text-[#eab308] hover:underline"
          >
            Read the docs
          </a>
        </p>
      </div>
    </div>
  );
}
