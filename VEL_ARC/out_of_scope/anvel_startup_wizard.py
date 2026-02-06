#!/usr/bin/env python3
"""
DEPRECATED: Use START_ANVEL.py --wizard instead
==============================================
This file is deprecated and will be removed in a future release.

New usage:
    python START_ANVEL.py --wizard    # Interactive wizard
    python START_ANVEL.py             # Automated startup

---

ANVEL Startup Wizard - Comprehensive System Initialization Helper
Guides users through safe system startup with pre-flight checks
Auto-installs dependencies and verifies all imports
"""

import os
import sys
import time
import json
import subprocess
import importlib


class ANVELStartupWizard:
    """
    Interactive startup wizard that performs pre-flight checks
    and guides users through system initialization with automatic dependency installation
    """

    def __init__(self):
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []
        self.config = None
        self.auto_fixed = []

        # All required dependencies
        self.stdlib_modules = [
            "os",
            "sys",
            "time",
            "json",
            "threading",
            "hashlib",
            "secrets",
            "random",
            "re",
            "shutil",
            "subprocess",
            "importlib",
            "traceback",
            "glob",
            "collections",
            "statistics",
            "decimal",
            "pathlib",
            "typing",
        ]

        self.external_packages = {"numpy": "numpy>=1.24.0"}

        # All ANVEL internal modules
        self.anvel_modules = [
            "anvel_brain",
            "anvel_consciousness",
            "anvel_event_bus",
            "anvel_health_monitor",
            "anvel_heartbeat_monitor",
            "anvel_memory",
            "anvel_analytics_core",
            "anvel_guardian_ai",
            "anvel_monitoring",
            "anvel_system_orchestrator",
            "anvel_trade_engine",
            "anvel_watchdog",
            "anvel_final_architecture",
        ]

    def clear_screen(self):
        """Clear console"""
        os.system("cls" if os.name == "nt" else "clear")

    def print_header(self, title: str):
        """Print formatted header"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70 + "\n")

    def print_status(self, message: str, status: str = "info"):
        """Print status message with icon"""
        icons = {
            "success": "✓",
            "fail": "✗",
            "warning": "⚠",
            "info": "ℹ",
            "working": "⏳",
            "fixing": "🔧",
        }
        icon = icons.get(status, "•")
        print(f"{icon} {message}")

    def install_package(self, package_spec: str) -> bool:
        """
        Automatically install a Python package using pip
        Returns True if successful, False otherwise
        """
        try:
            self.print_status(f"Installing {package_spec}...", "fixing")

            # Use subprocess to call pip
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_spec, "--quiet"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                self.print_status(f"Successfully installed {package_spec}", "success")
                return True
            else:
                self.print_status(f"Failed to install {package_spec}", "fail")
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}")
                return False

        except subprocess.TimeoutExpired:
            self.print_status(f"Installation timeout for {package_spec}", "fail")
            return False
        except Exception as e:
            self.print_status(f"Installation error: {str(e)}", "fail")
            return False

    def verify_import(self, module_name: str, install_if_missing: bool = True) -> bool:
        """
        Verify that a module can be imported
        If install_if_missing is True and it's an external package, auto-install it
        Returns True if import successful, False otherwise
        """
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            # If it's an external package and we should auto-install
            if install_if_missing and module_name in self.external_packages:
                package_spec = self.external_packages[module_name]
                if self.install_package(package_spec):
                    # Try importing again after installation
                    try:
                        importlib.import_module(module_name)
                        self.auto_fixed.append(f"Installed {module_name}")
                        return True
                    except ImportError:
                        return False
                return False
            return False
        except Exception as e:
            self.print_status(f"Error importing {module_name}: {str(e)}", "fail")
            return False

    def run(self):
        """Run the complete startup wizard"""
        self.clear_screen()
        self.print_header("🚀 ANVEL Startup Wizard")

        print("""
Welcome to the ANVEL Startup Wizard!

This wizard will:
  • Check system requirements
  • Auto-install missing dependencies
  • Verify all imports and modules
  • Validate configuration
  • Test module health
  • Wire up all components
  • Perform safety checks
  • Launch ANVEL safely

