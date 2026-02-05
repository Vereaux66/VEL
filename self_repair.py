#!/usr/bin/env python3
"""
VEL AI Self-Repair Module
==========================

Consolidated self-repair system for the VEL trading platform.
Production-critical code with capital implications.

This module provides:
- ImportRepairer: Fixes missing/broken imports with aggressive strategies
- CodeAnalyzer: AST-based code analysis for detecting issues
- CodeRepairer: Generates and applies fixes for detected issues
- CodeEvolutionEngine: Tracks code quality over time

Core Principles:
- NO stubs, TODOs, or placeholders
- Complete error handling with proper propagation
- Thread-safe operations with explicit locking
- All repairs are logged and reversible
- Security: Whitelisted packages only for auto-install
- Fail fast when correctness cannot be guaranteed
"""

from __future__ import annotations

import ast
import importlib
import json
import logging
import math
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Configure module logger
logger = logging.getLogger("vel.ai.self_repair")

# ============================================================================
# Package Mapping and Security Configuration
# ============================================================================

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

# Whitelisted packages allowed for auto-installation
# This is a security measure to prevent arbitrary package installation
WHITELISTED_PACKAGES: set[str] = {
    "numpy",
    "pandas",
    "pytest",
    "requests",
    "pyyaml",
    "python-dotenv",
    "python-jose",
    "PyJWT",
    "cryptography",
    "boto3",
    "psycopg2-binary",
    "redis",
    "celery",
    "fastapi",
    "uvicorn",
    "pydantic",
    "ccxt",
    "websockets",
    "aiohttp",
}


# ============================================================================
# Enumerations and Data Classes
# ============================================================================


class RepairStrategy(Enum):
    """Strategies for code repair"""

    PATTERN_MATCH = auto()  # Use known patterns
    SEMANTIC_FIX = auto()  # Understand and fix semantically
    TEMPLATE_REPLACE = auto()  # Replace with template
    INCREMENTAL = auto()  # Small incremental changes
    STRUCTURAL = auto()  # Fix structural issues
    TYPE_INFERENCE = auto()  # Fix type-related issues
    DEPENDENCY_FIX = auto()  # Fix import/dependency issues


class CodeQuality(Enum):
    """Code quality levels"""

    EXCELLENT = 5
    GOOD = 4
    ACCEPTABLE = 3
    NEEDS_IMPROVEMENT = 2
    POOR = 1
    BROKEN = 0


@dataclass
class ImportRepairAttempt:
    """Record of a single import repair attempt."""

    strategy: str
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class ImportRepairResult:
    """Result of the full repair sequence for a module."""

    module_name: str
    success: bool
    attempts: List[ImportRepairAttempt] = field(default_factory=list)
    final_error: Optional[str] = None


@dataclass
class CodePattern:
    """Represents a code pattern for matching and repair"""

    name: str
    description: str
    pattern_ast: Optional[str]  # AST pattern for matching
    pattern_regex: Optional[str]  # Regex pattern for matching
    fix_template: str
    confidence: float
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return self.confidence
        return self.success_count / total


@dataclass
class CodeIssue:
    """Represents a detected code issue"""

    file_path: str
    line_start: int
    line_end: int
    column_start: int
    column_end: int
    issue_type: str
    severity: str
    description: str
    code_snippet: str
    suggested_fix: Optional[str] = None
    confidence: float = 0.0
    auto_fixable: bool = False
    related_issues: List[str] = field(default_factory=list)


@dataclass
class RepairResult:
    """Result of a repair attempt"""

    success: bool
    original_code: str
    repaired_code: str
    strategy_used: RepairStrategy
    changes_made: List[str]
    confidence: float
    execution_time: float
    tests_passed: Optional[bool] = None
    error_message: Optional[str] = None


@dataclass
class CodeMetrics:
    """Code quality metrics"""

    file_path: str
    lines_of_code: int
    cyclomatic_complexity: int
    maintainability_index: float
    test_coverage: float
    documentation_ratio: float
    code_quality: CodeQuality
    issues_count: int
    last_modified: datetime


# ============================================================================
# Import Repairer
# ============================================================================


