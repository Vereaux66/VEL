from collections import defaultdict, Counter, deque
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError

logger = logging.getLogger(__name__)


class ANVELEventBus:
    def __init__(
        self,
        *,
        max_workers: int = 8,
        dispatch_timeout: float = 2.0,
        max_history: int = 10000,
    ):
        self.subscribers = defaultdict(list)
        self.event_log = deque(maxlen=max_history)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._dispatch_timeout = dispatch_timeout
        self._subscriptions = {}
        for channel in (
            "brain.commands",
            "trade.signals",
            "system.events",
            "system.update",
            "system.supervisor",
            "system.alerts",
        ):
            self.subscribers.setdefault(channel, [])

    def subscribe(self, channel, callback):
        token = f"{channel}:{uuid.uuid4().hex}"
        with self._lock:
            self.subscribers[channel].append((token, callback))
            self._subscriptions[token] = channel
        return token

    def bind(self, topic, handler):
        return self.subscribe(topic, handler)

    def register(self, channel, fn):
        return self.subscribe(channel, fn)

    def unsubscribe(self, token: str):
        if not token:
            return False
        with self._lock:
            channel = self._subscriptions.pop(token, None)
            if not channel:
                return False
            callbacks = self.subscribers.get(channel, [])
            self.subscribers[channel] = [
                entry for entry in callbacks if entry[0] != token
            ]
        return True

    def _invoke(self, callback, payload):
        try:
            return callback(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Event subscriber error: %s", exc)
            return f"Error: {exc}"

    def publish(self, channel, payload):
        timestamp = time.ctime()
        with self._lock:
            self.event_log.append((channel, payload, timestamp))
            callbacks = list(self.subscribers.get(channel, []))
        try:
            logger.debug(
                "publish channel=%s payload=%s",
                channel,
                str(payload)[:500],
            )
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_EVENT_BUS").debug("Exception suppressed in publish")
        if not callbacks:
            return f"[EVENT BUS] No subscribers on '{channel}'"
        responses = []
        for token, cb in callbacks:
            future = self._executor.submit(self._invoke, cb, payload)
            try:
                responses.append(future.result(timeout=self._dispatch_timeout))
            except TimeoutError:
                responses.append(f"Error: timeout waiting for subscriber {token}")
            except Exception as exc:  # noqa: BLE001
                responses.append(f"Error: {exc}")
        return responses

    def dispatch(self, topic, payload):
        return self.publish(topic, payload)

    def emit(self, channel, sig):
        return self.publish(channel, sig)

    def history(self, limit=5):
        if not self.event_log:
            return ["[EVENT BUS] No events"]
        return list(self.event_log)[-limit:]

    def close(self):
        with self._lock:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_EVENT_BUS").debug("Exception suppressed in close")
        return "[EVENT BUS] executor closed"


class ANVELSignalFilter:
    def __init__(self, min_score=0.5):
        self.min_score = min_score
        self.accepted = []
        self.rejected = []

    def filter(self, signal, score):
        entry = {"signal": signal, "score": score}
        if score >= self.min_score:
            self.accepted.append(entry)
            return "[FILTER] Accepted"
        self.rejected.append(entry)
        return "[FILTER] Rejected"

    def last_accepted(self, limit=5):
        return self.accepted[-limit:] if self.accepted else ["[FILTER] None"]

    def last_rejected(self, limit=5):
        return self.rejected[-limit:] if self.rejected else ["[FILTER] None"]

    def adjust_threshold(self, new_score):
        self.min_score = new_score
        return f"[FILTER] threshold set to {new_score}"


class ANVELSignalCombiner:
    def __init__(self):
        self._history = []

    def combine(self, signals):
        if not signals:
            return "[COMBINER] No signals"
        counts = Counter(signals)
        dom, ct = counts.most_common(1)[0]
        conf = ct / len(signals)
        self._history.append({"signals": signals, "result": dom, "conf": conf})
        return f"[COMBINER] {dom} conf:{conf:.2f}"

    def history(self, limit=5):
        return self._history[-limit:] if self._history else ["[COMBINER] None"]


class ANVELStreamBuffer:
    def __init__(self, maxlen=100):
        self.buffer = deque(maxlen=maxlen)

    def push(self, data):
        self.buffer.append(data)
        return "[BUFFER] Stored"

    def pop(self):
        return self.buffer.popleft() if self.buffer else None

    def snapshot(self):
        return list(self.buffer)


class ANVELStreamProcessor:
    def __init__(self):
        self.processors = []

    def register(self, fn):
        self.processors.append(fn)
        return "[STREAM] Processor registered"

    def process(self, data_stream):
        for data in data_stream:
            for fn in self.processors:
                data = fn(data)
        return data


class ANVELDataStreamRouter:
    def __init__(self):
        self.routes = {}

    def connect(self, source, handler):
        self.routes[source] = handler
        return f"[DSR] Connected {source}"

    def route(self, source, data):
        fn = self.routes.get(source)
        if fn:
            return fn(data)
        return "[DSR] No route"

    def list_sources(self):
        return list(self.routes.keys())


class AnvelEventBus(ANVELEventBus):
    """Concrete event bus with simple lifecycle."""

    def __init__(self):
        super().__init__()
        self.active = False

    def startup(self):
        self.active = True
        return "[EVENT BUS] started"

    def shutdown(self):
        self.active = False
        self.close()
        return "[EVENT BUS] stopped"
