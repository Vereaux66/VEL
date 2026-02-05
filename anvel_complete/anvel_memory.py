class ANVELMemory:
    def __init__(self):
        self.entries = []

    def remember(self, fact, tag=None, scope="general"):
        record = {"fact": fact, "tag": tag, "scope": scope}
        self.entries.append(record)
        if len(self.entries) > 10000:
            self.entries = self.entries[-5000:]
        return f"[MEMORY] Stored: {fact}"

    def recall_last(self):
        return self.entries[-1] if self.entries else "[MEMORY] Empty"

    def recall_by_tag(self, tag):
        tagged = [e for e in self.entries if e["tag"] == tag]
        return tagged[-3:] if tagged else [f"[MEMORY] No entries with tag '{tag}'"]

    def recall_by_scope(self, scope):
        scoped = [e for e in self.entries if e["scope"] == scope]
        return scoped[-3:] if scoped else [f"[MEMORY] No entries in scope '{scope}'"]


class ANVELMemoryFusion:
    def __init__(self, mindnet=None):
        self.snapshots = []
        self.mindnet = mindnet

    def snapshot(self, data):
        self.snapshots.append(data)
        return f"[MEM FUSE] Snapshot {len(self.snapshots)} stored"

    def fuse(self):
        fused = {}
        for s in self.snapshots:
            fused.update(s)
        if self.mindnet:
            for k, v in fused.items():
                self.mindnet.encode("fused", {k: v}, related_to=k)
        return fused or "[MEM FUSE] Empty"


class ANVELPredictiveMemory:
    def __init__(self):
        from collections import Counter

        self._Counter = Counter
        self.history = []

    def learn(self, outcome):
        self.history.append(outcome)
        return f"[PREDICTIVE MEMORY] Learned outcome: {outcome}"

    def predict_next(self):
        if not self.history:
            return "[PREDICT] No data"
        freq = self._Counter(self.history)
        prediction = freq.most_common(1)[0][0]
        return f"[PREDICT] Most likely next: {prediction}"

    def pattern_match(self, depth=3):
        if len(self.history) < depth + 1:
            return "[PREDICT] Insufficient data"
        last_pattern = tuple(self.history[-depth:])
        patterns = {}
        for i in range(len(self.history) - depth):
            seq = tuple(self.history[i : i + depth])
            next_val = self.history[i + depth]
            if seq == last_pattern:
                patterns[next_val] = patterns.get(next_val, 0) + 1
        if not patterns:
            return "[PREDICT] No match for pattern"
        predicted = max(patterns, key=patterns.get)
        return f"[PREDICT] Based on pattern: {predicted}"

    def full_history(self):
        return self.history


class AnvelMemory(ANVELMemory):
    """Concrete memory with lifecycle and convenience ops."""

    def __init__(self):
        super().__init__()
        self.active = False

    def startup(self):
        self.active = True
        return self.remember("system boot", tag="system", scope="lifecycle")

    def shutdown(self):
        self.active = False
        return "[MEMORY] flushed"
