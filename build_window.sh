#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/云绝区零排队提醒.app"
CONTENTS="$APP/Contents"

mkdir -p "$CONTENTS/MacOS"

swiftc -O "$DIR/QueueWindow.swift" \
    -o "$CONTENTS/MacOS/CloudZZZQueueWindow" \
    -framework Cocoa

cp "$DIR/QueueWindow-Info.plist" "$CONTENTS/Info.plist"
chmod +x "$CONTENTS/MacOS/CloudZZZQueueWindow"

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

open "$APP"
echo "窗口已打开：$APP"
