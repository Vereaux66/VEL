import threading
import time
import uuid
from collections import deque


class TaskPipeline:
    """Lightweight asynchronous task pipeline with SLA tracking."""

    def __init__(self, max_workers=4):
        self._queue = deque()
        self._results = {}
        self._metrics = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "sla_violations": 0,
        }
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._max_workers = max_workers
        self._active = True
        self._shutdown_event = threading.Event()
        self._workers = [
            threading.Thread(target=self._worker, daemon=True)
            for _ in range(max_workers)
        ]
        for worker in self._workers:
            worker.start()

    def shutdown(self, timeout=30):
        """
        Gracefully shutdown the task pipeline.

        Args:
            timeout: Maximum time to wait for workers to finish (seconds)

        Returns:
            True if clean shutdown, False if forced termination
        """
        with self._cv:
            self._active = False
            self._cv.notify_all()

        # Wait for workers to finish
        start = time.time()
        for worker in self._workers:
            remaining = max(0, timeout - (time.time() - start))
            worker.join(timeout=remaining)
            if worker.is_alive():
                # Worker didn't finish in time
                return False

        self._shutdown_event.set()
        return True

    def submit(self, task, context=None, sla_seconds=None, retries=0):
        task_id = str(uuid.uuid4())
        job = {
            "id": task_id,
            "task": task,
            "context": context or {},
            "sla": sla_seconds,
            "retries": retries,
            "submitted": time.time(),
        }
        with self._cv:
            self._queue.append(job)
            self._metrics["submitted"] += 1
            self._cv.notify()
        return task_id

    def await_result(self, task_id, timeout=None):
        deadline = time.time() + timeout if timeout else None
        with self._cv:
            while task_id not in self._results:
                if deadline and time.time() >= deadline:
                    return {"status": "timeout", "id": task_id}
                self._cv.wait(timeout=0.1)
            return self._results[task_id]

    def peek(self, task_id):
        with self._lock:
            return self._results.get(task_id)

    def metrics(self):
        with self._lock:
            return dict(self._metrics)

    def _worker(self):
        while self._active:
            with self._cv:
                while not self._queue and self._active:
                    self._cv.wait()
                if not self._active:
                    return
                job = self._queue.popleft()
            self._execute(job)

    def _execute(self, job):
        started = time.time()
        remaining = job["retries"] + 1
        last_error = None
        while remaining:
            try:
                result = job["task"](job["context"])
                duration = time.time() - started
                record = {
                    "id": job["id"],
                    "status": "ok",
                    "result": result,
                    "duration": duration,
                }
                if job["sla"] and duration > job["sla"]:
                    self._metrics["sla_violations"] += 1
                self._finalize(record)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                remaining -= 1
        record = {"id": job["id"], "status": "error", "error": last_error}
        self._finalize(record, failed=True)

    def _finalize(self, record, failed=False):
        with self._cv:
            self._results[record["id"]] = record
            if failed:
                self._metrics["failed"] += 1
            else:
                self._metrics["completed"] += 1
            self._cv.notify_all()


