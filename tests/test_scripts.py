#!/usr/bin/env python3
"""REA Viral scripts against accounts with known answers (make_fixtures.py) and edge cases.

    python3 tests/test_scripts.py [-v]

Each test copies a fixture into a temp folder and runs the skill's scripts the way an agent would (as programs, with
python3 -I). Checked: the validator's exact errors; baselines on an account that grew tenfold; formats and corners;
the follower jump found at the MEASURED level and the same post found at the ESTIMATED level without counts; gaps;
missing dates, zero views, one post, private and empty accounts; comment tactics; comments without replies; the report
refusing unlabelled, misquoted or stale claims; a caption with a script tag shown as data; the video probe on a
synthetic video with known cuts and words; the ledger's ceiling; the app check against a stand-in server.
Version 0.4.0: the Account report's "What did not work" (formats under the usual or fading, the flops, what sinks
in the words, "not enough data" said, did_not_work claims checked); the hand-over files for a planner connector
(report_record.json, radar_rows.json: shapes, the 600-character summary, stable keys, the recipe's beats); and the
report as ONE file (pictures inside, smaller with ffmpeg, under the caps and the budget, under 3 MB with heavy covers;
without ffmpeg only small originals go in and the rest is named).
Not checked here: Watch (test_watch.py), the Basic renderer (test_render.py), the page in a browser (verify_report.mjs).
"""
import csv
import datetime as dt
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SK = os.path.join(REPO, "skill", "scripts")
TMP = None
FX = None


def setUpModule():
    global TMP, FX
    TMP = tempfile.mkdtemp(prefix="rea-viral-test-")
    FX = os.path.join(TMP, "fixtures")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_fixtures.py"), "--out", FX],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError("make_fixtures.py failed: " + r.stderr.decode())


def tearDownModule():
    if TMP and os.environ.get("REA_KEEP") != "1":
        shutil.rmtree(TMP, ignore_errors=True)


def copy(name):
    dst = tempfile.mkdtemp(prefix=name + "-", dir=TMP)
    shutil.rmtree(dst)
    shutil.copytree(os.path.join(FX, name), dst)
    return dst


