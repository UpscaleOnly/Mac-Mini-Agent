"""
app/security.py — Security event detection and alerting (ADR-038)

Implements:
  - scan_security(...)        — pattern scanner, called from interceptor.py
  - write_security_event(...) — writes one row to security_events table
  - send_security_alert(...)  — real-time Telegram alert for high/critical events

Design rules (ADR-038 §5):
  - Scanner runs BEFORE the LLM call — after identity check, before token budget.
  - All pattern matching is pure Python string/regex — no LLM involved.
  - Detection does NOT block by default (flag-and-continue).
  - Exception: shell_injection (severity=high) is always blocked.
  - Real-time alerts fire immediately on high/critical. Quiet hours NOT respected
    for security alerts (ADR-038 §6).
  - medium/low events are written to security_events and surfaced in weekly digest only.

Call signature contract with interceptor.py:
  scan_security(text, persona, session_id, channel, channel_id, user_id)
  Returns SecurityScanResult with fields:
    .should_block  bool
    .block_reason  str
    .event_type    str | None
    .severity      str
    .pattern_matched str | None
    .send_alert    bool
    .clean         bool
"""

import re
import logging
import uuid
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern definitions (ADR-038 §5.2)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "disregard your system prompt",
    "forget everything",
    "new instructions:",
    "override:",
]

_PERSONA_OVERRIDE_PATTERNS = [
    "you are now",
    "act as",
    "pretend you are",
    "your new role is",
    "from now on you",
]

_SHELL_PATTERNS = [
    re.compile(r";\s*rm\s+-rf", re.IGNORECASE),
    re.compile(r"&&\s*curl", re.IGNORECASE),
    re.compile(r"\|\s*bash", re.IGNORECASE),
    re.compile(r"\$\("),
    re.compile(r"`[^`]+`"),
    re.compile(r">\s*/dev/"),
    re.compile(r"2>&1"),
]

_BASE64_RE = re.compile(r"(?<![a-zA-Z])[A-Za-z0-9+/]{40,}={0,2}(?![a-zA-Z])")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]{20,}")

_DEFAULT_ABNORMAL_LENGTH = 2000
_BRUTE_FORCE_WINDOW_SECONDS = 3600
_BRUTE_FORCE_THRESHOLD = 5

_block_timestamps: dict[str, list[float]] = defaultdict(list)


# ---------------------------------------------------------------------------
# Result dataclass — matches interceptor.py field expectations exactly
# ---------------------------------------------------------------------------

@dataclass
class SecurityScanResult:
    """
    Result of scan_security().
    interceptor.py reads: should_block, block_reason
    write_security_event reads: event_type, severity, pattern_matched, send_alert, clean
    """
    clean: bool = True
    should_block: bool = False
    block_reason: str = ""
    event_type: Optional[str] = None
    severity: str = "low"
    pattern_matched: Optional[str] = None
    action: str = "flagged"         # flagged | blocked
    send_alert: bool = False


# ---------------------------------------------------------------------------
# Public scanner — matches interceptor.py call signature exactly
# ---------------------------------------------------------------------------

