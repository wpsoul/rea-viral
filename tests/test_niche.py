#!/usr/bin/env python3
"""REA Viral's other ways in: a niche (many creators, the formats of the niche) and one post, against planted answers.

    python3 tests/test_niche.py [-v]

The fixtures come from make_niche_fixtures.py (answers in KNOWN.json). Each test copies a fixture into a temp folder
and runs the skill's scripts as an agent would (python3 -I). Checked: a small creator's real outlier ranks above a big
creator's ordinary post; too-new posts are never ranked; a creator with too few posts is scored on the weaker basis and
never counts toward a format; the rising format, the one creator's habit (not a format of the niche) and the fading
format come out exactly; the opening that lifts across creators comes out and one creator's habit opening does not; the
watchlist, the planner rows, Watch fed from the watchlist; the validator's niche errors; stale and unlabelled outputs
refused; the post run (ratio, repeats, too new, weaker basis); the account run
still builds with its "Format map". Version 0.4.0: the Niche report and the Post report by those names, their "What
did not work" (the niche's fading format; the post's mirror: under its creator's usual, repeats, words), the planner
rows (one per format of the niche, 3 creators or more; the post's own format keyed by the post) and records, and
"Format Radar" left only where it names the Pulse planner's tab. Not checked here: the pages in a browser
(verify_report.mjs in run_all.sh).
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SK = os.path.join(REPO, "skill", "scripts")
TMP = None
FX = None


def setUpModule():
    global TMP, FX
    TMP = tempfile.mkdtemp(prefix="rea-viral-niche-")
    FX = os.path.join(TMP, "fixtures")
    for script in ("make_fixtures.py", "make_niche_fixtures.py"):   # make_fixtures.py empties --out first
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script), "--out", FX],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if r.returncode != 0:
            raise RuntimeError("%s failed: %s" % (script, r.stderr.decode()))


def tearDownModule():
    if TMP and os.environ.get("REA_KEEP") != "1":
        shutil.rmtree(TMP, ignore_errors=True)


def copy(name, src=None):
    dst = tempfile.mkdtemp(prefix=name + "-", dir=TMP)
    shutil.rmtree(dst)
    shutil.copytree(src or os.path.join(FX, name), dst)
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


def rows(*p):
    with open(os.path.join(*p), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def page_data(d):
    """The data a report page draws, read back out of report.html."""
    html = read_text(os.path.join(d, "report.html"))
    a = html.index('id="rea-data">') + len('id="rea-data">')
    return json.loads(html[a:html.index("</script>", a)].replace("<\\/", "</").replace("<\\!--", "<!--"))


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


class Niche(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = copy("niche_main")
        cls.known = jload(cls.d, "KNOWN.json")
        run("validate.py", cls.d)
        run("radar.py", cls.d)          # runs trends.py's numbers first
        run("text_probe.py", cls.d)
        shutil.copy(os.path.join(cls.d, "findings.example.json"), os.path.join(cls.d, "findings.json"))
        run("build_report.py", cls.d)
        cls.tr = jload(cls.d, "trends.json")
        cls.radar = jload(cls.d, "radar.json")
        cls.wr = jload(cls.d, "writing.json")
        cls.P = dict((p["post_id"], p) for p in cls.tr["posts"])

    def test_small_outlier_ranks_above_big_creators_ordinary_post(self):
        small = self.known["small_outlier"]
        self.assertEqual(self.tr["ranked"][0], small)
        big = [p for p in self.tr["posts"] if p["creator"] == self.known["big_creator"] and p["status"] == "scored"]
        ordinary = [p for p in big if p["format"] is None]
        self.assertTrue(ordinary)
        for p in ordinary:
            self.assertGreater(p["views"], self.P[small]["views"])     # more views ...
            self.assertGreater(p["rank"], self.P[small]["rank"])       # ... and still ranked below
        self.assertGreater(self.P[small]["ratio"], 4.5)
        self.assertGreaterEqual(self.P[small]["baseline_n"], 8)

    def test_deep_read_picks_spread_over_creators(self):
        dr = self.tr["deep_read"]
        self.assertEqual(dr["trends"][0], self.known["small_outlier"])
        per = {}
        for pid in dr["trends"]:
            per[self.P[pid]["creator"]] = per.get(self.P[pid]["creator"], 0) + 1
            self.assertTrue(self.P[pid]["hit"])
        self.assertLessEqual(max(per.values()), 2)
        for k in ("ordinary", "flops"):
            cs = [self.P[pid]["creator"] for pid in dr[k]]
            self.assertEqual(len(cs), len(set(cs)), k)
        self.assertTrue(all(0.75 <= self.P[p]["ratio"] <= 1.33 for p in dr["ordinary"]))
        self.assertTrue(all(self.P[p]["ratio"] < 0.75 for p in dr["flops"]))

    def test_too_new_never_ranked(self):
        for pid in self.known["too_new"]:
            self.assertEqual(self.P[pid]["status"], "too_new")
            self.assertNotIn(pid, self.tr["ranked"])
            self.assertIsNone(self.P[pid]["ratio"])
            self.assertIsNotNone(self.P[pid]["ratio_so_far"])

    def test_weaker_basis_creator(self):
        fresh = [p for p in self.tr["posts"] if p["creator"] == self.known["weaker_basis_creator"]]
        self.assertTrue(fresh)
        for p in fresh:
            self.assertEqual(p["status"], "weaker_basis")
            self.assertNotIn(p["post_id"], self.tr["ranked"])
        self.assertTrue(self.P[self.known["lead"]]["lead"])
        self.assertEqual(self.tr["leads_weaker_basis"][0], self.known["lead"])

    def test_formats_exactly_the_planted_answer(self):
        got = dict((f["id"], f) for f in self.radar["formats"])
        self.assertEqual(self.radar["scope"], "shared")
        for fid, want in self.known["formats"].items():
            for k, v in want.items():
                self.assertEqual(got[fid][k], v, "%s.%s" % (fid, k))
        rise = got["before-after-split"]
        self.assertIn(self.known["lead"], rise["post_ids"])            # the weaker-basis post is in the group ...
        self.assertNotIn(self.known["weaker_basis_creator"], [c["creator"] for c in rise["by_creator"]])  # ... not a creator
        self.assertGreater(rise["usage_direction"], 1.2)
        self.assertEqual(len(set(e["creator"] for e in rise["examples"])), len(rise["examples"]))   # one proof per creator
        self.assertFalse(got["studio-desk-review"]["niche_format"])
        self.assertIn("creator habit", got["studio-desk-review"]["quadrant_name"])

    def test_recipes_are_shared(self):
        text = read_text(os.path.join(self.d, "formats", "before-after-split.md"))
        self.assertIn('"scope": "shared"', text)
        self.assertIn('"voice": "hooks.md"', text)
        self.assertIn("A format of the niche", text)
        habit = read_text(os.path.join(self.d, "formats", "studio-desk-review.md"))
        self.assertIn("NOT a format of the niche", habit)

    def test_hooks_across_creators(self):
        strong = sorted(f["id"] for f in self.wr["features"] if f["claim_ok"])
        self.assertEqual(strong, self.known["lifting_openings"])
        habit = [f for f in self.wr["features"] if f["id"] == self.known["habit_opening"]][0]
        self.assertEqual(habit["verdict"], "few creators")
        self.assertEqual(habit["creators_with"], 1)
        self.assertEqual(habit.get("verdict_before_creators"), "lifts")   # it would have passed on one creator's posts
        self.assertTrue(any({o["a"], o["b"]} == set(self.known["lifting_openings"]) for o in self.wr["overlaps"]))
        best = self.wr["first_lines"]["best"]
        self.assertLessEqual(max(sum(1 for x in best if x["creator"] == c) for c in set(x["creator"] for x in best)), 2)
        hooks = read_text(os.path.join(self.d, "hooks.md"))
        self.assertIn("```json rea-voice", hooks)
        self.assertIn("Hooks of the niche", hooks)

    def test_watchlist(self):
        wl = rows(self.d, "watchlist.csv")
        handles = [r["handle"] for r in wl]
        self.assertIn("tinyreels", handles)
        self.assertNotIn("freshchannel", handles)
        for r in wl:
            self.assertTrue(r["watch_command"].startswith("watch.py add rea-viral youtube "))
            self.assertGreaterEqual(int(r["hits"]), 1)
        tiny = [r for r in wl if r["handle"] == "tinyreels"][0]
        self.assertIn("before-after-split", tiny["formats"])

    def test_planner_rows(self):
        pr = jload(self.d, "planner_rows.json")["rows"]
        self.assertLessEqual(len(pr), 60)
        self.assertTrue(pr[0]["url"].endswith(self.known["small_outlier"]))
        for r in pr:
            self.assertGreaterEqual(len(r.get("author_recent_views") or []), 8)
            self.assertIn("its creator's usual", r["why"])
            self.assertTrue(r["author"].startswith("@"))
        self.assertTrue(any(r.get("pattern") == "Before / after split" for r in pr))

    def test_watch_takes_the_watchlist(self):
        w = tempfile.mkdtemp(prefix="watch-", dir=TMP)
        run("watch.py", "init", w, "--reader-file", "watch/inbox.csv")
        run("watch.py", "add", w, "--from", os.path.join(self.d, "watchlist.csv"))
        listed = rows(w, "watch", "watchlist.csv")
        self.assertEqual(len(listed), len(rows(self.d, "watchlist.csv")))
        self.assertTrue(all(r["source"] == "scout" for r in listed))

    def test_pages_and_niche_md(self):
        md = read_text(os.path.join(self.d, "NICHE.md"))
        self.assertIn("REA Viral, Niche report", md)
        self.assertNotIn("Format Radar", md)
        self.assertIn("Before / after split: Scale it, 5 creators", md)
        self.assertIn("Studio desk review (creator habit)", md)
        html = read_text(os.path.join(self.d, "report.html"))
        self.assertNotIn("<video", html)
        self.assertNotIn("<iframe", html)
        self.assertIn("'Formats of the niche'", html)
        self.assertIn("Niche report", html)
        self.assertNotIn("Format Radar", html)

    def test_what_did_not_work(self):
        D = page_data(self.d)
        nw = D["not_working"]
        self.assertEqual([f["id"] for f in nw["formats"]], ["prompt-reveal"])      # the fading format of the niche
        f = nw["formats"][0]
        self.assertTrue(f["fading"] and not f["under"])
        self.assertEqual(f["creators"], 4)
        self.assertEqual(len(f["lowest"]), 3)
        self.assertNotIn("studio-desk-review", [x["id"] for x in nw["formats"]])  # a creator habit is not the niche's
        self.assertEqual([x["post_id"] for x in nw["flops"]["picks"]], self.tr["deep_read"]["flops"])
        self.assertIn("across 3 creators", nw["words"]["note"])
        md = read_text(os.path.join(self.d, "NICHE.md"))
        self.assertIn("- [MEASURED] What did not work: Prompt reveal (Scale it), 4 creators", md)   # a corner says where it sits
        self.assertIn("| Fading over the window (later half under the earlier) | Prompt reveal |", md)  # the arrow, apart
        self.assertNotIn("Formats to make now (Scale it: many creators, lifting) | Before / after split; Prompt reveal", md)
        self.assertIn("### What did not work", md)
        self.assertIn("Prompt reveals are fading", md)                             # the agent's did_not_work claim
        self.assertIn("'What did not work'", read_text(os.path.join(self.d, "report.html")))

    def test_hand_over_rows_and_record(self):
        rows = jload(self.d, "radar_rows.json")
        self.assertEqual(rows["kind"], "niche")
        self.assertEqual([r["title"] for r in rows["rows"]], ["Before / after split", "Prompt reveal"])   # 3+ creators only
        got = dict((f["id"], f) for f in self.radar["formats"])
        for r, fid in zip(rows["rows"], ("before-after-split", "prompt-reveal")):
            self.assertRegex(r["key"], r"^f_[0-9a-f]{12}$")
            self.assertEqual((r["source"], r["state"], r["platform"]), ("report", "link", "youtube"))
            fm = r["format"]
            self.assertEqual(fm["niche"], "AI video editing tools")
            self.assertEqual(fm["creators"], got[fid]["creators"])
            self.assertGreaterEqual(fm["creators"], 3)
            self.assertEqual(fm["proof"], [e["url"] for e in got[fid]["examples"]])
            self.assertEqual(len(set(fm["proof"])), len(fm["proof"]))
            self.assertEqual(r["url"], fm["proof"][0])
            self.assertIn("followers", r["numbers"])
        self.assertEqual(rows["rows"][0]["format"]["trend"], "rising")
        self.assertEqual(rows["rows"][1]["format"]["trend"], "fading")
        rec = jload(self.d, "report_record.json")
        r = rec["report"]
        self.assertEqual((r["kind"], r["title"]), ("niche", "AI video editing tools"))
        self.assertEqual(r["subject"], {"niche": "AI video editing tools", "network": "youtube"})
        self.assertEqual(r["read"], {"posts": self.tr["counts"]["posts_read"], "creators": self.tr["counts"]["creators"]})
        self.assertLessEqual(len(r["summary"]), 600)
        self.assertIn("What did not work: Four creators use it", r["summary"])
        self.assertEqual(rec["formats"]["rows"], 2)
        b = jload(self.d, "brief.json")
        sys.path.insert(0, SK)
        sys.dont_write_bytecode = True
        try:
            import brief
            self.assertEqual(brief.check(b), [])
        finally:
            sys.path.remove(SK)
        self.assertEqual(rec["report"]["brief"]["answer"], b["answer"])
        self.assertEqual((b["worked"][0]["title"], b["worked"][0]["format"]), ("Before / after split", rows["rows"][0]["key"]))
        self.assertEqual((b["not_worked"][0]["title"], b["not_worked"][0]["format"]), ("Prompt reveal", rows["rows"][1]["key"]))
        self.assertIn("Prompt reveals are fading", [x["title"] for x in b["not_worked"]])
        self.assertNotIn("Prompt reveal", [x["title"] for x in b["worked"]])
        self.assertEqual(dict((x["label"], x["value"]) for x in b["numbers"])["Formats of the niche"], "2")
        self.assertEqual(b["not_worked"][0]["stat"], "fading: 0.23\u00d7 later vs earlier")   # never its 2.48x lift
        self.assertEqual([x["t"] for x in rows["rows"][0]["format"]["beats"]], ["0:00", "0:01.5", "0:12"])
        self.assertIsNone(rec["cover"])                                         # a niche has no picture of its own
        self.assertNotIn("data:image/", read_text(os.path.join(self.d, "report-light.html")))
        self.assertLess(rec["light"]["size"], os.path.getsize(os.path.join(self.d, "report.html")))
        keys = [x["key"] for x in rows["rows"]]
        run("build_report.py", self.d)
        self.assertEqual([x["key"] for x in jload(self.d, "radar_rows.json")["rows"]], keys)   # stable across builds

    def test_pictures_inside_the_niche_page(self):
        D = page_data(self.d)
        shown = [p for p in D["posts"] if p["cover"]]
        self.assertTrue(shown)
        self.assertTrue(all(p["cover"].startswith("data:image/") for p in shown))
        self.assertEqual(D["pictures"]["left_out"], 0)
        self.assertLess(len(shown), 40)                                            # the drawn ones, not all 405

    def test_draft_with_the_niches_hooks_takes_no_creators_sentence(self):
        os.makedirs(os.path.join(self.d, "drafts"), exist_ok=True)
        path = os.path.join(self.d, "drafts", "copy.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\nfor: my channel\nnetwork: youtube\npurpose: followers\nask: follow\nopenings: [opens_question]\n---\n"
                    "Before and after: the edit that saved this clip\nFollow for more.\n")
        code, out = run("draft_check.py", self.d, path, "--json", ok=(1,))
        res = json.loads(out[:out.rindex("}") + 1])
        reuse = [c for c in res["drafts"][0]["checks"] if c["id"] == "reuse"][0]
        self.assertFalse(reuse["ok"])

    def test_ledger_reads_the_niche_ceiling(self):
        self.assertEqual(run("ledger.py", self.d, "check", "0.5", ok=(3,))[0], 3)   # ceiling 0.40
        self.assertEqual(run("ledger.py", self.d, "check", "0.1")[0], 0)


class NicheEdges(unittest.TestCase):
    def test_too_few_creators_calls_no_format(self):
        d = copy("niche_main")
        keep = {"youtube-cutlab", "youtube-tinyreels"}
        for name in os.listdir(os.path.join(d, "accounts")):
            if name not in keep:
                shutil.rmtree(os.path.join(d, "accounts", name))
        os.remove(os.path.join(d, "formats.json"))
        os.remove(os.path.join(d, "found.csv"))
        run("radar.py", d)
        tr, radar = jload(d, "trends.json"), jload(d, "radar.json")
        self.assertEqual(tr["status"], "too_few_creators")
        self.assertEqual(radar["status"], "too_few_creators")
        self.assertEqual(radar["formats"], [])
        self.assertTrue(tr["ranked"])                                  # the posts are still ranked

    def test_validator_niche_errors(self):
        d = copy("niche_main")
        a = os.path.join(d, "accounts", "youtube-cutlab", "posts.csv")
        b = rows(d, "accounts", "youtube-tinyreels", "posts.csv")
        with open(a, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(b[0].keys()))
            w.writerow(b[0])
        fm = jload(d, "formats.json")
        fm["formats"][0]["posts"].append("nope_404")
        write_json(os.path.join(d, "formats.json"), fm)
        with open(os.path.join(d, "found.csv"), "a", encoding="utf-8") as f:
            f.write("x1,https://example.com/x1,youtube,someone,google,ai\n")
        code, out = run("validate.py", d, "--json", ok=(1,))
        rep = json.loads(out[:out.rindex("}") + 1])
        text = json.dumps(rep["errors"])
        self.assertIn("unique across the niche", text)
        self.assertIn("nope_404", text)
        self.assertIn("found_by", text)
        code, out = run("trends.py", d, ok=(1,))
        self.assertIn("fix them first", out)

    def test_stale_and_unlabelled_refused(self):
        d = copy("niche_main")
        run("radar.py", d)
        run("text_probe.py", d)
        run("build_report.py", d)
        p = os.path.join(d, "accounts", "youtube-cutlab", "posts.csv")
        with open(p, "a", encoding="utf-8") as f:
            f.write("cutlab_x,https://www.youtube.com/shorts/cutlab_x,2026-10-20T10:00:00Z,video,20,New one,5000,100,4,,,,,,,,,,,,\n")
        code, out = run("build_report.py", d, ok=(1,))
        self.assertIn("run trends.py again", out)
        run("radar.py", d)
        run("text_probe.py", d)
        write_json(os.path.join(d, "findings.json"), {"schema": "rea-viral/findings@1",
                                                      "formats": [{"text": "It rises.", "evidence": None}]})
        code, out = run("build_report.py", d, ok=(1,))
        self.assertIn("evidence", out)

    def test_an_old_era_does_not_set_the_usual(self):
        """A channel's old posts (months before the window, far smaller) must not lower its usual."""
        d = copy("niche_main")
        run("trends.py", d)
        before = jload(d, "trends.json")
        p = os.path.join(d, "accounts", "youtube-cutlab", "posts.csv")
        rs = rows(d, "accounts", "youtube-cutlab", "posts.csv")
        with open(p, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0].keys()))
            for k in range(30):
                w.writerow(dict(rs[0], post_id="old_%02d" % k, url="https://www.youtube.com/shorts/old_%02d" % k,
                                published_at="2025-06-%02dT10:00:00Z" % (k % 28 + 1), views="200", likes="5",
                                comments="0", cover_file=""))
        run("trends.py", d)
        after = jload(d, "trends.json")
        c0 = [c for c in before["creators"] if c["id"] == "youtube-cutlab"][0]
        c1 = [c for c in after["creators"] if c["id"] == "youtube-cutlab"][0]
        self.assertEqual(c1["usual"], c0["usual"])
        self.assertEqual(c1["older_posts_left_out"], c0["older_posts_left_out"] + 30)
        self.assertEqual(after["ranked"][:5], before["ranked"][:5])

    def test_account_scripts_refuse_a_niche_folder(self):
        d = copy("niche_main")
        code, out = run("analyze.py", d, ok=(2,))
        self.assertIn("niche folder", out)

    def test_covers_sheet_spans_creators(self):
        if not shutil.which("ffmpeg"):
            self.fail("ffmpeg is needed for the covers sheet test")
        d = copy("niche_main")
        run("trends.py", d)
        run("covers_sheet.py", d, "--sort", "ratio")
        sheet = jload(d, "covers_sheet.json")
        self.assertEqual(sheet["tiles"][0]["post_id"], jload(d, "KNOWN.json")["small_outlier"])
        self.assertEqual(len(sheet["tiles"]), jload(d, "trends.json")["counts"]["in_window"])
        self.assertTrue(all(t["cover"] == "read" for t in sheet["tiles"]))
        self.assertGreater(len(set(t["account"] for t in sheet["tiles"])), 5)


