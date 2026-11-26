#!/usr/bin/env python3
"""Tests for the Niche Topic Check workflow (0.5.1): topic_check.py, validate.py, standalone & niche reports, and r6 card.

    python3 tests/test_topic_check.py [-v]
"""
import csv
import datetime as dt
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SK = os.path.join(REPO, "skill", "scripts")
PLAYWRIGHT = next((p for p in (os.environ.get("REA_PLAYWRIGHT"), os.path.join(HERE, "node_modules", "playwright"),
                               os.path.expanduser("~/.cache/rea-viral/node_modules/playwright-core")) if p and os.path.isdir(p)), "")
sys.path.insert(0, SK)
import common  # noqa: E402

READ_AT = dt.datetime(2026, 11, 26, 15, 0, tzinfo=dt.timezone.utc)
TMP = None


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp(prefix="rea-viral-topic-")


def tearDownModule():
    if TMP and os.environ.get("REA_KEEP") != "1":
        shutil.rmtree(TMP, ignore_errors=True)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(hours):
    return iso(READ_AT - dt.timedelta(hours=hours))


def run(script, *args, ok=(0,), env=None):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if env:
        e.update(env)
    r = subprocess.run([sys.executable, "-I", os.path.join(SK, script)] + [str(a) for a in args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, env=e)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    if ok is not None and r.returncode not in ok:
        raise AssertionError("%s %s exited %d:\n%s" % (script, " ".join(map(str, args)), r.returncode, out[-3000:]))
    return r.returncode, out


def jload(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return json.load(f)


def text(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def make_topic_folder(name, rows, meta_extra=None):
    d = tempfile.mkdtemp(prefix=name + "-", dir=TMP)
    meta = {
        "schema": "rea-viral/topic@1",
        "topic": "Seedance 2.0",
        "slug": "seedance-2",
        "network": "x",
        "query": "Seedance 2.0",
        "read_at": iso(READ_AT),
        "sources": [{"what": "topic search", "via": "test_topic_check.py", "cost_usd": 0}],
    }
    if meta_extra:
        meta.update(meta_extra)
    with open(os.path.join(d, "topic.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(d, "topic_posts.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=common.TOPIC_POST_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, "" if r.get(k) is None else r.get(k)) for k in common.TOPIC_POST_COLUMNS))
    return d


def prow(pid, hours_ago, views, author="creator", followers=2000, caption="Seedance 2.0 test clip", sampled="", wtag=""):
    return {
        "post_id": pid,
        "url": "https://x.com/%s/status/%s" % (author, pid),
        "network": "x",
        "author": author,
        "author_followers": followers,
        "published_at": ago(hours_ago) if hours_ago is not None else "",
        "views": views,
        "likes": max(1, views // 50) if views is not None else "",
        "comments": max(0, views // 400) if views is not None else "",
        "reposts": max(0, views // 600) if views is not None else "",
        "caption": caption,
        "window_tag": wtag,
        "sampled": sampled,
        "source": "fixture",
    }


class TopicCheckMeasures(unittest.TestCase):
    def test_low_saturation_rising_none_yet(self):
        rows = [
            prow("r1", 0.5, 9000, "small1", 1200),
            prow("r2", 1.2, 6500, "small2", 2400),
            prow("r3", 2.0, 5200, "small3", 800),
            prow("r4", 3.5, 4100, "small4", 1900),
            prow("r5", 4.5, 3000, "small5", 3100),
            prow("r6", 5.2, 2200, "small6", 900),
            prow("p1", 7.0, 3500, "prev1", 1100),
            prow("p2", 9.0, 2900, "prev2", 1500),
        ]
        d = make_topic_folder("low-rising", rows)
        run("validate.py", d)
        run("topic_check.py", d)
        tc = jload(d, "topic_check.json")
        self.assertEqual(tc["status"], "ok")
        self.assertEqual(tc["saturation"]["level"], "low")
        self.assertEqual(tc["momentum"]["level"], "rising")
        self.assertEqual((tc["momentum"]["last_6h"]["posts"], tc["momentum"]["prev_6h"]["posts"]), (6, 2))
        self.assertEqual(tc["momentum"]["ratio"], 3.0)
        self.assertEqual(tc["lateness"]["band"], "none_yet")
        self.assertIsNone(tc["lateness"]["hours_since_first_big"])
        self.assertFalse(tc["sampled"])
        self.assertIn("Rising, not taken yet", tc["verdict"])
        md = text(d, "TOPIC.md")
        self.assertIn("Rising, not taken yet", md)
        self.assertIn("last 6h: 6 posts", md)

    def test_taken_by_large_account_and_late_fading(self):
        rows = [
            prow("big1", 13.0, 666000, "giant_ai", 250000, "Seedance 2.0 launch breakdown"),
            prow("f1", 2.0, 12000, "c1", 3000),
            prow("f2", 4.0, 8000, "c2", 1800),
            prow("p1", 7.0, 19000, "c3", 4000),
            prow("p2", 8.0, 14000, "c4", 3500),
            prow("p3", 9.5, 11000, "c5", 2200),
            prow("p4", 10.5, 9500, "c6", 2000),
            prow("p5", 11.0, 7500, "c7", 1500),
        ]
        d = make_topic_folder("taken-late", rows)
        run("topic_check.py", d)
        tc = jload(d, "topic_check.json")
        self.assertEqual(tc["saturation"]["level"], "taken")
        self.assertEqual(len(tc["saturation"]["large_account_breakouts"]), 1)
        self.assertEqual(tc["saturation"]["large_account_breakouts"][0]["author"], "giant_ai")
        self.assertEqual(tc["momentum"]["level"], "fading")
        self.assertEqual(tc["lateness"]["band"], "late")
        self.assertEqual(tc["lateness"]["hours_since_first_big"], 13.0)
        self.assertIn("Taken by @giant_ai", tc["verdict"])
        self.assertIn("fading", tc["verdict"])

    def test_user_followers_scales_large_account_threshold(self):
        # 25K-follower account gets a 150K breakout:
        # - Without user_followers: default threshold is 100K -> medium (not taken)
        # - With user.followers = 2000: threshold is max(10K, 10*2000) = 20K -> taken!
        rows = [
            prow("b1", 1.5, 150000, "mid_creator", 25000),
            prow("r1", 2.5, 8000, "c1", 1000),
            prow("r2", 3.5, 6000, "c2", 1200),
            prow("p1", 7.5, 7000, "c3", 1500),
            prow("p2", 9.5, 5000, "c4", 1100),
        ]
        d_default = make_topic_folder("thr-default", rows)
        run("topic_check.py", d_default)
        tc1 = jload(d_default, "topic_check.json")
        self.assertEqual(tc1["saturation"]["large_account_threshold"], 100000)
        self.assertEqual(tc1["saturation"]["level"], "medium")
        self.assertEqual(tc1["lateness"]["band"], "early")
        self.assertEqual(tc1["momentum"]["level"], "rising")

        d_small_user = make_topic_folder("thr-user", rows, {"user": {"handle": "me", "followers": 2000}})
        run("topic_check.py", d_small_user)
        tc2 = jload(d_small_user, "topic_check.json")
        self.assertEqual(tc2["saturation"]["large_account_threshold"], 20000)
        self.assertEqual(tc2["saturation"]["level"], "taken")

    def test_flat_tight_not_enough_data_and_sampled(self):
        # Flat momentum (3 vs 3) and tight lateness (3.5h since 120K small-account breakout) + sampled
        rows = [
            prow("b1", 3.5, 120000, "tiny_breakout", 4000, sampled="true"),
            prow("r1", 1.0, 5000, "c1", 1000),
            prow("r2", 2.0, 4000, "c2", 1200),
            prow("p1", 7.0, 6000, "c3", 1400),
            prow("p2", 8.0, 5500, "c4", 1600),
            prow("p3", 9.0, 4500, "c5", 1300),
        ]
        d = make_topic_folder("flat-tight", rows)
        run("topic_check.py", d)
        tc = jload(d, "topic_check.json")
        self.assertEqual(tc["momentum"]["level"], "flat")
        self.assertEqual(tc["lateness"]["band"], "tight")
        self.assertTrue(tc["sampled"])
        self.assertIn("(from sample)", tc["verdict"])
        self.assertIn("Sample only", tc["sample_note"])

        # Under 4 posts across both 6h windows -> not_enough_data + time_filter_supported=false
        d_few = make_topic_folder("few-posts", [prow("x1", 1.0, 5000, "a", 1000), prow("x2", 8.0, 4000, "b", 1000)],
                                  {"time_filter_supported": False})
        run("topic_check.py", d_few)
        tc_few = jload(d_few, "topic_check.json")
        self.assertEqual(tc_few["momentum"]["level"], "not_enough_data")
        self.assertTrue(tc_few["sampled"])

    def test_validate_rejects_bad_topic_inputs(self):
        d = make_topic_folder("bad-topic", [prow("p1", 1.0, 1000)], {"topic": ""})
        with open(os.path.join(d, "topic_posts.csv"), "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["p2", "", "x", "bob", "12.5K", "not-a-date", "500", "", "", "", "", "", "maybe", ""])
        code, out = run("validate.py", d, ok=(1,))
        self.assertIn("topic.json:topic", out)
        self.assertIn("topic_posts.csv:row 3:author_followers", out)
        self.assertIn("topic_posts.csv:row 3:published_at", out)
        self.assertIn("topic_posts.csv:row 3:sampled", out)


class TopicReportAndCard(unittest.TestCase):
    def test_standalone_report_stale_check_and_r6_card(self):
        rows = [
            prow("b1", 1.8, 180000, "fast_dev", 8500, "Built a full product ad with Seedance 2.0 in 10 minutes"),
            prow("r1", 0.7, 32000, "c1", 2200, "First side-by-side Seedance 2.0 vs Kling"),
            prow("r2", 1.5, 19000, "c2", 1800, "Testing Seedance 2.0 camera control"),
            prow("r3", 2.8, 12000, "c3", 3000, "Seedance 2.0 lighting test"),
            prow("r4", 4.1, 8500, "c4", 1200, "Seedance 2.0 prompt sheet"),
            prow("p1", 7.2, 9000, "c5", 1500, "Early look at Seedance 2.0"),
            prow("p2", 9.8, 6000, "c6", 900, "Seedance 2.0 just dropped"),
        ]
        d = make_topic_folder("standalone", rows)
        run("topic_check.py", d)
        run("build_report.py", d)
        self.assertTrue(os.path.exists(os.path.join(d, "report.html")))
        self.assertTrue(os.path.exists(os.path.join(d, "report-light.html")))
        html = text(d, "report.html")
        self.assertIn("Topic check", html)
        self.assertIn("Seedance 2.0", html)

        # Render r6 card via post_card.py
        if shutil.which("node") and os.path.isdir(PLAYWRIGHT):
            out_png = os.path.join(d, "topic-r6.png")
            run("post_card.py", d, "--layout", "r6", "--skin", "cobalt", "--out", out_png,
                env={"REA_PLAYWRIGHT": PLAYWRIGHT})
            self.assertTrue(os.path.exists(out_png))
            self.assertEqual(png_size(out_png), (1080, 1350))
        else:
            run("post_card.py", d, "--layout", "r6", "--skin", "cobalt", "--html-only")
            self.assertTrue(os.path.exists(os.path.join(d, "post-card.html")))

        # Stale check: editing topic_posts.csv blocks build_report.py until topic_check.py re-runs
        with open(os.path.join(d, "topic_posts.csv"), "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=common.TOPIC_POST_COLUMNS)
            w.writerow(prow("late_edit", 0.2, 5000, "late_author", 1000))
        code, out = run("build_report.py", d, ok=(1,))
        self.assertIn("run topic_check.py again", out)

    def test_niche_report_embeds_topic_check_block(self):
        nfx = os.path.join(TMP, "nfx")
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_niche_fixtures.py"), "--out", nfx],
                       check=True, stdout=subprocess.DEVNULL, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        nm = os.path.join(nfx, "niche_main")
        # Add topic_posts.csv inside the niche folder
        niche_read = dt.datetime.strptime(jload(nm, "niche.json")["read_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        rows = []
        for i, (h, v, fol) in enumerate([(1.0, 220000, 180000), (2.0, 18000, 3000), (3.0, 12000, 2000),
                                         (4.0, 9000, 1500), (7.5, 8000, 1200), (9.5, 6000, 1000)]):
            r = prow("nt%d" % i, 0, v, "niche_auth_%d" % i, fol)
            r["published_at"] = iso(niche_read - dt.timedelta(hours=h))
            rows.append(r)
        with open(os.path.join(nm, "topic_posts.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=common.TOPIC_POST_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow(dict((k, "" if r.get(k) is None else r.get(k)) for k in common.TOPIC_POST_COLUMNS))
        run("validate.py", nm)
        run("radar.py", nm)
        run("text_probe.py", nm)
        run("topic_check.py", nm)
        shutil.copy(os.path.join(nm, "findings.example.json"), os.path.join(nm, "findings.json"))
        run("build_report.py", nm)
        self.assertIn("Topic check", text(nm, "NICHE.md"))
        self.assertIn("section('topic-check'", text(nm, "report.html"))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
