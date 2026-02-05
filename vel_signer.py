#!/usr/bin/env python3
"""
VEL Signer Interface
====================

Security-isolated transaction signing boundary.

Design principles:
- No private keys in application memory
- Strict signing interface
- Per-wallet blast radius isolation
- Full audit logging of all sign requests
- Support for dev (local) and production (remote) signers

Signer types:
1. Dev signer: Local key management (development only)
2. Remote signer: External signing service (production)
3. Hardware signer: Hardware wallet integration (future)

All sign requests are logged and auditable.
"""

import hashlib
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount

logger = logging.getLogger(__name__)


class SignerType(Enum):
    """Signer implementation type."""
    DEV_LOCAL = "dev_local"
    REMOTE = "remote"
    HARDWARE = "hardware"


@dataclass
class SignRequest:
    """Transaction signing request."""
    request_id: str
    chain_id: int
    wallet_address: str
    transaction: Dict[str, Any]
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def fingerprint(self) -> str:
        """Generate fingerprint for audit trail."""
        data = f"{self.chain_id}:{self.wallet_address}:{self.transaction}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class SignResponse:
    """Transaction signing response."""
    request_id: str
    success: bool
    signed_transaction: Optional[str] = None
    error: Optional[str] = None
    signed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SignerInterface(ABC):
    """
    Abstract signer interface.
    
    All signers must implement this interface to ensure
    consistent security boundary enforcement.
    """
    
    @abstractmethod
    def sign_transaction(
        self,
        chain_id: int,
        wallet_address: str,
        transaction: Dict[str, Any]
    ) -> Optional[str]:
        """
        Sign transaction.
        
        Args:
            chain_id: Chain ID
            wallet_address: Wallet address
            transaction: Transaction data
            
        Returns:
            Signed transaction hex or None
        """
        pass
    
    @abstractmethod
    def get_supported_wallets(self) -> list[str]:
        """Get list of wallet addresses this signer supports."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if signer is available and operational."""
        pass


class DevLocalSigner(SignerInterface):
    """
    Development-only local signer.
    
    WARNING: NOT FOR PRODUCTION USE
    Stores private keys in memory - suitable only for development and testing.
    """
    
    def __init__(self):
        """Initialize dev signer."""
        self._accounts: Dict[str, LocalAccount] = {}
        self._audit_log: list[SignRequest] = []
        
        # Load from environment
        private_key = os.getenv("VEL_PRIVATE_KEY") or os.getenv("ANVEL_PRIVATE_KEY")
        if private_key:
            self.add_account(private_key)
        
        logger.warning(
            "DEV LOCAL SIGNER INITIALIZED - NOT FOR PRODUCTION USE"
        )
    
    def add_account(self, private_key: str) -> bool:
        """
        Add account to signer.
        
        Args:
            private_key: Private key hex (with or without 0x prefix)
            
        Returns:
            True if successful
        """
        try:
            # Normalize private key format
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            
            # Create account
            account = Account.from_key(private_key)
            address = account.address.lower()
            
            self._accounts[address] = account
            
            logger.info(f"Account added to dev signer: {address}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add account: {e}", exc_info=True)
            return False
    
    def sign_transaction(
        self,
        chain_id: int,
        wallet_address: str,
        transaction: Dict[str, Any]
    ) -> Optional[str]:
        """Sign transaction with local private key."""
        request = SignRequest(
            request_id=f"sign_{datetime.now(timezone.utc).timestamp()}",
            chain_id=chain_id,
            wallet_address=wallet_address.lower(),
            transaction=transaction
        )
        
        # Audit log
        self._audit_log.append(request)
        logger.info(
            f"Sign request: {request.request_id}, wallet={wallet_address}, "
            f"fingerprint={request.fingerprint()}",
            extra={
                "request_id": request.request_id,
                "wallet": wallet_address,
                "chain_id": chain_id,
                "fingerprint": request.fingerprint()
            }
        )
        
        try:
            # Find account
            address = wallet_address.lower()
            if address not in self._accounts:
                logger.error(f"Wallet not found in signer: {wallet_address}")
                return None
            
            account = self._accounts[address]
            
            # Ensure chain ID is set
            if 'chainId' not in transaction:
                transaction['chainId'] = chain_id
            
            # Sign transaction
            signed = account.sign_transaction(transaction)
            signed_tx_hex = signed.raw_transaction.hex()
            
            logger.info(
                f"Transaction signed: {request.request_id}",
                extra={"request_id": request.request_id, "tx_hash": signed.hash.hex()}
            )
            
            return signed_tx_hex
            
        except Exception as e:
            logger.error(
                f"Transaction signing failed: {e}",
                extra={"request_id": request.request_id},
                exc_info=True
            )
            return None
    
    def get_supported_wallets(self) -> list[str]:
        """Get supported wallet addresses."""
        return list(self._accounts.keys())
    
    def is_available(self) -> bool:
        """Check if signer is available."""
        return len(self._accounts) > 0
    
    def get_audit_log(self) -> list[SignRequest]:
        """Get audit log (dev only)."""
        return self._audit_log.copy()


