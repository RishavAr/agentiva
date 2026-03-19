import argparse
import asyncio
import json

from agentshield.api.server import run_server
from agentshield.interceptor.core import AgentShield


def _cmd_serve(args: argparse.Namespace) -> None:
    run_server(host=args.host, port=args.port)


def _cmd_shadow(args: argparse.Namespace) -> None:
    shield = AgentShield(mode="shadow", policy_path=args.policy_path)
    print(f"AgentShield shadow mode ready. policy={shield.policy_path}")


def _cmd_test_policy(args: argparse.Namespace) -> None:
    shield = AgentShield(mode="shadow", policy_path=args.policy_path)
    action = asyncio.run(
        shield.intercept(
            tool_name=args.tool_name,
            arguments={"to": args.to, "subject": args.subject},
            agent_id="cli",
        )
    )
    print(json.dumps(action.to_dict(), indent=2))


def _cmd_audit(_: argparse.Namespace) -> None:
    shield = AgentShield(mode="shadow")
    print(json.dumps(shield.get_audit_log()[-10:], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentshield")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    shadow = sub.add_parser("shadow", help="Initialize shadow mode")
    shadow.add_argument("--policy-path", default="policies/default.yaml")
    shadow.set_defaults(func=_cmd_shadow)

    test_policy = sub.add_parser("test-policy", help="Test a policy against a sample action")
    test_policy.add_argument("--policy-path", default="policies/default.yaml")
    test_policy.add_argument("--tool-name", default="send_email")
    test_policy.add_argument("--to", default="user@yourcompany.com")
    test_policy.add_argument("--subject", default="Test message")
    test_policy.set_defaults(func=_cmd_test_policy)

    audit = sub.add_parser("audit", help="Print recent audit log")
    audit.set_defaults(func=_cmd_audit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
