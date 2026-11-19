#!/usr/bin/env python3
"""Scout and Watch (skill/scripts/watch.py) on made-up counts with known jumps.

    python3 tests/test_watch.py [-v]

A stand-in reader (a small script that prints the count for the day it is asked about) plays three accounts:
  steady  ~+100 a day, then +2,000 on day 8           -> one jump alert on day 8, nothing else
  small   a 900-follower account wobbling +-30 a day  -> never fires (the floor of 50)
  big     12.3M shown rounded, moving one step a day  -> never fires (the floor of 2x the rounding)
Checked: counts.csv rows, the jump file and alerts.jsonl, exit code 10, the hot pace after a jump (4 h), a missed read
written as a gap and never filled, the file reader (an inbox another job appends to), Scout's prune, the analysis
reading Watch counts as MEASURED (Watched), and the schedule commands (printed only; nothing is installed here).
"""
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WATCH = os.path.join(REPO, "skill", "scripts", "watch.py")
T0 = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.timezone.utc)

READER = r'''
import json, os, sys, datetime as dt
net, handle = sys.argv[1], sys.argv[2]
now = dt.datetime.fromisoformat(open(os.path.join(os.path.dirname(__file__), "clock.txt")).read().strip())
day = (now - dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.timezone.utc)).total_seconds() / 86400.0
import math
if handle == "steady":
    f = 50000 + int(100 * day) + (2000 if day >= 8 else 0)
    print(json.dumps({"followers": f, "exact": True, "profile": {"bio": "steady", "link": "https://a.example"},
                      "recent_posts": [{"post_id": "s%d" % i, "url": "https://x.example/%d" % i,
                                        "published_at": (now - dt.timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        "views": 9000 if (i == 1 and day >= 8) else 3000} for i in range(1, 9)]}))
elif handle == "small":
    f = 900 + int(5 * day) + (30 if int(day) % 2 else -30)
    print(json.dumps({"followers": f, "exact": True}))
elif handle == "big":
    print(json.dumps({"followers": 12300000 + 100000 * (int(day) % 2), "exact": False}))
else:
    sys.exit(3)
'''


