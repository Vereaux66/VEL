# ANVEL Meta Suite - consolidated
import time
from collections import defaultdict


class ANVELMetaAICore:
    def __init__(self):
        self.audit_trail = []
        self.actions_taken = []
        self.alert_threshold = 5
        self.escalated = False

    def monitor(self, event, severity=1):
        timestamp = time.ctime()
        self.audit_trail.append((event, severity, timestamp))
        if severity >= self.alert_threshold and not self.escalated:
            self.escalated = True
            self.actions_taken.append(("escalate", event, timestamp))
            return f"[META AI CORE] ESCALATION TRIGGERED: {event}"
        return f"[META AI CORE] Logged event: {event} (Severity: {severity})"

    def status(self):
        return {
            "escalated": self.escalated,
            "audit_count": len(self.audit_trail),
            "last_action": self.actions_taken[-1] if self.actions_taken else "None",
        }

    def history(self, limit=5):
        return (
            self.audit_trail[-limit:]
            if self.audit_trail
            else ["[META AI CORE] No history"]
        )

    def actions(self):
        return (
            self.actions_taken[-5:]
            if self.actions_taken
            else ["[META AI CORE] No actions taken"]
        )


class ANVELMetaPlanner:
    def __init__(self, mission_planner=None):
        self.mission_planner = mission_planner
        self.goals = []

    def plan_goal(self, description, priority):
        self.goals.append({"desc": description, "priority": priority})
        if self.mission_planner:
            self.mission_planner.add_objective(description, priority)
        return f"[META PLAN] Goal planned: {description}"

    def list_goals(self):
        return sorted(self.goals, key=lambda g: -g["priority"])

    def execute_meta(self):
        executed = [g["desc"] for g in self.list_goals()]
        self.goals.clear()
        return f"[META PLAN] Executed: {executed}"


class ANVELMetaSentinel:
    def __init__(self):
        self.layer_events = defaultdict(list)
        self.anomalies = []
        self.rejection_count = defaultdict(int)
        self.max_rejections = 5

    def observe(self, layer, event, metadata=None):
        timestamp = time.ctime()
        record = {"event": event, "meta": metadata or {}, "time": timestamp}
        self.layer_events[layer].append(record)
        if metadata and metadata.get("anomaly", False):
            self.anomalies.append(record)
            return f"[META SENTINEL] Anomaly in {layer}: {event}"
        return f"[META SENTINEL] Observed in {layer}: {event}"

    def layer_summary(self, layer):
        events = self.layer_events.get(layer, [])
        return events[-3:] if events else [f"[META SENTINEL] No data for {layer}"]

    def flag_rejection(self, layer):
        self.rejection_count[layer] += 1
        if self.rejection_count[layer] >= self.max_rejections:
            return f"[META SENTINEL] ALERT: {layer} flagged for override"
        return f"[META SENTINEL] Rejection {self.rejection_count[layer]} for {layer}"

    def anomaly_report(self):
        return (
            self.anomalies[-5:]
            if self.anomalies
            else ["[META SENTINEL] No anomalies recorded"]
        )
