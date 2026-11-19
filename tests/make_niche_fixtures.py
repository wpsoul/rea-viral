#!/usr/bin/env python3
"""Make the REA Viral niche and post fixtures. Each has its answer built in (KNOWN.json beside it).

    python3 make_niche_fixtures.py [--out DIR]     (default: a folder you name; nothing is written into the repo)

Deterministic (a fixed random seed). YouTube Shorts-like rows, read 2026-11-16 12:00 UTC, window 2026-10-14 to
2026-11-15 (posts after 2026-11-09 12:00 are too new to score).

niche_main: 11 creators of a made-up niche ("AI video editing tools").
  - before-after-split RISES across 5 creators (c2..c6): early-half posts at 1.2x their own usual, late-half posts at
    2.8x and 3.4x; used more in the late half. Must come out a format of the niche, Scale it, rising.
  - studio-desk-review is ONE creator's habit (c1, a big studio): 6 posts at 4x. Must NOT be a format of the niche.
  - prompt-reveal FADES across 4 creators (c7..c10): early posts at 2.4x, late posts at 0.55x. Corner Fading, fading.
  - posts opening with a QUESTION lift across 8 creators (2 each, about 2.6x). Must come out as the niche's lifting
    opening (with has_question, the same posts). c1's habit posts all open with a number: that lifts on c1's posts
    alone, so it must come out "few creators", never a finding of the niche.
  - c6 (a small creator, usual 3,000 views) has one real outlier at 6x (18,000 views); c1's ordinary posts get about
    500,000 views. The small outlier must rank first, above every post of c1.
  - c11 has only 5 posts: no usual of its own; scored on views per follower (the weaker basis), one lead at 3.5x its
    followers, inside before-after-split. It must never count as one of the format's creators.
  - every creator has 2 posts under 7 days old: listed as too new, never ranked.
post_c3: the post run on c3's best before-after-split post (3.4x), with c3's 40 posts and its format marked in
  formats.json: the creator repeats the format 2 more times, above its usual both times, a hit once.
"""
import csv
import datetime as dt
import json
import os
import random
import shutil
import struct
import sys
import zlib

POST_HEADER = ["post_id", "url", "published_at", "type", "duration_s", "caption", "views", "likes", "comments", "shares",
               "saves", "cover_url", "cover_file", "video_file", "transcript_file", "sound", "is_pinned", "is_paid",
               "collaborators", "read_at", "source"]
READ_AT = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)
WIN_FROM = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)
WIN_TO = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc)
MID = WIN_FROM + (WIN_TO + dt.timedelta(days=1) - WIN_FROM) / 2   # 2026-10-30 12:00
TOO_NEW_AFTER = READ_AT - dt.timedelta(days=7)

CREATORS = [  # id, handle, usual views, followers
    ("c1", "bigstudio", 500000, 2400000),
    ("c2", "cutlab", 20000, 90000),
    ("c3", "frameforge", 8000, 30000),
    ("c4", "motionnest", 40000, 150000),
    ("c5", "editpilot", 12000, 52000),
    ("c6", "tinyreels", 3000, 9000),
    ("c7", "promptpix", 15000, 61000),
    ("c8", "renderroom", 5000, 21000),
    ("c9", "clipcraft", 25000, 110000),
    ("c10", "aistoryboard", 60000, 240000),
]
COLOURS = {"before-after-split": (51, 239, 171), "studio-desk-review": (125, 185, 255), "prompt-reveal": (243, 197, 107),
           None: (90, 96, 104)}