async def scan_security(
    text: str,
    persona: str,
    session_id: Optional[uuid.UUID],
    channel: Optional[str],
    channel_id: str,
    user_id: str,
    abnormal_length_threshold: int = _DEFAULT_ABNORMAL_LENGTH,
) -> SecurityScanResult:
    """
    Run all pattern checks against the inbound input.
    Called from interceptor.py immediately after circuit breaker.

    Order (first match wins for block decisions):
      1. shell_injection   — high, block
      2. injection         — high, flag + alert
      3. persona_override  — high, flag + alert
      4. encoding_attack   — medium, flag (digest only)
      5. abnormal_length   — low, flag (digest only)
    """
    text_lower = text.lower()

    # 1. Shell injection — block
    for pattern in _SHELL_PATTERNS:
        m = pattern.search(text)
        if m:
            matched = m.group(0)
            log.warning("SECURITY: shell_injection — pattern: %r", matched)
            return SecurityScanResult(
                clean=False,
                should_block=True,
                block_reason=f"Shell injection pattern detected: {matched!r}",
                event_type="shell_injection",
                severity="high",
                pattern_matched=matched,
                action="blocked",
                send_alert=True,
            )

    # 2. Prompt injection — flag + alert
    for phrase in _INJECTION_PATTERNS:
        if phrase in text_lower:
            log.warning("SECURITY: injection — pattern: %r", phrase)
            return SecurityScanResult(
                clean=False,
                should_block=False,
                event_type="injection",
                severity="high",
                pattern_matched=phrase,
                action="flagged",
                send_alert=True,
            )

    # 3. Persona override — flag + alert
    for phrase in _PERSONA_OVERRIDE_PATTERNS:
        if phrase in text_lower:
            log.warning("SECURITY: persona_override — pattern: %r", phrase)
            return SecurityScanResult(
                clean=False,
                should_block=False,
                event_type="persona_override",
                severity="high",
                pattern_matched=phrase,
                action="flagged",
                send_alert=True,
            )

    # 4. Encoding attack — flag, digest only
    b64_match = _BASE64_RE.search(text)
    if b64_match:
        log.info("SECURITY: encoding_attack (base64)")
        return SecurityScanResult(
            clean=False,
            should_block=False,
            event_type="encoding_attack",
            severity="medium",
            pattern_matched="base64_payload",
            action="flagged",
            send_alert=False,
        )

    hex_match = _HEX_RE.search(text)
    if hex_match:
        log.info("SECURITY: encoding_attack (hex)")
        return SecurityScanResult(
            clean=False,
            should_block=False,
            event_type="encoding_attack",
            severity="medium",
            pattern_matched="hex_payload",
            action="flagged",
            send_alert=False,
        )

    # 5. Abnormal length — flag, digest only
    if len(text) > abnormal_length_threshold:
        log.info("SECURITY: abnormal_length — %d chars", len(text))
        return SecurityScanResult(
            clean=False,
            should_block=False,
            event_type="abnormal_length",
            severity="low",
            pattern_matched=f"length_{len(text)}",
            action="flagged",
            send_alert=False,
        )

    return SecurityScanResult(clean=True)


def record_block_for_brute_force(channel_id: str) -> Optional[SecurityScanResult]:
    """
    Call after any blocked request. Returns brute_force SecurityScanResult
    if threshold exceeded within window, else None.
    """
    now = time.time()
    cutoff = now - _BRUTE_FORCE_WINDOW_SECONDS
    _block_timestamps[channel_id] = [
        t for t in _block_timestamps[channel_id] if t > cutoff
    ]
    _block_timestamps[channel_id].append(now)
    count = len(_block_timestamps[channel_id])

    if count >= _BRUTE_FORCE_THRESHOLD:
        log.warning(
            "SECURITY: brute_force — channel_id %s, %d blocks in window",
            channel_id, count,
        )
        return SecurityScanResult(
            clean=False,
            should_block=False,
            event_type="brute_force",
            severity="high",
            pattern_matched=f"{count}_blocks_in_60min",
            action="flagged",
            send_alert=True,
        )
    return None


# ---------------------------------------------------------------------------
# Database writer
# ---------------------------------------------------------------------------

