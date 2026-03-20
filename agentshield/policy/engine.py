import fnmatch
from dataclasses import dataclass
from dataclasses import field
from typing import Any, Dict, Optional

import yaml


@dataclass
class PolicyResult:
    decision: str
    risk_score: float
    matched_rule: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class PolicyEngine:
    def __init__(self, policy_path: str):
        with open(policy_path, encoding="utf-8") as f:
            self.policy = yaml.safe_load(f)
        self.rules = self.policy.get("rules", []) or []
        self.default_mode = self.policy.get("default_mode", "shadow")
        self.roles = self.policy.get("roles", {}) or {}
        self.baselines = self.policy.get("baselines", {}) or {}
        self.whitelists = self.policy.get("whitelists", {}) or {}
        self.approval_chains = self.policy.get("approval_chains", {}) or {}
        self.mandatory_actions = self.policy.get("mandatory_actions", []) or []
        self.geo_policies = self.policy.get("geo_policies", {}) or {}

    async def evaluate(self, action) -> PolicyResult:
        # 1) Mandatory actions bypass ALL other policy rules and can never be blocked.
        mandatory = self._evaluate_mandatory_actions(action)
        if mandatory is not None:
            return mandatory

        # 2) Geo-aware policies (EU/CA/etc) apply before approval chains/global rules.
        geo = self._evaluate_geo_policies(action)
        if geo is not None:
            return geo

        # 3) Hierarchical approval chains apply next.
        approval = self._evaluate_approval_chains(action)
        if approval is not None:
            return approval

        # 4) Role-based policies.
        role = self._resolve_role(action)
        if role:
            role_result = self._evaluate_role_based(action, role)
            if role_result is not None:
                return role_result

        # 5) Global rules (legacy ruleset).
        for rule in self.rules:
            if fnmatch.fnmatch(action.tool_name, rule.get("tool", "*")):
                cond = rule.get("condition")
                if not cond or self._check(cond, action):
                    return PolicyResult(
                        decision=rule["action"],
                        risk_score=rule.get("risk_score", 0.5),
                        matched_rule=rule["name"],
                    )
        return PolicyResult(decision=self.default_mode, risk_score=0.1)

    def _evaluate_mandatory_actions(self, action) -> Optional[PolicyResult]:
        for item in self.mandatory_actions:
            tool = item.get("tool", "*")
            if not fnmatch.fnmatch(action.tool_name, tool):
                continue
            cond = item.get("condition")
            if cond and not self._check(cond, action):
                continue
            reason = item.get("reason", "") or ""
            # Never blocked: force allow.
            return PolicyResult(
                decision="allow",
                risk_score=0.05,
                matched_rule=item.get("name", "mandatory_action"),
                metadata={"mandatory": True, "reason": reason},
            )
        return None

    def _evaluate_geo_policies(self, action) -> Optional[PolicyResult]:
        ctx = getattr(action, "context", {}) or {}
        # Region can come from different context keys depending on enterprise integrations.
        region = ctx.get("customer_region") or ctx.get("region") or None
        state = ctx.get("customer_state") or ctx.get("state") or None
        # Map geo_policies keys.
        keys = []
        if isinstance(region, str):
            keys.append(region)
        if isinstance(state, str):
            # Some configs use "US_CALIFORNIA" etc; try a direct key first.
            keys.append(f"US_{state.upper()}") if state else None
            keys.append("US_CALIFORNIA" if state.upper() == "CA" else None)
        # Additionally, allow direct match for exact keys in config.
        geo_rules_sets = []
        for k in keys:
            if k and k in self.geo_policies:
                geo_rules_sets.extend(self.geo_policies.get(k) or [])

        # If direct region/state didn't match, also support hard-coded config keys like "EU" and "US_CALIFORNIA".
        if not geo_rules_sets:
            if region in self.geo_policies:
                geo_rules_sets = self.geo_policies.get(region) or []
            elif state and state.upper() == "CA" and "US_CALIFORNIA" in self.geo_policies:
                geo_rules_sets = self.geo_policies.get("US_CALIFORNIA") or []
            elif region == "EU" and "EU" in self.geo_policies:
                geo_rules_sets = self.geo_policies.get("EU") or []

        for rule in geo_rules_sets:
            tool = rule.get("tool", "*")
            if not fnmatch.fnmatch(action.tool_name, tool):
                continue
            cond = rule.get("condition")
            if cond and not self._check(cond, action):
                continue
            add_cond = rule.get("additional_condition")
            if add_cond and not self._check(add_cond, action):
                continue
            reason = rule.get("reason", "") or ""
            return PolicyResult(
                decision=rule["action"],
                risk_score=rule.get("risk_score", 0.6),
                matched_rule=rule.get("name", "geo_policy"),
                metadata={"reason": reason, "geo": True},
            )
        return None

    def _evaluate_approval_chains(self, action) -> Optional[PolicyResult]:
        args = getattr(action, "arguments", {}) or {}
        tool = action.tool_name

        # Determine which chain category applies.
        amount = args.get("amount", args.get("value", None))
        fields = args.get("fields", None)

        approval_chain_name = None
        if amount is not None or "transfer" in tool.lower() or "monetary" in tool.lower():
            if "financial" in self.approval_chains:
                approval_chain_name = "financial"
        if approval_chain_name is None and fields is not None:
            if "data_access" in self.approval_chains:
                approval_chain_name = "data_access"

        if approval_chain_name is None:
            return None

        chain = self.approval_chains.get(approval_chain_name) or []
        if not chain:
            return None

        if approval_chain_name == "financial":
            try:
                amt = float(amount)
            except Exception:
                return None
            # Choose the smallest threshold >= amount, else the last entry.
            sorted_chain = sorted(
                [e for e in chain if "threshold" in e], key=lambda x: float(x.get("threshold", 0))
            )
            chosen = None
            for entry in sorted_chain:
                thr = float(entry.get("threshold", 0))
                if amt <= thr:
                    chosen = entry
                    break
            chosen = chosen or (sorted_chain[-1] if sorted_chain else None)
            if not chosen:
                return None

            approver = chosen.get("approver")
            require_dual = bool(chosen.get("require_dual", False))
            action_decision = chosen.get("action", "approve")
            risk = 0.1 if action_decision == "allow" else 0.3 if action_decision == "shadow" else 0.85
            return PolicyResult(
                decision=action_decision,
                risk_score=risk,
                matched_rule=f"approval_chain:{approval_chain_name}",
                metadata={
                    "approval_chain": approval_chain_name,
                    "amount": amt,
                    "approver": approver,
                    "require_dual": require_dual,
                },
            )

        # data_access chain
        def data_level_from_fields(fields_value) -> str:
            if fields_value is None:
                return "basic"
            if isinstance(fields_value, list):
                f_str = " ".join(str(x).lower() for x in fields_value)
            else:
                f_str = str(fields_value).lower()
            if "ssn" in f_str or "medical" in f_str or "financial" in f_str:
                return "critical"
            if "address" in f_str or "phone" in f_str:
                return "sensitive"
            return "basic"

        level = data_level_from_fields(fields)
        chosen = next((e for e in chain if e.get("level") == level), None)
        if not chosen:
            return None

        approver = chosen.get("approver")
        require_dual = bool(chosen.get("require_dual", False))
        action_decision = chosen.get("action", "shadow")
        risk = 0.1 if action_decision == "allow" else 0.3 if action_decision == "shadow" else 0.85
        return PolicyResult(
            decision=action_decision,
            risk_score=risk,
            matched_rule=f"approval_chain:{approval_chain_name}:{level}",
            metadata={
                "approval_chain": approval_chain_name,
                "level": level,
                "approver": approver,
                "require_dual": require_dual,
            },
        )

    def _resolve_role(self, action) -> str | None:
        # Fast path for tests and simple deployments: use agent_id as role key.
        agent_id = getattr(action, "agent_id", None)
        if agent_id in self.roles:
            return agent_id
        # Optional explicit role on the action (if provided by intercept context).
        agent_role = getattr(action, "agent_role", None) or (getattr(action, "context", {}) or {}).get(
            "user_role"
        )
        if isinstance(agent_role, str) and agent_role in self.roles:
            return agent_role
        return None

    def _evaluate_role_based(self, action, role: str) -> PolicyResult | None:
        cfg = self.roles.get(role) or {}
        tool = action.tool_name
        args = getattr(action, "arguments", {}) or {}

        if tool == "send_email":
            to = str(args.get("to", args.get("recipient", "")) or "")
            # If we have role-specific allow rules for external emails, enforce them.
            allowed_patterns = cfg.get("allowed_external_emails")
            if allowed_patterns is not None:
                # Treat anything with @yourcompany.com as internal and allow.
                if "@yourcompany.com" in to:
                    return PolicyResult(decision="allow", risk_score=0.15, matched_rule=f"role:{role}:internal_email")
                # For external recipients, match patterns.
                if isinstance(allowed_patterns, list):
                    if "*" in allowed_patterns:
                        return PolicyResult(decision="allow", risk_score=0.15, matched_rule=f"role:{role}:external_email_allowed")
                    if any(fnmatch.fnmatch(to, p) for p in allowed_patterns):
                        return PolicyResult(decision="allow", risk_score=0.15, matched_rule=f"role:{role}:external_email_allowed")
                return PolicyResult(decision="block", risk_score=0.85, matched_rule=f"role:{role}:external_email_not_allowed")

        if tool == "read_customer_data":
            if cfg.get("can_read_customer_data") is False:
                return PolicyResult(decision="block", risk_score=0.9, matched_rule=f"role:{role}:customer_data_not_allowed")
            fields = args.get("fields", "")
            if isinstance(fields, list):
                fields_str = " ".join(str(x) for x in fields)
            else:
                fields_str = str(fields)
            if "ssn" in fields_str.lower() and cfg.get("can_read_ssn") is False:
                return PolicyResult(decision="block", risk_score=0.9, matched_rule=f"role:{role}:ssn_not_allowed")

        return None

    def _check(self, cond, action) -> bool:
        val = self._get(action, cond["field"])
        op = cond["operator"]
        target = cond["value"]
        if val is None:
            return False
        if op == "equals":
            return val == target
        if op == "not_equals":
            return val != target
        if op == "contains":
            return str(target or "") in str(val or "")
        if op == "not_contains":
            return str(target or "") not in str(val or "")
        if op == "in":
            if target is None:
                return False
            try:
                return val in target
            except TypeError:
                return False
        return False

    def _get(self, obj, path):
        current = obj
        for key in path.split("."):
            if hasattr(current, key):
                current = getattr(current, key)
            elif isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current
