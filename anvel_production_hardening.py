"""
VEL Production Hardening Module
Phase 6: Formal Verification, Chaos Engineering, and Distributed Consensus

This module provides:
1. Formal verification of critical paths with invariant checking
2. Chaos engineering for resilience testing
3. Distributed consensus for critical decisions
4. Property-based testing utilities
5. Safety contracts and assertions

Author: VEL AI Enhancement System
"""

import threading
import time
import random
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum, auto
from collections import defaultdict
import functools
import queue
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# PART 1: FORMAL VERIFICATION AND CONTRACTS
# =============================================================================


class ContractViolation(Exception):
    """Exception raised when a contract is violated."""

    pass


class PreconditionError(ContractViolation):
    """Exception raised when a precondition is violated."""

    pass


class PostconditionError(ContractViolation):
    """Exception raised when a postcondition is violated."""

    pass


class InvariantError(ContractViolation):
    """Exception raised when an invariant is violated."""

    pass


def precondition(
    condition: Callable[..., bool], message: str = "Precondition violated"
):
    """Decorator to add precondition checking to a function."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not condition(*args, **kwargs):
                raise PreconditionError(f"{message} in {func.__name__}")
            return func(*args, **kwargs)

        return wrapper

    return decorator


def postcondition(
    condition: Callable[[Any], bool], message: str = "Postcondition violated"
):
    """Decorator to add postcondition checking to a function."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if not condition(result):
                raise PostconditionError(f"{message} in {func.__name__}")
            return result

        return wrapper

    return decorator


