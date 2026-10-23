#!/bin/bash
set -euo pipefail

LABEL="com.liuli.cloud-zzz-queue-monitor"
LEGACY_LABEL="com.liuli.cloud-zzz-queue-guard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LEGACY_PLIST="$HOME/Library/LaunchAgents/$LEGACY_LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)/$LEGACY_LABEL" >/dev/null 2>&1 || true
osascript -e 'tell application id "com.liuli.cloud-zzz-queue-monitor" to quit' >/dev/null 2>&1 || true
rm -f "$PLIST" "$LEGACY_PLIST"

echo "Uninstalled: $LABEL"
