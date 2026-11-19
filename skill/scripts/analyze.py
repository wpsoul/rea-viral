#!/usr/bin/env python3
"""The numbers of a run: baselines, outliers, rates, the timeline and which posts brought followers.

    python3 analyze.py <run folder> [--metric views|likes] [--now ISO] [--min-age-days N]

Reads account.json, posts.csv and, when present, comments.csv, formats.json (series) and watch/counts.csv.
Writes analysis.json and posts_scored.csv. Stops when validate.py finds errors.

What is measured (definitions in references/numbers.md):
- each post against the median of the 20 dated posts before it (at least 5 needed); posts under 7 days old are left
  out of scores and baselines (3 days on X and Threads, where views settle fast); the window's posts are scored, older
  posts only feed baselines;
- rates beside the views (likes, comments, shares, saves per view);
- the timeline: posts per month and week, the mix of types, pace changes, posting rhythm;
- followers: MEASURED when follower counts cover a post's 72 hours (the gain is split between overlapping posts by
  their views), otherwise an ESTIMATED score from signals, never a count;
- the deep-read picks: the top 8 outliers, 4 ordinary posts and 2 flops.

What it does not do: decide why anything worked. That is the agent's reading, written to findings.json.
"""
import datetime as dt
import hashlib
import math
import os
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    FOLLOW_RE, SKILL_VERSION, account_read_at, account_window, clamp, day, die, follower_readings, iso,
    load_account, load_comments, load_formats, load_posts, median, now_utc, parse_time, rnd, save_like, share_like,
    write_csv, write_json,
)
import validate  # noqa: E402

DEFAULTS = {
    "baseline_posts": 20,     # the median of this many earlier posts
    "min_prior_posts": 5,     # fewer earlier posts than this: no baseline
    "min_age_days": None,     # younger posts are still growing: left out. None = the network's own (MIN_AGE_DAYS)
    "hit_ratio": 2.0,         # a hit (and an outlier) is at least this times its baseline
    "flop_ratio": 0.5,        # a flop is at most this
    "min_window_posts": 20,   # fewer dated posts in the window: list them, call no pattern
    "attrib_hours": 72,       # the follower gain counted after each post
    "gap_hours": 48,          # two follower readings further apart than this are a gap, never filled
    "picks": (8, 4, 2),       # deep read: outliers, ordinary, flops
}

# How many days a post's counts take to settle, by network. Short videos keep gathering views for a week or more;
# a post on X or Threads gets most of its views in its first one or two days, so 3 days is enough there (INFERRED
# from how those feeds work; --min-age-days changes it). Any other network: 7.
MIN_AGE_DAYS = {"x": 3, "threads": 3}
DEFAULT_MIN_AGE_DAYS = 7

INPUT_FILES = ("account.json", "posts.csv", "comments.csv", "formats.json", "watch/counts.csv", "../watch/counts.csv")


def input_fingerprint(folder, files=INPUT_FILES):
    """A short hash of each input file (None when it does not exist), so a reader can tell a stale output."""
    out = {}
    for f in files:
        p = os.path.join(folder, *f.split("/"))
        if os.path.exists(p):
            h = hashlib.sha1()
            with open(p, "rb") as fh:
                h.update(fh.read())
            out[f] = h.hexdigest()[:16]
        else:
            out[f] = None
    return out


def log2(x):
    return math.log(x, 2)


# ---------------------------------------------------------------------------------------------- scoring

def choose_metric(posts, forced):
    if forced:
        return forced, None
    if not posts:
        return "views", None
    with_views = sum(1 for p in posts if p["views"] is not None)
    with_likes = sum(1 for p in posts if p["likes"] is not None)
    if with_views >= 0.8 * len(posts):
        return "views", None
    if with_likes >= 0.8 * len(posts):
        return "likes", ("only %d of %d posts have views; posts are scored on likes instead" % (with_views, len(posts)))
    return "views", ("only %d of %d posts have views; posts without views are not scored" % (with_views, len(posts)))


