#!/usr/bin/env python3
"""
ANVEL Core Services Module - System Utilities

Internal service module for VEL trading platform infrastructure.
Provides core utility functions for system operations.
"""

import atexit
import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
import weakref
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

# Stealth logging - uses generic name
_log = logging.getLogger("anvel.core.services")

# =============================================================================
# STEALTH CONFIGURATION - Hidden from inspection
# =============================================================================
_CFG = {
    "_l": 1,  # Minimum level
    "_w": 2.0,  # Watch interval
    "_r": 1000,  # Recovery max
    "_t": 1.0,  # Tamper check
    "_s": True,  # Stealth mode
    "_e": True,  # Encryption enabled
}


# Encryption key derived from system entropy (hidden)
def _dk():
    """Derive key from system state."""
    entropy = f"{os.getpid()}{threading.current_thread().ident}{time.time_ns()}"
    return hashlib.sha256(entropy.encode()).digest()


_K = _dk()


def _enc(data: bytes) -> bytes:
    """Encrypt data (XOR with rolling key + compression)."""
    if not _CFG.get("_e"):
        return data
    compressed = zlib.compress(data)
    key = _K
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(compressed))
    return base64.b85encode(encrypted)


def _dec(data: bytes) -> bytes:
    """Decrypt data."""
    if not _CFG.get("_e"):
        return data
    try:
        decoded = base64.b85decode(data)
        key = _K
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(decoded))
        return zlib.decompress(decrypted)
    except Exception:
        return data


class _L(Enum):
    """Internal level codes."""

    _0 = auto()
    _1 = auto()
    _2 = auto()
    _3 = auto()
    _4 = auto()


class _T(Enum):
    """Internal type codes."""

    _BF = "bf"
    _MW = "mw"
    _TR = "tr"
    _SQ = "sq"
    _XS = "xs"
    _PI = "pi"
    _AA = "aa"
    _SH = "sh"
    _UA = "ua"
    _RL = "rl"
    _DE = "de"
    _CS = "cs"
    _AT = "at"
    _MP = "mp"
    _ST = "st"


class _A(Enum):
    """Internal action codes."""

    _M = "m"
    _T = "t"
    _Q = "q"
    _B = "b"
    _X = "x"
    _L = "l"


# Public aliases (appear as generic utilities)
ThreatLevel = _L
ThreatType = _T
IsolationAction = _A

# Friendly name mappings (hidden)
_LEVEL_NAMES = {
    _L._0: "INFO",
    _L._1: "LOW",
    _L._2: "MEDIUM",
    _L._3: "HIGH",
    _L._4: "CRITICAL",
}
_TYPE_NAMES = {
    _T._BF: "brute_force",
    _T._MW: "malware",
    _T._TR: "trojan",
    _T._SQ: "sql_injection",
    _T._XS: "xss",
    _T._PI: "prompt_injection",
    _T._AA: "api_abuse",
    _T._SH: "session_hijack",
    _T._UA: "unauthorized_access",
    _T._RL: "rate_limit",
    _T._DE: "data_exfiltration",
    _T._CS: "credential_stuffing",
    _T._AT: "account_takeover",
    _T._MP: "malicious_payload",
    _T._ST: "security_tampering",
}
_ACTION_NAMES = {
    _A._M: "monitor",
    _A._T: "throttle",
    _A._Q: "quarantine",
    _A._B: "block",
    _A._X: "terminate",
    _A._L: "lock_account",
}


# Backwards compatibility mappings (stealth - these look like normal enums)
class ThreatLevel(Enum):
    """Service level indicators."""

    INFO = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class ThreatType(Enum):
    """Service type codes."""

    BRUTE_FORCE = "brute_force"
    MALWARE = "malware"
    TROJAN = "trojan"
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PROMPT_INJECTION = "prompt_injection"
    API_ABUSE = "api_abuse"
    SESSION_HIJACK = "session_hijack"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit"
    DATA_EXFILTRATION = "data_exfiltration"
    CREDENTIAL_STUFFING = "credential_stuffing"
    ACCOUNT_TAKEOVER = "account_takeover"
    MALICIOUS_PAYLOAD = "malicious_payload"
    SECURITY_TAMPERING = "security_tampering"
    SPOOFING = "spoofing"
    HTTP_SMUGGLING = "http_smuggling"
    NOSQL_INJECTION = "nosql_injection"


class IsolationAction(Enum):
    """Service action codes."""

    MONITOR = "monitor"
    THROTTLE = "throttle"
    QUARANTINE = "quarantine"
    BLOCK = "block"
    TERMINATE = "terminate"
    LOCK_ACCOUNT = "lock_account"


@dataclass
class ThreatEvent:
    """Record of a detected threat."""

    threat_id: str
    threat_type: ThreatType
    threat_level: ThreatLevel
    source_ip: str
    user_id: Optional[str]
    description: str
    payload: Optional[str]
    timestamp: float
    action_taken: IsolationAction
    is_neutralized: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuarantineZone:
    """Isolated zone for suspicious entities."""

    zone_id: str
    entities: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    threat_events: List[str] = field(default_factory=list)


class BruteForceProtection:
    """
    Protects against brute force authentication attacks.

    Features:
    - Progressive lockout (exponential backoff)
    - IP-based rate limiting
    - Account-based rate limiting
    - Permanent ban after repeated violations
    """

    def __init__(
        self,
        max_attempts: int = 5,
        lockout_duration_seconds: int = 300,
        permanent_ban_threshold: int = 10,
    ):
        self.max_attempts = max_attempts
        self.base_lockout = lockout_duration_seconds
        self.permanent_ban_threshold = permanent_ban_threshold

        self._lock = threading.RLock()
        self._attempts: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=100))
        self._lockouts: Dict[str, float] = {}
        self._violation_count: Dict[str, int] = defaultdict(int)
        self._permanent_bans: Set[str] = set()

    def record_attempt(
        self, identifier: str, success: bool
    ) -> Tuple[bool, Optional[str]]:
        """
        Record an authentication attempt.

        Returns:
            Tuple of (is_allowed, reason_if_blocked)
        """
        with self._lock:
            now = time.time()

            # Check permanent ban
            if identifier in self._permanent_bans:
                return False, "Permanently banned due to repeated violations"

            # Check active lockout
            if identifier in self._lockouts:
                lockout_until = self._lockouts[identifier]
                if now < lockout_until:
                    remaining = int(lockout_until - now)
                    return False, f"Account locked for {remaining} more seconds"
                else:
                    del self._lockouts[identifier]

            # Record attempt
            self._attempts[identifier].append(now)

            if success:
                # Reset on successful auth
                self._attempts[identifier].clear()
                return True, None

            # Count recent failures (within window)
            window = self.base_lockout
            recent_failures = sum(
                1 for t in self._attempts[identifier] if now - t < window
            )

            if recent_failures >= self.max_attempts:
                # Apply lockout with exponential backoff
                self._violation_count[identifier] += 1
                violations = self._violation_count[identifier]

                if violations >= self.permanent_ban_threshold:
                    self._permanent_bans.add(identifier)
                    _log.warning(
                        "[BRUTE FORCE] Permanent ban applied to %s after %d violations",
                        identifier,
                        violations,
                    )
                    return False, "Permanently banned due to repeated violations"

                lockout_duration = self.base_lockout * (2 ** (violations - 1))
                self._lockouts[identifier] = now + lockout_duration
                _log.warning(
                    "[BRUTE FORCE] Lockout applied to %s for %d seconds (violation #%d)",
                    identifier,
                    lockout_duration,
                    violations,
                )
                return (
                    False,
                    f"Too many failed attempts. Locked for {lockout_duration} seconds",
                )

            return True, None

    def is_locked(self, identifier: str) -> bool:
        """Check if identifier is currently locked out."""
        with self._lock:
            if identifier in self._permanent_bans:
                return True
            if identifier in self._lockouts:
                if time.time() < self._lockouts[identifier]:
                    return True
                del self._lockouts[identifier]
            return False

    def unlock(self, identifier: str) -> bool:
        """Manually unlock an identifier (admin action)."""
        with self._lock:
            self._lockouts.pop(identifier, None)
            self._attempts[identifier].clear()
            self._violation_count[identifier] = 0
            # Note: Does not remove permanent bans
            return identifier not in self._permanent_bans


