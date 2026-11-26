"""The niche hand-over: the Niche report (report.html: the formats of the niche across creators, the gallery of
formats, what did not work, the trends, the hooks, who to watch) and NICHE.md for agents, plus the planner files
(report_record.json; radar_rows.json, one row per format of the niche). Called by build_report.py on a niche folder;
it reads only the data files the scripts wrote.

Refuses to build while validate.py finds errors or while trends.json, radar.json or writing.json were made from older
inputs (or before a creator folder was added or removed). No other creator's video is embedded or re-hosted: the
gallery shows saved covers and frame sheets as small pictures inside the page, each linked to the original post.
"""
import os
import re

from common import (SKILL_VERSION, die, iso, niche_input_files, now_utc, read_csv, read_json, upgrade_radar, write_text)
from analyze import input_fingerprint
import brief
import hand_over
import page_kit
import trends as trends_mod


def _load(folder, name):
    p = os.path.join(folder, name)
    return read_json(p) if os.path.exists(p) else None


def _stale(folder, doc, name, script):
    if doc is None:
        return None
    was = doc.get("inputs") or {}
    now_files = niche_input_files(folder)
    have = input_fingerprint(folder, tuple(set(was.keys()) | set(now_files)))
    changed = sorted(k for k in set(was) | set(now_files) if have.get(k) != was.get(k))
    if changed:
        return "%s was made before %s changed: run %s again" % (name, ", ".join(changed[:6]) + (" ..." if len(changed) > 6 else ""), script)
    return None


def _cost(folder):
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


def _hooks_view(folder):
    p = os.path.join(folder, "hooks.md")
    if not os.path.exists(p):
        return None
    text = open(p, encoding="utf-8").read()
    m = re.search(r"```json rea-voice\s*\n(.*?)\n```", text, re.S)
    rec = None
    if m:
        import json
        try:
            rec = json.loads(m.group(1))
        except ValueError:
            rec = None
    prose = re.sub(r"```json rea-voice\s*\n.*?\n```", "", text, flags=re.S)
    prose = re.sub(r"<!-- rea:measured:start -->.*?<!-- rea:measured:end -->", "", prose, flags=re.S)
    prose = re.sub(r"^# .*\n", "", prose.strip())
    return {"file": "hooks.md", "rules": (rec or {}).get("rules"), "text": prose.strip()[:8000]}


def _recipes(folder, radar):
    import json
    out = {}
    for f in (radar or {}).get("formats") or []:
        p = os.path.join(folder, "formats", f["id"] + ".md")
        if not os.path.exists(p):
            continue
        m = re.search(r"```json rea-recipe\s*\n(.*?)\n```", open(p, encoding="utf-8").read(), re.S)
        rec = None
        if m:
            try:
                rec = json.loads(m.group(1))
            except ValueError:
                rec = None
        out[f["id"]] = {"file": "formats/%s.md" % f["id"],
                        "recipe": {k: (rec or {}).get(k) for k in ("hook_pattern", "beats", "caption_style", "sound", "ask", "length_s")}}
    return out


def _not_working(folder, tr, radar, wr):
    """What did not work across the niche (MEASURED, and SEEN from the watched flops): the formats of the niche under
    their creators' usual or fading, the flops, what sinks in the words across 3 creators or more. "Not enough data"
    where that is the truth; never a cause from one post."""
    P = dict((p["post_id"], p) for p in tr["posts"])
    out = {"status": tr.get("status"), "note": None}
    if tr.get("status") != "ok":
        out["note"] = "Not enough data: %s" % (tr.get("status_note") or tr.get("status"))
    r = radar or {}
    names = dict((f["id"], f.get("name")) for f in r.get("formats") or [])
    formats, fnote = [], None
    if r.get("status") != "ok":
        fnote = "Not enough data: %s" % (r.get("status_note") or "no formats measured yet (run radar.py)")
    else:
        for f in r.get("formats") or []:
            if not f.get("niche_format") or f.get("lift") is None:
                continue
            under, fading = f["lift"] < 1.0, f.get("direction_label") == "fading"
            if not (under or fading):
                continue
            low = list(reversed(f.get("proof") or []))[:3]
            formats.append({
                "id": f["id"], "name": f.get("name"), "quadrant": f["quadrant"], "quadrant_name": f["quadrant_name"],
                "creators": f.get("creators"), "creators_share": f.get("creators_share"), "lift": f["lift"],
                "posts_scored": f.get("posts_scored"), "direction": f.get("direction"),
                "direction_label": f.get("direction_label"), "few_posts": bool(f.get("few_posts")), "under": under,
                "fading": fading, "lowest": [{"post_id": x["post_id"], "account": x.get("account"), "ratio": x.get("ratio")}
                                             for x in low],
                "evidence": "MEASURED", "from": "radar.json#formats.%s" % f["id"]})
        formats.sort(key=lambda x: x["lift"])
        if not formats:
            fnote = "No format of the niche sits under its creators' usual or fades."
    out["formats"], out["formats_note"] = formats, fnote
    flop_ratio = (tr.get("rules") or {}).get("flop_ratio", 0.5)
    flops = [p for p in tr["posts"] if p["status"] == "scored" and p["ratio"] is not None and p["ratio"] <= flop_ratio]
    by = {}
    for p in flops:
        by[p.get("format")] = by.get(p.get("format"), 0) + 1
    picks = []
    for i in (tr.get("deep_read") or {}).get("flops") or []:
        p = P.get(i) or {}
        n = {}
        np_ = os.path.join(folder, "accounts", p.get("creator") or "", "videos", i, "notes.json")
        if os.path.exists(np_):
            try:
                n = read_json(np_)
            except ValueError:
                n = {}
        seen = (n.get("seen") or {}) if n.get("read") is True else {}

        def said(v):
            return (v.get("text") if isinstance(v, dict) else v) or None
        picks.append({"post_id": i, "account": p.get("account"), "ratio": p.get("ratio"),
                      "format": names.get(p.get("format")), "read": n.get("read"), "not_read_reason": n.get("not_read_reason"),
                      "hook": said(seen.get("hook")), "turn": said(seen.get("turn")), "ask": said(seen.get("ask"))})
    out["flops"] = {
        "count": len(flops), "of_scored": (tr.get("counts") or {}).get("scored") or 0, "flop_ratio": flop_ratio,
        "creators": len(set(p["creator"] for p in flops)),
        "by_format": [{"format": k, "name": names.get(k) if k else None, "flops": v}
                      for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0] or "~"))],
        "picks": picks, "evidence": "MEASURED", "from": "trends.json#posts",
        "note": None if flops else "No post sat at half its own creator's usual or under in the window."}
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
            words["note"] = "Nothing in the words sinks clearly across 3 creators or more."
            leads = [f for f in wr.get("features") or [] if f.get("verdict") == "no clear difference"
                     and f.get("vs_usual") is not None and f["vs_usual"] <= 0.8 and (f.get("with") or {}).get("posts", 0) >= 6]
            leads.sort(key=lambda f: f["vs_usual"])
            words["leads"] = [{"id": f["id"], "label": f["label"], "with": f["with"], "without": f["without"],
                               "chance": f.get("chance"), "from": "writing.json#features.%s" % f["id"]} for f in leads[:3]]
        words["worst"] = ((wr.get("first_lines") or {}).get("worst") or [])[:3]
    out["words"] = words
    return out


