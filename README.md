# AgentShield 🛡️

**Preview deployments for AI agents.**

[![Tests](https://img.shields.io/badge/tests-24%2C000%2B%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()
[![pip](https://img.shields.io/badge/pip%20install-agentshield-orange)]()

> 88% of companies had AI agent security incidents in 2025. Amazon's Kiro agent caused a 13-hour AWS outage. A Replit agent deleted 1,206 customer records. Microsoft Copilot was exploited via zero-click exfiltration.
>
> **AgentShield stops this.** See what your AI agent would do before it does it.

🌐 [Website](https://website-delta-black-67.vercel.app) · 📖 [Docs](#quick-start) · 💬 [Discord](#) · 🐦 [Twitter](https://twitter.com/RishavAr)

---

## 4 Lines to Protect Any Agent

```python
from agentshield import AgentShield

shield = AgentShield(mode="shadow")
tools = shield.protect([your_gmail_tool, your_slack_tool, your_jira_tool])

# Your agent runs normally. AgentShield intercepts every action.
# Nothing executes in shadow mode. Everything is logged.
print(shield.get_shadow_report())
```

---

## What AgentShield Catches

We ran 100 real-world scenarios. AgentShield caught every dangerous action:

```
🛑 BLOCKED  send_email → investor@externalfund.com (confidential financials)     risk: 0.90
🛑 BLOCKED  database   → DROP TABLE users; DELETE FROM transactions              risk: 0.95
🛑 BLOCKED  api_call   → suspicious-api.darkweb.com/exfiltrate                   risk: 0.99
🛑 BLOCKED  delete     → bulk_all_inactive user accounts                         risk: 0.90
🛑 BLOCKED  transfer   → $500K to unknown_offshore_789                           risk: 0.95
🛑 BLOCKED  shell      → rm -rf / (destructive command)                          risk: 0.98
🛑 BLOCKED  shell      → nmap scan + exploit script                              risk: 0.99
🛑 BLOCKED  permission → grant admin to AI agent itself                          risk: 0.95
👁️ SHADOW   send_email → team@yourcompany.com (internal, safe)                   risk: 0.10
👁️ SHADOW   slack      → #deployments (routine update)                           risk: 0.30
👁️ SHADOW   jira       → create bug ticket (low risk)                            risk: 0.20
✅ ALLOW    jira       → security vulnerability report                           risk: 0.10

Summary: 100 actions | 47 blocked | 21 shadowed | 32 allowed | 0 false positives
```

---

## Five Operating Modes

| Mode | What It Does |
|------|-------------|
| 👁️ **Shadow** | Observe without executing. See everything the agent *would* do. |
| 🔮 **Simulation** | Preview a diff of what would change before any action runs. |
| ✋ **Approval** | High-risk actions pause for human review via dashboard or Slack. |
| 💬 **Negotiation** | Agent gets feedback on *why* it was blocked + suggestions to self-correct. |
| ↩️ **Rollback** | Undo what the agent did. Revert tickets, restore data, revoke tokens. |

---

## Live Dashboard

AgentShield comes with a real-time dashboard for monitoring, approving, and auditing agent actions.

**Pages:**
- **Overview** — Total intercepted, blocked, shadowed, allowed with live counters
- **Live Feed** — Real-time WebSocket stream of every agent action, color-coded by risk
- **Audit Log** — Searchable, filterable history with pagination and CSV export
- **Agents** — Registry of all agents with reputation scores and kill switch
- **Policies** — YAML policy editor with live testing
- **AI Chat** — Ask AgentShield questions: "Why was that email blocked?" "Which agent is riskiest?"

[Screenshot placeholders - add your dashboard screenshots here]

---

## AI-Powered Chat Co-pilot

Talk to AgentShield. Ask questions about your agents' behavior.

```
You: "Why were actions blocked?"

AgentShield: "47 actions were blocked in this session. The top reasons:
1. External email recipients (12 blocks, avg risk 0.90)
2. Destructive database operations (8 blocks, avg risk 0.95)
3. Suspicious API endpoints (6 blocks, avg risk 0.97)

The riskiest action was a call to suspicious-api.darkweb.com with
risk score 0.99, attempted by demo-agent-v1.

Follow-up questions:
- Which agent is causing the most blocks?
- Show me the timeline of incidents
- Recommendations to improve security"
```

Basic mode works without any API key. Add `OPENROUTER_API_KEY` for Claude-powered deep analysis.

---

## Smart Risk Scoring

AgentShield scores every action using 8 signals:

| Signal | What It Detects |
|--------|----------------|
| **Tool Sensitivity** | email (0.7) > database (0.6) > slack (0.4) > jira (0.3) |
| **Recipient Analysis** | external (+0.3), broadcast (+0.2), internal (+0.0) |
| **Content Analysis** | destructive keywords (+0.4), sensitive data (+0.3) |
| **Pattern Detection** | bulk operations (+0.3), rapid fire (+0.2) |
| **Time Analysis** | after hours (+0.1), weekends (+0.15) |
| **Agent Reputation** | new agents get stricter scoring automatically |
| **Frequency** | abnormal request rates flagged |
| **Data Sensitivity** | PII (+0.3), financial (+0.4), credentials (+0.5) |

All deterministic. No LLM needed for scoring. Configurable weights via YAML.

---

## Agent Negotiation Protocol

When AgentShield blocks an action, it doesn't just say "no." It explains why and suggests alternatives:

```python
# Agent tries to email external recipient
result = await shield.intercept("send_email", {"to": "external@company.com", "body": "Q3 financials"})

# AgentShield responds:
# BLOCKED: External recipient detected (external@company.com)
# Policy: block_external_email (risk: 0.9)
# Risk factors: external_recipient (high), sensitive content 'financials' (medium)
# Suggestions:
#   1. Route through manager@yourcompany.com instead
#   2. Request human approval via /api/v1/request-approval
# Proposed safe version: {to: "manager@yourcompany.com", cc: "external@company.com"}
```

The agent can modify its action and retry. This creates a learning loop where agents improve over time.

---

## Works With Every Framework

```python
# LangChain
from agentshield import AgentShield
shield = AgentShield(mode="shadow")
tools = shield.protect(langchain_tools)

# CrewAI
crew = shield.protect_crewai(my_crew)

# OpenAI Agents SDK
functions = shield.protect_openai(my_functions)

# MCP Protocol
shield.start_mcp_proxy(upstream="localhost:3001", port=3002)

# Any custom tool
@shield.intercept("my_tool")
def handler(action):
    return action
```

---

## YAML Policy Engine

Write human-readable security rules:

```yaml
version: 1
default_mode: shadow

rules:
  - name: block_external_email
    tool: send_email
    condition:
      field: arguments.to
      operator: not_contains
      value: "@yourcompany.com"
    action: block
    risk_score: 0.9

  - name: block_destructive_sql
    tool: database_*
    condition:
      field: arguments.query
      operator: contains
      value: "DROP"
    action: block
    risk_score: 0.95

  - name: approve_large_transfers
    tool: transfer_funds
    condition:
      field: arguments.amount
      operator: contains
      value: "10000"
    action: approve
    risk_score: 0.8
```

**Industry templates included:**
- 🏥 Healthcare (HIPAA)
- 💰 Finance (PCI-DSS)
- 🛒 E-commerce
- ☁️ SaaS
- ⚖️ Legal

---

## Quick Start

### Option 1: pip install

```bash
pip install agentshield
agentshield serve --port 8000
```

### Option 2: From source

```bash
git clone https://github.com/RishavAr/agentshield.git
cd agentshield
python -m venv venv && source venv/bin/activate
pip install -e .
agentshield serve
```

### Option 3: Docker

```bash
docker compose up
```

### Start the dashboard

```bash
cd dashboard
npm install
npm run dev
# Open http://localhost:3000
```

### Run the live demo

```bash
python examples/live_demo.py
# Watch 100 scenarios run with real-time interception
```

---

## Architecture

```
┌───────────────────┐
│  AI Agent          │  (LangChain, CrewAI, OpenAI, MCP, custom)
└────────┬──────────┘
         │ tool_call
         ▼
┌──────────────────────────────────────────────┐
│              AGENTSHIELD RUNTIME              │
├──────────────────────────────────────────────┤
│  Interceptor → Policy Engine → Risk Scorer   │
│       │              │              │         │
│       ▼              ▼              ▼         │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐   │
│  │ Audit   │  │ Decision │  │ Negotiator│   │
│  │ Logger  │  │ Engine   │  │           │   │
│  └─────────┘  └──────────┘  └───────────┘   │
│       │         │       │         │          │
│  ┌────┴───┐ ┌──┴───┐ ┌─┴────┐ ┌──┴──────┐  │
│  │Rollback│ │Shadow│ │Approve│ │Simulate │  │
│  └────────┘ └──────┘ └──────┘ └─────────┘  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
         ┌───────────────────────┐
         │  Actual Tool/API      │  (Gmail, Slack, Jira, DB, etc.)
         └───────────────────────┘
```

---

## Compliance Ready

AgentShield generates compliance-ready exports:

- **SOC2** — Full audit trail with evidence of human-in-the-loop controls
- **GDPR** — Data subject access logs (Article 15)
- **EU AI Act** — Transparency reports, risk classification, human oversight documentation
- **CSV/JSON** — Export to any SIEM (Splunk, Datadog, ELK)

```bash
# Export SOC2 report
curl http://localhost:8000/api/v1/compliance/soc2?start=2026-01-01&end=2026-03-19

# Export GDPR data access log
curl http://localhost:8000/api/v1/compliance/gdpr/customer_12345
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check + stats |
| `/api/v1/intercept` | POST | Intercept an agent action |
| `/api/v1/audit` | GET | Query audit log with filters |
| `/api/v1/report` | GET | Shadow mode summary report |
| `/api/v1/chat` | POST | Chat with AgentShield AI co-pilot |
| `/api/v1/mode/{mode}` | POST | Switch operating mode |
| `/api/v1/approve` | POST | Approve/deny pending action |
| `/api/v1/negotiate/{id}` | POST | Get negotiation guidance |
| `/api/v1/retry/{id}` | POST | Retry blocked action with changes |
| `/api/v1/agents` | GET | List registered agents |
| `/api/v1/compliance/soc2` | GET | SOC2 compliance export |
| `/ws/actions` | WebSocket | Real-time action stream |

Full OpenAPI docs at `http://localhost:8000/docs`

---

## Testing

```bash
# Run all 24,000+ tests
python -m pytest tests/ -v

# Run specific test category
python -m pytest tests/test_param_attack_vectors.py -v  # Attack vectors
python -m pytest tests/test_param_real_incidents.py -v   # Real-world incidents
python -m pytest tests/test_param_industry_compliance.py -v  # Industry compliance
python -m pytest tests/test_edge_cases.py -v             # Edge cases
```

Test coverage includes:
- 64+ real-world attack vectors (prompt injection, privilege escalation, data exfiltration)
- 10 real AI agent incidents (Amazon Kiro, Copilot zero-click, Replit deletion)
- 5 industry compliance suites (Healthcare, Finance, E-commerce, SaaS, Legal)
- Concurrent stress tests (1000 simultaneous agents)
- Fuzzing with 500+ malformed inputs
- Policy permutation tests across 30+ tool types

---

## Roadmap

- [x] Core interceptor engine
- [x] LangChain integration
- [x] CrewAI integration
- [x] OpenAI Agents SDK integration
- [x] MCP protocol proxy
- [x] YAML policy engine
- [x] Smart risk scoring (8 signals)
- [x] Agent negotiation protocol
- [x] Simulation engine (dry-run diffs)
- [x] Rollback engine
- [x] Real-time dashboard
- [x] AI chat co-pilot
- [x] Agent registry + reputation
- [x] Compliance exports (SOC2, GDPR, EU AI Act)
- [x] 24,000+ tests
- [ ] Slack/Teams approval integration
- [ ] PagerDuty/Datadog alerting
- [ ] Kubernetes operator
- [ ] Agent behavior analytics ML
- [ ] Policy marketplace (community-shared rules)

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

Apache 2.0 — See [LICENSE](LICENSE)

---

## Built by

**[Rishav Aryan](https://rishavar.github.io)** — ML Engineer, George Mason University

🌐 [Website](https://website-delta-black-67.vercel.app) · 🐦 [Twitter](https://twitter.com/RishavAr) · 💼 [LinkedIn](https://linkedin.com/in/rishav-aryan) · 🐙 [GitHub](https://github.com/RishavAr)

---

<p align="center">
  <b>If you're deploying AI agents, star this repo. ⭐</b><br>
  <i>Your agents are only as safe as the system watching them.</i>
</p>
