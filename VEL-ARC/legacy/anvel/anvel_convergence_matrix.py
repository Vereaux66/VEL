from statistics import mean


class ANVELConvergenceMatrix:
    def __init__(self):
        self.points = {}

    def push(self, label, value):
        self.points.setdefault(label, []).append(value)
        return f"[CONVERGE]{label}:{value}"

    def converge(self, label):
        vals = self.points.get(label)
        return (
            "[CONVERGE]No data"
            if not vals
            else f"[CONVERGE]{label}=mean({mean(vals):.2f})"
        )
