#!/usr/bin/env python3
"""Topic check: is a topic still worth posting right now? (saturation + momentum + lateness).

    python3 topic_check.py <topic or niche folder> [--user-followers N] [--big-views N] [--now ISO]

Works in two places:
- Standalone topic folder: topic.json + topic_posts.csv (writes topic_check.json and TOPIC.md; build_report.py also
  builds report.html and report-light.html).
- Inside a niche folder: niche.json + topic_posts.csv (optional; falls back to the niche's creator posts in the last
  48 h when topic_posts.csv is absent). report_niche.py embeds the Topic check block in report.html and NICHE.md.

What it measures (all MEASURED from the rows read; never invented):
1. Saturation (last 48 h): biggest posts (views, author, author followers). Flags large accounts
   (>= max(10,000, 10x user_followers), or >= 100,000 when user_followers is unknown) that already have a breakout
   (>= 100,000 views by default). Level: low / medium / taken.
2. Momentum (last 6 h vs previous 6 h): post counts and posts/hour in each 6 h window. Level: rising / flat / fading /
   not_enough_data (under 4 posts across both 6 h windows).
3. Lateness: hours since the first big post (>= big_views) in the last 48 h. Band: none_yet / early (<2 h) /
   tight (2-6 h) / late (>=6 h).
4. Verdict: one plain line combining saturation, momentum, lateness and the biggest proof post.

Rules: real numbers only, sample size shown per window, explicitly marked as a sample when the reader could not filter
by time (sampled=true in topic_posts.csv or time_filter_supported=false in topic.json / niche.json).
"""
import datetime as dt
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    SKILL_VERSION, ShapeError, die, iso, load_posts, niche_creator_dirs, norm_handle, now_utc, parse_bool, parse_count,
    parse_time, read_csv, read_json, rnd, write_json, write_text,
)
from analyze import input_fingerprint  # noqa: E402

RULES = {
    "saturation_hours": 48,        # look-back window for saturation & first big post
    "momentum_hours": 6,           # each momentum window (last 6 h vs previous 6 h)
    "big_views": 100000,           # breakout threshold on a topic
    "medium_views": 25000,         # active / heating-up threshold
    "large_account_min": 10000,    # floor when user_followers is known (max(10K, 10x user_followers))
    "large_account_times": 10,     # multiplier of user_followers
    "large_account_default": 100000,  # large-account threshold when user_followers is unknown
    "min_momentum_posts": 4,       # fewer posts across both 6 h windows -> not_enough_data
    "rising_ratio": 1.33,          # last_6h / prev_6h >= this -> rising
    "fading_ratio": 0.75,          # last_6h / prev_6h <= this -> fading
    "taken_breakouts": 3,          # this many breakouts (>= big_views) in 48 h = taken even without a giant
    "early_hours": 2.0,            # under 2 h since first big post -> early
    "late_hours": 6.0,             # 6 h or more since first big post -> late
}


def _compact(n):
    if n is None:
        return "-"
    v = float(n)
    a = abs(v)
    if a >= 1e6:
        s = "%.1fM" % (v / 1e6)
    elif a >= 1e5:
        s = "%dK" % round(v / 1e3)
    elif a >= 1e3:
        s = "%.1fK" % (v / 1e3)
    else:
        return "%d" % round(v)
    return s.replace(".0K", "K").replace(".0M", "M")


def _count(v):
    try:
        return parse_count(v)
    except ShapeError:
        return None


def _time(v):
    try:
        return parse_time(v)
    except ShapeError:
        return None


def _bool(v):
    try:
        return parse_bool(v)
    except ShapeError:
        return None


def load_meta(folder):
    tp = os.path.join(folder, "topic.json")
    np_ = os.path.join(folder, "niche.json")
    if os.path.exists(tp):
        doc = read_json(tp)
        return doc, "topic"
    if os.path.exists(np_):
        doc = read_json(np_)
        return doc, "niche"
    die("no topic.json or niche.json in %s" % folder, 2)


