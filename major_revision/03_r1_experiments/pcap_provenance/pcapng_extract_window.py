"""Extract a time window from a pcapng file by copying raw blocks (no re-encoding).

Keeps every non-packet block (SHB, IDB, NRB, ISB, ...) so the output is a valid
pcapng; Enhanced Packet Blocks (type 6) and obsolete Packet Blocks (type 2) are
kept only if their timestamp lies in [start, end] (epoch seconds, inclusive start,
exclusive end).  Simple Packet Blocks (type 3, no timestamp) are reported and
dropped.  Timestamp resolution is read from each IDB's if_tsresol option
(default 1e-6).  --dry-run computes size/counts without writing.
Streaming: memory O(block); disk = size of the extracted window only.
"""
import argparse, hashlib, json, struct, sys, time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out")
    ap.add_argument("--start", type=float, required=True); ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    fin = open(a.inp, "rb", buffering=1 << 22)
    fout = None if a.dry_run else open(a.out, "wb", buffering=1 << 22)
    h_in = hashlib.sha256(); h_out = hashlib.sha256()
    st = {"blocks_total": 0, "packets_total": 0, "packets_kept": 0, "spb_dropped": 0, "bytes_out": 0,
          "first_ts_in": None, "last_ts_in": None, "first_ts_kept": None, "last_ts_kept": None, "non_packet_blocks": 0}
    endian = "<"; tsres = []
    while True:
        hdr = fin.read(8)
        if not hdr:
            break
        if len(hdr) < 8:
            raise SystemExit("truncated block header")
        btype = struct.unpack(endian + "I", hdr[:4])[0]
        if btype == 0x0A0D0D0A:  # SHB: determine endianness from BOM
            bom = fin.read(4)
            endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            blen = struct.unpack(endian + "I", hdr[4:8])[0]
            body = bom + fin.read(blen - 12)
            tsres = []
        else:
            blen = struct.unpack(endian + "I", hdr[4:8])[0]
            body = fin.read(blen - 8)
        blk = hdr + body
        if len(blk) != blen:
            raise SystemExit("truncated block")
        st["blocks_total"] += 1
        keep = True
        if btype == 1:  # IDB: parse options for if_tsresol (code 9)
            res = 1e-6
            opt = body[8:-4]; i = 0
            while i + 4 <= len(opt):
                code, ln = struct.unpack(endian + "HH", opt[i:i + 4])
                if code == 0:
                    break
                if code == 9:
                    v = opt[i + 4]
                    res = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                i += 4 + ((ln + 3) & ~3)
            tsres.append(res)
            st["non_packet_blocks"] += 1
        elif btype in (6, 2):
            if btype == 6:
                ifid, hi, lo = struct.unpack(endian + "III", body[:12])
            else:
                ifid, _drops, hi, lo = struct.unpack(endian + "HHII", body[:12])
            ts = ((hi << 32) | lo) * tsres[ifid]
            st["packets_total"] += 1
            if st["first_ts_in"] is None:
                st["first_ts_in"] = ts
            st["last_ts_in"] = ts
            keep = a.start <= ts < a.end
            if keep:
                st["packets_kept"] += 1
                if st["first_ts_kept"] is None:
                    st["first_ts_kept"] = ts
                st["last_ts_kept"] = ts
        elif btype == 3:
            st["spb_dropped"] += 1; keep = False
        else:
            st["non_packet_blocks"] += 1
        h_in.update(blk)
        if keep:
            st["bytes_out"] += len(blk)
            if fout:
                fout.write(blk); h_out.update(blk)
    fin.close()
    if fout:
        fout.close()
    st.update({"input": a.inp, "input_sha256_streamed": h_in.hexdigest(), "output": a.out,
               "output_sha256": h_out.hexdigest() if fout else None, "window_epoch": [a.start, a.end],
               "command": " ".join(sys.argv), "runtime_s": round(time.time() - t0, 1), "dry_run": a.dry_run,
               "tsres": sorted(set(tsres))})
    print(json.dumps(st, indent=1))
    if fout:
        Path(a.out + ".extract.json").write_text(json.dumps(st, indent=1))


if __name__ == "__main__":
    main()
