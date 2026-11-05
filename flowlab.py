#!/usr/bin/env python3
"""Class 2 demo and Experiment 2 starting point (CSC 6410, Week 2).

One Open vSwitch switch s1, three hosts h1-h3 (10.0.0.1-3), and NO controller: this script is the controller.
Run in the course lab container:   python3 flowlab.py        (WSL: sudo -E python3 flowlab.py, so MN_SWITCH reaches it)
It prints the flow table and a ping test (1) with an empty table, (2) after installing rules, (3) after a priority-200 drop rule.
Students: copy it, change it, and comment it in your own words (purpose, logic, assumptions, testing, limits).
"""

# My comments (Aamir Shoeb)
# Purpose: We create three hosts, h1, h2, h3. All three hosts are connected to one switch, s1.
# There is no controller, so the script installs the rules.
# Logic: Initially the switch has an empty flow table. When one host tries to ping another, the
# switch does not know where to send the packet, therefore the packets are dropped. After adding
# rules to the switch, we install two types of rules: ARP rules allow ARP packets to flood to all
# ports; IP rules tell the switch where to send packets based on the destination IP. All three
# hosts can communicate successfully because forwarding rules are installed.
# Priority: In simple words, the new drop rule has priority 200 while the normal forwarding rules
# have priority 100. The drop rule blocks any packets going from h3 to h1. It does not block all
# communication, only the packets from h3 to h1.
# Assumptions: The script runs on my local laptop environment, specifically in the setup where
# Mininet is installed, since the Docker container itself did not contain Mininet. I must set the
# switch environment variable MN_SWITCH=ovsk and execute the Python script using sudo -E to
# preserve the environment variables.
# Testing: Before using the script, these same steps were run by hand in the Mininet CLI. The
# script's output successfully matched those manual results, confirming that the packet and flow
# metrics such as successful ping rates and packet counts aligned.
# Limits: The script is hardcoded for a specific number of switches and hosts — one switch and
# three hosts, as defined in flowlab.py — with fixed IP addresses. It cannot handle a large
# network as is, without modifying the topology setup code inside the script. This is a simulated
# network running locally inside the laptop using Mininet, rather than a physical network. It
# measures reachability but does not measure real-world network metrics like latency, jitter, or
# actual link speed or bandwidth.

from mininet.net import Mininet
from mininet.topo import SingleSwitchTopo
from mininet.node import OVSSwitch
from functools import partial
import os
from mininet.log import setLogLevel

# Open vSwitch datapath: the lab container sets MN_SWITCH from its lab check ("ovsk" = kernel, "ovs,datapath=user" = userspace).
# In WSL: export MN_SWITCH=ovsk (or ovs,datapath=user if the lab check says userspace) before running this script.
MN_SWITCH = os.environ.get("MN_SWITCH", "ovsk")
SWITCH = partial(OVSSwitch, datapath="user") if "datapath=user" in MN_SWITCH else OVSSwitch


def flows(s1, title):
    print(f"\n=== {title}: ovs-ofctl dump-flows s1 ===")
    print(s1.cmd("ovs-ofctl dump-flows s1"))


def ping(net, title):
    print(f"=== {title}: pingall ===")
    loss = net.pingAll(timeout="1")          # returns the percentage of pings that were lost
    print(f"lost: {loss:.0f}%")


def main():
    # controller=None and failMode='secure': the switch forwards ONLY what its flow table says
    net = Mininet(topo=SingleSwitchTopo(k=3), switch=SWITCH, controller=None, autoSetMacs=True)
    net.start()
    print("switch:", MN_SWITCH)
    s1 = net.get("s1")
    print("fail mode:", s1.cmd("ovs-vsctl get-fail-mode s1").strip())

    flows(s1, "1 empty table")
    ping(net, "1 empty table")

    # 2 - be the controller: ARP may flood; IP goes to the port of its destination host (h1 is on port 1, etc.)
    s1.cmd("ovs-ofctl add-flow s1 priority=100,arp,actions=flood")
    for i in (1, 2, 3):
        s1.cmd(f"ovs-ofctl add-flow s1 priority=100,ip,nw_dst=10.0.0.{i},actions=output:{i}")
    ping(net, "2 after rules")
    flows(s1, "2 after rules")

    # 3 - a higher-priority drop rule wins over the forwarding rule for h3 -> h1 only
    s1.cmd("ovs-ofctl add-flow s1 priority=200,ip,nw_src=10.0.0.3,nw_dst=10.0.0.1,actions=drop")
    h2, h3 = net.get("h2", "h3")
    for name, h in (("h3 -> h1", h3), ("h2 -> h1", h2)):
        out = h.cmd("ping -c 2 -W 1 10.0.0.1")
        print(name, [ln for ln in out.splitlines() if "packet loss" in ln])
    print(s1.cmd("ovs-appctl ofproto/trace s1 in_port=3,ip,nw_src=10.0.0.3,nw_dst=10.0.0.1"))
    flows(s1, "3 after the drop rule")

    # 4 - the same drop rule at priority 50: the forwarding rule (100) now wins
    s1.cmd("ovs-ofctl --strict del-flows s1 priority=200,ip,nw_src=10.0.0.3,nw_dst=10.0.0.1")
    s1.cmd("ovs-ofctl add-flow s1 priority=50,ip,nw_src=10.0.0.3,nw_dst=10.0.0.1,actions=drop")
    out = h3.cmd("ping -c 2 -W 1 10.0.0.1")
    print("h3 -> h1 with drop at priority 50", [ln for ln in out.splitlines() if "packet loss" in ln])
    flows(s1, "4 after the priority-50 drop rule")

    net.stop()


if __name__ == "__main__":
    setLogLevel("warning")
    main()
