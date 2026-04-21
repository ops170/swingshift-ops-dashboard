#!/usr/bin/env python3
"""
Swing Shift ops worker - v0.1 (skeleton)
----------------------------------------
Long-running daemon managed by launchd. Every tick it:
  1. git pulls the dashboard repo
  2. processes any new prompt JSONs (stub routing in v0.1)
  3. writes a heartbeat
  4. commits + pushes changes back

Routing logic + Textmagic live send come in v0.2.

Config: ~/.config/swingshift-ops/worker.yaml (optional)
Logs:   stdout / stderr are redirected by launchd to worker/logs/*.log
"""

from __future__ import annotations

import glob
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ---------- config ----------

WORKER_VERSION = "0.1.0"

DEFAULT_CONFIG = {
    "tick_seconds": 60,
    "repo_path": "~/SwingShift-ops/swingshift-ops-dashboard",
    "log_level": "INFO",
}

CONFIG_PATH = Path("~/.config/swingshift-ops/worker.yaml").expanduser()

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


def _load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            import yaml  # type: ignore
            with CONFIG_PATH.open("r") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                cfg.update(data)
        except Exception as exc:
            # Intentionally don't fail startup on a bad config file.
            _log("WARNING", f"could not read config {CONFIG_PATH}: {exc}")
    return cfg


# ---------- logging ----------

_current_level = "INFO"


def _set_log_level(level: str) -> None:
    global _current_level
    level = (level or "INFO").upper()
    if level not in _LEVELS:
        level = "INFO"
    _current_level = level


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(level: str, msg: str) -> None:
    level = level.upper()
    if _LEVELS.get(level, 20) < _LEVELS.get(_current_level, 20):
        return
    stream = sys.stderr if level in ("WARNING", "ERROR") else sys.stdout
    stream.write(f"[{_iso_now()}] [{level}] {msg}\n")
    stream.flush()


# ---------- signal handling ----------

_shutdown = False


def _handle_signal(signum, _frame):
    global _shutdown
    name = {signal.SIGTERM: "SIGTERM", signal.SIGINT: "SIGINT"}.get(signum, str(signum))
    _log("INFO", f"received {name}; will exit after current tick")
    _shutdown = True


# ---------- git helpers ----------

def _run(cmd, cwd=None, timeout=30):
    """Run a subprocess; return (rc, stdout, stderr). Never raises on nonzero rc."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def _git_pull(repo_path: Path) -> bool:
    rc, _out, err = _run(
        ["git", "pull", "--rebase", "origin", "main"],
        cwd=str(repo_path),
        timeout=30,
    )
    if rc == 0:
        _log("INFO", "git pull ok")
        return True
    _log("WARNING", f"git pull failed rc={rc}: {err}")
    return False


def _git_has_changes(repo_path: Path) -> bool:
    rc, out, _err = _run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_path),
        timeout=10,
    )
    return rc == 0 and bool(out.strip())


def _git_commit_push(repo_path: Path, message: str) -> None:
    if not _git_has_changes(repo_path):
        _log("DEBUG", "no changes to commit")
        return
    rc, _out, err = _run(["git", "add", "-A"], cwd=str(repo_path), timeout=15)
    if rc != 0:
        _log("WARNING", f"git add failed: {err}")
        return
    rc, _out, err = _run(
        ["git", "commit", "-m", message],
        cwd=str(repo_path),
        timeout=15,
    )
    if rc != 0:
        _log("WARNING", f"git commit failed: {err}")
        return
    rc, _out, err = _run(
        ["git", "push", "origin", "main"],
        cwd=str(repo_path),
        timeout=30,
    )
    if rc != 0:
        # v0.2 TODO: proxy-block fallback goes here.
        _log("WARNING", f"git push failed rc={rc}: {err}")
        return
    _log("INFO", "git push ok")


# ---------- prompt processing ----------

def _process_prompts(repo_path: Path) -> int:
    prompts_dir = repo_path / ".dashboard" / "prompts"
    processed_dir = prompts_dir / "processed"
    tasks_dir = repo_path / ".dashboard" / "tasks"

    if not prompts_dir.exists():
        _log("DEBUG", f"prompts dir does not exist yet: {prompts_dir}")
        return 0

    processed_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    pattern = str(prompts_dir / "*.json")
    for path_str in sorted(glob.glob(pattern)):
        path = Path(path_str)
        # Skip anything already in processed/
        try:
            if processed_dir in path.parents:
                continue
        except Exception:
            pass

        try:
            with path.open("r") as f:
                prompt = json.load(f)
        except Exception as exc:
            _log("WARNING", f"could not parse prompt {path.name}: {exc}")
            continue

        pid = prompt.get("id") or path.stem
        kind = prompt.get("kind")
        action = prompt.get("action")
        _log("INFO", f"prompt id={pid} kind={kind} action={action}")

        # v0.1 stub: write task result, move prompt to processed.
        task = {
            "id": pid,
            "kind": kind,
            "state": "done",
            "result": "v0.1 stub - routing not implemented",
            "processed_at": _iso_now(),
        }
        try:
            with (tasks_dir / f"{pid}.json").open("w") as f:
                json.dump(task, f, indent=2)
        except Exception as exc:
            _log("WARNING", f"could not write task {pid}: {exc}")
            continue

        try:
            path.rename(processed_dir / f"{pid}.json")
        except Exception as exc:
            _log("WARNING", f"could not move prompt {path.name}: {exc}")
            continue

        count += 1

    return count


def _write_heartbeat(repo_path: Path, tick_count: int) -> None:
    dash = repo_path / ".dashboard"
    dash.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": _iso_now(),
        "worker_version": WORKER_VERSION,
        "pid": os.getpid(),
        "tick_count": tick_count,
    }
    try:
        with (dash / "heartbeat.json").open("w") as f:
            json.dump(payload, f, indent=2)
    except Exception as exc:
        _log("WARNING", f"could not write heartbeat: {exc}")


# ---------- main loop ----------

def run_forever() -> int:
    cfg = _load_config()
    _set_log_level(cfg.get("log_level", "INFO"))
    tick_seconds = int(cfg.get("tick_seconds", 60))
    repo_path = Path(str(cfg.get("repo_path"))).expanduser()

    _log("INFO", f"worker v{WORKER_VERSION} starting; pid={os.getpid()} repo={repo_path}")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not repo_path.exists():
        _log("ERROR", f"repo path missing: {repo_path}. Clone it first; worker will sleep and keep retrying.")

    tick = 0
    while not _shutdown:
        tick += 1
        _log("INFO", f"tick {tick} start")

        if repo_path.exists():
            _git_pull(repo_path)
            n = _process_prompts(repo_path)
            _write_heartbeat(repo_path, tick)
            _git_commit_push(repo_path, f"worker tick {_iso_now()}: processed {n} prompts")
        else:
            _log("WARNING", f"skipping tick work - repo not present at {repo_path}")

        _log("INFO", f"tick {tick} end; sleeping {tick_seconds}s")

        # Sleep in small slices so shutdown is responsive.
        slept = 0
        while slept < tick_seconds and not _shutdown:
            time.sleep(1)
            slept += 1

    _log("INFO", "shutdown complete")
    return 0


def main() -> int:
    try:
        return run_forever()
    except SystemExit:
        raise
    except BaseException:
        sys.stderr.write(f"[{_iso_now()}] [ERROR] unhandled exception:\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    sys.exit(main())