def page_data(folder, light=False):
    import build_report
    import topic_check
    niche = read_json(os.path.join(folder, "niche.json"))
    tr = _load(folder, "trends.json")
    if tr is None:
        die("no trends.json: run trends.py (or radar.py) first", 1)
    radar = upgrade_radar(_load(folder, "radar.json"))
    wr = _load(folder, "writing.json")
    tc = _load(folder, "topic_check.json")
    problems = [p for p in (_stale(folder, tr, "trends.json", "trends.py"), _stale(folder, radar, "radar.json", "radar.py"),
                            _stale(folder, wr, "writing.json", "text_probe.py"), topic_check.stale(folder)) if p]
    if problems:
        die("\n".join(problems), 1)
    findings = _load(folder, "findings.json") or {}
    sheets = {}
    posts = []
    for p in tr["posts"]:
        sheet = page_kit.existing(folder, "accounts/%s/videos/%s/first.jpg" % (p["creator"], p["post_id"]))
        if sheet:
            sheets[p["post_id"]] = sheet
        posts.append({"id": p["post_id"], "url": p["url"], "account": p["account"], "creator": p["creator"],
                      "at": p["published_at"], "views": p["views"], "ratio": p["ratio"], "ratio_so_far": p["ratio_so_far"],
                      "vpf": p["views_per_follower"], "baseline": p["baseline"], "baseline_n": p["baseline_n"],
                      "status": p["status"], "fresh": bool(p.get("fresh") or p["status"] == "fresh"),
                      "fresh_label": p.get("fresh_label"),
                      "basis": p["basis"], "format": p.get("format"), "rank": p.get("rank"),
                      "lead": p.get("lead"), "cover": page_kit.existing(folder, p.get("cover_file")),
                      "caption": (p.get("caption") or "")[:200]})
    formats = []
    for f in (radar or {}).get("formats") or []:
        formats.append(dict((k, f.get(k)) for k in (
            "id", "name", "container", "basis", "recipe", "posts_total", "posts_scored", "creators", "creators_share",
            "creators_all", "by_creator", "lift", "lift_posts", "hit_rate", "creators_hit", "direction", "direction_label",
            "usage_direction", "halves", "first_seen", "new", "age_days", "weaker_basis_posts", "too_new_posts", "effort",
            "niche_format", "scope_status", "few_posts", "quadrant", "quadrant_name", "examples", "proof",
            "length_s_median", "videos_read")))
    nw = _not_working(folder, tr, radar, wr)
    # The pictures go inside the page (one file), the gallery's proof posts first: a cover as the picture (its frame
    # sheet linked beside it while the page sits in its run folder), or the frame sheet when there is no cover.
    pics = page_kit.Pictures(folder, light=light)
    by_id = dict((p["id"], p) for p in posts)
    covers, drawn_sheets = {}, {}
    for f in formats:
        for e in f.get("examples") or []:
            pid = e["post_id"]
            if pid in covers or pid not in by_id:
                continue
            covers[pid] = pics.get(by_id[pid]["cover"], "cover")
            if not covers[pid] and sheets.get(pid):
                drawn_sheets[pid] = pics.get(sheets[pid], "sheet")
    for x in [y for f in nw["formats"] for y in f["lowest"]] + nw["flops"]["picks"]:
        if x["post_id"] not in covers and x["post_id"] in by_id:
            covers[x["post_id"]] = pics.get(by_id[x["post_id"]]["cover"], "cover")
    for p in posts:   # the Study view's "every post" tiles, last, while the budget lasts
        if p.get("format") and p["id"] not in covers and p.get("status") != "baseline_only":
            covers[p["id"]] = pics.get(p["cover"], "cover", optional=True)
    for p in posts:
        p["cover"] = covers.get(p["id"])
    sheets = dict((pid, (drawn_sheets.get(pid) if not covers.get(pid) else s)) for pid, s in sheets.items()
                  if pid in covers)
    sheets = dict((k, v) for k, v in sheets.items() if v)
    return {
        "skill_version": SKILL_VERSION,
        "built_at": iso(now_utc()),
        "niche": dict((k, niche.get(k)) for k in ("name", "slug", "question", "words", "tags", "seed_accounts", "networks",
                                                  "read_at", "window", "caps", "spend_ceiling_usd", "user")),
        "sources": niche.get("sources") or [],
        "trends": {k: tr.get(k) for k in ("status", "status_note", "counts", "window", "rules", "creators", "ranked",
                                          "leads_weaker_basis", "too_new", "warnings", "suspect_reach")},
        "radar": {k: (radar or {}).get(k) for k in ("status", "status_note", "rules", "axes", "creators_scored", "unformatted")},
        "formats": formats,
        "recipes": _recipes(folder, radar),
        "posts": posts,
        "sheets": sheets,
        "writing": build_report.writing_view(wr),
        "hooks": _hooks_view(folder),
        "watchlist": trends_mod.watchlist(tr, radar),
        "findings": findings,
        "topic_check": tc,
        "not_working": nw,
        "limits": page_kit.dedupe_limits(page_kit.run_limits("niche", folder), findings),
        "cost": _cost(folder),
        "pictures": pics.summary(),
    }


# ---------------------------------------------------------------------------------------------- NICHE.md

def _x(v):
    if v is None:
        return "-"
    return ("%.2f" % v).rstrip("0").rstrip(".") + "x"


def _pct(v):
    return "-" if v is None else "%d%%" % round(100 * v)


def claim_line(c):
    import build_report
    return build_report.claim_line(c)


