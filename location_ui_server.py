#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import random
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
SET_LOCATION = ROOT / "set-location.sh"
PRESETS = ROOT / "location-presets.json"
STATE_FILE = ROOT / "location-ui-state.json"
HOST = "127.0.0.1"
PORT = 8765
EARTH_RADIUS_M = 6371000.0
DEFAULT_TARGET = {"name": "London", "lat": 51.5074, "lon": -0.1278}
DEFAULT_SETTINGS = {
    "wobble": {"radius_m": 8.0, "interval_s": 1.5},
    "route": {"speed_mps": 2.2, "interval_s": 4.0, "wobble_m": 2.0, "loop": True},
}


def run_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)


def parse_dumpsys_location(text: str) -> dict[str, object]:
    result: dict[str, object] = {"providers": {}, "location_enabled": None}
    enabled = re.search(r"Location Setting:\s+(true|false)", text)
    if enabled:
        result["location_enabled"] = enabled.group(1) == "true"

    for provider in ("fused", "gps", "network", "passive"):
        match = re.search(
            rf"{provider} provider:.*?last location=Location\[{provider} ([^,\]]+),([^ \]]+)",
            text,
            re.S,
        )
        if match:
            result["providers"][provider] = {
                "lat": float(match.group(1)),
                "lon": float(match.group(2)),
            }

    return result


def emulator_status() -> dict[str, object]:
    devices = run_command("adb", "devices", "-l")
    location = run_command("adb", "shell", "dumpsys", "location")

    connected = "emulator-" in devices.stdout and "device" in devices.stdout
    status: dict[str, object] = {
        "connected": connected,
        "devices_output": devices.stdout.strip(),
        "providers": {},
        "location_enabled": None,
    }
    if connected and location.returncode == 0:
        status.update(parse_dumpsys_location(location.stdout))
    return status


def apply_location(lat: float, lon: float) -> dict[str, object]:
    applied = run_command(str(SET_LOCATION), str(lat), str(lon))
    status = emulator_status()
    ok = applied.returncode == 0
    return {
        "ok": ok,
        "requested": {"lat": lat, "lon": lon},
        "output": (applied.stdout + applied.stderr).strip(),
        "status": status,
    }


