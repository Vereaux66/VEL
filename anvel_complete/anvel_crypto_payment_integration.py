#!/usr/bin/env python3
"""
ANVEL Crypto Payment Integration
Handles blockchain payment verification and webhook processing.
Supports BTC, ETH, and stablecoins (USDT, USDC) for subscription payments.
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Dict, Optional
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

log = logging.getLogger(__name__)


@dataclass
class PaymentVerification:
    """Result of blockchain payment verification."""
    is_valid: bool
    confirmations: int
    amount_received: Decimal
    tx_hash: str
    error_message: Optional[str] = None


class CryptoPaymentIntegration:
    """
    Integrates with blockchain networks to verify crypto payments.
    Designed for production use with proper error handling and idempotency.
    """

    def __init__(
        self,
        db_config: Dict,
        blockchain_api_keys: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize crypto payment integration.
        
        Args:
            db_config: PostgreSQL connection parameters
            blockchain_api_keys: API keys for blockchain explorers
                - btc_api_key: For Bitcoin blockchain API
                - eth_api_key: For Ethereum blockchain API
        """
        self.db_config = db_config
        self.blockchain_api_keys = blockchain_api_keys or {}

        # Required confirmations per currency
        self.required_confirmations = {
            "BTC": 3,
            "ETH": 12,
            "USDT": 12,  # ERC-20
            "USDC": 12,  # ERC-20
        }

        # Blockchain explorer endpoints (use production APIs)
        self.blockchain_endpoints = {
            "BTC": "https://blockchain.info/rawaddr/",
            "ETH": "https://api.etherscan.io/api",
        }

    def _get_db_connection(self):
        """Get database connection with proper configuration."""
        return psycopg2.connect(
            host=self.db_config["host"],
            port=self.db_config.get("port", 5432),
            dbname=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            connect_timeout=10,
        )

    def generate_payment_address(
        self,
        user_id: str,
        crypto_currency: str,
    ) -> str:
        """
        Generate unique payment address for user.
        
        PRODUCTION WARNING: This is a mock implementation.
        In production, you must integrate with:
        - HD wallet service (e.g., BitGo, Fireblocks)
        - Payment processor (e.g., Coinbase Commerce, BTCPay)
        - Self-hosted wallet with proper key management
        
        Args:
            user_id: UUID of the user
            crypto_currency: BTC, ETH, USDT, USDC
            
        Returns:
            Unique payment address
            
        Raises:
            ValueError: If currency unsupported or wallet generation fails
        """
        import hashlib
        import time as _time

        # Deterministic address derivation from user_id + currency
        # In production: replace with HD wallet (BIP-44) or custodial API
        seed = f"{user_id}:{crypto_currency}:{_time.time()}".encode()
        addr_hash = hashlib.sha256(seed).hexdigest()

        if crypto_currency.upper() in ("ETH", "USDT", "USDC", "MATIC"):
            # EVM-compatible address (use web3 if available)
            try:
                from eth_account import Account
                acct = Account.create(extra_entropy=seed)
                address = acct.address
                logger.info(
                    "Generated EVM address for user=%s, currency=%s",
                    user_id, crypto_currency,
                )
                return address
            except ImportError:
                # Fallback: deterministic pseudo-address
                address = "0x" + addr_hash[:40]
                logger.warning(
                    "eth_account not available; generated pseudo-address for %s",
                    user_id,
                )
                return address

        elif crypto_currency.upper() == "BTC":
            # Bitcoin-style address (P2PKH format placeholder)
            address = "1" + addr_hash[:33]
            logger.info("Generated BTC address for user=%s", user_id)
            return address

        elif crypto_currency.upper() == "XMR":
            # Monero address (95-char base58, starts with 4)
            # Production: use monero-python or RPC wallet
            address = "4" + addr_hash[:94]
            logger.info("Generated XMR address for user=%s", user_id)
            return address

        else:
            raise ValueError(
                f"Unsupported currency for address generation: {crypto_currency}. "
                f"Supported: BTC, ETH, USDT, USDC, MATIC, XMR"
            )

    def verify_bitcoin_payment(
        self,
        payment_address: str,
        expected_amount: Decimal,
        tolerance: Decimal = Decimal("0.00001"),
    ) -> PaymentVerification:
        """
        Verify Bitcoin payment on blockchain.
        
        Args:
            payment_address: Bitcoin address to check
            expected_amount: Expected payment amount in BTC
            tolerance: Acceptable variance in amount
            
        Returns:
            PaymentVerification with status and details
        """
        try:
            # Query blockchain API
            url = f"{self.blockchain_endpoints['BTC']}{payment_address}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Check for transactions
            if not data.get("txs"):
                return PaymentVerification(
                    is_valid=False,
                    confirmations=0,
                    amount_received=Decimal("0"),
                    tx_hash="",
                    error_message="No transactions found"
                )

            # Find relevant transaction
            for tx in data["txs"]:
                for output in tx.get("out", []):
                    if output.get("addr") == payment_address:
                        amount_satoshis = output.get("value", 0)
                        amount_btc = Decimal(amount_satoshis) / Decimal("100000000")

                        # Check amount matches
                        if abs(amount_btc - expected_amount) <= tolerance:
                            confirmations = data.get("n_tx", 0)

                            return PaymentVerification(
                                is_valid=True,
                                confirmations=confirmations,
                                amount_received=amount_btc,
                                tx_hash=tx.get("hash", ""),
                            )

            return PaymentVerification(
                is_valid=False,
                confirmations=0,
                amount_received=Decimal("0"),
                tx_hash="",
                error_message="No matching transaction found"
            )

        except requests.RequestException as e:
            log.error(f"Bitcoin verification failed: {e}")
            return PaymentVerification(
                is_valid=False,
                confirmations=0,
                amount_received=Decimal("0"),
                tx_hash="",
                error_message=f"API error: {str(e)}"
            )

    def verify_ethereum_payment(
        self,
        payment_address: str,
        expected_amount: Decimal,
        token_contract: Optional[str] = None,
        tolerance: Decimal = Decimal("0.000001"),
    ) -> PaymentVerification:
        """
        Verify Ethereum or ERC-20 token payment on blockchain.
        
        Args:
            payment_address: Ethereum address to check
            expected_amount: Expected payment amount
            token_contract: ERC-20 contract address for USDT/USDC
            tolerance: Acceptable variance in amount
            
        Returns:
            PaymentVerification with status and details
        """
        try:
            api_key = self.blockchain_api_keys.get("eth_api_key", "")

            if token_contract:
                # Check ERC-20 token transfers
                params = {
                    "module": "account",
                    "action": "tokentx",
                    "contractaddress": token_contract,
                    "address": payment_address,
                    "sort": "desc",
                    "apikey": api_key,
                }
            else:
                # Check ETH transactions
                params = {
                    "module": "account",
                    "action": "txlist",
                    "address": payment_address,
                    "sort": "desc",
                    "apikey": api_key,
                }

            response = requests.get(
                self.blockchain_endpoints["ETH"],
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "1":
                return PaymentVerification(
                    is_valid=False,
                    confirmations=0,
                    amount_received=Decimal("0"),
                    tx_hash="",
                    error_message=data.get("message", "API error")
                )

            # Check transactions
            for tx in data.get("result", []):
                if token_contract:
                    amount_wei = Decimal(tx.get("value", 0))
                    decimals = int(tx.get("tokenDecimal", 18))
                    amount = amount_wei / (Decimal("10") ** decimals)
                else:
                    amount_wei = Decimal(tx.get("value", 0))
                    amount = amount_wei / Decimal("1000000000000000000")

                if abs(amount - expected_amount) <= tolerance:
                    # Get confirmation count
                    block_number = int(tx.get("blockNumber", 0))
                    current_block = self._get_current_eth_block()
                    confirmations = max(0, current_block - block_number)

                    return PaymentVerification(
                        is_valid=True,
                        confirmations=confirmations,
                        amount_received=amount,
                        tx_hash=tx.get("hash", ""),
                    )

            return PaymentVerification(
                is_valid=False,
                confirmations=0,
                amount_received=Decimal("0"),
                tx_hash="",
                error_message="No matching transaction found"
            )

        except requests.RequestException as e:
            log.error(f"Ethereum verification failed: {e}")
            return PaymentVerification(
                is_valid=False,
                confirmations=0,
                amount_received=Decimal("0"),
                tx_hash="",
                error_message=f"API error: {str(e)}"
            )

    def _get_current_eth_block(self) -> int:
        """Get current Ethereum block number."""
        try:
            api_key = self.blockchain_api_keys.get("eth_api_key", "")
            params = {
                "module": "proxy",
                "action": "eth_blockNumber",
                "apikey": api_key,
            }

            response = requests.get(
                self.blockchain_endpoints["ETH"],
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            block_hex = data.get("result", "0x0")
            return int(block_hex, 16)

        except Exception as e:
            log.error(f"Failed to get current block: {e}")
            return 0

    def verify_payment(
        self,
        payment_id: str,
    ) -> bool:
        """
        Verify pending payment on blockchain.
        Idempotent - safe to call multiple times.
        
        Args:
            payment_id: UUID of the payment record
            
        Returns:
            True if payment verified and confirmed, False otherwise
        """
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get payment details
                cur.execute("""
                    SELECT id, payment_address, crypto_currency, 
                           amount_crypto, status, confirmations, 
                           required_confirmations, tx_hash
                    FROM crypto_payments
                    WHERE id = %s
                """, (payment_id,))

                payment = cur.fetchone()

                if not payment:
                    log.error(f"Payment {payment_id} not found")
                    return False

                # Skip if already confirmed
                if payment["status"] == "confirmed":
                    return True

                crypto = payment["crypto_currency"]
                address = payment["payment_address"]
                expected_amount = payment["amount_crypto"]

                # Verify based on currency
                if crypto == "BTC":
                    verification = self.verify_bitcoin_payment(
                        address,
                        Decimal(str(expected_amount))
                    )
                elif crypto in ["ETH", "USDT", "USDC"]:
                    # Token contracts for stablecoins
                    token_contracts = {
                        "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
                        "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                    }

                    verification = self.verify_ethereum_payment(
                        address,
                        Decimal(str(expected_amount)),
                        token_contract=token_contracts.get(crypto),
                    )
                else:
                    log.error(f"Unsupported currency: {crypto}")
                    return False

                # Update payment record
                if verification.is_valid:
                    required = payment["required_confirmations"]

                    if verification.confirmations >= required:
                        # Payment confirmed
                        cur.execute("""
                            UPDATE crypto_payments
                            SET status = 'confirmed',
                                confirmations = %s,
                                tx_hash = %s,
                                confirmed_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (
                            verification.confirmations,
                            verification.tx_hash,
                            payment_id
                        ))

                        # Activate subscription
                        if payment["subscription_id"]:
                            cur.execute("""
                                UPDATE user_subscriptions
                                SET status = 'active',
                                    payment_method = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (crypto, payment["subscription_id"]))

                        conn.commit()
                        log.info(f"Payment {payment_id} confirmed: {verification.tx_hash}")
                        return True
                    else:
                        # Update confirmation count
                        cur.execute("""
                            UPDATE crypto_payments
                            SET confirmations = %s,
                                tx_hash = %s
                            WHERE id = %s
                        """, (
                            verification.confirmations,
                            verification.tx_hash,
                            payment_id
                        ))
                        conn.commit()
                        log.info(
                            f"Payment {payment_id} pending: "
                            f"{verification.confirmations}/{required} confirmations"
                        )
                        return False
                else:
                    log.warning(
                        f"Payment {payment_id} verification failed: "
                        f"{verification.error_message}"
                    )
                    return False

    def process_webhook(
        self,
        webhook_data: Dict,
        signature: str,
        webhook_secret: str,
    ) -> bool:
        """
        Process webhook from payment gateway or blockchain monitor.
        Validates signature and updates payment status.
        
        Args:
            webhook_data: Webhook payload
            signature: HMAC signature from webhook
            webhook_secret: Shared secret for signature verification
            
        Returns:
            True if webhook processed successfully
        """
        # Verify webhook signature
        payload = json.dumps(webhook_data, sort_keys=True)
        expected_signature = hmac.new(
            webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            log.error("Invalid webhook signature")
            return False

        # Extract payment info from webhook
        payment_id = webhook_data.get("payment_id")
        tx_hash = webhook_data.get("transaction_hash")
        confirmations = webhook_data.get("confirmations", 0)

        if not payment_id:
            log.error("No payment_id in webhook")
            return False

        # Update payment record
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE crypto_payments
                    SET confirmations = %s,
                        tx_hash = COALESCE(tx_hash, %s)
                    WHERE id = %s
                """, (confirmations, tx_hash, payment_id))

                conn.commit()

        # Verify payment
        return self.verify_payment(payment_id)

    def scan_pending_payments(self) -> int:
        """
        Background task to scan all pending payments.
        Should be run periodically (e.g., every 5 minutes).
        
        Returns:
            Number of payments verified
        """
        verified_count = 0

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get pending payments not expired
                cur.execute("""
                    SELECT id
                    FROM crypto_payments
                    WHERE status = 'pending'
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC
                    LIMIT 100
                """)

                payments = cur.fetchall()

        # Verify each payment
        for payment in payments:
            try:
                if self.verify_payment(payment["id"]):
                    verified_count += 1
            except Exception as e:
                log.error(f"Failed to verify payment {payment['id']}: {e}")

        log.info(f"Scanned {len(payments)} pending payments, verified {verified_count}")
        return verified_count
