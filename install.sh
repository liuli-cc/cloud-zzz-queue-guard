#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.liuli.cloud-zzz-queue-guard"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST="$LAUNCH_AGENTS/$LABEL.plist"
TEMPLATE="$DIR/com.liuli.cloud-zzz-queue-guard.plist.template"

mkdir -p "$LAUNCH_AGENTS" "$DIR/logs" "$DIR/state"

/usr/bin/python3 -m py_compile "$DIR/cloud_zzz_queue_guard.py"

sed "s|__PROJECT_DIR__|$DIR|g" "$TEMPLATE" > "$PLIST"

if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  sleep 1
fi

for _ in 1 2 3 4 5; do
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1; then
    break
  fi
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  sleep 1
done

launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true

echo "Installed and started: $LABEL"
echo "Project: $DIR"
echo "Run ./status.sh to inspect the current state."
echo
echo "If the log shows 'Operation not permitted', macOS needs Full Disk Access."
echo "Please add /usr/bin/python3 in System Settings > Privacy & Security > Full Disk Access."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" >/dev/null 2>&1 || true
