"""
VEL Financial Knowledge Graph & Neuro-Symbolic Reasoning Engine

Phase 5 Implementation:
- Financial Knowledge Graph for relationship modeling
- Neuro-Symbolic Reasoning for explainable decisions
- Event impact propagation through graph
- Rule extraction from learned models

Author: VEL AI Enhancement Roadmap
"""

import logging
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================================
# Core Data Structures
# ============================================================================


class RelationType(Enum):
    """Types of relationships in the knowledge graph."""

    # Market relationships
    CORRELATED_WITH = "correlated_with"
    INVERSELY_CORRELATED = "inversely_correlated"
    LEADS = "leads"  # Entity1 leads Entity2 in price movement
    LAGS = "lags"

    # Fundamental relationships
    BACKED_BY = "backed_by"  # Stablecoins backed by reserves
    PEGGED_TO = "pegged_to"
    FORK_OF = "fork_of"
    LAYER_2_OF = "layer_2_of"

    # Ecosystem relationships
    BUILT_ON = "built_on"  # Token built on blockchain
    COMPETES_WITH = "competes_with"
    PARTNERS_WITH = "partners_with"
    ACQUIRED_BY = "acquired_by"

    # Causal relationships
    CAUSES = "causes"
    AFFECTS = "affects"
    MITIGATES = "mitigates"
    AMPLIFIES = "amplifies"

    # Temporal relationships
    PRECEDES = "precedes"
    FOLLOWS = "follows"
    COINCIDES_WITH = "coincides_with"


class EntityType(Enum):
    """Types of entities in the knowledge graph."""

    CRYPTOCURRENCY = "cryptocurrency"
    BLOCKCHAIN = "blockchain"
    EXCHANGE = "exchange"
    PROTOCOL = "protocol"
    TOKEN = "token"
    STABLECOIN = "stablecoin"
    NFT_COLLECTION = "nft_collection"
    DAO = "dao"
    WHALE = "whale"
    INSTITUTION = "institution"
    COUNTRY = "country"
    REGULATION = "regulation"
    EVENT = "event"
    INDICATOR = "indicator"
    SENTIMENT = "sentiment"


@dataclass
class Entity:
    """An entity in the knowledge graph."""

    id: str
    name: str
    entity_type: EntityType
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Entity):
            return self.id == other.id
        return False


@dataclass
class Relationship:
    """A relationship between two entities."""

    source_id: str
    relation_type: RelationType
    target_id: str
    weight: float = 1.0  # Strength of relationship
    confidence: float = 1.0  # Confidence in the relationship
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # Some relationships are temporal

    @property
    def id(self) -> str:
        """Unique identifier for this relationship."""
        return f"{self.source_id}-{self.relation_type.value}-{self.target_id}"

    def is_valid(self) -> bool:
        """Check if relationship is still valid."""
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True


@dataclass
class Rule:
    """A symbolic rule for reasoning."""

    id: str
    name: str
    condition: str  # Logical condition
    action: str  # Action to take
    confidence: float = 1.0
    priority: int = 0  # Higher priority rules execute first
    enabled: bool = True

    def __hash__(self):
        return hash(self.id)


@dataclass
class Inference:
    """Result of reasoning/inference."""

    conclusion: str
    confidence: float
    supporting_facts: List[str]
    rule_chain: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================================
# Financial Knowledge Graph
# ============================================================================


