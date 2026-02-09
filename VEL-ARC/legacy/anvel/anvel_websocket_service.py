#!/usr/bin/env python3
"""
ANVEL WebSocket Service with Redis Pub/Sub
Provides realtime market data feeds to connected clients.
Production-ready with proper isolation from trading core.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional

import redis
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

log = logging.getLogger(__name__)


class WebSocketService:
    """
    WebSocket service for realtime market data broadcasting.
    Uses Redis pub/sub to decouple from trading core.
    """

    def __init__(
        self,
        flask_app: Flask,
        socketio: SocketIO,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: Optional[str] = None,
        redis_db: int = 0,
        auth_callback: Optional[callable] = None,
    ):
        """
        Initialize WebSocket service.
        
        Args:
            flask_app: Flask application instance
            socketio: Flask-SocketIO instance
            redis_host: Redis server host
            redis_port: Redis server port
            redis_password: Redis password (if required)
            redis_db: Redis database number
            auth_callback: Function to verify JWT tokens
        """
        self.app = flask_app
        self.socketio = socketio
        self.auth_callback = auth_callback

        # Redis connection for pub/sub
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                db=redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            self.redis_client.ping()
            log.info("Connected to Redis for pub/sub")
        except redis.RedisError as e:
            log.error(f"Failed to connect to Redis: {e}")
            raise

        # Track connected clients and their subscriptions
        self.connected_clients: Dict[str, Dict] = {}  # sid -> client_info
        self.room_subscribers: Dict[str, Set[str]] = {}  # room -> set of sids

        # Register SocketIO event handlers
        self._register_handlers()

        # Start Redis subscriber thread
        self._start_redis_subscriber()

    def _register_handlers(self):
        """Register SocketIO event handlers."""

        @self.socketio.on('connect')
        def handle_connect(auth):
            """Handle client connection."""
            from flask import request

            sid = request.sid

            # Authenticate client
            if self.auth_callback:
                try:
                    # Expect JWT token in auth dict
                    token = auth.get('token') if auth else None
                    if not token:
                        log.warning(f"Client {sid} connected without token")
                        disconnect()
                        return False

                    # Verify token
                    user_info = self.auth_callback(token)
                    if not user_info:
                        log.warning(f"Invalid token for client {sid}")
                        disconnect()
                        return False

                    # Store client info
                    self.connected_clients[sid] = {
                        "user_id": user_info.get("sub"),
                        "username": user_info.get("username"),
                        "tenant_id": user_info.get("tenant_id"),
                        "connected_at": datetime.utcnow().isoformat(),
                        "subscriptions": set(),
                    }

                    log.info(
                        f"Client {sid} authenticated as "
                        f"{user_info.get('username')}"
                    )

                except Exception as e:
                    log.error(f"Authentication error for {sid}: {e}")
                    disconnect()
                    return False
            else:
                # No auth - allow anonymous connections (dev mode only)
                self.connected_clients[sid] = {
                    "user_id": "anonymous",
                    "username": "anonymous",
                    "tenant_id": None,
                    "connected_at": datetime.utcnow().isoformat(),
                    "subscriptions": set(),
                }

            emit('connected', {
                "message": "Connected to ANVEL WebSocket service",
                "timestamp": datetime.utcnow().isoformat(),
            })

            return True

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection."""
            from flask import request

            sid = request.sid

            if sid in self.connected_clients:
                client_info = self.connected_clients[sid]

                # Leave all rooms
                for room in client_info.get("subscriptions", set()).copy():
                    self._unsubscribe_from_feed(sid, room)

                del self.connected_clients[sid]

                log.info(
                    f"Client {sid} ({client_info.get('username')}) "
                    f"disconnected"
                )

        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """Handle feed subscription request."""
            from flask import request

            sid = request.sid

            if sid not in self.connected_clients:
                emit('error', {"message": "Not authenticated"})
                return

            feed_type = data.get('feed')
            pair = data.get('pair')

            if not feed_type or not pair:
                emit('error', {"message": "Missing feed or pair parameter"})
                return

            # Validate feed type
            valid_feeds = [
                'ticker',
                'orderbook',
                'trades',
                'candles',
                'signals',
            ]

            if feed_type not in valid_feeds:
                emit('error', {"message": f"Invalid feed type: {feed_type}"})
                return

            # Create room name
            room = f"{feed_type}:{pair}"

            # Subscribe client
            self._subscribe_to_feed(sid, room)

            emit('subscribed', {
                "feed": feed_type,
                "pair": pair,
                "room": room,
                "timestamp": datetime.utcnow().isoformat(),
            })

            log.info(
                f"Client {sid} subscribed to {room}"
            )

        @self.socketio.on('unsubscribe')
        def handle_unsubscribe(data):
            """Handle feed unsubscription request."""
            from flask import request

            sid = request.sid

            if sid not in self.connected_clients:
                return

            feed_type = data.get('feed')
            pair = data.get('pair')

            if not feed_type or not pair:
                emit('error', {"message": "Missing feed or pair parameter"})
                return

            room = f"{feed_type}:{pair}"

            # Unsubscribe client
            self._unsubscribe_from_feed(sid, room)

            emit('unsubscribed', {
                "feed": feed_type,
                "pair": pair,
                "room": room,
                "timestamp": datetime.utcnow().isoformat(),
            })

            log.info(f"Client {sid} unsubscribed from {room}")

        @self.socketio.on('ping')
        def handle_ping():
            """Handle ping for keepalive."""
            emit('pong', {"timestamp": datetime.utcnow().isoformat()})

    def _subscribe_to_feed(self, sid: str, room: str):
        """Subscribe client to a feed room."""
        if sid not in self.connected_clients:
            return

        # Add to room
        join_room(room)

        # Track subscription
        self.connected_clients[sid]["subscriptions"].add(room)

        if room not in self.room_subscribers:
            self.room_subscribers[room] = set()

        self.room_subscribers[room].add(sid)

    def _unsubscribe_from_feed(self, sid: str, room: str):
        """Unsubscribe client from a feed room."""
        if sid not in self.connected_clients:
            return

        # Leave room
        leave_room(room)

        # Remove from tracking
        if room in self.connected_clients[sid]["subscriptions"]:
            self.connected_clients[sid]["subscriptions"].remove(room)

        if room in self.room_subscribers:
            self.room_subscribers[room].discard(sid)

            # Clean up empty rooms
            if not self.room_subscribers[room]:
                del self.room_subscribers[room]

    def _start_redis_subscriber(self):
        """Start Redis pub/sub subscriber in background thread."""
        import threading

        def redis_subscriber():
            """Redis subscriber loop."""
            pubsub = self.redis_client.pubsub()

            # Subscribe to market data channels
            channels = [
                "market:ticker:*",
                "market:orderbook:*",
                "market:trades:*",
                "market:candles:*",
                "market:signals:*",
            ]

            pubsub.psubscribe(*channels)

            log.info("Redis subscriber started")

            try:
                for message in pubsub.listen():
                    if message['type'] == 'pmessage':
                        self._handle_redis_message(message)
            except Exception as e:
                log.error(f"Redis subscriber error: {e}")
            finally:
                pubsub.close()

        thread = threading.Thread(target=redis_subscriber, daemon=True)
        thread.start()

    def _handle_redis_message(self, message: Dict):
        """Handle message from Redis pub/sub."""
        try:
            channel = message['channel']
            data_str = message['data']

            # Parse channel: market:feed:pair
            parts = channel.split(':', 2)
            if len(parts) < 3:
                return

            feed_type = parts[1]
            pair = parts[2]
            room = f"{feed_type}:{pair}"

            # Check if anyone is subscribed to this room
            if room not in self.room_subscribers or not self.room_subscribers[room]:
                return

            # Parse data
            data = json.loads(data_str)

            # Add metadata
            data['feed'] = feed_type
            data['pair'] = pair
            data['timestamp'] = datetime.utcnow().isoformat()

            # Broadcast to room
            self.socketio.emit(
                'market_data',
                data,
                room=room,
                namespace='/',
            )

        except Exception as e:
            log.error(f"Error handling Redis message: {e}")

    def publish_market_data(
        self,
        feed_type: str,
        pair: str,
        data: Dict,
    ):
        """
        Publish market data to Redis for broadcasting.
        Called by trading core or market data aggregator.
        
        Args:
            feed_type: Type of data (ticker, orderbook, trades, etc.)
            pair: Trading pair (e.g., BTC/USD)
            data: Market data to broadcast
        """
        channel = f"market:{feed_type}:{pair}"

        try:
            # Serialize to JSON
            data_json = json.dumps(data, default=str)

            # Publish to Redis
            self.redis_client.publish(channel, data_json)

        except Exception as e:
            log.error(f"Failed to publish market data: {e}")

    def get_stats(self) -> Dict:
        """
        Get WebSocket service statistics.
        
        Returns:
            Dict with connection and subscription stats
        """
        return {
            "connected_clients": len(self.connected_clients),
            "total_subscriptions": sum(
                len(client["subscriptions"])
                for client in self.connected_clients.values()
            ),
            "active_rooms": len(self.room_subscribers),
            "rooms": {
                room: len(sids)
                for room, sids in self.room_subscribers.items()
            },
        }


