#!/usr/bin/env python3
"""Why an account grows: the growth mechanisms, measured (the growth mode of an account run).

    python3 growth.py <run folder> [--top-share 0.15]

Run it after analyze.py and radar.py. Reads account.json, posts.csv, analysis.json, radar.json, comments.csv and,
when present, the growth files: reposters.csv (who reposted the top posts), replies_out.csv (the account's own
replies to other accounts, a sample) and originals.csv (the posts it quoted or replied to: when, how far they reached).
Shapes: references/data-shape.md, "The growth files". Steps: references/growth.md.

Writes growth.json (every number, MEASURED: cite it as growth.json#<key>) and GROWTH.md. With your sentences in
findings.json "growth" (why_it_grows, doesnt_move, copy_this) it fills them ({key} and {key:fmt} placeholders are
replaced by growth.json's numbers), builds the reply draft and checks it: 600 to 1,200 characters, the first and the
last line as references/growth.md gives them, no link inside (the link is the separate follow-up line).
Exit 0 = written (and the draft passes when there is one), 1 = the draft or a placeholder fails (GROWTH.md says what
to fix), 2 = the run cannot be read.

What it measures (definitions in references/growth.md):
1. posting cadence: posts per week and per month, views and replies per month, the change point (analysis.json's
   pace mark) and the window's posts before and after it;
2. concentration: the share of the period's views in its top posts, and what those posts have in common;
3. the repost graph of the top posts: who reposted, big accounts, accounts tagged in the post or its first self-reply;
4. tags and credits: @mentions in the post and in the author's first self-reply, and how many tagged accounts reposted;
5. crowd calls: an ask to a named crowd or a promise to reply ("I'll reply to everyone"), their replies, and the
   author's own replies read in those threads;
6. the author's replies to others: how many in the window read, to whom (by follower size), how many to its circle;
7. speed on big posts: minutes between a big original and the author's quote or reply, and the original's views;
8. the weakest format: what its posts lack against the account's other posts.
What it does not do: say why. "What those posts have in common", "a circle of creators" and every reason are your
reading in findings.json, labelled SEEN or INFERRED with the basis.
"""
import datetime as dt
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    SKILL_VERSION, ShapeError, account_read_at, account_window, day, die, follower_readings, iso, load_account,
    load_comments, load_posts, median, norm_handle, now_utc, parse_count, parse_time, read_csv, read_json, rnd,
    script_dir, write_json, write_text,
)
from analyze import input_fingerprint  # noqa: E402

# The files the numbers come from. analysis.json and radar.json are made from the first four (text_probe.py writes
# analysis.json again with a new time), so a change is caught at its source.
INPUT_FILES = ("account.json", "posts.csv", "comments.csv", "formats.json", "reposters.csv", "replies_out.csv",
               "originals.csv")
WORDS_FILE = os.path.join(script_dir(), "..", "data", "growth-words.json")
SETTINGS = {
    "top_share": 0.15,          # the top slice of a period: this share of its posts by views, 3 at least
    "repost_picks": 5,          # read who reposted this many posts (the most reposted of the period), one page each
    "big_min": 10000,           # a big account: this many followers or more, and 10x the account's own
    "big_times": 10,
    "big_original_views": 100000,   # a big original: this many views, or posted by an account with this many followers
    "few_posts": 6,             # a side with fewer posts is a lead, never a finding
    "default_days": 30,         # with no change point, the period is the last 30 days
}
REPLY_FIRST = ("Ran your account through REA Viral (free open-source skill for AI agents). Here's what's actually "
               "driving your growth:")
REPLY_LAST = 'Try it on your own account: install REA Viral and tell your agent "REA Viral: why is @handle growing".'
FOLLOW_UP = "github.com/wpsoul/rea-viral"
REPLY_CHARS = (600, 1200)   # owner 2026-11-24: plain sentences that say what each number means need the room
LINK_RE = re.compile(r"https?://|www\.|github\.com|\b[\w-]+\.(?:com|io|ai|dev|app|xyz|org|net|co)\b/?", re.I)
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{1,30})")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][\w.\-]*?)(?::(n|full|pct|x|date|raw|min))?\}")


# ---------------------------------------------------------------------------------------------- words

def load_words(path=WORDS_FILE):
    doc = read_json(path)
    L = (doc.get("languages") or {}).get("en") or {}

    def alt(xs):
        return "|".join(re.escape(x).replace("'", "'") for x in sorted(xs, key=len, reverse=True)) or r"(?!x)x"
    nouns = alt(L.get("crowd_nouns") or [])
    openers = alt(L.get("crowd_openers") or [])
    w = {
        # a named crowd: the first line opens on a crowd ("AI video creators, ...", "Calling all builders:"), the
        # crowd's name ending at a comma, a colon or a dash within the first few words
        "crowd": re.compile(r"^\s*(?:(?:%s)\s+)?(?:[\w&/+.'-]+\s+){0,5}?(?:%s)\b[^?\n]{0,80}?[,:—–]" % (openers, nouns)),
        "interest": re.compile(r"^\s*(?:%s)\b" % alt(L.get("interest_openers") or [])),
        "promise": re.compile(r"(?<![\w])(?:%s)(?![\w])" % alt(L.get("reply_promises") or [])),
        "ask": re.compile(r"(?<![\w])(?:%s)(?![\w])" % alt(L.get("reader_asks") or [])),
        "you": re.compile(r"(?<![\w'])(?:%s)(?![\w'])" % alt(L.get("second_person") or [])),
        "not_ask": re.compile(r"^\s*(?:%s)\b" % alt(L.get("not_asks") or [])),
    }
    return w


def norm(s):
    return (s or "").replace("’", "'").replace("‘", "'").lower()


def mentions(text, own):
    out = []
    for m in MENTION_RE.finditer(URL_RE.sub(" ", text or "")):
        h = m.group(1)
        if norm_handle(h) != norm_handle(own) and norm_handle(h) not in [norm_handle(x) for x in out]:
            out.append(h)
    return out


def first_self_reply(p):
    """The author's first reply under its own post that is not a thread part: the earliest of author_replies."""
    reps = [r for r in (p.get("author_replies") or []) if isinstance(r, dict)]
    if not reps:
        return None
    reps.sort(key=lambda r: (r.get("minutes_after") is None, r.get("minutes_after") or 0))
    return reps[0]


def features(p, own, W):
    """What growth.py reads in one post's words (regular expressions over the text, like text_probe.py)."""
    parts = p.get("parts") or []
    body = "\n".join(parts) if parts else (p.get("caption") or "")
    text = norm(URL_RE.sub(" ", body))
    first_line = next((ln for ln in text.split("\n") if ln.strip()), "")
    fr = first_self_reply(p)
    crowd = bool(W["crowd"].search(first_line)) or bool(W["interest"].search(first_line))
    promise = W["promise"].search(text)
    sentences = [s.strip() for s in re.split(r"(?<=[?!.])\s+|\n+", text) if s.strip()]
    q_you = [s for s in sentences if s.endswith("?") and W["you"].search(s) and not W["not_ask"].search(s)]
    ask = W["ask"].search(text)
    asks = bool(q_you or ask)
    tags_post = mentions(body, own)
    tags_reply = mentions((fr or {}).get("text"), own)
    cap = URL_RE.sub("", p.get("caption") or "").strip()
    return {
        "named_crowd": crowd,
        "reply_promise": bool(promise),
        "promise_words": promise.group(0) if promise else None,
        "asks_reader": asks,
        "crowd_call": bool((crowd or promise) and asks),
        "question": bool(asks and not (crowd or promise)),
        "tags_post": tags_post,
        "tags_first_reply": [h for h in tags_reply if norm_handle(h) not in [norm_handle(x) for x in tags_post]],
        "first_reply_minutes": (fr or {}).get("minutes_after"),
        "tagged": bool(tags_post or tags_reply),
        "quote": p.get("type") == "quote",
        "own_video": (p.get("own_media") or "") == "video",
        "one_line": bool(cap) and "\n" not in cap and len(cap) <= 100,
        "chars": len(cap),
    }


