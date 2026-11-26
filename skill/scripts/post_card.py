#!/usr/bin/env python3
"""The post picture: a run's numbers as a 1080 x 1350 card for X, Threads and Instagram, in one of 7 styles and 10
layouts (references/post.md).

    python3 post_card.py <run folder> [--layout t1..t5|r1..r5|all] [--skin cobalt|redword|night|holo|paper|warm|glass|all]
                         [--card card.json] [--out post-card.png] [--scale 1] [--browser chrome|chromium|<path>]
                         [--html-only] [--check]

Two kinds of card, picked from the folder:
- an account teardown (an account run with growth mode: growth.json, findings.json "growth"): layouts t1 to t5;
- a niche report (a niche run: niche.json, radar.json, writing.json): layouts r1 to r5.

What goes on the card is the run folder's card.json: your short lines, with every number written as a placeholder the
script fills, exactly as in findings.json "growth": {key} or {key:fmt} names a key of growth.json (teardown); a niche
card names formats ("format": "<radar.json id>") and writing features ("feature": "<writing.json id>") and the script
puts in their lifts. With no card.json the script writes a draft from the run (the mechanisms and their numbers, or the
niche's formats by lift), renders it, and asks you to rewrite the lines.

The rules it checks (exit 1 with the line to fix): every placeholder names a real key; the big numbers ("n", "tag")
come from placeholders only; a quote ("...") is the post's own words (posts.csv caption, its parts, the author's
replies); no he, him, his, she or her for the account owner (they, or the account); a niche card shows only formats of
the niche (3 creators or more) and features with 6 posts and 3 creators or more, "works" at 1x or more and "doesn't"
under it. A number typed in a line is a warning: check it is the run's.

Out: post-card.html (one file: its fonts and icon inside, opens anywhere) and post-card.png beside it, in the run folder
(--out to name the PNG); with --layout all or --skin all, post-cards/<skin>-<layout>.png. The picture is made by
render_card.mjs (Node 18+ and Playwright, as the Basic remake); each card shrinks long text until it fits and the
render fails when something still spills. Default style: cobalt. Default layout: card.json's, else t1 or r2.
Exit 0 = made and fits; 1 = a rule fails or a card does not fit (it says what); 2 = the run or card.json cannot be read,
or the PNG cannot be made here (the HTML is written; it says what to install).
"""
import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, read_csv, read_json, script_dir, write_json, write_text  # noqa: E402
import growth as G  # noqa: E402  (the same placeholders and number formats as findings.json "growth")

SKINS = ("cobalt", "redword", "night", "holo", "paper", "warm", "glass")
LAYOUTS = {"teardown": ("t1", "t2", "t3", "t4", "t5"), "report": ("r1", "r2", "r3", "r4", "r5")}
LAYOUT_NAMES = {"t1": "Scorecard", "t2": "2x2 numbers", "t3": "Hero number + checklist", "t4": "The proof post",
                "t5": "Numbered editorial", "r1": "Diverging bars", "r2": "Works | Doesn't", "r3": "Ranked, number first",
                "r4": "The winner + the rest", "r5": "Dot plot"}
DEFAULT_LAYOUT = {"teardown": "t1", "report": "r2"}
FAMILY = {"cobalt": "Poppins", "redword": "Red Hat Display", "holo": "Archivo", "night": "Inter Tight",
          "paper": "Inter Tight", "warm": "Inter Tight", "glass": "Inter Tight"}
# one glass icon per layout (as the template's gallery); Red Word has its own red set; none on the light styles for now
ICON = {"t1": "key", "t2": "arrow-up", "t3": "arrow-up", "t4": "bubble", "t5": "king",
        "r1": "arrow-up", "r2": "key", "r3": "king", "r4": "arrow-up", "r5": "bubble"}
RED = {"key": "cursor", "king": "cursor", "arrow-up": "arrow-up", "bubble": "bubble"}
NO_ICON = ("holo", "paper", "warm", "glass")
NETWORK = {"x": "X", "threads": "Threads", "tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube",
           "linkedin": "LinkedIn"}
NICHE_NETWORK = dict(NETWORK, youtube="YouTube Shorts")
GLYPH = {"x": "\U0001D54F"}   # the X mark; other networks show their name
TEMPLATE_DIR = os.path.join(script_dir(), "..", "templates", "post")
MONTHS_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]

