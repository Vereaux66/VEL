import time


class ANVELOperationalLedger:
    def __init__(self, summary_module=None):
        self.records = []
        self.summary_module = summary_module

    def record(self, op, status="OK", meta=None):
        entry = {"op": op, "status": status, "meta": meta or {}, "time": time.ctime()}
        self.records.append(entry)
        # update summary if available
        if self.summary_module:
            self.summary_module.add_record(op, 0, 0, 0)
        return f"[LEDGER] {op} → {status}"

    def recent(self, limit=5):
        return self.records[-limit:]

    def find(self, op):
        return [r for r in self.records if r["op"] == op]
