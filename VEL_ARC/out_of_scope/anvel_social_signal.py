import re
from collections import Counter


class ANVELSocialSignal:
    def __init__(self):
        self.signals = []
        self.keywords = {
            "bullish": ["buy", "moon", "pump", "bullish", "rocket", "long"],
            "bearish": ["sell", "dump", "rug", "bearish", "short"],
        }

    def ingest(self, message):
        sentiment = self._analyze_text(message)
        self.signals.append(sentiment)
        return f"[SOCIAL SIGNAL] Analyzed: {sentiment}"

    def _analyze_text(self, text):
        text = text.lower()
        scores = Counter()
        for category, keywords in self.keywords.items():
            matches = sum(1 for word in keywords if re.search(rf"\b{word}\b", text))
            scores[category] = matches

        if scores["bullish"] > scores["bearish"]:
            return "bullish"
        elif scores["bearish"] > scores["bullish"]:
            return "bearish"
        elif scores["bullish"] == scores["bearish"] and scores["bullish"] > 0:
            return "conflicted"
        return "neutral"

    def recent(self, limit=5):
        return (
            self.signals[-limit:]
            if self.signals
            else ["[SOCIAL SIGNAL] No recent signals"]
        )
