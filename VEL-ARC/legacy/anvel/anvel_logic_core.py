# ANVEL Logic Core - consolidated
import time
from collections import defaultdict


class ANVELDecisionTree:
    def __init__(self):
        self.tree = {}

    def add_branch(self, path, outcome):
        node = self.tree
        for feat, val in path:
            node = node.setdefault((feat, val), {})
        node["_outcome"] = outcome
        return "[DT] Branch added"

    def decide(self, features):
        node = self.tree
        for (feat, val), child in node.items():
            if feat in features and features[feat] == val:
                node = child
                if "_outcome" in node:
                    return f"[DT] Outcome: {node['_outcome']}"
        return "[DT] No decision"


class ANVELDirectiveEngine:
    def __init__(self):
        self.directives = defaultdict(list)
        self.execution_log = []

    def assign(self, level, directive_fn):
        self.directives[level].append(directive_fn)
        return f"[DIRECTIVE] Assigned to level '{level}'"

    def run_level(self, level):
        if level not in self.directives or not self.directives[level]:
            return f"[DIRECTIVE] No directives at level '{level}'"
        results = []
        for fn in self.directives[level]:
            try:
                result = fn()
                self.execution_log.append((level, result, time.ctime()))
                results.append(result)
            except Exception as e:
                self.execution_log.append((level, f"Error: {e}", time.ctime()))
                results.append(f"Error: {e}")
        return results

    def levels(self):
        return list(self.directives.keys()) or ["[DIRECTIVE] No levels defined"]

    def log(self, limit=5):
        return (
            self.execution_log[-limit:]
            if self.execution_log
            else ["[DIRECTIVE] No log data"]
        )


class ANVELRuleEngine:
    def __init__(self):
        self.rules = []

    def add(self, condition_fn, action_fn):
        self.rules.append((condition_fn, action_fn))
        return "[RULE] Added"

    def run(self, context):
        for cond, act in self.rules:
            if cond(context):
                return act(context)
        return "[RULE] No rule matched"


class ANVELConflictResolver:
    def __init__(self):
        self.resolutions = []

    def resolve(self, a, b, priority_a=1, priority_b=1):
        if priority_a > priority_b:
            win = a
        elif priority_b > priority_a:
            win = b
        else:
            win = a if str(a) < str(b) else b
        self.resolutions.append((a, b, win))
        return f"[RESOLVER] {win}"

    def last(self, limit=5):
        return self.resolutions[-limit:] if self.resolutions else ["[RESOLVER] None"]


class ANVELCompositeStrategy:
    def __init__(self, strategies=None):
        self.strategies = strategies or []

    def evaluate(self, context):
        results = [s(context) for s in self.strategies]
        return max(results) if results else None

    def add(self, strategy_fn):
        self.strategies.append(strategy_fn)
        return "[CS] Added"


class ANVELLogicHub:
    def __init__(self, mesh=None):
        self.paths = []
        self.history = []
        self.mesh = mesh

    def ingest(self, rule, context, outcome, weight=1.0):
        entry = {
            "rule": rule,
            "context": context,
            "outcome": outcome,
            "weight": weight,
            "time": time.ctime(),
        }
        self.paths.append(entry)
        self.history.append(entry)
        return f"[LOGIC HUB] Ingested: {rule} → {outcome}"

    def evaluate(self, input_context):
        candidates = [p for p in self.paths if p["context"] in input_context]
        if not candidates:
            return "[LOGIC HUB] No match"
        scores = {}
        for p in candidates:
            scores[p["outcome"]] = scores.get(p["outcome"], 0) + p["weight"]
        best = max(scores, key=scores.get)
        if self.mesh:
            self.mesh.dispatch(
                "logic_outcome", {"outcome": best, "score": scores[best]}
            )
        return f"[LOGIC HUB] Best: {best} (score={scores[best]:.2f})"

    def recall(self, limit=5):
        return self.history[-limit:]