ITEM_FIELDS = ("n", "unit", "line", "sub", "short", "tag", "say", "chip")
STRICT_FIELDS = ("n", "tag")            # the big numbers: placeholders only
MAX_ITEMS = 4
PROOF_CHARS = 300                       # the proof post's words, cut at a word with "…" past this
PRONOUN_RE = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.I)
QUOTE_RE = re.compile(r"[“\"]([^”\"]{2,}?)[”\"]")
TYPED_RE = re.compile(r"\d[\d.,:]*")
X_RE = re.compile(r"(\d)x\b")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ONE_TO_ONE = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def norm(s):
    s = (s or "").translate(ONE_TO_ONE).replace("…", "...")
    return re.sub(r"\s+", " ", s).strip().lower()


def md(s):
    """The run's words as safe HTML: escaped, then **bold** only."""
    return BOLD_RE.sub(r"<b>\1</b>", html.escape(s or "", quote=False))


def short_date(value):
    try:
        y, m, d = str(value)[:10].split("-")
        return "%s %d" % (G.MONTHS[int(m) - 1], int(d))
    except (ValueError, IndexError):
        return ""


def window_text(w):
    w = w or {}
    a, b = short_date(w.get("from")), short_date(w.get("to"))
    return "%s – %s" % (a, b) if a and b else ""


def lift_text(v):
    return "%.2f×" % float(v)