def create_websocket_service(
    flask_app: Flask,
    redis_config: Dict,
    auth_callback: Optional[callable] = None,
) -> WebSocketService:
    """
    Factory function to create WebSocket service.
    
    Args:
        flask_app: Flask application
        redis_config: Redis connection configuration
        auth_callback: Token verification function
        
    Returns:
        WebSocketService instance
    """
    # Create SocketIO instance with secure CORS configuration
    # Get allowed origins from environment or use secure defaults
    cors_origins = os.environ.get(
        "ANVEL_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8080,https://*.anvelbot.app,https://*.amazonaws.com"
    ).split(",")

    socketio = SocketIO(
        flask_app,
        cors_allowed_origins=cors_origins,
        async_mode='threading',
        logger=True,
        engineio_logger=True,
    )

    # Create WebSocket service
    ws_service = WebSocketService(
        flask_app=flask_app,
        socketio=socketio,
        redis_host=redis_config.get("host", "localhost"),
        redis_port=redis_config.get("port", 6379),
        redis_password=redis_config.get("password"),
        redis_db=redis_config.get("db", 0),
        auth_callback=auth_callback,
    )

    # Override CORS configuration if provided
    cors_origins = redis_config.get("cors_origins", os.getenv("WEBSOCKET_CORS_ORIGINS"))
    if cors_origins and cors_origins != "*":
        socketio.init_app(flask_app, cors_allowed_origins=cors_origins)

    return ws_service
