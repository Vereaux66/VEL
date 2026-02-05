import importlib
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class ANVELAutomatedUpdater:
    """System-wide automated maintenance and update coordinator.
    - Periodic self-checks and backups
    - EventBus integration (system.update channel)
    - Manual and scheduled task execution
    - Graceful lifecycle (startup/shutdown)
    """

    def __init__(
        self, scheduler=None, event_bus=None, brain=None, health=None, memory=None
    ):
        self.scheduler = scheduler  # optional external scheduler iface
        self.bus = event_bus
        self.brain = brain
        self.health = health
        self.memory = memory
        self._tasks: List[Dict[str, Any]] = (
            []
        )  # [{'fn':callable,'interval':sec,'next':ts,'name':str}]
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # Lifecycle
    def startup(self):
        # Subscribe to update channel
        if self.bus:
            self.bus.subscribe("system.update", self._on_update_event)
        # Default periodic tasks
        self.schedule_update(self._task_health_snapshot, 300, name="health-snapshot")
        self.schedule_update(self._task_housekeeping, 900, name="housekeeping")
        self._start_loop()
        return "[UPDATER] started"

    def shutdown(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        return "[UPDATER] stopped"

    # Scheduling
    def schedule_update(self, fn: Callable, interval: int, name: str = "task"):
        if self.scheduler and hasattr(self.scheduler, "schedule"):
            return self.scheduler.schedule(fn, interval)
        now = time.time()
        self._tasks.append(
            {
                "fn": fn,
                "interval": int(interval),
                "next": now + int(interval),
                "name": name,
            }
        )
        return f"[UPDATER] Scheduled {name} every {interval}s"

    def run_manual(self, fn: Callable):
        try:
            res = fn()
            return (
                f"[UPDATER] Manual update successful: {res}"
                if res is not None
                else "[UPDATER] Manual update successful"
            )
        except Exception as e:
            return f"[UPDATER] Error: {e}"

    def health_check(self):
        status = {"status": "ok", "time": time.ctime()}
        if self.health and hasattr(self.health, "summary"):
            try:
                status["health"] = self.health.summary()
            except Exception as e:
                status["health_error"] = str(e)
        return status

    # Event handling
    def _on_update_event(self, payload: Dict[str, Any]):
        action = (payload or {}).get("action", "check")
        if action == "check":
            result = self._perform_check()
        elif action == "backup":
            result = self._perform_backup()
        elif action == "apply":
            result = self._perform_apply(payload.get("modules"))
        elif action == "upgrade":
            result = self._perform_upgrade(payload)
        elif action == "diagnose":
            result = self._perform_diagnose()
        else:
            result = {"status": "unknown_action", "action": action}
        # Publish result
        if self.bus:
            self.bus.publish(
                "system.events",
                {"module": "updater", "intent": action, "result": result},
            )
        return result

    # Internal loop
    def _start_loop(self):
        def loop():
            while not self._stop.is_set():
                now = time.time()
                for t in self._tasks:
                    if now >= t["next"]:
                        try:
                            t["fn"]()
                        except Exception:
                            import logging as _lg  # noqa: E402
                            _lg.getLogger("ANVEL_AUTOMATED_UPDATER").debug("Exception suppressed in loop")
                        finally:
                            t["next"] = now + t["interval"]
                self._stop.wait(1.0)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    # Periodic tasks
    def _task_health_snapshot(self):
        snap = self.health_check()
        if self.memory and hasattr(self.memory, "remember"):
            try:
                self.memory.remember(json.dumps(snap), tag="updater", scope="health")
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_AUTOMATED_UPDATER").debug("Exception suppressed in _task_health_snapshot")

    def _task_housekeeping(self):
        # Ensure backups dir exists
        os.makedirs("backups", exist_ok=True)
        # Trim old logs/backups lightly (keep last 50 backups)
        try:
            backs = sorted(
                [
                    f
                    for f in os.listdir("backups")
                    if f.endswith(".json") or f.endswith(".txt")
                ]
            )
            excess = len(backs) - 50
            for f in backs[:excess]:
                try:
                    os.remove(os.path.join("backups", f))
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_AUTOMATED_UPDATER").debug("Exception suppressed in _task_housekeeping")
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_AUTOMATED_UPDATER").debug("Exception suppressed in _task_housekeeping")

    # Actions
    def _perform_check(self) -> Dict[str, Any]:
        result = {
            "time": time.ctime(),
            "health": self.health_check(),
        }
        return {"status": "ok", "data": result}

    def _perform_backup(self) -> Dict[str, Any]:
        os.makedirs("backups", exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = os.path.join("backups", f"updater_backup_{ts}.txt")
        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"ANVEL backup marker {ts}\n")
            return {"status": "ok", "file": fname}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _perform_apply(self, modules: Optional[List[str]] = None) -> Dict[str, Any]:
        # Best-effort module reload without external network
        applied = []
        errors = []
        targets = modules or [
            m for m in list(importlib.sys.modules.keys()) if m.startswith("anvel_")
        ]
        for m in targets:
            try:
                mod = importlib.import_module(m)
                importlib.reload(mod)
                applied.append(m)
            except Exception as e:
                errors.append({m: str(e)})
        status = "ok" if not errors else "partial"
        return {"status": status, "reloaded": applied, "errors": errors}

    def _perform_upgrade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upgrade packages via pip strictly (no fallbacks)."""
        import subprocess
        import sys

        req = (
            payload.get("requirements", "requirements.txt")
            if payload
            else "requirements.txt"
        )
        args = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            "-r",
            req,
        ]
        try:
            cp = subprocess.run(args, capture_output=True, text=True, timeout=900)
            success = cp.returncode == 0
            out = (cp.stdout + "\n" + cp.stderr).strip()[:4000]
            return {"status": "ok" if success else "error", "output": out}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _perform_diagnose(self) -> Dict[str, Any]:
        """Run diagnostic_report in-process and summarize."""
        try:
            import diagnostic_report as dr

            diag = dr.ANVELDiagnostic()
            results = diag.run_full_diagnostic()
            summary = {
                "modules": len(results),
                "failures": [k for k, v in results.items() if not v.get("import_ok")],
            }
            if self.memory and hasattr(self.memory, "remember"):
                try:
                    self.memory.remember(
                        json.dumps({"diagnostic": summary, "time": time.ctime()}),
                        tag="updater",
                        scope="diagnostic",
                    )
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_AUTOMATED_UPDATER").debug("Exception suppressed in _perform_diagnose")
            return {"status": "ok", "summary": summary}
        except Exception as e:
            return {"status": "error", "error": str(e)}
