#!/usr/bin/env python3
"""One post, beside its own creator's usual: the numbers of a post run.

    python3 post_probe.py <post run folder> [--now ISO]

A post run folder is an account folder (account.json and posts.csv: the post itself plus its creator's recent posts)
with post.json naming the post ({"post_id": "...", "url": "..."}), and formats.json when you marked which of the
creator's posts share the post's format. Writes post_probe.json and, when the post's format is marked, its recipe
skeleton formats/<id>.md (radar.py's shape; the agent fills the beats from the deep read).

What it measures (MEASURED):
- the post against its creator's usual: the median of the creator's OTHER settled recent posts (from 60 days before
  the post on; 8 or more), so the ratio says
  how far this post beat its own creator, whatever its size; with fewer, views per follower, labelled the weaker basis;
  a post under the settling time (7 days; 3 on X and Threads) gets its ratio so far, a floor;
- its words (text_probe.py's features) beside the creator's usual: what it opens with, its shape and its ask, against
  how often the creator does the same, and what the creator's posts with and without each show;
- whether the creator repeats the format (the posts you marked in formats.json), and whether it is above the usual
  each time.
It does not say why the post worked: that is the agent's reading, from the deep read, written to findings.json.
"""
import datetime as dt
import os
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    SKILL_VERSION, account_read_at, die, iso, load_account, load_formats, load_posts, median, now_utc, parse_time,
    read_json, rnd, write_json,
)
import analyze  # noqa: E402
import radar  # noqa: E402
import text_probe as tp  # noqa: E402
import trends  # noqa: E402

INPUTS = ("account.json", "posts.csv", "post.json", "formats.json")


