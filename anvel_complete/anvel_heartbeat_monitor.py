import threading
import time


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


class AnvelHeartbeatMonitor(ANVELHeartbeatMonitor):
    """Concrete heartbeat monitor with lifecycle."""

    def __init__(self, interval=10):
        super().__init__(interval=interval)
        self.active = False

    def startup(self):
        self.active = True
        return self.get_status()

    def shutdown(self):
        self.active = False
        return "[HEARTBEAT] stopped"
