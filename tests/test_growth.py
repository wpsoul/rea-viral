#!/usr/bin/env python3
"""Growth mode (0.5.0): growth.py, its files, its checks and its block in the Account report, on a made-up X account
with its answers planted.

    python3 tests/test_growth.py [-v]
    python3 tests/test_growth.py --make DIR     (only write the built account to DIR/growth_x, for run_all.sh)

The made-up account @fixture_grow (X, 300 followers, read 2026-11-20 12:00 UTC):
- 20 meme clips before the window (200 views each), then 6 slow weeks (2, 2, 1, 0, 1, 0 posts), then 8 posts a week
  from Monday 2026-10-19: the change point, 0.5 -> 8.0 posts a week;
- 4 crowd calls (a named crowd or "I'll reply to everyone", with an ask): 9,000 / 3,000 / 1,500 views, and one under
  3 days old; comparisons that ask "Which one wins for you?" (questions, not crowd calls);
- a short film whose first self-reply tags the tool and 4 creators: 3 of the 5 tagged repost it, a 250K account
  reposts it, and the account reposts itself (left out and counted);
- a quote of a big post (5M views) 40 minutes after it, and a quote of a small one 300 minutes after;
- one meme with 400,000 views (1000x the followers or more): left out of every sum;
- 20 replies to others in 60 minutes (one window: a sample), 5 to big accounts, 5 in its own crowd call's thread;
- the meme clips: under the usual, no tags, no ask: what the weakest format lacks.
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
SK = os.path.join(REPO, "skill", "scripts")
sys.dont_write_bytecode = True
sys.path.insert(0, SK)
import growth  # noqa: E402

READ_AT = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)
HANDLE = "fixture_grow"
HEADER = ["post_id", "url", "published_at", "type", "duration_s", "caption", "views", "likes", "comments", "shares",
          "saves", "cover_url", "cover_file", "video_file", "transcript_file", "sound", "is_pinned", "is_paid",
          "collaborators", "read_at", "source", "reposts", "quotes", "bookmarks", "lang", "parts", "author_replies",
          "quoted_url", "own_media"]
MEMES = ["when the tests pass on the first try", "me explaining my side project to my cat", "prod at 5pm on a friday",
         "the AI agent after one small change", "senior dev reviewing my PR", "my laptop fan during a build"]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def at(day_, hour=14, minute=0):
    return dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=day_ - 1, hours=hour, minutes=minute)


def d(month, day_, hour=14, minute=0):
    return dt.datetime(2026, month, day_, hour, minute, tzinfo=dt.timezone.utc)


def row(pid, t, kind, views, caption, comments=3, reposts=0, bookmarks=1, own_media="video", typ="video",
        author_replies=None, quoted_url=""):
    return {"post_id": pid, "url": "https://x.com/%s/status/%s" % (HANDLE, pid), "published_at": iso(t), "type": typ,
            "duration_s": 8 if own_media == "video" else "", "caption": caption, "views": views,
            "likes": max(1, views // 40), "comments": comments, "reposts": reposts, "quotes": 0, "bookmarks": bookmarks,
            "lang": "en", "author_replies": json.dumps(author_replies or []), "quoted_url": quoted_url,
            "own_media": own_media, "read_at": iso(READ_AT), "source": "made up", "_kind": kind}


def make(out):
    """Write the made-up account to out (a new folder) and return its planted answers."""
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    rows = []
    n = [0]

    def pid():
        n[0] += 1
        return "9%05d" % n[0]
    # 20 meme clips before the window: they only feed the first baselines
    for i in range(20):
        rows.append(row(pid(), d(8, 1 + i, 10), "meme", 200, MEMES[i % len(MEMES)] + " 💀", comments=1))
    # the slow weeks (window from Monday 2026-09-07): 2, 2, 1, 0, 1, 0 posts, all meme clips at 150 views
    for t in (d(9, 8), d(9, 10), d(9, 15), d(9, 17), d(9, 23), d(10, 7)):
        rows.append(row(pid(), t, "meme", 150, MEMES[len(rows) % len(MEMES)], comments=1))
    ans = {}
    # from Monday 2026-10-19: 8 posts a week for 4 weeks, then 5 in the week still running
    week = [
        ("crowd", 0), ("meme", 0), ("compare", 1), ("film", 2), ("meme", 3), ("news", 4), ("compare", 5), ("meme", 6)]
    crowd_texts = [
        ("AI video creators, what's your go-to right now?\n\nSeedance, Kling or something else?\n\nDrop yours + what you're "
         "building. I'll reply to everyone, let's connect 🤝", 9000, 60),
        ("Indie hackers: what are you shipping this week?\n\nI'll reply to everyone", 3000, 25),
        ("If you're into AI video, let's connect\n\nDrop a comment and follow each other", 1500, 18)]
    ci = 0
    meme_i = 0
    for w in range(4):
        monday = d(10, 19, 0) + dt.timedelta(days=7 * w)
        for k, (kind, dd) in enumerate(week):
            t = monday + dt.timedelta(days=dd, hours=9 + k)
            p = pid()
            if kind == "crowd":
                if ci < len(crowd_texts):
                    txt, v, c = crowd_texts[ci]
                    rows.append(row(p, t, "crowd", v, txt, comments=c, reposts=2, bookmarks=20, own_media="none", typ="text"))
                    ans.setdefault("crowd", []).append(p)
                    ci += 1
                else:
                    rows.append(row(p, t, "news", 300, "OpenAI shipped a new agent API today. The real story is the pricing.",
                                    own_media="none", typ="text"))
            elif kind == "meme":
                meme_i += 1
                if w == 0 and k == 1:
                    rows.append(row(p, t, "meme", 400000, "the art of rephrasing 💀", comments=40))
                    ans["suspect"] = p
                else:
                    rows.append(row(p, t, "meme", 150, MEMES[meme_i % len(MEMES)], comments=1))
            elif kind == "compare":
                rows.append(row(p, t, "compare", 400, "Kling 4 vs Seedance 2\n\nSame prompt, 5 s each.\n\nWhich one wins for you?",
                                comments=6, reposts=1, author_replies=[{"text": "Prompt: a paper boat in the rain. Made with @toolai", "minutes_after": 1}]))
            elif kind == "film":
                if w == 0:
                    rows.append(row(p, t, "film", 900, "we made a short film about robots learning to dance 🎬", comments=20,
                                    reposts=6, author_replies=[
                                        {"text": "made with @toolai\n\nshoutout to @ann_c @bob_c @cat_c @dan_c for starring in this one", "minutes_after": 1},
                                        {"text": "and thanks to @late_c", "minutes_after": 300}]))
                    ans["film"] = p
                elif w == 1:
                    rows.append(row(p, t, "quote", 4000, "Telegram group not found 💀", comments=6, reposts=2, own_media="video",
                                    typ="quote", quoted_url="https://x.com/bigname/status/777"))
                    ans["quote_big"] = p
                elif w == 2:
                    rows.append(row(p, t, "quote", 300, "agree with this take", comments=2, own_media="none", typ="quote",
                                    quoted_url="https://x.com/smallname/status/778"))
                    ans["quote_small"] = p
                else:
                    rows.append(row(p, t, "film", 700, "a 30 second film about a lighthouse keeper", comments=9, reposts=3,
                                    author_replies=[{"text": "made with @toolai, inspired by @studio_x", "minutes_after": 2}]))
            else:
                rows.append(row(p, t, "news", 300, "Anthropic's new model card says more than the launch post. Read section 4.",
                                own_media="none", typ="text"))
    # the week still running: Mon 16 to Thu 19 (the crowd call on the 19th is under 3 days old at read_at)
    for t, kind in ((d(11, 16, 9), "compare"), (d(11, 17, 9), "meme"), (d(11, 18, 9), "news"), (d(11, 18, 15), "compare"),
                    (d(11, 19, 9), "crowd")):
        p = pid()
        if kind == "crowd":
            rows.append(row(p, t, "crowd", 2500, "AI builders, founders and people deep in the tools: what are you shipping?\n\n"
                                                 "I'll reply to everyone 🤝", comments=30, reposts=1, own_media="none", typ="text"))
            ans["crowd_new"] = p
            ans.setdefault("crowd", []).append(p)
        elif kind == "meme":
            rows.append(row(p, t, "meme", 150, MEMES[0], comments=1))
        elif kind == "compare":
            rows.append(row(p, t, "compare", 400, "Veo 4 vs Kling 4\n\nWhich one is worth your credits?", comments=5))
        else:
            rows.append(row(p, t, "news", 300, "Google's agent kit is out. The docs are better than the demo.", own_media="none", typ="text"))
    with open(os.path.join(out, "posts.csv"), "w", encoding="utf-8", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        w_.writeheader()
        for r in rows:
            w_.writerow(r)
    acc = {"schema": "rea-viral/account@2", "network": "x", "handle": HANDLE, "name": "Fixture Grow",
           "url": "https://x.com/" + HANDLE, "bio": "AI video, made up", "followers": 300, "followers_exact": True,
           "posts_total": len(rows), "private": False, "read_at": iso(READ_AT), "window": {"from": "2026-09-07", "to": "2026-11-20"},
           "sources": [{"what": "made up", "via": "test_growth.py", "cost_usd": 0}],
           "comments_read": {"posts": 1, "per_post": 40, "replies_read": True},
           "growth_read": {"reposters": {"posts": [ans["film"], ans["crowd"][0], ans["quote_big"]], "pages_per_post": 1},
                           "replies_out": {"windows": 1, "pages": 1}},
           "spend_ceiling_usd": 1}
    with open(os.path.join(out, "account.json"), "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2)
    film, crowd1, qbig = ans["film"], ans["crowd"][0], ans["quote_big"]
    rep = [(film, "ann_c", 2000, "AI artist @nabu team"), (film, "bob_c", 3000, "AI creator"), (film, "cat_c", 1500, "AI films"),
           (film, "stranger1", 500, ""), (film, "bigacct", 250000, "Head of creators @studio_x"), (film, HANDLE, 300, "AI video, made up"),
           (crowd1, "r_one", 120, ""), (crowd1, "ann_c", 2000, "AI artist @nabu team")]
    with open(os.path.join(out, "reposters.csv"), "w", encoding="utf-8", newline="") as f:
        w_ = csv.writer(f)
        w_.writerow(["post_id", "handle", "name", "followers", "bio", "kind", "at", "source"])
        for r in rep:
            w_.writerow([r[0], r[1], r[1].upper(), r[2], r[3], "repost", "", "made up"])
    # 20 replies to others in 60 minutes on Nov 20, 09:00 to 10:00
    targets = [("megacorp", 500000), ("ailab", 1200000), ("bigdev", 40000), ("toolai", 90000), ("newsdesk", 15000)] + \
              [("small%d" % i, 100 + 50 * i) for i in range(10)] + [("ann_c", 2000), ("fan1", 80), ("fan2", 60), ("fan3", 40), ("fan4", 20)]
    crowd_new = ans["crowd_new"]
    with open(os.path.join(out, "replies_out.csv"), "w", encoding="utf-8", newline="") as f:
        w_ = csv.writer(f)
        w_.writerow(["reply_id", "url", "at", "to_handle", "to_followers", "to_bio", "conversation_id", "text", "views", "likes", "source"])
        for i, (h, fo) in enumerate(targets):
            conv = crowd_new if i >= 15 else "50%04d" % i
            t = d(11, 20, 9) + dt.timedelta(minutes=round(i * 60 / 19.0))
            w_.writerow(["8%05d" % i, "https://x.com/%s/status/8%05d" % (HANDLE, i), iso(t), h, fo, "", conv,
                         "@%s great point, and congrats" % h, 10 + i, 1, "made up"])
    with open(os.path.join(out, "originals.csv"), "w", encoding="utf-8", newline="") as f:
        w_ = csv.writer(f)
        w_.writerow(["post_id", "original_id", "original_url", "original_handle", "original_followers", "original_at", "original_views", "source"])
        tq = next(r for r in rows if r["post_id"] == qbig)["published_at"]
        tq = dt.datetime.strptime(tq, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        w_.writerow([qbig, "777", "https://x.com/bigname/status/777", "bigname", 2000000, iso(tq - dt.timedelta(minutes=40)), 5000000, "made up"])
        ts = next(r for r in rows if r["post_id"] == ans["quote_small"])["published_at"]
        ts = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        w_.writerow([ans["quote_small"], "778", "https://x.com/smallname/status/778", "smallname", 1500, iso(ts - dt.timedelta(minutes=300)), 2000, "made up"])
        w_.writerow(["800001", "779", "https://x.com/ailab/status/779", "ailab", 1200000, iso(d(11, 20, 9, 3) - dt.timedelta(minutes=12)), 300000, "made up"])
    # one page of replies under the first crowd call: 6 from others, 4 by the author
    with open(os.path.join(out, "comments.csv"), "w", encoding="utf-8", newline="") as f:
        w_ = csv.writer(f)
        w_.writerow(["post_id", "comment_id", "parent_id", "author", "author_is_creator", "text", "likes", "created_at", "created_at_exact", "is_pinned", "is_hearted", "reply_count"])
        t0 = dt.datetime.strptime(next(r for r in rows if r["post_id"] == crowd1)["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        for i in range(6):
            w_.writerow([crowd1, "c%d" % i, "", "user%d" % i, "false", "@%s Seedance for me, building a music video" % HANDLE, 2, iso(t0 + dt.timedelta(minutes=5 + i)), "true", "", "", 1])
        for i in range(4):
            w_.writerow([crowd1, "a%d" % i, "c%d" % i, HANDLE, "true", "@user%d love it, let's connect" % i, 1, iso(t0 + dt.timedelta(minutes=20 + i)), "true", "", "", 0])
    kinds = {}
    for r in rows:
        kinds.setdefault(r["_kind"], []).append(r["post_id"])
    fm = {"schema": "rea-viral/formats@1", "formats": [], "series": []}
    names = {"meme": "Meme clip", "crowd": "Crowd call", "compare": "Model vs model", "film": "Credited short film",
             "quote": "Quote take", "news": "AI news take"}
    for k, ids in kinds.items():
        fm["formats"].append({"id": k + "-fmt", "name": names[k], "hook": "made up", "structure": "made up", "look": "made up",
                              "length": "short", "effort": "low", "basis": "made up", "posts": ids, "examples": ids[-2:]})
    with open(os.path.join(out, "formats.json"), "w", encoding="utf-8") as f:
        json.dump(fm, f, indent=2)
    ans["rows"] = rows
    ans["memes"] = kinds["meme"]
    return ans


FINDINGS_GROWTH = {
    "why_it_grows": [
        {"title": "Volume", "text": "From {cadence.change_point.at:date} posting went from {cadence.change_point.before} to {cadence.change_point.after} a week, and {concentration.top_slice.n} posts hold {concentration.top_slice.share:pct} of the views since.",
         "reply": "Volume: from {cadence.change_point.at:date} you went from {cadence.change_point.before} to {cadence.change_point.after} posts a week; {concentration.top_slice.n} posts hold {concentration.top_slice.share:pct} of the views since then.",
         "evidence": "MEASURED", "from": "growth.json#cadence.change_point", "posts": [], "quote": []},
        {"title": "Crowd calls", "text": "The top crowd call got {crowd_calls.top.views} views and {crowd_calls.top.replies} replies.",
         "reply": "Open questions to a named crowd + \"I'll reply to everyone\": your top one got {crowd_calls.top.views} views and {crowd_calls.top.replies} replies.",
         "evidence": "MEASURED", "from": "growth.json#crowd_calls.top", "posts": [], "quote": ["I'll reply to everyone"]},
        {"title": "Credits", "text": "{repost_graph.best_tagged.reposted} of {repost_graph.best_tagged.tagged} tagged accounts reposted the film; a {repost_graph.biggest.followers} account did too.",
         "reply": "Tagging the cast and the tool in the first reply: {repost_graph.best_tagged.reposted} of {repost_graph.best_tagged.tagged} tagged reposted, and a {repost_graph.biggest.followers} account reposted it too.",
         "evidence": "MEASURED", "from": "growth.json#repost_graph.best_tagged", "posts": []},
        {"title": "Speed", "text": "The quote of a big post came {speed.top.minutes} minutes after it and got {speed.top.own_views} views; {replies_out.count} replies to others in {replies_out.span_minutes} minutes.",
         "reply": "Living in the replies: {replies_out.count} replies in {replies_out.span_minutes} min; a quote {speed.top.minutes} min after a {speed.top.original_views}-view post got {speed.top.own_views} views.",
         "evidence": "MEASURED", "from": "growth.json#speed.top", "posts": []}],
    "doesnt_move": [
        {"title": "Meme clips", "text": "Meme clips: {flops.format.posts} posts, {flops.format.hits} hits, {flops.format.lift:x} the usual.",
         "reply": "Doesn't move: one-line meme clips: {flops.format.posts} posts, {flops.format.hits} hits, {flops.format.lift:x} your usual. No tags, no question.",
         "evidence": "MEASURED", "from": "growth.json#flops.format", "posts": []}],
    "copy_this": ["Post one repeatable container daily.", "Ask a named crowd one open question a week and reply to everyone.",
                  "Credit the people and the tool in the first reply."],
}


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


def jsave(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def findings(ans):
    g = json.loads(json.dumps(FINDINGS_GROWTH))
    g["why_it_grows"][0]["posts"] = [ans["crowd"][0]]
    g["why_it_grows"][1]["posts"] = [ans["crowd"][0]]
    g["why_it_grows"][2]["posts"] = [ans["film"]]
    g["why_it_grows"][3]["posts"] = [ans["quote_big"]]
    g["doesnt_move"][0]["posts"] = [ans["memes"][-1]]
    return {"schema": "rea-viral/findings@1",
            "headline": {"text": "It grows by volume and crowd calls.", "evidence": "INFERRED", "basis": "growth.json"},
            "growth": g}


def build(out, with_findings=True):
    ans = make(out)
    for s in ("validate.py", "analyze.py", "radar.py", "growth.py"):
        run(s, out)
    if with_findings:
        jsave(os.path.join(out, "findings.json"), findings(ans))
        run("growth.py", out)
    return ans


TMP = None


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp(prefix="rea-viral-growth-")


def tearDownModule():
    if TMP and os.environ.get("REA_KEEP") != "1":
        shutil.rmtree(TMP, ignore_errors=True)


class Detection(unittest.TestCase):
    """What growth.py reads in a post's words: regular expressions, like text_probe.py."""

    W = growth.load_words()

    def f(self, caption, replies=None, typ="text"):
        return growth.features({"caption": caption, "author_replies": replies or [], "type": typ}, HANDLE, self.W)

    def test_crowd_calls(self):
        for t in ("AI video creators, what’s your go-to right now?\n\nDrop your favorite. I’ll reply to everyone, let’s connect 🤝",
                  "AI builders, founders and people deep in the weeds: what are you focused on right now?\n\nI’ll reply to everyone.",
                  "If you're into AI, let's connect\n\nDrop a comment, find some cool people in the replies",
                  "Real talk: which AI video tool is giving you the most consistent results right now?\n\nTell me yours. I'll reply to everyone 🤝"):
            x = self.f(t)
            self.assertTrue(x["crowd_call"], t)
            self.assertFalse(x["question"], t)
        self.assertTrue(self.f("AI video creators, what's your go-to right now?")["named_crowd"])
        self.assertFalse(self.f("Real talk: which tool do you use?")["named_crowd"])
        self.assertTrue(self.f("Real talk: which tool... I'll reply to everyone. Which one do you use?")["reply_promise"])

    def test_questions_and_not(self):
        q = self.f("Wan 3.0 vs Seedance 2.5\n\nWhich one is worth your credits?\n\nHave you tried Wan yet? 👇")
        self.assertTrue(q["question"])
        self.assertFalse(q["crowd_call"])
        for t in ("what if paying for something was as simple as asking your AI?", "POV: when you realize what Jensen Huang has built",
                  "Seedance 2.5 vs Kling 4.0", "same prompt, two video models, two different interpretations 🎬",
                  "Imagine an AI agent that doesn't just process records?"):
            x = self.f(t)
            self.assertFalse(x["asks_reader"], t)
            self.assertFalse(x["crowd_call"], t)

    def test_tags_in_the_first_self_reply(self):
        x = self.f("we got bored and became a rap group 💀", replies=[
            {"text": "and big shoutout to @late", "minutes_after": 300},
            {"text": "@toolai made with @toolai\n\nshoutout to @a_c @b_c @%s for starring" % HANDLE, "minutes_after": 1}])
        self.assertEqual(x["tags_post"], [])
        self.assertEqual(x["tags_first_reply"], ["toolai", "a_c", "b_c"])   # the earliest reply; the account itself left out
        self.assertTrue(x["tagged"])
        self.assertTrue(self.f("one line clip https://t.co/x", typ="video")["one_line"])
        self.assertEqual(self.f("thanks @ramp and @Ramp and mail@x.com")["tags_post"], ["ramp"])

    def test_number_formats(self):
        self.assertEqual(growth.fmt_value(12074, None), "12.1K")
        self.assertEqual(growth.fmt_value(37477, "n"), "37.5K")
        self.assertEqual(growth.fmt_value(302744, None), "303K")
        self.assertEqual(growth.fmt_value(11625992, None), "11.6M")
        self.assertEqual(growth.fmt_value(481, None), "481")
        self.assertEqual(growth.fmt_value(9.8, None), "9.8")
        self.assertEqual(growth.fmt_value(12061, "full"), "12,061")
        self.assertEqual(growth.fmt_value(0.6312, "pct"), "63%")
        self.assertEqual(growth.fmt_value(0.58, "x"), "0.58x")
        self.assertEqual(growth.fmt_value(510.88, "x"), "511x")
        self.assertEqual(growth.fmt_value(10.4, "x"), "10x")
        self.assertEqual(growth.fmt_value("2026-11-02", "date"), "Nov 2")
        g = {"a": {"b": [{"post_id": "p1", "views": 5}]}, "m": {"2026-11": {"posts": 3}}}
        self.assertEqual(growth.fill("{a.b.p1.views} and {m.2026-11.posts:full}", g)[0], "5 and 3")
        self.assertEqual(growth.fill("{a.nope}", g)[1], ["{a.nope}: growth.json has no such key"])


