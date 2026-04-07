"""CLI: scan exit codes and git pre-push hook install."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentiva.cli", *args],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def test_scan_exits_zero_on_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# ok\nnothing sensitive\n", encoding="utf-8")
    r = _run_cli("scan", str(tmp_path))
    assert r.returncode == 0, r.stderr + r.stdout
    last = tmp_path / ".agentiva" / "last_scan.json"
    assert last.is_file()
    data = json.loads(last.read_text(encoding="utf-8"))
    assert data["project"] == tmp_path.name
    assert data["files_scanned"] >= 1
    assert data["issues_found"] == 0
    assert data["issues"] == []


def test_scan_exits_nonzero_when_credentials_pattern(tmp_path: Path) -> None:
    (tmp_path / "leak.txt").write_text("password = 'supersecret123'\n", encoding="utf-8")
    r = _run_cli("scan", str(tmp_path))
    assert r.returncode == 1, r.stderr + r.stdout
    data = json.loads((tmp_path / ".agentiva" / "last_scan.json").read_text(encoding="utf-8"))
    assert data["issues_found"] >= 1
    assert any("leak.txt" in str(i.get("file", "")) for i in data["issues"])


def test_scan_flags_password_in_yaml_and_json(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("database:\n  password: secret123\n", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----"}', encoding="utf-8")
    r = _run_cli("scan", str(tmp_path))
    assert r.returncode == 1, r.stderr + r.stdout
    data = json.loads((tmp_path / ".agentiva" / "last_scan.json").read_text(encoding="utf-8"))
    files = {i.get("file") for i in data["issues"]}
    assert "config.yaml" in files or any("config.yaml" in str(f) for f in files)
    assert data["issues_found"] >= 1


def test_scan_advisory_exit_zero_despite_findings(tmp_path: Path) -> None:
    (tmp_path / "leak.txt").write_text("password = 'supersecret123'\n", encoding="utf-8")
    r = _run_cli("scan", str(tmp_path), "--advisory-exit")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "Advisory mode" in r.stdout


def test_dashboard_opens_report_after_scan(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# ok\n", encoding="utf-8")
    sr = _run_cli("scan", str(tmp_path), cwd=tmp_path)
    assert sr.returncode == 0, sr.stderr + sr.stdout
    dr = _run_cli("dashboard", ".", cwd=tmp_path)
    assert dr.returncode == 0, dr.stderr + dr.stdout
    assert "Report opened" in dr.stdout
    report = tmp_path / ".agentiva" / "report.html"
    assert report.is_file()
    assert "Agentiva Scan Report" in report.read_text(encoding="utf-8")


def test_dashboard_no_scan_message(tmp_path: Path) -> None:
    # Isolate HOME so dashboard does not pick up ~/.agentiva/last_scan.json from the dev machine.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    r = _run_cli("dashboard", ".", cwd=tmp_path, env={"HOME": str(fake_home)})
    assert r.returncode == 0, r.stderr + r.stdout
    assert "No scan results found" in r.stdout


def test_init_policy_uses_bundled_template_without_project_policies(tmp_path: Path) -> None:
    """init-policy must not require policies/default.yaml in cwd (uses package copy)."""
    r = _run_cli("init-policy", cwd=tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    out = tmp_path / "policies" / "default.yaml"
    assert out.is_file()
    assert "version:" in out.read_text(encoding="utf-8")


def test_init_installs_pre_push_hook() -> None:
    # Use a directory inside the repo (not system /tmp) so sandboxes allow `.git/hooks`.
    root = Path(__file__).resolve().parent.parent / ".pytest_git_scratch" / "hook_install"
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    try:
        r = _run_cli("init", cwd=root)
        if r.returncode != 0 and "PermissionError" in (r.stderr or ""):
            pytest.skip("Environment blocks writes under .git/hooks (e.g. sandbox).")
        assert r.returncode == 0, r.stderr + r.stdout
        hook = root / ".git" / "hooks" / "pre-push"
        assert hook.is_file()
        text = hook.read_text(encoding="utf-8")
        assert "agentiva scan ." in text or "agentiva.cli scan" in text
        assert "--advisory-exit" in text
        assert "agentiva dashboard" in text
        gi = root / ".gitignore"
        assert gi.is_file()
        assert ".agentiva/" in gi.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_init_fails_without_git(tmp_path: Path) -> None:
    r = _run_cli("init", cwd=tmp_path)
    assert r.returncode == 1
