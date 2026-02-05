class ANVELScenarioManager:
    def __init__(self):
        self.scenarios = {}
        self.current = None

    def define(self, name, conds):
        self.scenarios[name] = conds
        return f"[SCENARIO] {name}"

    def activate(self, name):
        if name not in self.scenarios:
            return "[SCENARIO] Unknown"
        self.current = name
        return f"[SCENARIO] Activated:{name}"

    def context(self):
        return (
            {"name": self.current, "conds": self.scenarios.get(self.current)}
            if self.current
            else "[SCENARIO] None"
        )
