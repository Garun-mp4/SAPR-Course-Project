"""Check the released KiCad netlist, firmware constants and CAD manifest against the profile."""
import argparse
import csv
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
        "tach_min_rpm": profile["exhaust"]["min_rpm"],
        "tach_max_rpm": profile["exhaust"]["max_rpm"],
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
        "SDA": {("A1", str(constants["sda_gpio"])), ("A2", "SDA")},
        "SCL": {("A1", str(constants["scl_gpio"])), ("A2", "SCL")},
        "FAN_EN": {("A1", str(constants["enable_gpio"])), ("A3", "ON"), ("R2", "1")},
        "TACH": {("A1", str(constants["tach_gpio"])), ("M1", "3"), ("X2", "3"), ("R1", "2")},
        "3V3": {("A1", "3V3"), ("R1", "1")},
        "USB_5V_D": {("A1", "5V"), ("A2", "VIN")},
        "12V_IN": {("X1", "1"), ("F1", "1")},
        "12V_FUSED": {("F1", "2"), ("A3", "VIN"), ("C1", "2"), ("VD1", "2")},
        "FAN_12V": {("A3", "VOUT"), ("M1", "2"), ("X2", "2"), ("VD2", "2")},
        "GND": {("A1", "GND"), ("A2", "GND"), ("A3", "GND"), ("M1", "1"), ("X1", "2"), ("X2", "1"),
                ("C1", "1"), ("R2", "2"), ("VD2", "1"), ("VD1", "1")},
    }
    require(nets == expected, "KiCad netlist differs from the reviewed wiring.")
    with (ROOT / "hardware/bom.csv").open(encoding="utf-8", newline="") as source:
        bom_refs = [row["Обозначение"] for row in csv.DictReader(source)]
    require(len(bom_refs) == len(set(bom_refs)), "Duplicate reference in BOM.")
    require({ref for nodes in expected.values() for ref, _ in nodes} == set(bom_refs) - {"PS1", "PS2"},
            "BOM references differ from the netlist.")
    with (ROOT / "hardware/connections.csv").open(encoding="utf-8", newline="") as source:
        documented_nets = {row["Цепь"] for row in csv.DictReader(source)}
    require(documented_nets - {"USB_5V", "FAN_GND"} == set(nets),
            "Wiring table net names differ from the netlist.")

    audit = json.loads((ROOT / "outputs/cad-audit.json").read_text(encoding="utf-8"))
    box = profile["enclosure_mm"]
    expected_bounds = [box["length"], box["width"], box["base_height"] + box["lid_thickness"]]
    require(audit["verified"] and audit["insertion_units"] == 4, "CAD file must be verified in millimeters.")
    require(audit["bounds"] == {"min": [0, 0, 0], "max": expected_bounds}, "Overall CAD dimensions differ.")
    require(audit["reopened_acis"]["bounds"] == audit["bounds"], "Reopened DWG dimensions differ.")
    solids = {solid["handle"]: solid for solid in audit["reopened_acis"]["solids"]}
    for module in box["modules"]:
        solid = solids[module["handle"]]
        require((solid["min"], solid["max"]) == (module["min"], module["max"]),
                f"Envelope of {module['ref']} differs from the reopened DWG.")
    require(solids["EE"]["max"] == [box["length"], box["width"], box["base_height"]], "Base bounds differ.")
    require(solids["102"]["min"] == [0, 0, box["base_height"]], "Lid is not at its mating plane.")
    features = audit["r02_verification"]
    require(features["audit"] == {"errors": 0, "warnings": 0, "lossless": True}, "Reopen audit failed.")
    require(features["slots"] == box["lid_slots"] and
            features["slot_corner_counts"] == [8] * len(box["lid_slots"]["y"]), "Lid slots differ.")
    port_boxes = []
    for port in box["ports"]:
        x0 = 0 if port["side"] == "left" else box["length"] - box["wall"]
        y, z = port["y"], port["z"]
        port_boxes.append([[x0, y, z], [x0 + box["wall"], y + port["width"], z + port["height"]]])
    require(features["port_boxes"] == port_boxes and features["port_corner_counts"] == [8] * len(port_boxes),
            "Side ports differ.")
    studs = {**box["studs"], "centers": sorted(box["studs"]["centers"])}
    require(features["studs"] == studs and
            len(features["hole_plane_hits"]) == len(studs["centers"]) and
            all(len(hits) == 4 and min(hits) > 0 for hits in features["hole_plane_hits"]), "Mounting holes differ.")
    supports = box["supports"]
    support_tops = [[part["min"][:2], part["max"][:2], part["max"][2]] for part in supports if part["ref"] != "Перегородка"]
    require(features["support_top_boxes"] == support_tops, "Module supports differ.")
    partition = [part for part in supports if part["ref"] == "Перегородка"]
    corners = features["partition_top_boundary"]
    for axis in (0, 1):
        require(min(point[axis] for point in corners) == min(part["min"][axis] for part in partition) and
                max(point[axis] for point in corners) == max(part["max"][axis] for part in partition), "Partition bounds differ.")
    require({point[2] for point in corners} == {part["max"][2] for part in partition}, "Partition height differs.")
    dwg_hash = hashlib.sha256((ROOT / "outputs/SAPR-001-assembly.dwg").read_bytes()).hexdigest()
    require(dwg_hash == audit["sha256"], "CAD file differs from the verified release.")
    print("PASS KiCad nets, BOM and wiring, firmware profile, DWG features and digest")


if __name__ == "__main__":
    main()