ORDINARY = [
    "My editing setup for short clips, step by step",
    "This plugin saves me an hour on every video",
    "Color grading a city shot in under a minute",
    "The keyframe trick nobody showed me sooner",
    "Testing a new AI tool on my old footage",
    "Five seconds of motion design, start to finish",
    "Cleaning up shaky footage with one setting",
    "A quick look at the timeline of this edit",
    "Turning a flat clip into something cinematic",
    "Masking a moving subject the easy way",
]
QUESTIONS = [
    "Why does this edit feel so smooth to watch?",
    "Can an AI tool really match a hand-made cut?",
    "What happens when you speed ramp a still photo?",
    "Is this the fastest way to caption a short?",
    "Would you guess this shot was made by AI?",
    "How long did this transition actually take me?",
]
NUMBERED = [
    "3 things I changed in this studio edit",
    "5 settings we use on every client video",
    "2 mistakes that slow down a studio edit",
    "4 tools on our desk this week",
]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def png(path, rgb, w=90, h=160):
    """A tiny solid PNG cover (no ffmpeg needed)."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in header})


def write_recipe(folder, rec, prose):
    """A filled recipe, as an agent leaves it after the deep read: radar.py keeps its beats and rewrites only the
    measured parts, so the hand-over rows carry beats (the planner's model checks their shape)."""
    os.makedirs(os.path.join(folder, "formats"), exist_ok=True)
    with open(os.path.join(folder, "formats", rec["id"] + ".md"), "w", encoding="utf-8") as f:
        f.write("# %s\n\n```json rea-recipe\n%s\n```\n\n<!-- rea:measured:start -->\n<!-- rea:measured:end -->\n\n%s\n"
                % (rec["name"], json.dumps(rec, indent=2), prose))


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def account(handle, followers, n_posts):
    return {
        "schema": "rea-viral/account@2", "network": "youtube", "handle": handle, "name": handle.title(),
        "url": "https://www.youtube.com/@%s" % handle, "bio": "A made-up creator for tests.", "link": None,
        "followers": followers, "followers_exact": False, "following": None, "posts_total": n_posts,
        "verified": False, "private": False, "read_at": iso(READ_AT),
        "window": {"from": WIN_FROM.strftime("%Y-%m-%d"), "to": WIN_TO.strftime("%Y-%m-%d")},
        "follower_history": [], "sources": [{"what": "recent posts", "via": "make_niche_fixtures.py", "cost_usd": 0}],
        "found_by": "search", "spend_ceiling_usd": 0.4,
    }


def make_niche(out):
    rng = random.Random(7)
    d = os.path.join(out, "niche_main")
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "accounts"))
    known = {"formats": {}, "creators_behind": {}, "small_outlier": None, "big_creator": "youtube-bigstudio",
             "weaker_basis_creator": "youtube-freshchannel", "lead": None, "too_new": [], "question_posts": []}
    fmt_posts = {"before-after-split": [], "studio-desk-review": [], "prompt-reveal": []}
    found = []
    # 40 posts per creator, one every 40 hours back from 2026-11-15 18:00: about 4 too new, 16 scored in the window.
    for ci, (cid, handle, usual, followers) in enumerate(CREATORS):
        times = [dt.datetime(2026, 11, 15, 18, 0, tzinfo=dt.timezone.utc) - dt.timedelta(hours=40 * k + 3 * ci)
                 for k in range(40)]
        times.sort()
        inw = [t for t in times if WIN_FROM <= t <= WIN_TO + dt.timedelta(days=1) and t < TOO_NEW_AFTER]
        early = [t for t in inw if t < MID]
        late = [t for t in inw if t >= MID]
        plan = {}
        n = int(cid[1:])
        if 2 <= n <= 6:      # the rising format: 1 early post at 1.2x, 2 late posts at 2.8x and 3.4x
            plan[early[0]] = ("before-after-split", 1.2)
            plan[late[-1]] = ("before-after-split", 3.4)
            plan[late[-2]] = ("before-after-split", 2.8)
        if 7 <= n <= 10:     # the fading format: 2 early posts at 2.4x, 1 late at 0.55x
            plan[early[0]] = ("prompt-reveal", 2.4)
            plan[early[1]] = ("prompt-reveal", 2.4)
            plan[late[-1]] = ("prompt-reveal", 0.55)
        if n == 1:           # one creator's habit: 6 posts at 4x
            for t in inw[:6]:
                plan[t] = ("studio-desk-review", 4.0)
        if n == 6:           # the small creator's real outlier
            free = [t for t in inw if t not in plan]
            plan[free[0]] = ("outlier", 6.0)
        if 2 <= n <= 9:      # 2 question-led posts at about 2.6x, not in any format
            free = [t for t in inw if t not in plan]
            for t in (free[1], free[-2]):
                plan[t] = ("question", 2.6)
        rows = []
        cdir = os.path.join(d, "accounts", "youtube-" + handle)
        os.makedirs(os.path.join(cdir, "covers"))
        for k, t in enumerate(times):
            pid = "%s_%02d" % (handle[:6], k)
            kind, ratio = plan.get(t, (None, 1.0))
            noise = 1.0 if kind else rng.uniform(0.82, 1.2)
            views = int(usual * ratio * noise)
            if kind in ("before-after-split", "prompt-reveal", "studio-desk-review"):
                fmt_posts[kind].append(pid)
                cap = {"before-after-split": "Before and after: the edit that saved this clip",
                       "prompt-reveal": "Prompt reveal: what I typed to get this shot",
                       "studio-desk-review": rng.choice(NUMBERED)}[kind]
                fmt = kind
            elif kind == "question":
                cap = QUESTIONS[(n + len(known["question_posts"])) % len(QUESTIONS)]
                known["question_posts"].append(pid)
                fmt = None
            else:
                cap = rng.choice(ORDINARY)
                fmt = None
            if kind == "outlier":
                known["small_outlier"] = pid
            if t >= TOO_NEW_AFTER:
                known["too_new"].append(pid)
            cover = "covers/%s.png" % pid
            png(os.path.join(cdir, cover), COLOURS.get(fmt, COLOURS[None]))
            rows.append({"post_id": pid, "url": "https://www.youtube.com/shorts/%s" % pid, "published_at": iso(t),
                         "type": "video", "duration_s": 24 if fmt != "studio-desk-review" else 55, "caption": cap,
                         "views": views, "likes": int(views * 0.04), "comments": int(views * 0.002),
                         "cover_file": cover, "source": "fixture"})
            if kind in ("before-after-split", "question", "outlier") and t >= MID:
                found.append({"post_id": pid, "url": rows[-1]["url"], "network": "youtube", "account": handle,
                              "found_by": "search", "query": "ai video editing"})
        write_csv(os.path.join(cdir, "posts.csv"), POST_HEADER, rows)
        write_json(os.path.join(cdir, "account.json"), account(handle, followers, len(rows)))
    # c11: too few posts for a usual of its own; scored on views per follower (the weaker basis).
    cdir = os.path.join(d, "accounts", "youtube-freshchannel")
    os.makedirs(os.path.join(cdir, "covers"))
    rows = []
    for k, (day, views) in enumerate([(16, 800), (20, 900), (2, 3500), (5, 700), (7, 600)]):
        t = dt.datetime(2026, 10 if day > 10 else 11, day, 15, 0, tzinfo=dt.timezone.utc)
        pid = "fresh_%02d" % k
        png(os.path.join(cdir, "covers/%s.png" % pid), COLOURS[None])
        rows.append({"post_id": pid, "url": "https://www.youtube.com/shorts/%s" % pid, "published_at": iso(t),
                     "type": "video", "duration_s": 22, "caption": "Before and after: my first AI edit" if views == 3500 else
                     "Trying AI editing for the first time", "views": views, "likes": views // 25, "comments": 3,
                     "cover_file": "covers/%s.png" % pid, "source": "fixture"})
        if views == 3500:
            fmt_posts["before-after-split"].append(pid)
            known["lead"] = pid
    write_csv(os.path.join(cdir, "posts.csv"), POST_HEADER, rows)
    write_json(os.path.join(cdir, "account.json"), account("freshchannel", 1000, 5))
    write_csv(os.path.join(d, "found.csv"), ["post_id", "url", "network", "account", "found_by", "query"], found)
    write_json(os.path.join(d, "niche.json"), {
        "schema": "rea-viral/niche@1", "name": "AI video editing tools", "slug": "ai-video-editing",
        "question": "what works now in AI video editing on YouTube Shorts",
        "words": ["ai video editing", "motion design"], "tags": ["#aivideo"], "seed_accounts": [],
        "networks": ["youtube"], "read_at": iso(READ_AT),
        "window": {"from": WIN_FROM.strftime("%Y-%m-%d"), "to": WIN_TO.strftime("%Y-%m-%d")},
        "caps": {"creators": 12, "posts": 300, "baseline_posts": 24}, "spend_ceiling_usd": 0.4,
        "sources": [{"what": "search and creators' recent posts", "via": "make_niche_fixtures.py", "cost_usd": 0}],
        "user": {"handle": None, "niche": None},
    })
    write_json(os.path.join(d, "formats.json"), {"schema": "rea-viral/formats@1", "formats": [
        {"id": "before-after-split", "name": "Before / after split", "hook": "the finished shot first, then the raw clip",
         "structure": "after, before, the one change, after again", "look": "split screen with a wipe", "length": "20-30 s",
         "effort": "low", "basis": "covers and frames of the late-half hits of five creators", "posts": fmt_posts["before-after-split"]},
        {"id": "studio-desk-review", "name": "Studio desk review", "hook": "a number of tools on a desk",
         "structure": "numbered list over desk shots", "look": "top-down desk", "length": "50-60 s",
         "effort": "medium", "basis": "one studio's series", "posts": fmt_posts["studio-desk-review"]},
        {"id": "prompt-reveal", "name": "Prompt reveal", "hook": "the result, then the prompt typed on screen",
         "structure": "result, prompt, result", "look": "screen recording", "length": "20-30 s",
         "effort": "low", "basis": "covers of four creators", "posts": fmt_posts["prompt-reveal"]},
    ]})
    write_json(os.path.join(d, "findings.example.json"), {
        "schema": "rea-viral/findings@1",
        "headline": {"text": "Before / after splits are rising across the niche; prompt reveals are fading.",
                     "evidence": "INFERRED", "basis": "radar.json: the rising format's lift and direction; the fading one's direction"},
        "formats": [{"title": "Before / after split", "text": "Lifts over each creator's own usual, across 5 creators.",
                     "evidence": "MEASURED", "from": "radar.json#formats.before-after-split.lift"},
                    {"title": "Prompt reveal", "text": "Worked early in the window and fades in the later half.",
                     "evidence": "MEASURED", "from": "radar.json#formats.prompt-reveal.direction"}],
        "did_not_work": [{"title": "Prompt reveals are fading", "text": "Four creators use it; its later posts sit far "
                          "under its earlier ones.", "evidence": "MEASURED",
                          "from": "radar.json#formats.prompt-reveal.direction"}],
        "hooks": [{"text": "Question-led first lines sit on the niche's hits.", "evidence": "SEEN",
                   "posts": known["question_posts"][:2], "quote": ["?"]}],
        "creators": [{"text": "A small creator's outlier ranks first.", "evidence": "MEASURED",
                      "from": "trends.json#creators.youtube-tinyreels.best.ratio"}],
        "plays": [{"title": "Make a before / after split this week", "what": "Your own raw clip first, then the edit.",
                   "evidence": "MEASURED", "from": "radar.json#formats.before-after-split.lift", "effort": "low",
                   "first_result": "views against your own usual after 7 days", "dont_copy": "their footage",
                   "prompt": "Make a before / after split of my clip."}],
        "not_read": [{"what": "Follower history", "why": "no source gives daily counts"}],
    })
    write_recipe(d, {
        "schema": "rea-viral/recipe@1", "id": "before-after-split", "name": "Before / after split", "length_s": 21,
        "beats": [{"at": 0.0, "what": "hook", "text": "the finished shot first"},
                  {"at": 1.5, "what": "turn", "text": "a hard cut to the raw clip", "cut": True},
                  {"at": 12.0, "what": "payoff", "text": "the finished shot again, full screen"}],
        "cuts_per_10s": 1.4, "words_per_minute": None, "hook_pattern": "the finished shot, then the raw clip",
        "caption_style": "none", "sound": "a trending beat", "ask": "none", "examples": [], "voice": "hooks.md",
        "tolerance": {"length_pct": 10, "cut_s": 0.25, "cuts_per_10s": 1.0, "words_per_minute_pct": 15}},
        "## Beats\n\nSeen at two creators (cutlab_35, tinyre_35): the finished shot, a hard cut to the raw clip, the "
        "finished shot again.")
    known["formats"] = {"before-after-split": {"quadrant": "scale_it", "direction_label": "rising", "creators": 5,
                                               "niche_format": True},
                        "studio-desk-review": {"quadrant": "too_few", "scope_status": "creator habit", "creators": 1,
                                               "niche_format": False},
                        "prompt-reveal": {"quadrant": "fading", "direction_label": "fading", "creators": 4,
                                          "niche_format": True}}
    known["lifting_openings"] = ["has_question", "opens_question"]
    known["habit_opening"] = "opens_number"
    write_json(os.path.join(d, "KNOWN.json"), known)
    return d, known


