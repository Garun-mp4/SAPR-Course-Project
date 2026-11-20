"""Generate a private SAPR NVS image without programming a board."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

NVS_SIZE = 0x6000


def validate(raw, directory):
    if not isinstance(raw, dict) or type(raw.get("commissioned")) is not bool:
        raise ValueError("commissioned must be explicitly true or false")
    result = {"version": 1, "commissioned": int(raw["commissioned"])}
    if "connection" not in raw:
        return result

    connection = raw["connection"]
    if not isinstance(connection, dict):
        raise ValueError("connection must be an object")
    for key, limit in {"ssid": 32, "password": 64, "server": 235, "token": 256, "ca_file": 4096}.items():
        value = connection.get(key)
        if not isinstance(value, str) or not value or "\0" in value or len(value.encode("utf-8")) > limit:
            raise ValueError(f"Invalid {key}")
    password = connection["password"]
    if not (8 <= len(password.encode("utf-8")) <= 63 or re.fullmatch(r"[A-Fa-f0-9]{64}", password)):
        raise ValueError("Expected a WPA2 passphrase or a 64-digit PSK")
    if not re.fullmatch(r"[!-~]{32,256}", connection["token"]):
        raise ValueError("Expected a 32–256-character ASCII bearer token")

    server = connection["server"]
    parsed = urlsplit(server)
    port = parsed.port
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path not in ("", "/") or
            port == 0 or not re.fullmatch(r"[A-Za-z0-9.:\[\]-]+", parsed.netloc) or
            any(ord(c) < 33 or ord(c) > 126 for c in server)):
        raise ValueError("Expected an HTTPS origin without credentials or path")
    ntp = connection.get("ntp_server", "pool.ntp.org")
    if not isinstance(ntp, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,253}", ntp):
        raise ValueError("Expected a valid SNTP host name or address")
    certificate = (directory / connection["ca_file"]).read_text(encoding="ascii")
    if len(certificate) > 3900:
        raise ValueError("Maximum root CA length is 3900 bytes")
    ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=certificate)
    result.update(ssid=connection["ssid"], password=password, token=connection["token"],
                  url=server.rstrip("/") + "/api/v1/telemetry", root_ca=certificate, ntp_server=ntp)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Private JSON outside the repository")
    parser.add_argument("--out", type=Path, required=True, help="A new image outside the repository")
    parser.add_argument("--idf", type=Path, default=Path.home() / ".platformio/packages/framework-espidf")
    args = parser.parse_args()

    try:
        repo = Path(__file__).resolve().parents[1]
        if any(path.resolve().is_relative_to(repo) for path in (args.config, args.out)):
            raise ValueError("Store the configuration and image outside this repository")
        if args.out.exists():
            raise ValueError("Choose a new output path")
        payload = validate(json.loads(args.config.read_text(encoding="utf-8-sig")), args.config.parent)
        generator = args.idf / "components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py"
        with tempfile.TemporaryDirectory(prefix="sapr-provision-") as directory:
            work = Path(directory)
            source, image = work / "nvs.csv", work / "nvs.bin"
            with source.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("key", "type", "encoding", "value"))
                writer.writerow(("sapr", "namespace", "", ""))
                for key, value in payload.items():
                    writer.writerow((key, "data", "u8" if isinstance(value, int) else "string", value))
            subprocess.run(
                [sys.executable, str(generator), "generate", str(source), str(image), hex(NVS_SIZE)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=30)
            result = image.read_bytes()
        if len(result) != NVS_SIZE:
            raise ValueError("Unexpected NVS size")
        with open(args.out, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
            output.write(result)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        print("NVS generation failed. Check the local JSON, certificate, IDF tools, and new output path.", file=sys.stderr)
        return 1
    print("NVS image created. It contains private configuration. No board was programmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
