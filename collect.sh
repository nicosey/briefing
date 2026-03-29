#!/bin/bash
# Wrapper for launchd: collect hourly search results for a topic.
# Usage: ./collect.sh <topic>

set -euo pipefail

TOPIC="${1:-robotics}"

cd "$(dirname "$0")"

python3 collect.py "$TOPIC"
