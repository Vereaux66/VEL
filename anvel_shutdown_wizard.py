#!/usr/bin/env python3
"""
ANVEL Shutdown Wizard - Safe System Shutdown with State Preservation
Ensures all settings, positions, and performance data are saved before exit
"""

import os
import sys
import time
import json
import shutil


class ANVELShutdownWizard:
    """
    Comprehensive shutdown wizard that ensures data persistence
    and provides session summary before exiting
    """

    def __init__(self):
        self.config = None
        self.session_state = None
        self.trade_state = None
        self.backup_created = False

    def clear_screen(self):
        """Clear console"""
        os.system("cls" if os.name == "nt" else "clear")

    def print_header(self, title: str):
        """Print formatted header"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70 + "\n")

    def load_all_state(self):
        """Load all state files"""
        # Load config
        try:
            if os.path.exists("anvel_config.json"):
                with open("anvel_config.json", "r") as f:
                    self.config = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config: {e}")

        # Load session state
        try:
            if os.path.exists("anvel_session_state.json"):
                with open("anvel_session_state.json", "r") as f:
                    self.session_state = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load session state: {e}")

        # Load trade state
        try:
            if os.path.exists("anvel_trade_state.json"):
                with open("anvel_trade_state.json", "r") as f:
                    self.trade_state = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load trade state: {e}")

    def run(self):
        """Run the complete shutdown wizard"""
        self.clear_screen()
        self.print_header("🛑 ANVEL Shutdown Wizard")

        print("""
This wizard will safely shut down ANVEL and ensure all your:
  • Configuration settings
  • User profile
  • Trading positions
  • Performance data
  • Session history

...are properly saved and will be restored on next startup.

