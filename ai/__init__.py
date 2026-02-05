#!/usr/bin/env python3
"""
ANVEL AI Package
================

Consolidated AI functionality for the ANVEL trading system.

Modules:
- core: AI Supervisor, Training Engine, System Health
- learning: Continuous Learning System
- self_repair: Self-repair and Auto-healing
- introspection: System introspection and analysis
"""

import logging

# Core imports with fallback for missing dependencies
try:
    from .core import (
        AISupervisor,
        TrainingEngine,
        SystemHealthMonitor,
        AIMetrics,
        SecureKnowledge,
        SystemHealth,
    )
except ImportError as e:
    logging.getLogger("ai").warning(f"Core AI module import error: {e}")
    
    # Provide stubs
    class AISupervisor:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def stop(self): pass
    
    class TrainingEngine:
        def __init__(self, **kwargs): pass
    
    class SystemHealthMonitor:
        def __init__(self, **kwargs): pass

try:
    from .learning import ContinuousLearningSystem
except ImportError:
    class ContinuousLearningSystem:
        def __init__(self, **kwargs): pass

try:
    from .self_repair import SelfRepairEngine
except ImportError:
    class SelfRepairEngine:
        def __init__(self, **kwargs): pass

try:
    from .introspection import IntrospectionEngine
except ImportError:
    class IntrospectionEngine:
        def __init__(self, **kwargs): pass


__all__ = [
    "AISupervisor",
    "TrainingEngine",
    "SystemHealthMonitor",
    "AIMetrics",
    "SecureKnowledge",
    "SystemHealth",
    "ContinuousLearningSystem",
    "SelfRepairEngine",
    "IntrospectionEngine",
]
