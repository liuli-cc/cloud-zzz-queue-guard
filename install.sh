#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.liuli.cloud-zzz-queue-monitor"
LEGACY_LABEL="com.liuli.cloud-zzz-queue-guard"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST="$LAUNCH_AGENTS/$LABEL.plist"
LEGACY_PLIST="$LAUNCH_AGENTS/$LEGACY_LABEL.plist"
TEMPLATE="$DIR/com.liuli.cloud-zzz-queue-guard.plist.template"

mkdir -p "$LAUNCH_AGENTS" "$DIR/logs" "$DIR/state"

APP_EXECUTABLE="$DIR/云绝区零排队提醒.app/Contents/MacOS/CloudZZZQueueMonitor"
BRIDGE_EXECUTABLE="$DIR/云绝区零排队提醒.app/Contents/Helpers/CloudZZZLifecycleBridge"
if [[ ! -x "$APP_EXECUTABLE" ]]; then
  echo "Missing app executable: $APP_EXECUTABLE" >&2
  echo "Run ./build_window.sh first, then retry installation." >&2
  exit 1
fi
if [[ ! -x "$BRIDGE_EXECUTABLE" ]]; then
  echo "Missing lifecycle bridge: $BRIDGE_EXECUTABLE" >&2
  echo "Run ./build_window.sh first, then retry installation." >&2
  exit 1
fi

cp "$TEMPLATE" "$PLIST"
/usr/bin/plutil -replace ProgramArguments -json "[\"$BRIDGE_EXECUTABLE\"]" "$PLIST"
/usr/bin/plutil -replace StandardOutPath -string "$DIR/logs/bridge.log" "$PLIST"
/usr/bin/plutil -replace StandardErrorPath -string "$DIR/logs/bridge.log" "$PLIST"

osascript -e 'tell application id "com.liuli.cloud-zzz-queue-monitor" to quit' >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)/$LEGACY_LABEL" >/dev/null 2>&1 || true
launchctl disable "gui/$(id -u)/$LEGACY_LABEL" >/dev/null 2>&1 || true
rm -f "$LEGACY_PLIST"

if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  sleep 1
fi

installed=0
for _ in 1 2 3 4 5; do
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1; then
    installed=1
    break
  fi
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  sleep 1
done

if [[ "$installed" -ne 1 ]] || ! launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  echo "LaunchAgent registration failed: $PLIST" >&2
  exit 1
fi

launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started: $LABEL"
echo "Project: $DIR"
echo "Run ./status.sh to inspect the current state."
echo
echo "The lifecycle bridge now launches and closes the monitor together with 云·绝区零."
echo "If macOS still blocks the queue database, add this app under Full Disk Access:"
echo "$DIR/云绝区零排队提醒.app"