class Card:
    """Reads one run, checks the card's lines, and builds the data the template draws."""

    def __init__(self, folder):
        self.folder = folder
        self.errors, self.warnings = [], []
        self.corpus = ""

    # ------------------------------------------------------------------ the rules every line meets
    def lint(self, where, raw, strict=False):
        bare = G.PLACEHOLDER_RE.sub("", raw)
        for q in QUOTE_RE.findall(bare):
            if norm(q) not in self.corpus:
                self.errors.append("%s: the quote \"%s\" is not in the posts' own words (their caption, parts or the "
                                   "author's replies): quote the post exactly, or say it without quote marks" % (where, q))
        outside = QUOTE_RE.sub("", bare)
        m = PRONOUN_RE.search(outside)
        if m:
            self.errors.append("%s: \"%s\": no he, his, she or her for the account owner: say they, or the account" % (where, m.group(0)))
        typed = TYPED_RE.findall(outside)
        if typed:
            msg = "%s: the number %s is typed: write it as a placeholder so it is the run's" % (where, ", ".join(typed))
            (self.errors if strict else self.warnings).append(msg if strict else msg + " (or check it is)")

    def load_corpus(self, post_files):
        words = []
        for p in post_files:
            try:
                rows = read_csv(p)[1]
            except (OSError, ValueError, IndexError):
                continue
            for r in rows:
                words += [r.get("caption") or "", r.get("parts") or "", r.get("author_replies") or ""]
        self.corpus = norm(" \n ".join(words))

    # ------------------------------------------------------------------ an account teardown
    def teardown(self, spec):
        f = self.folder
        try:
            g = read_json(os.path.join(f, "growth.json"))
        except (OSError, ValueError) as e:
            die("no growth.json in %s (%s): a teardown card needs growth mode (references/growth.md)" % (f, e))
        try:
            acc = read_json(os.path.join(f, "account.json"))
        except (OSError, ValueError):
            acc = {}
        self.g = g
        ga = g.get("account") or {}
        handle = acc.get("handle") or ga.get("handle") or ""
        net = acc.get("network") or ga.get("network") or ""
        rows = []
        try:
            rows = read_csv(os.path.join(f, "posts.csv"))[1]
        except (OSError, ValueError, IndexError):
            self.warnings.append("posts.csv cannot be read: quotes cannot be checked and the proof post has no words")
        self.posts = dict((r.get("post_id"), r) for r in rows)
        self.load_corpus([os.path.join(f, "posts.csv")])
        n_posts = len(g.get("posts") or {})
        netname = NETWORK.get(net, net)
        window = window_text(ga.get("window") or acc.get("window"))
        name = (acc.get("name") or handle or "").strip()
        initial = next((c.upper() for c in name if c.isalnum()), "@")
        followers = acc.get("followers") if acc.get("followers") is not None else ga.get("followers")
        d = {"type": "teardown", "kicker": "Teardown", "title": "Why <b>@%s</b> is growing" % html.escape(handle),
             "t1": {"title": "Why it’s <b>growing</b>"},
             "t2": {"sub": "%d posts on %s%s, each against the account’s own normal." % (n_posts, netname, (", " + window) if window else "")},
             "account": {"name": html.escape(name), "handle": "@" + html.escape(handle), "initial": html.escape(initial),
                         "followers": G.compact(followers) if isinstance(followers, (int, float)) else "",
                         "window": window, "glyph": GLYPH.get(net, html.escape(netname))},
             "foot": "1× = the account’s normal · %d posts on %s" % (n_posts, netname), "brand": "Made with <b>REA Viral</b>"}
        for k in ("kicker", "title"):
            if spec.get(k):
                d[k] = self.text(k, spec[k])
        if spec.get("sub"):
            d["t2"]["sub"] = self.text("sub", spec["sub"])
        for lid in LAYOUTS["teardown"]:
            for k, v in (spec.get(lid) or {}).items() if isinstance(spec.get(lid), dict) else []:
                if k in ("kicker", "title", "sub"):
                    d.setdefault(lid, {})[k] = self.text("%s.%s" % (lid, k), v)
        items = spec.get("items") or []
        if not isinstance(items, list) or not items:
            self.errors.append("items: write 3 or 4 items, best first (references/post.md)")
            items = []
        if len(items) > MAX_ITEMS:
            self.errors.append("items: %d items; a card holds %d at most" % (len(items), MAX_ITEMS))
        elif 0 < len(items) < 3:
            self.warnings.append("items: %d items; the layouts are made for 3 or 4" % len(items))
        d["items"] = [self.item("items[%d]" % i, it) for i, it in enumerate(items[:MAX_ITEMS])]
        d["miss"] = self.item("miss", spec["miss"]) if spec.get("miss") else None
        if spec.get("hero"):
            h = spec["hero"]
            d["hero"] = {"n": self.text("hero.n", h.get("n"), strict=True), "line": self.text("hero.line", h.get("line"))}
            if not h.get("n"):
                self.errors.append("hero: needs n (its number, as a placeholder)")
        if spec.get("proof"):
            d["proof"] = self.proof(spec["proof"], d["items"])
        return d

    def text(self, where, raw, strict=False):
        if raw is None or raw == "":
            return ""
        raw = str(raw)
        filled, problems, _ = G.fill(raw, self.g)
        self.errors += ["%s: %s" % (where, p) for p in problems]
        self.lint(where, raw, strict)
        return md(X_RE.sub("\\1×", filled))

    def item(self, where, it):
        if not isinstance(it, dict):
            self.errors.append("%s: an item is an object with n, unit, line, sub ..." % where)
            return {}
        out = {}
        for k in ITEM_FIELDS:
            if it.get(k) not in (None, ""):
                out[k] = self.text("%s.%s" % (where, k), it[k], strict=k in STRICT_FIELDS)
        for lid in LAYOUTS["teardown"]:
            if isinstance(it.get(lid), dict):
                out[lid] = dict((k, self.text("%s.%s.%s" % (where, lid, k), v, strict=k in STRICT_FIELDS))
                                for k, v in it[lid].items() if k in ITEM_FIELDS)
        for k in ("n", "line"):
            if not it.get(k):
                self.errors.append("%s: needs %s" % (where, k))
        unknown = [k for k in it if k not in ITEM_FIELDS and k not in LAYOUTS["teardown"]]
        if unknown:
            self.warnings.append("%s: %s not used (an item takes %s, and per-layout overrides t1 to t5)" % (where, ", ".join(unknown), ", ".join(ITEM_FIELDS)))
        return out

    def proof(self, p, items):
        pid = str(p.get("post") or "")
        gp = (self.g.get("posts") or {}).get(pid)
        if not gp:
            self.errors.append("proof.post: %r is not a post of growth.json (write the post id)" % pid)
            return None
        words = (self.posts.get(pid) or {}).get("caption") or ""
        if not words:
            self.errors.append("proof.post: post %s has no caption in posts.csv" % pid)
        if len(words) > PROOF_CHARS:
            cut = words[:PROOF_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:")
            words = cut + "…"
        marks = [m for m in (p.get("mark") or []) if isinstance(m, str) and m.strip()]
        spans, low = [], words.translate(ONE_TO_ONE).lower()
        for m in marks:
            i = low.find(m.translate(ONE_TO_ONE).lower())
            if i < 0:
                self.errors.append("proof.mark: \"%s\" is not in the post's words%s" % (m, " (as cut to %d characters)" % PROOF_CHARS if words.endswith("…") else ""))
            else:
                spans.append((i, i + len(m)))
        spans.sort()
        out, at = [], 0
        for a, b in spans:
            if a < at:
                continue
            out.append(html.escape(words[at:a], quote=False))
            out.append("<mark>%s</mark>" % html.escape(words[a:b], quote=False))
            at = b
        out.append(html.escape(words[at:], quote=False))
        stats = []
        for key, label in (("replies", "replies"), ("bookmarks", "bookmarks"), ("reposts", "reposts"), ("views", "views")):
            v = gp.get(key)
            if isinstance(v, (int, float)) and (v or key in ("replies", "views")):
                stats.append([G.compact(v), label])
        if len(stats) > 3:
            stats = [s for s in stats if s[1] != "reposts"][:3]
        chips = []
        want = p.get("chips")
        if want is None:
            skip = (p.get("item") or 0) - 1
            want = [i + 1 for i in range(len(items)) if i != skip][:3]
        for j, c in enumerate(want[:3] if isinstance(want, list) else []):
            if isinstance(c, int):
                if not 1 <= c <= len(items):
                    self.errors.append("proof.chips[%d]: there is no item %d" % (j, c))
                    continue
                it = dict(items[c - 1], **(items[c - 1].get("t4") or {}))
                chips.append({"n": it.get("n", ""), "text": it.get("chip") or it.get("unit") or ""})
            elif isinstance(c, dict):
                chips.append({"n": self.text("proof.chips[%d].n" % j, c.get("n"), strict=True), "text": self.text("proof.chips[%d].text" % j, c.get("text"))})
        return {"date": short_date(gp.get("at")), "text": "".join(out), "stats": stats,
                "caption": self.text("proof.caption", p.get("caption")), "chips": chips}

    # ------------------------------------------------------------------ a niche report
    def report(self, spec):
        f = self.folder
        try:
            radar = read_json(os.path.join(f, "radar.json"))
        except (OSError, ValueError) as e:
            die("no radar.json in %s (%s): a niche card needs radar.py first (references/niche.md)" % (f, e))
        writing = {}
        if os.path.exists(os.path.join(f, "writing.json")):
            writing = read_json(os.path.join(f, "writing.json"))
        niche = read_json(os.path.join(f, "niche.json")) if os.path.exists(os.path.join(f, "niche.json")) else {}
        accounts = os.path.join(f, "accounts")
        self.load_corpus([os.path.join(accounts, a, "posts.csv") for a in (sorted(os.listdir(accounts)) if os.path.isdir(accounts) else [])])
        self.formats = dict((x.get("id"), x) for x in radar.get("formats") or [])
        self.features = dict((x.get("id"), x) for x in writing.get("features") or [])
        st = writing.get("settings") or {}
        self.min_posts, self.min_creators = st.get("min_posts") or 6, st.get("min_creators") or 3
        counts = radar.get("counts") or {}
        creators, scored = counts.get("creators_scored") or 0, counts.get("scored") or 0
        nets = niche.get("networks") or (radar.get("subject") or {}).get("networks") or []
        netname = NICHE_NETWORK.get(nets[0], nets[0]) if nets else ""
        topic = niche.get("name") or (radar.get("subject") or {}).get("niche") or "this niche"
        window = window_text(radar.get("window") or niche.get("window"))
        d = {"type": "report", "kicker": "Save this",
             "title": "What works for <b>%s</b>%s right now" % (html.escape(topic), (" on " + netname) if netname else ""),
             "r1": {"sub": "Each post against its creator’s own usual. Right of the line = above it."},
             "r3": {"sub": "%d creators, %d posts%s. Ranked by how far each beats its creator’s usual." % (creators, scored, (", " + window) if window else "")},
             "r5": {"sub": "Where each lands against its creator’s usual (the white line)."},
             "foot": "1× = each creator’s own usual · %d creators · %d posts" % (creators, scored), "brand": "Measured with <b>REA Viral</b>"}
        for k in ("kicker", "title"):
            if spec.get(k):
                d[k] = self.rtext(k, spec[k], {})
        for lid in LAYOUTS["report"]:
            for k, v in (spec.get(lid) or {}).items() if isinstance(spec.get(lid), dict) else []:
                if k in ("kicker", "title", "sub", "winner", "winner_k"):
                    d.setdefault(lid, {})[k] = self.rtext("%s.%s" % (lid, k), v, {})
        works = [x for x in (self.entry("works[%d]" % i, w) for i, w in enumerate(spec.get("works") or [])) if x]
        doesnt = [x for x in (self.entry("doesnt[%d]" % i, w) for i, w in enumerate(spec.get("doesnt") or [])) if x]
        for x in works:
            if x["v"] < 1:
                self.errors.append("%s: %s is under 1x: it goes in doesnt" % (x["where"], x["n"]))
        for x in doesnt:
            if x["v"] >= 1:
                self.errors.append("%s: %s is 1x or more: it goes in works" % (x["where"], x["n"]))
        for name, lst in (("works", works), ("doesnt", doesnt)):
            if len(lst) > MAX_ITEMS:
                self.errors.append("%s: %d items; a card holds %d at most" % (name, len(lst), MAX_ITEMS))
        if not works:
            self.errors.append("works: at least one format or feature at 1x or more")
        elif len(works) + len(doesnt) < 2:
            self.errors.append("works and doesnt hold %d item: a card needs 2 or more" % (len(works) + len(doesnt)))
        works.sort(key=lambda x: -x["v"])
        doesnt.sort(key=lambda x: -x["v"])
        d["works"] = [dict((k, v) for k, v in x.items() if k != "where") for x in works[:MAX_ITEMS]]
        d["doesnt"] = [dict((k, v) for k, v in x.items() if k != "where") for x in doesnt[:MAX_ITEMS]]
        tip = self.entry("tip", spec["tip"]) if spec.get("tip") else None
        d["tip"] = dict((k, v) for k, v in tip.items() if k not in ("where", "v")) if tip else None
        if works:
            d["winner_k"] = "#1 format" if works[0]["kind"] == "format" else "#1 writing habit"
        if spec.get("winner"):
            d["winner"] = self.rtext("winner", spec["winner"], works[0]["ctx"] if works else {})
        for x in d["works"] + d["doesnt"]:
            x.pop("ctx", None)
            x.pop("kind", None)
        if d.get("tip"):
            d["tip"].pop("ctx", None)
            d["tip"].pop("kind", None)
        return d

    def rtext(self, where, raw, ctx):
        if raw is None or raw == "":
            return ""
        raw = str(raw)

        def sub(m):
            key, fm = m.group(1), m.group(2)
            if key not in ctx:
                self.errors.append("%s: {%s}: not a number of this item (it has %s)" % (where, key, ", ".join(sorted(ctx)) or "none"))
                return m.group(0)
            try:
                return G.fmt_value(ctx[key], fm)
            except ValueError as e:
                self.errors.append("%s: {%s}: %s" % (where, key, e))
                return m.group(0)
        filled = G.PLACEHOLDER_RE.sub(sub, raw)
        self.lint(where, raw)
        return md(X_RE.sub("\\1×", filled))

    def entry(self, where, w):
        if not isinstance(w, dict):
            self.errors.append("%s: write {\"format\": \"<radar.json id>\"} or {\"feature\": \"<writing.json id>\"}, and a label" % where)
            return None
        if w.get("format"):
            x = self.formats.get(w["format"])
            if not x:
                self.errors.append("%s: radar.json has no format %r" % (where, w["format"]))
                return None
            if x.get("lift") is None:
                self.errors.append("%s: format %r has no lift (not scored)" % (where, w["format"]))
                return None
            if not x.get("niche_format"):
                self.errors.append("%s: %r is a %s (%s creators): a niche card shows only formats of the niche, 3 creators or more"
                                   % (where, w["format"], x.get("scope_status") or "creator habit", x.get("creators")))
            if x.get("few_posts"):
                self.errors.append("%s: %r has few posts (%s scored): not a finding" % (where, w["format"], x.get("posts_scored")))
            kind, v, label = "format", float(x["lift"]), x.get("name") or w["format"]
            ctx = {"lift": v, "posts": x.get("posts_scored"), "creators": x.get("creators"), "hit_rate": x.get("hit_rate"),
                   "direction": x.get("direction_label")}
        elif w.get("feature"):
            x = self.features.get(w["feature"])
            if not x:
                self.errors.append("%s: writing.json has no feature %r" % (where, w["feature"]))
                return None
            wi, wo = x.get("with") or {}, x.get("without") or {}
            if wi.get("lift") is None:
                self.errors.append("%s: feature %r has no lift" % (where, w["feature"]))
                return None
            if (wi.get("posts") or 0) < self.min_posts or (x.get("creators_with") or 0) < self.min_creators:
                self.errors.append("%s: feature %r is in %s posts by %s creators: a niche card needs %d posts and %d creators"
                                   % (where, w["feature"], wi.get("posts"), x.get("creators_with"), self.min_posts, self.min_creators))
            if x.get("verdict") not in ("lifts", "sinks"):
                self.warnings.append("%s: feature %r: %s (not a clear lift or sink): say so, or leave it out" % (where, w["feature"], x.get("verdict")))
            kind, v, label = "feature", float(wi["lift"]), x.get("label") or w["feature"]
            ctx = {"lift": v, "posts": wi.get("posts"), "creators": x.get("creators_with"), "without": wo.get("lift")}
        else:
            self.errors.append("%s: name a \"format\" or a \"feature\"" % where)
            return None
        ctx = dict((k, val) for k, val in ctx.items() if val is not None)
        out = {"where": where, "kind": kind, "ctx": ctx, "v": round(v, 3), "n": lift_text(v),
               "label": self.rtext(where + ".label", w["label"], ctx) if w.get("label") else md(label)}
        for lid in LAYOUTS["report"]:
            if isinstance(w.get(lid), dict) and w[lid].get("label"):
                out[lid] = {"label": self.rtext("%s.%s.label" % (where, lid), w[lid]["label"], ctx)}
        return out


# ---------------------------------------------------------------------------------------------- drafts from the run

NUMBER_FOR = (   # the growth.json part a mechanism cites → its big number and the words under it
    ("cadence.change_point", "{cadence.change_point.before} → {cadence.change_point.after}", "posts a week"),
    ("crowd_calls", "{crowd_calls.top.replies}", "replies, {crowd_calls.top.views} views"),
    ("repost_graph.best_tagged", "{repost_graph.best_tagged.reposted} of {repost_graph.best_tagged.tagged}", "tagged accounts reposted"),
    ("repost_graph.biggest", "{repost_graph.biggest.followers}", "followers: the biggest account that reposted"),
    ("speed", "{speed.top.minutes:min} min", "after the original"),
    ("replies_out", "{replies_out.count}", "replies to others in the window read"),
    ("concentration", "{concentration.top_slice.share:pct}", "of the views in {concentration.top_slice.n} posts"),
    ("flops", "{flops.format.lift:x}", "{flops.format.hits} hits in {flops.format.posts} posts"),
)


def draft_number(g, claim):
    key = (claim.get("from") or "").split("#", 1)[-1]
    for prefix, n, unit in NUMBER_FOR:
        if key.startswith(prefix) and not G.fill(n, g)[1] and not G.fill(unit, g)[1]:
            return n, unit
    for m in G.PLACEHOLDER_RE.finditer(claim.get("text") or ""):
        if not G.fill(m.group(0), g)[1]:
            return m.group(0), ""
    return "", ""


def draft_teardown(folder):
    g = read_json(os.path.join(folder, "growth.json"))
    fp = os.path.join(folder, "findings.json")
    fi = (read_json(fp).get("growth") if os.path.exists(fp) else None) or {}
    why, dm = fi.get("why_it_grows") or [], fi.get("doesnt_move") or []
    if not why:
        return None

    def item(c):
        n, unit = draft_number(g, c)
        it = {"n": n, "unit": unit, "line": c.get("title") or "", "short": c.get("title") or ""}
        q = c.get("quote") if isinstance(c.get("quote"), list) else ([c["quote"]] if c.get("quote") else [])
        if q:
            it["sub"] = "“%s”" % q[0]
        return it
    spec = {"schema": "rea-viral/card@1", "type": "teardown", "layout": "t1", "skin": "cobalt",
            "items": [item(c) for c in why[:MAX_ITEMS]]}
    if dm:
        spec["miss"] = item(dm[0])
    months = sorted((g.get("cadence") or {}).get("months") or {})
    if len(months) >= 2:
        a, b = months[-1], months[-2]
        spec["hero"] = {"n": "{cadence.months.%s.views}" % a,
                        "line": "views in %s, from **{cadence.months.%s.views}** in %s" % (MONTHS_FULL[int(a[5:7]) - 1], b, MONTHS_FULL[int(b[5:7]) - 1])}
    pick = next((i for i, c in enumerate(why[:MAX_ITEMS]) if (c.get("from") or "").split("#")[-1].startswith("crowd_calls")), 0)
    c = why[pick]
    pid = next((x for x in c.get("posts") or [] if x in (g.get("posts") or {})), None)
    if pid:
        q = c.get("quote") if isinstance(c.get("quote"), list) else []
        spec["proof"] = {"post": pid, "mark": q, "item": pick + 1, "caption": c.get("title") or ""}
    return spec


def draft_report(folder):
    radar = read_json(os.path.join(folder, "radar.json"))
    writing = read_json(os.path.join(folder, "writing.json")) if os.path.exists(os.path.join(folder, "writing.json")) else {}
    st = writing.get("settings") or {}
    mp, mc = st.get("min_posts") or 6, st.get("min_creators") or 3
    cand = []
    for x in radar.get("formats") or []:
        if x.get("niche_format") and not x.get("few_posts") and x.get("lift") is not None:
            cand.append((float(x["lift"]), {"format": x["id"], "label": x.get("name") or x["id"]}))
    for x in writing.get("features") or []:
        wi = x.get("with") or {}
        if x.get("verdict") in ("lifts", "sinks") and wi.get("lift") is not None and (wi.get("posts") or 0) >= mp and (x.get("creators_with") or 0) >= mc:
            cand.append((float(wi["lift"]), {"feature": x["id"], "label": x.get("label") or x["id"]}))
    cand.sort(key=lambda c: -c[0])
    return {"schema": "rea-viral/card@1", "type": "report", "layout": "r2", "skin": "cobalt",
            "works": [c[1] for c in cand if c[0] >= 1][:MAX_ITEMS], "doesnt": [c[1] for c in cand if c[0] < 1][:MAX_ITEMS]}


# ---------------------------------------------------------------------------------------------- the page and the picture

def data_uri(path, mime):
    with open(path, "rb") as fh:
        return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))


