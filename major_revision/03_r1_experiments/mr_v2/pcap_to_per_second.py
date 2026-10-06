"""STEP 1-C (PRIMARY real-data evidence): official CIC-IDS2017 Friday-WorkingHours.pcap
-> complete per-second time series of the whole Friday capture.

Deterministic, streaming transformation (one pass, no derived PCAP):
  1. Read every block of the pcapng with dpkt (pcap fallback); timestamp ts =
     capture time (epoch, 1 us resolution); second = floor(ts).
  2. Series spans [floor(first_ts), floor(last_ts)] of the WHOLE capture
     (no restriction to the attack window); seconds without packets -> zeros.
  3. Per second: n_packets, n_bytes (captured length), n_wire_bytes (EPB original
     length is not exposed by dpkt; captured length used, snaplen recorded),
     n_flows_started (first appearance of a TCP/UDP 5-tuple in the capture),
     dport_entropy (Shannon, bits, over TCP/UDP destination ports),
     pkt_rate = n_packets (per-second analogue of the paper's packet-rate feature).
  4. Labels from the official CIC schedule (ADT = UTC-3; minute ends inclusive,
     i.e. hh:mm:00 .. hh:mm:59):
       label_botnet   10:02-11:02
       label_portscan 13:55-13:57, 13:58-14:00, 14:01-14:04, 14:05-14:07, 14:08-14:10,
                      14:11-14:13, 14:14-14:16, 14:17-14:19, 14:20-14:21, 14:22-14:24,
                      14:33-14:33, 14:35-14:35, 14:51-14:53, 14:54-14:56, 14:57-14:59,
                      15:00-15:02, 15:03-15:05, 15:06-15:07, 15:08-15:10, 15:11-15:12,
                      15:13-15:15, 15:16-15:18, 15:19-15:21, 15:22-15:24, 15:25-15:25,
                      15:26-15:27, 15:28-15:29
       label_ddos     15:56-16:16   (= label_schedule, primary event)
     Packet evidence (audit only): pk_nat_to_victim = packets 172.16.0.1 -> 192.168.10.50
     (firewall NAT of all external attackers -> web server), pk_botnet = packets between
     205.174.165.73 and the five Botnet victims.
  5. Outputs: CSV + manifest JSON (source SHA-256 recomputed, packet counts,
     malformed packets, time span, schedule, script SHA-256).
"""
import argparse, hashlib, json, math, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ADT = timezone(timedelta(hours=-3))
DAY = "2017-07-07"
NAT, VICTIM = "172.16.0.1", "192.168.10.50"
BOT_C2 = "205.174.165.73"; BOT_VICTIMS = {"192.168.10.15", "192.168.10.9", "192.168.10.14", "192.168.10.5", "192.168.10.8"}
SCHED = {
    "botnet": [("10:02", "11:02")],
    "portscan": [("13:55", "13:57"), ("13:58", "14:00"), ("14:01", "14:04"), ("14:05", "14:07"), ("14:08", "14:10"),
                 ("14:11", "14:13"), ("14:14", "14:16"), ("14:17", "14:19"), ("14:20", "14:21"), ("14:22", "14:24"),
                 ("14:33", "14:33"), ("14:35", "14:35"), ("14:51", "14:53"), ("14:54", "14:56"), ("14:57", "14:59"),
                 ("15:00", "15:02"), ("15:03", "15:05"), ("15:06", "15:07"), ("15:08", "15:10"), ("15:11", "15:12"),
                 ("15:13", "15:15"), ("15:16", "15:18"), ("15:19", "15:21"), ("15:22", "15:24"), ("15:25", "15:25"),
                 ("15:26", "15:27"), ("15:28", "15:29")],
    "ddos": [("15:56", "16:16")],
}
SCHED_SOURCE = "UNB CIC CIC-IDS2017 attack schedule (Friday July 7, 2017), as published with the dataset; Sharafaldin et al., ICISSP 2018"


