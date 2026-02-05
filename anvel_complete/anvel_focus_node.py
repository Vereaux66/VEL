class ANVELFocusNode:
    def __init__(self, mission_planner=None):
        self.tasks = []
        self.focus = None
        self.mission_planner = mission_planner

    def add_task(self, label, priority):
        self.tasks.append({"label": label, "priority": priority})
        self._recenter()
        return f"[FOCUS] Added: {label} (prio {priority})"

    def _recenter(self):
        self.tasks.sort(key=lambda x: -x["priority"])
        self.focus = self.tasks[0]["label"] if self.tasks else None
        # sync with mission planner
        if self.mission_planner:
            self.mission_planner.add_objective(self.focus, priority=1)

    def reevaluate(self):
        self._recenter()
        return f"[FOCUS] Now: {self.focus}"

    def context(self):
        return {"focus": self.focus, "tasks": list(self.tasks)}
