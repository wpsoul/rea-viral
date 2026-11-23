"""The hand-over files for a planner connector, written by build_report.py beside every report.

    report_record.json   the report's record, for a planner tool that keeps reports (GreenLight Pulse: save_report):
                         kind (account, post, niche, words), title, subject, summary (600 characters at most), what
                         was read, the provider and the cost as the provider reported it, the skill's version, the
                         brief (the short structured view a planner's panel draws, brief.py) and the page file
                         (report.html, one file, the Extended report) with its size
    brief.json           the same brief on its own (brief.py)
    radar_rows.json      formats, for a planner tool that keeps the user's saved formats (Pulse: save_formats, its
                         Format Radar tab, Saved): a niche run writes one row per format of the niche (3 creators or
                         more) with its recipe and the links of the posts that prove it; an account run its strongest
                         format (Scale it or Underused, 6 posts or more); a post run the post's own format

The rows are in the planner's shape (references/data-shape.md, "Hand-over files"). Nothing here calls anything: the
agent sends the files when such a tool is connected (references/connections.md, "A planner connector"); without one
they are simply files. Keys are stable across rebuilds, so saving again updates a row instead of adding one.
"""
import hashlib
import os
import re

from common import SKILL_VERSION, iso, now_utc, write_json

KINDS = ("account", "post", "niche", "words")
SUMMARY_MAX = 600
TITLE_MAX = 160
SUBJECT_MAX = 300
PROVIDER_MAX = 60
ROWS_MAX = 60
NETWORK_NAMES = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube", "x": "X", "threads": "Threads",
                 "linkedin": "LinkedIn"}
CORNER_ORDER = {"scale_it": 0, "underused": 1, "overused": 2, "fading": 2, "drop": 3}


def cut(text, n):
    """Plain words, one line, at most n characters, cut at a word."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) <= n:
        return s
    s = s[:n - 1]
    if " " in s[n // 2:]:
        s = s[:s.rindex(" ")]
    return s.rstrip(" ,;:.") + "…"


def first_line(text):
    for line in str(text or "").split("\n"):
        if line.strip():
            return line.strip()
    return ""


def format_key(scope, fid):
    """A format with no single post: "f_" and 12 hex, the same on every rebuild of the same run."""
    return "f_" + hashlib.sha1(("rea-viral|%s|%s" % (scope, fid)).encode("utf-8")).hexdigest()[:12]


def post_key(network, post_id):
    """A saved post: the planner's own key, "<network>:<post id>" (Pulse's postKey)."""
    return "%s:%s" % (network, post_id)


def provider_and_cost(sources, cost):
    """The provider as the sources name it, and the cost as reported: the ledger's total when paid calls were
    logged (ledger.py); else the sources' cost_usd added up; null when a source's price is unknown."""
    vias = []
    for s in sources or []:
        v = re.sub(r"\s+", " ", str((s or {}).get("via") or "")).strip()
        if v and v not in vias:
            vias.append(v)
    provider = cut(" + ".join(vias), PROVIDER_MAX) or "agent"
    rows = (cost or {}).get("rows") or []
    if rows:
        return provider, round(float((cost or {}).get("total_usd") or 0.0), 4)
    vals = [(s or {}).get("cost_usd") for s in sources or []]
    if not vals or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in vals):
        return provider, None
    return provider, round(sum(vals), 4)


def summary_text(headline, did_not_work=None, fallback=None):
    """The answer in plain words, at most 600 characters: the agent's headline, then its first "did not work" line."""
    s = cut((headline or {}).get("text") or fallback or "", SUMMARY_MAX)
    dnw = (did_not_work or [None])[0] if did_not_work else None
    extra = cut((dnw or {}).get("text") or "", SUMMARY_MAX)
    if s and extra and len(s) + len(extra) + 20 <= SUMMARY_MAX:
        s = s + " What did not work: " + extra
    return cut(s, SUMMARY_MAX)


def light_file(page_path, run_name):
    p = os.path.join(os.path.dirname(page_path), "report-light.html")
    if not os.path.exists(p):
        return None
    return {"path": "report-light.html", "name": "rea-viral-%s.html" % run_name, "type": "text/html",
            "size": os.path.getsize(p)}


def record(kind, title, subject, summary, read, sources, cost, page_path, run_name, rows_n, brief=None, cover=None):
    assert kind in KINDS
    provider, usd = provider_and_cost(sources, cost)
    subj = dict((k, cut(v, SUBJECT_MAX)) for k, v in (subject or {}).items() if v not in (None, ""))
    return {
        "schema": "rea-viral/report-record@1",
        "note": "The record for a planner tool that keeps reports (references/connections.md, 'A planner connector'). "
                "Send `report` with the page (`file`); add `by` (your own name) and, when you timed the run, `took_s`. "
                "The planner adds the id, the file and the dates. `report.brief` is the short view a planner's panel "
                "draws (the same as brief.json). The page: `file` (report.html, the full report with its pictures, to "
                "send by path or upload) or `light` (report-light.html, no pictures, to send as text from a chat). "
                "`cover`: the report's picture, to upload as its cover. For a words-only run set `kind` to \"words\".",
        "built_at": iso(now_utc()),
        "report": {
            "kind": kind, "title": cut(title, TITLE_MAX), "subject": subj, "summary": summary,
            "read": dict((k, v) for k, v in (read or {}).items() if isinstance(v, int)),
            "provider": provider, "cost_usd": usd,
            "skill": {"name": "rea-viral", "version": SKILL_VERSION},
        },
        "brief_file": "brief.json" if brief is not None else None,
        "file": {"path": "report.html", "name": "rea-viral-%s.html" % run_name, "type": "text/html",
                 "size": os.path.getsize(page_path) if os.path.exists(page_path) else None},
        "light": light_file(page_path, run_name),
        "cover": dict(cover, name="rea-viral-%s-cover%s" % (run_name, os.path.splitext(cover["path"])[1])) if cover else None,
        "formats": {"file": "radar_rows.json", "rows": rows_n},
    }


