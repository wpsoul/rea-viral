#!/usr/bin/env python3
"""The post picture: a run's numbers as a 1080 x 1350 card for X, Threads and Instagram, in 7 styles and 22 layouts
across every REA Viral report type (references/post.md).

    python3 post_card.py <run folder> [--type teardown|report|post|format|account|draft|writing|comments|compare|topic]
                         [--layout t1..t5|r1..r6|p1..p3|f1..f2|a1..a2|d1|w1|c1|x1|all]
                         [--skin cobalt|redword|night|holo|paper|warm|glass|all]
                         [--card card.json] [--format ID] [--draft PATH] [--pair A,B] [--vs FOLDER2]
                         [--out post-card.png] [--scale 1] [--browser chrome|chromium|<path>]
                         [--html-only] [--check]

Card types (auto-detected from the folder or --layout):
- teardown (t1..t5): account run with growth mode (growth.json, findings.json "growth")
- report   (r1..r6): niche run (niche.json, radar.json, writing.json; r6 when topic_check.json exists)
- topic    (r6):     niche topic check (topic_check.json: saturation + 6h momentum + lateness + verdict)
- post     (p1..p3): single post review (post_probe.json: proof post, hook breakdown, vs author's median)
- format   (f1..f2): single format recipe (radar.json + formats/<id>.md: "copy this" blueprint + best 3 posts)
- account  (a1..a2): account teardown WITHOUT growth mode (analysis.json + radar.json + optional writing.json)
- draft    (d1):     draft check vs author's habits (draft_check.py + writing.json; predicted range marked ESTIMATE)
- writing  (w1):     writing / voice breakdown (writing.json: openings, length bands, asks with x usual)
- comments (c1):     comment tactics (comments.json: own comments, reply rate, follow intent, echo prompts)
- compare  (x1):     compare two formats (--pair a,b) or two accounts (--vs <run2>) side by side

Rules checked (--check, exit 1 with line to fix):
- real script-computed numbers only (placeholders in teardown/report; no invented numbers);
- verbatim quotes checked against the run's posts/comments;
- no gendered pronouns (he/him/his/she/her) for the account owner outside quotes;
- @handles (including handles with digits like @b1rkh0ff) never trigger typed-number warnings;
- safe bare <b> and <mark> tags + **bold** supported in titles and text;
- :x ratios round to integer at >= 10x and 1 decimal below 10x (2 decimals in 0.95..0.99 so <1x never prints as 1x);
- small samples labelled; fresh posts (< 3 days) marked "still growing / so far"; d1 range explicitly labelled ESTIMATE.
"""
import argparse
import base64
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, median, read_csv, read_json, script_dir, write_json, write_text  # noqa: E402
import growth as G  # noqa: E402

SKINS = ("cobalt", "redword", "night", "holo", "paper", "warm", "glass")
LAYOUTS = {
    "teardown": ("t1", "t2", "t3", "t4", "t5"),
    "report": ("r1", "r2", "r3", "r4", "r5", "r6"),
    "post": ("p1", "p2", "p3"),
    "format": ("f1", "f2"),
    "account": ("a1", "a2"),
    "draft": ("d1",),
    "writing": ("w1",),
    "comments": ("c1",),
    "compare": ("x1",),
    "topic": ("r6",),
}
LAYOUT_NAMES = {
    "t1": "Scorecard", "t2": "2x2 numbers", "t3": "Hero number + checklist", "t4": "The proof post",
    "t5": "Numbered editorial",
    "r1": "Diverging bars", "r2": "Works | Doesn't", "r3": "Ranked, number first",
    "r4": "The winner + the rest", "r5": "Dot plot", "r6": "Topic check",
    "p1": "Proof post + chips", "p2": "Hook breakdown", "p3": "Vs author median",
    "f1": "Recipe blueprint", "f2": "Scorecard + examples",
    "a1": "Account scorecard", "a2": "Format bars + tip",
    "d1": "Draft check", "w1": "Writing & voice", "c1": "Comment tactics", "x1": "Compare two",
}
DEFAULT_LAYOUT = {
    "teardown": "t1", "report": "r2", "post": "p1", "format": "f1", "account": "a1",
    "draft": "d1", "writing": "w1", "comments": "c1", "compare": "x1", "topic": "r6",
}
FAMILY = {"cobalt": "Poppins", "redword": "Red Hat Display", "holo": "Archivo", "night": "Inter Tight",
          "paper": "Inter Tight", "warm": "Inter Tight", "glass": "Inter Tight"}
ICON = {
    "t1": "key", "t2": "arrow-up", "t3": "arrow-up", "t4": "bubble", "t5": "king",
    "r1": "arrow-up", "r2": "key", "r3": "king", "r4": "arrow-up", "r5": "bubble", "r6": "arrow-up",
    "p1": "bubble", "p2": "key", "p3": "arrow-up",
    "f1": "key", "f2": "king", "a1": "key", "a2": "arrow-up",
    "d1": "bubble", "w1": "key", "c1": "bubble", "x1": "king",
}
RED = {"key": "cursor", "king": "cursor", "arrow-up": "arrow-up", "bubble": "bubble"}
NO_ICON = ("holo", "paper", "warm", "glass")
NETWORK = {"x": "X", "threads": "Threads", "tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube",
           "linkedin": "LinkedIn"}
NICHE_NETWORK = dict(NETWORK, youtube="YouTube Shorts")
GLYPH = {"x": "\U0001D54F"}
TEMPLATE_DIR = os.path.join(script_dir(), "..", "templates", "post")
MONTHS_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]

ITEM_FIELDS = ("n", "unit", "line", "sub", "short", "tag", "say", "chip")
STRICT_FIELDS = ("n", "tag")
MAX_ITEMS = 4
PROOF_CHARS = 300
PRONOUN_RE = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.I)
QUOTE_RE = re.compile(r"[“\"]([^”\"]{2,}?)[”\"]")
TYPED_RE = re.compile(r"\d[\d.,:]*")
HANDLE_RE = re.compile(r"@[A-Za-z0-9_.]{1,40}")
X_RE = re.compile(r"(\d)x\b")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
SAFE_TAG_RE = re.compile(r"&lt;(/?)(b|mark)&gt;", re.I)
ONE_TO_ONE = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
QN_MAP = {"scale_it": "Scale it", "underused": "Underused", "overused": "Overused", "fading": "Overused",
          "drop": "Drop", "too_few": "Few posts"}


def norm(s):
    s = (s or "").translate(ONE_TO_ONE).replace("…", "...")
    return re.sub(r"\s+", " ", s).strip().lower()


def md(s):
    """Safe HTML: escape everything first, allow bare attribute-less <b> and <mark>, plus **bold**."""
    esc = html.escape(s or "", quote=False)
    esc = SAFE_TAG_RE.sub(lambda m: "<%s%s>" % (m.group(1), m.group(2).lower()), esc)
    return BOLD_RE.sub(r"<b>\1</b>", esc)


def fmt_x(v):
    """Multiplier format (0.5.1): integer at >= 10x (511×), 1 decimal below 10x (2.7×, 0.6×),
    2 decimals in 0.95..0.99 so under-1x never rounds up to 1×."""
    if v is None:
        return "—"
    x = float(v)
    if round(abs(x), 1) >= 10:
        return "%d×" % round(x)
    if 0.95 <= x < 1.0:
        return "%.2f×" % x
    return ("%.1f" % x).rstrip("0").rstrip(".") + "×"


def fmt_card_value(v, f):
    if f == "x":
        if v is None:
            raise ValueError("no value (null)")
        return fmt_x(v)
    return G.fmt_value(v, f)


def fill_card(text, doc):
    """Replace {key} and {key:fmt} using doc, with post_card's :x rounding."""
    problems, keys = [], []

    def sub(m):
        key, f = m.group(1), m.group(2)
        keys.append(key)
        try:
            return fmt_card_value(G.get_path(doc, key), f)
        except KeyError:
            problems.append("{%s}: data has no such key" % key)
        except ValueError as e:
            problems.append("{%s}: %s" % (key, e))
        return "{%s}" % key
    return G.PLACEHOLDER_RE.sub(sub, text or ""), problems, keys


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
    return fmt_x(v)


def _pct(v):
    if v is None:
        return "—"
    return "%d%%" % round(100 * float(v))


def _compact(v):
    if v is None:
        return "—"
    try:
        return G.compact(v)
    except (TypeError, ValueError):
        return str(v)


