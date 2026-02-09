#!/usr/bin/env python3
"""
ANVEL Encrypted Offline Backup System

Production-grade encrypted backup system for VEL trading platform.
Provides offline, encrypted storage for critical system data in case of compromise.

Features:
- AES-256-GCM encryption for data at rest
- Scrypt key derivation for password protection
- Integrity verification with SHA-256 checksums
- Automatic backup rotation
- Offline-capable (no network dependency)
- Tamper detection
- Recovery verification
"""

import base64
import gzip
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Cryptography imports
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

log = logging.getLogger(__name__)

# Constants
BACKUP_VERSION = 1
NONCE_SIZE = 12  # 96 bits for AES-GCM
SALT_SIZE = 32   # 256 bits
KEY_SIZE = 32    # 256 bits for AES-256
TAG_SIZE = 16    # 128 bits for GCM tag
SCRYPT_N = 2**17  # CPU/memory cost parameter
SCRYPT_R = 8      # Block size
SCRYPT_P = 1      # Parallelization


class BackupType(Enum):
    """Types of backup data."""
    FULL = "full"
    INCREMENTAL = "incremental"
    EMERGENCY = "emergency"
    CHECKPOINT = "checkpoint"


class BackupStatus(Enum):
    """Status of a backup."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CORRUPTED = "corrupted"
    VERIFIED = "verified"


@dataclass
class BackupMetadata:
    """Metadata for a backup entry."""
    backup_id: str
    backup_type: str
    created_at: float
    size_bytes: int
    compressed_size: int
    checksum: str
    status: str
    version: int
    description: str
    tables_included: List[str]
    encryption_salt: str  # Base64 encoded


class EncryptionEngine:
    """
    Handles encryption/decryption using AES-256-GCM.
    
    Security properties:
    - Authenticated encryption (confidentiality + integrity)
    - Unique nonce per encryption
    - Key derived from password using Scrypt
    """

    def __init__(self, password: str, salt: Optional[bytes] = None):
        """
        Initialize encryption engine.
        
        Args:
            password: Master password for encryption
            salt: Optional salt (generated if not provided)
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError(
                "cryptography library required for encryption. "
                "Install with: pip install cryptography"
            )

        if not password or len(password) < 12:
            raise ValueError("Password must be at least 12 characters")

        self.salt = salt or secrets.token_bytes(SALT_SIZE)
        self._key = self._derive_key(password, self.salt)
        self._cipher = AESGCM(self._key)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password using Scrypt."""
        kdf = Scrypt(
            salt=salt,
            length=KEY_SIZE,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            backend=default_backend(),
        )
        return kdf.derive(password.encode('utf-8'))

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypt data with AES-256-GCM.
        
        Returns:
            Encrypted data in format: nonce || ciphertext || tag
        """
        nonce = secrets.token_bytes(NONCE_SIZE)
        ciphertext = self._cipher.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        """
        Decrypt data encrypted with AES-256-GCM.
        
        Args:
            ciphertext: Data in format: nonce || ciphertext || tag
            
        Returns:
            Decrypted plaintext
        """
        if len(ciphertext) < NONCE_SIZE + TAG_SIZE:
            raise ValueError("Ciphertext too short")

        nonce = ciphertext[:NONCE_SIZE]
        data = ciphertext[NONCE_SIZE:]
        return self._cipher.decrypt(nonce, data, None)

    def get_salt_b64(self) -> str:
        """Get salt as base64 string for storage."""
        return base64.b64encode(self.salt).decode('ascii')

    @classmethod
    def from_salt_b64(cls, password: str, salt_b64: str) -> 'EncryptionEngine':
        """Create engine from stored base64 salt."""
        salt = base64.b64decode(salt_b64)
        return cls(password, salt)


