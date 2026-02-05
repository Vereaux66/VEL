class ANVELCommand:
    def __init__(self):
        self.commands = {}
        self.trace = []

    def register(self, name, func):
        if name in self.commands:
            return f"[COMMAND] '{name}' already registered"
        self.commands[name] = func
        return f"[COMMAND] Registered: {name}"

    def execute(self, name, *args, **kwargs):
        if name not in self.commands:
            self.trace.append((name, "UNKNOWN"))
            return f"[COMMAND] Unknown: {name}"
        try:
            result = self.commands[name](*args, **kwargs)
            self.trace.append((name, "OK", result))
            return result
        except Exception as e:
            self.trace.append((name, "ERROR", str(e)))
            return f"[COMMAND] Error executing '{name}': {e}"

    def list_commands(self):
        return list(self.commands.keys()) or ["[COMMAND] No commands available"]

    def history(self, limit=5):
        return self.trace[-limit:] if self.trace else ["[COMMAND] No trace history"]
