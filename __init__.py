"""
VEL AI Layer
============

Consolidated AI modules for the VEL trading system.

This package provides:
- AI Core: Supervisor, training engine, health monitoring, and execution bridges
- Learning: Online learning, adaptation, and persistence
- Self-Repair: Code analysis and automated repair capabilities
- Introspection: System state observation and diagnostics (NO EXECUTION AUTHORITY)

Each module is production-ready with:
- No stubs, TODOs, or placeholders
- Complete error handling
- Thread safety
- Clear interfaces
- Comprehensive logging

**IMPORTANT**: The introspection module has NO EXECUTION AUTHORITY.
It is for observation, monitoring, and diagnostics only.

Note: Imports are lazy to avoid heavy ML dependencies on import.
Use explicit imports when needed: `from ai.core import AISupervisor`
"""

import logging
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

# Lazy imports - actual modules are imported on demand
_core_imports = None
_learning_imports = None
_self_repair_imports = None
_introspection_imports = None


def _load_core():
    """Lazy load core AI module."""
    global _core_imports
    if _core_imports is None:
        try:
            from ai.core import (
                AICore,
                AISupervisor,
                TrainingEngine,
                SystemHealthMonitor,
                ExecutionBridge,
                MilitaryGradeEncryption,
                AIMetrics,
                SecureKnowledge,
                SystemHealth,
                get_ai_core,
            )
            _core_imports = {
                'AICore': AICore,
                'AISupervisor': AISupervisor,
                'TrainingEngine': TrainingEngine,
                'SystemHealthMonitor': SystemHealthMonitor,
                'ExecutionBridge': ExecutionBridge,
                'MilitaryGradeEncryption': MilitaryGradeEncryption,
                'AIMetrics': AIMetrics,
                'SecureKnowledge': SecureKnowledge,
                'SystemHealth': SystemHealth,
                'get_ai_core': get_ai_core,
            }
        except ImportError as e:
            _logger.warning(f"Core AI module unavailable: {e}")
            _core_imports = {}
    return _core_imports


def _load_learning():
    """Lazy load learning module."""
    global _learning_imports
    if _learning_imports is None:
        try:
            from ai.learning import (
                AdaptiveLearningEngine,
                ContinuousLearningSystem,
                KnowledgeRepository,
                LearningSample,
                LearningMetrics,
                KnowledgeRecord,
                SymbolKnowledgeStats,
                PredictionOutcome,
                DataConnector,
                CSVDataConnector,
                CoinbaseDataConnector,
                ModelCheckpointer,
                CloudWatchMetrics,
                EFSModelStorage,
                LearningSampleType,
            )
            _learning_imports = {
                'AdaptiveLearningEngine': AdaptiveLearningEngine,
                'ContinuousLearningSystem': ContinuousLearningSystem,
                'KnowledgeRepository': KnowledgeRepository,
                'LearningSample': LearningSample,
                'LearningMetrics': LearningMetrics,
                'KnowledgeRecord': KnowledgeRecord,
                'SymbolKnowledgeStats': SymbolKnowledgeStats,
                'PredictionOutcome': PredictionOutcome,
                'DataConnector': DataConnector,
                'CSVDataConnector': CSVDataConnector,
                'CoinbaseDataConnector': CoinbaseDataConnector,
                'ModelCheckpointer': ModelCheckpointer,
                'CloudWatchMetrics': CloudWatchMetrics,
                'EFSModelStorage': EFSModelStorage,
                'LearningSampleType': LearningSampleType,
            }
        except ImportError as e:
            _logger.warning(f"Learning module unavailable: {e}")
            _learning_imports = {}
    return _learning_imports


