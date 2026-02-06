#!/usr/bin/env python3
"""
Example integration of ANVEL SaaS subscription system.
Demonstrates how to integrate subscription management into existing application.
"""

import os
from flask import Flask, g, request
from anvel_subscription_manager import ANVELSubscriptionManager, SubscriptionTier
from anvel_crypto_payment_integration import CryptoPaymentIntegration
from anvel_api_gateway import APIGateway, create_api_routes


def create_saas_app():
    """
    Create Flask app with SaaS subscription support.
    Example integration for ANVEL trading system.
    """
    app = Flask(__name__)

    # Configuration from environment
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "anvel"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "changeme"),
    }

    redis_config = {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "port": int(os.getenv("REDIS_PORT", "6379")),
        "password": os.getenv("REDIS_PASSWORD", ""),
        "db": int(os.getenv("REDIS_DB", "0")),
    }

    jwt_secret = os.getenv("JWT_SECRET", "change-me-in-production")

    # Initialize components
    subscription_manager = ANVELSubscriptionManager(db_config, redis_config)
    payment_integration = CryptoPaymentIntegration(
        db_config,
        blockchain_api_keys={
            "btc_api_key": os.getenv("BTC_API_KEY", ""),
            "eth_api_key": os.getenv("ETH_API_KEY", ""),
        }
    )
    api_gateway = APIGateway(subscription_manager, jwt_secret)

    # Register API routes
    create_api_routes(app, api_gateway)

    # Example: Create subscription endpoint
    @app.route("/api/v1/subscription/create", methods=["POST"])
    @api_gateway.require_auth("subscription_create")
    def create_subscription():
        """Create or upgrade subscription."""
        user_id = g.user_id
        data = request.get_json()

        tier_name = data.get("tier", "starter")
        try:
            tier = SubscriptionTier(tier_name)
        except ValueError:
            return {"error": "Invalid tier"}, 400

        subscription = subscription_manager.create_subscription(
            user_id=user_id,
            tier=tier,
            duration_months=1,
        )

        return subscription, 201

    # Example: Payment webhook endpoint
    @app.route("/webhook/payment", methods=["POST"])
    def payment_webhook():
        """Process payment webhook from blockchain monitor."""
        signature = request.headers.get("X-Signature", "")
        webhook_secret = os.getenv("WEBHOOK_SECRET", "change-me")

        data = request.get_json()

        if payment_integration.process_webhook(data, signature, webhook_secret):
            return {"status": "processed"}, 200

        return {"error": "Invalid signature"}, 401

    # Example: Check user's trading limits
    @app.route("/api/v1/limits", methods=["GET"])
    @api_gateway.require_auth("limits_check")
    def check_limits():
        """Get user's subscription limits."""
        user_id = g.user_id
        limits = subscription_manager.validate_user_limits(user_id)

        return {
            "max_api_calls_per_minute": limits.max_api_calls_per_minute,
            "max_active_positions": limits.max_active_positions,
            "max_daily_trades": limits.max_daily_trades,
            "max_exchanges": limits.max_exchanges,
            "features": {
                "ai_enabled": limits.ai_features_enabled,
                "backtesting_enabled": limits.backtesting_enabled,
                "advanced_analytics": limits.advanced_analytics,
                "priority_support": limits.priority_support,
            }
        }

    return app


def setup_background_tasks():
    """
    Setup background tasks for payment verification and cleanup.
    This should be run as a separate process or cron job.
    """
    from celery import Celery
    from celery.schedules import crontab

    app = Celery('anvel_tasks')

    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "anvel"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "changeme"),
    }

    subscription_manager = ANVELSubscriptionManager(db_config)
    payment_integration = CryptoPaymentIntegration(db_config)

    @app.task
    def verify_pending_payments():
        """Scan and verify pending crypto payments."""
        count = payment_integration.scan_pending_payments()
        return f"Verified {count} payments"

    @app.task
    def cleanup_expired_payments():
        """Mark expired payments."""
        count = subscription_manager.cleanup_expired_payments()
        return f"Cleaned up {count} expired payments"

    # Schedule tasks
    app.conf.beat_schedule = {
        'verify-payments-every-5-min': {
            'task': 'verify_pending_payments',
            'schedule': crontab(minute='*/5'),
        },
        'cleanup-payments-hourly': {
            'task': 'cleanup_expired_payments',
            'schedule': crontab(hour='*', minute=0),
        },
    }

    return app


if __name__ == "__main__":
    # Run Flask app
    app = create_saas_app()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )
