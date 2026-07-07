"""
Secret redaction module — wraps detect-secrets to find and replace credentials.

Public API:
    redact(text: str) -> tuple[str, list[str]]
        Returns (redacted_text, notices) where notices describe each replacement.
        Never raises. Falls back to original text on any internal error.

Note on plugin selection:
    We deliberately exclude entropy-based detectors (HexHighEntropyString,
    Base64HighEntropyString) because they produce false positives on ordinary
    English prose. The curated list below catches real credential patterns
    (AWS keys, GitHub tokens, private keys, etc.) with minimal noise.
"""

from __future__ import annotations

import re

# Plugins that detect structured credential patterns without entropy heuristics.
# Entropy detectors are excluded: too many false positives on plain text.
_PLUGINS: list[dict[str, str]] = [
    {"name": "AWSKeyDetector"},
    {"name": "ArtifactoryDetector"},
    {"name": "AzureStorageKeyDetector"},
    {"name": "BasicAuthDetector"},
    {"name": "CloudantDetector"},
    {"name": "DiscordBotTokenDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "GitLabTokenDetector"},
    {"name": "IbmCloudIamDetector"},
    {"name": "IbmCosHmacDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "KeywordDetector"},
    {"name": "MailchimpDetector"},
    {"name": "NpmDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "PypiTokenDetector"},
    {"name": "SendGridDetector"},
    {"name": "SlackDetector"},
    {"name": "SoftlayerDetector"},
    {"name": "SquareOAuthDetector"},
    {"name": "StripeDetector"},
    {"name": "TelegramBotTokenDetector"},
    {"name": "TwilioKeyDetector"},
]

# Excluded detectors and rationale:
#   Base64HighEntropyString — false positives on base64-encoded binary data in docs
#   HexHighEntropyString    — false positives on hash values and hex color codes
#   IPPublicDetector        — produces no detections in practice on prose (v1.5.0)
#   OpenAIDetector          — only matches legacy sk-[20]T3BlbkFJ[20] format;
#                             new sk-proj-* format not detectable via this detector


def _replace_full_secret(line: str, prefix_value: str) -> str:
    """Replace prefix_value and any immediately following word chars with [KEY].

    Some detect-secrets detectors (e.g. GitHubTokenDetector) return only a token
    prefix (e.g. 'ghp') in secret_value rather than the full token. A naive
    line.replace(prefix, '[KEY]') would leave the token body exposed. This function
    replaces the prefix and any contiguous word characters that follow it.
    """
    escaped = re.escape(prefix_value)
    return re.sub(escaped + r"[A-Za-z0-9_/+=-]*", "[KEY]", line)


def redact(text: str) -> tuple[str, list[str]]:
    """Scan text line by line; replace detected secrets with [KEY].

    Returns:
        redacted_text: text with every detected secret replaced by [KEY]
        notices: human-readable list, one entry per redaction, e.g.
                 ["Redacted AWS Access Key on line 3"]
    """
    if not text:
        return text, []

    try:
        from detect_secrets.core.scan import scan_line
        from detect_secrets.settings import transient_settings
    except ImportError:
        # detect-secrets not installed — skip silently
        return text, []

    notices: list[str] = []
    lines = text.split("\n")
    result: list[str] = []

    try:
        with transient_settings({"plugins_used": _PLUGINS}):
            for i, line in enumerate(lines, 1):
                try:
                    seen: set[str] = set()
                    redacted_line = line
                    for secret in scan_line(line):
                        value = secret.secret_value
                        if value and value not in seen:
                            seen.add(value)
                            redacted_line = _replace_full_secret(redacted_line, value)
                            notices.append(f"Redacted {secret.type} on line {i}")
                except Exception:  # noqa: BLE001, S110  # fail-open: redaction must never lose data
                    pass  # skip line on error, preserve original
                result.append(redacted_line)
    except Exception:  # noqa: BLE001  # fail-open: if redaction crashes, return original text
        return text, []

    return "\n".join(result), notices
