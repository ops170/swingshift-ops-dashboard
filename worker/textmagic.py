"""Textmagic SMS wrapper (skeleton).

v0.1 is not wired to live send. We read credentials from
``~/.config/swingshift-ops/textmagic.env`` (KEY=value format). If the file
doesn't exist we just log what we would have sent and return None.

textmagic.env expected keys (all optional today):
    TEXTMAGIC_USERNAME=...
    TEXTMAGIC_API_KEY=...
    TEXTMAGIC_FROM=...   # optional
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CREDS_PATH = Path("~/.config/swingshift-ops/textmagic.env").expanduser()
API_URL = "https://rest.textmagic.com/api/v2/messages"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(level: str, msg: str) -> None:
    stream = sys.stderr if level in ("WARNING", "ERROR") else sys.stdout
    stream.write(f"[{_iso_now()}] [{level}] {msg}\n")
    stream.flush()


def _load_creds() -> Optional[dict]:
    if not CREDS_PATH.exists():
        return None
    creds: dict = {}
    try:
        with CREDS_PATH.open("r") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                creds[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as exc:
        _log("WARNING", f"could not read textmagic creds: {exc}")
        return None
    # Require the minimum pair.
    if not creds.get("TEXTMAGIC_USERNAME") or not creds.get("TEXTMAGIC_API_KEY"):
        _log("WARNING", "textmagic.env present but missing TEXTMAGIC_USERNAME / TEXTMAGIC_API_KEY")
        return None
    return creds


def send_sms(to_phone: str, body: str) -> Optional[dict]:
    """Send an SMS via Textmagic.

    Returns the parsed API response dict on success, or None if the worker is
    not configured (v0.1 always hits this branch) or the send failed.
    """
    snippet = (body or "")[:60]
    creds = _load_creds()
    if not creds:
        _log("INFO", f"textmagic not configured; would have sent: {snippet}")
        return None

    # v0.1 skeleton: we DO NOT live-send today. Keep the real POST behind a
    # feature flag so v0.2 can flip it on.
    enabled = creds.get("TEXTMAGIC_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled:
        _log("INFO", f"textmagic creds present but TEXTMAGIC_ENABLED!=true; would have sent: {snippet}")
        return None

    try:
        import requests  # type: ignore
    except Exception as exc:
        _log("WARNING", f"requests not importable: {exc}")
        return None

    payload = {"phones": to_phone, "text": body}
    try:
        resp = requests.post(
            API_URL,
            data=payload,
            auth=(creds["TEXTMAGIC_USERNAME"], creds["TEXTMAGIC_API_KEY"]),
            timeout=15,
        )
    except Exception as exc:
        _log("WARNING", f"textmagic POST exception: {exc}")
        return None

    if resp.status_code >= 300:
        _log("WARNING", f"textmagic POST failed {resp.status_code}: {resp.text[:200]}")
        return None

    try:
        return resp.json()
    except Exception:
        return {"status_code": resp.status_code, "text": resp.text}