def run(*args, ok=(0,)):
    r = subprocess.run([sys.executable, "-I", WATCH] + [str(a) for a in args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=120)
    out = r.stdout.decode() + r.stderr.decode()
    if ok is not None and r.returncode not in ok:
        raise AssertionError("watch.py %s exited %d:\n%s" % (" ".join(map(str, args)), r.returncode, out))
    return r.returncode, out


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def jload(path):
    with open(path) as f:
        return json.load(f)


def text(path):
    with open(path) as f:
        return f.read()


class Watch(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-watch-")
        self.reader = os.path.join(self.d, "reader.py")
        with open(self.reader, "w") as f:
            f.write(READER)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def at(self, t):
        with open(os.path.join(self.d, "clock.txt"), "w") as f:
            f.write(t.isoformat())
        return iso(t)

    def counts(self):
        with open(os.path.join(self.d, "watch", "counts.csv")) as f:
            return list(csv.DictReader(f))

    def test_jump_rule_and_pace(self):
        run("init", self.d, "--reader-command", "%s %s {network} {handle}" % (sys.executable, self.reader))
        for h in ("steady", "small", "big"):
            run("add", self.d, "tiktok", h)
        codes = {}
        for day in range(0, 10):
            now = self.at(T0 + dt.timedelta(days=day))
            code, out = run("run", self.d, "--now", now, ok=(0, 10))
            codes[day] = code
        self.assertEqual([d for d, c in codes.items() if c == 10], [8])
        jumps = os.listdir(os.path.join(self.d, "watch", "jumps"))
        self.assertEqual(jumps, ["2026-11-09-tiktok-steady.md"])
        body = text(os.path.join(self.d, "watch", "jumps", jumps[0]))
        self.assertIn("Posts of the last 72 hours", body)
        self.assertIn("3.0x", body)                                      # the fresh post at 3x the older ones
        alerts = [json.loads(l) for l in text(os.path.join(self.d, "watch", "alerts.jsonl")).splitlines()]
        self.assertEqual([(a["handle"], a["gain_day"] > 1500) for a in alerts], [("steady", True)])
        st = jload(os.path.join(self.d, "watch", "state.json"))
        nxt = dt.datetime.fromisoformat(st["tiktok:steady"]["next_read_at"].replace("Z", "+00:00"))
        last = dt.datetime.fromisoformat(st["tiktok:steady"]["last"]["at"].replace("Z", "+00:00"))
        self.assertEqual(nxt - last, dt.timedelta(hours=4))              # day 9: a post under 48 h runs at 3x: still hot
        nxt = dt.datetime.fromisoformat(st["tiktok:small"]["next_read_at"].replace("Z", "+00:00"))
        last = dt.datetime.fromisoformat(st["tiktok:small"]["last"]["at"].replace("Z", "+00:00"))
        self.assertEqual(nxt - last, dt.timedelta(hours=24))             # a quiet account: once a day
        self.assertGreater(st["tiktok:small"]["last"]["verdict"]["noise_daily"], 50)
        rows = self.counts()
        self.assertEqual(sum(1 for r in rows if r["status"] == "ok"), 30)

    def test_hot_pace_after_jump_and_gap(self):
        run("init", self.d, "--reader-command", "%s %s {network} {handle}" % (sys.executable, self.reader))
        run("add", self.d, "tiktok", "steady")
        for day in range(0, 9):
            run("run", self.d, "--now", self.at(T0 + dt.timedelta(days=day)), ok=(0, 10))
        st = jload(os.path.join(self.d, "watch", "state.json"))["tiktok:steady"]
        nxt = dt.datetime.fromisoformat(st["next_read_at"].replace("Z", "+00:00"))
        self.assertEqual(nxt, T0 + dt.timedelta(days=8, hours=4))        # every 4 h after a jump
        code, out = run("run", self.d, "--now", self.at(T0 + dt.timedelta(days=8, hours=2)))
        self.assertNotIn("tiktok:steady", out)                           # not due yet
        code, out = run("run", self.d, "--now", self.at(T0 + dt.timedelta(days=8, hours=4)), ok=(0, 10))
        self.assertIn("tiktok:steady", out)
        self.assertNotIn("JUMP", out)                                    # one alert per 24 h
        # Three days with no reads: the next run writes a gap row first, and nothing fills it.
        run("run", self.d, "--now", self.at(T0 + dt.timedelta(days=12)), ok=(0, 10))
        rows = self.counts()
        gaps = [r for r in rows if r["status"] == "gap"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("no reading since", gaps[0]["note"])

    def test_reader_failure_is_a_missed_read(self):
        run("init", self.d, "--reader-command", "%s %s {network} {handle}" % (sys.executable, self.reader))
        run("add", self.d, "tiktok", "nobody")
        code, out = run("run", self.d, "--now", self.at(T0), ok=(1,))
        rows = self.counts()
        self.assertEqual([r["status"] for r in rows], ["error"])
        self.assertEqual(rows[0]["followers"], "")

    def test_file_reader_and_analysis(self):
        run("init", self.d, "--reader-file", "watch/inbox.csv")
        run("add", self.d, "youtube", "examplechan")
        inbox = os.path.join(self.d, "watch", "inbox.csv")
        with open(inbox, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["read_at", "network", "handle", "followers", "exact", "posts_count", "source"])
            for day in range(0, 6):
                w.writerow([iso(T0 + dt.timedelta(days=day)), "youtube", "examplechan", 10000 + 50 * day, "true", "", "agent"])
        code, out = run("run", self.d, "--now", iso(T0 + dt.timedelta(days=5)))
        self.assertEqual(sum(1 for r in self.counts() if r["status"] == "ok"), 6)
        with open(inbox, "a", newline="") as f:
            csv.writer(f).writerow([iso(T0 + dt.timedelta(days=6)), "youtube", "examplechan", 10250 + 3000, "true", "", "agent"])
        code, out = run("run", self.d, "--now", iso(T0 + dt.timedelta(days=6)), ok=(10,))
        self.assertIn("JUMP youtube:examplechan", out)
        code, out = run("run", self.d, "--now", iso(T0 + dt.timedelta(days=6, hours=1)))
        self.assertEqual(sum(1 for r in self.counts() if r["status"] == "ok"), 7)   # rows are taken once
        with open(inbox, "a", newline="") as f:                          # reads go on after the jump
            for day in (7, 8, 9):
                csv.writer(f).writerow([iso(T0 + dt.timedelta(days=day)), "youtube", "examplechan", 13250 + 50 * (day - 6), "true", "", "agent"])
        run("run", self.d, "--now", iso(T0 + dt.timedelta(days=9)), ok=(0, 10))
        # The analysis of that account reads the Watch counts beside its run folder: MEASURED (Watched).
        run_dir = os.path.join(self.d, "youtube-examplechan")
        os.makedirs(run_dir)
        acc = {"schema": "rea-viral/account@1", "network": "youtube", "handle": "examplechan", "read_at": iso(T0 + dt.timedelta(days=14)),
               "window": {"from": "2026-10-01", "to": "2026-11-14"}, "sources": [{"what": "test", "via": "test", "cost_usd": 0}]}
        with open(os.path.join(run_dir, "account.json"), "w") as f:
            json.dump(acc, f)
        with open(os.path.join(run_dir, "posts.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["post_id", "url", "published_at", "type", "views"])
            for i in range(25):
                t = T0 - dt.timedelta(days=24) + dt.timedelta(days=i * 1.2)
                w.writerow(["v%02d" % i, "https://y.example/%d" % i, iso(t), "video", 30000 if i == 23 else 5000])
        r = subprocess.run([sys.executable, "-I", os.path.join(REPO, "skill", "scripts", "analyze.py"), run_dir],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        an = jload(os.path.join(run_dir, "analysis.json"))
        self.assertGreaterEqual(an["attribution"]["levels"]["watched"], 1)
        self.assertEqual(an["attribution"]["top_measured"][0], "v23")

    def test_prune_keeps_top_tenth(self):
        run("init", self.d, "--reader-file", "watch/inbox.csv")
        with open(os.path.join(self.d, "watch", "inbox.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["read_at", "network", "handle", "followers", "exact", "posts_count", "source"])
            for k in range(10):
                for day in range(0, 8):
                    w.writerow([iso(T0 + dt.timedelta(days=day)), "tiktok", "c%d" % k, 1000 + (10 + 40 * (k == 7)) * day, "true", "", "t"])
        for k in range(10):
            run("add", self.d, "tiktok", "c%d" % k, "--source", "scout")
        run("run", self.d, "--now", iso(T0 + dt.timedelta(days=7)))
        code, out = run("prune", self.d, "--days", "7", "--keep", "0.1", "--now", iso(T0 + dt.timedelta(days=7)))
        with open(os.path.join(self.d, "watch", "watchlist.csv")) as f:
            st = dict((r["handle"], r["status"]) for r in csv.DictReader(f))
        self.assertEqual([h for h, s in st.items() if s == "active"], ["c7"])
        self.assertEqual(sum(1 for s in st.values() if s == "dropped"), 9)

    def test_schedule_prints_and_asks(self):
        run("init", self.d, "--reader-file", "watch/inbox.csv")
        for what, needle in (("launchd", "<key>StartInterval</key>"), ("cron", "# rea-viral-watch"),
                             ("schtasks", "schtasks /Create"), ("agent", "Every 4 hours")):
            code, out = run("schedule", self.d, "--print", what)
            self.assertIn(needle, out)
            self.assertIn(os.path.abspath(self.d), out)
        code, out = run("schedule", self.d, "--print", "launchd")
        self.assertIn("take it down", out)
        code, out = run("schedule", self.d, "--install", "cron", ok=(2,))
        self.assertIn("ask the user", out)
        code, out = run("schedule", self.d, "--install", "launchd", "--yes", "--dry-run")
        self.assertIn("would write", out)
        self.assertFalse(os.path.exists(os.path.expanduser("~/Library/LaunchAgents/com.rea-viral.watch.plist")) and
                         "would write" not in out)


if __name__ == "__main__":
    unittest.main()
