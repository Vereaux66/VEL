from statistics import mean, stdev


class ANVELFeedbackLoop:
    def __init__(self, decay=0.9):
        self.scores = []
        self.decay = decay

    def record(self, value):
        self.scores = [s * self.decay for s in self.scores] + [value]
        return f"[FEEDBACK] Recorded: {value}"

    def adaptiveness(self):
        if not self.scores:
            return "[FEEDBACK] No data"
        m = mean(self.scores)
        s = stdev(self.scores) if len(self.scores) > 1 else 0
        return f"[FEEDBACK] Index: {max(0, m / (s + 1e-5)):.2f}"

    def feedback_trend(self, limit=5):
        return self.scores[-limit:]
