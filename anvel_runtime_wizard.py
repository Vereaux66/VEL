#!/usr/bin/env python3
"""
DEPRECATED: Use START_ANVEL.py --monitor instead
================================================
This file is deprecated and will be removed in a future release.

New usage:
    python START_ANVEL.py --monitor   # Runtime monitoring

---

ANVEL Runtime Wizard - Live System Monitoring & Control
Interactive dashboard for monitoring ANVEL while it's running
"""

import os
import sys
import time
import json


class ANVELRuntimeWizard:
    """
    Interactive runtime control panel for ANVEL
    Monitors live performance and provides real-time controls
    """

    def __init__(self):
        self.running = True
        self.trade_engine = None
        self.strategy_core = None
        self.brain = None
        self.orchestrator = None
        self.config = None
        self.session_state = {}

        # Load configuration and session state
        self.load_config()
        self.load_session_state()

    def load_config(self):
        """Load current configuration"""
        try:
            if os.path.exists("anvel_config.json"):
                with open("anvel_config.json", "r") as f:
                    self.config = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            self.config = {}

    def load_session_state(self):
        """Load previous session state if exists"""
        try:
            if os.path.exists("anvel_session_state.json"):
                with open("anvel_session_state.json", "r") as f:
                    self.session_state = json.load(f)
                print("✓ Previous session state loaded")
        except Exception as e:
            print(f"Note: No previous session state: {e}")
            self.session_state = {
                "last_shutdown": None,
                "total_sessions": 0,
                "cumulative_pnl": 0.0,
            }

    def save_session_state(self):
        """Save current session state"""
        try:
            self.session_state["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open("anvel_session_state.json", "w") as f:
                json.dump(self.session_state, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving session state: {e}")
            return False

    def clear_screen(self):
        """Clear console"""
        os.system("cls" if os.name == "nt" else "clear")

    def print_header(self, title: str):
        """Print formatted header"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70 + "\n")

    def connect_to_system(self):
        """Connect to running ANVEL modules"""
        try:
            # Try to import and get references to running modules
            from anvel_trade_engine import ANVELTradeEngine
            from anvel_strategy_core import ANVELStrategyCore
            from anvel_brain import ANVELBrain

            # In a real scenario, these would be singleton instances
            # For now, we'll create new instances to demonstrate
            self.trade_engine = ANVELTradeEngine()
            self.strategy_core = ANVELStrategyCore()
            self.brain = ANVELBrain()

            return True
        except Exception as e:
            print(f"Warning: Could not connect to all modules: {e}")
            return False

    def run(self):
        """Main runtime wizard loop"""
        self.clear_screen()
        self.print_header("🎮 ANVEL Runtime Control Panel")

        print("Connecting to ANVEL system...")
        if self.connect_to_system():
            print("✓ Connected to ANVEL modules\n")
        else:
            print("⚠ Running in limited mode\n")

        while self.running:
            self.show_dashboard()
            self.show_menu()
            choice = input("\nSelect option (1-10): ").strip()
            self.handle_choice(choice)

    def show_dashboard(self):
        """Display real-time dashboard"""
        self.clear_screen()
        self.print_header("📊 ANVEL Live Dashboard")

        # System Status
        print("🔧 SYSTEM STATUS:")
        print(
            f"   Trading: {'🟢 ACTIVE' if self.trade_engine and self.trade_engine.active else '🔴 HALTED'}"
        )
        print(f"   Time: {time.strftime('%H:%M:%S %Y-%m-%d')}")

        # Performance Metrics
        if self.trade_engine:
            stats = self.trade_engine.get_performance_stats()
            print("\n💰 PERFORMANCE:")
            print(f"   Daily P&L: ${stats['daily_pnl']:.2f}")
            print(f"   Total P&L: ${stats['total_pnl']:.2f}")
            print(f"   Win Rate: {stats['win_rate']:.1f}%")
            print(f"   Trades Today: {stats['daily_trades']}")
            print(f"   Total Trades: {stats['total_trades']}")

            # Position Summary
            positions = self.trade_engine.get_position_summary()
            print("\n📈 POSITIONS:")
            print(f"   Open Positions: {positions['total_positions']}")
            print(f"   Total Value: ${positions['total_value']:.2f}")
            print(f"   Unrealized P&L: ${positions['unrealized_pnl']:.2f}")

            if positions["positions"]:
                print("\n   Active Positions:")
                for pos in positions["positions"][:5]:  # Show top 5
                    pnl_color = "🟢" if pos["unrealized_pnl"] > 0 else "🔴"
                    print(
                        f"   {pnl_color} {pos['symbol']}: {pos['quantity']} @ ${pos['avg_price']:.2f} (P&L: ${pos['unrealized_pnl']:.2f})"
                    )

        # Strategy Performance
        if self.strategy_core:
            print("\n📊 STRATEGY PERFORMANCE:")
            perf_report = self.strategy_core.get_performance_report()
            if perf_report:
                for name, metrics in list(perf_report.items())[:3]:  # Top 3
                    print(
                        f"   • {name}: Win Rate {metrics['win_rate'] * 100:.1f}% | Weight {metrics['current_weight']:.2f}"
                    )

        # Recent Activity
        if self.trade_engine:
            print("\n📝 RECENT TRADES:")
            recent = self.trade_engine.history(3)
            if (
                recent
                and isinstance(recent, list)
                and recent[0] != "[TRADE ENGINE] No history"
            ):
                for trade in recent:
                    if isinstance(trade, dict):
                        side_icon = "🟢" if trade["side"] == "buy" else "🔴"
                        pnl_str = (
                            f" P&L: ${trade.get('pnl', 0):.2f}"
                            if "pnl" in trade
                            else ""
                        )
                        print(
                            f"   {side_icon} {trade['side'].upper()} {trade['quantity']} {trade['symbol']}{pnl_str}"
                        )

        print("\n" + "=" * 70)

    def show_menu(self):
        """Display control menu"""
        print("\n🎮 CONTROLS:")
        print("  1. Pause/Resume Trading")
        print("  2. Close All Positions")
        print("  3. Close Specific Position")
        print("  4. Adjust Risk Limits")
        print("  5. View Detailed Logs")
        print("  6. Strategy Performance Report")
        print("  7. Export Session Data")
        print("  8. Force Save State")
        print("  9. Emergency Stop")
        print("  10. Exit Runtime Wizard")

    def handle_choice(self, choice: str):
        """Handle user menu choice"""
        if choice == "1":
            self.toggle_trading()
        elif choice == "2":
            self.close_all_positions()
        elif choice == "3":
            self.close_specific_position()
        elif choice == "4":
            self.adjust_risk_limits()
        elif choice == "5":
            self.view_logs()
        elif choice == "6":
            self.strategy_report()
        elif choice == "7":
            self.export_session_data()
        elif choice == "8":
            self.force_save_state()
        elif choice == "9":
            self.emergency_stop()
        elif choice == "10":
            self.exit_wizard()
        else:
            print("\n⚠ Invalid option")
            time.sleep(1)

    def toggle_trading(self):
        """Pause or resume trading"""
        if not self.trade_engine:
            print("\n⚠ Trade engine not connected")
            input("\nPress Enter to continue...")
            return

        current = self.trade_engine.active
        self.trade_engine.toggle(not current)
        status = "RESUMED" if not current else "PAUSED"

        print(f"\n✓ Trading {status}")

        # Save state
        self.session_state["trading_active"] = not current
        self.save_session_state()

        input("\nPress Enter to continue...")

    def close_all_positions(self):
        """Close all open positions"""
        if not self.trade_engine:
            print("\n⚠ Trade engine not connected")
            input("\nPress Enter to continue...")
            return

        positions = self.trade_engine.get_open_positions()

        if not positions:
            print("\n✓ No open positions to close")
            input("\nPress Enter to continue...")
            return

        print(f"\n⚠ About to close {len(positions)} positions!")
        confirm = input("Type 'CONFIRM' to proceed: ").strip()

        if confirm == "CONFIRM":
            for symbol, pos in positions.items():
                result = self.trade_engine.queue_trade(
                    symbol=symbol,
                    side="sell",
                    quantity=pos["quantity"],
                    strategy="manual_close",
                    order_type="market",
                )
                print(f"  {result}")

            print(f"\n✓ Queued close orders for {len(positions)} positions")
            self.save_session_state()
        else:
            print("\n✗ Cancelled")

        input("\nPress Enter to continue...")

    def close_specific_position(self):
        """Close a specific position"""
        if not self.trade_engine:
            print("\n⚠ Trade engine not connected")
            input("\nPress Enter to continue...")
            return

        positions = self.trade_engine.get_open_positions()

        if not positions:
            print("\n✓ No open positions")
            input("\nPress Enter to continue...")
            return

        print("\nOpen Positions:")
        symbols = list(positions.keys())
        for i, (symbol, pos) in enumerate(positions.items(), 1):
            print(f"  {i}. {symbol}: {pos['quantity']} @ ${pos['avg_price']:.2f}")

        try:
            choice = int(input("\nSelect position to close (number): ").strip())
            if 1 <= choice <= len(symbols):
                symbol = symbols[choice - 1]
                pos = positions[symbol]

                result = self.trade_engine.queue_trade(
                    symbol=symbol,
                    side="sell",
                    quantity=pos["quantity"],
                    strategy="manual_close",
                    order_type="market",
                )
                print(f"\n✓ {result}")
                self.save_session_state()
            else:
                print("\n⚠ Invalid choice")
        except ValueError:
            print("\n⚠ Invalid input")

        input("\nPress Enter to continue...")

    def adjust_risk_limits(self):
        """Adjust risk management limits"""
        if not self.trade_engine:
            print("\n⚠ Trade engine not connected")
            input("\nPress Enter to continue...")
            return

        print("\nCurrent Risk Limits:")
        print(f"  Max Position Size: ${self.trade_engine.max_position_size:.2f}")
        print(f"  Daily Loss Limit: ${self.trade_engine.daily_loss_limit:.2f}")
        print(f"  Max Positions: {self.trade_engine.max_positions}")
        print(f"  Max Daily Trades: {self.trade_engine.max_daily_trades}")

        print("\nAdjust (leave blank to keep current):")

        try:
            max_pos = input(
                f"  Max Position Size [${self.trade_engine.max_position_size}]: "
            ).strip()
            daily_loss = input(
                f"  Daily Loss Limit [${self.trade_engine.daily_loss_limit}]: "
            ).strip()
            max_positions = input(
                f"  Max Positions [{self.trade_engine.max_positions}]: "
            ).strip()
            max_trades = input(
                f"  Max Daily Trades [{self.trade_engine.max_daily_trades}]: "
            ).strip()

            self.trade_engine.set_risk_limits(
                max_position_size=float(max_pos) if max_pos else None,
                daily_loss_limit=float(daily_loss) if daily_loss else None,
                max_positions=int(max_positions) if max_positions else None,
                max_daily_trades=int(max_trades) if max_trades else None,
            )

            print("\n✓ Risk limits updated")

            # Save to config
            if self.config:
                self.config["trading_config"][
                    "max_position_size"
                ] = self.trade_engine.max_position_size
                self.config["trading_config"][
                    "daily_loss_limit"
                ] = self.trade_engine.daily_loss_limit
                with open("anvel_config.json", "w") as f:
                    json.dump(self.config, f, indent=2)
                print("✓ Configuration saved")

        except ValueError:
            print("\n⚠ Invalid input")

        input("\nPress Enter to continue...")

    def view_logs(self):
        """View recent log entries"""
        print("\n📝 Recent Activity:")

        if self.trade_engine:
            print("\n🔹 Trade History:")
            history = self.trade_engine.history(10)
            for trade in history:
                if isinstance(trade, dict):
                    print(
                        f"  {trade.get('exec_time_str', 'N/A')}: {trade['side'].upper()} {trade['quantity']} {trade['symbol']}"
                    )

        if self.strategy_core:
            print("\n🔹 Strategy Log:")
            log = self.strategy_core.log(10)
            for entry in log:
                if isinstance(entry, tuple):
                    print(f"  {entry[0]}: Score {entry[1]:.2f}")

        input("\nPress Enter to continue...")

    def strategy_report(self):
        """Show detailed strategy performance"""
        if not self.strategy_core:
            print("\n⚠ Strategy core not connected")
            input("\nPress Enter to continue...")
            return

        print("\n📊 Strategy Performance Report:")
        print("=" * 70)

        perf = self.strategy_core.get_performance_report()

        if not perf:
            print("No performance data available yet")
        else:
            for name, metrics in perf.items():
                print(f"\n{name}:")
                print(f"  Win Rate: {metrics['win_rate'] * 100:.1f}%")
                print(f"  Total Signals: {metrics['total_signals']}")
                print(f"  Current Weight: {metrics['current_weight']:.2f}")
                print(f"  Avg Score: {metrics['avg_score']:.3f}")

        input("\nPress Enter to continue...")

    def export_session_data(self):
        """Export session data to file"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"anvel_session_export_{timestamp}.json"

        export_data = {
            "timestamp": timestamp,
            "config": self.config,
            "session_state": self.session_state,
            "performance": (
                self.trade_engine.get_performance_stats() if self.trade_engine else {}
            ),
            "positions": (
                self.trade_engine.get_position_summary() if self.trade_engine else {}
            ),
            "strategy_performance": (
                self.strategy_core.get_performance_report()
                if self.strategy_core
                else {}
            ),
        }

        try:
            with open(filename, "w") as f:
                json.dump(export_data, f, indent=2)
            print(f"\n✓ Session data exported to {filename}")
        except Exception as e:
            print(f"\n⚠ Export failed: {e}")

        input("\nPress Enter to continue...")

    def force_save_state(self):
        """Force save current state"""
        print("\n💾 Saving current state...")

        # Save session state
        if self.save_session_state():
            print("✓ Session state saved")

        # Save configuration
        if self.config:
            try:
                with open("anvel_config.json", "w") as f:
                    json.dump(self.config, f, indent=2)
                print("✓ Configuration saved")
            except Exception as e:
                print(f"⚠ Config save failed: {e}")

        # Save trade engine state if possible
        if self.trade_engine:
            try:
                state = {
                    "daily_pnl": self.trade_engine.daily_pnl,
                    "total_pnl": self.trade_engine.total_pnl,
                    "daily_trades": self.trade_engine.daily_trades,
                    "win_count": self.trade_engine.win_count,
                    "loss_count": self.trade_engine.loss_count,
                    "open_positions": self.trade_engine.get_open_positions(),
                    "timestamp": time.time(),
                }
                with open("anvel_trade_state.json", "w") as f:
                    json.dump(state, f, indent=2)
                print("✓ Trade engine state saved")
            except Exception as e:
                print(f"⚠ Trade state save failed: {e}")

        print("\n✓ All states saved successfully")
        input("\nPress Enter to continue...")

    def emergency_stop(self):
        """Emergency stop - halt all trading immediately"""
        print("\n🚨 EMERGENCY STOP")
        confirm = input("Type 'STOP' to confirm emergency shutdown: ").strip()

        if confirm == "STOP":
            if self.trade_engine:
                self.trade_engine.toggle(False)

            print("\n✓ Trading halted")
            print("✓ Saving state...")
            self.force_save_state()
            print("\n🛑 Emergency stop complete")

            time.sleep(2)
        else:
            print("\n✗ Cancelled")

        input("\nPress Enter to continue...")

    def exit_wizard(self):
        """Exit the runtime wizard"""
        print("\n👋 Exiting Runtime Wizard...")
        print("Saving final state...")
        self.save_session_state()
        self.running = False


def main():
    """Main entry point"""
    wizard = ANVELRuntimeWizard()
    try:
        wizard.run()
    except KeyboardInterrupt:
        print("\n\n⚠ Runtime wizard interrupted")
        print("Saving state...")
        wizard.save_session_state()
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error in runtime wizard: {e}")
        print("Attempting to save state...")
        wizard.save_session_state()
        sys.exit(1)


if __name__ == "__main__":
    main()
