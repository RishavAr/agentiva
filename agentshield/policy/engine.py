import fnmatch
from dataclasses import dataclass

import yaml


@dataclass
class PolicyResult:
    decision: str
    risk_score: float
    matched_rule: str = ""


class PolicyEngine:
    def __init__(self, policy_path: str):
        with open(policy_path, encoding="utf-8") as f:
            self.policy = yaml.safe_load(f)
        self.rules = self.policy.get("rules", [])
        self.default_mode = self.policy.get("default_mode", "shadow")

    async def evaluate(self, action) -> PolicyResult:
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

    def _check(self, cond, action) -> bool:
        val = self._get(action, cond["field"])
        op = cond["operator"]
        target = cond["value"]
        if op == "equals":
            return val == target
        if op == "not_equals":
            return val != target
        if op == "contains":
            return target in str(val or "")
        if op == "not_contains":
            return target not in str(val or "")
        if op == "in":
            return val in target
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