class ANVELSystemOrchestrator:
    def __init__(self, modules=None):
        self._module_specs = []
        self._module_index = {}
        self._last_launch_order = []
        self._workflows = {}
        self._task_pipeline = TaskPipeline()
        if modules:
            for entry in modules:
                self.add_module(entry)

    def add_module(self, entry):
        spec = self._normalize_entry(entry)
        name = spec["name"]
        self._module_specs.append(spec)
        self._module_index[name] = spec
        return name

    def _normalize_entry(self, entry):
        if isinstance(entry, dict):
            module = entry.get("module")
            name = (
                entry.get("name")
                or getattr(
                    module,
                    "__class__",
                    type("X", (), {}),
                ).__name__
            )
            depends_on = entry.get("depends_on") or entry.get("deps") or []
        else:
            module = entry
            name = module.__class__.__name__
            depends_on = []
        return {
            "name": name,
            "module": module,
            "depends_on": list(depends_on),
        }

    def _resolve_order(self):
        visited = {}
        order = []

        def visit(name):
            if name in visited:
                if visited[name] == "visiting":
                    raise RuntimeError(f"Dependency cycle detected at {name}")
                return
            visited[name] = "visiting"
            spec = self._module_index.get(name)
            if not spec:
                raise RuntimeError(
                    f"Unknown module '{name}' referenced in dependencies"
                )
            for dep in spec["depends_on"]:
                visit(dep)
            visited[name] = "visited"
            order.append(name)

        for spec in self._module_specs:
            visit(spec["name"])
        return order

    def launch_all(self):
        results = {}
        launched = set()
        try:
            order = self._resolve_order()
        except RuntimeError as exc:
            return {"orchestrator": f"error: {exc}"}
        self._last_launch_order = order
        for name in order:
            spec = self._module_index[name]
            missing = [dep for dep in spec["depends_on"] if dep not in launched]
            if missing:
                results[name] = f"blocked: missing {', '.join(missing)}"
                continue
            module = spec["module"]
            try:
                if hasattr(module, "startup"):
                    module.startup()
                results[name] = "launched"
                launched.add(name)
            except Exception as exc:  # noqa: BLE001
                results[name] = f"error: {exc}"
        return results

    def shutdown_all(self):
        results = {}
        order = self._last_launch_order or [spec["name"] for spec in self._module_specs]
        for name in reversed(order):
            module = self._module_index[name]["module"]
            try:
                if hasattr(module, "shutdown"):
                    module.shutdown()
                results[name] = "stopped"
            except Exception as exc:  # noqa: BLE001
                results[name] = f"error: {exc}"
        return results

    # ------------------------------------------------------------------
    # Workflow engine
    # ------------------------------------------------------------------
    def register_workflow(self, name, steps):
        if not name or not isinstance(steps, list) or not steps:
            raise ValueError("Workflow name and steps are required")
        for step in steps:
            if "task" not in step:
                raise ValueError("Each workflow step must define a task")
        self._workflows[name] = steps
        return name

    def run_workflow(self, name, context=None):
        if name not in self._workflows:
            raise ValueError(f"Workflow '{name}' not found")
        context = context or {}
        history = []
        for idx, step in enumerate(self._workflows[name]):
            task = step["task"]
            condition = step.get("condition")
            if condition and not condition(context):
                history.append({"task": task.__name__, "status": "skipped"})
                continue
            mode = step.get("mode")
            if mode == "async":
                task_id = self._task_pipeline.submit(
                    task,
                    context=context,
                    sla_seconds=step.get("sla"),
                    retries=step.get("retries", 0),
                )
                history.append(
                    {
                        "task": task.__name__,
                        "status": "queued",
                        "task_id": task_id,
                    }
                )
                continue
            if mode == "await":
                awaited = self._task_pipeline.await_result(
                    step.get("task_id"),
                    timeout=step.get("timeout"),
                )
                history.append(
                    {
                        "task": task.__name__,
                        "status": awaited.get("status", "unknown"),
                        "result": awaited,
                    }
                )
                continue
            try:
                result = task(context)
                history.append(
                    {
                        "task": task.__name__,
                        "status": "ok",
                        "result": result,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                history.append(
                    {
                        "task": task.__name__,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                break
        return history

    def enqueue_task(self, task, context=None, sla_seconds=None, retries=0):
        return self._task_pipeline.submit(
            task,
            context=context,
            sla_seconds=sla_seconds,
            retries=retries,
        )

    def task_status(self, task_id):
        return self._task_pipeline.peek(task_id)

    def task_metrics(self):
        return self._task_pipeline.metrics()


class AnvelSystemOrchestrator(ANVELSystemOrchestrator):
    """Concrete orchestrator supporting basic lifecycle."""

    def __init__(self, modules=None):
        super().__init__(modules)

    def startup(self):
        return self.launch_all()

    def shutdown(self):
        return self.shutdown_all()