def clock(sec):
    """A beat's time as the planner keeps it: text, minutes and seconds ("0:02", "0:02.2", "1:05")."""
    t10 = int(round(float(sec) * 10))
    m, s10 = t10 // 600, t10 % 600
    return ("%d:%02d" % (m, s10 // 10)) if s10 % 10 == 0 else ("%d:%02d.%d" % (m, s10 // 10, s10 % 10))


def beats_of(recipe):
    """The recipe's beats as the planner keeps them (its model: t is text, at most 20 characters; d a number of
    seconds, 0 or more; what text, at most 300): t "0:02.2", d how long until the next beat, what "hook: …"."""
    rec = recipe or {}
    bs = [b for b in rec.get("beats") or [] if isinstance(b, dict) and isinstance(b.get("at"), (int, float))]
    bs.sort(key=lambda b: b["at"])
    out = []
    for i, b in enumerate(bs):
        end = bs[i + 1]["at"] if i + 1 < len(bs) else rec.get("length_s")
        what = ": ".join(x for x in (str(b.get("what") or "").strip(), str(b.get("text") or "").strip()) if x)
        row = {"t": clock(b["at"]), "what": cut(what, 300)}
        if isinstance(end, (int, float)) and end > b["at"]:
            row["d"] = round(float(end) - float(b["at"]), 2)
        out.append(row)
    return out


def numbers_of(post, followers, at):
    n = dict((k, post.get(k)) for k in ("views", "likes", "comments", "shares", "saves") if isinstance(post.get(k), int))
    if isinstance(followers, int):
        n["followers"] = followers
    n["at"] = at
    return n


def format_row(key, f, recipe, best, niche=None, creators=None, trend=None, proof=None):
    """One planner row for a format: the format's best post is the row's face (link, numbers, caption); `format`
    holds what makes it a format. state "link": only the link is kept until the user's planner saves its media."""
    rec = recipe or {}
    fm = {"name": cut(f.get("name") or f.get("id"), 160)}
    if niche:
        fm["niche"] = cut(niche, 160)
    if creators is not None:
        fm["creators"] = creators
    if f.get("lift") is not None:
        fm["lift"] = f.get("lift")
    if trend in ("rising", "fading", "steady"):
        fm["trend"] = trend
    beats = beats_of(rec)
    if beats:
        fm["beats"] = beats
    hook = rec.get("hook_pattern") or (f.get("container") or {}).get("hook")
    if hook:
        fm["hook"] = cut(hook, 1000)
    if proof:
        fm["proof"] = [u for u in proof if u and len(u) <= 2000][:20]
    row = {"key": key, "source": "report", "url": best.get("url"), "platform": best.get("network"),
           "post_id": best.get("post_id"), "creator": ("@" + best["account"]) if best.get("account") else None,
           "title": cut(f.get("name") or f.get("id"), 300), "text": str(best.get("caption") or "")[:5000],
           "state": "link", "numbers": best.get("numbers") or {}, "format": fm}
    return dict((k, v) for k, v in row.items() if v not in (None, ""))


def write(folder, kind, rec_args, rows, note, brief=None, cover=None):
    """Write radar_rows.json, brief.json, then report_record.json (it counts the rows and carries the brief as
    report.brief). Returns (record, rows)."""
    rows = rows[:ROWS_MAX]
    write_json(os.path.join(folder, "radar_rows.json"), {
        "schema": "rea-viral/radar-rows@1", "kind": kind, "built_at": iso(now_utc()),
        "note": note, "rows": rows})
    if brief is not None:
        write_json(os.path.join(folder, "brief.json"), brief)
    rec = record(kind, rows_n=len(rows), brief=brief, cover=cover, **rec_args)
    if brief is not None:
        rec["report"]["brief"] = dict((k, v) for k, v in brief.items() if k != "schema")
    write_json(os.path.join(folder, "report_record.json"), rec)
    return rec, rows


def trend_of(direction_label):
    return {"rising": "rising", "fading": "fading", "weakening": "fading", "steady": "steady"}.get(direction_label)


def sort_formats(fm):
    return sorted(fm, key=lambda f: (CORNER_ORDER.get(f.get("quadrant"), 9), -(f.get("lift") or 0)))
