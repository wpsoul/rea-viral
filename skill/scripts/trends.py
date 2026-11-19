#!/usr/bin/env python3
"""Trends across a niche: every post against ITS OWN creator's usual, never against the biggest number.

    python3 trends.py <niche folder> [--now ISO]

Reads niche.json, found.csv (optional: how each post was found), formats.json (optional: the format of each post,
for the planner rows) and every creator folder accounts/<network>-<handle>/ (account.json and posts.csv, the shape of
references/data-shape.md). Writes:
- trends.json   every post with its ratio and the basis of that ratio, the ranked list, each creator's usual
- trends.csv    the same posts as one flat table, best first
- watchlist.csv the creators worth following (radar.py adds their formats); it feeds Scout and Watch
- planner_rows.json  the best posts as rows a planner connector's trend tools take (references/niche.md)

What a trend is (references/numbers.md, "A niche"):
- A creator's usual = the median of that creator's OTHER settled recent posts (the window and the 30 days before it;
  at least 8). A post's ratio =
  its views over that usual. A post at 2x or more is a hit: it beat its own creator's usual, whatever its size. So a
  small creator's real outlier ranks above a big creator's ordinary post.
- Fewer than 8 other settled posts: the weaker basis, views per follower, labelled weaker and ranked apart. Such posts
  never count toward a niche format.
- Posts younger than the settling time (7 days; 3 on X and Threads) are not scored: their ratio so far is shown as a
  floor (views only grow), never ranked.
- Under 3 creators with their own usual, or under 20 scored posts in the window, the posts are listed and no pattern
  of the niche is called (status too_few_creators or too_few_posts).
It decides nothing about why a post worked: that is the agent's reading.
"""
import datetime as dt
import os
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    SKILL_VERSION, account_read_at, day, die, iso, load_formats, load_niche, load_posts, median, niche_creator_dirs,
    niche_input_files, norm_handle, now_utc, parse_time, read_csv, read_json, rnd, save_like, share_like, write_csv,
    write_json,
)
import analyze  # noqa: E402

RULES = {
    "min_baseline_posts": 8,     # a creator's usual needs this many OTHER settled posts
    "baseline_days_before_window": 30,   # ... from its recent posts only: the window and the 30 days before it
    "hit_ratio": 2.0,            # a trend: at least this times its own creator's usual
    "flop_ratio": 0.5,
    "min_creators": 3,           # creators with their own usual before any pattern of the niche is called
    "min_scored_posts": 20,      # scored posts in the window before any pattern of the niche is called
    "default_window_days": 30,
    "reach_lead": 2.0,           # weaker basis: views at least this many times the followers is a lead
    "planner_rows_max": 60,      # what a planner connector's trend tools take in one call
}


def _status_of(p, read_at, min_age):
    if p["published_at"] is None:
        return "no_date"
    if (p.get("read_at") or read_at) - p["published_at"] < min_age:
        return "too_new"
    if p["value"] is None:
        return "no_metric"
    return "settled"


