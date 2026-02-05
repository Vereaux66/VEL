class ANVELLogicLayer:
    def __init__(self, neuro_forge=None):
        self.rules = []
        self.neuro_forge = neuro_forge

    def define(self, pattern, result, weight=1.0):
        self.rules.append({"pattern": pattern, "result": result, "weight": weight})
        return f"[LOGIC] Added: {pattern} → {result}"

    def evaluate(self, input_val):
        scores = {}
        for rule in self.rules:
            if rule["pattern"] in input_val:
                score = rule["weight"]
                # enhance with neuro_forge confidence if available
                if self.neuro_forge:
                    conf = float(
                        self.neuro_forge.predict(
                            rule["result"], len(input_val)
                        ).split()[-1]
                    )
                    score *= conf
                scores[rule["result"]] = scores.get(rule["result"], 0) + score
        if not scores:
            return "[LOGIC] No match"
        best = max(scores, key=scores.get)
        return f"[LOGIC] {best} (score={scores[best]:.2f})"
