# It reads a traceroute output file, finds which AS each hop belongs to using RIPEstat, and prints the AS path.

import re
import sys
import json
import time
import requests
from ipaddress import ip_address, ip_network

# These are the private address ranges that are never announced in BGP, so the script skips them.

PRIVATE_NETS = [ip_network(n) for n in
                ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"]]

CACHE_FILE = "as_cache.json"

# Block that opens as_cache.json — this loads the saved answers from the cache file, so RIPEstat is not asked the same question twice; 
# If the file doesn't exist yet, the cache starts empty.

try:
    with open(CACHE_FILE) as f:
        cache = json.load(f)
except FileNotFoundError:
    cache = {}

# This function checks whether an IP address falls inside any of the private ranges.

def is_private(ip):
    addr = ip_address(ip)
    return any(addr in net for net in PRIVATE_NETS)

# This function asks RIPEstat which AS announces the IP (network-info), then asks for that AS's name (as-overview),
# saves the answer in the cache file, and waits a moment so the API is not overloaded.

def lookup_as(ip):
    if ip in cache:
        return cache[ip]
    r = requests.get("https://stat.ripe.net/data/network-info/data.json",
                     params={"resource": ip}, timeout=30)
    data = r.json()["data"]
    asns = data.get("asns") or []
    asn = asns[0] if asns else None
    name = ""
    if asn:
        r2 = requests.get("https://stat.ripe.net/data/as-overview/data.json",
                          params={"resource": "AS" + asn}, timeout=30)
        name = r2.json()["data"].get("holder", "")
    cache[ip] = {"asn": asn, "name": name, "prefix": data.get("prefix")}
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1)
    time.sleep(0.5)
    return cache[ip]

# This is the main part: it reads the traceroute file one line at a time.

def main(path):
    with open(path) as f:
        lines = f.read().splitlines()
    as_path = []
    for line in lines:
        if not re.match(r"\s*\d+\s", line):
            continue
        found = re.findall(r"\d+\.\d+\.\d+\.\d+", line)
        if not found:
            print("(a hop that did not reply)")
            continue
        ip = found[-1]
        if is_private(ip):
            print(f"{ip:16} private address - skipped")
            continue
        info = lookup_as(ip)
        if info["asn"] is None:
            print(f"{ip:16} no AS found in RIPEstat")
            continue
        label = f"AS{info['asn']} ({info['name']})"
        print(f"{ip:16} {label}   announced as {info['prefix']}")
        if not as_path or as_path[-1] != label:
            as_path.append(label)
    print()
    print("AS path: " + "  ->  ".join(as_path))

# This runs the script using the filename typed after the command (for example, python aspath.py trace_cuw.txt).

if __name__ == "__main__":
    main(sys.argv[1])
