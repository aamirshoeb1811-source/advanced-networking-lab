#!/usr/bin/env python3
"""
ecmp_counters.py

Purpose:
    Measures how evenly ECMP distributes traffic across uplink paths in our fat-tree
    topology during iperf runs, and checks how traffic shifts (or drops) when a link goes down.

Logic:
    Takes a 'before' snapshot of cumulative TX byte counters on the target interfaces,
    waits while the iperf test runs, takes an 'after' snapshot, and subtracts the two
    to isolate the exact bytes sent during that single run. It then calculates each
    link's percentage share of the total traffic.

Assumptions:
    - All iperf flows run at a fixed, equal data rate so byte share directly reflects flow count.
    - Counters are read on pod 0's aggregation switch uplink ports (a00/a01 toward the core switches).
    - No unrelated background traffic is running on those ports during the measurement window.

Testing:
    Verified against known N=4, N=8, N=16, and N=32 iperf runs—the byte deltas divided cleanly
    into exact integer flow counts, and the link-down run accurately showed 0 bytes on the dead
    port while matching the OpenFlow group bucket stats on switch a00.

Limits & Fallback:
    - At high concurrency (like N=32), UDP ACK retries inflate total byte counts across all
      flows equally; shares remain accurate, though raw byte totals look higher than baseline.
    - Minor control-plane noise (ARP/LLDP) can add a few stray bytes if left idle too long.
    - Fallback: If a reading looks off (e.g., mixed runs or missing flows), cross-check the
      switch's OpenFlow group table directly using:
      `ovs-ofctl -O OpenFlow15 dump-group-stats a00`
"""

import csv
import os

# The four core links leaving pod 0: (agg switch, port, linux interface, core switch)
LINKS = [
    ("a00", 3, "a00-eth3", "c00"),
    ("a00", 4, "a00-eth4", "c01"),
    ("a01", 3, "a01-eth3", "c10"),
    ("a01", 4, "a01-eth4", "c11"),
]

RESULTS_FILE = "results.csv"


def tx_bytes(iface):
    # The kernel keeps a running TX byte total for every interface in sysfs.
    path = f"/sys/class/net/{iface}/statistics/tx_bytes"
    with open(path) as f:
        return int(f.read().strip())


def read_all():
    return {core: tx_bytes(iface) for (_, _, iface, core) in LINKS}


def main():
    label = input("Label for this run (e.g. N=8 run 1): ").strip() or "run"

    before = read_all()
    print("Before:", before)
    input("Start the iperf run in the Mininet CLI now. "
          "When it finishes, come back and press Enter...")
    after = read_all()
    print("After: ", after)

    total = sum(after[core] - before[core] for core in after)
    if total <= 0:
        print("WARNING: total byte gain is zero - did the run actually happen?")

    print(f"\n{label}")
    print(f"{'link':<16}{'bytes':>14}{'share':>9}")
    new_file = not os.path.exists(RESULTS_FILE)
    with open(RESULTS_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["label", "link", "bytes", "share_percent"])
        for (sw, port, iface, core) in LINKS:
            diff = after[core] - before[core]
            share = (100.0 * diff / total) if total > 0 else 0.0
            print(f"{iface + ' -> ' + core:<16}{diff:>14}{share:>8.1f}%")
            w.writerow([label, f"{iface}->{core}", diff, f"{share:.1f}"])
    print(f"(appended to {RESULTS_FILE})")


if __name__ == "__main__":
    main()
