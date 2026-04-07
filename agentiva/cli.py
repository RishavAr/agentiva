import argparse
import asyncio
import html
import json
import os
import shutil
import socket
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from agentiva.api.server import run_server
from agentiva.interceptor.core import Agentiva
from agentiva.interceptor.mcp_proxy import run_proxy
from agentiva.project_scan import read_utf8_text_file, scan_text_file


def _resolve_default_policy_path() -> str:
    """Resolve default policy: in-package (wheel/sdist), repo root, cwd, then data_files install."""
    cli_dir = Path(__file__).resolve().parent
    fallback = cli_dir / "policies" / "default.yaml"
    candidates = (
        fallback,
        cli_dir.parent / "policies" / "default.yaml",
        Path.cwd() / "policies" / "default.yaml",
    )
    for p in candidates:
        if p.is_file():
            return str(p)
    for prefix in (Path(sys.prefix), Path(getattr(sys, "base_prefix", sys.prefix))):
        installed = prefix / "policies" / "default.yaml"
        if installed.is_file():
            return str(installed)
    return str(fallback)


def _resolve_policy_template_path(template_arg: str) -> Path:
    """For init-policy: honor explicit paths; else cwd; else bundled default (no cwd file required)."""
    raw = Path(template_arg).expanduser()
    if raw.is_absolute():
        p = raw.resolve()
        if not p.is_file():
            raise SystemExit(f"Template policy not found: {p}")
        return p
    cwd_candidate = (Path.cwd() / raw).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate
    bundled = Path(_resolve_default_policy_path())
    if bundled.is_file():
        return bundled
    raise SystemExit(f"Template policy not found: {cwd_candidate}")


def _mirror_scan_results_to_user_cache(scan_json_path: str) -> None:
    """Copy last scan JSON to ~/.agentiva/ so `agentiva dashboard` works from any cwd."""
    try:
        dest_dir = os.path.expanduser("~/.agentiva")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, "last_scan.json")
        shutil.copy2(scan_json_path, dest)
    except OSError:
        pass


def _ensure_gitignore_agentiva_dir() -> None:
    """Append `.agentiva/` to the repo root `.gitignore` if missing."""
    gi = Path.cwd() / ".gitignore"
    line = ".agentiva/"
    if gi.is_file():
        try:
            text = gi.read_text(encoding="utf-8")
        except OSError:
            return
        if line in text.splitlines() or any(l.strip() == line for l in text.splitlines()):
            return
        try:
            with gi.open("a", encoding="utf-8") as f:
                if text and not text.endswith("\n"):
                    f.write("\n")
                f.write(f"{line}\n")
        except OSError:
            return
    else:
        try:
            gi.write_text(f"{line}\n", encoding="utf-8")
        except OSError:
            return
    print("  📝 Added .agentiva/ to .gitignore")