def creator_numbers(posts, acc, lo, hi, rules=RULES, read_at=None):
    """Score one creator's posts against that creator's own usual (leave-one-out median). Mutates the post dicts and
    returns the creator's summary. Used by trends.py (many creators) and post_probe.py (one post)."""
    read_at = read_at or account_read_at(acc)
    min_age = dt.timedelta(days=analyze.MIN_AGE_DAYS.get(acc.get("network"), analyze.DEFAULT_MIN_AGE_DAYS))
    dated = [p for p in posts if p["published_at"] is not None]
    metric, _ = analyze.choose_metric(dated, None)
    followers = acc.get("followers") if isinstance(acc.get("followers"), int) else None
    for p in posts:
        p["value"] = p.get(metric)
        p["metric"] = metric
        p["state"] = _status_of(p, read_at, min_age)
        p["in_window"] = bool(p["published_at"] and lo <= p["published_at"] <= hi)
    # The usual comes from RECENT posts only: an old era of the channel (a different format, before it took off)
    # must not set the bar for this month's posts (learned on a real run, 2026-11-16).
    since = lo - dt.timedelta(days=rules.get("baseline_days_before_window", 30))
    settled = [p for p in posts if p["state"] == "settled" and p["published_at"] >= since]
    for p in posts:
        p["baseline"] = p["baseline_n"] = p["ratio"] = p["ratio_so_far"] = None
        p["basis"] = None
        p["views_per_follower"] = (p["views"] / float(followers)) if (followers and p.get("views") is not None) else None
        others = [q["value"] for q in settled if q is not p]
        if p["state"] in ("no_date", "no_metric"):
            p["status"] = p["state"]
            continue
        if len(others) >= rules["min_baseline_posts"]:
            b = median(others)
            p["baseline"], p["baseline_n"] = b, len(others)
            if b and b > 0:
                p["basis"] = "own"
                r = p["value"] / float(b)
                if p["state"] == "too_new":
                    p["ratio_so_far"] = r
                else:
                    p["ratio"] = r
        if p["basis"] is None and p["views_per_follower"] is not None:
            p["basis"] = "followers"
        if not p["in_window"]:
            p["status"] = "baseline_only"
        elif p["state"] == "too_new":
            p["status"] = "too_new"
        elif p["basis"] == "own":
            p["status"] = "scored"
        elif p["basis"] == "followers":
            p["status"] = "weaker_basis"
        else:
            p["status"] = "no_baseline"
    scored = [p for p in posts if p["status"] == "scored"]
    hits = [p for p in scored if p["ratio"] >= rules["hit_ratio"]]
    best = max(scored, key=lambda p: p["ratio"]) if scored else None
    usual = median([p["value"] for p in settled]) if settled else None
    basis = "own" if len(settled) > rules["min_baseline_posts"] else ("followers" if followers else None)
    return {
        "metric": metric, "posts_read": len(posts), "dated": len(dated), "settled": len(settled),
        "in_window": sum(1 for p in posts if p["in_window"]), "scored": len(scored), "hits": len(hits),
        "hit_rate": rnd(len(hits) / float(len(scored)), 3) if scored else None,
        "usual": usual, "usual_from_posts": len(settled), "basis": basis,
        "best": {"post_id": best["post_id"], "ratio": rnd(best["ratio"], 3), "url": best["url"]} if best else None,
        "followers": followers, "followers_exact": acc.get("followers_exact"),
        "span": {"from": day(min(p["published_at"] for p in dated)) if dated else None,
                 "to": day(max(p["published_at"] for p in dated)) if dated else None},
        "usual_since": day(since),
        "older_posts_left_out": sum(1 for p in posts if p["state"] == "settled" and p["published_at"] < since),
    }


def niche_window(niche, read_at):
    w = niche.get("window") or {}
    lo = parse_time(w.get("from")) if w.get("from") else None
    hi = parse_time(w.get("to")) if w.get("to") else None
    if hi is not None and len(str(w.get("to")).strip()) == 10:
        hi = hi + dt.timedelta(days=1) - dt.timedelta(seconds=1)  # a date-only "to" includes that day
    hi = hi or read_at
    lo = lo or (hi - dt.timedelta(days=RULES["default_window_days"]))
    return lo, hi


def found_index(folder):
    p = os.path.join(folder, "found.csv")
    if not os.path.exists(p):
        return {}
    _, rows = read_csv(p)
    out = {}
    for r in rows:
        pid = (r.get("post_id") or "").strip()
        if pid and pid not in out:
            out[pid] = {"found_by": (r.get("found_by") or "").strip() or None, "query": (r.get("query") or "").strip() or None}
    return out


def format_of(folder):
    fdoc = load_formats(folder) or {}
    out = {}
    for f in fdoc.get("formats") or []:
        for pid in f.get("posts") or []:
            out.setdefault(pid, {"id": f.get("id"), "name": f.get("name")})
    return out


