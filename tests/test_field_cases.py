#!/usr/bin/env python3
"""What a real run on an X niche met (fixed in 0.4.1), each case on made-up rows with a known answer.

    python3 tests/test_field_cases.py [-v]

1. covers_sheet.py: several hundred covers in mixed files (JPEG, PNG with and without alpha, odd sizes) all land on
   their numbered sheets, each tile checked at its own place; "drew N of M on K sheets"; the sheet check catches a tile
   that is not there.
2. video_probe.py on X: a text post, a picture post, a carousel and a quote of someone else's video are never cut; the
   post's own video is; a downloader's "No video" marks that pick not read and the run goes on; a video row that does
   not say whose video it is is not fetched and says so.
3. Words per minute without subtitles: "not measured", never 0 (the medians, the recipe, remake_check.py, the report).
4. text_probe.py: openers read as a name by mistake ("Let's connect", "Here's why", ...) and real names.
5. Replies: left out of the numbers and counted; the account's own replies folded into their post.
6. Corner words: an older radar.json ("fading" as a corner, "weakening" as a direction) read in today's words.
7. formats_check.py: counts, overlaps, unassigned posts with their openers, an example that does not fit, --write.
8. Covers fetched like a browser: a stand-in server that answers 403 without a browser's User-Agent, a redirect, a
   403 and a 429 that stay "not read" with their status while the run goes on, a timeout.
9. Seeds checked first (a stand-in yt-dlp): found, not found, no posts in the window; a creator with no post in the
   window is not counted; the niche report names them and says why there is no voice sheet.
10. What was not read, from what happened: a thread's first part only, carousels by their cover, a sample.
"""
import csv
import datetime as dt
import http.server
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SK = os.path.join(REPO, "skill", "scripts")
sys.dont_write_bytecode = True
sys.path.insert(0, SK)
import common  # noqa: E402
import page_kit  # noqa: E402
import text_probe  # noqa: E402

TMP = None
FX = None
READ_AT = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)


def setUpModule():
    global TMP, FX
    TMP = tempfile.mkdtemp(prefix="rea-viral-field-")
    FX = os.path.join(TMP, "fixtures")
    for script in ("make_fixtures.py", "make_niche_fixtures.py"):   # make_fixtures.py empties --out first
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script), "--out", FX],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if r.returncode != 0:
            raise RuntimeError("%s failed: %s" % (script, r.stderr.decode()))


def tearDownModule():
    if TMP and os.environ.get("REA_KEEP") != "1":
        shutil.rmtree(TMP, ignore_errors=True)


def copy(name):
    dst = tempfile.mkdtemp(prefix=name.replace("/", "-") + "-", dir=TMP)
    shutil.rmtree(dst)
    shutil.copytree(os.path.join(FX, name), dst)
    return dst


