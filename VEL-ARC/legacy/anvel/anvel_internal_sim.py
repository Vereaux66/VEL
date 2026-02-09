import json


class ANVELInternalSim:
    def __init__(self):
        self.scenarios = []
        self.sim_log = []

    def simulate(self, scenario: dict):
        if (
            not isinstance(scenario, dict)
            or "action" not in scenario
            or "conditions" not in scenario
        ):
            return "[SIM] Invalid scenario format"

        action = scenario["action"]
        conditions = scenario["conditions"]
        result = self._evaluate(action, conditions)
        report = {"action": action, "conditions": conditions, "result": result}

        self.sim_log.append(report)
        return f"[SIM] Scenario completed: {json.dumps(report)}"

    def _evaluate(self, action, conditions):
        score = 0
        for k, v in conditions.items():
            score += 1 if v in ("good", True, 1) else -1
        return "success" if score >= 0 else "failure"

    def history(self, limit=5):
        return self.sim_log[-limit:] if self.sim_log else "[SIM] No simulations"
