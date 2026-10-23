#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/云绝区零排队提醒.app"
CONTENTS="$APP/Contents"
BUILD_DIR="$DIR/.build-window"
BRIDGE="$CONTENTS/Helpers/CloudZZZLifecycleBridge"

osascript -e 'tell application "云绝区零排队灵动岛" to quit' >/dev/null 2>&1 || true
sleep 1

rm -rf "$APP" "$BUILD_DIR"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources" "$CONTENTS/Helpers" "$BUILD_DIR/dist" "$BUILD_DIR/work"

swiftc -parse-as-library -O "$DIR/QueueWindow.swift" \
    -o "$CONTENTS/MacOS/CloudZZZQueueMonitor" \
    -framework Cocoa \
    -framework SwiftUI

swiftc -parse-as-library -O "$DIR/CloudZZZLifecycleBridge.swift" \
    -o "$BRIDGE" \
    -framework Cocoa

cp "$DIR/QueueWindow-Info.plist" "$CONTENTS/Info.plist"

PYINSTALLER=()
if command -v pyinstaller >/dev/null 2>&1; then
    PYINSTALLER=(pyinstaller)
elif python3 -c 'import PyInstaller' >/dev/null 2>&1; then
    PYINSTALLER=(python3 -m PyInstaller)
fi

if [[ "${#PYINSTALLER[@]}" -gt 0 ]]; then
    "${PYINSTALLER[@]}" --onefile \
        --name CloudZZZQueueMonitorCore \
        --distpath "$BUILD_DIR/dist" \
        --workpath "$BUILD_DIR/work" \
        --specpath "$BUILD_DIR" \
        "$DIR/cloud_zzz_queue_guard_gui.py" >/dev/null
    cp "$BUILD_DIR/dist/CloudZZZQueueMonitorCore" "$CONTENTS/Resources/CloudZZZQueueMonitorCore"
    chmod +x "$CONTENTS/Resources/CloudZZZQueueMonitorCore"
else
    echo "未找到 PyInstaller，无法打包排队数据核心。" >&2
    exit 1
fi

chmod +x "$CONTENTS/MacOS/CloudZZZQueueMonitor" "$BRIDGE"

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

echo "构建完成：$APP"
