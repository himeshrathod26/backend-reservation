#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:?usage: ./scripts/burst.sh <BASE_URL> [REQUESTS] [WORKERS]}"
REQUESTS="${2:-500}"
WORKERS="${3:-100}"
python3 scripts/burst.py "$BASE_URL" --requests "$REQUESTS" --workers "$WORKERS"