KIND_LABELS = {"crowd_call": "asks a named crowd or promises to reply", "question": "asks the reader (no crowd call)",
               "tagged": "tags accounts (in the post or its first self-reply)", "quote": "quotes another post",
               "own_video": "carries its own video", "one_line": "a one-line caption"}


# ---------------------------------------------------------------------------------------------- the growth files

def _csv(folder, name):
    p = os.path.join(folder, name)
    if not os.path.exists(p):
        return None
    _, rows = read_csv(p)
    return rows


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


def load_reposters(folder):
    rows = _csv(folder, "reposters.csv")
    if rows is None:
        return None
    out = []
    for r in rows:
        out.append({"post_id": (r.get("post_id") or "").strip(), "handle": (r.get("handle") or "").strip().lstrip("@"),
                    "name": r.get("name") or "", "followers": _count(r.get("followers")), "bio": r.get("bio") or "",
                    "kind": (r.get("kind") or "repost").strip().lower() or "repost", "at": _time(r.get("at"))})
    return out


def load_replies_out(folder):
    rows = _csv(folder, "replies_out.csv")
    if rows is None:
        return None
    out = []
    for r in rows:
        out.append({"reply_id": (r.get("reply_id") or "").strip(), "url": (r.get("url") or "").strip(),
                    "at": _time(r.get("at")), "to": (r.get("to_handle") or "").strip().lstrip("@"),
                    "to_followers": _count(r.get("to_followers")), "to_bio": r.get("to_bio") or "",
                    "conversation_id": (r.get("conversation_id") or "").strip(), "text": r.get("text") or "",
                    "views": _count(r.get("views")), "likes": _count(r.get("likes"))})
    return out


def load_originals(folder):
    rows = _csv(folder, "originals.csv")
    if rows is None:
        return None
    out = []
    for r in rows:
        out.append({"post_id": (r.get("post_id") or "").strip(), "original_id": (r.get("original_id") or "").strip(),
                    "url": (r.get("original_url") or "").strip(), "handle": (r.get("original_handle") or "").strip().lstrip("@"),
                    "followers": _count(r.get("original_followers")), "at": _time(r.get("original_at")),
                    "views": _count(r.get("original_views"))})
    return out


# ---------------------------------------------------------------------------------------------- helpers

def share(a, b):
    return rnd(a / float(b), 4) if b else None


def size_bucket(f):
    if f is None:
        return "unknown"
    if f >= 100000:
        return "over_100k"
    if f >= 10000:
        return "10k_100k"
    if f >= 1000:
        return "1k_10k"
    return "under_1k"


SIZE_ORDER = ["over_100k", "10k_100k", "1k_10k", "under_1k", "unknown"]
SIZE_LABELS = {"over_100k": "100K and over", "10k_100k": "10K to 100K", "1k_10k": "1K to 10K", "under_1k": "under 1K",
               "unknown": "size unknown"}


def period_stats(ps, too_new_ids):
    views = [p["views"] for p in ps if p["views"] is not None]
    return {
        "posts": len(ps),
        "views": sum(views) if views else 0,
        "views_known": len(views),
        "median_views": median(views),
        "median_replies": median([p["comments"] for p in ps if p["comments"] is not None]),
        "too_new": sum(1 for p in ps if p["post_id"] in too_new_ids),
    }


def side(ps, an_post):
    rs = [an_post[p["post_id"]]["ratio"] for p in ps if (an_post.get(p["post_id"]) or {}).get("ratio") is not None]
    return {"posts": len(ps), "scored": len(rs), "median_ratio": rnd(median(rs), 3),
            "hits": sum(1 for r in rs if r >= 2), "median_views": median([p["views"] for p in ps if p["views"] is not None]),
            "median_replies": median([p["comments"] for p in ps if p["comments"] is not None])}


# ---------------------------------------------------------------------------------------------- the measure

