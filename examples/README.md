# AgentShield Examples

This folder contains runnable demos that showcase AgentShield in realistic workflows.

## Available Examples

- `live_demo.py`  
  End-to-end simulation of a LangChain-like agent making **100+** realistic actions across email, Slack, databases, Jira, finance, DevOps, APIs, customer data, and admin permissions — designed for the live dashboard feed.  
  Actions stream into the dashboard live feed over the AgentShield API.

## Run the Live Demo

1. Start backend:

```bash
agentshield serve --port 8000 --mode shadow
```

2. Start dashboard (optional but recommended):

```bash
cd dashboard
npm install
npm run dev
```

3. Run the example:

```bash
venv/bin/python examples/live_demo.py
```

## Expected Outcome

- You should see `SHADOW` and `BLOCKED` decisions in terminal output.
- Dashboard live feed should update in near real-time.
- Audit log and report endpoints should reflect the full scenario sequence.
