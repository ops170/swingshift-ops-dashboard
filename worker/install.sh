#!/usr/bin/env bash
# Idempotent installer for the Swing Shift ops worker LaunchAgent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="${SCRIPT_DIR}/com.swingshift.opsworker.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.swingshift.opsworker.plist"
LABEL="com.swingshift.opsworker"
UID_NUM="$(id -u)"

echo "[install] user=$(whoami) uid=${UID_NUM} home=${HOME}"

# 1. Make required directories.
mkdir -p "${HOME}/SwingShift-ops/worker/logs"
mkdir -p "${HOME}/.config/swingshift-ops"
mkdir -p "${HOME}/Library/LaunchAgents"

# 2. Detect python3 and patch the plist so it uses an interpreter that exists.
PY_BIN=""
for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "${candidate}" ]; then
        PY_BIN="${candidate}"
        break
    fi
done
if [ -z "${PY_BIN}" ]; then
    PY_BIN="$(command -v python3 || true)"
fi
if [ -z "${PY_BIN}" ]; then
    echo "[install] ERROR: python3 not found. Install with: xcode-select --install   or   brew install python" >&2
    exit 1
fi
echo "[install] using python3: ${PY_BIN}"

# 3. Verify Python deps (requests, pyyaml). Install with --user if missing.
if ! "${PY_BIN}" -c "import requests, yaml" 2>/dev/null; then
    echo "[install] installing requests + pyyaml via pip3 --user"
    "${PY_BIN}" -m pip install --user --upgrade pip >/dev/null 2>&1 || true
    "${PY_BIN}" -m pip install --user requests pyyaml
fi

# 4. Render plist with the detected python and actual $HOME.
TMP_PLIST="$(mktemp -t opsworker_plist)"
sed \
    -e "s|/usr/bin/python3|${PY_BIN}|g" \
    -e "s|/Users/aaronallwood|${HOME}|g" \
    "${PLIST_SRC}" > "${TMP_PLIST}"
cp "${TMP_PLIST}" "${PLIST_DST}"
rm -f "${TMP_PLIST}"
echo "[install] wrote ${PLIST_DST}"

# 5. (Re)load the LaunchAgent.
launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/${UID_NUM}" "${PLIST_DST}"
launchctl enable "gui/${UID_NUM}/${LABEL}"
launchctl kickstart -k "gui/${UID_NUM}/${LABEL}"

echo "[install] done. Status:"
launchctl list | grep swingshift || echo "  (not yet visible; give it a few seconds and re-run: launchctl list | grep swingshift)"
echo
echo "Logs:  tail -f ${HOME}/SwingShift-ops/worker/logs/worker.out.log"