class FinancialKnowledgeGraph:
    """
    Graph-based knowledge representation for financial entities.

    Features:
    - Entity and relationship storage
    - Pattern matching and querying
    - Event impact propagation
    - Temporal decay of relationships
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Core storage
        self.entities: Dict[str, Entity] = {}
        self.relationships: Dict[str, Relationship] = {}

        # Adjacency lists for efficient traversal
        self.outgoing: Dict[str, Set[str]] = defaultdict(
            set
        )  # entity_id -> relationship_ids
        self.incoming: Dict[str, Set[str]] = defaultdict(
            set
        )  # entity_id -> relationship_ids

        # Indices for fast lookup
        self.entity_by_type: Dict[EntityType, Set[str]] = defaultdict(set)
        self.relationships_by_type: Dict[RelationType, Set[str]] = defaultdict(set)

        # Correlation matrix cache
        self._correlation_cache: Dict[Tuple[str, str], float] = {}
        self._cache_timestamp: datetime = datetime.now()

        # Initialize with common crypto knowledge
        self._initialize_base_knowledge()

    def _initialize_base_knowledge(self):
        """Initialize with common cryptocurrency relationships."""
        # Major cryptocurrencies
        btc = self.add_entity(
            "BTC",
            "Bitcoin",
            EntityType.CRYPTOCURRENCY,
            {"category": "store_of_value", "consensus": "PoW"},
        )
        eth = self.add_entity(
            "ETH",
            "Ethereum",
            EntityType.BLOCKCHAIN,
            {"category": "smart_contract", "consensus": "PoS"},
        )
        usdt = self.add_entity(
            "USDT",
            "Tether",
            EntityType.STABLECOIN,
            {"pegged_value": 1.0, "backing": "fiat"},
        )
        usdc = self.add_entity(
            "USDC",
            "USD Coin",
            EntityType.STABLECOIN,
            {"pegged_value": 1.0, "backing": "fiat"},
        )

        # Common relationships
        self.add_relationship("ETH", RelationType.CORRELATED_WITH, "BTC", weight=0.85)
        self.add_relationship("USDT", RelationType.PEGGED_TO, "USD", weight=1.0)
        self.add_relationship("USDC", RelationType.PEGGED_TO, "USD", weight=1.0)

        # Add USD as reference
        self.add_entity("USD", "US Dollar", EntityType.COUNTRY, {"type": "fiat"})

        logger.info("Initialized base financial knowledge graph")

    def add_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: EntityType,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Entity:
        """Add an entity to the knowledge graph."""
        with self._lock:
            if entity_id in self.entities:
                # Update existing entity
                entity = self.entities[entity_id]
                entity.name = name
                entity.entity_type = entity_type
                if attributes:
                    entity.attributes.update(attributes)
                entity.updated_at = datetime.now()
            else:
                # Create new entity
                entity = Entity(
                    id=entity_id,
                    name=name,
                    entity_type=entity_type,
                    attributes=attributes or {},
                )
                self.entities[entity_id] = entity
                self.entity_by_type[entity_type].add(entity_id)

            return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self.entities.get(entity_id)

    def add_relationship(
        self,
        source_id: str,
        relation_type: RelationType,
        target_id: str,
        weight: float = 1.0,
        confidence: float = 1.0,
        attributes: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[float] = None,
    ) -> Optional[Relationship]:
        """Add a directed relationship between entities."""
        with self._lock:
            # Ensure both entities exist
            if source_id not in self.entities:
                logger.warning(f"Source entity {source_id} not found")
                return None
            if target_id not in self.entities:
                logger.warning(f"Target entity {target_id} not found")
                return None

            # Create relationship
            expires_at = None
            if ttl_hours:
                expires_at = datetime.now() + timedelta(hours=ttl_hours)

            relationship = Relationship(
                source_id=source_id,
                relation_type=relation_type,
                target_id=target_id,
                weight=weight,
                confidence=confidence,
                attributes=attributes or {},
                expires_at=expires_at,
            )

            rel_id = relationship.id
            self.relationships[rel_id] = relationship
            self.outgoing[source_id].add(rel_id)
            self.incoming[target_id].add(rel_id)
            self.relationships_by_type[relation_type].add(rel_id)

            # Invalidate correlation cache
            self._correlation_cache.clear()

            return relationship

    def get_relationships(
        self,
        entity_id: str,
        direction: str = "both",
        relation_type: Optional[RelationType] = None,
    ) -> List[Relationship]:
        """Get relationships for an entity."""
        with self._lock:
            rel_ids = set()

            if direction in ["out", "both"]:
                rel_ids.update(self.outgoing.get(entity_id, set()))
            if direction in ["in", "both"]:
                rel_ids.update(self.incoming.get(entity_id, set()))

            relationships = []
            for rel_id in rel_ids:
                rel = self.relationships.get(rel_id)
                if rel and rel.is_valid():
                    if relation_type is None or rel.relation_type == relation_type:
                        relationships.append(rel)

            return relationships

    def query(self, pattern: str) -> List[Tuple[str, str, str]]:
        """
        Query the knowledge graph with a pattern.

        Patterns:
        - "?entity CORRELATED_WITH BTC" - Find all entities correlated with BTC
        - "ETH ?relation ?entity" - Find all relationships from ETH
        - "?source CAUSES ?target" - Find all causal relationships

        Returns list of (source, relation, target) tuples.
        """
        with self._lock:
            parts = pattern.split()
            if len(parts) != 3:
                logger.warning(f"Invalid pattern: {pattern}")
                return []

            source_pattern, rel_pattern, target_pattern = parts
            results = []

            for rel in self.relationships.values():
                if not rel.is_valid():
                    continue

                # Match source
                if source_pattern != "?source" and source_pattern != "?entity":
                    if rel.source_id != source_pattern:
                        continue

                # Match relation
                if rel_pattern != "?relation":
                    try:
                        expected_rel = RelationType(rel_pattern.lower())
                        if rel.relation_type != expected_rel:
                            continue
                    except ValueError:
                        if rel.relation_type.value != rel_pattern.lower():
                            continue

                # Match target
                if target_pattern != "?target" and target_pattern != "?entity":
                    if rel.target_id != target_pattern:
                        continue

                results.append((rel.source_id, rel.relation_type.value, rel.target_id))

            return results

    def find_path(
        self, source_id: str, target_id: str, max_depth: int = 4
    ) -> Optional[List[str]]:
        """Find shortest path between two entities using BFS."""
        if source_id not in self.entities or target_id not in self.entities:
            return None

        if source_id == target_id:
            return [source_id]

        visited = {source_id}
        queue = [(source_id, [source_id])]

        while queue:
            current, path = queue.pop(0)

            if len(path) > max_depth:
                continue

            # Check outgoing relationships
            for rel_id in self.outgoing.get(current, set()):
                rel = self.relationships.get(rel_id)
                if rel and rel.is_valid():
                    next_entity = rel.target_id
                    if next_entity == target_id:
                        return path + [next_entity]
                    if next_entity not in visited:
                        visited.add(next_entity)
                        queue.append((next_entity, path + [next_entity]))

            # Check incoming relationships (bidirectional search)
            for rel_id in self.incoming.get(current, set()):
                rel = self.relationships.get(rel_id)
                if rel and rel.is_valid():
                    next_entity = rel.source_id
                    if next_entity == target_id:
                        return path + [next_entity]
                    if next_entity not in visited:
                        visited.add(next_entity)
                        queue.append((next_entity, path + [next_entity]))

        return None

    def infer_impact(
        self,
        event: str,
        source_entity: str,
        impact_magnitude: float = 1.0,
        decay_factor: float = 0.7,
        max_depth: int = 3,
    ) -> Dict[str, float]:
        """
        Propagate event impact through the graph.

        Uses relationship weights and decay factor to calculate
        impact on connected entities.
        """
        if source_entity not in self.entities:
            return {}

        impacts = {source_entity: impact_magnitude}
        visited = {source_entity}
        current_layer = [source_entity]

        for depth in range(max_depth):
            next_layer = []
            current_decay = decay_factor**depth

            for entity_id in current_layer:
                current_impact = impacts[entity_id]

                # Propagate through relationships
                for rel_id in self.outgoing.get(entity_id, set()):
                    rel = self.relationships.get(rel_id)
                    if rel and rel.is_valid():
                        target = rel.target_id

                        # Calculate propagated impact
                        # Adjust based on relationship type
                        propagation = self._get_propagation_factor(rel.relation_type)
                        propagated_impact = (
                            current_impact
                            * rel.weight
                            * rel.confidence
                            * propagation
                            * current_decay
                        )

                        if abs(propagated_impact) > 0.01:  # Threshold
                            if target in impacts:
                                impacts[target] = max(
                                    impacts[target], propagated_impact
                                )
                            else:
                                impacts[target] = propagated_impact

                            if target not in visited:
                                visited.add(target)
                                next_layer.append(target)

            current_layer = next_layer
            if not current_layer:
                break

        return impacts

    def _get_propagation_factor(self, relation_type: RelationType) -> float:
        """Get impact propagation factor for relationship type."""
        propagation_factors = {
            RelationType.CORRELATED_WITH: 0.8,
            RelationType.INVERSELY_CORRELATED: -0.8,
            RelationType.LEADS: 0.9,
            RelationType.LAGS: 0.7,
            RelationType.CAUSES: 1.0,
            RelationType.AFFECTS: 0.6,
            RelationType.AMPLIFIES: 1.2,
            RelationType.MITIGATES: -0.5,
            RelationType.BUILT_ON: 0.7,
            RelationType.COMPETES_WITH: -0.3,
            RelationType.PARTNERS_WITH: 0.4,
        }
        return propagation_factors.get(relation_type, 0.5)

    def get_correlated_entities(
        self, entity_id: str, min_correlation: float = 0.5
    ) -> List[Tuple[str, float]]:
        """Get entities correlated with the given entity."""
        results = []

        for rel in self.get_relationships(entity_id, direction="both"):
            if rel.relation_type == RelationType.CORRELATED_WITH:
                other_id = (
                    rel.target_id if rel.source_id == entity_id else rel.source_id
                )
                if rel.weight >= min_correlation:
                    results.append((other_id, rel.weight))

        return sorted(results, key=lambda x: x[1], reverse=True)

    def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a specific type."""
        entity_ids = self.entity_by_type.get(entity_type, set())
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]

    def export_to_json(self) -> str:
        """Export knowledge graph to JSON."""
        data = {
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "type": e.entity_type.value,
                    "attributes": e.attributes,
                }
                for e in self.entities.values()
            ],
            "relationships": [
                {
                    "source": r.source_id,
                    "relation": r.relation_type.value,
                    "target": r.target_id,
                    "weight": r.weight,
                    "confidence": r.confidence,
                }
                for r in self.relationships.values()
                if r.is_valid()
            ],
        }
        return json.dumps(data, indent=2)

    def import_from_json(self, json_str: str):
        """Import knowledge graph from JSON."""
        data = json.loads(json_str)

        # Import entities
        for e in data.get("entities", []):
            self.add_entity(
                e["id"], e["name"], EntityType(e["type"]), e.get("attributes", {})
            )

        # Import relationships
        for r in data.get("relationships", []):
            self.add_relationship(
                r["source"],
                RelationType(r["relation"]),
                r["target"],
                weight=r.get("weight", 1.0),
                confidence=r.get("confidence", 1.0),
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the knowledge graph."""
        valid_rels = sum(1 for r in self.relationships.values() if r.is_valid())
        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
            "valid_relationships": valid_rels,
            "entities_by_type": {
                t.value: len(ids) for t, ids in self.entity_by_type.items() if ids
            },
            "relationships_by_type": {
                t.value: len(ids)
                for t, ids in self.relationships_by_type.items()
                if ids
            },
        }


# ============================================================================
# Neuro-Symbolic Reasoning Engine
# ============================================================================


class SymbolicRuleEngine:
    """
    Rule-based reasoning engine with symbolic logic.

    Combines learned patterns with explicit rules for
    explainable decision making.
    """

    def __init__(self, knowledge_graph: FinancialKnowledgeGraph):
        self.kg = knowledge_graph
        self._lock = threading.RLock()

        # Rule storage
        self.rules: Dict[str, Rule] = {}

        # Fact base (working memory)
        self.facts: Dict[str, Any] = {}

        # Inference history
        self.inference_history: List[Inference] = []

        # Initialize default rules
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        """Initialize default trading rules."""
        # Risk management rules
        self.add_rule(
            Rule(
                id="R001",
                name="correlation_risk",
                condition="portfolio_correlation > 0.8",
                action="reduce_position_overlap",
                confidence=0.9,
                priority=10,
            )
        )

        self.add_rule(
            Rule(
                id="R002",
                name="whale_alert",
                condition="whale_movement > 1000 BTC AND sentiment == 'bearish'",
                action="reduce_exposure",
                confidence=0.85,
                priority=9,
            )
        )

        self.add_rule(
            Rule(
                id="R003",
                name="correlation_breakdown",
                condition="btc_eth_correlation < 0.5 AND historical_correlation > 0.8",
                action="investigate_divergence",
                confidence=0.8,
                priority=8,
            )
        )

        self.add_rule(
            Rule(
                id="R004",
                name="momentum_confirmation",
                condition="price_trend == 'up' AND volume_trend == 'up' AND sentiment > 0.6",
                action="increase_position",
                confidence=0.75,
                priority=5,
            )
        )

        self.add_rule(
            Rule(
                id="R005",
                name="stablecoin_depeg_warning",
                condition="stablecoin_price < 0.98 OR stablecoin_price > 1.02",
                action="emergency_exit_stablecoin",
                confidence=0.95,
                priority=10,
            )
        )

        logger.info(f"Initialized {len(self.rules)} default rules")

    def add_rule(self, rule: Rule):
        """Add a rule to the engine."""
        with self._lock:
            self.rules[rule.id] = rule

    def remove_rule(self, rule_id: str):
        """Remove a rule from the engine."""
        with self._lock:
            self.rules.pop(rule_id, None)

    def set_fact(self, name: str, value: Any):
        """Set a fact in working memory."""
        with self._lock:
            self.facts[name] = value

    def get_fact(self, name: str, default: Any = None) -> Any:
        """Get a fact from working memory."""
        return self.facts.get(name, default)

    def clear_facts(self):
        """Clear all facts from working memory."""
        with self._lock:
            self.facts.clear()

    def evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate a rule condition against context.

        Supports:
        - Comparison operators: >, <, ==, !=, >=, <=
        - Logical operators: AND, OR, NOT
        - Arithmetic: +, -, *, /
        """
        try:
            # Combine facts with context
            env = {**self.facts, **context}

            # Parse and evaluate condition
            # Simple parser for basic conditions
            condition = condition.strip()

            # Handle AND/OR
            if " AND " in condition:
                parts = condition.split(" AND ")
                return all(self.evaluate_condition(p.strip(), context) for p in parts)

            if " OR " in condition:
                parts = condition.split(" OR ")
                return any(self.evaluate_condition(p.strip(), context) for p in parts)

            if condition.startswith("NOT "):
                return not self.evaluate_condition(condition[4:].strip(), context)

            # Handle comparisons
            for op in [">=", "<=", "!=", "==", ">", "<"]:
                if op in condition:
                    left, right = condition.split(op, 1)
                    left_val = self._resolve_value(left.strip(), env)
                    right_val = self._resolve_value(right.strip(), env)

                    if left_val is None or right_val is None:
                        return False

                    if op == ">":
                        return left_val > right_val
                    elif op == "<":
                        return left_val < right_val
                    elif op == ">=":
                        return left_val >= right_val
                    elif op == "<=":
                        return left_val <= right_val
                    elif op == "==":
                        return left_val == right_val
                    elif op == "!=":
                        return left_val != right_val

            # Boolean fact check
            return bool(env.get(condition, False))

        except Exception as e:
            logger.warning(f"Error evaluating condition '{condition}': {e}")
            return False

    def _resolve_value(self, expr: str, env: Dict[str, Any]) -> Any:
        """Resolve a value from expression."""
        expr = expr.strip()

        # String literal
        if expr.startswith("'") and expr.endswith("'"):
            return expr[1:-1]
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]

        # Numeric literal
        try:
            if "." in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_KNOWLEDGE_GRAPH").debug("Exception suppressed in _resolve_value")

        # Variable lookup
        if expr in env:
            return env[expr]

        return None

    def forward_chain(
        self, context: Optional[Dict[str, Any]] = None, max_iterations: int = 100
    ) -> List[Inference]:
        """
        Forward chaining inference.

        Evaluates rules against facts and context, firing
        matching rules and generating new facts.
        """
        context = context or {}
        inferences = []
        fired_rules = set()

        for iteration in range(max_iterations):
            rule_fired = False

            # Sort rules by priority
            sorted_rules = sorted(
                [
                    r
                    for r in self.rules.values()
                    if r.enabled and r.id not in fired_rules
                ],
                key=lambda r: r.priority,
                reverse=True,
            )

            for rule in sorted_rules:
                if self.evaluate_condition(rule.condition, context):
                    # Rule fires
                    inference = Inference(
                        conclusion=rule.action,
                        confidence=rule.confidence,
                        supporting_facts=self._get_supporting_facts(
                            rule.condition, context
                        ),
                        rule_chain=[rule.id],
                    )
                    inferences.append(inference)
                    fired_rules.add(rule.id)
                    rule_fired = True

                    logger.debug(f"Rule {rule.id} fired: {rule.action}")
                    break  # Restart from highest priority

            if not rule_fired:
                break

        self.inference_history.extend(inferences)
        return inferences

    def _get_supporting_facts(
        self, condition: str, context: Dict[str, Any]
    ) -> List[str]:
        """Extract facts that support a condition."""
        facts = []
        env = {**self.facts, **context}

        # Extract variable names from condition
        import re

        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", condition)

        for token in tokens:
            if token in env and token not in ["AND", "OR", "NOT"]:
                facts.append(f"{token}={env[token]}")

        return facts

    def backward_chain(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        depth: int = 0,
        max_depth: int = 10,
    ) -> Optional[List[str]]:
        """
        Backward chaining inference.

        Given a goal (action), find rules that can achieve it
        and recursively prove their conditions.
        """
        if depth > max_depth:
            return None

        context = context or {}

        # Check if goal is directly satisfiable
        if goal in self.facts or goal in context:
            return [f"FACT: {goal}"]

        # Find rules that conclude this goal
        for rule in self.rules.values():
            if rule.action == goal and rule.enabled:
                # Try to prove the condition
                if self.evaluate_condition(rule.condition, context):
                    return [f"RULE: {rule.id} ({rule.condition})"]

                # Try to prove sub-conditions
                # (Simplified - in full implementation would parse condition)
                proof = self.backward_chain(
                    rule.condition, context, depth + 1, max_depth
                )
                if proof:
                    return [f"RULE: {rule.id}"] + proof

        return None

    def explain_inference(self, inference: Inference) -> str:
        """Generate human-readable explanation of inference."""
        explanation = []
        explanation.append(f"Conclusion: {inference.conclusion}")
        explanation.append(f"Confidence: {inference.confidence:.2%}")
        explanation.append("Supporting facts:")
        for fact in inference.supporting_facts:
            explanation.append(f"  - {fact}")
        explanation.append(f"Rule chain: {' -> '.join(inference.rule_chain)}")
        return "\n".join(explanation)

    def get_applicable_rules(
        self, context: Optional[Dict[str, Any]] = None
    ) -> List[Rule]:
        """Get all rules that could fire given current facts and context."""
        context = context or {}
        applicable = []

        for rule in self.rules.values():
            if rule.enabled and self.evaluate_condition(rule.condition, context):
                applicable.append(rule)

        return sorted(applicable, key=lambda r: r.priority, reverse=True)