def apply_motion_location(lat: float, lon: float, speed_mps: float = 0.0, bearing_deg: float = 0.0) -> dict[str, object]:
    applied = run_command(
        str(SET_LOCATION),
        str(lat),
        str(lon),
        "--speed-mps",
        str(speed_mps),
        "--bearing-deg",
        str(bearing_deg),
    )
    status = emulator_status()
    ok = applied.returncode == 0
    return {
        "ok": ok,
        "requested": {"lat": lat, "lon": lon, "speed_mps": speed_mps, "bearing_deg": bearing_deg},
        "output": (applied.stdout + applied.stderr).strip(),
        "status": status,
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def interpolate_point(start: dict[str, float], end: dict[str, float], ratio: float) -> dict[str, float]:
    return {
        "lat": start["lat"] + (end["lat"] - start["lat"]) * ratio,
        "lon": start["lon"] + (end["lon"] - start["lon"]) * ratio,
    }


def offset_point(lat: float, lon: float, distance_m: float, bearing_rad: float) -> dict[str, float]:
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    angular_distance = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return {"lat": math.degrees(lat2), "lon": math.degrees(lon2)}


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def sanitize_point(point: dict[str, object]) -> dict[str, float]:
    return {"lat": float(point["lat"]), "lon": float(point["lon"])}


def ensure_state_shape(raw: dict[str, object] | None) -> dict[str, object]:
    raw = raw or {}
    last_target = raw.get("last_target") or DEFAULT_TARGET
    route_points = raw.get("route_points") or []
    settings = raw.get("settings") or {}
    wobble = settings.get("wobble") or DEFAULT_SETTINGS["wobble"]
    route = settings.get("route") or DEFAULT_SETTINGS["route"]
    return {
        "last_target": {
            "name": str(last_target.get("name", DEFAULT_TARGET["name"])),
            "lat": float(last_target.get("lat", DEFAULT_TARGET["lat"])),
            "lon": float(last_target.get("lon", DEFAULT_TARGET["lon"])),
        },
        "route_points": [sanitize_point(point) for point in route_points],
        "settings": {
            "wobble": {
                "radius_m": float(wobble.get("radius_m", DEFAULT_SETTINGS["wobble"]["radius_m"])),
                "interval_s": float(wobble.get("interval_s", DEFAULT_SETTINGS["wobble"]["interval_s"])),
            },
            "route": {
                "speed_mps": float(route.get("speed_mps", DEFAULT_SETTINGS["route"]["speed_mps"])),
                "interval_s": float(route.get("interval_s", DEFAULT_SETTINGS["route"]["interval_s"])),
                "wobble_m": float(route.get("wobble_m", DEFAULT_SETTINGS["route"]["wobble_m"])),
                "loop": bool(route.get("loop", DEFAULT_SETTINGS["route"]["loop"])),
            },
        },
        "updated_at": float(raw.get("updated_at", time.time())),
    }


class PersistentState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data = ensure_state_shape(self._load_raw())
        self._save_locked()

    def _load_raw(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return None

    def _save_locked(self) -> None:
        self.data["updated_at"] = time.time()
        self.path.write_text(json.dumps(self.data, indent=2))

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return json.loads(json.dumps(self.data))

    def update_target(self, target: dict[str, object]) -> None:
        with self.lock:
            self.data["last_target"] = {
                "name": str(target.get("name", self.data["last_target"]["name"])),
                "lat": float(target["lat"]),
                "lon": float(target["lon"]),
            }
            self._save_locked()

    def update_route_points(self, route_points: list[dict[str, object]]) -> None:
        with self.lock:
            self.data["route_points"] = [sanitize_point(point) for point in route_points]
            self._save_locked()

    def update_settings(self, settings: dict[str, object]) -> None:
        with self.lock:
            if "wobble" in settings:
                self.data["settings"]["wobble"] = {
                    "radius_m": float(settings["wobble"]["radius_m"]),
                    "interval_s": float(settings["wobble"]["interval_s"]),
                }
            if "route" in settings:
                self.data["settings"]["route"] = {
                    "speed_mps": float(settings["route"]["speed_mps"]),
                    "interval_s": float(settings["route"]["interval_s"]),
                    "wobble_m": float(settings["route"]["wobble_m"]),
                    "loop": bool(settings["route"]["loop"]),
                }
            self._save_locked()


PERSIST = PersistentState(STATE_FILE)


class SimulationManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state: dict[str, object] = {
            "mode": "idle",
            "running": False,
            "config": {},
            "current": None,
            "last_output": "",
            "started_at": None,
            "updated_at": None,
        }

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def stop(self) -> dict[str, object]:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.5)
        with self._lock:
            self._thread = None
            self._stop_event = threading.Event()
            self._state["mode"] = "idle"
            self._state["running"] = False
            self._state["config"] = {}
            self._state["updated_at"] = time.time()
        return self.snapshot()

    def start_wobble(self, center: dict[str, object], radius_m: float, interval_s: float) -> dict[str, object]:
        self.stop()
        normalized_center = {
            "name": str(center.get("name", "Target")),
            "lat": float(center["lat"]),
            "lon": float(center["lon"]),
        }
        PERSIST.update_target(normalized_center)
        PERSIST.update_settings({"wobble": {"radius_m": radius_m, "interval_s": interval_s}})
        config = {
            "center": sanitize_point(normalized_center),
            "radius_m": float(radius_m),
            "interval_s": float(interval_s),
        }
        with self._lock:
            self._state = {
                "mode": "wobble",
                "running": True,
                "config": config,
                "current": config["center"],
                "last_output": "",
                "started_at": time.time(),
                "updated_at": time.time(),
            }
        self._thread = threading.Thread(target=self._run_wobble, args=(config,), daemon=True)
        self._thread.start()
        return self.snapshot()

    def start_route(
        self,
        points: list[dict[str, object]],
        speed_mps: float,
        interval_s: float,
        loop: bool,
        wobble_m: float,
    ) -> dict[str, object]:
        if len(points) < 2:
            raise ValueError("Route needs at least two points.")

        self.stop()
        normalized_points = [sanitize_point(point) for point in points]
        PERSIST.update_route_points(normalized_points)
        PERSIST.update_target({"name": "Route start", **normalized_points[-1]})
        PERSIST.update_settings(
            {"route": {"speed_mps": speed_mps, "interval_s": interval_s, "wobble_m": wobble_m, "loop": loop}}
        )
        config = {
            "points": normalized_points,
            "speed_mps": float(speed_mps),
            "interval_s": float(interval_s),
            "loop": bool(loop),
            "wobble_m": float(wobble_m),
        }
        with self._lock:
            self._state = {
                "mode": "route",
                "running": True,
                "config": config,
                "current": normalized_points[0],
                "last_output": "",
                "started_at": time.time(),
                "updated_at": time.time(),
            }
        self._thread = threading.Thread(target=self._run_route, args=(config,), daemon=True)
        self._thread.start()
        return self.snapshot()

    def _record(self, current: dict[str, float], output: str) -> None:
        PERSIST.update_target({"name": "Last live point", **current})
        with self._lock:
            self._state["current"] = current
            self._state["last_output"] = output
            self._state["updated_at"] = time.time()

    def _finish(self) -> None:
        with self._lock:
            self._state["running"] = False
            self._state["updated_at"] = time.time()

    def _run_wobble(self, config: dict[str, object]) -> None:
        center = config["center"]
        radius_m = float(config["radius_m"])
        interval_s = float(config["interval_s"])
        previous = center

        while not self._stop_event.is_set():
            distance = random.uniform(0, radius_m)
            bearing = random.uniform(0, 2 * math.pi)
            current = offset_point(center["lat"], center["lon"], distance, bearing)
            course = bearing_deg(previous["lat"], previous["lon"], current["lat"], current["lon"])
            speed = max(distance / max(interval_s, 0.5), 0.7)
            result = apply_motion_location(current["lat"], current["lon"], speed_mps=speed, bearing_deg=course)
            self._record(current, result["output"])
            previous = current
            if self._stop_event.wait(interval_s):
                break

        self._finish()

    def _run_route(self, config: dict[str, object]) -> None:
        points = config["points"]
        speed_mps = float(config["speed_mps"])
        interval_s = float(config["interval_s"])
        loop = bool(config["loop"])
        wobble_m = float(config["wobble_m"])

        segments: list[dict[str, object]] = []
        total_distance = 0.0
        for index in range(len(points) - 1):
            start = points[index]
            end = points[index + 1]
            length = haversine_m(start["lat"], start["lon"], end["lat"], end["lon"])
            segments.append({"start": start, "end": end, "length": length})
            total_distance += length

        if total_distance <= 0:
            result = apply_location(points[0]["lat"], points[0]["lon"])
            self._record(points[0], result["output"])
            self._finish()
            return

        progress_m = 0.0
        min_step_m = 8.0
        effective_interval_s = max(interval_s, min_step_m / max(speed_mps, 0.5))
        while not self._stop_event.is_set():
            current_base = points[-1]
            remaining = progress_m
            for segment in segments:
                if segment["length"] == 0:
                    continue
                if remaining <= segment["length"]:
                    ratio = remaining / segment["length"]
                    current_base = interpolate_point(segment["start"], segment["end"], ratio)
                    break
                remaining -= segment["length"]

            current = current_base
            if wobble_m > 0:
                current = offset_point(
                    current_base["lat"],
                    current_base["lon"],
                    random.uniform(0, wobble_m),
                    random.uniform(0, 2 * math.pi),
                )

            lookahead_progress = min(progress_m + max(speed_mps * effective_interval_s, min_step_m), total_distance)
            next_base = current_base
            next_remaining = lookahead_progress
            for segment in segments:
                if segment["length"] == 0:
                    continue
                if next_remaining <= segment["length"]:
                    ratio = next_remaining / segment["length"]
                    next_base = interpolate_point(segment["start"], segment["end"], ratio)
                    break
                next_remaining -= segment["length"]

            course = bearing_deg(current["lat"], current["lon"], next_base["lat"], next_base["lon"])
            result = apply_motion_location(current["lat"], current["lon"], speed_mps=speed_mps, bearing_deg=course)
            self._record(current, result["output"])

            if self._stop_event.wait(effective_interval_s):
                break

            progress_m += speed_mps * effective_interval_s
            if progress_m >= total_distance:
                if loop:
                    progress_m = progress_m % total_distance
                else:
                    final_result = apply_motion_location(points[-1]["lat"], points[-1]["lon"], speed_mps=0.2, bearing_deg=course)
                    self._record(points[-1], final_result["output"])
                    break

        self._finish()


SIMULATOR = SimulationManager()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict[str, object], code: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self) -> None:
        data = (ROOT / "location-ui.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _full_status(self) -> dict[str, object]:
        return {
            "ok": True,
            "status": emulator_status(),
            "simulation": SIMULATOR.snapshot(),
            "persisted": PERSIST.snapshot(),
        }

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            return self._send_html()
        if path == "/api/status":
            return self._send_json(self._full_status())
        if path == "/api/presets":
            return self._send_json({"ok": True, "presets": json.loads(PRESETS.read_text())})
        return self._send_json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        try:
            if path == "/api/set-location":
                payload = self._read_json()
                lat = float(payload["lat"])
                lon = float(payload["lon"])
                label = str(payload.get("name", "Custom location"))
                PERSIST.update_target({"name": label, "lat": lat, "lon": lon})
                result = apply_location(lat, lon)
                result["simulation"] = SIMULATOR.snapshot()
                result["persisted"] = PERSIST.snapshot()
                return self._send_json(result, 200 if result["ok"] else 500)

            if path == "/api/persist":
                payload = self._read_json()
                if "target" in payload:
                    PERSIST.update_target(payload["target"])
                if "route_points" in payload:
                    PERSIST.update_route_points(list(payload["route_points"]))
                if "settings" in payload:
                    PERSIST.update_settings(payload["settings"])
                return self._send_json({"ok": True, "persisted": PERSIST.snapshot()})

            if path == "/api/sim/stop":
                return self._send_json(
                    {"ok": True, "simulation": SIMULATOR.stop(), "status": emulator_status(), "persisted": PERSIST.snapshot()}
                )

            if path == "/api/sim/wobble/start":
                payload = self._read_json()
                simulation = SIMULATOR.start_wobble(
                    center=payload["center"],
                    radius_m=float(payload.get("radius_m", 8)),
                    interval_s=float(payload.get("interval_s", 1.5)),
                )
                return self._send_json(
                    {"ok": True, "simulation": simulation, "status": emulator_status(), "persisted": PERSIST.snapshot()}
                )

            if path == "/api/sim/route/start":
                payload = self._read_json()
                simulation = SIMULATOR.start_route(
                    points=list(payload["points"]),
                    speed_mps=float(payload.get("speed_mps", 1.4)),
                    interval_s=float(payload.get("interval_s", 1.0)),
                    loop=bool(payload.get("loop", False)),
                    wobble_m=float(payload.get("wobble_m", 0)),
                )
                return self._send_json(
                    {"ok": True, "simulation": simulation, "status": emulator_status(), "persisted": PERSIST.snapshot()}
                )
        except (KeyError, TypeError, ValueError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            return self._send_json({"ok": False, "error": str(exc)}, 500)

        return self._send_json({"ok": False, "error": "Not found"}, 404)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Location UI available at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