def score(posts, acc, opts, metric):
    read_at = account_read_at(acc)
    lo, hi = account_window(acc)
    if hi is None:
        hi = read_at
    if lo is None:
        lo = hi - dt.timedelta(days=365)
    min_age = dt.timedelta(days=opts["min_age_days"])
    for p in posts:
        p["in_window"] = bool(p["published_at"] and lo <= p["published_at"] <= hi)
        p["value"] = p.get(metric)
        p["baseline"] = None
        p["ratio"] = None
        own_read = p.get("read_at") or read_at
        if p["published_at"] is None:
            p["status"] = "no_date"
        elif own_read - p["published_at"] < min_age:
            p["status"] = "too_new"
        elif p["value"] is None:
            p["status"] = "no_metric"
        else:
            p["status"] = "eligible"
    eligible = sorted([p for p in posts if p["status"] == "eligible"], key=lambda p: (p["published_at"], p["post_id"]))
    for i, p in enumerate(eligible):
        prior = eligible[max(0, i - opts["baseline_posts"]):i]
        if not p["in_window"]:
            p["status"] = "warmup"
            continue
        if len(prior) < opts["min_prior_posts"]:
            p["status"] = "no_baseline"
            p["baseline_n"] = len(prior)
            continue
        b = median([q["value"] for q in prior])
        p["baseline"] = b
        p["baseline_n"] = len(prior)
        if b and b > 0:
            p["ratio"] = p["value"] / float(b)
            p["status"] = "scored"
        else:
            p["status"] = "no_baseline"
            p["baseline_note"] = "the earlier posts' median is 0"
    return eligible, lo, hi


RATE_KEYS = ("like", "comment", "share", "save", "repost", "quote", "bookmark", "engagement")


def rates(p):
    """Per view. `share` and `save` fall back to reposts and bookmarks where the network has no shares or saves
    (X, Threads, LinkedIn), so the follower signals read the same on every network; `repost`, `quote` and `bookmark`
    are also kept under their own names. Engagement counts each interaction once."""
    v = p["views"]
    out = dict((k, None) for k in RATE_KEYS)
    if v is None or v <= 0:
        return out
    total = 0
    known = False
    vals = {"like": p["likes"], "comment": p["comments"], "share": share_like(p), "save": save_like(p),
            "repost": p.get("reposts"), "quote": p.get("quotes"), "bookmark": p.get("bookmarks")}
    for k, x in vals.items():
        out[k] = (x / float(v)) if x is not None else None
    for x in (p["likes"], p["comments"], share_like(p), save_like(p), p.get("quotes")):
        if x is not None:
            total += x
            known = True
    out["engagement"] = (total / float(v)) if known else None
    return out


# ---------------------------------------------------------------------------------------------- followers

def followers_at(readings, t, current, read_at):
    """The follower count at time t: between two readings within 7 days, linear; else the nearest within 30 days;
    else the current count. Returns (value, how)."""
    if readings:
        before = [r for r in readings if r["at"] <= t]
        after = [r for r in readings if r["at"] >= t]
        if before and after:
            a, b = before[-1], after[0]
            if a["at"] == b["at"]:
                return a["followers"], "reading"
            if (b["at"] - a["at"]) <= dt.timedelta(days=7):
                f = (t - a["at"]).total_seconds() / (b["at"] - a["at"]).total_seconds()
                return a["followers"] + f * (b["followers"] - a["followers"]), "between readings"
        near = min(readings, key=lambda r: abs((r["at"] - t).total_seconds()))
        if abs((near["at"] - t).total_seconds()) <= 30 * 86400:
            return near["followers"], "nearest reading"
    if current is not None:
        return current, "current count"
    return None, "unknown"


