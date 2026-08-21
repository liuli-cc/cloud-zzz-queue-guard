#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/云绝区零排队提醒.app"
CONTENTS="$APP/Contents"
BUILD_DIR="$DIR/.build-window"

osascript -e 'tell application "云绝区零排队灵动岛" to quit' >/dev/null 2>&1 || true
sleep 1

rm -rf "$APP" "$BUILD_DIR"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources" "$BUILD_DIR/dist" "$BUILD_DIR/work"

swiftc -parse-as-library -O "$DIR/QueueWindow.swift" \
    -o "$CONTENTS/MacOS/CloudZZZQueueMonitor" \
    -framework Cocoa \
    -framework SwiftUI

cp "$DIR/QueueWindow-Info.plist" "$CONTENTS/Info.plist"

if command -v pyinstaller >/dev/null 2>&1; then
    pyinstaller --clean --onefile \
        --name CloudZZZQueueMonitorCore \
        --distpath "$BUILD_DIR/dist" \
        --workpath "$BUILD_DIR/work" \
        --specpath "$BUILD_DIR" \
        "$DIR/cloud_zzz_queue_guard_gui.py" >/dev/null
    cp "$BUILD_DIR/dist/CloudZZZQueueMonitorCore" "$CONTENTS/Resources/CloudZZZQueueMonitorCore"
    chmod +x "$CONTENTS/Resources/CloudZZZQueueMonitorCore"
else
    echo "未找到 pyinstaller；灵动岛仍会构建，但需要已有后台监测进程写入状态。"
fi

chmod +x "$CONTENTS/MacOS/CloudZZZQueueMonitor"

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

open "$APP"
echo "窗口已打开：$APP"
