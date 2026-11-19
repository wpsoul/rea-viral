#!/usr/bin/env python3
"""How an account writes: text_probe.py and draft_check.py against accounts with known answers.

    python3 tests/test_writing.py [-v]

Checked: the planted answers are found exactly (an X account whose number openers lift 3x and whose links sink;
nothing else lifts or sinks, and lists pull bookmarks without lifting views); a thread account (long threads lift; the
author's later replies sit on the hits and are reported as later replies); an account in another language (every
word-based feature unknown, nothing invented); version-1 files still validate, analyse and probe; the text columns'
mistakes named exactly; the voice sheet kept across runs; draft_check.py passing good drafts and failing one draft for
each reason, including one that reuses a sentence of the reference account; the first words on screen of a
watched video measured beside the captions.
Not checked here: the page in a browser (run_all.sh runs verify_report.mjs on the built pages).
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
    TMP = tempfile.mkdtemp(prefix="rea-viral-writing-")
    FX = os.path.join(TMP, "fixtures")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_fixtures.py"), "--out", FX],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
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


def text_of(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def feats(w):
    return dict((f["id"], f) for f in w["features"] + w["numbers"])


def strong(w):
    return dict((f["id"], f["verdict"]) for f in w["features"] + w["numbers"] if f.get("claim_ok"))


class Planted(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = copy("writing_x")
        run("text_probe.py", cls.d)
        cls.w = jload(cls.d, "writing.json")
        cls.k = jload(cls.d, "KNOWN.json")

    def test_exactly_the_planted_answers(self):
        self.assertEqual(self.w["status"], "ok")
        got = strong(self.w)
        want = dict([(i, "lifts") for i in self.k["lifts"]] + [(i, "sinks") for i in self.k["sinks"]])
        self.assertEqual(got, want)                                   # nothing else lifts or sinks
        F = feats(self.w)
        self.assertTrue(2.6 <= F["opens_number"]["with"]["lift"] <= 3.6, F["opens_number"]["with"]["lift"])
        self.assertTrue(0.3 <= F["has_link"]["with"]["lift"] <= 0.5, F["has_link"]["with"]["lift"])
        self.assertLess(F["opens_number"]["chance"], 0.001)
        for n in self.w["numbers"]:
            self.assertIsNone(n["winning_range"], n["id"])

    def test_the_posts_behind_each_answer(self):
        F = feats(self.w)
        rows = dict((r["post_id"], r) for r in csv.DictReader(open(os.path.join(self.d, "posts_text.csv"), encoding="utf-8")))
        for pid in self.k["number_posts"]:
            self.assertEqual(rows[pid]["opens_number"], "true", pid)
        for pid in self.k["link_posts"]:
            self.assertEqual(rows[pid]["has_link"], "true", pid)
        n_scored = sum(1 for p in self.k["number_posts"] if rows[p]["status"] == "scored")
        self.assertEqual(F["opens_number"]["with"]["posts"], n_scored)

    def test_lists_pull_bookmarks_without_lifting(self):
        F = feats(self.w)
        lst = F["has_list"]
        self.assertEqual(lst["verdict"], "no clear difference")
        self.assertAlmostEqual(lst["signals"]["with"]["save"]["median"], self.k["list_bookmarks_per_like"], delta=0.1)
        self.assertAlmostEqual(lst["signals"]["without"]["save"]["median"], self.k["other_bookmarks_per_like"], delta=0.1)
        self.assertEqual(self.w["signal_names"]["save"], "bookmarks per like")
        self.assertEqual(self.w["signal_names"]["share"], "reposts per like")

    def test_x_posts_settle_in_three_days(self):
        an = jload(self.d, "analysis.json")
        P = dict((p["post_id"], p) for p in an["posts"])
        self.assertEqual(an["settings"]["min_age_days"], 3)
        for pid in self.k["too_new"]:
            self.assertEqual(P[pid]["status"], "too_new")

    def test_first_lines_and_voice_sheet(self):
        best = self.w["first_lines"]["best"]
        self.assertTrue(all("opens_number" in b["openings"] for b in best[:5]))
        worst = self.w["first_lines"]["worst"]
        self.assertTrue(all(b["ratio"] < 0.6 for b in worst[:5]))
        v = open(os.path.join(self.d, "voice.md"), encoding="utf-8").read()
        self.assertIn("```json rea-voice", v)
        block = json.loads(v.split("```json rea-voice\n", 1)[1].split("\n```", 1)[0])
        self.assertIn("opens_number", block["rules"]["openings"])
        self.assertEqual(block["rules"]["avoid"], ["has_link"])
        self.assertEqual(block["rules"]["length_limit"], 280)


class Threads(unittest.TestCase):
    def test_long_threads_and_later_replies(self):
        d = copy("writing_thread")
        run("text_probe.py", d)
        w = jload(d, "writing.json")
        F = feats(w)
        parts = F["parts"]
        self.assertTrue(parts["claim_ok"], parts["verdict"])
        self.assertGreaterEqual(parts["winning_range"]["range"][0], jload(d, "KNOWN.json")["parts_winning_from"])
        self.assertEqual(F["has_later_reply"]["verdict"], "lifts")
        self.assertEqual(F["ask_in_later_reply"]["verdict"], "lifts")
        pairs = [(o["a"], o["b"]) for o in w["overlaps"]]
        self.assertIn(("ask_in_later_reply", "has_later_reply"), pairs)          # they travel together
        self.assertIn("cannot be why", w["asks"]["later_replies"]["note"])
        rows = list(csv.DictReader(open(os.path.join(d, "posts_text.csv"), encoding="utf-8")))
        ask_rows = [r for r in rows if r["ask_follow"] == "true" and r["parts"]]
        self.assertTrue(ask_rows)
        self.assertTrue(all(r["ask_where"] == "end" for r in ask_rows))
        an = jload(d, "analysis.json")
        types = dict((b["bucket"], b) for b in an["by_type"])
        self.assertIn("thread", types)


class OtherLanguage(unittest.TestCase):
    def test_nothing_invented(self):
        d = copy("writing_es")
        run("text_probe.py", d)
        w = jload(d, "writing.json")
        self.assertNotIn("en", w["language"]["posts_by_language"])
        self.assertEqual(w["language"]["posts_covered"], 0)
        self.assertIn("cover English (en)", w["language"]["note"])
        for f in w["features"]:
            if f["needs_words"] is True:
                self.assertEqual(f["verdict"], "unknown", f["id"])
                self.assertEqual(f["usage"]["known"], 0, f["id"])
        self.assertNotIn("opens_negation", strong(w))           # "No ..." lifts 3x, but the word lists cannot say so
        rows = list(csv.DictReader(open(os.path.join(d, "posts_text.csv"), encoding="utf-8")))
        self.assertTrue(all(r["opens_negation"] == "" and r["has_ask"] == "" for r in rows))
        tagged = [r for r in rows if r["language"] == "es"]
        self.assertTrue(tagged)                                  # the network's own tag is kept, and still not covered


class VersionOne(unittest.TestCase):
    def test_v1_runs_unchanged(self):
        d = copy("main")
        code, out = run("validate.py", d)
        self.assertIn("OK: 0 error(s)", out)
        run("text_probe.py", d)
        self.assertEqual(jload(d, "writing.json")["status"], "ok")
        self.assertEqual(jload(d, "analysis.json")["settings"]["min_age_days"], 7)   # TikTok keeps its 7 days

    def test_first_line_on_screen(self):
        """The first words on screen, written down in a watched video's notes, are measured beside the captions."""
        d = copy("main")
        run("analyze.py", d)
        pid = jload(d, "analysis.json")["outliers"][0]
        os.makedirs(os.path.join(d, "videos", pid))
        with open(os.path.join(d, "videos", pid, "notes.json"), "w", encoding="utf-8") as f:
            json.dump({"post_id": pid, "read": True, "not_read_reason": None,
                       "seen": {"hook": {"text": "a big number on screen", "at": 0.0}, "first_frame": "the number",
                                "text_on_screen": "white chips", "sound": "voice", "turn": {"text": "the first mistake", "at": 2.0},
                                "ask": {"text": "none", "at": None}, "first_line": "3 words you will never forget"},
                       "beats": [], "cover": "the number"}, f)
        run("radar.py", d)
        run("comment_tactics.py", d)
        run("text_probe.py", d)
        on = jload(d, "writing.json")["on_screen"]
        self.assertEqual([(x["post_id"], x["evidence"]) for x in on], [(pid, "SEEN")])
        self.assertIn("opens_number", on[0]["openings"])
        run("build_report.py", d)
        self.assertIn("3 words you will never forget", text_of(d, "report.html"))

    def test_text_columns_named_exactly(self):
        d = copy("bad_text_rows")
        code, out = run("validate.py", d, "--json", ok=(1,))
        rep = json.loads(out[:out.rindex("}") + 1])
        k = jload(d, "KNOWN.json")
        self.assertEqual(sorted(e["where"] for e in rep["errors"]), sorted(k["errors"]))
        warns = [w["where"] for w in rep["warnings"]]
        for w in k["warnings_include"]:
            self.assertIn(w, warns)


