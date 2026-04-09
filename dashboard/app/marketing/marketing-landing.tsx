"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CirclePlay,
  Eye,
  MessageSquareText,
  Shield,
  Sparkles,
  Undo2,
} from "lucide-react";

const CALENDLY_DEMO_URL = "https://calendly.com/rishavaryan058/30min";

const CODE_SAMPLE = `from agentiva import Agentiva
shield = Agentiva(mode="shadow")
tools = shield.protect([your_tools])
print(shield.get_audit_log())`;

const modeCards = [
  { title: "Shadow Mode", icon: Eye, description: "Observe without executing" },
  { title: "Simulation", icon: CirclePlay, description: "Preview impact before acting" },
  { title: "Approval", icon: CheckCircle2, description: "Human-in-the-loop for risky actions" },
  { title: "Negotiation", icon: MessageSquareText, description: "Agent gets feedback to self-correct" },
  { title: "Rollback", icon: Undo2, description: "Undo what the agent did" },
];

const NAV_LINKS = [
  { href: "#product", label: "Product" },
  { href: "#modes", label: "Modes" },
  { href: "#proof", label: "Proof" },
  { href: "#pricing", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
] as const;

function useScrollY(): number {
  return useSyncExternalStore(
    (onStoreChange) => {
      if (typeof window === "undefined") {
        return () => {};
      }
      const handler = () => onStoreChange();
      window.addEventListener("scroll", handler, { passive: true });
      return () => window.removeEventListener("scroll", handler);
    },
    () => (typeof window !== "undefined" ? window.scrollY : 0),
    () => 0
  );
}

const faq = [
  {
    q: "What is Agentiva?",
    a: "Agentiva is the preview deployment system for AI agents. It intercepts every agent action before execution, scores the risk, and decides whether to allow, shadow, or block it.",
  },
  {
    q: "Is it free?",
    a: "Yes. The open-source core is free forever. Paid tiers add hosted dashboard, compliance exports, and team features.",
  },
  {
    q: "Will this slow down my agents?",
    a: "Risk scoring runs in milliseconds using deterministic rules - no LLM call needed. Shadow mode adds zero latency since actions aren't executed.",
  },
  {
    q: "Can I use this with LangChain/CrewAI/OpenAI?",
    a: "Yes. Agentiva is framework-agnostic: you wrap your tools the same way regardless of stack. We document integrations for LangChain, CrewAI, OpenAI Agents SDK, MCP, and custom agents via REST.",
  },
  {
    q: "Do I need cloud access?",
    a: "No. Agentiva runs entirely on your machine. No data leaves your infrastructure unless you opt into the cloud dashboard.",
  },
  {
    q: "How is this different from Okta/Salus/Alter?",
    a: "Okta handles agent identity. Salus and Alter are closed-source blockers. Agentiva is open-source with shadow mode, agent negotiation, and an AI co-pilot - the full lifecycle, not just block/allow.",
  },
];

export default function MarketingLanding() {
  const [typed, setTyped] = useState("");
  const [activeFaq, setActiveFaq] = useState(0);
  const scrollY = useScrollY();
  const [activeShot, setActiveShot] = useState(0);

  const shots = [
    {
      title: "Live policy decisions",
      subtitle: "Watch allow / shadow / block in real time",
      tint: "from-amber-500/30 to-yellow-800/20",
    },
    {
      title: "Approval workflow",
      subtitle: "Review high-risk actions before execution",
      tint: "from-emerald-500/30 to-amber-700/20",
    },
    {
      title: "Compliance exports",
      subtitle: "Generate SOC2, HIPAA, and PCI evidence",
      tint: "from-amber-600/35 to-yellow-900/25",
    },
  ];

  useEffect(() => {
    let idx = 0;
    const timer = setInterval(() => {
      idx += 1;
      setTyped(CODE_SAMPLE.slice(0, idx));
      if (idx >= CODE_SAMPLE.length) {
        clearInterval(timer);
      }
    }, 18);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveShot((prev) => (prev + 1) % shots.length);
    }, 2600);
    return () => clearInterval(timer);
  }, [shots.length]);

  useEffect(() => {
    const nodes = document.querySelectorAll<HTMLElement>("[data-reveal]");
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.16 }
    );
    nodes.forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, []);

  return (
    <div className="scroll-smooth bg-[#080604] text-[#e5e7eb]">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top,rgba(234,179,8,0.18),transparent_55%)]" />

      <header className="sticky top-0 z-40 border-b border-white/5 bg-[#080604]/80 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Shield className="h-4 w-4 text-[#fcd34d]" />
            Agentiva
          </div>
          <nav className="hidden items-center gap-6 text-xs text-[#94a3b8] md:flex">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-white">
                {link.label}
              </a>
            ))}
          </nav>
          <a
            href={CALENDLY_DEMO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-full border border-[#eab308]/40 bg-[#a16207]/20 px-4 py-2 text-xs font-semibold text-[#fef3c7] hover:bg-[#a16207]/30"
          >
            Book a demo
          </a>
        </div>
      </header>

      <section className="mx-auto grid min-h-[82vh] max-w-6xl items-center gap-10 px-6 py-20 md:grid-cols-2">
        <div data-reveal className="reveal-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-[#fef3c7]">
            <Sparkles className="h-3.5 w-3.5" /> Backed by 10,000+ security tests
          </span>
          <h1 className="mt-6 text-5xl font-semibold tracking-tight text-white md:text-6xl">
            Everything agents do,
            <br />
            <span className="bg-gradient-to-r from-[#fde047] to-[#f59e0b] bg-clip-text text-transparent">
              now under control.
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-lg text-[#94a3b8]">
            Agentiva brings the clarity of a modern product dashboard to AI agent security:
            observe, simulate, approve, rollback, and export compliance evidence.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-semibold text-[#0f172a]">
              Start onboarding <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href={CALENDLY_DEMO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full border border-[#eab308]/40 bg-[#a16207]/20 px-5 py-3 text-sm font-semibold text-[#fef3c7] hover:bg-[#a16207]/30"
            >
              Book a demo
            </a>
            <Link href="/dashboard" className="rounded-full border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">
              Open dashboard
            </Link>
          </div>
        </div>
        <div
          data-reveal
          className="reveal-up rounded-3xl border border-white/10 bg-gradient-to-b from-[#1a1610] to-[#0c0a06] p-5 shadow-2xl shadow-black/40 transition-transform duration-300"
          style={{ transform: `translateY(${Math.min(scrollY * 0.05, 20)}px)` }}
        >
          <div className="rounded-2xl border border-white/10 bg-[#080604] p-4">
            <p className="mb-3 text-[10px] uppercase tracking-[0.22em] text-[#64748b]">Live command preview</p>
            <pre className="min-h-[160px] whitespace-pre-wrap font-mono text-sm text-[#d1d5db]">{typed}</pre>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {[
              ["12", "Actions intercepted"],
              ["5", "Blocked before execution"],
              ["7", "Shadowed for review"],
            ].map(([n, label]) => (
              <div key={label} className="rounded-xl border border-white/10 bg-white/5 p-3 text-center">
                <p className="text-xl font-semibold text-white">{n}</p>
                <p className="text-xs text-[#94a3b8]">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="product" className="mx-auto max-w-6xl px-6 py-14">
        <div className="mb-6">
          <h2 data-reveal className="reveal-up text-3xl font-semibold text-white md:text-4xl">A product experience, not just a policy engine</h2>
          <p className="mt-2 text-[#94a3b8]">
            The flow is designed to feel modern and visual: cards, progressive sections, and clear narrative from risk to action.
          </p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Visual feed</p>
            <p className="mt-2 text-sm text-[#94a3b8]">See high-risk activity in real time, with decision context and mode status.</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Contextual chat co-pilot</p>
            <p className="mt-2 text-sm text-[#94a3b8]">Ask naturally: “what was blocked?” then follow with “why?” and get grounded answers.</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Auditor-ready exports</p>
            <p className="mt-2 text-sm text-[#94a3b8]">Generate SOC2, HIPAA, and PCI reports with clear evidence and traceability.</p>
          </div>
        </div>
      </section>

      <section id="showcase" className="mx-auto max-w-6xl px-6 py-16">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-3xl font-semibold text-white md:text-4xl">See the workflow end-to-end</h2>
            <p className="mt-2 text-[#94a3b8]">
              From incoming tool calls to safe execution, every step is visual, auditable, and fast.
            </p>
          </div>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-[#cbd5e1]">
            3-step product loop
          </span>
        </div>
        <div className="grid gap-5 lg:grid-cols-3">
          <article className="rounded-2xl border border-white/10 bg-gradient-to-b from-[#1a1610] to-[#12100a] p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-[#64748b]">Step 1</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Capture & score</h3>
            <p className="mt-2 text-sm text-[#94a3b8]">
              Agentiva intercepts each tool call and runs multi-signal scoring before side effects happen.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-[#0e0c08] p-3">
              <p className="text-xs text-[#cbd5e1]">send_email → external recipient</p>
              <p className="mt-2 text-xs font-semibold text-red-300">Risk 1.00 · BLOCK</p>
            </div>
          </article>
          <article className="rounded-2xl border border-white/10 bg-gradient-to-b from-[#1a1610] to-[#12100a] p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-[#64748b]">Step 2</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Decide by mode</h3>
            <p className="mt-2 text-sm text-[#94a3b8]">
              Shadow for observation, Live for automatic blocking, or Approval for human-in-the-loop review.
            </p>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[11px]">
              <span className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-2 text-amber-200">Shadow</span>
              <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-2 text-emerald-200">Live</span>
              <span className="rounded-lg border border-amber-500/35 bg-amber-500/10 px-2 py-2 text-amber-200">Approval</span>
            </div>
          </article>
          <article className="rounded-2xl border border-white/10 bg-gradient-to-b from-[#1a1610] to-[#12100a] p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-[#64748b]">Step 3</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Audit & improve</h3>
            <p className="mt-2 text-sm text-[#94a3b8]">
              Chat with co-pilot, inspect incidents, and export SOC2/HIPAA/PCI evidence instantly.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-[#0e0c08] p-3 text-xs text-[#cbd5e1]">
              “Why was that blocked?” → contextual analyst response
            </div>
          </article>
        </div>

        <div data-reveal className="reveal-up mt-10 rounded-3xl border border-white/10 bg-[#0e0c08] p-5">
          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[#080604] p-4">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.2em] text-[#64748b]">Product Showcase</p>
              <div className="flex items-center gap-1.5">
                {shots.map((_, i) => (
                  <span
                    key={i}
                    className={`h-1.5 rounded-full transition-all ${i === activeShot ? "w-6 bg-[#fde68a]" : "w-2 bg-white/30"}`}
                  />
                ))}
              </div>
            </div>

            <div className="relative h-[280px] overflow-hidden rounded-xl md:h-[340px]">
              <div
                className="flex h-full transition-transform duration-700 ease-out"
                style={{ transform: `translateX(-${activeShot * 100}%)` }}
              >
                {shots.map((shot) => (
                  <div key={shot.title} className="h-full min-w-full p-2">
                    <div
                      className={`h-full rounded-2xl border border-white/10 bg-gradient-to-br ${shot.tint} p-4`}
                    >
                      <div className="h-full rounded-xl border border-white/10 bg-[#0a1020]/85 p-4">
                        <div className="mb-3 flex items-center justify-between">
                          <div>
                            <p className="text-sm font-semibold text-white">{shot.title}</p>
                            <p className="text-xs text-[#9fb0c9]">{shot.subtitle}</p>
                          </div>
                          <span className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] text-[#cbd5e1]">
                            demo view
                          </span>
                        </div>
                        <div className="grid h-[calc(100%-44px)] gap-3 md:grid-cols-[240px_1fr]">
                          <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                            <p className="text-[11px] text-[#9fb0c9]">Agents</p>
                            <div className="mt-2 space-y-2">
                              <div className="rounded border border-white/10 bg-[#0d1324] px-2 py-1 text-xs text-[#fef9c3]">support-bot-v2</div>
                              <div className="rounded border border-white/10 bg-[#0d1324] px-2 py-1 text-xs text-[#fef9c3]">billing-agent</div>
                              <div className="rounded border border-white/10 bg-[#0d1324] px-2 py-1 text-xs text-[#fef9c3]">ops-runner</div>
                            </div>
                          </div>
                          <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                            <p className="text-[11px] text-[#9fb0c9]">Activity timeline</p>
                            <div className="mt-2 space-y-2">
                              <div className="rounded border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs text-red-200">send_email → BLOCK (risk 1.00)</div>
                              <div className="rounded border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">read_customer_data → SHADOW</div>
                              <div className="rounded border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-200">update_ticket → ALLOW</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-4 flex gap-2 overflow-x-auto">
              {shots.map((shot, i) => (
                <button
                  key={shot.title}
                  type="button"
                  onClick={() => setActiveShot(i)}
                  className={`min-w-[180px] rounded-lg border px-3 py-2 text-left text-xs transition ${
                    i === activeShot
                      ? "border-[#fcd34d]/50 bg-[#a16207]/20 text-[#fef9c3]"
                      : "border-white/10 bg-white/5 text-[#94a3b8]"
                  }`}
                >
                  {shot.title}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="modes" className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Five operating modes</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-5">
          {modeCards.map((mode) => (
            <div key={mode.title} className="rounded-2xl border border-white/10 bg-[#0d1324] p-4 hover:bg-[#121a30]">
              <mode.icon className="h-5 w-5 text-[#fde68a]" />
              <p className="mt-3 font-medium text-white">{mode.title}</p>
              <p className="mt-1 text-sm text-[#94a3b8]">{mode.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="proof" className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">
          TESTED AGAINST REAL-WORLD INCIDENTS
        </h2>
        <ul className="mt-8 grid gap-4 md:grid-cols-2">
          {[
            "Amazon Kiro — 13-hour AWS outage scenario",
            "Microsoft Copilot — zero-click exfiltration scenario",
            "Replit Agent — 1,206 record deletion scenario",
            "24,000+ automated security tests passing",
          ].map((line) => (
            <li
              key={line}
              className="list-none rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[#dbe3ef]"
            >
              • {line}
            </li>
          ))}
        </ul>
      </section>

      <section id="pricing" className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Pricing</h2>
        <p className="mt-2 max-w-3xl text-[#94a3b8]">
          Open core: scan + one agent free, self-hosted. Cloud Pro and Team are on the waitlist—same product, managed for you.
        </p>
        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <article className="flex flex-col rounded-2xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Free</p>
            <p className="mt-2 text-3xl font-semibold text-white">$0</p>
            <p className="mt-1 text-xs font-medium text-[#fde68a]">/forever · self-hosted</p>
            <ul className="mt-4 flex-1 space-y-2 text-xs text-[#cbd5e1]">
              <li>Project scan (agentiva scan)</li>
              <li>1 agent · policy + local dashboard</li>
              <li>Shadow + live modes</li>
              <li>Security co-pilot (baseline)</li>
              <li>Community support</li>
            </ul>
            <Link
              href="/dashboard"
              className="mt-5 inline-flex w-full items-center justify-center rounded-lg border border-white/15 bg-white/10 px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-white/15"
            >
              Get started free
            </Link>
          </article>
          <article className="relative flex flex-col rounded-2xl border-2 border-[#eab308] bg-gradient-to-b from-[#a16207]/25 to-white/5 p-5 shadow-xl shadow-amber-950/35">
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full border border-[#eab308] bg-[#422006] px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#fef3c7]">
              MOST POPULAR
            </span>
            <p className="text-sm font-semibold text-[#fef3c7]">Pro</p>
            <p className="mt-2 text-3xl font-semibold text-white">$49</p>
            <p className="mt-1 text-xs text-[#94a3b8]">/month · cloud waitlist</p>
            <ul className="mt-4 flex-1 space-y-2 text-xs text-[#fef9c3]">
              <li>Up to 5 agents</li>
              <li>Hosted cloud dashboard</li>
              <li>Email + Slack alerts</li>
              <li>Priority support</li>
            </ul>
            <a
              href="#waitlist"
              className="mt-5 inline-flex w-full items-center justify-center rounded-lg bg-[#ca8a04] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#a16207]"
            >
              Join waitlist
            </a>
          </article>
          <article className="flex flex-col rounded-2xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Team</p>
            <p className="mt-2 text-3xl font-semibold text-white">$149</p>
            <p className="mt-1 text-xs text-[#94a3b8]">/month · cloud waitlist</p>
            <ul className="mt-4 flex-1 space-y-2 text-xs text-[#cbd5e1]">
              <li>Up to 25 agents</li>
              <li>Compliance evidence exports</li>
              <li>SSO + team management</li>
              <li>Everything in Pro</li>
            </ul>
            <a
              href="#waitlist"
              className="mt-5 inline-flex w-full items-center justify-center rounded-lg border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/15"
            >
              Join waitlist
            </a>
          </article>
          <article className="flex flex-col rounded-2xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Enterprise</p>
            <p className="mt-2 text-2xl font-semibold text-white">Custom</p>
            <p className="mt-1 text-xs text-[#94a3b8]">Unlimited scale · SLA</p>
            <ul className="mt-4 flex-1 space-y-2 text-xs text-[#cbd5e1]">
              <li>Unlimited agents</li>
              <li>On-premise or dedicated deployment</li>
              <li>Custom integrations + SLA</li>
              <li>Dedicated support</li>
              <li>Security architecture review</li>
            </ul>
            <a
              href={CALENDLY_DEMO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 inline-flex w-full items-center justify-center rounded-lg border border-[#eab308]/50 bg-[#a16207]/30 px-4 py-2.5 text-sm font-semibold text-[#fef3c7] hover:bg-[#a16207]/40"
            >
              Book a demo
            </a>
          </article>
        </div>
        <p className="mt-6 text-center text-xs text-[#64748b]">
          Free tier is self-hosted forever. Pro and Team cloud pricing shown; join waitlist to get access.
        </p>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-12">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <h3 className="text-2xl font-semibold text-white">See Agentiva in action</h3>
          <p className="mt-2 text-sm text-[#94a3b8]">
            Book a 30-minute demo to see how Agentiva protects your AI agents.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <a
              href={CALENDLY_DEMO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-[#ca8a04] px-4 py-2 text-sm font-semibold text-white hover:bg-[#a16207]"
            >
              Book a demo →
            </a>
            <button
              type="button"
              className="rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10"
            >
              Watch demo video
            </button>
          </div>
        </div>
      </section>

      <section id="waitlist" className="mx-auto max-w-lg px-6 py-16">
        <h2 className="text-center text-2xl font-semibold text-white md:text-3xl">Join the cloud waitlist</h2>
        <p className="mt-2 text-center text-sm text-[#94a3b8]">Pro and Team tiers — we&apos;ll email you when hosted dashboard is ready.</p>
        <form
          action="https://formspree.io/f/maqlwezw"
          method="POST"
          className="mt-6 space-y-4 rounded-2xl border border-white/10 bg-white/5 p-6"
        >
          <div>
            <label htmlFor="mkt-wait-email" className="text-xs font-medium text-[#cbd5e1]">
              Email
            </label>
            <input
              id="mkt-wait-email"
              type="email"
              name="email"
              required
              autoComplete="email"
              placeholder="you@company.com"
              className="mt-1 w-full rounded-lg border border-white/10 bg-[#0d1324] px-3 py-2 text-sm text-white outline-none focus:ring-2 focus:ring-[#eab308]"
            />
          </div>
          <div>
            <label htmlFor="mkt-wait-company" className="text-xs font-medium text-[#cbd5e1]">
              Company <span className="text-[#64748b]">(optional)</span>
            </label>
            <input
              id="mkt-wait-company"
              type="text"
              name="company"
              autoComplete="organization"
              placeholder="Acme Inc."
              className="mt-1 w-full rounded-lg border border-white/10 bg-[#0d1324] px-3 py-2 text-sm text-white outline-none focus:ring-2 focus:ring-[#eab308]"
            />
          </div>
          <div>
            <label htmlFor="mkt-wait-agents" className="text-xs font-medium text-[#cbd5e1]">
              How many AI agents?
            </label>
            <select
              id="mkt-wait-agents"
              name="agents"
              className="mt-1 w-full rounded-lg border border-white/10 bg-[#0d1324] px-3 py-2 text-sm text-white outline-none focus:ring-2 focus:ring-[#eab308]"
              defaultValue=""
            >
              <option value="" disabled>
                Select range
              </option>
              <option value="1-5">1–5</option>
              <option value="5-20">5–20</option>
              <option value="20-100">20–100</option>
              <option value="100+">100+</option>
            </select>
          </div>
          <button
            type="submit"
            className="w-full rounded-lg bg-[#ca8a04] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#a16207]"
          >
            Join waitlist
          </button>
        </form>
      </section>

      <section id="faq" className="mx-auto max-w-4xl px-6 py-16">
        <h2 className="text-center text-3xl font-semibold text-white md:text-4xl">Frequently Asked Questions</h2>
        <div className="mt-8 space-y-3">
          {faq.map((item, idx) => (
            <button
              key={item.q}
              type="button"
              onClick={() => setActiveFaq((v) => (v === idx ? -1 : idx))}
              className="w-full rounded-xl border border-white/10 bg-white/5 p-4 text-left"
            >
              <div className="flex items-center justify-between gap-4">
                <p className="font-medium text-white">{item.q}</p>
                <span className="text-[#fde68a]">{activeFaq === idx ? "−" : "+"}</span>
              </div>
              {activeFaq === idx ? <p className="mt-3 text-sm text-[#94a3b8]">{item.a}</p> : null}
            </button>
          ))}
        </div>
      </section>

      <footer className="border-t border-white/10 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 text-sm text-[#94a3b8] md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <a href="https://github.com/RishavAr/agentiva" target="_blank" rel="noopener noreferrer">GitHub</a>
            <a href="https://twitter.com" target="_blank" rel="noopener noreferrer">Twitter</a>
            <span className="font-mono text-[#fde68a]">pipx install agentiva</span>
          </div>
          <p>Built by Rishav Aryan</p>
        </div>
      </footer>

      <style jsx global>{`
        .reveal-up {
          opacity: 0;
          transform: translateY(22px);
          transition: opacity 560ms ease, transform 560ms ease;
        }
        .reveal-up.is-visible {
          opacity: 1;
          transform: translateY(0);
        }
      `}</style>
    </div>
  );
}
