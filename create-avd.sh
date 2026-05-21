#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./android-env.sh
source "$ROOT_DIR/android-env.sh"

AVD_NAME="${1:-codex-play-35}"
PACKAGE="system-images;android-35;google_apis_playstore;arm64-v8a"
DEVICE="${ANDROID_DEVICE_ID:-pixel_8}"

if avdmanager list avd | grep -q "Name: $AVD_NAME"; then
  echo "AVD '$AVD_NAME' already exists."
  exit 0
fi

echo "no" | avdmanager create avd -n "$AVD_NAME" -k "$PACKAGE" -d "$DEVICE"

CONFIG_FILE="$HOME/.android/avd/$AVD_NAME.avd/config.ini"
if [ -f "$CONFIG_FILE" ]; then
  # Force hardware keyboard passthrough so macOS keyboard input works reliably.
  perl -0pi -e 's/^hw\.keyboard=.*/hw.keyboard=yes/m' "$CONFIG_FILE"
  perl -0pi -e 's/^PlayStore\.enabled=.*/PlayStore.enabled=yes/m' "$CONFIG_FILE"
  # Favor lower render cost and hardware acceleration for game testing.
  perl -0pi -e 's/^hw\.gpu\.enabled=.*/hw.gpu.enabled=yes/m' "$CONFIG_FILE"
  perl -0pi -e 's/^hw\.gpu\.mode=.*/hw.gpu.mode=host/m' "$CONFIG_FILE"
  perl -0pi -e 's/^hw\.lcd\.width=.*/hw.lcd.width=720/m' "$CONFIG_FILE"
  perl -0pi -e 's/^hw\.lcd\.height=.*/hw.lcd.height=1600/m' "$CONFIG_FILE"
  perl -0pi -e 's/^hw\.lcd\.density=.*/hw.lcd.density=320/m' "$CONFIG_FILE"
  perl -0pi -e 's/^hw\.cpu\.ncore=.*/hw.cpu.ncore=4/m' "$CONFIG_FILE"
  perl -0pi -e 's/^hw\.ramSize=.*/hw.ramSize=3G/m' "$CONFIG_FILE"
  perl -0pi -e 's/^vm\.heapSize=.*/vm.heapSize=384M/m' "$CONFIG_FILE"
  perl -0pi -e 's/^showDeviceFrame=.*/showDeviceFrame=no/m' "$CONFIG_FILE"
fi

echo "Created AVD '$AVD_NAME'."
