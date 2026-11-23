"""The brief: the short, structured view of a report that a planner draws in its own panel (GreenLight Pulse's
sliding panel), beside the full page (report.html, the Extended report). build_report.py builds it from
findings.json and the numbers the scripts measured, never from hand-typed text, and writes it as brief.json in the
run folder; report_record.json carries it as report.brief, so a save-report tool takes it with the record.

The planner's limits, all plain text:
    answer      400 characters at most: the answer in plain words (the agent's headline, or a measured line)
    numbers     6 at most of {label (24), value (16)}
    worked      6 at most of {title (80), stat (40), note (240), label: MEASURED | SEEN | INFERRED, format?}
    not_worked  the same shape, 6 at most: what did not work (the measured part first, then the agent's reading)
    plays       5 at most of {title (80), note (240)}
`stat` is the number behind an item ("2.81x its usual"); a claim whose source holds no number has none. Under
`not_worked` a stat says what is wrong, never a number above 1 alone: a fading format's direction ("fading: 0.23x
later vs earlier"), an under-usual format's lift below 1, the flops' ratio. `format` is the key of the item's format in
the planner's saved formats (a row of radar_rows.json), when it has one. With no headline in findings.json the answer
is a measured line ("Measured: …"), never empty (measured_answer).
"""
import json
import os
import re

from common import read_json

LIMITS = {"answer": 400, "numbers": 6, "label": 24, "value": 16, "items": 6, "title": 80, "stat": 40, "note": 240,
          "plays": 5}
LABELS = ("MEASURED", "SEEN", "INFERRED")