class TheNumbers(unittest.TestCase):
    """growth.json on the made-up account: every planted answer found."""

    @classmethod
    def setUpClass(cls):
        cls.d = os.path.join(TMP, "growth_x")
        cls.ans = build(cls.d)
        cls.g = jload(cls.d, "growth.json")
        cls.by = dict((r["post_id"], r) for r in cls.ans["rows"])

    def test_cadence_and_change_point(self):
        cp = self.g["cadence"]["change_point"]
        self.assertEqual((cp["at"], cp["before"], cp["after"]), ("2026-10-19", 0.5, 8.0))
        self.assertEqual(cp["since"]["posts"], 36)                        # 37 minus the 400,000-view meme left out
        self.assertEqual(cp["since"]["per_week"], round(36 / ((READ_AT - dt.datetime(2026, 10, 19, tzinfo=dt.timezone.utc)).total_seconds() / 86400.0) * 7, 1))
        ba = self.g["cadence"]["before_after"]
        self.assertEqual(ba["before"]["posts"], 6)
        self.assertEqual(ba["before"]["views"], 6 * 150)
        self.assertEqual(ba["after"]["posts"], 36)                        # 37 minus the 400,000-view meme left out
        after = [r for r in self.ans["rows"] if r["published_at"] >= "2026-10-19" and r["post_id"] != self.ans["suspect"]]
        self.assertEqual(ba["after"]["views"], sum(r["views"] for r in after))
        nov = [r for r in after if r["published_at"].startswith("2026-11")]
        m = self.g["cadence"]["months"]["2026-11"]
        self.assertEqual((m["posts"], m["views"]), (len(nov), sum(r["views"] for r in nov)))
        self.assertEqual(m["too_new"], 3)                                 # Nov 18 (two) and Nov 19: under 3 days old
        wk = self.g["cadence"]["weeks"]
        self.assertTrue(wk["2026-11-16"]["partial"])
        self.assertFalse(wk["2026-11-09"]["partial"])

    def test_left_out_and_followers(self):
        self.assertEqual(self.g["left_out"]["posts"], [self.ans["suspect"]])
        self.assertNotIn(self.ans["suspect"], self.g["posts"])
        self.assertFalse(self.g["followers"]["measured"])
        self.assertIn("cannot be measured", self.g["followers"]["note"])

    def test_concentration(self):
        co = self.g["concentration"]
        self.assertEqual(co["posts"], 36)
        self.assertEqual(co["top_slice"]["n"], 5)                         # round(0.15 x 36), 3 at least
        top = sorted([r for r in self.ans["rows"] if r["published_at"] >= "2026-10-19" and r["post_id"] != self.ans["suspect"]],
                     key=lambda r: -r["views"])[:5]
        self.assertEqual([x["post_id"] for x in co["top_posts"]], [r["post_id"] for r in top])
        self.assertAlmostEqual(co["top_slice"]["share"], round(sum(r["views"] for r in top) / float(co["views"]), 4))
        self.assertEqual(co["in_common"]["crowd_call"], 4)
        self.assertEqual(co["in_common"]["too_new"], 1)
        vs = [x["views"] for x in co["top_posts"]]
        self.assertEqual(co["half"]["n"], next(i + 1 for i in range(len(vs)) if sum(vs[:i + 1]) >= co["views"] / 2.0))

    def test_crowd_calls(self):
        cc = self.g["crowd_calls"]
        self.assertEqual(cc["count"], 4)
        self.assertEqual(sorted(cc["order"]), sorted(self.ans["crowd"]))
        self.assertEqual((cc["top"]["post_id"], cc["top"]["views"], cc["top"]["replies"]), (self.ans["crowd"][0], 9000, 60))
        self.assertEqual((cc["top"]["replies_read"], cc["top"]["author_replies_read"]), (10, 4))
        self.assertTrue(cc["posts"][self.ans["crowd_new"]]["too_new"])
        self.assertEqual(cc["posts"][self.ans["crowd_new"]]["author_replies_sample"], 5)
        self.assertEqual(self.g["kinds"]["question"]["with"]["posts"], 10)  # the comparisons ask; they are not crowd calls

    def test_repost_graph(self):
        rg = self.g["repost_graph"]
        self.assertEqual(rg["read"], [self.ans["film"], self.ans["crowd"][0], self.ans["quote_big"]])
        f = rg["posts"][self.ans["film"]]
        self.assertEqual(f["tagged"], ["toolai", "ann_c", "bob_c", "cat_c", "dan_c"])
        self.assertEqual(f["tagged_reposted"], ["ann_c", "bob_c", "cat_c"])
        self.assertEqual((f["rows_read"], f["self_reposts"]), (5, 1))
        self.assertEqual(rg["best_tagged"], {"post_id": self.ans["film"], "tagged": 5, "reposted": 3, "not_reposted": ["toolai", "dan_c"]})
        self.assertEqual((rg["biggest"]["handle"], rg["biggest"]["followers"]), ("bigacct", 250000))
        self.assertEqual(rg["posts"][self.ans["quote_big"]]["rows_read"], 0)   # read, nobody on the page
        self.assertEqual([r["handle"] for r in rg["repeat_reposters"]], ["ann_c"])
        self.assertEqual(rg["picks"][0], self.ans["film"])                       # the most reposted post of the period
        self.assertFalse(rg["quoters_read"])

    def test_replies_out_is_a_sample(self):
        ro = self.g["replies_out"]
        self.assertEqual((ro["count"], ro["span_minutes"], ro["per_hour"]), (20, 60, 20.0))
        self.assertTrue(ro["sample"])
        self.assertIn("a sample: one window read", ro["note"])
        self.assertEqual(ro["to_big"], 5)                                  # 10,000 followers or more
        self.assertEqual(ro["in_own_threads"], 5)
        self.assertEqual(ro["to_circle"], 2)                               # ann_c reposted and was tagged; toolai was tagged
        self.assertEqual(ro["by_size"]["over_100k"], 2)
        self.assertTrue(any("never a rate" in x["why"] for x in self.g["limits"]))

    def test_speed(self):
        sp = self.g["speed"]
        self.assertEqual((sp["top"]["post_id"], sp["top"]["minutes"], sp["top"]["original_views"], sp["top"]["own_views"]),
                         (self.ans["quote_big"], 40, 5000000, 4000))
        self.assertEqual((sp["big_quotes"], sp["big_replies"]), (1, 1))
        self.assertFalse(sp["items"][self.ans["quote_small"]]["big"])
        self.assertEqual(sp["items"]["800001"]["minutes"], 12)

    def test_the_weakest_format_lacks(self):
        fl = self.g["flops"]
        self.assertEqual(fl["format"]["id"], "meme-fmt")
        self.assertLess(fl["format"]["lift"], 1)
        self.assertEqual(fl["format"]["hits"], 0)
        self.assertEqual(fl["features"]["tagged"]["format"], 0)
        for k in ("tagged", "asks_reader"):
            self.assertIn(k, fl["lacks"])
        self.assertNotIn("own_video", fl["lacks"])

    def test_growth_md_and_the_reply(self):
        md = text(self.d, "GROWTH.md")
        v = growth.view(self.d)
        self.assertTrue(v["ready"], v["problems"] + v["checks"])
        self.assertTrue(600 <= v["reply_chars"] <= 1200, v["reply_chars"])
        self.assertTrue(v["reply"].startswith(growth.REPLY_FIRST))
        self.assertTrue(v["reply"].endswith('tell your agent "REA Viral: why is @handle growing".'))
        self.assertIn("\n1. Volume: from Oct 19 you went from 0.5 to 8 posts a week", v["reply"])
        self.assertIn("\n5. Doesn't move: one-line meme clips", v["reply"])
        self.assertIn("your top one got 9K views and 60 replies", v["reply"])
        self.assertNotIn("github", v["reply"])
        self.assertIn(v["reply"], md)
        self.assertIn("The follow-up line, a separate reply: github.com/wpsoul/rea-viral", md)
        self.assertTrue(md.rstrip().endswith('"REA Viral: why is @handle growing"'))
        self.assertIn("Note: replies to others: a sample: one window read", md)   # a claim citing a sample says so
        self.assertIn("Under 3 days old", md)


