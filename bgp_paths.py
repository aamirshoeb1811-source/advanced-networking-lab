import sys
import requests

prefix = sys.argv[1]
r = requests.get("https://stat.ripe.net/data/bgp-state/data.json",
                 params={"resource": prefix}, timeout=60)
entries = r.json()["data"]["bgp_state"]
print(prefix, ":", len(entries), "collector entries")

seen = []
for e in entries:
    p = tuple(e["path"])
    if p not in seen:
        seen.append(p)

print("Three AS paths seen by route collectors:")
for p in seen[:3]:
    print("  " + " ".join(str(a) for a in p))
print("Origin AS (last AS in the paths):", seen[0][-1])
