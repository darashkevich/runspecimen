"""Select or create an iPhone on the installed Simulator SDK's runtime.

Listing every available device instance (`simctl list devices`) can block
for minutes while CoreSimulator enumerates the catalog. Runtimes and
device types are small lists. Create one named simulator from those.
"""
from __future__ import annotations

import json
import subprocess
import sys

CREATED_NAME = "RSObserveCI"


def select(data, sdk):
    prefix = "com.apple.CoreSimulator.SimRuntime.iOS-" + sdk.replace(".", "-")
    for runtime, devices in data.get("devices", {}).items():
        if runtime != prefix and not runtime.startswith(prefix + "-"):
            continue
        for device in devices:
            if device.get("isAvailable") and "iPhone" in device.get("name", ""):
                return device["udid"]
    raise ValueError(f"No available iPhone runtime matching installed SDK {sdk}")


def runtime_identifier(runtimes, sdk):
    prefix = "com.apple.CoreSimulator.SimRuntime.iOS-" + sdk.replace(".", "-")
    for runtime in runtimes.get("runtimes", []):
        ident = runtime.get("identifier", "")
        if ident != prefix and not ident.startswith(prefix + "-"):
            continue
        if runtime.get("isAvailable", True):
            return ident
    raise ValueError(f"No available iPhone runtime matching installed SDK {sdk}")


def iphone_devicetype(devicetypes):
    for device_type in devicetypes.get("devicetypes", []):
        name = device_type.get("name", "")
        ident = device_type.get("identifier", "")
        if "iPhone" in name and ident:
            return ident
    raise ValueError("No iPhone device type")


def _simctl_json(*args: str) -> dict:
    raw = subprocess.check_output(["xcrun", "simctl", *args], text=True)
    return json.loads(raw)


def create(sdk: str) -> str:
    runtime = runtime_identifier(_simctl_json("list", "runtimes", "-j"), sdk)
    device_type = iphone_devicetype(_simctl_json("list", "devicetypes", "-j"))
    subprocess.run(
        ["xcrun", "simctl", "delete", CREATED_NAME],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    udid = subprocess.check_output(
        ["xcrun", "simctl", "create", CREATED_NAME, device_type, runtime],
        text=True,
    ).strip()
    if not udid:
        raise ValueError("simctl create returned an empty UDID")
    print(
        f"created name={CREATED_NAME} type={device_type} runtime={runtime}",
        file=sys.stderr,
    )
    return udid


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--create":
        print(create(sys.argv[2]))
    elif len(sys.argv) == 2:
        print(select(json.load(sys.stdin), sys.argv[1]))
    else:
        raise SystemExit("usage: select_ios_simulator.py [--create] SDK_VERSION")