def load_topic_posts(folder, kind):
    """Load topic_posts.csv when present; in a niche folder, fall back to creator posts when absent."""
    tp = os.path.join(folder, "topic_posts.csv")
    if os.path.exists(tp):
        _, rows = read_csv(tp)
        out = []
        for i, r in enumerate(rows):
            pid = (r.get("post_id") or "").strip() or ("row-%d" % (i + 2))
            out.append({
                "post_id": pid,
                "url": (r.get("url") or "").strip(),
                "network": (r.get("network") or "").strip().lower() or None,
                "author": (r.get("author") or "").strip().lstrip("@"),
                "author_followers": _count(r.get("author_followers")),
                "published_at": _time(r.get("published_at")),
                "views": _count(r.get("views")),
                "likes": _count(r.get("likes")),
                "comments": _count(r.get("comments")),
                "reposts": _count(r.get("reposts")),
                "caption": (r.get("caption") or "").strip(),
                "window_tag": (r.get("window_tag") or "").strip().lower() or None,
                "sampled": _bool(r.get("sampled")),
                "source": (r.get("source") or "").strip() or None,
            })
        return out, "topic_posts.csv"
    if kind == "niche":
        out = []
        for d in niche_creator_dirs(folder):
            acc = read_json(os.path.join(folder, d, "account.json"))
            handle = norm_handle(acc.get("handle"))
            fol = acc.get("followers") if isinstance(acc.get("followers"), int) else None
            net = acc.get("network")
            for p in load_posts(os.path.join(folder, d)):
                out.append({
                    "post_id": p["post_id"],
                    "url": p["url"],
                    "network": net,
                    "author": handle,
                    "author_followers": fol,
                    "published_at": p["published_at"],
                    "views": p["views"],
                    "likes": p["likes"],
                    "comments": p["comments"],
                    "reposts": p.get("reposts"),
                    "caption": (p.get("caption") or "").strip(),
                    "window_tag": None,
                    "sampled": True,
                    "source": "niche creator folders",
                })
        return out, "accounts/*/posts.csv"
    return [], None


def _hours_ago(t, read_at):
    if t is None or read_at is None:
        return None
    return max(0.0, (read_at - t).total_seconds() / 3600.0)


def _format_hours(h):
    if h is None:
        return "-"
    if h < 1.0:
        return "%d min" % max(1, round(h * 60))
    if h < 10.0:
        s = ("%.1f" % h).rstrip("0").rstrip(".")
        return "%sh" % s
    return "%dh" % round(h)


def _verdict(sat_level, mom_level, late_band, sat, mom, late, sampled):
    top_large = (sat.get("large_account_breakouts") or [None])[0]
    top_any = (sat.get("top_posts") or [None])[0]
    first_big = late.get("first_big_post")
    suffix = " (from sample)" if sampled else ""

    if sat_level == "unknown":
        return "Not enough recent posts read to judge this topic yet."

    if sat_level == "taken":
        owner = top_large or first_big or top_any
        who = ("@%s (%s, %s ago)" % (owner["author"], _compact(owner["views"]), _format_hours(owner["hours_ago"]))) if owner else "large accounts"
        if mom_level == "fading" or late_band == "late":
            return "Taken by %s and %s — skip or find a new angle%s" % (
                who, "fading" if mom_level == "fading" else "already late", suffix)
        return "Taken by %s — skip a basic take, only post with a sharp new angle or visual%s" % (who, suffix)

    if sat_level == "low":
        if mom_level == "rising":
            return "Rising, not taken yet — post within hours with your own visual%s" % suffix
        if mom_level == "fading":
            return "Not taken, but fading (%d → %d posts/6h) — only worth posting if you own the angle%s" % (
                mom["prev_6h"]["posts"], mom["last_6h"]["posts"], suffix)
        if mom_level == "flat":
            return "Steady and not taken yet — room to stand out with a clear visual%s" % suffix
        return "Not taken yet (small sample: %d posts in 12h) — room to be first with your own visual%s" % (
            mom["last_6h"]["posts"] + mom["prev_6h"]["posts"], suffix)

    # medium saturation
    lead = first_big or top_any
    who = ("@%s (%s, %s ago)" % (lead["author"], _compact(lead["views"]), _format_hours(lead["hours_ago"]))) if lead else "early posts"
    if late_band == "late":
        return "Heating up, already %s past %s — skip an explainer, only post a fresh angle%s" % (
            _format_hours(late.get("hours_since_first_big")), who, suffix)
    if mom_level == "rising":
        return "Rising and heating up (top: %s) — post within hours with your own visual%s" % (who, suffix)
    if mom_level == "fading":
        return "Peaked and fading (top: %s) — skip unless you have a contrarian take%s" % (who, suffix)
    return "Active, not owned by a large account yet (top: %s) — worth posting with a distinct angle%s" % (who, suffix)