class VoiceSheet(unittest.TestCase):
    def test_agent_text_and_rules_kept(self):
        d = copy("writing_x")
        run("text_probe.py", d)
        p = os.path.join(d, "voice.md")
        text = open(p, encoding="utf-8").read()
        block = json.loads(text.split("```json rea-voice\n", 1)[1].split("\n```", 1)[0])
        block["rules"]["max_paragraph_lines"] = 2
        text = text.split("```json rea-voice\n", 1)[0] + "```json rea-voice\n" + json.dumps(block, indent=2) + "\n```" + \
            text.split("```json rea-voice\n", 1)[1].split("\n```", 1)[1]
        text = text.replace("## Its shape\n", "## Its shape\n\nShort lines, one idea a post (SEEN: w030).\n")
        open(p, "w", encoding="utf-8").write(text)
        run("text_probe.py", d)
        again = open(p, encoding="utf-8").read()
        self.assertIn("Short lines, one idea a post (SEEN: w030).", again)
        b2 = json.loads(again.split("```json rea-voice\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(b2["rules"]["max_paragraph_lines"], 2)          # the agent's rule stays
        self.assertIn("opens_number", b2["measured"]["lifts"])          # the measured part is the script's


GOOD = """---
for: a solo founder who sells a design tool
network: x
purpose: followers
ask: follow
openings: [opens_number]
---
7 more pricing notes I wish someone told me in year one.

Charge for the outcome, not the hours.
Raise prices for new buyers first.

A price is a promise, so make it one you can keep.

If this helped, follow along for the next batch.
"""


class DraftCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = copy("writing_x")
        run("text_probe.py", cls.d)
        os.makedirs(os.path.join(cls.d, "drafts"))
        v = open(os.path.join(cls.d, "voice.md"), encoding="utf-8").read()
        cls.rules = json.loads(v.split("```json rea-voice\n", 1)[1].split("\n```", 1)[0])["rules"]

    def draft(self, name, text):
        p = os.path.join(self.d, "drafts", name + ".md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def result(self, text, name):
        p = self.draft(name, text)
        code, out = run("draft_check.py", self.d, p, "--json", ok=(0, 1))
        r = json.loads(out)["drafts"][0]
        return code, dict((c["id"], c) for c in r["checks"])

    def fails_only(self, text, name, which):
        code, c = self.result(text, name)
        self.assertEqual(code, 1)
        bad = sorted(k for k, v in c.items() if not v["ok"])
        self.assertEqual(bad, sorted(which), json.dumps(c, indent=1))
        return c

    def test_good_drafts_pass(self):
        lo, hi = self.rules["first_line_chars"]
        self.assertTrue(lo <= len("7 more pricing notes I wish someone told me in year one.") <= hi)
        code, c = self.result(GOOD, "good1")
        self.assertEqual(code, 0, json.dumps(c, indent=1))
        thread = GOOD.replace("A price is a promise, so make it one you can keep.", "---\nA price is a promise you keep.")
        code, c = self.result(thread, "good2")
        self.assertEqual(code, 0, json.dumps(c, indent=1))
        in_reply = GOOD.replace("ask: follow", "ask: follow\nask_in: reply").replace(
            "If this helped, follow along for the next batch.", "Price is a message to the buyer.") + \
            "\n=== reply ===\nIf this helped, follow along for the next batch.\n"
        code, c = self.result(in_reply, "good3")
        self.assertEqual(code, 0, json.dumps(c, indent=1))
        code, out = run("draft_check.py", self.d, "--all", ok=(0, 1))
        self.assertIn("drafts passed", out)

    def test_ask_that_does_not_fit(self):
        self.fails_only(GOOD.replace("purpose: followers", "purpose: sales"), "front", ["front"])

    def test_too_long_for_x_unless_long_posts(self):
        long_ = GOOD.replace("Raise prices for new buyers first.", "This is the part most people skip, so do it first. " * 6)
        self.fails_only(long_, "long", ["length", "shape"])           # past X's 280, and past the account's own range
        code, c = self.result(long_.replace("openings:", "long_posts: true\nopenings:"), "long_ok")
        self.assertTrue(c["length"]["ok"])

    def test_length_outside_the_accounts_range(self):
        self.fails_only(GOOD.replace("A price is a promise, so make it one you can keep.\n\n", ""), "short", ["shape"])

    def test_first_line_out_of_range(self):
        self.fails_only(GOOD.replace("7 more pricing notes I wish someone told me in year one.", "7 notes."),
                        "short_first", ["first_line"])

    def test_paragraph_too_long(self):
        many = "\n".join("Line %s." % w for w in ("one", "two", "three", "four", "five", "six"))
        self.fails_only(GOOD.replace("Charge for the outcome, not the hours.\nRaise prices for new buyers first.", many),
                        "para", ["paragraphs"])

    def test_opening_named_but_not_there(self):
        self.fails_only(GOOD.replace("7 more pricing notes I wish someone told me in year one.",
                                     "More pricing notes I wish someone had told me in year one."), "noopen", ["openings"])
        self.fails_only(GOOD.replace("[opens_number]", "[opens_quote]").replace(
            "7 more pricing notes", "\"7 more pricing notes"), "notvoice", ["openings"])

    def test_ask_missing_or_two_asks(self):
        self.fails_only(GOOD.replace("If this helped, follow along for the next batch.", "That is the whole list."),
                        "noask", ["ask"])
        self.fails_only(GOOD.replace("If this helped, follow along for the next batch.",
                                     "If this helped, follow along for the next batch. Bookmark it for later."),
                        "twoasks", ["ask"])

    def test_what_sinks_on_this_account(self):
        self.fails_only(GOOD.replace("Raise prices for new buyers first.", "Raise prices for new buyers first: https://example.com/p"),
                        "link", ["avoid"])

    def test_reused_sentence_of_the_reference_account(self):
        rows = list(csv.DictReader(open(os.path.join(self.d, "posts.csv"), encoding="utf-8")))
        sentence = "Nobody remembers the post that played it safe."
        self.assertTrue(any(sentence in r["caption"] for r in rows))
        c = self.fails_only(GOOD.replace("Charge for the outcome, not the hours.", sentence), "reuse", ["reuse"])
        self.assertIn("nobody remembers the post that played it safe", c["reuse"]["message"])

    def test_machine_marks(self):
        c = self.fails_only(GOOD.replace("Charge for the outcome, not the hours.",
                                         "Pricing is a game-changer \u2014 let's delve into it."), "machine", ["machine"])
        for m in ("game-changer", "delve", "em dash"):
            self.assertIn(m, c["machine"]["message"])

    def test_machine_mark_allowed_when_it_is_the_accounts_voice(self):
        d = copy("writing_x")
        path = os.path.join(d, "posts.csv")
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        for r in rows[:30]:
            r["caption"] = r["caption"].replace("\n\n", " \u2014 ", 1)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        run("text_probe.py", d)
        p = os.path.join(d, "dash.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(GOOD.replace("Charge for the outcome, not the hours.", "Charge for the outcome \u2014 not the hours."))
        code, out = run("draft_check.py", d, p, "--json", ok=(0, 1))
        c = dict((x["id"], x) for x in json.loads(out)["drafts"][0]["checks"])
        self.assertTrue(c["machine"]["ok"], c["machine"])
        self.assertIn("account's own voice", c["machine"]["message"])

    def test_language_not_covered(self):
        es = GOOD.replace("7 more pricing notes I wish someone told me in year one.",
                          "7 notas de precios que me hubiera gustado leer antes.").replace(
            "Charge for the outcome, not the hours.\nRaise prices for new buyers first.",
            "Cobra por el resultado y no por las horas.\nSube los precios primero para los nuevos.").replace(
            "If this helped, follow along for the next batch.", "Sigueme para la siguiente tanda.")
        code, c = self.result(es, "es")
        self.assertEqual(code, 1)
        self.assertFalse(c["language"]["ok"])

    def test_no_voice_sheet_refuses(self):
        d = copy("writing_x")
        p = os.path.join(d, "x.md")
        open(p, "w").write(GOOD)
        code, out = run("draft_check.py", d, p, ok=(2,))
        self.assertIn("run text_probe.py", out)


if __name__ == "__main__":
    unittest.main()
