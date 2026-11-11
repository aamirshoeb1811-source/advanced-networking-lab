"""collect_config.py - CSC 6410 Experiment 3 (Aamir Shoeb)

Purpose (my words): Collect the local machine's network interface configuration,
structure the data into a JSON format matching the defined schema, and validate
it against both the schema rules and an intended reference configuration.
Logic (my words): Read the host's network interfaces and adapter properties,
serialize the extracted parameters into structured JSON data, use the jsonschema
library to validate it against the project schema, and compare the validated
output with intended.json to highlight discrepancies.
Assumptions (my words): The operating system is Windows with standard network
adapter naming, and the local network configuration stays stable while the
script executes.
Testing (my words): Verify accuracy by cross-referencing the extracted values
and validation logs against the manual network properties and hand-recorded
notes collected during Step 1.
Limits (my words): The script cannot verify physical link status or dynamic
configuration changes happening outside it.
Fallback (my words): If automatic collection fails or misses an adapter, log
the failure and skip that adapter; virtual interfaces are skipped by my
counting rule (Step 2 decision).
"""
import json, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
SCHEMA_FILE = HERE.parent / "course_files" / "host_schema.json"
INTENDED_FILE = HERE.parent / "intended.json"
OBSERVED_FILE = HERE / "observed.json"
TOP = "student-host:host"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def value_after(line):
    return line.split(":", 1)[1].strip() if ":" in line else ""


def clean_ip(v):
    # "192.168.1.26(Preferred)" -> "192.168.1.26"
    return re.sub(r"\(.*?\)\s*$", "", v.strip()).strip()


def mac_ok(mac):
    # A real MAC line looks like 6C-94-66-48-82-8F; the DHCPv6 DUID line
    # contains longer hex groups and must NOT be mistaken for a MAC.
    return re.fullmatch(r"[0-9A-Fa-f]{2}(-[0-9A-Fa-f]{2}){5}", mac) is not None


def mask_to_prefix(mask):
    # 255.255.255.0 -> count the 1-bits -> 24
    bits = "".join(f"{int(p):08b}" for p in mask.split("."))
    return bits.count("1")


def parse_ipconfig(text):
    hostname, adapters, cur, host_done = None, [], None, False
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = re.match(r"^(.*?) adapter (.+):\s*$", raw.strip())
        if m and not raw.startswith(" "):
            cur = {"name": m.group(2).strip(), "kind": m.group(1).strip()}
            adapters.append(cur)
            host_done = True
            continue
        if ":" not in raw:
            continue
        label = raw.split(":", 1)[0].replace(".", " ").strip()
        val = raw.split(":", 1)[1].strip()
        if not host_done:
            if label == "Host Name":
                hostname = val
            continue
        if cur is None:
            continue
        if label == "Description":
            cur["description"] = val
        elif label == "Physical Address" and mac_ok(val):
            cur["mac"] = val
        elif label == "Media State":
            cur["media"] = val
        elif label == "IPv4 Address":
            cur["ipv4"] = clean_ip(val)
        elif label == "Subnet Mask":
            cur["mask"] = val
        elif label == "Default Gateway":
            cur["gateway"] = val
        elif label == "DNS Servers":
            cur.setdefault("dns", []).append(val)
        elif "IPv6 Address" in label and val:
            cur.setdefault("ipv6", []).append(clean_ip(val))
    return hostname, adapters


def parse_netsh_mtu(text):
    mtu = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+(\d+)\s+\d+\s+\d+\s+(.+?)\s*$", line)
        if m:
            mtu[m.group(3)] = int(m.group(1))
    return mtu


def build_host(hostname, adapters, mtu_map):
    # My counting rule (Step 2): keep only adapters that are UP and real -
    # no virtual, no loopback - matching what Settings displays.
    host = {"hostname": hostname, "os": "windows",
            "collected-at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "interface": []}
    for a in adapters:
        name = a["name"]
        desc = a.get("description", "")
        if "Virtual" in desc or "Loopback" in name or "Loopback" in desc:
            print(f"skip (virtual/loopback, my counting rule): {name}")
            continue
        if "media" in a:   # a Media State line appears only when disconnected
            print(f"skip (down): {name}")
            continue
        iface = {"name": name}
        iface["type"] = "wifi" if ("Wireless" in a["kind"] or "Wi-Fi" in desc) else "ethernet"
        if "mac" in a:
            iface["mac"] = a["mac"].replace("-", ":").lower()
        iface["oper-status"] = "up"
        if name in mtu_map:
            iface["mtu"] = mtu_map[name]
        if "ipv4" in a and "mask" in a:
            iface["ipv4"] = [f"{a['ipv4']}/{mask_to_prefix(a['mask'])}"]
        if "ipv6" in a:
            iface["ipv6"] = a["ipv6"]
        host["interface"].append(iface)
        if "gateway" in a and "default-gateway" not in host:
            host["default-gateway"] = a["gateway"]
        if "dns" in a and "dns-server" not in host:
            host["dns-server"] = a["dns"]
    return {TOP: host}


def drift(intended, observed):
    lines = []
    ih = intended.get(TOP, {})
    oh = observed.get(TOP, {})
    for key in ("hostname", "os", "default-gateway"):
        if key in ih and ih[key] != oh.get(key):
            lines.append(f"host / {key}: intended {ih[key]}, observed {oh.get(key)}")
    if "dns-server" in ih and ih["dns-server"] != oh.get("dns-server"):
        lines.append(f"host / dns-server: intended {ih['dns-server']}, observed {oh.get('dns-server')}")
    obs_by_name = {i["name"]: i for i in oh.get("interface", [])}
    for ii in ih.get("interface", []):
        name = ii["name"]
        if name not in obs_by_name:
            lines.append(f"interface {name}: intended present, observed MISSING")
            continue
        oi = obs_by_name[name]
        for key in ("type", "oper-status", "mtu", "mac"):
            if key in ii and ii[key] != oi.get(key):
                lines.append(f"interface {name} / {key}: intended {ii[key]}, observed {oi.get(key)}")
    return lines


def main():
    t0 = time.time()
    hostname, adapters = parse_ipconfig(run(["ipconfig", "/all"]))
    mtu_map = parse_netsh_mtu(run(["netsh", "interface", "ipv4", "show", "subinterfaces"]))
    observed = build_host(hostname, adapters, mtu_map)
    OBSERVED_FILE.write_text(json.dumps(observed, indent=2))
    print(f"collected {len(observed[TOP]['interface'])} interface(s) in {time.time() - t0:.2f} seconds")
    print(f"wrote {OBSERVED_FILE.name}")

    schema = json.loads(SCHEMA_FILE.read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(observed),
                    key=lambda e: list(e.absolute_path))
    if errors:
        print("SCHEMA: INVALID")
        for e in errors:
            print("  " + "/".join(str(p) for p in e.absolute_path) + ": " + e.message)
    else:
        print("SCHEMA: VALID")

    intended = json.loads(INTENDED_FILE.read_text())
    lines = drift(intended, observed)
    if lines:
        print("DRIFT:")
        for ln in lines:
            print("  " + ln)
    else:
        print("DRIFT: none - observed matches intended")


if __name__ == "__main__":
    main()