def niche_md(d):
    n, t, fi = d["niche"], d["trends"], d["findings"] or {}
    fm = d["formats"]
    nw = d.get("not_working") or {}
    L = ["# %s: REA Viral, Niche report" % (n.get("name") or "A niche"), "",
         "For agents. Read Layer 0 for the answer, Layer 1 to find the part a question needs, Layer 2 for the detail. "
         "A trend here is a post that beat ITS OWN creator's usual (the median of that creator's other posts), never "
         "the biggest number; a format of the niche needs 3 creators or more. Labels: MEASURED (the scripts), SEEN "
         "(a frame, row or caption, linked), INFERRED (reasoned, basis written). Built %s by REA Viral %s." % (
             d["built_at"], d["skill_version"]), "", "## Layer 0: the answer", ""]
    if t.get("status") != "ok":
        L.append("- Status: %s. %s" % (t.get("status"), t.get("status_note") or ""))
    if fi.get("headline"):
        L.append("- " + claim_line(fi["headline"]))
    placed = [f for f in fm if f.get("niche_format")]
    order = {"scale_it": 0, "underused": 1, "overused": 2, "drop": 3}
    placed.sort(key=lambda f: (order.get(f["quadrant"], 9), -(f.get("lift") or 0)))
    for f in placed[:3]:
        L.append("- [MEASURED] %s: %s, %d creators, lift %s over each creator's own usual%s%s (radar.json#formats.%s)." % (
            f["name"], f["quadrant_name"], f["creators"], _x(f["lift"]),
            ", %s %s" % (f["direction_label"], _x(f["direction"])) if f.get("direction") is not None else "",
            ", new in the window" if f.get("new") else "", f["id"]))
    if not placed and fm:
        L.append("- [MEASURED] No format reached 3 creators: nothing here is a format of the niche yet (radar.json).")
    wr = d.get("writing") or {}
    strong = [f for f in (wr.get("features") or []) if f.get("claim_ok")]
    if strong:
        L.append("- [MEASURED] In the words, across creators: %s (writing.json)." % "; ".join(
            "%s %s (%d posts, %s)" % (f["label"], f["verdict"], f["with"]["posts"], _x(f["with"]["lift"])) for f in strong[:3]))
    if nw.get("formats"):
        f = nw["formats"][0]
        L.append("- [MEASURED] What did not work: %s (%s), %d creators, lift %s over each creator's own usual%s (%s)." % (
            f["name"], f["quadrant_name"], f["creators"], _x(f["lift"]),
            ", %s %s" % (f["direction_label"], _x(f["direction"])) if f.get("direction") is not None else "", f["from"]))
    elif nw.get("formats_note"):
        L.append("- [MEASURED] What did not work, in the formats: %s" % nw["formats_note"])
    for cl in (fi.get("did_not_work") or [])[:1]:
        L.append("- " + claim_line(cl))
    L += ["", "## Layer 1: where each answer is", "", "| Question | Short answer | Read |", "|---|---|---|"]
    c = t.get("counts") or {}
    L.append("| How much was read? | %s creators (%s with their own usual), %s posts, %s in the window, %s scored | trends.json#counts |" % (
        c.get("creators"), c.get("creators_scored"), c.get("posts_read"), c.get("in_window"), c.get("scored")))
    by = dict((p["id"], p) for p in d["posts"])
    top = [by[i] for i in (t.get("ranked") or [])[:5] if i in by]
    L.append("| Which posts beat their own creator's usual? | %s at 2x or more; top: %s | trends.csv |" % (
        c.get("hits"), "; ".join("%s @%s %s" % (p["id"], p["account"], _x(p["ratio"])) for p in top) or "none"))
    for q, words in (("scale_it", "Formats to make now (Scale it: many creators, lifting)"),
                     ("underused", "Early openings (Underused: few creators, lifting)"),
                     ("overused", "Used by many, lifting little (Overused)"), ("drop", "Drop (few creators, lifting little)")):
        names = [f["name"] + (" (few posts)" if f.get("few_posts") else "") + (" (fading)" if f.get("direction_label") == "fading" else "")
                 for f in placed if f["quadrant"] == q and not (q in ("scale_it", "underused") and f.get("direction_label") == "fading")]
        if names:
            L.append("| %s | %s | radar.json, formats/*.md |" % (words, "; ".join(names)))
    fad = [f["name"] for f in placed if f.get("direction_label") == "fading"]
    if fad:
        L.append("| Fading over the window (later half under the earlier) | %s | radar.json#formats.<id>.direction |" % "; ".join(fad))
    habits = [f for f in fm if not f.get("niche_format")]
    if habits:
        L.append("| Not formats of the niche (yet) | %s | radar.json |" % "; ".join(
            "%s (%s)" % (f["name"], f["scope_status"]) for f in habits))
    if strong:
        hooks_short = "; ".join("%s: %s" % (f["label"], f["verdict"]) for f in strong[:4])
    elif not wr:
        hooks_short = "not measured yet (run text_probe.py)"
    elif wr.get("status") != "ok":
        hooks_short = "status %s: %s" % (wr.get("status"), wr.get("status_note") or "")
    else:
        hooks_short = "nothing in the words lifts or sinks clearly across 3 creators or more"
    L.append("| What do the hits open with? | %s | writing.json, hooks.md |" % hooks_short)
    fl, wd = nw.get("flops") or {}, nw.get("words") or {}
    dnw = ["; ".join("%s %s" % (f["name"], _x(f["lift"])) + (" (fading)" if f.get("fading") else "") for f in nw.get("formats") or [])
           or (nw.get("formats_note") or "")]
    if fl and fl.get("note"):
        dnw.append(fl["note"].rstrip("."))
    elif fl:
        dnw.append("%d flops of %d scored posts, from %d creators" % (fl["count"], fl["of_scored"], fl["creators"]))
    dnw.append(("words that sink: " + "; ".join(s["label"] for s in wd["sinks"])) if wd.get("sinks") else
               (wd.get("note") or ""))
    L.append("| What did not work? | %s | radar.json, trends.json, writing.json, findings.json#did_not_work |" % (
        ". ".join(x for x in dnw if x).replace("|", "/")))
    wl = d.get("watchlist") or []
    L.append("| Who to watch? | %s | watchlist.csv |" % ("; ".join("@%s (%s)" % (r["handle"], r["why"]) for r in wl[:4]) or "nobody stood out"))
    tc = d.get("topic_check")
    if tc:
        L.append("| Topic check (still worth posting?) | %s (saturation %s, momentum %s, lateness %s) | topic_check.json, TOPIC.md |" % (
            (tc.get("verdict") or "").replace("|", "/"), (tc.get("saturation") or {}).get("level"),
            (tc.get("momentum") or {}).get("level"), (tc.get("lateness") or {}).get("band")))
    L.append("| What was not read? | %s | findings.json#not_read and this run's own lines below |" % (
        "; ".join([x["what"] for x in fi.get("not_read") or []] + [x["what"] for x in d.get("limits") or []]) or "nothing listed"))
    L.append("| A voice sheet? | None in a niche run: hooks.md holds the niche's hooks across creators. For one creator's voice "
             "sheet, run an account run (or words only) on that creator | hooks.md |")
    L.append("| What did it cost? | $%.4f | cost.csv |" % d["cost"]["total_usd"])
    L += ["", "## Layer 2: detail", ""]
    if fm:
        L += ["### Formats (MEASURED by radar.py; the grouping is the agent's, formats.json)", "",
              "| Format | Corner | Creators | Posts scored | Lift | Hit rate | Direction | First seen | Effort | Recipe |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for f in fm:
            L.append("| %s | %s | %d (%s) | %d | %s | %s | %s | %s%s | %s | %s |" % (
                f["name"], f["quadrant_name"], f["creators"], f["scope_status"], f["posts_scored"], _x(f["lift"]),
                _pct(f["hit_rate"]), ("%s %s" % (_x(f["direction"]), f["direction_label"])) if f.get("direction") is not None else "-",
                (f.get("first_seen") or "-")[:10], " (new)" if f.get("new") else "", f.get("effort"), f["recipe"]))
        L.append("")
    L += ["### The top trends (MEASURED by trends.py)", "", "| # | Post | Creator | Views | Its creator's usual | Ratio |",
          "|---|---|---|---|---|---|"]
    for p in [by[i] for i in (t.get("ranked") or [])[:15] if i in by]:
        L.append("| %s | [%s](%s) | @%s | %s | %s (from %s posts) | %s%s |" % (
            p["rank"], p["id"], p["url"], p["account"], p["views"],
            p["baseline"], p["baseline_n"], _x(p["ratio"]),
            " (fresh / still growing)" if p.get("fresh") else ""))
    if t.get("suspect_reach"):
        sr = t["suspect_reach"]
        L.append("")
        L.append("- [MEASURED] Outlier warning (%s): %d post(s) had views >= 1000x the creator's followers (top: %s). "
                 "Check before calling them a finding (trends.json#suspect_reach)." % (
                     sr.get("rule") or "", sr.get("count") or 0,
                     ", ".join("@%s %s (%s views)" % (x.get("account"), x.get("post_id"), x.get("views")) for x in (sr.get("posts") or [])[:3])))
    L.append("")
    L += ["### What did not work (MEASURED by the scripts; SEEN from the watched flops)", ""]
    if nw.get("note"):
        L.append("- " + nw["note"])
    for f in nw.get("formats") or []:
        L.append("- [MEASURED] %s (%s): %d creators, %d scored posts, lift %s%s%s; its lowest posts: %s (%s)." % (
            f["name"], f["quadrant_name"], f["creators"], f["posts_scored"] or 0, _x(f["lift"]),
            ", %s %s" % (f["direction_label"], _x(f["direction"])) if f.get("direction") is not None else "",
            "; few posts, not a finding on its own" if f.get("few_posts") else "",
            ", ".join("%s @%s %s" % (x["post_id"], x["account"], _x(x["ratio"])) for x in f["lowest"]), f["from"]))
    if not nw.get("formats") and nw.get("formats_note"):
        L.append("- Formats: " + nw["formats_note"])
    if fl and fl.get("note"):
        L.append("- [MEASURED] " + fl["note"] + " (trends.json#posts)")
    elif fl:
        L.append("- [MEASURED] Flops (%s their own creator's usual or under): %d of %d scored posts, from %d creators%s "
                 "(trends.json#posts)." % (_x(fl["flop_ratio"]), fl["count"], fl["of_scored"], fl["creators"],
                                          "" if not fl["by_format"] else "; " + ", ".join(
                                              "%d %s" % (b["flops"], b["name"] or "in no format") for b in fl["by_format"])))
    if fl and fl["picks"]:
        L.append("- The lowest posts the deep read picked to watch, of different creators:")
    if fl:
        for x in fl["picks"]:
            if x["read"] is True:
                L.append("  - [SEEN] %s @%s at %s: hook: %s; turn: %s. What a flop shows is not why it flopped." % (
                    x["post_id"], x["account"], _x(x["ratio"]), x["hook"] or "-", x["turn"] or "-"))
            else:
                L.append("  - %s @%s at %s: not watched%s." % (x["post_id"], x["account"], _x(x["ratio"]),
                                                              (": " + x["not_read_reason"]) if x.get("not_read_reason") else ""))
    for s in wd.get("sinks") or []:
        L.append("- [MEASURED] In the words, %s sinks across creators: %d posts at %s against %s without (%s)." % (
            s["label"], s["with"]["posts"], _x(s["with"]["lift"]), _x(s["without"]["lift"]), s["from"]))
    if not wd.get("sinks") and wd.get("note"):
        L.append("- In the words: " + wd["note"][:1].lower() + wd["note"][1:])
    for cl in fi.get("did_not_work") or []:
        L.append("- " + ("**%s.** " % cl["title"] if cl.get("title") else "") + claim_line(cl))
    L.append("")
    if wl:
        L += ["### Who to watch (watchlist.csv; feeds Scout and Watch)", ""]
        for r in wl:
            L.append("- @%s (%s): %s. `%s`" % (r["handle"], r["network"], r["why"], r["watch_command"]))
        L.append("")
    if tc:
        sat, mom, late = tc.get("saturation") or {}, tc.get("momentum") or {}, tc.get("lateness") or {}
        sz = tc.get("sample_sizes") or {}
        L += ["### Topic check (MEASURED by topic_check.py)", "",
              "- [MEASURED] **%s** (topic_check.json#verdict)." % tc.get("verdict"),
              "- [MEASURED] Saturation (last %sh): %s (%s posts, %s breakouts, %s by large accounts). "
              "Momentum: %s (last 6h %s = %s/h vs prev 6h %s = %s/h). Lateness: %s%s (topic_check.json)." % (
                  sat.get("window_hours", 48), sat.get("level"), sat.get("posts_in_window"), sat.get("breakouts_count"),
                  len(sat.get("large_account_breakouts") or []), mom.get("level"),
                  (mom.get("last_6h") or {}).get("posts"), (mom.get("last_6h") or {}).get("per_hour"),
                  (mom.get("prev_6h") or {}).get("posts"), (mom.get("prev_6h") or {}).get("per_hour"),
                  late.get("band"),
                  (" (%sh since @%s)" % (late["hours_since_first_big"], (late.get("first_big_post") or {}).get("author")))
                  if late.get("hours_since_first_big") is not None else ""),
              "- Sample sizes: total %s · last 6h %s · prev 6h %s · 48h %s%s." % (
                  sz.get("total_read"), sz.get("last_6h"), sz.get("prev_6h"), sz.get("last_48h"),
                  " (sample only)" if tc.get("sampled") else ""),
              ""]
    for sec, title in (("formats", "The formats, the agent's reading"), ("hooks", "The hooks, the agent's reading"),
                       ("creators", "The creators, the agent's reading"), ("mechanisms", "Other findings")):
        if fi.get(sec):
            L += ["### " + title, ""]
            for cl in fi[sec]:
                L.append("- " + ("**%s.** " % cl["title"] if cl.get("title") else "") + claim_line(cl))
            L.append("")
    if fi.get("plays"):
        L += ["### Plays", ""]
        for i, p in enumerate(fi["plays"], 1):
            L.append("%d. **%s** (effort %s). %s" % (i, p["title"], p.get("effort"), claim_line(p)))
            L.append("   Prompt: %s" % (p.get("prompt") or "").replace("\n", " "))
        L.append("")
    if d.get("limits") or fi.get("not_read"):
        L += ["### Not read", ""] + ["- %s: %s" % (x["what"], x["why"]) for x in fi.get("not_read") or []] + \
             ["- [MEASURED] %s: %s" % (x["what"], x["why"]) for x in d.get("limits") or []] + [""]
    L += ["### Files", "",
          "niche.json (the question, the window, the sources) · accounts/<network>-<handle>/ (each creator's posts) · "
          "found.csv (how posts were found) · trends.json, trends.csv · radar.json, formats/<id>.md (recipes) · "
          "writing.json, posts_text.csv, hooks.md · watchlist.csv · planner_rows.json (trends) · findings.json · "
          "cost.csv · report.html (the Niche report, one file) · report_record.json and radar_rows.json (the report and "
          "the formats of the niche, for a planner connector)", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------- the page

BODY = r"""
var drawn = {radar: 0, gallery: 0, trends: 0, writing: 0, first_lines: 0, watchlist: 0, not_working: 0};
window.__reaReport = {drawn: drawn, ready: false, kind: 'niche'};
var N = D.niche || {}, T = D.trends || {}, R = D.radar || {}, F = D.findings || {}, FM = D.formats || [];
(D.posts || []).forEach(function(p){ POSTS[p.id] = p; });

/* ---------- header */
(function(){
  var w = T.window || {};
  app.appendChild(el('header', {cls: 'top'},
    el('div', null,
      el('div', {cls: 'kicker', text: 'REA Viral · Niche report · ' + (N.networks || []).join(', ') + ' · ' + date(w.from) + ' to ' + date(w.to)}),
      el('h1', {text: N.name || 'A niche'}),
      el('div', {cls: 'sub', text: (N.question ? N.question + ' · ' : '') + 'searched by: ' + [].concat(N.words || [], N.tags || []).join(', ')})),
    el('div', {cls: 'row'}, themeButton())));
  var c = T.counts || {}, tot = (D.cost || {}).total_usd || 0;
  app.appendChild(el('div', {cls: 'stats'},
    stat(c.creators == null ? '—' : (c.creators_active != null ? c.creators_active : c.creators), 'creators with posts in the window · ' + (c.creators_scored || 0) + ' with their own usual' + (c.creators_active != null && c.creators > c.creators_active ? ' · ' + (c.creators - c.creators_active) + ' read had none' : '')),
    stat(c.posts_read == null ? '—' : c.posts_read, 'posts read · ' + (c.in_window || 0) + ' in the window'),
    stat(c.scored == null ? '—' : c.scored, 'scored against their own creator'),
    stat(c.hits == null ? '—' : c.hits, 'at 2× their own creator\'s usual or more'),
    stat(FM.filter(function(f){ return f.niche_format; }).length, 'formats of the niche (3+ creators)'),
    stat('$' + tot.toFixed(tot < 1 ? 3 : 2), 'spent on data' + (N.spend_ceiling_usd != null ? ' (ceiling $' + N.spend_ceiling_usd + ')' : ''))));
  app.appendChild(legend());
  if (T.status && T.status !== 'ok') app.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Status: ' + T.status + '. '}), T.status_note || ''));
  app.appendChild(el('div', {cls: 'small muted', style: 'margin-top:10px', text: 'A trend here is a post that beat its OWN creator\'s usual (the median of that creator\'s other posts), never the biggest number. A small creator\'s real outlier ranks above a big creator\'s ordinary post.'}));
})();

/* ---------- the answer */
(function(){
  if (!F.headline && !(F.formats || []).length && !(F.mechanisms || []).length) return;
  var s = section('answer', 'What works now', 'The reading of the agent that ran the skill. Each line carries its evidence.');
  var p = el('div', {cls: 'panel'});
  if (F.headline) p.appendChild(el('div', {cls: 'answer'}, chip(F.headline.evidence), F.headline.text));
  if (F.headline && F.headline.basis) p.appendChild(el('div', {cls: 'basis muted small', text: 'Basis: ' + F.headline.basis}));
  var list = el('div', {style: 'margin-top:10px'});
  (F.formats || []).concat(F.mechanisms || []).forEach(function(m){ list.appendChild(claim(m)); });
  p.appendChild(list); s.appendChild(p);
})();

/* ---------- topic check (when topic_check.json is present) */
(function(){
  var TC = D.topic_check;
  if (!TC) return;
  var SAT = TC.saturation || {}, MOM = TC.momentum || {}, LATE = TC.lateness || {}, SZ = TC.sample_sizes || {};
  function fmtH(h){ if (h == null) return '—'; if (h < 1) return Math.max(1, Math.round(h * 60)) + ' min'; return (h < 10 ? h.toFixed(1).replace(/\.0$/, '') : Math.round(h)) + 'h'; }
  var s = section('topic-check', 'Topic check: is this still worth posting?', 'Saturation (last ' + (SAT.window_hours || 48) + 'h) + momentum (last 6h vs prev 6h) + lateness.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  p.appendChild(el('div', {cls: 'answer'}, chip('MEASURED'), TC.verdict || '—'));
  if (TC.sampled && TC.sample_note) p.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Sample only. '}), TC.sample_note));
  p.appendChild(el('div', {cls: 'stats', style: 'margin-top:12px'},
    stat(String(SAT.level || '—').toUpperCase(), 'saturation · ' + (SAT.breakouts_count || 0) + ' breakouts (' + ((SAT.large_account_breakouts || []).length) + ' large)'),
    stat(String(MOM.level || '—').replace(/_/g, ' ').toUpperCase(), 'last 6h: ' + ((MOM.last_6h || {}).posts || 0) + ' (' + ((MOM.last_6h || {}).per_hour || 0) + '/h) vs prev 6h: ' + ((MOM.prev_6h || {}).posts || 0) + ' (' + ((MOM.prev_6h || {}).per_hour || 0) + '/h)'),
    stat(LATE.hours_since_first_big != null ? fmtH(LATE.hours_since_first_big) : 'none yet', 'since first ' + num(LATE.big_views_threshold || 100000) + '+ post'),
    stat(String(SZ.last_48h || 0), 'posts read in 48h' + (TC.sampled ? ' (sample)' : ''))));
  var rows = SAT.top_posts || [];
  if (rows.length){
    var t = el('table', {style: 'margin-top:10px'}, el('tr', null, el('th', {text: 'Post'}), el('th', {text: 'Author'}), el('th', {cls: 'num', text: 'Followers'}), el('th', {cls: 'num', text: 'Views'}), el('th', {cls: 'num', text: 'Age'}), el('th', {text: 'Flags'})));
    rows.slice(0, 5).forEach(function(r){
      var fl = []; if (r.large_account) fl.push('large account'); if (r.breakout) fl.push('breakout');
      t.appendChild(el('tr', null, el('td', null, r.url ? el('a', {href: r.url, text: r.post_id}) : r.post_id), el('td', {text: '@' + (r.author || '—')}),
        el('td', {cls: 'num', text: num(r.author_followers)}), el('td', {cls: 'num'}, el('strong', {text: num(r.views)})),
        el('td', {cls: 'num', text: fmtH(r.hours_ago)}), el('td', {cls: 'small', text: fl.join(', ') || '—'})));
    });
    p.appendChild(t);
  }
  p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:8px'}, chip('MEASURED'), 'From topic_check.json. ' + (LATE.benchmark_note || '')));
  drawn.topic_check = 1;
})();

/* ---------- the radar */
(function(){
  var s = section('radar', 'Formats of the niche', 'Every format seen in the niche, each post against its own creator\'s usual (1×). A format of the niche needs 3 creators or more. Pick one to study it.');
  if (R.status !== 'ok' && !FM.length){
    s.appendChild(el('div', {cls: 'panel'}, el('div', {cls: 'empty', text: R.status_note || 'No formats measured yet.'})));
    return;
  }
  var top = el('div'); s.querySelector('.sec-head').appendChild(top);
  if (R.status !== 'ok') s.appendChild(el('div', {cls: 'status', text: R.status_note || 'No format reached 3 creators: nothing is a format of the niche yet.'}));
  var host = el('div'); s.appendChild(host);
  drawn.radar = studyFormats(host, {formats: FM, posts: D.posts || [], niche: true, top: top,
    recipe: function(id){ return id !== '__none'; }});
  var un = R.unformatted || {};
  s.appendChild(el('div', {cls: 'small muted', style: 'margin-top:8px'}, chip('MEASURED'), 'All numbers by radar.py and trends.py; the grouping is the agent\'s. A format of the niche needs 3 creators or more; fewer is that creator\'s habit. ' + (un.posts ? un.posts + ' posts in the window (' + pct(un.share) + ') belong to no format.' : '')));
})();

/* ---------- the gallery */
(function(){
  if (!FM.length) return;
  var s = section('gallery', 'The formats, with the posts that prove them', 'Each creator\'s best post of the format, best first. Covers and frame sheets link to the original posts; no video is copied here.');
  var gal = el('div', {cls: 'gallery'}); s.appendChild(gal);
  var order = {scale_it: 0, underused: 1, overused: 2, fading: 2, drop: 3, too_few: 4};
  FM.slice().sort(function(a, b){ return (order[a.quadrant] - order[b.quadrant]) || ((b.lift || 0) - (a.lift || 0)); }).forEach(function(f){
    var rc = ((D.recipes || {})[f.id] || {}), rec = rc.recipe || {};
    var card = el('div', {cls: 'fcard' + (f.niche_format ? '' : ' not'), id: 'fmt-' + f.id, 'data-format': f.id},
      el('div', {cls: 'head'}, el('h3', {text: f.name}), el('span', {cls: 'q ' + f.quadrant, text: f.niche_format ? QN[f.quadrant] : 'Not a niche format: ' + f.scope_status}),
        el('span', {cls: 'pill', text: f.creators + ' creator' + (f.creators === 1 ? '' : 's')}), f['new'] ? el('span', {cls: 'pill', text: 'new in the window'}) : null,
        el('span', {cls: 'pill', text: 'effort ' + (f.effort || '?')}), rc.file ? el('a', {cls: 'small', href: rc.file, text: rc.file}) : null),
      el('div', {cls: 'kv', style: 'margin-top:8px'},
        el('span', {cls: 'k', text: 'Container'}), el('span', {text: [f.container.hook, f.container.structure, f.container.look, f.container.length].filter(Boolean).join(' · ')}),
        el('span', {cls: 'k', text: 'Measured'}), !f.posts_scored ? el('span', null, chip('MEASURED'), 'None of its ' + f.posts_total + ' posts in the window could be scored against its own creator\'s usual (' + (f.weaker_basis_posts || 0) + ' on the weaker basis, ' + (f.too_new_posts || 0) + ' too new); first seen ' + date(f.first_seen)) : el('span', null, chip('MEASURED'), f.posts_scored + ' scored posts from ' + f.creators + (f.creators === 1 ? ' creator' : ' creators') + '; lift ' + xr(f.lift) + ' (each creator\'s median, then the median of those); hit rate ' + pct(f.hit_rate) + (f.direction != null ? '; ' + f.direction_label + ' ' + xr(f.direction) : '; direction: not enough posts in each half') + '; first seen ' + date(f.first_seen) + (f.few_posts ? '; few posts' : '')),
        f.basis ? [el('span', {cls: 'k', text: 'Grouped by'}), el('span', null, chip('SEEN'), f.basis)] : null,
        rec.hook_pattern ? [el('span', {cls: 'k', text: 'Hook'}), el('span', {text: rec.hook_pattern})] : null,
        (rec.beats || []).length ? [el('span', {cls: 'k', text: 'Beats'}), el('span', {text: rec.beats.map(function(b){ return b.at + ' s ' + b.what + (b.text ? ': ' + b.text : ''); }).join(' → ')})] : null));
    var proof = el('div', {cls: 'proof'});
    (f.examples || []).forEach(function(e){
      var p = POSTS[e.post_id] || {}, sheet = (D.sheets || {})[e.post_id];
      // The cover is the clearest picture; the frame sheet of a watched video is linked beside it.
      var pic = p.cover ? el('img', {src: p.cover, alt: ''}) : (sheet ? el('img', {src: sheet, cls: 'sheet', alt: 'The first seconds of the post'}) : el('div', {cls: 'ph'}));
      proof.appendChild(el('div', null, el('a', {href: e.url, title: (p.caption || '').slice(0, 140)}, pic,
        el('span', {cls: 'who', text: '@' + e.account}), xr(e.ratio) + ' its usual'),
        sheet && p.cover ? el('a', {cls: 'small', href: sheet, text: ' · frames'}) : null));
    });
    if (!(f.examples || []).length) proof.appendChild(el('div', {cls: 'empty', text: 'No scored post in the window.'}));
    card.appendChild(proof);
    gal.appendChild(card); drawn.gallery++;
  });
})();

/* ---------- what did not work */
(function(){
  var NW = D.not_working || {}, FL = NW.flops || {}, WD = NW.words || {};
  var s = section('not-working', 'What did not work', 'The formats of the niche under their creators\' usual or fading, the flops, and what sinks in the words across 3 creators or more. A flop shows what was there, never on its own why it flopped.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (NW.note) p.appendChild(el('div', {cls: 'empty', style: 'margin-bottom:8px', text: NW.note}));
  (F.did_not_work || []).forEach(function(c){ p.appendChild(claim(c)); drawn.not_working++; });
  p.appendChild(el('h3', {text: 'Formats under their creators\' usual or fading', style: 'margin-top:12px'}));
  if (!(NW.formats || []).length) p.appendChild(el('div', {cls: 'empty', text: NW.formats_note || 'No format of the niche sits under its creators\' usual or fades.'}));
  (NW.formats || []).forEach(function(f){
    var low = el('div', {cls: 'proof'});
    (f.lowest || []).forEach(function(x){ var q = POSTS[x.post_id] || {};
      low.appendChild(el('div', null, el('a', {href: q.url, title: (q.caption || '').slice(0, 140)}, q.cover ? el('img', {src: q.cover, alt: ''}) : el('div', {cls: 'ph'}), el('span', {cls: 'who', text: '@' + (x.account || q.account || '')}), xr(x.ratio) + ' its usual'))); });
    p.appendChild(el('div', {style: 'margin-top:10px'},
      el('div', {cls: 'row'}, el('a', {href: '#fmt-' + f.id, text: f.name}), el('span', {cls: 'q ' + f.quadrant, text: QN[f.quadrant]}), el('span', {cls: 'pill', text: f.creators + ' creators'}), f.few_posts ? el('span', {cls: 'pill', text: 'few posts: not a finding on its own'}) : null),
      el('div', {cls: 'small', style: 'margin-top:4px'}, chip('MEASURED'), f.posts_scored + ' scored posts at ' + xr(f.lift) + ' each creator\'s own usual' + (f.under ? '' : ' (over 1×, but fading)') +
        (f.direction != null ? '; ' + f.direction_label + ' ' + xr(f.direction) + ' (the later half against the earlier)' : '; direction: not enough posts') + '. Its lowest posts below. ', el('span', {cls: 'muted', text: 'From ' + f.from})),
      low));
    drawn.not_working++;
  });
  p.appendChild(el('h3', {text: 'The flops', style: 'margin-top:14px'}));
  p.appendChild(el('div', {cls: 'small'}, chip('MEASURED'), FL.note ? FL.note + ' ' : (FL.count + ' of ' + FL.of_scored + ' scored posts sat at ' + xr(FL.flop_ratio) + ' their own creator\'s usual or under, from ' + FL.creators + ' creators' +
    ((FL.by_format || []).length ? ': ' + FL.by_format.map(function(b){ return b.flops + ' ' + (b.name || 'in no format'); }).join(', ') : '') + '. '), el('span', {cls: 'muted', text: 'From ' + (FL.from || 'trends.json#posts')})));
  if ((FL.picks || []).length) p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: 'The lowest posts the deep read picked to watch, of different creators:'}));
  (FL.picks || []).forEach(function(x){
    p.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), el('div', {cls: 't'}, postLink(x.post_id), ' · @' + (x.account || ''), x.format ? el('span', {cls: 'muted', text: ' · ' + x.format}) : null,
      x.read === true ? el('div', {cls: 'small'}, chip('SEEN'), 'Hook: ' + (x.hook || '—') + ' · the turn: ' + (x.turn || '—') + (x.ask ? ' · the ask: ' + x.ask : ''))
                      : el('div', {cls: 'small muted', text: 'Not watched' + (x.not_read_reason ? ': ' + x.not_read_reason : '') + '.'}))));
    drawn.not_working++;
  });
  p.appendChild(el('h3', {text: 'What sinks in the words across creators', style: 'margin-top:14px'}));
  if ((WD.sinks || []).length){
    var t = el('table', null, el('tr', null, el('th', {text: 'In the words'}), el('th', {cls: 'num', text: 'With it'}), el('th', {cls: 'num', text: 'Without it'}), el('th', {text: 'Verdict'})));
    WD.sinks.forEach(function(x){ t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), x.label), el('td', {cls: 'num', text: x['with'].posts + ' posts · ' + xr(x['with'].lift)}), el('td', {cls: 'num', text: x.without.posts + ' posts · ' + xr(x.without.lift)}), el('td', null, el('span', {cls: 'v-sinks', text: 'sinks'})))); drawn.not_working++; });
    p.appendChild(t);
  } else p.appendChild(el('div', {cls: 'empty', text: WD.note || 'Nothing in the words sinks clearly across 3 creators or more.'}));
  (WD.leads || []).forEach(function(x){ p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:4px'}, chip('MEASURED'), 'A lead, not a finding: ' + x.label + ', ' + x['with'].posts + ' posts at ' + xr(x['with'].lift) + ' against ' + xr(x.without.lift) + ' without.')); });
  (WD.worst || []).forEach(function(x){ p.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), el('div', {cls: 't'}, chip('SEEN'), '"' + (x.first_line || '') + '"', el('div', {cls: 'small muted'}, postLink(x.post_id), ' · @' + (x.account || '') + ' · one of the worst first lines')))); });
})();

/* ---------- trends */
(function(){
  var s = section('trends', 'Posts that beat their own creator\'s usual', 'Ranked by how far each post beat the median of its own creator\'s other posts.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  var ids = (T.ranked || []).slice(0, 20);
  if (!ids.length){ p.appendChild(el('div', {cls: 'empty', text: 'No post could be scored against its own creator.'})); }
  else {
    var t = el('table', null, el('tr', null, el('th', {cls: 'num', text: '#'}), el('th', {text: 'Post'}), el('th', {text: 'Creator'}), el('th', {text: 'Date'}), el('th', {cls: 'num', text: 'Views'}), el('th', {cls: 'num', text: 'Its usual'}), el('th', {cls: 'num', text: 'Ratio'}), el('th', {text: 'Format'})));
    ids.forEach(function(id){ var q = POSTS[id]; if (!q) return;
      t.appendChild(el('tr', null, el('td', {cls: 'num', text: q.rank}), el('td', null, postLink(id)), el('td', {text: '@' + q.account}), el('td', {text: date(q.at)}),
        el('td', {cls: 'num', text: num(q.views)}), el('td', {cls: 'num', text: num(q.baseline) + ' (' + q.baseline_n + ')'}), el('td', {cls: 'num'}, el('strong', {text: xr(q.ratio)}), q.fresh ? el('span', {cls: 'small muted', text: ' fresh'}) : null), el('td', {cls: 'small', text: q.format || '—'})));
      drawn.trends++; });
    p.appendChild(t);
    p.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px'}, chip('MEASURED'), 'Its usual = the median of the creator\'s other settled posts (how many in brackets). Fresh posts under settling time are scored and marked fresh / still growing. trends.csv holds every post.'));
  }
  if (T.suspect_reach && (T.suspect_reach.posts || []).length){
    var sr = T.suspect_reach;
    p.appendChild(el('div', {cls: 'status'}, chip('MEASURED'), el('strong', {text: 'Check these outliers. '}),
      sr.count + ' post' + (sr.count === 1 ? '' : 's') + ' had views 1000× the creator\'s followers or more (' +
      sr.posts.slice(0, 3).map(function(x){ return '@' + x.account + ' ' + x.post_id + ' (' + num(x.views) + ' views on ' + num(x.followers) + ')'; }).join(', ') +
      '). Open before calling them a finding (trends.json#suspect_reach).'));
  }
  var weak = (T.leads_weaker_basis || []).map(function(id){ return POSTS[id]; }).filter(Boolean);
  if (weak.length) p.appendChild(el('div', {cls: 'small', style: 'margin-top:10px'}, chip('MEASURED'), el('strong', {text: 'Weaker basis. '}),
    weak.length + ' posts from creators with too few posts read for their own usual, measured as views per follower and never counted toward a format: ',
    weak.slice(0, 6).map(function(q, i){ return [i ? ', ' : '', postLink(q.id), ' @' + q.account + ' ' + (q.vpf != null ? q.vpf.toFixed(2) + ' views per follower' : '') + (q.lead ? ' (a lead)' : '')]; })));
  var young = (T.too_new || []).map(function(id){ return POSTS[id]; }).filter(function(q){ return q && (q.ratio != null || q.ratio_so_far != null); });
  if (young.length) p.appendChild(el('div', {cls: 'small', style: 'margin-top:8px'}, chip('MEASURED'), el('strong', {text: 'Fresh / still growing. '}),
    'Under settling time, included in scoring as a floor while views keep coming in: ', young.slice(0, 6).map(function(q, i){ return [i ? ', ' : '', postLink(q.id), ' @' + q.account + ' ' + xr(q.ratio != null ? q.ratio : q.ratio_so_far) + ' so far']; })));
})();

/* ---------- hooks */
(function(){
  var W = D.writing, V = D.hooks;
  if (!W) return;
  var cn = W.counts || {}, lg = W.language || {};
  var s = section('hooks', 'Hooks: what the winning posts open with', 'Each post\'s words against its own creator\'s usual: ' + (cn.scored_with_text || 0) + ' scored posts with words. A feature counts for the niche only when its posts come from 3 creators or more. A niche run writes the niche\'s hooks (hooks.md), not a voice sheet: for one creator\'s voice sheet, run an account run or words only on that creator. ' + (lg.note || ''));
  if (W.status !== 'ok') s.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Status: ' + W.status + '. '}), W.status_note || ''));
  var p1 = el('div', {cls: 'panel'});
  var feats = W.features || [], nums = W.numbers || [];
  var strong = feats.filter(function(f){ return f.claim_ok; }), strongN = nums.filter(function(f){ return f.claim_ok; });
  var habit = feats.filter(function(f){ return f.verdict === 'few creators'; });
  p1.appendChild(el('h3', {text: 'What lifts and what sinks across creators'}));
  if (!strong.length && !strongN.length) p1.appendChild(el('div', {cls: 'empty', text: 'Nothing in the words lifts or sinks clearly across 3 creators or more.'}));
  if (strong.length){
    var t = el('table', null, el('tr', null, el('th', {text: 'In the words'}), el('th', {cls: 'num', text: 'With it'}), el('th', {cls: 'num', text: 'Without it'}), el('th', {text: 'Verdict'})));
    strong.forEach(function(f){ t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), f.label), el('td', {cls: 'num', text: f['with'].posts + ' posts · ' + xr(f['with'].lift)}), el('td', {cls: 'num', text: f.without.posts + ' posts · ' + xr(f.without.lift)}),
      el('td', null, el('span', {cls: /sink/.test(f.verdict) ? 'v-sinks' : 'v-lifts', text: f.verdict}), el('span', {cls: 'muted small', text: f.chance != null ? ' · chance ' + (f.chance < 0.001 ? '<0.1%' : (f.chance * 100).toFixed(1) + '%') : ''})))); drawn.writing++; });
    p1.appendChild(t);
  }
  strongN.forEach(function(f){ var w = f.winning_range || {}; p1.appendChild(el('div', {cls: 'claim'}, chip('MEASURED'), el('strong', {text: f.label + ': '}), (w.range ? w.range[0] + '–' + w.range[1] : '') + ' lifts ' + xr(w.lift) + ' on ' + w.posts + ' posts')); drawn.writing++; });
  (W.overlaps || []).forEach(function(o){ p1.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px'}, chip('MEASURED'), o.a + ' and ' + o.b + ' sit on the same ' + o.posts_both + ' posts: the numbers cannot tell them apart.')); });
  if (habit.length) p1.appendChild(el('div', {cls: 'small muted', style: 'margin-top:8px'}, chip('MEASURED'), 'One creator\'s habit, not the niche\'s: ' + habit.map(function(f){ return f.label + ' (' + (f.note || '') + ')'; }).join('; ') + '.'));
  (F.hooks || []).forEach(function(c){ p1.appendChild(claim(c)); });
  s.appendChild(p1);
  var fl = W.first_lines || {};
  var g = el('div', {cls: 'grid2', style: 'margin-top:14px'});
  [['The best first lines', fl.best || []], ['The worst first lines', fl.worst || []]].forEach(function(col){
    var pn = el('div', {cls: 'panel'}, el('h3', null, chip('SEEN'), col[0]));
    if (!col[1].length) pn.appendChild(el('div', {cls: 'empty', text: 'No scored posts.'}));
    col[1].forEach(function(x){ pn.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(x.ratio)}), el('div', {cls: 't'}, '"' + (x.first_line || '') + '"',
      el('div', {cls: 'small muted'}, postLink(x.post_id), ' · @' + (x.account || '') + (x.chars != null ? ' · ' + x.chars + ' characters' : '') + (x.first_part_only ? ' · thread: first part only' : ''))))); drawn.first_lines++; });
    g.appendChild(pn);
  });
  s.appendChild(g);
  if (V){
    var p4 = el('div', {cls: 'panel voice', style: 'margin-top:14px'});
    p4.appendChild(el('div', {cls: 'row'}, el('h3', {text: 'The hooks sheet', style: 'margin:0'}), el('a', {cls: 'small', href: V.file, text: V.file})));
    var r = V.rules || {}, rr = el('div', {cls: 'rules'});
    if (r.first_line_chars) rr.appendChild(el('span', {cls: 'pill', text: 'first line ' + r.first_line_chars[0] + '–' + r.first_line_chars[1] + ' characters'}));
    (r.openings || []).forEach(function(o){ rr.appendChild(el('span', {cls: 'pill', text: o.replace(/_/g, ' ')})); });
    (r.avoid || []).forEach(function(o){ rr.appendChild(el('span', {cls: 'pill', text: 'avoid: ' + o.replace(/_/g, ' ')})); });
    p4.appendChild(rr);
    String(V.text || '').split(/\n(?=## )/).forEach(function(block){
      var lines = block.split('\n'), head = lines[0].indexOf('## ') === 0 ? lines.shift().slice(3) : null, body = lines.join('\n').trim();
      if (!head && !body) return;
      if (head) p4.appendChild(el('h3', {text: head}));
      body.split(/\n{2,}/).forEach(function(par){ par.split(/\n(?=- )/).forEach(function(item){ if (item.trim()) p4.appendChild(el('p', {text: item.replace(/\n\s*/g, ' ').replace(/`/g, '')})); }); });
    });
    s.appendChild(p4);
  }
})();

/* ---------- who to watch */
(function(){
  var wl = D.watchlist || [];
  var s = section('watchlist', 'Who to watch', 'Creators with a post at 2× their own usual or more, or who use a rising format. watchlist.csv feeds Scout and Watch.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (!wl.length){ p.appendChild(el('div', {cls: 'empty', text: 'Nobody stood out in this window.'})); }
  else {
    var t = el('table', null, el('tr', null, el('th', {cls: 'num', text: '#'}), el('th', {text: 'Creator'}), el('th', {cls: 'num', text: 'Followers'}), el('th', {cls: 'num', text: 'Usual views'}), el('th', {cls: 'num', text: 'Hits'}), el('th', {cls: 'num', text: 'Best'}), el('th', {text: 'Why'})));
    wl.forEach(function(r){ t.appendChild(el('tr', null, el('td', {cls: 'num', text: r.rank}), el('td', null, el('a', {href: r.url, text: '@' + r.handle})),
      el('td', {cls: 'num', text: num(r.followers)}), el('td', {cls: 'num', text: num(r.usual) + (r.basis === 'own' ? '' : ' (weaker)')}), el('td', {cls: 'num', text: r.hits + ' of ' + r.scored}),
      el('td', {cls: 'num'}, r.best_url ? el('a', {href: r.best_url, text: xr(r.best_ratio)}) : '—'), el('td', {cls: 'small'}, chip('MEASURED'), r.why))); drawn.watchlist++; });
    p.appendChild(t);
  }
  (F.creators || []).forEach(function(c){ p.appendChild(claim(c)); });
})();

waysToMake('Asked once, after the report, starting from one format of the niche: make it (Basic, Standard or Advanced), draft posts with the niche\'s hooks, or go deeper into one creator who owns the format.');
playsSection(F.plays || []);
sourcesSection(D.sources, F.not_read, D.cost, [(T.counts || {}).no_date ? (T.counts.no_date + ' posts had no date and were left out.') : null, picturesLine(D.pictures)].filter(Boolean), D.limits);
app.appendChild(el('footer', null, 'Niche report. Built ' + D.built_at + ' by REA Viral ' + D.skill_version + ' from the run\'s data files (niche.json, trends.json, radar.json, writing.json, findings.json); one file, the pictures inside it. Captions are shown as data.'));
stackTables();
window.__reaReport.ready = true;
"""


def build(folder, light_only=False):
    import validate
    rep = validate.validate(folder)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:30]]
        die("validate.py found %d error(s); the page is not built:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    d = page_data(folder, light=light_only)
    title = "%s · Niche report · REA Viral" % (d["niche"].get("name") or "Niche")
    if not light_only:
        write_text(os.path.join(folder, "report.html"), page_kit.page(title, "NICHE.md", d, BODY))
    write_text(os.path.join(folder, "report-light.html"), page_kit.page(title, "NICHE.md", light_niche(d), BODY))
    write_text(os.path.join(folder, "NICHE.md"), niche_md(d))
    d["hand_over"] = hand_over_files(folder, d)
    d["light_only"] = light_only
    return d


LIGHT_POST_KEYS = ("id", "url", "account", "creator", "at", "views", "ratio", "ratio_so_far", "vpf", "baseline",
                   "baseline_n", "status", "fresh", "basis", "format", "rank", "lead", "cover")


def light_niche(d):
    """The light page's data: no picture; the posts the page does not draw in full keep only what the links, the
    ranked table and the leads need."""
    out = page_kit.light_data(d)
    keep = set(e["post_id"] for f in out.get("formats") or [] for e in f.get("examples") or [])
    nw = out.get("not_working") or {}
    keep |= set(x["post_id"] for f in nw.get("formats") or [] for x in f.get("lowest") or [])
    keep |= set(x["post_id"] for x in (nw.get("flops") or {}).get("picks") or [])
    t = out.get("trends") or {}
    keep |= set((t.get("ranked") or [])[:20]) | set((t.get("leads_weaker_basis") or [])[:6]) | set((t.get("too_new") or [])[:6])
    links = page_kit.claim_post_ids(out.get("findings"))
    w = out.get("writing") or {}
    links |= set(x.get("post_id") for k in ("best", "worst") for x in ((w.get("first_lines") or {}).get(k) or []))
    # The posts the page draws keep everything; a post only linked keeps its link; the rest are not on the page.
    out["posts"] = [p if p["id"] in keep else dict((k, p.get(k)) for k in ("id", "url", "account", "ratio"))
                    for p in out.get("posts") or [] if p["id"] in keep or p["id"] in links]
    for f in out.get("formats") or []:
        f.pop("proof", None)                             # not drawn: radar.json keeps it
    if (out.get("radar") or {}).get("unformatted"):
        out["radar"]["unformatted"].pop("post_ids", None)
    out["sheets"] = {}
    out["writing"] = page_kit.light_writing(out.get("writing"))
    return out


def hand_over_files(folder, d):
    """report_record.json and radar_rows.json (hand_over.py): the Niche report's record, and one row per format of
    the niche (3 creators or more), its face the format's best proof post, with its recipe and the proof links."""
    n, fi, t = d["niche"], d["findings"] or {}, d["trends"]
    tr = read_json(os.path.join(folder, "trends.json"))
    P = dict((p["post_id"], p) for p in tr["posts"])
    followers = dict((c["id"], c.get("followers")) for c in tr.get("creators") or [])
    slug = n.get("slug") or os.path.basename(os.path.abspath(folder))
    rows = []
    placed = [f for f in d["formats"] if f.get("niche_format") and (d["radar"] or {}).get("status") == "ok"]
    for f in hand_over.sort_formats(placed):
        ex = P.get(((f.get("examples") or [{}])[0]).get("post_id")) or {}
        face = {"url": ex.get("url"), "network": ex.get("network"), "post_id": ex.get("post_id"),
                "account": ex.get("account"), "caption": ex.get("caption"),
                "numbers": hand_over.numbers_of(ex, followers.get(ex.get("creator")), tr.get("read_at"))}
        rows.append(hand_over.format_row(
            hand_over.format_key("niche-" + slug, f["id"]), f, (d["recipes"].get(f["id"]) or {}).get("recipe"), face,
            niche=n.get("name"), creators=f.get("creators"), trend=hand_over.trend_of(f.get("direction_label")),
            proof=[e.get("url") for e in f.get("examples") or []]))
    if rows:
        note = "One row per format of the niche (3 creators or more), best corner first, for the user's saved formats."
    elif t.get("status") != "ok":
        note = "No format of the niche: %s" % (t.get("status_note") or t.get("status"))
    else:
        note = "No format of the niche: no format reached 3 creators."
    fallback = brief.measured_answer("niche", d)      # never empty: findings.json may have no headline
    nets = n.get("networks") or []
    c = t.get("counts") or {}
    keys = dict((f["id"], r["key"]) for f, r in zip(hand_over.sort_formats(placed), rows))
    br = brief.niche(folder, d, keys, None)
    rec, _ = hand_over.write(folder, "niche", {
        "title": n.get("name") or slug,
        "subject": {"niche": n.get("name"), "network": nets[0] if len(nets) == 1 else None},
        "summary": hand_over.summary_text(fi.get("headline"), fi.get("did_not_work"), fallback),
        "read": {"posts": c.get("posts_read"), "creators": c.get("creators_active", c.get("creators"))},
        "sources": d.get("sources"), "cost": d.get("cost"),
        "page_path": os.path.join(folder, "report.html"), "run_name": os.path.basename(os.path.abspath(folder)),
    }, rows, note, brief=br)
    return {"record": rec, "rows": len(rows), "brief": br}
