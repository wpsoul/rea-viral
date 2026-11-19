#!/usr/bin/env python3
"""Build the hand-over from the data files: the report (report.html) for people, a layered file for agents, and the
files a planner connector takes.

    python3 build_report.py <run folder> [--light]

It picks the report from the folder: an Account report (account.json + posts.csv; ACCOUNT.md), a Post report
(post.json; POST.md, report_post.py) or a Niche report (niche.json; NICHE.md, report_niche.py). Every report has a
part of its own for what did not work, beside what worked.

The Account report reads account.json, analysis.json, radar.json, comments.json, writing.json, voice.md,
findings.json, formats/*.md, videos/*/notes.json and probe.json, cost.csv. The page draws a copy of that data,
embedded in it, so it opens from file:// with no server and no other file beside it: the pictures it draws (covers,
frame sheets) are inside it as small data URIs, each under a cap, all under one budget (page_kit.py), each linked to
the original post. The data files stay the source (an app can draw the same files). Rebuild after any change.

Beside the page it writes report-light.html (the same report with no pictures inside and only the data it draws: for
a planner in a chat app that takes the page as text), report-cover.jpg when the run has a picture of its own (the
account's picture, or the post's cover), and report_record.json, brief.json and radar_rows.json (hand_over.py,
brief.py): the report's record, its short view and the formats, in the shape a planner connector's tools take
(references/connections.md, "A planner connector"). It prints both pages' sizes (the full one's target is under
3 MB). --light writes the light page and the planner files only, with no picture work.

Refuses to build when:
- validate.py finds errors (a claim without an evidence label, a SEEN claim without its post, ...);
- analysis.json, radar.json, comments.json or writing.json were made from older inputs (it names the script to run
  again).

The page: one file, dark (a Light button switches), no scripts from anywhere, fonts from Google Fonts when online
(system fonts otherwise). Charts are SVG drawn by the page's own script. Every claim shows its evidence label.
"""
import csv
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SKILL_VERSION, die, iso, now_utc, read_csv, read_json, write_text  # noqa: E402
import validate  # noqa: E402
import brief  # noqa: E402
import hand_over  # noqa: E402
import page_kit  # noqa: E402
from analyze import input_fingerprint  # noqa: E402

RECIPE_RE = re.compile(r"```json rea-recipe\s*\n(.*?)\n```", re.S)


def load_opt(folder, name):
    p = os.path.join(folder, name)
    if not os.path.exists(p):
        return None
    return read_json(p)


def stale(folder, doc, name, script):
    if doc is None:
        return None
    was = doc.get("inputs") or {}
    have = input_fingerprint(folder, tuple(was.keys()))
    changed = sorted(k for k in was if have.get(k) != was.get(k))
    if changed:
        return "%s was made before %s changed: run %s again" % (name, ", ".join(changed), script)
    return None


def recipes(folder, radar):
    out = {}
    for f in (radar or {}).get("formats") or []:
        p = os.path.join(folder, "formats", f["id"] + ".md")
        if not os.path.exists(p):
            continue
        text = open(p, encoding="utf-8").read()
        m = RECIPE_RE.search(text)
        rec = None
        if m:
            try:
                rec = json.loads(m.group(1))
            except ValueError:
                rec = None
        prose = RECIPE_RE.sub("", text)
        prose = re.sub(r"<!-- rea:measured:start -->.*?<!-- rea:measured:end -->", "", prose, flags=re.S)
        out[f["id"]] = {"recipe": rec, "file": "formats/%s.md" % f["id"], "text": prose.strip()[:6000]}
    return out


def videos(folder):
    out = {}
    vdir = os.path.join(folder, "videos")
    if not os.path.isdir(vdir):
        return out
    for pid in sorted(os.listdir(vdir)):
        d = os.path.join(vdir, pid)
        if not os.path.isdir(d):
            continue
        notes = load_opt(folder, os.path.join("videos", pid, "notes.json"))
        probe = load_opt(folder, os.path.join("videos", pid, "probe.json"))
        if notes is None and probe is None:
            continue
        out[pid] = {"notes": notes, "probe": {"read": (probe or {}).get("read"),
                                              "not_read_reason": (probe or {}).get("not_read_reason"),
                                              "measured": (probe or {}).get("measured"),
                                              "sheet_first": existing(folder, ((probe or {}).get("files") or {}).get("sheet_first")),
                                              "sheet_shots": existing(folder, ((probe or {}).get("files") or {}).get("sheet_shots"))}}
    return out


def cost(folder):
    p = os.path.join(folder, "cost.csv")
    if not os.path.exists(p):
        return {"rows": [], "total_usd": 0.0}
    _, rows = read_csv(p)
    total = 0.0
    for r in rows:
        try:
            total += float(r.get("total_usd") or 0)
        except ValueError:
            pass
    return {"rows": rows, "total_usd": round(total, 4)}


def existing(folder, rel_path):
    """The page links only files that exist, so a missing cover or sheet is shown as missing, not as a broken load."""
    if not rel_path:
        return None
    return rel_path if os.path.exists(os.path.join(folder, rel_path)) else None


def page_data(folder, light=False):
    acc = read_json(os.path.join(folder, "account.json"))
    an = load_opt(folder, "analysis.json")
    if an is None:
        die("no analysis.json: run analyze.py first", 1)
    radar = load_opt(folder, "radar.json")
    com = load_opt(folder, "comments.json")
    wr = load_opt(folder, "writing.json")
    problems = [p for p in (stale(folder, an, "analysis.json", "analyze.py"),
                            stale(folder, radar, "radar.json", "radar.py"),
                            stale(folder, com, "comments.json", "comment_tactics.py"),
                            stale(folder, wr, "writing.json", "text_probe.py")) if p]
    if problems:
        die("\n".join(problems), 1)
    findings = load_opt(folder, "findings.json") or {}
    posts = []
    for p in an.get("posts") or []:
        f = p.get("followers") or {}
        posts.append({
            "id": p["post_id"], "url": p["url"], "at": p["published_at"], "type": p["type"], "views": p["views"],
            "likes": p["likes"], "comments": p["comments"], "shares": p["shares"], "saves": p["saves"],
            "ratio": p["ratio"], "hit": p["hit"], "status": p["status"], "in_window": p["in_window"],
            "cover": existing(folder, p.get("cover_file")), "caption": (p.get("caption") or "")[:220], "duration": p.get("duration_s"),
            "baseline": p.get("baseline"), "vpf": p.get("views_per_follower"),
            "f": {k: f.get(k) for k in ("level", "evidence", "gain_72h", "excess_72h", "share_of_gain", "score", "label",
                                         "signals", "raw", "reason")},
        })
    vids = videos(folder)
    nw = not_working(an, radar, wr, vids)
    pics = page_kit.Pictures(folder, light=light)
    # Only the pictures the page draws go inside it, the most telling first while the budget lasts: the formats'
    # proof posts, the watched videos' first seconds, then the posts of what did not work.
    wanted = []
    for f in (radar or {}).get("formats") or []:
        wanted += [e["post_id"] for e in f.get("examples") or []]
    by_id = dict((p["id"], p) for p in posts)
    covers = {}

    def cover_of(pid):
        if pid not in covers and pid in by_id:
            covers[pid] = pics.get(by_id[pid]["cover"], "cover")
    for pid in wanted:
        cover_of(pid)
    for pid, v in vids.items():
        pr = v["probe"]
        pr["sheet_first"] = pics.get(pr.get("sheet_first"), "sheet") if pr.get("sheet_first") else None
        pr["sheet_shots"] = None   # not drawn: it stays in the run folder
    for f in nw["formats"]:
        for x in f["lowest"]:
            cover_of(x["post_id"])
    for x in nw["flops"]["picks"]:
        cover_of(x["post_id"])
    for pid, v in vids.items():
        if not v["probe"].get("sheet_first"):
            cover_of(pid)
    for p in posts:
        p["cover"] = covers.get(p["id"])
    d = {
        "skill_version": SKILL_VERSION,
        "built_at": iso(now_utc()),
        "account": {k: acc.get(k) for k in ("network", "handle", "name", "url", "bio", "link", "followers",
                                             "followers_exact", "posts_total", "private", "read_at", "window",
                                             "spend_ceiling_usd", "user")},
        "sources": acc.get("sources") or [],
        "comments_read_meta": acc.get("comments_read"),
        "analysis": {k: an.get(k) for k in ("status", "status_note", "metric", "counts", "rates", "timeline", "followers",
                                            "attribution", "outliers", "flops", "deep_read", "baseline", "excluded",
                                            "settings", "warnings", "window")},
        "posts": posts,
        "radar": radar,
        "comments": com,
        "findings": findings,
        "recipes": recipes(folder, radar),
        "writing": writing_view(wr),
        "voice": voice_view(folder),
        "videos": vids,
        "not_working": nw,
        "missing_files": None,
        "cost": cost(folder),
        "pictures": pics.summary(),
    }
    return d


# ---------------------------------------------------------------------------------------------- what did not work

def not_working(an, radar, wr, vids):
    """What did not work, from the scripts' own files: the formats under the account's usual or weakening (radar.json),
    the flops and what the watched ones show (analysis.json, videos/*/notes.json), and what sinks in the words
    (writing.json). MEASURED and SEEN only; the agent's reading of it is findings.json `did_not_work`. Says "not
    enough data" where that is the truth, and never names a cause: a flop shows what was there, not why it flopped."""
    ratio = dict((p["post_id"], p.get("ratio")) for p in an.get("posts") or [])
    r = radar or {}
    fm = r.get("formats") or []
    in_fmt = {}
    for f in fm:
        for i in f.get("post_ids") or []:
            in_fmt[i] = f
    flops_all = list(an.get("flops") or [])
    out = {"status": an.get("status"), "note": None}
    if an.get("status") != "ok":
        out["note"] = "Not enough data: %s" % (an.get("status_note") or an.get("status"))
    formats, fnote = [], None
    if r.get("status") != "ok":
        fnote = "Not enough data: %s" % (r.get("status_note") or "no formats measured yet (run radar.py)")
    else:
        for f in fm:
            if f.get("quadrant") == "too_few" or f.get("lift") is None:
                continue
            under = f["lift"] < 1.0
            weak = f.get("direction_label") == "weakening"
            if not (under or weak):
                continue
            ids = set(f.get("post_ids") or [])
            scored = sorted([i for i in ids if ratio.get(i) is not None], key=lambda i: ratio[i])
            formats.append({
                "id": f["id"], "name": f.get("name"), "quadrant": f["quadrant"], "quadrant_name": f["quadrant_name"],
                "lift": f["lift"], "share": f.get("share"), "posts_total": f.get("posts_total"),
                "posts_scored": f.get("posts_scored"), "hit_rate": f.get("hit_rate"), "direction": f.get("direction"),
                "direction_label": f.get("direction_label"), "few_posts": bool(f.get("few_posts")),
                "under": under, "weakening": weak, "flops": sum(1 for i in flops_all if i in ids),
                "lowest": [{"post_id": i, "ratio": ratio[i]} for i in scored[:3]],
                "evidence": "MEASURED", "from": "radar.json#formats.%s" % f["id"]})
        formats.sort(key=lambda x: x["lift"])
        if not formats:
            fnote = "No format sits under the account's usual or weakens."
    out["formats"], out["formats_note"] = formats, fnote
    by = {}
    for i in flops_all:
        k = (in_fmt.get(i) or {}).get("id")
        by[k] = by.get(k, 0) + 1
    names = dict((f["id"], f.get("name")) for f in fm)
    picks = []
    for i in (an.get("deep_read") or {}).get("flops") or []:
        n = (vids.get(i) or {}).get("notes") or {}
        seen = (n.get("seen") or {}) if n.get("read") is True else {}

        def said(v):
            return (v.get("text") if isinstance(v, dict) else v) or None
        picks.append({"post_id": i, "ratio": ratio.get(i), "format": (in_fmt.get(i) or {}).get("name"),
                      "read": n.get("read"), "not_read_reason": n.get("not_read_reason"),
                      "hook": said(seen.get("hook")), "turn": said(seen.get("turn")), "ask": said(seen.get("ask"))})
    out["flops"] = {
        "count": len(flops_all), "of_scored": (an.get("counts") or {}).get("scored") or 0,
        "flop_ratio": (an.get("settings") or {}).get("flop_ratio", 0.5),
        "by_format": [{"format": k, "name": names.get(k) if k else None, "flops": v}
                      for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0] or "~"))],
        "picks": picks, "evidence": "MEASURED", "from": "analysis.json#flops",
        "note": None if flops_all else "No post sat at half its usual or under in the window."}
    words = {"sinks": [], "leads": [], "worst": [], "note": None}
    if wr is None:
        words["note"] = "Not measured: text_probe.py was not run, so what sinks in the words is unknown."
    elif wr.get("status") != "ok":
        words["note"] = "Not enough data: %s" % (wr.get("status_note") or wr.get("status"))
    else:
        for f in wr.get("features") or []:
            if f.get("claim_ok") and f.get("verdict") == "sinks":
                words["sinks"].append({"id": f["id"], "label": f["label"], "with": f["with"], "without": f["without"],
                                       "chance": f.get("chance"), "from": "writing.json#features.%s" % f["id"]})
        if not words["sinks"]:
            words["note"] = ("Nothing in the words sinks clearly (6 posts or more on each side, 0.8x the usual or under, "
                             "and the chance test).")
            leads = [f for f in wr.get("features") or [] if f.get("verdict") == "no clear difference"
                     and f.get("vs_usual") is not None and f["vs_usual"] <= 0.8 and (f.get("with") or {}).get("posts", 0) >= 6]
            leads.sort(key=lambda f: f["vs_usual"])
            words["leads"] = [{"id": f["id"], "label": f["label"], "with": f["with"], "without": f["without"],
                               "chance": f.get("chance"), "from": "writing.json#features.%s" % f["id"]} for f in leads[:3]]
        words["worst"] = ((wr.get("first_lines") or {}).get("worst") or [])[:3]
    out["words"] = words
    return out


