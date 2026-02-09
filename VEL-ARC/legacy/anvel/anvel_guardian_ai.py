import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional


class ThreatIntelMesh:
    """Aggregates threat feeds and enriches guardian decisions."""

    def __init__(self, default_ttl: int = 3600):
        self._feeds: Dict[str, Dict[str, Any]] = {}
        self._indicator_index: Dict[str, List[str]] = defaultdict(list)
        self._default_ttl = default_ttl

    def ingest_feed(
        self,
        name: str,
        indicators: Iterable[Any],
        confidence: float = 0.6,
        ttl: Optional[int] = None,
    ) -> str:
        if not name:
            raise ValueError("Feed name required")
        expires = time.time() + (ttl or self._default_ttl)
        payload: List[Dict[str, Any]] = []
        for entry in indicators:
            normalized = self._normalize_indicator(entry)
            if not normalized:
                continue
            payload.append(normalized)
            self._indicator_index[normalized["fingerprint"]].append(name)
        self._feeds[name] = {
            "confidence": max(0.0, min(1.0, confidence)),
            "expires": expires,
            "indicators": payload,
        }
        return f"[INTEL] Feed {name} ingested ({len(payload)} indicators)"

    def evaluate(self, source: str, description: str) -> Dict[str, Any]:
        self._purge_expired()
        if not self._feeds:
            return {"score": 0.0, "confidence": 0.0, "matches": []}
        matches: List[Dict[str, Any]] = []
        for feed_name, feed in self._feeds.items():
            for indicator in feed["indicators"]:
                if indicator["match_fn"](source, description):
                    match = {
                        "feed": feed_name,
                        "indicator": indicator["raw"],
                        "confidence": feed["confidence"],
                    }
                    matches.append(match)
        if not matches:
            return {"score": 0.0, "confidence": 0.0, "matches": []}
        avg_conf = sum(m["confidence"] for m in matches) / len(matches)
        score = min(1.0, avg_conf + len(matches) * 0.1)
        return {"score": score, "confidence": avg_conf, "matches": matches}

    def snapshot(self) -> Dict[str, Any]:
        self._purge_expired()
        return {
            name: {
                "confidence": meta["confidence"],
                "expires_in": max(0.0, meta["expires"] - time.time()),
                "indicators": len(meta["indicators"]),
            }
            for name, meta in self._feeds.items()
        }

    def _normalize_indicator(self, entry: Any) -> Optional[Dict[str, Any]]:
        if entry is None:
            return None
        if isinstance(entry, str):
            token = entry.strip().lower()
            if not token:
                return None
            return {
                "raw": entry,
                "fingerprint": token,
                "match_fn": lambda src, desc, t=token: t in src.lower()
                or t in desc.lower(),
            }
        if isinstance(entry, dict):
            token = (entry.get("value") or "").strip().lower()
            if not token:
                return None
            tags = entry.get("tags") or []

            def matcher(
                src: str,
                desc: str,
                keyword: str = token,
                tagset=tags,
            ):
                base_hit = keyword in src.lower() or keyword in desc.lower()
                if not tagset:
                    return base_hit
                return base_hit or any(t.lower() in desc.lower() for t in tagset)

            return {
                "raw": entry,
                "fingerprint": token,
                "match_fn": matcher,
            }
        return None

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [name for name, meta in self._feeds.items() if meta["expires"] <= now]
        for name in expired:
            del self._feeds[name]


class ANVELGuardianAI:
    def __init__(self):
        self.threats_detected = []
        self.threat_index = defaultdict(int)
        self.blocked_vectors = set()
        self.response_threshold = 3
        self.auto_block = True
        self._grants = {}
        self.intel_mesh = ThreatIntelMesh()

    def ingest_intel(self, name, indicators, confidence=0.6, ttl=None):
        return self.intel_mesh.ingest_feed(name, indicators, confidence, ttl)

    def detect(self, source, description, severity="medium"):
        timestamp = time.ctime()
        intel = self.intel_mesh.evaluate(source, description)
        escalation = 1 + int(intel["score"] * 2)
        self.threat_index[source] += escalation
        intel_note = (
            f"intel={len(intel['matches'])} feeds" if intel["matches"] else "intel=none"
        )
        if intel["confidence"] > 0.75 and severity != "critical":
            severity = "critical"
        log = {
            "source": source,
            "desc": description,
            "severity": severity,
            "time": timestamp,
            "intel": intel,
        }
        self.threats_detected.append(log)
        if self.auto_block and self.threat_index[source] >= self.response_threshold:
            self.blocked_vectors.add(source)
            return (
                f"[GUARDIAN AI] BLOCKED: {source} after "
                f"{self.threat_index[source]} threats ({intel_note})"
            )
        return (
            f"[GUARDIAN AI] Logged threat from {source}: {description} "
            f"({severity}) {intel_note}"
        )

    def audit(self, limit=5):
        if not self.threats_detected:
            return ["[GUARDIAN AI] No threats logged"]
        return self.threats_detected[-limit:]

    def is_blocked(self, source):
        return source in self.blocked_vectors

    def unblock(self, source):
        self.blocked_vectors.discard(source)
        return f"[GUARDIAN AI] {source} unblocked"

    # Access control used in tests
    def grant(self, user: str, token: str) -> str:
        ok = token.startswith("\u03a9") or token in ("authorized", "valid")
        self._grants[user] = bool(ok)
        return "[SEC]OK" if ok else "[SEC]NO"

    def status(self, user: str) -> bool:
        return bool(self._grants.get(user, False))

    def intel_status(self):
        return self.intel_mesh.snapshot()


class AnvelGuardianAi(ANVELGuardianAI):
    """Concrete guardian with lifecycle hooks."""

    def __init__(self):
        super().__init__()
        self.active = False

    def startup(self):
        self.active = True
        return "[GUARDIAN AI] armed"

    def shutdown(self):
        self.active = False
        return "[GUARDIAN AI] disarmed"