def _build_scan_report_html(
    project_name: str,
    subtitle_display: str,
    files_scanned: int,
    issues_found: int,
    scan_issues: list[dict],
) -> str:
    """Static HTML report for a scan (escape all dynamic text)."""
    blocked = [i for i in scan_issues if i.get("decision") == "block"]
    warnings = [i for i in scan_issues if i.get("decision") != "block"]
    clean_n = max(0, files_scanned - issues_found)
    esc_proj = html.escape(project_name)
    esc_sub = html.escape(subtitle_display)

    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html><head><meta charset=\"UTF-8\">",
        f"<title>Agentiva — {esc_proj}</title>",
        "<style>",
        "*{margin:0;padding:0;box-sizing:border-box}",
        "body{font-family:-apple-system,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px;max-width:900px;margin:0 auto}",
        "h1{font-size:28px;margin-bottom:4px;color:#10b981}",
        ".subtitle{color:#64748b;margin-bottom:32px;font-size:14px}",
        ".stats{display:flex;gap:16px;margin-bottom:32px;flex-wrap:wrap}",
        ".stat{background:#111827;border-radius:12px;padding:20px;flex:1;min-width:120px;text-align:center}",
        ".stat .num{font-size:32px;font-weight:700}",
        ".stat .label{font-size:12px;color:#64748b;margin-top:4px}",
        ".stat.block .num{color:#ef4444}",
        ".stat.warn .num{color:#f59e0b}",
        ".stat.safe .num{color:#10b981}",
        ".issue{background:#111827;border-radius:10px;padding:16px 20px;margin-bottom:12px;border-left:4px solid #ef4444;display:flex;justify-content:space-between;align-items:center;gap:16px}",
        ".issue.warn{border-left-color:#f59e0b}",
        ".issue .left{flex:1;min-width:0}",
        ".issue .file{font-family:monospace;color:#60a5fa;font-size:14px;margin-bottom:4px;word-break:break-all}",
        ".issue .desc{color:#94a3b8;font-size:13px}",
        ".issue .right{text-align:right;flex-shrink:0}",
        ".badge{padding:2px 10px;border-radius:4px;font-size:11px;font-weight:700}",
        ".badge.block{background:#7f1d1d;color:#fca5a5}",
        ".badge.shadow{background:#78350f;color:#fde68a}",
        ".risk{font-size:13px;color:#64748b;margin-top:4px}",
        ".clean{background:#111827;border-radius:12px;padding:32px;text-align:center;color:#10b981;font-size:18px}",
        ".footer{margin-top:40px;text-align:center;color:#475569;font-size:13px}",
        ".footer a{color:#3b82f6;text-decoration:none}",
        ".copilot{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;margin-top:24px}",
        ".copilot h3{font-size:16px;margin-bottom:12px;color:#60a5fa}",
        ".copilot p{font-size:13px;color:#94a3b8;line-height:1.6}",
        "</style></head><body>",
        "<h1>Agentiva Scan Report</h1>",
        f"<p class=\"subtitle\">{esc_proj} — {esc_sub}</p>",
        "<div class=\"stats\">",
        f"<div class=\"stat\"><div class=\"num\">{files_scanned}</div><div class=\"label\">Files Scanned</div></div>",
        f"<div class=\"stat block\"><div class=\"num\">{len(blocked)}</div><div class=\"label\">Blocked</div></div>",
        f"<div class=\"stat warn\"><div class=\"num\">{len(warnings)}</div><div class=\"label\">Warnings</div></div>",
        f"<div class=\"stat safe\"><div class=\"num\">{clean_n}</div><div class=\"label\">Clean</div></div>",
        "</div>",
    ]

    if issues_found == 0:
        parts.append('<div class="clean">✅ No security issues found. Safe to deploy.</div>')
    else:
        for issue in scan_issues:
            decision = issue.get("decision", "shadow")
            badge_cls = "block" if decision == "block" else "shadow"
            badge_text = "BLOCK" if decision == "block" else "WARN"
            issue_cls = "" if decision == "block" else " warn"
            file_e = html.escape(str(issue.get("file", "unknown")))
            desc_e = html.escape(str(issue.get("description", "")))
            risk = float(issue.get("risk", 0.0))
            parts.append(
                f'<div class="issue{issue_cls}">'
                '<div class="left">'
                f'<div class="file">{file_e}</div>'
                f'<div class="desc">{desc_e}</div>'
                "</div>"
                '<div class="right">'
                f'<div class="badge {badge_cls}">{badge_text}</div>'
                f'<div class="risk">Risk: {risk:.2f}</div>'
                "</div></div>"
            )
        parts.append('<div class="copilot"><h3>🤖 Security Co-pilot</h3><p>')
        if blocked:
            parts.append(
                html.escape(
                    f"Found {len(blocked)} critical issue(s) that must be fixed before deploying. "
                )
            )
            for b in blocked[:3]:
                bf = html.escape(str(b.get("file", "")))
                bd = html.escape(str(b.get("description", "")))
                parts.append(f"<strong>{bf}</strong> — {bd}. ")
        if warnings:
            parts.append(
                html.escape(f"{len(warnings)} warning(s) should be reviewed. ")
            )
        parts.append(
            "Fix the blocked items, then run <code>agentiva scan .</code> again.</p></div>"
        )

    parts.append(
        '<div class="footer"><p>Generated by <a href="https://github.com/RishavAr/agentiva">Agentiva</a> · '
        "pip install agentiva · "
        '<a href="https://calendly.com/rishavaryan058/30min">Book a demo</a></p></div></body></html>'
    )
    return "".join(parts)