Everything will be handled automatically! 🎯
        """)

        input("\nPress Enter to begin automated setup...")

        # Run all checks with auto-fixing
        self.check_python_version()
        self.check_and_install_dependencies()
        self.verify_all_imports()
        self.check_configuration()
        self.check_disk_space()
        self.check_modules()
        self.check_capital_settings()
        self.check_risk_limits()
        self.check_market_hours()
        self.check_strategies()

        # Show results
        self.show_results()

        # Launch decision
        if self.checks_failed:
            self.handle_failures()
        else:
            self.launch_system()

    def check_python_version(self):
        """Check Python version"""
        self.clear_screen()
        self.print_header("Check 1/10: Python Version")

        self.print_status("Checking Python version...", "working")
        time.sleep(0.5)

        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"

        if version.major == 3 and version.minor >= 8:
            self.print_status(f"Python {version_str} detected ✓", "success")
            self.checks_passed.append(("Python Version", version_str))
        else:
            self.print_status(f"Python {version_str} - Requires 3.8+", "fail")
            self.checks_failed.append(
                ("Python Version", f"Found {version_str}, need 3.8+")
            )

        input("\nPress Enter to continue...")

    def check_and_install_dependencies(self):
        """Check and auto-install all required dependencies"""
        self.clear_screen()
        self.print_header("Check 2/10: Dependencies & Auto-Installation")

        print("\n📦 Checking standard library modules...")
        stdlib_ok = True
        for module in self.stdlib_modules:
            try:
                importlib.import_module(module)
                print(f"  ✓ {module}")
            except ImportError:
                print(f"  ✗ {module} - MISSING (This shouldn't happen!)")
                stdlib_ok = False

        if stdlib_ok:
            self.print_status("All standard library modules available", "success")
        else:
            self.print_status("Some standard library modules missing", "warning")

        print("\n📦 Checking external packages...")
        external_ok = True
        for package, spec in self.external_packages.items():
            if self.verify_import(package, install_if_missing=True):
                print(f"  ✓ {package}")
            else:
                print(f"  ✗ {package} - Installation failed")
                external_ok = False

        if external_ok:
            self.print_status("All external packages installed", "success")
            self.checks_passed.append(("Dependencies", "All packages available"))
        else:
            self.print_status("Some packages could not be installed", "fail")
            self.checks_failed.append(("Dependencies", "Missing packages"))

        input("\nPress Enter to continue...")

    def verify_all_imports(self):
        """Verify all ANVEL internal modules can be imported"""
        self.clear_screen()
        self.print_header("Check 3/10: ANVEL Module Integration")

        print("\n🔌 Verifying ANVEL internal modules...")
        print("This ensures all components are properly wired together.\n")

        missing_modules = []
        working_modules = []

        for module in self.anvel_modules:
            try:
                # Try to import the module
                imported = importlib.import_module(module)

                # Check if it has the expected class
                class_name = "".join(word.capitalize() for word in module.split("_"))
                if hasattr(imported, class_name):
                    print(f"  ✓ {module} → {class_name}")
                    working_modules.append(module)
                else:
                    print(f"  ⚠ {module} imported but class {class_name} not found")
                    working_modules.append(module)

            except ImportError as e:
                print(f"  ✗ {module} - Import failed")
                missing_modules.append((module, str(e)))
            except Exception as e:
                print(f"  ⚠ {module} - {str(e)[:50]}")

        print(
            f"\n📊 Results: {len(working_modules)}/{len(self.anvel_modules)} modules verified"
        )

        if missing_modules:
            self.print_status(f"{len(missing_modules)} modules have issues", "warning")
            self.warnings.append(
                ("Module Integration", f"{len(missing_modules)} modules unavailable")
            )

            print("\n⚠ Missing modules:")
            for mod, err in missing_modules:
                print(f"  • {mod}")
        else:
            self.print_status("All ANVEL modules properly integrated!", "success")
            self.checks_passed.append(
                ("Module Integration", f"{len(working_modules)} modules ready")
            )

        input("\nPress Enter to continue...")

    def check_configuration(self):
        """Check configuration file"""
        self.clear_screen()
        self.print_header("Check 4/10: Configuration")

        self.print_status("Looking for configuration file...", "working")
        time.sleep(0.3)

        if not os.path.exists("anvel_config.json"):
            self.print_status("No configuration file found", "fail")
            self.checks_failed.append(("Configuration", "anvel_config.json not found"))
            print("\n💡 Run: python anvel_onboarding_wizard.py to create configuration")
            input("\nPress Enter to continue...")
            return

        self.print_status("Configuration file found ✓", "success")

        # Load and validate
        try:
            with open("anvel_config.json", "r") as f:
                self.config = json.load(f)

            self.print_status("Configuration loaded successfully ✓", "success")

            # Validate required fields
            required_fields = ["user_profile", "trading_config", "setup_completed"]
            missing = [f for f in required_fields if f not in self.config]

            if missing:
                self.print_status(f"Missing fields: {', '.join(missing)}", "fail")
                self.checks_failed.append(("Configuration", f"Missing: {missing}"))
            else:
                self.print_status("All required fields present ✓", "success")
                self.checks_passed.append(("Configuration", "Valid"))

                # Show summary
                print("\n📋 Configuration Summary:")
                trading_config = self.config.get("trading_config", {})
                print(f"   Mode: {trading_config.get('trading_mode', 'Unknown')}")
                print(f"   Market: {trading_config.get('market_type', 'Unknown')}")
                print(f"   Strategies: {len(trading_config.get('strategies', []))}")

        except json.JSONDecodeError:
            self.print_status("Configuration file corrupted", "fail")
            self.checks_failed.append(("Configuration", "Invalid JSON"))
        except Exception as e:
            self.print_status(f"Error reading configuration: {e}", "fail")
            self.checks_failed.append(("Configuration", str(e)))

        input("\nPress Enter to continue...")

    def check_disk_space(self):
        """Check available disk space"""
        self.clear_screen()
        self.print_header("Check 5/10: Disk Space")

        self.print_status("Checking disk space...", "working")
        time.sleep(0.3)

        try:
            import shutil

            total, used, free = shutil.disk_usage(".")
            free_gb = free // (2**30)

            if free_gb > 1:
                self.print_status(f"{free_gb} GB free ✓", "success")
                self.checks_passed.append(("Disk Space", f"{free_gb} GB available"))
            else:
                self.print_status(f"Only {free_gb} GB free", "warning")
                self.warnings.append(f"Low disk space: {free_gb} GB")
        except (OSError, AttributeError) as e:
            self.print_status(f"Could not check disk space: {e}", "warning")
            self.warnings.append("Disk space check skipped")

        input("\nPress Enter to continue...")

    def check_modules(self):
        """Check ANVEL modules"""
        self.clear_screen()
        self.print_header("Check 6/10: ANVEL Modules")

        critical_modules = [
            "anvel_brain",
            "anvel_memory",
            "anvel_event_bus",
            "anvel_trade_engine",
            "anvel_strategy_core",
            "anvel_guardian_ai",
            "anvel_watchdog",
            "anvel_system_orchestrator",
        ]

        print("Checking critical modules...")
        failed_imports = []

        for module in critical_modules:
            try:
                __import__(module)
                self.print_status(f"{module}.py ✓", "success")
            except ImportError:
                self.print_status(f"{module}.py missing", "fail")
                failed_imports.append(module)
                self.checks_failed.append(("Module", f"{module} not found"))

        if not failed_imports:
            self.checks_passed.append(("Modules", "All critical modules present"))

        input("\nPress Enter to continue...")

    def check_capital_settings(self):
        """Check capital and position sizing"""
        self.clear_screen()
        self.print_header("Check 7/10: Capital Settings")

        if not self.config:
            self.print_status("No configuration to check", "warning")
            input("\nPress Enter to continue...")
            return

        trading_config = self.config.get("trading_config", {})

        max_position = trading_config.get("max_position_size", 0)
        self.print_status(f"Max position size: ${max_position}", "info")

        if max_position == 0:
            self.print_status("Position size not set", "warning")
            self.warnings.append("Position size is 0 - may need configuration")
        elif max_position > 10000:
            self.print_status(f"Large position size: ${max_position}", "warning")
            self.warnings.append(f"Position size ${max_position} is quite large")
        else:
            self.print_status("Position size looks reasonable ✓", "success")
            self.checks_passed.append(("Capital", f"${max_position} per trade"))

        input("\nPress Enter to continue...")

    def check_risk_limits(self):
        """Check risk management settings"""
        self.clear_screen()
        self.print_header("Check 8/10: Risk Management")

        if not self.config:
            self.print_status("No configuration to check", "warning")
            input("\nPress Enter to continue...")
            return

        trading_config = self.config.get("trading_config", {})

        stop_loss = trading_config.get("stop_loss_percent", 0)
        take_profit = trading_config.get("take_profit_percent", 0)
        daily_limit = trading_config.get("daily_loss_limit", 0)

        print("📊 Risk Settings:")
        self.print_status(f"Stop Loss: {stop_loss}%", "info")
        self.print_status(f"Take Profit: {take_profit}%", "info")
        self.print_status(f"Daily Loss Limit: {daily_limit}%", "info")

        issues = []
        if stop_loss == 0:
            issues.append("No stop loss set")
            self.print_status("⚠️  No stop loss - HIGH RISK!", "warning")

        if daily_limit == 0:
            issues.append("No daily loss limit")
            self.print_status("⚠️  No daily loss limit", "warning")

        if issues:
            self.warnings.extend(issues)
            self.print_status("\n💡 Consider adding risk limits for safety", "warning")
        else:
            self.checks_passed.append(("Risk Management", "Limits configured"))
            self.print_status("\n✓ Risk management configured", "success")

        input("\nPress Enter to continue...")

    def check_market_hours(self):
        """Check if within market hours"""
        self.clear_screen()
        self.print_header("Check 9/10: Market Hours")

        if not self.config:
            self.print_status("No configuration to check", "warning")
            input("\nPress Enter to continue...")
            return

        trading_config = self.config.get("trading_config", {})
        market_type = trading_config.get("market_type", "unknown")
        trading_schedule = trading_config.get("trading_schedule", "market_hours")

        import datetime

        now = datetime.datetime.now()
        hour = now.hour
        weekday = now.weekday()

        self.print_status(f"Current time: {now.strftime('%H:%M %A')}", "info")
        self.print_status(f"Market: {market_type}", "info")
        self.print_status(f"Schedule: {trading_schedule}", "info")

        if market_type == "stocks" and trading_schedule == "market_hours":
            # US market hours: 9:30 AM - 4:00 PM ET (weekdays)
            if weekday >= 5:  # Weekend
                self.print_status("⚠️  Market is closed (weekend)", "warning")
                self.warnings.append("Markets closed - weekend")
            elif hour < 9 or hour >= 16:
                self.print_status("⚠️  Outside market hours", "warning")
                self.warnings.append("Outside regular market hours")
            else:
                self.print_status("✓ Within market hours", "success")
                self.checks_passed.append(("Market Hours", "Open"))
        elif market_type == "crypto":
            self.print_status("✓ Crypto markets always open", "success")
            self.checks_passed.append(("Market Hours", "24/7"))
        else:
            self.print_status("Market hours check skipped", "info")

        input("\nPress Enter to continue...")

    def check_strategies(self):
        """Check configured strategies"""
        self.clear_screen()
        self.print_header("Check 10/10: Trading Strategies")

        if not self.config:
            self.print_status("No configuration to check", "warning")
            input("\nPress Enter to continue...")
            return

        trading_config = self.config.get("trading_config", {})
        strategies = trading_config.get("strategies", [])

        if not strategies:
            self.print_status("No strategies configured", "fail")
            self.checks_failed.append(("Strategies", "None configured"))
        else:
            print(f"📊 Configured Strategies ({len(strategies)}):")
            for strategy in strategies:
                self.print_status(f"  • {strategy}", "info")

            self.print_status(f"\n✓ {len(strategies)} strategies ready", "success")
            self.checks_passed.append(("Strategies", f"{len(strategies)} configured"))

        input("\nPress Enter to see results...")

    def show_results(self):
        """Show final results"""
        self.clear_screen()
        self.print_header("Pre-Flight Check Results")

        print(f"✅ Checks Passed: {len(self.checks_passed)}")
        for check, detail in self.checks_passed:
            print(f"   ✓ {check}: {detail}")

        if self.auto_fixed:
            print(f"\n🔧 Auto-Fixed Issues: {len(self.auto_fixed)}")
            for fix in self.auto_fixed:
                print(f"   🔧 {fix}")

        if self.warnings:
            print(f"\n⚠️  Warnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"   ⚠ {warning}")

        if self.checks_failed:
            print(f"\n❌ Checks Failed: {len(self.checks_failed)}")
            for check, detail in self.checks_failed:
                print(f"   ✗ {check}: {detail}")

        print("\n" + "=" * 70)

    def handle_failures(self):
        """Handle failed checks"""
        print("\n⚠️  Some checks failed. ANVEL may not start correctly.\n")

        print("Recommendations:")
        for check, detail in self.checks_failed:
            if "Configuration" in check:
                print("  • Run: python anvel_onboarding_wizard.py")
            elif "Dependency" in check:
                print(f"  • Install: pip install {detail.split(':')[1].strip()}")
            elif "Module" in check:
                print("  • Verify all ANVEL files are present")

        print("\n" + "=" * 70)
        response = input("\nAttempt to launch anyway? (y/N): ").strip().lower()

        if response == "y":
            self.launch_system()
        else:
            print("\n👋 Startup cancelled. Fix issues and try again.")
            sys.exit(1)

    def launch_system(self):
        """Launch ANVEL"""
        print("\n" + "=" * 70)
        print("🚀 ALL SYSTEMS GO!")
        print("=" * 70)

        if self.warnings:
            print(f"\n⚠️  Note: {len(self.warnings)} warnings present (non-critical)")

        print("\n✨ Starting ANVEL Omega...")
        print("\n💡 Tips:")
        print("   • Monitor console output")
        print("   • Check logs/ directory")
        print("   • Press Ctrl+C to stop")
        print("   • Use runtime wizard for live control")

        response = input("\nLaunch now? (Y/n): ").strip().lower()

        if response in ["", "y", "yes"]:
            print("\n🚀 Launching...\n")
            time.sleep(1)
            import subprocess

            subprocess.run(["python", "launch_anel.py"])
        else:
            print("\n👋 Launch cancelled.")


def main():
    """Main entry point"""
    wizard = ANVELStartupWizard()
    try:
        wizard.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Startup wizard interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error in startup wizard: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
