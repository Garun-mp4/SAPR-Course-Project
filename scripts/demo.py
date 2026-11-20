#!/usr/bin/env python3
"""Run the shared C++ controller and optionally post its frames to the AirCheck API."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(url, token, frame=None):
    headers = {"Authorization": "Bearer " + token, "X-AirCheck-Source": "simulator"}
    body = None
    if frame is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(frame, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=body, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_scenario(command, name, root):
    output = subprocess.check_output([*command, name], cwd=root, encoding="utf-8")
    return {frame["controller"]["uptime_ms"]: frame for frame in map(json.loads, output.splitlines())}


def state(frame):
    sensor = frame["sensors"][0]
    fan = frame["actuators"]["exhaust"]
    return (sensor["values"]["co2"], sensor["status"], fan["requested_on"], fan["rpm"], fan["status"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl", action="store_true", help="Run the native simulator inside Ubuntu on Windows.")
    parser.add_argument("--url", help="Isolated AirCheck origin. Use HTTPS or HTTP on loopback.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    command = ["wsl", "-d", "Ubuntu", "--", "./build/sapr-simulator"] if args.wsl else ["./build/sapr-simulator"]

    runs = {name: run_scenario(command, name, root) for name in ("normal", "sensor", "tach", "network")}
    normal = runs["normal"]
    expected = {
        0: (700, "ok", False, None, "unknown"),
        5000: (1050, "ok", True, None, "unknown"),
        6000: (1050, "ok", True, 1800, "measured"),
        10000: (900, "ok", True, 1800, "measured"),
        15000: (750, "ok", True, 1800, "measured"),
        304000: (750, "ok", True, 1800, "measured"),
        305000: (750, "ok", False, None, "unknown"),
    }
    for elapsed, snapshot in expected.items():
        require(state(normal[elapsed]) == snapshot, f"Unexpected standard state at {elapsed} ms")
    require(state(runs["sensor"][10000]) == (1050, "timeout", False, None, "unknown"), "Sensor loss")
    require(state(runs["tach"][10000]) == (900, "ok", False, None, "fault"), "Tachometer fault")
    require(state(runs["tach"][15000])[-1] == "fault", "Tachometer fault must remain latched")
    require(all(state(runs["network"][ms]) == snapshot for ms, snapshot in expected.items()), "Network independence")

    for elapsed, frame in normal.items():
        ppm, _, on, rpm, _ = state(frame)
        print(f"{elapsed / 1000:6.1f} s  CO2={ppm:4d} ppm  fan={'ON ' if on else 'OFF'}  RPM={rpm}")
    print("PASS local scenarios: normal, sensor fault, tach fault, network independence")
    if not args.url:
        return

    origin = urlsplit(args.url)
    require(origin.scheme == "https" or (origin.scheme == "http" and origin.hostname in ("localhost", "127.0.0.1", "::1")),
            "Only HTTPS and loopback HTTP are accepted")
    require(not (origin.path.strip("/") or origin.username or origin.password or origin.query or origin.fragment),
            "Specify an AirCheck origin without a path or credentials")
    token = os.environ.get("SAPR_DEVICE_TOKEN", "")
    require(len(token) >= 32, "Set SAPR_DEVICE_TOKEN in the local environment")
    endpoint = args.url.rstrip("/") + "/api/v1/telemetry"

    first = normal[0]
    status, _ = send(endpoint, token + "-invalid", first)
    require(status in (401, 403), f"Invalid token returned {status}")
    status, payload = send(endpoint, token, first)
    require(status == 201 and not payload["data"]["duplicate"], f"First POST returned {status}: {payload}")
    status, duplicate = send(endpoint, token, first)
    require(status == 200 and duplicate["data"]["duplicate"] and duplicate["data"]["id"] == payload["data"]["id"],
            "Duplicate POST must keep its original record")

    def deliver(frame):
        status, result = send(endpoint, token, frame)
        require(status == 201 and result["data"]["current"], f"AirCheck POST returned {status}: {result}")
        status, head = send(endpoint, token)
        require(status == 200 and head["data"]["frame"] == frame, f"AirCheck GET mismatch: {head}")
        print(f"AirCheck POST 201 / GET 200  co2={state(frame)[0]}  fan={state(frame)[2]}  sequence={frame['sequence']}")

    for elapsed, frame in normal.items():
        if elapsed != 0:
            deliver(frame)
    deliver(runs["sensor"][10000])
    deliver(runs["tach"][10000])

    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        try:
            send(f"http://127.0.0.1:{unavailable.getsockname()[1]}/api/v1/telemetry", token, runs["network"][5000])
        except URLError:
            pass
        else:
            raise RuntimeError("Expected an actual connection error while the receiver is unavailable")
    deliver(runs["network"][6000])
    deliver(runs["network"][305000])
    print("PASS AirCheck: auth, duplicate, wire schema, current snapshot and delivery after an outage")


if __name__ == "__main__":
    main()
