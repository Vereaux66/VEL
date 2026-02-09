class ANVELContextualArbitrator:
    def __init__(self, logic_layer=None):
        self.history = []
        self.logic_layer = logic_layer

    def arbitrate(self, options, context):
        # score options based on context via logic_layer if available
        scores = {}
        for opt in options:
            base = 1.0
            if self.logic_layer:
                res = self.logic_layer.evaluate(context + opt)
                if "score=" in res:
                    base *= float(res.split("score=")[1].strip(")"))
            scores[opt] = base
        winner = max(scores, key=scores.get)
        entry = {
            "options": options,
            "context": context,
            "winner": winner,
            "scores": scores,
        }
        self.history.append(entry)
        return f"[ARBITRATOR] Chosen: {winner}"

    def review(self, limit=5):
        return self.history[-limit:]
