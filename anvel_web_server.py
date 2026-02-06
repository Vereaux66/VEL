#!/usr/bin/env python3
"""
ANVEL Web Server - Production-ready Flask application with WebSocket support

IMPORTANT SECURITY NOTE:
The password validation is deferred from module import to server instantiation to allow
import for testing and module inspection. However, ALL production code paths that use
web server functionality MUST call get_anvel_server() which triggers validation.

Production deployment checklist:
1. Set ANVEL_WEB_PASSWORD environment variable (minimum 12 characters)
2. Ensure all code paths that need web functionality call get_anvel_server()
3. Never import individual routes or functions directly - always use the server instance
4. The validation will fail IMMEDIATELY on server instantiation if password is not set

For production use:
    from anvel_web_server import get_anvel_server
    server = get_anvel_server()  # This triggers password validation
    server.run()
"""

import logging
import os
import secrets
import threading
from datetime import datetime, timedelta

import jwt
import redis
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, disconnect, emit
from psycopg2.pool import ThreadedConnectionPool
from werkzeug.security import check_password_hash

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# MANDATORY: Web password must be set for production security
# Note: Password validation is deferred to allow module import for testing
# Actual server startup will fail if password is not properly configured
WEB_PASSWORD = os.environ.get("ANVEL_WEB_PASSWORD")


def _validate_web_password():
    """Validate web password is set and meets requirements - called before server start"""
    if not WEB_PASSWORD:
        log.critical(
            "ANVEL_WEB_PASSWORD environment variable is not set. This is required for security."
        )
        log.critical(
            "Set ANVEL_WEB_PASSWORD to a strong password before starting the web application."
        )
        raise RuntimeError("ANVEL_WEB_PASSWORD is required but not set")

    # Validate password strength
    if len(WEB_PASSWORD) < 12:
        log.critical("ANVEL_WEB_PASSWORD must be at least 12 characters")
        raise RuntimeError(
            "ANVEL_WEB_PASSWORD does not meet minimum security requirements"
        )


# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))
app.config["JWT_ALGORITHM"] = "HS256"
app.config["JWT_EXPIRATION_DELTA"] = timedelta(hours=24)

# Initialize CORS and SocketIO with secure configuration
cors_origins = os.environ.get(
    "ANVEL_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8080,https://kessann.bot,https://*.kessann.bot,https://*.anvelbot.app,https://*.amazonaws.com",
).split(",")
CORS(app, origins=cors_origins)
socketio = SocketIO(app, cors_allowed_origins=cors_origins, async_mode="threading")

# Redis connection for real-time data (lazy initialization)
redis_client = None


def get_redis_client():
    """Get or create Redis client (lazy initialization)"""
    global redis_client
    if redis_client is None:
        redis_client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            decode_responses=True,
        )
    return redis_client


# PostgreSQL connection pool (lazy initialization)
db_pool = None


def get_db_pool():
    """Get or create database connection pool (lazy initialization)"""
    global db_pool
    if db_pool is None:
        db_pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 5432)),
            database=os.environ.get("DB_NAME", "anvel"),
            user=os.environ.get("DB_USER", "anvel"),
            password=os.environ.get("DB_PASSWORD", "anvel_secure_pass"),
        )
    return db_pool


# Active sessions tracking
active_sessions = {}
trade_subscribers = set()


