#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/云绝区零排队提醒.app"
CONTENTS="$APP/Contents"

osascript -e 'tell application "云绝区零排队监测" to quit' >/dev/null 2>&1 || true
sleep 1

mkdir -p "$CONTENTS/MacOS"

swiftc -O "$DIR/QueueWindow.swift" \
    -o "$CONTENTS/MacOS/CloudZZZQueueWindow" \
    -framework Cocoa

cp "$DIR/QueueWindow-Info.plist" "$CONTENTS/Info.plist"
chmod +x "$CONTENTS/MacOS/CloudZZZQueueWindow"

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

open "$APP"
echo "窗口已打开：$APP"
