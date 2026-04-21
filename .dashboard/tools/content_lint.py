#!/usr/bin/env python3
"""
Swing Shift content linter.

Loads .dashboard/config/rules.yaml (auto-located relative to the repo root) and
checks one or more files for banned signers, banned terms, capacity overage,
missing signer on outbound emails, and missing send sentinel on ready-to-send
files.

Usage:
    python content_lint.py <file1> [<file2> ...]
    cat file | python content_lint.py -

Exit codes:
    0  clean
    1  violations found
    2  usage / config error
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR  pyyaml is required: pip install pyyaml\n")
    sys.exit(2)


RULES_RELATIVE = Path(".dashboard/config/rules.yaml")
SUPPORTED_TEXT_EXTS = {".md", ".txt", ".eml", ".html"}
NEEDS_EXTRACTION_EXTS = {".xlsx", ".pdf"}

CAPACITY_RE = re.compile(
    r"(up to|accommodate|host|seat|fit)\s+(\d+)\s+(people|guests|attendees|pax)",
    re.IGNORECASE,
)
BANNED_SIGNER_LINE_RE = re.compile(
    r"(?i)^\s*-?\s*(larry|larry botman)\s*[,.]?\s*$"
)
EMAIL_MARKERS = ("Subject:", "Dear", "Hi there")


def locate_rules(start: Path) -> Path | None:
    """Walk up from start looking for .dashboard/config/rules.yaml."""
    here = start.resolve()
    candidates = [here] + list(here.parents)
    for base in candidates:
        candidate = base / RULES_RELATIVE
        if candidate.is_file():
            return candidate
    # Last-ditch: script-relative search
    script_here = Path(__file__).resolve()
    for base in [script_here.parent] + list(script_here.parents):
        candidate = base / RULES_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def load_rules() -> dict:
    rules_path = locate_rules(Path.cwd())
    if rules_path is None:
        sys.stderr.write(
            f"ERROR  could not locate {RULES_RELATIVE} from cwd or script path\n"
        )
        sys.exit(2)
    try:
        with rules_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        sys.stderr.write(f"ERROR  failed to parse {rules_path}: {exc}\n")
        sys.exit(2)
    return data


def read_target(path_arg: str) -> tuple[str, str, list[str]]:
    """Return (display_name, raw_text, lines). Handles '-' for stdin."""
    if path_arg == "-":
        text = sys.stdin.read()
        return ("<stdin>", text, text.splitlines())
    p = Path(path_arg)
    if not p.is_file():
        raise FileNotFoundError(path_arg)
    ext = p.suffix.lower()
    if ext in NEEDS_EXTRACTION_EXTS:
        return (str(p), "", [])  # signalled via ext check later
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"cannot read {p}: {exc}") from exc
    return (str(p), text, text.splitlines())


def looks_like_email(text: str) -> bool:
    return any(marker in text for marker in EMAIL_MARKERS)


def last_n_nonempty_lines(lines: Iterable[str], n: int) -> list[str]:
    non_empty = [ln for ln in lines if ln.strip()]
    return non_empty[-n:] if non_empty else []


def check_file(
    display: str,
    text: str,
    lines: list[str],
    rules: dict,
    ext: str,
) -> list[tuple[str, str, str]]:
    """Return list of (rule, locator, message) violations."""
    violations: list[tuple[str, str, str]] = []

    if ext in NEEDS_EXTRACTION_EXTS:
        print(
            f"NOTE  {display}: text extraction needed for {ext} — "
            "out of scope for v1"
        )
        return violations

    banned_terms = [t for t in (rules.get("banned_terms") or []) if t]
    capacity_max = int(rules.get("capacity_max", 0) or 0)
    signer = rules.get("signer") or ""
    signer_aliases = rules.get("signer_aliases") or []
    send_sentinel = rules.get("send_sentinel") or ""

    # Banned signer — only check the tail region (last 15 non-empty lines).
    # We still report the true 1-based line number from the full file.
    indexed = [(i + 1, ln) for i, ln in enumerate(lines)]
    nonempty_indexed = [(i, ln) for i, ln in indexed if ln.strip()]
    tail = nonempty_indexed[-15:] if nonempty_indexed else []
    for lineno, ln in tail:
        if BANNED_SIGNER_LINE_RE.match(ln):
            violations.append(
                (
                    "banned_signer",
                    f"{display}:{lineno}",
                    f"signer line matches banned signer: {ln.strip()!r}",
                )
            )

    # Banned terms — case-insensitive, report first hit per term per file.
    lowered_lines = [ln.lower() for ln in lines]
    for term in banned_terms:
        needle = term.lower()
        for idx, low in enumerate(lowered_lines, start=1):
            if needle in low:
                violations.append(
                    (
                        "banned_term",
                        f"{display}:{idx}",
                        f"banned term present: {term!r}",
                    )
                )
                break

    # Capacity overage
    if capacity_max > 0:
        for idx, ln in enumerate(lines, start=1):
            for m in CAPACITY_RE.finditer(ln):
                try:
                    n = int(m.group(2))
                except ValueError:
                    continue
                if n > capacity_max:
                    violations.append(
                        (
                            "capacity_overage",
                            f"{display}:{idx}",
                            f"claims {n} {m.group(3)} but capacity_max={capacity_max}",
                        )
                    )

    # Missing signer on outbound emails
    if looks_like_email(text):
        needles = [s for s in ([signer] + list(signer_aliases)) if s]
        tail_lines = last_n_nonempty_lines(lines, 10)
        tail_text = "\n".join(tail_lines)
        if not any(n and n in tail_text for n in needles):
            violations.append(
                (
                    "missing_signer",
                    f"{display}:EOF",
                    f"outbound email missing signer ({signer!r}) in last 10 non-empty lines",
                )
            )

    # Missing send sentinel
    name = os.path.basename(display)
    if fnmatch.fnmatch(name, "*_ready_to_send*") or fnmatch.fnmatch(
        name, "*_approved*"
    ):
        if send_sentinel and send_sentinel not in text:
            violations.append(
                (
                    "missing_send_sentinel",
                    f"{display}:EOF",
                    f"ready-to-send file missing sentinel {send_sentinel!r}",
                )
            )

    return violations


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a]
    check_mode = False
    if "--check" in args:
        check_mode = True
        args = [a for a in args if a != "--check"]

    if not args:
        sys.stderr.write(
            "Usage: python content_lint.py <file1> [<file2> ...]\n"
            "       cat file | python content_lint.py -\n"
        )
        return 2

    rules = load_rules()

    total_violations = 0
    for target in args:
        try:
            display, text, lines = read_target(target)
        except FileNotFoundError:
            sys.stderr.write(f"ERROR  file not found: {target}\n")
            return 2
        except RuntimeError as exc:
            sys.stderr.write(f"ERROR  {exc}\n")
            return 2

        ext = "" if target == "-" else Path(target).suffix.lower()
        # Unknown extensions that aren't the special-extraction set: allow
        # and treat as text (stdin case too).
        if target != "-" and ext and ext not in SUPPORTED_TEXT_EXTS and ext not in NEEDS_EXTRACTION_EXTS:
            print(
                f"NOTE  {display}: extension {ext} not in supported set "
                f"{sorted(SUPPORTED_TEXT_EXTS)} — linting as plain text anyway"
            )

        violations = check_file(display, text, lines, rules, ext)
        for rule, locator, message in violations:
            print(f"FAIL  {rule}  {locator}  {message}")
        total_violations += len(violations)

    if total_violations == 0:
        if not check_mode:
            print("OK  0 violations")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
