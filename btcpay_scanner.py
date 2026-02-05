#!/usr/bin/env python3
"""
BTCPay Invoice Scanner Background Worker
Periodically scans pending invoices and updates payment status.
Run as a daemon or cron job.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict

from anvel_btcpay_integration import BTCPayServerIntegration

# Ensure log directory exists (use local logs if /app not available)
log_dir = Path(os.getenv('LOG_DIR', './logs'))
log_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'btcpay_scanner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger(__name__)


def get_db_config() -> Dict:
    """Get database configuration from environment."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "anvel"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


def get_btcpay_config() -> Dict:
    """Get BTCPay configuration from environment."""
    return {
        "btcpay_url": os.getenv("BTCPAY_SERVER_URL", ""),
        "btcpay_api_key": os.getenv("BTCPAY_API_KEY", ""),
        "btcpay_store_id": os.getenv("BTCPAY_STORE_ID", ""),
        "webhook_secret": os.getenv("BTCPAY_WEBHOOK_SECRET", ""),
    }


def validate_config(config: Dict) -> bool:
    """Validate configuration is complete."""
    required_keys = [
        "btcpay_url",
        "btcpay_api_key",
        "btcpay_store_id",
        "webhook_secret",
    ]

    for key in required_keys:
        if not config.get(key):
            log.error(f"Missing required configuration: {key}")
            return False

    return True


def main():
    """Main scanner loop."""
    log.info("BTCPay Invoice Scanner starting...")

    # Get configuration
    db_config = get_db_config()
    btcpay_config = get_btcpay_config()

    # Validate configuration
    if not validate_config(btcpay_config):
        log.error("Invalid BTCPay configuration. Exiting.")
        sys.exit(1)

    # Initialize BTCPay integration
    try:
        btcpay = BTCPayServerIntegration(
            db_config=db_config,
            **btcpay_config
        )
        log.info("BTCPay integration initialized")
    except Exception as e:
        log.error(f"Failed to initialize BTCPay integration: {e}")
        sys.exit(1)

    # Scan interval in seconds (default: 5 minutes)
    scan_interval = int(os.getenv("BTCPAY_SCAN_INTERVAL", "300"))
    log.info(f"Scan interval: {scan_interval} seconds")

    # Main loop
    while True:
        try:
            log.info("Scanning pending invoices...")
            verified_count = btcpay.scan_pending_invoices()
            log.info(f"Scan complete. Verified {verified_count} invoices.")

        except KeyboardInterrupt:
            log.info("Scanner stopped by user")
            break

        except Exception as e:
            log.error(f"Error during scan: {e}", exc_info=True)

        # Wait before next scan
        time.sleep(scan_interval)


if __name__ == "__main__":
    main()