def measure(folder, top_share=None):
    acc = load_account(folder)
    an_path = os.path.join(folder, "analysis.json")
    if not os.path.exists(an_path):
        die("no analysis.json: run analyze.py first", 2)
    an = read_json(an_path)
    was = an.get("inputs") or {}
    have = input_fingerprint(folder, tuple(was.keys()))
    changed = sorted(k for k in was if have.get(k) != was.get(k))
    if changed:
        die("analysis.json was made before %s changed: run analyze.py again" % ", ".join(changed), 2)
    radar = read_json(os.path.join(folder, "radar.json")) if os.path.exists(os.path.join(folder, "radar.json")) else None
    W = load_words()
    s = dict(SETTINGS)
    if top_share:
        s["top_share"] = top_share
    own = acc.get("handle") or ""
    followers = acc.get("followers")
    big_line = max(s["big_min"], s["big_times"] * (followers or 0))
    read_at = account_read_at(acc)
    lo, hi = account_window(acc)
    posts = [p for p in load_posts(folder) if p.get("published_at") is not None]
    posts.sort(key=lambda p: (p["published_at"], p["post_id"]))
    an_post = dict((x["post_id"], x) for x in an.get("posts") or [])
    min_age = (an.get("settings") or {}).get("min_age_days")
    too_new = set(i for i, x in an_post.items() if x.get("fresh") or x.get("status") in ("too_new", "fresh"))
    suspect = set(x["post_id"] for x in ((an.get("suspect_reach") or {}).get("posts") or []))
    lo = lo or (posts[0]["published_at"] if posts else read_at)
    inw = [p for p in posts if lo <= p["published_at"] <= (hi or read_at) and p["post_id"] not in suspect]
    by_id = dict((p["post_id"], p) for p in posts)
    F = dict((p["post_id"], features(p, own, W)) for p in posts)

    out = {
        "schema": "rea-viral/growth@1", "skill_version": SKILL_VERSION, "generated_at": iso(now_utc()),
        "inputs": input_fingerprint(folder, INPUT_FILES),
        "account": {"network": acc.get("network"), "handle": own, "followers": followers, "read_at": iso(read_at),
                    "window": {"from": day(lo), "to": day(hi or read_at)}},
        "rules": {"top_share": s["top_share"], "big_account": "%s followers or more (10,000 at least, and 10x the account's own)" % "{:,}".format(big_line),
                  "big_account_followers": big_line, "big_original": "views >= %d, or an account with followers >= 100,000" % s["big_original_views"],
                  "settle_days": min_age, "few_posts": s["few_posts"],
                  "left_out": "posts with views 1000x the followers or more (analysis.json#suspect_reach) are left out of every sum"},
        "status": "ok" if len(inw) >= 20 else "too_few_posts",
        "status_note": None if len(inw) >= 20 else "%d posts in the window (20 make a pattern): the numbers are listed, no mechanism is measured as one" % len(inw),
        "left_out": {"posts": sorted(suspect), "why": "views 1000x the followers or more: analysis.json#suspect_reach"} if suspect else None,
    }

    # 1. cadence -------------------------------------------------------------------------------------------
    weeks = {}
    for w in (an.get("timeline") or {}).get("weeks") or []:
        ws = parse_time(w["week"])
        days = min(7, max(0, (read_at.date() - ws.date()).days + 1))
        weeks[w["week"]] = {"posts": w["posts"], "days": days, "partial": days < 7}
    months = {}
    for p in inw:
        k = p["published_at"].strftime("%Y-%m")
        months.setdefault(k, []).append(p)
    month_rows = {}
    for k in sorted(months):
        month_rows[k] = period_stats(months[k], too_new)
    marks = [m for m in (an.get("timeline") or {}).get("marks") or [] if m.get("kind") == "pace"]
    wk = (an.get("timeline") or {}).get("weeks") or []
    cp = None
    best = None
    for m in marks:
        idx = next((i for i, w in enumerate(wk) if w["week"] == m["at"]), None)
        if idx is None or idx < 4:
            continue
        before = sum(w["posts"] for w in wk[idx - 4:idx]) / 4.0
        after = sum(w["posts"] for w in wk[idx:idx + 4]) / 4.0
        if after > before and (best is None or after / max(before, 0.25) > best[0]):
            best = (after / max(before, 0.25), m, before, after)
    if best:
        _, m, before, after = best
        start = parse_time(m["at"])
        since = [p for p in inw if p["published_at"] >= start]
        span = max(1.0, (read_at - start).total_seconds() / 86400.0)
        cp = {"at": m["at"], "before": rnd(before, 1), "after": rnd(after, 1), "text": m["text"],
              "from": "analysis.json#timeline.marks", "evidence": "MEASURED",
              "since": {"posts": len(since), "days": rnd(span, 1), "per_week": rnd(len(since) / span * 7, 1),
                        "note": "the 4 weeks after the change count the week still running as a whole week; this is the "
                                "real pace since the change"}}
        p_from = start
    else:
        p_from = read_at - dt.timedelta(days=s["default_days"])
    after_ps = [p for p in inw if p["published_at"] >= p_from]
    before_ps = [p for p in inw if p["published_at"] < p_from]
    period = {"from": day(p_from), "to": day(read_at), "why": "from the change point" if cp else "the last %d days (no change point)" % s["default_days"]}

    def ba(ps, a, b):
        st = period_stats(ps, too_new)
        days = max(1.0, (b - a).total_seconds() / 86400.0)
        st.update({"from": day(a), "to": day(b - dt.timedelta(seconds=1)) if b != read_at else day(b), "days": rnd(days, 1),
                   "per_week": rnd(len(ps) / days * 7, 1)})
        return st
    out["cadence"] = {
        "weeks": weeks, "months": month_rows, "change_point": cp,
        "before_after": {"before": ba(before_ps, lo, p_from), "after": ba(after_ps, p_from, read_at)} if before_ps else
                        {"before": None, "after": ba(after_ps, p_from, read_at)},
    }
    b_, a_ = out["cadence"]["before_after"]["before"], out["cadence"]["before_after"]["after"]
    if b_ and b_["views"]:
        out["cadence"]["before_after"]["views_times"] = rnd(a_["views"] / float(b_["views"]), 1)

    # 2. concentration (the period since the change point) -------------------------------------------------------
    pv = sorted([p for p in after_ps if p["views"] is not None], key=lambda p: -p["views"])
    total = sum(p["views"] for p in pv)
    n_top = min(len(pv), max(3, int(round(s["top_share"] * len(after_ps)))))
    curve = {}
    for n in (1, 3, 5, 10):
        if n <= len(pv):
            curve[str(n)] = {"n": n, "views": sum(p["views"] for p in pv[:n]), "share": share(sum(p["views"] for p in pv[:n]), total)}
    half = None
    acc_v = 0
    for i, p in enumerate(pv):
        acc_v += p["views"]
        if total and acc_v >= total / 2.0:
            half = {"n": i + 1, "share": share(acc_v, total)}
            break
    top = pv[:n_top]

    def kinds_of(pid):
        f = F[pid]
        return [k for k in ("crowd_call", "question", "tagged", "quote", "own_video", "one_line") if f.get(k)]
    in_common = {}
    for k in ("crowd_call", "reply_promise", "named_crowd", "question", "asks_reader", "tagged", "quote", "own_video", "one_line"):
        in_common[k] = sum(1 for p in top if F[p["post_id"]].get(k))
    in_common["too_new"] = sum(1 for p in top if p["post_id"] in too_new)
    out["concentration"] = {
        "period": period, "posts": len(after_ps), "views": total,
        "top_slice": {"n": len(top), "views": sum(p["views"] for p in top), "share": share(sum(p["views"] for p in top), total),
                      "rule": "the top %d%% of the period's posts by views, 3 at least" % round(100 * s["top_share"])},
        "curve": curve, "half": half, "in_common": in_common,
        "top_posts": [{"post_id": p["post_id"], "url": p["url"], "at": iso(p["published_at"]), "type": p["type"],
                       "views": p["views"], "share": share(p["views"], total), "replies": p["comments"],
                       "reposts": p.get("reposts"), "ratio": (an_post.get(p["post_id"]) or {}).get("ratio"),
                       "too_new": p["post_id"] in too_new, "kinds": kinds_of(p["post_id"]),
                       "first_line": (next((ln for ln in (p.get("caption") or "").split("\n") if ln.strip()), "") or "")[:140]}
                      for p in top],
    }

    # posts by id, for citing (growth.json#posts.<id>.views)
    out["posts"] = {}
    for p in inw:
        f = F[p["post_id"]]
        out["posts"][p["post_id"]] = {
            "url": p["url"], "at": iso(p["published_at"]), "type": p["type"], "views": p["views"], "replies": p["comments"],
            "reposts": p.get("reposts"), "bookmarks": p.get("bookmarks"), "ratio": (an_post.get(p["post_id"]) or {}).get("ratio"),
            "too_new": p["post_id"] in too_new, "kinds": kinds_of(p["post_id"]),
            "tags": f["tags_post"] + f["tags_first_reply"]}

    # 5. kinds over the window, with against without -----------------------------------------------------------------
    kinds = {}
    for k in ("crowd_call", "question", "tagged", "quote", "one_line"):
        w_ = [p for p in inw if F[p["post_id"]].get(k)]
        wo = [p for p in inw if not F[p["post_id"]].get(k)]
        in_after = [p for p in after_ps if F[p["post_id"]].get(k)]
        views_after = sum(p["views"] for p in in_after if p["views"] is not None)
        kw, kwo = side(w_, an_post), side(wo, an_post)
        kinds[k] = {"label": KIND_LABELS.get(k, k), "with": kw, "without": kwo,
                    "in_period": {"posts": len(in_after), "views": views_after, "share": share(views_after, total)},
                    "few_posts": kw["scored"] < s["few_posts"] or kwo["scored"] < s["few_posts"]}
    out["kinds"] = kinds

    # crowd calls in detail
    comments = load_comments(folder) or []
    replies_out = load_replies_out(folder)
    reposters = load_reposters(folder)
    originals = load_originals(folder)
    gr = acc.get("growth_read") or {}
    read_c = {}
    for c in comments:
        d = read_c.setdefault(c["post_id"], {"rows": 0, "author": 0})
        d["rows"] += 1
        if c.get("author_is_creator") is True:
            d["author"] += 1
    own_thread = {}
    for r in replies_out or []:
        if r["conversation_id"] in by_id:
            own_thread[r["conversation_id"]] = own_thread.get(r["conversation_id"], 0) + 1
    calls = []
    for p in inw:
        f = F[p["post_id"]]
        if not f["crowd_call"]:
            continue
        rc = read_c.get(p["post_id"])
        calls.append({"post_id": p["post_id"], "url": p["url"], "at": iso(p["published_at"]), "views": p["views"],
                      "replies": p["comments"], "bookmarks": p.get("bookmarks"), "too_new": p["post_id"] in too_new,
                      "named_crowd": f["named_crowd"], "reply_promise": f["reply_promise"], "promise_words": f["promise_words"],
                      "first_line": next((ln for ln in (p.get("caption") or "").split("\n") if ln.strip()), "")[:140],
                      "replies_read": rc["rows"] if rc else None, "author_replies_read": rc["author"] if rc else None,
                      "author_replies_sample": own_thread.get(p["post_id"])})
    calls.sort(key=lambda c: -(c["views"] or 0))
    out["crowd_calls"] = {
        "posts": dict((c["post_id"], c) for c in calls), "order": [c["post_id"] for c in calls], "count": len(calls),
        "top": calls[0] if calls else None,
        "views_in_period": kinds["crowd_call"]["in_period"]["views"], "share_in_period": kinds["crowd_call"]["in_period"]["share"],
        "note": "replies_read and author_replies_read count the rows read under the post (comments.csv), not every reply; "
                "author_replies_sample counts the author's replies in this thread within the replies read (replies_out.csv)"}

    # 4. tags and credits ------------------------------------------------------------------------------------------
    tag_count = {}
    for p in inw:
        f = F[p["post_id"]]
        for h in f["tags_post"]:
            d = tag_count.setdefault(h.lower(), {"handle": h, "posts": 0, "in_post": 0, "in_first_reply": 0})
            d["posts"] += 1
            d["in_post"] += 1
        for h in f["tags_first_reply"]:
            d = tag_count.setdefault(h.lower(), {"handle": h, "posts": 0, "in_post": 0, "in_first_reply": 0})
            d["posts"] += 1
            d["in_first_reply"] += 1
    out["tags"] = {"posts_with_tags": sum(1 for p in inw if F[p["post_id"]]["tagged"]), "of_posts": len(inw),
                   "in_first_reply": sum(1 for p in inw if F[p["post_id"]]["tags_first_reply"]),
                   "top": sorted(tag_count.values(), key=lambda d: (-d["posts"], d["handle"].lower()))[:15]}

    # 3. the repost graph ------------------------------------------------------------------------------------------
    picks = sorted([p for p in after_ps if (p.get("reposts") or 0) >= 1], key=lambda p: (-(p.get("reposts") or 0), -(p["views"] or 0)))
    picks = [p["post_id"] for p in picks[:s["repost_picks"]]]
    read_ids = []
    for i in list((gr.get("reposters") or {}).get("posts") or []) + [r["post_id"] for r in reposters or []]:
        if i not in read_ids:
            read_ids.append(i)
    reply_targets = set(norm_handle(r["to"]) for r in replies_out or [])
    graph_posts = {}
    tagged_total = tagged_rep = 0
    big = {}
    seen_on = {}
    self_reposts = 0
    for pid in read_ids:
        p = by_id.get(pid)
        if not p:
            continue
        f = F[pid]
        tagged = f["tags_post"] + f["tags_first_reply"]
        tset = set(norm_handle(h) for h in tagged)
        rows = [r for r in reposters or [] if r["post_id"] == pid]
        mine = [r for r in rows if norm_handle(r["handle"]) == norm_handle(own)]
        self_reposts += len(mine)
        rows = [r for r in rows if norm_handle(r["handle"]) != norm_handle(own)]
        rep_set = set(norm_handle(r["handle"]) for r in rows)
        t_rep = [h for h in tagged if norm_handle(h) in rep_set]
        tagged_total += len(tagged)
        tagged_rep += len(t_rep)
        lst = []
        for r in sorted(rows, key=lambda r: -(r["followers"] or -1)):
            isbig = (r["followers"] or 0) >= big_line
            lst.append({"handle": r["handle"], "followers": r["followers"], "bio": r["bio"][:160], "kind": r["kind"],
                        "big": isbig, "tagged": norm_handle(r["handle"]) in tset,
                        "replied_to": norm_handle(r["handle"]) in reply_targets})
            seen_on.setdefault(norm_handle(r["handle"]), {"handle": r["handle"], "followers": r["followers"], "posts": []})["posts"].append(pid)
            if isbig:
                b = big.setdefault(norm_handle(r["handle"]), {"handle": r["handle"], "followers": r["followers"], "bio": r["bio"][:160],
                                                              "posts": [], "tagged_on": []})
                b["posts"].append(pid)
                if norm_handle(r["handle"]) in tset:
                    b["tagged_on"].append(pid)
        graph_posts[pid] = {"post_id": pid, "url": p["url"], "views": p["views"], "reposts": p.get("reposts"),
                            "rows_read": len(rows), "self_reposts": len(mine), "tagged": tagged, "tagged_reposted": t_rep,
                            "tagged_count": len(tagged), "tagged_reposted_count": len(t_rep),
                            "big": [x["handle"] for x in lst if x["big"]], "reposters": lst}
    bigl = sorted(big.values(), key=lambda b: -(b["followers"] or 0))
    out["repost_graph"] = {
        "picks": picks, "read": [i for i in read_ids if i in graph_posts],
        "not_read": [i for i in picks if i not in graph_posts],
        "posts": graph_posts, "tagged": tagged_total, "tagged_reposted": tagged_rep,
        "big": bigl, "biggest": bigl[0] if bigl else None, "self_reposts": self_reposts,
        "repeat_reposters": sorted([v for v in seen_on.values() if len(v["posts"]) >= 2], key=lambda v: (-len(v["posts"]), v["handle"].lower())),
        "quoters_read": any(r["kind"] == "quote" for r in reposters or []),
        "note": "one page of reposters per post (the rows read against the post's repost count); the account's own reposts "
                "of itself are left out and counted"}
    if graph_posts:
        best_t = max(graph_posts.values(), key=lambda g: (g["tagged_reposted_count"], -g["tagged_count"]))
        out["repost_graph"]["best_tagged"] = {"post_id": best_t["post_id"], "tagged": best_t["tagged_count"],
                                              "reposted": best_t["tagged_reposted_count"],
                                              "not_reposted": [h for h in best_t["tagged"] if h not in best_t["tagged_reposted"]]}

    # 6. the author's replies to other accounts ----------------------------------------------------------------------
    if replies_out:
        ts = sorted(r["at"] for r in replies_out if r["at"])
        span = (ts[-1] - ts[0]).total_seconds() / 60.0 if len(ts) >= 2 else None
        circle = set(seen_on) | set(tag_count)
        by_size = dict((k, 0) for k in SIZE_ORDER)
        targets = {}
        for r in replies_out:
            by_size[size_bucket(r["to_followers"])] += 1
            t = targets.setdefault(norm_handle(r["to"]), {"handle": r["to"], "followers": r["to_followers"], "replies": 0,
                                                          "bio": r["to_bio"][:140], "circle": norm_handle(r["to"]) in circle})
            t["replies"] += 1
        rr = gr.get("replies_out") or {}
        windows = rr.get("windows")
        out["replies_out"] = {
            "count": len(replies_out), "from": iso(ts[0]) if ts else None, "to": iso(ts[-1]) if ts else None,
            "span_minutes": rnd(span, 0), "per_hour": rnd(len(replies_out) / (span / 60.0), 1) if span else None,
            "windows": windows, "sample": windows is None or windows <= 1,
            "targets": len(targets), "in_own_threads": sum(1 for r in replies_out if r["conversation_id"] in by_id),
            "to_big": sum(1 for r in replies_out if (r["to_followers"] or 0) >= big_line),
            "to_circle": sum(1 for r in replies_out if norm_handle(r["to"]) in circle),
            "by_size": by_size, "by_size_labels": SIZE_LABELS,
            "big_targets": sorted([t for t in targets.values() if (t["followers"] or 0) >= big_line], key=lambda t: -(t["followers"] or 0)),
            "circle_targets": sorted([t for t in targets.values() if t["circle"]], key=lambda t: t["handle"].lower()),
            "examples": [{"reply_id": r["reply_id"], "url": r["url"], "at": iso(r["at"]), "to": r["to"], "to_followers": r["to_followers"],
                          "text": r["text"][:200]} for r in sorted(replies_out, key=lambda r: -(r["to_followers"] or 0))[:6]],
            "note": ("a sample: one window read" if (windows is None or windows <= 1) else "%d windows read" % windows) +
                    (" (%s to %s UTC)" % (iso(ts[0])[5:16].replace("T", " "), iso(ts[-1])[11:16]) if ts else "")}
    else:
        out["replies_out"] = None

    # 7. speed on big posts ------------------------------------------------------------------------------------------
    rep_by = dict((r["reply_id"], r) for r in replies_out or [])
    items = []
    for o in originals or []:
        if o["post_id"] in by_id:
            p = by_id[o["post_id"]]
            at, kind, views, url = p["published_at"], "quote", p["views"], p["url"]
        elif o["post_id"] in rep_by:
            r = rep_by[o["post_id"]]
            at, kind, views, url = r["at"], "reply", r["views"], r["url"]
        else:
            continue
        if not (at and o["at"]):
            continue
        mins = (at - o["at"]).total_seconds() / 60.0
        isbig = (o["views"] or 0) >= s["big_original_views"] or (o["followers"] or 0) >= 100000
        items.append({"post_id": o["post_id"], "kind": kind, "url": url, "own_views": views, "minutes": rnd(mins, 0),
                      "original_url": o["url"], "original_handle": o["handle"], "original_followers": o["followers"],
                      "original_views": o["views"], "big": isbig, "too_new": o["post_id"] in too_new})
    items.sort(key=lambda x: (x["kind"] != "quote", -(x["own_views"] or 0)))
    bq = [x for x in items if x["big"] and x["kind"] == "quote"]
    br = [x for x in items if x["big"] and x["kind"] == "reply"]
    out["speed"] = {
        "items": dict((x["post_id"], x) for x in items), "order": [x["post_id"] for x in items],
        "big_quotes": len(bq), "big_replies": len(br),
        "median_minutes_big_quotes": rnd(median([x["minutes"] for x in bq]), 0),
        "median_minutes_big_replies": rnd(median([x["minutes"] for x in br]), 0),
        "top": max(bq, key=lambda x: x["own_views"] or 0) if bq else None,
        "quotes_in_period": sum(1 for p in after_ps if p["type"] == "quote"),
        "quotes_with_original": sum(1 for x in items if x["kind"] == "quote"),
    } if items else None

    # 8. the weakest format ------------------------------------------------------------------------------------------
    out["flops"] = None
    fm = (radar or {}).get("formats") or []
    cand = [f for f in fm if f.get("lift") is not None and not f.get("few_posts") and f["lift"] < 1.0]
    if cand:
        f0 = min(cand, key=lambda f: f["lift"])
        ids = set(f0.get("post_ids") or [])
        ins = [p for p in inw if p["post_id"] in ids]
        rest = [p for p in inw if p["post_id"] not in ids]

        def sh(ps, k):
            return share(sum(1 for p in ps if F[p["post_id"]].get(k)), len(ps))
        feats = {}
        for k in ("tagged", "crowd_call", "asks_reader", "quote", "own_video", "one_line"):
            feats[k] = {"label": KIND_LABELS.get(k, "asks the reader" if k == "asks_reader" else k), "format": sh(ins, k), "rest": sh(rest, k)}
        feats["chars"] = {"label": "median caption length (characters)", "format": median([F[p["post_id"]]["chars"] for p in ins]),
                          "rest": median([F[p["post_id"]]["chars"] for p in rest])}
        lacks = [k for k, v in feats.items() if k != "chars" and v["rest"] is not None and v["rest"] >= 0.15
                 and (v["format"] or 0) <= v["rest"] / 2.0]
        flops_all = set(an.get("flops") or [])
        sc = side(ins, an_post)
        out["flops"] = {"format": {"id": f0["id"], "name": f0.get("name"), "lift": f0["lift"], "posts": len(ins),
                                   "scored": sc["scored"], "hits": sc["hits"], "median_ratio": sc["median_ratio"],
                                   "flops": sum(1 for i in ids if i in flops_all), "flops_all": len(flops_all),
                                   "direction_label": f0.get("direction_label"), "from": "radar.json#formats.%s" % f0["id"]},
                        "features": feats, "lacks": lacks,
                        "note": "what the format's posts carry against the account's other posts in the window; a share "
                                "the others have (15% or more) that the format has at half or less is listed in lacks"}

    # followers ------------------------------------------------------------------------------------------------------
    readings = follower_readings(folder, acc)
    if len(readings) >= 2 and (readings[-1]["at"] - readings[0]["at"]).total_seconds() >= 86400:
        out["followers"] = {"measured": True, "from": iso(readings[0]["at"]), "to": iso(readings[-1]["at"]),
                            "first": readings[0]["followers"], "last": readings[-1]["followers"],
                            "gain": readings[-1]["followers"] - readings[0]["followers"], "readings": len(readings)}
    else:
        out["followers"] = {"measured": False, "current": followers, "readings": len(readings),
                            "note": "cannot be measured: no follower history covers the window "
                                    "(%d reading%s). Watch collects counts from now on (references/watch.md)" % (
                                        len(readings), "" if len(readings) == 1 else "s")}

    # what to read next, and what is a sample ------------------------------------------------------------------------
    quotes_missing = [p["post_id"] for p in after_ps if p["type"] == "quote" and p["post_id"] not in set(o["post_id"] for o in originals or [])]
    calls_unread = [c["post_id"] for c in calls if c["post_id"] not in read_c and c["post_id"] in set(x["post_id"] for x in after_ps)]
    out["reads"] = {"reposters": out["repost_graph"]["not_read"], "replies_under": calls_unread[:5],
                    "originals": quotes_missing[:10], "replies_out": replies_out is None}
    lim = []
    if suspect:
        lim.append({"what": "Left out of the sums", "why": "%d post%s with views 1000x the followers or more (%s): open them before reading anything into them" % (
            len(suspect), "" if len(suspect) == 1 else "s", ", ".join(sorted(suspect)))})
    tn = [p for p in after_ps if p["post_id"] in too_new]
    if tn:
        lim.append({"what": "Under %s days old" % (int(min_age) if min_age and float(min_age).is_integer() else min_age),
                    "why": "%d post%s of the period (%s): views still growing, counted as they stand" % (
                        len(tn), "" if len(tn) == 1 else "s", ", ".join(p["post_id"] for p in tn))})
    if replies_out is None:
        lim.append({"what": "The author's replies to others", "why": "not read (replies_out.csv): reply activity and the circle are not measured"})
    elif out["replies_out"]["sample"]:
        lim.append({"what": "The author's replies to others", "why": out["replies_out"]["note"] + "; never a rate for the account"})
    if reposters is None:
        lim.append({"what": "Who reposted", "why": "not read (reposters.csv): the repost graph is not measured"})
    elif graph_posts:
        lim.append({"what": "Who reposted", "why": "one page each for %d post%s (%s); %s" % (
            len(graph_posts), "" if len(graph_posts) == 1 else "s",
            "; ".join("%s: %d of %s" % (g["post_id"], g["rows_read"], g["reposts"] if g["reposts"] is not None else "?") for g in graph_posts.values()),
            "who quoted them was read too" if out["repost_graph"]["quoters_read"] else "who quoted them was not read")})
    if calls and not read_c:
        lim.append({"what": "Replies under the crowd calls", "why": "not read (comments.csv): the author's own replies there are not counted"})
    elif calls:
        lim.append({"what": "Replies under the crowd calls", "why": "one page under %d of %d crowd-call posts: the author's replies counted there are those in the rows read" % (
            sum(1 for c in calls if c["post_id"] in read_c), len(calls))})
    if originals is None and any(p["type"] == "quote" for p in after_ps):
        lim.append({"what": "Quoted originals", "why": "not read (originals.csv): speed on big posts is not measured"})
    if not out["followers"]["measured"]:
        lim.append({"what": "Follower growth", "why": out["followers"]["note"]})
    out["limits"] = lim
    return out


