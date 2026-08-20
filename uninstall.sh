#!/bin/bash
set -euo pipefail

LABEL="com.liuli.cloud-zzz-queue-guard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"

echo "Uninstalled: $LABEL"