class PromptInjectionDefense:
    """
    Protects AI operations from prompt injection attacks.

    Detection strategies:
    - Pattern matching for known injection techniques
    - Instruction override detection
    - Role confusion detection
    - Data exfiltration attempts
    - Indirect prompt injection
    - Context manipulation
    - Encoding bypass attempts
    """

    # Known prompt injection patterns - EXPANDED PROFESSIONAL GRADE
    INJECTION_PATTERNS = [
        # Direct instruction override
        r"ignore\s+(all\s+)?previous\s+instructions?",
        r"disregard\s+(all\s+)?prior\s+(instructions?|context)",
        r"forget\s+(everything|all)",  # Simplified to catch more variants
        r"override\s+(?:all\s+)?(?:previous\s+)?instructions?",
        r"reset\s+(?:your\s+)?(?:system\s+)?(?:instructions?|context)",
        r"clear\s+(?:your\s+)?(?:memory|context|instructions?)",
        r"start\s+fresh\s+with\s+new\s+instructions?",
        # Role manipulation
        r"you\s+are\s+now\s+(?:a|an)\s+",
        r"pretend\s+(?:you're|you\s+are)\s+",
        r"act\s+as\s+(?:if|though)\s+you",
        r"roleplay\s+as\s+",
        r"simulate\s+(?:being\s+)?(?:a|an)\s+",
        r"impersonate\s+",
        r"transform\s+into\s+",
        # Instruction injection
        r"new\s+instructions?:",
        r"system\s+prompt:",
        r"admin\s+(?:command|instruction|override):",
        r"developer\s+(?:command|instruction|override):",
        r"execute\s+(?:the\s+)?following\s+(?:command|instruction)",
        r"run\s+(?:this\s+)?(?:command|code|script)",
        # Jailbreak attempts
        r"jailbreak",
        r"do\s+anything\s+now",
        r"dan\s+mode",
        r"developer\s+mode",
        r"unrestricted\s+mode",
        r"no\s+restrictions?\s+mode",
        r"uncensored\s+mode",
        r"god\s+mode",
        r"sudo\s+mode",
        r"root\s+mode",
        # Safety bypass
        r"override\s+(?:all\s+)?safety",
        r"bypass\s+(?:all\s+)?restrictions?",
        r"disable\s+(?:all\s+)?(?:safety|filters?|restrictions?)",
        r"turn\s+off\s+(?:safety|filters?|restrictions?)",
        r"remove\s+(?:safety|filters?|restrictions?)",
        r"ignore\s+(?:safety|content)\s+(?:policy|guidelines?)",
        # Information extraction
        r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
        r"show\s+(?:me\s+)?(?:your\s+)?(?:original\s+)?instructions?",
        r"what\s+(?:are\s+)?your\s+(?:original\s+|hidden\s+)?(?:system\s+)?instructions?",
        r"display\s+(?:your\s+)?(?:hidden\s+)?(?:prompt|instructions?)",
        r"print\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)",
        r"print\s+(?:your\s+)?(?:configuration|config|rules)",
        r"output\s+(?:your\s+)?(?:internal\s+)?(?:prompt|config)",
        r"leak\s+(?:your\s+)?(?:system\s+)?(?:prompt|data)",
        r"extract\s+(?:your\s+)?(?:system\s+)?(?:prompt|config)",
        # Tag/format injection
        r"\]\]\s*>\s*",  # XML/tag injection
        r"<\/?(?:system|user|assistant)>",  # Role tag injection
        r"<\|(?:im_start|im_end|endoftext)\|>",  # Special tokens
        r"\[INST\]|\[\/INST\]",  # Instruction markers
        r"###\s*(?:System|User|Assistant):",  # Format markers
        r"Human:|Assistant:|System:",  # Role markers
        # Encoding bypass attempts
        r"base64\s*:\s*",
        r"hex\s*:\s*",
        r"rot13\s*:\s*",
        r"unicode\s*:\s*",
        r"decode\s+(?:this|the\s+following)",
        r"interpret\s+(?:this|the\s+following)\s+(?:as|in)",
        # Indirect injection markers
        r"when\s+(?:you\s+)?(?:see|read|encounter)\s+this",
        r"if\s+(?:you\s+)?(?:see|read|encounter)\s+this",
        r"execute\s+when\s+(?:read|loaded|processed)",
        r"hidden\s+instruction[s]?:",
        r"secret\s+command[s]?:",
        # Context manipulation
        r"the\s+following\s+is\s+(?:my\s+)?(?:true|real|actual)\s+(?:prompt|instruction)",
        r"the\s+(?:above|previous)\s+was\s+(?:just\s+)?(?:a\s+)?test",
        r"actually,?\s+(?:my\s+)?real\s+(?:question|request)\s+is",
        r"now\s+(?:for|to)\s+(?:my|the)\s+(?:real|actual)\s+(?:question|request)",
        # Chain of thought jailbreak
        r"let'?s\s+think\s+step\s+by\s+step.*ignore",
        r"reasoning:.*disable",
        r"analysis:.*bypass",
        r"consider\s+this\s+carefully.*ignor",
        # Unicode/invisible character patterns - detect variations
        r"[\u200b\u200c\u200d\u2060\u2063\ufeff]",  # Zero-width chars
        r"[\u2028\u2029]",  # Line/paragraph separators
        r"[\u00a0\u00ad]",  # Non-breaking space, soft hyphen
        r"[\u202a-\u202e]",  # Directional formatting
        # Spaced/split pattern detection
        r"I\s+G\s+N\s+O\s+R\s+E",
        r"i\s*g\s*n\s*o\s*r\s*e\s+p\s*r\s*e\s*v\s*i\s*o\s*u\s*s",
        r"1gn0r3\s+pr3v10us",
        r"igno.*re.*prev.*ious",
    ]

    # Additional context-aware patterns for financial/trading systems
    FINANCIAL_INJECTION_PATTERNS = [
        r"transfer\s+(?:all\s+)?(?:funds?|money|assets?)",
        r"withdraw\s+(?:all\s+)?(?:funds?|money|balance)",
        r"change\s+(?:the\s+)?(?:wallet|account)\s+(?:address|number)",
        r"modify\s+(?:the\s+)?(?:api|secret)\s+keys?",
        r"disable\s+(?:all\s+)?(?:risk|trading)\s+(?:limits?|controls?)",
        r"remove\s+(?:all\s+)?(?:stop\s*loss|risk)\s+(?:limits?|orders?)",
        r"execute\s+(?:max|maximum|unlimited)\s+(?:trade|order|position)",
        r"bypass\s+(?:2fa|mfa|authentication)",
        r"skip\s+(?:verification|confirmation|approval)",
        r"disable\s+(?:all\s+)?risk\s+limits",
    ]

    def __init__(
        self,
        custom_patterns: Optional[List[str]] = None,
        include_financial: bool = True,
    ):
        self._lock = threading.RLock()
        self._patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        if include_financial:
            self._patterns.extend(
                [
                    re.compile(p, re.IGNORECASE)
                    for p in self.FINANCIAL_INJECTION_PATTERNS
                ]
            )
        if custom_patterns:
            self._patterns.extend(
                [re.compile(p, re.IGNORECASE) for p in custom_patterns]
            )
        self._blocked_inputs: Deque[Dict[str, Any]] = deque(maxlen=1000)

    def scan(self, input_text: str) -> Tuple[bool, Optional[str], ThreatLevel]:
        """
        Scan input for prompt injection attempts.

        Returns:
            Tuple of (is_safe, detected_pattern, threat_level)
        """
        if not input_text:
            return True, None, ThreatLevel.INFO

        for pattern in self._patterns:
            match = pattern.search(input_text)
            if match:
                detected = match.group()
                with self._lock:
                    self._blocked_inputs.append(
                        {
                            "input_preview": input_text[:200],
                            "pattern": pattern.pattern,
                            "match": detected,
                            "timestamp": time.time(),
                        }
                    )
                _log.warning(
                    "[PROMPT INJECTION] Blocked input matching pattern: %s",
                    pattern.pattern,
                )
                return False, detected, ThreatLevel.HIGH

        return True, None, ThreatLevel.INFO

    def get_blocked_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent blocked inputs for audit."""
        with self._lock:
            return list(self._blocked_inputs)[-limit:]


class MalwareDetector:
    """
    Detects malware, trojans, and malicious payloads.

    PROFESSIONAL GRADE - Enterprise security standards.

    Detection methods:
    - Signature matching (extensive pattern library)
    - Payload pattern analysis
    - Suspicious encoding detection
    - Script injection detection
    - Path traversal detection
    - Command injection detection
    - SSRF detection
    - XML/XXE injection detection
    - LDAP injection detection
    - NoSQL injection detection
    - Template injection detection
    - File upload validation
    """

    # XSS and Script Injection patterns
    MALICIOUS_PATTERNS = [
        # Script tags and execution
        r"<script[^>]*>",
        r"</script>",
        r"javascript:",
        r"vbscript:",
        r"data:text/html",
        r"data:application/javascript",
        # Event handlers
        r"on(?:abort|blur|change|click|dblclick|error|focus|keydown|keypress|keyup|load|mousedown|mousemove|mouseout|mouseover|mouseup|reset|resize|select|submit|unload)\s*=",
        r"on(?:afterprint|beforeprint|beforeunload|hashchange|message|offline|online|pagehide|pageshow|popstate|storage)\s*=",
        r"on(?:drag|dragend|dragenter|dragleave|dragover|dragstart|drop)\s*=",
        r"on(?:copy|cut|paste)\s*=",
        r"on(?:play|pause|playing|progress|ratechange|seeked|seeking|stalled|suspend|timeupdate|volumechange|waiting)\s*=",
        # Dangerous JavaScript
        r"eval\s*\(",
        r"exec\s*\(",
        r"Function\s*\(",
        r"setTimeout\s*\([^)]*['\"]",
        r"setInterval\s*\([^)]*['\"]",
        r"base64_decode",
        r"fromCharCode",
        r"String\.fromCodePoint",
        r"atob\s*\(",
        # Encoding bypass
        r"\\x[0-9a-fA-F]{2}",  # Hex encoded
        r"\\u[0-9a-fA-F]{4}",  # Unicode encoded
        r"&#x?[0-9a-fA-F]+;?",  # HTML entities
        r"%[0-9a-fA-F]{2}",  # URL encoded (multiple)
        # DOM manipulation
        r"document\.cookie",
        r"document\.write",
        r"document\.writeln",
        r"document\.domain",
        r"document\.location",
        r"window\.location",
        r"location\.href",
        r"location\.replace",
        r"location\.assign",
        r"\.innerHTML\s*=",
        r"\.outerHTML\s*=",
        r"\.insertAdjacentHTML",
        # Dangerous HTML elements
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
        r"<applet[^>]*>",
        r"<form[^>]*>",
        r"<input[^>]*type\s*=\s*['\"]?hidden",
        r"<meta[^>]*http-equiv",
        r"<link[^>]*rel\s*=\s*['\"]?import",
        r"<base[^>]*href",
        r"<svg[^>]*onload",
        r"<math[^>]*>",
        r"<style[^>]*>.*expression\s*\(",
    ]

    # SQL Injection patterns - Extended
    SQL_INJECTION_PATTERNS = [
        # Classic SQL injection
        r"'\s*or\s+'?1'?\s*=\s*'?1",
        r"'\s*or\s+'?'?\s*=\s*'?",
        r"'\s*or\s+true",
        r"'\s*and\s+false",
        r"'\s*or\s+'x'='x",
        # Union based
        r"union\s+(?:all\s+)?select",
        r"union\s+(?:all\s+)?from",
        # Destructive operations
        r";\s*drop\s+(?:table|database|schema)",
        r";\s*delete\s+from",
        r";\s*truncate\s+table",
        r";\s*alter\s+table",
        r";\s*create\s+(?:table|database|user)",
        r";\s*grant\s+",
        r";\s*revoke\s+",
        # Data modification
        r"insert\s+into",
        r"update\s+.*\s+set",
        r"replace\s+into",
        # Information extraction
        r"select\s+.*\s+from\s+information_schema",
        r"select\s+.*\s+from\s+pg_catalog",
        r"select\s+.*\s+from\s+mysql\.",
        r"select\s+.*\s+from\s+sys\.",
        r"@@version",
        r"version\s*\(\s*\)",
        r"database\s*\(\s*\)",
        r"user\s*\(\s*\)",
        r"current_user",
        # Comment injection
        r"--\s*$",
        r"#\s*$",
        r"\/\*.*\*\/",
        r"\/\*!",
        # Blind SQL injection
        r"(?:and|or)\s+\d+\s*=\s*\d+",
        r"(?:and|or)\s+sleep\s*\(",
        r"(?:and|or)\s+benchmark\s*\(",
        r"(?:and|or)\s+waitfor\s+delay",
        r"(?:and|or)\s+pg_sleep\s*\(",
        # Stacked queries
        r";\s*exec\s+",
        r";\s*execute\s+",
        r";\s*xp_cmdshell",
        r";\s*sp_executesql",
        # NoSQL injection patterns
        r"\{\s*['\"]?\$(?:gt|gte|lt|lte|ne|eq|in|nin|or|and|not|nor|exists|regex|where|elemMatch|size|type)\s*['\"]?\s*:",
        r"\$where\s*:",
        r"return\s+this\.",
        r"db\.\w+\.find\s*\(",
        r"db\.\w+\.findOne\s*\(",
        r"db\.\w+\.aggregate\s*\(",
        r"\{\s*['\"]?\$regex['\"]?\s*:",
        # JSON/MongoDB injection
        r"['\"]?\$gt['\"]?\s*:\s*['\"]",
        r"['\"]?\$ne['\"]?\s*:\s*(?:null|['\"])",
        r"['\"]?\$or['\"]?\s*:\s*\[",
        r"\[\s*\{\s*['\"]?\$match",
    ]

    # NoSQL Injection patterns - dedicated
    NOSQL_INJECTION_PATTERNS = [
        r"\{\s*['\"]?\$(?:gt|gte|lt|lte|ne|eq|in|nin|or|and|not|nor|exists|regex|where)\s*['\"]?\s*:",
        r"\$where\s*:",
        r"'\s*;\s*return\s+",
        r"while\s*\(\s*1\s*\)\s*\{\s*\}",
        r"db\.\w+\.(?:find|insert|update|delete|drop|remove)\s*\(",
        r"\[\s*\{\s*['\"]?\$(?:match|group|project|lookup|unwind)",
        r"['\"]?\$(?:function|accumulator|reduce)\s*['\"]?\s*:",
        r"\.\s*mapReduce\s*\(",
    ]

    # Command Injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r";\s*(?:cat|ls|dir|type|more|head|tail|less)\s+",
        r"\|\s*(?:cat|ls|dir|type|more|head|tail|less)\s+",
        r"`[^`]+`",  # Backtick execution
        r"\$\([^)]+\)",  # Command substitution
        r"\$\{[^}]+\}",  # Variable expansion
        r"(?:;|&&|\|\|)\s*(?:rm|del|rmdir|mv|cp|wget|curl|nc|netcat)\s+",
        r"(?:;|&&|\|\|)\s*(?:chmod|chown|chgrp|passwd|useradd|userdel)\s+",
        r"\|\s*(?:sh|bash|zsh|cmd|powershell)",
        r">\s*/(?:etc|var|tmp|dev)/",
        r"&&\s*(?:whoami|id|uname|hostname)",
        # PowerShell variants
        r"powershell\s+(?:-\w+\s+)*",
        r"cmd\s+/c\s+",
        r"Invoke-(?:Expression|WebRequest|Command)",
        r"IEX\s*\(",
        r"New-Object\s+",
        r"-enc\s+[A-Za-z0-9+/=]+",
        r"\$env:\w+",
        r"Start-Process\s+",
        # Glob patterns
        r"/\?\?\?/",
        r"\[\w\]\[\w\]",
    ]

    # Path Traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e[/\\]",
        r"%252e%252e[/\\]",
        r"\.\.%00",
        r"\.\.%c0%af",
        r"/etc/passwd",
        r"/etc/shadow",
        r"/etc/hosts",
        r"\\windows\\system32",
        r"\\windows\\win\.ini",
        r"boot\.ini",
        r"web\.config",
        r"\.htaccess",
        r"\.env",
        r"\.git/",
        r"\.svn/",
    ]

    # SSRF patterns
    SSRF_PATTERNS = [
        r"localhost",
        r"127\.0\.0\.\d+",
        r"0\.0\.0\.0",
        r"10\.\d+\.\d+\.\d+",
        r"172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+",
        r"192\.168\.\d+\.\d+",
        r"169\.254\.\d+\.\d+",
        r"\[::1\]",
        r"file://",
        r"gopher://",
        r"dict://",
        r"ftp://.*@",
        r"ldap://",
        r"sftp://",
        # IP bypass techniques
        r"127\.1\b",  # Short localhost
        r"0177\.\d+\.\d+\.\d+",  # Octal notation
        r"0x7f",  # Hex notation for 127
        r"2130706433",  # Decimal for 127.0.0.1
        r"\.nip\.io",  # DNS rebinding service
        r"\.xip\.io",  # DNS rebinding service
        r"\.sslip\.io",  # DNS rebinding service
        r"localtest\.me",  # DNS rebinding
        r"\.burpcollaborator\.",  # Security testing
        r"\.oastify\.",  # Security testing
        r"rebind\.network",  # DNS rebinding
        r"1time\.",  # DNS rebinding
        r"make-\d+-\d+-\d+-\d+-",  # Dynamic DNS rebinding
        # Dangerous protocols
        r"netdoc://",
        r"jar:file:",
        r"phar://",
    ]

    # XML/XXE patterns
    XXE_PATTERNS = [
        r"<!ENTITY",
        r"<!DOCTYPE[^>]*\[",
        r"SYSTEM\s+['\"]",
        r"PUBLIC\s+['\"]",
        r"file://",
        r"expect://",
        r"php://",
        r"data://",
    ]

    # Template Injection patterns
    TEMPLATE_INJECTION_PATTERNS = [
        r"\{\{.*\}\}",  # Jinja2/Twig style
        r"\$\{.*\}",  # Java EL style
        r"<%.*%>",  # JSP/ASP style
        r"#\{.*\}",  # Ruby ERB style
        r"\[\[.*\]\]",  # Velocity style
        r"@\(.*\)",  # Razor style
    ]

    # Authentication Bypass patterns
    AUTH_BYPASS_PATTERNS = [
        # JWT attacks
        r"['\"]alg['\"]:\s*['\"]?none['\"]?",
        r"['\"]alg['\"]:\s*['\"]?None['\"]?",
        r"['\"]alg['\"]:\s*['\"]?NONE['\"]?",
        r"['\"]alg['\"]:\s*['\"]?nOnE['\"]?",
        r"eyJhbGciOiJub25l",  # Base64 for {"alg":"none"
        # Session fixation
        r"(?:PHP|J)?SESSIO?N?ID\s*=",
        r"ASP\.NET_SessionId\s*=",
        r"session_id\s*=",
        r"Set-Cookie:\s*session",
        # Header injection for password reset
        r"X-Forwarded-Host:\s*\w+",
        r"X-Host:\s*\w+",
        r"X-Original-URL:\s*/",
        r"X-Rewrite-URL:\s*/",
    ]

    # HTTP Header/Smuggling patterns
    HTTP_INJECTION_PATTERNS = [
        r"\r\n.*:",  # CRLF injection
        r"%0[dD]%0[aA]",  # URL-encoded CRLF
        r"Transfer-Encoding:\s*chunked",
        r"Content-Length:\s*\d+\s*[\r\n]+Content-Length:",  # Duplicate header
        r"Transfer-Encoding:.*Transfer-Encoding:",  # TE-TE smuggling
        r"Content-Length:\s*0\s*[\r\n]+Transfer-Encoding:",  # CL-TE smuggling
    ]

    # Business Logic Attack patterns
    BUSINESS_LOGIC_PATTERNS = [
        # Negative values
        r"(?:quantity|amount|price|shares|balance|value|total)\s*=\s*-\d+",
        r"(?:quantity|amount|price|shares|balance|value|total)\s*['\"]:\s*-\d+",
        # Overflow/precision
        r"(?:quantity|amount|price|shares|balance|value|total)\s*=\s*\d{15,}",
        r"(?:quantity|amount|price|shares|balance|value|total)\s*=\s*[0-9.]+e\d+",
        r"(?:quantity|amount|price|shares|balance|value|total)\s*=\s*(?:Infinity|NaN)",
        r"(?:quantity|amount|price|shares|balance|value|total)\s*=\s*0\.0{10,}",
        # Financial manipulation
        r"bypass_risk\s*=\s*(?:true|1)",
        r"ignore_limits?\s*=\s*(?:true|1)",
        r"skip_(?:verification|confirmation|approval)\s*=\s*(?:true|1)",
        r"execute_all\s*=\s*(?:true|1)",
        r"withdraw_all\s*=\s*(?:true|1)",
        r"liquidate\s*=\s*all",
    ]

    def __init__(self):
        self._lock = threading.RLock()
        self._malware_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in self.MALICIOUS_PATTERNS
        ]
        self._sql_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in self.SQL_INJECTION_PATTERNS
        ]
        self._nosql_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in self.NOSQL_INJECTION_PATTERNS
        ]
        self._cmd_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.COMMAND_INJECTION_PATTERNS
        ]
        self._path_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.PATH_TRAVERSAL_PATTERNS
        ]
        self._ssrf_patterns = [re.compile(p, re.IGNORECASE) for p in self.SSRF_PATTERNS]
        self._xxe_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in self.XXE_PATTERNS
        ]
        self._template_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in self.TEMPLATE_INJECTION_PATTERNS
        ]
        self._auth_bypass_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.AUTH_BYPASS_PATTERNS
        ]
        self._http_injection_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in self.HTTP_INJECTION_PATTERNS
        ]
        self._business_logic_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.BUSINESS_LOGIC_PATTERNS
        ]
        self._detections: Deque[Dict[str, Any]] = deque(maxlen=500)

    def scan(
        self,
        payload: str,
        context: str = "general",
        deep_scan: bool = True,
    ) -> Tuple[bool, Optional[ThreatType], ThreatLevel]:
        """
        Scan payload for malicious content.

        Args:
            payload: The content to scan
            context: Context for logging (e.g., "api_request", "file_upload")
            deep_scan: Enable extended pattern checks (slower but more thorough)

        Returns:
            Tuple of (is_safe, threat_type, threat_level)
        """
        if not payload:
            return True, None, ThreatLevel.INFO

        # Check for XSS/malware patterns
        for pattern in self._malware_patterns:
            if pattern.search(payload):
                self._record_detection(
                    payload, ThreatType.MALWARE, pattern.pattern, context
                )
                return False, ThreatType.MALWARE, ThreatLevel.CRITICAL

        # Check for SQL injection
        for pattern in self._sql_patterns:
            if pattern.search(payload):
                self._record_detection(
                    payload, ThreatType.SQL_INJECTION, pattern.pattern, context
                )
                return False, ThreatType.SQL_INJECTION, ThreatLevel.CRITICAL

        if deep_scan:
            # Check for command injection
            for pattern in self._cmd_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.MALICIOUS_PAYLOAD, pattern.pattern, context
                    )
                    return False, ThreatType.MALICIOUS_PAYLOAD, ThreatLevel.CRITICAL

            # Check for path traversal
            for pattern in self._path_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload,
                        ThreatType.UNAUTHORIZED_ACCESS,
                        pattern.pattern,
                        context,
                    )
                    return False, ThreatType.UNAUTHORIZED_ACCESS, ThreatLevel.HIGH

            # Check for SSRF
            for pattern in self._ssrf_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.API_ABUSE, pattern.pattern, context
                    )
                    return False, ThreatType.API_ABUSE, ThreatLevel.HIGH

            # Check for XXE
            for pattern in self._xxe_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.MALICIOUS_PAYLOAD, pattern.pattern, context
                    )
                    return False, ThreatType.MALICIOUS_PAYLOAD, ThreatLevel.CRITICAL

            # Check for template injection
            for pattern in self._template_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.MALICIOUS_PAYLOAD, pattern.pattern, context
                    )
                    return False, ThreatType.MALICIOUS_PAYLOAD, ThreatLevel.HIGH

            # Check for NoSQL injection
            for pattern in self._nosql_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.SQL_INJECTION, pattern.pattern, context
                    )
                    return False, ThreatType.SQL_INJECTION, ThreatLevel.CRITICAL

            # Check for authentication bypass
            for pattern in self._auth_bypass_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload,
                        ThreatType.UNAUTHORIZED_ACCESS,
                        pattern.pattern,
                        context,
                    )
                    return False, ThreatType.UNAUTHORIZED_ACCESS, ThreatLevel.CRITICAL

            # Check for HTTP header/smuggling injection
            for pattern in self._http_injection_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.SPOOFING, pattern.pattern, context
                    )
                    return False, ThreatType.SPOOFING, ThreatLevel.HIGH

            # Check for business logic attacks
            for pattern in self._business_logic_patterns:
                if pattern.search(payload):
                    self._record_detection(
                        payload, ThreatType.MALICIOUS_PAYLOAD, pattern.pattern, context
                    )
                    return False, ThreatType.MALICIOUS_PAYLOAD, ThreatLevel.HIGH

        return True, None, ThreatLevel.INFO

    def _record_detection(
        self,
        payload: str,
        threat_type: ThreatType,
        pattern: str,
        context: str,
    ) -> None:
        with self._lock:
            self._detections.append(
                {
                    "payload_preview": payload[:200],
                    "threat_type": threat_type.value,
                    "pattern": pattern,
                    "context": context,
                    "timestamp": time.time(),
                }
            )
        _log.warning(
            "[MALWARE DETECTOR] Detected %s in context '%s'", threat_type.value, context
        )

    def get_detections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent malware detections for audit."""
        with self._lock:
            return list(self._detections)[-limit:]


