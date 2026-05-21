# Android Emulator Setup

This workspace is set up for a Google Play-enabled Android emulator on Apple Silicon macOS.

## What this gives you

- Google Play services and Play Store support
- A repeatable emulator launch flow
- Command-line location spoofing for app testing
- F-Droid as a second app store

## Files

- `android-env.sh`: shared SDK and Java environment
- `create-avd.sh`: creates the Play-enabled AVD
- `start-emulator.sh`: launches the emulator
- `start-emulator-game-mode.sh`: launches the emulator with more aggressive 3D-oriented settings
- `wait-for-boot.sh`: waits for Android to finish booting
- `set-location.sh`: spoofs device GPS coordinates
- `start-location-ui.sh`: starts the local browser UI for fake locations
- `install-fdroid.sh`: installs F-Droid on the running emulator

## Standard workflow

1. `./create-avd.sh`
2. `./start-emulator.sh`
3. In another terminal: `./wait-for-boot.sh`
4. Sign into Google Play if you want Play Store access.
5. Install F-Droid: `./install-fdroid.sh`
6. Spoof location when needed: `./set-location.sh 51.5074 -0.1278`

## Better fake-location UI

1. Start the panel: `./start-location-ui.sh`
2. Open `http://127.0.0.1:8765`
3. Click the map, drag the pin, use a preset city, or enter coordinates manually
4. Use `GPS Wobble` to simulate small real-world drift around the target pin
5. Switch to `Route Draw Mode` to add waypoints and simulate walking along a route

The panel shows the emulator's current fused and GPS location after each change, and it can now run background wobble or route-walking simulations while your app stays open in the emulator.

The panel also remembers your last target location, saved route, and movement settings across restarts, so you can pick up where you left off.

## 3D game performance

- The emulator is tuned for a lighter 720x1600 display with hardware GPU mode.
- `./start-emulator.sh` launches with `-gpu host` and the emulator virtual scene camera enabled.
- `./start-emulator-game-mode.sh` uses a safer 3D-oriented profile with 3GB RAM, 4 cores, and no boot animation.
- If 3D performance is still poor, close memory-heavy apps on the Mac first. This machine is currently under memory pressure, which can force slower graphics paths.

## Notes

- The AVD uses `system-images;android-35;google_apis_playstore;arm64-v8a`.
- `adb emu geo fix` is usually enough for location-based testing and works well with emulator-based workflows.
- The local UI repeats the location update once, polls `dumpsys location`, and can run timed wobble or route simulations through the same external control path.
- If your app specifically checks for mock providers, test both with and without app-side mock-location detection enabled.
