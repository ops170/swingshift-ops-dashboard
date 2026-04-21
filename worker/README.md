# Swing Shift ops worker (v0.1)

Launchd-managed Python daemon that replaces all in-app scheduling. It runs at
OS level, survives reboots and app crashes, polls the dashboard repo, processes
prompt JSONs, writes heartbeats, and (soon, in v0.2) sends Textmagic SMS.

## What it does each 60s tick

1. `git pull --rebase origin main` in `~/SwingShift-ops/swingshift-ops-dashboard/`
2. Read every `.dashboard/prompts/*.json` not already under `processed/`
3. For each: write `.dashboard/tasks/{id}.json` (stub result in v0.1) and move
   the prompt into `.dashboard/prompts/processed/`
4. Write `.dashboard/heartbeat.json` with timestamp, pid, tick count
5. `git add -A && git commit && git push origin main` (skips if no changes)

Failures at any stage are logged and the loop continues — the daemon never
exits on a tick error. Unhandled exceptions cause exit 1; launchd restarts us
with `ThrottleInterval=10`.

## Install

```bash
cd ~/SwingShift-ops/worker   # or wherever you unpacked the source
./install.sh
```

The installer is idempotent — re-run it any time you update `worker.py`.
It will:

- create `~/SwingShift-ops/worker/logs/` and `~/.config/swingshift-ops/`
- detect an available `python3` and patch the plist accordingly
- ensure `requests` and `pyyaml` are installed for that interpreter
- copy the plist to `~/Library/LaunchAgents/` and load it with `launchctl`

## Check status

```bash
launchctl list | grep swingshift
tail -f ~/SwingShift-ops/worker/logs/worker.out.log
tail -f ~/SwingShift-ops/worker/logs/worker.err.log
cat ~/SwingShift-ops/swingshift-ops-dashboard/.dashboard/heartbeat.json
```

## Stop / uninstall

```bash
./uninstall.sh
```

## Config

Optional file `~/.config/swingshift-ops/worker.yaml`:

```yaml
tick_seconds: 60
repo_path: ~/SwingShift-ops/swingshift-ops-dashboard
log_level: INFO
```

Optional Textmagic creds at `~/.config/swingshift-ops/textmagic.env`
(not used for live sending in v0.1):

```
TEXTMAGIC_USERNAME=...
TEXTMAGIC_API_KEY=...
TEXTMAGIC_ENABLED=false
```

## Prerequisites the installer does NOT handle

- The dashboard repo must be cloned at `~/SwingShift-ops/swingshift-ops-dashboard`.
  If it isn't, the worker will still run, log a warning each tick, and retry —
  so you can clone it before or after install:

  ```bash
  git clone https://github.com/ops170/swingshift-ops-dashboard \
      ~/SwingShift-ops/swingshift-ops-dashboard
  ```

- `git` must be able to push. If the local network is proxy-blocked, pushes
  will log a warning each tick; the v0.2 fallback is not yet implemented.

## Versioning

- v0.1 (this): skeleton daemon, heartbeat, stub prompt routing, no live SMS.
- v0.2 (this week): real routing via `rules.yaml`, live Textmagic send,
  proxy-block push fallback.