# ============================================================================
# Rule Extractor (Learn Rules from Neural Models)
# ============================================================================


class RuleExtractor:
    """
    Extract symbolic rules from neural network decisions.

    Uses decision boundaries and feature importance to
    generate interpretable rules.
    """

    def __init__(self, rule_engine: SymbolicRuleEngine):
        self.rule_engine = rule_engine
        self.extracted_rules: List[Rule] = []

    def extract_from_decision_tree_approximation(
        self,
        model_predictions: List[Tuple[Dict[str, float], str]],
        min_samples: int = 10,
        min_confidence: float = 0.7,
    ) -> List[Rule]:
        """
        Extract rules by analyzing model input/output patterns.

        Args:
            model_predictions: List of (features, prediction) tuples
            min_samples: Minimum samples to form a rule
            min_confidence: Minimum confidence threshold
        """

        # Group by prediction
        prediction_groups: Dict[str, List[Dict[str, float]]] = defaultdict(list)
        for features, prediction in model_predictions:
            prediction_groups[prediction].append(features)

        rules = []
        rule_counter = len(self.extracted_rules)

        for prediction, feature_sets in prediction_groups.items():
            if len(feature_sets) < min_samples:
                continue

            # Find common feature ranges
            feature_ranges = self._find_common_ranges(feature_sets)

            # Generate rule conditions
            conditions = []
            for feature, (low, high) in feature_ranges.items():
                if low == high:
                    conditions.append(f"{feature} == {low:.2f}")
                else:
                    conditions.append(f"{feature} >= {low:.2f}")
                    conditions.append(f"{feature} <= {high:.2f}")

            if conditions:
                rule_counter += 1
                rule = Rule(
                    id=f"LEARNED_R{rule_counter:03d}",
                    name=f"learned_rule_{rule_counter}",
                    condition=" AND ".join(conditions[:3]),  # Limit complexity
                    action=prediction,
                    confidence=len(feature_sets) / len(model_predictions),
                    priority=5,
                )
                rules.append(rule)

        self.extracted_rules.extend(rules)
        return rules

    def _find_common_ranges(
        self, feature_sets: List[Dict[str, float]]
    ) -> Dict[str, Tuple[float, float]]:
        """Find common value ranges across feature sets."""
        if not feature_sets:
            return {}

        ranges = {}
        all_features = set()
        for fs in feature_sets:
            all_features.update(fs.keys())

        for feature in all_features:
            values = [fs[feature] for fs in feature_sets if feature in fs]
            if values:
                # Use percentiles for robustness
                values.sort()
                n = len(values)
                low_idx = int(n * 0.1)
                high_idx = int(n * 0.9)
                ranges[feature] = (values[low_idx], values[high_idx])

        return ranges

    def extract_from_attention_weights(
        self,
        attention_weights: List[Dict[str, float]],
        predictions: List[str],
        threshold: float = 0.3,
    ) -> List[str]:
        """
        Extract feature importance rules from attention weights.

        Returns list of feature importance statements.
        """
        from collections import Counter

        feature_importance = Counter()

        for weights, pred in zip(attention_weights, predictions):
            for feature, weight in weights.items():
                if weight > threshold:
                    feature_importance[(feature, pred)] += 1

        statements = []
        for (feature, pred), count in feature_importance.most_common(10):
            statements.append(
                f"When predicting '{pred}', feature '{feature}' is important "
                f"({count} occurrences)"
            )

        return statements


