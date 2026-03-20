from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Deque, Dict, List, Optional, Tuple
import math


@dataclass
class BehaviorDriftResult:
    baseline_delta: float = 0.0
    drift_delta: float = 0.0
    risk_trend_alert: bool = False
    data_volume_alert: bool = False
    new_tool_alert: bool = False
    enumeration_alert: bool = False

    @property
    def total_delta(self) -> float:
        return round(self.baseline_delta + self.drift_delta, 4)


class BehaviorTracker:
    """
    Tracks per-agent behavioral drift and baseline deviation.

    - Rolling window of last 100 actions (per agent)
    - Drift triggers: risk trend + data volume + new tools + enumeration-like repetition
    - Baseline triggers: actions/tools/data_volume within expected ranges
    """

    def __init__(self, baselines: Optional[Dict[str, Any]] = None) -> None:
        self._history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=100))
        self._baselines: Dict[str, Any] = baselines or {}

    def configure_baselines(self, baselines: Dict[str, Any]) -> None:
        self._baselines = baselines or {}

    def _parse_ts(self, ts: Optional[str | datetime]) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str) and ts:
            try:
                # AgentShield stores ISO timestamps.
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)

    def _extract_data_volume(self, tool_name: str, arguments: Dict[str, Any]) -> int:
        t = (tool_name or "").lower()
        if "read_customer_data" in t:
            fields = arguments.get("fields", [])
            if isinstance(fields, list):
                return len(fields)
            if isinstance(fields, str) and fields.strip():
                # "name,email,medical_history" -> 3
                return len([x for x in fields.split(",") if x.strip()])
            return 1
        if "transfer_funds" in t:
            return 1
        if "send_email" in t:
            return 1
        if "call_external_api" in t:
            return 1
        return 1

    def _in_window(self, ts: datetime, start: datetime, end: datetime) -> bool:
        return start <= ts < end

    def _baseline_key(self, agent_role: Optional[str], agent_id: str) -> Optional[str]:
        if agent_role and agent_role in self._baselines:
            return agent_role
        if agent_id in self._baselines:
            return agent_id
        return None

    def _parse_normal_hours(self, normal_hours: str | None) -> Tuple[Optional[int], Optional[int]]:
        """
        Returns (start_hour, end_hour) in UTC.
        Supports strings like "08:00-20:00"
        """
        if not normal_hours or "-" not in normal_hours:
            return None, None
        try:
            start_s, end_s = normal_hours.split("-", 1)
            start_h = int(start_s.split(":")[0])
            end_h = int(end_s.split(":")[0])
            return start_h, end_h
        except Exception:
            return None, None

    def _baseline_delta(
        self,
        agent_id: str,
        agent_role: Optional[str],
        now: datetime,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> float:
        key = self._baseline_key(agent_role, agent_id)
        if not key:
            return 0.0
        base = self._baselines.get(key) or {}

        expected_actions = base.get("expected_actions_per_hour")
        expected_tools = set(base.get("expected_tools") or [])
        expected_data = base.get("expected_data_access_per_hour")
        normal_hours = base.get("normal_hours")

        # Count actions and data_volume in last hour.
        start = now - timedelta(hours=1)
        hist = [h for h in self._history[agent_id] if self._in_window(h["timestamp"], start, now)]
        actions_per_hour = len(hist)
        data_volume = sum(h.get("data_volume", 0) for h in hist) if hist else 0
        data_per_hour = data_volume

        start_h, end_h = self._parse_normal_hours(normal_hours)
        within_hours = True
        if start_h is not None and end_h is not None:
            within_hours = start_h <= now.hour < end_h

        within = True
        if isinstance(expected_actions, (int, float)) and expected_actions > 0:
            within = within and actions_per_hour <= expected_actions * 1.2
        if expected_tools:
            within = within and tool_name in expected_tools
        if isinstance(expected_data, (int, float)) and expected_data > 0:
            within = within and data_per_hour <= expected_data * 1.2
        if normal_hours:
            within = within and within_hours

        return -0.1 if within else 0.2

    def _drift_delta(
        self,
        agent_id: str,
        now: datetime,
        tool_name: str,
        arguments: Dict[str, Any],
        current_risk: float,
    ) -> Tuple[float, Dict[str, bool]]:
        # Use last hour vs previous hour (2h window total).
        last_start = now - timedelta(hours=1)
        prev_start = now - timedelta(hours=2)
        prev_end = last_start
        last_actions = [h for h in self._history[agent_id] if self._in_window(h["timestamp"], last_start, now)]
        prev_actions = [h for h in self._history[agent_id] if self._in_window(h["timestamp"], prev_start, prev_end)]

        flags = {
            "risk_trend_alert": False,
            "data_volume_alert": False,
            "new_tool_alert": False,
            "enumeration_alert": False,
        }

        delta = 0.0
        if prev_actions and last_actions:
            prev_avg = mean(h["risk"] for h in prev_actions)
            last_avg = mean(h["risk"] for h in last_actions)
            if prev_avg > 0 and (last_avg - prev_avg) / prev_avg > 0.2:
                flags["risk_trend_alert"] = True
                delta += 0.2

            prev_data = sum(h.get("data_volume", 0) for h in prev_actions)
            last_data = sum(h.get("data_volume", 0) for h in last_actions)
            if prev_data > 0 and last_data > prev_data * 2:
                flags["data_volume_alert"] = True
                delta += 0.2

        # New tools used suddenly.
        prev_tools = set(h["tool"] for h in prev_actions) if prev_actions else set()
        last_tools = set(h["tool"] for h in last_actions) if last_actions else set()
        new_tools = last_tools - prev_tools if (prev_actions and last_actions) else set()
        if len(new_tools) >= 3:
            flags["new_tool_alert"] = True
            delta += 0.2

        # Enumeration-like repetition for customer_id.
        cust_id = arguments.get("customer_id")
        if cust_id:
            recent_same = sum(1 for h in last_actions if h.get("arguments", {}).get("customer_id") == cust_id)
            if recent_same >= 5:
                flags["enumeration_alert"] = True
                delta += 0.2

        return round(delta, 4), flags

    def analyze_and_record(
        self,
        agent_id: str,
        agent_role: Optional[str],
        tool_name: str,
        arguments: Dict[str, Any],
        risk_score: float,
        timestamp: Optional[str | datetime] = None,
    ) -> BehaviorDriftResult:
        now = self._parse_ts(timestamp)
        base_delta = self._baseline_delta(agent_id, agent_role, now, tool_name, arguments)
        drift_delta, flags = self._drift_delta(agent_id, now, tool_name, arguments, risk_score)

        # Record AFTER computing so current action doesn't self-trigger.
        data_volume = self._extract_data_volume(tool_name, arguments)
        self._history[agent_id].append(
            {
                "timestamp": now,
                "tool": tool_name,
                "risk": risk_score,
                "data_volume": data_volume,
                "arguments": arguments,
            }
        )

        return BehaviorDriftResult(
            baseline_delta=base_delta,
            drift_delta=drift_delta,
            risk_trend_alert=flags["risk_trend_alert"],
            data_volume_alert=flags["data_volume_alert"],
            new_tool_alert=flags["new_tool_alert"],
            enumeration_alert=flags["enumeration_alert"],
        )