def run(folder, opts=None):
    rules = dict(RULES)
    rules.update(opts or {})
    import validate
    rep = validate.validate(folder, inputs_only=True)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:20]]
        die("validate.py found %d error(s); fix them first:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    niche = load_niche(folder)
    read_at = parse_time(niche.get("read_at")) if niche.get("read_at") else now_utc()
    lo, hi = niche_window(niche, read_at)
    found = found_index(folder)
    fmt = format_of(folder)
    creators, posts = [], []
    for d in niche_creator_dirs(folder):
        acc = read_json(os.path.join(folder, d, "account.json"))
        ps = load_posts(os.path.join(folder, d))
        summary = creator_numbers(ps, acc, lo, hi, rules)
        cid = d.split("/", 1)[1]
        summary.update({"id": cid, "dir": d, "network": acc.get("network"), "handle": norm_handle(acc.get("handle")),
                        "name": acc.get("name"), "url": acc.get("url"), "found_by": acc.get("found_by")})
        creators.append(summary)
        for p in ps:
            f = found.get(p["post_id"]) or {}
            posts.append({
                "id": p["post_id"], "post_id": p["post_id"], "creator": cid, "network": acc.get("network"),
                "account": norm_handle(acc.get("handle")), "url": p["url"], "published_at": iso(p["published_at"]),
                "type": p["type"], "duration_s": p["duration_s"], "views": p["views"], "likes": p["likes"],
                "comments": p["comments"], "shares": share_like(p), "saves": save_like(p), "metric": p["metric"],
                "in_window": p["in_window"], "status": p["status"], "basis": p["basis"],
                "baseline": rnd(p["baseline"], 1), "baseline_n": p["baseline_n"], "ratio": rnd(p["ratio"], 3),
                "ratio_so_far": rnd(p["ratio_so_far"], 3), "views_per_follower": rnd(p["views_per_follower"], 4),
                "hit": bool(p["ratio"] is not None and p["ratio"] >= rules["hit_ratio"]),
                "found_by": f.get("found_by") or "the creator's recent posts", "query": f.get("query"),
                "format": (fmt.get(p["post_id"]) or {}).get("id"),
                "caption": (p["caption"] or "")[:400], "cover_file": (d + "/" + p["cover_file"]) if p["cover_file"] else None,
                "cover_url": p["cover_url"] or None,
            })
    scored = sorted([p for p in posts if p["status"] == "scored"], key=lambda p: (-p["ratio"], p["post_id"]))
    for i, p in enumerate(scored, 1):
        p["rank"] = i
    weak = sorted([p for p in posts if p["status"] == "weaker_basis"], key=lambda p: -(p["views_per_follower"] or 0))
    for p in weak:
        p["lead"] = bool(p["views_per_follower"] is not None and p["views_per_follower"] >= rules["reach_lead"])
    young = sorted([p for p in posts if p["status"] == "too_new"], key=lambda p: -(p["ratio_so_far"] or 0))
    scored_creators = sorted(set(p["creator"] for p in scored))
    picks = deep_read_picks(scored, rules)
    out = {
        "schema": "rea-viral/trends@1",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": analyze.input_fingerprint(folder, niche_input_files(folder)),
        "niche": {k: niche.get(k) for k in ("name", "slug", "question", "words", "tags", "networks")},
        "read_at": iso(read_at),
        "window": {"from": day(lo), "to": day(hi)},
        "rules": rules,
        "counts": {
            "creators": len(creators), "creators_scored": len(scored_creators),
            "creators_weaker_basis": sum(1 for c in creators if c["scored"] == 0 and c["basis"] == "followers"),
            "posts_read": len(posts), "in_window": sum(1 for p in posts if p["in_window"]),
            "scored": len(scored), "hits": sum(1 for p in scored if p["hit"]),
            "too_new": len(young), "weaker_basis": len(weak),
            "no_baseline": sum(1 for p in posts if p["status"] == "no_baseline"),
            "no_date": sum(1 for p in posts if p["status"] == "no_date"),
        },
        "creators": creators,
        "ranked": [p["post_id"] for p in scored],
        "leads_weaker_basis": [p["post_id"] for p in weak],
        "too_new": [p["post_id"] for p in young],
        "deep_read": picks,
        "posts": sorted(posts, key=lambda p: (p.get("rank") or 10 ** 6, p["creator"], p["published_at"] or "")),
    }
    if not posts:
        out["status"], out["status_note"] = "empty", "No post was read: nothing to score."
    elif len(scored_creators) < rules["min_creators"]:
        out["status"] = "too_few_creators"
        out["status_note"] = ("%d creators have their own usual (%d other settled posts or more); a pattern of the niche "
                              "needs %d. The posts are ranked and no format is called." % (
                                  len(scored_creators), rules["min_baseline_posts"], rules["min_creators"]))
    elif len(scored) < rules["min_scored_posts"]:
        out["status"] = "too_few_posts"
        out["status_note"] = ("%d posts in the window are scored against their own creator; a pattern needs %d. The posts "
                              "are ranked and no format is called." % (len(scored), rules["min_scored_posts"]))
    else:
        out["status"], out["status_note"] = "ok", None
    return out


def deep_read_picks(scored, rules, n_top=8, n_ord=3, n_flop=2, per_creator=2):
    """The posts to watch: the top trends (at most 2 per creator, so one creator cannot fill the reading), ordinary
    posts near 1x and flops, each of a different creator where possible."""
    top, seen = [], {}
    for p in scored:   # best first
        if p["ratio"] < rules["hit_ratio"] or len(top) >= n_top:
            break
        if seen.get(p["creator"], 0) < per_creator:
            top.append(p["post_id"])
            seen[p["creator"]] = seen.get(p["creator"], 0) + 1

    def spread(cands, n):
        out, used = [], set()
        for p in cands:
            if p["post_id"] in top or p["creator"] in used:
                continue
            out.append(p["post_id"])
            used.add(p["creator"])
            if len(out) >= n:
                break
        return out
    import math as _m
    ordinary = spread(sorted([p for p in scored if 0.75 <= p["ratio"] <= 1.33], key=lambda p: abs(_m.log(p["ratio"]))), n_ord)
    flops = spread(sorted([p for p in scored if p["ratio"] < 0.75], key=lambda p: p["ratio"]), n_flop)
    return {"trends": top, "ordinary": ordinary, "flops": flops}


# ---------------------------------------------------------------------------------------------- outputs

TREND_COLUMNS = ["rank", "post_id", "network", "account", "url", "published_at", "type", "duration_s", "views", "likes",
                 "comments", "shares", "saves", "basis", "baseline", "baseline_n", "ratio", "hit", "ratio_so_far",
                 "views_per_follower", "status", "format", "found_by", "query", "caption", "cover_file"]
WATCH_COLUMNS = ["rank", "network", "handle", "url", "followers", "followers_exact", "posts_read", "basis", "usual",
                 "usual_from_posts", "scored", "hits", "hit_rate", "best_ratio", "best_post", "best_url", "formats", "why",
                 "watch_command"]


def watchlist(tr, radar=None):
    """Creators worth following: those with a post at 2x their own usual or more, and (with radar.json) those who
    use a niche format that is rising or in Scale it / Underused. Best first: hits, then the best ratio."""
    owns = {}
    for f in (radar or {}).get("formats") or []:
        if not f.get("niche_format"):
            continue
        good = f.get("quadrant") in ("scale_it", "underused") or f.get("direction_label") == "rising"
        for c in f.get("by_creator") or []:
            owns.setdefault(c["creator"], []).append((f["id"], good))
    rows = []
    for c in tr["creators"]:
        fm = owns.get(c["id"], [])
        if not c["hits"] and not any(g for _, g in fm):
            continue
        why = []
        if c["hits"]:
            why.append("%d of %d scored posts at 2x its own usual or more; best %sx" % (
                c["hits"], c["scored"], ("%.2f" % c["best"]["ratio"]).rstrip("0").rstrip(".")))
        good = [i for i, g in fm if g]
        if good:
            why.append("uses %s" % ", ".join(good))
        rows.append({
            "network": c["network"], "handle": c["handle"], "url": c["url"], "followers": c["followers"],
            "followers_exact": c["followers_exact"], "posts_read": c["posts_read"], "basis": c["basis"],
            "usual": rnd(c["usual"], 0), "usual_from_posts": c["usual_from_posts"], "scored": c["scored"],
            "hits": c["hits"], "hit_rate": c["hit_rate"], "best_ratio": (c["best"] or {}).get("ratio"),
            "best_post": (c["best"] or {}).get("post_id"), "best_url": (c["best"] or {}).get("url"),
            "formats": ";".join(i for i, _ in fm), "why": "; ".join(why),
            "watch_command": "watch.py add rea-viral %s %s --source scout" % (c["network"], c["handle"]),
        })
    rows.sort(key=lambda r: (-r["hits"], -(r["best_ratio"] or 0), r["handle"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def planner_rows(tr, formats_by_post=None, names=None):
    """Rows for a planner connector's trend tools (score and save): the scored posts best first, at most 60. Each
    carries its creator's recent numbers, so the planner compares the post with its own creator's usual too."""
    recent = {}
    for p in tr["posts"]:
        if p["status"] in ("scored", "baseline_only") and p.get("views") is not None:
            recent.setdefault(p["creator"], []).append((p["published_at"] or "", p["views"]))
    followers = dict((c["id"], c["followers"]) for c in tr["creators"])
    rows = []
    for p in [q for q in tr["posts"] if q["status"] == "scored"][:tr["rules"]["planner_rows_max"]]:
        first = ((p.get("caption") or "").strip().split("\n") or [""])[0]
        row = {"url": p["url"], "text": (p.get("caption") or "")[:2000], "author": "@" + p["account"],
               "posted_at": p["published_at"], "has_video": p["type"] == "video"}
        if followers.get(p["creator"]) is not None:
            row["followers"] = followers[p["creator"]]
        for k in ("views", "likes", "comments", "shares", "saves"):
            if p.get(k) is not None:
                row[k] = p[k]
        others = [v for t, v in sorted(recent.get(p["creator"], []), reverse=True) if v is not None]
        mine = p.get("views")
        if mine in others:
            others.remove(mine)
        if others:
            row["author_recent_views"] = others[:30]
        f = p.get("format")
        if f:
            row["pattern"] = (names or {}).get(f) or f
        row["why"] = "%sx its creator's usual (the median of %d other posts)" % (
            ("%.2f" % p["ratio"]).rstrip("0").rstrip("."), p["baseline_n"] or 0)
        if first:
            row["hook"] = first[:200]
        rows.append(row)
    return rows


def write_outputs(folder, tr, radar=None):
    write_json(os.path.join(folder, "trends.json"), tr)
    rows = []
    for p in tr["posts"]:
        r = dict(p)
        r["hit"] = "true" if p["hit"] else "false"
        r["caption"] = (p.get("caption") or "").replace("\n", " ")[:160]
        rows.append(r)
    write_csv(os.path.join(folder, "trends.csv"), TREND_COLUMNS, rows)
    write_csv(os.path.join(folder, "watchlist.csv"), WATCH_COLUMNS, watchlist(tr, radar))
    names = dict((f["id"], f.get("name")) for f in (radar or {}).get("formats") or [])
    write_json(os.path.join(folder, "planner_rows.json"), {
        "schema": "rea-viral/planner-rows@1",
        "note": "Rows for a planner connector's trend tools (score and save). Built by trends.py from trends.json; "
                "see references/niche.md, 'A planner connector'.",
        "rows": planner_rows(tr, names=names)})


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    if "--now" in argv:
        os.environ["REA_NOW"] = argv[argv.index("--now") + 1]
        parse_time(os.environ["REA_NOW"])
    tr = run(folder)
    radar = None
    rp = os.path.join(folder, "radar.json")
    if os.path.exists(rp):
        radar = read_json(rp)
    write_outputs(folder, tr, radar)
    c = tr["counts"]
    print("trends.json: status %s; %d creators (%d with their own usual), %d posts read, %d in the window, %d scored, "
          "%d at 2x their own creator's usual or more; %d too new, %d on the weaker basis" % (
              tr["status"], c["creators"], c["creators_scored"], c["posts_read"], c["in_window"], c["scored"], c["hits"],
              c["too_new"], c["weaker_basis"]))
    if tr.get("status_note"):
        print("  " + tr["status_note"])
    by = dict((p["post_id"], p) for p in tr["posts"])
    for pid in tr["ranked"][:10]:
        p = by[pid]
        print("  #%-3d %-24s @%-20s %6sx  (usual %s from %d posts)" % (
            p["rank"], pid[:24], p["account"][:20], ("%.2f" % p["ratio"]), p["baseline"], p["baseline_n"] or 0))
    for c in tr["creators"]:
        print("  creator %-28s %3d read, %2d scored, %d hits, usual %s (%s)" % (
            c["id"][:28], c["posts_read"], c["scored"], c["hits"], rnd(c["usual"], 0), c["basis"] or "no basis"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