def topic_input_files(folder, kind):
    files = ["topic.json" if kind == "topic" else "niche.json", "topic_posts.csv"]
    if kind == "niche" and not os.path.exists(os.path.join(folder, "topic_posts.csv")):
        for d in niche_creator_dirs(folder):
            files += [d + "/account.json", d + "/posts.csv"]
    return tuple(files)


def run(folder, opts=None):
    rules = dict(RULES)
    rules.update(opts or {})
    meta, kind = load_meta(folder)
    read_at = parse_time(meta.get("read_at")) if meta.get("read_at") else now_utc()
    user_fol = rules.get("user_followers")
    if user_fol is None:
        u = meta.get("user") or {}
        if isinstance(u, dict) and isinstance(u.get("followers"), int):
            user_fol = u["followers"]
        elif isinstance(meta.get("user_followers"), int):
            user_fol = meta["user_followers"]
    if user_fol is not None:
        large_thr = max(rules["large_account_min"], rules["large_account_times"] * int(user_fol))
        large_rule = "%s followers or more (max 10K, 10x your %s followers)" % ("{:,}".format(large_thr), "{:,}".format(int(user_fol)))
    else:
        large_thr = rules["large_account_default"]
        large_rule = "%s followers or more (default; user follower count unknown)" % "{:,}".format(large_thr)

    rows, source_file = load_topic_posts(folder, kind)
    # Deduplicate by post_id keeping highest views if repeated across two window fetches.
    dedup = {}
    for r in rows:
        pid = r["post_id"]
        if pid not in dedup or (r.get("views") or -1) > (dedup[pid].get("views") or -1):
            dedup[pid] = r
    posts = list(dedup.values())

    sampled_rows = any(p.get("sampled") is True for p in posts)
    time_filter = meta.get("time_filter_supported")
    sampled = bool(sampled_rows or time_filter is False or source_file == "accounts/*/posts.csv")
    sample_note = None
    if sampled:
        if source_file == "accounts/*/posts.csv":
            sample_note = ("Sample from the niche's creator folders (no topic_posts.csv time-window search); "
                           "post rates reflect the tracked creators, not the whole network.")
        else:
            sample_note = ("Sample only: the reader could not filter strictly by time window, so counts and "
                           "posts/hour reflect the returned sample rather than every post in each 6h window.")

    sat_h = float(rules["saturation_hours"])
    mom_h = float(rules["momentum_hours"])
    big_v = int(rules["big_views"])
    med_v = int(rules["medium_views"])

    enriched = []
    for p in posts:
        h_ago = _hours_ago(p["published_at"], read_at)
        v = p.get("views")
        fol = p.get("author_followers")
        is_large = bool(fol is not None and fol >= large_thr)
        is_breakout = bool(v is not None and v >= big_v)
        # Determine momentum bucket: exact timestamp preferred, window_tag fallback
        wt = p.get("window_tag")
        if h_ago is not None:
            if h_ago <= mom_h:
                bucket = "last_6h"
            elif h_ago <= 2 * mom_h:
                bucket = "prev_6h"
            elif h_ago <= 24.0:
                bucket = "12h_24h"
            elif h_ago <= sat_h:
                bucket = "24h_48h"
            else:
                bucket = "older"
        elif wt in ("last_6h", "prev_6h", "24h", "48h"):
            bucket = wt
        else:
            bucket = "unknown"
        enriched.append({
            "post_id": p["post_id"],
            "url": p["url"],
            "network": p["network"],
            "author": p["author"],
            "author_followers": fol,
            "published_at": iso(p["published_at"]),
            "hours_ago": rnd(h_ago, 2),
            "views": v,
            "likes": p.get("likes"),
            "comments": p.get("comments"),
            "reposts": p.get("reposts"),
            "large_account": is_large,
            "breakout": is_breakout,
            "bucket": bucket,
            "caption": p["caption"][:240],
            "source": p["source"],
        })

    in_48h = [p for p in enriched if p["bucket"] in ("last_6h", "prev_6h", "12h_24h", "24h_48h", "24h", "48h")]
    in_24h = [p for p in enriched if p["bucket"] in ("last_6h", "prev_6h", "12h_24h", "24h")]
    last_6h = [p for p in enriched if p["bucket"] == "last_6h"]
    prev_6h = [p for p in enriched if p["bucket"] == "prev_6h"]

    # 1. Saturation
    by_views = sorted([p for p in in_48h if p["views"] is not None], key=lambda p: (-p["views"], p["post_id"]))
    breakouts = [p for p in by_views if p["breakout"]]
    large_breakouts = [p for p in breakouts if p["large_account"]]
    strong_posts = [p for p in by_views if p["views"] >= med_v]
    large_strong = [p for p in strong_posts if p["large_account"]]

    if not in_48h:
        sat_level = "unknown"
    elif large_breakouts or len(breakouts) >= rules["taken_breakouts"]:
        sat_level = "taken"
    elif breakouts or len(strong_posts) >= 2 or large_strong:
        sat_level = "medium"
    else:
        sat_level = "low"

    saturation = {
        "level": sat_level,
        "window_hours": int(sat_h),
        "posts_in_window": len(in_48h),
        "posts_with_views": len(by_views),
        "breakouts_count": len(breakouts),
        "strong_posts_count": len(strong_posts),
        "large_account_threshold": large_thr,
        "large_account_rule": large_rule,
        "big_views_threshold": big_v,
        "large_account_breakouts": large_breakouts[:5],
        "top_posts": by_views[:6],
        "evidence": "MEASURED",
    }

    # 2. Momentum (last 6 h vs previous 6 h)
    n_last, n_prev = len(last_6h), len(prev_6h)
    rate_last = rnd(n_last / mom_h, 2)
    rate_prev = rnd(n_prev / mom_h, 2)
    mom_ratio = rnd(n_last / float(n_prev), 2) if n_prev > 0 else None
    if n_last + n_prev < rules["min_momentum_posts"]:
        mom_level = "not_enough_data"
    elif n_prev == 0:
        mom_level = "rising"
    elif mom_ratio >= rules["rising_ratio"]:
        mom_level = "rising"
    elif mom_ratio <= rules["fading_ratio"]:
        mom_level = "fading"
    else:
        mom_level = "flat"

    momentum = {
        "level": mom_level,
        "window_hours": int(mom_h),
        "last_6h": {"posts": n_last, "per_hour": rate_last},
        "prev_6h": {"posts": n_prev, "per_hour": rate_prev},
        "ratio": mom_ratio,
        "min_posts_needed": rules["min_momentum_posts"],
        "sampled": sampled,
        "evidence": "MEASURED",
    }

    # 3. Lateness (hours since first big post in last 48 h)
    dated_breakouts = [p for p in breakouts if p["hours_ago"] is not None]
    if dated_breakouts:
        first_big = max(dated_breakouts, key=lambda p: p["hours_ago"])
        h_first = first_big["hours_ago"]
        if h_first < rules["early_hours"]:
            late_band = "early"
        elif h_first < rules["late_hours"]:
            late_band = "tight"
        else:
            late_band = "late"
    else:
        first_big, h_first, late_band = None, None, "none_yet"

    lateness = {
        "band": late_band,
        "hours_since_first_big": rnd(h_first, 1),
        "first_big_post": first_big,
        "big_views_threshold": big_v,
        "benchmark_note": ("Empirical benchmark: follow-up 2h after a 666K breakout got 3.9K; an explainer 13h late "
                           "flopped — once past 2h, only a fresh visual or distinct angle competes."),
        "evidence": "MEASURED",
    }

    sample_sizes = {
        "total_read": len(enriched),
        "last_6h": n_last,
        "prev_6h": n_prev,
        "last_24h": len(in_24h),
        "last_48h": len(in_48h),
    }

    verdict = _verdict(sat_level, mom_level, late_band, saturation, momentum, lateness, sampled)
    topic_name = meta.get("topic") or meta.get("name") or os.path.basename(os.path.abspath(folder))
    status = "ok" if in_48h else "no_recent_posts"
    status_note = None if in_48h else "No posts within the last %d hours were read." % int(sat_h)

    return {
        "schema": "rea-viral/topic-check@1",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": input_fingerprint(folder, topic_input_files(folder, kind)),
        "kind": kind,
        "topic": topic_name,
        "query": meta.get("query") or (meta.get("words") or [topic_name])[0] if isinstance(meta.get("words"), list) and meta.get("words") else (meta.get("query") or topic_name),
        "networks": meta.get("networks") or ([meta["network"]] if meta.get("network") else []),
        "read_at": iso(read_at),
        "source_file": source_file,
        "status": status,
        "status_note": status_note,
        "sampled": sampled,
        "sample_note": sample_note,
        "sample_sizes": sample_sizes,
        "rules": {
            "saturation_hours": int(sat_h),
            "momentum_hours": int(mom_h),
            "big_views": big_v,
            "large_account_followers": large_thr,
            "large_account_rule": large_rule,
            "min_momentum_posts": rules["min_momentum_posts"],
        },
        "saturation": saturation,
        "momentum": momentum,
        "lateness": lateness,
        "verdict": verdict,
        "posts": sorted(in_48h, key=lambda p: (-(p["views"] or -1), p["hours_ago"] if p["hours_ago"] is not None else 999))[:20],
    }