def font_css(skin):
    fam = FAMILY[skin]
    out = []
    for rule in open(os.path.join(TEMPLATE_DIR, "fonts", "fonts.css"), encoding="utf-8").read().splitlines():
        if "font-family:'%s'" % fam not in rule:
            continue
        m = re.search(r"url\(([^)]+)\)", rule)
        out.append(rule.replace(m.group(0), "url(%s)" % data_uri(os.path.join(TEMPLATE_DIR, "fonts", m.group(1)), "font/woff2")))
    return "\n".join(out)


def icon_uri(layout, skin):
    n = ICON.get(layout)
    if not n or skin in NO_ICON:
        return None
    name = ("red-" + RED[n]) if skin == "redword" else ("cobalt-" + n)
    return data_uri(os.path.join(TEMPLATE_DIR, "icons", name + ".png"), "image/png")


def page(d, layout, skin):
    tpl = open(os.path.join(TEMPLATE_DIR, "card.html"), encoding="utf-8").read()
    data = dict(d, layout=layout, skin=skin, icon=icon_uri(layout, skin))
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    link = '<link rel="stylesheet" href="fonts/fonts.css" id="rea-fonts">'
    slot = '<script type="application/json" id="rea-card">null</script>'
    if link not in tpl or slot not in tpl:
        die("the template %s has lost its font link or its data slot" % os.path.join(TEMPLATE_DIR, "card.html"))
    tpl = tpl.replace(link, '<style id="rea-fonts">\n%s\n</style>' % font_css(skin))
    return tpl.replace(slot, '<script type="application/json" id="rea-card">%s</script>' % js)


