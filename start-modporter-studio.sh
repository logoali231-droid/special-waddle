#!/usr/bin/env bash
# ModPorter Studio - double-click launcher (macOS / Linux)
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it from https://www.python.org/downloads/"
  exit 1
fi
python3 -m modporter.cli studio
