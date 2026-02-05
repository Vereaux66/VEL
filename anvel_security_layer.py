import hashlib
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Sequence


class ANVELSecurityLayer:
    """Threat tracker plus zero-trust access control for ANVEL runtime."""

    def __init__(self, payout_tracker: Optional[Any] = None):
        self.threats_detected: List[Dict[str, Any]] = []
        self.threat_index: Dict[str, int] = defaultdict(int)
        self.blocked_vectors: set[str] = set()
        self.response_threshold = 3
        self.auto_block = True
        self._lock = threading.RLock()

        # Zero Trust Gate state
        self._fingerprint_hash: Optional[str] = None
        self._max_attempts = 3
        self._failed_attempts: Deque[float] = deque(maxlen=10)
        self._gate_locked = False
        self._access_log: List[Dict[str, Any]] = []

        # Fraud detection linkage
        self._payout_tracker = payout_tracker
        self._fraud_flags: Deque[Dict[str, Any]] = deque(maxlen=50)

    # ------------------------------------------------------------------
    # Threat intelligence
    # ------------------------------------------------------------------
    def detect(
        self,
        source: str,
        description: str,
        severity: str = "medium",
    ) -> str:
        """Record a threat. Auto-block repeat offenders when enabled."""
        if not source or not description:
            raise ValueError("source and description are required for threat logging")
        severity = severity.lower()
        timestamp = time.ctime()
        with self._lock:
            self.threat_index[source] += 1
            log = {
                "source": source,
                "description": description,
                "severity": severity,
                "time": timestamp,
            }
            self.threats_detected.append(log)
            blocked = False
            if self.auto_block and self.threat_index[source] >= self.response_threshold:
                self.blocked_vectors.add(source)
                blocked = True
        if blocked:
            logging.warning(
                "[SECURITY] Source %s blocked after %s events",
                source,
                self.threat_index[source],
            )
            return (
                f"[SECURITY] BLOCKED: {source} after "
                f"{self.threat_index[source]} threats"
            )
        logging.info(
            "[SECURITY] Threat logged from %s: %s",
            source,
            description,
        )
        return f"[SECURITY] Logged threat from {source}: {description} " f"({severity})"

    def audit(self, limit: int = 5) -> List[Dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            if not self.threats_detected:
                return [{"message": "[SECURITY] No threats logged"}]
            return list(self.threats_detected[-limit:])

    def is_blocked(self, source: str) -> bool:
        with self._lock:
            return source in self.blocked_vectors

    def unblock(self, source: str) -> str:
        with self._lock:
            self.blocked_vectors.discard(source)
        logging.info("[SECURITY] Source %s manually unblocked", source)
        return f"[SECURITY] {source} unblocked"

    # ------------------------------------------------------------------
    # Zero Trust Access Gate
    # ------------------------------------------------------------------
    def register_fingerprint(self, fingerprint: str) -> str:
        if not fingerprint:
            raise ValueError("fingerprint cannot be empty")
        with self._lock:
            self._fingerprint_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
            self._failed_attempts.clear()
            self._gate_locked = False
            self._access_log.clear()
        logging.info("[ZERO TRUST] Fingerprint registered")
        return "[ZERO TRUST] Fingerprint registered"

    def attempt_access(self, fingerprint: str) -> str:
        if not fingerprint:
            raise ValueError("fingerprint cannot be empty")
        with self._lock:
            if self._gate_locked:
                return "[ZERO TRUST] Gate is locked. Access denied."
            if not self._fingerprint_hash:
                return "[ZERO TRUST] No fingerprint registered"
            hashed = hashlib.sha256(fingerprint.encode()).hexdigest()
            timestamp = time.ctime()
            if hashed == self._fingerprint_hash:
                self._access_log.append(
                    {
                        "time": timestamp,
                        "status": "granted",
                    }
                )
                self._failed_attempts.clear()
                return "[ZERO TRUST] Access granted"
            self._failed_attempts.append(time.time())
            self._access_log.append({"time": timestamp, "status": "denied"})
            if len(self._failed_attempts) >= self._max_attempts:
                self._gate_locked = True
                logging.error(
                    "[ZERO TRUST] Gate locked after %s failures",
                    self._max_attempts,
                )
                return "[ZERO TRUST] Max attempts exceeded. Gate locked."
            return (
                f"[ZERO TRUST] Access denied ("
                f"{len(self._failed_attempts)} failed attempts)"
            )

    def override_unlock(self, master_passphrase: str) -> str:
        if not master_passphrase:
            raise ValueError("master_passphrase cannot be empty")
        hashed = hashlib.sha256(master_passphrase.encode()).hexdigest()
        with self._lock:
            if hashed.startswith("00"):
                self._gate_locked = False
                self._failed_attempts.clear()
                logging.warning("[ZERO TRUST] Gate unlocked via override")
                return "[ZERO TRUST] Gate manually unlocked by override"
        logging.error("[ZERO TRUST] Unlock attempt failed")
        return "[ZERO TRUST] Unlock failed"

    def audit_zero_trust(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            if not self._access_log:
                return [{"message": "[ZERO TRUST] No access attempts logged"}]
            return list(self._access_log[-limit:])

    # ------------------------------------------------------------------
    # Fraud detection
    # ------------------------------------------------------------------
    def link_payout_tracker(self, tracker: Any) -> str:
        if tracker is None or not hasattr(tracker, "recent"):
            raise ValueError("tracker must expose a recent(limit) method")
        with self._lock:
            self._payout_tracker = tracker
        logging.info("[SECURITY] Payout tracker linked for fraud detection")
        return "[SECURITY] Payout tracker linked"

    def scan_for_fraud(
        self,
        lookback: int = 50,
        threshold: float = 1000.0,
    ) -> List[Dict[str, Any]]:
        if lookback <= 0 or threshold <= 0:
            raise ValueError("lookback and threshold must be positive values")
        tracker = self._payout_tracker
        if tracker is None:
            raise RuntimeError("Payout tracker not configured; cannot run fraud scan")
        try:
            recent: Sequence[Any] = tracker.recent(lookback)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to retrieve payout history: {exc}")
        aggregates: Dict[str, float] = defaultdict(float)
        for record in recent:
            if not isinstance(record, dict):
                continue
            source = str(record.get("source") or "unknown")
            amount = float(record.get("amount") or 0.0)
            aggregates[source] += amount
        suspicious = [
            {"source": src, "total": total}
            for src, total in aggregates.items()
            if total >= threshold
        ]
        with self._lock:
            for entry in suspicious:
                entry["time"] = time.ctime()
                self._fraud_flags.append(entry)
        if suspicious:
            logging.warning("[SECURITY] Fraud flags raised: %s", suspicious)
        return suspicious or []

    def recent_fraud_flags(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            return list(self._fraud_flags[-limit:])
