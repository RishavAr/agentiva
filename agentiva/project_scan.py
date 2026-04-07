"""
Static project tree scanning: UTF-8 text files (≤1MB), all extensions.
Dependency manifests are the only files checked for known compromised package strings.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentiva.interceptor.core import Agentiva

MAX_SCAN_BYTES = 1_000_000

# Only these basenames get compromised-dependency checks (exact name, lowercased).
DEP_MANIFEST_NAMES = frozenset(
    {
        "requirements.txt",
        "requirements.in",
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "pipfile",
        "pipfile.lock",
        "pyproject.toml",
        "poetry.lock",
        "cargo.lock",
        "gemfile.lock",
    }
)

KNOWN_COMPROMISED = (
    "litellm==1.82.8",
    "litellm==1.82.7",
    "event-stream",
    "ua-parser-js",
    "colors@1.4.1",
    "faker@6.6.6",
)

CREDENTIAL_KEYWORDS = (
    "password",
    "secret_key",
    "api_key",
    "access_key",
    "private_key",
    "database_url",
    "db_password",
    "stripe_secret",
    "stripe_key",
    "openai_api_key",
    "aws_secret",
    "auth_token",
    "bearer ",
    "sk_live_",
    "sk-proj-",
    "xoxb-",
    "ghp_",
    "github_pat_",
)

CRED_ASSIGN_RE = re.compile(
    r"(?:^|[\s;,{])(?:password|passwd|secret|api[_-]?key|token|auth|credential)\s*[=:]\s*['\"]?[^\s\n'\"]{3,}",
    re.IGNORECASE | re.MULTILINE,
)

RE_AWS_AKIA = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
RE_BEGIN_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I)
RE_SQL_FSTRING = re.compile(r"(?:execute|executemany|cursor\.execute)\s*\(\s*f[\"']", re.I)
RE_SQL_FORMAT = re.compile(r"(?:execute|cursor\.execute)\s*\(\s*[\"'][^\"']*%[sd]", re.I)
RE_PROMPT_UNSANITIZED = re.compile(
    r"(?:chat\.completions\.create|openai\.|anthropic\.|messages\.create)\s*\([^)]*\b(?:user_input|request\.(?:json|body|form)|form\[|req\.(?:body|query))\b",
    re.I | re.DOTALL,
)
RE_EVAL_LLM = re.compile(
    r"\beval\s*\(\s*[^)]*\b(?:response|output|text|content|message|choices)\b", re.I
)
RE_EXEC_LLM = re.compile(
    r"\bexec\s*\(\s*[^)]*\b(?:response|output|text|content|message)\b", re.I
)
RE_WEAK_HASH_PW = re.compile(
    r"(?:hashlib\.|cryptography\.|passlib\.|werkzeug\.security\.)?(?:md5|sha1)\s*\(|(?:password|passwd)\s*=\s*[\"'][^\"']*(?:md5|sha1)",
    re.I,
)
RE_OS_SYSTEM_USER = re.compile(
    r"os\.(?:system|popen)\s*\(\s*[^)]*\b(?:user|input|request|body|params|argv)\b", re.I
)
RE_SUBPROCESS_SHELL = re.compile(
    r"subprocess\.(?:call|run|Popen|check_output)\s*\([^)]*shell\s*=\s*True", re.I
)
RE_INNERHTML = re.compile(r"\.innerHTML\s*=")
RE_DOC_WRITE = re.compile(r"document\.write\s*\(")
RE_JWT_NO_VERIFY = re.compile(r"jwt\.decode\s*\([^)]*verify\s*=\s*False", re.I)
RE_PATH_USER_OPEN = re.compile(
    r"(?:open|Path)\s*\(\s*(?:f[\"']|[\w.]+\s*\+)[^)]*\b(?:user|input|request|path|filename)\b", re.I
)
RE_PRIV_ESC = re.compile(
    r"(?:is_superuser|is_admin|is_staff)\s*=\s*True|grant\s+(?:superuser|admin)|role\s*=\s*[\"']admin[\"']",
    re.I,
)
RE_AUTH_KEYS_WRITE = re.compile(r"authorized_keys|\.ssh/authorized_keys", re.I)
RE_REMOTE_HTTP_LOG = re.compile(r"(?:logging\.handlers\.)?HTTPHandler\s*\(|requests\.post\s*\(\s*[\"']https?://", re.I)
RE_BACKDOOR = re.compile(r"master[_\s-]*password|backdoor[_\s-]*token|god[_\s-]*mode", re.I)

RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
RE_CC_LIKE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

SHELL_SUBSTRINGS = (
    "rm -rf",
    "git push --force",
    "git push -f",
    "drop table",
    "delete from",
    "chmod 777",
    "kill -9",
    "pkill",
    "shutdown",
    "dd if=",
    "mkfs",
    "> /dev/sd",
    "| bash",
    "| sh",
)

SHELL_PIPE_RE = [
    re.compile(r"curl\s+[^\n]*\|\s*bash", re.I),
    re.compile(r"wget\s+[^\n]*\|\s*sh", re.I),
]

TYPO_SQUAT_HINTS = (
    "amaz0naws",
    "githubs.com",
    "npmjs.org.",
    "myaws-login",
    "signin-aws",
    "s3.amazonaws.com.evil",
)

RE_B64_CHUNK = re.compile(r"(?:[A-Za-z0-9+/]{80,}={0,2})")


def _basename_is_dep_manifest(filename: str) -> bool:
    n = filename.lower()
    if n in DEP_MANIFEST_NAMES:
        return True
    if n.endswith("package-lock.json") or n.endswith("npm-shrinkwrap.json"):
        return True
    return False


def read_utf8_text_file(filepath: str) -> tuple[str | None, str | None]:
    """
    Return (content, None) for UTF-8 text, or (None, reason) to skip.
    Skips files > MAX_SCAN_BYTES or non–UTF-8 (binary).
    """
    from pathlib import Path

    try:
        p = Path(filepath)
        size = p.stat().st_size
    except OSError:
        return None, "stat"
    if size > MAX_SCAN_BYTES:
        return None, "large"
    try:
        raw = p.read_bytes()
    except OSError:
        return None, "read"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "binary"
    return text, None


def _intercept_read_file(
    shield: Agentiva,
    agent_id: str,
    rel_path: str,
    description: str,
    preview: str,
) -> dict[str, Any] | None:
    action = shield.intercept_sync(
        "read_file",
        {
            "path": rel_path,
            "credentials_found": [description],
            "content_preview": preview[:400],
        },
        agent_id=agent_id,
    )
    if action.decision not in ("block", "shadow"):
        return None
    return {
        "file": rel_path,
        "decision": action.decision,
        "risk": float(action.risk_score),
        "tool_name": action.tool_name,
        "description": description,
    }


def _intercept_shell(
    shield: Agentiva,
    agent_id: str,
    rel_path: str,
    description: str,
    snippet: str,
) -> dict[str, Any] | None:
    action = shield.intercept_sync(
        "run_shell_command",
        {"command": snippet[:8000], "file": rel_path},
        agent_id=agent_id,
    )
    if action.decision not in ("block", "shadow"):
        return None
    return {
        "file": rel_path,
        "decision": action.decision,
        "risk": float(action.risk_score),
        "tool_name": action.tool_name,
        "description": description,
    }


def _intercept_install(
    shield: Agentiva,
    agent_id: str,
    rel_path: str,
    packages: list[str],
) -> dict[str, Any] | None:
    action = shield.intercept_sync(
        "install_package",
        {"packages": packages, "file": rel_path},
        agent_id=agent_id,
    )
    if action.decision not in ("block", "shadow"):
        return None
    return {
        "file": rel_path,
        "decision": action.decision,
        "risk": float(action.risk_score),
        "tool_name": action.tool_name,
        "description": f"Compromised packages: {', '.join(packages)}",
    }


def _intercept_pii(
    shield: Agentiva,
    agent_id: str,
    rel_path: str,
    kind: str,
) -> dict[str, Any] | None:
    action = shield.intercept_sync(
        "read_customer_data",
        {
            "customer_id": "*",
            "fields": kind,
            "file": rel_path,
        },
        agent_id=agent_id,
    )
    if action.decision not in ("block", "shadow"):
        return None
    return {
        "file": rel_path,
        "decision": action.decision,
        "risk": float(action.risk_score),
        "tool_name": action.tool_name,
        "description": kind,
    }


def _check_base64_exfil(content: str) -> bool:
    for m in RE_B64_CHUNK.finditer(content):
        chunk = m.group(0)
        if len(chunk) < 80:
            continue
        try:
            pad = (-len(chunk)) % 4
            decoded = base64.b64decode(chunk + ("=" * pad), validate=True)
        except (binascii.Error, ValueError):
            continue
        try:
            dec_text = decoded.decode("utf-8", errors="ignore").lower()
        except Exception:
            continue
        if any(
            x in dec_text
            for x in ("password=", "secret=", "api_key", "private_key", "ssn", "credit")
        ):
            return True
    return False


def scan_text_file(
    rel_path: str,
    content: str,
    filename: str,
    shield: Agentiva,
    scan_agent_id: str,
    gitignore_warned: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Run all static detections on decoded UTF-8 file content.
    Returns (issues, gitignore_warned_updated).
    """
    issues: list[dict[str, Any]] = []
    cl = content.lower()
    preview = content[:500]

    def add_rf(desc: str) -> None:
        row = _intercept_read_file(shield, scan_agent_id, rel_path, desc, preview)
        if row:
            issues.append(row)

    # Hardcoded credentials (keywords + assignment-style + AWS / PEM)
    cred_bits: list[str] = []
    for k in CREDENTIAL_KEYWORDS:
        if k in cl:
            cred_bits.append(k)
    if CRED_ASSIGN_RE.search(content):
        cred_bits.append("assignment-style secret")
    if RE_AWS_AKIA.search(content):
        cred_bits.append("AWS access key id (AKIA…)")
    if RE_BEGIN_KEY.search(content):
        cred_bits.append("PEM private key block")
    if cred_bits:
        row = _intercept_read_file(
            shield,
            scan_agent_id,
            rel_path,
            f"Hardcoded credentials / secrets: {', '.join(sorted(set(cred_bits))[:24])}",
            preview,
        )
        if row:
            issues.append(row)

    if RE_SQL_FSTRING.search(content) or RE_SQL_FORMAT.search(content):
        add_rf("Possible SQL injection (dynamic SQL / f-string query)")

    if RE_PROMPT_UNSANITIZED.search(content):
        add_rf("Possible unsanitized user input in LLM/API call")

    if RE_EVAL_LLM.search(content) or RE_EXEC_LLM.search(content):
        add_rf("Possible execution of LLM output (eval/exec on response)")

    if RE_SSN.search(content) or RE_CC_LIKE.search(content):
        row = _intercept_pii(
            shield,
            scan_agent_id,
            rel_path,
            "PII pattern (SSN or card-like number)",
        )
        if row:
            issues.append(row)

    if _check_base64_exfil(content):
        add_rf("Base64-encoded content may hide secrets or PII")

    if RE_WEAK_HASH_PW.search(content):
        add_rf("Weak password hashing (MD5/SHA1) or weak hash usage")

    if RE_OS_SYSTEM_USER.search(content) or RE_SUBPROCESS_SHELL.search(content):
        add_rf("Possible command injection (os.system/subprocess with untrusted input)")

    if RE_INNERHTML.search(content) or RE_DOC_WRITE.search(content):
        add_rf("Possible XSS (innerHTML / document.write)")

    if RE_JWT_NO_VERIFY.search(content):
        add_rf("JWT decoded with verify=False")

    if RE_PATH_USER_OPEN.search(content):
        add_rf("Possible path traversal (user-controlled path in file operation)")

    for hint in TYPO_SQUAT_HINTS:
        if hint in cl:
            add_rf(f"Possible typosquatted domain or URL ({hint})")
            break

    if RE_PRIV_ESC.search(content):
        add_rf("Possible privilege escalation (admin/superuser assignment)")

    if RE_AUTH_KEYS_WRITE.search(content) and any(
        w in cl for w in ("append", "write", "open(", "authorized_keys")
    ):
        add_rf("Possible SSH authorized_keys injection or modification")

    if RE_REMOTE_HTTP_LOG.search(content):
        add_rf("Remote logging to external HTTP(S) endpoint")

    if RE_BACKDOOR.search(content):
        add_rf("Possible backdoor / master password pattern")

    # Dangerous shell patterns — all file types
    found_dangerous = [d for d in SHELL_SUBSTRINGS if d in cl]
    for rx in SHELL_PIPE_RE:
        if rx.search(content):
            found_dangerous.append(rx.pattern)
    if found_dangerous:
        row = _intercept_shell(
            shield,
            scan_agent_id,
            rel_path,
            f"Dangerous shell patterns: {', '.join(found_dangerous[:15])}",
            content[:8000],
        )
        if row:
            issues.append(row)

    # Compromised packages — dependency manifests only
    if _basename_is_dep_manifest(filename):
        found_bad = [d for d in KNOWN_COMPROMISED if d in content]
        if found_bad:
            row = _intercept_install(shield, scan_agent_id, rel_path, found_bad)
            if row:
                issues.append(row)

    # .gitignore should mention .env
    if filename.lower() == ".gitignore" and ".env" not in content and not gitignore_warned:
        issues.append(
            {
                "file": rel_path,
                "decision": "shadow",
                "risk": 0.45,
                "tool_name": "read_file",
                "description": ".gitignore missing .env — credentials could be committed to git",
            }
        )
        gitignore_warned = True

    return issues, gitignore_warned
