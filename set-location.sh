#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./android-env.sh
source "$ROOT_DIR/android-env.sh"

status_line() {
  adb shell dumpsys location | python3 -c '
import re
import sys

text = sys.stdin.read()
for provider in ("fused", "gps"):
    match = re.search(rf"last location=Location\[{provider} ([^,\]]+),([^ \]]+)", text)
    if match:
        print(f"{provider}:{match.group(1)},{match.group(2)}")
'
}

SPEED_MPS="0"
BEARING_DEG="0"

if [ "$#" -lt 2 ]; then
  echo "Usage: ./set-location.sh <latitude> <longitude> [--speed-mps <mps>] [--bearing-deg <deg>]"
  exit 1
fi

LAT="$1"
LON="$2"
shift 2

while [ "$#" -gt 0 ]; do
  case "$1" in
    --speed-mps)
      SPEED_MPS="${2:-0}"
      shift 2
      ;;
    --bearing-deg)
      BEARING_DEG="${2:-0}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

adb wait-for-device >/dev/null

# Send the fix twice with a short delay so fused location listeners tend to pick
# it up more quickly than with a single point injection.
adb emu geo fix "$LON" "$LAT" >/dev/null
sleep 0.35
adb emu geo fix "$LON" "$LAT" >/dev/null

# For walking-style movement, also send NMEA sentences carrying speed and course.
python3 - "$LAT" "$LON" "$SPEED_MPS" "$BEARING_DEG" <<'PY' | while IFS= read -r sentence; do
import datetime as dt
import math
import sys

lat = float(sys.argv[1])
lon = float(sys.argv[2])
speed_mps = float(sys.argv[3])
bearing_deg = float(sys.argv[4])

def checksum(body: str) -> str:
    value = 0
    for ch in body:
        value ^= ord(ch)
    return f"*{value:02X}"

def dd_to_nmea_lat(value: float) -> tuple[str, str]:
    hemi = "N" if value >= 0 else "S"
    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60
    return f"{degrees:02d}{minutes:07.4f}", hemi

def dd_to_nmea_lon(value: float) -> tuple[str, str]:
    hemi = "E" if value >= 0 else "W"
    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60
    return f"{degrees:03d}{minutes:07.4f}", hemi

utc_now = dt.datetime.now(dt.timezone.utc)
time_str = utc_now.strftime("%H%M%S") + f".{int(utc_now.microsecond / 10000):02d}"
date_str = utc_now.strftime("%d%m%y")
lat_str, lat_hemi = dd_to_nmea_lat(lat)
lon_str, lon_hemi = dd_to_nmea_lon(lon)
speed_knots = speed_mps * 1.94384449
speed_kmh = speed_mps * 3.6

rmc = f"GPRMC,{time_str},A,{lat_str},{lat_hemi},{lon_str},{lon_hemi},{speed_knots:.2f},{bearing_deg:.2f},{date_str},,,A"
gga = f"GPGGA,{time_str},{lat_str},{lat_hemi},{lon_str},{lon_hemi},1,08,0.9,15.0,M,0.0,M,,"
vtg = f"GPVTG,{bearing_deg:.2f},T,,M,{speed_knots:.2f},N,{speed_kmh:.2f},K,A"

for body in (rmc, gga, vtg):
    print(f"${body}{checksum(body)}")
PY
  adb emu geo nmea "$sentence" >/dev/null
done

VERIFY_OUTPUT=""
for _ in 1 2 3 4 5; do
  VERIFY_OUTPUT="$(status_line || true)"
  if printf '%s\n' "$VERIFY_OUTPUT" | grep -q "$LAT"; then
    break
  fi
  sleep 0.4
done

echo "Location requested: lat=$LAT lon=$LON"
echo "Movement hint: speed_mps=$SPEED_MPS bearing_deg=$BEARING_DEG"
if [ -n "$VERIFY_OUTPUT" ]; then
  echo "$VERIFY_OUTPUT"
fi