def _write_scan_report_file(
    agentiva_dir: str,
    project_name: str,
    files_scanned: int,
    issues_found: int,
    scan_issues: list[dict],
) -> str:
    os.makedirs(agentiva_dir, exist_ok=True)
    subtitle = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    doc = _build_scan_report_html(
        project_name, subtitle, files_scanned, issues_found, scan_issues
    )
    report_path = os.path.join(agentiva_dir, "report.html")
    with open(report_path, "w", encoding="utf-8") as rf:
        rf.write(doc)
    return report_path


def find_available_port(listen_host: str = "0.0.0.0", start: int = 8000, end: int = 8100) -> int | None:
    """Return first free TCP port in [start, end). Uses same bind address family as uvicorn will."""
    probe_host = "0.0.0.0" if listen_host in ("0.0.0.0", "::", "::0") else listen_host
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((probe_host, port))
                return port
        except OSError:
            continue
    return None


def _cmd_scan(args: argparse.Namespace) -> None:
    """Walk a directory tree: UTF-8 text files ≤1MB, all extensions; dependency manifests also checked for bad packages."""
    directory = args.directory
    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        raise SystemExit(f"Not a directory: {abs_dir}")

    project_name = os.path.basename(abs_dir)
    scan_agent_id = f"scan-{project_name}"

    print(f"\n  Agentiva scanning: {abs_dir}\n")

    policy_path = _resolve_default_policy_path()
    shield = Agentiva(mode="shadow", policy_path=policy_path)
    issues_found = 0
    files_scanned = 0
    gitignore_warned = False
    scan_issues: list[dict] = []

    skip_dir_names = {
        ".git",
        ".agentiva",
        "node_modules",
        "__pycache__",
        "venv",
        ".next",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
        ".tox",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
    }

    for root, dirs, files in os.walk(abs_dir):
        dirs[:] = [d for d in dirs if d not in skip_dir_names]

        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, abs_dir)

            try:
                content, _ = read_utf8_text_file(filepath)
                if content is None:
                    continue

                files_scanned += 1
                if not content.strip():
                    continue

                new_issues, gitignore_warned = scan_text_file(
                    rel_path,
                    content,
                    filename,
                    shield,
                    scan_agent_id,
                    gitignore_warned,
                )
                for row in new_issues:
                    issues_found += 1
                    scan_issues.append(row)
                    icon = "[BLOCK]" if row.get("decision") == "block" else "[WARN]"
                    print(f"  {icon} {rel_path}")
                    print(f"     {row.get('description', '')}")
                    print(f"     Risk: {row.get('risk', 0):.2f}\n")

            except OSError:
                continue

    agentiva_dir = os.path.join(abs_dir, ".agentiva")
    os.makedirs(agentiva_dir, exist_ok=True)
    scan_payload = {
        "project": project_name,
        "scan_root": abs_dir,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": scan_agent_id,
        "files_scanned": files_scanned,
        "issues_found": issues_found,
        "issues": scan_issues,
    }
    last_scan_path = os.path.join(agentiva_dir, "last_scan.json")
    with open(last_scan_path, "w", encoding="utf-8") as sf:
        json.dump(scan_payload, sf, indent=2)
    _mirror_scan_results_to_user_cache(last_scan_path)

    sep = "=" * 50
    print(f"  {sep}")
    print("  Scan complete")
    print(f"  Files scanned: {files_scanned}")
    print(f"  Issues found: {issues_found}")
    blocked_count = sum(1 for i in scan_issues if i.get("decision") == "block")
    if blocked_count > 0:
        print(f"\n  🛑 {blocked_count} blocking issue(s) found.")
        print("  Fix these before deploying.")
    if issues_found > 0:
        if blocked_count == 0:
            print("\n  Fix these issues before deploying.")
        print("  Ask the co-pilot: 'what should I fix?' (when using the full UI)")
    else:
        print("\n  ✅ No security issues found. Safe to deploy (verify manually).")
    print(f"  {sep}\n")

    report_path = _write_scan_report_file(
        agentiva_dir, project_name, files_scanned, issues_found, scan_issues
    )
    webbrowser.open(Path(report_path).resolve().as_uri())
    print("  📊 Report opened in browser")
    print(f"  📁 {report_path}")
    print("  Open this report later: agentiva dashboard")

    # Strict exit (default): non-zero if policy blocks OR any finding (good for CI).
    # --advisory-exit: always 0 when the scan completed (pre-push hook — surface findings, still allow push).
    if getattr(args, "advisory_exit", False):
        if blocked_count > 0 or issues_found > 0:
            print(
                "  ℹ️  Advisory mode: push will not be blocked. "
                "Run `agentiva scan .` (without --advisory-exit) in CI for a strict gate.\n"
            )
        raise SystemExit(0)
    must_block_push = blocked_count > 0 or issues_found > 0
    raise SystemExit(1 if must_block_push else 0)


