#!/usr/bin/env python3
"""ANVEL Learning Persistence Module.

Provides model checkpointing, versioning, and CloudWatch metrics integration
for the continuous learning system to support eternal 24/7 operation.

Security Note:
    All new model checkpoints are saved with HMAC-SHA256 signatures for integrity
    verification. Legacy models without signatures can still be loaded (with warnings)
    for backward compatibility. Set ANVEL_ENFORCE_MODEL_SIGNATURES=true to reject
    unsigned models in production environments.
"""

import hashlib
import hmac
import json
import logging
import os
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Get signing key for model integrity verification
# SECURITY: This MUST be set in production via AWS Secrets Manager or SSM Parameter Store
# If not set, a warning is logged and a session-specific key is generated
_SIGNING_KEY_ENV = os.getenv("ANVEL_MODEL_SIGNING_KEY")
if _SIGNING_KEY_ENV:
    _SIGNING_KEY = _SIGNING_KEY_ENV.encode("utf-8")
else:
    # Generate a random key for this session only
    # Models saved with this key can only be verified in the same session
    import secrets

    _SIGNING_KEY = secrets.token_bytes(32)
    logger.warning(
        "SECURITY WARNING: ANVEL_MODEL_SIGNING_KEY not set. Using session-specific random key. "
        "Models saved in this session cannot be verified after restart. "
        "Set ANVEL_MODEL_SIGNING_KEY in production to enable cross-session verification."
    )

# Option to enforce signature verification and reject unsigned models
_ENFORCE_SIGNATURES = (
    os.getenv("ANVEL_ENFORCE_MODEL_SIGNATURES", "false").lower() == "true"
)


def _compute_signature(data: bytes) -> str:
    """Compute HMAC-SHA256 signature for data integrity verification.

    Args:
        data: Raw bytes to sign

    Returns:
        Hex-encoded signature
    """
    return hmac.new(_SIGNING_KEY, data, hashlib.sha256).hexdigest()


def _verify_signature(data: bytes, expected_signature: str) -> bool:
    """Verify HMAC-SHA256 signature of data.

    Args:
        data: Raw bytes to verify
        expected_signature: Expected hex-encoded signature

    Returns:
        True if signature matches
    """
    actual_signature = _compute_signature(data)
    return hmac.compare_digest(actual_signature, expected_signature)


def _secure_pickle_dump(obj: Any, file_path: Path) -> str:
    """Securely serialize object with integrity signature.

    Args:
        obj: Object to serialize
        file_path: Path to write pickled object

    Returns:
        Hex-encoded signature of the pickled data
    """
    pickled_data = pickle.dumps(obj)
    signature = _compute_signature(pickled_data)

    with open(file_path, "wb") as f:
        f.write(pickled_data)

    return signature


def _secure_pickle_load(file_path: Path, expected_signature: str) -> Any:
    """Securely deserialize object with signature verification.

    Args:
        file_path: Path to pickled object
        expected_signature: Expected hex-encoded signature

    Returns:
        Deserialized object

    Raises:
        ValueError: If signature verification fails
    """
    with open(file_path, "rb") as f:
        pickled_data = f.read()

    if not _verify_signature(pickled_data, expected_signature):
        raise ValueError(
            f"Model file signature verification failed for {file_path}. "
            "File may have been tampered with or corrupted."
        )

    return pickle.loads(pickled_data)