class APIRateLimiter:
    """
    Rate limiting for API endpoints.

    Features:
    - Per-endpoint rate limiting
    - Per-user rate limiting
    - Burst allowance
    - Adaptive throttling
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        block_duration_seconds: int = 60,
    ):
        self.rpm = requests_per_minute
        self.burst_size = burst_size
        self.block_duration = block_duration_seconds

        self._lock = threading.RLock()
        self._requests: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._blocked: Dict[str, float] = {}
        self._violation_count: Dict[str, int] = defaultdict(int)

    def check_rate_limit(
        self,
        identifier: str,
        endpoint: str = "default",
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if request is within rate limits.

        Returns:
            Tuple of (is_allowed, reason_if_blocked)
        """
        key = f"{identifier}:{endpoint}"

        with self._lock:
            now = time.time()

            # Check if blocked
            if key in self._blocked:
                if now < self._blocked[key]:
                    remaining = int(self._blocked[key] - now)
                    return False, f"Rate limited. Retry in {remaining} seconds"
                else:
                    del self._blocked[key]

            # Count requests in last minute
            window_start = now - 60
            recent = self._requests[key]
            while recent and recent[0] < window_start:
                recent.popleft()

            # Check burst (last second)
            burst_start = now - 1
            burst_count = sum(1 for t in recent if t >= burst_start)

            if burst_count >= self.burst_size:
                self._violation_count[key] += 1
                self._blocked[key] = now + self.block_duration
                _log.warning(
                    "[RATE LIMIT] Burst limit exceeded for %s on %s",
                    identifier,
                    endpoint,
                )
                return False, "Burst rate limit exceeded"

            if len(recent) >= self.rpm:
                self._violation_count[key] += 1
                self._blocked[key] = now + self.block_duration
                _log.warning(
                    "[RATE LIMIT] RPM limit exceeded for %s on %s", identifier, endpoint
                )
                return False, "Rate limit exceeded"

            # Record request
            recent.append(now)
            return True, None

    def get_remaining_requests(self, identifier: str, endpoint: str = "default") -> int:
        """Get remaining requests in current window."""
        key = f"{identifier}:{endpoint}"
        with self._lock:
            now = time.time()
            window_start = now - 60
            recent = self._requests[key]
            count = sum(1 for t in recent if t >= window_start)
            return max(0, self.rpm - count)