def weakest_line(nw):
    """One line of what did not work, MEASURED, for ACCOUNT.md and the summary."""
    fs = nw.get("formats") or []
    if fs:
        f = fs[0]
        return "%s (%s): lift %s over the account's own usual on %d scored posts%s%s%s" % (
            f["name"], f["quadrant_name"], xr(f["lift"]), f["posts_scored"] or 0,
            (", %s %s" % (f["direction_label"], xr(f["direction"]))) if f.get("direction") is not None else "",
            (", %d of the %d flops" % (f["flops"], nw["flops"]["count"])) if f.get("flops") else "",
            "; few posts, not a finding on its own" if f.get("few_posts") else "")
    return nw.get("formats_note") or "nothing measured"


def writing_view(wr):
    """The part of writing.json the page draws."""
    if not wr:
        return None
    keep = ("id", "group", "label", "kind", "needs_words", "verdict", "claim_ok", "with", "without", "unknown",
            "vs_without", "vs_usual", "chance", "usage", "best", "worst", "note", "unknown_why")
    feats = []
    for f in wr.get("features") or []:
        x = dict((k, f.get(k)) for k in keep)
        x["signals"] = {"with": dict((k, (v or {}).get("median")) for k, v in ((f.get("signals") or {}).get("with") or {}).items()),
                        "without": dict((k, (v or {}).get("median")) for k, v in ((f.get("signals") or {}).get("without") or {}).items())}
        feats.append(x)
    nums = []
    for f in wr.get("numbers") or []:
        nums.append(dict((k, f.get(k)) for k in ("id", "group", "label", "verdict", "claim_ok", "usage", "groups",
                                                 "winning_range", "chance", "hits_median", "flops_median", "note")))
        for g in nums[-1].get("groups") or []:
            g.pop("signals", None)
    out = dict((k, wr.get(k)) for k in ("status", "status_note", "counts", "language", "signal_names", "account_signals",
                                        "overlaps", "first_lines", "asks", "on_screen", "settings", "metric"))
    out["features"] = feats
    out["numbers"] = nums
    return out


def voice_view(folder):
    p = os.path.join(folder, "voice.md")
    if not os.path.exists(p):
        return None
    text = open(p, encoding="utf-8").read()
    m = re.search(r"```json rea-voice\s*\n(.*?)\n```", text, re.S)
    rec = None
    if m:
        try:
            rec = json.loads(m.group(1))
        except ValueError:
            rec = None
    prose = re.sub(r"```json rea-voice\s*\n.*?\n```", "", text, flags=re.S)
    prose = re.sub(r"<!-- rea:measured:start -->.*?<!-- rea:measured:end -->", "", prose, flags=re.S)
    prose = re.sub(r"^# .*\n", "", prose.strip())
    return {"file": "voice.md", "rules": (rec or {}).get("rules"), "text": prose.strip()[:8000]}


def embed(d):
    s = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")


# ---------------------------------------------------------------------------------------------- ACCOUNT.md

def pct(v):
    if v is None:
        return "-"
    return ("%.1f%%" % (100 * v)) if 0 < v < 0.1 else "%d%%" % round(100 * v)


def xr(v):
    if v is None:
        return "-"
    v = float(v)
    if 0.995 <= v < 1.005 and v != 1.0:
        return "%.3fx" % v
    return ("%.2f" % v).rstrip("0").rstrip(".") + "x"


def claim_line(c):
    ev = c.get("evidence")
    extra = ""
    if ev == "SEEN":
        extra = " (seen in: %s)" % ", ".join((c.get("posts") or []) + (c.get("links") or []))
    elif ev == "INFERRED":
        extra = " (basis: %s)" % c.get("basis")
    elif ev == "MEASURED":
        extra = " (from %s)" % c.get("from")
    return "[%s] %s%s" % (ev, c.get("text") or c.get("what") or "", extra)


