#!/bin/bash
set -euo pipefail

STATE_FILE="$HOME/Library/Application Support/CloudZZZQueueMonitor/state/status.json"
if [[ ! -f "$STATE_FILE" ]]; then
  echo "No status file yet: $STATE_FILE"
  exit 1
fi
exec /usr/bin/python3 -c 'import json, pathlib, sys; print(json.dumps(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")), ensure_ascii=False, indent=2))' "$STATE_FILE"
