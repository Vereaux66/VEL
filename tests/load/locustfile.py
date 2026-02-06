#!/usr/bin/env python3
"""
VEL Load Testing Suite
======================

Production load testing using Locust.

Usage:
    # Run load test
    locust -f tests/load/locustfile.py --host http://localhost:8080
    
    # Run with specific user count
    locust -f tests/load/locustfile.py --host http://localhost:8080 -u 100 -r 10 --headless
    
    # Run distributed
    locust -f tests/load/locustfile.py --master
    locust -f tests/load/locustfile.py --worker

Test Scenarios:
1. Health check - Basic availability
2. Authentication - Login flow
3. Trading - Trade execution endpoints
4. WebSocket - Real-time data streams
"""

import json
import random
import time
from locust import HttpUser, TaskSet, task, between, events
from locust.runners import MasterRunner


# =============================================================================
# Test Configuration
# =============================================================================

# Sample trade data
SAMPLE_TOKENS = [
    ("USDC", "ETH"),
    ("USDC", "BTC"),
    ("ETH", "USDC"),
    ("WBTC", "ETH"),
    ("USDC", "MATIC"),
]

SAMPLE_CHAINS = [1, 137, 42161, 10]  # Ethereum, Polygon, Arbitrum, Optimism

SAMPLE_PROTOCOLS = ["uniswap_v3", "sushiswap", "curve", "balancer"]


# =============================================================================
# Health Check Tasks
# =============================================================================

class HealthTasks(TaskSet):
    """Health check and monitoring endpoint tests."""
    
    @task(10)
    def health_check(self):
        """Basic health check endpoint."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(5)
    def readiness_check(self):
        """Readiness probe endpoint."""
        with self.client.get("/api/readiness", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Readiness check failed: {response.status_code}")
    
    @task(2)
    def metrics_check(self):
        """Prometheus metrics endpoint."""
        with self.client.get("/metrics", catch_response=True) as response:
            if response.status_code in (200, 403):  # 403 if internal-only
                response.success()
            else:
                response.failure(f"Metrics failed: {response.status_code}")


# =============================================================================
# Authentication Tasks
# =============================================================================

class AuthTasks(TaskSet):
    """Authentication flow tests."""
    
    @task(1)
    def login_attempt(self):
        """Test login endpoint rate limiting."""
        payload = {
            "username": f"loadtest_user_{random.randint(1, 1000)}",
            "password": "test_password_123"
        }
        
        with self.client.post(
            "/api/login",
            json=payload,
            catch_response=True
        ) as response:
            # Login may fail (no real user) but endpoint should respond
            if response.status_code in (200, 401, 429):
                response.success()
            else:
                response.failure(f"Login failed unexpectedly: {response.status_code}")
    
    @task(5)
    def token_validation(self):
        """Test token validation (protected endpoint)."""
        headers = {"Authorization": "Bearer test_invalid_token"}
        
        with self.client.get(
            "/api/user/profile",
            headers=headers,
            catch_response=True
        ) as response:
            # Should get 401 for invalid token
            if response.status_code in (401, 403, 404):
                response.success()
            else:
                response.failure(f"Token validation unexpected: {response.status_code}")


# =============================================================================
# Trading Tasks
# =============================================================================

class TradingTasks(TaskSet):
    """Trading endpoint tests."""
    
    def on_start(self):
        """Login and get auth token on task start."""
        self.auth_token = None
        self._try_login()
    
    def _try_login(self):
        """Attempt to login and get token."""
        payload = {
            "username": "loadtest_trader",
            "password": "secure_test_password_123"
        }
        response = self.client.post("/api/login", json=payload)
        if response.status_code == 200:
            data = response.json()
            self.auth_token = data.get("token")
    
    def _get_headers(self):
        """Get request headers with auth token."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers
    
    @task(3)
    def get_market_data(self):
        """Fetch market data."""
        with self.client.get(
            "/api/market/prices",
            headers=self._get_headers(),
            catch_response=True
        ) as response:
            if response.status_code in (200, 401, 404):
                response.success()
            else:
                response.failure(f"Market data failed: {response.status_code}")
    
    @task(2)
    def get_portfolio(self):
        """Fetch user portfolio."""
        with self.client.get(
            "/api/portfolio",
            headers=self._get_headers(),
            catch_response=True
        ) as response:
            if response.status_code in (200, 401, 404):
                response.success()
            else:
                response.failure(f"Portfolio failed: {response.status_code}")
    
    @task(5)
    def get_quote(self):
        """Get trade quote."""
        token_in, token_out = random.choice(SAMPLE_TOKENS)
        chain_id = random.choice(SAMPLE_CHAINS)
        amount = random.uniform(10, 1000)
        
        payload = {
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": str(amount),
            "chain_id": chain_id,
            "protocol": random.choice(SAMPLE_PROTOCOLS)
        }
        
        with self.client.post(
            "/api/quote",
            json=payload,
            headers=self._get_headers(),
            catch_response=True
        ) as response:
            if response.status_code in (200, 400, 401, 404, 429):
                response.success()
            else:
                response.failure(f"Quote failed: {response.status_code}")
    
    @task(1)
    def simulate_trade(self):
        """Simulate trade execution (dry-run)."""
        token_in, token_out = random.choice(SAMPLE_TOKENS)
        chain_id = random.choice(SAMPLE_CHAINS)
        amount = random.uniform(10, 1000)
        
        payload = {
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": str(amount),
            "chain_id": chain_id,
            "protocol": random.choice(SAMPLE_PROTOCOLS),
            "max_slippage": "0.5",
            "dry_run": True  # Always simulate in load tests
        }
        
        with self.client.post(
            "/api/trade/execute",
            json=payload,
            headers=self._get_headers(),
            catch_response=True
        ) as response:
            # Trade may be blocked by risk controls, which is OK
            if response.status_code in (200, 400, 401, 403, 404, 429):
                response.success()
            else:
                response.failure(f"Trade simulate failed: {response.status_code}")
    
    @task(2)
    def get_trade_history(self):
        """Fetch trade history."""
        with self.client.get(
            "/api/trades/history?limit=10",
            headers=self._get_headers(),
            catch_response=True
        ) as response:
            if response.status_code in (200, 401, 404):
                response.success()
            else:
                response.failure(f"Trade history failed: {response.status_code}")


