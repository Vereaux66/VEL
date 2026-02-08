#!/usr/bin/env python3
"""
VEL Trading System - Unified Launch Script
===========================================

Single authoritative entry point for the VEL trading system.
This script is invoked by start.sh and provides deterministic,
phase-gated startup with safety kernel loaded before execution.

All boot operations go through vel_orchestration_manifest.py.
NO FALLBACKS - If boot fails, system halts. No silent degradation.

Usage:
    python run.py              # Standard boot (recommended)
    python run.py --dry-run    # Validate without starting
    python run.py --help       # Show help
"""

import logging
import sys
import os
from pathlib import Path

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vel.run")


def main() -> int:
    """
    Unified entry point - delegates to START_ANVEL.py orchestration.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = sys.argv[1:]
    
    if "--help" in args or "-h" in args:
        print(__doc__)
        print("\nOptions:")
        print("  --dry-run    Validate configuration without starting")
        print("  --help       Show this help message")
        print("\nFor most users, just run: python run.py")
        return 0
    
    if "--dry-run" in args:
        logger.info("Running dry-run validation...")
        return run_dry_validation()
    
    # Standard boot via START_ANVEL.py
    return run_orchestrated_boot()


def run_dry_validation() -> int:
    """
    Run validation without starting the system.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        from START_ANVEL import PreBootValidator
        
        validator = PreBootValidator()
        success, errors, warnings = validator.validate_all()
        
        if warnings:
            for warning in warnings:
                logger.warning(f"Validation warning: {warning}")
        
        if not success:
            logger.error("Dry-run validation FAILED:")
            for error in errors:
                logger.error(f"  ✗ {error}")
            return 1
        
        logger.info("Dry-run validation PASSED")
        return 0
        
    except ImportError as e:
        logger.error(f"Could not import validation module: {e}")
        return 1
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return 1


def run_orchestrated_boot() -> int:
    """
    Execute orchestrated boot sequence.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Import and run the unified startup
        from START_ANVEL import main as start_main
        start_main()
        return 0
        
    except SystemExit as e:
        # Pass through exit codes from START_ANVEL
        return e.code if e.code is not None else 1
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        return 0
    except Exception as e:
        logger.critical(f"Boot error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