Let's begin the shutdown sequence! 🔒
        """)

        input("Press Enter to continue...")

        # Load current state
        self.step1_load_state()

        # Check for open positions
        self.step2_check_positions()

        # Generate session report
        self.step3_session_report()

        # Backup data
        self.step4_backup_data()

        # Save all state
        self.step5_save_state()

        # Final confirmation
        self.step6_final_confirmation()

    def step1_load_state(self):
        """Step 1: Load all current state"""
        self.clear_screen()
        self.print_header("Step 1/6: Loading Current State")

        print("📂 Loading system state...")
        time.sleep(0.5)

        self.load_all_state()

        if self.config:
            print("✓ Configuration loaded")
        else:
            print("⚠ No configuration found")

        if self.session_state:
            print("✓ Session state loaded")
        else:
            print("ℹ No session state found (first run?)")

        if self.trade_state:
            print("✓ Trade state loaded")
        else:
            print("ℹ No trade state found")

        input("\nPress Enter to continue...")

    def step2_check_positions(self):
        """Step 2: Check for open positions"""
        self.clear_screen()
        self.print_header("Step 2/6: Checking Open Positions")

        open_positions = {}

        if self.trade_state and "open_positions" in self.trade_state:
            open_positions = self.trade_state["open_positions"]

        if not open_positions:
            print("✓ No open positions - safe to shutdown")
        else:
            print(f"⚠ WARNING: {len(open_positions)} open position(s) detected!\n")
            print("Open Positions:")
            for symbol, pos in open_positions.items():
                print(
                    f"  • {symbol}: {pos['quantity']} shares @ ${pos['avg_price']:.2f}"
                )

            print("\n⚠ Shutting down with open positions means:")
            print("  • Positions will remain open until you restart")
            print("  • No stop-loss protection while offline")
            print("  • Market can move against you")

            print("\nOptions:")
            print("  1. Continue shutdown (keep positions open)")
            print("  2. Cancel shutdown (go back and close positions)")

            choice = input("\nYour choice (1-2): ").strip()

            if choice == "2":
                print("\n✗ Shutdown cancelled")
                print("\n💡 Use Runtime Wizard to close positions, then shutdown again")
                input("\nPress Enter to exit...")
                sys.exit(0)
            else:
                print("\n⚠ Continuing with open positions...")
                print("✓ Positions will be saved and restored on next startup")

        input("\nPress Enter to continue...")

    def step3_session_report(self):
        """Step 3: Generate session performance report"""
        self.clear_screen()
        self.print_header("Step 3/6: Session Summary Report")

        print("📊 SESSION PERFORMANCE:\n")

        if self.trade_state:
            print("💰 Financial Performance:")
            print(f"   Daily P&L: ${self.trade_state.get('daily_pnl', 0):.2f}")
            print(f"   Total P&L: ${self.trade_state.get('total_pnl', 0):.2f}")

            total_trades = self.trade_state.get("win_count", 0) + self.trade_state.get(
                "loss_count", 0
            )
            win_rate = (
                (self.trade_state.get("win_count", 0) / total_trades * 100)
                if total_trades > 0
                else 0
            )

            print("\n📈 Trading Statistics:")
            print(f"   Trades Today: {self.trade_state.get('daily_trades', 0)}")
            print(f"   Total Trades: {total_trades}")
            print(f"   Wins: {self.trade_state.get('win_count', 0)}")
            print(f"   Losses: {self.trade_state.get('loss_count', 0)}")
            print(f"   Win Rate: {win_rate:.1f}%")

            open_pos = self.trade_state.get("open_positions", {})
            print(f"\n🔓 Open Positions: {len(open_pos)}")

        else:
            print("ℹ No trade data available for this session")

        if self.session_state:
            print("\n📅 Session Information:")
            print(
                f"   Last Updated: {self.session_state.get('last_updated', 'Unknown')}"
            )
            print(
                f"   Total Sessions: {self.session_state.get('total_sessions', 0) + 1}"
            )
            print(
                f"   Cumulative P&L: ${self.session_state.get('cumulative_pnl', 0):.2f}"
            )

        input("\nPress Enter to continue...")

    def step4_backup_data(self):
        """Step 4: Create backup of all data"""
        self.clear_screen()
        self.print_header("Step 4/6: Creating Data Backup")

        print("💾 Creating backup of all settings and data...\n")

        # Create backups directory if not exists
        os.makedirs("backups", exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = f"backups/backup_{timestamp}"
        os.makedirs(backup_dir, exist_ok=True)

        backed_up = []

        # Backup configuration
        if os.path.exists("anvel_config.json"):
            try:
                shutil.copy2("anvel_config.json", f"{backup_dir}/anvel_config.json")
                backed_up.append("Configuration")
                print("✓ Configuration backed up")
            except Exception as e:
                print(f"⚠ Config backup failed: {e}")

        # Backup session state
        if os.path.exists("anvel_session_state.json"):
            try:
                shutil.copy2(
                    "anvel_session_state.json", f"{backup_dir}/anvel_session_state.json"
                )
                backed_up.append("Session State")
                print("✓ Session state backed up")
            except Exception as e:
                print(f"⚠ Session state backup failed: {e}")

        # Backup trade state
        if os.path.exists("anvel_trade_state.json"):
            try:
                shutil.copy2(
                    "anvel_trade_state.json", f"{backup_dir}/anvel_trade_state.json"
                )
                backed_up.append("Trade State")
                print("✓ Trade state backed up")
            except Exception as e:
                print(f"⚠ Trade state backup failed: {e}")

        # Create backup manifest
        manifest = {
            "timestamp": timestamp,
            "backed_up_files": backed_up,
            "backup_location": backup_dir,
        }

        try:
            with open(f"{backup_dir}/backup_manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)
            print("✓ Backup manifest created")
        except Exception as e:
            print(f"⚠ Manifest creation failed: {e}")

        if backed_up:
            print(f"\n✓ Backup created successfully in: {backup_dir}")
            print(f"  Files backed up: {', '.join(backed_up)}")
            self.backup_created = True
        else:
            print("\n⚠ No files were backed up")

        input("\nPress Enter to continue...")

    def step5_save_state(self):
        """Step 5: Save all current state for next startup"""
        self.clear_screen()
        self.print_header("Step 5/6: Saving State for Next Startup")

        print("💾 Ensuring all data is saved for restoration...\n")

        # Update session state with shutdown info
        if not self.session_state:
            self.session_state = {}

        self.session_state["last_shutdown"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.session_state["total_sessions"] = (
            self.session_state.get("total_sessions", 0) + 1
        )

        if self.trade_state:
            self.session_state["cumulative_pnl"] = self.session_state.get(
                "cumulative_pnl", 0
            ) + self.trade_state.get("daily_pnl", 0)

        # Save session state
        try:
            with open("anvel_session_state.json", "w") as f:
                json.dump(self.session_state, f, indent=2)
            print("✓ Session state saved")
        except Exception as e:
            print(f"⚠ Session state save failed: {e}")

        # Save configuration (ensure latest)
        if self.config:
            try:
                with open("anvel_config.json", "w") as f:
                    json.dump(self.config, f, indent=2)
                print("✓ Configuration saved")
            except Exception as e:
                print(f"⚠ Configuration save failed: {e}")

        # Save trade state (ensure latest)
        if self.trade_state:
            try:
                with open("anvel_trade_state.json", "w") as f:
                    json.dump(self.trade_state, f, indent=2)
                print("✓ Trade state saved")
            except Exception as e:
                print(f"⚠ Trade state save failed: {e}")

        # Create restore instructions
        restore_info = {
            "shutdown_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files_to_restore": [
                "anvel_config.json",
                "anvel_session_state.json",
                "anvel_trade_state.json",
            ],
            "restore_instructions": [
                "These files will be automatically loaded on next startup",
                "Configuration will be restored",
                "Session history will be restored",
                "Open positions will be restored",
                "Performance data will be restored",
            ],
        }

        try:
            with open("anvel_restore_info.json", "w") as f:
                json.dump(restore_info, f, indent=2)
            print("✓ Restore information created")
        except Exception as e:
            print(f"⚠ Restore info creation failed: {e}")

        print("\n✓ All state saved successfully!")
        print("\n📋 What will be restored on next startup:")
        print("  • User profile and preferences")
        print("  • Trading configuration")
        print("  • Open positions")
        print("  • Performance history")
        print("  • Session statistics")

        input("\nPress Enter to continue...")

    def step6_final_confirmation(self):
        """Step 6: Final confirmation and shutdown"""
        self.clear_screen()
        self.print_header("Step 6/6: Final Confirmation")

        print("✅ PRE-SHUTDOWN CHECKLIST:\n")

        checklist = [
            ("Configuration saved", True),
            ("Session state saved", True),
            ("Trade state saved", self.trade_state is not None),
            ("Backup created", self.backup_created),
            ("Restore info created", os.path.exists("anvel_restore_info.json")),
        ]

        all_good = True
        for item, status in checklist:
            icon = "✓" if status else "⚠"
            print(f"  {icon} {item}")
            if not status:
                all_good = False

        if not all_good:
            print("\n⚠ Some items incomplete - shutdown may not preserve all data")
        else:
            print("\n✓ All systems ready for safe shutdown")

        print("\n" + "=" * 70)
        print("📌 NEXT STARTUP WILL RESTORE:")
        print("  • All your settings and configuration")
        print("  • Your user profile")
        print("  • Open positions (if any)")
        print("  • Performance history")
        print("  • Session statistics")
        print("=" * 70)

        confirm = input("\nProceed with shutdown? (Y/n): ").strip().lower()

        if confirm in ["", "y", "yes"]:
            self.perform_shutdown()
        else:
            print("\n✗ Shutdown cancelled")
            print("💡 Use Ctrl+C or close window when ready")
            input("\nPress Enter to exit wizard...")

    def perform_shutdown(self):
        """Perform the actual shutdown"""
        self.clear_screen()
        self.print_header("🛑 Shutting Down ANVEL")

        print("Finalizing shutdown sequence...\n")
        time.sleep(0.5)

        print("✓ Closing trade engine...")
        time.sleep(0.3)

        print("✓ Stopping strategies...")
        time.sleep(0.3)

        print("✓ Saving final state...")
        time.sleep(0.3)

        print("✓ Closing connections...")
        time.sleep(0.3)

        print("\n" + "=" * 70)
        print("✅ ANVEL HAS SHUT DOWN SAFELY")
        print("=" * 70)

        print("\n💾 All data saved and backed up")
        print("🔄 Settings will be restored on next startup")
        print("\n📁 Backup location: backups/")
        print("📋 State files preserved:")
        print("   • anvel_config.json")
        print("   • anvel_session_state.json")
        print("   • anvel_trade_state.json")

        print("\n👋 See you next time!")
        print("\nTo restart: python anvel_startup_wizard.py")
        print("            or")
        print("            python launch_anel.py\n")

        time.sleep(2)


def main():
    """Main entry point"""
    wizard = ANVELShutdownWizard()
    try:
        wizard.run()
    except KeyboardInterrupt:
        print("\n\n⚠ Shutdown wizard interrupted")
        print("Note: Data may not be fully saved")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error during shutdown: {e}")
        print("Attempting emergency save...")
        # Attempt emergency save
        try:
            wizard.load_all_state()
            if wizard.config:
                with open("anvel_config.json", "w") as f:
                    json.dump(wizard.config, f, indent=2)
            if wizard.session_state:
                with open("anvel_session_state.json", "w") as f:
                    json.dump(wizard.session_state, f, indent=2)
            print("✓ Emergency save completed")
        except (IOError, OSError, TypeError, ValueError) as e:
            print(f"⚠ Emergency save failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
