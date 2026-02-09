#!/usr/bin/env python3
"""
ANVEL Eternal Learning Engine
==============================

Continuous AI learning engine that runs perpetually, learning from:
- Market data patterns
- Trading outcomes
- Strategy performance
- On-chain events

This module provides adaptive machine learning that improves over time
without manual retraining.

Features:
- Continuous model updates
- Knowledge persistence
- AWS S3/EFS integration for model storage
- CloudWatch metrics integration
- Graceful degradation when dependencies unavailable
"""

import logging
import threading
import time
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_LEARNING_INTERVAL = 60  # seconds
MAX_KNOWLEDGE_ENTRIES = 10000
MODEL_CHECKPOINT_INTERVAL = 300  # 5 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE STORE
# ═══════════════════════════════════════════════════════════════════════════════

class KnowledgeStore:
    """Persistent knowledge storage for learned patterns."""
    
    def __init__(self, persist_path: Optional[str] = None):
        self.persist_path = persist_path
        self.knowledge: Dict[str, Any] = {}
        self.patterns: deque = deque(maxlen=MAX_KNOWLEDGE_ENTRIES)
        self.lock = threading.RLock()
        self._load_existing()
    
    def _load_existing(self):
        """Load existing knowledge from disk."""
        if self.persist_path and Path(self.persist_path).exists():
            try:
                with open(self.persist_path, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            self.patterns.append(entry)
                        except json.JSONDecodeError:
                            continue
                logger.info(f"Loaded {len(self.patterns)} knowledge entries")
            except Exception as e:
                logger.warning(f"Could not load knowledge: {e}")
    
    def add_pattern(self, pattern_type: str, data: Dict[str, Any]):
        """Add a learned pattern to the store."""
        with self.lock:
            entry = {
                "type": pattern_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.patterns.append(entry)
            
            # Persist to disk
            if self.persist_path:
                try:
                    Path(self.persist_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(self.persist_path, 'a') as f:
                        f.write(json.dumps(entry) + "\n")
                except Exception as e:
                    logger.warning(f"Could not persist pattern: {e}")
    
    def get_patterns(self, pattern_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Retrieve patterns from the store."""
        with self.lock:
            patterns = list(self.patterns)
            if pattern_type:
                patterns = [p for p in patterns if p.get("type") == pattern_type]
            return patterns[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge store statistics."""
        with self.lock:
            type_counts = {}
            for p in self.patterns:
                t = p.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            
            return {
                "total_patterns": len(self.patterns),
                "pattern_types": type_counts,
                "persist_path": self.persist_path,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# LEARNING STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

class LearningStrategy:
    """Base class for learning strategies."""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.last_run = None
        self.metrics = {"runs": 0, "patterns_found": 0}
    
    def learn(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process data and return learned patterns.
        Override in subclasses.
        """
        raise NotImplementedError
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "last_run": self.last_run,
            **self.metrics
        }


class PricePatternLearner(LearningStrategy):
    """Learn price movement patterns."""
    
    def __init__(self):
        super().__init__("price_patterns")
        self.price_history: Dict[str, deque] = {}
    
    def learn(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = []
        
        prices = data.get("prices", {})
        for symbol, price in prices.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=1000)
            
            self.price_history[symbol].append({
                "price": price,
                "timestamp": time.time()
            })
            
            # Simple pattern detection: significant moves
            history = list(self.price_history[symbol])
            if len(history) >= 10:
                recent = [h["price"] for h in history[-10:]]
                avg = sum(recent) / len(recent)
                current = recent[-1]
                
                # Detect >2% deviation
                if abs(current - avg) / avg > 0.02:
                    direction = "up" if current > avg else "down"
                    patterns.append({
                        "symbol": symbol,
                        "pattern": f"significant_move_{direction}",
                        "magnitude": (current - avg) / avg,
                        "price": current,
                    })
        
        self.metrics["runs"] += 1
        self.metrics["patterns_found"] += len(patterns)
        self.last_run = datetime.utcnow().isoformat()
        
        return patterns


class TradingOutcomeLearner(LearningStrategy):
    """Learn from trading outcomes."""
    
    def __init__(self):
        super().__init__("trading_outcomes")
        self.outcomes: deque = deque(maxlen=1000)
    
    def learn(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = []
        
        trades = data.get("trades", [])
        for trade in trades:
            self.outcomes.append(trade)
            
            # Analyze outcome
            pnl = trade.get("pnl", 0)
            strategy = trade.get("strategy", "unknown")
            
            if pnl != 0:
                patterns.append({
                    "strategy": strategy,
                    "outcome": "profit" if pnl > 0 else "loss",
                    "magnitude": abs(pnl),
                    "conditions": trade.get("conditions", {}),
                })
        
        self.metrics["runs"] += 1
        self.metrics["patterns_found"] += len(patterns)
        self.last_run = datetime.utcnow().isoformat()
        
        return patterns


class VolatilityLearner(LearningStrategy):
    """Learn volatility patterns."""
    
    def __init__(self):
        super().__init__("volatility")
        self.volatility_history: Dict[str, deque] = {}
    
    def learn(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = []
        
        volatility = data.get("volatility", {})
        for symbol, vol in volatility.items():
            if symbol not in self.volatility_history:
                self.volatility_history[symbol] = deque(maxlen=100)
            
            self.volatility_history[symbol].append(vol)
            
            history = list(self.volatility_history[symbol])
            if len(history) >= 5:
                avg_vol = sum(history) / len(history)
                
                # Detect volatility spikes
                if vol > avg_vol * 1.5:
                    patterns.append({
                        "symbol": symbol,
                        "pattern": "volatility_spike",
                        "current": vol,
                        "average": avg_vol,
                        "ratio": vol / avg_vol,
                    })
        
        self.metrics["runs"] += 1
        self.metrics["patterns_found"] += len(patterns)
        self.last_run = datetime.utcnow().isoformat()
        
        return patterns


# ═══════════════════════════════════════════════════════════════════════════════
# ETERNAL LEARNING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class EternalLearningEngine:
    """
    Continuous learning engine that runs perpetually.
    
    Features:
    - Multiple learning strategies
    - Knowledge persistence
    - AWS integration (S3, EFS, CloudWatch)
    - Graceful shutdown
    """
    
    def __init__(
        self,
        symbols: List[str],
        interval_seconds: int = DEFAULT_LEARNING_INTERVAL,
        s3_bucket: Optional[str] = None,
        efs_mount: Optional[str] = None,
        enable_cloudwatch: bool = False,
        knowledge_persist_path: Optional[str] = None,
    ):
        self.symbols = symbols
        self.interval = interval_seconds
        self.s3_bucket = s3_bucket
        self.efs_mount = efs_mount
        self.enable_cloudwatch = enable_cloudwatch
        
        # Knowledge storage
        persist_path = knowledge_persist_path or (
            f"{efs_mount}/knowledge.jsonl" if efs_mount else "./data/knowledge.jsonl"
        )
        self.knowledge = KnowledgeStore(persist_path)
        
        # Learning strategies
        self.strategies: List[LearningStrategy] = [
            PricePatternLearner(),
            TradingOutcomeLearner(),
            VolatilityLearner(),
        ]
        
        # Data providers
        self.data_providers: List[Callable[[], Dict[str, Any]]] = []
        
        # Runtime state
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_checkpoint = time.time()
        
        # Metrics
        self.metrics = {
            "started_at": None,
            "iterations": 0,
            "total_patterns": 0,
            "errors": 0,
        }
        
        logger.info(f"EternalLearningEngine initialized for {len(symbols)} symbols")
    
    def register_data_provider(self, provider: Callable[[], Dict[str, Any]]):
        """Register a data provider function."""
        self.data_providers.append(provider)
    
    def add_strategy(self, strategy: LearningStrategy):
        """Add a learning strategy."""
        self.strategies.append(strategy)
    
    def start(self):
        """Start the eternal learning loop."""
        if self.running:
            logger.warning("Learning engine already running")
            return
        
        self.running = True
        self._stop_event.clear()
        self.metrics["started_at"] = datetime.utcnow().isoformat()
        
        self._thread = threading.Thread(target=self._learning_loop, daemon=True)
        self._thread.start()
        
        logger.info("Eternal learning engine started")
    
    def stop(self):
        """Stop the learning engine."""
        if not self.running:
            return
        
        self.running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        self._save_checkpoint()
        logger.info("Eternal learning engine stopped")
    
    def _learning_loop(self):
        """Main learning loop."""
        while not self._stop_event.is_set():
            try:
                self._learning_iteration()
            except Exception as e:
                logger.error(f"Learning iteration error: {e}")
                self.metrics["errors"] += 1
            
            # Check for checkpoint
            if time.time() - self._last_checkpoint > MODEL_CHECKPOINT_INTERVAL:
                self._save_checkpoint()
                self._last_checkpoint = time.time()
            
            self._stop_event.wait(self.interval)
    
    def _learning_iteration(self):
        """Single learning iteration."""
        # Gather data
        data = self._gather_data()
        
        # Run all strategies
        total_patterns = 0
        for strategy in self.strategies:
            if not strategy.enabled:
                continue
            
            try:
                patterns = strategy.learn(data)
                for pattern in patterns:
                    self.knowledge.add_pattern(strategy.name, pattern)
                    total_patterns += 1
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} error: {e}")
        
        self.metrics["iterations"] += 1
        self.metrics["total_patterns"] += total_patterns
        
        # Send to CloudWatch if enabled
        if self.enable_cloudwatch and total_patterns > 0:
            self._send_cloudwatch_metrics(total_patterns)
    
    def _gather_data(self) -> Dict[str, Any]:
        """Gather data from all providers."""
        data = {
            "symbols": self.symbols,
            "timestamp": time.time(),
            "prices": {},
            "trades": [],
            "volatility": {},
        }
        
        for provider in self.data_providers:
            try:
                provider_data = provider()
                if isinstance(provider_data, dict):
                    for key, value in provider_data.items():
                        if key in data and isinstance(data[key], dict):
                            data[key].update(value)
                        elif key in data and isinstance(data[key], list):
                            data[key].extend(value if isinstance(value, list) else [value])
                        else:
                            data[key] = value
            except Exception as e:
                logger.warning(f"Data provider error: {e}")
        
        return data
    
    def _save_checkpoint(self):
        """Save model checkpoint."""
        checkpoint = {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": self.metrics,
            "knowledge_stats": self.knowledge.get_stats(),
            "strategy_metrics": [s.get_metrics() for s in self.strategies],
        }
        
        # Save to EFS if available
        if self.efs_mount:
            try:
                checkpoint_path = Path(self.efs_mount) / "checkpoints" / f"checkpoint_{int(time.time())}.json"
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                with open(checkpoint_path, 'w') as f:
                    json.dump(checkpoint, f, indent=2)
                logger.debug(f"Saved checkpoint to {checkpoint_path}")
            except Exception as e:
                logger.warning(f"Could not save checkpoint to EFS: {e}")
        
        # Upload to S3 if available
        if self.s3_bucket:
            self._upload_to_s3(checkpoint)
    
    def _upload_to_s3(self, checkpoint: Dict[str, Any]):
        """Upload checkpoint to S3."""
        try:
            import boto3
            s3 = boto3.client('s3')
            key = f"checkpoints/checkpoint_{int(time.time())}.json"
            s3.put_object(
                Bucket=self.s3_bucket,
                Key=key,
                Body=json.dumps(checkpoint),
                ContentType='application/json'
            )
            logger.debug(f"Uploaded checkpoint to s3://{self.s3_bucket}/{key}")
        except ImportError:
            pass  # boto3 not available
        except Exception as e:
            logger.warning(f"Could not upload to S3: {e}")
    
    def _send_cloudwatch_metrics(self, patterns_count: int):
        """Send metrics to CloudWatch."""
        try:
            import boto3
            cloudwatch = boto3.client('cloudwatch')
            cloudwatch.put_metric_data(
                Namespace='VEL/Learning',
                MetricData=[
                    {
                        'MetricName': 'PatternsLearned',
                        'Value': patterns_count,
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'LearningIterations',
                        'Value': self.metrics["iterations"],
                        'Unit': 'Count'
                    },
                ]
            )
        except ImportError:
            pass  # boto3 not available
        except Exception as e:
            logger.warning(f"Could not send CloudWatch metrics: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        return {
            "running": self.running,
            "symbols": self.symbols,
            "interval": self.interval,
            "metrics": self.metrics,
            "knowledge": self.knowledge.get_stats(),
            "strategies": [s.get_metrics() for s in self.strategies],
        }
    
    def get_insights(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent learned insights."""
        return self.knowledge.get_patterns(limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def create_eternal_engine(
    symbols: List[str],
    interval_seconds: int = DEFAULT_LEARNING_INTERVAL,
    s3_bucket: Optional[str] = None,
    efs_mount: Optional[str] = None,
    enable_cloudwatch: bool = False,
    knowledge_persist_path: Optional[str] = None,
) -> EternalLearningEngine:
    """
    Factory function to create an EternalLearningEngine.
    
    Args:
        symbols: List of trading symbols to learn from
        interval_seconds: Learning interval in seconds
        s3_bucket: Optional S3 bucket for model storage
        efs_mount: Optional EFS mount point for shared storage
        enable_cloudwatch: Enable CloudWatch metrics
        knowledge_persist_path: Path to persist knowledge
    
    Returns:
        Configured EternalLearningEngine instance
    """
    return EternalLearningEngine(
        symbols=symbols,
        interval_seconds=interval_seconds,
        s3_bucket=s3_bucket,
        efs_mount=efs_mount,
        enable_cloudwatch=enable_cloudwatch,
        knowledge_persist_path=knowledge_persist_path,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN (for testing)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create engine
    engine = create_eternal_engine(
        symbols=["ETH", "BTC", "USDC"],
        interval_seconds=5,
        knowledge_persist_path="./data/test_knowledge.jsonl",
    )
    
    # Add test data provider
    def test_provider():
        import random
        return {
            "prices": {
                "ETH": 2000 + random.uniform(-100, 100),
                "BTC": 40000 + random.uniform(-2000, 2000),
            },
            "volatility": {
                "ETH": random.uniform(0.01, 0.05),
                "BTC": random.uniform(0.01, 0.03),
            }
        }
    
    engine.register_data_provider(test_provider)
    
    # Start and run for a bit
    engine.start()
    
    try:
        print("Learning engine running. Press Ctrl+C to stop.")
        while True:
            time.sleep(10)
            status = engine.get_status()
            print(f"Iterations: {status['metrics']['iterations']}, Patterns: {status['metrics']['total_patterns']}")
    except KeyboardInterrupt:
        engine.stop()
        print("Engine stopped")