def make_post(out, niche_dir):
    """The post run: c3's best before-after-split post with c3's 24 recent posts."""
    d = os.path.join(out, "post_c3")
    if os.path.exists(d):
        shutil.rmtree(d)
    shutil.copytree(os.path.join(niche_dir, "accounts", "youtube-frameforge"), d)
    fmt = json.load(open(os.path.join(niche_dir, "formats.json"), encoding="utf-8"))
    mine = set()
    with open(os.path.join(d, "posts.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = set(r["post_id"] for r in rows)
    for fm in fmt["formats"]:
        if fm["id"] == "before-after-split":
            mine = [p for p in fm["posts"] if p in ids]
    best = max(mine, key=lambda p: int([r for r in rows if r["post_id"] == p][0]["views"]))
    write_json(os.path.join(d, "post.json"), {"schema": "rea-viral/post@1", "post_id": best,
                                              "url": "https://www.youtube.com/shorts/%s" % best,
                                              "given_as": "https://youtube.com/shorts/%s?feature=share" % best})
    write_json(os.path.join(d, "formats.json"), {"schema": "rea-viral/formats@1", "formats": [
        {"id": "before-after-split", "name": "Before / after split", "hook": "the finished shot first",
         "structure": "after, before, the change, after", "look": "split screen", "length": "20-30 s", "effort": "low",
         "basis": "the post and its creator's posts of the same container", "posts": mine}]})
    write_json(os.path.join(d, "KNOWN.json"), {"post_id": best, "ratio_about": 3.4, "repeats": len(mine) - 1,
                                               "above_usual": len(mine) - 1, "hits_other": 1})
    return d


def main(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    if not out:
        sys.stderr.write("usage: make_niche_fixtures.py --out DIR\n")
        return 2
    os.makedirs(out, exist_ok=True)
    d, known = make_niche(out)
    p = make_post(out, d)
    print(json.dumps({"niche_main": d, "post_c3": p, "small_outlier": known["small_outlier"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
