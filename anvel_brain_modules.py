"""Lightweight brain submodules extracted from the experimental phase.

These helpers keep `anvel_brain.py` slimmer while preserving the
behaviour of the AI shell, context router, and related bridges that were
previously archived. Each class is intentionally simple so it can be used
independently during testing or diagnostics.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import random


class ANVELAiShell:
    """Keyword driven command shell used by the brain's CLI hooks."""

    def __init__(self) -> None:
        self._commands: Dict[str, Callable[[str], str]] = {}
        self._context_memory: List[str] = []

    def register_command(self, keyword: str, handler: Callable[[str], str]) -> str:
        if keyword in self._commands:
            raise ValueError(f"Command '{keyword}' already registered")
        self._commands[keyword] = handler
        return f"[AI SHELL] Registered command: {keyword}"

    def interpret(self, text: str) -> str:
        self._context_memory.append(text)
        for keyword, handler in self._commands.items():
            if keyword.lower() in text.lower():
                try:
                    return handler(text)
                except Exception as exc:  # noqa: BLE001
                    return f"[AI SHELL] Error in '{keyword}': {exc}"
        return "[AI SHELL] No matching command found"

    def memories(self, limit: int = 5) -> List[str]:
        return self._context_memory[-limit:]


class ANVELContextRouter:
    """Routes context payloads to the first compatible handler."""

    def __init__(self) -> None:
        self._routes: Dict[str, Callable[[Dict[str, str]], str]] = {}

    def add_route(
        self, context_key: str, handler: Callable[[Dict[str, str]], str]
    ) -> str:
        self._routes[context_key] = handler
        return f"[ROUTER] Route: {context_key}"

    def route(self, context: Dict[str, str]) -> str:
        for key, fn in self._routes.items():
            if key in context:
                return fn(context)
        return "[ROUTER] No route"


class ANVELLanguageBridge:
    """Minimal vocabulary translator."""

    def __init__(self) -> None:
        self._vocab: Dict[str, str] = {}

    def learn_word(self, word: str, meaning: str) -> str:
        self._vocab[word] = meaning
        return f"[LANGUAGE] Learned: {word}"

    def translate(self, text: str) -> str:
        return " ".join(self._vocab.get(token, token) for token in text.split())


class ANVELEmotionMatrix:
    """Tracks labelled emotion intensities for operator dashboards."""

    def __init__(self) -> None:
        self._emotions: Dict[str, List[float]] = defaultdict(list)

    def log_emotion(self, label: str, intensity: float) -> str:
        self._emotions[label].append(float(intensity))
        return f"[EMOTION] {label}: {intensity}"

    def dominant_emotion(self) -> str:
        if not self._emotions:
            return "[EMOTION] None"
        averages = {
            label: sum(values) / len(values) for label, values in self._emotions.items()
        }
        dominant = max(averages, key=averages.get)
        return f"[EMOTION] Dominant: {dominant}"

    def snapshot(self) -> Dict[str, float]:
        return {
            label: sum(values) / len(values) for label, values in self._emotions.items()
        }


class ANVELIntuitionEngine:
    """Produces fast heuristics for qualitative topics."""

    def __init__(self) -> None:
        self._profile: Dict[str, float] = {}

    def generate(self, topic: str, bias: Optional[int] = None) -> str:
        seed = hash(topic) + (bias if bias is not None else random.randint(1, 99))
        signal = (seed % 1000) / 1000
        self._profile[topic] = signal
        return f"[INTUITION] {topic} conf: {signal:.3f}"

    def reflect(self, topic: str) -> str:
        return (
            f"[INTUITION] {topic} conf: {self._profile[topic]:.3f}"
            if topic in self._profile
            else "[INTUITION] No insight"
        )


class ANVELThoughtMap:
    """Stores lightweight knowledge graphs."""

    def __init__(self) -> None:
        self._concepts: Dict[str, str] = {}
        self._links: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    def add_concept(self, label: str, definition: str) -> str:
        self._concepts[label] = definition
        return f"[THOUGHT MAP] Concept '{label}' added"

    def link(self, source: str, target: str, relationship: str) -> str:
        self._links[source].append((target, relationship))
        return f"[THOUGHT MAP] Linked '{source}' -> '{target}' as '{relationship}'"

    def define(self, label: str) -> str:
        return self._concepts.get(label, "[THOUGHT MAP] Unknown concept")

    def trace(self, label: str) -> List[Tuple[str, str]]:
        return self._links.get(label, [("[THOUGHT MAP]", f"No links for '{label}'")])


class ANVELNeuroForge:
    """Simple statistical learner kept for diagnostics."""

    def __init__(self) -> None:
        self._models: Dict[str, Dict[str, float]] = {}

    def learn(self, label: str, data: Iterable[float]) -> str:
        values = [float(v) for v in data]
        if len(values) < 2:
            return "[NEURO] Insufficient samples"
        self._models[label] = {"mean": mean(values), "stdev": pstdev(values)}
        return f"[NEURO] Learned '{label}'"

    def predict(self, label: str, value: float) -> str:
        model = self._models.get(label)
        if not model:
            return "[NEURO] No model"
        diff = abs(model["mean"] - float(value))
        confidence = max(0.0, 1.0 - (diff / (model["stdev"] + 1e-5)))
        return f"[NEURO] {label} conf:{confidence:.2f}"


@dataclass
class BrainSubsystems:
    """Convenience container used when exporting subsystem state."""

    shell: ANVELAiShell = field(default_factory=ANVELAiShell)
    context_router: ANVELContextRouter = field(default_factory=ANVELContextRouter)
    language_bridge: ANVELLanguageBridge = field(default_factory=ANVELLanguageBridge)
    emotion_matrix: ANVELEmotionMatrix = field(default_factory=ANVELEmotionMatrix)
    intuition_engine: ANVELIntuitionEngine = field(default_factory=ANVELIntuitionEngine)
    thought_map: ANVELThoughtMap = field(default_factory=ANVELThoughtMap)
    legacy_neuro_forge: ANVELNeuroForge = field(default_factory=ANVELNeuroForge)

    def snapshot(self) -> Dict[str, object]:
        return {
            "shell_commands": list(self.shell._commands.keys()),
            "context_routes": list(self.context_router._routes.keys()),
            "vocabulary": list(self.language_bridge._vocab.keys()),
            "emotions": self.emotion_matrix.snapshot(),
            "intuition_topics": list(self.intuition_engine._profile.keys()),
            "concepts": list(self.thought_map._concepts.keys()),
            "legacy_models": list(self.legacy_neuro_forge._models.keys()),
        }