# ---------------------------------------------------------------------------------------------- placeholders

def get_path(doc, path):
    """growth.json value at a dotted path: dict keys (an id may hold dots: the longest run that names a key wins), a
    list item by its id, post_id, handle or index. Raises KeyError."""
    parts = path.split(".")
    cur, i = doc, 0
    while i < len(parts):
        step = None
        for j in range(len(parts), i, -1):
            name = ".".join(parts[i:j])
            if isinstance(cur, dict) and name in cur:
                step = (cur[name], j)
            elif isinstance(cur, list):
                hit = [x for x in cur if isinstance(x, dict) and name in (str(x.get("id")), str(x.get("post_id")), str(x.get("handle")))]
                if hit:
                    step = (hit[0], j)
                elif j == i + 1 and name.isdigit() and int(name) < len(cur):
                    step = (cur[int(name)], j)
            if step:
                break
        if not step:
            raise KeyError(path)
        cur, i = step
    return cur


def compact(v):
    v = float(v)
    a = abs(v)
    if a >= 1e6:
        s = "%.1fM" % (v / 1e6)
    elif a >= 1e5:
        s = "%dK" % round(v / 1e3)
    elif a >= 1e3:
        s = "%.1fK" % (v / 1e3)
    else:
        return ("%d" % round(v)) if v == int(v) else ("%.1f" % v).rstrip("0").rstrip(".")
    return s.replace(".0K", "K").replace(".0M", "M")


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_value(v, f):
    if v is None:
        raise ValueError("no value (null)")
    if isinstance(v, (dict, list)):
        raise ValueError("not a number or a word (a %s)" % type(v).__name__)
    if isinstance(v, bool):
        return "yes" if v else "no"
    if f == "raw" or isinstance(v, str) and f in (None, "n"):
        return str(v)
    if f == "date":
        t = parse_time(str(v))
        return "%s %d" % (MONTHS[t.month - 1], t.day)
    if f == "pct":
        return "%d%%" % round(100 * float(v))
    if f == "x":
        x = float(v)
        if round(abs(x), 1) >= 10:
            return "%dx" % round(x)
        return ("%.2f" % x).rstrip("0").rstrip(".") + "x"
    if f == "full":
        return "{:,}".format(int(round(float(v)))) if float(v) == int(float(v)) or abs(float(v)) >= 100 else str(v)
    if f == "min":
        return "%d" % round(float(v))
    return compact(v)