def attribution(posts, readings, opts):
    """MEASURED follower gain in the hours after each post, split between overlapping posts by their views."""
    H = dt.timedelta(hours=opts["attrib_hours"])
    gap = dt.timedelta(hours=opts["gap_hours"])
    res = {"readings": len(readings), "gaps": [], "usual_daily_gain": None, "coverage": None,
           "total_gain": None, "gain_with_no_post_running": None, "days": []}
    if len(readings) < 2:
        return res, {}
    intervals = []
    for a, b in zip(readings, readings[1:]):
        span = b["at"] - a["at"]
        intervals.append({"a": a, "b": b, "span": span, "gain": b["followers"] - a["followers"], "gap": span > gap,
                          "watch": a["watch"] and b["watch"]})
    for it in intervals:
        if it["gap"]:
            res["gaps"].append({"from": iso(it["a"]["at"]), "to": iso(it["b"]["at"]),
                                "hours": rnd(it["span"].total_seconds() / 3600.0, 1)})
    daily = [it["gain"] / (it["span"].total_seconds() / 86400.0) for it in intervals
             if not it["gap"] and it["span"] >= dt.timedelta(hours=1)]
    usual_daily = median(daily)
    res["usual_daily_gain"] = rnd(usual_daily, 1)
    usual_per_s = (usual_daily or 0.0) / 86400.0
    first, last = readings[0]["at"], readings[-1]["at"]
    res["coverage"] = {"from": iso(first), "to": iso(last)}
    res["total_gain"] = readings[-1]["followers"] - readings[0]["followers"]

    dated = [p for p in posts if p["published_at"] is not None and p["status"] != "no_date"]
    vals = [p["views"] for p in dated if p["views"] is not None]
    fallback_w = median(vals) or 1.0
    wins = []
    for p in dated:
        w = p["views"] if p["views"] is not None else (p.get("baseline") or fallback_w)
        wins.append((p, p["published_at"], p["published_at"] + H, max(float(w), 1.0)))

    # Breakpoints: readings, and every post window's start and end inside the covered span.
    pts = set(r["at"] for r in readings)
    for _, s, e, _ in wins:
        for t in (s, e):
            if first < t < last:
                pts.add(t)
    pts = sorted(pts)
    per = {}
    no_post = 0.0
    ii = 0
    by_day = {}
    for s, e in zip(pts, pts[1:]):
        while ii < len(intervals) and intervals[ii]["b"]["at"] <= s:
            ii += 1
        if ii >= len(intervals):
            break
        it = intervals[ii]
        if it["gap"]:
            continue
        frac = (e - s).total_seconds() / it["span"].total_seconds()
        g = it["gain"] * frac
        x = g - usual_per_s * (e - s).total_seconds()
        dkey = day(s)
        by_day[dkey] = by_day.get(dkey, 0.0) + g
        mid = s + (e - s) / 2
        active = [(p, w) for (p, ps, pe, w) in wins if ps <= mid < pe]
        if not active:
            no_post += g
            continue
        tw = sum(w for _, w in active)
        for p, w in active:
            d = per.setdefault(p["post_id"], {"gain": 0.0, "excess": 0.0, "watch_only": True})
            d["gain"] += g * w / tw
            d["excess"] += x * w / tw
            if not it["watch"]:
                d["watch_only"] = False
    res["gain_with_no_post_running"] = rnd(no_post, 0)
    top_days = sorted(by_day.items(), key=lambda kv: -kv[1])[:5]
    res["days"] = [{"day": k, "gain": rnd(v, 0)} for k, v in top_days]

    out = {}
    for p, s, e, _ in wins:
        covered = s >= first and e <= last
        if covered:
            for it in intervals:
                if it["gap"] and it["a"]["at"] < e and it["b"]["at"] > s:
                    covered = False
                    break
        if not covered:
            continue
        d = per.get(p["post_id"], {"gain": 0.0, "excess": 0.0, "watch_only": False})
        out[p["post_id"]] = {
            "level": "watched" if d["watch_only"] else "measured",
            "evidence": "MEASURED",
            "gain_72h": rnd(d["gain"], 0),
            "excess_72h": rnd(d["excess"], 0),
            "share_of_gain": rnd(d["gain"] / res["total_gain"], 4) if res["total_gain"] else None,
        }
    return res, out