class ModelCheckpointer:
    """Manages model checkpointing to local and cloud storage."""

    def __init__(
        self,
        local_path: str = "./data/models",
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "anvel/models",
        checkpoint_interval: int = 3600,  # 1 hour
    ):
        """Initialize the checkpointer.

        Args:
            local_path: Local directory for model checkpoints
            s3_bucket: Optional S3 bucket name for cloud persistence
            s3_prefix: S3 key prefix for model storage
            checkpoint_interval: Minimum seconds between checkpoints
        """
        self.local_path = Path(local_path)
        self.local_path.mkdir(parents=True, exist_ok=True)
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.checkpoint_interval = checkpoint_interval
        self._last_checkpoint: Dict[str, float] = {}
        self._s3_client = None

        if s3_bucket:
            try:
                import boto3

                self._s3_client = boto3.client("s3")
                logger.info(
                    "S3 checkpointing enabled: s3://%s/%s",
                    s3_bucket,
                    s3_prefix,
                )
            except ImportError:
                logger.warning("boto3 not available, S3 checkpointing disabled")
            except Exception as exc:
                logger.warning("Failed to initialize S3 client: %s", exc)

    def should_checkpoint(self, symbol: str) -> bool:
        """Check if enough time has passed to checkpoint this symbol."""
        last = self._last_checkpoint.get(symbol, 0)
        return (time.time() - last) >= self.checkpoint_interval

    def save_model(
        self,
        symbol: str,
        model: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Save a model checkpoint locally and to S3 if configured.

        Args:
            symbol: Trading symbol
            model: Model object to checkpoint
            metadata: Optional metadata to save alongside model

        Returns:
            True if checkpoint succeeded
        """
        if not self.should_checkpoint(symbol):
            return False

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Use semantic versioning: v{timestamp}_{symbol}_{iteration}
        iteration = int(time.time() % 100000)  # Rolling iteration counter
        version = f"v{timestamp}_{symbol}_{iteration}"
        model_filename = f"{symbol}_{version}.pkl"
        meta_filename = f"{symbol}_{version}_meta.json"

        try:
            # Save locally with integrity signature
            local_model_path = self.local_path / model_filename
            local_meta_path = self.local_path / meta_filename

            # Use secure pickle dump with HMAC signature
            signature = _secure_pickle_dump(model, local_model_path)

            checkpoint_meta = {
                "symbol": symbol,
                "timestamp": timestamp,
                "version": version,
                "checkpoint_time": time.time(),
                "signature": signature,  # Store signature for verification
                **(metadata or {}),
            }

            with open(local_meta_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint_meta, f, indent=2)

            logger.info("Model checkpoint saved locally: %s", local_model_path)

            # Upload to S3 if configured
            if self._s3_client and self.s3_bucket:
                try:
                    s3_model_key = f"{self.s3_prefix}/{model_filename}"
                    s3_meta_key = f"{self.s3_prefix}/{meta_filename}"

                    self._s3_client.upload_file(
                        str(local_model_path), self.s3_bucket, s3_model_key
                    )
                    self._s3_client.upload_file(
                        str(local_meta_path), self.s3_bucket, s3_meta_key
                    )

                    # Update latest pointer
                    latest_key = f"{self.s3_prefix}/{symbol}_latest.json"
                    latest_info = {
                        "model_key": s3_model_key,
                        "meta_key": s3_meta_key,
                        "version": version,
                        "timestamp": timestamp,
                    }
                    self._s3_client.put_object(
                        Bucket=self.s3_bucket,
                        Key=latest_key,
                        Body=json.dumps(latest_info, indent=2).encode("utf-8"),
                    )

                    logger.info(
                        "Model checkpoint uploaded to S3: s3://%s/%s",
                        self.s3_bucket,
                        s3_model_key,
                    )
                except Exception as exc:
                    logger.error("Failed to upload checkpoint to S3: %s", exc)

            self._last_checkpoint[symbol] = time.time()
            return True

        except Exception as exc:
            logger.error("Failed to save model checkpoint: %s", exc)
            return False

    def load_latest_model(self, symbol: str) -> Optional[Any]:
        """Load the latest model checkpoint for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Loaded model or None if no checkpoint exists
        """
        try:
            # Try S3 first if configured
            if self._s3_client and self.s3_bucket:
                try:
                    latest_key = f"{self.s3_prefix}/{symbol}_latest.json"
                    response = self._s3_client.get_object(
                        Bucket=self.s3_bucket, Key=latest_key
                    )
                    latest_info = json.loads(response["Body"].read().decode("utf-8"))
                    model_key = latest_info["model_key"]
                    meta_key = latest_info.get("meta_key")

                    # Get signature from metadata if available
                    signature = None
                    if meta_key:
                        try:
                            meta_response = self._s3_client.get_object(
                                Bucket=self.s3_bucket, Key=meta_key
                            )
                            meta_data = json.loads(
                                meta_response["Body"].read().decode("utf-8")
                            )
                            signature = meta_data.get("signature")
                        except Exception as exc:
                            logger.warning(
                                "Could not load metadata for signature: %s", exc
                            )

                    # Download to temp location
                    temp_path = self.local_path / f"{symbol}_temp.pkl"
                    try:
                        self._s3_client.download_file(
                            self.s3_bucket, model_key, str(temp_path)
                        )

                        # Use secure load if signature is available
                        if signature:
                            model = _secure_pickle_load(temp_path, signature)
                            logger.info(
                                "Model loaded from S3 with verified signature: s3://%s/%s",
                                self.s3_bucket,
                                model_key,
                            )
                        else:
                            if _ENFORCE_SIGNATURES:
                                raise ValueError(
                                    f"Unsigned model rejected by security policy: s3://{self.s3_bucket}/{model_key}. "
                                    "Set ANVEL_ENFORCE_MODEL_SIGNATURES=false to allow legacy models."
                                )
                            logger.warning(
                                "SECURITY WARNING: Loading model from S3 without signature verification (legacy model). "
                                "This is a security risk. Model: s3://%s/%s. "
                                "Consider re-saving models to add signature protection.",
                                self.s3_bucket,
                                model_key,
                            )
                            with open(temp_path, "rb") as f:
                                model = pickle.load(f)

                        return model
                    finally:
                        # Always clean up temp file
                        if temp_path.exists():
                            temp_path.unlink()

                except Exception as exc:
                    logger.warning("Failed to load from S3, trying local: %s", exc)

            # Fall back to local storage
            pattern = f"{symbol}_*_v*.pkl"
            checkpoints = sorted(self.local_path.glob(pattern), reverse=True)

            if checkpoints:
                latest_checkpoint = checkpoints[0]

                # Try to load metadata for signature
                meta_path = latest_checkpoint.with_name(
                    latest_checkpoint.stem + "_meta.json"
                )
                signature = None
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta_data = json.load(f)
                            signature = meta_data.get("signature")
                    except Exception as exc:
                        logger.warning("Could not load metadata for signature: %s", exc)

                # Use secure load if signature is available
                if signature:
                    model = _secure_pickle_load(latest_checkpoint, signature)
                    logger.info(
                        "Model loaded from local with verified signature: %s",
                        latest_checkpoint,
                    )
                else:
                    if _ENFORCE_SIGNATURES:
                        raise ValueError(
                            f"Unsigned model rejected by security policy: {latest_checkpoint}. "
                            "Set ANVEL_ENFORCE_MODEL_SIGNATURES=false to allow legacy models."
                        )
                    logger.warning(
                        "SECURITY WARNING: Loading model from local storage without signature verification (legacy model). "
                        "This is a security risk. Model: %s. "
                        "Consider re-saving models to add signature protection.",
                        latest_checkpoint,
                    )
                    with open(latest_checkpoint, "rb") as f:
                        model = pickle.load(f)

                return model

            logger.info("No checkpoint found for %s", symbol)
            return None

        except Exception as exc:
            logger.error("Failed to load model checkpoint: %s", exc)
            return None


class CloudWatchMetrics:
    """Publishes learning metrics to AWS CloudWatch."""

    def __init__(
        self,
        namespace: str = "ANVEL/Learning",
        enabled: bool = True,
    ):
        """Initialize CloudWatch metrics publisher.

        Args:
            namespace: CloudWatch namespace for metrics
            enabled: Whether CloudWatch publishing is enabled
        """
        self.namespace = namespace
        self.enabled = enabled
        self._cw_client = None

        if enabled:
            try:
                import boto3

                self._cw_client = boto3.client("cloudwatch")
                logger.info("CloudWatch metrics enabled: %s", namespace)
            except ImportError:
                logger.warning("boto3 not available, CloudWatch metrics disabled")
                self.enabled = False
            except Exception as exc:
                logger.warning("Failed to initialize CloudWatch client: %s", exc)
                self.enabled = False

    def publish_learning_metrics(
        self,
        symbol: str,
        metrics: Dict[str, float],
    ) -> bool:
        """Publish learning metrics to CloudWatch.

        Args:
            symbol: Trading symbol
            metrics: Dictionary of metric names to values

        Returns:
            True if metrics were published successfully
        """
        if not self.enabled or not self._cw_client:
            return False

        try:
            metric_data = []
            timestamp = datetime.now(timezone.utc)

            for metric_name, value in metrics.items():
                metric_data.append(
                    {
                        "MetricName": metric_name,
                        "Value": float(value),
                        "Timestamp": timestamp,
                        "Unit": "None",
                        "Dimensions": [
                            {"Name": "Symbol", "Value": symbol},
                        ],
                    }
                )

            if metric_data:
                self._cw_client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=metric_data,
                )
                return True

        except Exception as exc:
            logger.error("Failed to publish CloudWatch metrics: %s", exc)

        return False

    def publish_model_checkpoint(
        self,
        symbol: str,
        version: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publish a model checkpoint event to CloudWatch.

        Args:
            symbol: Trading symbol
            version: Model version
            metadata: Optional metadata about the checkpoint

        Returns:
            True if event was published successfully
        """
        if not self.enabled or not self._cw_client:
            return False

        try:
            metrics = [
                {
                    "MetricName": "ModelCheckpoint",
                    "Value": 1.0,
                    "Timestamp": datetime.now(timezone.utc),
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "Symbol", "Value": symbol},
                        {"Name": "Version", "Value": version},
                    ],
                }
            ]

            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (int, float)):
                        metrics.append(
                            {
                                "MetricName": f"Checkpoint_{key}",
                                "Value": float(value),
                                "Timestamp": datetime.now(timezone.utc),
                                "Unit": "None",
                                "Dimensions": [
                                    {"Name": "Symbol", "Value": symbol},
                                    {"Name": "Version", "Value": version},
                                ],
                            }
                        )

            self._cw_client.put_metric_data(
                Namespace=self.namespace,
                MetricData=metrics,
            )
            return True

        except Exception as exc:
            logger.error("Failed to publish checkpoint event to CloudWatch: %s", exc)
            return False