# =============================================================================
# Risk Engine Tasks
# =============================================================================

class RiskTasks(TaskSet):
    """Risk engine endpoint tests."""
    
    @task(5)
    def get_risk_status(self):
        """Check risk engine status."""
        with self.client.get(
            "/api/risk/status",
            catch_response=True
        ) as response:
            if response.status_code in (200, 401, 404):
                response.success()
            else:
                response.failure(f"Risk status failed: {response.status_code}")
    
    @task(3)
    def get_circuit_breaker_status(self):
        """Check circuit breaker status."""
        with self.client.get(
            "/api/risk/circuit-breaker",
            catch_response=True
        ) as response:
            if response.status_code in (200, 401, 404):
                response.success()
            else:
                response.failure(f"Circuit breaker failed: {response.status_code}")


# =============================================================================
# User Classes
# =============================================================================

class HealthCheckUser(HttpUser):
    """User focused on health checks (high volume, low impact)."""
    tasks = [HealthTasks]
    wait_time = between(0.5, 2)
    weight = 3


class AuthUser(HttpUser):
    """User focused on authentication flows."""
    tasks = [AuthTasks]
    wait_time = between(1, 3)
    weight = 2


class TraderUser(HttpUser):
    """User simulating trading activity."""
    tasks = [TradingTasks]
    wait_time = between(2, 5)
    weight = 10


class RiskMonitorUser(HttpUser):
    """User checking risk status."""
    tasks = [RiskTasks]
    wait_time = between(5, 15)
    weight = 1


# =============================================================================
# Event Hooks
# =============================================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 60)
    print("VEL Load Test Starting")
    print("=" * 60)
    print(f"Host: {environment.host}")
    if isinstance(environment.runner, MasterRunner):
        print("Running in distributed mode (master)")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("=" * 60)
    print("VEL Load Test Complete")
    print("=" * 60)
    
    # Print summary statistics
    if environment.stats.total.num_requests > 0:
        print(f"Total Requests: {environment.stats.total.num_requests}")
        print(f"Failures: {environment.stats.total.num_failures}")
        print(f"Avg Response Time: {environment.stats.total.avg_response_time:.2f}ms")
        print(f"Min Response Time: {environment.stats.total.min_response_time:.2f}ms")
        print(f"Max Response Time: {environment.stats.total.max_response_time:.2f}ms")
        print(f"RPS: {environment.stats.total.current_rps:.2f}")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Called for each request (use sparingly, impacts performance)."""
    if exception:
        print(f"Request failed: {name} - {exception}")