def estimated_signals(p, eligible_index, eligible, comments_by_post, med_rates, series_next, opts):
    """Signals that go with follows, each 0..1, or None when unknown. See references/numbers.md."""
    sig = {}
    raw = {}
    r = p.get("ratio")
    if r is not None:
        raw["outlier_ratio"] = rnd(r, 3)
        sig["outlier"] = clamp(log2(max(r, 1e-9)) / 3.0)
    reach = p.get("reach")
    if reach is not None and reach > 0:
        raw["views_per_follower"] = rnd(reach, 3)
        sig["stranger_reach"] = clamp(log2(reach) / 3.0)
    for k in ("share", "save"):
        x = (p.get("rates") or {}).get(k)
        m = med_rates.get(k)
        if x is not None and m:
            raw[k + "_rate_vs_median"] = rnd(x / m, 3)
            sig[k + "_rate"] = clamp(log2(max(x / m, 1e-9)) / 2.0)
    cl = comments_by_post.get(p["post_id"])
    if cl is not None:
        n = sum(1 for c in cl if c.get("author_is_creator") is not True and FOLLOW_RE.search(c.get("text") or ""))
        raw["follow_comments"] = n
        sig["follow_comments"] = clamp(n / 3.0)
    if p.get("baseline") and eligible_index is not None:
        nxt = [q["value"] for q in eligible[eligible_index + 1:eligible_index + 6] if q["value"] is not None]
        if len(nxt) >= 3:
            lift = median(nxt) / float(p["baseline"])
            raw["next_posts_vs_baseline"] = rnd(lift, 3)
            sig["raised_baseline"] = clamp(log2(max(lift, 1e-9)) / 1.5)
    if p["post_id"] in series_next:
        nr = series_next[p["post_id"]]
        if nr is not None:
            raw["part2_ratio"] = rnd(nr, 3)
            sig["part2_holds"] = 1.0 if nr >= 1.0 else 0.0
    known = [v for v in sig.values() if v is not None]
    sc = sum(known) / len(known) if known else None
    label = None
    if sc is not None:
        if sc >= 0.5 and len(known) >= 3:
            label = "likely brought followers"
        elif sc >= 0.3 and len(known) >= 2:
            label = "may have brought followers"
    return {"score": rnd(sc, 3), "signals_known": len(known), "signals": {k: rnd(v, 3) for k, v in sig.items()},
            "raw": raw, "label": label}


# ---------------------------------------------------------------------------------------------- timeline

def month_key(t):
    return t.strftime("%Y-%m")


def week_start(t):
    d = t.date() - dt.timedelta(days=t.weekday())
    return d


def timeline(posts, lo, hi, opts):
    inw = sorted([p for p in posts if p["in_window"]], key=lambda p: p["published_at"])
    months = []
    if inw:
        y, m = lo.year, lo.month
        while (y, m) <= (hi.year, hi.month):
            key = "%04d-%02d" % (y, m)
            ps = [p for p in inw if month_key(p["published_at"]) == key]
            types = {}
            for p in ps:
                types[p["type"]] = types.get(p["type"], 0) + 1
            months.append({
                "month": key, "posts": len(ps), "types": types,
                "median_views": median([p["views"] for p in ps if p["status"] != "too_new"]),
                "median_ratio": rnd(median([p["ratio"] for p in ps if p["ratio"] is not None]), 3),
                "hits": sum(1 for p in ps if p["ratio"] is not None and p["ratio"] >= opts["hit_ratio"]),
            })
            m += 1
            if m > 12:
                y, m = y + 1, 1
    weeks = []
    if inw:
        w = week_start(lo)
        end = week_start(hi)
        counts = {}
        for p in inw:
            k = week_start(p["published_at"])
            counts[k] = counts.get(k, 0) + 1
        while w <= end:
            weeks.append({"week": w.isoformat(), "posts": counts.get(w, 0)})
            w += dt.timedelta(days=7)
    marks = []
    # Pace changes: the 4 weeks after a boundary against the 4 weeks before.
    cand = []
    W = [x["posts"] for x in weeks]
    for i in range(4, len(W) - 3):
        before = sum(W[i - 4:i]) / 4.0
        after = sum(W[i:i + 4]) / 4.0
        if (after >= 2 * before and after - before >= 1) or (after <= 0.5 * before and before - after >= 1):
            cand.append((abs(log2((after + 0.25) / (before + 0.25))), i, before, after))
    cand.sort(reverse=True)
    taken = []
    for strength, i, before, after in cand:
        if any(abs(i - j) < 4 for j in taken):
            continue
        taken.append(i)
        marks.append({"at": weeks[i]["week"], "kind": "pace", "evidence": "MEASURED",
                      "text": "posting went from %.1f to %.1f a week" % (before, after)})
    # Mix changes: the month's most common type differs from the month before (3+ posts in both).
    prev = None
    for mo in months:
        if mo["posts"] >= 3:
            top = max(mo["types"].items(), key=lambda kv: kv[1])[0]
            if prev is not None and top != prev[1]:
                marks.append({"at": mo["month"] + "-01", "kind": "mix", "evidence": "MEASURED",
                              "text": "most posts became %s (was %s)" % (top, prev[1])})
            prev = (mo["month"], top)
    marks.sort(key=lambda m: m["at"])
    gaps = [(b["published_at"] - a["published_at"]).total_seconds() / 3600.0 for a, b in zip(inw, inw[1:])]
    wd = [0] * 7
    hrs = [0] * 24
    for p in inw:
        wd[p["published_at"].weekday()] += 1
        hrs[p["published_at"].hour] += 1
    rhythm = {
        "posts_per_week": rnd(len(inw) / max(1.0, (hi - lo).days / 7.0), 2) if inw else None,
        "median_hours_between_posts": rnd(median(gaps), 1),
        "weekday_counts_mon_first": wd,
        "hour_counts_utc": hrs,
    }
    return {"months": months, "weeks": weeks, "marks": marks, "rhythm": rhythm}


