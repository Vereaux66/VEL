#!/usr/bin/env python3
"""
ANVEL BTCPay Server Integration
Handles invoice creation, webhook verification, and payment status updates.
Production-ready with proper error handling and idempotency.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

log = logging.getLogger(__name__)


@dataclass
class BTCPayInvoice:
    """BTCPay invoice details."""
    invoice_id: str
    checkout_link: str
    amount: Decimal
    currency: str
    status: str
    expiry: datetime


class BTCPayServerIntegration:
    """
    Integrates with BTCPay Server for cryptocurrency payments.
    Handles invoice creation, webhook verification, and payment status tracking.
    """

    def __init__(
        self,
        db_config: Dict,
        btcpay_url: str,
        btcpay_api_key: str,
        btcpay_store_id: str,
        webhook_secret: str,
        speed_policy: str = "MediumSpeed",
        expiration_minutes: int = 30,
        monitoring_minutes: int = 1440,
    ):
        """
        Initialize BTCPay Server integration.
        
        Args:
            db_config: PostgreSQL connection parameters
            btcpay_url: BTCPay Server URL (e.g., https://btcpay.example.com)
            btcpay_api_key: BTCPay API key
            btcpay_store_id: BTCPay store ID
            webhook_secret: Shared secret for webhook validation
            speed_policy: Confirmation speed (HighSpeed/MediumSpeed/LowSpeed)
            expiration_minutes: Invoice expiration time
            monitoring_minutes: Payment monitoring duration
        """
        if not all([btcpay_url, btcpay_api_key, btcpay_store_id, webhook_secret]):
            raise ValueError("All BTCPay configuration parameters are required")

        self.db_config = db_config
        self.btcpay_url = btcpay_url.rstrip('/')
        self.btcpay_api_key = btcpay_api_key
        self.btcpay_store_id = btcpay_store_id
        self.webhook_secret = webhook_secret

        # Configurable invoice settings
        self.speed_policy = speed_policy
        self.expiration_minutes = expiration_minutes
        self.monitoring_minutes = monitoring_minutes

        # BTCPay API endpoints
        self.api_base = f"{self.btcpay_url}/api/v1"

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

    def _make_btcpay_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
    ) -> Dict:
        """
        Make authenticated request to BTCPay Server API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request payload
            
        Returns:
            Response JSON
            
        Raises:
            requests.RequestException: If request fails
        """
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"token {self.btcpay_api_key}",
            "Content-Type": "application/json",
        }

        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                resp = requests.post(url, json=data, headers=headers, timeout=30)
            elif method.upper() == "PUT":
                resp = requests.put(url, json=data, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as e:
            log.error(f"BTCPay API request failed: {e}")
            raise

    def create_invoice(
        self,
        user_id: str,
        subscription_id: str,
        amount_usd: Decimal,
        tier: str,
        metadata: Optional[Dict] = None,
    ) -> BTCPayInvoice:
        """
        Create BTCPay invoice for subscription payment.
        
        Args:
            user_id: User UUID
            subscription_id: Subscription UUID
            amount_usd: Amount in USD
            tier: Subscription tier
            metadata: Additional metadata
            
        Returns:
            BTCPayInvoice with invoice details
            
        Raises:
            requests.RequestException: If invoice creation fails
        """
        # Prepare invoice data
        invoice_data = {
            "amount": str(amount_usd),
            "currency": "USD",
            "metadata": {
                "user_id": user_id,
                "subscription_id": subscription_id,
                "tier": tier,
                "orderId": subscription_id,
                **(metadata or {}),
            },
            "checkout": {
                "speedPolicy": self.speed_policy,
                "paymentMethods": ["BTC", "BTC-LightningNetwork"],
                "expirationMinutes": self.expiration_minutes,
                "monitoringMinutes": self.monitoring_minutes,
                "paymentTolerance": 0,
                "redirectURL": metadata.get("redirect_url") if metadata else None,
            }
        }

        try:
            # Create invoice via BTCPay API
            response = self._make_btcpay_request(
                "POST",
                f"stores/{self.btcpay_store_id}/invoices",
                invoice_data,
            )

            invoice_id = response["id"]
            checkout_link = response["checkoutLink"]
            status = response["status"]
            created_time = datetime.fromisoformat(
                response["createdTime"].replace('Z', '+00:00')
            )
            expiry_minutes = invoice_data["checkout"]["expirationMinutes"]
            expiry = created_time + timedelta(minutes=expiry_minutes)

            # Store in database
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO btcpay_invoices (
                            invoice_id, user_id, subscription_id,
                            amount_usd, tier, status,
                            checkout_link, expires_at, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        invoice_id, user_id, subscription_id,
                        amount_usd, tier, status,
                        checkout_link, expiry, json.dumps(metadata or {}),
                    ))
                    conn.commit()

            log.info(f"Created BTCPay invoice {invoice_id} for user {user_id}")

            return BTCPayInvoice(
                invoice_id=invoice_id,
                checkout_link=checkout_link,
                amount=amount_usd,
                currency="USD",
                status=status,
                expiry=expiry,
            )

        except Exception as e:
            log.error(f"Failed to create BTCPay invoice: {e}")
            raise

    def get_invoice_status(self, invoice_id: str) -> Dict:
        """
        Get invoice status from BTCPay Server.
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            Invoice status details
        """
        try:
            response = self._make_btcpay_request(
                "GET",
                f"stores/{self.btcpay_store_id}/invoices/{invoice_id}",
            )

            return {
                "invoice_id": response["id"],
                "status": response["status"],
                "amount": Decimal(response["amount"]),
                "currency": response["currency"],
                "created_time": response["createdTime"],
                "expiry_time": response.get("expirationTime"),
                "payment_method": response.get("paymentMethod"),
                "metadata": response.get("metadata", {}),
            }

        except Exception as e:
            log.error(f"Failed to get invoice status: {e}")
            raise

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify BTCPay webhook signature.
        
        Args:
            payload: Raw webhook payload bytes
            signature: Signature from BTCPay-Sig header
            
        Returns:
            True if signature is valid
        """
        if not signature or not payload:
            return False

        try:
            # BTCPay uses HMAC-SHA256
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()

            # Extract signature value (format: "sha256=...")
            if signature.startswith("sha256="):
                signature = signature[7:]

            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            log.error(f"Webhook signature verification failed: {e}")
            return False

    def process_webhook(
        self,
        payload_bytes: bytes,
        signature: str,
    ) -> bool:
        """
        Process BTCPay webhook notification.
        Validates signature and updates payment status.
        
        Args:
            payload_bytes: Raw webhook payload
            signature: Webhook signature from BTCPay-Sig header
            
        Returns:
            True if webhook processed successfully
        """
        # Verify signature
        if not self.verify_webhook_signature(payload_bytes, signature):
            log.error("Invalid webhook signature")
            return False

        try:
            payload = json.loads(payload_bytes.decode('utf-8'))
        except json.JSONDecodeError as e:
            log.error(f"Invalid webhook payload: {e}")
            return False

        # Extract invoice data
        invoice_id = payload.get("invoiceId")
        if not invoice_id:
            log.error("No invoiceId in webhook payload")
            return False

        # Get full invoice details
        try:
            invoice_status = self.get_invoice_status(invoice_id)
        except Exception as e:
            log.error(f"Failed to get invoice status: {e}")
            return False

        # Update database
        return self._update_payment_status(invoice_id, invoice_status)

    def _update_payment_status(
        self,
        invoice_id: str,
        invoice_status: Dict,
    ) -> bool:
        """
        Update payment status in database based on invoice status.
        Idempotent - safe to call multiple times.
        
        Args:
            invoice_id: BTCPay invoice ID
            invoice_status: Invoice status from BTCPay
            
        Returns:
            True if update successful
        """
        status = invoice_status["status"]
        metadata = invoice_status.get("metadata", {})
        subscription_id = metadata.get("subscription_id")

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Update invoice record
                cur.execute("""
                    UPDATE btcpay_invoices
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP,
                        payment_method = %s,
                        settled_at = CASE 
                            WHEN %s IN ('Settled', 'Processing') AND settled_at IS NULL
                            THEN CURRENT_TIMESTAMP
                            ELSE settled_at
                        END
                    WHERE invoice_id = %s
                """, (
                    status,
                    invoice_status.get("payment_method"),
                    status,
                    invoice_id,
                ))

                # If invoice settled/processing, activate subscription
                if status in ["Settled", "Processing"] and subscription_id:
                    # Check if already activated
                    cur.execute("""
                        SELECT status
                        FROM user_subscriptions
                        WHERE id = %s
                    """, (subscription_id,))

                    sub = cur.fetchone()
                    if sub and sub["status"] != "active":
                        # Activate subscription
                        cur.execute("""
                            UPDATE user_subscriptions
                            SET status = 'active',
                                payment_method = 'btcpay',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (subscription_id,))

                        log.info(
                            f"Activated subscription {subscription_id} "
                            f"via BTCPay invoice {invoice_id}"
                        )

                        # Log audit event
                        user_id = metadata.get("user_id")
                        if user_id:
                            cur.execute("""
                                INSERT INTO audit_log (
                                    user_id, action, resource,
                                    resource_id, details
                                ) VALUES (
                                    %s, %s, %s, %s, %s
                                )
                            """, (
                                user_id,
                                "subscription_payment_received",
                                "subscription",
                                subscription_id,
                                json.dumps({
                                    "invoice_id": invoice_id,
                                    "amount": str(invoice_status["amount"]),
                                    "currency": invoice_status["currency"],
                                    "status": status,
                                }),
                            ))

                # If invoice expired/invalid, mark subscription as pending
                elif status in ["Expired", "Invalid"] and subscription_id:
                    cur.execute("""
                        UPDATE user_subscriptions
                        SET status = 'payment_pending',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND status != 'active'
                    """, (subscription_id,))

                conn.commit()

        log.info(f"Updated BTCPay invoice {invoice_id} status to {status}")
        return True

    def scan_pending_invoices(self) -> int:
        """
        Background task to check pending invoice statuses.
        Should be run periodically (e.g., every 5 minutes).
        
        Returns:
            Number of invoices updated
        """
        updated_count = 0

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get pending invoices not expired
                cur.execute("""
                    SELECT invoice_id
                    FROM btcpay_invoices
                    WHERE status IN ('New', 'Processing')
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC
                    LIMIT 100
                """)

                invoices = cur.fetchall()

        # Check each invoice
        for invoice in invoices:
            try:
                invoice_status = self.get_invoice_status(invoice["invoice_id"])
                if self._update_payment_status(
                    invoice["invoice_id"],
                    invoice_status
                ):
                    updated_count += 1
            except Exception as e:
                log.error(
                    f"Failed to check invoice {invoice['invoice_id']}: {e}"
                )

        log.info(
            f"Scanned {len(invoices)} pending invoices, "
            f"updated {updated_count}"
        )
        return updated_count