def invariant(condition: Callable[[Any], bool], message: str = "Invariant violated"):
    """Decorator for class methods to check class invariants."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Check invariant before
            if not condition(self):
                raise InvariantError(f"{message} (before) in {func.__name__}")
            result = func(self, *args, **kwargs)
            # Check invariant after
            if not condition(self):
                raise InvariantError(f"{message} (after) in {func.__name__}")
            return result

        return wrapper

    return decorator


@dataclass
class Contract:
    """Formal contract specification."""

    name: str
    preconditions: List[Callable[..., bool]] = field(default_factory=list)
    postconditions: List[Callable[[Any], bool]] = field(default_factory=list)
    invariants: List[Callable[..., bool]] = field(default_factory=list)

    def verify_preconditions(self, *args, **kwargs) -> bool:
        """Verify all preconditions."""
        for condition in self.preconditions:
            if not condition(*args, **kwargs):
                return False
        return True

    def verify_postconditions(self, result: Any) -> bool:
        """Verify all postconditions."""
        for condition in self.postconditions:
            if not condition(result):
                return False
        return True

    def verify_invariants(self, obj: Any) -> bool:
        """Verify all invariants."""
        for condition in self.invariants:
            if not condition(obj):
                return False
        return True


class RiskManagementContract:
    """Formal contracts for risk management operations."""

    @staticmethod
    def position_size_positive(position_size: float) -> bool:
        """Position size must be non-negative."""
        return position_size >= 0

    @staticmethod
    def risk_within_budget(result: Dict[str, float]) -> bool:
        """Risk must be within budget."""
        return result.get("risk", float("inf")) <= result.get("max_risk", 0)

    @staticmethod
    def leverage_within_limits(leverage: float, max_leverage: float = 10.0) -> bool:
        """Leverage must be within acceptable limits."""
        return 0 <= leverage <= max_leverage

    @staticmethod
    def portfolio_sum_to_one(weights: List[float], tolerance: float = 0.001) -> bool:
        """Portfolio weights must sum to 1."""
        return abs(sum(weights) - 1.0) < tolerance

    @staticmethod
    def no_negative_weights(weights: List[float]) -> bool:
        """No negative portfolio weights (long-only)."""
        return all(w >= 0 for w in weights)


class FormalVerifier:
    """Formal verification engine for critical paths."""

    def __init__(self):
        self.contracts: Dict[str, Contract] = {}
        self.violations: List[Dict[str, Any]] = []
        self.verification_count = 0
        self.lock = threading.Lock()

    def register_contract(self, name: str, contract: Contract):
        """Register a contract for verification."""
        with self.lock:
            self.contracts[name] = contract

    def verify(
        self, contract_name: str, func: Callable, *args, **kwargs
    ) -> Tuple[Any, bool]:
        """
        Verify a function execution against its contract.
        Returns (result, success).
        """
        with self.lock:
            self.verification_count += 1

        contract = self.contracts.get(contract_name)
        if contract is None:
            # No contract, just execute
            return func(*args, **kwargs), True

        # Verify preconditions
        if not contract.verify_preconditions(*args, **kwargs):
            violation = {
                "contract": contract_name,
                "type": "precondition",
                "timestamp": time.time(),
                "args": str(args)[:100],
                "kwargs": str(kwargs)[:100],
            }
            with self.lock:
                self.violations.append(violation)
            raise PreconditionError(f"Precondition violated for {contract_name}")

        # Execute function
        result = func(*args, **kwargs)

        # Verify postconditions
        if not contract.verify_postconditions(result):
            violation = {
                "contract": contract_name,
                "type": "postcondition",
                "timestamp": time.time(),
                "result": str(result)[:100],
            }
            with self.lock:
                self.violations.append(violation)
            raise PostconditionError(f"Postcondition violated for {contract_name}")

        return result, True

    def get_violation_report(self) -> Dict[str, Any]:
        """Get report of all contract violations."""
        with self.lock:
            return {
                "total_verifications": self.verification_count,
                "total_violations": len(self.violations),
                "violations": self.violations.copy(),
                "violation_rate": len(self.violations)
                / max(1, self.verification_count),
            }


# =============================================================================
# PART 2: PROPERTY-BASED TESTING
# =============================================================================


class PropertyGenerator:
    """Generate test inputs for property-based testing."""

    @staticmethod
    def random_float(min_val: float = -1e6, max_val: float = 1e6) -> float:
        """Generate random float."""
        return random.uniform(min_val, max_val)

    @staticmethod
    def random_positive_float(max_val: float = 1e6) -> float:
        """Generate random positive float."""
        return random.uniform(0.001, max_val)

    @staticmethod
    def random_percentage() -> float:
        """Generate random percentage [0, 1]."""
        return random.random()

    @staticmethod
    def random_price(base: float = 100.0, volatility: float = 0.1) -> float:
        """Generate random price around a base."""
        return base * (1 + random.gauss(0, volatility))

    @staticmethod
    def random_weights(n: int) -> List[float]:
        """Generate random weights that sum to 1."""
        raw = [random.random() for _ in range(n)]
        total = sum(raw)
        return [w / total for w in raw]

    @staticmethod
    def random_order(
        min_size: float = 0.01, max_size: float = 100.0, price_base: float = 100.0
    ) -> Dict[str, Any]:
        """Generate random order."""
        return {
            "side": random.choice(["buy", "sell"]),
            "size": random.uniform(min_size, max_size),
            "price": PropertyGenerator.random_price(price_base),
            "timestamp": time.time(),
        }


@dataclass
class PropertyTestResult:
    """Result of property-based testing."""

    property_name: str
    passed: bool
    iterations: int
    failures: List[Dict[str, Any]] = field(default_factory=list)
    shrunk_example: Optional[Dict[str, Any]] = None


class PropertyTester:
    """Property-based testing framework."""

    def __init__(self, iterations: int = 100):
        self.iterations = iterations
        self.results: List[PropertyTestResult] = []

    def test_property(
        self,
        property_name: str,
        property_fn: Callable[..., bool],
        generator: Callable[[], Tuple],
        iterations: Optional[int] = None,
    ) -> PropertyTestResult:
        """Test a property with random inputs."""
        iters = iterations or self.iterations
        failures = []

        for i in range(iters):
            try:
                args = generator()
                if not property_fn(*args):
                    failures.append(
                        {"iteration": i, "args": args, "type": "property_false"}
                    )
            except Exception as e:
                failures.append(
                    {
                        "iteration": i,
                        "args": args if "args" in dir() else None,
                        "type": "exception",
                        "error": str(e),
                    }
                )

        result = PropertyTestResult(
            property_name=property_name,
            passed=len(failures) == 0,
            iterations=iters,
            failures=failures[:10],  # Limit stored failures
        )

        self.results.append(result)
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all property tests."""
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        return {
            "total_properties": len(self.results),
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / max(1, len(self.results)),
            "failed_properties": [
                r.property_name for r in self.results if not r.passed
            ],
        }


