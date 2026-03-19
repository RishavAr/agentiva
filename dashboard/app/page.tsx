"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, Eye, MessageSquareText, PlayCircle, Undo2 } from "lucide-react";

const CODE_SAMPLE = `from agentshield import AgentShield
shield = AgentShield(mode="shadow")
tools = shield.protect([your_tools])
print(shield.get_audit_log())`;

const modeCards = [
  { title: "Shadow Mode", icon: Eye, description: "Observe without executing" },
  { title: "Simulation", icon: PlayCircle, description: "Preview impact before acting" },
  { title: "Approval", icon: CheckCircle2, description: "Human-in-the-loop for risky actions" },
  { title: "Negotiation", icon: MessageSquareText, description: "Agent gets feedback to self-correct" },
  { title: "Rollback", icon: Undo2, description: "Undo what the agent did" },
];

export default function LandingPage() {
  const [typed, setTyped] = useState("");

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

  return (
    <div className="scroll-smooth bg-[#0a0a0a] text-[#e5e7eb]">
      <section className="mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-6 py-24">
        <div className="mb-6 flex flex-wrap gap-2">
          <span className="rounded-full border border-[#2f2f2f] bg-[#111827] px-3 py-1 text-xs text-[#93c5fd]">
            10,000+ tests passing
          </span>
          <span className="rounded-full border border-[#2f2f2f] bg-[#111827] px-3 py-1 text-xs text-[#a7f3d0]">
            Apache 2.0
          </span>
        </div>
        <h1 className="text-5xl font-semibold tracking-tight text-white md:text-7xl">AgentShield</h1>
        <p className="mt-4 text-xl text-[#93c5fd] md:text-2xl">Preview deployments for AI agents</p>
        <p className="mt-5 max-w-3xl text-lg text-[#9ca3af]">
          See what your AI agent would do before it does it. Shadow mode. Simulation. Approval.
          Rollback. Open-source.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/dashboard"
            className="rounded-md bg-[#3b82f6] px-5 py-3 font-medium text-white transition hover:bg-[#2563eb]"
          >
            Get Started — pip install agentshield
          </Link>
          <a
            href="https://github.com/RishavAr/agentshield"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-[#374151] bg-[#111827] px-5 py-3 font-medium text-[#d1d5db] transition hover:bg-[#1f2937]"
          >
            View on GitHub
          </a>
        </div>

        <div className="mt-10 rounded-xl border border-[#2a2a2a] bg-[#0d1117] p-4">
          <p className="mb-3 text-xs uppercase tracking-widest text-[#6b7280]">Terminal</p>
          <pre className="min-h-[120px] whitespace-pre-wrap font-mono text-sm text-[#d1d5db]">{typed}</pre>
        </div>
      </section>

      <section id="problem" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">AI agents are breaking things in production</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[
            ["88%", "of companies had AI agent security incidents"],
            ["48%", "of security pros rank agentic AI as #1 attack vector"],
            ["$1M+", "average cost of AI agent failures (EY 2026)"],
          ].map(([stat, label]) => (
            <div key={stat} className="rounded-xl border border-[#2a2a2a] bg-[#0d1117] p-5">
              <p className="text-4xl font-semibold text-[#3b82f6]">{stat}</p>
              <p className="mt-2 text-sm text-[#9ca3af]">{label}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {[
            "Amazon Kiro outage (13h production downtime)",
            "Replit record deletion (1,206 customer records)",
            "Copilot zero-click exfiltration (SharePoint leak)",
          ].map((incident) => (
            <div key={incident} className="rounded-xl border border-[#2a2a2a] bg-[#111827] p-4 text-sm text-[#d1d5db]">
              {incident}
            </div>
          ))}
        </div>
      </section>

      <section id="how" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Four lines to protect any agent</h2>
        <div className="mt-8 rounded-xl border border-[#2a2a2a] bg-[#0d1117] p-5">
          <pre className="overflow-x-auto font-mono text-sm text-[#d1d5db]">{CODE_SAMPLE}</pre>
        </div>
        <div className="mt-8 rounded-xl border border-[#2a2a2a] bg-[#111827] p-5 font-mono text-xs text-[#d1d5db] md:text-sm">
          Agent --&gt; AgentShield --&gt; Policy Check --&gt; Decision (Allow/Shadow/Block/Approve) --&gt;
          Action or Log
        </div>
      </section>

      <section id="modes" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Five operating modes</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-5">
          {modeCards.map((mode) => (
            <div key={mode.title} className="rounded-xl border border-[#2a2a2a] bg-[#0d1117] p-4">
              <mode.icon className="h-5 w-5 text-[#60a5fa]" />
              <p className="mt-3 font-medium text-white">{mode.title}</p>
              <p className="mt-1 text-sm text-[#9ca3af]">{mode.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="demo" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Watch AgentShield in action</h2>
        <div className="mt-8 rounded-xl border border-[#2a2a2a] bg-[#0d1117] p-6">
          <div className="rounded-lg border border-dashed border-[#334155] bg-[#111827] p-10 text-center text-[#9ca3af]">
            Dashboard screenshot/iframe placeholder: 12 actions, 5 blocked, 7 shadowed
          </div>
        </div>
      </section>

      <section id="integrations" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Works with every agent framework</h2>
        <div className="mt-8 grid grid-cols-2 gap-3 text-sm text-[#d1d5db] md:grid-cols-7">
          {["LangChain", "CrewAI", "OpenAI Agents SDK", "Anthropic", "MCP Protocol", "AutoGen", "MetaGPT"].map(
            (item) => (
              <div key={item} className="rounded-lg border border-[#2a2a2a] bg-[#0d1117] p-3 text-center">
                {item}
              </div>
            )
          )}
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          {["Healthcare (HIPAA)", "Finance (PCI-DSS)", "E-commerce", "SaaS", "Legal"].map((tag) => (
            <span key={tag} className="rounded-full border border-[#2a2a2a] bg-[#111827] px-3 py-1 text-xs text-[#93c5fd]">
              {tag}
            </span>
          ))}
        </div>
      </section>

      <section id="trust" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-semibold text-white md:text-4xl">Built for production</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-4">
          {[
            "10,000+ tests",
            "64 attack vectors covered",
            "SOC2/GDPR/EU AI Act compliance exports",
            "Open-source (Apache 2.0)",
          ].map((item) => (
            <div key={item} className="rounded-xl border border-[#2a2a2a] bg-[#0d1117] p-4">
              <p className="text-sm text-[#d1d5db]">{item}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-[#1f2937] px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 text-sm text-[#9ca3af] md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-4">
            <a href="https://github.com/RishavAr/agentshield" target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
            <a href="https://twitter.com" target="_blank" rel="noopener noreferrer">
              Twitter
            </a>
            <span className="font-mono text-[#93c5fd]">pip install agentshield</span>
          </div>
          <a href="https://rishavaryan.dev" target="_blank" rel="noopener noreferrer" className="text-[#d1d5db]">
            Built by Rishav Aryan
          </a>
        </div>
      </footer>
    </div>
  );
}