def topic_md(tc):
    sat, mom, late = tc["saturation"], tc["momentum"], tc["lateness"]
    sz = tc["sample_sizes"]
    L = [
        "# %s: Topic check (REA Viral)" % tc["topic"],
        "",
        "Read %s%s. Every number is MEASURED by topic_check.py (topic_check.json). Built by REA Viral %s." % (
            (tc.get("read_at") or "")[:16].replace("T", " "),
            (" on " + ", ".join(tc["networks"])) if tc.get("networks") else "",
            tc.get("skill_version") or SKILL_VERSION),
        "",
        "## Verdict",
        "",
        "- [MEASURED] **%s** (topic_check.json#verdict)" % tc["verdict"],
    ]
    if tc.get("sampled") and tc.get("sample_note"):
        L.append("- Note: %s" % tc["sample_note"])
    L += [
        "",
        "## Summary",
        "",
        "| Signal | Level | Measured | Read |",
        "|---|---|---|---|",
        "| Saturation (last %dh) | **%s** | %d posts read, %d breakouts (>= %s views), %d by large accounts (%s) | topic_check.json#saturation |" % (
            sat["window_hours"], sat["level"], sat["posts_in_window"], sat["breakouts_count"],
            _compact(sat["big_views_threshold"]), len(sat["large_account_breakouts"]), sat["large_account_rule"]),
        "| Momentum (6h vs prev 6h) | **%s** | last 6h: %d posts (%s/h) vs prev 6h: %d posts (%s/h)%s | topic_check.json#momentum |" % (
            mom["level"], mom["last_6h"]["posts"], mom["last_6h"]["per_hour"],
            mom["prev_6h"]["posts"], mom["prev_6h"]["per_hour"],
            (", ratio %sx" % mom["ratio"]) if mom.get("ratio") is not None else ""),
        "| Lateness | **%s** | %s | topic_check.json#lateness |" % (
            late["band"],
            ("%s since first %s+ post (@%s, %s views)" % (
                _format_hours(late["hours_since_first_big"]), _compact(late["big_views_threshold"]),
                late["first_big_post"]["author"], _compact(late["first_big_post"]["views"])))
            if late.get("first_big_post") else "no %s+ breakout yet in the last %dh" % (_compact(late["big_views_threshold"]), sat["window_hours"])),
        "| Sample size | %s | total %d · last 6h: %d · prev 6h: %d · 24h: %d · 48h: %d | topic_check.json#sample_sizes |" % (
            "sample" if tc.get("sampled") else "windowed", sz["total_read"], sz["last_6h"], sz["prev_6h"], sz["last_24h"], sz["last_48h"]),
        "",
    ]
    if sat.get("top_posts"):
        L += [
            "## Biggest posts in the last %dh (MEASURED)" % sat["window_hours"],
            "",
            "| Post | Author | Followers | Views | Age | Flags |",
            "|---|---|---|---|---|---|",
        ]
        for p in sat["top_posts"]:
            flags = []
            if p["large_account"]:
                flags.append("large account")
            if p["breakout"]:
                flags.append("breakout")
            link = "[%s](%s)" % (p["post_id"], p["url"]) if p.get("url") else p["post_id"]
            L.append("| %s | @%s | %s | %s | %s | %s |" % (
                link, p["author"] or "-", _compact(p["author_followers"]), _compact(p["views"]),
                _format_hours(p["hours_ago"]), ", ".join(flags) or "-"))
        L.append("")
    L += [
        "## Lateness benchmark",
        "",
        "- %s" % late["benchmark_note"],
        "",
    ]
    return "\n".join(L)