class PostRun(unittest.TestCase):
    def test_post_against_its_creators_usual(self):
        d = copy("post_c3")
        k = jload(d, "KNOWN.json")
        run("post_probe.py", d)
        pp = jload(d, "post_probe.json")
        self.assertEqual(pp["status"], "ok")
        self.assertEqual(pp["post"]["post_id"], k["post_id"])
        self.assertTrue(0.85 * k["ratio_about"] <= pp["post"]["ratio"] <= 1.15 * k["ratio_about"], pp["post"]["ratio"])
        self.assertGreaterEqual(pp["post"]["usual_from_posts"], 8)
        self.assertEqual(pp["repeats"]["times"], k["repeats"])
        self.assertEqual(pp["repeats"]["above_usual"], k["above_usual"])
        self.assertEqual(pp["repeats"]["hits"], k["hits_other"])
        self.assertTrue(pp["repeats"]["every_time"])
        self.assertEqual(pp["words"]["status"], "ok")
        self.assertTrue(os.path.exists(os.path.join(d, "formats", "before-after-split.md")))
        run("build_report.py", d)
        md = read_text(os.path.join(d, "POST.md"))
        self.assertIn("its creator's usual", md)
        self.assertIn("repeated 2 more times", md)
        self.assertIn("REA Viral, Post report", md)
        self.assertIn("## What did not work", md)
        nw = page_data(d)["not_working"]
        self.assertIsNone(nw["post_below"])                                         # it beat its usual
        self.assertEqual(nw["repeats"]["below"], [])
        self.assertIn("Every scored repeat", nw["repeats"]["note"])
        rows = jload(d, "radar_rows.json")["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "youtube:" + k["post_id"])                 # the planner's own key for a post
        self.assertEqual(rows[0]["url"], "https://www.youtube.com/shorts/" + k["post_id"])
        self.assertEqual(rows[0]["format"]["proof"][0], rows[0]["url"])
        self.assertEqual(len(rows[0]["format"]["proof"]), 1 + k["above_usual"])
        cv = jload(d, "report_record.json")["cover"]
        self.assertEqual((cv["path"], cv["from"]), ("report-cover.jpg", "covers/%s.png" % k["post_id"]))   # the post's own cover
        self.assertTrue(os.path.exists(os.path.join(d, "report-cover.jpg")))
        rec = jload(d, "report_record.json")["report"]
        self.assertEqual((rec["brief"]["worked"][0]["title"], rec["brief"]["worked"][0]["format"]), ("This post", rows[0]["key"]))
        self.assertEqual(rec["brief"]["not_worked"][0]["title"], "Nothing measured under the usual")
        self.assertEqual(rec["kind"], "post")
        self.assertEqual(rec["subject"]["url"], rows[0]["url"])
        self.assertEqual(rec["read"]["creators"], 1)

    def test_a_post_under_its_creators_usual(self):
        """The mirror on a post that did not work: it sits under its creator's usual, its format is not marked."""
        d = copy("post_c3")
        run("post_probe.py", d)
        low = [q for q in jload(d, "post_probe.json")["creator_posts"] if q["ratio"] is not None and q["ratio"] < 0.9][0]
        write_json(os.path.join(d, "post.json"), {"post_id": low["post_id"], "url": low["url"]})
        os.remove(os.path.join(d, "formats.json"))
        run("post_probe.py", d)
        run("build_report.py", d)
        nw = page_data(d)["not_working"]
        self.assertLess(nw["post_below"]["ratio"], 1)
        self.assertIn("not marked", nw["repeats"]["note"])
        self.assertEqual(jload(d, "radar_rows.json")["rows"], [])
        self.assertIn("not marked", jload(d, "radar_rows.json")["note"])
        self.assertIn("The post itself sits under its creator's usual", read_text(os.path.join(d, "POST.md")))
        b = jload(d, "brief.json")
        self.assertEqual(b["not_worked"][0]["title"], "This post")
        self.assertTrue(b["not_worked"][0]["stat"].startswith("0."))
        self.assertNotIn("This post", [x["title"] for x in b["worked"]])

    def test_too_new_post_is_a_floor(self):
        d = copy("post_c3")
        young = [r["post_id"] for r in rows(d, "posts.csv") if r["published_at"] >= "2026-11-10"][0]
        write_json(os.path.join(d, "post.json"), {"post_id": young, "url": "https://www.youtube.com/shorts/" + young})
        run("post_probe.py", d)
        pp = jload(d, "post_probe.json")
        self.assertEqual(pp["status"], "too_new")
        self.assertIsNone(pp["post"]["ratio"])
        self.assertIsNotNone(pp["post"]["ratio_so_far"])

    def test_few_creator_posts_is_the_weaker_basis(self):
        d = copy("post_c3")
        focus = jload(d, "post.json")["post_id"]
        rs = rows(d, "posts.csv")
        keep = [r for r in rs if r["post_id"] == focus] + [r for r in rs if r["post_id"] != focus][:4]
        with open(os.path.join(d, "posts.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0].keys()))
            w.writeheader()
            w.writerows(keep)
        os.remove(os.path.join(d, "formats.json"))
        run("post_probe.py", d)
        pp = jload(d, "post_probe.json")
        self.assertEqual(pp["status"], "weaker_basis")
        self.assertIsNotNone(pp["post"]["views_per_follower"])
        self.assertIsNone(pp["repeats"]["format"])

    def test_post_json_must_name_a_read_post(self):
        d = copy("post_c3")
        write_json(os.path.join(d, "post.json"), {"post_id": "not_read_1"})
        code, out = run("validate.py", d, ok=(1,))
        self.assertIn("post.json:post_id", out)

class WordsOnly(unittest.TestCase):
    def test_users_own_draft_general_craft(self):
        d = tempfile.mkdtemp(prefix="words-", dir=TMP)
        good = os.path.join(d, "good.md")
        with open(good, "w", encoding="utf-8") as f:
            f.write("---\nnetwork: x\npurpose: replies\nask: reply\n---\nMost editing advice is about tools.\n"
                    "The cut matters more than the plugin.\n\nWhat is the one cut you always make? Reply below.\n")
        code, out = run("draft_check.py", d, good, "--general")
        self.assertIn("general craft only", out)
        long_ = os.path.join(d, "long.md")
        with open(long_, "w", encoding="utf-8") as f:
            f.write("---\nnetwork: x\npurpose: replies\nask: reply\n---\n" + "This is far too long for one post. " * 12 +
                    "\nFollow me and reply below.\n")
        code, out = run("draft_check.py", d, long_, "--general", "--json", ok=(1,))
        res = json.loads(out[:out.rindex("}") + 1])
        failed = sorted(c["id"] for c in res["drafts"][0]["checks"] if not c["ok"])
        self.assertEqual(failed, ["ask", "length"])           # over X's 280, and two asks (follow and reply)
        code, out = run("draft_check.py", d, good, ok=(2,))    # without --general a voice sheet is required
        self.assertIn("--general", out)


class Names(unittest.TestCase):
    def test_format_radar_names_only_the_planners_tab(self):
        """In 0.4.0 the skill makes reports; "Format Radar" is the Pulse planner's tab, never a name of the skill's."""
        root = REPO
        bad = []
        # what people and agents read: the skill and the top-level docs (the tests spell the name to forbid it)
        walk = [(root, [], [f for f in os.listdir(root) if f.endswith(".md")])] + list(os.walk(os.path.join(root, "skill")))
        for dp, dn, fn in walk:
            for name in fn:
                if not name.endswith((".md", ".py", ".mjs", ".html", ".json")):
                    continue
                path = os.path.join(dp, name)
                with open(path, encoding="utf-8") as f:
                    prev = ""
                    for i, line in enumerate(f, 1):
                        near = prev + " " + line      # the line and the one before it (a sentence may wrap)
                        if "Format Radar" in line and not ("Pulse" in near or "planner" in near):
                            bad.append("%s:%d: %s" % (os.path.relpath(path, root), i, line.strip()[:100]))
                        prev = line
        self.assertEqual(bad, [])


class AccountRunStill(unittest.TestCase):
    def test_account_page_calls_it_the_format_map(self):
        d = copy("main")
        run("analyze.py", d)
        run("radar.py", d)
        self.assertEqual(jload(d, "radar.json")["scope"], "account")
        shutil.copy(os.path.join(d, "findings.example.json"), os.path.join(d, "findings.json"))
        run("comment_tactics.py", d)
        run("build_report.py", d)
        html = read_text(os.path.join(d, "report.html"))
        self.assertIn("'Format map'", html)
        self.assertIn("HyperFrames", html)                      # the ways to make, with both Standard ways
        self.assertIn("Format map", read_text(os.path.join(d, "ACCOUNT.md")))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