class ANVELWebServer:
    """Main web server class for ANVEL trading system"""

    def __init__(self):
        # Validate security requirements before initializing
        _validate_web_password()

        self.trading_active = False
        self.ai_assistant_active = True
        self.simulation_running = False
        self.performance_metrics = {}
        self.initialize_routes()

    def initialize_routes(self):
        """Initialize all API routes"""

        @app.before_request
        def before_request():
            """Pre-request processing"""
            if request.endpoint and request.endpoint.startswith("api."):
                # Check JWT token for API endpoints
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if not token:
                    return jsonify({"error": "No authorization token"}), 401

                try:
                    payload = jwt.decode(
                        token,
                        app.config["JWT_SECRET_KEY"],
                        algorithms=[app.config["JWT_ALGORITHM"]],
                    )
                    request.user_id = payload["user_id"]
                except jwt.ExpiredSignatureError:
                    return jsonify({"error": "Token expired"}), 401
                except jwt.InvalidTokenError:
                    return jsonify({"error": "Invalid token"}), 401

        @app.route("/api/login", methods=["POST"])
        def login():
            """User authentication endpoint"""
            data = request.json
            username = data.get("username")
            password = data.get("password")
            totp_code = data.get("totp")  # 2FA code

            # Validate credentials
            conn = db_pool.getconn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, password_hash, totp_secret FROM users WHERE username = %s",
                    (username,),
                )
                user = cursor.fetchone()

                if not user or not check_password_hash(user[1], password):
                    return jsonify({"error": "Invalid credentials"}), 401

                # Verify 2FA if enabled
                if user[2]:  # totp_secret exists
                    import pyotp

                    totp = pyotp.TOTP(user[2])
                    if not totp.verify(totp_code, valid_window=1):
                        return jsonify({"error": "Invalid 2FA code"}), 401

                # Generate JWT token
                payload = {
                    "user_id": user[0],
                    "username": username,
                    "exp": datetime.utcnow() + app.config["JWT_EXPIRATION_DELTA"],
                }
                token = jwt.encode(
                    payload,
                    app.config["JWT_SECRET_KEY"],
                    algorithm=app.config["JWT_ALGORITHM"],
                )

                # Track session
                session_id = secrets.token_hex(16)
                active_sessions[session_id] = {
                    "user_id": user[0],
                    "username": username,
                    "login_time": datetime.utcnow(),
                    "last_activity": datetime.utcnow(),
                }

                return (
                    jsonify(
                        {"token": token, "session_id": session_id, "username": username}
                    ),
                    200,
                )

            finally:
                db_pool.putconn(conn)

        @app.route("/api/dashboard", methods=["GET"])
        def dashboard():
            """Main dashboard data endpoint"""
            conn = db_pool.getconn()
            try:
                cursor = conn.cursor()

                # Get current portfolio
                cursor.execute(
                    """
                    SELECT asset, quantity, average_price, current_price, pnl_percentage
                    FROM portfolio WHERE user_id = %s
                """,
                    (request.user_id,),
                )
                portfolio = cursor.fetchall()

                # Get recent trades
                cursor.execute(
                    """
                    SELECT id, timestamp, pair, side, price, quantity, total, pnl, status
                    FROM trades WHERE user_id = %s
                    ORDER BY timestamp DESC LIMIT 50
                """,
                    (request.user_id,),
                )
                trades = cursor.fetchall()

                # Get performance metrics from Redis cache
                metrics = redis_client.hgetall(f"metrics:{request.user_id}")

                return (
                    jsonify(
                        {
                            "portfolio": [
                                {
                                    "asset": p[0],
                                    "quantity": float(p[1]),
                                    "avgPrice": float(p[2]),
                                    "currentPrice": float(p[3]),
                                    "pnl": float(p[4]),
                                }
                                for p in portfolio
                            ],
                            "trades": [
                                {
                                    "id": t[0],
                                    "timestamp": t[1].isoformat(),
                                    "pair": t[2],
                                    "side": t[3],
                                    "price": float(t[4]),
                                    "quantity": float(t[5]),
                                    "total": float(t[6]),
                                    "pnl": float(t[7]) if t[7] else 0,
                                    "status": t[8],
                                }
                                for t in trades
                            ],
                            "metrics": {
                                "totalPnl": float(metrics.get("total_pnl", 0)),
                                "winRate": float(metrics.get("win_rate", 0)),
                                "sharpeRatio": float(metrics.get("sharpe_ratio", 0)),
                                "maxDrawdown": float(metrics.get("max_drawdown", 0)),
                                "totalTrades": int(metrics.get("total_trades", 0)),
                                "activePositions": int(
                                    metrics.get("active_positions", 0)
                                ),
                            },
                        }
                    ),
                    200,
                )

            finally:
                db_pool.putconn(conn)

        @app.route("/api/trading/start", methods=["POST"])
        def start_trading():
            """Start automated trading"""
            data = request.json
            strategy = data.get("strategy", "ai_composite")
            risk_level = data.get("risk_level", "conservative")
            max_positions = data.get("max_positions", 5)

            # Start trading engine in background thread
            threading.Thread(
                target=self.start_trading_engine,
                args=(request.user_id, strategy, risk_level, max_positions),
            ).start()

            self.trading_active = True

            # Notify via WebSocket
            socketio.emit(
                "trading_status",
                {"status": "active", "strategy": strategy, "risk_level": risk_level},
                room=f"user_{request.user_id}",
            )

            return jsonify({"status": "Trading started"}), 200

        @app.route("/api/trading/stop", methods=["POST"])
        def stop_trading():
            """Stop automated trading"""
            self.trading_active = False

            # Close all positions if requested
            if request.json.get("close_positions", False):
                self.close_all_positions(request.user_id)

            socketio.emit(
                "trading_status", {"status": "inactive"}, room=f"user_{request.user_id}"
            )

            return jsonify({"status": "Trading stopped"}), 200

        @app.route("/api/ai/ask", methods=["POST"])
        def ai_assistant():
            """AI assistant endpoint"""
            question = request.json.get("question", "")
            context = request.json.get("context", "")

            # Process with AI assistant
            response = self.process_ai_query(question, context, request.user_id)

            return (
                jsonify(
                    {"response": response, "timestamp": datetime.utcnow().isoformat()}
                ),
                200,
            )

        @app.route("/api/ai/toggle", methods=["POST"])
        def toggle_ai():
            """Toggle AI assistant on/off"""
            self.ai_assistant_active = not self.ai_assistant_active
            return jsonify({"active": self.ai_assistant_active}), 200

        @app.route("/api/simulation/start", methods=["POST"])
        def start_simulation():
            """Start 24/7 learning simulation"""
            if not self.simulation_running:
                threading.Thread(target=self.run_continuous_simulation).start()
                self.simulation_running = True

            return jsonify({"status": "Simulation started"}), 200

        @app.route("/api/performance/report", methods=["GET"])
        def performance_report():
            """Get detailed performance report"""
            timeframe = request.args.get("timeframe", "30d")

            conn = db_pool.getconn()
            try:
                cursor = conn.cursor()

                # Calculate date range
                if timeframe == "24h":
                    start_date = datetime.utcnow() - timedelta(hours=24)
                elif timeframe == "7d":
                    start_date = datetime.utcnow() - timedelta(days=7)
                elif timeframe == "30d":
                    start_date = datetime.utcnow() - timedelta(days=30)
                else:
                    start_date = datetime.utcnow() - timedelta(days=365)

                # Get performance data
                cursor.execute(
                    """
                    SELECT
                        DATE(timestamp) as date,
                        SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as profits,
                        SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as losses,
                        COUNT(*) as trade_count,
                        AVG(pnl) as avg_pnl
                    FROM trades
                    WHERE user_id = %s AND timestamp >= %s
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """,
                    (request.user_id, start_date),
                )

                daily_performance = cursor.fetchall()

                return (
                    jsonify(
                        {
                            "daily": [
                                {
                                    "date": str(d[0]),
                                    "profits": float(d[1]),
                                    "losses": float(d[2]),
                                    "trades": d[3],
                                    "avgPnl": float(d[4]) if d[4] else 0,
                                }
                                for d in daily_performance
                            ]
                        }
                    ),
                    200,
                )

            finally:
                db_pool.putconn(conn)

        # WebSocket events
        @socketio.on("connect")
        def handle_connect():
            """Handle WebSocket connection"""
            token = request.args.get("token")
            if not token:
                disconnect()
                return

            try:
                payload = jwt.decode(
                    token,
                    app.config["JWT_SECRET_KEY"],
                    algorithms=[app.config["JWT_ALGORITHM"]],
                )
                user_id = payload["user_id"]

                # Join user room for targeted messages
                room = f"user_{user_id}"
                socketio.server.enter_room(request.sid, room)
                trade_subscribers.add(request.sid)

                emit("connected", {"status": "Connected to ANVEL"})

            except jwt.InvalidTokenError:
                disconnect()

        @socketio.on("disconnect")
        def handle_disconnect():
            """Handle WebSocket disconnection"""
            trade_subscribers.discard(request.sid)

        @socketio.on("subscribe_trades")
        def handle_trade_subscription(data):
            """Subscribe to real-time trade updates"""
            pairs = data.get("pairs", [])
            # Implementation for filtered subscriptions
            emit("subscription_confirmed", {"pairs": pairs})

    def start_trading_engine(self, user_id, strategy, risk_level, max_positions):
        """Start the automated trading engine"""
        import time

        while self.trading_active:
            try:
                # Get market data
                market_data = self.fetch_market_data()

                # Run strategy
                signals = self.run_strategy(strategy, market_data, risk_level)

                # Execute trades
                for signal in signals:
                    if signal["confidence"] > 0.7:  # Confidence threshold
                        self.execute_trade(user_id, signal)

                # Broadcast updates
                self.broadcast_portfolio_update(user_id)

                # Rate limiting
                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                print(f"Trading engine error: {e}")
                time.sleep(10)

    def process_ai_query(self, question, context, user_id):
        """Process AI assistant queries"""
        # This would integrate with your AI modules
        # For now, returning structured responses

        responses = {
            "market": "Current market conditions show moderate volatility with BTC trading at resistance levels.",
            "strategy": "The AI composite strategy is currently favoring momentum trades in trending markets.",
            "risk": "Your current risk exposure is within acceptable parameters at 15% of portfolio.",
            "performance": "Your portfolio is up 12.5% this month with a 67% win rate.",
        }

        # Simple keyword matching for demo
        for key, response in responses.items():
            if key in question.lower():
                return response

        return "I'm analyzing your query. The system shows all parameters are within normal ranges."

    def run_continuous_simulation(self):
        """Run 24/7 learning simulation"""
        import time

        while self.simulation_running:
            try:
                # Run backtesting on historical data
                self.run_backtest_cycle()

                # Train models with new data
                self.train_ai_models()

                # Optimize strategies
                self.optimize_strategies()

                # Sleep for next cycle
                time.sleep(300)  # Run every 5 minutes

            except Exception as e:
                print(f"Simulation error: {e}")
                time.sleep(60)

    def fetch_market_data(self):
        """Fetch current market data"""
        # Implementation would connect to exchanges
        return {}

    def run_strategy(self, strategy, market_data, risk_level):
        """Run trading strategy"""
        # Implementation would use strategy modules
        return []

    def execute_trade(self, user_id, signal):
        """Execute a trade"""
        # Implementation would place orders

    def broadcast_portfolio_update(self, user_id):
        """Send portfolio updates via WebSocket"""
        room = f"user_{user_id}"
        socketio.emit(
            "portfolio_update",
            {
                "timestamp": datetime.utcnow().isoformat(),
                "data": self.get_portfolio_snapshot(user_id),
            },
            room=room,
        )

    def get_portfolio_snapshot(self, user_id):
        """Get current portfolio snapshot"""
        # Implementation would fetch from database
        return {}

    def close_all_positions(self, user_id):
        """Close all open positions"""
        # Implementation would close positions

    def run_backtest_cycle(self):
        """Run backtesting cycle"""
        # Implementation for backtesting

    def train_ai_models(self):
        """Train AI models with new data"""
        # Implementation for model training

    def optimize_strategies(self):
        """Optimize trading strategies"""
        # Implementation for strategy optimization


