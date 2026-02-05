import threading
import time


class ANVELWatchdog:
    def __init__(self, timeout=60):
        self.timeout = timeout
        self.last_ping = time.time()
        self.status = "OK"
        self.lock = threading.Lock()
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


class AnvelWatchdog(ANVELWatchdog):
    """Concrete watchdog with lifecycle."""

    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.active = False

    def startup(self):
        self.active = True
        return self.get_status()

    def shutdown(self):
        self.active = False
        return "[WATCHDOG] stopped"
