# flake8: noqa
# Consolidated Monitoring & Telemetry
import json
import threading
import time
import zlib
from collections import deque, defaultdict


class ANVELWatchdog:
    def __init__(self, timeout=60):
        self.timeout = timeout
        self.last_ping = time.time()
        self.status = "OK"
        self.lock = threading.RLock()
        self._start_monitor()

    def ping(self):
        with self.lock:
            self.last_ping = time.time()
            self.status = "OK"
            return "[WATCHDOG] Heartbeat received"

    def is_alive(self):
        with self.lock:
            return time.time() - self.last_ping < self.timeout

    def get_status(self):
        with self.lock:
            if not self.is_alive():
                self.status = "UNRESPONSIVE"
            return f"[WATCHDOG] Status: {self.status}"

    def _start_monitor(self):
        def monitor():
            while True:
                time.sleep(5)
                if not self.is_alive():
                    with self.lock:
                        self.status = "UNRESPONSIVE"

        threading.Thread(target=monitor, daemon=True).start()


class ANVELHeartbeatMonitor:
    def __init__(self, interval=10):
        self.interval = interval
        self.last_ping = time.time()
        self.heartbeat_log = []
        self.status = "ACTIVE"
        self.lock = threading.Lock()
        self._start_heartbeat_loop()

    def _start_heartbeat_loop(self):
        def loop():
            while True:
                time.sleep(self.interval)
                self._record_heartbeat()

        threading.Thread(target=loop, daemon=True).start()

    def _record_heartbeat(self):
        with self.lock:
            now = time.time()
            self.last_ping = now
            self.heartbeat_log.append(now)
            if len(self.heartbeat_log) > 1000:
                self.heartbeat_log = self.heartbeat_log[-500:]

    def get_last_heartbeat(self):
        with self.lock:
            return time.ctime(self.last_ping)

    def get_status(self):
        with self.lock:
            elapsed = time.time() - self.last_ping
            self.status = "STALLED" if elapsed > self.interval * 2 else "ACTIVE"
            return f"[HEARTBEAT] {self.status} ({elapsed:.2f}s since last ping)"


class ANVELHealthMonitor:
    def __init__(self):
        self.checks = []

    def check(self, name, fn):
        status = "OK" if fn() else "FAIL"
        self.checks.append((name, status, time.ctime()))
        return f"[HEALTH] {name}:{status}"

    def summary(self):
        return self.checks[-5:]


class ANVELSelfDiagnostics:
    def __init__(self, modules=None):
        self.checks = {}
        self.status = {}
        self.history = []
        self.modules = modules or []
        self.lock = threading.Lock()

    def run_check(self, label, fn, heal_fn=None):
        ts = time.ctime()
        try:
            fn()
            st = "OK"
            entry = {"label": label, "status": st, "time": ts}
        except Exception as e:
            st = f"FAIL: {e}"
            entry = {"label": label, "status": "FAIL", "time": ts, "error": str(e)}
            if heal_fn:
                try:
                    entry["healed"] = heal_fn()
                except Exception as he:
                    entry["heal_error"] = str(he)
        with self.lock:
            self.status[label] = st
            self.history.append(entry)
        return entry

    def global_report(self):
        with self.lock:
            return self.status.copy()

    def automated_cycle(self, interval=60):
        def cycle():
            while True:
                for mod in self.modules:
                    label = getattr(mod, "__name__", "module")
                    self.run_check(
                        label,
                        getattr(mod, "self_test", lambda: True),
                        getattr(mod, "heal", None),
                    )
                time.sleep(interval)

        threading.Thread(target=cycle, daemon=True).start()
        return "[DIAGNOSTICS] Automated cycle started"


