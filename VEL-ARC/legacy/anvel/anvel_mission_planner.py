import time


class ANVELMissionPlanner:
    def __init__(self):
        self.objectives = []
        self.completed = []

    def add_objective(self, description, priority=1):
        obj = {
            "desc": description,
            "priority": priority,
            "created": time.ctime(),
            "status": "pending",
        }
        self.objectives.append(obj)
        self.objectives.sort(key=lambda x: -x["priority"])
        return f"[MISSION] Added: {description}"

    def complete(self, index):
        if index < 0 or index >= len(self.objectives):
            return "[MISSION] Invalid index"
        obj = self.objectives.pop(index)
        obj["status"] = "completed"
        obj["completed"] = time.ctime()
        self.completed.append(obj)
        return f"[MISSION] Completed: {obj['desc']}"

    def upcoming(self, limit=5):
        return self.objectives[:limit] if self.objectives else ["[MISSION] None"]

    def history(self, limit=5):
        return self.completed[-limit:] if self.completed else ["[MISSION] None"]
