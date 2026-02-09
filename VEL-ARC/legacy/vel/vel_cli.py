#!/usr/bin/env python3
"""
VEL Command Line Interface
===========================

Pure CLI wrapper that delegates all operations to vel_orchestration_manifest.py.
This is the command-line interface for VEL operations.

Usage:
    vel start              # Start VEL system
    vel stop               # Stop VEL system gracefully
    vel status             # Show system status
    vel health             # Check system health
    vel validate           # Run pre-flight validation
    vel version            # Show version information

All commands enforce the single boot authority: vel_orchestration_manifest.py
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vel.cli")


def get_manifest():
    """Get OrchestrationManifest instance."""
    try:
        from vel_orchestration_manifest import OrchestrationManifest
        
        config = {}
        config_path = Path("anvel_config.json")
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
        
        return OrchestrationManifest(config=config)
    except ImportError as e:
        logger.critical(f"Failed to import OrchestrationManifest: {e}")
        sys.exit(1)


def cmd_start(args) -> int:
    """Start VEL system."""
    logger.info("Starting VEL system...")
    
    if not args.skip_validation:
        if not cmd_validate(args):
            return 1
    
    manifest = get_manifest()
    boot_report = manifest.execute_boot_sequence()
    
    if not boot_report.success:
        logger.critical(
            f"Boot failed at phase {boot_report.failed_phase}: "
            f"{boot_report.failure_reason}"
        )
        return 1
    
    logger.info("=" * 50)
    logger.info("VEL SYSTEM ONLINE")
    logger.info(f"  Components: {len(boot_report.components_online)} online")
    logger.info(f"  Boot time:  {boot_report.total_duration_seconds:.1f}s")
    logger.info("=" * 50)
    
    if args.daemon:
        logger.info("Running in daemon mode...")
        # Keep running until interrupted
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass
    else:
        print("\nPress ENTER to stop system, or Ctrl+C for emergency stop\n")
        try:
            input()
        except KeyboardInterrupt:
            pass
    
    return cmd_stop(args)


def cmd_stop(args) -> int:
    """Stop VEL system."""
    logger.info("Stopping VEL system...")
    
    manifest = get_manifest()
    shutdown_report = manifest.execute_shutdown_sequence()
    
    stopped = sum(1 for v in shutdown_report.values() if v == "stopped")
    logger.info(f"VEL stopped ({stopped} components shut down)")
    return 0


def cmd_status(args) -> int:
    """Show system status."""
    manifest = get_manifest()
    
    print("\n" + "=" * 50)
    print("VEL SYSTEM STATUS")
    print("=" * 50)
    
    # Show component status
    for name, component in manifest.components.items():
        status = "ONLINE" if component else "OFFLINE"
        print(f"  {name}: {status}")
    
    print("=" * 50 + "\n")
    return 0


def cmd_health(args) -> int:
    """Check system health."""
    try:
        from vel_health_server import HealthServer
        health = HealthServer()
        report = health.check_all()
        
        print("\n" + "=" * 50)
        print("VEL HEALTH CHECK")
        print("=" * 50)
        
        overall = "HEALTHY" if report.get("healthy", False) else "UNHEALTHY"
        print(f"  Overall Status: {overall}")
        
        for check, result in report.get("checks", {}).items():
            status = "✓" if result.get("healthy") else "✗"
            print(f"  {status} {check}: {result.get('message', 'N/A')}")
        
        print("=" * 50 + "\n")
        return 0 if report.get("healthy") else 1
        
    except ImportError:
        logger.warning("Health server not available")
        return 1


def cmd_validate(args) -> int:
    """Run pre-flight validation."""
    logger.info("Running pre-flight validation...")
    
    try:
        from START_ANVEL import PreBootValidator
        validator = PreBootValidator()
        success, errors, warnings = validator.validate_all()
        
        if warnings:
            for warning in warnings:
                logger.warning(f"Warning: {warning}")
        
        if not success:
            logger.error("Validation FAILED:")
            for error in errors:
                logger.error(f"  ✗ {error}")
            return 1
        
        logger.info("Pre-flight validation PASSED")
        return 0
        
    except ImportError as e:
        logger.error(f"Failed to import validator: {e}")
        return 1


def cmd_version(args) -> int:
    """Show version information."""
    print("\nVEL Trading System")
    print("Version: 2.0.0")
    print("Boot Authority: vel_orchestration_manifest.py")
    print("")
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="vel",
        description="VEL Trading System Command Line Interface"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start VEL system")
    start_parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip pre-boot validation"
    )
    start_parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode"
    )
    start_parser.set_defaults(func=cmd_start)
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop VEL system")
    stop_parser.set_defaults(func=cmd_stop)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status")
    status_parser.set_defaults(func=cmd_status)
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.set_defaults(func=cmd_health)
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Run pre-flight validation")
    validate_parser.set_defaults(func=cmd_validate)
    
    # Version command
    version_parser = subparsers.add_parser("version", help="Show version")
    version_parser.set_defaults(func=cmd_version)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