class ANVELSelfDebugger:
    def __init__(self):
        self.scan_history = []
        self.issues_found = []
        self.last_run = None

    def diagnose(self, module_name, test_fn):
        result = "OK"
        ts = time.ctime()
        try:
            outcome = test_fn()
            if outcome is False or outcome == "FAIL":
                result = "FAIL"
                self.issues_found.append((module_name, ts, "Logic test failed"))
        except Exception as e:
            result = "ERROR"
            self.issues_found.append((module_name, ts, str(e)))
        report = {"module": module_name, "time": ts, "result": result}
        self.scan_history.append(report)
        self.last_run = ts
        return f"[SELF DEBUGGER] {module_name}: {result}"

    def history(self, limit=5):
        return (
            self.scan_history[-limit:]
            if self.scan_history
            else ["[SELF DEBUGGER] No scans run"]
        )

    def issues(self):
        return (
            self.issues_found[-5:]
            if self.issues_found
            else ["[SELF DEBUGGER] No issues detected"]
        )

    def last_check(self):
        return self.last_run or "[SELF DEBUGGER] Never executed"


class ANVELSelfOptimizer:
    def __init__(self):
        self.metrics = []

    def log_performance(self, score):
        self.metrics.append(score)
        self.metrics.pop(0) if len(self.metrics) > 50 else None
        return f"[OPTIMIZER] Logged:{score}"

    def trend(self):
        return (
            "[OPTIMIZER] No data"
            if not self.metrics
            else f"[OPTIMIZER] Δ:{self.metrics[-1] - self.metrics[0]:.2f}"
        )


class ANVELPerformanceMonitor:
    def __init__(self):
        self.records = []

    def start(self):
        self.begin = time.time()
        return "[PERF] Started"

    def stop(self, label):
        elapsed = time.time() - self.begin
        self.records.append({"label": label, "time": elapsed})
        return f"[PERF] {label}: {elapsed:.4f}s"

    def summary(self):
        return self.records or "[PERF] No data"


class ANVELTelemetryBridge:
    def __init__(self):
        self.channels = {}
        self.metrics = {}
        self.buffers = defaultdict(list)
        self.replay = defaultdict(lambda: deque(maxlen=200))
        self.lock = threading.RLock()

    def attach(
        self,
        name,
        handler,
        monitor=False,
        batch_window=0,
        max_batch=1,
        compression=None,
        replay_depth=0,
    ):
        self.channels[name] = {
            "handler": handler,
            "monitor": monitor,
            "batch_window": batch_window,
            "max_batch": max_batch,
            "compression": compression,
            "replay_depth": replay_depth,
            "last_flush": time.time(),
        }
        self.metrics[name] = {"count": 0, "errors": 0, "last_error": None}
        return f"[TELEMETRY] Attached: {name}"

    def transmit(self, name, payload, meta=None):
        if name not in self.channels:
            return "[TELEMETRY] No channel"
        meta = meta or {}
        envelope = {
            "payload": payload,
            "meta": {**meta, "timestamp": meta.get("timestamp") or time.time()},
        }
        with self.lock:
            channel = self.channels[name]
            buffer = self.buffers[name]
            buffer.append(envelope)
            if len(buffer) >= channel["max_batch"] or (
                channel["batch_window"]
                and time.time() - channel["last_flush"] >= channel["batch_window"]
            ):
                return self._flush(name)
        return "[TELEMETRY] Buffered"

    def _flush(self, name):
        channel = self.channels[name]
        buffer = self.buffers[name]
        if not buffer:
            return "[TELEMETRY] No data"
        payload = buffer.copy()
        buffer.clear()
        channel["last_flush"] = time.time()
        blob = json.dumps(payload)
        if channel["compression"] == "zlib":
            blob = zlib.compress(blob.encode())
        try:
            result = channel["handler"](blob)
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            self.metrics[name]["errors"] += 1
            self.metrics[name]["last_error"] = str(exc)
            result = f"Error: {exc}"
            status = "error"
        self.metrics[name]["count"] += len(payload)
        if channel["replay_depth"]:
            dq = self.replay[name]
            dq.extend(payload)
            while len(dq) > channel["replay_depth"]:
                dq.popleft()
        if channel["monitor"]:
            return {
                "channel": name,
                "status": status,
                "result": result,
                "batch": len(payload),
                "metrics": self.metrics[name],
            }
        return result

    def flush(self, name=None):
        if name:
            return self._flush(name)
        return {chan: self._flush(chan) for chan in list(self.channels)}

    def replay_stream(self, name, limit=10):
        if name not in self.replay:
            return []
        dq = self.replay[name]
        return list(dq)[-limit:]

    def stats(self, name=None):
        if name:
            return self.metrics.get(name, {})
        return self.metrics


