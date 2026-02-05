#!/usr/bin/env python3
"""
VEL AI Introspection Module
===========================

This module provides comprehensive introspection capabilities for the VEL system.

**CRITICAL: This module has NO EXECUTION AUTHORITY**

Purpose:
    - System state observation and aggregation
    - Performance tracking and historical analysis
    - Metric fusion and unified system views
    - Audit trail and action reconstruction
    - Self-awareness and reflection capabilities

What this module IS:
    - Read-only observation layer
    - Diagnostic and analysis tool
    - Historical record keeper
    - Performance monitor

What this module IS NOT:
    - Trade execution system
    - Autonomous decision maker
    - System behavior modifier
    - Capital-affecting component

All outputs are observational and diagnostic only.
No methods in this module execute trades or modify live system behavior.
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vel.ai.introspection")


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ReflectionEntry:
    """Structured reflection entry for self-reflection system"""

    timestamp: float
    insight: str
    sentiment: float
    category: str
    performance_impact: Optional[float] = None
    action_taken: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateEvent:
    """Structured event for system state tracking"""

    subsystem: str
    state: str
    timestamp: float
    time_str: str
    salience: float
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionEvent:
    """Structured event for action tracking"""

    action: str
    context: Dict[str, Any]
    timestamp: float
    time_str: str


# ============================================================================
# SystemStateAggregator - Consciousness Replacement
# ============================================================================


class SystemStateAggregator:
    """
    Aggregates state from subsystems and provides unified views.
    
    **NO EXECUTION AUTHORITY** - This is a read-only observation layer.
    
    Tracks:
        - Subsystem health and status
        - State transitions and timeline
        - System awareness and focus
        - Anomalies and alerts
    
    Does NOT:
        - Execute trades
        - Modify system behavior
        - Make autonomous decisions
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize the system state aggregator.
        
        Args:
            max_events: Maximum events to retain in memory
        """
        self.events: deque = deque(maxlen=max_events)
        self.max_events = max_events
        self.count_by_subsystem: Dict[str, int] = defaultdict(int)
        self.count_by_state: Dict[str, int] = defaultdict(int)
        self.last_state: Dict[str, str] = {}
        self.salience_history: deque = deque(maxlen=1000)
        self.focus_stack: List[str] = []
        self.lock = threading.RLock()
        
        logger.info("[SystemStateAggregator] Initialized - NO EXECUTION AUTHORITY")

    def log_state(
        self, subsystem: str, state: str = "alive", meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a state observation from a subsystem.
        
        **OBSERVATION ONLY** - Does not affect system behavior.
        
        Args:
            subsystem: Name of the subsystem
            state: Current state (alive, error, degraded, etc.)
            meta: Optional metadata dictionary
        
        Returns:
            Formatted log string
        """
        with self.lock:
            ts = time.time()
            tstr = time.ctime(ts)
            sal = self._calculate_salience(subsystem, state)
            
            event = StateEvent(
                subsystem=subsystem,
                state=state,
                timestamp=ts,
                time_str=tstr,
                salience=sal,
                meta=meta or {},
            )
            
            self.events.append(event)
            self.count_by_subsystem[subsystem] += 1
            self.count_by_state[state] += 1
            self.last_state[subsystem] = state
            self.salience_history.append(sal)
            
            return f"[StateAggregator] {subsystem}:{state}@{tstr} (Salience:{sal:.2f})"

    def get_recent_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get the most recent state events.
        
        Args:
            limit: Number of recent events to retrieve
        
        Returns:
            List of event dictionaries
        """
        with self.lock:
            if not self.events:
                return [{"message": "No events recorded"}]
            
            recent = list(self.events)[-limit:]
            return [
                {
                    "subsystem": e.subsystem,
                    "state": e.state,
                    "time": e.time_str,
                    "timestamp": e.timestamp,
                    "salience": e.salience,
                    "meta": e.meta,
                }
                for e in recent
            ]

    def get_timeline(
        self, start_ts: float = 0, end_ts: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get events within a specific time window.
        
        Args:
            start_ts: Start timestamp (default: 0)
            end_ts: End timestamp (default: now)
        
        Returns:
            List of events in the time window
        """
        end_ts = end_ts or time.time()
        
        with self.lock:
            filtered = [
                {
                    "subsystem": e.subsystem,
                    "state": e.state,
                    "timestamp": e.timestamp,
                    "time": e.time_str,
                    "salience": e.salience,
                    "meta": e.meta,
                }
                for e in self.events
                if start_ts <= e.timestamp <= end_ts
            ]
            return filtered

    def get_window(self, seconds: int = 300) -> List[Dict[str, Any]]:
        """
        Get events from the last N seconds.
        
        Args:
            seconds: Time window in seconds
        
        Returns:
            List of events in the window
        """
        now = time.time()
        with self.lock:
            return [
                {
                    "subsystem": e.subsystem,
                    "state": e.state,
                    "timestamp": e.timestamp,
                    "time": e.time_str,
                    "salience": e.salience,
                    "meta": e.meta,
                }
                for e in self.events
                if now - e.timestamp <= seconds
            ]

    def get_summary(self, limit: int = 10) -> Dict[str, Any]:
        """
        Get a summary of system state.
        
        Args:
            limit: Number of top items to include
        
        Returns:
            Summary dictionary with aggregated statistics
        """
        with self.lock:
            top_subs = sorted(
                self.count_by_subsystem.items(), key=lambda x: x[1], reverse=True
            )[:limit]
            top_states = sorted(
                self.count_by_state.items(), key=lambda x: x[1], reverse=True
            )[:limit]
            avg_sal = (
                sum(self.salience_history) / len(self.salience_history)
                if self.salience_history
                else 0.0
            )
            
            return {
                "top_subsystems": top_subs,
                "top_states": top_states,
                "avg_salience": round(avg_sal, 2),
                "current_focus": self.get_current_focus(),
                "total_events": len(self.events),
                "subsystems_tracked": len(self.count_by_subsystem),
            }

    def get_anomalies(self, seconds: int = 300) -> List[Dict[str, Any]]:
        """
        Detect anomalous states in recent history.
        
        Anomalies include error states, failures, alerts, or high salience events.
        
        Args:
            seconds: Time window to check
        
        Returns:
            List of anomalous events
        """
        window = self.get_window(seconds)
        
        issues = [
            e
            for e in window
            if e["state"].lower() in ("error", "fail", "alert", "panic", "degraded")
            or e.get("salience", 0) > 0.9
        ]
        
        return issues[-10:]  # Last 10 anomalies

    def focus_on(self, subsystem: str) -> str:
        """
        Set focus on a specific subsystem for analysis.
        
        **OBSERVATION ONLY** - Does not change system behavior.
        
        Args:
            subsystem: Name of subsystem to focus on
        
        Returns:
            Confirmation string
        """
        with self.lock:
            self.focus_stack.append(subsystem)
            return f"[StateAggregator] Focus→{subsystem}"

    def defocus(self) -> Optional[str]:
        """
        Remove current focus.
        
        Returns:
            Name of subsystem that was focused, or None
        """
        with self.lock:
            return self.focus_stack.pop() if self.focus_stack else None

    def get_current_focus(self) -> Optional[str]:
        """
        Get the currently focused subsystem.
        
        Returns:
            Name of focused subsystem, or None
        """
        with self.lock:
            return self.focus_stack[-1] if self.focus_stack else None

    def get_subsystem_health(self) -> Dict[str, str]:
        """
        Get current health status of all tracked subsystems.
        
        Returns:
            Dictionary mapping subsystem name to current state
        """
        with self.lock:
            return dict(self.last_state)

    def _calculate_salience(self, subsystem: str, state: str) -> float:
        """
        Calculate salience (importance) of a state event.
        
        Salience is based on:
            - State severity (error > warn > ok)
            - Novelty (state change)
            - Recency bias
        
        Args:
            subsystem: Subsystem name
            state: State name
        
        Returns:
            Salience score (0.0 to 1.0)
        """
        # Base weights by state type
        state_weights = {
            "error": 1.0,
            "fail": 0.95,
            "panic": 0.98,
            "warn": 0.7,
            "degraded": 0.6,
            "awake": 0.3,
            "sleep": 0.2,
            "ok": 0.4,
            "alive": 0.4,
            "ready": 0.5,
        }
        
        base = state_weights.get(state.lower(), 0.5)
        
        # Novelty: bonus if state changed
        novelty = (
            0.2
            if self.last_state.get(subsystem) and self.last_state[subsystem] != state
            else 0.0
        )
        
        # Recency bias
        recency = 0.1
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, base + novelty + recency))


