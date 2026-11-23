#!/usr/bin/env python3
"""Check your grouping of posts into formats before radar.py measures it. A tool for your judgement, not a classifier.

    python3 formats_check.py <run folder> [--write] [--json]

Reads formats.json (yours) and the window's posts (an account or post folder: analysis.json's window when present;
a niche folder: every creator folder, trends.json's window). Each format may carry, beside its posts:

  "examples": ["id1", "id2"]                   the posts you say show the format best
  "match": {"opens": ["^\\\\d+ (mistakes|ways)"],   regular expressions on the first line (any one is enough)
            "patterns": ["before and after"],     regular expressions on the whole caption (any one is enough)
            "types": ["video"],                   the post types it takes
            "min_s": 15, "max_s": 35}             the length range in seconds
  (a post matches when every condition given holds; case is ignored)

It prints, and writes formats_check.json:
- per format: its posts, the posts its match takes, three sample posts with their first lines, and the check of its
  examples: an example its own match does not take, or that is not among its posts, FAILS the run (exit 1);
- the posts two formats both take (by their posts or their match): decide which one each belongs to;
- the posts in no format, with the openers they repeat most (the first three words): a format you may have missed,
  or one-offs that stay out.
--write sets "posts" of each format that has a match to the posts its match takes, leaving out the posts another
format also takes (they are listed: put each where it belongs by hand). A format without a match is never touched.
Run it, fix what it shows, then radar.py.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, load_formats, load_posts, niche_creator_dirs, read_json, write_json  # noqa: E402


def first_line(text):
    for line in str(text or "").split("\n"):
        if line.strip():
            return line.strip()
    return ""


def window_posts(folder):
    """The posts a format is grouped from: the window's (the numbers' own window when they were run), else all."""
    posts, inw, ratio = [], None, {}
    if os.path.exists(os.path.join(folder, "niche.json")):
        tp = os.path.join(folder, "trends.json")
        if os.path.exists(tp):
            tr = read_json(tp)
            inw = set(p["post_id"] for p in tr.get("posts") or [] if p.get("in_window"))
            ratio = dict((p["post_id"], p.get("ratio")) for p in tr.get("posts") or [])
        for d in niche_creator_dirs(folder):
            for p in load_posts(os.path.join(folder, d)):
                p["account"] = d.split("/", 1)[1]
                posts.append(p)
    else:
        ap = os.path.join(folder, "analysis.json")
        if os.path.exists(ap):
            an = read_json(ap)
            inw = set(p["post_id"] for p in an.get("posts") or [] if p.get("in_window"))
            ratio = dict((p["post_id"], p.get("ratio")) for p in an.get("posts") or [])
        posts = load_posts(folder)
    if inw is not None:
        posts = [p for p in posts if p["post_id"] in inw]
    return posts, ratio


def compile_match(m, where):
    out = {}
    for k in ("opens", "patterns"):
        rx = []
        for s in (m or {}).get(k) or []:
            try:
                rx.append(re.compile(s, re.I))
            except re.error as e:
                die("%s.match.%s: %r is not a regular expression (%s)" % (where, k, s, e), 1)
        out[k] = rx
    out["types"] = [t.lower() for t in (m or {}).get("types") or []]
    out["min_s"], out["max_s"] = (m or {}).get("min_s"), (m or {}).get("max_s")
    return out


def matches(m, p):
    if m["opens"] and not any(r.search(first_line(p.get("caption"))) for r in m["opens"]):
        return False
    if m["patterns"] and not any(r.search(p.get("caption") or "") for r in m["patterns"]):
        return False
    if m["types"] and (p.get("type") or "") not in m["types"]:
        return False
    d = p.get("duration_s")
    if m["min_s"] is not None and (d is None or d < m["min_s"]):
        return False
    if m["max_s"] is not None and (d is None or d > m["max_s"]):
        return False
    return True


def opener(p):
    words = re.findall(r"[^\W_]+(?:['’][^\W_]+)?", first_line(p.get("caption")).lower())
    return " ".join(words[:3]) if words else None


def check(folder):
    fdoc = load_formats(folder)
    if not fdoc or not fdoc.get("formats"):
        die("formats.json is missing or has no formats: write your grouping first (references/radar.md)", 1)
    posts, ratio = window_posts(folder)
    P = dict((p["post_id"], p) for p in posts)
    rows, takes, problems = [], {}, []
    for i, f in enumerate(fdoc["formats"]):
        where = "formats.json:formats[%d] (%s)" % (i, f.get("id"))
        assigned = [x for x in f.get("posts") or [] if x in P]
        m = compile_match(f.get("match"), where) if f.get("match") else None
        matched = [p["post_id"] for p in posts if m and matches(m, p)]
        for x in set(assigned) | set(matched):
            takes.setdefault(x, []).append(f["id"])
        ex = f.get("examples") or []
        bad = []
        for x in ex:
            if x not in P:
                bad.append("%s is not a post of the window" % x)
            elif m and x not in matched:
                bad.append("%s does not fit the format's own match (first line: %r)" % (x, first_line(P[x].get("caption"))[:80]))
            elif not m and x not in assigned:
                bad.append("%s is not among its posts" % x)
        if bad:
            problems += ["%s: %s" % (f["id"], b) for b in bad]
        pick = sorted(set(assigned) | set(matched), key=lambda x: -(ratio.get(x) or 0))[:3]
        rows.append({"id": f["id"], "name": f.get("name"), "posts": len(assigned), "matched": len(matched) if m else None,
                     "only_by_hand": sorted(set(assigned) - set(matched)) if m else [],
                     "examples": ex, "examples_ok": not bad,
                     "samples": [{"post_id": x, "ratio": ratio.get(x), "first_line": first_line(P[x].get("caption"))[:120]}
                                 for x in pick]})
    overlaps = [{"post_id": x, "formats": fs, "first_line": first_line(P[x].get("caption"))[:120]}
                for x, fs in sorted(takes.items()) if len(set(fs)) > 1]
    none = [p for p in posts if p["post_id"] not in takes]
    openers = {}
    for p in none:
        o = opener(p)
        if o:
            openers.setdefault(o, []).append(p["post_id"])
    top = sorted(openers.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:10]
    return fdoc, {
        "schema": "rea-viral/formats-check@1", "posts_in_window": len(posts), "formats": rows, "overlaps": overlaps,
        "unassigned": {"posts": len(none), "top_openers": [{"opener": o, "posts": len(ids), "examples": ids[:3]}
                                                           for o, ids in top if len(ids) >= 2]},
        "problems": problems, "ok": not problems}


def write_back(folder, fdoc, res):
    overlap = set(o["post_id"] for o in res["overlaps"])
    posts, _ = window_posts(folder)
    for i, f in enumerate(fdoc["formats"]):
        if not f.get("match"):
            continue
        m = compile_match(f["match"], "formats.json:formats[%d]" % i)
        keep = [x for x in f.get("posts") or [] if x not in set(p["post_id"] for p in posts)]   # outside the window: kept
        f["posts"] = keep + [p["post_id"] for p in posts if matches(m, p) and p["post_id"] not in overlap]
    write_json(os.path.join(folder, "formats.json"), fdoc)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    fdoc, res = check(folder)
    write_json(os.path.join(folder, "formats_check.json"), res)
    if "--json" in argv:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("formats_check: %d formats over %d posts of the window" % (len(res["formats"]), res["posts_in_window"]))
        for r in res["formats"]:
            print("  %-26s %3d posts%s; examples %s" % (
                r["id"][:26], r["posts"], "" if r["matched"] is None else ", its match takes %d" % r["matched"],
                "ok" if r["examples_ok"] else "DO NOT FIT"))
            for s in r["samples"]:
                print("      %-14s %-7s %s" % (s["post_id"][:14], ("%.2fx" % s["ratio"]) if s["ratio"] is not None else "-", s["first_line"][:80]))
        print("  in two formats: %d" % len(res["overlaps"]))
        for o in res["overlaps"][:12]:
            print("      %-14s %s: %s" % (o["post_id"][:14], " + ".join(o["formats"]), o["first_line"][:70]))
        u = res["unassigned"]
        print("  in no format: %d; the openers they repeat: %s" % (
            u["posts"], "; ".join("%r x%d" % (t["opener"], t["posts"]) for t in u["top_openers"]) or "none"))
        for p in res["problems"]:
            print("  FAIL " + p)
    if "--write" in argv:
        write_back(folder, fdoc, res)
        print("formats.json: posts set from each match (the posts two formats take were left out: place them by hand)")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