def account_md(d):
    a = d["account"]
    an = d["analysis"]
    r = d["radar"] or {}
    fi = d["findings"] or {}
    nw = d.get("not_working") or {}
    L = []
    name = a.get("name") or a.get("handle")
    L.append("# %s (@%s on %s): REA Viral, Account report" % (name, a.get("handle"), a.get("network")))
    L.append("")
    L.append("For agents. Read Layer 0 for the answer (what worked and what did not), Layer 1 to find the part a question "
             "needs, Layer 2 for the detail. "
             "Labels: MEASURED = computed by the skill's scripts from the data files; SEEN = a frame, comment or row shows "
             "it (linked); INFERRED = reasoned, with the basis written. Built %s by REA Viral %s." % (d["built_at"], d["skill_version"]))
    L.append("")
    L.append("## Layer 0: the answer")
    L.append("")
    if an.get("status") != "ok":
        L.append("- Status: %s. %s" % (an.get("status"), an.get("status_note") or ""))
    if fi.get("headline"):
        L.append("- " + claim_line(fi["headline"]))
    fm = r.get("formats") or []
    order = {"scale_it": 0, "underused": 1}
    best = [f for f in fm if f["quadrant"] in order and not f.get("few_posts")]
    best.sort(key=lambda f: (order[f["quadrant"]], -(f.get("lift") or 0)))
    if best:
        f = best[0]
        L.append("- [MEASURED] Strongest format: %s (%s), lift %s over the account's own baseline, %s of posts, hit rate %s%s "
                 "(radar.json#formats.%s; the grouping is the agent's, formats.json)." % (
                     f["name"], f["quadrant_name"], xr(f["lift"]), pct(f["share"]), pct(f["hit_rate"]),
                     (", direction %s %s" % (xr(f["direction"]), f["direction_label"])) if f.get("direction") is not None else "",
                     f["id"]))
    elif fm:
        L.append("- [MEASURED] No format sits in Scale it or Underused with 6+ posts (radar.json).")
    if nw.get("formats"):
        L.append("- [MEASURED] What did not work: %s (%s)." % (weakest_line(nw), nw["formats"][0]["from"]))
    elif nw.get("formats_note"):
        L.append("- [MEASURED] What did not work, in its formats: %s" % nw["formats_note"])
    for cl in (fi.get("did_not_work") or [])[:1]:
        L.append("- " + claim_line(cl))
    att = an.get("attribution") or {}
    lv = att.get("levels") or {}
    if (lv.get("measured") or 0) + (lv.get("watched") or 0):
        L.append("- [MEASURED] Follower gain is measured for %d posts (daily counts cover them); top: %s." % (
            lv.get("measured", 0) + lv.get("watched", 0), ", ".join(att.get("top_measured", [])[:3])))
    elif lv.get("estimated"):
        posts_by = dict((p["id"], p) for p in d["posts"])
        lab = [i for i in att.get("top_estimated", []) if (posts_by.get(i, {}).get("f") or {}).get("label")]
        L.append("- [INFERRED] No daily follower counts: which posts brought followers is ESTIMATED from signals, never "
                 "counted; " + ("likeliest: %s." % ", ".join(lab[:3]) if lab else
                                "no post shows a clear sign (no score reached 0.3)."))
    L.append("")
    L.append("## Layer 1: where each answer is")
    L.append("")
    c = an.get("counts") or {}
    L.append("| Question | Short answer | Read |")
    L.append("|---|---|---|")
    L.append("| How many posts were read? | %s posts, %s in the window, %s scored against a baseline | analysis.json#counts |" % (
        c.get("posts_total"), c.get("in_window"), c.get("scored")))
    outl = an.get("outliers") or []
    L.append("| Which posts beat the account's usual? | %d at 2x or more: %s | posts_scored.csv |" % (
        len(outl), (", ".join(outl[:5]) + (", …" if len(outl) > 5 else "")) or "none"))
    for q in ("scale_it", "underused", "fading", "drop"):
        names = [f["name"] + (" (few posts)" if f.get("few_posts") else "") for f in fm if f["quadrant"] == q]
        if names:
            L.append("| Formats to %s | %s | radar.json, formats/*.md |" % (
                {"scale_it": "scale", "underused": "use more (underused)", "fading": "watch (fading)", "drop": "drop"}[q],
                "; ".join(names)))
    nfl, wd = nw.get("flops") or {}, nw.get("words") or {}
    dnw = []
    if nw.get("formats"):
        dnw.append("formats under its usual or weakening: " + "; ".join(
            "%s %s" % (f["name"], xr(f["lift"])) + (" (few posts)" if f.get("few_posts") else "") for f in nw["formats"]))
    elif nw.get("formats_note"):
        dnw.append(nw["formats_note"])
    if nfl and nfl.get("note"):
        dnw.append(nfl["note"][:1].lower() + nfl["note"][1:].rstrip("."))
    elif nfl:
        dnw.append(("%d flops of %d scored posts" % (nfl["count"], nfl["of_scored"])) +
                   ("" if not nfl["by_format"] else " (" + ", ".join(
                       "%d %s" % (b["flops"], b["name"] or "in no format") for b in nfl["by_format"][:3]) + ")"))
    if wd.get("sinks"):
        dnw.append("in the words: " + "; ".join("%s sinks" % s["label"] for s in wd["sinks"]))
    elif wd.get("note"):
        dnw.append("in the words: " + wd["note"][:1].lower() + wd["note"][1:])
    if dnw:
        L.append("| What did not work? | %s | radar.json, analysis.json#flops, writing.json, findings.json#did_not_work |" % (
            ". ".join(dnw).replace("|", "/")))
    if d.get("comments") and d["comments"].get("status") == "ok":
        cm = d["comments"]
        rb = cm.get("replies_by_creator") or {}
        L.append("| How are the comments run? | own comment on %s of %s posts; reply rate %s; %d follow comments | comments.json |" % (
            (cm.get("creator_comment") or {}).get("posts_with_own_comment"), (cm.get("creator_comment") or {}).get("of_posts"),
            pct(rb.get("rate")) if rb.get("rate") is not None else "unknown", (cm.get("follow_comments") or {}).get("count", 0)))
    marks = (an.get("timeline") or {}).get("marks") or []
    marks = marks + ((r.get("timeline_marks") or []) if r else [])
    if marks:
        L.append("| What changed when? | %s | analysis.json#timeline.marks, radar.json#timeline_marks |" % "; ".join(
            "%s %s" % (m["at"], m["text"]) for m in sorted(marks, key=lambda m: m["at"])[:4]))
    wr = d.get("writing") or {}
    if wr:
        st = [f for f in (wr.get("features") or []) + (wr.get("numbers") or []) if f.get("claim_ok")]
        if wr.get("status") != "ok":
            short = "status %s: %s" % (wr.get("status"), wr.get("status_note") or "")
        else:
            short = "; ".join("%s: %s" % (f["label"], f["verdict"]) for f in st[:5]) or "nothing in the words lifts or sinks clearly"
        L.append("| How does it write? | %s | writing.json, voice.md |" % short)
    if fi.get("plays"):
        L.append("| What should the user do? | %s | findings.json#plays |" % "; ".join(p["title"] for p in fi["plays"][:5]))
    L.append("| What was not read? | %s | findings.json#not_read |" % (
        "; ".join(n["what"] for n in (fi.get("not_read") or [])) or "nothing listed"))
    L.append("| What did it cost? | $%.4f | cost.csv |" % d["cost"]["total_usd"])
    L.append("")
    L.append("## Layer 2: detail")
    L.append("")
    if fm:
        L.append("### Its formats: the Format map (MEASURED by radar.py)")
        L.append("")
        L.append("| Format | Corner | Posts | Share | Lift | Hit rate | Direction | Follower pull | Effort | Recipe |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for f in fm:
            L.append("| %s | %s | %d | %s | %s | %s | %s | %s [%s] | %s | %s |" % (
                f["name"], f["quadrant_name"], f["posts_total"], pct(f["share"]), xr(f["lift"]), pct(f["hit_rate"]),
                (xr(f["direction"]) + " " + (f["direction_label"] or "")) if f["direction"] is not None else "-",
                f["follower_pull"]["label"], f["follower_pull"].get("evidence") or "unknown", f["effort"], f["recipe"]))
        L.append("")
    if wr:
        L.append("### How it writes (MEASURED by text_probe.py)")
        L.append("")
        L.append("%s scored posts with words. %s" % ((wr.get("counts") or {}).get("scored_with_text"), (wr.get("language") or {}).get("note") or ""))
        L.append("")
        L.append("| In the words | With it | Without it | Verdict | Chance |")
        L.append("|---|---|---|---|---|")
        n_rows = 0
        for f in wr.get("features") or []:
            if f.get("claim_ok"):
                n_rows += 1
                L.append("| %s | %s posts, %s | %s posts, %s | %s | %s |" % (
                    f["label"], f["with"]["posts"], xr(f["with"]["lift"]), f["without"]["posts"], xr(f["without"]["lift"]),
                    f["verdict"], "-" if f.get("chance") is None else "%.4f" % f["chance"]))
        for f in wr.get("numbers") or []:
            if f.get("claim_ok"):
                n_rows += 1
                w = f["winning_range"]
                L.append("| %s %s to %s | %s posts, %s | weakest group %s | %s | %s |" % (
                    f["label"], w["range"][0], w["range"][1], w["posts"], xr(w["lift"]), xr((w.get("weakest") or {}).get("lift")),
                    f["verdict"], "-" if f.get("chance") is None else "%.4f" % f["chance"]))
        if not n_rows:
            L.append("| Nothing lifts or sinks clearly | - | - | - | - |")
        L.append("")
        fl = wr.get("first_lines") or {}
        for key, title in (("best", "Best first lines (SEEN)"), ("worst", "Worst first lines (SEEN)")):
            if fl.get(key):
                L.append("%s: %s" % (title, " | ".join('%s "%s" (%s)' % (xr(x["ratio"]), (x.get("first_line") or "")[:90], x["post_id"])
                                                    for x in fl[key][:4])))
        L.append("")
        L.append("The voice sheet: voice.md (its JSON block is what draft_check.py reads).")
        L.append("")
    L.append("### What did not work (MEASURED by the scripts; SEEN from the watched flops)")
    L.append("")
    if nw.get("note"):
        L.append("- " + nw["note"])
    if nw.get("formats"):
        L.append("| Format | Corner | Posts scored | Lift | Direction | Flops in it | Lowest posts |")
        L.append("|---|---|---|---|---|---|---|")
        for f in nw["formats"]:
            L.append("| %s%s | %s | %d | %s | %s | %d | %s |" % (
                f["name"], " (few posts)" if f.get("few_posts") else "", f["quadrant_name"], f["posts_scored"] or 0,
                xr(f["lift"]), (xr(f["direction"]) + " " + (f["direction_label"] or "")) if f.get("direction") is not None else "-",
                f["flops"], ", ".join("%s %s" % (x["post_id"], xr(x["ratio"])) for x in f["lowest"])))
        L.append("")
    elif nw.get("formats_note"):
        L.append("- Formats: " + nw["formats_note"])
    if nfl and nfl.get("note"):
        L.append("- [MEASURED] " + nfl["note"] + " (analysis.json#flops)")
    if nfl and not nfl.get("note"):
        L.append("- [MEASURED] Flops (%s of their baseline or under): %d of %d scored posts%s (analysis.json#flops)." % (
            xr(nfl["flop_ratio"]), nfl["count"], nfl["of_scored"],
            "" if not nfl["by_format"] else "; " + ", ".join("%d %s" % (b["flops"], b["name"] or "in no format") for b in nfl["by_format"])))
        if nfl["picks"]:
            L.append("- The lowest posts the deep read picked to watch:")
        for x in nfl["picks"]:
            if x["read"] is True:
                L.append("  - [SEEN] %s at %s%s: hook: %s; turn: %s (videos/%s/notes.json). What a flop shows is not why "
                         "it flopped." % (x["post_id"], xr(x["ratio"]), (" (%s)" % x["format"]) if x["format"] else "",
                                          x["hook"] or "-", x["turn"] or "-", x["post_id"]))
            else:
                L.append("  - %s at %s: not watched%s." % (x["post_id"], xr(x["ratio"]),
                                                          (": " + x["not_read_reason"]) if x.get("not_read_reason") else ""))
    if wd.get("sinks"):
        for s in wd["sinks"]:
            L.append("- [MEASURED] In the words, %s sinks: %d posts at %s against %s without (%s)." % (
                s["label"], s["with"]["posts"], xr(s["with"]["lift"]), xr(s["without"]["lift"]), s["from"]))
    elif wd.get("note"):
        L.append("- In the words: " + wd["note"][:1].lower() + wd["note"][1:])
    for s in wd.get("leads") or []:
        L.append("- [MEASURED] A lead, not a finding: %s, %d posts at %s against %s without, chance %s (%s)." % (
            s["label"], s["with"]["posts"], xr(s["with"]["lift"]), xr(s["without"]["lift"]),
            "-" if s.get("chance") is None else "%.3f" % s["chance"], s["from"]))
    for cl in fi.get("did_not_work") or []:
        L.append("- " + ("**%s.** " % cl["title"] if cl.get("title") else "") + claim_line(cl))
    L.append("")
    for sec, title in (("mechanisms", "What worked, the agent's reading"), ("writing", "How it writes, the agent's reading"),
                       ("comment_tactics", "Comment tactics"), ("timeline_notes", "Timeline notes")):
        if fi.get(sec):
            L.append("### " + title)
            L.append("")
            for cl in fi[sec]:
                L.append("- " + ("**%s.** " % cl["title"] if cl.get("title") else "") + claim_line(cl))
            L.append("")
    if fi.get("plays"):
        L.append("### Plays")
        L.append("")
        for i, p in enumerate(fi["plays"], 1):
            L.append("%d. **%s** (effort %s). %s" % (i, p["title"], p.get("effort"), claim_line(p)))
            if p.get("dont_copy"):
                L.append("   Do not copy: %s" % p["dont_copy"])
            L.append("   Prompt: %s" % p.get("prompt", "").replace("\n", " "))
        L.append("")
    if fi.get("not_read"):
        L.append("### Not read")
        L.append("")
        for n in fi["not_read"]:
            L.append("- %s: %s" % (n["what"], n["why"]))
        L.append("")
    L.append("### Files")
    L.append("")
    L.append("account.json (profile, window, sources) · posts.csv (the corpus) · comments.csv · analysis.json and "
             "posts_scored.csv (numbers) · comments.json · radar.json · formats/<id>.md (recipes) · videos/<id>/ (frames, "
             "probe.json, notes.json) · writing.json, posts_text.csv and voice.md (how it writes) · findings.json (the "
             "agent's reading) · cost.csv · report.html (the Account report, one file) · report_record.json and "
             "radar_rows.json (for a planner connector)")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------- the page

PAGE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0c0e11;--panel:#14171c;--panel2:#1a1e24;--line:#262b33;--text:#e9ecef;--muted:#98a2ad;--faint:#6c7580;
--accent:#33efab;--accent-text:#0f1115;--measured:#33efab;--seen:#7db9ff;--inferred:#f3c56b;--bad:#ff7a7a;
--scale:#33efab;--under:#7db9ff;--fading:#f3c56b;--drop:#ff8f8f;--radius:12px}
:root[data-theme="light"]{--bg:#f6f7f9;--panel:#ffffff;--panel2:#f0f2f5;--line:#dfe3e8;--text:#14171c;--muted:#56606b;
--faint:#7d8792;--measured:#0f9e6e;--seen:#2f6fd0;--inferred:#a7700b;--bad:#c93c3c;--scale:#0f9e6e;--under:#2f6fd0;
--fading:#a7700b;--drop:#c93c3c}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text)}
body{font-family:Manrope,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;
-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
a{color:inherit;text-decoration:underline;text-decoration-color:var(--faint);text-underline-offset:2px}
a:hover{text-decoration-color:var(--accent)}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header.top{display:flex;gap:16px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.kicker{color:var(--muted);font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
h1{font-size:34px;line-height:1.1;margin:6px 0 6px;font-weight:800;letter-spacing:-.02em}
h2{font-size:20px;margin:0 0 4px;font-weight:800;letter-spacing:-.01em}
h3{font-size:15px;margin:0 0 6px;font-weight:700}
.sub{color:var(--muted)}
.btn{font:inherit;font-size:13px;font-weight:700;border-radius:8px;padding:7px 14px;cursor:pointer;border:1px solid var(--line);
background:var(--panel2);color:var(--text)}
.btn.primary{background:var(--accent);color:var(--accent-text);border-color:transparent}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:20px 0 6px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.stat .v{font-size:22px;font-weight:800}
.stat .l{color:var(--muted);font-size:12px}
section{margin-top:34px}
.sec-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px}
.grid2{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:14px}
@media (max-width:860px){.grid2{grid-template-columns:minmax(0,1fr)}}
.grid2>*{min-width:0}
.panel{overflow-x:auto}
.ev{display:inline-block;font-size:10.5px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;margin-right:6px;
border:1px solid currentColor;vertical-align:1px;white-space:nowrap}
.ev.MEASURED{color:var(--measured)}.ev.SEEN{color:var(--seen)}.ev.INFERRED{color:var(--inferred)}.ev.NONE{color:var(--faint)}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin-top:10px}
.claim{padding:10px 0;border-top:1px solid var(--line)}
.claim:first-child{border-top:none}
.claim .basis{color:var(--muted);font-size:13px;margin-top:3px}
.answer{font-size:19px;font-weight:700;line-height:1.4}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--muted);font-weight:700;font-size:12px;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.num{text-align:right;white-space:nowrap}
.q{display:inline-block;font-size:11.5px;font-weight:800;border-radius:999px;padding:1px 8px;color:var(--accent-text)}
.q.scale_it{background:var(--scale)}.q.underused{background:var(--under)}.q.fading{background:var(--fading)}.q.drop{background:var(--drop)}
.q.too_few{background:var(--faint)}
svg text{font-family:inherit;fill:var(--muted);font-size:11px}
svg .axis{stroke:var(--line)}
svg .split{stroke:var(--faint);stroke-dasharray:4 4}
.chart{width:100%;height:auto;display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column}
.card .body{padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.cover{width:100%;aspect-ratio:9/12;object-fit:cover;background:var(--panel2);display:block}
.cover.missing{display:flex;align-items:center;justify-content:center;color:var(--faint);font-size:12px}
.sheet{width:100%;display:block;background:var(--panel2)}
.thumbs{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.thumb{width:84px;text-decoration:none;font-size:11.5px;color:var(--muted)}
.thumb img,.thumb .ph{width:84px;height:112px;object-fit:cover;border-radius:8px;background:var(--panel2);display:block;margin-bottom:3px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;font-size:13px}
.kv .k{color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:12.5px}
.prompt{white-space:pre-wrap;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:13.5px;margin:8px 0}
.play{border-top:1px solid var(--line);padding:14px 0}
.play:first-child{border-top:none;padding-top:0}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.pill{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:1px 8px;color:var(--muted)}
.status{border-left:3px solid var(--inferred);padding:10px 14px;background:var(--panel);border-radius:8px;margin-top:16px}
.empty{color:var(--faint);font-size:13.5px}
.quote{border-left:2px solid var(--line);padding-left:10px;margin:6px 0;font-size:13.5px}
.fmt{margin-top:14px}
.fmt:first-child{margin-top:0}
footer{margin-top:48px;color:var(--faint);font-size:12.5px}
.v-lifts{color:var(--measured);font-weight:800}.v-sinks{color:var(--bad);font-weight:800}.v-other{color:var(--muted)}
.fl{border-top:1px solid var(--line);padding:9px 0;display:grid;grid-template-columns:64px minmax(0,1fr);gap:10px;align-items:baseline}
.fl:first-of-type{border-top:none}
.fl .r{font-weight:800;text-align:right;white-space:nowrap}
.fl .t{overflow-wrap:anywhere}
details.more{margin-top:12px}
details.more summary{cursor:pointer;color:var(--muted);font-size:13px;font-weight:700}
.voice h3{margin-top:12px}
.voice p{margin:4px 0;font-size:13.5px;overflow-wrap:anywhere}
.rules{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 4px}
</style>
</head>
<body>
<div class="wrap" id="app"><noscript>This page draws itself with JavaScript. ACCOUNT.md beside it holds the same findings as text.</noscript></div>
<script type="application/json" id="rea-data">__DATA__</script>
<script>
(function(){
"use strict";
var D = JSON.parse(document.getElementById('rea-data').textContent);
var drawn = {radar: 0, timeline: 0, followers: 0, writing: 0, first_lines: 0, not_working: 0};
window.__reaReport = {drawn: drawn, ready: false};
var SVGNS = 'http://www.w3.org/2000/svg';

function el(tag, attrs){
  var n = document.createElement(tag);
  attrs = attrs || {};
  for (var k in attrs){
    if (!Object.prototype.hasOwnProperty.call(attrs, k) || attrs[k] == null) continue;
    if (k === 'text') n.textContent = String(attrs[k]);
    else if (k === 'cls') n.className = attrs[k];
    else if (k === 'href'){ var u = safeHref(attrs[k]); if (u) { n.setAttribute('href', u); n.setAttribute('target', '_blank'); n.setAttribute('rel', 'noopener noreferrer'); } }
    else if (k === 'src'){ var s = safeSrc(attrs[k]); if (s) n.setAttribute('src', s); }
    else if (k.indexOf('on') === 0) n.addEventListener(k.slice(2), attrs[k]);
    else n.setAttribute(k, attrs[k]);
  }
  for (var i = 2; i < arguments.length; i++) add(n, arguments[i]);
  return n;
}
function add(n, c){
  if (c == null || c === false) return;
  if (Array.isArray(c)) { c.forEach(function(x){ add(n, x); }); return; }
  n.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
}
function sv(tag, attrs){
  var n = document.createElementNS(SVGNS, tag);
  for (var k in attrs || {}) { if (attrs[k] != null) { if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); } }
  return n;
}
function safeHref(u){ u = String(u || ''); return /^https?:\/\//i.test(u) ? u : (/^[\w./-]+$/.test(u) && u.indexOf('..') < 0 ? u : null); }
function safeSrc(u){ u = String(u || ''); if (/^https:\/\//i.test(u) || /^data:image\/(jpeg|png|webp|gif);base64,[A-Za-z0-9+\/=]+$/.test(u)) return u; return (/^[\w./-]+$/.test(u) && u.indexOf('..') < 0) ? u : null; }
function num(n){ if (n == null) return '—'; var a = Math.abs(n);
  if (a >= 1e9) return (n/1e9).toFixed(a >= 1e10 ? 0 : 1) + 'B'; if (a >= 1e6) return (n/1e6).toFixed(a >= 1e7 ? 0 : 1) + 'M';
  if (a >= 1e4) return (n/1e3).toFixed(0) + 'K'; if (a >= 1e3) return (n/1e3).toFixed(1) + 'K'; return String(Math.round(n)); }
function pct(x){ return x == null ? '—' : (x > 0 && x < 0.1 ? (x * 100).toFixed(1) : Math.round(x * 100)) + '%'; }
function xr(x){ if (x == null) return '—'; if (x >= 0.995 && x < 1.005 && x !== 1) return x.toFixed(3) + '×'; return (x >= 10 ? x.toFixed(0) : x.toFixed(2).replace(/0$/, '').replace(/\.$/, '')) + '×'; }
function date(s){ return s ? String(s).slice(0, 10) : '—'; }
function chip(ev){ return el('span', {cls: 'ev ' + (ev || 'NONE'), text: ev || 'UNKNOWN', title: EVTIP[ev] || 'not known'}); }
var EVTIP = {MEASURED: 'Computed by the skill\'s scripts from the data files', SEEN: 'A frame, a comment or a row shows it (linked)', INFERRED: 'Reasoned, with the basis written out'};
var POSTS = {}; (D.posts || []).forEach(function(p){ POSTS[p.id] = p; });
var QN = {scale_it: 'Scale it', underused: 'Underused', fading: 'Fading', drop: 'Drop', too_few: 'Too few posts'};
var QC = {scale_it: 'var(--scale)', underused: 'var(--under)', fading: 'var(--fading)', drop: 'var(--drop)', too_few: 'var(--faint)'};
var A = D.analysis || {}, R = D.radar || {}, F = D.findings || {}, C = D.comments || null, acc = D.account || {};
var app = document.getElementById('app');

function postLink(id){ var p = POSTS[id]; return p ? el('a', {href: p.url, text: id}) : el('span', {text: id}); }
function postLinks(ids){ var out = []; (ids || []).forEach(function(id, i){ if (i) out.push(', '); out.push(postLink(id)); }); return out; }
function claim(c){
  if (!c) return null;
  var src = [];
  if (c.evidence === 'SEEN') { if (c.posts && c.posts.length) src.push('Seen in ', postLinks(c.posts)); (c.links || []).forEach(function(u, i){ src.push(i || src.length ? ' · ' : '', el('a', {href: u, text: u.replace(/^https?:\/\//, '').slice(0, 48)})); }); }
  if (c.evidence === 'INFERRED') src.push('Basis: ' + (c.basis || ''));
  if (c.evidence === 'MEASURED') src.push('From ' + (c.from || ''));
  if (c.evidence !== 'SEEN' && c.posts && c.posts.length) src.push(' · posts: ', postLinks(c.posts));
  return el('div', {cls: 'claim'},
    el('div', null, chip(c.evidence), c.title ? el('strong', {text: c.title + '. '}) : null, c.text || c.what || ''),
    src.length ? el('div', {cls: 'basis'}, src) : null);
}
function section(id, title, sub){ var s = el('section', {id: id}); s.appendChild(el('div', {cls: 'sec-head'}, el('div', null, el('h2', {text: title}), sub ? el('div', {cls: 'sub small', text: sub}) : null))); app.appendChild(s); return s; }

/* ---------- header */
(function(){
  var name = acc.name || acc.handle || 'Account';
  var top = el('header', {cls: 'top'},
    el('div', null,
      el('div', {cls: 'kicker', text: 'REA Viral · Account report · ' + (acc.network || '') + ' · window ' + date((A.window || {}).from) + ' to ' + date((A.window || {}).to)}),
      el('h1', {text: name}),
      el('div', {cls: 'sub'}, acc.url ? el('a', {href: acc.url, text: '@' + acc.handle}) : '@' + acc.handle, acc.bio ? ' · ' + String(acc.bio).slice(0, 160) : '')),
    el('div', {cls: 'row'},
      el('button', {cls: 'btn', id: 'theme', type: 'button', text: 'Light', onclick: function(e){
        var r = document.documentElement; var dark = r.getAttribute('data-theme') !== 'light';
        r.setAttribute('data-theme', dark ? 'light' : 'dark'); e.target.textContent = dark ? 'Dark' : 'Light'; }})));
  app.appendChild(top);
  var c = A.counts || {};
  var tot = (D.cost || {}).total_usd || 0;
  var stats = el('div', {cls: 'stats'},
    stat(acc.followers == null ? '—' : num(acc.followers), 'followers' + (acc.followers_exact === false ? ' (rounded by the network)' : '') + ' on ' + date(acc.read_at)),
    stat(c.posts_total == null ? '—' : c.posts_total, 'posts read · ' + (c.in_window || 0) + ' in the window'),
    stat(c.scored == null ? '—' : c.scored, 'scored against their own baseline'),
    stat(c.hits == null ? '—' : c.hits, 'at 2× their baseline or more'),
    stat(((R.formats || []).length) || '—', 'formats measured'),
    stat('$' + tot.toFixed(tot < 1 ? 3 : 2), 'spent on data' + (acc.spend_ceiling_usd != null ? ' (ceiling $' + acc.spend_ceiling_usd + ')' : '')));
  app.appendChild(stats);
  app.appendChild(el('div', {cls: 'legend'}, el('span', null, chip('MEASURED'), EVTIP.MEASURED), el('span', null, chip('SEEN'), EVTIP.SEEN), el('span', null, chip('INFERRED'), EVTIP.INFERRED)));
  if (A.status && A.status !== 'ok') app.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Status: ' + A.status + '. '}), A.status_note || ''));
  function stat(v, l){ return el('div', {cls: 'stat'}, el('div', {cls: 'v', text: v}), el('div', {cls: 'l', text: l})); }
})();

/* ---------- the answer */
(function(){
  if (!F.headline && !(F.mechanisms || []).length) return;
  var s = section('answer', 'What worked', 'Why it grows, in the reading of the agent that ran the skill. Each line carries its evidence.');
  var p = el('div', {cls: 'panel'});
  if (F.headline) p.appendChild(el('div', {cls: 'answer'}, chip(F.headline.evidence), F.headline.text));
  if (F.headline && F.headline.basis) p.appendChild(el('div', {cls: 'basis muted small', text: 'Basis: ' + F.headline.basis}));
  var list = el('div', {style: 'margin-top:10px'});
  (F.mechanisms || []).forEach(function(m){ list.appendChild(claim(m)); });
  p.appendChild(list);
  s.appendChild(p);
})();

/* ---------- what did not work */
(function(){
  var NW = D.not_working || {}, FL = NW.flops || {}, WD = NW.words || {};
  var s = section('not-working', 'What did not work', 'What sits under the account\'s own usual: its formats under 1× or weakening, its flops, and what sinks in its words. A flop shows what was there, never on its own why it flopped.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (NW.note) p.appendChild(el('div', {cls: 'empty', style: 'margin-bottom:8px', text: NW.note}));
  var mine = el('div'); (F.did_not_work || []).forEach(function(c){ mine.appendChild(claim(c)); drawn.not_working++; });
  if ((F.did_not_work || []).length) p.appendChild(mine);
  p.appendChild(el('h3', {text: 'Formats under its usual or weakening', style: 'margin-top:12px'}));
  if (!(NW.formats || []).length) p.appendChild(el('div', {cls: 'empty', text: NW.formats_note || 'No format sits under the account\'s usual or weakens.'}));
  (NW.formats || []).forEach(function(f){
    p.appendChild(el('div', {cls: 'fmt'},
      el('div', {cls: 'row'}, el('a', {href: '#fmt-' + f.id, text: f.name}), el('span', {cls: 'q ' + f.quadrant, text: QN[f.quadrant]}), f.few_posts ? el('span', {cls: 'pill', text: 'few posts: not a finding on its own'}) : null),
      el('div', {cls: 'small', style: 'margin-top:4px'}, chip('MEASURED'), f.posts_scored + ' scored posts at ' + xr(f.lift) + ' the account\'s own usual' + (f.under ? '' : ' (over 1×, but weakening)') +
        (f.direction != null ? '; direction ' + xr(f.direction) + ' (' + f.direction_label + ')' : '; direction: not enough posts') + (f.flops ? '; ' + f.flops + ' of the ' + FL.count + ' flops' : '') + '. ', el('span', {cls: 'muted', text: 'From ' + f.from})),
      el('div', {cls: 'thumbs'}, (f.lowest || []).map(function(x){ return thumb(x.post_id, x.ratio); }))));
    drawn.not_working++;
  });
  p.appendChild(el('h3', {text: 'The flops', style: 'margin-top:14px'}));
  p.appendChild(el('div', {cls: 'small'}, chip('MEASURED'), FL.note ? FL.note + ' ' : (FL.count + ' of ' + FL.of_scored + ' scored posts sat at ' + xr(FL.flop_ratio) + ' their baseline or under' +
    ((FL.by_format || []).length ? ': ' + FL.by_format.map(function(b){ return b.flops + ' ' + (b.name || 'in no format'); }).join(', ') : '') + '. '), el('span', {cls: 'muted', text: 'From ' + (FL.from || 'analysis.json#flops')})));
  if ((FL.picks || []).length) p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'The lowest posts the deep read picked to watch:'}));
  (FL.picks || []).forEach(function(x){
    var t = el('div', {cls: 't'}, postLink(x.post_id), x.format ? el('span', {cls: 'muted', text: ' · ' + x.format}) : null,
      x.read === true ? el('div', {cls: 'small'}, chip('SEEN'), 'Hook: ' + (x.hook || '—') + ' · the turn: ' + (x.turn || '—') + (x.ask ? ' · the ask: ' + x.ask : ''))
                      : el('div', {cls: 'small muted', text: 'Not watched' + (x.not_read_reason ? ': ' + x.not_read_reason : '') + '.'}));
    p.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), t)); drawn.not_working++;
  });
  p.appendChild(el('h3', {text: 'What sinks in its words', style: 'margin-top:14px'}));
  if ((WD.sinks || []).length){
    var t = el('table', null, el('tr', null, el('th', {text: 'In the words'}), el('th', {cls: 'num', text: 'With it'}), el('th', {cls: 'num', text: 'Without it'}), el('th', {text: 'Verdict'})));
    WD.sinks.forEach(function(x){ t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), x.label), el('td', {cls: 'num', text: x['with'].posts + ' posts · ' + xr(x['with'].lift)}), el('td', {cls: 'num', text: x.without.posts + ' posts · ' + xr(x.without.lift)}),
      el('td', null, el('span', {cls: 'v-sinks', text: 'sinks'}), el('span', {cls: 'muted small', text: x.chance != null ? ' · chance ' + (x.chance < 0.001 ? '<0.1%' : (x.chance * 100).toFixed(1) + '%') : ''})))); drawn.not_working++; });
    p.appendChild(t);
  } else p.appendChild(el('div', {cls: 'empty', text: WD.note || 'Nothing in the words sinks clearly.'}));
  (WD.leads || []).forEach(function(x){ p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:4px'}, chip('MEASURED'), 'A lead, not a finding: ' + x.label + ', ' + x['with'].posts + ' posts at ' + xr(x['with'].lift) + ' against ' + xr(x.without.lift) + ' without' + (x.chance != null ? ', chance ' + (x.chance * 100).toFixed(1) + '%' : '') + '.')); });
  (WD.worst || []).forEach(function(x){ p.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), el('div', {cls: 't'}, chip('SEEN'), '"' + (x.first_line || '') + '"', el('div', {cls: 'small muted'}, postLink(x.post_id), ' · one of the worst first lines')))); });
})();

/* ---------- timeline */
(function(){
  var tl = A.timeline || {};
  var s = section('timeline', 'Timeline', 'Each dot is a post: its views over the median of the 20 posts before it (log scale). Lines mark measured changes.');
  var pts = (D.posts || []).filter(function(p){ return p.in_window && p.ratio != null && p.at; });
  var p = el('div', {cls: 'panel'});
  s.appendChild(p);
  if (!pts.length){ p.appendChild(el('div', {cls: 'empty', text: 'No scored posts to draw.'})); return; }
  var W = 960, H = 300, L = 46, Rr = 56, T = 16, B = 34;
  var t0 = Date.parse((A.window || {}).from), t1 = Date.parse((A.window || {}).to) + 864e5;
  var lo = -3, hi = 3;
  pts.forEach(function(q){ var y = Math.log2(Math.max(q.ratio, 1/16)); lo = Math.min(lo, Math.floor(y)); hi = Math.max(hi, Math.ceil(y)); });
  hi = Math.min(hi, 6); lo = Math.max(lo, -4);
  function X(t){ return L + (W - L - Rr) * (t - t0) / Math.max(1, t1 - t0); }
  function Y(r){ var y = Math.log2(Math.max(r, Math.pow(2, lo))); return T + (H - T - B) * (hi - Math.min(y, hi)) / (hi - lo); }
  var svg = sv('svg', {viewBox: '0 0 ' + W + ' ' + H, cls: 'chart', role: 'img', 'aria-label': 'Posts over time against their baseline', 'class': 'chart', 'data-chart': 'timeline'});
  for (var e = lo; e <= hi; e++){
    var yy = Y(Math.pow(2, e));
    svg.appendChild(sv('line', {x1: L, x2: W - Rr, y1: yy, y2: yy, 'class': e === 0 ? 'split' : 'axis'}));
    svg.appendChild(sv('text', {x: L - 6, y: yy + 4, 'text-anchor': 'end', text: (e >= 0 ? Math.pow(2, e) : '1/' + Math.pow(2, -e)) + '×'}));
  }
  (tl.months || []).forEach(function(m, i){ if (i % Math.max(1, Math.ceil((tl.months || []).length / 12))) return; var x = X(Date.parse(m.month + '-01')); svg.appendChild(sv('text', {x: x, y: H - 12, text: m.month})); });
  var fs = (A.followers || {}).series || [];
  if (fs.length > 1){
    var fmin = Math.min.apply(null, fs.map(function(r){ return r.followers; })), fmax = Math.max.apply(null, fs.map(function(r){ return r.followers; }));
    var d = '', rng = Math.max(1, fmax - fmin);
    fs.forEach(function(r, i){ var t = Date.parse(r.at); if (t < t0 || t > t1) return; var x = X(t), y = T + (H - T - B) * (1 - (r.followers - fmin) / rng); d += (d ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); });
    if (d){ svg.appendChild(sv('path', {d: d, fill: 'none', stroke: 'var(--seen)', 'stroke-width': 1.6, opacity: 0.85})); drawn.followers = fs.length;
      svg.appendChild(sv('text', {x: W - Rr + 6, y: T + 8, text: num(fmax)})); svg.appendChild(sv('text', {x: W - Rr + 6, y: H - B, text: num(fmin)}));
      svg.appendChild(sv('text', {x: W - Rr + 6, y: T + 22, text: 'followers', fill: 'var(--seen)'})); }
  }
  var marks = (tl.marks || []).concat(R.timeline_marks || []);
  marks.forEach(function(m, i){ var x = X(Date.parse(m.at)); if (!(x >= L && x <= W - Rr)) return;
    svg.appendChild(sv('line', {x1: x, x2: x, y1: T, y2: H - B, stroke: 'var(--inferred)', 'stroke-dasharray': '2 4', opacity: 0.7}));
    var t = sv('title', {text: m.at + ': ' + m.text + ' [' + m.evidence + ']'}); var hit = sv('rect', {x: x - 4, y: T, width: 8, height: H - T - B, fill: 'transparent'}); hit.appendChild(t); svg.appendChild(hit); });
  pts.forEach(function(q){
    var c = sv('circle', {cx: X(Date.parse(q.at)).toFixed(1), cy: Y(q.ratio).toFixed(1), r: q.hit ? 4.6 : 3, fill: q.hit ? 'var(--accent)' : (q.ratio <= 0.5 ? 'var(--drop)' : 'var(--faint)'), opacity: q.hit ? 0.95 : 0.7, 'data-post': q.id});
    c.appendChild(sv('title', {text: q.id + ' · ' + date(q.at) + ' · ' + num(q.views) + ' views · ' + xr(q.ratio)}));
    svg.appendChild(c); drawn.timeline++;
  });
  p.appendChild(svg);
  var ml = el('div', {style: 'margin-top:10px'});
  marks.sort(function(a, b){ return a.at < b.at ? -1 : 1; }).forEach(function(m){ ml.appendChild(el('div', {cls: 'small'}, chip(m.evidence), el('strong', {text: m.at + ' '}), m.text, m.posts ? [' · ', postLinks(m.posts)] : null)); });
  (F.timeline_notes || []).forEach(function(c){ ml.appendChild(claim(c)); });
  var rh = tl.rhythm || {};
  if (rh.posts_per_week != null) ml.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px'}, chip('MEASURED'), rh.posts_per_week + ' posts a week; median ' + rh.median_hours_between_posts + ' h between posts.'));
  p.appendChild(ml);
})();

/* ---------- format radar */
(function(){
  var s = section('radar', 'Format map', 'This account\'s own formats. Across: how often a format is used. Up: its lift over the account\'s own baseline. Size: follower pull. Arrow: its direction.');
  var p = el('div', {cls: 'grid2'});
  s.appendChild(p);
  var fm = (R.formats || []);
  if (!R.status || R.status !== 'ok' || !fm.length){
    p.appendChild(el('div', {cls: 'panel'}, el('div', {cls: 'empty', text: R.status_note || 'No formats measured yet.'}),
      (R.posts || []).length ? el('table', null, el('tr', null, el('th', {text: 'Post'}), el('th', {text: 'Date'}), el('th', {cls: 'num', text: 'Views'})),
        R.posts.map(function(q){ return el('tr', null, el('td', null, postLink(q.post_id)), el('td', {text: date(q.published_at)}), el('td', {cls: 'num', text: num(q.views)})); })) : null));
    return;
  }
  var W = 560, H = 420, L = 54, Rr = 18, T = 18, B = 44;
  var placed = fm.filter(function(f){ return f.quadrant !== 'too_few' && f.lift != null; });
  var xmax = Math.max(0.4, Math.max.apply(null, placed.map(function(f){ return f.share; }).concat([0])) * 1.18);
  var ylo = -2, yhi = 2;
  placed.forEach(function(f){ var y = Math.log2(f.lift); ylo = Math.min(ylo, Math.floor(y - 0.4)); yhi = Math.max(yhi, Math.ceil(y + 0.4)); });
  function X(v){ return L + (W - L - Rr) * v / xmax; }
  function Y(v){ return T + (H - T - B) * (yhi - Math.log2(Math.max(v, Math.pow(2, ylo)))) / (yhi - ylo); }
  var svg = sv('svg', {viewBox: '0 0 ' + W + ' ' + H, 'class': 'chart', role: 'img', 'aria-label': 'Format map', 'data-chart': 'radar'});
  var xs = (R.rules || {}).often_share || 0.15, ys = (R.rules || {}).strong_lift || 1;
  svg.appendChild(sv('rect', {x: L, y: T, width: W - L - Rr, height: H - T - B, fill: 'var(--panel2)', rx: 8}));
  svg.appendChild(sv('line', {x1: X(xs), x2: X(xs), y1: T, y2: H - B, 'class': 'split'}));
  svg.appendChild(sv('line', {x1: L, x2: W - Rr, y1: Y(ys), y2: Y(ys), 'class': 'split'}));
  [['Scale it', W - Rr - 8, T + 18, 'end', 'var(--scale)'], ['Underused', L + 8, T + 18, 'start', 'var(--under)'],
   ['Fading', W - Rr - 8, H - B - 10, 'end', 'var(--fading)'], ['Drop', L + 8, H - B - 10, 'start', 'var(--drop)']].forEach(function(q){
    svg.appendChild(sv('text', {x: q[1], y: q[2], 'text-anchor': q[3], text: q[0], fill: q[4], 'font-weight': 800, 'font-size': 13})); });
  for (var e = ylo; e <= yhi; e++){ svg.appendChild(sv('text', {x: L - 6, y: Y(Math.pow(2, e)) + 4, 'text-anchor': 'end', text: (e >= 0 ? Math.pow(2, e) : '1/' + Math.pow(2, -e)) + '×'})); }
  [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].forEach(function(v){ if (v > xmax) return; svg.appendChild(sv('text', {x: X(v), y: H - B + 16, 'text-anchor': 'middle', text: Math.round(v * 100) + '%'})); });
  svg.appendChild(sv('text', {x: (L + W - Rr) / 2, y: H - 8, 'text-anchor': 'middle', text: 'share of posts'}));
  var tt = sv('text', {x: 14, y: (T + H - B) / 2, 'text-anchor': 'middle', transform: 'rotate(-90 14 ' + ((T + H - B) / 2) + ')', text: 'lift over baseline'}); svg.appendChild(tt);
  var labels = [];
  var maxM = 0; placed.forEach(function(f){ if (f.follower_pull.level === 'measured' && f.follower_pull.value > maxM) maxM = f.follower_pull.value; });
  placed.slice().sort(function(a, b){ return (b.follower_pull.value || 0) - (a.follower_pull.value || 0); }).forEach(function(f){
    var pull = f.follower_pull || {}, n = 0;
    if (pull.level === 'measured' && maxM > 0) n = Math.max(0, pull.value) / maxM; else if (pull.level === 'estimated') n = pull.value || 0;
    var r = 9 + 24 * Math.sqrt(Math.max(0, Math.min(1, n)));
    var cx = X(f.share), cy = Y(f.lift), g = sv('g', {'data-format': f.id});
    g.appendChild(sv('circle', {cx: cx, cy: cy, r: r, fill: QC[f.quadrant], 'fill-opacity': pull.level === 'none' ? 0.08 : 0.28, stroke: QC[f.quadrant], 'stroke-width': 2}));
    if (f.direction != null){
      var len = Math.max(-1, Math.min(1, Math.log2(f.direction))) * 26;
      if (Math.abs(len) > 3){ var y2 = cy - len; g.appendChild(sv('line', {x1: cx, y1: cy, x2: cx, y2: y2, stroke: 'var(--text)', 'stroke-width': 2}));
        g.appendChild(sv('path', {d: 'M' + (cx - 5) + ' ' + (y2 + (len > 0 ? 6 : -6)) + 'L' + cx + ' ' + y2 + 'L' + (cx + 5) + ' ' + (y2 + (len > 0 ? 6 : -6)), fill: 'none', stroke: 'var(--text)', 'stroke-width': 2})); }
    }
    labels.push({cx: cx, cy: cy, r: r, name: f.name.length > 26 ? f.name.slice(0, 25) + '…' : f.name, g: g});
    g.appendChild(sv('title', {text: f.name + ' · ' + QN[f.quadrant] + ' · ' + pct(f.share) + ' of posts · lift ' + xr(f.lift) + ' · hit rate ' + pct(f.hit_rate) + ' · ' + (pull.label || '')}));
    svg.appendChild(g); drawn.radar++;
  });
  // Labels: right of the bubble, or left of it in the right half; pushed down when they would overlap.
  var taken = [];
  labels.sort(function(a, b){ return a.cy - b.cy; }).forEach(function(l){
    var w = l.name.length * 6.6, left = l.cx > (L + W - Rr) / 2;
    var x = left ? l.cx - l.r - 6 - w : l.cx + l.r + 6, y = l.cy + 4;
    for (var k = 0; k < 12; k++){
      var hit = taken.some(function(t){ return x < t.x + t.w && t.x < x + w && Math.abs(t.y - y) < 15; });
      if (!hit) break; y += 15;
    }
    taken.push({x: x, y: y, w: w});
    l.g.appendChild(sv('text', {x: x, y: y, text: l.name, fill: 'var(--text)', 'font-weight': 700, 'font-size': 12}));
  });
  p.appendChild(el('div', {cls: 'panel'}, svg));
  var tbl = el('table', null, el('tr', null, el('th', {text: 'Format'}), el('th', {text: 'Corner'}), el('th', {cls: 'num', text: 'Posts'}), el('th', {cls: 'num', text: 'Lift'}), el('th', {cls: 'num', text: 'Hits'}), el('th', {text: 'Direction'})));
  fm.forEach(function(f){ tbl.appendChild(el('tr', null, el('td', null, el('a', {href: '#fmt-' + f.id, text: f.name})), el('td', null, el('span', {cls: 'q ' + f.quadrant, text: QN[f.quadrant]})),
    el('td', {cls: 'num', text: f.posts_total + ' · ' + pct(f.share)}), el('td', {cls: 'num', text: xr(f.lift)}), el('td', {cls: 'num', text: pct(f.hit_rate)}),
    el('td', {cls: 'small', text: f.direction == null ? 'not enough posts' : xr(f.direction) + ' ' + (f.direction_label || '')}))); });
  var un = R.unformatted || {};
  p.appendChild(el('div', {cls: 'panel'}, tbl, el('div', {cls: 'small muted', style: 'margin-top:8px'}, chip('MEASURED'), 'All numbers by radar.py. ' + (un.posts ? un.posts + ' posts (' + pct(un.share) + ') belong to no format.' : ''))));
  var list = el('div', {cls: 'panel', style: 'margin-top:14px'});
  fm.forEach(function(f){
    var rc = (D.recipes || {})[f.id] || {}, rec = rc.recipe || {}, pull = f.follower_pull || {};
    var box = el('div', {cls: 'fmt', id: 'fmt-' + f.id},
      el('div', {cls: 'row'}, el('h3', {text: f.name, style: 'margin:0'}), el('span', {cls: 'q ' + f.quadrant, text: QN[f.quadrant]}), el('span', {cls: 'pill', text: 'effort ' + (f.effort || '?')}), rc.file ? el('a', {cls: 'small', href: rc.file, text: rc.file}) : null),
      el('div', {cls: 'kv', style: 'margin-top:8px'},
        el('span', {cls: 'k', text: 'Container'}), el('span', {text: [f.container.hook, f.container.structure, f.container.look, f.container.length].filter(Boolean).join(' · ')}),
        el('span', {cls: 'k', text: 'Measured'}), el('span', null, chip('MEASURED'), f.posts_total + ' posts, ' + pct(f.share) + ' of the window; lift ' + xr(f.lift) + '; hit rate ' + pct(f.hit_rate) + (f.direction != null ? '; direction ' + xr(f.direction) + ' (' + f.direction_label + ')' : '') + (f.length_s_median != null ? '; median length ' + f.length_s_median + ' s' : '')),
        el('span', {cls: 'k', text: 'Follower pull'}), el('span', null, chip(pull.evidence), pull.label || 'unknown', pull.basis ? el('span', {cls: 'muted', text: ' · ' + pull.basis}) : null),
        rec.hook_pattern ? [el('span', {cls: 'k', text: 'Hook'}), el('span', {text: rec.hook_pattern})] : null,
        (rec.beats || []).length ? [el('span', {cls: 'k', text: 'Beats'}), el('span', {text: rec.beats.map(function(b){ return b.at + ' s ' + b.what + (b.text ? ': ' + b.text : ''); }).join(' → ')})] : null,
        rec.caption_style ? [el('span', {cls: 'k', text: 'Captions'}), el('span', {text: rec.caption_style})] : null,
        rec.sound ? [el('span', {cls: 'k', text: 'Sound'}), el('span', {text: rec.sound})] : null,
        f.basis ? [el('span', {cls: 'k', text: 'Why a format'}), el('span', null, chip('SEEN'), f.basis)] : null),
      el('div', {cls: 'thumbs'}, (f.examples || []).map(function(e){ return thumb(e.post_id, e.ratio); })));
    list.appendChild(box);
  });
  s.appendChild(list);
})();
/* ---------- how it writes */
(function(){
  var W = D.writing, V = D.voice;
  if (!W) return;
  var cn = W.counts || {}, lg = W.language || {}, sn = W.signal_names || {};
  var s = section('writing', 'How it writes', 'The account\'s own words measured against its own results: ' + (cn.scored_with_text || 0) + ' scored posts with words. ' + (lg.note || ''));
  if (W.status !== 'ok') s.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Status: ' + W.status + '. '}), W.status_note || ''));
  var OL = {opens_number: 'a number', opens_result_number: 'a result in numbers', opens_time_span: 'a time span', opens_question: 'a question',
    opens_how: '"how"', opens_you: '"you"', opens_i: '"I" or "my"', opens_name: 'a name', opens_quote: 'a quote mark', opens_negation: 'a negation', opens_imperative: 'a command'};
  function openLabel(o){ return 'opens with ' + (OL[o] || o.replace('opens_', '').replace(/_/g, ' ')); }
  function vcls(v){ return /lift/.test(v || '') && v !== 'no clear difference' ? 'v-lifts' : (/sink/.test(v || '') ? 'v-sinks' : 'v-other'); }
  function side(g){ return g && g.posts ? g.posts + ' posts · ' + xr(g.lift) : '—'; }
  var feats = W.features || [], nums = W.numbers || [];
  var strong = feats.filter(function(f){ return f.claim_ok; });
  var strongN = nums.filter(function(f){ return f.claim_ok; });
  var p1 = el('div', {cls: 'panel'});
  p1.appendChild(el('h3', {text: 'What lifts and what sinks'}));
  if (!strong.length && !strongN.length) p1.appendChild(el('div', {cls: 'empty', text: 'Nothing in the words lifts or sinks clearly: no feature passed with 6 posts or more on each side, a 1.25× difference and the chance test.'}));
  if (strong.length){
    var t = el('table', null, el('tr', null, el('th', {text: 'In the words'}), el('th', {cls: 'num', text: 'With it'}), el('th', {cls: 'num', text: 'Without it'}), el('th', {text: 'Verdict'}), el('th', {text: (sn.save || 'saves per like') + ', with / without'})));
    strong.forEach(function(f){
      var sg = f.signals || {};
      t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), f.label), el('td', {cls: 'num', text: side(f['with'])}), el('td', {cls: 'num', text: side(f.without)}),
        el('td', null, el('span', {cls: vcls(f.verdict), text: f.verdict}), el('span', {cls: 'muted small', text: f.chance != null ? ' · chance ' + (f.chance < 0.001 ? '<0.1%' : (f.chance * 100).toFixed(1) + '%') : ''})),
        el('td', {cls: 'small muted', text: ((sg['with'] || {}).save != null ? (sg['with'].save).toFixed(2) : '—') + ' / ' + ((sg.without || {}).save != null ? (sg.without.save).toFixed(2) : '—')})));
      drawn.writing++;
    });
    p1.appendChild(t);
  }
  strongN.forEach(function(f){
    var w = f.winning_range || {};
    p1.appendChild(el('div', {cls: 'claim'}, el('div', null, chip('MEASURED'), el('strong', {text: f.label + ': '}),
      (f.groups || []).map(function(g, i){ return (i ? ' · ' : '') + fmtR(g.range) + ' → ' + xr(g.lift) + ' (' + g.posts + ' posts)'; }).join(''),
      el('span', {cls: 'v-lifts', text: '  ' + f.verdict}))));
    drawn.writing++;
  });
  function fmtR(r){ if (!r) return '—'; var a = r[0], b = r[1]; function f(x){ return x == null ? '?' : (x % 1 ? x.toFixed(2) : String(x)); } return a === b ? f(a) : f(a) + '–' + f(b); }
  (W.overlaps || []).forEach(function(o){ p1.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px'}, chip('MEASURED'), o.a + ' and ' + o.b + ' sit on the same ' + o.posts_both + ' posts: the numbers cannot tell them apart.')); });
  (F.writing || []).forEach(function(c){ p1.appendChild(claim(c)); });
  var rest = feats.filter(function(f){ return !f.claim_ok; }).concat(nums.filter(function(f){ return !f.claim_ok; }));
  if (rest.length){
    var det = el('details', {cls: 'more'}, el('summary', {text: 'Everything else measured (' + rest.length + ')'}));
    var t2 = el('table', null, el('tr', null, el('th', {text: 'Feature'}), el('th', {cls: 'num', text: 'Used in'}), el('th', {text: 'Verdict'})));
    rest.forEach(function(f){
      var u = f.usage || {};
      var used = f.kind === 'number' || f.groups ? (u.median != null ? 'median ' + (u.median % 1 ? u.median.toFixed(2) : u.median) : '—') : (u.known ? u['with'] + ' of ' + u.known + ' posts' : 'unknown');
      t2.appendChild(el('tr', null, el('td', {text: f.label}), el('td', {cls: 'num', text: used}), el('td', {cls: 'small ' + vcls(f.verdict), text: (f.verdict || '—') + (f.note ? ' (' + f.note + ')' : '') + (f.unknown_why ? ' (' + f.unknown_why + ')' : '')})));
    });
    det.appendChild(t2);
    p1.appendChild(det);
  }
  s.appendChild(p1);
  var fl = W.first_lines || {};
  var g = el('div', {cls: 'grid2', style: 'margin-top:14px'});
  [['The best first lines', fl.best || []], ['The worst first lines', fl.worst || []]].forEach(function(col){
    var pn = el('div', {cls: 'panel'}, el('h3', null, chip('SEEN'), col[0]));
    if (!col[1].length) pn.appendChild(el('div', {cls: 'empty', text: 'No scored posts.'}));
    col[1].forEach(function(x){
      pn.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), el('div', {cls: 't'}, '"' + (x.first_line || '') + '"',
        el('div', {cls: 'small muted'}, postLink(x.post_id), ' · ' + (x.chars != null ? x.chars + ' characters' : '') + (x.openings && x.openings.length ? ' · ' + x.openings.map(openLabel).join(', ') : ''))))); drawn.first_lines++; });
    g.appendChild(pn);
  });
  s.appendChild(g);
  if ((W.on_screen || []).length){
    var po = el('div', {cls: 'panel', style: 'margin-top:14px'}, el('h3', null, chip('SEEN'), 'First lines on screen (watched videos)'));
    W.on_screen.forEach(function(x){ po.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), el('div', {cls: 't'}, '"' + x.first_line + '"',
      el('div', {cls: 'small muted'}, postLink(x.post_id), ' · ' + x.chars + ' characters' + (x.openings.length ? ' · ' + x.openings.map(openLabel).join(', ') : ''))))); });
    s.appendChild(po);
  }
  var ak = W.asks || {}, as = W.account_signals || {};
  var p3 = el('div', {cls: 'panel', style: 'margin-top:14px'});
  p3.appendChild(el('h3', {text: 'Its asks, and what its words pull'}));
  if (ak.posts_known){
    var kinds = Object.keys(ak.kinds || {}).filter(function(k){ return ak.kinds[k]; });
    p3.appendChild(el('div', {cls: 'small'}, chip('MEASURED'), ak.posts_with_ask + ' of ' + ak.posts_known + ' posts ask for something' + (kinds.length ? ': ' + kinds.map(function(k){ return k + ' ' + ak.kinds[k]; }).join(', ') : '') +
      (ak.where && Object.keys(ak.where).length ? '; where: ' + Object.keys(ak.where).map(function(k){ return String(k).replace('_', ' ') + ' ' + ak.where[k]; }).join(', ') : '') + '.'));
    var lr = ak.later_replies || {};
    if (lr.posts) p3.appendChild(el('div', {cls: 'small', style: 'margin-top:4px'}, chip('MEASURED'), 'The author replied under ' + lr.posts + ' posts later, with an ask on ' + lr.with_ask + '. ', el('span', {cls: 'muted', text: lr.note || ''})));
    (ak.examples || []).slice(0, 4).forEach(function(e){ if (e.phrases && e.phrases.length) p3.appendChild(el('div', {cls: 'quote'}, chip('SEEN'), e.phrases.map(function(x){ return '"' + x + '"'; }).join(' '), el('span', {cls: 'muted small'}, ' · ', postLink(e.post_id), ' · ' + xr(e.ratio)))); });
  } else p3.appendChild(el('div', {cls: 'empty', text: 'The asks could not be read: the word lists do not cover these posts\' language.'}));
  var sig = Object.keys(as).filter(function(k){ return as[k] && as[k].median != null; });
  p3.appendChild(el('div', {cls: 'small', style: 'margin-top:8px'}, chip('MEASURED'), sig.length ? 'Per like, the account\'s median: ' + sig.map(function(k){ return (sn[k] || k) + ' ' + as[k].median.toFixed(2); }).join(' · ') + '.' : 'The network gives no saves, shares or replies to set against likes here (unknown, not zero).'));
  s.appendChild(p3);
  if (V){
    var p4 = el('div', {cls: 'panel voice', style: 'margin-top:14px'});
    p4.appendChild(el('div', {cls: 'row'}, el('h3', {text: 'The voice sheet', style: 'margin:0'}), el('a', {cls: 'small', href: V.file, text: V.file})));
    var r = V.rules || {};
    var rr = el('div', {cls: 'rules'});
    if (r.first_line_chars) rr.appendChild(el('span', {cls: 'pill', text: 'first line ' + r.first_line_chars[0] + '–' + r.first_line_chars[1] + ' characters'}));
    if (r.max_paragraph_lines) rr.appendChild(el('span', {cls: 'pill', text: 'paragraphs up to ' + r.max_paragraph_lines + ' lines'}));
    (r.openings || []).forEach(function(o){ rr.appendChild(el('span', {cls: 'pill', text: openLabel(o)})); });
    (r.avoid || []).forEach(function(o){ rr.appendChild(el('span', {cls: 'pill', text: 'avoid: ' + o.replace(/_/g, ' ')})); });
    if (r.asks && (r.asks.kinds || []).length) rr.appendChild(el('span', {cls: 'pill', text: 'asks: ' + r.asks.kinds.join(', ') + (r.asks.where ? ' (' + String(r.asks.where).replace('_', ' ') + ')' : '')}));
    if (r.length_limit) rr.appendChild(el('span', {cls: 'pill', text: 'limit ' + r.length_limit + ' characters'}));
    p4.appendChild(rr);
    p4.appendChild(el('div', {cls: 'small muted', text: 'The rules a draft is checked against (draft_check.py). Below: the agent\'s reading, each line with its label.'}));
    String(V.text || '').split(/\n(?=## )/).forEach(function(block){
      var lines = block.split('\n'), head = lines[0].indexOf('## ') === 0 ? lines.shift().slice(3) : null;
      var body = lines.join('\n').trim();
      if (!head && !body) return;
      if (head) p4.appendChild(el('h3', {text: head}));
      body.split(/\n{2,}/).forEach(function(par){
        // a markdown list: each "- " line is its own paragraph; backticks are dropped (the page shows no code font)
        par.split(/\n(?=- )/).forEach(function(item){ if (item.trim()) p4.appendChild(el('p', {text: item.replace(/\n\s*/g, ' ').replace(/`/g, '')})); });
      });
    });
    s.appendChild(p4);
  }
})();
function thumb(id, ratio){
  var p = POSTS[id] || {};
  return el('a', {cls: 'thumb', href: p.url, title: (p.caption || '').slice(0, 120)}, p.cover ? el('img', {src: p.cover, alt: ''}) : el('div', {cls: 'ph'}), id.slice(0, 12) + ' · ' + xr(ratio != null ? ratio : p.ratio));
}

/* ---------- followers */
(function(){
  var s = section('followers', 'Which posts brought followers', 'No public source says which post a follower came from. The level says what this is based on.');
  var at = A.attribution || {}, lv = at.levels || {}, fo = A.followers || {};
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  var meas = (at.top_measured || []).map(function(id){ return POSTS[id]; }).filter(Boolean);
  var est = (at.top_estimated || []).map(function(id){ return POSTS[id]; }).filter(Boolean);
  p.appendChild(el('div', {cls: 'small muted', style: 'margin-bottom:8px'}, chip('MEASURED'),
    (lv.measured || 0) + ' posts measured from follower counts, ' + (lv.watched || 0) + ' from our own Watch counts, ' + (lv.estimated || 0) + ' estimated from signals.' +
    (fo.usual_daily_gain != null ? ' Usual gain ' + num(fo.usual_daily_gain) + ' a day.' : '') + (fo.gaps && fo.gaps.length ? ' ' + fo.gaps.length + ' gaps in the counts (never filled).' : '')));
  if (meas.length){
    var t = el('table', null, el('tr', null, el('th', {text: 'Post'}), el('th', {text: 'Date'}), el('th', {cls: 'num', text: 'Views'}), el('th', {cls: 'num', text: 'Gain in 72 h'}), el('th', {cls: 'num', text: 'Above usual'}), el('th', {text: 'Level'})));
    meas.forEach(function(q){ t.appendChild(el('tr', null, el('td', null, postLink(q.id)), el('td', {text: date(q.at)}), el('td', {cls: 'num', text: num(q.views)}), el('td', {cls: 'num', text: num(q.f.gain_72h)}), el('td', {cls: 'num', text: num(q.f.excess_72h)}), el('td', null, chip('MEASURED'), q.f.level))); });
    p.appendChild(t);
    p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'The gain in the 72 hours after each post, split between posts that ran at the same time by their views. "Above usual" takes off the account\'s usual daily pace.'}));
  }
  if (est.length){
    var nl = 0, nm = 0; (D.posts || []).forEach(function(q){ if (q.f && q.f.level === 'estimated'){ if (q.f.label === 'likely brought followers') nl++; else if (q.f.label === 'may have brought followers') nm++; } });
    p.appendChild(el('div', {cls: 'small', style: 'margin:4px 0 6px'}, chip('INFERRED'), nl || nm ? (nl + ' posts likely brought followers, ' + nm + ' may have. The ten highest scores:') : 'No post shows a clear sign of bringing followers. The ten highest scores, for the record:'));
    var t2 = el('table', {style: 'margin-top:10px'}, el('tr', null, el('th', {text: 'Post'}), el('th', {text: 'Date'}), el('th', {cls: 'num', text: 'Views'}), el('th', {cls: 'num', text: 'Score'}), el('th', {text: 'Reading'}), el('th', {text: 'Signals'})));
    est.forEach(function(q){ var sg = q.f.signals || {}; t2.appendChild(el('tr', null, el('td', null, postLink(q.id)), el('td', {text: date(q.at)}), el('td', {cls: 'num', text: num(q.views)}), el('td', {cls: 'num', text: q.f.score == null ? '—' : q.f.score.toFixed(2)}),
      el('td', null, chip('INFERRED'), q.f.label || 'no clear sign'), el('td', {cls: 'small muted', text: Object.keys(sg).map(function(k){ return k.replace(/_/g, ' ') + ' ' + sg[k].toFixed(2); }).join(' · ')}))); });
    p.appendChild(t2);
    p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'Estimated: a score from signals that go with follows (reach past the follower count, outlier size, share and save rates against the account\'s median, comments from new followers, a raised baseline after, a part 2 that held). Written as "likely", never as a count.'}));
  }
  if (!meas.length && !est.length) p.appendChild(el('div', {cls: 'empty', text: 'Nothing to say: no follower counts and no scored posts.'}));
})();

/* ---------- deep read */
(function(){
  var V = D.videos || {}, ids = Object.keys(V);
  var nRead = ids.filter(function(id){ return (V[id].notes || {}).read === true; }).length;
  var s = section('deep-read', nRead ? 'The videos, watched' : 'The videos (none watched)', nRead ? 'The outliers, some ordinary posts and the flops, so that every "this is why it works" is tested against posts where it did not.' : 'No video could be watched in this run; nothing below describes a video.');
  if (!ids.length){ s.appendChild(el('div', {cls: 'panel empty', text: 'No video was read in this run.'})); return; }
  var dr = A.deep_read || {}, role = {};
  (dr.outliers || []).forEach(function(i){ role[i] = 'outlier'; }); (dr.ordinary || []).forEach(function(i){ role[i] = 'ordinary'; }); (dr.flops || []).forEach(function(i){ role[i] = 'flop'; });
  var cards = el('div', {cls: 'cards'}); s.appendChild(cards);
  ids.sort(function(a, b){ var o = {outlier: 0, ordinary: 1, flop: 2}; return (o[role[a]] == null ? 3 : o[role[a]]) - (o[role[b]] == null ? 3 : o[role[b]]); }).forEach(function(id){
    var v = V[id], n = v.notes || {}, pr = v.probe || {}, m = pr.measured || {}, q = POSTS[id] || {}, se = n.seen || {};
    var body = el('div', {cls: 'body'},
      el('div', {cls: 'row'}, el('strong', null, postLink(id)), el('span', {cls: 'pill', text: (role[id] || 'read') + ' · ' + xr(q.ratio)}), el('span', {cls: 'pill', text: num(q.views) + ' views'})));
    if (n.read === true){
      body.appendChild(el('div', {cls: 'kv'},
        el('span', {cls: 'k', text: 'Length'}), el('span', null, chip('MEASURED'), (m.length_s != null ? m.length_s.toFixed(1) + ' s' : '—') + ' · ' + (m.cuts_per_10s != null ? m.cuts_per_10s + ' cuts per 10 s' : '') + (m.words_per_minute != null ? ' · ' + m.words_per_minute + ' words/min' : '')),
        row('Hook', se.hook), row('First frame', se.first_frame), row('On screen', se.text_on_screen), row('Sound', se.sound), row('The turn', se.turn), row('The ask', se.ask)));
    } else {
      body.appendChild(el('div', {cls: 'empty', text: 'Not read: ' + (n.not_read_reason || pr.not_read_reason || 'the frames were not looked at yet')}));
    }
    cards.appendChild(el('div', {cls: 'card'}, pr.sheet_first ? el('img', {cls: 'sheet', src: pr.sheet_first, alt: 'The first three seconds'}) : (q.cover ? el('img', {cls: 'cover', src: q.cover, alt: ''}) : null), body));
    function row(k, val){ var t = val && typeof val === 'object' ? (val.text || '') + (val.at != null ? ' (' + val.at + ' s)' : '') : (val || ''); return [el('span', {cls: 'k', text: k}), el('span', null, chip('SEEN'), t || '—')]; }
  });
})();

/* ---------- comments */
(function(){
  var s = section('comments', 'How the comments are run', C && C.status === 'ok' ? (C.comments_read + ' comments read on ' + C.posts_read + ' posts' + (C.replies_read === true ? ', replies included' : C.replies_read === false ? ', replies not read' : '') + '.') : null);
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (!C || C.status !== 'ok'){ p.appendChild(el('div', {cls: 'empty', text: (C && C.note) || 'The comments were not read.'})); return; }
  var cc = C.creator_comment || {}, pin = C.pinned || {}, rb = C.replies_by_creator || {}, cw = C.comment_a_word || {}, fc = C.follow_comments || {};
  var t = el('table', null,
    tr('The creator\'s own comment', cc.posts_with_own_comment == null ? 'unknown: ' + (cc.note || '') : cc.posts_with_own_comment + ' of ' + cc.of_posts + ' posts' + (cc.came_first_known ? ' · first on ' + cc.came_first + ' of ' + cc.came_first_known : '') + (cc.within_10_min_known ? ' · within 10 min on ' + cc.within_10_min + ' of ' + cc.within_10_min_known : ''), cc.evidence),
    tr('Pinned comment', pin.posts_with_pinned == null ? 'unknown: ' + (pin.note || '') : pin.posts_with_pinned + ' of ' + pin.of_posts + ' posts (' + pin.by_creator + ' by the creator, ' + pin.by_audience + ' by the audience)', pin.evidence),
    tr('"Comment a word"', cw.posts_asking + ' of ' + cw.of_posts + ' captions ask for a word' + ((cw.echo || []).length ? ' · echoed on ' + cw.echo.length + ' posts (top: "' + cw.echo[0].word + '", ' + pct(cw.echo[0].share) + ' of comments)' : ''), cw.evidence),
    tr('Replies by the creator', rb.rate == null ? (rb.note || 'unknown') : pct(rb.rate) + ' of audience comments answered (' + rb.answered + ' of ' + rb.of_top_level + ')' + (rb.median_minutes_to_reply != null ? ' · median ' + rb.median_minutes_to_reply + ' min to answer' : '') + (rb.note ? ' · ' + rb.note : ''), rb.evidence),
    tr('Comments the creator hearted', !C.hearted || C.hearted.count == null ? 'unknown' + (C.hearted && C.hearted.note ? ': ' + C.hearted.note : '') : C.hearted.count + ' of ' + C.hearted.of_audience_comments + ' audience comments, on ' + C.hearted.posts_with_hearts + ' posts', C.hearted && C.hearted.evidence),
    tr('New followers say so', fc.count + ' comments on ' + fc.posts + ' posts', fc.evidence),
    tr('Questions · objections', C.questions_count + ' · ' + C.objections_count, 'MEASURED'));
  p.appendChild(t);
  if (C.times_exact && C.times_exact.note) p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'Note: ' + C.times_exact.note + '.'}));
  function tr(k, v, ev){ return el('tr', null, el('td', {text: k, style: 'width:34%'}), el('td', null, chip(ev), v)); }
  (F.comment_tactics || []).forEach(function(c){ p.appendChild(claim(c)); });
  var q = el('div', {cls: 'grid2', style: 'margin-top:12px'});
  q.appendChild(el('div', null, el('h3', {text: 'What new followers write'}), (fc.examples || []).slice(0, 6).map(quote)));
  q.appendChild(el('div', null, el('h3', {text: 'Questions and objections, in their words (found by pattern)'}), (C.questions || []).slice(0, 4).concat((C.objections || []).slice(0, 3)).map(quote)));
  p.appendChild(q);
  function quote(c){ return el('div', {cls: 'quote'}, chip('SEEN'), '"' + c.text + '"', el('span', {cls: 'muted small'}, ' · ', postLink(c.post_id), c.likes != null ? ' · ' + num(c.likes) + ' likes' : '')); }
})();

/* ---------- plays */
(function(){
  var plays = F.plays || [];
  var s = section('plays', 'The playbook', plays.length ? plays.length + ' plays, each with its evidence, the effort and what not to copy.' : null);
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (!plays.length){ p.appendChild(el('div', {cls: 'empty', text: 'No plays written.'})); return; }
  plays.forEach(function(pl, i){
    var pr = el('div', {cls: 'prompt', text: pl.prompt || ''});
    p.appendChild(el('div', {cls: 'play'},
      el('div', {cls: 'row'}, el('h3', {text: (i + 1) + '. ' + pl.title, style: 'margin:0'}), el('span', {cls: 'pill', text: 'effort ' + pl.effort}), pl.first_result ? el('span', {cls: 'pill', text: 'first result: ' + pl.first_result}) : null),
      claim({evidence: pl.evidence, text: pl.text || pl.what || '', basis: pl.basis, posts: pl.posts, links: pl.links, from: pl.from}),
      pl.dont_copy ? el('div', {cls: 'small'}, el('strong', {text: 'Do not copy: '}), pl.dont_copy) : null,
      pr,
      el('button', {cls: 'btn primary', type: 'button', text: 'Copy prompt', onclick: function(e){ copy(pl.prompt || '', e.target); }})));
  });
  function copy(text, b){
    function ok(){ b.textContent = 'Copied'; setTimeout(function(){ b.textContent = 'Copy prompt'; }, 1400); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback); else fallback();
    function fallback(){ var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); ok(); } catch (e) {} document.body.removeChild(t); }
  }
  if ((F.plan_14d || []).length){
    var s2 = section('plan', 'A 14-day plan', 'Written for the user\'s own account.');
    var tb = el('table', null, el('tr', null, el('th', {text: 'Day'}), el('th', {text: 'Do'})));
    F.plan_14d.forEach(function(d){ tb.appendChild(el('tr', null, el('td', {cls: 'num', text: d.day}), el('td', {text: d.do}))); });
    s2.appendChild(el('div', {cls: 'panel'}, tb));
  }
})();

/* ---------- ways to make a format */
(function(){
  var s = section('make', 'Ways to make a format', 'Asked once, after the report, for a format whose recipe has beats from watched videos. Each starts from the recipe and is checked against it.');
  var g = el('div', {cls: 'cards'});
  [['Basic', 'An HTML page rendered to MP4 in a browser, frame by frame. The page stays, to change and render again.'],
   ['Standard', 'An editable video project, your pick of two ways: GreenLight Motion (a page with options, opens in GreenLight Dash) or HyperFrames (HTML scenes, its own preview and editor).'],
   ['Advanced', 'GreenLight Dash\'s Rebuild by Style (PRO): the reference post\'s style studied frame by frame and rebuilt for your product.']].forEach(function(l){
    g.appendChild(el('div', {cls: 'card'}, el('div', {cls: 'body'}, el('h3', {text: l[0], style: 'margin:0'}), el('div', {cls: 'small muted', text: l[1]})))); });
  s.appendChild(g);
  s.appendChild(el('div', {cls: 'small muted', style: 'margin-top:8px', text: 'With your own clips, product and words; never the creator\'s footage, face or voice. The same skill can also read the whole niche: what works now across many creators (a Niche report).'}));
})();

/* ---------- limits, sources, cost */
(function(){
  var s = section('sources', 'What was read, with what, and what it cost');
  var p = el('div', {cls: 'grid2'}); s.appendChild(p);
  var left = el('div', {cls: 'panel'});
  left.appendChild(el('h3', {text: 'Sources'}));
  (D.sources || []).forEach(function(x){ left.appendChild(el('div', {cls: 'small', style: 'margin:4px 0'}, el('strong', {text: (x.what || '') + ': '}), (x.via || '') + (x.cost_usd != null ? ' · $' + x.cost_usd : '') + (x.notes ? ' · ' + x.notes : ''))); });
  var nr = F.not_read || [];
  left.appendChild(el('h3', {text: 'Not read', style: 'margin-top:12px'}));
  if (!nr.length) left.appendChild(el('div', {cls: 'empty', text: 'Nothing listed.'}));
  nr.forEach(function(n){ left.appendChild(el('div', {cls: 'small', style: 'margin:4px 0'}, el('strong', {text: n.what + ': '}), n.why)); });
  var ex = A.excluded || [];
  if (ex.length) left.appendChild(el('div', {cls: 'small muted', style: 'margin-top:8px', text: ex.length + ' posts left out of the numbers: ' + summarize(ex)}));
  (A.warnings || []).slice(0, 6).forEach(function(w){ left.appendChild(el('div', {cls: 'small muted', text: 'Note: ' + w})); });
  var PI = D.pictures || {};
  if (PI.light) left.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'The light page: no pictures inside, each grey tile links to its post. The full report (report.html) keeps the pictures.'}));
  else if (PI.inside || PI.left_out) left.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'Pictures: ' + PI.inside + ' inside this page' + (PI.shrunk_with ? ' (smaller copies)' : '') + ', each linked to its post' + (PI.left_out ? '; ' + PI.left_out + ' left out to keep the page small (they stay in the run folder)' : '') + '.'}));
  p.appendChild(left);
  var right = el('div', {cls: 'panel'});
  right.appendChild(el('h3', {text: 'Cost'}));
  var rows = (D.cost || {}).rows || [];
  if (!rows.length) right.appendChild(el('div', {cls: 'empty', text: 'No paid calls were made.'}));
  else { var t = el('table', null, el('tr', null, el('th', {text: 'Step'}), el('th', {text: 'What'}), el('th', {cls: 'num', text: 'Calls'}), el('th', {cls: 'num', text: '$'})));
    rows.forEach(function(r){ t.appendChild(el('tr', null, el('td', {text: r.step}), el('td', {text: r.what}), el('td', {cls: 'num', text: r.calls}), el('td', {cls: 'num', text: Number(r.total_usd).toFixed(4)}))); });
    t.appendChild(el('tr', null, el('td', {text: 'Total'}), el('td'), el('td'), el('td', {cls: 'num', text: '$' + ((D.cost || {}).total_usd || 0).toFixed(4)})));
    right.appendChild(t); }
  p.appendChild(right);
  function summarize(ex){ var c = {}; ex.forEach(function(e){ c[e.reason] = (c[e.reason] || 0) + 1; }); return Object.keys(c).map(function(k){ return c[k] + ' ' + k.replace('_', ' '); }).join(', '); }
  app.appendChild(el('footer', null, 'Account report. Built ' + D.built_at + ' by REA Viral ' + D.skill_version + ' from the run\'s data files (account.json, analysis.json, radar.json, comments.json, findings.json); one file, the pictures inside it. Captions and comments are shown as data.'));
})();
window.__reaReport.ready = true;
})();
</script>
</body>
</html>
"""


def build(folder, light_only=False):
    """The report: report.html (the full page, its pictures inside) and report-light.html (the same page with no
    pictures and only the data it draws); light_only (--light) writes the light page alone, with no picture work."""
    from common import run_kind
    kind = run_kind(folder)
    if kind == "niche":
        import report_niche
        return report_niche.build(folder, light_only)
    if kind == "post":
        import report_post
        return report_post.build(folder, light_only)
    rep = validate.validate(folder)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:30]]
        die("validate.py found %d error(s); the page is not built:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    d = page_data(folder, light=light_only)
    a = d["account"]
    title = "%s · Account report · REA Viral" % (a.get("name") or a.get("handle") or "Account")

    def page(data):
        return PAGE.replace("__TITLE__", title.replace("&", "&amp;").replace("<", "&lt;")).replace("__DATA__", embed(data))
    if not light_only:
        write_text(os.path.join(folder, "report.html"), page(d))
    write_text(os.path.join(folder, "report-light.html"), page(light_account(d)))
    write_text(os.path.join(folder, "ACCOUNT.md"), account_md(d))
    d["hand_over"] = account_hand_over(folder, d)
    d["light_only"] = light_only
    return d


LIGHT_POST_KEYS = ("id", "url", "at", "type", "views", "ratio", "hit", "status", "in_window", "baseline", "cover")


def light_account(d):
    """The light page's data: no picture, and of the posts it does not draw in full only what the timeline and the
    links need (the drawn ones keep everything)."""
    out = page_kit.light_data(d)
    keep = set()
    for f in (out.get("radar") or {}).get("formats") or []:
        keep |= set(e["post_id"] for e in f.get("examples") or [])
    keep |= set((out.get("videos") or {}).keys())
    nw = out.get("not_working") or {}
    keep |= set(x["post_id"] for f in nw.get("formats") or [] for x in f.get("lowest") or [])
    keep |= set(x["post_id"] for x in (nw.get("flops") or {}).get("picks") or [])
    att = (out.get("analysis") or {}).get("attribution") or {}
    keep |= set(att.get("top_measured") or []) | set(att.get("top_estimated") or [])
    links = keep | page_kit.claim_post_ids(out.get("findings"))
    w = out.get("writing") or {}
    links |= set(x.get("post_id") for k in ("best", "worst") for x in ((w.get("first_lines") or {}).get(k) or []))
    links |= set(x.get("post_id") for x in w.get("on_screen") or [])
    links |= set(x.get("post_id") for x in ((w.get("asks") or {}).get("examples") or []))
    posts = []
    for p in out.get("posts") or []:
        if p["id"] in keep:
            posts.append(p)
        elif p.get("in_window") or p["id"] in links:     # a dot on the timeline, or a link in a claim or a line
            x = dict((k, p.get(k)) for k in LIGHT_POST_KEYS)
            x["f"] = {"level": (p.get("f") or {}).get("level"), "label": (p.get("f") or {}).get("label")}
            posts.append(x)
    out["posts"] = posts
    out["writing"] = page_kit.light_writing(out.get("writing"))
    for r in (out.get("recipes") or {}).values():
        r.pop("text", None)
    for f in (out.get("radar") or {}).get("formats") or []:
        f.pop("post_ids", None)                          # not drawn: radar.json keeps them
    if (out.get("radar") or {}).get("unformatted"):
        out["radar"]["unformatted"].pop("post_ids", None)
    fo = (out.get("analysis") or {}).get("followers") or {}
    if len(fo.get("series") or []) > 160:                # the followers line: 160 points draw the same line
        s = fo["series"]
        step = len(s) / 160.0
        fo["series"] = [s[int(i * step)] for i in range(160)] + [s[-1]]
    com = out.get("comments")
    if com:
        com.pop("top_comments", None)
        com["questions"] = (com.get("questions") or [])[:4]
        com["objections"] = (com.get("objections") or [])[:3]
        if isinstance(com.get("follow_comments"), dict):
            com["follow_comments"]["examples"] = (com["follow_comments"].get("examples") or [])[:6]
    return out


def strongest_format(fm):
    """The format worth offering: Scale it first, then Underused, 6 scored posts or more, the best lift first."""
    order = {"scale_it": 0, "underused": 1}
    best = [f for f in fm or [] if f.get("quadrant") in order and not f.get("few_posts")]
    best.sort(key=lambda f: (order[f["quadrant"]], -(f.get("lift") or 0)))
    return best[0] if best else None


def account_hand_over(folder, d):
    """report_record.json and radar_rows.json for a planner connector (hand_over.py): the Account report's record,
    and its strongest format as one row."""
    a, fi, r = d["account"], d["findings"] or {}, d["radar"] or {}
    an = read_json(os.path.join(folder, "analysis.json"))
    P = dict((p["post_id"], p) for p in an.get("posts") or [])
    net, handle = a.get("network"), a.get("handle")
    best = strongest_format(r.get("formats"))
    rows, note = [], None
    if best and best.get("examples"):
        ex = P.get(best["examples"][0]["post_id"]) or {}
        face = {"url": ex.get("url"), "network": net, "post_id": ex.get("post_id"), "account": handle,
                "caption": ex.get("caption"),
                "numbers": hand_over.numbers_of(ex, a.get("followers"), a.get("read_at"))}
        rows.append(hand_over.format_row(
            hand_over.format_key("%s-%s" % (net, handle), best["id"]), best,
            ((d.get("recipes") or {}).get(best["id"]) or {}).get("recipe"), face, creators=1,
            trend=hand_over.trend_of(best.get("direction_label")), proof=[e.get("url") for e in best.get("examples") or []]))
        note = "The account's strongest format (%s), for the user's saved formats." % best["quadrant_name"]
    else:
        note = ("No format to offer: none sits in Scale it or Underused with 6 scored posts or more."
                if r.get("status") == "ok" else "No format to offer: %s" % (r.get("status_note") or "no formats measured"))
    fallback = brief.measured_answer("account", d)      # never empty: findings.json may have no headline
    c = d["analysis"].get("counts") or {}
    keys = dict((best["id"], rows[0]["key"]) for _ in rows[:1]) if best and rows else {}
    br = brief.account(folder, d, keys, None)
    try:
        picture = read_json(os.path.join(folder, "account.json")).get("picture_file")
    except (OSError, ValueError):
        picture = None
    cover = page_kit.write_cover(folder, picture)
    rec, _ = hand_over.write(folder, "account", {
        "title": "@%s · %s" % (handle, hand_over.NETWORK_NAMES.get(net, net)),
        "subject": {"network": net, "handle": handle, "url": a.get("url")},
        "summary": hand_over.summary_text(fi.get("headline"), fi.get("did_not_work"), fallback),
        "read": {"posts": c.get("posts_total"), "creators": 1},
        "sources": d.get("sources"), "cost": d.get("cost"),
        "page_path": os.path.join(folder, "report.html"), "run_name": os.path.basename(os.path.abspath(folder)),
    }, rows, note, brief=br, cover=cover)
    return {"record": rec, "rows": len(rows), "brief": br}


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    from common import run_kind
    kind = run_kind(folder)
    d = build(folder, light_only="--light" in argv)
    page = os.path.join(folder, "report.html")
    if kind == "niche":
        print("The Niche report: report.html and NICHE.md written (%d creators, %d posts, %d formats, %d of them formats "
              "of the niche, %d on the watchlist)" % (d["trends"]["counts"]["creators"], len(d["posts"]), len(d["formats"]),
                                                     sum(1 for f in d["formats"] if f.get("niche_format")), len(d["watchlist"])))
    elif kind == "post":
        print("The Post report: report.html and POST.md written (the post run's short page)")
    else:
        read = sum(1 for v in d["videos"].values() if (v.get("notes") or {}).get("read") is True)
        cut = sum(1 for v in d["videos"].values() if (v.get("probe") or {}).get("read") is True)
        print("The Account report: report.html and ACCOUNT.md written (%d posts, %d formats, %d under its usual or "
              "weakening, %d videos cut, %d looked at, %d plays)" % (
                  len(d["posts"]), len((d["radar"] or {}).get("formats") or []), len(d["not_working"]["formats"]), cut,
                  read, len((d["findings"] or {}).get("plays") or [])))
    if d.get("light_only"):
        print("--light: report.html was not rebuilt" + ("" if os.path.exists(page) else " (there is none yet)"))
    else:
        print(page_kit.size_line(page, d.get("pictures")))
        for x in (d.get("pictures") or {}).get("left") or []:
            print("  left out of the page: %s (%s)" % (x["file"], x["why"]))
    print(page_kit.light_line(os.path.join(folder, "report-light.html")))
    ho = d.get("hand_over") or {}
    cv = (ho.get("record") or {}).get("cover")
    print("report-cover%s: %s" % (os.path.splitext(cv["path"])[1], page_kit.kb(cv["size"])) if cv else
          "no cover: the run has no picture of its own (account.json picture_file, or the post's cover)")
    b = ho.get("brief") or {}
    print("report_record.json (%s), brief.json (%d worked, %d did not work) and radar_rows.json (%d format%s) written "
          "for a planner connector" % (ho.get("record", {}).get("report", {}).get("kind"), len(b.get("worked") or []),
                                       len(b.get("not_worked") or []), ho.get("rows", 0), "" if ho.get("rows") == 1 else "s"))
    print("open: file://" + os.path.abspath(page))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