def run(script, *args, ok=(0,), env=None):
    r = subprocess.run([sys.executable, "-I", os.path.join(SK, script)] + [str(a) for a in args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, env=env)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    if ok is not None and r.returncode not in ok:
        raise AssertionError("%s %s exited %d:\n%s" % (script, " ".join(map(str, args)), r.returncode, out[-3000:]))
    return r.returncode, out


def jload(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return json.load(f)


def jsave(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def text(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def ff(*args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=300)
    if r.returncode != 0:
        raise AssertionError("ffmpeg failed: " + r.stderr.decode("utf-8", "replace")[-500:])
    return r.stdout


def account_folder(name, handle, rows, network="x", **extra):
    """A made-up account folder: account.json and posts.csv (every column of the shape, 0.4.1's included)."""
    d = tempfile.mkdtemp(prefix=name + "-", dir=TMP)
    acc = {"schema": "rea-viral/account@2", "network": network, "handle": handle, "name": handle.title(),
           "url": "https://x.com/%s" % handle if network == "x" else "https://www.tiktok.com/@%s" % handle,
           "followers": 12000, "followers_exact": True, "read_at": iso(READ_AT),
           "window": {"from": "2026-09-01", "to": "2026-11-19"}, "follower_history": [],
           "sources": [{"what": "posts", "via": "test_field_cases.py", "cost_usd": 0}], "spend_ceiling_usd": 1}
    acc.update(extra)
    jsave(os.path.join(d, "account.json"), acc)
    with open(os.path.join(d, "posts.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=common.POST_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, "" if r.get(k) is None else r.get(k)) for k in common.POST_COLUMNS))
    return d


def x_row(pid, i, caption, kind="text", views=10000, handle="fixture", **kw):
    t = dt.datetime(2026, 9, 2, 15, tzinfo=dt.timezone.utc) + dt.timedelta(hours=6 * i)   # 305 rows end before read_at
    r = {"post_id": pid, "url": "https://x.com/%s/status/%d" % (handle, 2000 + i), "published_at": iso(t),
         "type": kind, "caption": caption, "views": views, "likes": views // 50, "comments": views // 500,
         "reposts": views // 1000, "bookmarks": views // 400, "lang": "en", "source": "fixture"}
    r.update(kw)
    return r


def fake_tool(name, body):
    """A stand-in command on a PATH of its own (yt-dlp here); returns the env that finds it first."""
    bindir = tempfile.mkdtemp(prefix="bin-", dir=TMP)
    path = os.path.join(bindir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!%s\n%s" % (sys.executable, body))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1")


def colour(i):
    return ((i * 37 + 20) % 256, (i * 91 + 40) % 256, (i * 53 + 60) % 256)


def make_covers(dest, first, count, size, ext, pix=None):
    """count solid covers named c<first..>.<ext>, cover i in colour(i): one ffmpeg call."""
    vf = ("format=%s,geq=r='mod((N+%d)*37+20,256)':g='mod((N+%d)*91+40,256)':b='mod((N+%d)*53+60,256)'%s"
          % ("rgba" if pix == "rgba" else "rgb24", first, first, first, ":a=200" if pix == "rgba" else ""))
    args = ["-f", "lavfi", "-i", "color=c=black:s=%s:r=1" % size, "-frames:v", str(count), "-vf", vf]
    if pix:
        args += ["-pix_fmt", pix]
    ff(*(args + ["-start_number", str(first), os.path.join(dest, "c%03d." + ext)]))


def sheet_pixels(path, cols, rows):
    w = 2 * 4 + cols * 180 + (cols - 1) * 4
    h = 2 * 4 + rows * 320 + (rows - 1) * 4
    raw = ff("-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1")
    if len(raw) != w * h * 3:
        raise AssertionError("%s is not %dx%d" % (path, w, h))

    def at(c, r):   # the mean of a 9 x 9 patch at the tile's centre
        x0, y0 = 4 + c * 184 + 90, 4 + r * 324 + 160
        acc = [0, 0, 0]
        for y in range(y0 - 4, y0 + 5):
            for x in range(x0 - 4, x0 + 5):
                k = (y * w + x) * 3
                for j in range(3):
                    acc[j] += raw[k + j]
        return tuple(v / 81.0 for v in acc)
    return at


def near(a, b, tol=30):
    return max(abs(x - y) for x, y in zip(a, b)) <= tol


# ---------------------------------------------------------------------------------------------- 1. the covers sheet

@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class CoversSheet(unittest.TestCase):
    def test_every_cover_on_its_numbered_sheet(self):
        n_cov, no_cover = 300, {7, 120, 233, 301, 304}
        rows, cover_of, j = [], {}, 0
        for i in range(n_cov + len(no_cover)):
            pid = "p%03d" % i
            r = x_row(pid, i, "Post %d of a made-up account" % i, kind="image", own_media="image")
            if i not in no_cover:
                cover_of[pid] = j
                j += 1
            rows.append(r)
        d = account_folder("covers", "fixture_pictures", rows)
        cdir = os.path.join(d, "covers")
        os.makedirs(cdir)
        # Three kinds of file, as a network gives them: JPEG (phone-tall), PNG with alpha (square), PNG RGB (wide).
        make_covers(cdir, 0, 100, "90x160", "jpg")
        make_covers(cdir, 100, 100, "300x300", "png", "rgba")
        make_covers(cdir, 200, 100, "160x90", "png", "rgb24")
        for r in rows:
            if r["post_id"] in cover_of:
                k = cover_of[r["post_id"]]
                r["cover_file"] = "covers/c%03d.%s" % (k, "jpg" if k < 100 else "png")
        with open(os.path.join(d, "posts.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=common.POST_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow(dict((k, "" if r.get(k) is None else r.get(k)) for k in common.POST_COLUMNS))
        jsave(os.path.join(cdir, "not_read.json"), {"p007": "HTTP 403", "p120": "HTTP 429"})
        open(os.path.join(d, "covers_sheet-9.jpg"), "wb").close()      # an older, longer run's sheet
        code, out = run("covers_sheet.py", d)
        total = len(rows)
        self.assertIn("covers_sheet: drew %d of %d on 7 sheets" % (total, total), out)
        self.assertFalse(os.path.exists(os.path.join(d, "covers_sheet-9.jpg")))
        cs = jload(d, "covers_sheet.json")
        self.assertEqual((cs["of"], cs["drawn"], cs["per_sheet"], len(cs["sheets"])), (total, total, 50, 7))
        self.assertEqual([s["file"] for s in cs["sheets"]],
                         ["covers_sheet.jpg"] + ["covers_sheet-%d.jpg" % k for k in range(2, 8)])
        self.assertEqual([t["post_id"] for t in cs["tiles"]], [r["post_id"] for r in rows])
        why = dict((t["post_id"], (t["cover"], t["why"])) for t in cs["tiles"])
        self.assertEqual(why["p007"], ("not read", "HTTP 403"))
        self.assertEqual(why["p120"], ("not read", "HTTP 429"))
        self.assertEqual(why["p233"], ("not read", "no cover saved"))
        self.assertEqual(why["p000"], ("read", None))
        # Every tile looked at on its own sheet, at its own place: the cover's colour, or grey for "not read".
        wrong = []
        for s in cs["sheets"]:
            first, last = s["tiles"]
            n = last - first + 1
            at = sheet_pixels(os.path.join(d, s["file"]), 10, (n + 9) // 10)
            for k in range(n):
                t = cs["tiles"][first - 1 + k]
                want = colour(cover_of[t["post_id"]]) if t["post_id"] in cover_of else (0x33, 0x33, 0x33)
                got = at(k % 10, k // 10)
                if not near(got, want):
                    wrong.append("%s tile %d: %s, not %s" % (s["file"], t["tile"], tuple(round(v) for v in got), want))
        self.assertEqual(wrong, [])

    def test_the_sheet_check_catches_a_missing_tile(self):
        import covers_sheet
        src = tempfile.mkdtemp(prefix="src-", dir=TMP)
        make_covers(src, 0, 20, "90x160", "jpg")
        tiles = tempfile.mkdtemp(prefix="tiles-", dir=TMP)
        for i in range(20):
            self.assertTrue(covers_sheet.make_tile(os.path.join(src, "c%03d.jpg" % i), i + 1,
                                                   os.path.join(tiles, "%05d.png" % (i + 1))))
        out = os.path.join(TMP, "check-sheet.jpg")
        rows = covers_sheet.build_sheet(tiles, 1, 20, 10, out)
        self.assertEqual(covers_sheet.check_sheet(tiles, 1, 20, 10, rows, out), 20)
        shutil.copy(os.path.join(tiles, "00006.png"), os.path.join(tiles, "00005.png"))   # tile 5 is not what the sheet shows
        self.assertEqual(covers_sheet.check_sheet(tiles, 1, 20, 10, rows, out), 19)


# ---------------------------------------------------------------------------------------------- 2. own videos only

YTDLP_VIDEOS = r'''
import shutil, sys
args = sys.argv[1:]
url = args[-1]
with open(%(log)r, "a") as f:
    f.write(("subs " if "--skip-download" in args else "video ") + url + "\n")
if "--skip-download" in args:
    sys.exit(0)
if url.endswith("/status/2005"):
    sys.stderr.write("ERROR: [twitter] 2005: No video could be found in this tweet\n")
    sys.exit(1)
shutil.copy(%(clip)r, args[args.index("-o") + 1].replace("%%(ext)s", "mp4"))
'''


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class OwnVideoOnly(unittest.TestCase):
    def test_x_posts_cut_only_their_own_video(self):
        clip = os.path.join(TMP, "clip.mp4")
        ff("-f", "lavfi", "-i", "testsrc=d=3:s=180x320:r=25", "-pix_fmt", "yuv420p", clip)
        log = os.path.join(TMP, "ytdlp-videos.log")
        env = fake_tool("yt-dlp", YTDLP_VIDEOS % {"log": log, "clip": clip})
        h = "fixture_quotes"
        rows = [x_row("x1", 1, "Words only, no media at all", "text", handle=h, own_media="none"),
                x_row("x2", 2, "One picture of the desk", "image", handle=h, own_media="image"),
                x_row("x3", 3, "Four slides on pricing", "carousel", handle=h, own_media="images"),
                x_row("x4", 4, "This clip says it all", "quote", handle=h, own_media="none",
                      quoted_url="https://x.com/someone_else/status/99"),
                x_row("x5", 5, "My own clip of the launch", "video", handle=h, own_media="video"),
                x_row("x6", 6, "My take, with my own clip", "quote", handle=h, own_media="video",
                      quoted_url="https://x.com/someone_else/status/98"),
                x_row("x7", 7, "A video row from a reader that does not say whose", "video", handle=h),
                x_row("x8", 8, "A quote row from a reader that does not say whose", "quote", handle=h,
                      quoted_url="https://x.com/someone_else/status/97")]
        d = account_folder("own-video", h, rows)
        code, out = run("video_probe.py", d, "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "--fetch", env=env)
        self.assertEqual(code, 0, out)
        with open(log, encoding="utf-8") as f:
            asked = set(line.split()[1].rsplit("/", 1)[1] for line in f)
        self.assertEqual(asked, {"2005", "2006"})                      # only the posts' own videos were asked for
        for pid in ("x1", "x2", "x3", "x4"):
            self.assertFalse(os.path.exists(os.path.join(d, "videos", pid)), pid)
        self.assertIn("x2: an image post with no video of its own, not cut (its cover: covers_sheet.py)", out)
        self.assertIn("x4: a quote post with no video of its own, not cut (its words: text_probe.py)", out)
        n5 = jload(d, "videos", "x5", "notes.json")
        self.assertIs(n5["read"], False)
        self.assertIn("No video could be found", n5["not_read_reason"])
        self.assertEqual(n5["not_read_by"], "video_probe.py")
        self.assertTrue(jload(d, "videos", "x6", "probe.json")["read"])  # the run went on after x5
        self.assertIsNone(jload(d, "videos", "x6", "notes.json")["read"])
        for pid in ("x7", "x8"):
            n = jload(d, "videos", pid, "notes.json")
            self.assertIs(n["read"], False)
            self.assertIn("does not say whether the video is this post's own", n["not_read_reason"])
        self.assertIn("1 of 2 videos could not be read: marked not read with why; the run goes on", out)
        code, out = run("validate.py", d, ok=(0, 1))
        self.assertIn("2 video or quote rows do not say whose video it is", out)
        lim = dict((x["what"], x["why"]) for x in page_kit.run_limits("account", d))
        self.assertIn("2 picked posts", lim.get("Videos not watched", ""))
        self.assertIn("1 of 1 watched video had no subtitles", lim.get("Speech in videos", ""))
        # The video saved by hand later: read, and the automatic "not read" gives way to the template.
        shutil.copy(clip, os.path.join(d, "videos", "x5", "video.mp4"))
        run("video_probe.py", d, "x5", env=env)
        self.assertIsNone(jload(d, "videos", "x5", "notes.json")["read"])

    def test_video_networks_keep_their_videos(self):
        self.assertTrue(common.own_video({"type": "video"}, "youtube"))
        self.assertTrue(common.own_video({"type": "video"}, "tiktok"))
        self.assertFalse(common.own_video({"type": "carousel"}, "instagram"))
        self.assertIsNone(common.own_video({"type": "video"}, "x"))
        self.assertIsNone(common.own_video({"type": "quote"}, "threads"))
        self.assertFalse(common.own_video({"type": "quote", "own_media": "none"}, "x"))
        self.assertTrue(common.own_video({"type": "quote", "own_media": "video"}, "x"))
        self.assertFalse(common.own_video({"type": "text"}, "x"))


# ---------------------------------------------------------------------------------------------- 3. speech rate

def probe_without_words(d, pid):
    vdir = os.path.join(d, "videos", pid)
    os.makedirs(vdir, exist_ok=True)
    m = {"length_s": 24.0, "cuts_per_10s": 2.5, "first_cut_s": 1.1, "average_shot_s": 4.0, "cuts": [1.1, 5.0],
         "words": None, "words_per_minute": None, "transcript_note": "no subtitles found; the words were not read"}
    jsave(os.path.join(vdir, "probe.json"), {"schema": "rea-viral/probe@1", "post_id": pid, "read": True, "measured": m})
    jsave(os.path.join(vdir, "notes.json"), {
        "post_id": pid, "read": True, "not_read_reason": None,
        "measured": dict((k, m[k]) for k in ("length_s", "cuts_per_10s", "first_cut_s", "average_shot_s", "words_per_minute")),
        "seen": {"hook": {"text": "a hand slams a laptop shut", "at": 0.0}, "first_frame": "a laptop on a desk",
                 "text_on_screen": "none", "sound": "music, no voice", "turn": {"text": "none", "at": None},
                 "ask": {"text": "none", "at": None}},
        "beats": [{"at": 0.0, "what": "hook", "text": "the laptop shuts"}], "cover": "a laptop"})


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class SpeechRate(unittest.TestCase):
    def test_no_subtitles_is_not_measured_never_zero(self):
        d = copy("main")
        run("analyze.py", d)
        an = jload(d, "analysis.json")
        inw = dict((p["post_id"], p) for p in an["posts"] if p["in_window"] and p["type"] == "video")
        fm = next(f for f in jload(d, "formats.json")["formats"] if sum(1 for x in f["posts"] if x in inw) >= 2)
        picked = [x for x in fm["posts"] if x in inw][:2]
        for pid in picked:
            probe_without_words(d, pid)
        run("radar.py", d)
        f = next(x for x in jload(d, "radar.json")["formats"] if x["id"] == fm["id"])
        self.assertEqual(f["videos_read"], 2)
        self.assertIsNone(f["probe"]["words_per_minute"])               # not 0: nothing was heard
        self.assertEqual(f["probe"]["cuts_per_10s"], 2.5)
        rec = os.path.join(TMP, "recipe-no-words.md")
        with open(rec, "w", encoding="utf-8") as fh:
            fh.write("# A recipe\n\n```json rea-recipe\n%s\n```\n" % json.dumps(
                {"schema": "rea-viral/recipe@1", "id": "r", "name": "R", "length_s": 3.0, "cuts_per_10s": 0,
                 "words_per_minute": None, "beats": []}))
        clip = os.path.join(TMP, "remake.mp4")
        ff("-f", "lavfi", "-i", "color=c=0x225588:s=180x320:r=25:d=3", "-pix_fmt", "yuv420p", clip)
        words = os.path.join(TMP, "remake-words.json")
        jsave(words, {"words": [{"w": "one", "start": 0.2, "end": 0.5}, {"w": "two", "start": 0.6, "end": 0.9}]})
        code, out = run("remake_check.py", clip, rec, "--words", words, "--json", ok=(0, 1))
        res = json.loads(out)
        self.assertIn("words per minute not checked: the recipe has none (its videos had no subtitles)", res["notes"])
        self.assertNotIn("words per minute", [c["check"] for c in res["checks"]])
        run("comment_tactics.py", d)
        shutil.copy(os.path.join(d, "findings.example.json"), os.path.join(d, "findings.json"))
        run("build_report.py", d)
        md = text(d, "ACCOUNT.md")
        self.assertIn("[MEASURED] Speech in videos: 2 of 2 watched videos had no subtitles: words per minute not "
                      "measured", md)
        self.assertIn("words/min not measured: no subtitles", text(d, "report.html"))


# ---------------------------------------------------------------------------------------------- 4. names in the opening

class OpensName(unittest.TestCase):
    NOT_NAMES = ["Let's connect if you build in public", "Let\u2019s connect if you build in public",
                 "Here's why most launches fail", "Don't do this before you post", "I'm done writing for reach",
                 "It's over for long captions", "That's the whole trick", "What's your first post going to be?",
                 "We're hiring a designer this month", "You're not behind, you're early", "Today I shipped the update",
                 "There's a better way to price", "Nobody tells you this about pricing"]
    NAMES = ["@someone_builds taught me this", "Maria's launch got 40,000 views", "Maria Lopez just shipped her app",
             "Jordan Lee said it best", "Sam\u2019s first week on the job"]

    def test_contractions_are_not_names(self):
        words = text_probe.load_words()
        for line in self.NOT_NAMES:
            self.assertIs(text_probe.opening_kinds(line, "en", words)["opens_name"], False, line)
        for line in self.NAMES:
            self.assertIs(text_probe.opening_kinds(line, "en", words)["opens_name"], True, line)

    def test_the_words_live_in_the_data_file(self):
        doc = jload(os.path.dirname(SK), "data", "writing-words.json")
        c = set(w.lower() for w in doc["languages"]["en"]["contractions"])
        self.assertTrue({"let's", "here's", "don't", "i'm", "it's"} <= c)


# ---------------------------------------------------------------------------------------------- 5. replies

class Replies(unittest.TestCase):
    def test_replies_left_out_counted_and_own_folded(self):
        h = "fixture_replies"
        rows = [x_row("p%02d" % i, i * 2, "Plain post number %d about shipping small things" % i, views=10000 + 37 * i,
                      handle=h, own_media="none") for i in range(30)]
        for k in range(8):   # replies to other accounts, as X writes them: the text opens with the handle answered
            rows.append(x_row("r%02d" % k, 61 + k, "@someone_else%d good point, thanks" % k, views=40, handle=h))
        rows.append(x_row("r08", 70, "Agreed, this is the part people skip", views=35, handle=h, reply_to="another_account"))
        rows.append(x_row("r09", 71, "Same here", views=30, handle=h, reply_to="@Another_Account"))
        at = dict((r["post_id"], dt.datetime.strptime(r["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc))
                  for r in rows)
        p05, p10 = at["p05"], at["p10"]
        rows.append(x_row("s01", 72, "@fixture_replies And the second half of the story.", views=900, handle=h,
                          reply_to=h, reply_to_id="p05", published_at=iso(p05 + dt.timedelta(seconds=50))))
        rows.append(x_row("s02", 73, "@fixture_replies If this helped, follow me for more.", views=300, handle=h,
                          reply_to=h, reply_to_id="p10", published_at=iso(p10 + dt.timedelta(minutes=300))))
        rows.append(x_row("s03", 74, "@fixture_replies a reply of my own under a post that was not read", views=20,
                          handle=h, reply_to=h))
        d = account_folder("replies", h, rows)
        self.assertEqual(common.replies_left_out(d), {"other": 10, "self": 1, "folded": 2})
        posts = dict((p["post_id"], p) for p in common.load_posts(d))
        self.assertEqual(sorted(posts), ["p%02d" % i for i in range(30)])
        self.assertEqual((posts["p05"]["type"], posts["p05"]["parts"]),
                         ("thread", ["Plain post number 5 about shipping small things", "And the second half of the story."]))
        self.assertEqual(posts["p10"]["author_replies"], [{"text": "If this helped, follow me for more.", "minutes_after": 300.0}])
        run("analyze.py", d)
        an = jload(d, "analysis.json")
        self.assertEqual((an["counts"]["posts_total"], an["counts"]["replies_left_out"], an["counts"]["own_replies_folded"]),
                         (30, 11, 2))
        self.assertTrue(all(p["post_id"].startswith("p") for p in an["posts"]))   # never in the usual or the trends
        code, out = run("validate.py", d, ok=(0, 1))
        self.assertIn("10 rows are replies to other accounts", out)
        self.assertIn("3 rows are the account's own replies", out)
        lim = dict((x["what"], x["why"]) for x in page_kit.run_limits("account", d))
        self.assertEqual(lim.get("Replies"), "11 replies left out of the numbers (replies are not posts)")

    def test_an_at_sign_is_a_reply_only_on_x_and_threads(self):
        p = {"caption": "@friend look at this edit"}
        self.assertEqual(common.reply_kind(p, "me", "x"), "other")
        self.assertEqual(common.reply_kind(p, "me", "threads"), "other")
        self.assertIsNone(common.reply_kind(p, "me", "youtube"))
        self.assertIsNone(common.reply_kind(p, "me", "tiktok"))
        self.assertEqual(common.reply_kind({"caption": "@Me part two"}, "me", "x"), "self")


# ---------------------------------------------------------------------------------------------- 6. corner words

class CornerWords(unittest.TestCase):
    def test_an_older_radar_is_read_in_todays_words(self):
        old = {"scope": "account", "rules": {"often_share": 0.15, "strong_lift": 1.0}, "formats": [
            {"id": "a", "quadrant": "fading", "quadrant_name": "Fading", "share": 0.3, "lift": 0.7, "direction_label": "weakening"},
            {"id": "b", "quadrant": "scale_it", "quadrant_name": "Scale it", "share": 0.3, "lift": 1.4, "direction_label": "weakening"},
            {"id": "c", "quadrant": "fading", "quadrant_name": "Fading", "share": 0.05, "lift": 1.6, "direction_label": "weakening"},
            {"id": "d", "quadrant": "too_few", "share": 0.02, "lift": None, "direction_label": None}]}
        new = dict((f["id"], (f["quadrant"], f.get("quadrant_name"), f["direction_label"]))
                   for f in common.upgrade_radar(old)["formats"])
        self.assertEqual(new["a"], ("overused", "Overused", "fading"))
        self.assertEqual(new["b"], ("scale_it", "Scale it", "fading"))   # where it sits; its direction says it fades
        self.assertEqual(new["c"], ("underused", "Underused", "fading"))
        self.assertEqual(new["d"], ("too_few", None, None))
        shared = {"scope": "shared", "rules": {"often_creators_share": 0.4, "strong_lift": 1.0}, "formats": [
            {"id": "e", "quadrant": "fading", "creators_share": 0.5, "lift": 0.8, "direction_label": "fading"}]}
        self.assertEqual(common.upgrade_radar(shared)["formats"][0]["quadrant"], "overused")

    def test_the_report_from_an_older_radar(self):
        d = copy("main")
        for s in ("analyze.py", "radar.py", "comment_tactics.py"):
            run(s, d)
        rj = jload(d, "radar.json")
        for f in rj["formats"]:
            if f["quadrant"] == "overused":
                f["quadrant"], f["quadrant_name"] = "fading", "Fading"
            if f.get("direction_label") == "fading":
                f["direction_label"] = "weakening"
        self.assertIn('"quadrant": "fading"', json.dumps(rj))
        jsave(os.path.join(d, "radar.json"), rj)
        shutil.copy(os.path.join(d, "findings.example.json"), os.path.join(d, "findings.json"))
        run("build_report.py", d)
        md = text(d, "ACCOUNT.md")
        self.assertIn("(Overused", md)
        self.assertNotIn("(Fading", md)
        self.assertNotIn("weakening", md)
        rows = jload(d, "radar_rows.json")["rows"]
        self.assertTrue(all(r["format"]["trend"] in ("rising", "steady", "fading") for r in rows))


# ---------------------------------------------------------------------------------------------- 7. formats_check

BODY = {"hook": "the first line", "structure": "one idea", "look": "a face to camera", "length": "20-30 s",
        "effort": "low", "basis": "made up for the test"}


class FormatsCheck(unittest.TestCase):
    def folder(self):
        caps = {}
        for i in range(12):
            caps["m%02d" % (i + 1)] = "%d %s that slow every edit down" % (3 + i % 3, ("mistakes", "ways")[i % 2])
        for i in range(10):
            caps["b%02d" % (i + 1)] = "Before and after: the grade on clip %d" % (i + 1)
        for i in range(3):
            caps["o%02d" % (i + 1)] = "5 ways to light a room, before and after"
        for i in range(8):
            caps["n%02d" % (i + 1)] = "Nobody tells you this about %s" % ("pricing", "hiring", "editing", "posting")[i % 4]
        for i, c in enumerate(["Quiet morning in the studio", "My desk tour", "A clip from the weekend",
                               "Testing the new lens", "Why I moved cities", "Q and A, part one", "Thank you for 10k"]):
            caps["z%02d" % (i + 1)] = c
        rows = []
        for i, (pid, cap) in enumerate(sorted(caps.items())):
            t = dt.datetime(2026, 9, 3, 14, tzinfo=dt.timezone.utc) + dt.timedelta(hours=40 * i)
            rows.append({"post_id": pid, "url": "https://www.tiktok.com/@fixture_formats/video/%d" % (100 + i),
                         "published_at": iso(t), "type": "video", "duration_s": 25, "caption": cap,
                         "views": 5000 + 10 * i, "likes": 200, "comments": 9, "source": "fixture"})
        d = account_folder("formats", "fixture_formats", rows, network="tiktok")
        fdoc = {"schema": "rea-viral/formats@1", "formats": [
            dict(BODY, id="numbered-list", name="Numbered list", posts=["m%02d" % i for i in range(1, 13)],
                 examples=["m01", "m02"], match={"opens": ["^\\d+ (mistakes|ways)\\b"]}),
            dict(BODY, id="before-after", name="Before and after", posts=["b%02d" % i for i in range(1, 11)],
                 examples=["b01", "z01"], match={"patterns": ["before and after"], "types": ["video"]}),
            dict(BODY, id="studio-life", name="Studio life", posts=["z02", "z03"])]}
        jsave(os.path.join(d, "formats.json"), fdoc)
        return d, fdoc

    def test_counts_overlaps_openers_and_a_bad_example(self):
        d, fdoc = self.folder()
        code, out = run("formats_check.py", d, ok=(1,))
        self.assertIn("FAIL before-after: z01 does not fit the format's own match", out)
        res = jload(d, "formats_check.json")
        by = dict((f["id"], f) for f in res["formats"])
        self.assertEqual((by["numbered-list"]["posts"], by["numbered-list"]["matched"]), (12, 15))
        self.assertEqual((by["before-after"]["posts"], by["before-after"]["matched"]), (10, 13))
        self.assertEqual((by["studio-life"]["posts"], by["studio-life"]["matched"]), (2, None))
        self.assertTrue(by["numbered-list"]["examples_ok"])
        self.assertFalse(by["before-after"]["examples_ok"])
        self.assertEqual(len(by["numbered-list"]["samples"]), 3)
        self.assertEqual(sorted(o["post_id"] for o in res["overlaps"]), ["o01", "o02", "o03"])
        self.assertEqual(sorted(res["overlaps"][0]["formats"]), ["before-after", "numbered-list"])
        self.assertEqual(res["unassigned"]["posts"], 13)
        self.assertEqual(res["unassigned"]["top_openers"][0]["opener"], "nobody tells you")
        self.assertEqual(res["unassigned"]["top_openers"][0]["posts"], 8)

    def test_write_takes_each_match_and_leaves_overlaps_to_you(self):
        d, fdoc = self.folder()
        fdoc["formats"][1]["examples"] = ["b01", "b02"]
        jsave(os.path.join(d, "formats.json"), fdoc)
        code, out = run("formats_check.py", d, "--write")
        self.assertIn("examples ok", out)
        got = dict((f["id"], f["posts"]) for f in jload(d, "formats.json")["formats"])
        self.assertEqual(got["numbered-list"], ["m%02d" % i for i in range(1, 13)])   # the o's: in two formats, left out
        self.assertEqual(got["before-after"], ["b%02d" % i for i in range(1, 11)])
        self.assertEqual(got["studio-life"], ["z02", "z03"])                            # no match: never touched
        code, out = run("validate.py", d, ok=(0,))

    def test_a_pattern_that_is_not_one_is_named(self):
        d, fdoc = self.folder()
        fdoc["formats"][0]["match"] = {"opens": ["(unclosed"]}
        jsave(os.path.join(d, "formats.json"), fdoc)
        code, out = run("validate.py", d, ok=(1,))
        self.assertIn("formats.json:formats[0].match", out)
        code, out = run("formats_check.py", d, ok=(1,))
        self.assertIn("is not a regular expression", out)


# ---------------------------------------------------------------------------------------------- 8. fetching like a browser

class Pictures(http.server.BaseHTTPRequestHandler):
    jpg = png = b""

    def do_GET(self):
        ua, acc = self.headers.get("User-Agent") or "", self.headers.get("Accept") or ""
        name = self.path.rsplit("/", 1)[-1]
        if self.path.startswith("/moved/"):
            self.send_response(302)
            self.send_header("Location", "/pic/" + name)
            self.end_headers()
            return
        if self.path.startswith("/slow/"):
            time.sleep(3)
        if self.path.startswith("/always403/"):
            code = 403
        elif self.path.startswith("/busy/"):
            code = 429
        elif "Mozilla/" not in ua or "image/" not in acc:   # a picture server that refuses scripts
            code = 403
        else:
            code = 200
        body = (Pictures.png if self.path.startswith("/png/") else Pictures.jpg) if code == 200 else b"no"
        self.send_response(code)
        self.send_header("Content-Type", "image/png" if self.path.startswith("/png/") else "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class FetchLikeABrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = tempfile.mkdtemp(prefix="pics-", dir=TMP)
        make_covers(src, 0, 1, "90x160", "jpg")
        make_covers(src, 1, 1, "90x160", "png", "rgb24")
        with open(os.path.join(src, "c000.jpg"), "rb") as f:
            Pictures.jpg = f.read()
        with open(os.path.join(src, "c001.png"), "rb") as f:
            Pictures.png = f.read()
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pictures)
        cls.srv.daemon_threads = True
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_the_stand_in_refuses_a_script(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.base + "/pic/a1", timeout=5)
        self.assertEqual(e.exception.code, 403)
        status, body, why = common.http_get(self.base + "/pic/a1")
        self.assertEqual((status, why), (200, None))
        self.assertEqual(body[:3], b"\xff\xd8\xff")
        status, body, why = common.http_get(self.base + "/slow/a1", timeout=1)
        self.assertIsNone(body)
        self.assertIn("timed out", why)

    def test_covers_fetched_and_the_rest_kept_not_read(self):
        b = self.base
        rows = [x_row("f1", 1, "a", "image", own_media="image", cover_url=b + "/pic/f1"),
                x_row("f2", 2, "b", "image", own_media="image", cover_url=b + "/png/f2"),
                x_row("f3", 3, "c", "image", own_media="image", cover_url=b + "/moved/f3"),
                x_row("f4", 4, "d", "image", own_media="image", cover_url=b + "/always403/f4"),
                x_row("f5", 5, "e", "image", own_media="image", cover_url=b + "/busy/f5"),
                x_row("f6", 6, "f", "text", own_media="none")]
        d = account_folder("fetch", "fixture_fetch", rows)
        code, out = run("covers_sheet.py", d, "--fetch")
        self.assertIn("covers: 3 saved now, 0 already saved, 2 not read (HTTP 403: 1, HTTP 429: 1)", out)
        self.assertIn("covers_sheet: drew 6 of 6 on 1 sheet", out)
        with open(os.path.join(d, "posts.csv"), encoding="utf-8") as f:
            files = dict((r["post_id"], r["cover_file"]) for r in csv.DictReader(f))
        self.assertEqual(files, {"f1": "covers/f1.jpg", "f2": "covers/f2.png", "f3": "covers/f3.jpg",
                                 "f4": "", "f5": "", "f6": ""})
        self.assertEqual(jload(d, "covers", "not_read.json"), {"f4": "HTTP 403", "f5": "HTTP 429"})
        tiles = dict((t["post_id"], (t["cover"], t["why"])) for t in jload(d, "covers_sheet.json")["tiles"])
        self.assertEqual(tiles["f4"], ("not read", "HTTP 403"))
        self.assertEqual(tiles["f6"], ("not read", "no cover saved"))
        self.assertEqual(tiles["f3"], ("read", None))
        code, out = run("covers_sheet.py", d, "--fetch")
        self.assertIn("covers: 0 saved now, 3 already saved, 2 not read", out)
        lim = dict((x["what"], x["why"]) for x in page_kit.run_limits("account", d))
        self.assertEqual(lim.get("Covers"), "2 not saved: HTTP 403 1, HTTP 429 1")


# ---------------------------------------------------------------------------------------------- 9. seeds

YTDLP_SEEDS = r'''
import json, sys
args = sys.argv[1:]
url = args[-1]
if "--flat-playlist" in args:
    h = url.split("/@", 1)[1].split("/", 1)[0]
    if h == "seed_gone":
        sys.stderr.write("ERROR: [youtube:tab] @seed_gone: This channel does not exist.\n")
        sys.exit(1)
    ids = {"seed_found": ["aaa"], "seed_quiet": ["bbb"], "seed_empty": []}[h]
    print(json.dumps({"entries": [{"id": i, "url": "https://www.youtube.com/shorts/" + i} for i in ids]}))
else:
    print(json.dumps({"id": url[-3:], "timestamp": {"aaa": 1794000000, "bbb": 1786000000}[url[-3:]]}))
'''


class Seeds(unittest.TestCase):
    def test_seeds_checked_named_and_not_counted(self):
        d = copy("niche_main")
        nj = jload(d, "niche.json")
        nj["seed_accounts"] = [{"network": "youtube", "handle": h} for h in ("seed_found", "seed_quiet", "seed_gone", "seed_empty")]
        nj["seed_accounts"].append({"network": "x", "handle": "seed_on_x"})
        jsave(os.path.join(d, "niche.json"), nj)
        code, out = run(os.path.join("readers", "ytdlp_reader.py"), "seeds", d, env=fake_tool("yt-dlp", YTDLP_SEEDS))
        st = dict((s["handle"], s.get("status")) for s in jload(d, "niche.json")["seed_accounts"])
        self.assertEqual(st, {"seed_found": "found", "seed_quiet": "inactive", "seed_gone": "not_found",
                              "seed_empty": "inactive", "seed_on_x": None})
        self.assertIn("say so in the setup answer, by name, and go on with the rest: @seed_quiet (inactive), "
                      "@seed_gone (not found), @seed_empty (inactive)", out)
        code, out = run("validate.py", d, ok=(0, 1))
        self.assertIn("1 seeds are not checked yet", out)
        # A creator read whose posts are all before the window, and one reply among a creator's rows.
        q = os.path.join(d, "accounts", "youtube-seed_quiet")
        os.makedirs(q)
        rows = []
        for k in range(10):
            t = dt.datetime(2026, 7, 1, 15, tzinfo=dt.timezone.utc) + dt.timedelta(days=5 * k)
            rows.append({"post_id": "quiet_%02d" % k, "url": "https://www.youtube.com/shorts/quiet_%02d" % k,
                         "published_at": iso(t), "type": "video", "duration_s": 20, "caption": "An old Short %d" % k,
                         "views": 3000 + k, "likes": 100, "comments": 4, "source": "fixture"})
        acc = jload(d, "accounts", "youtube-tinyreels", "account.json")
        acc.update({"handle": "seed_quiet", "name": "Seed Quiet", "url": "https://www.youtube.com/@seed_quiet"})
        jsave(os.path.join(q, "account.json"), acc)
        with open(os.path.join(q, "posts.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=common.POST_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow(dict((k, "" if r.get(k) is None else r.get(k)) for k in common.POST_COLUMNS))
        tr_dir = os.path.join(d, "accounts", "youtube-tinyreels")
        with open(os.path.join(tr_dir, "posts.csv"), encoding="utf-8") as f:
            old = list(csv.DictReader(f))
        old.append(dict(old[-1], post_id="tiny_reply", caption="Thanks, glad it helped!", views="12", reply_to="a_viewer"))
        with open(os.path.join(tr_dir, "posts.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=common.POST_COLUMNS)
            w.writeheader()
            for r in old:
                w.writerow(dict((k, r.get(k) or "") for k in common.POST_COLUMNS))
        run("trends.py", d)
        tr = jload(d, "trends.json")
        self.assertEqual(tr["counts"]["creators_active"], tr["counts"]["creators"] - 1)
        self.assertEqual(tr["counts"]["replies_left_out"], 1)
        self.assertEqual([s["handle"] for s in tr["seeds"]["not_found"]], ["seed_gone"])
        self.assertEqual([s["handle"] for s in tr["seeds"]["inactive"]], ["seed_quiet", "seed_empty"])
        self.assertEqual([s["handle"] for s in tr["seeds"]["unchecked"]], ["seed_on_x"])
        self.assertNotIn("youtube-seed_quiet", [p["creator"] for p in tr["posts"] if p["in_window"]])
        run("radar.py", d)
        self.assertTrue(all("youtube-seed_quiet" not in [c["account"] for c in f["by_creator"]]
                            for f in jload(d, "radar.json")["formats"]))
        run("text_probe.py", d)
        shutil.copy(os.path.join(d, "findings.example.json"), os.path.join(d, "findings.json"))
        code, out = run("build_report.py", d)
        self.assertIn("(%d creators with posts in the window" % tr["counts"]["creators_active"], out)
        md = text(d, "NICHE.md")
        self.assertIn("- [MEASURED] Seed accounts: not found: @seed_gone", md)
        self.assertIn("- [MEASURED] Seed accounts: no posts in the window: @seed_quiet, @seed_empty", md)
        self.assertIn("- [MEASURED] Replies: 1 reply left out of the numbers (replies are not posts)", md)
        self.assertIn("| A voice sheet? | None in a niche run", md)
        rec = jload(d, "report_record.json")["report"]
        self.assertEqual(rec["read"]["creators"], tr["counts"]["creators_active"])


# ---------------------------------------------------------------------------------------------- 10. what was not read

class NotReadFromWhatHappened(unittest.TestCase):
    def test_limits_follow_the_run(self):
        h = "fixture_limits"
        rows = [x_row("p%02d" % i, i, "A plain post %d" % i, views=9000 + 11 * i, handle=h, own_media="none")
                for i in range(24)]
        rows += [x_row("t01", 30, "Here is how I price a first client \U0001F9F5", "thread", handle=h, own_media="none"),
                 x_row("t02", 31, "The whole story of my first year, 1/", "thread", handle=h, own_media="none"),
                 x_row("t03", 32, "Three lessons, one per part", "thread", handle=h, own_media="none",
                       parts=json.dumps(["Three lessons, one per part", "One: ship.", "Two: ask.", "Three: repeat."]))]
        rows += [x_row("k%02d" % i, 40 + i, "Slides on pricing, part %d" % i, "carousel", handle=h, own_media="images")
                 for i in range(3)]
        d = account_folder("limits", h, rows, sampled={"read": 30, "of": 180, "how": "spread across the window"})
        run("analyze.py", d)
        lim = dict((x["what"], x["why"]) for x in page_kit.run_limits("account", d))
        self.assertEqual(lim.get("Threads"), "2 threads came as their first part only (t01, t02): their length and "
                                             "their ask are not judged")
        self.assertEqual(lim.get("Carousel slides"), "3 of 3 carousel posts read by their cover only (the slides were "
                                                     "not saved)")
        self.assertEqual(lim.get("Sampled"), "@fixture_limits: 30 of its latest 180 posts, spread across the window")
        self.assertIn("Follower history", lim)
        for what in ("Speech in videos", "Videos not watched", "Covers", "Replies", "Seed accounts"):
            self.assertNotIn(what, lim)
        run("text_probe.py", d)
        with open(os.path.join(d, "posts_text.csv"), encoding="utf-8") as f:
            pt = dict((r["post_id"], r) for r in csv.DictReader(f))
        self.assertEqual(pt["t01"]["chars"], "")                         # one part cannot say the post's length
        self.assertNotEqual(pt["t03"]["chars"], "")
        firsts = [x for x in json.dumps(jload(d, "writing.json")).split('"post_id": ') if x.startswith('"t01"')]
        self.assertTrue(firsts and '"first_part_only": true' in firsts[0])

    def test_nothing_said_that_did_not_happen(self):
        d = copy("tenfold")
        run("analyze.py", d)
        lim = [x["what"] for x in page_kit.run_limits("account", d)]
        for what in ("Threads", "Carousel slides", "Sampled", "Replies", "Covers", "Videos not watched", "Speech in videos"):
            self.assertNotIn(what, lim)


if __name__ == "__main__":
    unittest.main()