# ============================================================================
# SelfReflector - Enhanced from anvel_self_reflector
# ============================================================================


class SelfReflector:
    """
    Advanced self-reflection system for observing and learning from outcomes.
    
    **NO EXECUTION AUTHORITY** - This is an observation and analysis system.
    
    Tracks:
        - System insights and observations
        - Sentiment and performance trends
        - Learning outcomes
        - Historical patterns
    
    Does NOT:
        - Execute trades
        - Autonomously modify system parameters
        - Make capital-affecting decisions
    
    Note: While reflection analysis may suggest actions, this module does NOT
    implement those actions. It only records observations.
    """

    def __init__(self, max_reflections: int = 10000):
        """
        Initialize the self-reflector.
        
        Args:
            max_reflections: Maximum reflections to retain
        """
        self.reflections: deque = deque(maxlen=max_reflections)
        self.sentiment_log: deque = deque(maxlen=1000)
        self.performance_history: deque = deque(maxlen=1000)
        self.insights_by_category: Dict[str, List[ReflectionEntry]] = {}
        self.lock = threading.RLock()
        self.awareness_level: float = 0.0  # 0-1 scale of system self-awareness
        
        logger.info("[SelfReflector] Initialized - NO EXECUTION AUTHORITY")

    def reflect(
        self,
        insight: str,
        sentiment: float = 0.0,
        category: str = "general",
        performance_impact: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record a reflection with analysis.
        
        **OBSERVATION ONLY** - Records observations but does not execute actions.
        
        Args:
            insight: The insight or observation
            sentiment: Sentiment score (-1 to 1, negative=bad, positive=good)
            category: Category of reflection (trading, learning, system, error)
            performance_impact: Measured impact on system performance
            metadata: Additional context
        
        Returns:
            Analysis string (informational only)
        """
        with self.lock:
            entry = ReflectionEntry(
                timestamp=time.time(),
                insight=insight,
                sentiment=sentiment,
                category=category,
                performance_impact=performance_impact,
                metadata=metadata or {},
            )

            # Analyze the reflection (observation only)
            suggested_action = self._analyze_reflection(entry)
            entry.action_taken = suggested_action

            # Store the reflection
            self.reflections.append(entry)
            self.sentiment_log.append(sentiment)

            # Update performance history if provided
            if performance_impact is not None:
                self.performance_history.append(performance_impact)

            # Categorize
            if category not in self.insights_by_category:
                self.insights_by_category[category] = []
            self.insights_by_category[category].append(entry)

            # Update awareness level
            self._update_awareness()

            return (
                f"[Reflector] {insight} | Sentiment: {sentiment:.2f} | "
                f"Suggested: {suggested_action}"
            )

    def _analyze_reflection(self, entry: ReflectionEntry) -> str:
        """
        Analyze reflection and suggest actions (informational only).
        
        **CRITICAL**: This method SUGGESTS actions but does NOT execute them.
        Suggestions are for logging/diagnostic purposes only.
        
        Args:
            entry: Reflection entry to analyze
        
        Returns:
            Suggested action string (informational)
        """
        suggestions = []

        # Sentiment-based observations
        if entry.sentiment < -0.5:
            suggestions.append("Observation: Negative sentiment detected")
            if entry.category == "trading":
                suggestions.append("Suggestion: Consider position size review")
            elif entry.category == "system":
                suggestions.append("Suggestion: System health check recommended")
        elif entry.sentiment > 0.7:
            suggestions.append("Observation: Positive outcome - pattern recorded")

        # Performance-based observations
        if entry.performance_impact is not None:
            if entry.performance_impact < -0.1:
                suggestions.append("Observation: Performance degradation detected")
            elif entry.performance_impact > 0.1:
                suggestions.append("Observation: Performance improvement detected")

        # Category-specific observations
        if entry.category == "error":
            suggestions.append("Observation: Error logged for analysis")
        elif entry.category == "learning":
            suggestions.append("Observation: Learning event recorded")

        return " | ".join(suggestions) if suggestions else "Observation logged"

    def _update_awareness(self):
        """
        Update system's self-awareness level based on reflection quality.
        
        Awareness is calculated from:
            1. Number of reflections (experience)
            2. Diversity of categories (breadth)
            3. Sentiment variance (emotional range)
        """
        with self.lock:
            if len(self.reflections) < 10:
                self.awareness_level = 0.1
                return

            experience_factor = min(1.0, len(self.reflections) / 1000)
            diversity_factor = min(1.0, len(self.insights_by_category) / 10)

            sentiment_variance = (
                stdev(self.sentiment_log) if len(self.sentiment_log) > 1 else 0.0
            )
            emotional_factor = min(1.0, sentiment_variance)

            # Weighted average
            self.awareness_level = (
                0.4 * experience_factor + 0.3 * diversity_factor + 0.3 * emotional_factor
            )

    def get_recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent reflections with full details.
        
        Args:
            limit: Number of recent reflections
        
        Returns:
            List of reflection dictionaries
        """
        with self.lock:
            if not self.reflections:
                return [{"message": "No reflections yet"}]

            recent = list(self.reflections)[-limit:]
            return [
                {
                    "timestamp": time.ctime(r.timestamp),
                    "insight": r.insight,
                    "sentiment": r.sentiment,
                    "category": r.category,
                    "performance_impact": r.performance_impact,
                    "action_taken": r.action_taken,
                    "metadata": r.metadata,
                }
                for r in recent
            ]

    def get_mood(self) -> Dict[str, Any]:
        """
        Get comprehensive mood analysis.
        
        **OBSERVATION ONLY** - Does not affect system behavior.
        
        Returns:
            Mood analysis dictionary
        """
        with self.lock:
            if not self.sentiment_log:
                return {
                    "mood": "neutral",
                    "sentiment_avg": 0.0,
                    "message": "No sentiment data yet",
                }

            avg_sentiment = mean(self.sentiment_log)
            sentiment_trend = self._calculate_trend(list(self.sentiment_log))

            # Determine mood
            if avg_sentiment > 0.5:
                mood = "optimistic"
            elif avg_sentiment > 0:
                mood = "positive"
            elif avg_sentiment > -0.5:
                mood = "cautious"
            else:
                mood = "concerned"

            return {
                "mood": mood,
                "sentiment_avg": avg_sentiment,
                "sentiment_std": (
                    stdev(self.sentiment_log) if len(self.sentiment_log) > 1 else 0.0
                ),
                "trend": sentiment_trend,
                "awareness_level": self.awareness_level,
                "total_reflections": len(self.reflections),
                "categories_tracked": len(self.insights_by_category),
            }

    def _calculate_trend(self, data: List[float]) -> str:
        """
        Calculate trend direction.
        
        Args:
            data: List of numeric values
        
        Returns:
            Trend description (improving/declining/stable)
        """
        if len(data) < 2:
            return "stable"

        # Compare recent half to older half
        mid = len(data) // 2
        older_avg = mean(data[:mid])
        recent_avg = mean(data[mid:])

        diff = recent_avg - older_avg

        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        else:
            return "stable"

    def analyze_category(self, category: str) -> Dict[str, Any]:
        """
        Analyze reflections in a specific category.
        
        Args:
            category: Category to analyze
        
        Returns:
            Category analysis dictionary
        """
        with self.lock:
            if category not in self.insights_by_category:
                return {"error": f"No reflections in category: {category}"}

            entries = self.insights_by_category[category]

            sentiments = [e.sentiment for e in entries]
            avg_sentiment = mean(sentiments)

            impacts = [
                e.performance_impact
                for e in entries
                if e.performance_impact is not None
            ]
            avg_impact = mean(impacts) if impacts else None

            return {
                "category": category,
                "total_entries": len(entries),
                "avg_sentiment": avg_sentiment,
                "avg_performance_impact": avg_impact,
                "recent_insights": [e.insight for e in entries[-5:]],
                "trend": self._calculate_trend(sentiments),
            }

    def get_positive_insights(self, min_sentiment: float = 0.5) -> List[str]:
        """
        Get positive insights that led to good outcomes.
        
        Args:
            min_sentiment: Minimum sentiment threshold
        
        Returns:
            List of positive insights
        """
        with self.lock:
            positive_insights = [
                r.insight for r in self.reflections if r.sentiment >= min_sentiment
            ]
            return positive_insights[-20:]

    def get_warnings(self, max_sentiment: float = -0.3) -> List[str]:
        """
        Get negative insights that indicate problems.
        
        Args:
            max_sentiment: Maximum sentiment threshold
        
        Returns:
            List of warning insights
        """
        with self.lock:
            warnings = [
                r.insight for r in self.reflections if r.sentiment <= max_sentiment
            ]
            return warnings[-10:]

    def generate_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive self-awareness report.
        
        **DIAGNOSTIC ONLY** - Report is for analysis purposes.
        
        Returns:
            Comprehensive report dictionary
        """
        with self.lock:
            mood_data = self.get_mood()

            # Category analysis
            category_summaries = {}
            for category in self.insights_by_category:
                category_summaries[category] = self.analyze_category(category)

            # Performance analysis
            if self.performance_history:
                avg_performance = mean(self.performance_history)
                performance_trend = self._calculate_trend(list(self.performance_history))
            else:
                avg_performance = 0.0
                performance_trend = "unknown"

            return {
                "timestamp": time.time(),
                "awareness_level": self.awareness_level,
                "mood": mood_data,
                "total_reflections": len(self.reflections),
                "categories": category_summaries,
                "performance": {
                    "average": avg_performance,
                    "trend": performance_trend,
                    "samples": len(self.performance_history),
                },
                "top_insights": self.get_positive_insights(),
                "recent_warnings": self.get_warnings(),
            }

    def save(self, filepath: str) -> bool:
        """
        Save reflections to file for persistence.
        
        Args:
            filepath: Path to save file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.lock:
                data = {
                    "reflections": [
                        {
                            "timestamp": r.timestamp,
                            "insight": r.insight,
                            "sentiment": r.sentiment,
                            "category": r.category,
                            "performance_impact": r.performance_impact,
                            "action_taken": r.action_taken,
                            "metadata": r.metadata,
                        }
                        for r in self.reflections
                    ],
                    "awareness_level": self.awareness_level,
                }

                with open(filepath, "w") as f:
                    json.dump(data, f, indent=2)

                logger.info(f"Saved {len(self.reflections)} reflections to {filepath}")
                return True
        except Exception as e:
            logger.error(f"Failed to save reflections: {e}")
            return False

    def load(self, filepath: str) -> bool:
        """
        Load reflections from file.
        
        Args:
            filepath: Path to load from
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            with self.lock:
                for r in data.get("reflections", []):
                    entry = ReflectionEntry(
                        timestamp=r["timestamp"],
                        insight=r["insight"],
                        sentiment=r["sentiment"],
                        category=r["category"],
                        performance_impact=r.get("performance_impact"),
                        action_taken=r.get("action_taken"),
                        metadata=r.get("metadata", {}),
                    )
                    self.reflections.append(entry)
                    self.sentiment_log.append(entry.sentiment)

                    if entry.category not in self.insights_by_category:
                        self.insights_by_category[entry.category] = []
                    self.insights_by_category[entry.category].append(entry)

                self.awareness_level = data.get("awareness_level", 0.0)

            logger.info(f"Loaded {len(data.get('reflections', []))} reflections")
            return True
        except Exception as e:
            logger.error(f"Failed to load reflections: {e}")
            return False

    def purge(self, keep_last: int = 100) -> str:
        """
        Clear old reflections, keeping the most recent.
        
        Args:
            keep_last: Number of recent reflections to keep (0 = clear all)
        
        Returns:
            Status message
        """
        with self.lock:
            if keep_last > 0:
                # Keep last N reflections
                recent = list(self.reflections)[-keep_last:]
                self.reflections.clear()
                self.reflections.extend(recent)

                # Rebuild category index
                self.insights_by_category.clear()
                for entry in self.reflections:
                    if entry.category not in self.insights_by_category:
                        self.insights_by_category[entry.category] = []
                    self.insights_by_category[entry.category].append(entry)

                return f"[Reflector] Purged old reflections, kept last {keep_last}"
            else:
                # Clear everything
                count = len(self.reflections)
                self.reflections.clear()
                self.sentiment_log.clear()
                self.performance_history.clear()
                self.insights_by_category.clear()
                self.awareness_level = 0.0
                return f"[Reflector] Cleared all {count} reflections"


# ============================================================================
# ActionReconstructor - Enhanced from anvel_action_reconstructor
# ============================================================================


class ActionReconstructor:
    """
    Reconstructs action history and provides audit trail.
    
    **NO EXECUTION AUTHORITY** - This is a historical record keeper only.
    
    Tracks:
        - Action history
        - Decision patterns
        - Context and outcomes
    
    Does NOT:
        - Execute actions
        - Replay actions
        - Modify system behavior
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize the action reconstructor.
        
        Args:
            max_events: Maximum events to retain
        """
        self.events: deque = deque(maxlen=max_events)
        self.max_events = max_events
        self.lock = threading.RLock()
        
        logger.info("[ActionReconstructor] Initialized - NO EXECUTION AUTHORITY")

    def capture(
        self, action: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Capture an action event for historical record.
        
        **RECORDING ONLY** - Does not execute or replay actions.
        
        Args:
            action: Action description
            context: Optional context dictionary
        
        Returns:
            Confirmation string
        """
        with self.lock:
            ts = time.time()
            event = ActionEvent(
                action=action,
                context=context or {},
                timestamp=ts,
                time_str=time.ctime(ts),
            )
            self.events.append(event)
            return f"[ActionReconstructor] Captured: {action}"

    def reconstruct(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Reconstruct recent action history.
        
        Args:
            limit: Number of recent actions to retrieve
        
        Returns:
            List of action dictionaries
        """
        with self.lock:
            if not self.events:
                return [{"message": "No actions recorded"}]

            recent = list(self.events)[-limit:]
            return [
                {
                    "action": e.action,
                    "context": e.context,
                    "time": e.time_str,
                    "timestamp": e.timestamp,
                }
                for e in recent
            ]

    def get_action(self, index: int = -1) -> Dict[str, Any]:
        """
        Get a specific action by index.
        
        Args:
            index: Index in event list (default: -1 for most recent)
        
        Returns:
            Action dictionary
        """
        with self.lock:
            if not self.events:
                return {"error": "No actions recorded"}

            try:
                event = self.events[index]
                return {
                    "action": event.action,
                    "context": event.context,
                    "time": event.time_str,
                    "timestamp": event.timestamp,
                }
            except IndexError:
                return {"error": f"Invalid index: {index}"}

    def get_timeline(
        self, start_ts: float = 0, end_ts: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get actions within a specific time window.
        
        Args:
            start_ts: Start timestamp
            end_ts: End timestamp (default: now)
        
        Returns:
            List of actions in the time window
        """
        end_ts = end_ts or time.time()
        
        with self.lock:
            filtered = [
                {
                    "action": e.action,
                    "context": e.context,
                    "time": e.time_str,
                    "timestamp": e.timestamp,
                }
                for e in self.events
                if start_ts <= e.timestamp <= end_ts
            ]
            return filtered

    def analyze_patterns(self) -> Dict[str, Any]:
        """
        Analyze action patterns for insights.
        
        **DIAGNOSTIC ONLY** - Analysis is for observation.
        
        Returns:
            Pattern analysis dictionary
        """
        with self.lock:
            if not self.events:
                return {"message": "No actions to analyze"}

            # Count action types
            action_counts: Dict[str, int] = defaultdict(int)
            for event in self.events:
                action_counts[event.action] += 1

            # Find most common actions
            top_actions = sorted(
                action_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]

            # Calculate event rate
            if len(self.events) >= 2:
                time_span = self.events[-1].timestamp - self.events[0].timestamp
                event_rate = len(self.events) / time_span if time_span > 0 else 0
            else:
                event_rate = 0

            return {
                "total_actions": len(self.events),
                "unique_actions": len(action_counts),
                "top_actions": top_actions,
                "event_rate_per_second": event_rate,
                "time_span_seconds": (
                    self.events[-1].timestamp - self.events[0].timestamp
                    if len(self.events) >= 2
                    else 0
                ),
            }

    def search_actions(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search for actions containing a keyword.
        
        Args:
            keyword: Keyword to search for
        
        Returns:
            List of matching actions
        """
        with self.lock:
            keyword_lower = keyword.lower()
            matches = [
                {
                    "action": e.action,
                    "context": e.context,
                    "time": e.time_str,
                    "timestamp": e.timestamp,
                }
                for e in self.events
                if keyword_lower in e.action.lower()
            ]
            return matches


# ============================================================================
# MetricFusion - Enhanced from anvel_dynamic_fusion
# ============================================================================


class MetricFusion:
    """
    Fuses metrics from multiple sources for unified system view.
    
    **NO EXECUTION AUTHORITY** - This is a metric aggregation system only.
    
    Provides:
        - Metric collection from multiple sources
        - Dynamic metric fusion
        - Unified performance view
        - Historical metric tracking
    
    Does NOT:
        - Execute trades
        - Modify system behavior
        - Make autonomous decisions
    """

    def __init__(self, max_snapshots: int = 1000):
        """
        Initialize the metric fusion system.
        
        Args:
            max_snapshots: Maximum snapshots to retain
        """
        self.snapshots: deque = deque(maxlen=max_snapshots)
        self.max_snapshots = max_snapshots
        self.source_metrics: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        
        logger.info("[MetricFusion] Initialized - NO EXECUTION AUTHORITY")

    def capture_snapshot(
        self, source: str, metrics: Dict[str, Any]
    ) -> str:
        """
        Capture a metric snapshot from a source.
        
        **RECORDING ONLY** - Does not affect system behavior.
        
        Args:
            source: Source identifier
            metrics: Dictionary of metrics
        
        Returns:
            Confirmation string
        """
        with self.lock:
            snapshot = {
                "source": source,
                "metrics": metrics,
                "timestamp": time.time(),
                "time_str": time.ctime(),
            }
            self.snapshots.append(snapshot)
            self.source_metrics[source] = metrics
            return f"[MetricFusion] Captured snapshot from {source}"

    def fuse_metrics(self) -> Dict[str, Any]:
        """
        Fuse metrics from all sources into a unified view.
        
        **READ-ONLY** - Returns aggregated view without side effects.
        
        Returns:
            Fused metrics dictionary
        """
        with self.lock:
            if not self.source_metrics:
                return {"message": "No metrics to fuse"}

            fused = {
                "timestamp": time.time(),
                "sources": list(self.source_metrics.keys()),
                "metrics": {},
            }

            # Merge all source metrics
            for source, metrics in self.source_metrics.items():
                for key, value in metrics.items():
                    # Prefix keys with source to avoid collisions
                    fused_key = f"{source}.{key}"
                    fused["metrics"][fused_key] = value

            return fused

    def get_source_metrics(self, source: str) -> Dict[str, Any]:
        """
        Get metrics from a specific source.
        
        Args:
            source: Source identifier
        
        Returns:
            Metrics dictionary or error
        """
        with self.lock:
            if source not in self.source_metrics:
                return {"error": f"No metrics from source: {source}"}
            return dict(self.source_metrics[source])

    def get_recent_snapshots(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent metric snapshots.
        
        Args:
            limit: Number of recent snapshots
        
        Returns:
            List of snapshot dictionaries
        """
        with self.lock:
            if not self.snapshots:
                return [{"message": "No snapshots recorded"}]

            recent = list(self.snapshots)[-limit:]
            return recent

    def get_metric_history(
        self, metric_key: str, source: Optional[str] = None
    ) -> List[Tuple[float, Any]]:
        """
        Get historical values for a specific metric.
        
        Args:
            metric_key: Metric key to track
            source: Optional source filter
        
        Returns:
            List of (timestamp, value) tuples
        """
        with self.lock:
            history = []
            
            for snapshot in self.snapshots:
                if source and snapshot["source"] != source:
                    continue
                
                metrics = snapshot["metrics"]
                if metric_key in metrics:
                    history.append((snapshot["timestamp"], metrics[metric_key]))
            
            return history

    def calculate_metric_stats(
        self, metric_key: str, source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate statistics for a metric over its history.
        
        Args:
            metric_key: Metric to analyze
            source: Optional source filter
        
        Returns:
            Statistics dictionary
        """
        history = self.get_metric_history(metric_key, source)
        
        if not history:
            return {"error": f"No history for metric: {metric_key}"}
        
        values = [v for _, v in history if isinstance(v, (int, float))]
        
        if not values:
            return {"error": f"No numeric values for metric: {metric_key}"}
        
        return {
            "metric": metric_key,
            "source": source or "all",
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": mean(values),
            "std": stdev(values) if len(values) > 1 else 0.0,
            "current": values[-1],
        }

    def get_all_sources(self) -> List[str]:
        """
        Get list of all metric sources.
        
        Returns:
            List of source identifiers
        """
        with self.lock:
            return list(self.source_metrics.keys())

    def clear_source(self, source: str) -> str:
        """
        Clear metrics from a specific source.
        
        Args:
            source: Source to clear
        
        Returns:
            Status message
        """
        with self.lock:
            if source in self.source_metrics:
                del self.source_metrics[source]
                return f"[MetricFusion] Cleared metrics from {source}"
            else:
                return f"[MetricFusion] No metrics from {source}"


# ============================================================================
# Exports and Module Initialization
# ============================================================================


__all__ = [
    "SystemStateAggregator",
    "SelfReflector",
    "ActionReconstructor",
    "MetricFusion",
    "ReflectionEntry",
    "StateEvent",
    "ActionEvent",
]

logger.info("VEL AI Introspection module loaded - NO EXECUTION AUTHORITY")