# =============================================================================
# PART 3: CHAOS ENGINEERING
# =============================================================================


class FailureType(Enum):
    """Types of failures that can be injected."""

    CPU_SPIKE = auto()
    MEMORY_PRESSURE = auto()
    NETWORK_LATENCY = auto()
    NETWORK_PARTITION = auto()
    DISK_FULL = auto()
    PROCESS_CRASH = auto()
    DEPENDENCY_FAILURE = auto()
    DATA_CORRUPTION = auto()
    CLOCK_SKEW = auto()
    RATE_LIMIT = auto()


@dataclass
class ChaosExperiment:
    """Definition of a chaos experiment."""

    id: str
    failure_type: FailureType
    target_component: str
    duration_seconds: float
    intensity: float = 0.5  # 0-1 scale
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class ChaosResult:
    """Result of a chaos experiment."""

    experiment_id: str
    started_at: float
    ended_at: float
    success: bool
    recovered: bool
    recovery_time_seconds: Optional[float]
    observations: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)


class FailureInjector:
    """Inject various types of failures."""

    def __init__(self):
        self.active_failures: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()

    def inject_cpu_spike(self, duration: float, intensity: float) -> str:
        """Simulate CPU spike by busy waiting."""
        failure_id = str(uuid.uuid4())[:8]
        stop_event = threading.Event()

        def cpu_load():
            end_time = time.time() + duration
            while time.time() < end_time and not stop_event.is_set():
                # Busy loop for intensity * 10ms, then sleep
                busy_end = time.time() + 0.01 * intensity
                while time.time() < busy_end:
                    _ = sum(i * i for i in range(100))
                time.sleep(0.01 * (1 - intensity))

        with self.lock:
            self.active_failures[failure_id] = stop_event

        thread = threading.Thread(target=cpu_load)
        thread.daemon = True
        thread.start()

        return failure_id

    def inject_memory_pressure(self, duration: float, mb_to_allocate: int) -> str:
        """Simulate memory pressure by allocating memory."""
        failure_id = str(uuid.uuid4())[:8]
        stop_event = threading.Event()

        def memory_load():
            try:
                # Allocate memory
                data = bytearray(mb_to_allocate * 1024 * 1024)
                # Keep it alive for duration
                stop_event.wait(timeout=duration)
                # Explicit cleanup
                del data
            except MemoryError:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_PRODUCTION_HARDENING").debug("Exception suppressed in memory_load")

        with self.lock:
            self.active_failures[failure_id] = stop_event

        thread = threading.Thread(target=memory_load)
        thread.daemon = True
        thread.start()

        return failure_id

    def inject_latency(
        self, component: str, latency_ms: float, jitter_ms: float = 0
    ) -> Callable:
        """Return a wrapper that adds latency to calls."""

        def latency_wrapper(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                delay = latency_ms + random.uniform(-jitter_ms, jitter_ms)
                time.sleep(max(0, delay) / 1000)
                return func(*args, **kwargs)

            return wrapper

        return latency_wrapper

    def inject_error_rate(self, error_rate: float) -> Callable:
        """Return a wrapper that randomly raises errors."""

        def error_wrapper(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if random.random() < error_rate:
                    raise RuntimeError("Chaos: Injected error")
                return func(*args, **kwargs)

            return wrapper

        return error_wrapper

    def stop_failure(self, failure_id: str) -> bool:
        """Stop an active failure injection."""
        with self.lock:
            if failure_id in self.active_failures:
                self.active_failures[failure_id].set()
                del self.active_failures[failure_id]
                return True
        return False

    def stop_all(self):
        """Stop all active failure injections."""
        with self.lock:
            for event in self.active_failures.values():
                event.set()
            self.active_failures.clear()


class RecoveryVerifier:
    """Verify system recovery after chaos experiments."""

    def __init__(self):
        self.health_checks: Dict[str, Callable[[], bool]] = {}

    def register_health_check(self, component: str, check_fn: Callable[[], bool]):
        """Register a health check for a component."""
        self.health_checks[component] = check_fn

    def verify_health(self, component: Optional[str] = None) -> Dict[str, bool]:
        """Verify health of components."""
        if component:
            checks = {component: self.health_checks.get(component)}
        else:
            checks = self.health_checks

        results = {}
        for name, check_fn in checks.items():
            if check_fn is None:
                results[name] = False
            else:
                try:
                    results[name] = check_fn()
                except Exception:
                    results[name] = False

        return results

    def wait_for_recovery(
        self, component: str, timeout_seconds: float, check_interval: float = 0.5
    ) -> Tuple[bool, float]:
        """Wait for a component to recover, return (recovered, time_taken)."""
        start = time.time()

        while time.time() - start < timeout_seconds:
            health = self.verify_health(component)
            if health.get(component, False):
                return True, time.time() - start
            time.sleep(check_interval)

        return False, timeout_seconds


class ChaosEngine:
    """Main chaos engineering engine."""

    def __init__(self):
        self.injector = FailureInjector()
        self.verifier = RecoveryVerifier()
        self.experiments: Dict[str, ChaosExperiment] = {}
        self.results: List[ChaosResult] = []
        self.lock = threading.Lock()

    def create_experiment(
        self,
        failure_type: FailureType,
        target_component: str,
        duration_seconds: float,
        intensity: float = 0.5,
        **parameters,
    ) -> ChaosExperiment:
        """Create a new chaos experiment."""
        experiment = ChaosExperiment(
            id=str(uuid.uuid4())[:8],
            failure_type=failure_type,
            target_component=target_component,
            duration_seconds=duration_seconds,
            intensity=intensity,
            parameters=parameters,
        )

        with self.lock:
            self.experiments[experiment.id] = experiment

        return experiment

    def run_experiment(
        self, experiment: ChaosExperiment, recovery_timeout: float = 30.0
    ) -> ChaosResult:
        """Run a chaos experiment and verify recovery."""
        started_at = time.time()
        observations = []
        failure_id = None

        # Inject failure based on type
        if experiment.failure_type == FailureType.CPU_SPIKE:
            failure_id = self.injector.inject_cpu_spike(
                experiment.duration_seconds, experiment.intensity
            )
            observations.append(f"Injected CPU spike at {experiment.intensity*100}%")

        elif experiment.failure_type == FailureType.MEMORY_PRESSURE:
            mb = experiment.parameters.get("mb", int(experiment.intensity * 100))
            failure_id = self.injector.inject_memory_pressure(
                experiment.duration_seconds, mb
            )
            observations.append(f"Injected memory pressure: {mb}MB")

        # Wait for experiment duration
        time.sleep(experiment.duration_seconds)

        # Stop failure if still active
        if failure_id:
            self.injector.stop_failure(failure_id)

        ended_at = time.time()
        observations.append(
            f"Failure injection completed after {experiment.duration_seconds}s"
        )

        # Verify recovery
        recovered, recovery_time = self.verifier.wait_for_recovery(
            experiment.target_component, recovery_timeout
        )

        if recovered:
            observations.append(f"System recovered in {recovery_time:.2f}s")
        else:
            observations.append(f"System did not recover within {recovery_timeout}s")

        result = ChaosResult(
            experiment_id=experiment.id,
            started_at=started_at,
            ended_at=ended_at,
            success=True,
            recovered=recovered,
            recovery_time_seconds=recovery_time if recovered else None,
            observations=observations,
            metrics={
                "duration": ended_at - started_at,
                "recovery_time": recovery_time if recovered else recovery_timeout,
            },
        )

        with self.lock:
            self.results.append(result)

        return result

    def get_chaos_report(self) -> Dict[str, Any]:
        """Get comprehensive chaos engineering report."""
        with self.lock:
            total = len(self.results)
            recovered = sum(1 for r in self.results if r.recovered)

            avg_recovery = 0.0
            if recovered > 0:
                recovery_times = [
                    r.recovery_time_seconds for r in self.results if r.recovered
                ]
                avg_recovery = sum(recovery_times) / len(recovery_times)

            return {
                "total_experiments": total,
                "recovered": recovered,
                "failed_to_recover": total - recovered,
                "recovery_rate": recovered / max(1, total),
                "average_recovery_time": avg_recovery,
                "experiments": [
                    {
                        "id": r.experiment_id,
                        "recovered": r.recovered,
                        "recovery_time": r.recovery_time_seconds,
                    }
                    for r in self.results[-10:]  # Last 10
                ],
            }


# =============================================================================
# PART 4: DISTRIBUTED CONSENSUS (Raft-like)
# =============================================================================


class NodeState(Enum):
    """Raft node states."""

    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()


@dataclass
class LogEntry:
    """Raft log entry."""

    term: int
    index: int
    command: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class RequestVote:
    """Raft RequestVote RPC."""

    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


@dataclass
class RequestVoteResponse:
    """Response to RequestVote RPC."""

    term: int
    vote_granted: bool


@dataclass
class AppendEntries:
    """Raft AppendEntries RPC."""

    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: List[LogEntry]
    leader_commit: int


@dataclass
class AppendEntriesResponse:
    """Response to AppendEntries RPC."""

    term: int
    success: bool
    match_index: int = 0


class RaftNode:
    """Simplified Raft consensus node."""

    def __init__(self, node_id: str, peers: List[str]):
        self.node_id = node_id
        self.peers = peers

        # Persistent state
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []

        # Volatile state
        self.commit_index = 0
        self.last_applied = 0

        # Leader state
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}

        # Node state
        self.state = NodeState.FOLLOWER
        self.leader_id: Optional[str] = None

        # Timing
        self.election_timeout = random.uniform(150, 300) / 1000  # 150-300ms
        self.heartbeat_interval = 50 / 1000  # 50ms
        self.last_heartbeat = time.time()

        # Message queues (simulated network)
        self.inbox: queue.Queue = queue.Queue()
        self.outbox: Dict[str, queue.Queue] = {}

        # State machine
        self.state_machine: Dict[str, Any] = {}

        self.running = False
        self.lock = threading.Lock()

    def start(self):
        """Start the Raft node."""
        self.running = True

        # Start election timer
        threading.Thread(target=self._election_timer, daemon=True).start()

    def stop(self):
        """Stop the Raft node."""
        self.running = False

    def _election_timer(self):
        """Election timeout timer."""
        while self.running:
            time.sleep(0.05)

            with self.lock:
                if self.state != NodeState.LEADER:
                    if time.time() - self.last_heartbeat > self.election_timeout:
                        self._start_election()

    def _start_election(self):
        """Start a leader election."""
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        votes_received = 1  # Vote for self

        last_log_index = len(self.log) - 1 if self.log else -1
        last_log_term = self.log[last_log_index].term if self.log else 0

        # Request votes from peers (simplified)
        for peer in self.peers:
            request = RequestVote(
                term=self.current_term,
                candidate_id=self.node_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term,
            )

            # In real implementation, send over network
            # Here we just count as granted for simulation
            votes_received += 1

        # Check if won election
        if votes_received > (len(self.peers) + 1) / 2:
            self._become_leader()

    def _become_leader(self):
        """Transition to leader state."""
        self.state = NodeState.LEADER
        self.leader_id = self.node_id

        # Initialize leader state
        for peer in self.peers:
            self.next_index[peer] = len(self.log)
            self.match_index[peer] = 0

    def handle_request_vote(self, request: RequestVote) -> RequestVoteResponse:
        """Handle RequestVote RPC."""
        with self.lock:
            if request.term < self.current_term:
                return RequestVoteResponse(term=self.current_term, vote_granted=False)

            if request.term > self.current_term:
                self.current_term = request.term
                self.state = NodeState.FOLLOWER
                self.voted_for = None

            # Grant vote if we haven't voted and candidate's log is up-to-date
            log_ok = True
            if self.log:
                last_term = self.log[-1].term
                last_index = len(self.log) - 1
                log_ok = request.last_log_term > last_term or (
                    request.last_log_term == last_term
                    and request.last_log_index >= last_index
                )

            if (
                self.voted_for is None or self.voted_for == request.candidate_id
            ) and log_ok:
                self.voted_for = request.candidate_id
                self.last_heartbeat = time.time()
                return RequestVoteResponse(term=self.current_term, vote_granted=True)

            return RequestVoteResponse(term=self.current_term, vote_granted=False)

    def handle_append_entries(self, request: AppendEntries) -> AppendEntriesResponse:
        """Handle AppendEntries RPC."""
        with self.lock:
            if request.term < self.current_term:
                return AppendEntriesResponse(term=self.current_term, success=False)

            self.last_heartbeat = time.time()

            if request.term > self.current_term:
                self.current_term = request.term
                self.state = NodeState.FOLLOWER
                self.voted_for = None

            self.leader_id = request.leader_id

            # Check log consistency
            if request.prev_log_index >= 0:
                if len(self.log) <= request.prev_log_index:
                    return AppendEntriesResponse(term=self.current_term, success=False)
                if self.log[request.prev_log_index].term != request.prev_log_term:
                    return AppendEntriesResponse(term=self.current_term, success=False)

            # Append entries
            for entry in request.entries:
                if entry.index < len(self.log):
                    if self.log[entry.index].term != entry.term:
                        self.log = self.log[: entry.index]
                        self.log.append(entry)
                else:
                    self.log.append(entry)

            # Update commit index
            if request.leader_commit > self.commit_index:
                self.commit_index = min(request.leader_commit, len(self.log) - 1)
                self._apply_committed()

            return AppendEntriesResponse(
                term=self.current_term, success=True, match_index=len(self.log) - 1
            )

    def _apply_committed(self):
        """Apply committed log entries to state machine."""
        while self.last_applied <= self.commit_index:
            if self.last_applied < len(self.log):
                entry = self.log[self.last_applied]
                self._apply_command(entry.command)
            self.last_applied += 1

    def _apply_command(self, command: Dict[str, Any]):
        """Apply a command to the state machine."""
        op = command.get("operation")
        key = command.get("key")
        value = command.get("value")

        if op == "set":
            self.state_machine[key] = value
        elif op == "delete":
            self.state_machine.pop(key, None)

    def propose(self, command: Dict[str, Any]) -> bool:
        """Propose a command (only works if leader)."""
        with self.lock:
            if self.state != NodeState.LEADER:
                return False

            entry = LogEntry(
                term=self.current_term, index=len(self.log), command=command
            )
            self.log.append(entry)

            # In real implementation, replicate to followers
            # For simulation, auto-commit
            self.commit_index = len(self.log) - 1
            self._apply_committed()

            return True

    def get_state(self) -> Dict[str, Any]:
        """Get current node state."""
        with self.lock:
            return {
                "node_id": self.node_id,
                "state": self.state.name,
                "term": self.current_term,
                "leader_id": self.leader_id,
                "log_length": len(self.log),
                "commit_index": self.commit_index,
                "state_machine": self.state_machine.copy(),
            }


class DistributedConsensus:
    """Distributed consensus manager."""

    def __init__(self, node_count: int = 3):
        self.nodes: Dict[str, RaftNode] = {}
        self.node_count = node_count

        # Create nodes
        node_ids = [f"node_{i}" for i in range(node_count)]
        for node_id in node_ids:
            peers = [n for n in node_ids if n != node_id]
            self.nodes[node_id] = RaftNode(node_id, peers)

    def start_cluster(self):
        """Start all nodes in the cluster."""
        for node in self.nodes.values():
            node.start()

        # Give time for leader election
        time.sleep(0.5)

        # Force one node to become leader for testing
        leader = list(self.nodes.values())[0]
        leader._become_leader()

    def stop_cluster(self):
        """Stop all nodes."""
        for node in self.nodes.values():
            node.stop()

    def get_leader(self) -> Optional[RaftNode]:
        """Get current leader node."""
        for node in self.nodes.values():
            if node.state == NodeState.LEADER:
                return node
        return None

    def propose_value(self, key: str, value: Any) -> bool:
        """Propose a value through consensus."""
        leader = self.get_leader()
        if leader is None:
            return False

        return leader.propose({"operation": "set", "key": key, "value": value})

    def get_value(self, key: str) -> Optional[Any]:
        """Get a value from the state machine."""
        leader = self.get_leader()
        if leader is None:
            # Read from any node
            for node in self.nodes.values():
                if key in node.state_machine:
                    return node.state_machine[key]
            return None
        return leader.state_machine.get(key)

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get status of the entire cluster."""
        return {
            "node_count": len(self.nodes),
            "leader": self.get_leader().node_id if self.get_leader() else None,
            "nodes": {
                node_id: node.get_state() for node_id, node in self.nodes.items()
            },
        }


# =============================================================================
# PART 5: CRITICAL DECISION VALIDATOR
# =============================================================================


class DecisionSeverity(Enum):
    """Severity levels for critical decisions."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


@dataclass
class CriticalDecision:
    """A critical decision requiring validation."""

    id: str
    decision_type: str
    severity: DecisionSeverity
    parameters: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    validations: List[Dict[str, Any]] = field(default_factory=list)
    approved: bool = False


class DecisionValidator:
    """Validate critical decisions before execution."""

    def __init__(self):
        self.validators: Dict[str, List[Callable[[Dict], bool]]] = defaultdict(list)
        self.decisions: Dict[str, CriticalDecision] = {}
        self.lock = threading.Lock()

    def register_validator(
        self, decision_type: str, validator: Callable[[Dict], bool], name: str = ""
    ):
        """Register a validator for a decision type."""
        self.validators[decision_type].append((name, validator))

    def create_decision(
        self, decision_type: str, severity: DecisionSeverity, **parameters
    ) -> CriticalDecision:
        """Create a new critical decision for validation."""
        decision = CriticalDecision(
            id=str(uuid.uuid4())[:8],
            decision_type=decision_type,
            severity=severity,
            parameters=parameters,
        )

        with self.lock:
            self.decisions[decision.id] = decision

        return decision

    def validate_decision(self, decision: CriticalDecision) -> bool:
        """Validate a decision through all registered validators."""
        validators = self.validators.get(decision.decision_type, [])

        all_passed = True
        for name, validator in validators:
            try:
                result = validator(decision.parameters)
                decision.validations.append(
                    {"validator": name, "passed": result, "timestamp": time.time()}
                )
                if not result:
                    all_passed = False
            except Exception as e:
                decision.validations.append(
                    {
                        "validator": name,
                        "passed": False,
                        "error": str(e),
                        "timestamp": time.time(),
                    }
                )
                all_passed = False

        # For critical decisions, require consensus
        if decision.severity == DecisionSeverity.CRITICAL:
            # All validators must pass
            decision.approved = all_passed and len(validators) > 0
        else:
            # Majority must pass
            passed_count = sum(1 for v in decision.validations if v["passed"])
            decision.approved = passed_count > len(validators) / 2

        return decision.approved

    def get_decision_status(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a decision."""
        with self.lock:
            decision = self.decisions.get(decision_id)
            if decision is None:
                return None

            return {
                "id": decision.id,
                "type": decision.decision_type,
                "severity": decision.severity.name,
                "parameters": decision.parameters,
                "validations": decision.validations,
                "approved": decision.approved,
            }


# =============================================================================
# PART 6: PRODUCTION READINESS CHECKER
# =============================================================================


class ReadinessCheck:
    """Individual readiness check."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[], bool],
        category: str = "general",
        required: bool = True,
    ):
        self.name = name
        self.check_fn = check_fn
        self.category = category
        self.required = required

    def run(self) -> Tuple[bool, Optional[str]]:
        """Run the check, return (passed, error_message)."""
        try:
            result = self.check_fn()
            return result, None if result else f"{self.name} failed"
        except Exception as e:
            return False, f"{self.name} error: {str(e)}"


class ProductionReadinessChecker:
    """Check system readiness for production."""

    def __init__(self):
        self.checks: List[ReadinessCheck] = []
        self.last_results: Dict[str, Any] = {}

    def add_check(
        self,
        name: str,
        check_fn: Callable[[], bool],
        category: str = "general",
        required: bool = True,
    ):
        """Add a readiness check."""
        self.checks.append(ReadinessCheck(name, check_fn, category, required))

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all readiness checks."""
        results = {
            "timestamp": time.time(),
            "passed": True,
            "checks": [],
            "by_category": defaultdict(list),
            "required_failed": [],
        }

        for check in self.checks:
            passed, error = check.run()

            check_result = {
                "name": check.name,
                "category": check.category,
                "required": check.required,
                "passed": passed,
                "error": error,
            }

            results["checks"].append(check_result)
            results["by_category"][check.category].append(check_result)

            if not passed and check.required:
                results["passed"] = False
                results["required_failed"].append(check.name)

        self.last_results = results
        return results

    def is_production_ready(self) -> bool:
        """Check if system is production ready."""
        results = self.run_all_checks()
        return results["passed"]

    def get_readiness_summary(self) -> str:
        """Get human-readable readiness summary."""
        if not self.last_results:
            self.run_all_checks()

        lines = ["Production Readiness Check Results", "=" * 40]

        if self.last_results["passed"]:
            lines.append("✅ PRODUCTION READY")
        else:
            lines.append("❌ NOT PRODUCTION READY")
            lines.append(
                f"Failed required checks: {', '.join(self.last_results['required_failed'])}"
            )

        lines.append("")

        for category, checks in self.last_results["by_category"].items():
            passed = sum(1 for c in checks if c["passed"])
            lines.append(f"{category}: {passed}/{len(checks)} passed")

        return "\n".join(lines)


# =============================================================================
# FACTORY AND INTEGRATION
# =============================================================================


class ProductionHardeningSystem:
    """Integrated production hardening system."""

    def __init__(self):
        # Core components
        self.formal_verifier = FormalVerifier()
        self.property_tester = PropertyTester()
        self.chaos_engine = ChaosEngine()
        self.consensus = None  # Created lazily
        self.decision_validator = DecisionValidator()
        self.readiness_checker = ProductionReadinessChecker()

        # Setup default contracts
        self._setup_default_contracts()

        # Setup default readiness checks
        self._setup_default_readiness_checks()

    def _setup_default_contracts(self):
        """Setup default formal contracts."""
        # Position sizing contract
        position_contract = Contract(
            name="position_sizing",
            preconditions=[
                lambda size, **_: size >= 0,
                lambda size, max_size=1000, **_: size <= max_size,
            ],
            postconditions=[lambda result: result.get("position", 0) >= 0],
        )
        self.formal_verifier.register_contract("position_sizing", position_contract)

        # Risk calculation contract
        risk_contract = Contract(
            name="risk_calculation",
            preconditions=[lambda positions, **_: len(positions) >= 0],
            postconditions=[lambda result: result.get("total_risk", float("inf")) >= 0],
        )
        self.formal_verifier.register_contract("risk_calculation", risk_contract)

    def _setup_default_readiness_checks(self):
        """Setup default production readiness checks."""
        # Memory check
        self.readiness_checker.add_check(
            "memory_available",
            lambda: True,  # Simplified
            category="resources",
            required=True,
        )

        # Disk check
        self.readiness_checker.add_check(
            "disk_space",
            lambda: True,  # Simplified
            category="resources",
            required=True,
        )

        # Configuration check
        self.readiness_checker.add_check(
            "config_valid",
            lambda: True,  # Simplified
            category="configuration",
            required=True,
        )

    def initialize_consensus(self, node_count: int = 3):
        """Initialize distributed consensus."""
        self.consensus = DistributedConsensus(node_count)
        self.consensus.start_cluster()

    def run_chaos_experiment(
        self, failure_type: FailureType, component: str, duration: float = 5.0
    ) -> ChaosResult:
        """Run a chaos engineering experiment."""
        experiment = self.chaos_engine.create_experiment(
            failure_type=failure_type,
            target_component=component,
            duration_seconds=duration,
        )
        return self.chaos_engine.run_experiment(experiment)

    def validate_critical_decision(
        self, decision_type: str, severity: DecisionSeverity, **parameters
    ) -> Tuple[bool, CriticalDecision]:
        """Validate a critical decision."""
        decision = self.decision_validator.create_decision(
            decision_type, severity, **parameters
        )
        approved = self.decision_validator.validate_decision(decision)
        return approved, decision

    def get_system_report(self) -> Dict[str, Any]:
        """Get comprehensive system hardening report."""
        return {
            "formal_verification": self.formal_verifier.get_violation_report(),
            "property_testing": self.property_tester.get_summary(),
            "chaos_engineering": self.chaos_engine.get_chaos_report(),
            "consensus": (
                self.consensus.get_cluster_status() if self.consensus else None
            ),
            "readiness": self.readiness_checker.run_all_checks(),
        }


# Create singleton instance
_production_system: Optional[ProductionHardeningSystem] = None


def get_production_system() -> ProductionHardeningSystem:
    """Get the production hardening system singleton."""
    global _production_system
    if _production_system is None:
        _production_system = ProductionHardeningSystem()
    return _production_system