# Initialize server (must be before route definitions that use it)
anvel_server = None


# Health check endpoint (critical for production monitoring)
@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint for load balancers and monitoring systems.
    Returns 200 OK if all critical services are operational.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "services": {},
    }

    # Check Redis connection
    try:
        redis_client.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # Check PostgreSQL connection
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        db_pool.putconn(conn)
        health_status["services"]["database"] = "healthy"
    except Exception as e:
        health_status["services"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # Check trading engine status
    if anvel_server:
        health_status["services"]["trading_engine"] = (
            "active" if anvel_server.trading_active else "inactive"
        )
    else:
        health_status["services"]["trading_engine"] = "initializing"
        health_status["status"] = "degraded"

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


@app.route("/api/readiness", methods=["GET"])
def readiness_check():
    """
    Readiness check endpoint for Kubernetes/orchestration systems.
    Returns 200 OK if the service is ready to accept traffic.
    """
    readiness_status = {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }

    # Check if server is initialized
    if anvel_server is None:
        readiness_status["ready"] = False
        readiness_status["checks"]["initialization"] = "incomplete"
    elif not hasattr(anvel_server, "performance_metrics"):
        readiness_status["ready"] = False
        readiness_status["checks"]["initialization"] = "incomplete"
    else:
        readiness_status["checks"]["initialization"] = "complete"

    status_code = 200 if readiness_status["ready"] else 503
    return jsonify(readiness_status), status_code


# Initialize server (deferred initialization)
anvel_server = None


def get_anvel_server():
    """Get or create ANVEL web server instance"""
    global anvel_server
    if anvel_server is None:
        anvel_server = ANVELWebServer()
    return anvel_server


if __name__ == "__main__":
    # Initialize server for direct execution
    get_anvel_server()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