def stale(folder):
    p = os.path.join(folder, "topic_check.json")
    if not os.path.exists(p):
        return None
    doc = read_json(p)
    kind = doc.get("kind") or ("topic" if os.path.exists(os.path.join(folder, "topic.json")) else "niche")
    was = doc.get("inputs") or {}
    now_files = topic_input_files(folder, kind)
    have = input_fingerprint(folder, tuple(set(was.keys()) | set(now_files)))
    changed = sorted(k for k in set(was) | set(now_files) if have.get(k) != was.get(k))
    if changed:
        return "topic_check.json was made before %s changed: run topic_check.py again" % ", ".join(changed[:6])
    return None


def write(folder, opts=None):
    tc = run(folder, opts)
    write_json(os.path.join(folder, "topic_check.json"), tc)
    write_text(os.path.join(folder, "TOPIC.md"), topic_md(tc))
    return tc


# ---------------------------------------------------------------------------------------------- standalone HTML report

TOPIC_BODY = r"""
var drawn = {topic: 0};
window.__reaReport = {drawn: drawn, ready: false, kind: 'topic'};
var TC = D.topic_check || {}, SAT = TC.saturation || {}, MOM = TC.momentum || {}, LATE = TC.lateness || {}, SZ = TC.sample_sizes || {};
function fmtH(h){ if (h == null) return '—'; if (h < 1) return Math.max(1, Math.round(h * 60)) + ' min'; return (h < 10 ? h.toFixed(1).replace(/\.0$/, '') : Math.round(h)) + 'h'; }

app.appendChild(el('header', {cls: 'top'},
  el('div', null,
    el('div', {cls: 'kicker', text: 'REA Viral · Topic check · ' + ((TC.networks || []).join(', ') || 'topic') + ' · read ' + date(TC.read_at)}),
    el('h1', {text: TC.topic || 'Topic check'}),
    el('div', {cls: 'sub', text: 'Is this topic still worth posting right now? Saturation (48h) + momentum (6h vs 6h) + lateness.'})),
  el('div', {cls: 'row'}, themeButton())));

app.appendChild(el('div', {cls: 'stats'},
  stat(String(SAT.level || '—').toUpperCase(), 'saturation (last ' + (SAT.window_hours || 48) + 'h)'),
  stat(String(MOM.level || '—').replace(/_/g, ' ').toUpperCase(), (MOM.last_6h ? MOM.last_6h.per_hour + '/h now vs ' + MOM.prev_6h.per_hour + '/h prev' : 'momentum')),
  stat(LATE.hours_since_first_big != null ? fmtH(LATE.hours_since_first_big) : 'none yet', 'since first ' + num(LATE.big_views_threshold || 100000) + '+ post'),
  stat(String(SZ.last_48h || 0), 'posts read in 48h' + (TC.sampled ? ' (sample)' : ''))));

app.appendChild(legend());
if (TC.sampled && TC.sample_note) app.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Sample only. '}), TC.sample_note));

(function(){
  var s = section('verdict', 'Verdict', 'Built from saturation, 6h momentum, and hours since the first breakout.');
  var p = el('div', {cls: 'panel'});
  p.appendChild(el('div', {cls: 'answer'}, chip('MEASURED'), TC.verdict || '—'));
  p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:8px'},
    'Sample sizes: total ' + (SZ.total_read || 0) + ' · last 6h: ' + (SZ.last_6h || 0) + ' · prev 6h: ' + (SZ.prev_6h || 0) +
    ' · last 24h: ' + (SZ.last_24h || 0) + ' · last 48h: ' + (SZ.last_48h || 0) + '. ' + (LATE.benchmark_note || '')));
  s.appendChild(p);
  drawn.topic++;
})();

(function(){
  var s = section('momentum', 'Momentum: last 6h vs previous 6h', 'Posts per hour across two 6-hour windows (cheap 1-page search each).');
  var p = el('div', {cls: 'panel'});
  var l6 = (MOM.last_6h || {}).posts || 0, p6 = (MOM.prev_6h || {}).posts || 0, mx = Math.max(l6, p6, 1);
  var svg = sv('svg', {viewBox: '0 0 560 110', 'class': 'chart', role: 'img', 'aria-label': 'Posts in previous 6h vs last 6h'});
  [['Previous 6h', p6, (MOM.prev_6h || {}).per_hour || 0, 18, 'var(--faint)'],
   ['Last 6h', l6, (MOM.last_6h || {}).per_hour || 0, 62, MOM.level === 'rising' ? 'var(--scale)' : (MOM.level === 'fading' ? 'var(--drop)' : 'var(--under)')]].forEach(function(b){
    svg.appendChild(sv('text', {x: 8, y: b[3] + 19, text: b[0]}));
    var w = Math.max(6, Math.round(330 * b[1] / mx));
    svg.appendChild(sv('rect', {x: 108, y: b[3], width: w, height: 28, rx: 5, fill: b[4], opacity: 0.9}));
    svg.appendChild(sv('text', {x: 118 + w, y: b[3] + 19, text: b[1] + ' posts (' + b[2] + '/h)'}));
  });
  p.appendChild(svg);
  s.appendChild(p);
  drawn.topic++;
})();

(function(){
  var s = section('saturation', 'Biggest posts in the last ' + (SAT.window_hours || 48) + 'h', 'Large account threshold: ' + (SAT.large_account_rule || '') + '. Breakout: ' + num(SAT.big_views_threshold || 100000) + '+ views.');
  var p = el('div', {cls: 'panel'});
  var rows = SAT.top_posts || [];
  if (!rows.length) p.appendChild(el('div', {cls: 'empty', text: 'No posts with views in the last 48h.'}));
  else {
    var t = el('table', null, el('tr', null, el('th', {text: 'Post'}), el('th', {text: 'Author'}), el('th', {cls: 'num', text: 'Followers'}), el('th', {cls: 'num', text: 'Views'}), el('th', {cls: 'num', text: 'Age'}), el('th', {text: 'Flags'})));
    rows.forEach(function(r){
      var fl = []; if (r.large_account) fl.push('large account'); if (r.breakout) fl.push('breakout');
      t.appendChild(el('tr', null,
        el('td', null, r.url ? el('a', {href: r.url, text: r.post_id}) : r.post_id, r.caption ? el('div', {cls: 'small muted', text: r.caption.slice(0, 90)}) : null),
        el('td', {text: '@' + (r.author || '—')}),
        el('td', {cls: 'num', text: num(r.author_followers)}),
        el('td', {cls: 'num'}, el('strong', {text: num(r.views)})),
        el('td', {cls: 'num', text: fmtH(r.hours_ago)}),
        el('td', {cls: 'small', text: fl.join(', ') || '—'})));
      drawn.topic++;
    });
    p.appendChild(t);
  }
  s.appendChild(p);
})();

sourcesSection(D.sources, (D.findings || {}).not_read, D.cost, [TC.sampled ? TC.sample_note : null].filter(Boolean), []);
app.appendChild(el('footer', null, 'Topic check report. Built ' + D.built_at + ' by REA Viral ' + D.skill_version + ' from topic_check.json.'));
stackTables();
window.__reaReport.ready = true;
"""


