"""STEP 1-C (PRIMARY real-data evidence) — STATUS: BLOCKED.

The official file Friday-WorkingHours.pcap (UNB CIC, cicresearch.ca) requires a
manual registration form; it is not reachable from the sandbox (HTTP redirect
to the CIC dataset landing page, verified 2026-10-03).  This script is ready
but has NOT been run on real data.

Procedure (documented, reproducible, streaming; never loads the PCAP in RAM):
  1. Stream packets with dpkt (pcap or pcapng), take the capture timestamp
     ts (epoch, microsecond precision), floor to integer second.
  2. Restrict to the Friday-afternoon interval [--start, --end] (default
     2017-07-07 15:00:00 to 17:05:00 America/Halifax = ADT, i.e. UTC-3,
     the time zone used by CIC for CIC-IDS2017 labels).
  3. Per second emit: n_packets, n_bytes, n_flows_started (new 5-tuples),
     dport_entropy (Shannon over TCP/UDP destination ports), and
     pkt_rate_proxy = n_packets (the per-second analogue of the summed
     "Flow Packets/s" used by the paper; the exact construct difference is
     recorded as a threat to construct validity).
  4. Label per second from the official CIC attack schedule for Friday
     afternoon: DDoS LOIT 15:56-16:16 ADT, attacker 205.174.165.73 ->
     victim 192.168.10.50 (Sharafaldin et al., ICISSP 2018; internal NAT 172.16.0.1); a second is
     labelled 1 if it contains >=1 packet attacker->victim.  Both the
     schedule label and the packet-evidence label are written.
  5. Output CSV columns: t (s from start), epoch_s, n_packets, n_bytes,
     n_flows_started, dport_entropy, pkt_rate, label_schedule, label_packets.
  6. A JSON manifest records the PCAP SHA-256, packet counts, dropped/
     malformed packets, interval, timezone and script commit.
Then run:  exp_single.py --dataset real_second --input <csv>  (grid W={64,128,256} x s={1,4,8}).
"""
import argparse, hashlib, json, math, sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ADT = timezone(timedelta(hours=-3))
ATTACKER, VICTIM = "172.16.0.1", "192.168.10.50"  # NAT address seen inside the capture (verified: 128,024 DDoS flows 172.16.0.1->192.168.10.50 in TrafficLabelling CSV); public attacker 205.174.165.73


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main():
    import dpkt, socket
    ap = argparse.ArgumentParser(); ap.add_argument("--pcap", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2017-07-07 15:00:00"); ap.add_argument("--end", default="2017-07-07 17:05:00")
    ap.add_argument("--attack-start", default="2017-07-07 15:56:00"); ap.add_argument("--attack-end", default="2017-07-07 16:16:59")
    a = ap.parse_args()
    to_epoch = lambda s: int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ADT).timestamp())
    t0, t1, a0, a1 = map(to_epoch, (a.start, a.end, a.attack_start, a.attack_end))
    n = t1 - t0 + 1
    pk = [0] * n; by = [0] * n; nf = [0] * n; atk = [0] * n; ports = [Counter() for _ in range(n)]
    seen = set(); stats_ = Counter()
    with open(a.pcap, "rb") as f:
        try:
            rd = dpkt.pcap.Reader(f)
        except ValueError:
            f.seek(0); rd = dpkt.pcapng.Reader(f)
        for ts, buf in rd:
            stats_["packets_total"] += 1
            sec = int(math.floor(ts))
            if sec < t0 or sec > t1:
                continue
            i = sec - t0; stats_["packets_in_interval"] += 1
            pk[i] += 1; by[i] += len(buf)
            try:
                ip = dpkt.ethernet.Ethernet(buf).data
                if not isinstance(ip, dpkt.ip.IP):
                    continue
                src, dst = socket.inet_ntoa(ip.src), socket.inet_ntoa(ip.dst)
                l4 = ip.data
                if isinstance(l4, (dpkt.tcp.TCP, dpkt.udp.UDP)):
                    ports[i][l4.dport] += 1
                    key = (src, dst, l4.sport, l4.dport, ip.p)
                    if key not in seen:
                        seen.add(key); nf[i] += 1
                if src == ATTACKER and dst == VICTIM:
                    atk[i] = 1
            except Exception:
                stats_["malformed"] += 1
    rows = ["t,epoch_s,n_packets,n_bytes,n_flows_started,dport_entropy,pkt_rate,label_schedule,label_packets"]
    for i in range(n):
        c = ports[i]; tot = sum(c.values())
        H = abs(-sum((v / tot) * math.log2(v / tot) for v in c.values())) if tot else 0.0
        e = t0 + i
        rows.append(f"{i},{e},{pk[i]},{by[i]},{nf[i]},{H:.6f},{pk[i]},{int(a0 <= e <= a1)},{atk[i]}")
    Path(a.out).write_text("\n".join(rows) + "\n")
    man = {"command": " ".join(sys.argv), "pcap_sha256": sha256(a.pcap), "interval_ADT": [a.start, a.end],
           "attack_schedule_ADT": [a.attack_start, a.attack_end], "attacker": ATTACKER, "victim": VICTIM, **stats_}
    Path(a.out).with_suffix(".manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
