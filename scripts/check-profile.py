"""Check the released KiCad netlist, firmware constants and CAD manifest against the profile."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path, help="KiCad schematic export in kicadxml format")
    args = parser.parse_args()

    profile = json.loads((ROOT / "hardware/profile.json").read_text(encoding="utf-8"))
    header = (ROOT / "include/profile.hpp").read_text(encoding="utf-8")
    require(f'"{profile["device_id"]}"' in header, "Device ID differs between profile and firmware.")
    constants = {
        "sda_gpio": profile["i2c"]["sda"],
        "scl_gpio": profile["i2c"]["scl"],
        "i2c_hz": profile["i2c"]["frequency_hz"],
        "sensor_address": profile["i2c"]["address"],
        "enable_gpio": profile["exhaust"]["enable"],
        "tach_gpio": profile["exhaust"]["tach"],
        "pulses_per_revolution": profile["exhaust"]["pulses_per_revolution"],
        **profile["policy"],
    }
    for name, value in constants.items():
        match = re.search(rf"\b{name}\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\s*;", header)
        require(match and int(match[1], 0) == value, f"Firmware constant mismatch: {name}")

    nets = {
        net.attrib["name"].lstrip("/"): {(node.attrib["ref"], node.attrib["pin"]) for node in net.findall("node")}
        for net in ElementTree.parse(args.netlist).findall("./nets/net")
    }
    expected = {
        "SDA": {("U1", str(constants["sda_gpio"])), ("U2", "SDA")},
        "SCL": {("U1", str(constants["scl_gpio"])), ("U2", "SCL")},
        "FAN_EN": {("U1", str(constants["enable_gpio"])), ("U3", "ON"), ("R2", "1")},
        "TACH": {("U1", str(constants["tach_gpio"])), ("M1", "3"), ("R1", "2")},
        "3V3": {("U1", "3V3"), ("U2", "VIN"), ("R1", "1")},
        "12V_IN": {("J1", "1"), ("F1", "1")},
        "12V_FUSED": {("F1", "2"), ("U3", "VIN"), ("C1", "2"), ("TVS1", "2")},
        "FAN_12V": {("U3", "VOUT"), ("M1", "2"), ("D1", "2")},
        "GND": {("U1", "GND"), ("U2", "GND"), ("U3", "GND"), ("M1", "1"), ("J1", "2"),
                ("C1", "1"), ("R2", "2"), ("D1", "1"), ("TVS1", "1")},
    }
    require(nets == expected, "KiCad netlist differs from the reviewed wiring.")

    audit = json.loads((ROOT / "outputs/cad-audit.json").read_text(encoding="utf-8"))
    box = profile["enclosure_mm"]
    expected_bounds = [box["length"], box["width"], box["base_height"] + box["lid_thickness"]]
    require(audit["verified"] and audit["insertion_units"] == 4, "CAD file must be verified in millimeters.")
    require(audit["bounds"] == {"min": [0, 0, 0], "max": expected_bounds}, "Overall CAD dimensions differ.")
    dwg_hash = hashlib.sha256((ROOT / "outputs/SAPR-001-assembly.dwg").read_bytes()).hexdigest()
    require(dwg_hash == audit["sha256"], "CAD file differs from the verified release.")
    print("PASS KiCad nets, firmware profile, DWG dimensions and digest")


if __name__ == "__main__":
    main()
