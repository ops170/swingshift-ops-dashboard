"""Load routing rules from the dashboard repo.

v0.1: rules.yaml is expected to be created by a parallel task. Until then we
return an empty dict and log a warning. v0.2 will consume these rules.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _warn(msg: str) -> None:
    sys.stderr.write(f"[{_iso_now()}] [WARNING] {msg}\n")
    sys.stderr.flush()


def load_rules(repo_root) -> dict:
    """Read .dashboard/config/rules.yaml under ``repo_root``.

    Returns an empty dict (and logs a warning) if the file is missing or
    cannot be parsed. Never raises.
    """
    root = Path(str(repo_root)).expanduser()
    rules_path = root / ".dashboard" / "config" / "rules.yaml"

    if not rules_path.exists():
        _warn(f"rules file missing: {rules_path} (expected until parallel task commits it)")
        return {}

    try:
        import yaml  # type: ignore
    except Exception as exc:
        _warn(f"pyyaml not importable: {exc}")
        return {}

    try:
        with rules_path.open("r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        _warn(f"could not parse rules.yaml: {exc}")
        return {}

    if not isinstance(data, dict):
        _warn(f"rules.yaml did not parse to a dict (got {type(data).__name__})")
        return {}

    return data
