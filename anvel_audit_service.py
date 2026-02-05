#!/usr/bin/env python3
"""
ANVEL Audit Logging Service
Provides structured logging for compliance and security audit trails.
Logs authentication, subscription, payment, trade, and admin events.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict

import psycopg2

log = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """Base audit event structure."""
    action: str
    success: bool
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    severity: str = "info"
    error_message: Optional[str] = None
    details: Optional[Dict] = None


class AuditLogger:
    """
    Production-grade audit logging service.
    Ensures all compliance-relevant events are logged to database.
    """

    def __init__(self, db_config: Dict, enable_structured_logs: bool = True):
        """
        Initialize audit logger.

        Args:
            db_config: PostgreSQL connection parameters
            enable_structured_logs: Enable JSON structured logging to file
        """
        self.db_config = db_config
        self.enable_structured_logs = enable_structured_logs

        # Setup structured logging if enabled
        if enable_structured_logs:
            self._setup_structured_logging()

    def _setup_structured_logging(self):
        """Setup JSON structured logging to file."""
        from pythonjsonlogger import jsonlogger

        audit_handler = logging.FileHandler('logs/audit.log')
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
        audit_handler.setFormatter(formatter)

        audit_log = logging.getLogger('audit')
        audit_log.addHandler(audit_handler)
        audit_log.setLevel(logging.INFO)
        audit_log.propagate = False

    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(
            host=self.db_config["host"],
            port=self.db_config.get("port", 5432),
            dbname=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            connect_timeout=10,
        )

    def log_event(self, event: AuditEvent):
        """
        Log generic audit event to database and structured log.

        Args:
            event: AuditEvent to log
        """
        try:
            # Log to database
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO audit_log (
                            user_id, tenant_id, action, resource, resource_id,
                            ip_address, user_agent, request_id, session_id,
                            severity, success, error_message, details
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        event.user_id, event.tenant_id, event.action,
                        event.resource, event.resource_id,
                        event.ip_address, event.user_agent,
                        event.request_id, event.session_id,
                        event.severity, event.success,
                        event.error_message,
                        json.dumps(event.details) if event.details else None,
                    ))
                    conn.commit()

            # Log to structured log file
            if self.enable_structured_logs:
                audit_log = logging.getLogger('audit')
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": asdict(event),
                }
                audit_log.info(json.dumps(log_data))

        except Exception as e:
            log.error(f"Failed to log audit event: {e}")
            # Don't raise - audit logging failures should not break app

    def log_auth_event(
        self,
        action: str,
        success: bool,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        auth_method: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """
        Log authentication event to dedicated auth audit table.

        Args:
            action: Auth action (login, logout, register, 2fa_verify, etc.)
            success: Whether auth succeeded
            user_id: User UUID (if available)
            tenant_id: Tenant UUID
            username: Username
            email: Email address
            auth_method: Authentication method (password, oauth, totp)
            ip_address: Client IP
            user_agent: Client user agent
            failure_reason: Reason for failure (if applicable)
            request_id: Request correlation ID
            metadata: Additional metadata
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO auth_audit_log (
                            user_id, tenant_id, username, email, action,
                            auth_method, ip_address, user_agent, success,
                            failure_reason, request_id, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        user_id, tenant_id, username, email, action,
                        auth_method, ip_address, user_agent, success,
                        failure_reason, request_id,
                        json.dumps(metadata) if metadata else None,
                    ))
                    conn.commit()

            # Also log to structured log
            if self.enable_structured_logs:
                audit_log = logging.getLogger('audit')
                audit_log.info(json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "authentication",
                    "action": action,
                    "success": success,
                    "user_id": user_id,
                    "username": username,
                    "auth_method": auth_method,
                    "ip_address": ip_address,
                    "failure_reason": failure_reason,
                }))

        except Exception as e:
            log.error(f"Failed to log auth event: {e}")

    def log_trade_event(
        self,
        user_id: str,
        tenant_id: Optional[str],
        trade_id: Optional[int],
        order_id: Optional[str],
        exchange: str,
        pair: str,
        side: str,
        order_type: str,
        price: Optional[float],
        quantity: float,
        total: float,
        fee: float,
        status: str,
        strategy: Optional[str] = None,
        signal_confidence: Optional[float] = None,
        risk_score: Optional[float] = None,
        compliance_flags: Optional[list] = None,
        metadata: Optional[Dict] = None,
    ):
        """
        Log trade event to dedicated trade audit table for compliance.

        Args:
            user_id: User UUID
            tenant_id: Tenant UUID
            trade_id: Trade ID (if available)
            order_id: Order UUID
            exchange: Exchange name
            pair: Trading pair
            side: buy or sell
            order_type: market, limit, stop
            price: Execution price
            quantity: Trade quantity
            total: Total value
            fee: Trading fee
            status: Trade status
            strategy: Trading strategy used
            signal_confidence: AI signal confidence
            risk_score: Risk assessment score
            compliance_flags: Any compliance issues flagged
            metadata: Additional metadata
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO trade_audit_log (
                            user_id, tenant_id, trade_id, order_id,
                            exchange, pair, side, order_type,
                            price, quantity, total, fee, status,
                            strategy, signal_confidence, risk_score,
                            compliance_flags, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        user_id, tenant_id, trade_id, order_id,
                        exchange, pair, side, order_type,
                        price, quantity, total, fee, status,
                        strategy, signal_confidence, risk_score,
                        json.dumps(compliance_flags) if compliance_flags else None,
                        json.dumps(metadata) if metadata else None,
                    ))
                    conn.commit()

            # Also log to structured log
            if self.enable_structured_logs:
                audit_log = logging.getLogger('audit')
                audit_log.info(json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "trade",
                    "user_id": user_id,
                    "exchange": exchange,
                    "pair": pair,
                    "side": side,
                    "order_type": order_type,
                    "quantity": quantity,
                    "status": status,
                    "compliance_flags": compliance_flags,
                }))

        except Exception as e:
            log.error(f"Failed to log trade event: {e}")

    def log_admin_action(
        self,
        admin_user_id: str,
        admin_username: str,
        action: str,
        target_user_id: Optional[str] = None,
        target_tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        changes: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        """
        Log administrative action for security audit.

        Args:
            admin_user_id: Admin user UUID
            admin_username: Admin username
            action: Action performed
            target_user_id: Target user (if applicable)
            target_tenant_id: Target tenant (if applicable)
            resource_type: Type of resource modified
            resource_id: Resource ID
            changes: JSON of changes made
            ip_address: Admin's IP address
            user_agent: Admin's user agent
            request_id: Request correlation ID
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO admin_audit_log (
                            admin_user_id, admin_username, action,
                            target_user_id, target_tenant_id,
                            resource_type, resource_id, changes,
                            ip_address, user_agent, request_id
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        admin_user_id, admin_username, action,
                        target_user_id, target_tenant_id,
                        resource_type, resource_id,
                        json.dumps(changes) if changes else None,
                        ip_address, user_agent, request_id,
                    ))
                    conn.commit()

            # Also log to structured log with high severity
            if self.enable_structured_logs:
                audit_log = logging.getLogger('audit')
                audit_log.warning(json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "admin_action",
                    "severity": "warning",
                    "admin_user_id": admin_user_id,
                    "admin_username": admin_username,
                    "action": action,
                    "target_user_id": target_user_id,
                    "resource_type": resource_type,
                    "ip_address": ip_address,
                }))

        except Exception as e:
            log.error(f"Failed to log admin action: {e}")

    def log_subscription_event(
        self,
        user_id: str,
        tenant_id: Optional[str],
        action: str,
        subscription_id: Optional[str] = None,
        tier: Optional[str] = None,
        amount: Optional[float] = None,
        payment_method: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """
        Log subscription/payment event.

        Args:
            user_id: User UUID
            tenant_id: Tenant UUID
            action: Action (subscribe, renew, cancel, payment_received, etc.)
            subscription_id: Subscription UUID
            tier: Subscription tier
            amount: Payment amount
            payment_method: Payment method used
            details: Additional details
        """
        event = AuditEvent(
            action=action,
            success=True,
            user_id=user_id,
            tenant_id=tenant_id,
            resource="subscription",
            resource_id=subscription_id,
            severity="info",
            details={
                "tier": tier,
                "amount": amount,
                "payment_method": payment_method,
                **(details or {}),
            }
        )

        self.log_event(event)


def create_audit_logger(db_config: Dict) -> AuditLogger:
    """
    Factory function to create audit logger.

    Args:
        db_config: Database configuration

    Returns:
        AuditLogger instance
    """
    return AuditLogger(db_config, enable_structured_logs=True)
