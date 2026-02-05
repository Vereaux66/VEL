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
"""

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

from ai.introspection import (
    SystemStateAggregator,
    SelfReflector,
    ActionReconstructor,
    MetricFusion,
    ReflectionEntry,
    StateEvent,
    ActionEvent,
)

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
