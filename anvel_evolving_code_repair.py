#!/usr/bin/env python3
"""
ANVEL Self-Evolving Code Repair System
======================================

Phase 3.2 Implementation: Autonomous code improvement with intelligent repair.

This module implements:
- Pattern-based code repair with learning from past fixes
- Semantic code understanding through AST analysis
- Intelligent fix generation using pattern matching and code synthesis
- Self-improvement through fix success tracking
- Code quality metrics and improvement suggestions

NO EXTERNAL API DEPENDENCIES - Uses local pattern-based intelligence.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("anvel.evolving_code_repair")


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


class ASTPatternMatcher:
    """
    Matches AST patterns for intelligent code analysis.
    Provides semantic understanding of code structure.
    """

    def __init__(self):
        self.patterns: Dict[str, List[ast.AST]] = {}
        self._build_patterns()

    def _build_patterns(self):
        """Build AST patterns for common issues"""
        # Pattern: Empty except block
        self.patterns["empty_except"] = []

        # Pattern: Unused variable
        self.patterns["unused_variable"] = []

        # Pattern: Missing return type hint
        self.patterns["missing_return_type"] = []

    def find_pattern(self, tree: ast.AST, pattern_name: str) -> List[ast.AST]:
        """Find all occurrences of a pattern in AST"""
        matches = []

        for node in ast.walk(tree):
            if pattern_name == "empty_except":
                if isinstance(node, ast.ExceptHandler):
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        matches.append(node)

            elif pattern_name == "bare_except":
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        matches.append(node)

            elif pattern_name == "missing_docstring":
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    if not ast.get_docstring(node):
                        matches.append(node)

            elif pattern_name == "nested_try":
                if isinstance(node, ast.Try):
                    for handler in node.handlers:
                        for child in ast.walk(handler):
                            if isinstance(child, ast.Try) and child != node:
                                matches.append(node)
                                break

            elif pattern_name == "too_many_arguments":
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
                        matches.append(node)

            elif pattern_name == "magic_number":
                if isinstance(node, ast.Constant):
                    if isinstance(node.value, (int, float)):
                        if node.value not in (0, 1, -1, 2, 10, 100):
                            matches.append(node)

            elif pattern_name == "global_variable":
                if isinstance(node, ast.Global):
                    matches.append(node)

        return matches

    def analyze_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity of AST"""
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

    def extract_function_signature(self, node: ast.FunctionDef) -> Dict[str, Any]:
        """Extract function signature details"""
        args = node.args

        return {
            "name": node.name,
            "args": [arg.arg for arg in args.args],
            "defaults": len(args.defaults),
            "kwargs": args.kwarg.arg if args.kwarg else None,
            "varargs": args.vararg.arg if args.vararg else None,
            "returns": ast.unparse(node.returns) if node.returns else None,
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "docstring": ast.get_docstring(node),
            "complexity": self._function_complexity(node),
        }

    def _function_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate complexity for a single function"""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity


class CodeSynthesizer:
    """
    Synthesizes code fixes based on patterns and context.
    Uses template-based generation with intelligent filling.
    """

    def __init__(self):
        self.templates: Dict[str, str] = self._load_templates()
        self.fix_history: List[Dict[str, Any]] = []

    def _load_templates(self) -> Dict[str, str]:
        """Load fix templates"""
        return {
            "exception_handler": """except {exception_type} as e:
    logger.error(f"{{type(e).__name__}}: {{e}}")
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
            "type_hint_function": """def {name}({args}) -> {return_type}:""",
            "null_check": """if {var} is None:
    raise ValueError("{var} cannot be None")""",
            "bounds_check": """if not ({lower} <= {var} <= {upper}):
    raise ValueError(f"{var} must be between {lower} and {upper}, got {{{var}}}")""",
            "retry_wrapper": """@retry(max_attempts={attempts}, delay={delay})
def {name}({args}):""",
            "logging_wrapper": """logger.debug(f"Entering {name} with args: {{{args_str}}}")
try:
    result = {original_call}
    logger.debug(f"Exiting {name} with result: {{result}}")
    return result
except Exception as e:
    logger.error(f"Error in {name}: {{e}}")
    raise""",
            "property_getter": '''@property
def {name}(self) -> {type_hint}:
    """Get {description}."""
    return self._{name}''',
            "property_setter": '''@{name}.setter
def {name}(self, value: {type_hint}) -> None:
    """Set {description}."""
    self._{name} = value''',
            "context_manager": '''def __enter__(self):
    """Enter context manager."""
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    """Exit context manager."""
    self.close()
    return False''',
            "iterator": '''def __iter__(self):
    """Return iterator."""
    return iter(self._items)

def __next__(self):
    """Get next item."""
    return next(self._iterator)''',
        }

    def synthesize_fix(
        self, issue: CodeIssue, context: Dict[str, Any]
    ) -> Optional[str]:
        """Synthesize a fix for the given issue"""

        if issue.issue_type == "bare_except":
            return self._fix_bare_except(issue, context)

        elif issue.issue_type == "empty_except":
            return self._fix_empty_except(issue, context)

        elif issue.issue_type == "missing_docstring":
            return self._fix_missing_docstring(issue, context)

        elif issue.issue_type == "missing_type_hint":
            return self._fix_missing_type_hint(issue, context)

        elif issue.issue_type == "unused_import":
            return self._fix_unused_import(issue, context)

        elif issue.issue_type == "undefined_variable":
            return self._fix_undefined_variable(issue, context)

        elif issue.issue_type == "too_complex":
            return self._fix_too_complex(issue, context)

        return None

    def _fix_bare_except(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Fix bare except clause"""
        # Analyze what exceptions might be raised
        exception_type = context.get("likely_exception", "Exception")
        template = self.templates["exception_handler"]
        return template.format(exception_type=exception_type)

    def _fix_empty_except(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Fix empty except block"""
        exception_type = context.get("exception_type", "Exception")
        action = context.get("recommended_action", "log_and_raise")

        if action == "log_and_raise":
            return f"""except {exception_type} as e:
    logger.error(f"Error: {{e}}")
    raise"""
        elif action == "log_and_continue":
            return f"""except {exception_type} as e:
    logger.warning(f"Handled error: {{e}}")"""
        else:
            return f"""except {exception_type} as e:
    logger.error(f"{{type(e).__name__}}: {{e}}")
    raise"""

    def _fix_missing_docstring(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Generate docstring for function/class"""
        name = context.get("name", "function")
        args = context.get("args", [])
        returns = context.get("returns", "None")
        is_class = context.get("is_class", False)

        if is_class:
            # Generate class docstring
            attrs = context.get("attributes", [])
            attrs_doc = (
                "\n".join(f"        {attr}: Description of {attr}" for attr in attrs)
                if attrs
                else "        None"
            )

            template = self.templates["class_docstring"]
            return template.format(description=f"{name} class", attrs_doc=attrs_doc)
        else:
            # Generate function docstring
            args_doc = (
                "\n".join(f"        {arg}: Description of {arg}" for arg in args)
                if args
                else "        None"
            )

            template = self.templates["function_docstring"]
            return template.format(
                description=f"Execute {name} operation",
                args_doc=args_doc,
                return_doc=returns or "None",
            )

    def _fix_missing_type_hint(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Add type hints to function"""
        name = context.get("name", "function")
        args = context.get("args", [])
        inferred_types = context.get("inferred_types", {})
        return_type = context.get("return_type", "None")

        typed_args = []
        for arg in args:
            arg_type = inferred_types.get(arg, "Any")
            typed_args.append(f"{arg}: {arg_type}")

        args_str = ", ".join(typed_args)
        return f"def {name}({args_str}) -> {return_type}:"

    def _fix_unused_import(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Remove unused import"""
        # Return empty to indicate removal
        return ""

    def _fix_undefined_variable(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Fix undefined variable"""
        var_name = context.get("variable", "var")
        likely_type = context.get("likely_type", "None")

        if likely_type == "list":
            return f"{var_name} = []"
        elif likely_type == "dict":
            return f"{var_name} = {{}}"
        elif likely_type == "str":
            return f'{var_name} = ""'
        elif likely_type == "int":
            return f"{var_name} = 0"
        elif likely_type == "float":
            return f"{var_name} = 0.0"
        elif likely_type == "bool":
            return f"{var_name} = False"
        else:
            return f"{var_name} = None"

    def _fix_too_complex(self, issue: CodeIssue, context: Dict[str, Any]) -> str:
        """Suggest refactoring for complex code"""
        # This returns a comment with suggestions
        suggestions = [
            "# REFACTORING SUGGESTION:",
            "# This function has high cyclomatic complexity.",
            "# Consider:",
            "#   1. Breaking into smaller functions",
            "#   2. Using early returns to reduce nesting",
            "#   3. Using dict dispatch instead of multiple if/elif",
            "#   4. Extracting helper methods for complex conditions",
        ]
        return "\n".join(suggestions)


class FixLearner:
    """
    Learns from successful and failed fixes to improve repair strategies.
    Maintains a knowledge base of patterns and their effectiveness.
    """

    def __init__(self, knowledge_base_path: Optional[Path] = None):
        self.knowledge_base_path = knowledge_base_path or Path(
            "fix_knowledge_base.json"
        )
        self.patterns: Dict[str, CodePattern] = {}
        self.fix_history: List[Dict[str, Any]] = []
        self.lock = threading.RLock()  # Use RLock to allow reentrant locking
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """Load knowledge base from disk"""
        if self.knowledge_base_path.exists():
            try:
                with open(self.knowledge_base_path, "r") as f:
                    data = json.load(f)
                    for name, pattern_data in data.get("patterns", {}).items():
                        self.patterns[name] = CodePattern(
                            name=pattern_data["name"],
                            description=pattern_data["description"],
                            pattern_ast=pattern_data.get("pattern_ast"),
                            pattern_regex=pattern_data.get("pattern_regex"),
                            fix_template=pattern_data["fix_template"],
                            confidence=pattern_data["confidence"],
                            success_count=pattern_data.get("success_count", 0),
                            failure_count=pattern_data.get("failure_count", 0),
                        )
                    self.fix_history = data.get("history", [])
            except Exception as e:
                logger.warning(f"Could not load knowledge base: {e}")

        # Add default patterns
        self._add_default_patterns()

    def _add_default_patterns(self):
        """Add default repair patterns"""
        defaults = [
            CodePattern(
                name="bare_except_to_specific",
                description="Convert bare except to specific exception",
                pattern_ast="ExceptHandler(type=None)",
                pattern_regex=r"except\s*:",
                fix_template="except Exception as e:\n    logger.error(f'Error: {e}')\n    raise",
                confidence=0.95,
            ),
            CodePattern(
                name="add_missing_import",
                description="Add missing import statement",
                pattern_ast=None,
                pattern_regex=r"NameError:.*'(\w+)'",
                fix_template="from {module} import {name}",
                confidence=0.8,
            ),
            CodePattern(
                name="fix_indentation",
                description="Fix indentation errors",
                pattern_ast=None,
                pattern_regex=r"IndentationError",
                fix_template="{fixed_code}",
                confidence=0.7,
            ),
            CodePattern(
                name="add_self_parameter",
                description="Add missing self parameter to method",
                pattern_ast="FunctionDef in ClassDef without self",
                pattern_regex=r"def\s+(\w+)\s*\(\s*\)",
                fix_template="def {name}(self):",
                confidence=0.9,
            ),
            CodePattern(
                name="fix_attribute_error",
                description="Fix attribute access errors",
                pattern_ast=None,
                pattern_regex=r"AttributeError:.*'(\w+)'.*'(\w+)'",
                fix_template="# Check if attribute exists or initialize it",
                confidence=0.6,
            ),
        ]

        for pattern in defaults:
            if pattern.name not in self.patterns:
                self.patterns[pattern.name] = pattern

    def save_knowledge_base(self):
        """Save knowledge base to disk"""
        with self.lock:
            data = {
                "patterns": {
                    name: {
                        "name": p.name,
                        "description": p.description,
                        "pattern_ast": p.pattern_ast,
                        "pattern_regex": p.pattern_regex,
                        "fix_template": p.fix_template,
                        "confidence": p.confidence,
                        "success_count": p.success_count,
                        "failure_count": p.failure_count,
                    }
                    for name, p in self.patterns.items()
                },
                "history": self.fix_history[-1000:],  # Keep last 1000 entries
            }

            try:
                with open(self.knowledge_base_path, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Could not save knowledge base: {e}")

    def record_fix_attempt(
        self, issue: CodeIssue, result: RepairResult, pattern_used: Optional[str] = None
    ):
        """Record a fix attempt for learning"""
        with self.lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "issue_type": issue.issue_type,
                "file": issue.file_path,
                "success": result.success,
                "strategy": result.strategy_used.name,
                "pattern": pattern_used,
                "confidence": result.confidence,
                "execution_time": result.execution_time,
            }

            self.fix_history.append(entry)

            # Update pattern statistics
            if pattern_used and pattern_used in self.patterns:
                pattern = self.patterns[pattern_used]
                if result.success:
                    pattern.success_count += 1
                else:
                    pattern.failure_count += 1

            # Save periodically
            if len(self.fix_history) % 10 == 0:
                self.save_knowledge_base()

    def get_best_pattern(self, issue_type: str) -> Optional[CodePattern]:
        """Get the best pattern for an issue type based on success rate"""
        candidates = [
            p
            for p in self.patterns.values()
            if issue_type.lower() in p.name.lower()
            or issue_type.lower() in p.description.lower()
        ]

        if not candidates:
            return None

        # Sort by success rate, then by confidence
        candidates.sort(key=lambda p: (p.success_rate, p.confidence), reverse=True)
        return candidates[0]

    def learn_new_pattern(
        self, name: str, issue_code: str, fix_code: str, description: str = ""
    ):
        """Learn a new pattern from a successful fix"""
        with self.lock:
            # Create pattern from example
            pattern = CodePattern(
                name=name,
                description=description or f"Learned pattern: {name}",
                pattern_ast=None,
                pattern_regex=self._extract_pattern(issue_code),
                fix_template=fix_code,
                confidence=0.5,  # Start with moderate confidence
                success_count=1,
                failure_count=0,
            )

            self.patterns[name] = pattern
            self.save_knowledge_base()

            logger.info(f"Learned new pattern: {name}")

    def _extract_pattern(self, code: str) -> str:
        """Extract a regex pattern from code"""
        # Escape special regex characters but leave word boundaries
        escaped = re.escape(code)
        # Allow variable content in strings
        escaped = re.sub(r"\\\w+", r"\\w+", escaped)
        return escaped


class SelfEvolvingCodeRepairer:
    """
    Main class for self-evolving code repair.
    Integrates pattern matching, code synthesis, and learning.
    """

    def __init__(
        self,
        root_path: Optional[Path] = None,
        knowledge_base_path: Optional[Path] = None,
    ):
        self.root_path = root_path or Path(".")
        self.ast_matcher = ASTPatternMatcher()
        self.synthesizer = CodeSynthesizer()
        self.learner = FixLearner(knowledge_base_path)
        self.repair_history: List[RepairResult] = []
        self.lock = threading.Lock()

        # Statistics
        self.total_repairs = 0
        self.successful_repairs = 0
        self.failed_repairs = 0

    def analyze_file(self, file_path: Path) -> List[CodeIssue]:
        """Analyze a file for issues"""
        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Try to parse AST
            try:
                tree = ast.parse(content, filename=str(file_path))

                # Find pattern-based issues
                issues.extend(self._find_ast_issues(tree, file_path, lines))

                # Analyze complexity
                complexity = self.ast_matcher.analyze_complexity(tree)
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
                        auto_fixable=True,
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
        """Find issues using AST analysis"""
        issues = []

        # Check for bare except
        for node in self.ast_matcher.find_pattern(tree, "bare_except"):
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
        for node in self.ast_matcher.find_pattern(tree, "empty_except"):
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
                        lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    ),
                    auto_fixable=True,
                    confidence=0.9,
                )
            )

        # Check for missing docstrings
        for node in self.ast_matcher.find_pattern(tree, "missing_docstring"):
            if isinstance(node, ast.ClassDef) or (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not node.name.startswith("_")
            ):
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
                            lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        ),
                        auto_fixable=True,
                        confidence=0.85,
                    )
                )

        # Check for too many arguments
        for node in self.ast_matcher.find_pattern(tree, "too_many_arguments"):
            issues.append(
                CodeIssue(
                    file_path=str(file_path),
                    line_start=node.lineno,
                    line_end=node.lineno,
                    column_start=node.col_offset,
                    column_end=node.col_offset,
                    issue_type="too_many_arguments",
                    severity="MEDIUM",
                    description=f"Function {node.name} has too many arguments",
                    code_snippet=(
                        lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    ),
                    auto_fixable=False,
                    confidence=0.8,
                )
            )

        return issues

    def _find_regex_issues(
        self, content: str, file_path: Path, lines: List[str]
    ) -> List[CodeIssue]:
        """Find issues using regex patterns"""
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

    def repair_file(self, file_path: Path, dry_run: bool = False) -> List[RepairResult]:
        """Repair all auto-fixable issues in a file"""
        results = []
        issues = self.analyze_file(file_path)

        # Filter auto-fixable issues and sort by line number (descending to avoid offset issues)
        auto_fixable = [i for i in issues if i.auto_fixable]
        auto_fixable.sort(key=lambda x: x.line_start, reverse=True)

        if not auto_fixable:
            return results

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            modified_lines = lines.copy()

            for issue in auto_fixable:
                start_time = time.time()

                # Build context for fix
                context = self._build_fix_context(issue, lines)

                # Get best pattern
                pattern = self.learner.get_best_pattern(issue.issue_type)

                # Synthesize fix
                fix = self.synthesizer.synthesize_fix(issue, context)

                if fix:
                    # Apply fix
                    result = self._apply_fix(issue, fix, modified_lines, dry_run)
                    result.execution_time = time.time() - start_time

                    # Record for learning
                    self.learner.record_fix_attempt(
                        issue, result, pattern.name if pattern else None
                    )

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

        except Exception as e:
            logger.error(f"Error repairing {file_path}: {e}")

        return results

    def _build_fix_context(self, issue: CodeIssue, lines: List[str]) -> Dict[str, Any]:
        """Build context for fix synthesis"""
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
            # Parse surrounding code
            code_block = "\n".join(context["surrounding_lines"])
            try:
                tree = ast.parse(code_block)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sig = self.ast_matcher.extract_function_signature(node)
                        context["function"] = sig
                        context["name"] = sig["name"]
                        context["args"] = sig["args"]
                        context["returns"] = sig["returns"]
                        break
                    elif isinstance(node, ast.ClassDef):
                        context["is_class"] = True
                        context["name"] = node.name
                        context["attributes"] = [
                            n.targets[0].attr
                            for n in ast.walk(node)
                            if isinstance(n, ast.Assign)
                            and isinstance(n.targets[0], ast.Attribute)
                        ][
                            :10
                        ]  # Limit to 10 attributes
                        break
            except (SyntaxError, ValueError, TypeError, AttributeError):
                # AST parsing or attribute access error - context may be incomplete
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_EVOLVING_CODE_REPAIR").debug("Exception suppressed in _build_fix_context")
        except (OSError, IOError, UnicodeDecodeError):
            # File reading error - context unavailable
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_EVOLVING_CODE_REPAIR").debug("Exception suppressed in _build_fix_context")

        return context

    def _apply_fix(
        self, issue: CodeIssue, fix: str, lines: List[str], dry_run: bool
    ) -> RepairResult:
        """Apply a fix to the code"""
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

                elif fix == "":
                    # Remove the line (for unused imports)
                    del lines[issue.line_start - 1]

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
        """Repair all Python files in a directory"""
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
        """Get repair statistics"""
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
                "patterns_known": len(self.learner.patterns),
                "fix_history_size": len(self.learner.fix_history),
            }

    def generate_report(self, issues: List[CodeIssue]) -> str:
        """Generate a human-readable report of issues"""
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