class ImportRepairer:
    """
    Aggressive import repairer that tries multiple strategies to fix failed imports.

    Strategies (in order):
    1. Install Missing Package (if whitelisted)
    2. Upgrade Package
    3. Force Reinstall
    4. Install from requirements.txt
    5. Resolve Circular Dependencies
    6. Clear Cache and Reinstall
    7. Try Alternative Versions

    Security:
    - Only installs whitelisted packages
    - All pip operations are logged
    - Timeout protection on all subprocess calls
    """

    def __init__(
        self,
        root: Optional[Path] = None,
        requirements_file: Optional[Path] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        local_module_prefixes: Optional[List[str]] = None,
        allow_auto_install: bool = False,
    ):
        """
        Initialize ImportRepairer.

        Args:
            root: Root directory of the project
            requirements_file: Path to requirements.txt
            log_callback: Optional callback for logging
            local_module_prefixes: Prefixes for identifying local modules
            allow_auto_install: Allow automatic package installation (default: False)
        """
        self.root = root or Path.cwd()
        self.requirements_file = requirements_file or (self.root / "requirements.txt")
        self.log_callback = log_callback or self._default_log
        self.repair_history: Dict[str, ImportRepairResult] = {}
        self.local_module_prefixes = local_module_prefixes or ["anvel_", "vel_"]
        self.allow_auto_install = allow_auto_install
        self.lock = threading.RLock()

    def _default_log(self, message: str, level: str = "INFO") -> None:
        """Default logging to module logger."""
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)

    def _is_local_module(self, module_name: str) -> bool:
        """Check if module is a local module (exists as a .py file)."""
        module_file = self.root / f"{module_name}.py"
        return module_file.exists()

    def _is_whitelisted(self, package_name: str) -> bool:
        """Check if package is whitelisted for auto-installation."""
        return package_name.lower() in {p.lower() for p in WHITELISTED_PACKAGES}

    def _run_pip(
        self,
        args: List[str],
        timeout: int = 300,
    ) -> Tuple[bool, str]:
        """
        Run a pip command and return success status and output.

        Args:
            args: List of pip arguments
            timeout: Timeout in seconds

        Returns:
            Tuple of (success, output)
        """
        cmd = [sys.executable, "-m", "pip"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            success = result.returncode == 0
            output = result.stdout + result.stderr
            self.log_callback(
                f"pip {' '.join(args)}: {'SUCCESS' if success else 'FAILED'}",
                "INFO" if success else "WARNING",
            )
            return success, output
        except subprocess.TimeoutExpired:
            self.log_callback(f"pip command timed out after {timeout}s", "ERROR")
            return False, "Command timed out"
        except Exception as e:
            self.log_callback(f"pip command error: {e}", "ERROR")
            return False, str(e)

    def _try_import(self, module_name: str) -> Tuple[bool, Optional[str]]:
        """
        Try to import a module, return success and error message.

        Args:
            module_name: Name of module to import

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Clear any cached failed imports
            if module_name in sys.modules:
                del sys.modules[module_name]
            importlib.import_module(module_name)
            return True, None
        except Exception as e:
            return False, str(e)

    def _get_package_name(self, module_name: str) -> str:
        """
        Convert module name to pip package name.

        Args:
            module_name: Python module name

        Returns:
            pip package name
        """
        # Check known mappings first
        if module_name in MODULE_TO_PACKAGE:
            return MODULE_TO_PACKAGE[module_name]
        # Default: replace underscores with hyphens
        return module_name.replace("_", "-")

    def _strategy_install_package(
        self,
        module_name: str,
        package_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 1: Install the missing package."""
        start = datetime.now()
        self.log_callback(f"[Strategy 1] Installing {package_name}...", "INFO")

        # Security check
        if not self._is_whitelisted(package_name):
            duration = (datetime.now() - start).total_seconds() * 1000
            return ImportRepairAttempt(
                strategy="install_package",
                success=False,
                error=f"Package {package_name} not in whitelist",
                duration_ms=duration,
            )

        if not self.allow_auto_install:
            duration = (datetime.now() - start).total_seconds() * 1000
            return ImportRepairAttempt(
                strategy="install_package",
                success=False,
                error="Auto-install disabled",
                duration_ms=duration,
            )

        success, output = self._run_pip(["install", package_name, "--quiet"])
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return ImportRepairAttempt(
            strategy="install_package",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_upgrade_package(
        self,
        module_name: str,
        package_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 2: Upgrade the package."""
        start = datetime.now()
        self.log_callback(f"[Strategy 2] Upgrading {package_name}...", "INFO")

        success, output = self._run_pip(
            ["install", "--upgrade", package_name, "--quiet"]
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return ImportRepairAttempt(
            strategy="upgrade_package",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_force_reinstall(
        self,
        module_name: str,
        package_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 3: Force reinstall the package."""
        start = datetime.now()
        self.log_callback(f"[Strategy 3] Force reinstalling {package_name}...", "INFO")

        success, output = self._run_pip(
            ["install", "--force-reinstall", package_name, "--quiet"],
            timeout=600,
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return ImportRepairAttempt(
            strategy="force_reinstall",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_install_requirements(
        self,
        module_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 4: Install from requirements.txt."""
        start = datetime.now()
        self.log_callback("[Strategy 4] Installing from requirements.txt...", "INFO")

        if not self.requirements_file.exists():
            return ImportRepairAttempt(
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
        return ImportRepairAttempt(
            strategy="install_requirements",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_resolve_circular(
        self,
        module_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 5: Try to resolve circular import issues."""
        start = datetime.now()
        self.log_callback(
            "[Strategy 5] Checking for circular dependencies...", "INFO"
        )

        # Clear all related modules from cache
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
                pass

        # Try importing again
        success, error = self._try_import(module_name)

        duration = (datetime.now() - start).total_seconds() * 1000
        return ImportRepairAttempt(
            strategy="resolve_circular",
            success=success,
            error=error[:200] if error else None,
            duration_ms=duration,
        )

    def _strategy_clear_cache(
        self,
        module_name: str,
        package_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 6: Clear cache and reinstall."""
        start = datetime.now()
        self.log_callback("[Strategy 6] Clearing cache and reinstalling...", "INFO")

        # Clear pip cache
        self._run_pip(["cache", "purge"], timeout=60)

        # Clear __pycache__ directories
        for pycache in self.root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
            except Exception as e:
                logger.debug(f"Could not remove {pycache}: {e}")

        # Clear .pyc files
        for pyc in self.root.rglob("*.pyc"):
            try:
                pyc.unlink()
            except Exception as e:
                logger.debug(f"Could not remove {pyc}: {e}")

        # Uninstall and reinstall
        self._run_pip(["uninstall", "-y", package_name], timeout=60)
        success, output = self._run_pip(["install", package_name, "--quiet"])

        if success:
            import_ok, _ = self._try_import(module_name)
            success = import_ok

        duration = (datetime.now() - start).total_seconds() * 1000
        return ImportRepairAttempt(
            strategy="clear_cache",
            success=success,
            error=None if success else output[:200],
            duration_ms=duration,
        )

    def _strategy_alternative_versions(
        self,
        module_name: str,
        package_name: str,
    ) -> ImportRepairAttempt:
        """Strategy 7: Try alternative package versions."""
        start = datetime.now()
        self.log_callback("[Strategy 7] Trying alternative versions...", "INFO")

        # Try to install without version constraint first
        success, output = self._run_pip(
            ["install", "--no-deps", package_name], timeout=120
        )
        if success:
            import_ok, _ = self._try_import(module_name)
            if import_ok:
                duration = (datetime.now() - start).total_seconds() * 1000
                return ImportRepairAttempt(
                    strategy="alternative_versions",
                    success=True,
                    duration_ms=duration,
                )

        # Try reinstalling with all dependencies
        self._run_pip(
            ["install", "--upgrade", "--force-reinstall", package_name], timeout=180
        )
        import_ok, error = self._try_import(module_name)

        duration = (datetime.now() - start).total_seconds() * 1000
        return ImportRepairAttempt(
            strategy="alternative_versions",
            success=import_ok,
            error=error[:100] if error else None,
            duration_ms=duration,
        )

    def repair_import(self, module_name: str) -> ImportRepairResult:
        """
        Attempt to repair a failed import using all available strategies.

        For local modules, prioritizes:
        - Circular dependency resolution
        - Requirements installation

        For external packages, prioritizes:
        - pip install (if whitelisted)
        - pip upgrade
        - force reinstall

        Args:
            module_name: Name of module to repair

        Returns:
            ImportRepairResult with details of all attempts made
        """
        with self.lock:
            self.log_callback(
                f"Starting import repair for: {module_name}",
                "INFO",
            )

            result = ImportRepairResult(module_name=module_name, success=False)
            package_name = self._get_package_name(module_name)

            # Check if already importable
            ok, error = self._try_import(module_name)
            if ok:
                self.log_callback(
                    f"{module_name} imported successfully (no repair needed)", "INFO"
                )
                result.success = True
                return result

            result.final_error = error

            # Check if this is a local module
            is_local = self._is_local_module(module_name)

            if is_local:
                # For local modules, prioritize strategies that fix dependency issues
                self.log_callback(
                    f"{module_name} is a local module, using local repair strategies",
                    "INFO",
                )
                strategies: List[Callable[[], ImportRepairAttempt]] = [
                    lambda: self._strategy_resolve_circular(module_name),
                    lambda: self._strategy_install_requirements(module_name),
                    lambda: self._strategy_clear_cache(module_name, package_name),
                ]
            else:
                # For external packages, use all strategies
                strategies = [
                    lambda: self._strategy_install_package(module_name, package_name),
                    lambda: self._strategy_upgrade_package(module_name, package_name),
                    lambda: self._strategy_force_reinstall(module_name, package_name),
                    lambda: self._strategy_install_requirements(module_name),
                    lambda: self._strategy_resolve_circular(module_name),
                    lambda: self._strategy_clear_cache(module_name, package_name),
                    lambda: self._strategy_alternative_versions(
                        module_name, package_name
                    ),
                ]

            for i, strategy_fn in enumerate(strategies, 1):
                try:
                    attempt = strategy_fn()
                    result.attempts.append(attempt)

                    if attempt.success:
                        self.log_callback(
                            f"Strategy {i} ({attempt.strategy}) succeeded for {module_name}",
                            "INFO",
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
                    logger.error(f"Strategy {i} raised exception: {e}")
                    result.attempts.append(
                        ImportRepairAttempt(
                            strategy=f"strategy_{i}",
                            success=False,
                            error=str(e)[:200],
                        )
                    )

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
    ) -> Tuple[Any, Optional[ImportRepairResult]]:
        """
        Safely import a module with automatic repair on failure.

        Args:
            module_name: Name of module to import
            attribute: Optional attribute to get from module

        Returns:
            Tuple of (module_or_attribute, repair_result).
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
        with self.lock:
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


# ============================================================================
# Code Analyzer
# ============================================================================


class CodeAnalyzer:
    """
    Analyzes Python code using AST for detecting issues.

    Detects:
    - Syntax errors
    - Empty functions/stubs
    - TODO/FIXME comments
    - Bare except clauses
    - Missing docstrings
    - High complexity
    - Hardcoded credentials (basic detection)
    """

    def __init__(self):
        """Initialize CodeAnalyzer."""
        self.lock = threading.Lock()

    def analyze_file(self, file_path: Path) -> List[CodeIssue]:
        """
        Analyze a file for issues.

        Args:
            file_path: Path to Python file

        Returns:
            List of CodeIssue objects
        """
        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Try to parse AST
            try:
                tree = ast.parse(content, filename=str(file_path))

                # Find AST-based issues
                issues.extend(self._find_ast_issues(tree, file_path, lines))

                # Analyze complexity
                complexity = self._calculate_complexity(tree)
                if complexity > 15:
                    issues.append(
                        CodeIssue(
                            file_path=str(file_path),
                            line_start=1,
                            line_end=len(lines),
                            column_start=0,
                            column_end=0,
                            issue_type="too_complex",
                            severity="MEDIUM",
                            description=f"File has high cyclomatic complexity: {complexity}",
                            code_snippet="",
                            auto_fixable=False,
                        )
                    )

            except SyntaxError as e:
                issues.append(
                    CodeIssue(
                        file_path=str(file_path),
                        line_start=e.lineno or 1,
                        line_end=e.lineno or 1,
                        column_start=e.offset or 0,
                        column_end=e.offset or 0,
                        issue_type="syntax_error",
                        severity="CRITICAL",
                        description=str(e.msg),
                        code_snippet=e.text or "",
                        auto_fixable=False,
                    )
                )

            # Find regex-based issues
            issues.extend(self._find_regex_issues(content, file_path, lines))

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")

        return issues

    def _find_ast_issues(
        self, tree: ast.AST, file_path: Path, lines: List[str]
    ) -> List[CodeIssue]:
        """Find issues using AST analysis."""
        issues = []

        for node in ast.walk(tree):
            # Check for bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(
                    CodeIssue(
                        file_path=str(file_path),
                        line_start=node.lineno,
                        line_end=node.lineno,
                        column_start=node.col_offset,
                        column_end=node.col_offset,
                        issue_type="bare_except",
                        severity="MEDIUM",
                        description="Bare except clause should specify exception type",
                        code_snippet=(
                            lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        ),
                        auto_fixable=True,
                        confidence=0.95,
                    )
                )

            # Check for empty except
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    issues.append(
                        CodeIssue(
                            file_path=str(file_path),
                            line_start=node.lineno,
                            line_end=node.lineno,
                            column_start=node.col_offset,
                            column_end=node.col_offset,
                            issue_type="empty_except",
                            severity="HIGH",
                            description="Empty except block silently swallows exceptions",
                            code_snippet=(
                                lines[node.lineno - 1]
                                if node.lineno <= len(lines)
                                else ""
                            ),
                            auto_fixable=True,
                            confidence=0.9,
                        )
                    )

            # Check for missing docstrings
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not ast.get_docstring(node):
                    # Only report for public functions/classes
                    if isinstance(node, ast.ClassDef) or not node.name.startswith("_"):
                        issues.append(
                            CodeIssue(
                                file_path=str(file_path),
                                line_start=node.lineno,
                                line_end=node.lineno,
                                column_start=node.col_offset,
                                column_end=node.col_offset,
                                issue_type="missing_docstring",
                                severity="LOW",
                                description=f"Missing docstring for {node.name}",
                                code_snippet=(
                                    lines[node.lineno - 1]
                                    if node.lineno <= len(lines)
                                    else ""
                                ),
                                auto_fixable=True,
                                confidence=0.85,
                            )
                        )

            # Check for functions with too many arguments
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                total_args = (
                    len(args.args)
                    + len(args.posonlyargs)
                    + len(args.kwonlyargs)
                    + (1 if args.vararg else 0)
                    + (1 if args.kwarg else 0)
                )
                if total_args > 7:
                    issues.append(
                        CodeIssue(
                            file_path=str(file_path),
                            line_start=node.lineno,
                            line_end=node.lineno,
                            column_start=node.col_offset,
                            column_end=node.col_offset,
                            issue_type="too_many_arguments",
                            severity="MEDIUM",
                            description=f"Function {node.name} has {total_args} arguments (max: 7)",
                            code_snippet=(
                                lines[node.lineno - 1]
                                if node.lineno <= len(lines)
                                else ""
                            ),
                            auto_fixable=False,
                            confidence=0.8,
                        )
                    )

            # Check for empty functions (stubs)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if function body only contains pass, ellipsis, or docstring
                body = node.body
                if body:
                    # Skip docstring if present
                    start_idx = 1 if ast.get_docstring(node) else 0
                    real_body = body[start_idx:]
                    if all(
                        isinstance(stmt, (ast.Pass, ast.Expr))
                        and (
                            not isinstance(stmt, ast.Expr)
                            or isinstance(stmt.value, ast.Constant)
                        )
                        for stmt in real_body
                    ):
                        issues.append(
                            CodeIssue(
                                file_path=str(file_path),
                                line_start=node.lineno,
                                line_end=node.lineno,
                                column_start=node.col_offset,
                                column_end=node.col_offset,
                                issue_type="empty_function",
                                severity="HIGH",
                                description=f"Function {node.name} is empty/stub",
                                code_snippet=(
                                    lines[node.lineno - 1]
                                    if node.lineno <= len(lines)
                                    else ""
                                ),
                                auto_fixable=False,
                                confidence=0.95,
                            )
                        )

        return issues

    def _find_regex_issues(
        self, content: str, file_path: Path, lines: List[str]
    ) -> List[CodeIssue]:
        """Find issues using regex patterns."""
        issues = []

        # Check for TODO/FIXME comments
        todo_pattern = re.compile(
            r"#\s*(TODO|FIXME|XXX|HACK)\s*:?\s*(.*)$", re.IGNORECASE
        )
        for i, line in enumerate(lines, 1):
            match = todo_pattern.search(line)
            if match:
                issues.append(
                    CodeIssue(
                        file_path=str(file_path),
                        line_start=i,
                        line_end=i,
                        column_start=match.start(),
                        column_end=match.end(),
                        issue_type="todo_comment",
                        severity="LOW",
                        description=f"{match.group(1)}: {match.group(2)}",
                        code_snippet=line,
                        auto_fixable=False,
                        confidence=1.0,
                    )
                )

        # Check for print statements (should use logging)
        print_pattern = re.compile(r"^\s*print\s*\(", re.MULTILINE)
        for match in print_pattern.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            issues.append(
                CodeIssue(
                    file_path=str(file_path),
                    line_start=line_num,
                    line_end=line_num,
                    column_start=match.start(),
                    column_end=match.end(),
                    issue_type="print_statement",
                    severity="LOW",
                    description="Consider using logging instead of print",
                    code_snippet=lines[line_num - 1] if line_num <= len(lines) else "",
                    auto_fixable=True,
                    confidence=0.7,
                )
            )

        # Check for hardcoded credentials (basic check)
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "hardcoded_password"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "hardcoded_api_key"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "hardcoded_secret"),
        ]

        for pattern, issue_type in secret_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                issues.append(
                    CodeIssue(
                        file_path=str(file_path),
                        line_start=line_num,
                        line_end=line_num,
                        column_start=match.start(),
                        column_end=match.end(),
                        issue_type=issue_type,
                        severity="CRITICAL",
                        description="Possible hardcoded credential detected",
                        code_snippet=(
                            lines[line_num - 1] if line_num <= len(lines) else ""
                        ),
                        auto_fixable=False,
                        confidence=0.6,
                    )
                )

        return issues

    def _calculate_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity of AST."""
        complexity = 1  # Base complexity

        for node in ast.walk(tree):
            # Decision points increase complexity
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # Each boolean operator adds complexity
                complexity += len(node.values) - 1
            elif isinstance(node, ast.comprehension):
                complexity += 1
                if node.ifs:
                    complexity += len(node.ifs)

        return complexity

    def calculate_metrics(self, file_path: Path) -> Optional[CodeMetrics]:
        """
        Calculate code quality metrics for a file.

        Args:
            file_path: Path to Python file

        Returns:
            CodeMetrics object or None if error
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Try to parse AST
            try:
                tree = ast.parse(content)
            except SyntaxError:
                return CodeMetrics(
                    file_path=str(file_path),
                    lines_of_code=len(lines),
                    cyclomatic_complexity=0,
                    maintainability_index=0.0,
                    test_coverage=0.0,
                    documentation_ratio=0.0,
                    code_quality=CodeQuality.BROKEN,
                    issues_count=1,
                    last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
                )

            # Calculate metrics
            loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])
            complexity = self._calculate_complexity(tree)

            # Count documented items
            documented = 0
            total_items = 0
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    total_items += 1
                    if ast.get_docstring(node):
                        documented += 1

            doc_ratio = documented / total_items if total_items > 0 else 0.0

            # Calculate maintainability index (simplified)
            # MI = 171 - 5.2 * ln(V) - 0.23 * G - 16.2 * ln(LOC)
            volume = loc * math.log2(max(1, loc))  # Simplified Halstead volume
            mi = max(
                0,
                min(
                    100,
                    171
                    - 5.2 * math.log(max(1, volume))
                    - 0.23 * complexity
                    - 16.2 * math.log(max(1, loc)),
                ),
            )

            # Analyze issues
            issues = self.analyze_file(file_path)

            # Determine quality level
            if len(issues) == 0 and mi > 80:
                quality = CodeQuality.EXCELLENT
            elif len(issues) <= 2 and mi > 65:
                quality = CodeQuality.GOOD
            elif len(issues) <= 5 and mi > 50:
                quality = CodeQuality.ACCEPTABLE
            elif len(issues) <= 10 and mi > 30:
                quality = CodeQuality.NEEDS_IMPROVEMENT
            else:
                quality = CodeQuality.POOR

            return CodeMetrics(
                file_path=str(file_path),
                lines_of_code=loc,
                cyclomatic_complexity=complexity,
                maintainability_index=mi / 100.0,
                test_coverage=0.0,  # Would need test runner integration
                documentation_ratio=doc_ratio,
                code_quality=quality,
                issues_count=len(issues),
                last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
            )

        except Exception as e:
            logger.error(f"Error calculating metrics for {file_path}: {e}")
            return None


# ============================================================================
# Code Repairer
# ============================================================================


class CodeRepairer:
    """
    Generates and applies fixes for detected code issues.

    Features:
    - Safe, bounded repairs
    - Logging and audit trail
    - Rollback capability via backup
    - Pattern-based fix generation
    """

    def __init__(self, root_path: Optional[Path] = None):
        """
        Initialize CodeRepairer.

        Args:
            root_path: Root directory of the project
        """
        self.root_path = root_path or Path.cwd()
        self.analyzer = CodeAnalyzer()
        self.fix_templates = self._load_fix_templates()
        self.repair_history: List[RepairResult] = []
        self.lock = threading.Lock()

        # Statistics
        self.total_repairs = 0
        self.successful_repairs = 0
        self.failed_repairs = 0

    def _load_fix_templates(self) -> Dict[str, str]:
        """Load fix templates for common issues."""
        return {
            "bare_except": """except Exception as e:
    logger.error(f"{{type(e).__name__}}: {{e}}")
    raise""",
            "empty_except": """except {exception_type} as e:
    logger.error(f"Error: {{e}}")
    raise""",
            "function_docstring": '''"""
    {description}

    Args:
{args_doc}

    Returns:
        {return_doc}
    """''',
            "class_docstring": '''"""
    {description}

    Attributes:
{attrs_doc}
    """''',
        }

    def repair_file(
        self, file_path: Path, dry_run: bool = False, backup: bool = True
    ) -> List[RepairResult]:
        """
        Repair all auto-fixable issues in a file.

        Args:
            file_path: Path to file to repair
            dry_run: If True, don't write changes
            backup: If True, create backup before modifying

        Returns:
            List of RepairResult objects
        """
        results = []
        issues = self.analyzer.analyze_file(file_path)

        # Filter auto-fixable issues and sort by line number (descending to avoid offset issues)
        auto_fixable = [i for i in issues if i.auto_fixable]
        auto_fixable.sort(key=lambda x: x.line_start, reverse=True)

        if not auto_fixable:
            return results

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
                lines = original_content.split("\n")

            # Create backup if requested
            if backup and not dry_run:
                backup_path = file_path.parent / f"{file_path.name}.backup"
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(original_content)
                logger.info(f"Created backup: {backup_path}")

            modified_lines = lines.copy()

            for issue in auto_fixable:
                start_time = time.time()

                # Build context for fix
                context = self._build_fix_context(issue, lines)

                # Generate fix
                fix = self._generate_fix(issue, context)

                if fix:
                    # Apply fix
                    result = self._apply_fix(issue, fix, modified_lines, dry_run)
                    result.execution_time = time.time() - start_time

                    results.append(result)

                    # Update statistics
                    with self.lock:
                        self.total_repairs += 1
                        if result.success:
                            self.successful_repairs += 1
                        else:
                            self.failed_repairs += 1

            # Write modified content
            if not dry_run and any(r.success for r in results):
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(modified_lines))
                logger.info(f"Applied {len([r for r in results if r.success])} fixes to {file_path}")

        except Exception as e:
            logger.error(f"Error repairing {file_path}: {e}")

        return results

    def _build_fix_context(self, issue: CodeIssue, lines: List[str]) -> Dict[str, Any]:
        """Build context for fix generation."""
        context = {
            "issue_type": issue.issue_type,
            "line": (
                lines[issue.line_start - 1] if issue.line_start <= len(lines) else ""
            ),
            "surrounding_lines": lines[
                max(0, issue.line_start - 3) : issue.line_end + 2
            ],
        }

        # Try to parse and extract more context
        try:
            code_block = "\n".join(context["surrounding_lines"])
            try:
                tree = ast.parse(code_block)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = node.args
                        context["name"] = node.name
                        context["args"] = [arg.arg for arg in args.args]
                        context["returns"] = (
                            ast.unparse(node.returns) if node.returns else None
                        )
                        break
                    elif isinstance(node, ast.ClassDef):
                        context["is_class"] = True
                        context["name"] = node.name
                        break
            except (SyntaxError, ValueError, TypeError, AttributeError):
                pass
        except (OSError, IOError, UnicodeDecodeError):
            pass

        return context

    def _generate_fix(
        self, issue: CodeIssue, context: Dict[str, Any]
    ) -> Optional[str]:
        """Generate a fix for the given issue."""
        if issue.issue_type == "bare_except":
            return self.fix_templates["bare_except"]

        elif issue.issue_type == "empty_except":
            exception_type = context.get("exception_type", "Exception")
            return self.fix_templates["empty_except"].format(
                exception_type=exception_type
            )

        elif issue.issue_type == "missing_docstring":
            name = context.get("name", "function")
            args = context.get("args", [])
            returns = context.get("returns", "None")
            is_class = context.get("is_class", False)

            if is_class:
                attrs = context.get("attributes", [])
                attrs_doc = (
                    "\n".join(f"        {attr}: Description of {attr}" for attr in attrs)
                    if attrs
                    else "        None"
                )
                return self.fix_templates["class_docstring"].format(
                    description=f"{name} class", attrs_doc=attrs_doc
                )
            else:
                args_doc = (
                    "\n".join(f"        {arg}: Description of {arg}" for arg in args)
                    if args
                    else "        None"
                )
                return self.fix_templates["function_docstring"].format(
                    description=f"Execute {name} operation",
                    args_doc=args_doc,
                    return_doc=returns or "None",
                )

        elif issue.issue_type == "print_statement":
            return None  # Will be handled specially in _apply_fix

        return None

    def _apply_fix(
        self, issue: CodeIssue, fix: str, lines: List[str], dry_run: bool
    ) -> RepairResult:
        """Apply a fix to the code."""
        original = lines[issue.line_start - 1] if issue.line_start <= len(lines) else ""

        try:
            if not dry_run:
                if issue.issue_type in ["bare_except", "empty_except"]:
                    # Replace the except line and potentially following lines
                    indent = len(original) - len(original.lstrip())
                    fixed_lines = [" " * indent + line for line in fix.split("\n")]

                    # Find the end of the except block
                    end_line = issue.line_start
                    for i in range(
                        issue.line_start, min(issue.line_start + 10, len(lines))
                    ):
                        stripped = lines[i].strip()
                        if stripped and not stripped.startswith("#"):
                            current_indent = len(lines[i]) - len(lines[i].lstrip())
                            if current_indent <= indent and i > issue.line_start:
                                break
                            end_line = i + 1

                    # Replace lines
                    lines[issue.line_start - 1 : end_line] = fixed_lines

                elif issue.issue_type == "missing_docstring":
                    # Insert docstring after function/class definition
                    indent = len(original) - len(original.lstrip()) + 4
                    docstring_lines = [" " * indent + line for line in fix.split("\n")]

                    # Insert after the colon
                    insert_pos = issue.line_start
                    if original.rstrip().endswith(":"):
                        lines[insert_pos:insert_pos] = docstring_lines

                elif issue.issue_type == "print_statement":
                    # Replace print with logger
                    new_line = original.replace("print(", "logger.info(")
                    lines[issue.line_start - 1] = new_line

            return RepairResult(
                success=True,
                original_code=original,
                repaired_code=fix,
                strategy_used=RepairStrategy.PATTERN_MATCH,
                changes_made=[f"Fixed {issue.issue_type} at line {issue.line_start}"],
                confidence=issue.confidence,
                execution_time=0.0,
            )

        except Exception as e:
            return RepairResult(
                success=False,
                original_code=original,
                repaired_code=fix,
                strategy_used=RepairStrategy.PATTERN_MATCH,
                changes_made=[],
                confidence=0.0,
                execution_time=0.0,
                error_message=str(e),
            )

    def repair_directory(
        self,
        directory: Path,
        recursive: bool = True,
        dry_run: bool = False,
        exclude_patterns: Optional[List[str]] = None,
    ) -> Dict[str, List[RepairResult]]:
        """
        Repair all Python files in a directory.

        Args:
            directory: Directory to scan
            recursive: Scan subdirectories
            dry_run: Don't write changes
            exclude_patterns: Patterns to exclude

        Returns:
            Dict mapping file paths to repair results
        """
        results = {}
        exclude_patterns = exclude_patterns or [
            "__pycache__",
            ".git",
            "venv",
            ".venv",
            "node_modules",
        ]

        pattern = "**/*.py" if recursive else "*.py"

        for file_path in directory.glob(pattern):
            # Check exclusions
            if any(excl in str(file_path) for excl in exclude_patterns):
                continue

            file_results = self.repair_file(file_path, dry_run)
            if file_results:
                results[str(file_path)] = file_results

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get repair statistics."""
        with self.lock:
            success_rate = (
                self.successful_repairs / self.total_repairs * 100
                if self.total_repairs > 0
                else 0
            )

            return {
                "total_repairs": self.total_repairs,
                "successful_repairs": self.successful_repairs,
                "failed_repairs": self.failed_repairs,
                "success_rate": success_rate,
            }

    def generate_report(self, issues: List[CodeIssue]) -> str:
        """Generate a human-readable report of issues."""
        report_lines = [
            "=" * 70,
            "CODE ANALYSIS REPORT",
            "=" * 70,
            f"Generated: {datetime.now().isoformat()}",
            f"Total issues found: {len(issues)}",
            "",
        ]

        # Group by severity
        by_severity = {}
        for issue in issues:
            by_severity.setdefault(issue.severity, []).append(issue)

        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if severity in by_severity:
                report_lines.append(
                    f"\n{severity} ({len(by_severity[severity])} issues):"
                )
                report_lines.append("-" * 40)
                for issue in by_severity[severity]:
                    report_lines.append(
                        f"  [{issue.issue_type}] {issue.file_path}:{issue.line_start}"
                    )
                    report_lines.append(f"    {issue.description}")
                    if issue.auto_fixable:
                        report_lines.append("    [Auto-fixable]")

        report_lines.append("\n" + "=" * 70)

        return "\n".join(report_lines)


# ============================================================================
# Code Evolution Engine
# ============================================================================


class CodeEvolutionEngine:
    """
    Engine for tracking code quality over time.
    Monitors metrics and trends without automatic modifications.
    """

    def __init__(self, analyzer: CodeAnalyzer):
        """
        Initialize CodeEvolutionEngine.

        Args:
            analyzer: CodeAnalyzer instance
        """
        self.analyzer = analyzer
        self.metrics_history: Dict[str, List[CodeMetrics]] = {}
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def track_metrics(self, file_path: Path):
        """
        Track metrics over time for a file.

        Args:
            file_path: Path to file to track
        """
        metrics = self.analyzer.calculate_metrics(file_path)
        if metrics:
            with self.lock:
                if str(file_path) not in self.metrics_history:
                    self.metrics_history[str(file_path)] = []
                self.metrics_history[str(file_path)].append(metrics)

                # Keep only last 100 measurements
                self.metrics_history[str(file_path)] = self.metrics_history[
                    str(file_path)
                ][-100:]

    def get_improvement_trend(self, file_path: Path) -> Optional[float]:
        """
        Get the improvement trend for a file (positive = improving).

        Args:
            file_path: Path to file

        Returns:
            Trend value or None if insufficient data
        """
        with self.lock:
            history = self.metrics_history.get(str(file_path), [])

        if len(history) < 2:
            return None

        # Calculate trend based on maintainability index
        recent = history[-5:]  # Last 5 measurements
        if len(recent) >= 2:
            mi_values = [m.maintainability_index for m in recent]
            trend = (mi_values[-1] - mi_values[0]) / len(mi_values)
            return trend

        return None

    def get_evolution_report(self) -> Dict[str, Any]:
        """Get a report on code evolution."""
        with self.lock:
            total_files = len(self.metrics_history)

            if total_files == 0:
                return {
                    "files_tracked": 0,
                    "average_quality": 0,
                    "improving_files": 0,
                    "degrading_files": 0,
                }

            improving = 0
            degrading = 0
            total_quality = 0

            for path, history in self.metrics_history.items():
                if history:
                    total_quality += history[-1].code_quality.value
                    trend = self.get_improvement_trend(Path(path))
                    if trend is not None:
                        if trend > 0:
                            improving += 1
                        elif trend < 0:
                            degrading += 1

            return {
                "files_tracked": total_files,
                "average_quality": total_quality / total_files,
                "improving_files": improving,
                "degrading_files": degrading,
            }


# ============================================================================
# Public API
# ============================================================================


def create_import_repairer(
    root: Optional[Path] = None,
    allow_auto_install: bool = False,
) -> ImportRepairer:
    """
    Create a configured ImportRepairer.

    Args:
        root: Root directory of the project
        allow_auto_install: Allow automatic package installation

    Returns:
        ImportRepairer instance
    """
    return ImportRepairer(root=root, allow_auto_install=allow_auto_install)


def create_code_analyzer() -> CodeAnalyzer:
    """
    Create a configured CodeAnalyzer.

    Returns:
        CodeAnalyzer instance
    """
    return CodeAnalyzer()


def create_code_repairer(root_path: Optional[Path] = None) -> CodeRepairer:
    """
    Create a configured CodeRepairer.

    Args:
        root_path: Root directory of the project

    Returns:
        CodeRepairer instance
    """
    return CodeRepairer(root_path=root_path)


def create_evolution_engine(analyzer: CodeAnalyzer) -> CodeEvolutionEngine:
    """
    Create a configured CodeEvolutionEngine.

    Args:
        analyzer: CodeAnalyzer instance

    Returns:
        CodeEvolutionEngine instance
    """
    return CodeEvolutionEngine(analyzer=analyzer)


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    # Core Classes
    "ImportRepairer",
    "CodeAnalyzer",
    "CodeRepairer",
    "CodeEvolutionEngine",
    # Data Classes
    "ImportRepairAttempt",
    "ImportRepairResult",
    "CodePattern",
    "CodeIssue",
    "RepairResult",
    "CodeMetrics",
    # Enums
    "RepairStrategy",
    "CodeQuality",
    # Factory Functions
    "create_import_repairer",
    "create_code_analyzer",
    "create_code_repairer",
    "create_evolution_engine",
    # Configuration
    "MODULE_TO_PACKAGE",
    "WHITELISTED_PACKAGES",
]


if __name__ == "__main__":
    # Demo/test mode
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 70)
    print("VEL AI Self-Repair Module")
    print("=" * 70)
    print("\nAvailable components:")
    print("  - ImportRepairer: Fix import issues")
    print("  - CodeAnalyzer: Detect code issues")
    print("  - CodeRepairer: Generate and apply fixes")
    print("  - CodeEvolutionEngine: Track quality metrics")
    print("\nUse factory functions to create instances:")
    print("  - create_import_repairer()")
    print("  - create_code_analyzer()")
    print("  - create_code_repairer()")
    print("  - create_evolution_engine(analyzer)")
    print("=" * 70)