def run(folder):
    import validate
    rep = validate.validate(folder, inputs_only=True)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:20]]
        die("validate.py found %d error(s); fix them first:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    if not os.path.exists(os.path.join(folder, "post.json")):
        die("no post.json: write {\"post_id\": \"<the post's id>\", \"url\": \"<its link>\"} (references/post-run.md)")
    focus = read_json(os.path.join(folder, "post.json"))
    pid = str(focus.get("post_id")).strip()
    acc = load_account(folder)
    posts = load_posts(folder)
    read_at = account_read_at(acc)
    P = dict((p["post_id"], p) for p in posts)
    # The creator's usual comes from its recent posts, as in a niche run: from 60 days before the post on (30 days
    # of "window" before it, and the usual's 30 more). An old era of the channel must not set the bar: on a real
    # run (2026-11-16) a channel's 2025 posts made its best Short read 325x instead of 51x.
    anchor = P[pid]["published_at"] or read_at
    lo = anchor - dt.timedelta(days=30)
    summary = trends.creator_numbers(posts, acc, lo, read_at, trends.RULES, read_at)
    me = P[pid]
    scored = sorted([p for p in posts if p["status"] == "scored"], key=lambda p: -p["ratio"])
    rank = ([p["post_id"] for p in scored].index(pid) + 1) if pid in [p["post_id"] for p in scored] else None
    others_settled = sum(1 for p in posts if p["state"] == "settled" and p is not me)
    if me["basis"] == "own" and me["status"] == "scored":
        status, note = "ok", None
    elif me["status"] == "too_new":
        status = "too_new"
        note = ("The post is under %d days old: its views are still growing, so its ratio so far is a floor." %
                analyze.MIN_AGE_DAYS.get(acc.get("network"), analyze.DEFAULT_MIN_AGE_DAYS))
    elif me["basis"] == "followers":
        status = "weaker_basis"
        note = ("Only %d other settled posts of the creator were read (8 needed for its usual): the post is measured on "
                "views per follower, a weaker basis." % others_settled)
    else:
        status = "no_baseline"
        note = "The creator's usual could not be measured: read more of its recent posts (8 or more, settled)."
    post = {
        "post_id": pid, "url": me["url"], "published_at": iso(me["published_at"]), "type": me["type"],
        "duration_s": me["duration_s"], "views": me["views"], "likes": me["likes"], "comments": me["comments"],
        "metric": me["metric"], "basis": me["basis"], "usual": rnd(me["baseline"], 1), "usual_from_posts": me["baseline_n"],
        "ratio": rnd(me["ratio"], 3), "ratio_so_far": rnd(me["ratio_so_far"], 3),
        "views_per_follower": rnd(me["views_per_follower"], 4), "rank_among_creator": rank,
        "creator_scored": len(scored), "hit": bool(me["ratio"] is not None and me["ratio"] >= trends.RULES["hit_ratio"]),
        "cover_file": me["cover_file"] or None, "caption": (me["caption"] or "")[:1000],
    }
    words = words_beside_usual(posts, me)
    repeats, fmt = repeats_of(folder, posts, pid)
    out = {
        "schema": "rea-viral/post-probe@1",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": analyze.input_fingerprint(folder, INPUTS),
        "status": status, "status_note": note,
        "creator": {"network": acc.get("network"), "handle": acc.get("handle"), "name": acc.get("name"),
                    "usual_since": summary["usual_since"], "older_posts_left_out": summary["older_posts_left_out"],
                    "url": acc.get("url"), "followers": summary["followers"], "followers_exact": summary["followers_exact"],
                    "posts_read": summary["posts_read"], "settled": summary["settled"], "scored": summary["scored"],
                    "hits": summary["hits"], "hit_rate": summary["hit_rate"], "usual": rnd(summary["usual"], 1),
                    "span": summary["span"], "metric": summary["metric"]},
        "post": post,
        "words": words,
        "repeats": repeats,
        "creator_posts": [{"post_id": p["post_id"], "url": p["url"], "published_at": iso(p["published_at"]),
                           "ratio": rnd(p["ratio"], 3), "status": p["status"], "views": p["views"],
                           "cover_file": p["cover_file"] or None, "caption": (p["caption"] or "")[:160]}
                          for p in sorted(posts, key=lambda p: (p["published_at"] is None, p["published_at"] or read_at))],
    }
    written = None
    if fmt is not None:
        out["recipe"] = "formats/%s.md" % fmt["id"]
        written = write_recipe(folder, fmt, posts, repeats)
    return out, written


def words_beside_usual(posts, me):
    """The post's words, and how often the creator does the same in its other posts."""
    words = tp.load_words()
    feats = {}
    for p in posts:
        feats[p["post_id"]] = tp.mark_first_part_only(p, tp.text_features(p.get("parts") or [p.get("caption") or ""],
                                                                          p.get("lang"), words, p.get("author_replies")))
    mine = feats[me["post_id"]]
    if mine.get("empty"):
        return {"status": "no_text", "note": "The post has no words to read (no caption or title)."}
    others = [p for p in posts if p is not me and not feats[p["post_id"]].get("empty")]
    scored = [p for p in others if p["status"] == "scored"]
    flags = []
    for fid, group, label, _ in tp.BOOL_FEATURES:
        v = mine.get(fid)
        known = [p for p in others if feats[p["post_id"]].get(fid) is not None]
        used = sum(1 for p in known if feats[p["post_id"]].get(fid) is True)
        share = (used / float(len(known))) if known else None
        w = [p["ratio"] for p in scored if feats[p["post_id"]].get(fid) is True]
        wo = [p["ratio"] for p in scored if feats[p["post_id"]].get(fid) is False]
        rec = {"id": fid, "group": group, "label": label, "post": v, "creator_uses": used, "creator_known": len(known),
               "creator_share": rnd(share, 3),
               "creator_with": {"posts": len(w), "lift": rnd(median(w), 3) if w else None},
               "creator_without": {"posts": len(wo), "lift": rnd(median(wo), 3) if wo else None},
               "evidence": "MEASURED"}
        if v is True and share is not None and share <= 0.25:
            rec["differs"] = "the post has it; the creator rarely does (%d of %d other posts)" % (used, len(known))
        elif v is False and share is not None and share >= 0.75:
            rec["differs"] = "the creator usually does (%d of %d other posts); this post does not" % (used, len(known))
        if len(w) < 6 or len(wo) < 6:
            rec["note"] = "few posts on one side: a lead at most, never a finding about the creator"
        if v is True or rec.get("differs"):
            flags.append(rec)
    nums = []
    for fid, group, label in tp.NUM_FEATURES:
        v = mine.get(fid)
        vals = sorted(feats[p["post_id"]].get(fid) for p in others if feats[p["post_id"]].get(fid) is not None)
        if v is None or not vals:
            continue
        q = tp.quantiles(vals)
        rec = {"id": fid, "group": group, "label": label, "post": v, "creator_median": q["median"],
               "creator_usual": [q["p10"], q["p90"]], "creator_posts": q["posts"], "evidence": "MEASURED"}
        if q["p10"] is not None and (rnd(float(v), 2) < q["p10"] or rnd(float(v), 2) > q["p90"]):   # as rounded as the range
            rec["differs"] = "outside the creator's usual range (8 in 10 of its posts)"
        nums.append(rec)
    return {"status": "ok", "language": mine.get("language"), "language_covered": mine.get("language_covered"),
            "first_part_only": bool(mine.get("first_part_only")),
            "first_line": mine.get("first_line"),
            "openings": [k for k, x in mine.items() if k.startswith("opens_") and x is True],
            "ask": {"kinds": mine.get("ask_kinds"), "where": mine.get("ask_where"), "phrases": mine.get("ask_phrases")},
            "flags": flags, "numbers": nums,
            "note": ("Thread: first part only (the reader gave no other part), so its length and its ask are not "
                     "judged. " if mine.get("first_part_only") else "") +
                    "Beside the creator's other %d posts with words. With one creator's posts most differences are "
                    "leads, not findings (6 posts on each side are needed)." % len(others)}


def repeats_of(folder, posts, pid):
    fdoc = load_formats(folder) or {}
    P = dict((p["post_id"], p) for p in posts)
    for f in fdoc.get("formats") or []:
        ids = [i for i in f.get("posts") or [] if i in P]
        if pid not in ids:
            continue
        others = [P[i] for i in ids if i != pid]
        sc = [p for p in others if p["status"] == "scored"]
        rs = [p["ratio"] for p in sc]
        above = sum(1 for r in rs if r >= 1.0)
        hits = sum(1 for r in rs if r >= trends.RULES["hit_ratio"])
        rep = {"format": f["id"], "name": f.get("name"), "times": len(others), "scored": len(sc),
               "above_usual": above, "hits": hits, "lift_others": rnd(median(rs), 3) if rs else None,
               "every_time": bool(sc) and above == len(sc),
               "posts": [{"post_id": p["post_id"], "url": p["url"], "published_at": iso(p["published_at"]),
                          "ratio": rnd(p["ratio"], 3), "status": p["status"]} for p in
                         sorted(others, key=lambda p: (p["published_at"] is None, p["published_at"]))],
               "evidence": "MEASURED",
               "label": ("repeated %d more time%s in the %d posts read; above its usual %d of %d scored times, at 2x or "
                         "more %d" % (len(others), "" if len(others) == 1 else "s", len(posts), above, len(sc), hits))
               if others else "not repeated in the %d posts read" % len(posts)}
        return rep, f
    return ({"format": None, "label": "not marked: write formats.json with the post's format and the creator's other "
                                      "posts of the same container, then run post_probe.py again"}, None)


def write_recipe(folder, f, posts, repeats):
    P = dict((p["post_id"], p) for p in posts)
    ids = [i for i in f.get("posts") or [] if i in P]
    sc = sorted([P[i] for i in ids if P[i]["status"] == "scored"], key=lambda p: -p["ratio"])
    rs = [p["ratio"] for p in sc]
    pn, n_probed = radar.probe_numbers(folder, ids)
    durs = [P[i]["duration_s"] for i in ids if P[i]["duration_s"] is not None]
    rec = {
        "id": f["id"], "name": f.get("name"),
        "container": {k: f.get(k) for k in ("hook", "structure", "look", "length")},
        "posts_total": len(ids), "posts_scored": len(sc),
        "share": rnd(len(ids) / float(len(posts)), 3) if posts else 0.0,
        "lift": rnd(median(rs), 3) if rs else None,
        "hit_rate": rnd(sum(1 for r in rs if r >= 2.0) / float(len(rs)), 3) if rs else None,
        "direction": None, "direction_label": None,
        "follower_pull": {"level": "none", "evidence": None, "value": None, "label": "not measured in a post run"},
        "effort": f.get("effort"), "quadrant": "post", "quadrant_name": "One post's format (not placed on a chart)",
        "length_s_median": rnd(median(durs), 1), "probe": pn, "videos_read": n_probed,
        "examples": [{"post_id": p["post_id"], "url": p["url"], "ratio": p["ratio"]} for p in sc[:3]],
    }
    return radar.write_recipe(folder, rec)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    if "--now" in argv:
        os.environ["REA_NOW"] = argv[argv.index("--now") + 1]
        parse_time(os.environ["REA_NOW"])
    out, written = run(folder)
    write_json(os.path.join(folder, "post_probe.json"), out)
    p, c = out["post"], out["creator"]
    if p["ratio"] is not None:
        line = "%sx its creator's usual (the median of %d other posts: %s %s); #%s of %d scored posts" % (
            ("%.2f" % p["ratio"]), p["usual_from_posts"] or 0, p["usual"], p["metric"], p["rank_among_creator"],
            p["creator_scored"])
    elif p["ratio_so_far"] is not None:
        line = "%sx its creator's usual so far (too new: a floor)" % ("%.2f" % p["ratio_so_far"])
    elif p["views_per_follower"] is not None:
        line = "%s views per follower (weaker basis)" % p["views_per_follower"]
    else:
        line = "no basis"
    print("post_probe.json: status %s; @%s's post %s: %s" % (out["status"], c["handle"], p["post_id"], line))
    if out.get("status_note"):
        print("  " + out["status_note"])
    print("  repeats: %s" % out["repeats"]["label"])
    w = out["words"]
    if w.get("status") == "ok":
        print("  first line: %r; opens with: %s" % (w["first_line"], ", ".join(w["openings"]) or "nothing counted"))
        for f in w["flags"]:
            if f.get("differs"):
                print("  differs: %s: %s" % (f["label"], f["differs"]))
    if written:
        print("  %s %s" % ("wrote" if written[1] else "updated", os.path.relpath(written[0], folder)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