def _cmd_dashboard(args: argparse.Namespace) -> None:
    """Open the latest scan HTML report (same file produced by `agentiva scan`)."""
    root = os.path.abspath(args.directory)
    results_dir = os.path.join(root, ".agentiva")
    report_path = os.path.join(results_dir, "report.html")
    json_path = os.path.join(results_dir, "last_scan.json")

    if not os.path.isfile(report_path) and os.path.isfile(json_path):
        with open(json_path, encoding="utf-8") as jf:
            data = json.load(jf)
        report_path = _write_scan_report_file(
            results_dir,
            str(data.get("project", os.path.basename(root))),
            int(data.get("files_scanned", 0)),
            int(data.get("issues_found", 0)),
            list(data.get("issues") or []),
        )

    if os.path.isfile(report_path):
        webbrowser.open(Path(report_path).resolve().as_uri())
        print("  📊 Report opened in browser")
        print(f"  📁 {report_path}")
        return

    print("  No scan results found. Run 'agentiva scan .' first.")
    raise SystemExit(0)


def _cmd_serve(args: argparse.Namespace) -> None:
    os.environ["AGENTIVA_MODE"] = args.mode
    start_port = args.port
    end_port = start_port + 100
    chosen = find_available_port(args.host, start_port, end_port)
    if chosen is None:
        raise SystemExit(
            f"No free port between {start_port} and {end_port - 1} for host {args.host!r}. "
            f"Stop the process using port {start_port} (e.g. kill $(lsof -ti :{start_port})) or pass --port."
        )
    if chosen != start_port:
        print(f"Port {start_port} is busy; using port {chosen}.", file=sys.stderr)
        print(
            f"Tip: point the dashboard at this API — set AGENTIVA_API_URL=http://127.0.0.1:{chosen} "
            f"in dashboard/.env.local",
            file=sys.stderr,
        )
    display_host = "127.0.0.1" if args.host in ("0.0.0.0", "::", "::0") else args.host
    print(f"Agentiva API: http://{display_host}:{chosen}")
    run_server(host=args.host, port=chosen)


def _cmd_demo(_: argparse.Namespace) -> None:
    from examples.live_demo import run_demo

    asyncio.run(run_demo())


def _cmd_test(args: argparse.Namespace) -> None:
    cmd = [sys.executable, "-m", "pytest"]
    if args.verbose:
        cmd.append("-v")
    if args.path:
        cmd.append(args.path)
    else:
        cmd.append("tests")
    result = subprocess.run(cmd, check=False)
    raise SystemExit(result.returncode)