def run(script, *args, ok=(0,)):
    r = subprocess.run([sys.executable, "-I", os.path.join(SK, script)] + [str(a) for a in args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
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


def posts_by_id(an):
    return dict((p["post_id"], p) for p in an["posts"])


class Validator(unittest.TestCase):
    def test_bad_rows_named_exactly(self):
        d = copy("bad_rows")
        code, out = run("validate.py", d, "--json", ok=(1,))
        rep = json.loads(out[:out.rindex("}") + 1])
        where = sorted(e["where"] for e in rep["errors"])
        self.assertEqual(where, sorted(jload(d, "KNOWN.json")["errors"]))
        text = json.dumps(rep)
        self.assertIn("12300", text)                        # tells what to write instead of 12.3K
        self.assertIn("is type video", text)                # a reel is a video
        self.assertIn("Unix time", text)
        code, out = run("analyze.py", d, ok=(1,))           # the numbers refuse bad rows
        self.assertIn("fix them first", out)

    def test_good_fixture_has_no_errors(self):
        d = copy("main")
        code, out = run("validate.py", d)
        self.assertIn("OK: 0 error(s)", out)


class Numbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = copy("main")
        run("analyze.py", cls.d)
        run("radar.py", cls.d)
        cls.an = jload(cls.d, "analysis.json")
        cls.radar = jload(cls.d, "radar.json")
        cls.known = jload(cls.d, "KNOWN.json")

    def test_statuses(self):
        P = posts_by_id(self.an)
        self.assertEqual(self.an["status"], "ok")
        for pid in self.known["too_new"]:
            self.assertEqual(P[pid]["status"], "too_new")
        for pid in self.known["warmup"]:
            self.assertIn(P[pid]["status"], ("warmup",))
        self.assertEqual(self.an["counts"]["scored"], 120)

    def test_format_corners_and_lift(self):
        got = dict((f["id"], f["quadrant"]) for f in self.radar["formats"])
        self.assertEqual(got, self.known["formats"])
        tm = [f for f in self.radar["formats"] if f["id"] == "three-mistakes"][0]
        self.assertTrue(2.4 <= tm["lift"] <= 3.6, tm["lift"])          # built at 3x
        self.assertGreaterEqual(tm["hit_rate"], 0.9)
        fd = [f for f in self.radar["formats"] if f["id"] == "founder-diary"][0]
        self.assertLess(fd["direction"], 0.75)                          # built from 1.7x down to 0.6x
        self.assertEqual(fd["direction_label"], "fading")      # 0.4.1: rising / steady / fading only

    def test_new_format_mark(self):
        marks = [m for m in self.radar["timeline_marks"] if m["kind"] == "format"]
        self.assertEqual([m["format"] for m in marks], [self.known["new_format"]["id"]])
        self.assertEqual(marks[0]["at"], self.known["new_format"]["first"][:10])

    def test_followers_measured_jump(self):
        P = posts_by_id(self.an)
        top = self.an["attribution"]["top_measured"][0]
        self.assertEqual(top, self.known["jump_post"])
        ex = P[top]["followers"]["excess_72h"]
        self.assertTrue(0.7 * self.known["jump_size"] <= ex <= 1.05 * self.known["jump_size"], ex)
        self.assertEqual(P[top]["followers"]["evidence"], "MEASURED")
        self.assertEqual(len(self.an["followers"]["gaps"]), 1)
        for pid in self.known["gap_posts"]:
            if P[pid]["status"] == "scored":
                self.assertEqual(P[pid]["followers"]["level"], "estimated", pid)   # a gap is never filled
        pulls = dict((f["id"], f["follower_pull"]["value"]) for f in self.radar["formats"])
        self.assertEqual(max(pulls, key=pulls.get), "three-mistakes")          # +200 after each of its posts

    def test_estimated_without_counts(self):
        d = copy("main_estimated")
        run("analyze.py", d)
        an = jload(d, "analysis.json")
        P = posts_by_id(an)
        top = an["attribution"]["top_estimated"][0]
        self.assertEqual(top, "p087")
        f = P[top]["followers"]
        self.assertEqual((f["level"], f["evidence"], f["label"]), ("estimated", "INFERRED", "likely brought followers"))
        self.assertNotIn("gain_72h", f)                                         # never a count
        likely = [p for p in an["posts"] if (p["followers"] or {}).get("label") == "likely brought followers"]
        self.assertEqual([p["post_id"] for p in likely], ["p087"])

    def test_length_buckets(self):
        rows = dict((r["bucket"], r) for r in self.an["by_length"])
        self.assertEqual(rows["60 s and over"]["posts"], 12)                   # long-story is 62 s
        self.assertLess(rows["60 s and over"]["median_ratio"], 0.7)


class EdgeCases(unittest.TestCase):
    def test_tenfold_growth(self):
        d = copy("tenfold")
        run("analyze.py", d)
        an = jload(d, "analysis.json")
        self.assertEqual(an["outliers"], ["t150"])
        # The trap the local baseline avoids: against one global median, most late posts look like hits.
        vals = sorted(p["views"] for p in an["posts"] if p["in_window"])
        med = vals[len(vals) // 2]
        self.assertGreater(sum(1 for v in vals if v > 2 * med), 25)
        pace = [m for m in an["timeline"]["marks"] if m["kind"] == "pace"]
        self.assertEqual(len(pace), 1)
        at = dt.date.fromisoformat(pace[0]["at"])
        self.assertLessEqual(abs((at - dt.date(2026, 10, 5)).days), 14)

    def test_missing_dates(self):
        d = copy("missing_dates")
        run("analyze.py", d)
        an = jload(d, "analysis.json")
        self.assertEqual(an["status"], "ok")
        self.assertEqual(sorted(e["post_id"] for e in an["excluded"] if e["reason"] == "no_date"),
                         jload(d, "KNOWN.json")["no_date"])

    def test_no_dates(self):
        d = copy("no_dates")
        run("analyze.py", d)
        self.assertEqual(jload(d, "analysis.json")["status"], "no_dates")
        run("radar.py", d)
        self.assertEqual(jload(d, "radar.json")["status"], "no_dates")

    def test_zero_views(self):
        d = copy("zero_views")
        code, out = run("validate.py", d)
        self.assertIn("posts.csv:row 37:views: views 0 but likes 50", out)
        run("analyze.py", d)
        P = posts_by_id(jload(d, "analysis.json"))
        for pid in jload(d, "KNOWN.json")["baseline_zero"]:
            self.assertEqual(P[pid]["status"], "no_baseline", pid)
        self.assertEqual(P["z30"]["ratio"], 0.0)
        self.assertIn("z30", jload(d, "analysis.json")["flops"])

    def test_one_post(self):
        d = copy("one_post")
        run("analyze.py", d)
        self.assertEqual(jload(d, "analysis.json")["status"], "too_few_posts")
        run("radar.py", d)
        r = jload(d, "radar.json")
        self.assertEqual((r["status"], r["formats"], len(r["posts"])), ("too_few_posts", [], 1))
        run("build_report.py", d)

    def test_private_and_empty(self):
        for name in ("private", "empty"):
            d = copy(name)
            run("analyze.py", d)
            self.assertEqual(jload(d, "analysis.json")["status"], name)
            run("radar.py", d)
            run("build_report.py", d)
            self.assertTrue(os.path.exists(os.path.join(d, "report.html")))
            self.assertIn("Status: %s" % name, text(d, "ACCOUNT.md"))


class Comments(unittest.TestCase):
    def test_tactics_known(self):
        d = copy("main")
        run("comment_tactics.py", d)
        c = jload(d, "comments.json")
        k = jload(d, "KNOWN.json")["comments"]
        self.assertEqual(c["posts_read"], k["posts_read"])
        self.assertEqual(c["creator_comment"]["posts_with_own_comment"], k["own_comment_posts"])
        self.assertEqual(c["creator_comment"]["came_first"], k["own_comment_posts"])
        self.assertEqual(c["creator_comment"]["within_10_min"], k["own_comment_posts"])
        self.assertEqual(c["pinned"]["posts_with_pinned"], k["pinned_posts"])
        self.assertEqual(c["pinned"]["by_creator"], k["pinned_posts"])
        self.assertEqual(c["comment_a_word"]["posts_asking"], k["posts_asking"])
        echo = c["comment_a_word"]["echo"]
        self.assertEqual(len(echo), k["echo_posts"])
        self.assertTrue(all(e["word"] == k["echo_word"] and abs(e["share"] - k["echo_share"]) < 1e-9 for e in echo))
        self.assertAlmostEqual(c["replies_by_creator"]["rate"], k["reply_rate"])
        self.assertAlmostEqual(c["replies_by_creator"]["median_minutes_to_reply"], k["median_reply_minutes"])
        self.assertEqual(c["follow_comments"]["count"], k["follow_comments"])
        self.assertEqual(c["follow_comments"]["by_post"]["p087"], k["follow_on_jump_post"])
        self.assertGreaterEqual(c["objections_count"], k["objections_at_least"])

    def test_no_replies_and_unread_replies(self):
        d = copy("no_replies")
        run("comment_tactics.py", d)
        rb = jload(d, "comments.json")["replies_by_creator"]
        self.assertEqual((rb["rate"], rb["evidence"]), (0.0, "MEASURED"))
        self.assertIn("no replies", rb["note"])
        d = copy("replies_unread")
        run("comment_tactics.py", d)
        rb = jload(d, "comments.json")["replies_by_creator"]
        self.assertIsNone(rb["rate"])
        self.assertIn("not read", rb["note"])

    def test_inexact_times_measure_no_minutes(self):
        d = copy("main")
        path = os.path.join(d, "comments.csv")
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["created_at_exact"] = "false"
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        run("comment_tactics.py", d)
        c = jload(d, "comments.json")
        self.assertIsNone(c["replies_by_creator"]["median_minutes_to_reply"])
        self.assertEqual(c["creator_comment"]["within_10_min_known"], 0)
        self.assertIn("nothing is measured in minutes", c["times_exact"]["note"])


class Report(unittest.TestCase):
    def setUp(self):
        self.d = copy("main")
        run("analyze.py", self.d)
        run("radar.py", self.d)
        run("comment_tactics.py", self.d)
        shutil.copy(os.path.join(self.d, "findings.example.json"), os.path.join(self.d, "findings.json"))

    def findings(self, fn):
        p = os.path.join(self.d, "findings.json")
        f = jload(p)
        fn(f)
        with open(p, "w") as fh:
            json.dump(f, fh)

    def test_builds_and_embeds_data_safely(self):
        run("build_report.py", self.d)
        html = text(self.d, "report.html")
        self.assertEqual(html.count("</script>"), 2)                   # the injected caption cannot close a script
        self.assertIn("<\\/script>", html)
        self.assertNotIn("monospace", html)
        acc = text(self.d, "ACCOUNT.md")
        for layer in ("Layer 0", "Layer 1", "Layer 2"):
            self.assertIn(layer, acc)

    def test_refuses_unlabelled_claim(self):
        self.findings(lambda f: f["mechanisms"].append({"title": "x", "text": "a claim with no label"}))
        code, out = run("build_report.py", self.d, ok=(1,))
        self.assertIn("evidence", out)

    def test_refuses_seen_without_posts_and_inferred_without_basis(self):
        self.findings(lambda f: f["mechanisms"].extend([{"text": "seen", "evidence": "SEEN"},
                                                        {"text": "guess", "evidence": "INFERRED"}]))
        code, out = run("build_report.py", self.d, ok=(1,))
        self.assertIn("SEEN needs", out)
        self.assertIn("INFERRED needs", out)

    def test_refuses_wrong_quote(self):
        self.findings(lambda f: f["comment_tactics"].append(
            {"text": "fans say so", "evidence": "SEEN", "posts": ["p087"], "quote": "this is a comment nobody wrote"}))
        code, out = run("build_report.py", self.d, ok=(1,))
        self.assertIn("is not in a caption or comment", out)
        self.findings(lambda f: f["comment_tactics"].__setitem__(-1, dict(f["comment_tactics"][-1], quote="just followed")))
        run("build_report.py", self.d)

    def test_refuses_measured_key_that_does_not_exist(self):
        self.findings(lambda f: f["mechanisms"].append(
            {"text": "Shorts win by 940 percent.", "evidence": "MEASURED", "from": "analysis.json#nothing.here"}))
        code, out = run("build_report.py", self.d, ok=(1,))
        self.assertIn("has no key 'nothing.here'", out)
        self.findings(lambda f: f["mechanisms"].__setitem__(-1, dict(f["mechanisms"][-1],
                                                                     **{"from": "radar.json#formats.three-mistakes.lift"})))
        run("build_report.py", self.d)

    def test_refuses_stale_numbers(self):
        with open(os.path.join(self.d, "posts.csv"), "a", encoding="utf-8") as f:
            f.write("p999,https://www.tiktok.com/@x/video/p999,2026-11-01T10:00:00Z,video,20,late,100,1,1,1,1,,,,,,,,,,\n")
        code, out = run("build_report.py", self.d, ok=(1,))
        self.assertIn("run analyze.py again", out)


def page_data_of(path):
    html = text(path)
    a = html.index('id="rea-data">') + len('id="rea-data">')
    return json.loads(html[a:html.index("</script>", a)].replace("<\\/", "</").replace("<\\!--", "<!--"))


def page_data(d):
    """The data the page draws, read back out of report.html."""
    html = text(d, "report.html")
    a = html.index('id="rea-data">') + len('id="rea-data">')
    return json.loads(html[a:html.index("</script>", a)].replace("<\\/", "</").replace("<\\!--", "<!--"))


def build_main(with_pictures=False, env=None):
    d = copy("main")
    if with_pictures:
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "add_pictures.py"), d],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if r.returncode != 0:
            raise AssertionError("add_pictures.py: " + r.stderr.decode())
    run("analyze.py", d)
    run("radar.py", d)
    run("comment_tactics.py", d)
    shutil.copy(os.path.join(d, "findings.example.json"), os.path.join(d, "findings.json"))
    return d


class WhatDidNotWork(unittest.TestCase):
    """The Account report's part of its own beside what worked: formats under the usual or fading, the flops,
    what sinks in the words; the agent's did_not_work claims checked like every claim."""

    @classmethod
    def setUpClass(cls):
        cls.d = build_main()
        cls.code, cls.out = run("build_report.py", cls.d)
        cls.D = page_data(cls.d)

    def test_formats_under_the_usual_or_fading(self):
        nw = self.D["not_working"]
        self.assertEqual([f["id"] for f in nw["formats"]], ["long-story", "founder-diary"])   # lowest lift first
        ls, fd = nw["formats"]
        self.assertTrue(ls["under"] and not ls["fading"])
        self.assertTrue(fd["fading"])
        self.assertEqual(ls["flops"], 4)                       # 4 of the 5 flops are long stories (planted)
        self.assertEqual(len(ls["lowest"]), 3)
        self.assertTrue(all(x["ratio"] < 1 for x in ls["lowest"]))
        self.assertNotIn("three-mistakes", [f["id"] for f in nw["formats"]])
        self.assertNotIn("pov-skit", [f["id"] for f in nw["formats"]])

    def test_flops_and_unknown_words(self):
        fl = self.D["not_working"]["flops"]
        self.assertEqual(fl["count"], len(jload(self.d, "analysis.json")["flops"]))
        self.assertEqual(fl["by_format"][0]["format"], "long-story")
        self.assertEqual([x["post_id"] for x in fl["picks"]], jload(self.d, "analysis.json")["deep_read"]["flops"])
        self.assertTrue(all(x["read"] is None for x in fl["picks"]))       # nothing watched: never described
        self.assertIn("Not measured", self.D["not_working"]["words"]["note"])

    def test_account_md_and_page(self):
        md = text(self.d, "ACCOUNT.md")
        self.assertIn("REA Viral, Account report", md)
        self.assertIn("- [MEASURED] What did not work: Long story (Drop)", md)
        self.assertIn("| What did not work? |", md)
        self.assertIn("### What did not work", md)
        self.assertIn("The founder diary fades", md)          # the agent's did_not_work claim
        html = text(self.d, "report.html")
        self.assertIn("'What did not work'", html)
        self.assertIn("'What worked'", html)
        self.assertIn("Account report", html)
        self.assertNotIn("Format Radar", html)

    def test_sinking_words_come_through(self):
        d = copy("writing_x")
        run("text_probe.py", d)
        run("build_report.py", d)
        words = page_data(d)["not_working"]["words"]
        self.assertEqual(len(words["sinks"]), 1)               # posts with a link sink (planted)
        self.assertTrue(words["sinks"][0]["from"].startswith("writing.json#features."))
        self.assertIn("sinks", text(d, "ACCOUNT.md"))

    def test_did_not_work_claims_are_checked(self):
        d = build_main()
        f = jload(d, "findings.json")
        f["did_not_work"].append({"text": "the diary is boring"})
        with open(os.path.join(d, "findings.json"), "w") as fh:
            json.dump(f, fh)
        code, out = run("build_report.py", d, ok=(1,))
        self.assertIn("did_not_work", out)
        self.assertIn("evidence", out)

    def test_not_enough_data_said(self):
        d = copy("one_post")
        run("analyze.py", d)
        run("radar.py", d)
        run("build_report.py", d)
        nw = page_data(d)["not_working"]
        self.assertTrue(nw["note"].startswith("Not enough data"))
        self.assertTrue(nw["formats_note"].startswith("Not enough data"))
        self.assertEqual(jload(d, "radar_rows.json")["rows"], [])
        self.assertIn("No format to offer", jload(d, "radar_rows.json")["note"])
        b = jload(d, "brief.json")
        self.assertEqual(b["not_worked"][0]["title"], "Not enough data")
        self.assertEqual(b["worked"], [])


class HandOverFiles(unittest.TestCase):
    """report_record.json and radar_rows.json: the shapes a planner connector's save_report and save_formats take."""

    @classmethod
    def setUpClass(cls):
        cls.d = build_main()
        run("build_report.py", cls.d)
        cls.rec = jload(cls.d, "report_record.json")
        cls.rows = jload(cls.d, "radar_rows.json")

    def test_record(self):
        r = self.rec["report"]
        self.assertEqual(self.rec["schema"], "rea-viral/report-record@1")
        self.assertEqual(r["kind"], "account")
        self.assertEqual(r["title"], "@fixture_main · TikTok")
        self.assertEqual(r["subject"], {"network": "tiktok", "handle": "fixture_main", "url": "https://www.tiktok.com/@fixture_main"})
        self.assertLessEqual(len(r["summary"]), 600)
        self.assertTrue(r["summary"].startswith("It grows on one repeatable list format"))
        self.assertIn("What did not work: A quarter of the posts are diaries", r["summary"])
        self.assertEqual(r["read"], {"posts": 142, "creators": 1})
        self.assertEqual(r["skill"], {"name": "rea-viral", "version": "0.4.2"})
        self.assertEqual(r["cost_usd"], 0)
        self.assertEqual(jload(self.d, "report_record.json")["file"]["size"], os.path.getsize(os.path.join(self.d, "report.html")))
        self.assertEqual(self.rec["formats"], {"file": "radar_rows.json", "rows": 1})
        for k in ("id", "file", "created_at", "by"):
            self.assertNotIn(k, r)                             # the planner's and the agent's to add

    def test_strongest_format_row(self):
        self.assertEqual(self.rows["schema"], "rea-viral/radar-rows@1")
        self.assertEqual(len(self.rows["rows"]), 1)
        row = self.rows["rows"][0]
        self.assertRegex(row["key"], r"^f_[0-9a-f]{12}$")
        self.assertEqual((row["source"], row["state"], row["platform"], row["title"]), ("report", "link", "tiktok", "Three mistakes"))
        self.assertEqual(row["creator"], "@fixture_main")
        fm = row["format"]
        self.assertEqual((fm["name"], fm["creators"], fm["trend"]), ("Three mistakes", 1, "steady"))
        self.assertGreater(fm["lift"], 2.5)
        self.assertEqual(len(fm["proof"]), 3)
        self.assertTrue(all(u.startswith("https://") for u in fm["proof"]))
        self.assertEqual(row["url"], fm["proof"][0])
        self.assertIsInstance(row["numbers"]["views"], int)
        self.assertEqual(row["numbers"]["followers"], jload(self.d, "account.json")["followers"])

    def test_keys_stable_and_beats_carried(self):
        # The fixture's recipe has beats (filled as after a deep read); the planner keeps t as TEXT ("0:02.2").
        b = self.rows["rows"][0]["format"]["beats"]
        self.assertEqual(len(b), 5)
        self.assertEqual(b[0], {"t": "0:00", "what": "hook: the number and the loss on screen", "d": 2.2})
        self.assertEqual((b[1]["t"], b[1]["what"]), ("0:02.2", "turn: mistake one, a hard cut"))
        self.assertEqual((b[4]["t"], b[4]["d"]), ("0:22.5", 1.5))              # the last runs to the recipe's length
        self.assertTrue(all(isinstance(x["t"], str) and len(x["t"]) <= 20 for x in b))
        run("build_report.py", self.d)
        self.assertEqual(jload(self.d, "radar_rows.json")["rows"][0]["key"], self.rows["rows"][0]["key"])

    def test_clock(self):
        sys.path.insert(0, SK)
        sys.dont_write_bytecode = True
        try:
            import hand_over
            self.assertEqual([hand_over.clock(x) for x in (0, 2.2, 9.95, 59.99, 65, 125.5)],
                             ["0:00", "0:02.2", "0:10", "1:00", "1:05", "2:05.5"])
        finally:
            sys.path.remove(SK)

    def test_light_page_and_no_cover(self):
        full, light = os.path.join(self.d, "report.html"), os.path.join(self.d, "report-light.html")
        self.assertTrue(os.path.exists(light))
        self.assertLess(os.path.getsize(light), os.path.getsize(full))
        self.assertNotIn("data:image/", text(light))
        L = page_data_of(light)
        self.assertTrue(L["light"] and L["pictures"]["light"])
        self.assertEqual(len([p for p in L["posts"] if p.get("in_window")]),
                         len([p for p in page_data(self.d)["posts"] if p.get("in_window")]))   # every timeline dot
        rec = jload(self.d, "report_record.json")
        self.assertEqual(rec["light"]["size"], os.path.getsize(light))
        self.assertEqual(rec["light"]["path"], "report-light.html")
        self.assertIsNone(rec["cover"])                                        # no picture of its own

    def test_light_flag_builds_the_light_page_only(self):
        d = build_main()
        code, out = run("build_report.py", d, "--light")
        self.assertFalse(os.path.exists(os.path.join(d, "report.html")))
        self.assertTrue(os.path.exists(os.path.join(d, "report-light.html")))
        self.assertIn("--light: report.html was not rebuilt", out)
        self.assertIn("report-light.html:", out)
        self.assertIsNone(jload(d, "report_record.json")["file"]["size"])


def brief_problems(b):
    sys.path.insert(0, SK)
    sys.dont_write_bytecode = True
    try:
        import brief
        return brief.check(b)
    finally:
        sys.path.remove(SK)


class Brief(unittest.TestCase):
    """brief.json: the short view a planner's panel draws, built from findings.json and the numbers, never by hand."""

    @classmethod
    def setUpClass(cls):
        cls.d = build_main()
        run("build_report.py", cls.d)
        cls.b = jload(cls.d, "brief.json")

    def test_fits_the_limits_and_rides_in_the_record(self):
        self.assertEqual(brief_problems(self.b), [])
        rec = jload(self.d, "report_record.json")
        self.assertEqual(rec["report"]["brief"], dict((k, v) for k, v in self.b.items() if k != "schema"))
        self.assertEqual(rec["brief_file"], "brief.json")
        self.assertEqual(self.b["answer"], jload(self.d, "findings.json")["headline"]["text"])
        self.assertEqual(len(self.b["numbers"]), 6)
        self.assertEqual(self.b["numbers"][0], {"label": "Posts read", "value": "142"})

    def test_worked_and_not_worked(self):
        w, n = self.b["worked"], self.b["not_worked"]
        self.assertEqual(w[0]["title"], "Three mistakes")
        self.assertEqual(w[0]["label"], "MEASURED")
        self.assertTrue(w[0]["stat"].startswith("2.81"))
        self.assertEqual(w[0]["format"], jload(self.d, "radar_rows.json")["rows"][0]["key"])
        self.assertIn("The same backdrop every time", [x["title"] for x in w])      # the agent's SEEN mechanism
        titles = [x["title"] for x in n]
        self.assertEqual(titles[:2], ["Long story", "Founder diary"])               # measured first, lowest lift first
        self.assertIn("The founder diary fades", titles)                             # the agent's did_not_work
        self.assertIn("Flops", titles)
        flops = [x for x in n if x["title"] == "Flops"][0]
        self.assertEqual(flops["stat"], "5 at 0.5\u00d7 or under")
        self.assertTrue(flops["note"].startswith("5 of 120 scored posts"))
        self.assertEqual([p["title"] for p in self.b["plays"]], ["Run your own three-mistakes series", "Ask for one word"])

    def test_not_worked_never_reads_as_a_success(self):
        """Under not_worked a stat says what is wrong: never a multiple of 1 or more without its word."""
        import re as _re
        d = copy("writing_x")
        run("text_probe.py", d)
        run("build_report.py", d)
        for b in (self.b, jload(d, "brief.json")):
            for x in b["not_worked"]:
                for v in _re.findall(r"(\d+(?:\.\d+)?)\u00d7", x.get("stat") or ""):
                    self.assertLess(float(v), 1.0, x)
        n = dict((x["title"], x) for x in self.b["not_worked"])
        self.assertEqual(n["Long story"]["stat"], "0.55\u00d7 its usual")
        self.assertEqual(n["The founder diary fades"]["stat"], "0.45\u00d7 later vs earlier")
        self.assertEqual(n["Flops"]["stat"], "5 at 0.5\u00d7 or under")

    def test_no_headline_gives_a_measured_answer(self):
        d = build_main()
        f = jload(d, "findings.json")
        f.pop("headline")
        with open(os.path.join(d, "findings.json"), "w") as fh:
            json.dump(f, fh)
        run("build_report.py", d)
        want = "Measured: strongest format Three mistakes (Scale it), 2.81\u00d7 its usual; weakest Long story (Drop), 0.55\u00d7 its usual."
        self.assertEqual(jload(d, "brief.json")["answer"], want)
        self.assertTrue(jload(d, "report_record.json")["report"]["summary"].startswith(want))
        e = copy("one_post")                                                  # no findings.json at all
        run("analyze.py", e)
        run("radar.py", e)
        run("build_report.py", e)
        self.assertTrue(jload(e, "brief.json")["answer"].startswith("Measured: "))
        self.assertTrue(jload(e, "report_record.json")["report"]["summary"].startswith("Measured: "))

    def test_long_findings_are_cut_to_the_limits(self):
        d = build_main()
        f = jload(d, "findings.json")
        long = "word " * 200
        f["headline"]["text"] = long
        f["mechanisms"] = [{"title": long, "text": long, "evidence": "INFERRED", "basis": "<b>bold</b> " + long}] * 8
        f["did_not_work"] = [{"text": long, "evidence": "INFERRED", "basis": long}] * 8
        f["plays"] = [dict(f["plays"][0], title=long, what=long) for _ in range(9)]
        with open(os.path.join(d, "findings.json"), "w") as fh:
            json.dump(f, fh)
        run("build_report.py", d)
        b = jload(d, "brief.json")
        self.assertEqual(brief_problems(b), [])
        self.assertEqual(len(b["plays"]), 5)
        self.assertLessEqual(len(b["worked"]), 6)
        self.assertLessEqual(len(jload(d, "report_record.json")["report"]["summary"]), 600)


class OneFile(unittest.TestCase):
    """report.html is ONE file: the pictures it draws are inside it (smaller copies with ffmpeg), under the caps and
    the budget, nothing else of the run folder is asked for, and the page stays under 3 MB with heavy covers."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg"):
            raise AssertionError("ffmpeg is needed for the one-file report test")
        cls.d = build_main(with_pictures=True)
        cls.code, cls.out = run("build_report.py", cls.d)
        cls.D = page_data(cls.d)
        cls.html = text(cls.d, "report.html")

    def uris(self):
        import re as _re
        return _re.findall(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", self.html)

    def test_pictures_inside_small_and_counted(self):
        import base64 as _b64
        P = self.D["pictures"]
        self.assertEqual(P["shrunk_with"], "ffmpeg")
        self.assertGreaterEqual(P["inside"], 30)               # 4 formats' proof, 14 watched sheets, what did not work
        self.assertEqual(P["left_out"], 0)
        u = self.uris()
        self.assertEqual(len(u), P["inside"])                  # each picture once
        for x in u:
            self.assertTrue(x.startswith("data:image/jpeg;base64,"))
            self.assertLessEqual(len(_b64.b64decode(x.split(",", 1)[1])), 160000)
        drawn = [p for p in self.D["posts"] if p["cover"]]
        self.assertLess(len(drawn), 30)                        # only the drawn covers, not all 142
        for v in self.D["videos"].values():
            self.assertTrue(v["probe"]["sheet_first"].startswith("data:image/jpeg"))

    def test_no_file_of_the_run_folder_is_drawn(self):
        # Every picture source the page draws is inside it (the browser check, verify_report.mjs, opens it alone).
        D = self.D
        for p in D["posts"]:
            self.assertTrue(p["cover"] is None or p["cover"].startswith("data:"))
        for v in D["videos"].values():
            self.assertIsNone(v["probe"]["sheet_shots"])
            self.assertTrue(v["probe"]["sheet_first"] is None or v["probe"]["sheet_first"].startswith("data:"))

    def test_cover_from_the_accounts_picture(self):
        rec = jload(self.d, "report_record.json")
        cv = rec["cover"]
        self.assertEqual((cv["path"], cv["type"], cv["from"]), ("report-cover.jpg", "image/jpeg", "covers/_profile.jpg"))
        self.assertEqual(cv["size"], os.path.getsize(os.path.join(self.d, "report-cover.jpg")))
        self.assertLessEqual(cv["size"], 300000)
        self.assertTrue(cv["name"].endswith("-cover.jpg"))
        self.assertIn("report-cover.jpg", self.out)

    def test_light_page_keeps_no_picture(self):
        light = os.path.join(self.d, "report-light.html")
        self.assertNotIn("data:image/", text(light))
        self.assertLess(os.path.getsize(light), 300000)
        self.assertIn("report-light.html:", self.out)

    def test_size_printed_and_under_3_mb(self):
        size = os.path.getsize(os.path.join(self.d, "report.html"))
        self.assertLess(size, 3000000)
        self.assertIn("report.html: %.2f MB, one file (%d pictures inside" % (size / 1e6, self.D["pictures"]["inside"]), self.out)

    def test_without_ffmpeg_only_small_originals(self):
        env = dict(os.environ, PATH="/nonexistent")
        r = subprocess.run([sys.executable, "-I", os.path.join(SK, "build_report.py"), self.d], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        out = r.stdout.decode()
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        P = page_data(self.d)["pictures"]
        self.assertIsNone(P["shrunk_with"])
        self.assertGreater(P["inside"], 0)                     # the small covers fit as they are
        self.assertGreater(P["left_out"], 0)                   # the big ones are left out, and said so
        self.assertIn("no ffmpeg here to make it smaller", out)
        self.assertLess(os.path.getsize(os.path.join(self.d, "report.html")), 1000000)
        run("build_report.py", self.d)                         # back to the ffmpeg build for the other tests

    def test_budget_leaves_out_and_counts(self):
        sys.path.insert(0, SK)
        sys.dont_write_bytecode = True                         # no __pycache__ in the skill folder
        try:
            import page_kit
            pics = page_kit.Pictures(self.d, budget=500000)
            got = [pics.get("videos/%s/first.jpg" % pid, "sheet") for pid in sorted(self.D["videos"])]
        finally:
            sys.path.remove(SK)
        s = pics.summary()
        self.assertGreater(s["inside"], 0)
        self.assertGreater(s["left_out"], 0)
        self.assertLessEqual(s["bytes"], 500000)
        self.assertEqual(sum(1 for g in got if g), s["inside"])
        self.assertIn("budget", s["left"][0]["why"])


class Probe(unittest.TestCase):
    def test_cuts_words_and_template(self):
        if not shutil.which("ffmpeg"):
            self.fail("ffmpeg is not on PATH: this test cannot run")
        d = copy("main")
        vdir = os.path.join(d, "videos", "p087")
        os.makedirs(vdir)
        # Three shots with grain (so the scene detector sees real pictures): cuts at 2.0 and 4.5 s.
        segs = [("red", 2.0), ("blue", 2.5), ("green", 2.5)]
        parts = []
        for i, (c, s) in enumerate(segs):
            p = os.path.join(TMP, "seg%d.mp4" % i)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=%s:s=360x640:r=30:d=%s,noise=alls=20:allf=t" % (c, s), "-f", "lavfi", "-i",
                            "sine=frequency=300:duration=%s" % s, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", p], check=True)
            parts.append(p)
        lst = os.path.join(TMP, "list.txt")
        with open(lst, "w") as f:
            f.write("".join("file '%s'\n" % p for p in parts))
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", os.path.join(vdir, "video.mp4")], check=True)
        with open(os.path.join(vdir, "video.en.vtt"), "w") as f:
            f.write("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nthree<00:00:00.500><c> mistakes</c><00:00:01.000><c> that</c>"
                    "<00:00:01.500><c> kill</c>\n\n00:00:02.000 --> 00:00:02.010\nthree mistakes that kill\n\n"
                    "00:00:02.010 --> 00:00:04.000\nyour<00:00:02.500><c> launch</c>\n")
        code, out = run("video_probe.py", d, "p087")
        pr = jload(vdir, "probe.json")
        m = pr["measured"]
        self.assertEqual(len(m["cuts"]), 2, m["cuts"])
        self.assertLess(abs(m["cuts"][0] - 2.0), 0.1)
        self.assertLess(abs(m["cuts"][1] - 4.5), 0.1)
        self.assertEqual(m["words"], 6)                                   # the rolling repeat line is dropped
        self.assertEqual(m["first_words_3s"], "three mistakes that kill your launch")
        for k in ("sheet_first", "sheet_shots"):
            self.assertTrue(os.path.exists(os.path.join(d, pr["files"][k])), k)
        self.assertEqual(len(pr["files"]["first_seconds"]), 12)
        n = jload(vdir, "notes.json")
        self.assertIsNone(n["read"])
        code, out = run("validate.py", d, ok=(1,))                        # an undecided template blocks the report
        self.assertIn("videos/p087/notes.json:read", out)


class NoVideo(unittest.TestCase):
    def test_not_read_in_one_go(self):
        d = copy("main")
        run("analyze.py", d)
        code, out = run("video_probe.py", d, "--picks", "--not-read", "no network to download videos")
        picks = jload(d, "analysis.json")["deep_read"]
        ids = picks["outliers"] + picks["ordinary"] + picks["flops"]
        kinds = dict((p["post_id"], p["type"]) for p in jload(d, "analysis.json")["posts"])
        for pid in ids:
            if kinds[pid] != "video":                     # a carousel has no video of its own: never cut, no stub
                self.assertFalse(os.path.exists(os.path.join(d, "videos", pid)), pid)
                continue
            n = jload(d, "videos", pid, "notes.json")
            self.assertEqual((n["read"], n["not_read_reason"]), (False, "no network to download videos"))
        self.assertTrue(any(kinds[i] != "video" for i in ids))   # the fixture's picks hold a carousel
        run("radar.py", d)
        self.assertTrue(all(f["videos_read"] == 0 for f in jload(d, "radar.json")["formats"]))   # stubs measure nothing
        code, out = run("validate.py", d)
        self.assertIn("OK: 0 error(s)", out)


class LedgerAndApp(unittest.TestCase):
    def test_ledger_ceiling(self):
        d = copy("main")
        acc = jload(d, "account.json")
        acc["spend_ceiling_usd"] = 0.01
        with open(os.path.join(d, "account.json"), "w") as f:
            json.dump(acc, f)
        self.assertEqual(run("ledger.py", d, "check", "0.005")[0], 0)
        self.assertEqual(run("ledger.py", d, "add", "--step", "2", "--what", "posts", "--calls", "4", "--unit", "0.002")[0], 0)
        self.assertEqual(run("ledger.py", d, "check", "0.005", ok=(3,))[0], 3)
        self.assertEqual(run("ledger.py", d, "add", "--what", "one more", "--unit", "0.004", ok=(3,))[0], 3)
        code, out = run("validate.py", d, ok=(1,))
        self.assertIn("over the ceiling", out)

    def test_check_app(self):
        class H(http.server.BaseHTTPRequestHandler):
            body = b"[]"

            def do_GET(self):
                self.send_response(200 if self.path == "/api/moodboards" else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(H.body)

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            code, out = run("check_app.py", "--base", "http://127.0.0.1:%d" % port, ok=(0,))
            self.assertTrue(json.loads(out)["running"])
            H.body = b"{}"
            code, out = run("check_app.py", "--base", "http://127.0.0.1:%d" % port, ok=(1,))
            self.assertFalse(json.loads(out)["running"])
        finally:
            srv.shutdown()
            srv.server_close()
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
        s.close()
        code, out = run("check_app.py", "--base", "http://127.0.0.1:%d" % dead, ok=(1,))
        self.assertIn("no answer", json.loads(out)["why"])


if __name__ == "__main__":
    unittest.main()