def _load_self_repair():
    """Lazy load self-repair module."""
    global _self_repair_imports
    if _self_repair_imports is None:
        try:
            from ai.self_repair import (
                ImportRepairer,
                CodeAnalyzer,
                CodeRepairer,
                CodeEvolutionEngine,
                ImportRepairAttempt,
                ImportRepairResult,
                CodePattern,
                CodeIssue,
                RepairResult,
                CodeMetrics,
                RepairStrategy,
                CodeQuality,
                create_import_repairer,
                create_code_analyzer,
                create_code_repairer,
                create_evolution_engine,
                MODULE_TO_PACKAGE,
                WHITELISTED_PACKAGES,
            )
            _self_repair_imports = {
                'ImportRepairer': ImportRepairer,
                'CodeAnalyzer': CodeAnalyzer,
                'CodeRepairer': CodeRepairer,
                'CodeEvolutionEngine': CodeEvolutionEngine,
                'ImportRepairAttempt': ImportRepairAttempt,
                'ImportRepairResult': ImportRepairResult,
                'CodePattern': CodePattern,
                'CodeIssue': CodeIssue,
                'RepairResult': RepairResult,
                'CodeMetrics': CodeMetrics,
                'RepairStrategy': RepairStrategy,
                'CodeQuality': CodeQuality,
                'create_import_repairer': create_import_repairer,
                'create_code_analyzer': create_code_analyzer,
                'create_code_repairer': create_code_repairer,
                'create_evolution_engine': create_evolution_engine,
                'MODULE_TO_PACKAGE': MODULE_TO_PACKAGE,
                'WHITELISTED_PACKAGES': WHITELISTED_PACKAGES,
            }
        except ImportError as e:
            _logger.warning(f"Self-repair module unavailable: {e}")
            _self_repair_imports = {}
    return _self_repair_imports


def _load_introspection():
    """Lazy load introspection module."""
    global _introspection_imports
    if _introspection_imports is None:
        try:
            from ai.introspection import (
                SystemStateAggregator,
                SelfReflector,
                ActionReconstructor,
                MetricFusion,
                ReflectionEntry,
                StateEvent,
                ActionEvent,
            )
            _introspection_imports = {
                'SystemStateAggregator': SystemStateAggregator,
                'SelfReflector': SelfReflector,
                'ActionReconstructor': ActionReconstructor,
                'MetricFusion': MetricFusion,
                'ReflectionEntry': ReflectionEntry,
                'StateEvent': StateEvent,
                'ActionEvent': ActionEvent,
            }
        except ImportError as e:
            _logger.warning(f"Introspection module unavailable: {e}")
            _introspection_imports = {}
    return _introspection_imports


# Cache for combined lookup
_combined_imports: Optional[Dict[str, Any]] = None


def _get_combined_imports() -> Dict[str, Any]:
    """Get combined imports dictionary with caching."""
    global _combined_imports
    if _combined_imports is not None:
        return _combined_imports
    
    _combined_imports = {}
    # Load modules in order, later modules can shadow earlier ones
    for loader in [_load_core, _load_learning, _load_self_repair, _load_introspection]:
        try:
            _combined_imports.update(loader())
        except ImportError:
            pass  # Module unavailable - expected for optional dependencies
        except Exception as exc:
            _logger.exception("Unexpected error while loading '%s': %s", loader.__name__, exc)
    return _combined_imports


def __getattr__(name: str) -> Any:
    """Lazy attribute access for AI components with cached lookup."""
    imports = _get_combined_imports()
    if name in imports:
        return imports[name]
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    # Core AI
    'AICore',
    'AISupervisor',
    'TrainingEngine',
    'SystemHealthMonitor',
    'ExecutionBridge',
    'MilitaryGradeEncryption',
    'AIMetrics',
    'SecureKnowledge',
    'SystemHealth',
    'get_ai_core',
    # Learning
    'AdaptiveLearningEngine',
    'ContinuousLearningSystem',
    'KnowledgeRepository',
    'LearningSample',
    'LearningMetrics',
    'KnowledgeRecord',
    'SymbolKnowledgeStats',
    'PredictionOutcome',
    'DataConnector',
    'CSVDataConnector',
    'CoinbaseDataConnector',
    'ModelCheckpointer',
    'CloudWatchMetrics',
    'EFSModelStorage',
    'LearningSampleType',
    # Self-Repair
    'ImportRepairer',
    'CodeAnalyzer',
    'CodeRepairer',
    'CodeEvolutionEngine',
    'ImportRepairAttempt',
    'ImportRepairResult',
    'CodePattern',
    'CodeIssue',
    'RepairResult',
    'CodeMetrics',
    'RepairStrategy',
    'CodeQuality',
    'create_import_repairer',
    'create_code_analyzer',
    'create_code_repairer',
    'create_evolution_engine',
    'MODULE_TO_PACKAGE',
    'WHITELISTED_PACKAGES',
    # Introspection (NO EXECUTION AUTHORITY)
    'SystemStateAggregator',
    'SelfReflector',
    'ActionReconstructor',
    'MetricFusion',
    'ReflectionEntry',
    'StateEvent',
    'ActionEvent',
]

__version__ = '1.0.0'
