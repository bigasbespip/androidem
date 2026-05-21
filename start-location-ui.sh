#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./android-env.sh
source "$ROOT_DIR/android-env.sh"

exec python3 "$ROOT_DIR/location_ui_server.py"
