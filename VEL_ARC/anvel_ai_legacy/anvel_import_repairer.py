#!/usr/bin/env python3
# flake8: noqa
"""
ANVEL Aggressive Import Repairer
================================
Implements multiple repair strategies for failed imports.
NO FALLBACKS - tries every possible method to fix failed imports.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Map common module names to their pip package names
MODULE_TO_PACKAGE: Dict[str, str] = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "dateutil": "python-dateutil",
    "socketio": "python-socketio",
    "jwt": "PyJWT",
    "Crypto": "pycryptodome",
}


@dataclass
class RepairAttempt:
    """Record of a single repair attempt."""

    strategy: str
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class RepairResult:
    """Result of the full repair sequence for a module."""

    module_name: str
    success: bool
    attempts: List[RepairAttempt] = field(default_factory=list)
    final_error: Optional[str] = None


class AggressiveImportRepairer:
    """
    Aggressive import repairer that tries every possible method to fix failed imports.

    Strategies (in order):
    1. Install Missing Package
    2. Upgrade Package
    3. Force Reinstall
    4. Install from requirements.txt
    5. Check for Circular Dependencies (reorder)
    6. Restore from Backup (via ANVELResilienceAgent)
    7. Rebuild Native Extensions (Rust/C++)
    8. Clear Cache and Reinstall
    9. Try Alternative Package Versions
    10. Full Environment Rebuild
    """

    def __init__(
        self,
        root: Optional[Path] = None,
        requirements_file: Optional[Path] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        local_module_prefixes: Optional[List[str]] = None,
    ):
        self.root = root or Path(__file__).resolve().parent
        self.requirements_file = requirements_file or (self.root / "requirements.txt")
        self.log_callback = log_callback or self._default_log
        self.repair_history: Dict[str, RepairResult] = {}
        self._failed_strategies: Dict[str, List[str]] = {}
        # Configurable prefixes for identifying local modules
        self.local_module_prefixes = local_module_prefixes or ["anvel_"]

    def _default_log(self, message: str, level: str = "INFO") -> None:
        """Default logging to stdout."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {
            "INFO": "ℹ",
            "SUCCESS": "✓",
            "ERROR": "✗",
            "WARNING": "⚠",
            "WORKING": "⟳",
            "REPAIR": "🔧",
        }
        icon = icons.get(level, "ℹ")
        print(f"[{timestamp}] {icon} {message}")

    def _is_local_module(self, module_name: str) -> bool:
        """Check if module is a local ANVEL module (exists as a .py file)."""
        module_file = self.root / f"{module_name}.py"
        return module_file.exists()

    def _run_pip(
        self,
        args: List[str],
        timeout: int = 300,
    ) -> Tuple[bool, str]:
        """Run a pip command and return success status and output."""
        cmd = [sys.executable, "-m", "pip"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def _try_import(self, module_name: str) -> Tuple[bool, Optional[str]]:
        """Try to import a module, return success and error message."""
        try:
            # Clear any cached failed imports
            if module_name in sys.modules:
                del sys.modules[module_name]
            importlib.import_module(module_name)
            return True, None
        except Exception as e:
            return False, str(e)

    def _get_package_name(self, module_name: str) -> str:
        """Convert module name to pip package name."""
        # Check known mappings first
        if module_name in MODULE_TO_PACKAGE:
            return MODULE_TO_PACKAGE[module_name]
        # Default: replace underscores with hyphens
        return module_name.replace("_", "-")

    def _strategy_install_package(
        self,
        module_name: str,
        package_name: str,
    ) -> RepairAttempt:
        """Strategy 1: Install the missing package."""
        start = datetime.now()
        self.log_callback(f"[Strategy 1] Installing {package_name}...", "REPAIR")

        success, output = self._run_pip(["install", package_name, "--quiet"])
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="install_package",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_upgrade_package(
        self,
        module_name: str,
        package_name: str,
    ) -> RepairAttempt:
        """Strategy 2: Upgrade the package."""
        start = datetime.now()
        self.log_callback(f"[Strategy 2] Upgrading {package_name}...", "REPAIR")

        success, output = self._run_pip(
            ["install", "--upgrade", package_name, "--quiet"]
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="upgrade_package",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_force_reinstall(
        self,
        module_name: str,
        package_name: str,
    ) -> RepairAttempt:
        """Strategy 3: Force reinstall the package."""
        start = datetime.now()
        self.log_callback(
            f"[Strategy 3] Force reinstalling {package_name}...", "REPAIR"
        )

        success, output = self._run_pip(
            ["install", "--force-reinstall", package_name, "--quiet"],
            timeout=600,
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="force_reinstall",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_install_requirements(
        self,
        module_name: str,
    ) -> RepairAttempt:
        """Strategy 4: Install from requirements.txt."""
        start = datetime.now()
        self.log_callback(f"[Strategy 4] Installing from requirements.txt...", "REPAIR")

        if not self.requirements_file.exists():
            return RepairAttempt(
                strategy="install_requirements",
                success=False,
                error="requirements.txt not found",
                duration_ms=0,
            )

        success, output = self._run_pip(
            ["install", "-r", str(self.requirements_file), "--quiet"],
            timeout=900,
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="install_requirements",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_resolve_circular(
        self,
        module_name: str,
    ) -> RepairAttempt:
        """Strategy 5: Try to resolve circular import issues."""
        start = datetime.now()
        self.log_callback(
            f"[Strategy 5] Checking for circular dependencies...", "REPAIR"
        )

        # Clear all related modules from cache (using configurable prefixes)
        to_remove = [
            name
            for name in sys.modules
            if any(name.startswith(prefix) for prefix in self.local_module_prefixes)
            or name == module_name
        ]
        for name in to_remove:
            try:
                del sys.modules[name]
            except KeyError:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_IMPORT_REPAIRER").debug("Exception suppressed in _strategy_resolve_circular")

        # Try importing again
        success, error = self._try_import(module_name)

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="resolve_circular",
            success=success,
            error=error[:200] if error else None,
            duration_ms=duration,
        )

    def _strategy_restore_from_backup(
        self,
        module_name: str,
    ) -> RepairAttempt:
        """Strategy 6: Use ANVELResilienceAgent to restore files."""
        start = datetime.now()
        self.log_callback(f"[Strategy 6] Attempting file restoration...", "REPAIR")

        try:
            # Import resilience agent without triggering full system
            from anvel_resilience_agent import ANVELResilienceAgent

            agent = ANVELResilienceAgent(root=self.root, dry_run=False)
            result = agent.execute(
                run_tests=False,
                produce_backup_script=False,
                auto_heal=True,
                restore_missing=True,
            )

            # Check if restoration helped
            success, error = self._try_import(module_name)

            duration = (datetime.now() - start).total_seconds() * 1000
            return RepairAttempt(
                strategy="restore_from_backup",
                success=success,
                error=error[:200] if error else None,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            return RepairAttempt(
                strategy="restore_from_backup",
                success=False,
                error=str(e)[:200],
                duration_ms=duration,
            )

    def _strategy_rebuild_native(
        self,
        module_name: str,
    ) -> RepairAttempt:
        """Strategy 7: Rebuild native extensions (Rust/C++)."""
        start = datetime.now()
        self.log_callback(f"[Strategy 7] Rebuilding native extensions...", "REPAIR")

        errors = []

        # Try rebuilding Rust components
        rust_dir = self.root / "rust_sandbox"
        if rust_dir.exists():
            try:
                result = subprocess.run(
                    ["cargo", "build", "--release"],
                    cwd=rust_dir,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode != 0:
                    errors.append(f"Rust build failed: {result.stderr[:100]}")
            except FileNotFoundError:
                errors.append("cargo not found")
            except Exception as e:
                errors.append(f"Rust build error: {str(e)[:100]}")

        # Try rebuilding C++ gateway
        cpp_dir = self.root / "native" / "cpp_gateway"
        if cpp_dir.exists():
            build_dir = cpp_dir / "build"
            try:
                build_dir.mkdir(exist_ok=True)
                subprocess.run(
                    ["cmake", ".."],
                    cwd=build_dir,
                    capture_output=True,
                    timeout=120,
                )
                subprocess.run(
                    ["cmake", "--build", ".", "--config", "Release"],
                    cwd=build_dir,
                    capture_output=True,
                    timeout=600,
                )
            except FileNotFoundError:
                errors.append("cmake not found")
            except Exception as e:
                errors.append(f"C++ build error: {str(e)[:100]}")

        success, error = self._try_import(module_name)

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="rebuild_native",
            success=success,
            error="; ".join(errors) if errors else (error[:200] if error else None),
            duration_ms=duration,
        )

    def _strategy_clear_cache(
        self,
        module_name: str,
        package_name: str,
    ) -> RepairAttempt:
        """Strategy 8: Clear cache and reinstall."""
        start = datetime.now()
        self.log_callback(f"[Strategy 8] Clearing cache and reinstalling...", "REPAIR")

        # Clear pip cache
        self._run_pip(["cache", "purge"], timeout=60)

        # Clear __pycache__ directories
        for pycache in self.root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_IMPORT_REPAIRER").debug("Exception suppressed in _strategy_clear_cache")

        # Clear .pyc files
        for pyc in self.root.rglob("*.pyc"):
            try:
                pyc.unlink()
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_IMPORT_REPAIRER").debug("Exception suppressed in _strategy_clear_cache")

        # Uninstall and reinstall
        self._run_pip(["uninstall", "-y", package_name], timeout=60)
        success, output = self._run_pip(["install", package_name, "--quiet"])

        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="clear_cache",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_alternative_versions(
        self,
        module_name: str,
        package_name: str,
    ) -> RepairAttempt:
        """Strategy 9: Try alternative package versions."""
        start = datetime.now()
        self.log_callback(f"[Strategy 9] Trying alternative versions...", "REPAIR")

        # Try to install without version constraint first, which might pick a compatible version
        success, output = self._run_pip(
            ["install", "--no-deps", package_name], timeout=120
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            if import_ok:
                duration = (datetime.now() - start).total_seconds() * 1000
                return RepairAttempt(
                    strategy="alternative_versions",
                    success=True,
                    duration_ms=duration,
                )

        # Try getting installed version info and reinstalling with deps
        info_success, info_output = self._run_pip(["show", package_name], timeout=30)

        versions_tried = []
        if info_success:
            # Package exists but import fails - try reinstalling with all dependencies
            self._run_pip(
                ["install", "--upgrade", "--force-reinstall", package_name], timeout=180
            )
            import_ok, _ = self._try_import(module_name)
            if import_ok:
                duration = (datetime.now() - start).total_seconds() * 1000
                return RepairAttempt(
                    strategy="alternative_versions",
                    success=True,
                    duration_ms=duration,
                )
            versions_tried.append("reinstall-with-deps")

        import_ok, error = self._try_import(module_name)
        duration = (datetime.now() - start).total_seconds() * 1000
        return RepairAttempt(
            strategy="alternative_versions",
            success=import_ok,
            error=f"Tried: {versions_tried}; {error[:100] if error else ''}",
            duration_ms=duration,
        )

    def _strategy_full_rebuild(
        self,
        module_name: str,
    ) -> RepairAttempt:
        """Strategy 10: Full environment rebuild via run_pipeline.py."""
        start = datetime.now()
        self.log_callback(
            f"[Strategy 10] Attempting full environment rebuild...", "REPAIR"
        )

        pipeline_script = self.root / "scripts" / "run_pipeline.py"
        if not pipeline_script.exists():
            return RepairAttempt(
                strategy="full_rebuild",
                success=False,
                error="run_pipeline.py not found",
                duration_ms=0,
            )

        try:
            result = subprocess.run(
                [sys.executable, str(pipeline_script), "all"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes
            )

            if result.returncode == 0:
                import_ok, error = self._try_import(module_name)
                duration = (datetime.now() - start).total_seconds() * 1000
                return RepairAttempt(
                    strategy="full_rebuild",
                    success=import_ok,
                    error=error[:200] if error else None,
                    duration_ms=duration,
                )
            else:
                duration = (datetime.now() - start).total_seconds() * 1000
                return RepairAttempt(
                    strategy="full_rebuild",
                    success=False,
                    error=result.stderr[:200],
                    duration_ms=duration,
                )
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start).total_seconds() * 1000
            return RepairAttempt(
                strategy="full_rebuild",
                success=False,
                error="Full rebuild timed out",
                duration_ms=duration,
            )
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            return RepairAttempt(
                strategy="full_rebuild",
                success=False,
                error=str(e)[:200],
                duration_ms=duration,
            )

    def repair_import(self, module_name: str) -> RepairResult:
        """
        Attempt to repair a failed import using all available strategies.

        For local ANVEL modules, prioritizes:
        - Circular dependency resolution
        - File restoration
        - Requirements installation

        For external packages, prioritizes:
        - pip install
        - pip upgrade
        - force reinstall

        Returns a RepairResult with details of all attempts made.
        """
        self.log_callback(
            f"Starting aggressive import repair for: {module_name}",
            "REPAIR",
        )

        result = RepairResult(module_name=module_name, success=False)
        package_name = self._get_package_name(module_name)

        # Check if already importable
        ok, error = self._try_import(module_name)
        if ok:
            self.log_callback(
                f"{module_name} imported successfully (no repair needed)", "SUCCESS"
            )
            result.success = True
            return result

        result.final_error = error

        # Check if this is a local ANVEL module
        is_local = self._is_local_module(module_name)

        if is_local:
            # For local modules, prioritize strategies that fix dependency issues
            # rather than trying to install non-existent packages
            self.log_callback(
                f"{module_name} is a local module, using local repair strategies",
                "INFO",
            )
            strategies: List[Callable[[], RepairAttempt]] = [
                lambda: self._strategy_resolve_circular(module_name),
                lambda: self._strategy_install_requirements(module_name),
                lambda: self._strategy_restore_from_backup(module_name),
                lambda: self._strategy_rebuild_native(module_name),
                lambda: self._strategy_clear_cache(module_name, package_name),
                lambda: self._strategy_full_rebuild(module_name),
            ]
        else:
            # For external packages, use all strategies
            strategies = [
                lambda: self._strategy_install_package(module_name, package_name),
                lambda: self._strategy_upgrade_package(module_name, package_name),
                lambda: self._strategy_force_reinstall(module_name, package_name),
                lambda: self._strategy_install_requirements(module_name),
                lambda: self._strategy_resolve_circular(module_name),
                lambda: self._strategy_restore_from_backup(module_name),
                lambda: self._strategy_rebuild_native(module_name),
                lambda: self._strategy_clear_cache(module_name, package_name),
                lambda: self._strategy_alternative_versions(module_name, package_name),
                lambda: self._strategy_full_rebuild(module_name),
            ]

        for i, strategy_fn in enumerate(strategies, 1):
            try:
                attempt = strategy_fn()
                result.attempts.append(attempt)

                if attempt.success:
                    self.log_callback(
                        f"Strategy {i} ({attempt.strategy}) succeeded for {module_name}",
                        "SUCCESS",
                    )
                    result.success = True
                    result.final_error = None
                    break
                else:
                    self.log_callback(
                        f"Strategy {i} ({attempt.strategy}) failed: {attempt.error or 'unknown'}",
                        "WARNING",
                    )
            except Exception as e:
                result.attempts.append(
                    RepairAttempt(
                        strategy=f"strategy_{i}",
                        success=False,
                        error=str(e)[:200],
                    )
                )
                self.log_callback(f"Strategy {i} raised exception: {e}", "ERROR")

        if not result.success:
            self.log_callback(
                f"ALL repair strategies exhausted for {module_name}",
                "ERROR",
            )
            # Update final error with most recent
            if result.attempts:
                result.final_error = result.attempts[-1].error

        self.repair_history[module_name] = result
        return result

    def safe_import(
        self,
        module_name: str,
        attribute: Optional[str] = None,
    ) -> Tuple[Any, Optional[RepairResult]]:
        """
        Safely import a module with automatic repair on failure.

        Returns (module_or_attribute, repair_result).
        If repair_result is None, no repair was needed.
        """
        # First try direct import
        ok, error = self._try_import(module_name)
        if ok:
            mod = sys.modules[module_name]
            if attribute:
                return getattr(mod, attribute, None), None
            return mod, None

        # Import failed, try to repair
        repair_result = self.repair_import(module_name)

        if repair_result.success:
            mod = sys.modules.get(module_name)
            if mod:
                if attribute:
                    return getattr(mod, attribute, None), repair_result
                return mod, repair_result

        # Repair failed
        return None, repair_result

    def get_repair_summary(self) -> Dict[str, Any]:
        """Get a summary of all repair attempts."""
        summary = {
            "total_modules": len(self.repair_history),
            "successful_repairs": sum(
                1 for r in self.repair_history.values() if r.success
            ),
            "failed_repairs": sum(
                1 for r in self.repair_history.values() if not r.success
            ),
            "details": {},
        }

        for module_name, result in self.repair_history.items():
            summary["details"][module_name] = {
                "success": result.success,
                "attempts_count": len(result.attempts),
                "strategies_tried": [a.strategy for a in result.attempts],
                "final_error": result.final_error,
            }

        return summary


# Singleton instance for global use
_repairer: Optional[AggressiveImportRepairer] = None


def get_repairer() -> AggressiveImportRepairer:
    """Get the global AggressiveImportRepairer instance."""
    global _repairer
    if _repairer is None:
        _repairer = AggressiveImportRepairer()
    return _repairer


def aggressive_import(
    module_name: str,
    attribute: Optional[str] = None,
) -> Any:
    """
    Import a module with aggressive auto-repair on failure.

    Usage:
        EventBus = aggressive_import('anvel_event_bus', 'AnvelEventBus')
        trade_engine = aggressive_import('anvel_trade_engine')

    Raises ImportError only after ALL repair strategies have been exhausted.
    """
    repairer = get_repairer()
    obj, repair_result = repairer.safe_import(module_name, attribute)

    if obj is None:
        error_msg = f"Failed to import {module_name}"
        if repair_result and repair_result.final_error:
            error_msg += f": {repair_result.final_error}"
        if repair_result:
            error_msg += f" (tried {len(repair_result.attempts)} repair strategies)"
        raise ImportError(error_msg)

    return obj


__all__ = [
    "AggressiveImportRepairer",
    "RepairAttempt",
    "RepairResult",
    "get_repairer",
    "aggressive_import",
]