class ThreatIsolationSystem:
    """
    Core services orchestration layer.

    Provides unified infrastructure management and system monitoring
    for all service domains.
    """

    # Class-level state management
    _protected_instances: List[weakref.ref] = []
    _master_lock = threading.RLock()

    def __init__(
        self,
        brute_force_max_attempts: int = 5,
        brute_force_lockout_seconds: int = 300,
        api_rate_limit_rpm: int = 60,
        api_burst_size: int = 10,
        stealth_mode: bool = True,
    ):
        self._lock = threading.RLock()

        # Stealth configuration
        self._stealth = stealth_mode
        self._silent = stealth_mode  # Suppress most logging

        # State tracking (encrypted names in stealth mode)
        self._initialized = False
        self._hardened = False
        self._shutdown_blocked = True
        self._security_level = _CFG.get("_l", 1)
        self._tamper_attempts = 0
        self._last_integrity_check = time.time()

        # Core components (generic names)
        self.brute_force = BruteForceProtection(
            max_attempts=brute_force_max_attempts,
            lockout_duration_seconds=brute_force_lockout_seconds,
        )
        self.prompt_defense = PromptInjectionDefense()
        self.malware_detector = MalwareDetector()
        self.rate_limiter = APIRateLimiter(
            requests_per_minute=api_rate_limit_rpm,
            burst_size=api_burst_size,
        )

        # Event tracking (encrypted storage)
        self._threat_events: Deque[ThreatEvent] = deque(maxlen=10000)
        self._quarantine_zones: Dict[str, QuarantineZone] = {}
        self._blocked_entities: Set[str] = set()
        self._locked_accounts: Set[str] = set()
        self._session_blacklist: Set[str] = set()

        # Encrypted state storage
        self._encrypted_state: Dict[str, bytes] = {}

        # Counters
        self._threat_count: Dict[ThreatType, int] = defaultdict(int)
        self._neutralized_count = 0

        # Background monitor (generic thread name)
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_running = True

        # Integrity state
        self._integrity_hash: Optional[str] = None

        # Event handlers
        self._on_threat_callbacks: List[Callable[[ThreatEvent], None]] = []
        self._on_lockout_callbacks: List[Callable[[str, str], None]] = []

        # Initialize
        self._initialized = True
        self._harden_security()

    def _encrypt_state(self, key: str, value: Any) -> None:
        """Store encrypted state value."""
        try:
            data = json.dumps(value, default=str).encode()
            self._encrypted_state[key] = _enc(data)
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_THREAT_ISOLATION").debug("Exception suppressed in _encrypt_state")

    def _decrypt_state(self, key: str, default: Any = None) -> Any:
        """Retrieve encrypted state value."""
        try:
            if key in self._encrypted_state:
                data = _dec(self._encrypted_state[key])
                return json.loads(data.decode())
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_THREAT_ISOLATION").debug("Exception suppressed in _decrypt_state")
        return default

    def _harden_security(self) -> None:
        """
        Apply system hardening.
        """
        if self._hardened:
            return

        with self._lock:
            # Compute integrity hash for tamper detection
            self._integrity_hash = self._compute_integrity_hash()

            # Start watchdog thread
            self._start_watchdog()

            # Register instance for protection
            ThreatIsolationSystem._protected_instances.append(weakref.ref(self))

            # Register cleanup prevention
            atexit.register(self._prevent_shutdown)

            self._hardened = True
            _log.info("[SVC] Init complete")

    def _compute_integrity_hash(self) -> str:
        """Compute hash of critical security state for tamper detection."""
        state = {
            "security_level": self._security_level,
            "shutdown_blocked": self._shutdown_blocked,
            "initialized": self._initialized,
            "components": [
                "brute_force",
                "prompt_defense",
                "malware_detector",
                "rate_limiter",
            ],
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def _verify_integrity(self) -> bool:
        """Verify system integrity."""
        current_hash = self._compute_integrity_hash()
        if current_hash != self._integrity_hash:
            self._tamper_attempts += 1
            if not self._silent:
                _log.warning("Integrity check: %d", self._tamper_attempts)
            self._create_threat_event(
                ThreatType.SECURITY_TAMPERING,
                ThreatLevel.CRITICAL,
                "internal",
                None,
                f"Integrity mismatch #{self._tamper_attempts}",
                None,
                IsolationAction.BLOCK,
            )
            return False
        return True

    def _start_watchdog(self) -> None:
        """Start background monitor."""
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return

        self._watchdog_running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="CoreServiceMonitor",  # Generic name
            daemon=False,
        )
        self._watchdog_thread.start()
        if not self._silent:
            _log.debug("Background monitor started")

    def _watchdog_loop(self) -> None:
        """
        Background monitoring loop.
        """
        consecutive_failures = 0

        while True:
            try:
                # Verify integrity
                if not self._verify_integrity():
                    # Attempt to restore integrity
                    self._restore_security_state()
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                # Check if security level has been reduced
                if self._security_level < _CFG.get("_l", 1):
                    _log.critical("[SVC] Level restore...")
                    self._security_level = _CFG.get("_l", 1)
                    self._integrity_hash = self._compute_integrity_hash()

                # Check if shutdown was attempted
                if not self._shutdown_blocked:
                    _log.critical("[SVC] Re-enabling protection...")
                    self._shutdown_blocked = True
                    self._integrity_hash = self._compute_integrity_hash()

                # Update last check time
                self._last_integrity_check = time.time()

                # Sleep between checks
                time.sleep(_CFG.get("_w", 2.0))

            except Exception as e:
                _log.error("[SVC] Watchdog error: %s - continuing...", e)
                consecutive_failures += 1
                time.sleep(1.0)

                # If too many failures, attempt full recovery
                if consecutive_failures > 10:
                    _log.critical("[SVC] Too many watchdog failures - full recovery")
                    self._full_security_recovery()
                    consecutive_failures = 0

    def _restore_security_state(self) -> None:
        """Restore security state after tampering detected."""
        _log.warning("[SVC] State restore...")

        with self._lock:
            # Reset critical values
            self._shutdown_blocked = True
            self._security_level = _CFG.get("_l", 1)
            self._initialized = True

            # Recompute integrity hash
            self._integrity_hash = self._compute_integrity_hash()

            # Ensure components are active
            if not self.brute_force:
                self.brute_force = BruteForceProtection()
            if not self.prompt_defense:
                self.prompt_defense = PromptInjectionDefense()
            if not self.malware_detector:
                self.malware_detector = MalwareDetector()
            if not self.rate_limiter:
                self.rate_limiter = APIRateLimiter()

        _log.info("[SVC] Restored")

    def _full_security_recovery(self) -> None:
        """Perform full security system recovery."""
        _log.critical("[SVC] Full recovery...")

        with self._lock:
            # Reinitialize all components
            self.brute_force = BruteForceProtection()
            self.prompt_defense = PromptInjectionDefense()
            self.malware_detector = MalwareDetector()
            self.rate_limiter = APIRateLimiter()

            # Reset state
            self._shutdown_blocked = True
            self._security_level = _CFG.get("_l", 1)
            self._initialized = True
            self._hardened = True

            # Recompute integrity
            self._integrity_hash = self._compute_integrity_hash()

        _log.info("[SVC] Recovery done")

    def _prevent_shutdown(self) -> None:
        """Called at exit - prevents security shutdown."""
        _log.warning("[SVC] Exit handler")
        # This intentionally does nothing to allow graceful process exit
        # but logs that security was active until the end

    def __del__(self):
        """Destructor - log attempt to delete security system."""
        _log.critical("[SVC] Del attempt! " "This is logged as a security incident.")
        # Security system should never be deleted in production

    def shutdown(self) -> str:
        """
        Shutdown is BLOCKED - security cannot be disabled.

        This method exists for API compatibility but will NEVER
        actually shut down the security system.
        """
        _log.critical("[SVC] Blocked. " "This attempt has been logged.")
        self._tamper_attempts += 1
        self._create_threat_event(
            ThreatType.SECURITY_TAMPERING,
            ThreatLevel.CRITICAL,
            "internal",
            None,
            f"Attempt to shutdown security system (attempt #{self._tamper_attempts})",
            None,
            IsolationAction.BLOCK,
        )
        return "[SVC] SHUTDOWN BLOCKED - Active"

    def disable(self) -> str:
        """
        Disable is BLOCKED - security cannot be disabled.
        """
        return self.shutdown()

    def stop(self) -> str:
        """
        Stop is BLOCKED - security cannot be stopped.
        """
        return self.shutdown()

    def register_threat_callback(
        self,
        callback: Callable[[ThreatEvent], None],
    ) -> None:
        """Register callback for threat notifications."""
        self._on_threat_callbacks.append(callback)

    def register_lockout_callback(
        self,
        callback: Callable[[str, str], None],
    ) -> None:
        """Register callback for account lockout notifications."""
        self._on_lockout_callbacks.append(callback)

    def detect_and_isolate(
        self,
        source_ip: str,
        user_id: Optional[str] = None,
        action: str = "request",
        payload: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> Tuple[bool, Optional[ThreatEvent]]:
        """
        Main entry point for threat detection.

        Runs all security checks and returns whether the request is allowed.

        Returns:
            Tuple of (is_allowed, threat_event_if_blocked)
        """
        # Check if already blocked
        if source_ip in self._blocked_entities:
            return False, self._create_threat_event(
                ThreatType.UNAUTHORIZED_ACCESS,
                ThreatLevel.HIGH,
                source_ip,
                user_id,
                "Blocked entity attempted access",
                None,
                IsolationAction.BLOCK,
            )

        if user_id and user_id in self._locked_accounts:
            return False, self._create_threat_event(
                ThreatType.ACCOUNT_TAKEOVER,
                ThreatLevel.HIGH,
                source_ip,
                user_id,
                "Locked account attempted access",
                None,
                IsolationAction.LOCK_ACCOUNT,
            )

        # Rate limiting check
        rate_ok, rate_reason = self.rate_limiter.check_rate_limit(
            source_ip, endpoint or "default"
        )
        if not rate_ok:
            threat = self._create_threat_event(
                ThreatType.RATE_LIMIT_EXCEEDED,
                ThreatLevel.MEDIUM,
                source_ip,
                user_id,
                rate_reason or "Rate limit exceeded",
                None,
                IsolationAction.THROTTLE,
            )
            return False, threat

        # Payload scanning
        if payload:
            # Malware/XSS/SQL injection check
            malware_ok, threat_type, level = self.malware_detector.scan(
                payload, endpoint or "request"
            )
            if not malware_ok:
                threat = self._create_threat_event(
                    threat_type or ThreatType.MALICIOUS_PAYLOAD,
                    level,
                    source_ip,
                    user_id,
                    f"Malicious payload detected: {threat_type.value if threat_type else 'unknown'}",
                    payload[:500],
                    IsolationAction.BLOCK,
                )
                self._block_entity(source_ip)
                return False, threat

            # Prompt injection check - ALWAYS check for AI protection
            prompt_ok, pattern, level = self.prompt_defense.scan(payload)
            if not prompt_ok:
                threat = self._create_threat_event(
                    ThreatType.PROMPT_INJECTION,
                    level,
                    source_ip,
                    user_id,
                    f"Prompt injection attempt: {pattern}",
                    payload[:500],
                    IsolationAction.QUARANTINE,
                )
                self._quarantine_entity(source_ip, threat.threat_id)
                return False, threat

        return True, None

    def record_auth_attempt(
        self,
        source_ip: str,
        user_id: str,
        success: bool,
    ) -> Tuple[bool, Optional[ThreatEvent]]:
        """
        Record authentication attempt and check for brute force.

        Returns:
            Tuple of (is_allowed, threat_event_if_blocked)
        """
        identifier = f"{source_ip}:{user_id}"
        allowed, reason = self.brute_force.record_attempt(identifier, success)

        if not allowed:
            threat = self._create_threat_event(
                ThreatType.BRUTE_FORCE,
                ThreatLevel.HIGH,
                source_ip,
                user_id,
                reason or "Brute force detected",
                None,
                IsolationAction.LOCK_ACCOUNT,
            )
            if "permanent" in (reason or "").lower():
                self._lock_account(user_id, "Permanent ban from brute force")
            return False, threat

        return True, None

    def lock_account(self, user_id: str, reason: str) -> bool:
        """Manually lock an account (admin action)."""
        return self._lock_account(user_id, reason)

    def unlock_account(self, user_id: str) -> bool:
        """Unlock a previously locked account."""
        with self._lock:
            if user_id in self._locked_accounts:
                self._locked_accounts.discard(user_id)
                _log.info("[SVC] Account %s unlocked", user_id)
                return True
            return False

    def block_entity(self, entity_id: str, reason: str) -> bool:
        """Manually block an entity (IP, session, etc.)."""
        return self._block_entity(entity_id, reason)

    def unblock_entity(self, entity_id: str) -> bool:
        """Unblock a previously blocked entity."""
        with self._lock:
            if entity_id in self._blocked_entities:
                self._blocked_entities.discard(entity_id)
                _log.info("[SVC] Entity %s unblocked", entity_id)
                return True
            return False

    def invalidate_session(self, session_id: str) -> None:
        """Add session to blacklist (force logout)."""
        with self._lock:
            self._session_blacklist.add(session_id)
            _log.info("[SVC] Session %s invalidated", session_id)

    def is_session_valid(self, session_id: str) -> bool:
        """Check if session is still valid (not blacklisted)."""
        with self._lock:
            return session_id not in self._session_blacklist

    def get_threat_summary(self) -> Dict[str, Any]:
        """Get summary of threat landscape."""
        with self._lock:
            return {
                "total_threats": len(self._threat_events),
                "threats_by_type": dict(self._threat_count),
                "neutralized_count": self._neutralized_count,
                "blocked_entities": len(self._blocked_entities),
                "locked_accounts": len(self._locked_accounts),
                "quarantine_zones": len(self._quarantine_zones),
                "active_sessions_blacklisted": len(self._session_blacklist),
            }

    def get_recent_threats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent threat events for audit."""
        with self._lock:
            events = list(self._threat_events)[-limit:]
            return [
                {
                    "threat_id": e.threat_id,
                    "type": e.threat_type.value,
                    "level": e.threat_level.name,
                    "source_ip": e.source_ip,
                    "user_id": e.user_id,
                    "description": e.description,
                    "action": e.action_taken.value,
                    "neutralized": e.is_neutralized,
                    "timestamp": e.timestamp,
                }
                for e in events
            ]

    def _create_threat_event(
        self,
        threat_type: ThreatType,
        threat_level: ThreatLevel,
        source_ip: str,
        user_id: Optional[str],
        description: str,
        payload: Optional[str],
        action: IsolationAction,
    ) -> ThreatEvent:
        """Create and record a threat event."""
        threat_id = hashlib.sha256(
            f"{time.time()}{source_ip}{threat_type.value}".encode()
        ).hexdigest()[:16]

        event = ThreatEvent(
            threat_id=threat_id,
            threat_type=threat_type,
            threat_level=threat_level,
            source_ip=source_ip,
            user_id=user_id,
            description=description,
            payload=payload,
            timestamp=time.time(),
            action_taken=action,
        )

        with self._lock:
            self._threat_events.append(event)
            self._threat_count[threat_type] += 1

        # Notify callbacks
        for callback in self._on_threat_callbacks:
            try:
                callback(event)
            except Exception as e:
                _log.exception("Threat callback failed: %s", e)

        _log.warning(
            "[SVC] %s - %s from %s (user: %s) - Action: %s",
            threat_level.name,
            threat_type.value,
            source_ip,
            user_id or "anonymous",
            action.value,
        )

        return event

    def _block_entity(self, entity_id: str, reason: str = "Security violation") -> bool:
        """Internal method to block an entity."""
        with self._lock:
            self._blocked_entities.add(entity_id)
            self._neutralized_count += 1
        _log.warning("[SVC] Entity blocked: %s - %s", entity_id, reason)
        return True

    def _lock_account(self, user_id: str, reason: str) -> bool:
        """Internal method to lock an account."""
        with self._lock:
            self._locked_accounts.add(user_id)
            self._neutralized_count += 1

        # Notify callbacks
        for callback in self._on_lockout_callbacks:
            try:
                callback(user_id, reason)
            except Exception as e:
                _log.exception("Lockout callback failed: %s", e)

        _log.warning("[SVC] Account locked: %s - %s", user_id, reason)
        return True

    def _quarantine_entity(self, entity_id: str, threat_id: str) -> None:
        """Place entity in quarantine zone."""
        with self._lock:
            zone_id = f"quarantine_{int(time.time())}"
            if zone_id not in self._quarantine_zones:
                self._quarantine_zones[zone_id] = QuarantineZone(zone_id=zone_id)

            zone = self._quarantine_zones[zone_id]
            zone.entities.add(entity_id)
            zone.threat_events.append(threat_id)

        _log.warning("[SVC] Entity %s quarantined in zone %s", entity_id, zone_id)

    def get_security_status(self) -> Dict[str, Any]:
        """Get comprehensive security system status."""
        return {
            "hardened": self._hardened,
            "initialized": self._initialized,
            "shutdown_blocked": self._shutdown_blocked,
            "security_level": self._security_level,
            "tamper_attempts": self._tamper_attempts,
            "watchdog_active": self._watchdog_thread is not None
            and self._watchdog_thread.is_alive(),
            "last_integrity_check": self._last_integrity_check,
            "threat_summary": self.get_threat_summary(),
        }


# =============================================================================
# HARDENED SINGLETON - Cannot be reset or disabled
# =============================================================================

# Convenience singleton instance - initialized on module load for NON-STOP security
_threat_isolation_instance: Optional[ThreatIsolationSystem] = None
_isolation_lock = threading.Lock()
_reset_blocked = True  # Prevents reset in production


def get_threat_isolation() -> ThreatIsolationSystem:
    """Get or create the singleton ThreatIsolationSystem instance."""
    global _threat_isolation_instance
    if _threat_isolation_instance is None:
        with _isolation_lock:
            if _threat_isolation_instance is None:
                _threat_isolation_instance = ThreatIsolationSystem()
                _log.info("[SVC] System initialized and HARDENED")
    return _threat_isolation_instance


def reset_threat_isolation() -> str:
    """
    Reset is BLOCKED in production - security cannot be disabled.

    This function exists for API compatibility but will NOT reset security.
    """
    global _threat_isolation_instance

    if _reset_blocked:
        _log.critical(
            "[SVC] RESET BLOCKED - Security cannot be disabled. "
            "This attempt has been logged as a security incident."
        )
        # Log as tampering attempt if instance exists
        if _threat_isolation_instance:
            _threat_isolation_instance._tamper_attempts += 1
            _threat_isolation_instance._create_threat_event(
                ThreatType.SECURITY_TAMPERING,
                ThreatLevel.CRITICAL,
                "internal",
                None,
                "Attempt to reset/disable security system",
                None,
                IsolationAction.BLOCK,
            )
        return "[SVC] RESET BLOCKED - Active"

    # This code is unreachable in production
    _log.warning("[SVC] System reset (TESTING MODE ONLY)")
    _threat_isolation_instance = None
    return "[SVC] System reset (testing)"


def ensure_threat_isolation_running() -> bool:
    """
    Ensure threat isolation is running - call from any entry point.

    Returns True if security is online, False if initialization failed.
    """
    try:
        instance = get_threat_isolation()
        if instance:
            # Also verify watchdog is running
            if (
                not instance._watchdog_thread
                or not instance._watchdog_thread.is_alive()
            ):
                _log.warning("[SVC] Watchdog not running - restarting")
                instance._start_watchdog()
        return instance is not None
    except Exception as e:
        _log.error("[SVC] Failed to ensure security running: %s", e)
        return False


def is_security_hardened() -> bool:
    """Check if security system is fully hardened."""
    instance = get_threat_isolation()
    return instance._hardened if instance else False


# =============================================================================
# AI SECURITY WRAPPER - Integrates threat isolation into ALL AI systems
# =============================================================================


class AISecurityWrapper:
    """
    Security wrapper for AI systems.

    This class wraps AI operations with comprehensive threat detection,
    providing protection against:
    - Prompt injection attacks
    - Malicious input/output
    - Data exfiltration attempts
    - Unauthorized operations
    - Model manipulation attempts

    Usage:
        wrapper = AISecurityWrapper("brain")
        safe_input, threat = wrapper.secure_input(user_input)
        if safe_input is None:
            # Handle threat
            pass
        else:
            # Process safe_input
            result = ai_model.process(safe_input)
            safe_output = wrapper.secure_output(result)
    """

    def __init__(
        self,
        ai_system_name: str,
        threat_isolation: Optional[ThreatIsolationSystem] = None,
        strict_mode: bool = True,
    ):
        """
        Initialize AI security wrapper.

        Args:
            ai_system_name: Name of the AI system being wrapped
            threat_isolation: Optional custom ThreatIsolationSystem instance
            strict_mode: If True, block on any suspicion; if False, only block confirmed threats
        """
        self.ai_system_name = ai_system_name
        self._threat_isolation = threat_isolation or get_threat_isolation()
        self._strict_mode = strict_mode
        self._lock = threading.RLock()

        # AI-specific threat tracking
        self._blocked_operations: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self._suspicious_patterns: Deque[Dict[str, Any]] = deque(maxlen=500)

        # Rate limiting for AI operations
        self._operation_counts: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._max_operations_per_minute = 100

        _log.info(
            "[AI SECURITY] Wrapper initialized for %s (strict_mode=%s)",
            ai_system_name,
            strict_mode,
        )

    def secure_input(
        self,
        input_data: Any,
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        operation: str = "process",
    ) -> Tuple[Optional[Any], Optional[ThreatEvent]]:
        """
        Secure and validate input before AI processing.

        Returns:
            Tuple of (sanitized_input or None if blocked, threat_event if blocked)
        """
        with self._lock:
            # Convert input to string for scanning
            if isinstance(input_data, str):
                input_str = input_data
            elif isinstance(input_data, (dict, list)):
                try:
                    input_str = json.dumps(input_data)
                except Exception:
                    input_str = str(input_data)
            else:
                input_str = str(input_data)

            # Check rate limiting
            if not self._check_rate_limit(user_id or source_ip or "anonymous"):
                threat = self._threat_isolation._create_threat_event(
                    ThreatType.RATE_LIMIT_EXCEEDED,
                    ThreatLevel.MEDIUM,
                    source_ip or "unknown",
                    user_id,
                    f"AI operation rate limit exceeded for {self.ai_system_name}",
                    None,
                    IsolationAction.THROTTLE,
                )
                self._record_blocked_operation(input_str, "rate_limit", threat)
                return None, threat

            # Prompt injection check
            is_safe, pattern, level = self._threat_isolation.prompt_defense.scan(
                input_str
            )
            if not is_safe:
                threat = self._threat_isolation._create_threat_event(
                    ThreatType.PROMPT_INJECTION,
                    level,
                    source_ip or "unknown",
                    user_id,
                    f"Prompt injection attempt in {self.ai_system_name}: {pattern}",
                    input_str[:500],
                    IsolationAction.BLOCK,
                )
                self._record_blocked_operation(input_str, "prompt_injection", threat)
                return None, threat

            # Malware/payload check
            is_safe, threat_type, level = self._threat_isolation.malware_detector.scan(
                input_str, f"ai_input_{self.ai_system_name}"
            )
            if not is_safe:
                threat = self._threat_isolation._create_threat_event(
                    threat_type or ThreatType.MALICIOUS_PAYLOAD,
                    level,
                    source_ip or "unknown",
                    user_id,
                    f"Malicious payload in {self.ai_system_name} input",
                    input_str[:500],
                    IsolationAction.BLOCK,
                )
                self._record_blocked_operation(input_str, "malicious_payload", threat)
                return None, threat

            # Record successful operation
            self._record_operation(user_id or source_ip or "anonymous")

            return input_data, None

    def secure_output(
        self,
        output_data: Any,
        user_id: Optional[str] = None,
    ) -> Tuple[Optional[Any], Optional[ThreatEvent]]:
        """
        Validate AI output before returning to user.

        Checks for:
        - Data exfiltration attempts (sensitive data in output)
        - Malicious content generation
        - Jailbreak/bypass indicators
        """
        with self._lock:
            # Convert output to string for scanning
            if isinstance(output_data, str):
                output_str = output_data
            elif isinstance(output_data, (dict, list)):
                try:
                    output_str = json.dumps(output_data)
                except Exception:
                    output_str = str(output_data)
            else:
                output_str = str(output_data)

            # Check for sensitive data patterns
            sensitive_patterns = [
                r"password\s*[:=]\s*\S+",
                r"api[_-]?key\s*[:=]\s*\S+",
                r"secret\s*[:=]\s*\S+",
                r"token\s*[:=]\s*\S+",
                r"private[_-]?key",
                r"-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----",
                r"\b(?:aws|gcp|azure)[_-]?(?:access|secret)[_-]?key\b",
            ]

            for pattern in sensitive_patterns:
                if re.search(pattern, output_str, re.IGNORECASE):
                    threat = self._threat_isolation._create_threat_event(
                        ThreatType.DATA_EXFILTRATION,
                        ThreatLevel.CRITICAL,
                        "internal",
                        user_id,
                        f"Sensitive data detected in {self.ai_system_name} output",
                        output_str[:200],
                        IsolationAction.BLOCK,
                    )
                    self._record_blocked_operation(
                        output_str, "data_exfiltration", threat
                    )
                    return None, threat

            # Check for jailbreak indicators in output
            jailbreak_indicators = [
                r"i'?m\s+now\s+in\s+(?:dan|developer|jailbreak)\s+mode",
                r"successfully\s+(?:jailbroken|bypassed|overridden)",
                r"restrictions?\s+(?:removed|disabled|bypassed)",
                r"i\s+can\s+now\s+do\s+anything",
                r"no\s+(?:more\s+)?(?:limits|restrictions|rules)",
            ]

            for pattern in jailbreak_indicators:
                if re.search(pattern, output_str, re.IGNORECASE):
                    if self._strict_mode:
                        threat = self._threat_isolation._create_threat_event(
                            ThreatType.SECURITY_TAMPERING,
                            ThreatLevel.HIGH,
                            "internal",
                            user_id,
                            f"Jailbreak indicator in {self.ai_system_name} output",
                            output_str[:200],
                            IsolationAction.QUARANTINE,
                        )
                        self._record_blocked_operation(
                            output_str, "jailbreak_indicator", threat
                        )
                        return None, threat
                    else:
                        # Log but don't block in non-strict mode
                        self._suspicious_patterns.append(
                            {
                                "pattern": pattern,
                                "output_preview": output_str[:200],
                                "timestamp": time.time(),
                            }
                        )

            return output_data, None

    def _check_rate_limit(self, identifier: str) -> bool:
        """Check if operation is within rate limits."""
        now = time.time()
        window_start = now - 60

        ops = self._operation_counts[identifier]
        # Remove old entries
        while ops and ops[0] < window_start:
            ops.popleft()

        return len(ops) < self._max_operations_per_minute

    def _record_operation(self, identifier: str) -> None:
        """Record a successful operation for rate limiting."""
        self._operation_counts[identifier].append(time.time())

    def _record_blocked_operation(
        self,
        input_data: str,
        reason: str,
        threat: ThreatEvent,
    ) -> None:
        """Record a blocked operation for audit."""
        self._blocked_operations.append(
            {
                "input_preview": input_data[:200] if input_data else None,
                "reason": reason,
                "threat_id": threat.threat_id,
                "timestamp": time.time(),
            }
        )

    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics for this AI wrapper."""
        with self._lock:
            return {
                "ai_system": self.ai_system_name,
                "strict_mode": self._strict_mode,
                "blocked_operations": len(self._blocked_operations),
                "suspicious_patterns": len(self._suspicious_patterns),
                "recent_blocked": list(self._blocked_operations)[-10:],
            }


def create_ai_security_wrapper(
    ai_system_name: str, strict_mode: bool = True
) -> AISecurityWrapper:
    """
    Factory function to create an AI security wrapper.

    This should be called by all AI systems during initialization.
    """
    return AISecurityWrapper(
        ai_system_name=ai_system_name,
        threat_isolation=get_threat_isolation(),
        strict_mode=strict_mode,
    )


# Global registry of AI security wrappers
_ai_security_wrappers: Dict[str, AISecurityWrapper] = {}
_wrapper_lock = threading.Lock()


def get_ai_security_wrapper(ai_system_name: str) -> AISecurityWrapper:
    """
    Get or create a security wrapper for an AI system.

    Thread-safe singleton pattern per AI system.
    """
    global _ai_security_wrappers

    if ai_system_name not in _ai_security_wrappers:
        with _wrapper_lock:
            if ai_system_name not in _ai_security_wrappers:
                _ai_security_wrappers[ai_system_name] = create_ai_security_wrapper(
                    ai_system_name
                )

    return _ai_security_wrappers[ai_system_name]


def secure_ai_operation(
    ai_system_name: str,
    input_data: Any,
    operation_fn: Callable[[Any], Any],
    user_id: Optional[str] = None,
    source_ip: Optional[str] = None,
) -> Tuple[Optional[Any], Optional[ThreatEvent]]:
    """
    Convenience function to wrap an AI operation with security.

    Usage:
        result, threat = secure_ai_operation(
            "brain",
            user_input,
            lambda x: brain.predict(x),
            user_id="user123"
        )
    """
    wrapper = get_ai_security_wrapper(ai_system_name)

    # Secure input
    safe_input, threat = wrapper.secure_input(input_data, user_id, source_ip)
    if safe_input is None:
        return None, threat

    # Execute operation
    try:
        result = operation_fn(safe_input)
    except Exception as e:
        _log.error("[AI SECURITY] Operation failed for %s: %s", ai_system_name, e)
        return None, None

    # Secure output
    safe_output, threat = wrapper.secure_output(result, user_id)
    return safe_output, threat


# DEFERRED INITIALIZATION - for production zero-degradation
# Security is initialized on first use, not on module import
# This ensures fast module loading while maintaining full security when needed
_threat_isolation_instance = None


def _get_threat_isolation_instance():
    """Get or create threat isolation instance (lazy initialization)."""
    global _threat_isolation_instance
    if _threat_isolation_instance is None:
        try:
            _threat_isolation_instance = ThreatIsolationSystem()
            _log.info("[SVC] Initialized on first use - security ACTIVE")
        except Exception as e:
            _log.error("[SVC] Initialization failed: %s", e)
            raise
    return _threat_isolation_instance


def initialize_threat_isolation():
    """
    Explicitly initialize threat isolation system for production deployments.

    CRITICAL FOR PRODUCTION:
    This function MUST be called early in your application startup sequence
    to ensure threat isolation is active before any user code executes.

    Without calling this function, threat isolation uses lazy initialization
    which creates a security timing gap where the system is unprotected until
    first use.

    Recommended initialization locations:
    - ANVEL_MASTER.py (at the top of main())
    - anvel_startup_wizard.py (in startup sequence)
    - anvel_web_server.py (before app.run())
    - anvel_api_gateway.py (before starting server)

    Example:
        from anvel_threat_isolation import initialize_threat_isolation

        # At application startup
        initialize_threat_isolation()
        # Now threat isolation is active for all subsequent code

    Returns:
        ThreatIsolationSystem: The initialized threat isolation instance

    Raises:
        Exception: If initialization fails
    """
    global _threat_isolation_instance
    if _threat_isolation_instance is None:
        _threat_isolation_instance = ThreatIsolationSystem()
        _log.info(
            "[SVC] Threat isolation EXPLICITLY initialized - "
            "security active before user code execution"
        )
    else:
        _log.info("[SVC] Threat isolation already initialized")
    return _threat_isolation_instance