class CodeEvolutionEngine:
    """
    Engine for evolving code over time through continuous improvement.
    Tracks code quality metrics and applies incremental improvements.
    """

    def __init__(self, repairer: SelfEvolvingCodeRepairer):
        self.repairer = repairer
        self.metrics_history: Dict[str, List[CodeMetrics]] = {}
        self.improvement_queue: List[Tuple[Path, CodeIssue]] = []
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def calculate_metrics(self, file_path: Path) -> Optional[CodeMetrics]:
        """Calculate code quality metrics for a file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Parse AST
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
            complexity = self.repairer.ast_matcher.analyze_complexity(tree)

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
            import math

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
            issues = self.repairer.analyze_file(file_path)

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

    def track_metrics(self, file_path: Path):
        """Track metrics over time for a file"""
        metrics = self.calculate_metrics(file_path)
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
        """Get the improvement trend for a file (positive = improving)"""
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

    def start_evolution(self, interval: float = 3600.0):
        """Start continuous code evolution process"""
        self.running = True
        self._thread = threading.Thread(
            target=self._evolution_loop, args=(interval,), daemon=True
        )
        self._thread.start()
        logger.info("Code evolution engine started")

    def stop_evolution(self):
        """Stop the evolution process"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Code evolution engine stopped")

    def _evolution_loop(self, interval: float):
        """Main evolution loop"""
        while self.running:
            try:
                # Process improvement queue
                with self.lock:
                    queue_copy = self.improvement_queue.copy()
                    self.improvement_queue.clear()

                for file_path, issue in queue_copy:
                    self.repairer.repair_file(file_path)
                    self.track_metrics(file_path)

            except Exception as e:
                logger.error(f"Error in evolution loop: {e}")

            time.sleep(interval)

    def queue_improvement(self, file_path: Path, issue: CodeIssue):
        """Queue an improvement for processing"""
        with self.lock:
            self.improvement_queue.append((file_path, issue))

    def get_evolution_report(self) -> Dict[str, Any]:
        """Get a report on code evolution"""
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
                "repair_statistics": self.repairer.get_statistics(),
            }


# Factory function for easy instantiation
def create_evolving_repairer(
    root_path: Optional[Path] = None, knowledge_base_path: Optional[Path] = None
) -> Tuple[SelfEvolvingCodeRepairer, CodeEvolutionEngine]:
    """Create a configured self-evolving code repairer with evolution engine"""
    repairer = SelfEvolvingCodeRepairer(root_path, knowledge_base_path)
    engine = CodeEvolutionEngine(repairer)
    return repairer, engine


# Main execution
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 70)
    print("ANVEL Self-Evolving Code Repair System")
    print("=" * 70)

    repairer, engine = create_evolving_repairer()

    # Analyze current directory
    print("\nAnalyzing code...")

    results = repairer.repair_directory(Path("."), dry_run=True)

    total_issues = sum(len(r) for r in results.values())
    print(f"\nFound {total_issues} auto-fixable issues across {len(results)} files")

    # Show statistics
    stats = repairer.get_statistics()
    print("\nStatistics:")
    print(f"  Patterns known: {stats['patterns_known']}")
    print(f"  Fix history: {stats['fix_history_size']} entries")

    print("\n" + "=" * 70)
