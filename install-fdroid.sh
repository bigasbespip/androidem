#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./android-env.sh
source "$ROOT_DIR/android-env.sh"

TMP_APK="${TMPDIR:-/tmp}/F-Droid.apk"

curl -L "https://f-droid.org/F-Droid.apk" -o "$TMP_APK"
adb wait-for-device >/dev/null
adb install -r "$TMP_APK"
echo "F-Droid installed."

