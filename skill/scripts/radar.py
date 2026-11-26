#!/usr/bin/env python3
"""Formats, measured: one account's Format map, or the formats of a niche across many creators.

    python3 radar.py <run folder>       an account or post folder: the Format map (scope "account")
    python3 radar.py <niche folder>     a niche folder (niche.json): the formats of the niche (scope "shared"; see the
                                        SHARED_RULES below and references/radar.md, "The formats of a niche")

Reads formats.json (the agent's grouping of posts into formats, after the deep read) and recomputes the numbers with
analyze.py, so they are never stale. Writes radar.json and one recipe file per format, formats/<id>.md: a new file
gets a skeleton; an existing one keeps everything the agent wrote and only its measured parts are replaced (the JSON
block's "measured" object and the table between the rea:measured markers).

Per format (definitions in references/radar.md): posts and share of the window, lift (median of its posts' ratios to
their own baselines), hit rate (share at 2x or more), direction (median ratio of its last third against its first
third, 6+ posts: rising, steady or fading), follower pull (at the level the data allows), effort (the agent's call),
and the corner of the chart. The corner is where the format SITS, nothing else (across: how often, split at 15% of the
window's posts; up: lift, split at 1x, the account's own usual); the direction is the arrow, never the corner:
  Scale it  = often and lift >= 1 (top right)
  Underused = rare and lift >= 1 (top left)
  Overused  = often and lift under 1 (bottom right; called Fading before 0.4.1, which could read against a rising arrow)
  Drop      = rare and lift under 1 (bottom left)
Under 20 dated posts in the window the radar lists the posts and calls no format. A format with fewer than 3 scored
posts is listed but not placed.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    SKILL_VERSION, die, iso, load_formats, median, now_utc, read_json, rnd, write_json, write_text,
)
import analyze  # noqa: E402

RULES = {
    "often_share": 0.15,
    "strong_lift": 1.0,
    "fading_direction": 0.75,      # direction under this: fading (0.4.1; was "weakening_direction")
    "rising_direction": 1.33,
    "hit_ratio": 2.0,
    "min_posts_window": 20,
    "min_posts_format": 3,
    "min_posts_direction": 6,
}
MEASURED_START = "<!-- rea:measured:start -->"
MEASURED_END = "<!-- rea:measured:end -->"
RECIPE_RE = re.compile(r"```json rea-recipe\s*\n(.*?)\n```", re.S)


def quadrant(f):
    """Where the format sits on the chart: position only (share x lift). The direction never moves it."""
    if f["posts_scored"] < RULES["min_posts_format"]:
        return "too_few"
    often = f["share"] >= RULES["often_share"]
    strong = f["lift"] >= RULES["strong_lift"]
    if not strong:
        return "overused" if often else "drop"
    return "scale_it" if often else "underused"


QUADRANT_NAMES = {"scale_it": "Scale it", "underused": "Underused", "overused": "Overused", "drop": "Drop",
                  "too_few": "Too few posts to place"}


def probe_numbers(folder, ids):
    out = {"length_s": [], "cuts_per_10s": [], "words_per_minute": [], "first_cut_s": []}
    read = 0
    for pid in ids:
        p = os.path.join(folder, "videos", pid, "probe.json")
        if not os.path.exists(p):
            continue
        try:
            d = read_json(p)
        except ValueError:
            continue
        if not d.get("read"):
            continue  # a "not read" stub measures nothing
        read += 1
        m = d.get("measured") or {}
        for k in out:
            if m.get(k) is not None:
                out[k].append(m[k])
    return dict((k, rnd(median(v), 2)) for k, v in out.items()), read


def measure(folder, an, fdoc):
    posts = dict((p["post_id"], p) for p in an["posts"])
    inw = [p for p in an["posts"] if p["in_window"]]
    n_window = len(inw)
    formats = []
    owned = set()
    for f in fdoc.get("formats") or []:
        ids = [i for i in f.get("posts") or [] if i in posts]
        owned |= set(ids)
        win = [posts[i] for i in ids if posts[i]["in_window"]]
        sc = sorted([p for p in win if p["ratio"] is not None], key=lambda p: p["published_at"])
        ratios = [p["ratio"] for p in sc]
        lift = median(ratios)
        hit = (sum(1 for r in ratios if r >= RULES["hit_ratio"]) / float(len(ratios))) if ratios else None
        direction = None
        if len(sc) >= RULES["min_posts_direction"]:
            t = len(sc) // 3
            a, b = median(ratios[:t]), median(ratios[-t:])
            direction = (b / a) if a else None
        dlabel = None
        if direction is not None:
            dlabel = "rising" if direction >= RULES["rising_direction"] else (
                "fading" if direction < RULES["fading_direction"] else "steady")
        meas = [p for p in sc if (p["followers"] or {}).get("level") in ("measured", "watched")]
        est = [p for p in sc if (p["followers"] or {}).get("level") == "estimated"]
        if sc and len(meas) * 2 >= len(sc):
            val = sum(max(0, p["followers"].get("excess_72h") or 0) for p in meas)
            pull = {"level": "measured", "evidence": "MEASURED", "value": rnd(val, 0),
                    "per_post_median": rnd(median([p["followers"].get("excess_72h") for p in meas]), 0),
                    "posts": len(meas), "unit": "followers gained in the 72 h after its posts, above the usual pace",
                    "label": "%d followers above the usual pace in the 72 h after its %d measured posts" % (val, len(meas))}
        elif est:
            sc_mean = sum(p["followers"]["score"] for p in est) / float(len(est))
            likely = sum(1 for p in est if p["followers"].get("label") == "likely brought followers")
            pull = {"level": "estimated", "evidence": "INFERRED", "value": rnd(sc_mean, 3), "posts": len(est),
                    "likely_posts": likely, "unit": "estimated score 0-1 (never a count)",
                    "basis": "the mean of its posts' estimated follower scores (references/numbers.md)",
                    "label": "estimated score %.2f; %d of its %d posts likely brought followers" % (sc_mean, likely, len(est))}
        else:
            pull = {"level": "none", "evidence": None, "value": None, "label": "unknown"}
        examples = sorted(sc, key=lambda p: -p["ratio"])[:3]
        pn, n_probed = probe_numbers(folder, ids)
        durs = [p["duration_s"] for p in win if p["duration_s"] is not None]
        rec = {
            "id": f["id"], "name": f.get("name"),
            "container": {k: f.get(k) for k in ("hook", "structure", "look", "length")},
            "basis": f.get("basis"),
            "recipe": "formats/%s.md" % f["id"],
            "posts_total": len(win), "posts_scored": len(sc),
            "fresh_posts": sum(1 for p in sc if p.get("fresh") or p.get("status") == "fresh"),
            "share": rnd(len(win) / float(n_window), 3) if n_window else 0.0,
            "lift": rnd(lift, 3) if lift is not None else None,
            "hit_rate": rnd(hit, 3),
            "direction": rnd(direction, 3), "direction_label": dlabel,
            "follower_pull": pull,
            "effort": f.get("effort"), "effort_note": f.get("effort_note"),
            "evidence": "MEASURED",
            "grouping": "the agent's (formats.json); the numbers of the group are measured",
            "few_posts": len(sc) < 6,
            "first_seen": win and min(p["published_at"] for p in win if p["published_at"]) or None,
            "last_seen": win and max(p["published_at"] for p in win if p["published_at"]) or None,
            "length_s_median": rnd(median(durs), 1),
            "probe": pn, "videos_read": n_probed,
            "examples": [{"post_id": p["post_id"], "url": p["url"], "ratio": p["ratio"], "views": p["views"],
                          "published_at": p["published_at"], "cover_file": p["cover_file"],
                          "fresh": bool(p.get("fresh") or p.get("status") == "fresh")} for p in examples],
            "post_ids": ids,
        }
        if lift is None:
            rec["quadrant"] = "too_few"
        else:
            rec["quadrant"] = quadrant(rec)
        rec["quadrant_name"] = QUADRANT_NAMES[rec["quadrant"]]
        formats.append(rec)
    unformatted = [p for p in inw if p["post_id"] not in owned]
    return formats, unformatted, n_window


def timeline_marks(an, fdoc, formats):
    marks = []
    # A format that is there from the window's first month is not a change; one that starts later is.
    lo = an["window"]["from"]
    import datetime as _dt
    lo30 = (_dt.date(int(lo[:4]), int(lo[5:7]), int(lo[8:10])) + _dt.timedelta(days=30)).isoformat()
    for f in formats:
        if f["first_seen"] and f["first_seen"][:10] > lo30:
            marks.append({"at": f["first_seen"][:10], "kind": "format", "evidence": "MEASURED",
                          "text": "first post of format: %s" % f["name"], "format": f["id"]})
    posts = dict((p["post_id"], p) for p in an["posts"])
    for s in fdoc.get("series") or []:
        ids = [i for i in s.get("posts") or [] if i in posts and posts[i]["published_at"]]
        if ids:
            marks.append({"at": posts[ids[0]]["published_at"][:10], "kind": "series", "evidence": "SEEN",
                          "posts": ids[:2], "text": "series starts: %s (%d parts)" % (s.get("name") or s.get("id"), len(ids))})
    return sorted(marks, key=lambda m: m["at"])


def measured_table(f):
    pull = f["follower_pull"]
    rows = [
        "| Posts | Share | Lift | Hit rate | Direction | Follower pull | Effort | Corner |",
        "|---|---|---|---|---|---|---|---|",
        "| %s | %s | %s | %s | %s | %s (%s) | %s | %s |" % (
            f["posts_total"], pct(f["share"]), x(f["lift"]), pct(f["hit_rate"]),
            (x(f["direction"]) + " " + (f["direction_label"] or "")) if f["direction"] is not None else "not enough posts",
            pull["label"], (pull.get("evidence") or "unknown"), f["effort"], f["quadrant_name"]),
        "",
        "All MEASURED by radar.py from posts.csv (lift = median of each post's views over the median of the 20 posts "
        "before it). Follower pull is %s." % (pull.get("evidence") or "unknown"),
        "",
        "Examples (best first): " + ", ".join("[%s](%s) %s%s" % (
            e["post_id"], e["url"], x(e["ratio"]), " (fresh / still growing)" if e.get("fresh") else "") for e in f["examples"]),
    ]
    return "\n".join(rows)


def pct(v):
    return "-" if v is None else "%d%%" % round(100 * v)


def x(v):
    if v is None:
        return "-"
    v = float(v)
    if 0.995 <= v < 1.005 and v != 1.0:
        return "%.3fx" % v  # never show 0.998 as "1x"
    return ("%.2f" % v).rstrip("0").rstrip(".") + "x"


def write_recipe(folder, f, shared=False):
    path = os.path.join(folder, "formats", f["id"] + ".md")
    measured = {"posts": f["posts_total"], "share": f["share"], "lift": f["lift"], "hit_rate": f["hit_rate"],
                "direction": f["direction"], "length_s_median": f["length_s_median"],
                "cuts_per_10s_median": f["probe"]["cuts_per_10s"], "words_per_minute_median": f["probe"]["words_per_minute"],
                "first_cut_s_median": f["probe"]["first_cut_s"], "videos_read": f["videos_read"],
                "follower_pull": f["follower_pull"]["label"], "quadrant": f["quadrant"]}
    if shared:
        measured.update({"scope": "shared", "creators": f["creators"], "creators_share": f["creators_share"],
                         "niche_format": f["niche_format"], "scope_status": f["scope_status"],
                         "direction_label": f["direction_label"], "first_seen": f["first_seen"], "new": f["new"],
                         "by_creator": [{"account": c["account"], "posts": c["posts"], "lift": c["lift"]} for c in f["by_creator"]]})
    table = MEASURED_START + "\n" + (measured_table_shared(f) if shared else measured_table(f)) + "\n" + MEASURED_END
    voice = "hooks.md" if shared else "voice.md"
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        m = RECIPE_RE.search(text)
        if m:
            try:
                rec = json.loads(m.group(1))
            except ValueError:
                die("%s: the rea-recipe JSON block does not parse; fix it, then run radar.py again" % path, 1)
            rec["measured"] = measured
            rec["examples"] = rec.get("examples") or [e["post_id"] for e in f["examples"]]
            rec.setdefault("voice", voice)
            text = text[:m.start()] + "```json rea-recipe\n" + json.dumps(rec, indent=2, ensure_ascii=False) + "\n```" + text[m.end():]
        if MEASURED_START in text and MEASURED_END in text:
            a = text.index(MEASURED_START)
            b = text.index(MEASURED_END) + len(MEASURED_END)
            text = text[:a] + table + text[b:]
        write_text(path, text)
        return path, False
    c = f["container"]
    rec = {
        "schema": "rea-viral/recipe@1",
        "id": f["id"], "name": f["name"],
        "length_s": f["length_s_median"],
        "beats": [],
        "cuts_per_10s": f["probe"]["cuts_per_10s"],
        "words_per_minute": f["probe"]["words_per_minute"],
        "hook_pattern": c.get("hook") or "",
        "caption_style": "",
        "sound": "",
        "ask": "",
        "examples": [e["post_id"] for e in f["examples"]],
        "voice": voice,
        "tolerance": {"length_pct": 10, "cut_s": 0.25, "cuts_per_10s": 1.0, "words_per_minute_pct": 15},
        "measured": measured,
    }
    words_note = ([
        "The words: what the niche's winning posts open with, measured against each creator's own usual, is in",
        "`hooks.md` (written by `text_probe.py`). A draft for this format follows both.",
    ] if shared else [
        "The words: how the account writes its captions and first lines, measured against its results, is in its",
        "voice sheet, `voice.md` (written by `text_probe.py`). A draft for this format follows both.",
    ])
    body = [
        "# %s" % f["name"],
        "",
        "A format recipe of REA Viral. The JSON block is what a remake reads; the agent fills `beats`, `hook_pattern`,",
        "`caption_style`, `sound` and `ask` from the deep read (each beat: `{\"at\": seconds, \"what\": \"hook\", \"text\": \"...\"}`).",
        "radar.py rewrites only `measured` and the table between the markers.",
        "",
    ] + ([
        "Seen across creators: the beats below must hold on watched posts of at least two different creators, each beat",
        "marked SEEN with the posts it was seen in. What only one creator does is that creator's, not the format's.",
        "",
    ] if shared else []) + [
        "```json rea-recipe",
        json.dumps(rec, indent=2, ensure_ascii=False),
        "```",
        "",
        table,
        "",
        "## The container",
        "",
        "- Hook: %s" % (c.get("hook") or ""),
        "- Structure: %s" % (c.get("structure") or ""),
        "- Look: %s" % (c.get("look") or ""),
        "- Length: %s" % (c.get("length") or ""),
        "",
        "## Beats",
        "",
        "(The agent: the beats with their times, from the videos read. Mark each SEEN with the post it was seen in.)",
        "",
        "## Caption style, pace, sound",
        "",
    ] + words_note + [
        "",
        "## What not to copy",
        "",
    ]
    write_text(path, "\n".join(body))
    return path, True


# ---------------------------------------------------------------------------------------------- the formats of a niche
# scope "shared": a niche run (niche.json). The same file shape as one account's format map, plus per format the
# creators behind it. Rules in references/radar.md, "The formats of a niche". (The scope name and the file name stay
# as they are: older run folders and the planner's readers rely on them.)

SHARED_RULES = {
    "often_creators_share": 0.4,   # across: the share of the niche's scored creators that use it (split)
    "strong_lift": 1.0,            # up: its lift over each creator's own usual (split)
    "min_creators": 3,             # creators with scored posts before it is called a format of the niche
    "min_posts_format": 3,         # scored posts before it is placed at all
    "few_posts": 6,                # under this many scored posts it is placed but marked few posts
    "min_posts_half": 3,           # scored posts in each half of the window before a direction is said
    "rising_direction": 1.33,
    "fading_direction": 0.75,
    "hit_ratio": 2.0,
}


def shared_quadrant(f):
    """Where a format of the niche sits: position only (creators x lift). The direction is its arrow, never its corner."""
    if not f["niche_format"]:
        return "too_few"
    often = f["creators_share"] >= SHARED_RULES["often_creators_share"]
    strong = f["lift"] >= SHARED_RULES["strong_lift"]
    if not strong:
        return "overused" if often else "drop"
    return "scale_it" if often else "underused"


def probe_numbers_shared(folder, posts_by_id, ids):
    out = {"length_s": [], "cuts_per_10s": [], "words_per_minute": [], "first_cut_s": []}
    read = 0
    for pid in ids:
        p = posts_by_id.get(pid)
        if not p:
            continue
        path = os.path.join(folder, "accounts", p["creator"], "videos", pid, "probe.json")
        if not os.path.exists(path):
            continue
        try:
            d = read_json(path)
        except ValueError:
            continue
        if not d.get("read"):
            continue
        read += 1
        m = d.get("measured") or {}
        for k in out:
            if m.get(k) is not None:
                out[k].append(m[k])
    return dict((k, rnd(median(v), 2)) for k, v in out.items()), read


def measure_shared(folder, tr, fdoc):
    import datetime as _dt
    from common import parse_time
    R = SHARED_RULES
    P = dict((p["post_id"], p) for p in tr["posts"])
    lo = parse_time(tr["window"]["from"])
    hi = parse_time(tr["window"]["to"]) + _dt.timedelta(days=1)
    mid = lo + (hi - lo) / 2
    inw_all = [p for p in tr["posts"] if p["in_window"]]
    scored_creators = sorted(set(p["creator"] for p in tr["posts"] if p["status"] in ("scored", "fresh")))
    n_creators = len(scored_creators)
    early_all = sum(1 for p in inw_all if parse_time(p["published_at"]) < mid)
    late_all = len(inw_all) - early_all
    formats, owned = [], set()
    for f in fdoc.get("formats") or []:
        ids = [i for i in f.get("posts") or [] if i in P]
        owned |= set(ids)
        win = [P[i] for i in ids if P[i]["in_window"]]
        sc = sorted([p for p in win if p["status"] in ("scored", "fresh")], key=lambda p: p["published_at"])
        by_c = {}
        for p in sc:
            by_c.setdefault(p["creator"], []).append(p)
        by_creator = []
        for cid, ps in sorted(by_c.items()):
            rs = [p["ratio"] for p in ps]
            by_creator.append({"creator": cid, "account": ps[0]["account"], "network": ps[0]["network"], "posts": len(ps),
                               "lift": rnd(median(rs), 3), "hits": sum(1 for r in rs if r >= R["hit_ratio"]),
                               "best": max(ps, key=lambda p: p["ratio"])["post_id"]})
        ratios = [p["ratio"] for p in sc]
        lift = median([c["lift"] for c in by_creator]) if by_creator else None
        hit = (sum(1 for r in ratios if r >= R["hit_ratio"]) / float(len(ratios))) if ratios else None
        early = [p["ratio"] for p in sc if parse_time(p["published_at"]) < mid]
        late = [p["ratio"] for p in sc if parse_time(p["published_at"]) >= mid]
        direction = None
        if len(early) >= R["min_posts_half"] and len(late) >= R["min_posts_half"]:
            a, b = median(early), median(late)
            direction = (b / a) if a else None
        dlabel = None
        if direction is not None:
            dlabel = "rising" if direction >= R["rising_direction"] else (
                "fading" if direction < R["fading_direction"] else "steady")
        e_use = sum(1 for p in win if parse_time(p["published_at"]) < mid)
        l_use = len(win) - e_use
        usage = None
        if early_all and late_all and e_use:
            usage = (l_use / float(late_all)) / (e_use / float(early_all))
        dated_all = [P[i]["published_at"] for i in ids if P[i]["published_at"]]
        first_seen = min(dated_all) if dated_all else None
        n_c = len(by_creator)
        niche_format = n_c >= R["min_creators"] and len(sc) >= R["min_posts_format"]
        if n_c >= R["min_creators"]:
            scope_status = "niche format" if len(sc) >= R["min_posts_format"] else "few posts"
        elif n_c == 2:
            scope_status = "few creators"
        elif n_c == 1:
            scope_status = "creator habit"
        else:
            scope_status = "not scored"
        # The proof spans creators: each creator's best post, best first.
        best_each = sorted([max(by_c[c], key=lambda p: p["ratio"]) for c in by_c], key=lambda p: -p["ratio"])
        weak = [p for p in win if p["status"] == "weaker_basis"]
        young = [p for p in win if p.get("fresh") or p["status"] in ("too_new", "fresh")]
        pn, n_probed = probe_numbers_shared(folder, P, ids)
        durs = [p["duration_s"] for p in win if p["duration_s"] is not None]
        rec = {
            "id": f["id"], "name": f.get("name"),
            "container": {k: f.get(k) for k in ("hook", "structure", "look", "length")},
            "basis": f.get("basis"),
            "recipe": "formats/%s.md" % f["id"],
            "posts_total": len(win), "posts_scored": len(sc),
            "fresh_posts": len(young),
            "creators": n_c, "creators_share": rnd(n_c / float(n_creators), 3) if n_creators else 0.0,
            "creators_all": len(set(p["creator"] for p in win)),
            "by_creator": by_creator,
            "share": rnd(len(win) / float(len(inw_all)), 3) if inw_all else 0.0,
            "lift": rnd(lift, 3), "lift_posts": rnd(median(ratios), 3) if ratios else None,
            "hit_rate": rnd(hit, 3), "creators_hit": sum(1 for c in by_creator if c["hits"]),
            "direction": rnd(direction, 3), "direction_label": dlabel,
            "halves": {"early_scored": len(early), "late_scored": len(late), "early_lift": rnd(median(early), 3) if early else None,
                       "late_lift": rnd(median(late), 3) if late else None, "early_posts": e_use, "late_posts": l_use},
            "usage_direction": rnd(usage, 3),
            "first_seen": first_seen, "new": bool(first_seen and parse_time(first_seen) >= mid),
            "age_days": rnd((hi - parse_time(first_seen)).total_seconds() / 86400.0, 1) if first_seen else None,
            "last_seen": max(dated_all) if dated_all else None,
            "weaker_basis_posts": len(weak), "too_new_posts": len(young),
            "follower_pull": {"level": "none", "evidence": None, "value": None,
                              "label": "not measured across a niche (no follower counts per post)"},
            "effort": f.get("effort"), "effort_note": f.get("effort_note"),
            "evidence": "MEASURED",
            "grouping": "the agent's (formats.json); the numbers of the group are measured",
            "niche_format": niche_format, "scope_status": scope_status,
            "few_posts": len(sc) < R["few_posts"],
            "length_s_median": rnd(median(durs), 1),
            "probe": pn, "videos_read": n_probed,
            "examples": [{"post_id": p["post_id"], "account": p["account"], "creator": p["creator"], "url": p["url"],
                          "ratio": p["ratio"], "views": p["views"], "published_at": p["published_at"],
                          "cover_file": p["cover_file"],
                          "fresh": bool(p.get("fresh") or p["status"] == "fresh")} for p in best_each[:6]],
            "proof": [{"post_id": p["post_id"], "account": p["account"], "ratio": p["ratio"],
                       "fresh": bool(p.get("fresh") or p["status"] == "fresh")}
                      for p in sorted(sc, key=lambda p: -p["ratio"])],
            "post_ids": ids,
        }
        rec["quadrant"] = shared_quadrant(rec) if rec["lift"] is not None else "too_few"
        rec["quadrant_name"] = QUADRANT_NAMES[rec["quadrant"]] if rec["quadrant"] != "too_few" else (
            "Not a niche format: %s" % scope_status)
        formats.append(rec)
    unformatted = [p for p in inw_all if p["post_id"] not in owned]
    return formats, unformatted, len(inw_all), n_creators


def measured_table_shared(f):
    rows = [
        "| Creators | Posts | Lift | Hit rate | Direction | First seen | Effort | Corner |",
        "|---|---|---|---|---|---|---|---|",
        "| %d of the niche's %s (%s) | %d (%d scored) | %s | %s | %s | %s%s | %s | %s |" % (
            f["creators"], "creators", pct(f["creators_share"]), f["posts_total"], f["posts_scored"], x(f["lift"]),
            pct(f["hit_rate"]),
            (x(f["direction"]) + " " + (f["direction_label"] or "")) if f["direction"] is not None else "not enough posts",
            (f["first_seen"] or "-")[:10], " (new)" if f["new"] else "", f["effort"], f["quadrant_name"]),
        "",
        "All MEASURED by radar.py from trends.json: each post's views over the median of its OWN creator's other posts; "
        "lift = the median of each creator's median, so one prolific creator cannot carry it. Direction = the later half "
        "of the window against the earlier half. %s." % (
            "A format of the niche (%d creators or more)" % SHARED_RULES["min_creators"] if f["niche_format"] else
            "NOT a format of the niche: %s" % f["scope_status"]),
        "",
        "The posts that prove it (each creator's best, best first): " + ", ".join(
            "[%s](%s) @%s %s" % (e["post_id"], e["url"], e["account"], x(e["ratio"])) for e in f["examples"]),
    ]
    return "\n".join(rows)


def run_shared(folder):
    import trends
    fdoc = load_formats(folder)
    tr = trends.run(folder)
    out = {
        "schema": "rea-viral/radar@1",
        "scope": "shared",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": tr["inputs"],
        "subject": {"niche": tr["niche"].get("name"), "slug": tr["niche"].get("slug"), "words": tr["niche"].get("words"),
                    "tags": tr["niche"].get("tags"), "networks": tr["niche"].get("networks")},
        "window": tr["window"],
        "rules": SHARED_RULES,
        "axes": {
            "x": {"key": "creators_share", "label": "How many of the niche's creators use it", "split": SHARED_RULES["often_creators_share"]},
            "y": {"key": "lift", "label": "Lift over each creator's own usual", "split": SHARED_RULES["strong_lift"], "scale": "log2"},
            "size": {"key": "creators", "label": "Creators behind it"},
            "arrow": {"key": "direction", "label": "Direction: the later half of the window against the earlier half"},
        },
        "quadrants": QUADRANT_NAMES,
        "counts": tr["counts"],
    }
    if tr["status"] != "ok":
        out["status"], out["status_note"] = tr["status"], tr["status_note"]
        out["formats"] = []
        out["posts"] = [{"post_id": p["post_id"], "account": p["account"], "url": p["url"], "published_at": p["published_at"],
                         "views": p["views"], "ratio": p["ratio"], "fresh": bool(p.get("fresh"))} for p in tr["posts"] if p["status"] in ("scored", "fresh")]
        return out, [], tr
    if not fdoc or not fdoc.get("formats"):
        out["status"] = "no_formats"
        out["status_note"] = ("formats.json is missing or empty: group the niche's posts into formats (from the covers "
                              "sheet and the videos you watched), then run radar.py again.")
        out["formats"] = []
        return out, [], tr
    formats, unformatted, n_window, n_creators = measure_shared(folder, tr, fdoc)
    out["status"], out["status_note"] = "ok", None
    out["creators_scored"] = n_creators
    out["formats"] = formats
    out["unformatted"] = {"posts": len(unformatted), "share": rnd(len(unformatted) / float(n_window), 3) if n_window else None,
                          "post_ids": [p["post_id"] for p in unformatted]}
    out["timeline_marks"] = [{"at": f["first_seen"][:10], "kind": "format", "evidence": "MEASURED", "format": f["id"],
                              "text": "first post of %s seen in what was read" % f["name"]}
                             for f in formats if f["new"] and f["first_seen"]]
    written = []
    for f in formats:
        written.append(write_recipe(folder, f, shared=True))
    return out, written, tr


def run(folder):
    from common import run_kind
    if run_kind(folder) == "niche":
        out, written, _ = run_shared(folder)
        return out, written
    fdoc = load_formats(folder)
    an = analyze.run(folder)
    analyze.write_outputs(folder, an)
    out = {
        "schema": "rea-viral/radar@1",
        "scope": "account",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": an["inputs"],
        "subject": {"network": an["account"]["network"], "handle": an["account"]["handle"], "url": an["account"].get("url")},
        "window": an["window"],
        "rules": RULES,
        "axes": {
            "x": {"key": "share", "label": "How often it is used (share of posts)", "split": RULES["often_share"]},
            "y": {"key": "lift", "label": "Lift over the account's own baseline", "split": RULES["strong_lift"], "scale": "log2"},
            "size": {"key": "follower_pull.value", "label": "Follower pull"},
            "arrow": {"key": "direction", "label": "Direction: last third against first third"},
        },
        "quadrants": QUADRANT_NAMES,
    }
    if an["status"] in ("private", "empty", "no_dates", "too_few_posts"):
        out["status"] = an["status"]
        out["status_note"] = an["status_note"]
        out["formats"] = []
        out["posts"] = [{"post_id": p["post_id"], "url": p["url"], "published_at": p["published_at"], "type": p["type"],
                         "views": p["views"], "ratio": p["ratio"]} for p in an["posts"] if p["in_window"] or an["status"] == "no_dates"]
        return out, []
    if not fdoc or not fdoc.get("formats"):
        out["status"] = "no_formats"
        out["status_note"] = "formats.json is missing or empty: group the posts into formats after the deep read, then run radar.py again."
        out["formats"] = []
        return out, []
    formats, unformatted, n_window = measure(folder, an, fdoc)
    out["status"] = "ok"
    out["status_note"] = None
    out["formats"] = formats
    out["unformatted"] = {"posts": len(unformatted), "share": rnd(len(unformatted) / float(n_window), 3) if n_window else None,
                          "post_ids": [p["post_id"] for p in unformatted]}
    out["timeline_marks"] = timeline_marks(an, fdoc, formats)
    written = []
    for f in formats:
        path, new = write_recipe(folder, f)
        written.append((path, new))
    return out, written


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    from common import run_kind
    if run_kind(folder) == "niche":
        import trends
        out, written, tr = run_shared(folder)
        write_json(os.path.join(folder, "radar.json"), out)
        trends.write_outputs(folder, tr, out)   # the watchlist gains each creator's formats
        print("radar.json (the formats of the niche, %d creators scored): status %s" % (tr["counts"]["creators_scored"], out["status"]) +
              ("" if not out.get("status_note") else " (%s)" % out["status_note"]))
        for f in out["formats"]:
            print("  %-28s %-10s creators %d (%s)  posts %3d  lift %6s  hits %4s  direction %-14s first %s%s" % (
                f["id"][:28], f["quadrant"], f["creators"], f["scope_status"], f["posts_scored"], x(f["lift"]),
                pct(f["hit_rate"]), (x(f["direction"]) + " " + (f["direction_label"] or "")) if f["direction"] is not None else "-",
                (f["first_seen"] or "-")[:10], " new" if f["new"] else ""))
        for path, new in written:
            print("  %s %s" % ("wrote" if new else "updated", os.path.relpath(path, folder)))
        return 0
    out, written = run(folder)
    write_json(os.path.join(folder, "radar.json"), out)
    print("radar.json: status %s" % out["status"] + ("" if not out.get("status_note") else " (%s)" % out["status_note"]))
    for f in out["formats"]:
        print("  %-28s %-10s posts %3d  share %4s  lift %6s  hits %4s  direction %-16s pull %s" % (
            f["id"][:28], f["quadrant"], f["posts_total"], pct(f["share"]), x(f["lift"]), pct(f["hit_rate"]),
            (x(f["direction"]) + " " + (f["direction_label"] or "")) if f["direction"] is not None else "-",
            f["follower_pull"]["label"]))
    for path, new in written:
        print("  %s %s" % ("wrote" if new else "updated", os.path.relpath(path, folder)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
