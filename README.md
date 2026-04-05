# Agentiva

**Runtime safety for AI agents.** Intercept tool calls, score risk against policy, log everything to an audit trail, and ship with shadow mode before you enforce blocks.

[![Tests](https://img.shields.io/badge/tests-24%2C599%20passing-brightgreen)]()
[![OWASP](https://img.shields.io/badge/OWASP%20LLM%20Top%2010-100%25-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()

---

## Table of contents

- [Why Agentiva](#why-agentiva)
- [What you get](#what-you-get)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [End-to-end local setup](#end-to-end-local-setup)
- [CLI reference](#cli-reference)
- [Wire Agentiva into your agent](#wire-agentiva-into-your-agent)
- [Policies and environment](#policies-and-environment)
- [Docker Compose](#docker-compose)
- [Marketing site (`website/`)](#marketing-site-website)
- [Dashboard](#dashboard)
- [API](#api)
- [Tests and benchmarks](#tests-and-benchmarks)
- [Git pre-push scan](#git-pre-push-scan)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Contributing and license](#contributing-and-license)

---

## Why Agentiva

Agents call real tools: email, databases, shells, payments. Agentiva sits **in front of those calls**, applies **YAML policies** and a **risk scorer**, supports **shadow / live / approval** style modes, and persists **audit evidence** you can export for compliance workflows.

It is **self-hostable**, open source (Apache 2.0), and integrates with common stacks (LangChain, CrewAI, OpenAI-style tools, Anthropic, MCP, or plain HTTP).

---

## What you get

| Capability | Description |
|------------|-------------|
| **Intercept** | Score and allow / shadow / block (or hand off to approval) before side effects run |
| **Policy engine** | Declarative rules in YAML; tune for your org |
| **Audit log** | Searchable history, agent registry, compliance-oriented exports in the dashboard |
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
pip install agentiva
agentiva serve --port 8000
```

OpenAPI docs: `http://127.0.0.1:8000/docs`.

### From source (recommended for development)

```bash
git clone https://github.com/RishavAr/agentshield.git
cd agentshield

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -e .
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
| `agentiva dashboard [DIR]` | Open the last scan report in HTML |
| `agentiva init` | Install git pre-push hook that runs `agentiva scan` |
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

## Marketing site (`website/`)

Static landing page (demo embed, pricing, install walkthrough). Deploy with any static host; many teams use [Vercel](https://vercel.com):

```bash
cd website
npx vercel --prod
```

---

## Dashboard

When the Next app is running in **development**:

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

Repository: [github.com/RishavAr/agentshield](https://github.com/RishavAr/agentiva)