# ============================================================================
# Causal Reasoner
# ============================================================================


class CausalReasoner:
    """
    Causal reasoning for understanding market dynamics.

    Uses knowledge graph relationships to infer
    causal chains and predict consequences.
    """

    def __init__(self, knowledge_graph: FinancialKnowledgeGraph):
        self.kg = knowledge_graph

        # Causal relationship types
        self.causal_relations = {
            RelationType.CAUSES,
            RelationType.AFFECTS,
            RelationType.LEADS,
            RelationType.AMPLIFIES,
            RelationType.MITIGATES,
        }

    def find_causal_chain(
        self, cause: str, effect: str, max_depth: int = 4
    ) -> Optional[List[Tuple[str, str, str]]]:
        """
        Find causal chain between two entities.

        Returns list of (source, relation, target) tuples forming the chain.
        """
        if cause not in self.kg.entities or effect not in self.kg.entities:
            return None

        # BFS to find causal path
        visited = {cause}
        queue = [(cause, [])]

        while queue:
            current, path = queue.pop(0)

            if len(path) >= max_depth:
                continue

            for rel_id in self.kg.outgoing.get(current, set()):
                rel = self.kg.relationships.get(rel_id)
                if (
                    rel
                    and rel.is_valid()
                    and rel.relation_type in self.causal_relations
                ):
                    next_entity = rel.target_id
                    new_path = path + [(current, rel.relation_type.value, next_entity)]

                    if next_entity == effect:
                        return new_path

                    if next_entity not in visited:
                        visited.add(next_entity)
                        queue.append((next_entity, new_path))

        return None

    def estimate_causal_strength(self, cause: str, effect: str) -> float:
        """
        Estimate strength of causal relationship.

        Combines direct and indirect path strengths.
        """
        chain = self.find_causal_chain(cause, effect)
        if not chain:
            return 0.0

        # Calculate strength as product of relationship weights
        strength = 1.0
        for source, relation, target in chain:
            rel_id = f"{source}-{relation}-{target}"
            rel = self.kg.relationships.get(rel_id)
            if rel:
                strength *= rel.weight * rel.confidence

        # Apply depth decay
        depth_decay = 0.9 ** len(chain)

        return strength * depth_decay

    def counterfactual_analysis(
        self, entity: str, hypothetical_change: float, metric: str = "price"
    ) -> Dict[str, float]:
        """
        Counterfactual analysis: "What if X changed by Y%?"

        Propagates hypothetical change through causal graph.
        """
        impacts = self.kg.infer_impact(
            f"counterfactual_{metric}_change",
            entity,
            impact_magnitude=hypothetical_change,
        )

        return {
            k: v
            for k, v in impacts.items()
            if abs(v) > 0.001  # Filter negligible impacts
        }

    def identify_root_causes(
        self, effect: str, max_depth: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Identify potential root causes of an observed effect.

        Traces back through causal relationships.
        """
        if effect not in self.kg.entities:
            return []

        root_causes = []
        visited = {effect}
        queue = [(effect, 1.0, 0)]  # (entity, strength, depth)

        while queue:
            current, strength, depth = queue.pop(0)

            if depth >= max_depth:
                continue

            has_incoming_causal = False

            for rel_id in self.kg.incoming.get(current, set()):
                rel = self.kg.relationships.get(rel_id)
                if (
                    rel
                    and rel.is_valid()
                    and rel.relation_type in self.causal_relations
                ):
                    has_incoming_causal = True
                    source = rel.source_id
                    new_strength = strength * rel.weight * rel.confidence * 0.9

                    if source not in visited:
                        visited.add(source)
                        queue.append((source, new_strength, depth + 1))

            # If no incoming causal links, this could be a root cause
            if not has_incoming_causal and current != effect:
                root_causes.append((current, strength))

        return sorted(root_causes, key=lambda x: x[1], reverse=True)


# ============================================================================
# Unified Reasoning System
# ============================================================================


class NeuroSymbolicReasoner:
    """
    Unified neuro-symbolic reasoning system.

    Combines:
    - Knowledge graph for structured knowledge
    - Symbolic rules for explicit reasoning
    - Neural pattern recognition for learning
    - Causal analysis for understanding dynamics
    """

    def __init__(self):
        self.knowledge_graph = FinancialKnowledgeGraph()
        self.rule_engine = SymbolicRuleEngine(self.knowledge_graph)
        self.rule_extractor = RuleExtractor(self.rule_engine)
        self.causal_reasoner = CausalReasoner(self.knowledge_graph)

        # Reasoning cache
        self._reasoning_cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes

        logger.info("Initialized NeuroSymbolicReasoner")

    def reason(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform comprehensive reasoning on given context.

        Returns:
            Dict with conclusions, explanations, and confidence
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "inferences": [],
            "causal_insights": [],
            "recommendations": [],
            "confidence": 1.0,
        }

        # 1. Apply symbolic rules
        inferences = self.rule_engine.forward_chain(context)
        for inf in inferences:
            results["inferences"].append(
                {
                    "conclusion": inf.conclusion,
                    "confidence": inf.confidence,
                    "explanation": self.rule_engine.explain_inference(inf),
                }
            )

        # 2. Knowledge graph queries
        if "asset" in context:
            asset = context["asset"]

            # Get correlated entities
            correlated = self.knowledge_graph.get_correlated_entities(asset)
            if correlated:
                results["causal_insights"].append(
                    {
                        "type": "correlation",
                        "asset": asset,
                        "correlated_with": correlated[:5],
                    }
                )

            # Check for causal impacts
            if "event" in context:
                impacts = self.knowledge_graph.infer_impact(context["event"], asset)
                if impacts:
                    results["causal_insights"].append(
                        {
                            "type": "event_impact",
                            "event": context["event"],
                            "impacts": dict(list(impacts.items())[:10]),
                        }
                    )

        # 3. Generate recommendations
        applicable_rules = self.rule_engine.get_applicable_rules(context)
        for rule in applicable_rules[:3]:
            results["recommendations"].append(
                {
                    "action": rule.action,
                    "confidence": rule.confidence,
                    "rule": rule.name,
                }
            )

        # 4. Calculate overall confidence
        if results["inferences"]:
            avg_confidence = sum(i["confidence"] for i in results["inferences"]) / len(
                results["inferences"]
            )
            results["confidence"] = avg_confidence

        return results

    def update_knowledge(
        self, entity_id: str, relation: str, target_id: str, evidence: Dict[str, Any]
    ):
        """Update knowledge graph with new information."""
        # Ensure entities exist
        if entity_id not in self.knowledge_graph.entities:
            self.knowledge_graph.add_entity(
                entity_id, entity_id, EntityType.CRYPTOCURRENCY
            )
        if target_id not in self.knowledge_graph.entities:
            self.knowledge_graph.add_entity(
                target_id, target_id, EntityType.CRYPTOCURRENCY
            )

        # Add relationship
        try:
            rel_type = RelationType(relation)
        except ValueError:
            rel_type = RelationType.AFFECTS

        confidence = evidence.get("confidence", 0.8)
        weight = evidence.get("weight", 0.5)

        self.knowledge_graph.add_relationship(
            entity_id, rel_type, target_id, weight=weight, confidence=confidence
        )

    def learn_from_observations(self, observations: List[Tuple[Dict, str]]):
        """
        Learn new rules from observations.

        Args:
            observations: List of (features, outcome) tuples
        """
        new_rules = self.rule_extractor.extract_from_decision_tree_approximation(
            observations
        )

        for rule in new_rules:
            self.rule_engine.add_rule(rule)

        logger.info(f"Learned {len(new_rules)} new rules from observations")

    def explain_decision(self, decision: str, context: Dict[str, Any]) -> str:
        """Generate human-readable explanation for a decision."""
        explanations = []

        # Check which rules support this decision
        for rule in self.rule_engine.rules.values():
            if rule.action == decision and rule.enabled:
                if self.rule_engine.evaluate_condition(rule.condition, context):
                    explanations.append(
                        f"Rule '{rule.name}' supports this decision:\n"
                        f"  Condition: {rule.condition}\n"
                        f"  Confidence: {rule.confidence:.2%}"
                    )

        # Add knowledge graph context
        if "asset" in context:
            related = self.knowledge_graph.get_relationships(context["asset"])
            if related:
                explanations.append(
                    f"\nKnowledge graph relationships for {context['asset']}:\n"
                    + "\n".join(
                        f"  - {r.source_id} {r.relation_type.value} {r.target_id}"
                        for r in related[:5]
                    )
                )

        return "\n\n".join(explanations) if explanations else "No explanation available"

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the reasoning system."""
        return {
            "knowledge_graph": self.knowledge_graph.get_stats(),
            "rules": {
                "total": len(self.rule_engine.rules),
                "enabled": sum(1 for r in self.rule_engine.rules.values() if r.enabled),
                "learned": len(self.rule_extractor.extracted_rules),
            },
            "inference_history": len(self.rule_engine.inference_history),
        }


# ============================================================================
# Factory Function
# ============================================================================


def create_reasoner() -> NeuroSymbolicReasoner:
    """Create and configure a NeuroSymbolicReasoner instance."""
    reasoner = NeuroSymbolicReasoner()

    # Add additional common crypto relationships
    kg = reasoner.knowledge_graph

    # Layer 2s
    kg.add_entity("MATIC", "Polygon", EntityType.BLOCKCHAIN, {"layer": 2})
    kg.add_entity("ARB", "Arbitrum", EntityType.BLOCKCHAIN, {"layer": 2})
    kg.add_entity("OP", "Optimism", EntityType.BLOCKCHAIN, {"layer": 2})

    kg.add_relationship("MATIC", RelationType.LAYER_2_OF, "ETH", weight=1.0)
    kg.add_relationship("ARB", RelationType.LAYER_2_OF, "ETH", weight=1.0)
    kg.add_relationship("OP", RelationType.LAYER_2_OF, "ETH", weight=1.0)

    # DeFi protocols
    kg.add_entity("AAVE", "Aave", EntityType.PROTOCOL, {"category": "lending"})
    kg.add_entity("UNI", "Uniswap", EntityType.PROTOCOL, {"category": "dex"})
    kg.add_entity("LINK", "Chainlink", EntityType.PROTOCOL, {"category": "oracle"})

    kg.add_relationship("AAVE", RelationType.BUILT_ON, "ETH", weight=0.9)
    kg.add_relationship("UNI", RelationType.BUILT_ON, "ETH", weight=0.9)
    kg.add_relationship("AAVE", RelationType.CORRELATED_WITH, "ETH", weight=0.75)

    # Competition relationships
    kg.add_entity("SOL", "Solana", EntityType.BLOCKCHAIN, {"consensus": "PoH"})
    kg.add_entity("AVAX", "Avalanche", EntityType.BLOCKCHAIN, {"consensus": "Snow"})

    kg.add_relationship("SOL", RelationType.COMPETES_WITH, "ETH", weight=0.6)
    kg.add_relationship("AVAX", RelationType.COMPETES_WITH, "ETH", weight=0.5)
    kg.add_relationship("SOL", RelationType.CORRELATED_WITH, "ETH", weight=0.7)

    return reasoner


# Export main classes
__all__ = [
    "FinancialKnowledgeGraph",
    "SymbolicRuleEngine",
    "RuleExtractor",
    "CausalReasoner",
    "NeuroSymbolicReasoner",
    "create_reasoner",
    "Entity",
    "Relationship",
    "Rule",
    "Inference",
    "RelationType",
    "EntityType",
]
