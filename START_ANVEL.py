#!/usr/bin/env python3
"""
UNIFIED ANVEL STARTUP SCRIPT
============================
Single entry point for all ANVEL startup operations.

Primary boot path uses the OrchestrationManifest for deterministic,
phase-gated startup with safety kernel loaded before execution.

Falls back to ANVEL_MASTER.py legacy boot if manifest is unavailable.

Usage:
    python START_ANVEL.py              # Deterministic boot (default)
    python START_ANVEL.py --legacy     # Legacy ANVEL_MASTER boot
    python START_ANVEL.py --monitor    # Runtime monitoring only
    python START_ANVEL.py --skip-validation  # Skip pre-boot validation
    python START_ANVEL.py --help       # Show help
"""

import logging
import sys
import os
from pathlib import Path
from typing import List, Tuple

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("anvel.startup")


class PreBootValidator:
    """
    Validates environment, configuration, and connectivity before boot.
    
    Fail-fast on critical issues - no silent defaults allowed.
    """
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        Run all validation checks.
        
        Returns:
            Tuple of (success, errors, warnings)
        """
        self._validate_python_version()
        self._validate_environment_variables()
        self._validate_config_files()
        self._validate_directories()
        self._validate_db_connectivity()
        self._validate_rpc_connectivity()
        
        return len(self.errors) == 0, self.errors, self.warnings
    
    def _validate_python_version(self) -> None:
        """Ensure Python version is compatible."""
        if sys.version_info < (3, 10):
            self.errors.append(
                f"Python 3.10+ required (for type union syntax and match statements), "
                f"found {sys.version_info.major}.{sys.version_info.minor}"
            )
    
    def _validate_environment_variables(self) -> None:
        """Validate required environment variables exist."""
        # Required for production mode
        env = os.environ.get("ANVEL_ENVIRONMENT", "development")
        
        if env == "production":
            required_vars = [
                "ANVEL_DATABASE_URL",
            ]
            
            for var in required_vars:
                if not os.environ.get(var):
                    self.errors.append(f"Missing required environment variable: {var}")
            
            # Warn about sensitive variables that should be set
            sensitive_vars = [
                "ANVEL_WALLET_PRIVATE_KEY",
                "ANVEL_KRAKEN_API_KEY",
                "ANVEL_COINBASE_API_KEY",
            ]
            
            for var in sensitive_vars:
                if not os.environ.get(var):
                    self.warnings.append(f"Production mode: {var} not set (trading may be limited)")
        
        # Check for debug mode in production
        if env == "production" and os.environ.get("ANVEL_DEBUG", "").lower() == "true":
            self.errors.append("ANVEL_DEBUG must not be 'true' in production")
    
    def _validate_config_files(self) -> None:
        """Validate required configuration files exist."""
        config_dir = Path("config")
        required_configs = ["system.json", "trading.json", "networks.json"]
        env = os.environ.get("ANVEL_ENVIRONMENT", "development")
        
        if config_dir.exists():
            for cfg in required_configs:
                cfg_path = config_dir / cfg
                if not cfg_path.exists():
                    if env == "production":
                        # In production, missing configs are errors
                        self.errors.append(f"Required configuration file missing: {cfg_path}")
                    else:
                        self.warnings.append(f"Configuration file missing: {cfg_path}")
        else:
            # Check for main config
            if not Path("anvel_config.json").exists():
                if env == "production":
                    self.errors.append("No configuration directory or anvel_config.json found")
                else:
                    self.warnings.append("No configuration directory or anvel_config.json found")
    
    def _validate_directories(self) -> None:
        """Validate data directories are writable."""
        data_dir = Path(os.environ.get("ANVEL_DATA_DIR", "data"))
        logs_dir = Path("logs")
        
        for dir_path in [data_dir, logs_dir]:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                # Test write permissions
                test_file = dir_path / ".write_test"
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                self.errors.append(f"Cannot write to directory {dir_path}: {e}")
    
    def _validate_db_connectivity(self) -> None:
        """Check database configuration (actual connectivity verified during boot phase)."""
        db_url = os.environ.get("ANVEL_DATABASE_URL", "")
        
        if db_url and not db_url.startswith("sqlite"):
            # For non-SQLite databases, actual connectivity is verified during boot
            self.warnings.append("Non-SQLite database configured - connectivity will be verified during boot")
    
    def _validate_rpc_connectivity(self) -> None:
        """Check RPC endpoint configuration (actual connectivity verified during boot phase)."""
        trading_enabled = os.environ.get("ANVEL_TRADING_ENABLED", "false").lower() == "true"
        
        if trading_enabled:
            rpc_vars = [
                "ANVEL_ETHEREUM_RPC_URL",
                "ANVEL_ARBITRUM_RPC_URL",
                "ANVEL_POLYGON_RPC_URL",
            ]
            
            has_rpc = any(os.environ.get(var) for var in rpc_vars)
            if not has_rpc:
                self.errors.append("Trading enabled but no RPC endpoints configured")


def show_help():
    """Display help information"""
    print(__doc__)
    print("\nOptions:")
    print("  --legacy           Use legacy ANVEL_MASTER boot path")
    print("  --monitor          Launch runtime monitoring dashboard")
    print("  --skip-validation  Skip pre-boot validation checks")
    print("  --help             Show this help message")
    print("\nFor most users, just run: python START_ANVEL.py")
    print()


def launch_monitor():
    """Launch runtime monitoring dashboard"""
    try:
        from anvel_ultimate_runtime import main as monitor_main
        monitor_main()
    except ImportError as e:
        logger.error(f"Could not import monitoring module: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error launching monitor: {e}")
        sys.exit(1)


def launch_orchestrated():
    """Launch via deterministic OrchestrationManifest (primary boot path)."""
    try:
        from vel_orchestration_manifest import OrchestrationManifest
        import json

        logger.info("Starting ANVEL via OrchestrationManifest (deterministic boot)...")

        # Load config
        config = {}
        config_path = Path("anvel_config.json")
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)

        manifest = OrchestrationManifest(config=config)
        boot_report = manifest.execute_boot_sequence()

        if not boot_report.success:
            logger.error(
                f"Boot failed at phase {boot_report.failed_phase}: "
                f"{boot_report.failure_reason}"
            )
            logger.error(f"Components online: {len(boot_report.components_online)}")
            logger.error(f"Components failed: {boot_report.components_failed}")
            logger.warning("Falling back to legacy ANVEL_MASTER boot...")
            launch_legacy()
            return

        logger.info("=" * 50)
        logger.info("ANVEL SYSTEM ONLINE")
        logger.info(f"  Components: {len(boot_report.components_online)} online")
        logger.info(f"  Boot time:  {boot_report.total_duration_seconds:.1f}s")
        if boot_report.warnings:
            logger.warning(f"  Warnings:   {len(boot_report.warnings)}")
        logger.info("=" * 50)

        print("\n  Press ENTER to stop system, or Ctrl+C for emergency stop\n")

        # Wait for shutdown signal
        try:
            input()
        except KeyboardInterrupt:
            logger.warning("Interrupt received")

        # Graceful shutdown in reverse boot order
        logger.info("Initiating graceful shutdown...")
        shutdown_report = manifest.execute_shutdown_sequence()
        stopped = sum(1 for v in shutdown_report.values() if v == "stopped")
        logger.info(f"ANVEL stopped ({stopped} components shut down)")

    except ImportError:
        logger.warning("OrchestrationManifest not available — using legacy boot")
        launch_legacy()
    except Exception as e:
        logger.error(f"Error in orchestrated boot: {e}")
        logger.warning("Falling back to legacy ANVEL_MASTER boot...")
        launch_legacy()


def launch_legacy():
    """Launch ANVEL system via legacy ANVEL_MASTER"""
    try:
        from ANVEL_MASTER import main as master_main
        master_main()
    except ImportError as e:
        logger.error(f"Could not import ANVEL_MASTER: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error launching system: {e}")
        sys.exit(1)


def run_pre_boot_validation() -> bool:
    """
    Run pre-boot validation checks.
    
    Returns:
        True if validation passed, False otherwise
    """
    validator = PreBootValidator()
    success, errors, warnings = validator.validate_all()
    
    if warnings:
        for warning in warnings:
            logger.warning(f"Pre-boot warning: {warning}")
    
    if not success:
        logger.error("=" * 50)
        logger.error("PRE-BOOT VALIDATION FAILED")
        logger.error("=" * 50)
        for error in errors:
            logger.error(f"  ✗ {error}")
        logger.error("")
        logger.error("Fix the above issues before starting ANVEL.")
        logger.error("Use --skip-validation to bypass (not recommended)")
        return False
    
    logger.info("Pre-boot validation passed")
    return True


def main():
    """Unified entry point"""
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()
        return

    if "--monitor" in args:
        logger.info("Launching runtime monitor...")
        launch_monitor()
        return

    # Run pre-boot validation unless skipped
    skip_validation = "--skip-validation" in args
    
    if not skip_validation:
        if not run_pre_boot_validation():
            sys.exit(1)

    if "--legacy" in args or "--wizard" in args:
        logger.info("Launching via legacy ANVEL_MASTER...")
        launch_legacy()
        return

    # Default: deterministic orchestrated boot
    launch_orchestrated()


if __name__ == "__main__":
    main()