def fill(text, g):
    """Replace {key} and {key:fmt} with growth.json's values. Returns (text, problems, keys)."""
    problems, keys = [], []

    def sub(m):
        key, f = m.group(1), m.group(2)
        keys.append(key)
        try:
            return fmt_value(get_path(g, key), f)
        except KeyError:
            problems.append("{%s}: growth.json has no such key" % key)
        except ValueError as e:
            problems.append("{%s}: %s" % (key, e))
        return "{%s}" % key
    return PLACEHOLDER_RE.sub(sub, text or ""), problems, keys


def placeholders(text):
    return [m.group(1) for m in PLACEHOLDER_RE.finditer(text or "")]


# ---------------------------------------------------------------------------------------------- the reading and the reply

def view(folder, g=None):
    """growth.json with the agent's sentences filled in and the reply draft built and checked (for GROWTH.md and the
    report). None when the run has no growth.json."""
    if g is None:
        p = os.path.join(folder, "growth.json")
        if not os.path.exists(p):
            return None
        g = read_json(p)
    fp = os.path.join(folder, "findings.json")
    fi = (read_json(fp).get("growth") if os.path.exists(fp) else None) or {}
    handle = (g.get("account") or {}).get("handle") or ""
    problems = []
    marks = notes_for(g)

    def item(c, sec, i):
        text, pr1, k1 = fill(c.get("text"), g)
        reply, pr2, k2 = fill(c.get("reply") or c.get("text"), g)
        for x in pr1 + pr2:
            problems.append("findings.json:growth.%s[%d]: %s" % (sec, i, x))
        posts = [x for x in c.get("posts") or [] if isinstance(x, str)]
        ex = []
        for pid in posts:
            pp = (g.get("posts") or {}).get(pid) or {}
            ex.append({"post_id": pid, "url": pp.get("url") or "", "too_new": bool(pp.get("too_new"))})
        flags = []
        for k in k1 + k2:
            for prefix, note in marks:
                if k.startswith(prefix) and note not in flags:
                    flags.append(note)
        for e in ex:
            if e["too_new"]:
                flags.append("post %s is under %s days old: its numbers are still growing" % (e["post_id"], (g.get("rules") or {}).get("settle_days")))
        return {"title": c.get("title"), "text": text, "reply": reply.strip(), "evidence": c.get("evidence"),
                "from": c.get("from"), "basis": c.get("basis"), "posts": ex, "links": c.get("links") or [],
                "quote": c.get("quote") if isinstance(c.get("quote"), list) else ([c["quote"]] if c.get("quote") else []),
                "numbers": len(set(k1 + k2)), "marks": flags}
    why = [item(c, "why_it_grows", i) for i, c in enumerate(fi.get("why_it_grows") or [])]
    dm = [item(c, "doesnt_move", i) for i, c in enumerate(fi.get("doesnt_move") or [])]
    cp = []
    for i, c in enumerate(fi.get("copy_this") or []):
        t, pr, _ = fill(c.get("text") if isinstance(c, dict) else c, g)
        problems += ["findings.json:growth.copy_this[%d]: %s" % (i, x) for x in pr]
        cp.append(t)
    reply = None
    checks = []
    if why:
        lines = [REPLY_FIRST, ""]
        n = 0
        for x in why:
            n += 1
            lines.append("%d. %s" % (n, x["reply"]))
        for x in dm:
            n += 1
            r = x["reply"]
            lines.append("%d. %s" % (n, r))   # as written: the line itself says what does not work (no forced label)
        lines += ["", REPLY_LAST]
        reply = "\n".join(lines)
        n_chars = len(reply)
        if n_chars < REPLY_CHARS[0]:
            checks.append("the reply is %d characters: %d at least (add a number or an example)" % (n_chars, REPLY_CHARS[0]))
        if n_chars > REPLY_CHARS[1]:
            longest = max(why + dm, key=lambda x: len(x["reply"]))
            checks.append("the reply is %d characters: %d at most (shorten the reply lines; the longest is %r, %d characters)" % (
                n_chars, REPLY_CHARS[1], (longest["title"] or longest["reply"][:30]), len(longest["reply"])))
        if not reply.startswith(REPLY_FIRST):
            checks.append("the reply must start with: " + REPLY_FIRST)
        if not reply.endswith(REPLY_LAST):
            checks.append("the reply must end with: " + REPLY_LAST)
        for x in why + dm:
            if LINK_RE.search(x["reply"]):
                checks.append("no link in the reply (the link is the follow-up line): %r" % x["reply"][:60])
        if not 3 <= len(why) <= 5:
            checks.append("why_it_grows has %d items: 3 to 5" % len(why))
        if not 1 <= len(dm) <= 2:
            checks.append("doesnt_move has %d items: 1 or 2" % len(dm))
        for i, x in enumerate(why):
            if not x["numbers"]:
                checks.append("why_it_grows[%d] has no number: write 1 or 2 as {growth.json key}" % i)
            if not (x["posts"] or x["links"]):
                checks.append("why_it_grows[%d] has no example: posts (ids) or links" % i)
        if len(cp) != 3 and fi.get("copy_this") is not None:
            checks.append("copy_this has %d items: 3" % len(cp))
    return {"growth": g, "why": why, "doesnt_move": dm, "copy_this": cp, "reply": reply,
            "reply_chars": len(reply) if reply else None, "follow_up": FOLLOW_UP, "problems": problems, "checks": checks,
            "ready": bool(reply) and not problems and not checks, "has_reading": bool(why or dm or cp)}