class Checks(unittest.TestCase):
    """What growth.py and validate.py refuse."""

    @classmethod
    def setUpClass(cls):
        cls.base = os.path.join(TMP, "checks_base")
        cls.ans = build(cls.base)

    def copy(self, name):
        dst = os.path.join(TMP, name)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(self.base, dst)
        return dst

    def test_the_reply_is_checked(self):
        d = self.copy("long")
        fi = jload(d, "findings.json")
        fi["growth"]["why_it_grows"][0]["reply"] += " And that is why the volume kept going, week after week after week, " * 10
        jsave(os.path.join(d, "findings.json"), fi)
        code, out = run("growth.py", d, ok=(1,))
        self.assertIn("NOT READY: the reply is", out)
        self.assertIn("at most", out)
        fi["growth"]["why_it_grows"][0]["reply"] = "Volume: see github.com/me for {cadence.change_point.after} posts a week."
        jsave(os.path.join(d, "findings.json"), fi)
        code, out = run("growth.py", d, ok=(1,))
        self.assertIn("no link in the reply", out)
        self.assertIn("NOT READY", text(d, "GROWTH.md"))

    def test_claims_are_checked(self):
        d = self.copy("claims")
        fi = jload(d, "findings.json")
        fi["growth"]["why_it_grows"][1]["text"] = "Crowd calls work: {crowd_calls.nope.views} views."
        fi["growth"]["why_it_grows"][1]["reply"] = "Crowd calls work."
        fi["growth"]["why_it_grows"][2]["posts"] = []
        fi["growth"]["why_it_grows"][3]["text"] = "Fast quotes."
        fi["growth"]["why_it_grows"][3]["reply"] = "Fast quotes."
        fi["growth"]["doesnt_move"][0]["evidence"] = "INFERRED"
        jsave(os.path.join(d, "findings.json"), fi)
        code, out = run("validate.py", d, ok=(1,))
        self.assertIn("growth.why_it_grows[1]: {crowd_calls.nope.views}: growth.json has no such key", out)
        self.assertIn("growth.why_it_grows[2]: an example", out)
        self.assertIn("growth.why_it_grows[3]: 1 or 2 real numbers", out)
        self.assertIn("growth.doesnt_move[0].basis: INFERRED needs its basis", out)
        code, out = run("build_report.py", d, ok=(1,))
        self.assertIn("the page is not built", out)

    def test_bad_growth_files(self):
        d = self.copy("badfiles")
        with open(os.path.join(d, "reposters.csv"), "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["nope", "@who", "", "12.3K", "", "like", "", ""])
        with open(os.path.join(d, "replies_out.csv"), "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["800000", "", "", HANDLE, "", "", "", "dup and no time", "", "", ""])
        with open(os.path.join(d, "originals.csv"), "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["unknown", "1", "", "", "", "2026-11-01T00:00:00Z", "", ""])
        code, out = run("validate.py", d, ok=(1,))
        for s in ("reposters.csv:row 10:post_id: 'nope' is not a post_id", "reposters.csv:row 10:followers",
                  "reposters.csv:row 10:kind", "write the handle without the @", "replies_out.csv:row 22:reply_id: '800000' repeats",
                  "replies_out.csv:row 22:at: empty", "a reply to the account itself is not a reply to others",
                  "originals.csv:row 5:post_id: 'unknown' is neither a post"):
            self.assertIn(s, out)

    def test_stale_and_no_growth_files(self):
        d = self.copy("stale")
        run("text_probe.py", d)
        run("build_report.py", d)
        with open(os.path.join(d, "replies_out.csv"), "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["899999", "", "2026-11-20T11:00:00Z", "late_one", "5", "", "", "hi", "", "", ""])
        code, out = run("build_report.py", d, ok=(1,))
        self.assertIn("growth.json was made before replies_out.csv changed: run growth.py again", out)
        d2 = self.copy("bare")
        for f in ("reposters.csv", "replies_out.csv", "originals.csv", "comments.csv", "findings.json"):
            os.remove(os.path.join(d2, f))
        acc = jload(d2, "account.json")
        acc.pop("growth_read")
        acc.pop("comments_read")
        jsave(os.path.join(d2, "account.json"), acc)
        run("analyze.py", d2)
        run("radar.py", d2)
        code, out = run("growth.py", d2)
        g = jload(d2, "growth.json")
        self.assertIsNone(g["replies_out"])
        self.assertIsNone(g["speed"])
        self.assertEqual(g["repost_graph"]["read"], [])
        whats = [x["what"] for x in g["limits"]]
        for w in ("The author's replies to others", "Who reposted", "Replies under the crowd calls", "Quoted originals"):
            self.assertIn(w, whats)
        self.assertIn("read next: one window of the account's replies to others", out)
        self.assertIn("next: write findings.json \"growth\"", out)

    def test_the_report_block(self):
        d = self.copy("report")
        run("text_probe.py", d)
        code, out = run("build_report.py", d)
        self.assertIn("GROWTH.md written (growth mode: 4 mechanisms, 1 that do not move; the reply draft", out)
        html = text(d, "report.html")
        self.assertIn("section('growth', 'Why it grows'", html)
        self.assertIn('"why":[{"title":"Volume"', html.replace(" ", ""))
        acc_md = text(d, "ACCOUNT.md")
        self.assertIn("| Why is it growing (growth mode)? | 1. Volume; 2. Crowd calls; 3. Credits; 4. Speed | GROWTH.md", acc_md)
        light = text(d, "report-light.html")
        self.assertIn("Copy reply", light)

    def test_not_an_account_folder(self):
        d = os.path.join(TMP, "a_niche")
        os.makedirs(d, exist_ok=True)
        jsave(os.path.join(d, "niche.json"), {"name": "x"})
        code, out = run("growth.py", d, ok=(2,))
        self.assertIn("growth mode runs on one account", out)


if __name__ == "__main__":
    if "--make" in sys.argv:
        out = os.path.join(sys.argv[sys.argv.index("--make") + 1], "growth_x")
        build(out)
        run("text_probe.py", out)
        print(out)
        sys.exit(0)
    unittest.main()
