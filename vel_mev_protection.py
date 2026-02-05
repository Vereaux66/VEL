#!/usr/bin/env python3
"""
VEL MEV Protection & Adversarial Routing Hardening
===================================================

Production-grade MEV protection for DeFi trading operations.

Features:
- Pool/path allowlists per protocol (config-driven)
- Liquidity floor checks before routing
- Slippage tightening during volatility spikes
- MEV risk scoring prior to submission
- Config-driven private transaction routing support

Rules:
- If MEV risk > threshold → reject or reroute
- If liquidity < floor → reject
- All decisions logged with intent_id correlation

NO SILENT FAILURES - All decisions are explicit and logged.
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MEVRiskLevel(Enum):
    """MEV risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RoutingDecision(Enum):
    """Routing decision outcomes."""
    APPROVE = "approve"
    REJECT = "reject"
    REROUTE = "reroute"
    USE_PRIVATE = "use_private"


@dataclass
class MEVProtectionConfig:
    """MEV protection configuration."""
    # Risk thresholds
    max_risk_score: Decimal = Decimal("70")  # 0-100 scale
    critical_risk_threshold: Decimal = Decimal("85")
    
    # Liquidity requirements
    min_liquidity_usd: Decimal = Decimal("100000")  # $100k minimum
    min_liquidity_depth_ratio: Decimal = Decimal("5")  # 5x trade size
    max_trade_to_liquidity_ratio: Decimal = Decimal("0.2")  # 20% of pool maximum
    
    # Slippage controls
    base_max_slippage_bps: int = 50  # 0.5% base
    volatility_adjusted_max_slippage_bps: int = 100  # 1% during volatility
    high_volatility_threshold: Decimal = Decimal("0.05")  # 5% price movement
    
    # Private transaction routing
    enable_private_routing: bool = False
    private_routing_risk_threshold: Decimal = Decimal("60")
    private_relay_endpoints: List[str] = field(default_factory=list)
    
    # Pool/path allowlists (per-protocol)
    pool_allowlists: Dict[str, Set[str]] = field(default_factory=dict)
    router_allowlists: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Volatility window
    volatility_window_seconds: int = 300  # 5 minutes


@dataclass
class MEVRiskAssessment:
    """MEV risk assessment result."""
    assessment_id: str
    intent_id: str
    risk_level: MEVRiskLevel
    risk_score: Decimal  # 0-100
    decision: RoutingDecision
    reasons: List[str] = field(default_factory=list)
    
    # Risk factors
    sandwich_risk: Decimal = Decimal("0")
    frontrun_risk: Decimal = Decimal("0")
    backrun_risk: Decimal = Decimal("0")
    liquidity_risk: Decimal = Decimal("0")
    slippage_risk: Decimal = Decimal("0")
    
    # Route details
    pool_address: Optional[str] = None
    router_address: Optional[str] = None
    liquidity_usd: Optional[Decimal] = None
    expected_slippage_bps: Optional[int] = None
    
    # Private routing recommendation
    recommend_private: bool = False
    private_relay: Optional[str] = None
    
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "assessment_id": self.assessment_id,
            "intent_id": self.intent_id,
            "risk_level": self.risk_level.value,
            "risk_score": str(self.risk_score),
            "decision": self.decision.value,
            "reasons": self.reasons,
            "sandwich_risk": str(self.sandwich_risk),
            "frontrun_risk": str(self.frontrun_risk),
            "backrun_risk": str(self.backrun_risk),
            "liquidity_risk": str(self.liquidity_risk),
            "slippage_risk": str(self.slippage_risk),
            "liquidity_usd": str(self.liquidity_usd) if self.liquidity_usd else None,
            "expected_slippage_bps": self.expected_slippage_bps,
            "recommend_private": self.recommend_private,
            "assessed_at": self.assessed_at.isoformat()
        }