class EFSModelStorage:
    """Manages model storage on AWS EFS for shared access across instances."""

    def __init__(
        self,
        mount_point: str = "/mnt/efs/anvel/models",
        enabled: bool = True,
        max_retries: int = 3,
        retry_delay: int = 5,
    ):
        """Initialize EFS model storage.

        Args:
            mount_point: EFS mount point path
            enabled: Whether EFS storage is enabled
            max_retries: Number of retries for EFS mount verification
            retry_delay: Seconds to wait between retries
        """
        self.mount_point = Path(mount_point)
        self.enabled = enabled

        if enabled:
            # Retry logic for delayed EFS availability during bootstrap
            for attempt in range(max_retries):
                try:
                    # Check if mount point exists
                    if not self.mount_point.exists():
                        if attempt < max_retries - 1:
                            logger.info(
                                "EFS mount point %s not yet available, retrying in %ds (attempt %d/%d)",
                                mount_point,
                                retry_delay,
                                attempt + 1,
                                max_retries,
                            )
                            time.sleep(retry_delay)
                            continue
                        else:
                            raise FileNotFoundError(
                                f"Mount point {mount_point} does not exist"
                            )

                    # Verify it's actually an EFS mount by checking /proc/mounts
                    try:
                        with open("/proc/mounts", "r") as f:
                            mounts = f.read()
                            if "nfs4" not in mounts and "efs" not in mounts:
                                logger.warning(
                                    "Path %s exists but may not be an EFS mount",
                                    mount_point,
                                )
                    except Exception:
                        pass  # /proc/mounts may not be available on all systems

                    self.mount_point.mkdir(parents=True, exist_ok=True)
                    # Test write access
                    test_file = self.mount_point / ".write_test"
                    test_file.write_text("test")
                    test_file.unlink()
                    logger.info("EFS model storage ready: %s", mount_point)
                    break
                except Exception as exc:
                    if attempt < max_retries - 1:
                        logger.warning(
                            "EFS mount verification failed (attempt %d/%d): %s, retrying in %ds",
                            attempt + 1,
                            max_retries,
                            exc,
                            retry_delay,
                        )
                        time.sleep(retry_delay)
                    else:
                        logger.warning(
                            "EFS mount not available after %d attempts (%s), disabling",
                            max_retries,
                            exc,
                        )
                        self.enabled = False

    def save_model(
        self,
        symbol: str,
        model: Any,
        version: str,
    ) -> bool:
        """Save a model to EFS.

        Args:
            symbol: Trading symbol
            model: Model object
            version: Model version

        Returns:
            True if save succeeded
        """
        if not self.enabled:
            return False

        try:
            model_dir = self.mount_point / symbol
            model_dir.mkdir(parents=True, exist_ok=True)

            model_file = model_dir / f"{version}.pkl"
            sig_file = model_dir / f"{version}.sig"

            # Use secure pickle dump with HMAC signature
            signature = _secure_pickle_dump(model, model_file)

            # Save signature separately
            with open(sig_file, "w") as f:
                f.write(signature)

            # Update symlinks to latest
            latest_link = model_dir / "latest.pkl"
            latest_sig_link = model_dir / "latest.sig"

            if latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(model_file.name)

            if latest_sig_link.exists():
                latest_sig_link.unlink()
            latest_sig_link.symlink_to(sig_file.name)

            logger.info("Model saved to EFS with signature: %s", model_file)
            return True

        except Exception as exc:
            logger.error("Failed to save model to EFS: %s", exc)
            return False

    def load_latest_model(self, symbol: str) -> Optional[Any]:
        """Load the latest model from EFS.

        Args:
            symbol: Trading symbol

        Returns:
            Loaded model or None
        """
        if not self.enabled:
            return None

        try:
            model_dir = self.mount_point / symbol
            latest_link = model_dir / "latest.pkl"
            latest_sig_link = model_dir / "latest.sig"

            if not latest_link.exists():
                return None

            # Try to load signature
            signature = None
            if latest_sig_link.exists():
                try:
                    with open(latest_sig_link, "r") as f:
                        signature = f.read().strip()
                except Exception as exc:
                    logger.warning("Could not load signature from EFS: %s", exc)

            # Use secure load if signature is available
            if signature:
                model = _secure_pickle_load(latest_link, signature)
                logger.info(
                    "Model loaded from EFS with verified signature: %s", latest_link
                )
            else:
                if _ENFORCE_SIGNATURES:
                    raise ValueError(
                        f"Unsigned model rejected by security policy: {latest_link}. "
                        "Set ANVEL_ENFORCE_MODEL_SIGNATURES=false to allow legacy models."
                    )
                logger.warning(
                    "SECURITY WARNING: Loading model from EFS without signature verification (legacy model). "
                    "This is a security risk. Model: %s. "
                    "Consider re-saving models to add signature protection.",
                    latest_link,
                )
                with open(latest_link, "rb") as f:
                    model = pickle.load(f)

            return model

        except Exception as exc:
            logger.error("Failed to load model from EFS: %s", exc)
            return None