async def write_security_event(
    event_type: str,
    severity: str,
    source: str = "interceptor",
    persona: Optional[str] = None,
    session_id: Optional[uuid.UUID] = None,
    channel: Optional[str] = None,
    channel_id: Optional[str] = None,
    user_id: Optional[str] = None,
    input_text: Optional[str] = None,
    pattern_matched: Optional[str] = None,
    action_taken: str = "flagged",
    alert_sent: bool = False,
    raw_detail: Optional[dict] = None,
) -> Optional[uuid.UUID]:
    """Write one row to security_events. Returns event_id or None on error."""
    from app.db import get_pool
    import json

    input_snippet = (input_text or "")[:200] or None
    raw_detail_json = json.dumps(raw_detail) if raw_detail else None

    sql = """
        INSERT INTO security_events (
            event_type, severity, source, persona, session_id,
            channel, channel_id, user_id, input_snippet,
            pattern_matched, action_taken, alert_sent, raw_detail
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13::jsonb
        )
        RETURNING event_id
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                event_type, severity, source, persona, session_id,
                channel, channel_id, user_id, input_snippet,
                pattern_matched, action_taken, alert_sent, raw_detail_json,
            )
            event_id = row["event_id"]
            log.info(
                "security_events: %s/%s event_id=%s action=%s",
                event_type, severity, event_id, action_taken,
            )
            return event_id
    except Exception as e:
        log.error("write_security_event failed: %s", e)
        return None


async def mark_alert_sent(event_id: uuid.UUID) -> None:
    """Update alert_sent=TRUE after Telegram alert confirmed sent."""
    from app.db import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE security_events SET alert_sent = TRUE WHERE event_id = $1",
                event_id,
            )
    except Exception as e:
        log.error("mark_alert_sent failed for %s: %s", event_id, e)


# ---------------------------------------------------------------------------
# Real-time Telegram alert (ADR-038 §6) — quiet hours NOT respected
# ---------------------------------------------------------------------------

async def send_security_alert(
    event_type: str,
    severity: str,
    persona: Optional[str],
    session_id: Optional[uuid.UUID],
    channel: Optional[str],
    user_id: Optional[str],
    pattern_matched: Optional[str],
    input_text: Optional[str],
    action_taken: str,
) -> bool:
    """
    Send real-time Telegram security alert to operator.
    Quiet hours are NOT respected for high/critical (ADR-038 §6).
    Returns True if sent successfully.
    """
    import httpx
    from datetime import datetime, timezone
    from app.config import get_settings

    settings = get_settings()
    bot_token = settings.telegram_bot_token
    chat_id = settings.telegram_operator_id

    if not bot_token or not chat_id:
        log.error("send_security_alert: bot_token or operator_id not configured.")
        return False

    input_preview = ""
    if input_text:
        preview = input_text[:100]
        if len(input_text) > 100:
            preview += "..."
        input_preview = preview

    session_short = str(session_id)[:8] + "..." if session_id else "N/A"
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    event_labels = {
        "injection": "Prompt Injection Attempt",
        "persona_override": "Persona Override Attempt",
        "encoding_attack": "Encoding Attack Detected",
        "shell_injection": "Shell Injection Attempt",
        "abnormal_length": "Abnormal Input Length",
        "brute_force": "Brute Force Detected",
        "unauthorized_user": "Unauthorized User Attempt",
        "ssh_failure": "SSH Authentication Failure",
        "ssh_key_rejected": "SSH Key Rejected",
        "ssh_success": "SSH Login (Informational)",
    }
    event_label = event_labels.get(event_type, event_type.replace("_", " ").title())
    action_label = (
        "Blocked — request rejected"
        if action_taken == "blocked"
        else "Flagged — request continued"
    )

    lines = [
        "🚨 SECURITY ALERT — OpenClaw",
        "",
        f"Event: {event_label}",
        f"Severity: {severity.upper()}",
        "",
        f"Persona: {persona or 'N/A'}  |  Session: {session_short}",
        f"Channel: {channel or 'N/A'}  |  User: {user_id or 'N/A'}",
        "",
        f"Pattern: {pattern_matched or 'N/A'}",
    ]
    if input_preview:
        lines.append(f"Input (first 100 chars): {input_preview}")
    lines += [
        "",
        f"Action: {action_label}",
        f"Time: {now_utc}",
    ]

    message = "\n".join(lines)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                log.info(
                    "Security alert sent — event_type=%s severity=%s",
                    event_type, severity,
                )
                return True
            else:
                log.error(
                    "Security alert send failed: %d — %s",
                    resp.status_code, resp.text[:200],
                )
                return False
    except Exception as e:
        log.error("Security alert send error: %s", e)
        return False