def build_report(folder, light_only=False):
    import page_kit
    import validate
    rep = validate.validate(folder)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:30]]
        die("validate.py found %d error(s); the page is not built:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    p = os.path.join(folder, "topic_check.json")
    if not os.path.exists(p):
        tc = write(folder)
    else:
        st = stale(folder)
        if st:
            die(st, 1)
        tc = read_json(p)
    meta, _ = load_meta(folder)
    cost = {"rows": [], "total_usd": 0.0}
    cp = os.path.join(folder, "cost.csv")
    if os.path.exists(cp):
        _, rows = read_csv(cp)
        cost = {"rows": rows, "total_usd": round(sum(float(r.get("total_usd") or 0) for r in rows), 4)}
    fp = os.path.join(folder, "findings.json")
    d = {
        "skill_version": SKILL_VERSION,
        "built_at": iso(now_utc()),
        "topic_check": tc,
        "findings": read_json(fp) if os.path.exists(fp) else {},
        "sources": meta.get("sources") or [],
        "cost": cost,
        "pictures": {"inside": 0, "left_out": 0, "light": light_only},
    }
    title = "%s · Topic check · REA Viral" % (tc.get("topic") or "Topic")
    if not light_only:
        write_text(os.path.join(folder, "report.html"), page_kit.page(title, "TOPIC.md", d, TOPIC_BODY))
    write_text(os.path.join(folder, "report-light.html"), page_kit.page(title, "TOPIC.md", page_kit.light_data(d), TOPIC_BODY))
    write_text(os.path.join(folder, "TOPIC.md"), topic_md(tc))
    d["light_only"] = light_only
    return d


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    opts = {}
    if "--user-followers" in argv:
        opts["user_followers"] = int(argv[argv.index("--user-followers") + 1])
    if "--big-views" in argv:
        opts["big_views"] = int(argv[argv.index("--big-views") + 1])
    if "--now" in argv:
        os.environ["REA_NOW"] = argv[argv.index("--now") + 1]
        parse_time(os.environ["REA_NOW"])
    tc = write(folder, opts)
    sat, mom, late = tc["saturation"], tc["momentum"], tc["lateness"]
    print("topic_check.json and TOPIC.md: %s" % tc["verdict"])
    print("  saturation: %s (%d posts in %dh, %d breakouts, %d by large accounts)" % (
        sat["level"], sat["posts_in_window"], sat["window_hours"], sat["breakouts_count"], len(sat["large_account_breakouts"])))
    print("  momentum:   %s (last 6h: %d = %s/h; prev 6h: %d = %s/h)" % (
        mom["level"], mom["last_6h"]["posts"], mom["last_6h"]["per_hour"], mom["prev_6h"]["posts"], mom["prev_6h"]["per_hour"]))
    print("  lateness:   %s (%s)" % (
        late["band"],
        ("%s since first big post @%s (%s)" % (_format_hours(late["hours_since_first_big"]), late["first_big_post"]["author"], _compact(late["first_big_post"]["views"])))
        if late.get("first_big_post") else "no big post yet"))
    if tc.get("sampled"):
        print("  note: " + (tc.get("sample_note") or "sampled"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