# ---------------------------------------------------------------------------------------------- picks

def deep_read_picks(scored, opts):
    n_out, n_ord, n_flop = opts["picks"]
    by = sorted(scored, key=lambda p: -p["ratio"])
    outl = [p for p in by if p["ratio"] >= opts["hit_ratio"]][:n_out]
    taken = set(p["post_id"] for p in outl)
    flops_c = [p for p in sorted(scored, key=lambda p: p["ratio"]) if p["ratio"] <= opts["flop_ratio"] and p["post_id"] not in taken]
    if not flops_c:
        flops_c = [p for p in sorted(scored, key=lambda p: p["ratio"]) if p["ratio"] < 0.75 and p["post_id"] not in taken]
    flops = flops_c[:n_flop]
    taken |= set(p["post_id"] for p in flops)
    ordc = [p for p in scored if 0.75 <= p["ratio"] <= 1.33 and p["post_id"] not in taken]
    ordc.sort(key=lambda p: p["published_at"])
    ordinary = []
    if ordc and n_ord:
        # spread over the window: one from each part of the window, the one closest to 1x in that part
        k = min(n_ord, len(ordc))
        size = len(ordc) / float(k)
        for j in range(k):
            part = ordc[int(j * size):int((j + 1) * size)] or ordc[-1:]
            ordinary.append(min(part, key=lambda p: abs(log2(p["ratio"]))))
    return {"outliers": [p["post_id"] for p in outl], "ordinary": [p["post_id"] for p in ordinary],
            "flops": [p["post_id"] for p in flops]}


# ---------------------------------------------------------------------------------------------- run