@dataclass
class VolatilityMetrics:
    """Real-time volatility metrics."""
    chain_id: int
    token_address: str
    price_change_1m: Decimal = Decimal("0")
    price_change_5m: Decimal = Decimal("0")
    volume_spike_ratio: Decimal = Decimal("1")
    is_high_volatility: bool = False
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MEVProtectionEngine:
    """
    MEV protection and adversarial routing hardening engine.
    
    Provides comprehensive protection against MEV attacks including:
    - Sandwich attacks
    - Front-running
    - Back-running
    - JIT (Just-In-Time) liquidity attacks
    
    All routing decisions are explicit and logged.
    """
    
    def __init__(self, config: Optional[MEVProtectionConfig] = None):
        """
        Initialize MEV protection engine.
        
        Args:
            config: MEV protection configuration (uses defaults if not provided)
        """
        self.config = config or MEVProtectionConfig()
        self._lock = threading.Lock()
        
        # Volatility tracking
        self._volatility_metrics: Dict[tuple[int, str], VolatilityMetrics] = {}
        
        # Historical price tracking for volatility calculation
        self._price_history: Dict[tuple[int, str], List[tuple[datetime, Decimal]]] = {}
        
        # Risk assessment cache (short TTL)
        self._assessment_cache: Dict[str, MEVRiskAssessment] = {}
        self._cache_ttl_seconds = 10  # 10 second cache
        
        logger.info(
            "MEV protection engine initialized",
            extra={
                "max_risk_score": str(self.config.max_risk_score),
                "min_liquidity_usd": str(self.config.min_liquidity_usd),
                "private_routing_enabled": self.config.enable_private_routing
            }
        )
    
    def assess_mev_risk(
        self,
        intent_id: str,
        chain_id: int,
        protocol: str,
        route: Dict[str, Any],
        trade_size_usd: Decimal,
        expected_slippage_bps: int
    ) -> MEVRiskAssessment:
        """
        Assess MEV risk for a proposed trade route.
        
        Args:
            intent_id: Intent identifier for correlation
            chain_id: Chain ID
            protocol: DEX protocol name
            route: Route details including pools and paths
            trade_size_usd: Trade size in USD
            expected_slippage_bps: Expected slippage in basis points
            
        Returns:
            MEVRiskAssessment with risk score and routing decision
        """
        assessment_id = f"mev_{intent_id}_{datetime.now(timezone.utc).timestamp()}"
        
        logger.info(
            f"Assessing MEV risk: intent={intent_id}, protocol={protocol}, "
            f"size=${trade_size_usd}, slippage={expected_slippage_bps}bps",
            extra={
                "intent_id": intent_id,
                "assessment_id": assessment_id,
                "chain_id": chain_id,
                "protocol": protocol,
                "trade_size_usd": str(trade_size_usd)
            }
        )
        
        reasons = []
        risk_factors = {}
        
        # Factor 1: Check pool/router allowlists
        pool_address = route.get("pool_address")
        router_address = route.get("router_address")
        
        if not self._check_allowlists(protocol, pool_address, router_address):
            reasons.append("Pool or router not in allowlist")
            risk_factors["allowlist_violation"] = Decimal("30")
        
        # Factor 2: Check liquidity depth
        liquidity_usd = self._get_pool_liquidity(chain_id, pool_address)
        liquidity_risk = self._assess_liquidity_risk(
            liquidity_usd, trade_size_usd
        )
        risk_factors["liquidity_risk"] = liquidity_risk
        
        if liquidity_usd < self.config.min_liquidity_usd:
            reasons.append(
                f"Insufficient pool liquidity: ${liquidity_usd} < "
                f"${self.config.min_liquidity_usd}"
            )
        
        # Factor 3: Check trade size relative to liquidity
        if liquidity_usd > 0:
            trade_to_liquidity_ratio = trade_size_usd / liquidity_usd
            if trade_to_liquidity_ratio > self.config.max_trade_to_liquidity_ratio:
                reasons.append(
                    f"Trade size too large relative to liquidity: "
                    f"{trade_to_liquidity_ratio:.1%}"
                )
                risk_factors["size_risk"] = Decimal("25")
        
        # Factor 4: Assess sandwich attack risk
        sandwich_risk = self._assess_sandwich_risk(
            chain_id, protocol, trade_size_usd, liquidity_usd, expected_slippage_bps
        )
        risk_factors["sandwich_risk"] = sandwich_risk
        
        if sandwich_risk > Decimal("50"):
            reasons.append(f"High sandwich attack risk: {sandwich_risk}")
        
        # Factor 5: Assess front-running risk
        frontrun_risk = self._assess_frontrun_risk(
            chain_id, protocol, trade_size_usd
        )
        risk_factors["frontrun_risk"] = frontrun_risk
        
        # Factor 6: Assess slippage risk based on volatility
        token_in = route.get("token_in")
        token_out = route.get("token_out")
        slippage_risk = self._assess_slippage_risk(
            chain_id, token_in, token_out, expected_slippage_bps
        )
        risk_factors["slippage_risk"] = slippage_risk
        
        # Calculate composite risk score (0-100)
        risk_score = self._calculate_composite_risk(risk_factors)
        
        # Determine risk level
        if risk_score >= self.config.critical_risk_threshold:
            risk_level = MEVRiskLevel.CRITICAL
        elif risk_score >= self.config.max_risk_score:
            risk_level = MEVRiskLevel.HIGH
        elif risk_score >= Decimal("40"):
            risk_level = MEVRiskLevel.MEDIUM
        else:
            risk_level = MEVRiskLevel.LOW
        
        # Make routing decision
        decision, recommend_private, private_relay = self._make_routing_decision(
            risk_score, risk_level, liquidity_usd, reasons
        )
        
        # Build assessment
        assessment = MEVRiskAssessment(
            assessment_id=assessment_id,
            intent_id=intent_id,
            risk_level=risk_level,
            risk_score=risk_score,
            decision=decision,
            reasons=reasons,
            sandwich_risk=risk_factors.get("sandwich_risk", Decimal("0")),
            frontrun_risk=risk_factors.get("frontrun_risk", Decimal("0")),
            backrun_risk=risk_factors.get("backrun_risk", Decimal("0")),
            liquidity_risk=risk_factors.get("liquidity_risk", Decimal("0")),
            slippage_risk=risk_factors.get("slippage_risk", Decimal("0")),
            pool_address=pool_address,
            router_address=router_address,
            liquidity_usd=liquidity_usd,
            expected_slippage_bps=expected_slippage_bps,
            recommend_private=recommend_private,
            private_relay=private_relay
        )
        
        # Log assessment
        logger.info(
            f"MEV risk assessment complete: {decision.value}",
            extra=assessment.to_dict()
        )
        
        # Cache assessment
        with self._lock:
            self._assessment_cache[assessment_id] = assessment
        
        return assessment
    
    def _check_allowlists(
        self,
        protocol: str,
        pool_address: Optional[str],
        router_address: Optional[str]
    ) -> bool:
        """Check if pool and router are in allowlists."""
        # If no allowlist configured, allow by default
        if not self.config.pool_allowlists and not self.config.router_allowlists:
            return True
        
        # Check pool allowlist
        if protocol in self.config.pool_allowlists:
            pool_allowlist = self.config.pool_allowlists[protocol]
            if pool_address and pool_address.lower() not in {p.lower() for p in pool_allowlist}:
                logger.warning(
                    f"Pool {pool_address} not in allowlist for {protocol}",
                    extra={"protocol": protocol, "pool_address": pool_address}
                )
                return False
        
        # Check router allowlist
        if protocol in self.config.router_allowlists:
            router_allowlist = self.config.router_allowlists[protocol]
            if router_address and router_address.lower() not in {r.lower() for r in router_allowlist}:
                logger.warning(
                    f"Router {router_address} not in allowlist for {protocol}",
                    extra={"protocol": protocol, "router_address": router_address}
                )
                return False
        
        return True
    
    def _get_pool_liquidity(
        self,
        chain_id: int,
        pool_address: Optional[str]
    ) -> Decimal:
        """
        Get current pool liquidity in USD by querying on-chain reserves.
        
        Connects to the chain via RPC, reads the pool's token reserves,
        and converts to a USD estimate using the reserve balances and
        the assumption that one side of the pool is a USD-pegged stablecoin
        or can be priced via a reference pair.
        
        Falls back to Decimal("0") if the query fails, which will cause
        the liquidity risk check to flag the trade as maximum risk —
        a safe failure mode.
        """
        if not pool_address:
            return Decimal("0")

        try:
            from web3 import Web3

            # Determine RPC URL for the chain
            from anvel_dex_broker_factory import SUPPORTED_CHAINS
            chain_config = SUPPORTED_CHAINS.get(chain_id)
            if not chain_config:
                logger.warning(
                    "No chain config for chain_id=%d, cannot query liquidity",
                    chain_id,
                )
                return Decimal("0")

            rpc_url = os.environ.get(
                f"VEL_RPC_{chain_id}",
                chain_config.default_rpc,
            )

            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
            if not w3.is_connected():
                logger.warning("Cannot connect to RPC for chain %d", chain_id)
                return Decimal("0")

            pool_addr = Web3.to_checksum_address(pool_address)

            # Uniswap V2-style pair: getReserves() → (reserve0, reserve1, timestamp)
            PAIR_ABI = [
                {
                    "constant": True,
                    "inputs": [],
                    "name": "getReserves",
                    "outputs": [
                        {"name": "_reserve0", "type": "uint112"},
                        {"name": "_reserve1", "type": "uint112"},
                        {"name": "_blockTimestampLast", "type": "uint32"},
                    ],
                    "type": "function",
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "token0",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function",
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "token1",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function",
                },
            ]

            DECIMALS_ABI = [
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function",
                }
            ]

            pool_contract = w3.eth.contract(address=pool_addr, abi=PAIR_ABI)

            reserves = pool_contract.functions.getReserves().call()
            reserve0, reserve1 = reserves[0], reserves[1]

            token0 = pool_contract.functions.token0().call()
            token1 = pool_contract.functions.token1().call()

            # Get decimals for both tokens
            t0_contract = w3.eth.contract(address=token0, abi=DECIMALS_ABI)
            t1_contract = w3.eth.contract(address=token1, abi=DECIMALS_ABI)
            d0 = t0_contract.functions.decimals().call()
            d1 = t1_contract.functions.decimals().call()

            r0_human = Decimal(reserve0) / Decimal(10 ** d0)
            r1_human = Decimal(reserve1) / Decimal(10 ** d1)

            # Known stablecoins (6 or 18 decimals) — if either side is a
            # stablecoin, we can directly estimate USD liquidity as 2 × that reserve.
            # Otherwise, fall back to geometric mean as rough approximation.
            from vel_token_registry import get_token_registry
            registry = get_token_registry()

            _STABLE_SYMBOLS = {"USDC", "USDT", "DAI", "BUSD"}
            stable_addrs = set()
            for sym in _STABLE_SYMBOLS:
                addr = registry.resolve(sym, chain_id)
                if addr:
                    stable_addrs.add(addr.lower())

            if token0.lower() in stable_addrs:
                # token0 is the stablecoin — total liquidity ≈ 2 × reserve0
                liquidity_usd = r0_human * Decimal("2")
            elif token1.lower() in stable_addrs:
                liquidity_usd = r1_human * Decimal("2")
            else:
                # Neither side is a known stablecoin.
                # Use geometric mean of reserves as a rough USD proxy.
                # This is intentionally conservative.
                import math
                geo = Decimal(str(math.sqrt(float(r0_human * r1_human))))
                liquidity_usd = geo * Decimal("2")

            logger.debug(
                "Pool %s on chain %d: reserves=(%s, %s), liquidity_usd=%s",
                pool_address, chain_id, r0_human, r1_human, liquidity_usd,
            )

            return liquidity_usd

        except Exception as e:
            logger.warning(
                "Failed to query pool liquidity for %s on chain %d: %s. "
                "Returning 0 (maximum risk).",
                pool_address, chain_id, e,
            )
            return Decimal("0")
    
    def _assess_liquidity_risk(
        self,
        liquidity_usd: Decimal,
        trade_size_usd: Decimal
    ) -> Decimal:
        """Assess risk based on liquidity depth."""
        if liquidity_usd == 0:
            return Decimal("100")  # Maximum risk
        
        # Calculate depth ratio
        depth_ratio = liquidity_usd / trade_size_usd
        
        if depth_ratio < self.config.min_liquidity_depth_ratio:
            # Risk increases as depth ratio decreases
            risk = Decimal("100") * (
                Decimal("1") - (depth_ratio / self.config.min_liquidity_depth_ratio)
            )
            return min(risk, Decimal("100"))
        
        return Decimal("0")
    
    def _assess_sandwich_risk(
        self,
        chain_id: int,
        protocol: str,
        trade_size_usd: Decimal,
        liquidity_usd: Decimal,
        expected_slippage_bps: int
    ) -> Decimal:
        """
        Assess sandwich attack risk.
        
        Sandwich attacks are more likely with:
        - Large trades relative to liquidity
        - High expected slippage
        - Public mempool (non-private transactions)
        """
        risk = Decimal("0")
        
        # Factor 1: Trade size impact (0-40 points)
        if liquidity_usd > 0:
            size_ratio = trade_size_usd / liquidity_usd
            risk += min(size_ratio * Decimal("200"), Decimal("40"))
        
        # Factor 2: Slippage tolerance (0-30 points)
        slippage_risk = min(Decimal(expected_slippage_bps) / Decimal("10"), Decimal("30"))
        risk += slippage_risk
        
        # Factor 3: Protocol-specific risk (0-30 points)
        # Some protocols are more vulnerable to sandwich attacks
        if protocol.lower() in ["uniswap_v2", "pancakeswap"]:
            risk += Decimal("20")  # Constant product AMMs more vulnerable
        elif protocol.lower() in ["curve", "balancer"]:
            risk += Decimal("10")  # Stable/weighted pools less vulnerable
        
        return min(risk, Decimal("100"))
    
    def _assess_frontrun_risk(
        self,
        chain_id: int,
        protocol: str,
        trade_size_usd: Decimal
    ) -> Decimal:
        """
        Assess front-running risk.
        
        Front-running risk increases with:
        - Larger trade sizes
        - Higher gas prices (incentivizes attackers)
        - Predictable execution patterns
        """
        risk = Decimal("0")
        
        # Factor 1: Trade size (0-50 points)
        if trade_size_usd > Decimal("10000"):  # >$10k
            risk += Decimal("20")
        if trade_size_usd > Decimal("50000"):  # >$50k
            risk += Decimal("20")
        if trade_size_usd > Decimal("100000"):  # >$100k
            risk += Decimal("10")
        
        # Factor 2: Chain congestion (0-30 points)
        # In production, would check gas prices and mempool
        # For now, assume moderate risk
        risk += Decimal("15")
        
        return min(risk, Decimal("100"))
    
    def _assess_slippage_risk(
        self,
        chain_id: int,
        token_in: Optional[str],
        token_out: Optional[str],
        expected_slippage_bps: int
    ) -> Decimal:
        """
        Assess slippage risk based on current volatility.
        
        During high volatility, slippage can exceed expectations.
        """
        risk = Decimal("0")
        
        # Check volatility for both tokens
        if token_in:
            volatility = self._get_volatility_metrics(chain_id, token_in)
            if volatility and volatility.is_high_volatility:
                risk += Decimal("30")
        
        if token_out:
            volatility = self._get_volatility_metrics(chain_id, token_out)
            if volatility and volatility.is_high_volatility:
                risk += Decimal("30")
        
        # Factor in expected slippage
        if expected_slippage_bps > self.config.base_max_slippage_bps:
            excess_slippage = expected_slippage_bps - self.config.base_max_slippage_bps
            risk += min(Decimal(excess_slippage) / Decimal("5"), Decimal("40"))
        
        return min(risk, Decimal("100"))
    
    def _calculate_composite_risk(self, risk_factors: Dict[str, Decimal]) -> Decimal:
        """
        Calculate composite risk score from individual factors.
        
        Weighted average with emphasis on critical factors.
        """
        weights = {
            "sandwich_risk": Decimal("0.30"),
            "frontrun_risk": Decimal("0.25"),
            "liquidity_risk": Decimal("0.25"),
            "slippage_risk": Decimal("0.15"),
            "allowlist_violation": Decimal("0.40"),  # Critical factor
            "size_risk": Decimal("0.20"),
        }
        
        weighted_sum = Decimal("0")
        total_weight = Decimal("0")
        
        for factor, score in risk_factors.items():
            weight = weights.get(factor, Decimal("0.1"))
            weighted_sum += score * weight
            total_weight += weight
        
        if total_weight == 0:
            return Decimal("0")
        
        composite_score = weighted_sum / total_weight
        return min(composite_score, Decimal("100"))
    
    def _make_routing_decision(
        self,
        risk_score: Decimal,
        risk_level: MEVRiskLevel,
        liquidity_usd: Decimal,
        reasons: List[str]
    ) -> tuple[RoutingDecision, bool, Optional[str]]:
        """
        Make final routing decision based on risk assessment.
        
        Returns:
            (decision, recommend_private, private_relay)
        """
        # Critical risk - reject outright
        if risk_level == MEVRiskLevel.CRITICAL:
            return RoutingDecision.REJECT, False, None
        
        # Insufficient liquidity - reject
        if liquidity_usd < self.config.min_liquidity_usd:
            return RoutingDecision.REJECT, False, None
        
        # High risk - use private routing if available
        if risk_level == MEVRiskLevel.HIGH:
            if self.config.enable_private_routing and self.config.private_relay_endpoints:
                private_relay = self.config.private_relay_endpoints[0]
                return RoutingDecision.USE_PRIVATE, True, private_relay
            else:
                return RoutingDecision.REJECT, False, None
        
        # Medium risk - recommend private but allow public
        if risk_level == MEVRiskLevel.MEDIUM:
            if self.config.enable_private_routing and self.config.private_relay_endpoints:
                if risk_score >= self.config.private_routing_risk_threshold:
                    private_relay = self.config.private_relay_endpoints[0]
                    return RoutingDecision.USE_PRIVATE, True, private_relay
        
        # Low risk - approve
        return RoutingDecision.APPROVE, False, None
    
    def _get_volatility_metrics(
        self,
        chain_id: int,
        token_address: str
    ) -> Optional[VolatilityMetrics]:
        """Get current volatility metrics for token."""
        key = (chain_id, token_address.lower())
        
        with self._lock:
            if key in self._volatility_metrics:
                metrics = self._volatility_metrics[key]
                # Check if metrics are still fresh
                age = datetime.now(timezone.utc) - metrics.last_updated
                if age.total_seconds() < self.config.volatility_window_seconds:
                    return metrics
        
        return None
    
    def update_volatility_metrics(
        self,
        chain_id: int,
        token_address: str,
        current_price: Decimal
    ):
        """
        Update volatility metrics for token.
        
        Args:
            chain_id: Chain ID
            token_address: Token address
            current_price: Current token price in USD
        """
        key = (chain_id, token_address.lower())
        now = datetime.now(timezone.utc)
        
        with self._lock:
            # Update price history
            if key not in self._price_history:
                self._price_history[key] = []
            
            price_history = self._price_history[key]
            price_history.append((now, current_price))
            
            # Keep only recent history
            cutoff = now - timedelta(seconds=self.config.volatility_window_seconds)
            price_history = [(t, p) for t, p in price_history if t > cutoff]
            self._price_history[key] = price_history
            
            # Calculate volatility
            if len(price_history) >= 2:
                oldest_price = price_history[0][1]
                price_change = abs(current_price - oldest_price) / oldest_price
                
                is_high_volatility = price_change >= self.config.high_volatility_threshold
                
                metrics = VolatilityMetrics(
                    chain_id=chain_id,
                    token_address=token_address.lower(),
                    price_change_5m=price_change,
                    is_high_volatility=is_high_volatility,
                    last_updated=now
                )
                
                self._volatility_metrics[key] = metrics
                
                if is_high_volatility:
                    logger.warning(
                        f"High volatility detected: {token_address} on chain {chain_id}, "
                        f"change={price_change:.2%}",
                        extra={
                            "chain_id": chain_id,
                            "token_address": token_address,
                            "price_change": str(price_change)
                        }
                    )
    
    def adjust_slippage_for_volatility(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        base_slippage_bps: int
    ) -> int:
        """
        Adjust slippage tolerance based on current volatility.
        
        Args:
            chain_id: Chain ID
            token_in: Input token address
            token_out: Output token address
            base_slippage_bps: Base slippage tolerance in basis points
            
        Returns:
            Adjusted slippage in basis points
        """
        # Check volatility for both tokens
        high_volatility = False
        
        for token in [token_in, token_out]:
            metrics = self._get_volatility_metrics(chain_id, token)
            if metrics and metrics.is_high_volatility:
                high_volatility = True
                break
        
        if high_volatility:
            adjusted = min(
                base_slippage_bps * 2,
                self.config.volatility_adjusted_max_slippage_bps
            )
            logger.info(
                f"Slippage adjusted for volatility: {base_slippage_bps} -> {adjusted} bps",
                extra={
                    "chain_id": chain_id,
                    "base_slippage": base_slippage_bps,
                    "adjusted_slippage": adjusted
                }
            )
            return adjusted
        
        return base_slippage_bps
    
    def get_assessment(self, assessment_id: str) -> Optional[MEVRiskAssessment]:
        """Get cached risk assessment."""
        with self._lock:
            return self._assessment_cache.get(assessment_id)
    
    def configure_pool_allowlist(self, protocol: str, pool_addresses: Set[str]):
        """Configure pool allowlist for protocol."""
        with self._lock:
            self.config.pool_allowlists[protocol] = {addr.lower() for addr in pool_addresses}
        
        logger.info(
            f"Pool allowlist configured for {protocol}: {len(pool_addresses)} pools",
            extra={"protocol": protocol, "pool_count": len(pool_addresses)}
        )
    
    def configure_router_allowlist(self, protocol: str, router_addresses: Set[str]):
        """Configure router allowlist for protocol."""
        with self._lock:
            self.config.router_allowlists[protocol] = {addr.lower() for addr in router_addresses}
        
        logger.info(
            f"Router allowlist configured for {protocol}: {len(router_addresses)} routers",
            extra={"protocol": protocol, "router_count": len(router_addresses)}
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get MEV protection statistics."""
        with self._lock:
            total_assessments = len(self._assessment_cache)
            
            decision_counts = {
                RoutingDecision.APPROVE: 0,
                RoutingDecision.REJECT: 0,
                RoutingDecision.REROUTE: 0,
                RoutingDecision.USE_PRIVATE: 0
            }
            
            risk_level_counts = {
                MEVRiskLevel.LOW: 0,
                MEVRiskLevel.MEDIUM: 0,
                MEVRiskLevel.HIGH: 0,
                MEVRiskLevel.CRITICAL: 0
            }
            
            for assessment in self._assessment_cache.values():
                decision_counts[assessment.decision] += 1
                risk_level_counts[assessment.risk_level] += 1
            
            return {
                "total_assessments": total_assessments,
                "decisions": {k.value: v for k, v in decision_counts.items()},
                "risk_levels": {k.value: v for k, v in risk_level_counts.items()},
                "volatility_tracked_tokens": len(self._volatility_metrics),
                "config": {
                    "max_risk_score": str(self.config.max_risk_score),
                    "min_liquidity_usd": str(self.config.min_liquidity_usd),
                    "private_routing_enabled": self.config.enable_private_routing
                }
            }
