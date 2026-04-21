#!/usr/bin/env bash
# Unload + remove the Swing Shift ops worker LaunchAgent.
set -u

LABEL="com.swingshift.opsworker"
UID_NUM="$(id -u)"
PLIST_DST="${HOME}/Library/LaunchAgents/com.swingshift.opsworker.plist"

launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
rm -f "${PLIST_DST}"
echo "Uninstalled ${LABEL}. (Source tree under ~/SwingShift-ops/ was NOT deleted.)"
