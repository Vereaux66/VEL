import time
from collections import defaultdict, deque


class ANVELConsciousness:
    def __init__(self, max_events: int = 10000):
        self.stream = []  # list of events
        self.max_events = max_events
        self.count_by_subsystem = defaultdict(int)
        self.count_by_state = defaultdict(int)
        self.last_state = {}
        self.salience_history = deque(maxlen=1000)
        self.focus_stack = []  # attention focus
        self.memory = None
        self.bus = None

    def log_awareness(self, subsystem, state="alive", meta=None):
        ts = time.time()
        tstr = time.ctime(ts)
        sal = self._salience(subsystem, state)
        event = {
            "subsystem": subsystem,
            "state": state,
            "time": tstr,
            "ts": ts,
            "salience": sal,
            "meta": meta or {},
        }
        self.stream.append(event)
        self.count_by_subsystem[subsystem] += 1
        self.count_by_state[state] += 1
        self.last_state[subsystem] = state
        self.salience_history.append(sal)
        # Prevent unbounded growth
        if len(self.stream) > self.max_events:
            self.stream = self.stream[-self.max_events // 2 :]
        if self.memory and hasattr(self.memory, "remember"):
            try:
                self.memory.remember(
                    f"{subsystem}:{state}", tag="consciousness", scope="awareness"
                )
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_CONSCIOUSNESS").debug("Exception suppressed in log_awareness")
        return f"[CONSCIOUSNESS] {subsystem}:{state}@{tstr} (S:{sal:.2f})"

    def stream_state(self, limit=5):
        return self.stream[-limit:] if self.stream else ["[CONSCIOUSNESS] No awareness"]

    def timeline(self, start_ts: float = 0, end_ts: float = None):
        end_ts = end_ts or time.time()
        return [
            e
            for e in self.stream
            if e.get("ts", 0) >= start_ts and e.get("ts", 0) <= end_ts
        ]

    # Attention and insights
    def focus_on(self, subsystem):
        self.focus_stack.append(subsystem)
        return f"[CONSCIOUSNESS] focus→{subsystem}"

    def defocus(self):
        return self.focus_stack.pop() if self.focus_stack else None

    def current_focus(self):
        return self.focus_stack[-1] if self.focus_stack else None

    def window(self, seconds: int = 300):
        now = time.time()
        return [e for e in self.stream if now - e.get("ts", now) <= seconds]

    def summary(self, limit: int = 10):
        top_subs = sorted(
            self.count_by_subsystem.items(), key=lambda x: x[1], reverse=True
        )[:limit]
        top_states = sorted(
            self.count_by_state.items(), key=lambda x: x[1], reverse=True
        )[:limit]
        avg_sal = (
            sum(self.salience_history) / len(self.salience_history)
            if self.salience_history
            else 0.0
        )
        return {
            "top_subsystems": top_subs,
            "top_states": top_states,
            "avg_salience": round(avg_sal, 2),
            "focus": self.current_focus(),
        }

    def anomalies(self, seconds: int = 300):
        w = self.window(seconds)
        issues = [
            e
            for e in w
            if e["state"].lower() in ("error", "fail", "alert", "panic")
            or e.get("salience", 0) > 0.9
        ]
        return issues[-10:]

    def attach_memory(self, memory):
        self.memory = memory
        return "[CONSCIOUSNESS] memory attached"

    def attach_event_bus(self, bus):
        self.bus = bus
        return "[CONSCIOUSNESS] event bus attached"

    def _salience(self, subsystem: str, state: str) -> float:
        w = {
            "error": 1.0,
            "fail": 0.95,
            "panic": 0.98,
            "warn": 0.7,
            "degraded": 0.6,
            "awake": 0.3,
            "sleep": 0.2,
            "ok": 0.4,
            "alive": 0.4,
            "ready": 0.5,
        }
        base = w.get(state.lower(), 0.5)
        novelty = (
            0.2
            if self.last_state.get(subsystem) and self.last_state[subsystem] != state
            else 0.0
        )
        recency = 0.1  # small recency bias
        return max(0.0, min(1.0, base + novelty + recency))


class AnvelConsciousness(ANVELConsciousness):
    """Operational consciousness layer with lifecycle hooks."""

    def __init__(self):
        super().__init__()
        self.active = False

    def startup(self):
        self.active = True
        return self.log_awareness("system", "awake")

    def shutdown(self):
        self.active = False
        return self.log_awareness("system", "sleep")

    def aware_of(self, subsystem, state="ok", meta=None):
        return self.log_awareness(subsystem, state, meta=meta)