def _cmd_init_policy(args: argparse.Namespace) -> None:
    source = _resolve_policy_template_path(args.template_policy)
    destination = Path.cwd() / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"Created policy file at {destination}")


def _cmd_init(args: argparse.Namespace) -> None:
    """Install git pre-push hook that runs `agentiva scan .` before each push."""
    git_dir = os.path.join(os.getcwd(), ".git")
    if not os.path.isdir(git_dir):
        print("  ⚠️  No git repository found. Run 'git init' first.")
        raise SystemExit(1)

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    hook_path = os.path.join(hooks_dir, "pre-push")

    hook_content = """#!/usr/bin/env bash
# Agentiva Security Gate — auto-scans before git push
set +e

echo ""
echo "🛡️  Agentiva scanning before push..."
echo ""

if command -v agentiva >/dev/null 2>&1; then
  agentiva scan . --advisory-exit
else
  python -m agentiva.cli scan . --advisory-exit
fi
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo "❌ Push BLOCKED — agentiva scan failed or found issues (exit $EXIT_CODE)"
    echo "   Fix the issues above, then push again."
    echo "   View full report: agentiva dashboard"
    echo ""
    exit 1
fi

echo ""
echo "✅ Agentiva: pre-push scan finished (advisory). Pushing..."
echo ""
exit 0
"""

    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(hook_content)
    os.chmod(hook_path, 0o755)

    _ensure_gitignore_agentiva_dir()

    print("  ✅ Agentiva initialized")
    print("  📋 Git pre-push hook installed")
    print("  🛡️  Every 'git push' will scan for security issues first")
    print("  📊 View scan report: agentiva dashboard  ·  API + web UI: agentiva serve")


def _cmd_mcp_proxy(args: argparse.Namespace) -> None:
    run_proxy(upstream=args.upstream, port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentiva")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--mode", default="shadow", choices=["shadow", "live", "approval"])
    serve.set_defaults(func=_cmd_serve)

    demo = sub.add_parser("demo", help="Run the live demo scenarios")
    demo.set_defaults(func=_cmd_demo)

    test_cmd = sub.add_parser("test", help="Run test suite")
    test_cmd.add_argument("--path", default="tests")
    test_cmd.add_argument("--verbose", action="store_true")
    test_cmd.set_defaults(func=_cmd_test)

    init_cmd = sub.add_parser(
        "init",
        help="Initialize Agentiva in the current project (installs git pre-push scan hook)",
    )
    init_cmd.set_defaults(func=_cmd_init)

    init_policy_cmd = sub.add_parser(
        "init-policy",
        help="Copy default policy YAML into the current directory",
    )
    init_policy_cmd.add_argument("--output", default="policies/default.yaml")
    init_policy_cmd.add_argument("--template-policy", default="policies/default.yaml")
    init_policy_cmd.set_defaults(func=_cmd_init_policy)

    mcp_proxy_cmd = sub.add_parser("mcp-proxy", help="Run MCP proxy with interception")
    mcp_proxy_cmd.add_argument("--upstream", default="localhost:3001")
    mcp_proxy_cmd.add_argument("--port", type=int, default=3002)
    mcp_proxy_cmd.set_defaults(func=_cmd_mcp_proxy)

    scan_cmd = sub.add_parser("scan", help="Scan a project for security issues (automatic heuristics)")
    scan_cmd.add_argument("directory", nargs="?", default=".", help="Root directory to scan (default: .)")
    scan_cmd.add_argument(
        "--advisory-exit",
        action="store_true",
        help="Always exit 0 after a completed scan (e.g. git pre-push: show findings without blocking push).",
    )
    scan_cmd.set_defaults(func=_cmd_scan)

    dash_cmd = sub.add_parser(
        "dashboard",
        help="Open last scan results as a local HTML report (no server)",
    )
    dash_cmd.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Project root that contains .agentiva/last_scan.json (default: .)",
    )
    dash_cmd.set_defaults(func=_cmd_dashboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
