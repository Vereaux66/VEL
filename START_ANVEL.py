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
    python START_ANVEL.py --help       # Show help
"""

import sys
import os

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def show_help():
    """Display help information"""
    print(__doc__)
    print("\nOptions:")
    print("  --legacy    Use legacy ANVEL_MASTER boot path")
    print("  --monitor   Launch runtime monitoring dashboard")
    print("  --help      Show this help message")
    print("\nFor most users, just run: python START_ANVEL.py")
    print()


def launch_monitor():
    """Launch runtime monitoring dashboard"""
    try:
        from anvel_ultimate_runtime import main as monitor_main
        monitor_main()
    except ImportError as e:
        print(f"Error: Could not import monitoring module: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching monitor: {e}")
        sys.exit(1)


def launch_orchestrated():
    """Launch via deterministic OrchestrationManifest (primary boot path)."""
    try:
        from vel_orchestration_manifest import OrchestrationManifest
        import json
        from pathlib import Path

        print("Starting ANVEL via OrchestrationManifest (deterministic boot)...")
        print()

        # Load config
        config = {}
        config_path = Path("anvel_config.json")
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)

        manifest = OrchestrationManifest(config=config)
        boot_report = manifest.execute_boot_sequence()

        if not boot_report.success:
            print(f"\n✗ Boot failed at phase {boot_report.failed_phase}: "
                  f"{boot_report.failure_reason}")
            print(f"  Components online: {len(boot_report.components_online)}")
            print(f"  Components failed: {boot_report.components_failed}")
            print("\nFalling back to legacy ANVEL_MASTER boot...")
            launch_legacy()
            return

        print(f"\n✓ ANVEL SYSTEM ONLINE")
        print(f"  Components: {len(boot_report.components_online)} online")
        print(f"  Boot time:  {boot_report.total_duration_seconds:.1f}s")
        if boot_report.warnings:
            print(f"  Warnings:   {len(boot_report.warnings)}")

        print("\n  Press ENTER to stop system, or Ctrl+C for emergency stop")
        print()

        # Wait for shutdown signal
        try:
            input()
        except KeyboardInterrupt:
            print("\n\n⚠ Interrupt received")

        # Graceful shutdown in reverse boot order
        print("\nInitiating graceful shutdown...")
        shutdown_report = manifest.execute_shutdown_sequence()
        stopped = sum(1 for v in shutdown_report.values() if v == "stopped")
        print(f"✓ ANVEL stopped ({stopped} components shut down)")

    except ImportError:
        print("OrchestrationManifest not available — using legacy boot")
        launch_legacy()
    except Exception as e:
        print(f"Error in orchestrated boot: {e}")
        print("Falling back to legacy ANVEL_MASTER boot...")
        launch_legacy()


def launch_legacy():
    """Launch ANVEL system via legacy ANVEL_MASTER"""
    try:
        from ANVEL_MASTER import main as master_main
        master_main()
    except ImportError as e:
        print(f"Error: Could not import ANVEL_MASTER: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching system: {e}")
        sys.exit(1)


def main():
    """Unified entry point"""
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()
        return

    if "--monitor" in args:
        print("Launching runtime monitor...")
        launch_monitor()
        return

    if "--legacy" in args or "--wizard" in args:
        print("Launching via legacy ANVEL_MASTER...")
        launch_legacy()
        return

    # Default: deterministic orchestrated boot
    launch_orchestrated()


if __name__ == "__main__":
    main()