def plain(s, n):
    """One line of plain text, at most n characters, cut at a word."""
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    s = s[:n - 1]
    if " " in s[n // 2:]:
        s = s[:s.rindex(" ")]
    return s.rstrip(" ,;:.") + "…"


def xr(v):
    if v is None:
        return "-"
    v = float(v)
    if 0.995 <= v < 1.005 and v != 1.0:
        return "%.3f×" % v
    return (("%.0f" % v) if v >= 10 else ("%.2f" % v).rstrip("0").rstrip(".")) + "×"


def pct(v):
    return "-" if v is None else (("%.1f%%" % (100 * v)) if 0 < v < 0.1 else "%d%%" % round(100 * v))


def short(n):
    if n is None:
        return "-"
    a = abs(n)
    if a >= 1e9:
        return ("%.1fB" % (n / 1e9)).replace(".0B", "B")
    if a >= 1e6:
        return ("%.1fM" % (n / 1e6)).replace(".0M", "M")
    if a >= 1e4:
        return "%dK" % round(n / 1e3)
    if a >= 1e3:
        return ("%.1fK" % (n / 1e3)).replace(".0K", "K")
    return str(int(round(n)))


def spent(cost, sources):
    rows = (cost or {}).get("rows") or []
    if not rows and any((s or {}).get("cost_usd") is None for s in sources or []):
        return "price unknown"
    return "$%.2f" % float((cost or {}).get("total_usd") or 0.0)


def number(label, value):
    return {"label": plain(label, LIMITS["label"]), "value": plain(value, LIMITS["value"])}


def item(title, note, label, stat=None, fmt=None):
    x = {"title": plain(title, LIMITS["title"])}
    if stat:
        x["stat"] = plain(stat, LIMITS["stat"])
    x["note"] = plain(note, LIMITS["note"])
    x["label"] = label if label in LABELS else "INFERRED"
    if fmt:
        x["format"] = fmt
    return x


def _get(doc, keypath):
    """Follow a.b.c through dicts and lists (a list part matches an item's id, as validate.py does). None if absent."""
    parts, cur, i = keypath.split("."), doc, 0
    while i < len(parts):
        step = None
        for j in range(len(parts), i, -1):
            name = ".".join(parts[i:j])
            if isinstance(cur, dict) and name in cur:
                step = (cur[name], j)
            elif isinstance(cur, list):
                hit = [x for x in cur if isinstance(x, dict) and (x.get("id") == name or x.get("bucket") == name)]
                if hit:
                    step = (hit[0], j)
                elif j == i + 1 and name.isdigit() and int(name) < len(cur):
                    step = (cur[int(name)], j)
            if step:
                break
        if not step:
            return None
        cur, i = step
    return cur


def claim_stat(folder, c, failing=False):
    """The number behind a claim: a MEASURED claim's cited value when it is a number; a SEEN claim's post count.
    failing (a claim under not_worked): a direction reads "later vs earlier", and a multiple of 1 or more is left out,
    since alone it would read as a success."""
    ev = c.get("evidence")
    if ev == "SEEN":
        n = len(c.get("posts") or []) or len(c.get("links") or [])
        return ("seen in %d post%s" % (n, "" if n == 1 else "s")) if n else None
    if ev != "MEASURED" or not c.get("from"):
        return None
    f, _, kp = str(c["from"]).partition("#")
    p = os.path.join(folder, f)
    if not kp or not f.endswith(".json") or not os.path.exists(p):
        return None
    try:
        v = _get(read_json(p), kp)
    except (ValueError, OSError):
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        if isinstance(v, list):
            return "%d post%s" % (len(v), "" if len(v) == 1 else "s")
        return None
    last = kp.split(".")[-1]
    if last in ("direction", "usage_direction"):
        return ("%s later vs earlier" % xr(v)) if (v < 1 or not failing) else None
    if last in ("lift", "ratio", "lift_posts", "ratio_so_far") or last.endswith("_lift"):
        if failing and v >= 1:
            return None
        return xr(v) + (" its usual" if last in ("lift", "ratio", "lift_posts") else "")
    if last in ("share", "hit_rate", "creators_share", "rate"):
        return pct(v)
    return short(v) if isinstance(v, (int, float)) and abs(v) >= 1000 else str(round(v, 3)).rstrip("0").rstrip(".")


def source_line(c):
    if c.get("evidence") == "MEASURED" and c.get("from"):
        return "From " + c["from"]
    if c.get("evidence") == "SEEN":
        return "Seen in " + ", ".join((c.get("posts") or []) + (c.get("links") or []))
    if c.get("basis"):
        return "Basis: " + c["basis"]
    return ""


def from_claims(folder, claims, n, taken=None, failing=False):
    """The agent's claims as items: its title (or its words) and the words or where they come from, never an item
    whose title another item already has."""
    out, taken = [], taken if taken is not None else set()
    for c in claims or []:
        if len(out) >= n:
            break
        text = c.get("text") or c.get("what") or ""
        title = c.get("title") or text
        if plain(title, LIMITS["title"]).lower() in taken:
            continue
        taken.add(plain(title, LIMITS["title"]).lower())
        note = text if c.get("title") else (source_line(c) if len(text) <= LIMITS["title"] else text)
        out.append(item(title, note, c.get("evidence"), claim_stat(folder, c, failing)))
    return out


def titles(items):
    return set(x["title"].lower() for x in items)


def nothing(note_parts):
    """An honest empty part: what was measured and found nothing under the usual."""
    return item("Nothing measured under the usual", " ".join(x for x in note_parts if x), "MEASURED")


def plays_of(findings):
    return [{"title": plain(p.get("title"), LIMITS["title"]), "note": plain(p.get("what") or p.get("text"), LIMITS["note"])}
            for p in (findings.get("plays") or [])[:LIMITS["plays"]] if p.get("title")]


def finish(answer, numbers, worked, not_worked, plays):
    return {"schema": "rea-viral/brief@1", "answer": plain(answer, LIMITS["answer"]),
            "numbers": [x for x in numbers if x["value"] not in ("", "-")][:LIMITS["numbers"]],
            "worked": worked[:LIMITS["items"]], "not_worked": not_worked[:LIMITS["items"]], "plays": plays}


def words_items(wr, verdict, n, usual="its usual"):
    out = []
    for f in (wr or {}).get("features") or []:
        if f.get("claim_ok") and f.get("verdict") == verdict and len(out) < n:
            out.append(item(f["label"], "%d posts with it at %s, %s without it." % (
                f["with"]["posts"], xr(f["with"]["lift"]), xr(f["without"]["lift"])), "MEASURED",
                "%s %s" % (xr(f["with"]["lift"]), usual)))
    return out


def failing_stat(f, usual):
    """What is wrong with a format under not_worked: under its usual, its lift (below 1); over it but fading, its
    direction (the later posts against the earlier, below 1)."""
    if f.get("lift") is not None and f["lift"] < 1.0:
        return "%s %s" % (xr(f["lift"]), usual)
    if f.get("direction") is not None:
        return "%s: %s later vs earlier" % (f.get("direction_label") or "fading", xr(f["direction"]))
    return None


def flops_stat(fl):
    return "%d at %s or under" % (fl["count"], xr(fl.get("flop_ratio", 0.5)))


def measured_answer(kind, d):
    """The answer when findings.json has no headline: a line of the measured numbers, never empty."""
    nw = d.get("not_working") or {}
    weak = (nw.get("formats") or [None])[0]
    if kind == "account":
        an, r = d["analysis"], d.get("radar") or {}
        c = an.get("counts") or {}
        if an.get("status") != "ok":
            return "Measured: %s" % (an.get("status_note") or an.get("status"))
        order = {"scale_it": 0, "underused": 1}
        fm = [f for f in r.get("formats") or [] if f.get("quadrant") != "too_few" and f.get("lift") is not None]
        good = sorted([f for f in fm if f.get("quadrant") in ("scale_it", "underused")],
                      key=lambda f: (f.get("direction_label") == "fading", order[f["quadrant"]], -(f["lift"])))
        best = good[0] if good else (max(fm, key=lambda f: f["lift"]) if fm else None)
        parts = []
        if best and good:
            parts.append("strongest format %s (%s), %s its usual" % (best["name"], best["quadrant_name"], xr(best["lift"])))
        elif best:
            parts.append("no format sits in Scale it or Underused; the highest lift is %s (%s), %s its usual" % (
                best["name"], best["quadrant_name"], xr(best["lift"])))
        if weak and (not best or weak["id"] != best["id"]):
            parts.append("weakest %s (%s), %s" % (weak["name"], weak["quadrant_name"], failing_stat(weak, "its usual")))
        if not parts:
            parts.append("%s posts read, %s at 2\u00d7 their usual or more, %s flops" % (
                c.get("posts_total"), c.get("hits"), (nw.get("flops") or {}).get("count", 0)))
        return "Measured: " + "; ".join(parts) + "."
    if kind == "post":
        pp = d["probe"]
        p, rp = pp["post"], pp.get("repeats") or {}
        if p.get("ratio") is None:
            return "Measured: %s" % (pp.get("status_note") or pp.get("status"))
        return "Measured: %s its creator's usual (the median of %d other posts); %s." % (
            xr(p["ratio"]), p.get("usual_from_posts") or 0, rp.get("label") or "its format is not marked")
    t = d["trends"]
    if t.get("status") != "ok":
        return "Measured: %s" % (t.get("status_note") or t.get("status"))
    order = {"scale_it": 0, "underused": 1, "overused": 2, "drop": 3}
    placed = sorted([f for f in d["formats"] if f.get("niche_format") and f.get("lift") is not None],
                    key=lambda f: (order.get(f["quadrant"], 9), -f["lift"]))
    parts = []
    if placed:
        b = placed[0]
        parts.append("strongest format of the niche %s (%s), %d creators, %s each creator's usual" % (
            b["name"], b["quadrant_name"], b["creators"], xr(b["lift"])))
    else:
        parts.append("no format reached 3 creators")
    if weak:
        parts.append("%s: %s" % (weak["name"], failing_stat(weak, "each creator's usual")))
    return "Measured: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------------------------- the three reports

def account(folder, d, keys, fallback):
    fi, an, r, nw = d["findings"] or {}, d["analysis"], d["radar"] or {}, d.get("not_working") or {}
    c, acc = an.get("counts") or {}, d["account"]
    fm = r.get("formats") or []
    nums = [number("Posts read", c.get("posts_total")), number("At 2× or more", c.get("hits")),
            number("Flops", (nw.get("flops") or {}).get("count")), number("Formats", len(fm) if fm else "-"),
            number("Followers", short(acc.get("followers")) if acc.get("followers") is not None else "-"),
            number("Spent on data", spent(d.get("cost"), d.get("sources")))]
    order = {"scale_it": 0, "underused": 1}
    weak_ids = set(f["id"] for f in nw.get("formats") or [])        # a fading one is told under not_worked, not here
    good = sorted([f for f in fm if f.get("quadrant") in order and f["id"] not in weak_ids],
                  key=lambda f: (order[f["quadrant"]], -(f.get("lift") or 0)))
    worked = [item(f["name"], "%s: %d posts, %s of the window; %s of them at 2× or more%s%s." % (
        f["quadrant_name"], f["posts_total"], pct(f["share"]), pct(f["hit_rate"]),
        ("; %s" % f["direction_label"]) if f.get("direction_label") else "",
        "; few posts, not a finding on its own" if f.get("few_posts") else ""), "MEASURED",
        "%s its usual" % xr(f["lift"]), keys.get(f["id"])) for f in good[:2]]
    worked += from_claims(folder, fi.get("mechanisms"), 3, titles(worked))
    worked += words_items(d.get("writing"), "lifts", LIMITS["items"] - len(worked))
    not_worked = [item(f["name"], "%s: %d scored posts at %s its usual%s%s." % (
        f["quadrant_name"], f["posts_scored"] or 0, xr(f["lift"]),
        ("; %s %s later vs earlier" % (f["direction_label"], xr(f["direction"]))) if f.get("direction") is not None else "",
        ("; %d of the %d flops" % (f["flops"], nw["flops"]["count"])) if f.get("flops") else ""), "MEASURED",
        failing_stat(f, "its usual"), keys.get(f["id"])) for f in (nw.get("formats") or [])[:2]]
    not_worked += from_claims(folder, fi.get("did_not_work"), 2, titles(not_worked), failing=True)
    not_worked += words_items(d.get("writing"), "sinks", 1)
    fl = nw.get("flops") or {}
    if fl.get("count"):
        not_worked.append(item("Flops", "%d of %d scored posts" % (fl["count"], fl["of_scored"]) + (": " + ", ".join(
            "%d %s" % (b["flops"], b["name"] or "in no format") for b in fl["by_format"][:3]) if fl.get("by_format") else "")
            + ".", "MEASURED", flops_stat(fl)))
    if not not_worked:
        not_worked.append(item("Not enough data", nw["note"], "MEASURED") if nw.get("note") else
                          nothing([nw.get("formats_note"), (nw.get("flops") or {}).get("note"), (nw.get("words") or {}).get("note")]))
    answer = (fi.get("headline") or {}).get("text") or fallback or measured_answer("account", d)
    return finish(answer, nums, worked, not_worked, plays_of(fi))


def post(folder, d, key, fallback):
    pp, fi, nw = d["probe"], d["findings"] or {}, d.get("not_working") or {}
    p, rp = pp["post"], pp.get("repeats") or {}
    nums = [number("Its usual", xr(p["ratio"]) if p.get("ratio") is not None else
                   (xr(p["ratio_so_far"]) + " so far" if p.get("ratio_so_far") is not None else "-")),
            number("Usual " + (p.get("metric") or "views"), short(p.get("usual"))),
            number("Views", short(p.get("views"))),
            number("Rank", "#%s of %s" % (p["rank_among_creator"], p.get("creator_scored")) if p.get("rank_among_creator") else "-"),
            number("Repeats", ("%d more" % rp["times"]) if rp.get("format") else "-"),
            number("Spent on data", spent(d.get("cost"), d.get("sources")))]
    worked = []
    if p.get("ratio") is not None and p["ratio"] >= 1.0:
        worked.append(item("This post", "Against the median of %d other posts of its creator; #%s of %s scored." % (
            p.get("usual_from_posts") or 0, p.get("rank_among_creator"), p.get("creator_scored")), "MEASURED",
            "%s its usual" % xr(p["ratio"]), key))
    if rp.get("scored") and rp.get("above_usual"):
        worked.append(item("The format repeats", rp.get("label") or "", "MEASURED",
                           "%d of %d above its usual" % (rp["above_usual"], rp["scored"])))
    worked += from_claims(folder, fi.get("mechanisms"), LIMITS["items"] - len(worked), titles(worked))
    not_worked = []
    if nw.get("post_below"):
        not_worked.append(item("This post", "Under its creator's usual.", "MEASURED", "%s its usual" % xr(nw["post_below"]["ratio"]), key))
    rep = nw.get("repeats") or {}
    if rep.get("below"):
        not_worked.append(item("Repeats under the usual", "%d of %d scored repeats: " % (len(rep["below"]), rep["scored"]) +
                               ", ".join("%s %s" % (q["post_id"], xr(q["ratio"])) for q in rep["below"]), "MEASURED",
                               "%d under 1\u00d7, lowest %s" % (len(rep["below"]), xr(min(q["ratio"] for q in rep["below"])))))
    for x in (nw.get("words") or [])[:2]:
        not_worked.append(item(("Has: " if x["kind"] == "has" else "Lacks: ") + x["label"],
                               "The creator's posts with it sit at %s (%d posts), without it %s (%d)%s." % (
                                   xr(x["with"]["lift"]), x["with"]["posts"], xr(x["without"]["lift"]), x["without"]["posts"],
                                   "; a lead, few posts" if x["few"] else ""), "MEASURED"))
    not_worked += from_claims(folder, fi.get("did_not_work"), 2, titles(not_worked), failing=True)
    if not not_worked:
        not_worked.append(item("Not enough data", nw["note"], "MEASURED") if nw.get("note") else
                          nothing([(nw.get("repeats") or {}).get("note"), nw.get("words_note")]))
    answer = (fi.get("headline") or {}).get("text") or fallback or measured_answer("post", d)
    return finish(answer, nums, worked, not_worked, plays_of(fi))


def niche(folder, d, keys, fallback):
    fi, t, nw = d["findings"] or {}, d["trends"], d.get("not_working") or {}
    c, fm = t.get("counts") or {}, d["formats"]
    placed = [f for f in fm if f.get("niche_format")]
    nums = [number("Creators", c.get("creators")), number("Posts read", c.get("posts_read")),
            number("Scored", c.get("scored")), number("At 2× or more", c.get("hits")),
            number("Formats of the niche", len(placed)), number("Spent on data", spent(d.get("cost"), d.get("sources")))]
    weak = set(f["id"] for f in nw.get("formats") or [])
    order = {"scale_it": 0, "underused": 1, "overused": 2, "drop": 3}
    good = sorted([f for f in placed if f["id"] not in weak and f.get("lift") is not None],
                  key=lambda f: (order.get(f["quadrant"], 9), -(f.get("lift") or 0)))
    worked = [item(f["name"], "%s: %d creators, %d scored posts%s%s." % (
        f["quadrant_name"], f["creators"], f["posts_scored"],
        ("; %s %s" % (f["direction_label"], xr(f["direction"]))) if f.get("direction") is not None else "",
        "; few posts" if f.get("few_posts") else ""), "MEASURED", "%s each creator's usual" % xr(f["lift"]),
        keys.get(f["id"])) for f in good[:3]]
    names = dict((f.get("name"), f["id"]) for f in fm)

    def about_weak(cl):
        return cl.get("format") in weak or names.get(cl.get("title")) in weak
    worked += from_claims(folder, [x for x in fi.get("formats") or [] if not about_weak(x)], 2, titles(worked))
    worked += words_items(d.get("writing"), "lifts", LIMITS["items"] - len(worked), "each creator's usual")
    worked += from_claims(folder, fi.get("hooks"), LIMITS["items"] - len(worked), titles(worked))
    not_worked = [item(f["name"], "%s: %d creators, %d scored posts at %s each creator's usual%s." % (
        f["quadrant_name"], f["creators"], f["posts_scored"] or 0, xr(f["lift"]),
        ("; %s %s later vs earlier" % (f["direction_label"], xr(f["direction"]))) if f.get("direction") is not None else ""),
        "MEASURED", failing_stat(f, "each creator's usual"), keys.get(f["id"])) for f in (nw.get("formats") or [])[:3]]
    not_worked += from_claims(folder, [x for x in fi.get("formats") or [] if about_weak(x)] + list(fi.get("did_not_work") or []),
                              2, titles(not_worked), failing=True)
    not_worked += words_items(d.get("writing"), "sinks", 1, "each creator's usual")
    fl = nw.get("flops") or {}
    if fl.get("count"):
        not_worked.append(item("Flops", "%d of %d scored posts, each against its own creator's usual, from %d creators." % (
            fl["count"], fl["of_scored"], fl["creators"]), "MEASURED", flops_stat(fl)))
    if not not_worked:
        not_worked.append(item("Not enough data", nw["note"], "MEASURED") if nw.get("note") else
                          nothing([nw.get("formats_note"), fl.get("note"), (nw.get("words") or {}).get("note")]))
    answer = (fi.get("headline") or {}).get("text") or fallback or measured_answer("niche", d)
    return finish(answer, nums, worked, not_worked, plays_of(fi))


def check(b):
    """The limits, as a list of problems (empty when the brief fits). Used by the tests."""
    bad = []
    if len(b.get("answer") or "") > LIMITS["answer"]:
        bad.append("answer over %d characters" % LIMITS["answer"])
    if len(b.get("numbers") or []) > LIMITS["numbers"]:
        bad.append("more than %d numbers" % LIMITS["numbers"])
    for x in b.get("numbers") or []:
        if len(x["label"]) > LIMITS["label"] or len(x["value"]) > LIMITS["value"]:
            bad.append("number too long: %r" % x)
    for sec in ("worked", "not_worked"):
        if len(b.get(sec) or []) > LIMITS["items"]:
            bad.append("%s: more than %d" % (sec, LIMITS["items"]))
        for x in b.get(sec) or []:
            for k in ("title", "stat", "note"):
                if len(x.get(k) or "") > LIMITS[k]:
                    bad.append("%s.%s over %d: %r" % (sec, k, LIMITS[k], x.get(k)))
            if x.get("label") not in LABELS:
                bad.append("%s: label %r" % (sec, x.get("label")))
    if len(b.get("plays") or []) > LIMITS["plays"]:
        bad.append("more than %d plays" % LIMITS["plays"])
    for x in b.get("plays") or []:
        if len(x["title"]) > LIMITS["title"] or len(x["note"]) > LIMITS["note"]:
            bad.append("play too long: %r" % x["title"])
    if re.search(r"<[A-Za-z/!][^>]*>", json.dumps(b, ensure_ascii=False)):
        bad.append("not plain text: a tag")
    return bad
