class ANVELConsentGate:
    def __init__(self, required_actors=2):
        self.required = required_actors
        self.approvals = set()
        self.log = []

    def approve(self, actor_id):
        self.approvals.add(actor_id)
        self.log.append((actor_id, "approved"))
        if len(self.approvals) >= self.required:
            return "[CONSENT GATE] Unlocked"
        return f"[CONSENT GATE] Waiting for {self.required - len(self.approvals)} more"

    def revoke(self, actor_id):
        self.approvals.discard(actor_id)
        self.log.append((actor_id, "revoked"))
        return f"[CONSENT GATE] Revoked by {actor_id}"

    def status(self):
        return {
            "required": self.required,
            "current": len(self.approvals),
            "unlocked": len(self.approvals) >= self.required,
        }

    def history(self, limit=5):
        return self.log[-limit:] if self.log else ["[CONSENT GATE] No history"]
