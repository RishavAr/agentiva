from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RollbackPlan:
    action_id: str
    tool_name: str
    undo_steps: List[str] = field(default_factory=list)
    original_state: Dict[str, Any] = field(default_factory=dict)
    reversible: bool = True
    rollback_executed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RollbackHandler = Callable[[RollbackPlan, Dict[str, Any]], RollbackPlan]


class RollbackEngine:
    def __init__(self) -> None:
        self._handlers: Dict[str, RollbackHandler] = {}
        self._plans: Dict[str, RollbackPlan] = {}
        self._register_builtin_handlers()

    def register(self, tool_name: str) -> Callable[[RollbackHandler], RollbackHandler]:
        def decorator(func: RollbackHandler) -> RollbackHandler:
            self._handlers[tool_name] = func
            return func

        return decorator

    def capture_state(
        self,
        action_id: str,
        tool_name: str,
        original_state: Optional[Dict[str, Any]] = None,
        reversible: Optional[bool] = None,
    ) -> RollbackPlan:
        reversible_value = self._infer_reversible(tool_name) if reversible is None else reversible
        plan = RollbackPlan(
            action_id=action_id,
            tool_name=tool_name,
            original_state=original_state or {},
            reversible=reversible_value,
            undo_steps=self._default_undo_steps(tool_name, original_state or {}),
        )
        self._plans[action_id] = plan
        return plan

    def rollback(self, action_id: str, current_state: Optional[Dict[str, Any]] = None) -> RollbackPlan:
        if action_id not in self._plans:
            raise KeyError(f"No rollback plan for action_id={action_id}")
        plan = self._plans[action_id]
        if not plan.reversible:
            return plan
        handler = self._handlers.get(plan.tool_name, self._default_handler)
        updated = handler(plan, current_state or {})
        updated.rollback_executed = True
        self._plans[action_id] = updated
        return updated

    def execute_with_rollback(
        self,
        action_id: str,
        tool_name: str,
        original_state: Optional[Dict[str, Any]] = None,
    ) -> RollbackPlan:
        return self.capture_state(
            action_id=action_id,
            tool_name=tool_name,
            original_state=original_state or {},
        )

    def get_plan(self, action_id: str) -> Optional[RollbackPlan]:
        return self._plans.get(action_id)

    def all_plans(self) -> List[RollbackPlan]:
        return list(self._plans.values())

    def list_rollbackable(self) -> List[RollbackPlan]:
        return [plan for plan in self._plans.values() if plan.reversible]

    def _infer_reversible(self, tool_name: str) -> bool:
        return tool_name not in {"gmail_send", "send_email", "email_send"}

    def _default_undo_steps(self, tool_name: str, original_state: Dict[str, Any]) -> List[str]:
        if tool_name.startswith("jira"):
            return ["Fetch current issue fields", "Restore original field values", "Add rollback comment"]
        if tool_name.startswith("slack"):
            return ["Delete posted message by timestamp", "Notify channel about rollback"]
        if "database" in tool_name:
            return ["Restore pre-action snapshot", "Reconcile schema drift if present"]
        if tool_name in {"gmail_send", "send_email"}:
            return ["Action is not reversible after delivery; notify compliance and recipient if needed."]
        return [f"Manual rollback required for tool={tool_name}"]

    def _register_builtin_handlers(self) -> None:
        self._handlers["jira"] = self._rollback_jira
        self._handlers["jira_update"] = self._rollback_jira
        self._handlers["slack"] = self._rollback_slack
        self._handlers["slack_post"] = self._rollback_slack
        self._handlers["database"] = self._rollback_database
        self._handlers["database_query"] = self._rollback_database
        self._handlers["filesystem"] = self._rollback_filesystem
        self._handlers["file_write"] = self._rollback_filesystem

    def _rollback_jira(self, plan: RollbackPlan, _: Dict[str, Any]) -> RollbackPlan:
        plan.undo_steps = [
            "Restore original Jira fields from captured state",
            "Re-open ticket if status was changed",
            "Attach rollback audit comment",
        ]
        return plan

    def _rollback_slack(self, plan: RollbackPlan, _: Dict[str, Any]) -> RollbackPlan:
        timestamp = plan.original_state.get("ts", "(unknown-ts)")
        plan.undo_steps = [
            f"Delete Slack message at ts={timestamp}",
            "Post follow-up rollback notice if required by policy",
        ]
        return plan

    def _rollback_database(self, plan: RollbackPlan, _: Dict[str, Any]) -> RollbackPlan:
        snapshot = plan.original_state.get("snapshot_id", "(latest-snapshot)")
        plan.undo_steps = [
            f"Restore database from snapshot {snapshot}",
            "Run integrity checks on affected tables",
        ]
        return plan

    def _default_handler(self, plan: RollbackPlan, _: Dict[str, Any]) -> RollbackPlan:
        plan.undo_steps = [f"Manual rollback for action {plan.action_id}"]
        return plan

    def _rollback_filesystem(self, plan: RollbackPlan, _: Dict[str, Any]) -> RollbackPlan:
        backup_path = plan.original_state.get("backup_path", "(missing-backup)")
        plan.undo_steps = [
            f"Restore file from backup at {backup_path}",
            "Validate file checksum and permissions",
        ]
        return plan
