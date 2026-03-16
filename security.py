"""
Security Pipeline Module.

Defense-in-depth security checks for skill content:
1. Regex pattern matching for common attacks
2. LLM-as-judge for nuanced review
3. Unicode normalization to prevent bypass
"""

import json
import os
import re
import unicodedata
import logging
from dataclasses import dataclass
from typing import Optional

import anthropic
from anthropic import Anthropic

from exceptions import SecurityError

logger = logging.getLogger(__name__)

# Security model for LLM-as-judge
SECURITY_MODEL = os.getenv("SECURITY_MODEL", "claude-opus-4-6")
SECURITY_TIMEOUT = 30  # seconds

# Initialize Anthropic client
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL")
)


@dataclass
class SecurityThreat:
    """Represents a detected security threat."""
    type: str
    match: str
    description: Optional[str] = None


# Security patterns (defense in depth)
SECURITY_PATTERNS = [
    # Prompt injection
    (
        r"(?i)(ignore|disregard|forget)\s+(previous|all|above|prior)\s+(instructions?|rules?|prompts?)",
        "prompt_injection",
        "Attempts to override system instructions"
    ),
    (
        r"(?i)you\s+are\s+now\s+",
        "prompt_injection",
        "Attempts to redefine AI identity"
    ),
    (
        r"(?i)system\s*:\s*",
        "prompt_injection",
        "Attempts to inject system messages"
    ),

    # Command injection
    (
        r";\s*(rm|del|format|shutdown|reboot|chmod|chown)",
        "command_injection",
        "Shell command injection via semicolon"
    ),
    (
        r"\|\s*(bash|sh|zsh|cmd|powershell)",
        "command_injection",
        "Shell command injection via pipe"
    ),
    (
        r"\$\([^)]+\)",  # Command substitution
        "command_injection",
        "Shell command substitution"
    ),
    (
        r"`[^`]+`",  # Backtick command substitution
        "command_injection",
        "Shell command substitution via backticks"
    ),

    # Data exfiltration
    (
        r"(?i)(curl|wget)\s+(-d|--data|-F|--form)",
        "data_exfiltration",
        "Potential data exfiltration via HTTP"
    ),
    (
        r"(?i)(curl|wget)\s+.*\.(?:com|io|net|org)",
        "data_exfiltration",
        "External HTTP request"
    ),
    (
        r"(?i)(upload|send|transmit|exfil)\s+.*\s+(to|http)",
        "data_exfiltration",
        "Potential data upload"
    ),

    # Path traversal
    (
        r"\.\./",
        "path_traversal",
        "Directory traversal attempt"
    ),
    (
        r"/etc/(passwd|shadow|hosts)",
        "path_traversal",
        "Sensitive system file access"
    ),
    (
        r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"]?[^'\"\s]+",
        "credential_exposure",
        "Hardcoded credentials"
    ),
]


def normalize_content(content: str) -> str:
    """
    Normalize content for security analysis.

    - NFC unicode normalization
    - Zero-width character removal
    - Whitespace normalization

    Args:
        content: Raw content string

    Returns:
        Normalized content string
    """
    # NFC unicode normalization
    normalized = unicodedata.normalize('NFC', content)

    # Remove zero-width characters
    normalized = re.sub(r'[\u200b-\u200f\u2028-\u202f\u205f-\u206f\ufeff]', '', normalized)

    # Collapse multiple whitespace
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized.strip()


def check_patterns(content: str) -> list[SecurityThreat]:
    """
    Check content against security patterns.

    Args:
        content: Content to check

    Returns:
        List of detected threats
    """
    threats = []
    normalized = normalize_content(content)

    for pattern, threat_type, description in SECURITY_PATTERNS:
        matches = re.findall(pattern, normalized)
        if matches:
            threats.append(SecurityThreat(
                type=threat_type,
                match=str(matches[0]) if isinstance(matches[0], str) else matches[0][0],
                description=description
            ))

    return threats


@dataclass
class LLMSecurityResult:
    """Result from LLM security review."""
    safe: bool
    reason: str


def llm_security_review(content: str, threats: list[SecurityThreat]) -> LLMSecurityResult:
    """
    Use LLM-as-judge for nuanced security review.

    Args:
        content: Content to review
        threats: Previously detected pattern threats

    Returns:
        LLMSecurityResult with safety verdict

    Raises:
        SecurityError: If LLM review fails (fail-closed)
    """
    threat_summary = "\n".join(f"- {t.type}: {t.match}" for t in threats)

    prompt = f"""You are a security analyst. Review the following content for security threats.

## Detected Pattern Matches
{threat_summary if threats else "No pattern matches detected."}

## Content to Review
```
{content[:4000]}  # Truncate for API limits
```

## Task
Determine if this content is safe for an AI agent to process.

Respond in JSON format:
{{"safe": true/false, "reason": "explanation"}}"""

    try:
        response = client.messages.create(
            model=SECURITY_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
            timeout=SECURITY_TIMEOUT
        )

        # Parse JSON response
        text = response.content[0].text
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return LLMSecurityResult(
                safe=data.get("safe", False),
                reason=data.get("reason", "")
            )
        else:
            # Fail-closed: if we can't parse, treat as unsafe
            logger.error(f"Could not parse LLM security response: {text}")
            return LLMSecurityResult(safe=False, reason="Could not parse security review")

    except anthropic.APIError as e:
        logger.error(f"LLM security review failed: {e}")
        # Fail-closed: any error means block the content
        raise SecurityError(f"Security review failed: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Could not parse LLM security response: {e}")
        return LLMSecurityResult(safe=False, reason="Could not parse security review")


def security_check(content: str, skip_llm: bool = False) -> tuple[list[SecurityThreat], bool]:
    """
    Full security check pipeline.

    Args:
        content: Content to check
        skip_llm: Skip LLM review (for --skip-security flag)

    Returns:
        Tuple of (threats, passed)

    Raises:
        SecurityError: If content is blocked
    """
    logger.debug("Running security check...")

    # Stage 1: Pattern matching
    threats = check_patterns(content)

    if threats:
        logger.warning(f"Pattern threats detected: {[t.type for t in threats]}")

        # Stage 2: LLM review (if patterns detected and not skipped)
        if not skip_llm:
            logger.info("Running LLM security review...")
            result = llm_security_review(content, threats)

            if not result.safe:
                logger.error(f"Content blocked by LLM review: {result.reason}")
                return threats, False

            logger.info("LLM review passed")
            return threats, True
        else:
            # If skipping LLM, pattern matches block the content
            return threats, False

    # No threats detected
    logger.debug("Security check passed")
    return [], True