class ANVELMetricDashboard:
    def __init__(self, ledger=None, summary=None):
        self.ledger = ledger
        self.summary = summary

    def metrics(self):
        data = {}
        if self.ledger:
            data["operations"] = len(getattr(self.ledger, "records", []))
        if self.summary:
            data["pnl"] = getattr(self.summary, "total_pnl", lambda: "n/a")()
        return data

    def display(self):
        return f"[DASHBOARD] {self.metrics()}"


class ANVELNetworkPulse:
    def __init__(self, threshold=200):
        self.log = []
        self.metrics = {}
        self.threshold = threshold

    def ping(self, source, latency, meta=None):
        ts = time.ctime()
        record = {"source": source, "latency": latency, "time": ts, "meta": meta}
        self.log.append(record)
        self.metrics[source] = latency
        return (
            f"[NET PULSE] ALERT: {source} high latency {latency}ms"
            if latency > self.threshold
            else f"[NET PULSE] OK: {source} {latency}ms"
        )

    def average_latency(self, sources=None):
        sources = sources or list(self.metrics.keys())
        vals = [self.metrics[s] for s in sources if s in self.metrics]
        return (
            "[NET PULSE] No data"
            if not vals
            else f"[NET PULSE] Avg: {sum(vals) / len(vals):.2f}ms"
        )

    def trend(self, source):
        vals = [r["latency"] for r in self.log if r["source"] == source]
        return vals[-5:] if len(vals) else f"[NET PULSE] No history for {source}"


class ANVELIntegrityMonitor:
    def __init__(self):
        self.baselines = {}

    def record(self, k, data):
        import hashlib

        h = hashlib.sha256(data.encode()).hexdigest()
        self.baselines[k] = h
        return f"[INTG]{k}:{h[:10]}"

    def scan(self, k, live):
        import hashlib

        lh = hashlib.sha256(live.encode()).hexdigest()
        return "[INTG]OK" if self.baselines.get(k) == lh else "[INTG]BAD"


class AnvelMonitoring:
    """Aggregate monitoring facade for quick use."""

    def __init__(self, timeout=60, interval=10, summary_provider=None):
        self.watchdog = ANVELWatchdog(timeout=timeout)
        self.heartbeat = ANVELHeartbeatMonitor(interval=interval)
        self.health = ANVELHealthMonitor()
        self.perf = ANVELPerformanceMonitor()
        self.dashboard = ANVELMetricDashboard(
            ledger=self.perf,
            summary=summary_provider,
        )
        self._summary_provider = summary_provider
        self.active = False

    def attach_summary_provider(self, provider):
        self._summary_provider = provider
        self.dashboard = ANVELMetricDashboard(
            ledger=self.perf,
            summary=provider,
        )
        return "[MON] Summary provider attached"

    def startup(self):
        self.active = True
        self.perf.start()
        return "[MON] started"

    def shutdown(self):
        self.active = False
        return self.perf.stop("monitoring")

    def status(self):
        metrics_snapshot = self.dashboard.metrics()
        return {
            "watchdog": self.watchdog.get_status(),
            "heartbeat": self.heartbeat.get_status(),
            "health": self.health.summary(),
            "metrics": metrics_snapshot,
        }
