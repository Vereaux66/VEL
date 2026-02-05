class ANVELValidationMatrix:
    def __init__(self, chain_validator=None):
        self.validators = {}
        self.history = []
        self.chain_validator = chain_validator

    def register(self, key, fn, fallback=None):
        self.validators[key] = {"fn": fn, "fallback": fallback}
        return f"[VALIDATION] Registered: {key}"

    def validate(self, key, value):
        entry = {"key": key, "value": value}
        if key not in self.validators:
            entry["result"] = "no rule"
        else:
            fn = self.validators[key]["fn"]
            try:
                ok = fn(value)
                entry["result"] = "pass" if ok else "fail"
                if not ok and self.validators[key]["fallback"]:
                    entry["repaired"] = self.validators[key]["fallback"](value)
            except Exception as e:
                entry["result"] = f"error:{e}"
        self.history.append(entry)
        # record to chain if available
        if self.chain_validator:
            self.chain_validator.add_block(f"{key}:{value}->{entry['result']}")
        return entry

    def recent(self, limit=5):
        return self.history[-limit:]
