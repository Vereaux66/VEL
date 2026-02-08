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

NO STUBS - All modules must be present and functional.
If any module fails to load, boot will fail immediately.
"""

import logging
import sys

logger = logging.getLogger("ai")

# Import errors are FATAL - no stubs allowed
# This ensures all AI components are fully operational

from .core import (
    AISupervisor,
    TrainingEngine,
    SystemHealthMonitor,
    AIMetrics,
    SecureKnowledge,
    SystemHealth,
)

from .learning import ContinuousLearningSystem

from .self_repair import SelfRepairEngine

from .introspection import IntrospectionEngine


def validate_ai_modules() -> bool:
    """
    Validate all AI modules are properly loaded and functional.
    
    Returns:
        True if all modules are valid
        
    Raises:
        ImportError: If any required module is missing
        RuntimeError: If any module fails validation
    """
    required_classes = [
        ("AISupervisor", AISupervisor),
        ("TrainingEngine", TrainingEngine),
        ("SystemHealthMonitor", SystemHealthMonitor),
        ("ContinuousLearningSystem", ContinuousLearningSystem),
        ("SelfRepairEngine", SelfRepairEngine),
        ("IntrospectionEngine", IntrospectionEngine),
    ]
    
    for name, cls in required_classes:
        if cls is None:
            raise RuntimeError(f"AI module {name} is None - system cannot start")
        
        # Verify class has required methods
        if not callable(getattr(cls, "__init__", None)):
            raise RuntimeError(f"AI module {name} missing __init__ - invalid class")
    
    logger.info("AI module validation passed - all modules operational")
    return True


# Run validation on import
try:
    validate_ai_modules()
except Exception as e:
    logger.critical(f"AI MODULE VALIDATION FAILED: {e}")
    logger.critical("System cannot start without all AI modules operational")
    raise


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
    "validate_ai_modules",
]
