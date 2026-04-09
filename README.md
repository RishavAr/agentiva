# Agentiva

**Runtime safety for AI agents.** Intercept tool calls, score risk against policy, log everything to an audit trail, and ship with shadow mode before you enforce blocks.

[![Tests](https://img.shields.io/badge/tests-24%2C599%20passing-brightgreen)]()
[![OWASP](https://img.shields.io/badge/OWASP%20LLM%20Top%2010-100%25-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()

**How to use this README**

| Goal | Where to start |
|------|----------------|
| Use Agentiva in **your** project (`pipx install`, scan-on-push, or `agentiva serve`) | [Quick start](#quick-start) |
| **Develop** Agentiva from a clone (API + Next.js dashboard) | [Install → from source](#install), then [End-to-end local setup](#end-to-end-local-setup) |
| See what the dashboard looks like in motion (optional) | Screen recording: [`assets/demo.gif`](assets/demo.gif) — not required for install or setup |

---

## Table of contents

- [Quick start](#quick-start)
- [Why Agentiva](#why-agentiva)
- [What you get](#what-you-get)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [End-to-end local setup](#end-to-end-local-setup)
- [CLI reference](#cli-reference)
- [Wire Agentiva into your agent](#wire-agentiva-into-your-agent)
- [Policies and environment](#policies-and-environment)
- [Docker Compose](#docker-compose)
- [Landing page (website/)](#landing-page-website)
- [Dashboard](#dashboard)
- [API](#api)
- [Tests and benchmarks](#tests-and-benchmarks)
- [Git pre-push scan](#git-pre-push-scan)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Contributing and license](#contributing-and-license)

---

## Quick start

Two ways to use Agentiva: **scan on every git push** (coding agents) or **intercept tool calls at runtime** (agent frameworks).

### AI coding agents

```bash
pipx install agentiva
cd your-project
agentiva init
```

If you don’t have `pipx` (or you’re on macOS/Homebrew and see “externally-managed-environment”), use a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -U agentiva
```

Then commit and push as usual. Agentiva scans on each push; if critical issues are found, the push is blocked. Fix the findings and push again.

```bash
git add .
git commit -m "your change"
git push
```

If you get warnings for things you know are safe (mock credentials in tests, local dev config), allow them once so future scans skip them:

```bash
# Allow a specific file
agentiva allow tests/test_auth.py

# Allow an entire folder
agentiva allow tests/

# Allow a specific dev config file
agentiva allow config/dev.yaml

# See / remove / reset
agentiva allow --list
agentiva allow --remove config/dev.yaml
agentiva allow --reset
```

```bash
agentiva dashboard   # opens the HTML scan report in your browser
```

After `agentiva init`, every git push is protected automatically — no extra commands for day-to-day work.

### Agent frameworks

```bash
pipx install agentiva
agentiva serve
```

The API starts; use [End-to-end local setup](#end-to-end-local-setup) for the full Next.js dashboard (audit log, live feed, co-pilot). Wrap tools with `Agentiva` — see [Wire Agentiva into your agent](#wire-agentiva-into-your-agent). Start in **shadow** mode to observe; switch to **live** to block; use **approval** for human-in-the-loop.

### What Agentiva checks on every scan

Hardcoded credentials · SQL injection · Prompt injection · LLM output execution · Compromised packages · PII exposure · Base64 obfuscation · Weak hashing · Command injection · XSS · JWT bypass · Path traversal · Typosquatted domains · Privilege escalation · SSH key injection · Remote exfiltration — across file types.

### FAQ (short)

| Question | Answer |
|----------|--------|
| **Languages / file types?** | Project-wide: Python, JavaScript, TypeScript, Go, Java, Ruby, PHP, YAML, JSON, `.env`, Markdown, shell scripts, configs, and more. |
| **Runs automatically?** | Yes — run `agentiva init` once; then every `git push` is scanned. |
| **Blocks deployment?** | Critical issues block push; warnings are logged but typically do not block. |
| **Slow?** | Scans are local pattern checks (seconds on typical repos; no LLM in the scanner). |
| **Replaces a pentest?** | No — use Agentiva as a first line of defense; still do formal reviews for production. |
| **Only AI-written code?** | No — all code is scanned. |
| **Customize rules?** | Yes — YAML policies, thresholds, allowlists. |
| **vs VibeLint / Snyk?** | Static patterns plus **runtime** interception for agent actions (email, DB, APIs). |
| **Data privacy?** | Runs locally; scan output under `.agentiva/` (hook adds it to `.gitignore`). |
| **See results?** | Terminal on push; `agentiva dashboard` for HTML report; `agentiva serve` for live dashboard. |
| **MCP?** | Use `agentiva mcp-proxy` — point the client at Agentiva instead of upstream. |
| **Cursor?** | `pipx install agentiva` + `agentiva init` in the repo; add `agentiva serve` for live monitoring. |

---

## Why Agentiva

Agents call real tools: email, databases, shells, payments. Agentiva sits **in front of those calls**, applies **YAML policies** and a **risk scorer**, supports **shadow / live / approval** style modes, and persists **audit evidence** you can export for audit and review workflows.

It is **self-hostable**, open source (Apache 2.0), and integrates with common stacks (LangChain, CrewAI, OpenAI-style tools, Anthropic, MCP, or plain HTTP).

---

## What you get

| Capability | Description |
|------------|-------------|
| **Intercept** | Score and allow / shadow / block (or hand off to approval) before side effects run |
| **Policy engine** | Declarative rules in YAML; tune for your org |
| **Audit log** | Searchable history, agent registry, audit log exports (JSON, CSV) in the dashboard |
| **Security co-pilot** | Chat over your logs; optional LLM via OpenRouter |
| **Project scanner** | `agentiva scan` for risky patterns in repos (optional git hook on `agentiva init`) |
| **MCP proxy** | Route MCP traffic through interception |

---

## Prerequisites

| Component | Version / notes |
|-----------|-----------------|
| **Python** | 3.10+ (3.11 used in Docker image) |
| **Node.js** | Current LTS recommended for the Next.js dashboard |
| **Git** | For clone and optional pre-push hook |
| **Docker** (optional) | Docker Compose for full stack + Postgres + Redis |

---

## Install

### From PyPI (runtime only)

```bash
pipx install agentiva
agentiva scan .
agentiva init
```

This installs the CLI (scanner + optional git pre-push gate). You do **not** need to run the API to use `agentiva scan`.

**What PyPI includes:** the Python package only — API, CLI, policies, `agentiva scan`, and `agentiva dashboard` (that command opens the **local scan report** HTML under `.agentiva/`, not the full product UI). The **Next.js dashboard** (audit log, live feed, co-pilot, policy screens) lives in the [`dashboard/`](dashboard/) directory in this repo and is **not** shipped inside the wheel. To use it, **clone the repository** and follow [End-to-end local setup](#end-to-end-local-setup), or run **[Docker Compose](#docker-compose)**.

### From source (recommended for development)

```bash
git clone https://github.com/RishavAr/agentiva.git
cd agentiva

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs the `agentiva` CLI and pulls dependencies from `requirements.txt` (via `pyproject.toml`).

---

## End-to-end local setup

Agentiva is two moving parts in development:

1. **Python API** (FastAPI) — default `http://127.0.0.1:8000`
2. **Next.js dashboard** — dev server on **`http://127.0.0.1:3001`** (proxies `/api/v1/*` to the API)

### Option A — one script (from repo root)

```bash
./scripts/dev-stack.sh
```

- Creates or updates `dashboard/.env.local` with `AGENTIVA_API_URL=http://127.0.0.1:8000` (or the port you set with `AGENTIVA_PORT`).
- Starts the API, then `npm run dev` in `dashboard/`.

### Option B — two terminals

**Terminal 1 — API**

```bash
source venv/bin/activate
agentiva serve --port 8000
# or: python -m agentiva.cli serve --port 8000
```

**Terminal 2 — dashboard**

```bash
cd dashboard
cp env.local.template .env.local   # first time only; edit AGENTIVA_API_URL if needed
npm install                         # first time only
npm run dev
```

Open **`http://127.0.0.1:3001`** in the browser. The dev server binds to `127.0.0.1` by default to avoid common VPN/Docker hostname issues on macOS.

### Optional: free stuck ports then serve API only

```bash
./scripts/serve-fresh.sh    # clears listeners on 8000 and 3001, then agentiva serve --port 8000
```

---

## CLI reference

| Command | Purpose |
|---------|---------|
| `agentiva serve [--port 8000] [--host 0.0.0.0] [--mode shadow\|live\|approval]` | Start the FastAPI server |
| `agentiva scan [DIR]` | Static scan of a project tree (reports under `.agentiva/`) |
| `agentiva dashboard [DIR]` | Open the **scan report** HTML in `.agentiva/` (not the Next.js audit UI) |
| `agentiva init` | Install git pre-push hook that runs `agentiva scan` |
| `agentiva allow PATH \| --list \| --remove PATH \| --reset` | Allow false positives (skip files/folders during scans) |
| `agentiva init-policy [--output policies/default.yaml]` | Copy default policy YAML into your tree |
| `agentiva mcp-proxy --upstream HOST:PORT --port 3002` | MCP proxy with interception |
| `agentiva demo` | Run packaged demo scenarios |
| `agentiva test` | Run pytest wrapper (see [Tests](#tests-and-benchmarks)) |

---

## Wire Agentiva into your agent

Minimal pattern (shadow mode observes without blocking side effects — behavior depends on mode and policy):

```python
from agentiva import Agentiva

shield = Agentiva(mode="shadow")
tools = shield.protect([your_tool_a, your_tool_b])

# Pass `tools` into LangChain, CrewAI, or your own executor unchanged.
```

**HTTP interception** — POST tool intent to the API (see OpenAPI `POST /api/v1/intercept`) for custom runtimes.

**MCP** — point clients at `agentiva mcp-proxy` and configure upstream per CLI help.

### MCP upstream allowlist (org policy)

If you run `agentiva mcp-proxy`, Agentiva adds the upstream server into the policy context as `context.mcp_upstream`.
You can enforce an org allowlist in your YAML policy:

```yaml
rules:
  - name: mcp_upstream_allowlist
    tool: "*"
    condition:
      field: context.mcp_upstream
      operator: not_in
      value:
        - "localhost:3001"
        - "mcp.internal.yourcompany.com:443"
    action: block
    risk_score: 0.95
```

### Multi-upstream MCP proxy (optional)

If you want **one** Agentiva proxy to front multiple MCP servers, start it with explicit aliases:

```bash
agentiva mcp-proxy \
  --upstream "mcp.dev.yourcompany.com:3001" \
  --upstream-alias prod=mcp.prod.yourcompany.com:3001 \
  --upstream-alias staging=mcp.staging.yourcompany.com:3001 \
  --multi-upstream
```

Then MCP clients can send `upstream: "prod"` (or `"staging"`) in the request body, and policy can enforce:
- `context.mcp_upstream` (actual host:port)
- `context.mcp_upstream_alias` (alias name)

---

## Policies and environment

- Default policy file in-repo: `policies/default.yaml`. Packaged copy: `agentiva/policies/default.yaml` (used when installed as a wheel).
- Docker Compose sets (see `docker-compose.yml`):

  | Variable | Role |
  |----------|------|
  | `AGENTIVA_DATABASE_URL` | DB connection (default SQLite in compose example) |
  | `AGENTIVA_POLICY_PATH` | Path to policy YAML |
  | `AGENTIVA_MODE` | e.g. `shadow` |
  | `AGENTIVA_RATE_LIMIT_PER_MINUTE` | Rate limit |
  | `AGENTIVA_HOST` / `AGENTIVA_PORT` | Bind address / port |

Use a local `.env` for secrets; do not commit real credentials (see `.gitignore`).

---

## Docker Compose

Full stack with API, dashboard image, Postgres, and Redis:

```bash
cp .env.example .env    # if present; configure secrets for production
docker compose up --build
```

- API: mapped host port from `AGENTIVA_PORT` (default **8000**).
- Dashboard container: **`http://localhost:3000`** in the compose file (`NEXT_PUBLIC_API_BASE` points at the backend service).

Paths and env names match `docker-compose.yml` in this repo.

---

## Landing page (website/)

The [`website/`](website/) folder is optional static HTML (copy and screenshots for a public page). **It is not part of using Agentiva** — no install step, no dependency on any host or provider.

If you edit it, preview by opening `website/index.html` in a browser. Everything that matters for the product is the Python package, CLI, and [`dashboard/`](dashboard/) app above.

---

## Dashboard

There are two different things named “dashboard”:

1. **`agentiva dashboard`** (works after `pip install`) — Opens the **security scan** report (`report.html` produced by `agentiva scan`). No Node.js required.
2. **Next.js app in `dashboard/`** — The **full product UI** (overview, live actions, audit, agents, policies, chat). Requires a **repo clone** or **Docker Compose**; it is not installed by `pipx install agentiva`.

When the Next.js app is running in **development**:

| Area | Purpose |
|------|---------|
| Overview | High-level stats and activity |
| Live | Real-time action feed (WebSocket) |
| Audit | Searchable log, filters, exports |
| Agents | Registry and controls |
| Policies | Policy editing workflow |
| Chat / co-pilot | Ask questions over your data |

**Optional LLM:** set `OPENROUTER_API_KEY` where your server or dashboard expects it for richer co-pilot answers (OpenRouter).

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health, mode, threshold hints |
| `/api/v1/intercept` | POST | Evaluate a tool call |
| `/api/v1/audit` | GET | Query audit log |
| `/api/v1/report` | GET | Summary report |
| `/api/v1/settings` | PUT | Runtime settings |
| `/ws/actions` | WebSocket | Live action stream |

Interactive docs: **`http://127.0.0.1:8000/docs`** after `agentiva serve`.

---

## Tests and benchmarks

```bash
source venv/bin/activate
python -m pytest tests/ -q
```

Full suite including slower markers:

```bash
python -m pytest tests/ -m "slow or not slow" -q
```

Benchmark-style runners (see `benchmarks/`):

```bash
python benchmarks/run_benchmark.py
python benchmarks/run_all_benchmarks.py
```

### Reported verification highlights

| Area | Note |
|------|------|
| Test suite | Large automated suite covering attacks, compliance scenarios, and integrations |
| OWASP LLM Top 10 | Category coverage in project tests |
| DeepTeam, Garak, PyRIT | Third-party style assessments documented in `benchmarks/` |

---

## Git pre-push scan

If you run `agentiva init`, a **pre-push** hook runs `agentiva scan .`. If the scan exits non-zero (e.g. BLOCK findings in demos or tests), `git push` is blocked. To push anyway when you accept the risk:

```bash
git push --no-verify
```

For day-to-day development, keep the hook or adjust scan configuration as your team prefers.

---

## Architecture

```
┌────────────────────┐
│  Your agent        │  LangChain · CrewAI · OpenAI · Anthropic · MCP · custom
└─────────┬──────────┘
          │ tool calls
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Agentiva API (FastAPI)                                                  │
│  /api/v1/intercept · audit · chat · WebSocket feed · OpenAPI /docs       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
┌──────────────────────┐                 ┌──────────────────────┐
│  Policy + scoring    │                 │  Shield chat /       │
│  YAML · risk · PHI   │                 │  sessions (SQLite)   │
└──────────┬───────────┘                 └──────────┬───────────┘
           │                                        │
           ▼                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Persistence: action logs, registry, approvals, chat                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| Dashboard cannot reach API | Check `dashboard/.env.local` → `AGENTIVA_API_URL` matches `agentiva serve` port |
| Blank page or connection error on `localhost` | Use **`http://127.0.0.1:3001`** (dev server hostname) |
| Port 8000 or 3001 in use | Stop other processes or run `./scripts/serve-fresh.sh` for API |
| `agentiva: command not found` | Activate `venv` and `pip install -e .` |
| Push rejected by hook | Fix scan findings or `git push --no-verify` |

---

## Contributing and license

- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md).
- **License:** Apache 2.0 — [LICENSE](LICENSE).

---

## Built by

**Rishav Aryan** — ML Engineer, George Mason University

[GitHub](https://github.com/RishavAr) · [Twitter](https://twitter.com/RISHAVA28874444) · [LinkedIn](https://linkedin.com/in/rishav-aryan)

Repository: [github.com/RishavAr/agentiva](https://github.com/RishavAr/agentiva)