class RemoteSigner(SignerInterface):
    """
    Production remote signer.
    
    Communicates with external signing service.
    Private keys never touch application memory.
    """
    
    def __init__(self, endpoint: str, api_key: str):
        """
        Initialize remote signer.
        
        Args:
            endpoint: Remote signing service endpoint
            api_key: API key for authentication
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self._supported_wallets: list[str] = []
        
        # Fetch supported wallets from service
        self._refresh_supported_wallets()
        
        logger.info(f"Remote signer initialized: {endpoint}")
    
    def _refresh_supported_wallets(self):
        """Refresh list of supported wallets from remote service."""
        # Production implementation would call remote API
        logger.warning("Remote signer wallet refresh not implemented")
        self._supported_wallets = []
    
    def sign_transaction(
        self,
        chain_id: int,
        wallet_address: str,
        transaction: Dict[str, Any]
    ) -> Optional[str]:
        """Sign transaction via remote service."""
        request = SignRequest(
            request_id=f"sign_{datetime.now(timezone.utc).timestamp()}",
            chain_id=chain_id,
            wallet_address=wallet_address.lower(),
            transaction=transaction
        )
        
        logger.info(
            f"Remote sign request: {request.request_id}, wallet={wallet_address}",
            extra={
                "request_id": request.request_id,
                "wallet": wallet_address,
                "chain_id": chain_id,
                "fingerprint": request.fingerprint()
            }
        )
        
        # Production implementation would:
        # 1. Serialize transaction
        # 2. Send to remote signing service
        # 3. Wait for signed transaction
        # 4. Validate signature
        # 5. Return signed transaction
        
        logger.error("Remote signer not fully implemented")
        return None
    
    def get_supported_wallets(self) -> list[str]:
        """Get supported wallet addresses."""
        return self._supported_wallets.copy()
    
    def is_available(self) -> bool:
        """Check if remote signer is available."""
        # Production implementation would ping remote service
        return False


class MockSigner(SignerInterface):
    """
    Mock signer for testing.
    
    Does not actually sign - returns mock signatures.
    For testing pipeline only.
    """
    
    def __init__(self):
        """Initialize mock signer."""
        self._wallets = ["0x0000000000000000000000000000000000000001"]
        logger.warning("MOCK SIGNER INITIALIZED - FOR TESTING ONLY")
    
    def sign_transaction(
        self,
        chain_id: int,
        wallet_address: str,
        transaction: Dict[str, Any]
    ) -> Optional[str]:
        """Return mock signed transaction."""
        logger.info(f"Mock sign: wallet={wallet_address}, chain={chain_id}")
        # Return valid-looking but fake signed transaction
        return "0x" + "00" * 100
    
    def get_supported_wallets(self) -> list[str]:
        """Get mock wallet addresses."""
        return self._wallets.copy()
    
    def is_available(self) -> bool:
        """Mock signer is always available."""
        return True


class MultiWalletSigner(SignerInterface):
    """
    Multi-wallet signer orchestrator.
    
    Routes signing requests to appropriate signer based on wallet address.
    Provides blast radius isolation - compromise of one wallet doesn't affect others.
    """
    
    def __init__(self):
        """Initialize multi-wallet signer."""
        self._signers: Dict[str, SignerInterface] = {}  # wallet -> signer
        logger.info("Multi-wallet signer initialized")
    
    def register_wallet(self, wallet_address: str, signer: SignerInterface) -> bool:
        """
        Register wallet with signer.
        
        Args:
            wallet_address: Wallet address
            signer: Signer instance for this wallet
            
        Returns:
            True if successful
        """
        try:
            address = wallet_address.lower()
            self._signers[address] = signer
            logger.info(f"Wallet registered: {address}")
            return True
        except Exception as e:
            logger.error(f"Failed to register wallet: {e}", exc_info=True)
            return False
    
    def sign_transaction(
        self,
        chain_id: int,
        wallet_address: str,
        transaction: Dict[str, Any]
    ) -> Optional[str]:
        """Route signing request to appropriate signer."""
        address = wallet_address.lower()
        
        if address not in self._signers:
            logger.error(f"No signer registered for wallet: {wallet_address}")
            return None
        
        signer = self._signers[address]
        
        if not signer.is_available():
            logger.error(f"Signer for wallet {wallet_address} is not available")
            return None
        
        return signer.sign_transaction(chain_id, wallet_address, transaction)
    
    def get_supported_wallets(self) -> list[str]:
        """Get all supported wallet addresses."""
        return list(self._signers.keys())
    
    def is_available(self) -> bool:
        """Check if at least one signer is available."""
        return any(signer.is_available() for signer in self._signers.values())


# Global signer instance
_default_signer: Optional[SignerInterface] = None


def get_default_signer() -> SignerInterface:
    """
    Get default signer instance.
    
    In production, this should be configured based on environment.
    For development, returns DevLocalSigner.
    """
    global _default_signer
    
    if _default_signer is None:
        # Check environment for signer type
        signer_type = os.getenv("VEL_SIGNER_TYPE", "dev_local").lower()
        
        if signer_type == "dev_local":
            _default_signer = DevLocalSigner()
        elif signer_type == "remote":
            endpoint = os.getenv("VEL_SIGNER_ENDPOINT")
            api_key = os.getenv("VEL_SIGNER_API_KEY")
            if endpoint and api_key:
                _default_signer = RemoteSigner(endpoint, api_key)
            else:
                logger.error("Remote signer requires VEL_SIGNER_ENDPOINT and VEL_SIGNER_API_KEY")
                _default_signer = MockSigner()
        elif signer_type == "mock":
            _default_signer = MockSigner()
        else:
            logger.warning(f"Unknown signer type: {signer_type}, using mock")
            _default_signer = MockSigner()
    
    return _default_signer


def set_default_signer(signer: SignerInterface):
    """Set default signer instance."""
    global _default_signer
    _default_signer = signer
    logger.info(f"Default signer set: {type(signer).__name__}")