def _trim(s, limit=120):
    s = re.sub(r"\s+", " ", (s or "").strip())
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _hours_text(h):
    if h is None:
        return "—"
    if h < 1.0:
        return "%d min" % max(1, round(h * 60))
    if h < 10.0:
        return ("%s" % ("%.1f" % h).rstrip("0").rstrip(".")) + "h"
    return "%dh" % round(h)


def _mark_text(words, marks):
    """HTML-escape words and wrap matched substrings in <mark>...</mark>."""
    spans, low = [], words.translate(ONE_TO_ONE).lower()
    missing = []
    for m in marks or []:
        if not isinstance(m, str) or not m.strip():
            continue
        i = low.find(m.translate(ONE_TO_ONE).lower())
        if i < 0:
            missing.append(m)
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
    return "".join(out), missing


class Card:
    """Reads one run, checks the card's lines, and builds the data the template draws."""

    def __init__(self, folder):
        self.folder = folder
        self.errors, self.warnings = [], []
        self.corpus = ""
        self.handle = ""

    # ------------------------------------------------------------------ the rules every line meets
    def lint(self, where, raw, strict=False, allow_typed=False):
        bare = G.PLACEHOLDER_RE.sub("", raw or "")
        # Strip bare <b> / <mark> tags before quote/pronoun/digit checks
        bare_clean = re.sub(r"</?(?:b|mark)>", "", bare, flags=re.I)
        for q in QUOTE_RE.findall(bare_clean):
            if self.corpus and norm(q) not in self.corpus:
                self.errors.append("%s: the quote \"%s\" is not in the posts' own words (their caption, parts or the "
                                   "author's replies): quote the post exactly, or say it without quote marks" % (where, q))
        outside = QUOTE_RE.sub("", bare_clean)
        m = PRONOUN_RE.search(outside)
        if m:
            self.errors.append("%s: \"%s\": no he, his, she or her for the account owner: say they, or the account" % (where, m.group(0)))
        if not allow_typed:
            # Strip @handles (e.g. @b1rkh0ff) and bare handle so digits in handles never trigger a warning (0.5.1)
            no_handles = HANDLE_RE.sub("", outside)
            if self.handle and any(ch.isdigit() for ch in self.handle):
                no_handles = re.sub(r"\b" + re.escape(self.handle) + r"\b", "", no_handles, flags=re.I)
            typed = TYPED_RE.findall(no_handles)
            if typed:
                msg = "%s: the number %s is typed: write it as a placeholder so it is the run's" % (where, ", ".join(typed))
                (self.errors if strict else self.warnings).append(msg if strict else msg + " (or check it is)")

    def load_corpus(self, post_files, comment_files=None):
        words = []
        for p in post_files:
            try:
                rows = read_csv(p)[1]
            except (OSError, ValueError, IndexError):
                continue
            for r in rows:
                words += [r.get("caption") or "", r.get("parts") or "", r.get("author_replies") or ""]
        for p in comment_files or []:
            try:
                rows = read_csv(p)[1]
            except (OSError, ValueError, IndexError):
                continue
            for r in rows:
                words.append(r.get("text") or "")
        self.corpus = norm(" \n ".join(words))

    def _safe_prose(self, where, raw, allow_typed=True):
        if raw is None or raw == "":
            return ""
        raw = str(raw)
        self.lint(where, raw, strict=False, allow_typed=allow_typed)
        return md(X_RE.sub("\\1×", raw))

    # ------------------------------------------------------------------ 1. account teardown (growth mode, t1-t5)
    def teardown(self, spec):
        f = self.folder
        try:
            g = read_json(os.path.join(f, "growth.json"))
        except (OSError, ValueError) as e:
            die("no growth.json in %s (%s): a teardown card needs growth mode (references/growth.md); "
                "for an account without growth mode use --type account (--layout a1 or a2)" % (f, e))
        try:
            acc = read_json(os.path.join(f, "account.json"))
        except (OSError, ValueError):
            acc = {}
        self.g = g
        ga = g.get("account") or {}
        handle = acc.get("handle") or ga.get("handle") or ""
        self.handle = handle
        net = acc.get("network") or ga.get("network") or ""
        rows = []
        try:
            rows = read_csv(os.path.join(f, "posts.csv"))[1]
        except (OSError, ValueError, IndexError):
            self.warnings.append("posts.csv cannot be read: quotes cannot be checked and the proof post has no words")
        self.posts = dict((r.get("post_id"), r) for r in rows)
        self.load_corpus([os.path.join(f, "posts.csv")], [os.path.join(f, "comments.csv")])
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
        filled, problems, _ = fill_card(raw, self.g)
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
        marked, missing = _mark_text(words, p.get("mark") or [])
        for m in missing:
            self.errors.append("proof.mark: \"%s\" is not in the post's words%s" % (m, " (as cut to %d characters)" % PROOF_CHARS if words.endswith("…") else ""))
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
        return {"date": short_date(gp.get("at")), "text": marked, "stats": stats,
                "caption": self.text("proof.caption", p.get("caption")), "chips": chips}

    # ------------------------------------------------------------------ 2. niche report (r1-r5 + optional r6)
    def report(self, spec):
        f = self.folder
        try:
            radar = read_json(os.path.join(f, "radar.json"))
        except (OSError, ValueError) as e:
            die("no radar.json in %s (%s): a niche card needs radar.py first (references/niche.md)" % (f, e))
        writing = read_json(os.path.join(f, "writing.json")) if os.path.exists(os.path.join(f, "writing.json")) else {}
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
        # Attach topic check payload when topic_check.json exists so --layout r6 works in a niche folder too
        if os.path.exists(os.path.join(f, "topic_check.json")):
            d["topic"] = self.topic(spec.get("topic") or {})
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
                return fmt_card_value(ctx[key], fm)
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

    # ------------------------------------------------------------------ 3. post review (p1-p3)
    def post_card(self, spec):
        f = self.folder
        pp_path = os.path.join(f, "post_probe.json")
        if not os.path.exists(pp_path):
            die("no post_probe.json in %s: run post_probe.py first (references/post-run.md)" % f)
        pp = read_json(pp_path)
        acc = read_json(os.path.join(f, "account.json")) if os.path.exists(os.path.join(f, "account.json")) else {}
        self.load_corpus([os.path.join(f, "posts.csv")], [os.path.join(f, "comments.csv")])
        p, cr = pp.get("post") or {}, pp.get("creator") or {}
        handle = cr.get("handle") or acc.get("handle") or ""
        self.handle = handle
        net = cr.get("network") or acc.get("network") or ""
        netname = NETWORK.get(net, net)
        name = (cr.get("name") or acc.get("name") or handle or "").strip()
        initial = next((c.upper() for c in name if c.isalnum()), "@")
        ratio = p.get("ratio") if p.get("ratio") is not None else p.get("ratio_so_far")
        is_fresh = bool(p.get("fresh") or pp.get("status") in ("fresh", "too_new"))
        mult = fmt_x(ratio) if ratio is not None else (
            ("%.1f× fol" % p["views_per_follower"]) if p.get("views_per_follower") is not None else "—")
        usual_n = p.get("usual_from_posts") or 0
        usual_v = p.get("usual")
        usual_lbl = ("so far vs @%s’s usual (median %s from %d posts)" if is_fresh else "vs @%s’s usual (median %s from %d posts)") % (
            handle, _compact(usual_v), usual_n) if usual_v is not None else ("measured on views per follower (weaker basis)")

        raw_cap = (p.get("caption") or "").strip()
        if len(raw_cap) > PROOF_CHARS:
            raw_cap = raw_cap[:PROOF_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
        first_line = ((pp.get("words") or {}).get("first_line") or (raw_cap.split("\n")[0] if raw_cap else "")).strip()
        marks = spec.get("mark") if spec.get("mark") is not None else ([first_line] if first_line else [])
        marked_cap, missing = _mark_text(raw_cap, marks)
        for m in missing:
            self.errors.append("mark: \"%s\" is not in the post's caption" % m)

        stats = []
        for k, lbl in (("views", "views"), ("likes", "likes"), ("bookmarks", "bookmarks"), ("comments", "replies")):
            v = p.get(k)
            if v is not None:
                stats.append([_compact(v), lbl])

        # Compute author's median metrics from posts.csv for p3 Before/After
        other_rows = []
        try:
            for r in read_csv(os.path.join(f, "posts.csv"))[1]:
                if (r.get("post_id") or "").strip() != str(p.get("post_id")):
                    other_rows.append(r)
        except (OSError, ValueError, IndexError):
            pass

        def _med_col(col):
            vals = []
            for r in other_rows:
                try:
                    if (r.get(col) or "").strip() != "":
                        vals.append(int(float(r[col])))
                except ValueError:
                    pass
            return median(vals)

        compare = []
        if usual_v is not None and p.get("views") is not None:
            compare.append({"label": "Views", "usual": _compact(usual_v), "post": _compact(p["views"]),
                            "delta": mult + (" so far" if is_fresh else "")})
        for col, lbl, pk in (("likes", "Likes", "likes"), ("comments", "Replies", "comments"), ("bookmarks", "Bookmarks", "bookmarks")):
            mv = _med_col(col)
            pv = p.get(pk)
            if mv is not None and pv is not None:
                dl = fmt_x(pv / float(mv)) if mv > 0 else ("+%s" % _compact(pv))
                compare.append({"label": lbl, "usual": _compact(mv), "post": _compact(pv), "delta": dl})
        if first_line:
            fl_lens = [len(((r.get("caption") or "").strip().split("\n")[0]).strip()) for r in other_rows if (r.get("caption") or "").strip()]
            mfl = median(fl_lens)
            if mfl is not None:
                compare.append({"label": "First line", "usual": "%d chars" % round(mfl), "post": "%d chars" % len(first_line),
                                "delta": "Shorter" if len(first_line) < mfl * 0.85 else ("Longer" if len(first_line) > mfl * 1.15 else "Same")})
        compare = compare[:4]

        # Structure steps (from spec or notes.json or caption breakdown)
        structure = []
        if spec.get("structure"):
            for i, s in enumerate(spec["structure"][:3]):
                structure.append({"step": self._safe_prose("structure[%d].step" % i, s.get("step") or ("0%d" % (i + 1))),
                                  "text": self._safe_prose("structure[%d].text" % i, s.get("text"))})
        else:
            notes_p = os.path.join(f, "videos", str(p.get("post_id")), "notes.json")
            seen = (read_json(notes_p).get("seen") or {}) if os.path.exists(notes_p) else {}
            if seen.get("hook"):
                for step_lbl, k in (("01 · Hook", "hook"), ("02 · Turn", "turn"), ("03 · Ask", "ask")):
                    val = seen.get(k)
                    txt = val.get("text") if isinstance(val, dict) else val
                    if txt and str(txt).lower() != "none":
                        structure.append({"step": step_lbl, "text": md(_trim(str(txt), 95))})
            if not structure:
                lines = [ln.strip() for ln in (p.get("caption") or "").split("\n") if ln.strip()]
                if lines:
                    structure.append({"step": "01 · Hook", "text": md(_trim(lines[0], 95))})
                if len(lines) >= 2:
                    structure.append({"step": "02 · Body", "text": md(_trim(" ".join(lines[1:-1] if len(lines) > 2 else lines[1:]), 95))})
                if len(lines) >= 3:
                    structure.append({"step": "03 · Close", "text": md(_trim(lines[-1], 95))})

        # Why it worked points (2-3 with evidence)
        why = []
        if spec.get("why"):
            for i, w in enumerate(spec["why"][:3]):
                why.append({"tag": self._safe_prose("why[%d].tag" % i, w.get("tag") or mult),
                            "line": self._safe_prose("why[%d].line" % i, w.get("line")),
                            "sub": self._safe_prose("why[%d].sub" % i, w.get("sub"))})
        else:
            wds = pp.get("words") or {}
            for fl in (wds.get("flags") or []):
                if fl.get("differs") and len(why) < 2:
                    why.append({"tag": fmt_x((fl.get("creator_with") or {}).get("lift")) if (fl.get("creator_with") or {}).get("lift") else mult,
                                "line": md(fl.get("label") or ""), "sub": md(_trim(fl.get("differs") or "", 90))})
            rep = pp.get("repeats") or {}
            if rep.get("format") and rep.get("times"):
                why.append({"tag": "%d repeats" % rep["times"], "line": md("Format repeats: " + (rep.get("name") or rep["format"])),
                            "sub": md("%d of %d scored repeats beat usual" % (rep.get("above_usual") or 0, rep.get("scored") or 0))})
            fi = read_json(os.path.join(f, "findings.json")) if os.path.exists(os.path.join(f, "findings.json")) else {}
            for m in (fi.get("mechanisms") or []):
                if len(why) >= 3:
                    break
                why.append({"tag": m.get("evidence") or "SEEN", "line": md(_trim(m.get("title") or m.get("text") or "", 52)),
                            "sub": md(_trim(m.get("text") or "", 90))})
            if not why:
                why.append({"tag": mult + (" so far" if is_fresh else ""),
                            "line": md("Ranked #%s of %s scored posts" % (p.get("rank_among_creator") or "—", p.get("creator_scored") or 0)),
                            "sub": md(usual_lbl)})

        openings = [o.replace("opens_", "").replace("_", " ") for o in ((pp.get("words") or {}).get("openings") or [])]
        hook_tag = " · ".join(([", ".join(openings[:2])] if openings else []) + (["%d chars" % len(first_line)] if first_line else []))
        title_def = "Why this post hit <b>%s</b>%s their usual" % (mult, " so far" if is_fresh else "")
        d = {
            "type": "post",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Post review"),
            "title": self._safe_prose("title", spec.get("title") or title_def),
            "fresh": "Still growing · so far" if is_fresh else None,
            "account": {"name": html.escape(name), "handle": "@" + html.escape(handle), "initial": html.escape(initial),
                        "followers": _compact(cr.get("followers")), "glyph": GLYPH.get(net, html.escape(netname))},
            "post": {"date": short_date(p.get("published_at")), "multiplier": mult, "usual_label": md(usual_lbl),
                     "text": marked_cap, "hook": html.escape(_trim(first_line, 120), quote=False), "hook_tag": md(hook_tag),
                     "stats": stats, "structure": structure},
            "why": why[:3],
            "compare": compare,
            "foot": "1× = @%s’s usual%s · post_probe.json" % (html.escape(handle), " · still growing" if is_fresh else ""),
            "brand": "Measured with <b>REA Viral</b>",
        }
        return d

    # ------------------------------------------------------------------ 4. format recipe (f1-f2)
    def format_card(self, spec, fmt_id=None):
        f = self.folder
        rp = os.path.join(f, "radar.json")
        if not os.path.exists(rp):
            die("no radar.json in %s: run radar.py first" % f)
        radar = read_json(rp)
        formats = radar.get("formats") or []
        if not formats:
            die("radar.json in %s has no formats" % f)
        want_id = fmt_id or spec.get("format")
        if want_id:
            fmt = next((x for x in formats if x.get("id") == want_id), None)
            if not fmt:
                self.errors.append("format: radar.json has no format %r" % want_id)
                fmt = formats[0]
        else:
            order = {"scale_it": 0, "underused": 1, "overused": 2, "drop": 3, "too_few": 4}
            fmt = sorted(formats, key=lambda x: (bool(x.get("few_posts")), order.get(x.get("quadrant"), 9), -(x.get("lift") or 0)))[0]

        is_shared = radar.get("scope") == "shared"
        subj = radar.get("subject") or {}
        handle = subj.get("handle") or ""
        self.handle = handle
        who = ("@" + handle) if handle else (subj.get("niche") or "this niche")

        # Load captions & fresh flags from analysis.json or trends.json
        an = read_json(os.path.join(f, "trends.json")) if is_shared and os.path.exists(os.path.join(f, "trends.json")) else (
            read_json(os.path.join(f, "analysis.json")) if os.path.exists(os.path.join(f, "analysis.json")) else {})
        by_id = dict((p["post_id"], p) for p in an.get("posts") or [])

        # Also read recipe JSON from formats/<id>.md if available
        rec_json = {}
        rpath = os.path.join(f, "formats", "%s.md" % fmt["id"])
        if os.path.exists(rpath):
            m = re.search(r"```json rea-recipe\s*\n(.*?)\n```", open(rpath, encoding="utf-8").read(), re.S)
            if m:
                try:
                    rec_json = json.loads(m.group(1))
                except ValueError:
                    pass

        cont = fmt.get("container") or {}
        recipe = [
            {"k": "Hook", "v": md(_trim(rec_json.get("hook_pattern") or cont.get("hook") or "—", 110))},
            {"k": "Structure", "v": md(_trim(cont.get("structure") or "—", 110))},
            {"k": "Look", "v": md(_trim(cont.get("look") or "—", 110))},
            {"k": "Length", "v": md(_trim(cont.get("length") or (("%ss median" % fmt["length_s_median"]) if fmt.get("length_s_median") else "—"), 110))},
        ]
        if spec.get("recipe"):
            recipe = [{"k": self._safe_prose("recipe[%d].k" % i, r.get("k")), "v": self._safe_prose("recipe[%d].v" % i, r.get("v"))}
                      for i, r in enumerate(spec["recipe"][:4])]

        stats = [
            {"n": fmt_x(fmt.get("lift")), "label": "vs each creator’s usual" if is_shared else "median vs usual"},
            {"n": _pct(fmt.get("hit_rate")), "label": "hit rate (2×+)"},
            {"n": ("%d creators" % fmt["creators"]) if is_shared else _pct(fmt.get("share")),
             "label": "in niche" if is_shared else "share of posts"},
            {"n": str(fmt.get("effort") or "—").capitalize(), "label": "effort"},
        ]

        posts_tiles = []
        for e in (fmt.get("examples") or [])[:3]:
            pid = e.get("post_id")
            row = by_id.get(pid) or {}
            cap = (row.get("caption") or "").strip().split("\n")[0] if row.get("caption") else pid
            is_fr = bool(e.get("fresh") or row.get("fresh") or row.get("status") == "fresh")
            posts_tiles.append({
                "ratio": fmt_x(e.get("ratio")),
                "views": _compact(e.get("views") if e.get("views") is not None else row.get("views")),
                "date": short_date(e.get("published_at") or row.get("published_at")),
                "line": md(_trim(cap or pid, 72)),
                "fresh": is_fr,
            })

        qn = QN_MAP.get(fmt.get("quadrant"), fmt.get("quadrant_name") or "")
        dir_lbl = (" · " + fmt["direction_label"].capitalize()) if fmt.get("direction_label") else ""
        small = ("Few posts (%d scored) · early lead" % (fmt.get("posts_scored") or 0)) if fmt.get("few_posts") else None
        fname = fmt.get("name") or fmt["id"]
        return {
            "type": "format",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Format recipe"),
            "title": self._safe_prose("title", spec.get("title") or ("Copy this: <b>%s</b>" % fname)),
            "badge": qn + dir_lbl if qn else None,
            "small_sample": small,
            "stats": stats,
            "recipe": recipe,
            "posts": posts_tiles,
            "foot": "1× = %s’s usual · %d posts in format · radar.json" % (html.escape(who), fmt.get("posts_total") or 0),
            "brand": "Measured with <b>REA Viral</b>",
        }

    # ------------------------------------------------------------------ 5. account teardown WITHOUT growth (a1-a2)
    def account_card(self, spec):
        f = self.folder
        an_p, rd_p = os.path.join(f, "analysis.json"), os.path.join(f, "radar.json")
        if not os.path.exists(an_p):
            die("no analysis.json in %s: run analyze.py first" % f)
        if not os.path.exists(rd_p):
            die("no radar.json in %s: run radar.py first" % f)
        an, radar = read_json(an_p), read_json(rd_p)
        wr = read_json(os.path.join(f, "writing.json")) if os.path.exists(os.path.join(f, "writing.json")) else {}
        acc = an.get("account") or {}
        handle = acc.get("handle") or ""
        self.handle = handle
        net = acc.get("network") or ""
        netname = NETWORK.get(net, net)
        name = (acc.get("name") or handle or "").strip()
        initial = next((c.upper() for c in name if c.isalnum()), "@")
        counts = an.get("counts") or {}
        window = window_text(an.get("window"))
        self.load_corpus([os.path.join(f, "posts.csv")])

        formats = [x for x in (radar.get("formats") or []) if x.get("lift") is not None]
        top_fmts = sorted([x for x in formats if float(x["lift"]) >= 1.0], key=lambda x: -float(x["lift"]))
        drop_fmts = sorted([x for x in formats if float(x["lift"]) < 1.0], key=lambda x: float(x["lift"]))

        def _fmt_row(x):
            qn = QN_MAP.get(x.get("quadrant"), x.get("quadrant_name") or "")
            meta_parts = [_pct(x.get("share")) + " of posts", _pct(x.get("hit_rate")) + " hit rate"]
            if x.get("few_posts"):
                meta_parts.append("%d posts · lead" % (x.get("posts_scored") or 0))
            elif x.get("direction_label"):
                meta_parts.append(x["direction_label"])
            return {"v": round(float(x["lift"]), 3), "n": fmt_x(x["lift"]), "name": md(x.get("name") or x["id"]),
                    "meta": md(" · ".join(meta_parts)), "quadrant": qn}

        top_rows = [_fmt_row(x) for x in top_fmts[:3]]
        drop_rows = [_fmt_row(x) for x in drop_fmts[:2]]
        if not top_rows and not drop_rows:
            self.errors.append("account: radar.json has no scored formats with a lift")

        tip = None
        if spec.get("tip"):
            t = spec["tip"]
            tip = {"n": self._safe_prose("tip.n", t.get("n")), "label": self._safe_prose("tip.label", t.get("label")),
                   "sub": self._safe_prose("tip.sub", t.get("sub"))}
        elif wr:
            strong = [x for x in (wr.get("features") or []) if x.get("claim_ok") and x.get("verdict") == "lifts"]
            strong.sort(key=lambda x: -((x.get("with") or {}).get("lift") or 0))
            if strong:
                x = strong[0]
                wi, wo = x.get("with") or {}, x.get("without") or {}
                tip = {"n": fmt_x(wi.get("lift")),
                       "label": md("Writing tip: " + (x.get("label") or x["id"])),
                       "sub": md("%d posts at %s vs %s without (writing.json)" % (wi.get("posts") or 0, fmt_x(wi.get("lift")), fmt_x(wo.get("lift"))))}
            else:
                leads = [x for x in (wr.get("features") or []) if (x.get("with") or {}).get("lift") and (x.get("with") or {}).get("posts", 0) >= 3]
                leads.sort(key=lambda x: -((x.get("with") or {}).get("lift") or 0))
                if leads and (leads[0].get("with") or {}).get("lift", 0) >= 1.15:
                    x = leads[0]
                    wi = x.get("with") or {}
                    tip = {"n": fmt_x(wi.get("lift")),
                           "label": md("Writing lead: " + (x.get("label") or x["id"])),
                           "sub": md("%d posts (small sample / lead · writing.json)" % (wi.get("posts") or 0))}

        return {
            "type": "account",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Account teardown"),
            "title": self._safe_prose("title", spec.get("title") or ("What works on <b>@%s</b>" % handle)),
            "a2": {"sub": md("%d posts on %s%s. Each format measured against @%s’s own usual (1×)." % (
                counts.get("in_window") or counts.get("posts_total") or 0, netname, (", " + window) if window else "", handle))},
            "account": {"name": html.escape(name), "handle": "@" + html.escape(handle), "initial": html.escape(initial),
                        "followers": _compact(acc.get("followers")),
                        "window": "%s · %d posts" % (window, counts.get("in_window") or counts.get("posts_total") or 0) if window else "%d posts" % (counts.get("posts_total") or 0),
                        "glyph": GLYPH.get(net, html.escape(netname))},
            "top": top_rows,
            "drop": drop_rows,
            "tip": tip,
            "foot": "1× = @%s’s usual · %d scored posts · analysis.json + radar.json" % (html.escape(handle), counts.get("scored") or 0),
            "brand": "Measured with <b>REA Viral</b>",
        }

    # ------------------------------------------------------------------ 6. draft check (d1)
    def draft_card(self, spec, draft_path=None):
        import text_probe as tp
        import draft_check as dc
        f = self.folder
        wr = read_json(os.path.join(f, "writing.json")) if os.path.exists(os.path.join(f, "writing.json")) else {}
        acc = read_json(os.path.join(f, "account.json")) if os.path.exists(os.path.join(f, "account.json")) else {}
        handle = acc.get("handle") or (wr.get("subject") or {}).get("handle") or ""
        self.handle = handle

        dp = draft_path or spec.get("draft_file")
        if dp and not os.path.isabs(dp):
            dp = os.path.join(f, dp)
        if not dp and not spec.get("draft_text"):
            cands = sorted(glob.glob(os.path.join(f, "drafts", "*.md")))
            dp = cands[-1] if cands else None

        words = tp.load_words()
        voice = tp.read_voice(f)
        if dp and os.path.exists(dp):
            _, parts, reply = dc.parse_draft(dp)
            draft_full = "\n\n".join(parts)
            corp = dc.corpus(f) if os.path.exists(os.path.join(f, "posts.csv")) else []
            chk = dc.check_draft(dp, f, voice, words, dc.corpus_index(corp), dc.own_marks(corp, words), len(corp), general=not bool(voice))
        elif spec.get("draft_text"):
            draft_full = str(spec["draft_text"])
            parts, reply, chk = [draft_full], None, {"checks": []}
        else:
            die("no draft given: pass --draft <draft.md>, put a file in drafts/*.md, or set draft_text in card.json")

        tf = tp.text_features(parts, None, words, [{"text": reply, "minutes_after": None}] if reply else None)
        first_line = (tf.get("first_line") or "").strip()
        preview = _trim(draft_full, 210)
        marked_draft, _ = _mark_text(preview, [first_line] if first_line and first_line in preview else [])
        meta_parts = ["%d chars" % (tf.get("chars") or len(draft_full))]
        if tf.get("first_line_chars") is not None:
            meta_parts.append("first line %d chars" % tf["first_line_chars"])
        ops = [k.replace("opens_", "").replace("_", " ") for k, v in tf.items() if k.startswith("opens_") and v is True]
        if ops:
            meta_parts.append("opens: " + ", ".join(ops[:2]))

        lifts, drags, lift_vals = [], [], []
        # Match writing.json features against the draft
        for feat in wr.get("features") or []:
            fid = feat.get("id")
            if tf.get(fid) is not True:
                continue
            wi = feat.get("with") or {}
            wo = feat.get("without") or {}
            lv = wi.get("lift")
            if lv is None or (wi.get("posts") or 0) < 3:
                continue
            is_lead = not feat.get("claim_ok")
            sub = "%d past posts at %s vs %s without%s" % (wi.get("posts") or 0, fmt_x(lv), fmt_x(wo.get("lift")), " (lead)" if is_lead else "")
            if lv >= 1.15:
                lifts.append((lv, {"tag": fmt_x(lv), "line": md(feat.get("label") or fid), "sub": md(sub)}))
                lift_vals.append(float(lv))
            elif lv <= 0.85:
                drags.append((lv, {"tag": fmt_x(lv), "line": md(feat.get("label") or fid), "sub": md(sub)}))
                lift_vals.append(float(lv))

        # Check numeric winning ranges (chars, first_line_chars)
        for nf in wr.get("numbers") or []:
            w_rng = nf.get("winning_range")
            val = tf.get(nf.get("id"))
            if not w_rng or val is None:
                continue
            lo, hi = w_rng["range"]
            if lo <= val <= hi:
                lifts.append((w_rng["lift"], {"tag": fmt_x(w_rng["lift"]), "line": md("%s in winning band (%s–%s)" % (nf.get("label"), int(lo), int(hi))),
                                              "sub": md("Your draft: %d (%d posts in winning band)" % (int(val), w_rng.get("posts") or 0))}))
                lift_vals.append(float(w_rng["lift"]))
            else:
                wk = w_rng.get("weakest") or {}
                drags.append((wk.get("lift") or 0.8, {"tag": fmt_x(wk.get("lift") or 0.8),
                                                      "line": md("%s outside winning band (%s–%s)" % (nf.get("label"), int(lo), int(hi))),
                                                      "sub": md("Your draft: %d" % int(val))}))
                if wk.get("lift"):
                    lift_vals.append(float(wk["lift"]))

        # Surface failed voice checks from draft_check.py as drags
        for c in (chk.get("checks") or []):
            if not c.get("ok") and c.get("id") not in ("front",):
                drags.append((0.7, {"tag": "Check", "line": md("Voice check failed: " + c["id"].replace("_", " ")),
                                    "sub": md(_trim(c.get("message") or "", 90))}))

        lifts.sort(key=lambda x: -x[0])
        drags.sort(key=lambda x: x[0])
        lift_items = [x[1] for x in lifts[:3]]
        drag_items = [x[1] for x in drags[:3]]

        if spec.get("lifts"):
            lift_items = [{"tag": self._safe_prose("lifts[%d].tag" % i, x.get("tag")), "line": self._safe_prose("lifts[%d].line" % i, x.get("line")),
                           "sub": self._safe_prose("lifts[%d].sub" % i, x.get("sub"))} for i, x in enumerate(spec["lifts"][:3])]
        if spec.get("drags"):
            drag_items = [{"tag": self._safe_prose("drags[%d].tag" % i, x.get("tag")), "line": self._safe_prose("drags[%d].line" % i, x.get("line")),
                           "sub": self._safe_prose("drags[%d].sub" % i, x.get("sub"))} for i, x in enumerate(spec["drags"][:3])]

        # Conservative, transparent ESTIMATE range from matched past signals
        if lift_vals:
            geo = 1.0
            for v in lift_vals:
                geo *= max(0.3, min(4.0, v))
            center = geo ** (1.0 / len(lift_vals))
            lo_e = max(0.4, round(center * 0.78, 1))
            hi_e = min(5.0, round(center * 1.28, 1))
            est_range = "%s – %s" % (fmt_x(lo_e), fmt_x(hi_e))
            est_label = "Estimated range vs @%s’s usual from %d matched writing signals (never a guarantee)" % (handle or "account", len(lift_vals))
        else:
            est_range = "0.8× – 1.3×"
            est_label = "Rough baseline estimate — no strong lifting or sinking signal matched yet"

        est = {"badge": "ESTIMATE · NOT A GUARANTEE", "range": est_range, "label": md(est_label)}
        if spec.get("estimate"):
            se = spec["estimate"]
            est["badge"] = self._safe_prose("estimate.badge", se.get("badge") or est["badge"])
            est["range"] = self._safe_prose("estimate.range", se.get("range") or est["range"])
            est["label"] = self._safe_prose("estimate.label", se.get("label") or est_label)
            if "estimate" not in (est["badge"] + " " + est["label"]).lower():
                self.errors.append("estimate: predicted range must be explicitly labelled as an estimate")

        scored_n = (wr.get("counts") or {}).get("scored_with_text") or 0
        return {
            "type": "draft",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Draft check"),
            "title": self._safe_prose("title", spec.get("title") or ("Before you post this%s" % ((" on <b>@%s</b>" % handle) if handle else ""))),
            "draft": {"text": marked_draft, "meta": md(" · ".join(meta_parts))},
            "lifts": lift_items,
            "drags": drag_items,
            "estimate": est,
            "foot": "Estimate from %d scored posts · signals, not a promise · draft_check.py" % scored_n,
            "brand": "Checked with <b>REA Viral</b>",
        }

    # ------------------------------------------------------------------ 7. writing / voice (w1)
    def writing_card(self, spec):
        f = self.folder
        wp = os.path.join(f, "writing.json")
        if not os.path.exists(wp):
            die("no writing.json in %s: run text_probe.py first" % f)
        wr = read_json(wp)
        subj = wr.get("subject") or {}
        handle = subj.get("handle") or ""
        self.handle = handle
        who = ("@" + handle) if handle else (subj.get("niche") or "this niche")
        net = NETWORK.get(subj.get("network") or "", subj.get("network") or "")
        counts = wr.get("counts") or {}
        scored_n = counts.get("scored_with_text") or 0
        small = ("Small sample · %d posts" % scored_n) if (wr.get("status") != "ok" or scored_n < 30) else None

        # Openings & top habits
        feats = wr.get("features") or []
        strong = [x for x in feats if x.get("claim_ok") and (x.get("with") or {}).get("lift") is not None]
        strong.sort(key=lambda x: -abs(float((x.get("with") or {}).get("lift") or 1.0) - 1.0))
        picks = strong[:4]
        if len(picks) < 3:
            cands = [x for x in feats if x not in picks and (x.get("with") or {}).get("lift") is not None and (x.get("with") or {}).get("posts", 0) >= 3]
            cands.sort(key=lambda x: -(x.get("with") or {}).get("posts", 0))
            picks += cands[:(4 - len(picks))]
        openings = []
        for x in picks[:4]:
            wi = x.get("with") or {}
            lv = float(wi.get("lift") or 1.0)
            v = x.get("verdict") or "lead"
            meta = "%d posts · %s" % (wi.get("posts") or 0, v if x.get("claim_ok") else "lead")
            openings.append({"n": fmt_x(lv), "label": md(x.get("label") or x["id"]), "meta": md(meta), "up": lv >= 1.0})

        # Length bands (chars or first_line_chars)
        bands = []
        nums = wr.get("numbers") or []
        len_f = next((x for x in nums if x.get("id") == "chars" and x.get("groups")), None) or \
                next((x for x in nums if x.get("id") == "first_line_chars" and x.get("groups")), None)
        if len_f:
            w_groups = set((len_f.get("winning_range") or {}).get("groups") or [])
            for g in (len_f.get("groups") or [])[:3]:
                lo, hi = g.get("range") or [0, 0]
                is_best = g.get("name") in w_groups
                bands.append({
                    "range": "%d – %d chars" % (round(lo), round(hi)),
                    "n": fmt_x(g.get("lift")),
                    "posts": "%d posts%s" % (g.get("posts") or 0, " · winning band" if is_best else ""),
                    "best": is_best,
                })
        elif len_f is None:
            ch_f = next((x for x in nums if x.get("id") == "chars"), None)
            if ch_f and (ch_f.get("usage") or {}).get("median") is not None:
                u = ch_f["usage"]
                bands.append({"range": "Usual length", "n": "%d chars" % round(u["median"]),
                              "posts": "8 in 10 posts: %d–%d" % (round(u["p10"] or 0), round(u["p90"] or 0)), "best": True})

        # Asks summary
        ask_obj = None
        asks = wr.get("asks") or {}
        if asks.get("posts_known"):
            ha = next((x for x in feats if x.get("id") == "has_ask"), None)
            w_lift = ((ha or {}).get("with") or {}).get("lift")
            wo_lift = ((ha or {}).get("without") or {}).get("lift")
            kinds = [k for k, v in sorted((asks.get("kinds") or {}).items(), key=lambda kv: -kv[1]) if v][:2]
            where = max((asks.get("where") or {}).items(), key=lambda kv: kv[1])[0].replace("_", " ") if asks.get("where") else ""
            note = "%d of %d posts ask%s%s." % (
                asks.get("posts_with_ask") or 0, asks.get("posts_known") or 0,
                (" (" + ", ".join(kinds) + ")") if kinds else "",
                (" · usually at " + where) if where else "")
            ask_obj = {
                "share": _pct(asks.get("share")),
                "share_lbl": "posts ask",
                "lift": fmt_x(w_lift) if w_lift is not None else "—",
                "lift_lbl": ("with ask (vs %s)" % fmt_x(wo_lift)) if wo_lift is not None else "with ask",
                "note": md(note),
            }

        return {
            "type": "writing",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Writing & voice"),
            "title": self._safe_prose("title", spec.get("title") or ("How <b>%s</b> writes for reach" % html.escape(who))),
            "sub": self._safe_prose("sub", spec.get("sub") or ("%d scored posts%s · each feature measured against %s’s own usual (1×)." % (
                scored_n, (" on " + net) if net else "", who))),
            "small_sample": small,
            "openings": openings,
            "length_bands": bands,
            "asks": ask_obj,
            "foot": "1× = %s’s usual · %d posts with text · writing.json" % (html.escape(who), scored_n),
            "brand": "Measured with <b>REA Viral</b>",
        }

    # ------------------------------------------------------------------ 8. comment tactics (c1)
    def comments_card(self, spec):
        f = self.folder
        cp = os.path.join(f, "comments.json")
        if not os.path.exists(cp):
            die("no comments.json in %s: run comment_tactics.py first" % f)
        cm = read_json(cp)
        if cm.get("status") != "ok":
            die("comments.json status is %s (%s)" % (cm.get("status"), cm.get("note") or "no comments"))
        acc = read_json(os.path.join(f, "account.json")) if os.path.exists(os.path.join(f, "account.json")) else {}
        handle = acc.get("handle") or ""
        self.handle = handle
        self.load_corpus([os.path.join(f, "posts.csv")], [os.path.join(f, "comments.csv")])

        cc = cm.get("creator_comment") or {}
        rb = cm.get("replies_by_creator") or {}
        fc = cm.get("follow_comments") or {}
        cw = cm.get("comment_a_word") or {}
        pin = cm.get("pinned") or {}

        metrics = []
        if cc.get("posts_with_own_comment") is not None:
            sub = "%d of %d posts" % (cc["posts_with_own_comment"], cc.get("of_posts") or 0)
            if cc.get("came_first_known"):
                sub += " · first on %d" % (cc.get("came_first") or 0)
            if cc.get("within_10_min_known"):
                sub += " · <10 min on %d" % (cc.get("within_10_min") or 0)
            metrics.append({"k": "Own comment", "n": _pct(cc.get("share")), "label": "Posts with creator comment", "sub": md(sub)})
        if rb.get("rate") is not None:
            sub = "%d of %d top-level answered" % (rb.get("answered") or 0, rb.get("of_top_level") or 0)
            if rb.get("median_minutes_to_reply") is not None:
                sub += " · median %s min" % _compact(rb["median_minutes_to_reply"])
            metrics.append({"k": "Creator replies", "n": _pct(rb["rate"]), "label": "Audience comments answered", "sub": md(sub)})
        metrics.append({"k": "Follow intent", "n": str(fc.get("count") or 0), "label": "New followers say so",
                        "sub": md("Across %d posts (“just followed”, “found you”)" % (fc.get("posts") or 0))})
        echo = cw.get("echo") or []
        if cw.get("posts_asking") or echo:
            sub = ("Top word “%s” = %s of comments" % (echo[0]["word"].upper(), _pct(echo[0]["share"]))) if echo else (
                "Asked on %d of %d captions" % (cw.get("posts_asking") or 0, cw.get("of_posts") or 0))
            metrics.append({"k": "Echo prompts", "n": "%d posts" % (cw.get("posts_asking") or len(echo)),
                            "label": "“Comment a word” mechanic", "sub": md(sub)})
        elif pin.get("posts_with_pinned") is not None:
            metrics.append({"k": "Pinned", "n": "%d/%d" % (pin["posts_with_pinned"], pin.get("of_posts") or 0),
                            "label": "Posts with pinned comment",
                            "sub": md("%d by creator · %d by audience" % (pin.get("by_creator") or 0, pin.get("by_audience") or 0))})

        quote = None
        if spec.get("quote"):
            q = spec["quote"]
            qt = self._safe_prose("quote.text", q.get("text"))
            quote = {"text": qt, "meta": self._safe_prose("quote.meta", q.get("meta"))}
        else:
            ex = (fc.get("examples") or [])[:1] or (cm.get("questions") or [])[:1] or (cc.get("examples") or [])[:1]
            if ex:
                e = ex[0]
                quote = {"text": md("“%s”" % _trim(e.get("text") or "", 135)),
                         "meta": md("Comment on %s%s" % (e.get("post_id") or "", (" · %s likes" % _compact(e["likes"])) if e.get("likes") else ""))}

        return {
            "type": "comments",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Comment tactics"),
            "title": self._safe_prose("title", spec.get("title") or ("How <b>@%s</b> runs comments" % handle)),
            "sub": self._safe_prose("sub", spec.get("sub") or ("%d comments read across %d posts%s · comments.json." % (
                cm.get("comments_read") or 0, cm.get("posts_read") or 0,
                " (replies included)" if cm.get("replies_read") is True else ""))),
            "metrics": metrics[:4],
            "quote": quote,
            "foot": "%d comments read on %d posts · comments.json" % (cm.get("comments_read") or 0, cm.get("posts_read") or 0),
            "brand": "Measured with <b>REA Viral</b>",
        }

    # ------------------------------------------------------------------ 9. compare two (x1)
    def compare_card(self, spec, pair=None, vs_folder=None):
        f = self.folder
        vs = vs_folder or spec.get("vs")
        if vs:
            vs = os.path.abspath(vs) if os.path.isabs(vs) else os.path.abspath(os.path.join(f, vs))
            return self._compare_accounts(spec, f, vs)
        return self._compare_formats(spec, f, pair)

    def _compare_formats(self, spec, f, pair):
        rp = os.path.join(f, "radar.json")
        if not os.path.exists(rp):
            die("no radar.json in %s: run radar.py first" % f)
        radar = read_json(rp)
        formats = [x for x in (radar.get("formats") or []) if x.get("lift") is not None]
        if len(formats) < 2:
            die("radar.json in %s needs at least 2 scored formats to compare" % f)
        by_id = dict((x["id"], x) for x in formats)
        ids = (pair.split(",") if isinstance(pair, str) else spec.get("pair")) or []
        ids = [x.strip() for x in ids if x.strip()]
        if len(ids) >= 2:
            a, b = by_id.get(ids[0]), by_id.get(ids[1])
            if not a or not b:
                die("compare --pair: format not found in radar.json (available: %s)" % ", ".join(by_id))
        else:
            ordered = sorted(formats, key=lambda x: -float(x["lift"]))
            a, b = ordered[0], ordered[-1]

        subj = radar.get("subject") or {}
        who = ("@" + subj["handle"]) if subj.get("handle") else (subj.get("niche") or "this niche")
        is_shared = radar.get("scope") == "shared"

        def _side(x, win):
            ex0 = (x.get("examples") or [{}])[0]
            rows = [
                {"k": "Volume", "v": "%d posts (%s)" % (x.get("posts_total") or 0, ("%d creators" % x["creators"]) if is_shared else _pct(x.get("share")))},
                {"k": "Hit rate (2×+)", "v": _pct(x.get("hit_rate"))},
                {"k": "Direction", "v": (fmt_x(x["direction"]) + " " + (x.get("direction_label") or "")) if x.get("direction") is not None else "too few posts"},
                {"k": "Effort", "v": str(x.get("effort") or "—").capitalize()},
                {"k": "Best post", "v": "%s · %s views" % (fmt_x(ex0.get("ratio")), _compact(ex0.get("views"))) if ex0.get("ratio") is not None else "—"},
            ]
            qn = QN_MAP.get(x.get("quadrant"), x.get("quadrant_name") or "")
            lbl = "median vs usual" + (" (lead)" if x.get("few_posts") else "")
            return {"name": md(x.get("name") or x["id"]), "badge": qn, "hero_n": fmt_x(x.get("lift")),
                    "hero_label": lbl, "win": win, "rows": rows}

        la, lb = float(a["lift"]), float(b["lift"])
        a_wins = la >= lb
        rel = fmt_x(max(la, lb) / max(0.01, min(la, lb)))
        win_name = a.get("name") if a_wins else b.get("name")
        lose_name = b.get("name") if a_wins else a.get("name")
        verdict = {"n": rel, "label": md("%s beats %s by %s on median lift%s." % (
            win_name, lose_name, rel, " (small sample noted)" if (a.get("few_posts") or b.get("few_posts")) else ""))}
        return {
            "type": "compare",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Compare two"),
            "title": self._safe_prose("title", spec.get("title") or ("<b>%s</b> vs <b>%s</b>" % (a.get("name"), b.get("name")))),
            "sub": self._safe_prose("sub", spec.get("sub") or ("Same %s (%s). Both formats measured against usual (1×)." % (
                "niche" if is_shared else "account", who))),
            "left": _side(a, True if a_wins else False),
            "right": _side(b, False if a_wins else True),
            "verdict": verdict,
            "foot": "1× = %s’s usual · Study view comparison · radar.json" % html.escape(who),
            "brand": "Measured with <b>REA Viral</b>",
        }

    def _compare_accounts(self, spec, f1, f2):
        def _load_acc(folder):
            an = read_json(os.path.join(folder, "analysis.json"))
            rd = read_json(os.path.join(folder, "radar.json")) if os.path.exists(os.path.join(folder, "radar.json")) else {}
            wr = read_json(os.path.join(folder, "writing.json")) if os.path.exists(os.path.join(folder, "writing.json")) else {}
            acc = an.get("account") or {}
            c = an.get("counts") or {}
            scored = c.get("scored") or 0
            hr = (c.get("hits", 0) / float(scored)) if scored else 0.0
            fmts = [x for x in (rd.get("formats") or []) if x.get("lift") is not None]
            best_f = max(fmts, key=lambda x: float(x["lift"])) if fmts else None
            weak_f = min(fmts, key=lambda x: float(x["lift"])) if fmts else None
            strong_w = [x for x in (wr.get("features") or []) if x.get("claim_ok") and x.get("verdict") == "lifts"]
            strong_w.sort(key=lambda x: -((x.get("with") or {}).get("lift") or 0))
            pw = ((an.get("timeline") or {}).get("rhythm") or {}).get("posts_per_week")
            return {
                "handle": acc.get("handle") or os.path.basename(folder),
                "followers": acc.get("followers"),
                "scored": scored,
                "hit_rate": hr,
                "per_week": pw,
                "best_f": best_f,
                "weak_f": weak_f,
                "top_w": strong_w[0] if strong_w else None,
            }

        a, b = _load_acc(f1), _load_acc(f2)
        a_wins = a["hit_rate"] >= b["hit_rate"]

        def _side(x, win):
            rows = [
                {"k": "Followers", "v": _compact(x["followers"])},
                {"k": "Posts / week", "v": ("%.1f / wk" % x["per_week"]) if x["per_week"] is not None else "—"},
                {"k": "Best format", "v": ("%s · %s" % (_trim(x["best_f"]["name"], 22), fmt_x(x["best_f"]["lift"]))) if x["best_f"] else "—"},
                {"k": "Weakest format", "v": ("%s · %s" % (_trim(x["weak_f"]["name"], 22), fmt_x(x["weak_f"]["lift"]))) if x["weak_f"] else "—"},
                {"k": "Top writing", "v": ("%s · %s" % (_trim(x["top_w"]["label"], 20), fmt_x((x["top_w"].get("with") or {}).get("lift")))) if x["top_w"] else "none measured"},
            ]
            return {"name": "@" + html.escape(x["handle"]), "badge": "Higher hit rate" if win else "Lower hit rate",
                    "hero_n": _pct(x["hit_rate"]), "hero_label": "hit rate (2×+ usual · %d scored)" % x["scored"],
                    "win": win, "rows": rows}

        hi, lo = (a, b) if a_wins else (b, a)
        verdict = {"n": _pct(hi["hit_rate"]), "label": md("@%s hits 2× usual on %s of posts vs %s for @%s." % (
            hi["handle"], _pct(hi["hit_rate"]), _pct(lo["hit_rate"]), lo["handle"]))}
        return {
            "type": "compare",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Compare two accounts"),
            "title": self._safe_prose("title", spec.get("title") or ("<b>@%s</b> vs <b>@%s</b>" % (a["handle"], b["handle"]))),
            "sub": self._safe_prose("sub", spec.get("sub") or "Two accounts side by side, each measured against its own usual (1×)."),
            "left": _side(a, True if a_wins else False),
            "right": _side(b, False if a_wins else True),
            "verdict": verdict,
            "foot": "Measured from two run folders · analysis.json + radar.json",
            "brand": "Measured with <b>REA Viral</b>",
        }

    # ------------------------------------------------------------------ 10. topic check (r6)
    def topic(self, spec):
        f = self.folder
        tp = os.path.join(f, "topic_check.json")
        if not os.path.exists(tp):
            die("no topic_check.json in %s: run topic_check.py first (references/niche.md)" % f)
        tc = read_json(tp)
        sat, mom, late = tc.get("saturation") or {}, tc.get("momentum") or {}, tc.get("lateness") or {}
        sz = tc.get("sample_sizes") or {}
        sat_lvl = sat.get("level") or "unknown"
        mom_lvl = mom.get("level") or "not_enough_data"
        late_band = late.get("band") or "none_yet"

        if sat_lvl == "taken" or (late_band == "late" and mom_lvl == "fading"):
            v_status, v_label = "skip", "TAKEN · SKIP OR NEW ANGLE"
        elif sat_lvl == "low" and mom_lvl == "rising":
            v_status, v_label = "go", "POST WITHIN HOURS"
        elif sat_lvl == "low" and mom_lvl in ("flat", "not_enough_data"):
            v_status, v_label = "go" if mom_lvl == "flat" else "caution", "OPEN WINDOW" if mom_lvl == "flat" else "EARLY · SMALL SAMPLE"
        else:
            v_status, v_label = "caution", "ACTIVE · NEEDS NEW ANGLE"

        sat_tone = "bad" if sat_lvl == "taken" else ("warn" if sat_lvl == "medium" else "good")
        mom_tone = "good" if mom_lvl == "rising" else ("bad" if mom_lvl == "fading" else "warn")
        late_tone = "good" if late_band in ("none_yet", "early") else ("warn" if late_band == "tight" else "bad")

        l6 = mom.get("last_6h") or {}
        p6 = mom.get("prev_6h") or {}
        signals = [
            {"k": "Saturation (%dh)" % (sat.get("window_hours") or 48), "n": sat_lvl.upper(),
             "sub": "%d large breakouts · %d posts read" % (len(sat.get("large_account_breakouts") or []), sat.get("posts_in_window") or 0),
             "tone": sat_tone},
            {"k": "Momentum (6h)", "n": "FEW POSTS" if mom_lvl == "not_enough_data" else mom_lvl.upper(),
             "sub": "%d (%s/h) vs %d prev (%s/h)" % (l6.get("posts") or 0, l6.get("per_hour") or 0, p6.get("posts") or 0, p6.get("per_hour") or 0),
             "tone": mom_tone},
            {"k": "Lateness",
             "n": _hours_text(late.get("hours_since_first_big")) if late.get("hours_since_first_big") is not None else "NONE YET",
             "sub": ("since first %s+ post (%s)" % (_compact(late.get("big_views_threshold") or 100000), late_band))
             if late.get("first_big_post") else "no %s+ breakout yet" % _compact(late.get("big_views_threshold") or 100000),
             "tone": late_tone},
        ]

        proof_posts = []
        for p in (sat.get("top_posts") or [])[:3]:
            fl = "large + breakout" if (p.get("large_account") and p.get("breakout")) else (
                "breakout" if p.get("breakout") else ("large account" if p.get("large_account") else ""))
            proof_posts.append({
                "author": "@" + html.escape(p.get("author") or "unknown"),
                "followers": _compact(p.get("author_followers")) if p.get("author_followers") is not None else "",
                "views": _compact(p.get("views")),
                "age": _hours_text(p.get("hours_ago")) + " ago" if p.get("hours_ago") is not None else "",
                "flag": fl,
            })

        nets = tc.get("networks") or []
        net_s = (" on " + NETWORK.get(nets[0], nets[0])) if nets else ""
        return {
            "type": "topic",
            "kicker": self._safe_prose("kicker", spec.get("kicker") or "Topic check · Still worth posting?"),
            "title": self._safe_prose("title", spec.get("title") or ("<b>%s</b>%s" % (tc.get("topic") or "Topic", net_s))),
            "sampled": "Sample only · no time filter" if tc.get("sampled") else None,
            "verdict": {"status": v_status, "label": v_label, "text": md(tc.get("verdict") or "")},
            "signals": signals,
            "bars": {"prev_n": p6.get("posts") or 0, "prev_rate": "%s/h" % (p6.get("per_hour") or 0),
                     "last_n": l6.get("posts") or 0, "last_rate": "%s/h" % (l6.get("per_hour") or 0)},
            "proof_posts": proof_posts,
            "foot": "%s: %d posts in 48h (%d last 6h, %d prev 6h) · topic_check.json" % (
                "Sample only" if tc.get("sampled") else "Read", sz.get("last_48h") or 0, sz.get("last_6h") or 0, sz.get("prev_6h") or 0),
            "brand": "Measured with <b>REA Viral</b>",
        }


# ---------------------------------------------------------------------------------------------- drafts from the run

NUMBER_FOR = (
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
        if key.startswith(prefix) and not fill_card(n, g)[1] and not fill_card(unit, g)[1]:
            return n, unit
    for m in G.PLACEHOLDER_RE.finditer(claim.get("text") or ""):
        if not fill_card(m.group(0), g)[1]:
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


def draft_spec(folder, kind, fmt_id=None, draft_path=None, pair=None, vs=None):
    if kind == "teardown":
        return draft_teardown(folder)
    if kind == "report":
        return draft_report(folder)
    spec = {"schema": "rea-viral/card@1", "type": kind, "layout": DEFAULT_LAYOUT[kind], "skin": "cobalt"}
    if kind == "format" and fmt_id:
        spec["format"] = fmt_id
    if kind == "draft" and draft_path:
        spec["draft_file"] = draft_path
    if kind == "compare":
        if pair:
            spec["pair"] = [x.strip() for x in pair.split(",") if x.strip()]
        if vs:
            spec["vs"] = vs
    return spec


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


LAYOUT_KIND = {
    "t1": "teardown", "t2": "teardown", "t3": "teardown", "t4": "teardown", "t5": "teardown",
    "r1": "report", "r2": "report", "r3": "report", "r4": "report", "r5": "report", "r6": "topic",
    "p1": "post", "p2": "post", "p3": "post",
    "f1": "format", "f2": "format",
    "a1": "account", "a2": "account",
    "d1": "draft", "w1": "writing", "c1": "comments", "x1": "compare",
}


def kind_of(folder, want_type, want_layout=None, fmt_id=None, draft_path=None, pair=None, vs=None):
    if want_type:
        return want_type
    if want_layout and want_layout != "all" and want_layout in LAYOUT_KIND:
        k = LAYOUT_KIND[want_layout]
        if k == "topic" and os.path.exists(os.path.join(folder, "niche.json")) and not os.path.exists(os.path.join(folder, "topic.json")):
            return "topic"  # topic_check.json inside a niche folder renders cleanly via topic()
        return k
    if draft_path:
        return "draft"
    if pair or vs:
        return "compare"
    if fmt_id:
        return "format"
    if os.path.exists(os.path.join(folder, "topic.json")):
        return "topic"
    if os.path.exists(os.path.join(folder, "post.json")):
        return "post"
    if os.path.exists(os.path.join(folder, "niche.json")):
        return "report"
    if os.path.exists(os.path.join(folder, "growth.json")):
        return "teardown"
    if os.path.exists(os.path.join(folder, "analysis.json")) and os.path.exists(os.path.join(folder, "radar.json")):
        return "account"
    if os.path.exists(os.path.join(folder, "writing.json")):
        return "writing"
    if os.path.exists(os.path.join(folder, "comments.json")):
        return "comments"
    die("%s has no recognized run outputs (growth.json, niche.json, post.json, topic.json, analysis.json+radar.json, writing.json, or comments.json)" % folder)


def main(argv):
    ap = argparse.ArgumentParser(description="The post picture of a run (references/post.md).")
    ap.add_argument("folder")
    ap.add_argument("--type", choices=tuple(LAYOUTS.keys()))
    ap.add_argument("--layout", help="t1..t5, r1..r6, p1..p3, f1..f2, a1..a2, d1, w1, c1, x1, or all")
    ap.add_argument("--skin", help="cobalt (default), redword, night, holo, paper, warm, glass, or all")
    ap.add_argument("--card", help="the card's lines (default: <run>/card.json; written as a draft when missing)")
    ap.add_argument("--format", dest="fmt_id", help="format id for format cards (f1, f2)")
    ap.add_argument("--draft", dest="draft_path", help="draft .md file for draft check card (d1)")
    ap.add_argument("--pair", help="two comma-separated format ids for compare card (x1)")
    ap.add_argument("--vs", help="second run folder for two-account compare card (x1)")
    ap.add_argument("--out", help="the PNG (default: <run>/post-card.png)")
    ap.add_argument("--scale", type=float, default=1, help="pixel density: 2 gives 2160 x 2700")
    ap.add_argument("--browser")
    ap.add_argument("--html-only", action="store_true", help="write the HTML, make no PNG")
    ap.add_argument("--check", action="store_true", help="check the card's lines only, write nothing")
    a = ap.parse_args(argv)
    folder = os.path.abspath(a.folder)
    if not os.path.isdir(folder):
        die("no such folder: " + folder)
    kind = kind_of(folder, a.type, a.layout, a.fmt_id, a.draft_path, a.pair, a.vs)
    card_path = os.path.abspath(a.card) if a.card else os.path.join(folder, "card.json")
    drafted = False
    if os.path.exists(card_path):
        try:
            spec = read_json(card_path)
        except ValueError as e:
            die("%s does not parse: %s" % (card_path, e))
        # When the user explicitly asks for another card type/layout on a folder that already has card.json (e.g. --layout f1
        # on an account folder with a teardown card.json), auto-draft the requested type without clobbering card.json.
        if not a.card and spec.get("type") and spec["type"] != kind and (a.type or a.layout or a.fmt_id or a.draft_path or a.pair or a.vs):
            spec = draft_spec(folder, kind, a.fmt_id, a.draft_path, a.pair, a.vs)
            drafted = True
    elif a.card:
        die("no such card file: " + card_path)
    else:
        spec = draft_spec(folder, kind, a.fmt_id, a.draft_path, a.pair, a.vs)
        if spec is None:
            die("no card.json and nothing to draft it from: findings.json has no \"growth\" reading (growth.md, step 4); "
                "write card.json yourself (references/post.md)", 1)
        drafted = True
        if not a.check:
            write_json(card_path, spec)
    if spec.get("type") and spec["type"] != kind:
        die("card.json is a %s card and this folder makes a %s card" % (spec["type"], kind))

    c = Card(folder)
    if kind == "teardown":
        d = c.teardown(spec)
    elif kind == "report":
        d = c.report(spec)
    elif kind == "post":
        d = c.post_card(spec)
    elif kind == "format":
        d = c.format_card(spec, a.fmt_id)
    elif kind == "account":
        d = c.account_card(spec)
    elif kind == "draft":
        d = c.draft_card(spec, a.draft_path)
    elif kind == "writing":
        d = c.writing_card(spec)
    elif kind == "comments":
        d = c.comments_card(spec)
    elif kind == "compare":
        d = c.compare_card(spec, a.pair, a.vs)
    elif kind == "topic":
        d = c.topic(spec)
    else:
        die("unknown card type: %s" % kind)

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
        need = {"t3": "hero", "t4": "proof", "r6": "topic" if kind == "report" else None}.get(lid)
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
