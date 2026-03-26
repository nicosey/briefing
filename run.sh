#!/bin/bash
# Wrapper for launchd: generate briefing then publish.
# Usage: ./run.sh <topic> <dest>
# Example: ./run.sh robotics x

set -euo pipefail

TOPIC="${1:-robotics}"
DEST="${2:-}"

cd "$(dirname "$0")"

python3 briefing.py "$TOPIC"

if [ -n "$DEST" ]; then
    python3 publish.py "$DEST"
else
    python3 publish.py
fi