def run(folder, metric=None, opts=None):
    o = dict(DEFAULTS)
    o.update(opts or {})
    if os.environ.get("REA_MIN_AGE_DAYS"):
        o["min_age_days"] = float(os.environ["REA_MIN_AGE_DAYS"])
    rep = validate.validate(folder, inputs_only=True)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:20]]
        die("validate.py found %d error(s); fix them first:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    acc = load_account(folder)
    if o["min_age_days"] is None:
        o["min_age_days"] = MIN_AGE_DAYS.get(acc.get("network"), DEFAULT_MIN_AGE_DAYS)
    posts = load_posts(folder)
    comments = load_comments(folder)
    formats = load_formats(folder) or {}
    read_at = account_read_at(acc)
    out = {
        "schema": "rea-viral/analysis@1",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": input_fingerprint(folder),
        "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in o.items()},
        "account": {k: acc.get(k) for k in ("network", "handle", "name", "url", "bio", "link", "followers",
                                             "followers_exact", "following", "posts_total", "verified", "private")},
        "warnings": [w["where"] + ": " + w["problem"] for w in rep.warnings],
    }
    out["account"]["read_at"] = iso(read_at)
    lo, hi = account_window(acc)
    if acc.get("private"):
        out.update({"status": "private", "status_note": "The account is private: nothing public to read."})
    elif not posts:
        out.update({"status": "empty", "status_note": "The account has no posts that could be read."})
    m, note = choose_metric([p for p in posts if p["published_at"] is not None], metric)
    if note:
        out["warnings"].append(note)
    out["metric"] = m
    eligible, lo, hi = score(posts, acc, o, m)
    out["window"] = {"from": day(lo), "to": day(hi)}
    readings = follower_readings(folder, acc)
    current = acc.get("followers")
    comments_by_post = None
    if comments is not None:
        comments_by_post = {}
        for c in comments:
            comments_by_post.setdefault(c["post_id"], []).append(c)
    for p in posts:
        p["rates"] = rates(p)
        if p["published_at"] is not None:
            f, how = followers_at(readings, p["published_at"], current, read_at)
        else:
            f, how = None, "unknown"
        p["followers_at_post"] = {"value": rnd(f, 0), "how": how}
        p["reach"] = (p["views"] / float(f)) if (p["views"] is not None and f) else None
    scored = [p for p in posts if p["status"] == "scored"]
    med_rates = {k: median([p["rates"][k] for p in scored if p["rates"][k] is not None]) for k in RATE_KEYS}
    out["rates"] = {"median_" + k + "_rate": rnd(v, 5) for k, v in med_rates.items()}
    inw_dated = [p for p in posts if p["in_window"]]
    out["counts"] = {
        "posts_total": len(posts),
        "in_window": len(inw_dated),
        "scored": len(scored),
        "hits": sum(1 for p in scored if p["ratio"] >= o["hit_ratio"]),
    }
    for st in ("no_date", "too_new", "no_metric", "no_baseline", "warmup"):
        out["counts"][st] = sum(1 for p in posts if p["status"] == st)
    if "status" not in out:
        dated = [p for p in posts if p["published_at"] is not None]
        if not dated:
            out.update({"status": "no_dates", "status_note": "No post has a date: this source's rows cannot be used for baselines or "
                        "the timeline. Read the posts with a source whose rows carry dates."})
        elif len(inw_dated) < o["min_window_posts"]:
            out.update({"status": "too_few_posts", "status_note": "%d dated posts in the window; a pattern needs %d. The posts are "
                        "listed and no format is called." % (len(inw_dated), o["min_window_posts"])})
        else:
            out.update({"status": "ok", "status_note": None})

    # Series (from formats.json): the part that follows each first part.
    series_next = {}
    ratio_of = dict((p["post_id"], p["ratio"]) for p in posts)
    for s in formats.get("series") or []:
        ids = s.get("posts") or []
        if len(ids) >= 2:
            series_next[ids[0]] = ratio_of.get(ids[1])

    fol, measured = attribution(posts, readings, o)
    out["followers"] = fol
    out["followers"]["current"] = current
    out["followers"]["current_exact"] = acc.get("followers_exact")
    step = max(1, len(readings) // 400)
    out["followers"]["series"] = [{"at": iso(r["at"]), "followers": r["followers"], "source": "watch" if r["watch"] else r["source"]}
                                  for r in readings[::step]]
    if readings and out["followers"]["series"][-1]["at"] != iso(readings[-1]["at"]):
        r = readings[-1]
        out["followers"]["series"].append({"at": iso(r["at"]), "followers": r["followers"], "source": "watch" if r["watch"] else r["source"]})

    idx = dict((p["post_id"], i) for i, p in enumerate(eligible))
    levels = {"measured": 0, "watched": 0, "estimated": 0, "none": 0}
    for p in posts:
        if p["status"] not in ("scored", "no_baseline"):
            p["followers"] = {"level": "none", "reason": p["status"]}
            levels["none"] += 1
            continue
        est = estimated_signals(p, idx.get(p["post_id"]), eligible, comments_by_post or {}, med_rates, series_next, o)
        if p["post_id"] in measured:
            d = dict(measured[p["post_id"]])
            d["estimate_for_comparison"] = est
            p["followers"] = d
            levels[d["level"]] += 1
        elif est["score"] is not None:
            p["followers"] = {"level": "estimated", "evidence": "INFERRED", "score": est["score"], "label": est["label"],
                              "signals": est["signals"], "raw": est["raw"], "signals_known": est["signals_known"],
                              "basis": "signals that go with follows (references/numbers.md); never a count"}
            levels["estimated"] += 1
        else:
            p["followers"] = {"level": "none", "reason": "no signal known"}
            levels["none"] += 1
    out["attribution"] = {"levels": levels}
    meas = [p for p in posts if (p.get("followers") or {}).get("level") in ("measured", "watched")]
    meas.sort(key=lambda p: -(p["followers"].get("excess_72h") or 0))
    est = [p for p in posts if (p.get("followers") or {}).get("level") == "estimated"]
    est.sort(key=lambda p: -(p["followers"].get("score") or 0))
    out["attribution"]["top_measured"] = [p["post_id"] for p in meas[:10]]
    out["attribution"]["top_estimated"] = [p["post_id"] for p in est[:10]]

    out["timeline"] = timeline(posts, lo, hi, o) if posts else {"months": [], "weeks": [], "marks": [], "rhythm": {}}
    hits = sorted([p for p in scored if p["ratio"] >= o["hit_ratio"]], key=lambda p: -p["ratio"])
    flops = sorted([p for p in scored if p["ratio"] <= o["flop_ratio"]], key=lambda p: p["ratio"])
    out["outliers"] = [p["post_id"] for p in hits]
    out["flops"] = [p["post_id"] for p in flops]
    out["deep_read"] = deep_read_picks(scored, o) if scored else {"outliers": [], "ordinary": [], "flops": []}
    out["baseline"] = {
        "median_value_window": median([p["value"] for p in inw_dated if p.get("value") is not None]),
        "median_ratio": rnd(median([p["ratio"] for p in scored]), 3),
    }
    # Buckets any reading can lean on: length and weekday against the ratio (MEASURED, scored posts only).
    def bucket_rows(groups):
        rows_b = []
        for label, ps in groups:
            rs = [p["ratio"] for p in ps]
            rows_b.append({"bucket": label, "posts": len(ps), "median_ratio": rnd(median(rs), 3),
                           "hits": sum(1 for r in rs if r >= o["hit_ratio"]),
                           "flops": sum(1 for r in rs if r <= o["flop_ratio"])})
        return rows_b
    edges = [(0, 10, "under 10 s"), (10, 15, "10-15 s"), (15, 30, "15-30 s"), (30, 60, "30-60 s"), (60, 1e9, "60 s and over")]
    out["by_length"] = bucket_rows([(lab, [p for p in scored if p["duration_s"] is not None and a <= p["duration_s"] < b])
                                    for a, b, lab in edges])
    out["by_length"].append({"bucket": "length unknown", "posts": sum(1 for p in scored if p["duration_s"] is None)})
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out["by_weekday_utc"] = bucket_rows([(days[d], [p for p in scored if p["published_at"].weekday() == d]) for d in range(7)])
    by_type = {}
    for p in scored:
        by_type.setdefault(p["type"], []).append(p)
    out["by_type"] = bucket_rows(sorted(by_type.items()))
    out["excluded"] = [{"post_id": p["post_id"], "reason": p["status"]} for p in posts
                       if p["status"] in ("no_date", "too_new", "no_metric")]

    rows = []
    for p in sorted(posts, key=lambda p: (p["published_at"] is None, p["published_at"] or read_at, p["post_id"])):
        f = p.get("followers") or {}
        rec = {
            "post_id": p["post_id"], "url": p["url"], "published_at": iso(p["published_at"]), "type": p["type"],
            "duration_s": p["duration_s"], "views": p["views"], "likes": p["likes"], "comments": p["comments"],
            "shares": p["shares"], "saves": p["saves"], "reposts": p.get("reposts"), "quotes": p.get("quotes"),
            "bookmarks": p.get("bookmarks"), "in_window": p["in_window"], "status": p["status"],
            "baseline": rnd(p["baseline"], 1) if p["baseline"] is not None else None,
            "baseline_n": p.get("baseline_n"),
            "ratio": rnd(p["ratio"], 3), "hit": bool(p["ratio"] is not None and p["ratio"] >= o["hit_ratio"]),
            "rates": {k: rnd(v, 5) for k, v in p["rates"].items()},
            "followers_at_post": p["followers_at_post"], "views_per_follower": rnd(p["reach"], 4),
            "followers": f, "caption": (p["caption"] or "")[:400], "cover_file": p["cover_file"] or None,
            "cover_url": p["cover_url"] or None, "video_file": p["video_file"] or None, "sound": p["sound"] or None,
            "is_pinned": p["is_pinned"], "is_paid": p["is_paid"], "collaborators": p["collaborators"] or None,
        }
        rows.append(rec)
    out["posts"] = rows
    return out


def write_outputs(folder, out):
    write_json(os.path.join(folder, "analysis.json"), out)
    header = ["post_id", "published_at", "type", "duration_s", "status", "views", "likes", "comments", "shares", "saves",
              "reposts", "quotes", "bookmarks", "baseline", "ratio", "hit", "share_rate", "save_rate", "views_per_follower", "followers_level",
              "gain_72h", "excess_72h", "estimate_score", "estimate_label", "url", "caption"]
    rows = []
    for p in out["posts"]:
        f = p["followers"] or {}
        est = f.get("estimate_for_comparison") or {}
        rows.append({
            "post_id": p["post_id"], "published_at": p["published_at"], "type": p["type"],
            "duration_s": p["duration_s"], "caption": (p["caption"] or "").replace("\n", " ")[:120], "status": p["status"],
            "views": p["views"], "likes": p["likes"], "comments": p["comments"], "shares": p["shares"], "saves": p["saves"],
            "reposts": p.get("reposts"), "quotes": p.get("quotes"), "bookmarks": p.get("bookmarks"),
            "baseline": p["baseline"], "ratio": p["ratio"], "hit": "true" if p["hit"] else "false",
            "share_rate": p["rates"]["share"], "save_rate": p["rates"]["save"],
            "views_per_follower": p["views_per_follower"], "followers_level": f.get("level"),
            "gain_72h": f.get("gain_72h"), "excess_72h": f.get("excess_72h"),
            "estimate_score": f.get("score", est.get("score")), "estimate_label": f.get("label", est.get("label")),
            "url": p["url"],
        })
    write_csv(os.path.join(folder, "posts_scored.csv"), header, rows)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    if len(argv) >= 2 and os.path.exists(os.path.join(argv[1], "niche.json")):
        die("%s is a niche folder: run trends.py" % argv[1])
    folder = argv[1]
    metric = None
    if "--metric" in argv:
        metric = argv[argv.index("--metric") + 1]
        if metric not in ("views", "likes"):
            die("--metric is views or likes")
    if "--now" in argv:
        os.environ["REA_NOW"] = argv[argv.index("--now") + 1]
        parse_time(os.environ["REA_NOW"])
    if "--min-age-days" in argv:
        os.environ["REA_MIN_AGE_DAYS"] = str(float(argv[argv.index("--min-age-days") + 1]))
    out = run(folder, metric)
    write_outputs(folder, out)
    c = out["counts"]
    print("analysis.json: status %s; %d posts, %d in the window, %d scored, %d hits (>= %.0fx); metric %s"
          % (out["status"], c["posts_total"], c["in_window"], c["scored"], c["hits"], DEFAULTS["hit_ratio"], out["metric"]))
    lv = out["attribution"]["levels"]
    print("followers: %d measured, %d watched, %d estimated, %d none" % (lv["measured"], lv["watched"], lv["estimated"], lv["none"]))
    dr = out["deep_read"]
    print("deep read: outliers %s | ordinary %s | flops %s" % (", ".join(dr["outliers"]) or "-", ", ".join(dr["ordinary"]) or "-",
                                                               ", ".join(dr["flops"]) or "-"))
    for w in out["warnings"][:8]:
        print("warning: " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