def ep(hm, end=False):
    e = int(datetime.strptime(f"{DAY} {hm}", "%Y-%m-%d %H:%M").replace(tzinfo=ADT).timestamp())
    return e + 59 if end else e


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main():
    import dpkt, socket
    ap = argparse.ArgumentParser(); ap.add_argument("--pcap", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--skip-sha", action="store_true", help="do not recompute source SHA-256 (already recorded)")
    a = ap.parse_args(); t0 = time.time()
    pk = Counter(); by = Counter(); nf = Counter(); nat = Counter(); bot = Counter(); ports = defaultdict(Counter)
    seen = set(); st = Counter(); first = last = None; snaplens = set()
    with open(a.pcap, "rb") as f:
        try:
            rd = dpkt.pcapng.Reader(f); fmt = "pcapng"
        except ValueError:
            f.seek(0); rd = dpkt.pcap.Reader(f); fmt = "pcap"
        try:
            snaplens.add(int(rd.snaplen))
        except Exception:
            pass
        for ts, buf in rd:
            st["packets_total"] += 1
            sec = int(math.floor(ts))
            first = sec if first is None else first; last = sec
            pk[sec] += 1; by[sec] += len(buf)
            try:
                eth = dpkt.ethernet.Ethernet(buf); ip = eth.data
                if not isinstance(ip, dpkt.ip.IP):
                    st["non_ipv4"] += 1; continue
                src, dst = socket.inet_ntoa(ip.src), socket.inet_ntoa(ip.dst)
                l4 = ip.data
                if isinstance(l4, (dpkt.tcp.TCP, dpkt.udp.UDP)):
                    ports[sec][l4.dport] += 1
                    key = (ip.src, ip.dst, l4.sport, l4.dport, ip.p)
                    if key not in seen:
                        seen.add(key); nf[sec] += 1
                if src == NAT and dst == VICTIM:
                    nat[sec] += 1
                if (src == BOT_C2 and dst in BOT_VICTIMS) or (dst == BOT_C2 and src in BOT_VICTIMS):
                    bot[sec] += 1
            except Exception:
                st["malformed"] += 1
            if st["packets_total"] % 1_000_000 == 0:
                print(f"[pcap] {st['packets_total']:,} packets ({time.time()-t0:.0f}s)", flush=True)
    iv = {k: [(ep(s), ep(e, True)) for s, e in v] for k, v in SCHED.items()}
    inn = lambda e, k: int(any(s <= e <= t for s, t in iv[k]))
    rows = ["t,epoch_s,n_packets,n_bytes,n_flows_started,dport_entropy,pkt_rate,label_botnet,label_portscan,label_ddos,label_schedule,label_any_attack,pk_nat_to_victim,pk_botnet"]
    for e in range(first, last + 1):
        c = ports.get(e, {}); tot = sum(c.values())
        H = abs(-sum((v / tot) * math.log2(v / tot) for v in c.values())) if tot else 0.0
        lb, lp, ld = inn(e, "botnet"), inn(e, "portscan"), inn(e, "ddos")
        rows.append(f"{e-first},{e},{pk[e]},{by[e]},{nf[e]},{H:.6f},{pk[e]},{lb},{lp},{ld},{ld},{int(lb or lp or ld)},{nat[e]},{bot[e]}")
    Path(a.out).write_text("\n".join(rows) + "\n")
    to_adt = lambda e: datetime.fromtimestamp(e, ADT).strftime("%H:%M:%S")
    man = {"command": " ".join(sys.argv), "script_sha256": sha256(__file__), "format": fmt, "snaplen": sorted(snaplens),
           "source": a.pcap, "source_sha256": None if a.skip_sha else sha256(a.pcap),
           "first_second_epoch": first, "last_second_epoch": last, "first_second_ADT": to_adt(first), "last_second_ADT": to_adt(last),
           "n_seconds": last - first + 1, "seconds_with_zero_packets": sum(1 for e in range(first, last + 1) if pk[e] == 0),
           "unique_5tuples": len(seen), "schedule_ADT": SCHED, "schedule_epoch": iv, "schedule_source": SCHED_SOURCE,
           "timezone": "ADT (UTC-3)", "output": a.out, "output_sha256": sha256(a.out), "runtime_s": round(time.time() - t0, 1), "malformed": 0, "non_ipv4": 0, **st}
    Path(a.out).with_suffix(".manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: man.get(k, 0) for k in ("n_seconds", "first_second_ADT", "last_second_ADT", "packets_total", "malformed", "output_sha256")}))


if __name__ == "__main__":
    main()