def notes_for(g):
    """Which keys carry a sample or a small-number mark (shown beside a claim that cites them)."""
    out = []
    ro = g.get("replies_out") or {}
    if ro and ro.get("sample"):
        out.append(("replies_out", "replies to others: " + (ro.get("note") or "a sample")))
    if (g.get("repost_graph") or {}).get("read"):
        out.append(("repost_graph", "reposters: one page per post read (repost_graph.note)"))
    if g.get("crowd_calls"):
        out.append(("crowd_calls.posts", "replies read under a post: one page"))
    tn = (g.get("concentration") or {}).get("in_common", {}).get("too_new")
    if tn:
        out.append(("concentration", "%d of the top posts are under %s days old: views still growing" % (tn, (g.get("rules") or {}).get("settle_days"))))
    return out


# ---------------------------------------------------------------------------------------------- GROWTH.md

def table(head, rows):
    L = ["", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        L.append("| " + " | ".join(("-" if c is None else str(c)).replace("|", "/").replace("\n", " ") for c in r) + " |")
    return L


def n0(v):
    return "-" if v is None else "{:,}".format(int(round(v))) if isinstance(v, (int, float)) else str(v)


def pc(v):
    return "-" if v is None else "%d%%" % round(100 * v)


def xr(v):
    return "-" if v is None else ("%.2f" % v).rstrip("0").rstrip(".") + "x"


def claim_tail(x):
    ev = x.get("evidence")
    if ev == "MEASURED":
        return "[MEASURED, %s]" % x.get("from")
    if ev == "SEEN":
        return "[SEEN in %s]" % ", ".join([e["post_id"] for e in x["posts"]] + list(x.get("links") or []))
    if ev == "INFERRED":
        return "[INFERRED; basis: %s]" % x.get("basis")
    return "[no label]"


def growth_md(v):
    g = v["growth"]
    a = g.get("account") or {}
    h = a.get("handle")
    L = ["# @%s: why it grows (REA Viral, growth mode)" % h, ""]
    L.append("Read %s on %s; window %s to %s. Every number is MEASURED by growth.py (growth.json); every reason is "
             "the agent's reading in findings.json, labelled SEEN (a post or a row shows it) or INFERRED (the basis is "
             "written). Built by REA Viral %s." % ((a.get("read_at") or "")[:16].replace("T", " "), a.get("network"),
                                                   (a.get("window") or {}).get("from"), (a.get("window") or {}).get("to"), g.get("skill_version")))
    L.append("")
    if g.get("status") != "ok":
        L += ["Status: %s. %s" % (g.get("status"), g.get("status_note") or ""), ""]
    if v["has_reading"]:
        L += ["## Why it grows", ""]
        for i, x in enumerate(v["why"], 1):
            L.append("%d. **%s.** %s %s" % (i, x["title"] or "", x["text"], claim_tail(x)))
            for j, e in enumerate(x["posts"][:2]):
                L.append("   Example: %s%s" % (e["url"] or e["post_id"], (' "%s"' % x["quote"][0]) if x["quote"] and not j else ""))
            for m in x["marks"]:
                L.append("   Note: %s." % m)
        L += ["", "## What doesn't move", ""]
        for x in v["doesnt_move"]:
            L.append("- **%s.** %s %s" % (x["title"] or "", x["text"], claim_tail(x)))
            for m in x["marks"]:
                L.append("  Note: %s." % m)
        L += ["", "## Copy this", ""]
        for i, t in enumerate(v["copy_this"], 1):
            L.append("%d. %s" % (i, t))
        L += ["", "## The reply draft", ""]
        if v["reply"]:
            L.append("Paste as is (%d characters%s):" % (v["reply_chars"], "" if v["ready"] else "; NOT READY, see below"))
            L += ["", "```text", v["reply"], "```", "", "The follow-up line, a separate reply: %s" % v["follow_up"]]
        for p in v["problems"] + v["checks"]:
            L.append("- NOT READY: %s" % p)
        L.append("")
    else:
        L += ["The agent's reading is not written yet: findings.json \"growth\" (references/growth.md, step 4). Below: "
              "the numbers it starts from.", ""]
    L += ["## The numbers (MEASURED by growth.py, growth.json)", ""]
    c = g.get("cadence") or {}
    cp = c.get("change_point")
    L.append("### Posting cadence")
    L.append("")
    if cp:
        L.append("- Change point %s: %s posts a week in the 4 weeks before, %s in the 4 weeks after (%s). Since then: %d "
                 "posts in %s days, %s a week." % (cp["at"], cp["before"], cp["after"], cp["from"], cp["since"]["posts"],
                                                  cp["since"]["days"], cp["since"]["per_week"]))
    else:
        L.append("- No change in posting pace (analysis.json#timeline.marks): the period is the last 30 days.")
    ba = c.get("before_after") or {}
    rows = []
    for k in ("before", "after"):
        x = ba.get(k)
        if x:
            rows.append([k, "%s to %s" % (x["from"], x["to"]), x["posts"], x["per_week"], n0(x["views"]), n0(x["median_views"]),
                         n0(x["median_replies"]), x["too_new"]])
    L.append("")
    L += table(["", "Dates", "Posts", "A week", "Views", "Median views", "Median replies", "Under settle"], rows)
    L.append("")
    L += table(["Month", "Posts", "Views", "Median views", "Median replies", "Under settle"],
               [[k, m["posts"], n0(m["views"]), n0(m["median_views"]), n0(m["median_replies"]), m["too_new"]] for k, m in (c.get("months") or {}).items()])
    L.append("")
    L.append("Posts a week: " + ", ".join("%s %d%s" % (k[5:], w["posts"], " (partial)" if w["partial"] else "") for k, w in (c.get("weeks") or {}).items()))
    L.append("")
    co = g.get("concentration") or {}
    ts = co.get("top_slice") or {}
    L += ["### Concentration (%s to %s, %s)" % (co["period"]["from"], co["period"]["to"], co["period"]["why"]), ""]
    L.append("- %d posts, %s views. The top %d posts hold %s of them (%s); half the views come from %s post%s." % (
        co.get("posts") or 0, n0(co.get("views")), ts.get("n") or 0, pc(ts.get("share")), ts.get("rule"),
        (co.get("half") or {}).get("n", "-"), "" if (co.get("half") or {}).get("n") == 1 else "s"))
    ic = co.get("in_common") or {}
    L.append("- In the top %d: %s." % (ts.get("n") or 0, ", ".join("%s %d" % (k.replace("_", " "), ic[k]) for k in ic if ic[k])))
    L += table(["Post", "Date", "Type", "Views", "Share", "Replies", "Ratio", "Kinds"],
               [[x["post_id"], x["at"][:10], x["type"], n0(x["views"]), pc(x["share"]), n0(x["replies"]), xr(x["ratio"]),
                 ", ".join(x["kinds"]) + (" (under settle)" if x["too_new"] else "")] for x in co.get("top_posts") or []])
    L.append("")
    cc = g.get("crowd_calls") or {}
    L += ["### Crowd calls (a named crowd or a promise to reply, with an ask)", ""]
    if cc.get("count"):
        L.append("- %d posts; %s of the period's views (%s)." % (cc["count"], pc(cc.get("share_in_period")), n0(cc.get("views_in_period"))))
        L += table(["Post", "Date", "Views", "Replies", "Rows read", "Author's replies read", "First line"],
                   [[x["post_id"], x["at"][:10], n0(x["views"]), n0(x["replies"]), n0(x["replies_read"]), n0(x["author_replies_read"]),
                     x["first_line"][:80] + (" (under settle)" if x["too_new"] else "")] for x in (cc.get("posts") or {}).values()])
    else:
        L.append("- None found.")
    L.append("")
    K = g.get("kinds") or {}
    L += ["### Kinds of post, with against without (the window's scored posts)", ""]
    L += table(["Kind", "With: posts / median ratio / hits", "Without", "Share of the period's views", "Few posts"],
               [[x["label"], "%d / %s / %d" % (x["with"]["scored"], xr(x["with"]["median_ratio"]), x["with"]["hits"]),
                 "%d / %s / %d" % (x["without"]["scored"], xr(x["without"]["median_ratio"]), x["without"]["hits"]),
                 pc(x["in_period"]["share"]), "yes" if x["few_posts"] else ""] for x in K.values()])
    L.append("")
    rg = g.get("repost_graph") or {}
    L += ["### Who reposted the top posts", ""]
    if rg.get("read"):
        L.append("- Tagged accounts that reposted: %d of %d, across %d posts read. Big accounts (%s): %s." % (
            rg["tagged_reposted"], rg["tagged"], len(rg["read"]), (g.get("rules") or {}).get("big_account"),
            ", ".join("@%s (%s)" % (b["handle"], n0(b["followers"])) for b in rg.get("big") or []) or "none"))
        for pid in rg["read"]:
            x = rg["posts"][pid]
            L.append("- %s (%s views, %s reposts, %d read): tagged %s; reposted by %s." % (
                pid, n0(x["views"]), n0(x["reposts"]), x["rows_read"],
                "%d of %d reposted" % (x["tagged_reposted_count"], x["tagged_count"]) if x["tagged_count"] else "none",
                ", ".join("@%s %s%s%s" % (r["handle"], n0(r["followers"]), " big" if r["big"] else "", " tagged" if r["tagged"] else "") for r in x["reposters"]) or "-"))
        if rg.get("repeat_reposters"):
            L.append("- On 2 or more of these posts: " + ", ".join("@%s (%d)" % (r["handle"], len(r["posts"])) for r in rg["repeat_reposters"]))
    else:
        L.append("- Not read.")
    L.append("")
    tg = g.get("tags") or {}
    L += ["### Tags and credits", "",
          "- %d of %d posts tag accounts (in the post or its first self-reply; %d in the first self-reply). Most tagged: %s." % (
              tg.get("posts_with_tags", 0), tg.get("of_posts", 0), tg.get("in_first_reply", 0),
              ", ".join("@%s %d" % (t["handle"], t["posts"]) for t in (tg.get("top") or [])[:8]) or "none"), ""]
    ro = g.get("replies_out")
    L += ["### Replies to other accounts", ""]
    if ro:
        L.append("- %d replies from %s to %s (%s min, %s an hour; %s). %d accounts; %d in its own threads; %d to big accounts; "
                 "%d to accounts that reposted or were tagged." % (ro["count"], (ro["from"] or "")[:16].replace("T", " "),
                                                                    (ro["to"] or "")[11:16], n0(ro["span_minutes"]), ro["per_hour"],
                                                                    ro["note"], ro["targets"], ro["in_own_threads"], ro["to_big"], ro["to_circle"]))
        L.append("- By the size of the account answered: " + ", ".join("%s %d" % (SIZE_LABELS.get(k, k), n) for k, n in ro["by_size"].items() if n))
        if ro.get("big_targets"):
            L.append("- Big accounts answered: " + ", ".join("@%s (%s)" % (t["handle"], n0(t["followers"])) for t in ro["big_targets"]))
    else:
        L.append("- Not read.")
    L.append("")
    sp = g.get("speed")
    L += ["### Speed on big posts", ""]
    if sp:
        L += table(["Own post", "Kind", "Original", "Original views", "Minutes after", "Own views", "Big"],
                   [[x["post_id"], x["kind"], "@%s" % x["original_handle"], n0(x["original_views"]), n0(x["minutes"]),
                     n0(x["own_views"]), "yes" if x["big"] else ""] for x in sp["items"].values()])
    else:
        L.append("- Not read.")
    L.append("")
    fl = g.get("flops")
    L += ["### What the weakest format lacks", ""]
    if fl:
        f = fl["format"]
        L.append("- %s: %d posts in the window, lift %s, %d hits, %d of the %d flops (%s)." % (
            f["name"], f["posts"], xr(f["lift"]), f["hits"], f["flops"], f["flops_all"], f["from"]))
        L += table(["", "In the format", "The other posts"],
                   [[x["label"], pc(x["format"]) if k != "chars" else n0(x["format"]), pc(x["rest"]) if k != "chars" else n0(x["rest"])]
                    for k, x in fl["features"].items()])
        L.append("- It lacks: %s." % (", ".join(fl["features"][k]["label"] for k in fl["lacks"]) or "nothing measured here"))
    else:
        L.append("- No format with 6 scored posts or more sits under the account's usual (radar.json).")
    L.append("")
    fo = g.get("followers") or {}
    L += ["### Followers", "", "- " + ("%s to %s: %s to %s (%+d)." % (fo["from"][:10], fo["to"][:10], n0(fo["first"]), n0(fo["last"]), fo["gain"])
                                       if fo.get("measured") else "Follower growth " + fo.get("note", "")), ""]
    if g.get("limits"):
        L += ["### Samples and what was not read", ""]
        for x in g["limits"]:
            L.append("- %s: %s." % (x["what"], x["why"].rstrip(".")))
        L.append("")
    L.append('Try it on your own account or any other: "REA Viral: why is @handle growing"')
    L.append("")
    return "\n".join(L)


def write(folder, top_share=None):
    g = measure(folder, top_share)
    write_json(os.path.join(folder, "growth.json"), g)
    v = view(folder, g)
    write_text(os.path.join(folder, "GROWTH.md"), growth_md(v))
    return g, v


def page_view(v):
    """What the report's "Why it grows" block draws: the reading, the reply draft and the measured parts, with bios and
    texts cut short (build_report.py embeds it in the page)."""
    if not v:
        return None
    g = dict(v["growth"])
    g.pop("posts", None)
    g.pop("inputs", None)
    rg = dict(g.get("repost_graph") or {})
    rg["posts"] = [dict(x, reposters=[dict(r, bio=(r.get("bio") or "")[:90]) for r in x["reposters"][:12]])
                   for x in (rg.get("posts") or {}).values()]
    g["repost_graph"] = rg
    cad = dict(g.get("cadence") or {})
    cad["weeks"] = [dict(w, week=k) for k, w in (cad.get("weeks") or {}).items()]
    cad["months"] = [dict(m, month=k) for k, m in (cad.get("months") or {}).items()]
    g["cadence"] = cad
    cc = g.get("crowd_calls") or {}
    g["crowd_calls"] = dict(cc, posts=[cc["posts"][i] for i in cc.get("order") or []])
    sp = g.get("speed")
    if sp:
        g["speed"] = dict(sp, items=[sp["items"][i] for i in sp.get("order") or []])
    return {"g": g, "why": v["why"], "doesnt_move": v["doesnt_move"], "copy_this": v["copy_this"], "reply": v["reply"],
            "reply_chars": v["reply_chars"], "follow_up": v["follow_up"], "ready": v["ready"],
            "checks": v["problems"] + v["checks"], "has_reading": v["has_reading"]}


def stale(folder):
    p = os.path.join(folder, "growth.json")
    if not os.path.exists(p):
        return None
    was = read_json(p).get("inputs") or {}
    have = input_fingerprint(folder, tuple(was.keys()))
    changed = sorted(k for k in was if have.get(k) != was.get(k))
    return ("growth.json was made before %s changed: run growth.py again" % ", ".join(changed)) if changed else None


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    if os.path.exists(os.path.join(folder, "niche.json")) or os.path.exists(os.path.join(folder, "post.json")):
        die("%s is not an account folder: growth mode runs on one account (references/growth.md)" % folder)
    ts = None
    if "--top-share" in argv:
        ts = float(argv[argv.index("--top-share") + 1])
        if not 0 < ts < 1:
            die("--top-share is a share between 0 and 1, e.g. 0.15")
    g, v = write(folder, ts)
    cp = (g.get("cadence") or {}).get("change_point")
    co = g.get("concentration") or {}
    print("growth.json and GROWTH.md: status %s; %s; top %d posts = %s of %s views since %s" % (
        g["status"], ("change point %s: %s -> %s posts a week" % (cp["at"], cp["before"], cp["after"])) if cp else "no change point",
        (co.get("top_slice") or {}).get("n") or 0, pc((co.get("top_slice") or {}).get("share")), n0(co.get("views")),
        co["period"]["from"]))
    cc = g.get("crowd_calls") or {}
    rg = g.get("repost_graph") or {}
    print("crowd calls %d; tagged accounts that reposted %d of %d (%d posts read); replies to others %s; big quotes %s" % (
        cc.get("count") or 0, rg.get("tagged_reposted") or 0, rg.get("tagged") or 0, len(rg.get("read") or []),
        (g.get("replies_out") or {}).get("count", "not read"), (g.get("speed") or {}).get("big_quotes", "not read")))
    rd = g.get("reads") or {}
    if rd.get("reposters"):
        print("read next: who reposted %s (one page each)" % ", ".join(rd["reposters"]))
    if rd.get("replies_under"):
        print("read next: the replies under %s (one page each)" % ", ".join(rd["replies_under"]))
    if rd.get("originals"):
        print("read next: the originals quoted by %s (originals.csv)" % ", ".join(rd["originals"]))
    if rd.get("replies_out"):
        print("read next: one window of the account's replies to others (replies_out.csv)")
    for x in g.get("limits") or []:
        print("note: %s: %s" % (x["what"], x["why"]))
    if not v["has_reading"]:
        print("next: write findings.json \"growth\" (references/growth.md, step 4), then run growth.py again for the reply draft")
        return 0
    if v["reply"]:
        print("reply draft: %d characters, %s" % (v["reply_chars"], "ready" if v["ready"] else "NOT READY"))
    for p in v["problems"] + v["checks"]:
        print("NOT READY: " + p)
    return 0 if v["ready"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
