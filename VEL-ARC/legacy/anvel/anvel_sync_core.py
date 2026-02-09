class ANVELSyncCore:
    def __init__(self, validator=None):
        self.state = {}
        self.checkpoints = []
        self.validator = validator

    def update(self, key, value, source="local"):
        old = self.state.get(key)
        self.state[key] = value
        cp = {"key": key, "old": old, "new": value, "source": source}
        self.checkpoints.append(cp)
        # validate chain if available
        if self.validator:
            self.validator.add_block(f"{key}:{old}->{value}")
        return f"[SYNC] {key}: {old}→{value}"

    def diff(self, external):
        return {
            k: v for k, v in self.state.items() if external.get(k) != v
        } or "[SYNC] No drift"

    def history(self, limit=5):
        return self.checkpoints[-limit:]
