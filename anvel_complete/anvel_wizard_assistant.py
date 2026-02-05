#!/usr/bin/env python3
"""
ANVEL Wizard Assistant (Consolidated)
Continuous assistant that unifies setup, startup, runtime, shutdown, debug, and verify flows.
Date: 2025-10-20T18:02:55.906Z
"""

import importlib
import os
import subprocess
import sys
import traceback
from typing import Optional

# Force UTF-8-safe output
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    import logging as _lg  # noqa: E402
    _lg.getLogger("ANVEL_WIZARD_ASSISTANT").debug("Exception suppressed")


class ANVELWizardAssistant:
    def __init__(self):
        self.cwd = os.getcwd()

    # Internal helpers
    def _run_subprocess(self, args, timeout: Optional[int] = None):
        try:
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
            )
            out, err = proc.communicate(timeout=timeout)
            return (
                proc.returncode,
                (out.decode(errors="replace") + err.decode(errors="replace")).strip(),
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            return (
                124,
                (out.decode(errors="replace") + err.decode(errors="replace")).strip(),
            )
        except Exception as e:
            return 1, f"ERROR: {e}"

    def _call_wizard_class(
        self, module_name: str, class_name: str, method: str = "run"
    ):
        try:
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            inst = cls()
            fn = getattr(inst, method, None)
            if callable(fn):
                return 0, str(fn()) or "OK"
            return 0, "OK"
        except Exception:
            # fallback to subprocess
            code, out = self._run_subprocess([sys.executable, f"{module_name}.py"])
            return code, out

    # Public unified operations
    def setup(self, noninteractive=False):
        # Prefer onboarding wizard
        if noninteractive:
            # Quick verify + create default config when missing
            if not os.path.exists("anvel_config.json"):
                default_cfg = {
                    "user_profile": {
                        "experience": "expert",
                        "goal": "profit",
                        "risk_tolerance": "medium",
                    },
                    "trading_config": {
                        "trading_mode": "simulation",
                        "market_type": "stocks",
                        "strategies": ["baseline"],
                        "max_position_size": 1000,
                        "stop_loss_percent": 5,
                        "take_profit_percent": 10,
                        "daily_loss_limit": 2,
                    },
                    "system_config": {
                        "hybrid": {
                            "enabled": False,
                            "exec_core_endpoint": "localhost:50051",
                            "gateway_endpoint": "localhost:50052",
                        }
                    },
                    "setup_completed": True,
                }
                import json

                with open("anvel_config.json", "w", encoding="utf-8") as f:
                    json.dump(default_cfg, f, indent=2)
                return "[ASSIST] Setup: default configuration created"
            return "[ASSIST] Setup: configuration already present"
        code, out = self._call_wizard_class(
            "anvel_onboarding_wizard", "ANVELOnboardingWizard"
        )
        return (
            "[ASSIST] Setup complete" if code == 0 else f"[ASSIST] Setup failed\n{out}"
        )

    def startup(self):
        # Prefer ultimate startup wizard when present
        try:
            mod = importlib.import_module("anvel_ultimate_startup")
            return (
                "[ASSIST] Startup launched"
                if mod.main() is None
                else "[ASSIST] Startup done"
            )
        except Exception:
            code, out = self._call_wizard_class(
                "anvel_startup_wizard", "ANVELStartupWizard"
            )
            return (
                "[ASSIST] Startup complete"
                if code == 0
                else f"[ASSIST] Startup failed\n{out}"
            )

    def runtime(self):
        code, out = self._call_wizard_class(
            "anvel_runtime_wizard", "ANVELRuntimeWizard"
        )
        return (
            "[ASSIST] Runtime session complete"
            if code == 0
            else f"[ASSIST] Runtime failed\n{out}"
        )

    def shutdown(self):
        code, out = self._call_wizard_class(
            "anvel_shutdown_wizard", "ANVELShutdownWizard"
        )
        return (
            "[ASSIST] Shutdown complete"
            if code == 0
            else f"[ASSIST] Shutdown failed\n{out}"
        )

    def debug(self):
        # Prefer ultimate debug
        try:
            mod = importlib.import_module("anvel_ultimate_debug")
            return (
                "[ASSIST] Debug completed"
                if getattr(mod, "main", lambda: 0)() == 0
                else "[ASSIST] Debug done"
            )
        except Exception:
            code, out = self._call_wizard_class(
                "anvel_debug_wizard", "ANVELDebugWizard"
            )
            return (
                "[ASSIST] Debug done" if code == 0 else f"[ASSIST] Debug failed\n{out}"
            )

    def verify(self, quick=True):
        script = (
            "verify_system_quick.py"
            if quick and os.path.exists("verify_system_quick.py")
            else "verify_system.py"
        )
        code, out = self._run_subprocess([sys.executable, script])
        return "[ASSIST] Verify PASS" if code == 0 else f"[ASSIST] Verify FAIL\n{out}"

    def auto(self):
        # Continuous assistant: verify -> setup if needed -> startup -> runtime
        out = []
        if not os.path.exists("anvel_config.json"):
            out.append(self.setup(noninteractive=True))
        out.append(self.verify(quick=True))
        out.append(self.startup())
        # non-blocking runtime smoke (5s): use launch_anel --no-wait
        code, launch = self._run_subprocess(
            [sys.executable, "launch_anel.py", "--no-wait"], timeout=15
        )
        out.append(
            "[ASSIST] Launch OK" if code == 0 else f"[ASSIST] Launch failed\n{launch}"
        )
        return "\n".join(out)


# CLI


def main():
    import argparse

    p = argparse.ArgumentParser(description="ANVEL Wizard Assistant (Consolidated)")
    p.add_argument(
        "command",
        nargs="?",
        default="auto",
        choices=["auto", "setup", "startup", "runtime", "shutdown", "debug", "verify"],
    )
    p.add_argument("--noninteractive", action="store_true")
    p.add_argument("--full", action="store_true", help="full verify instead of quick")
    args = p.parse_args()
    asst = ANVELWizardAssistant()
    if args.command == "setup":
        print(asst.setup(noninteractive=args.noninteractive))
        return
    if args.command == "startup":
        print(asst.startup())
        return
    if args.command == "runtime":
        print(asst.runtime())
        return
    if args.command == "shutdown":
        print(asst.shutdown())
        return
    if args.command == "debug":
        print(asst.debug())
        return
    if args.command == "verify":
        print(asst.verify(quick=not args.full))
        return
    print(asst.auto())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ASSIST] Interrupted")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
