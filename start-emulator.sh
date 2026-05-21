#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./android-env.sh
source "$ROOT_DIR/android-env.sh"

AVD_NAME="codex-play-35"

if [ "${1:-}" != "" ] && [[ "${1:-}" != -* ]]; then
  AVD_NAME="$1"
  shift
fi

if ! avdmanager list avd | grep -q "Name: $AVD_NAME"; then
  echo "AVD '$AVD_NAME' does not exist yet."
  echo "Run ./create-avd.sh first."
  exit 1
fi

exec emulator @"$AVD_NAME" \
  -netdelay none \
  -netspeed full \
  -gpu host \
  -camera-back virtualscene \
  -camera-front none \
  -memory 3072 \
  -cores 4 \
  "$@"
