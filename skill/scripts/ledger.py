#!/usr/bin/env python3
"""The run's spend: check before a paid call, record after it, stop at the ceiling.

    python3 ledger.py <run folder> check <usd>                 exit 0 = it fits, 3 = it would pass the ceiling: stop
    python3 ledger.py <run folder> add --step 1 --what "profile read (data connector)" --calls 1 --unit 0.002 [--note "..."]
    python3 ledger.py <run folder> total

The ceiling is account.json spend_ceiling_usd (niche.json for a niche run; default 3). cost.csv: at, step, what, calls, unit_usd, total_usd, note.
`add` always records (the money is spent) and exits 3 when the total is now over the ceiling, so the run stops there.
Free calls (yt-dlp, plain web reading) need no line; list them in account.json sources with cost_usd 0.
"""
import os
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import iso, now_utc, read_csv, read_json  # noqa: E402

HEADER = ["at", "step", "what", "calls", "unit_usd", "total_usd", "note"]


def ceiling(folder):
    p = os.path.join(folder, "niche.json")
    if not os.path.exists(p):
        p = os.path.join(folder, "account.json")
    if os.path.exists(p):
        c = read_json(p).get("spend_ceiling_usd")
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            return float(c)
    return 3.0


def spent(folder):
    p = os.path.join(folder, "cost.csv")
    if not os.path.exists(p):
        return 0.0
    _, rows = read_csv(p)
    return sum(float(r.get("total_usd") or 0) for r in rows)


def opt(argv, k, d=None):
    return argv[argv.index(k) + 1] if k in argv else d


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 2
    folder, cmd = argv[1], argv[2]
    cap = ceiling(folder)
    s = spent(folder)
    if cmd == "total":
        print("spent $%.4f of $%.2f" % (s, cap))
        return 0
    if cmd == "check":
        usd = float(argv[3])
        if s + usd > cap + 1e-9:
            print("STOP: $%.4f spent + $%.4f = $%.4f, over the ceiling $%.2f" % (s, usd, s + usd, cap))
            return 3
        print("ok: $%.4f spent + $%.4f fits the ceiling $%.2f" % (s, usd, cap))
        return 0
    if cmd == "add":
        calls = int(opt(argv, "--calls", "1"))
        unit = float(opt(argv, "--unit", "0"))
        row = {"at": iso(now_utc()), "step": opt(argv, "--step", ""), "what": opt(argv, "--what", ""), "calls": calls,
               "unit_usd": "%.6f" % unit, "total_usd": "%.6f" % (calls * unit), "note": opt(argv, "--note", "")}
        p = os.path.join(folder, "cost.csv")
        new = not os.path.exists(p)
        import csv
        with open(p, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            if new:
                w.writeheader()
            w.writerow(row)
        total = s + calls * unit
        if total > cap + 1e-9:
            print("recorded; STOP: $%.4f is over the ceiling $%.2f" % (total, cap))
            return 3
        print("recorded; spent $%.4f of $%.2f" % (total, cap))
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
