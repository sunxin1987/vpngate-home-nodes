#!/usr/bin/env python3
"""Fetch VPNGate relays, keep JP/KR residential ones, write .ovpn files + index."""
import base64, csv, glob, io, json, os, urllib.request
from datetime import datetime, timezone

API_URLS = ["https://www.vpngate.net/api/iphone/", "http://www.vpngate.net/api/iphone/"]
COUNTRIES = {"JP": 6, "KR": 6}
EXCLUDE_PREFIX = "219.100.37."  # Univ. of Tsukuba official cluster (datacenter, not residential)
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"}

def fetch_csv():
    last = None
    for u in API_URLS:
        try:
            req = urllib.request.Request(u, headers=UA)
            data = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
            if "OpenVPN_ConfigData_Base64" in data:
                return data
        except Exception as e:
            last = e
    raise SystemExit(f"fetch failed: {last}")

def ip_quality(ips):
    try:
        req = urllib.request.Request(
            "http://ip-api.com/batch?fields=query,isp,proxy,hosting",
            data=json.dumps(ips).encode(),
            headers={"Content-Type": "application/json"})
        out = {}
        for r in json.load(urllib.request.urlopen(req, timeout=30)):
            out[r["query"]] = r
        return out
    except Exception:
        return {}

def main():
    text = fetch_csv()
    lines = [l for l in text.splitlines() if not l.startswith("*")]
    rdr = csv.DictReader(io.StringIO("\n".join(lines).replace("#HostName", "HostName", 1)))
    rows = []
    for r in rdr:
        if r["CountryShort"] not in COUNTRIES:
            continue
        if r["IP"].startswith(EXCLUDE_PREFIX):
            continue
        if int(r["NumVpnSessions"]) <= 0:
            continue
        try:
            cfg = base64.b64decode(r["OpenVPN_ConfigData_Base64"]).decode("utf-8", "replace")
        except Exception:
            continue
        if "proto tcp" not in cfg:
            continue
        r["_cfg"] = cfg
        rows.append(r)
    quality = ip_quality([r["IP"] for r in rows])
    rows = [r for r in rows if not quality.get(r["IP"], {}).get("hosting", False)]
    def rank(r):
        q = quality.get(r["IP"], {})
        return (q.get("proxy", True), -int(r["Score"]))
    rows.sort(key=rank)
    for old in glob.glob("??-??.ovpn"):
        os.remove(old)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    picked = []
    for cc, limit in COUNTRIES.items():
        n = 0
        for r in rows:
            if r["CountryShort"] != cc or n >= limit:
                continue
            n += 1
            fname = f"{cc}-{n:02d}.ovpn"
            with open(fname, "w") as f:
                f.write(r["_cfg"])
            q = quality.get(r["IP"], {})
            picked.append({"file": fname, "country": cc, "ip": r["IP"],
                           "isp": q.get("isp", ""), "proxy_flag": q.get("proxy", None),
                           "speed_mbps": int(r["Speed"]) // 10**6,
                           "sessions": int(r["NumVpnSessions"]), "score": int(r["Score"])})
    with open("nodes.json", "w") as f:
        json.dump({"updated": now, "nodes": picked}, f, ensure_ascii=False, indent=1)
    rows_html = "\n".join(
        f'<tr><td><a href="{p["file"]}">{p["file"]}</a></td><td>{p["country"]}</td><td>{p["isp"]}</td>'
        f'<td>{p["ip"]}</td><td>{p["speed_mbps"]} Mbps</td><td>{p["sessions"]}</td></tr>' for p in picked)
    with open("index.html", "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>VPNGate residential nodes</title>
<h1>VPNGate JP/KR residential OpenVPN nodes</h1>
<p>Updated: {now}. Auto-refreshed every 3 hours. Import a .ovpn link into OpenVPN Connect via URL.</p>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>File</th><th>Country</th><th>ISP</th><th>IP</th><th>Speed</th><th>Sessions</th></tr>
{rows_html}
</table>
""")
    print(f"picked {len(picked)} nodes")

if __name__ == "__main__":
    main()