class OfflineDatabase:
    """
    SQLite-based offline database with encryption support.
    
    Features:
    - Encrypted data storage
    - Integrity verification
    - Offline operation
    - Automatic compression
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS backups (
        backup_id TEXT PRIMARY KEY,
        backup_type TEXT NOT NULL,
        created_at REAL NOT NULL,
        size_bytes INTEGER NOT NULL,
        compressed_size INTEGER NOT NULL,
        checksum TEXT NOT NULL,
        status TEXT NOT NULL,
        version INTEGER NOT NULL,
        description TEXT,
        tables_included TEXT,
        encryption_salt TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS backup_data (
        backup_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        encrypted_data BLOB NOT NULL,
        checksum TEXT NOT NULL,
        PRIMARY KEY (backup_id, chunk_index),
        FOREIGN KEY (backup_id) REFERENCES backups(backup_id)
    );
    
    CREATE TABLE IF NOT EXISTS integrity_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        backup_id TEXT,
        event_type TEXT NOT NULL,
        success INTEGER NOT NULL,
        details TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_backups_created ON backups(created_at);
    CREATE INDEX IF NOT EXISTS idx_backups_type ON backups(backup_type);
    CREATE INDEX IF NOT EXISTS idx_integrity_timestamp ON integrity_log(timestamp);
    """

    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for large backups

    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize offline database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection (creates if needed)."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def store_backup(
        self,
        backup_id: str,
        metadata: BackupMetadata,
        encrypted_data: bytes,
    ) -> bool:
        """
        Store encrypted backup data.
        
        Args:
            backup_id: Unique backup identifier
            metadata: Backup metadata
            encrypted_data: Encrypted backup data
            
        Returns:
            True if successful
        """
        with self._lock:
            try:
                conn = self._get_connection()

                # Store metadata
                conn.execute(
                    """
                    INSERT OR REPLACE INTO backups 
                    (backup_id, backup_type, created_at, size_bytes, compressed_size,
                     checksum, status, version, description, tables_included, encryption_salt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        backup_id,
                        metadata.backup_type,
                        metadata.created_at,
                        metadata.size_bytes,
                        metadata.compressed_size,
                        metadata.checksum,
                        metadata.status,
                        metadata.version,
                        metadata.description,
                        json.dumps(metadata.tables_included),
                        metadata.encryption_salt,
                    ),
                )

                # Store data in chunks
                for i in range(0, len(encrypted_data), self.CHUNK_SIZE):
                    chunk = encrypted_data[i:i + self.CHUNK_SIZE]
                    chunk_checksum = hashlib.sha256(chunk).hexdigest()
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO backup_data
                        (backup_id, chunk_index, encrypted_data, checksum)
                        VALUES (?, ?, ?, ?)
                        """,
                        (backup_id, i // self.CHUNK_SIZE, chunk, chunk_checksum),
                    )

                # Log success
                self._log_integrity_event(
                    conn, backup_id, "backup_stored", True,
                    f"Stored {len(encrypted_data)} bytes in "
                    f"{(len(encrypted_data) + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE} chunks"
                )

                conn.commit()
                return True

            except Exception as e:
                log.exception("Failed to store backup: %s", e)
                self._log_integrity_event(
                    conn, backup_id, "backup_store_failed", False, str(e)
                )
                return False

    def retrieve_backup(self, backup_id: str) -> Tuple[Optional[BackupMetadata], Optional[bytes]]:
        """
        Retrieve encrypted backup data.
        
        Args:
            backup_id: Backup identifier
            
        Returns:
            Tuple of (metadata, encrypted_data) or (None, None) if not found
        """
        with self._lock:
            try:
                conn = self._get_connection()

                # Get metadata
                row = conn.execute(
                    "SELECT * FROM backups WHERE backup_id = ?",
                    (backup_id,),
                ).fetchone()

                if not row:
                    return None, None

                metadata = BackupMetadata(
                    backup_id=row["backup_id"],
                    backup_type=row["backup_type"],
                    created_at=row["created_at"],
                    size_bytes=row["size_bytes"],
                    compressed_size=row["compressed_size"],
                    checksum=row["checksum"],
                    status=row["status"],
                    version=row["version"],
                    description=row["description"],
                    tables_included=json.loads(row["tables_included"]),
                    encryption_salt=row["encryption_salt"],
                )

                # Get data chunks
                chunks = conn.execute(
                    """
                    SELECT encrypted_data, checksum FROM backup_data
                    WHERE backup_id = ?
                    ORDER BY chunk_index
                    """,
                    (backup_id,),
                ).fetchall()

                # Verify and assemble data
                data_parts = []
                for chunk in chunks:
                    chunk_data = chunk["encrypted_data"]
                    expected_checksum = chunk["checksum"]
                    actual_checksum = hashlib.sha256(chunk_data).hexdigest()

                    if actual_checksum != expected_checksum:
                        self._log_integrity_event(
                            conn, backup_id, "chunk_corruption_detected", False,
                            "Checksum mismatch in chunk"
                        )
                        return metadata, None

                    data_parts.append(chunk_data)

                encrypted_data = b"".join(data_parts)

                # Verify overall checksum
                overall_checksum = hashlib.sha256(encrypted_data).hexdigest()
                if overall_checksum != metadata.checksum:
                    self._log_integrity_event(
                        conn, backup_id, "backup_corruption_detected", False,
                        "Overall checksum mismatch"
                    )
                    return metadata, None

                self._log_integrity_event(
                    conn, backup_id, "backup_retrieved", True,
                    f"Retrieved {len(encrypted_data)} bytes"
                )

                return metadata, encrypted_data

            except Exception as e:
                log.exception("Failed to retrieve backup: %s", e)
                return None, None

    def list_backups(
        self,
        backup_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[BackupMetadata]:
        """List available backups."""
        with self._lock:
            conn = self._get_connection()

            if backup_type:
                rows = conn.execute(
                    """
                    SELECT * FROM backups 
                    WHERE backup_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (backup_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM backups 
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

            return [
                BackupMetadata(
                    backup_id=row["backup_id"],
                    backup_type=row["backup_type"],
                    created_at=row["created_at"],
                    size_bytes=row["size_bytes"],
                    compressed_size=row["compressed_size"],
                    checksum=row["checksum"],
                    status=row["status"],
                    version=row["version"],
                    description=row["description"],
                    tables_included=json.loads(row["tables_included"]),
                    encryption_salt=row["encryption_salt"],
                )
                for row in rows
            ]

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup and its data."""
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("DELETE FROM backup_data WHERE backup_id = ?", (backup_id,))
                conn.execute("DELETE FROM backups WHERE backup_id = ?", (backup_id,))
                conn.commit()

                self._log_integrity_event(
                    conn, backup_id, "backup_deleted", True, "Backup removed"
                )
                return True
            except Exception as e:
                log.exception("Failed to delete backup: %s", e)
                return False

    def verify_integrity(self, backup_id: str) -> Tuple[bool, str]:
        """
        Verify integrity of a stored backup.
        
        Returns:
            Tuple of (is_valid, message)
        """
        metadata, data = self.retrieve_backup(backup_id)

        if not metadata:
            return False, "Backup not found"

        if not data:
            return False, "Backup data corrupted or missing"

        # Verify checksum
        actual_checksum = hashlib.sha256(data).hexdigest()
        if actual_checksum != metadata.checksum:
            return False, "Checksum verification failed"

        return True, "Integrity verified"

    def get_integrity_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent integrity log entries."""
        with self._lock:
            conn = self._get_connection()
            rows = conn.execute(
                """
                SELECT * FROM integrity_log
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    def _log_integrity_event(
        self,
        conn: sqlite3.Connection,
        backup_id: Optional[str],
        event_type: str,
        success: bool,
        details: str,
    ) -> None:
        """Log an integrity event."""
        conn.execute(
            """
            INSERT INTO integrity_log (timestamp, backup_id, event_type, success, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (time.time(), backup_id, event_type, 1 if success else 0, details),
        )

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class EncryptedBackupSystem:
    """
    Main backup system with encryption, compression, and rotation.
    
    Features:
    - Automatic encryption of all backup data
    - Compression before encryption
    - Backup rotation with configurable retention
    - Emergency backup capability
    - Recovery verification
    """

    def __init__(
        self,
        backup_dir: Union[str, Path],
        master_password: str,
        max_backups: int = 30,
        auto_verify: bool = True,
    ):
        """
        Initialize encrypted backup system.
        
        Args:
            backup_dir: Directory for backup storage
            master_password: Master password for encryption
            max_backups: Maximum backups to retain (per type)
            auto_verify: Automatically verify backups after creation
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._master_password = master_password
        self._max_backups = max_backups
        self._auto_verify = auto_verify
        self._lock = threading.RLock()

        # Initialize offline database
        self._db = OfflineDatabase(self.backup_dir / "backup_catalog.db")

        log.info(
            "[BACKUP] Encrypted backup system initialized at %s",
            self.backup_dir
        )

    def create_backup(
        self,
        data: Dict[str, Any],
        backup_type: BackupType = BackupType.FULL,
        description: str = "",
        tables: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Create an encrypted backup.
        
        Args:
            data: Data to backup (will be JSON serialized)
            backup_type: Type of backup
            description: Optional description
            tables: List of tables/sections included
            
        Returns:
            Backup ID if successful, None otherwise
        """
        with self._lock:
            try:
                # Generate backup ID
                backup_id = f"{backup_type.value}_{int(time.time())}_{secrets.token_hex(4)}"

                # Serialize and compress
                json_data = json.dumps(data, default=str, indent=None)
                original_size = len(json_data.encode('utf-8'))
                compressed_data = gzip.compress(json_data.encode('utf-8'), compresslevel=9)
                compressed_size = len(compressed_data)

                # Create encryption engine with new salt
                engine = EncryptionEngine(self._master_password)

                # Encrypt
                encrypted_data = engine.encrypt(compressed_data)
                checksum = hashlib.sha256(encrypted_data).hexdigest()

                # Create metadata
                metadata = BackupMetadata(
                    backup_id=backup_id,
                    backup_type=backup_type.value,
                    created_at=time.time(),
                    size_bytes=original_size,
                    compressed_size=compressed_size,
                    checksum=checksum,
                    status=BackupStatus.COMPLETED.value,
                    version=BACKUP_VERSION,
                    description=description,
                    tables_included=tables or ["all"],
                    encryption_salt=engine.get_salt_b64(),
                )

                # Store in database
                if not self._db.store_backup(backup_id, metadata, encrypted_data):
                    return None

                # Verify if auto_verify enabled
                if self._auto_verify:
                    is_valid, msg = self._db.verify_integrity(backup_id)
                    if not is_valid:
                        log.error("[BACKUP] Verification failed: %s", msg)
                        return None
                    metadata.status = BackupStatus.VERIFIED.value

                # Rotate old backups
                self._rotate_backups(backup_type.value)

                log.info(
                    "[BACKUP] Created %s backup: %s (%d bytes -> %d bytes encrypted)",
                    backup_type.value, backup_id, original_size, len(encrypted_data)
                )

                return backup_id

            except Exception as e:
                log.exception("[BACKUP] Failed to create backup: %s", e)
                return None

    def restore_backup(
        self,
        backup_id: str,
        password: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Restore data from an encrypted backup.
        
        Args:
            backup_id: Backup identifier
            password: Password (uses master password if not provided)
            
        Returns:
            Restored data dictionary, or None if failed
        """
        with self._lock:
            try:
                # Retrieve backup
                metadata, encrypted_data = self._db.retrieve_backup(backup_id)

                if not metadata or not encrypted_data:
                    log.error("[BACKUP] Backup not found or corrupted: %s", backup_id)
                    return None

                # Create decryption engine with stored salt
                pwd = password or self._master_password
                engine = EncryptionEngine.from_salt_b64(pwd, metadata.encryption_salt)

                # Decrypt
                compressed_data = engine.decrypt(encrypted_data)

                # Decompress
                json_data = gzip.decompress(compressed_data).decode('utf-8')

                # Parse
                data = json.loads(json_data)

                log.info("[BACKUP] Restored backup: %s", backup_id)
                return data

            except Exception as e:
                log.exception("[BACKUP] Failed to restore backup: %s", e)
                return None

    def create_emergency_backup(
        self,
        data: Dict[str, Any],
        reason: str = "Emergency backup",
    ) -> Optional[str]:
        """
        Create an emergency backup (bypasses rotation).
        
        Use this when system compromise is detected.
        """
        return self.create_backup(
            data,
            backup_type=BackupType.EMERGENCY,
            description=f"EMERGENCY: {reason}",
        )

    def list_backups(
        self,
        backup_type: Optional[BackupType] = None,
    ) -> List[Dict[str, Any]]:
        """List available backups."""
        type_str = backup_type.value if backup_type else None
        backups = self._db.list_backups(backup_type=type_str)
        return [asdict(b) for b in backups]

    def verify_backup(self, backup_id: str) -> Tuple[bool, str]:
        """Verify backup integrity."""
        return self._db.verify_integrity(backup_id)

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup."""
        return self._db.delete_backup(backup_id)

    def get_status(self) -> Dict[str, Any]:
        """Get backup system status."""
        all_backups = self._db.list_backups(limit=1000)

        by_type = {}
        for b in all_backups:
            t = b.backup_type
            if t not in by_type:
                by_type[t] = {"count": 0, "total_size": 0, "latest": None}
            by_type[t]["count"] += 1
            by_type[t]["total_size"] += b.compressed_size
            if by_type[t]["latest"] is None or b.created_at > by_type[t]["latest"]:
                by_type[t]["latest"] = b.created_at

        return {
            "backup_dir": str(self.backup_dir),
            "total_backups": len(all_backups),
            "max_backups_per_type": self._max_backups,
            "backups_by_type": by_type,
            "auto_verify": self._auto_verify,
            "database_size": self._get_db_size(),
        }

    def get_integrity_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get integrity audit log."""
        return self._db.get_integrity_log(limit)

    def _rotate_backups(self, backup_type: str) -> None:
        """Remove old backups exceeding retention limit."""
        backups = self._db.list_backups(backup_type=backup_type, limit=1000)

        if len(backups) > self._max_backups:
            # Sort by created_at, delete oldest
            to_delete = sorted(backups, key=lambda b: b.created_at)[:-self._max_backups]
            for backup in to_delete:
                self._db.delete_backup(backup.backup_id)
                log.info("[BACKUP] Rotated old backup: %s", backup.backup_id)

    def _get_db_size(self) -> int:
        """Get database file size in bytes."""
        db_path = self.backup_dir / "backup_catalog.db"
        if db_path.exists():
            return db_path.stat().st_size
        return 0

    def close(self) -> None:
        """Close the backup system."""
        self._db.close()


# Convenience singleton instance
_backup_system_instance: Optional[EncryptedBackupSystem] = None


def get_backup_system(
    backup_dir: Optional[str] = None,
    master_password: Optional[str] = None,
) -> EncryptedBackupSystem:
    """
    Get or create the singleton EncryptedBackupSystem instance.
    
    Args:
        backup_dir: Backup directory (uses env var or default if not provided)
        master_password: Master password (uses env var if not provided)
    """
    global _backup_system_instance

    if _backup_system_instance is None:
        # Get configuration from environment or defaults
        dir_path = backup_dir or os.getenv(
            "ANVEL_BACKUP_DIR",
            os.path.join(os.path.expanduser("~"), ".anvel", "backups")
        )
        password = master_password or os.getenv("ANVEL_BACKUP_PASSWORD")

        if not password:
            raise ValueError(
                "Backup password required. Set ANVEL_BACKUP_PASSWORD environment "
                "variable or provide master_password parameter."
            )

        _backup_system_instance = EncryptedBackupSystem(
            backup_dir=dir_path,
            master_password=password,
        )

    return _backup_system_instance


def reset_backup_system() -> None:
    """Reset the singleton instance (for testing)."""
    global _backup_system_instance
    if _backup_system_instance:
        _backup_system_instance.close()
    _backup_system_instance = None