def render(pairs, scale, browser):
    node = shutil.which("node")
    if not node:
        return None, "node is not on PATH (Node 18+ makes the PNG)"
    cmd = [node, os.path.join(script_dir(), "render_card.mjs")]
    for h, p in pairs:
        cmd += [h, p]
    cmd += ["--scale", str(scale)] + (["--browser", browser] if browser else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    if r.returncode == 2 or not out:
        return None, (r.stderr or r.stdout).strip() or "render_card.mjs gave nothing"
    return out, None


def kind_of(folder, want):
    if want:
        return want
    if os.path.exists(os.path.join(folder, "niche.json")):
        return "report"
    if os.path.exists(os.path.join(folder, "growth.json")):
        return "teardown"
    if os.path.exists(os.path.join(folder, "post.json")):
        die("a post run has no card yet: a card is an account teardown (growth mode) or a niche report")
    die("%s has no growth.json (an account run with growth mode) and no niche.json (a niche run)" % folder)


def main(argv):
    ap = argparse.ArgumentParser(description="The post picture of a run (references/post.md).")
    ap.add_argument("folder")
    ap.add_argument("--type", choices=("teardown", "report"))
    ap.add_argument("--layout", help="t1..t5 (teardown), r1..r5 (report), or all")
    ap.add_argument("--skin", help="cobalt (default), redword, night, holo, paper, warm, glass, or all")
    ap.add_argument("--card", help="the card's lines (default: <run>/card.json; written as a draft when missing)")
    ap.add_argument("--out", help="the PNG (default: <run>/post-card.png)")
    ap.add_argument("--scale", type=float, default=1, help="pixel density: 2 gives 2160 x 2700")
    ap.add_argument("--browser")
    ap.add_argument("--html-only", action="store_true", help="write the HTML, make no PNG")
    ap.add_argument("--check", action="store_true", help="check the card's lines only, write nothing")
    a = ap.parse_args(argv)
    folder = os.path.abspath(a.folder)
    if not os.path.isdir(folder):
        die("no such folder: " + folder)
    kind = kind_of(folder, a.type)
    card_path = os.path.abspath(a.card) if a.card else os.path.join(folder, "card.json")
    drafted = False
    if os.path.exists(card_path):
        try:
            spec = read_json(card_path)
        except ValueError as e:
            die("%s does not parse: %s" % (card_path, e))
    elif a.card:
        die("no such card file: " + card_path)
    else:
        spec = draft_teardown(folder) if kind == "teardown" else draft_report(folder)
        if spec is None:
            die("no card.json and nothing to draft it from: findings.json has no \"growth\" reading (growth.md, step 4); "
                "write card.json yourself (references/post.md)", 1)
        drafted = True
        if not a.check:
            write_json(card_path, spec)
    if spec.get("type") and spec["type"] != kind:
        die("card.json is a %s card and this folder makes a %s card" % (spec["type"], kind))
    c = Card(folder)
    d = c.teardown(spec) if kind == "teardown" else c.report(spec)
    layouts = list(LAYOUTS[kind]) if a.layout == "all" else [a.layout or spec.get("layout") or DEFAULT_LAYOUT[kind]]
    skins = list(SKINS) if a.skin == "all" else [a.skin or spec.get("skin") or "cobalt"]
    for lid in layouts:
        if lid not in LAYOUTS[kind]:
            die("layout %r is not a %s layout (%s)" % (lid, kind, ", ".join(LAYOUTS[kind])))
    for s in skins:
        if s not in SKINS:
            die("style %r is not one of %s" % (s, ", ".join(SKINS)))
    skipped = []
    for lid in list(layouts):
        need = {"t3": "hero", "t4": "proof"}.get(lid)
        if need and not d.get(need):
            if len(layouts) > 1:
                layouts.remove(lid)
                skipped.append("%s (%s) needs \"%s\" in card.json" % (lid, LAYOUT_NAMES[lid], need))
            else:
                c.errors.append("%s (%s) needs \"%s\" in card.json (references/post.md)" % (lid, LAYOUT_NAMES[lid], need))
    for w in c.warnings:
        print("note: " + w)
    for s in skipped:
        print("skipped: " + s)
    if c.errors:
        for e in c.errors:
            print("FIX: " + e)
        print("NOT MADE: %d line%s of %s to fix" % (len(c.errors), "" if len(c.errors) == 1 else "s", os.path.relpath(card_path)))
        return 1
    if a.check:
        print("card.json passes: %s, %d layout%s" % (kind, len(layouts), "" if len(layouts) == 1 else "s"))
        return 0
    many = len(layouts) * len(skins) > 1
    pairs = []
    for s in skins:
        for lid in layouts:
            if many:
                png = os.path.join(os.path.abspath(a.out) if a.out else os.path.join(folder, "post-cards"), "%s-%s.png" % (s, lid))
            else:
                png = os.path.abspath(a.out) if a.out else os.path.join(folder, "post-card.png")
            htm = re.sub(r"\.png$", "", png, flags=re.I) + ".html"
            write_text(htm, page(d, lid, s))
            pairs.append((htm, png))
    if drafted:
        print("wrote a draft %s from the run: rewrite its lines in plain words (references/post.md) and run again" % os.path.relpath(card_path))
    if a.html_only:
        for h, _ in pairs:
            print("html: " + h)
        return 0
    res, err = render(pairs, a.scale, a.browser)
    if res is None:
        for h, _ in pairs:
            print("html: " + h)
        print("NO PNG: " + err)
        print("the HTML opens in any browser; for the PNG install Playwright once: npm install --prefix ~/.cache/rea-viral playwright-core@1.49.1")
        return 2
    bad = 0
    for r in res:
        z = r.get("zoom") or 1
        what = "%s %s" % (r.get("layout"), r.get("skin"))
        if r.get("ok"):
            extra = []
            if z < 1:
                extra.append("text at %d %%" % round(z * 100))
            if r.get("shrunk"):
                extra.append("shrunk to fit: " + "; ".join('"%s"' % x for x in r["shrunk"][:3]))
            print("made %s (%s)%s" % (r["png"], what, (": " + ", ".join(extra)) if extra else ""))
        else:
            bad += 1
            print("DOES NOT FIT %s (%s): %s" % (r["png"], what, "; ".join(r.get("problems", []) + r.get("errors", []))))
        fam = FAMILY.get(r.get("skin"))
        if r.get("ok") and fam and r.get("fonts") is not None and fam not in r["fonts"]:
            print("note: %s did not load in %s: the browser drew a fallback font" % (fam, r["png"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
