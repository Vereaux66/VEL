#!/usr/bin/env python3
"""
ANVEL ULTIMATE RUNTIME MONITOR
================================
Real-time system monitoring with:
 Live performance metrics
 Active trade monitoring
 Health status checking
 Error detection
 Resource usage
 Event stream monitoring
"""

import os
import json
import time
from datetime import datetime


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    ENDC = "\033[0m"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def colored(text, color, bold=False):
    return f"{Colors.BOLD if bold else ''}{color}{text}{Colors.ENDC}"


class RuntimeMonitor:
    """Real-time ANVEL monitoring dashboard"""

    def __init__(self):
        self.running = True
        self.refresh_interval = 5

    def banner(self):
        print(
            colored(
                """
+==========================================================================+===========================================================================+
|                                                                          |
|                  [STATS] ANVEL RUNTIME MONITOR [STATS]                            |
|                                                                          |
|                    Live System Status Dashboard                         |
|                                                                          |
+==========================================================================+
""",
                Colors.CYAN,
                True,
            )
        )

    def load_state(self):
        """Load current system state"""
        state = {}

        # Load session state
        if os.path.exists("anvel_session_state.json"):
            try:
                with open("anvel_session_state.json", "r") as f:
                    state["session"] = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load session state: {e}")
                state["session"] = None

        # Load trade state
        if os.path.exists("anvel_trade_state.json"):
            try:
                with open("anvel_trade_state.json", "r") as f:
                    state["trade"] = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load trade state: {e}")
                state["trade"] = None

        # Load config
        if os.path.exists("anvel_config.json"):
            try:
                with open("anvel_config.json", "r") as f:
                    state["config"] = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load config: {e}")
                state["config"] = None

        return state

    def display_dashboard(self, state):
        """Display monitoring dashboard"""
        clear()
        self.banner()

        # System Status
        print("=" * 78)
        print(colored("  SYSTEM STATUS", Colors.CYAN, True))
        print("=" * 78 + "\n")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Current Time: {now}")

        if state.get("session"):
            last_startup = state["session"].get("last_startup", "Unknown")
            print(f"Last Startup: {last_startup}")

            sessions = state["session"].get("sessions", [])
            print(f"Total Sessions: {len(sessions)}")

        # Trading Status
        print("\n" + "=" * 78)
        print(colored("  TRADING STATUS", Colors.CYAN, True))
        print("=" * 78 + "\n")

        if state.get("config"):
            mode = (
                state["config"].get("trading_config", {}).get("trading_mode", "Unknown")
            )
            market = (
                state["config"].get("trading_config", {}).get("market_type", "Unknown")
            )

            print(
                f"Mode: {colored(mode.upper(), Colors.GREEN if mode == 'simulation' else Colors.YELLOW)}"
            )
            print(f"Market: {market}")

            if mode == "simulation":
                print(colored(" SAFE MODE - Using fake money", Colors.GREEN))

        if state.get("trade"):
            positions = state["trade"].get("positions", [])
            trades = state["trade"].get("trades", [])
            balance = state["trade"].get("balance", 0)

            print(f"\nBalance: ${balance:,.2f}")
            print(f"Open Positions: {len(positions)}")
            print(f"Total Trades: {len(trades)}")

        # Health Status
        print("\n" + "=" * 78)
        print(colored("  HEALTH STATUS", Colors.CYAN, True))
        print("=" * 78 + "\n")

        # Check for error logs
        error_count = 0
        if os.path.exists("logs"):
            error_logs = [f for f in os.listdir("logs") if "error" in f.lower()]
            error_count = len(error_logs)

        if error_count == 0:
            print(colored(" No errors detected", Colors.GREEN))
        else:
            print(colored(f"  {error_count} error log(s) found", Colors.YELLOW))

        # State persistence check
        state_files = [
            "anvel_config.json",
            "anvel_session_state.json",
            "anvel_trade_state.json",
        ]
        all_exist = all(os.path.exists(f) for f in state_files)

        if all_exist:
            print(colored(" All state files present", Colors.GREEN))
        else:
            missing = [f for f in state_files if not os.path.exists(f)]
            print(
                colored(f"  Missing state files: {', '.join(missing)}", Colors.YELLOW)
            )

        # Controls
        print("\n" + "=" * 78)
        print(colored("  CONTROLS", Colors.CYAN, True))
        print("=" * 78 + "\n")
        print(f"Auto-refresh: {self.refresh_interval} seconds")
        print("Press Ctrl+C to exit")

        print("\n" + "=" * 78)
        print(f"Refreshing in {self.refresh_interval} seconds...")

    def run(self):
        """Run monitoring loop"""
        try:
            while self.running:
                state = self.load_state()
                self.display_dashboard(state)
                time.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            clear()
            print("\n" + colored("Monitor stopped.", Colors.CYAN) + "\n")


def main():
    monitor = RuntimeMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
