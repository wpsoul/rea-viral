#!/usr/bin/env python3
"""Check a run folder against the documented shapes and say exactly what is wrong.

    python3 validate.py <run folder> [--json]

Reads account.json (required), posts.csv, comments.csv, formats.json, findings.json, videos/*/notes.json and
cost.csv when they exist; post.json in a post run. A niche folder (niche.json): niche.json, found.csv, formats.json,
findings.json, cost.csv and every creator folder under accounts/ checked as an account (a post id must be unique
across the niche). Prints one line per problem: file, row, column and what to write instead.
Exit 0 = no errors (warnings may remain), 1 = errors, 2 = the folder could not be read.

What it checks: every column and field in references/data-shape.md, ids unique and resolvable, counts that look
wrong (views 0 with likes, more likes than views), files that rows point at, claims without an evidence label.
What it does not check: whether the numbers are true. That is the reader's job; say in the report where they came from.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    ACCOUNT_SCHEMAS, COMMENT_COLUMNS, COUNT_COLUMNS, EVIDENCE, NETWORKS, POST_COLUMNS, POST_TYPES,
    REQUIRED_COMMENT_COLUMNS, REQUIRED_POST_COLUMNS, TEXT_NETWORKS, UNKNOWN_WORDS, V2_POST_COLUMNS, ShapeError,
    parse_author_replies, parse_bool, parse_count, parse_float, parse_parts, parse_time, read_csv, read_json,
)

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
EFFORTS = ("low", "medium", "high")
SEEN_FIELDS = ("hook", "first_frame", "text_on_screen", "sound", "turn", "ask")


class Report(object):
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, where, msg):
        self.errors.append({"where": where, "problem": msg})

    def warn(self, where, msg):
        self.warnings.append({"where": where, "problem": msg})


# ---------------------------------------------------------------------------------------------- account.json

def check_account(folder, rep):
    path = os.path.join(folder, "account.json")
    if not os.path.exists(path):
        rep.err("account.json", "missing. Write it first (references/data-shape.md, account.json)")
        return None
    try:
        acc = read_json(path)
    except ValueError as e:
        rep.err("account.json", "not valid JSON: %s" % e)
        return None
    if not isinstance(acc, dict):
        rep.err("account.json", "must be one JSON object")
        return None
    w = "account.json"
    if acc.get("schema") not in ACCOUNT_SCHEMAS:
        rep.warn(w + ":schema", 'write "schema": "rea-viral/account@2" (version 1 files are read as they are)')
    elif acc.get("schema") == "rea-viral/account@1" and acc.get("network") in TEXT_NETWORKS:
        rep.warn(w + ":schema", 'a text network is shape version 2: write "schema": "rea-viral/account@2"')
    net = acc.get("network")
    if not net:
        rep.err(w + ":network", "missing; one of %s" % ", ".join(NETWORKS))
    elif net not in NETWORKS:
        rep.warn(w + ":network", "%r is not one of the tested networks (%s); the numbers still run" % (net, ", ".join(NETWORKS)))
    if not str(acc.get("handle") or "").strip():
        rep.err(w + ":handle", "missing; the account's handle without @")
    elif str(acc.get("handle")).startswith("@"):
        rep.warn(w + ":handle", "write the handle without the @")
    try:
        if parse_time(acc.get("read_at")) is None:
            rep.err(w + ":read_at", "missing; when the corpus was read, ISO 8601 UTC (e.g. 2026-11-14T09:30:00Z)")
    except ShapeError as e:
        rep.err(w + ":read_at", str(e))
    win = acc.get("window")
    if not isinstance(win, dict):
        rep.warn(w + ":window", 'missing; write {"from": "2025-11-14", "to": "2026-11-14"}. The scripts use the 365 days before read_at')
    else:
        for k in ("from", "to"):
            try:
                if parse_time(win.get(k)) is None:
                    rep.err(w + ":window." + k, "missing; an ISO date")
            except ShapeError as e:
                rep.err(w + ":window." + k, str(e))
    for k in ("followers", "following", "posts_total"):
        if acc.get(k) is not None:
            try:
                parse_count(str(acc.get(k)), k)
                if not isinstance(acc.get(k), int):
                    rep.err(w + ":" + k, "write a JSON number, not a string (%r)" % acc.get(k))
            except ShapeError as e:
                rep.err(w + ":" + k, str(e))
    for k in ("followers_exact", "private", "verified"):
        if k in acc and acc.get(k) is not None and not isinstance(acc.get(k), bool):
            rep.err(w + ":" + k, "true, false or null")
    if acc.get("followers") is not None and acc.get("followers_exact") is None:
        rep.warn(w + ":followers_exact", "say whether the count is exact (false when the network shows 12.3M)")
    hist = acc.get("follower_history") or []
    if not isinstance(hist, list):
        rep.err(w + ":follower_history", "a list of {at, followers, source}")
        hist = []
    for i, h in enumerate(hist):
        where = "%s:follower_history[%d]" % (w, i)
        if not isinstance(h, dict):
            rep.err(where, "an object {at, followers, source}")
            continue
        try:
            if parse_time(h.get("at")) is None:
                rep.err(where + ".at", "missing")
        except ShapeError as e:
            rep.err(where + ".at", str(e))
        f = h.get("followers")
        if not isinstance(f, int) or isinstance(f, bool) or f < 0:
            rep.err(where + ".followers", "a whole number (got %r)" % (f,))
    src = acc.get("sources")
    if not isinstance(src, list) or not src:
        rep.warn(w + ":sources", 'list what was read with what, e.g. [{"what": "posts", "via": "yt-dlp 2026.07.04", "cost_usd": 0}]')
    cr = acc.get("comments_read")
    if cr is not None:
        if not isinstance(cr, dict):
            rep.err(w + ":comments_read", 'an object {"posts": 14, "per_post": 50, "replies_read": true}')
        elif cr.get("replies_read") is not None and not isinstance(cr.get("replies_read"), bool):
            rep.err(w + ":comments_read.replies_read", "true or false")
    ceiling = acc.get("spend_ceiling_usd")
    if ceiling is not None and (not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling < 0):
        rep.err(w + ":spend_ceiling_usd", "a number of dollars, 0 or more")
    pic = acc.get("picture_file")
    if pic not in (None, ""):
        if not isinstance(pic, str) or os.path.isabs(pic):
            rep.err(w + ":picture_file", "the account's picture, relative to the run folder (e.g. covers/_profile.jpg)")
        elif not os.path.exists(os.path.join(folder, pic)):
            rep.warn(w + ":picture_file", "%r does not exist; leave it out when the picture was not saved" % pic)
    return acc


# ---------------------------------------------------------------------------------------------- posts.csv

def check_posts(folder, acc, rep):
    path = os.path.join(folder, "posts.csv")
    if not os.path.exists(path):
        if acc and acc.get("private"):
            return {}
        rep.err("posts.csv", "missing. A private or empty account still gets posts.csv with the header row only")
        return {}
    try:
        header, rows = read_csv(path)
    except (UnicodeDecodeError, OSError) as e:
        rep.err("posts.csv", "cannot read: %s (save it as UTF-8)" % e)
        return {}
    for c in REQUIRED_POST_COLUMNS:
        if c not in header:
            rep.err("posts.csv:header", "column %r is missing" % c)
    for c in header:
        if c not in POST_COLUMNS:
            rep.warn("posts.csv:header", "column %r is not in the shape; it is ignored" % c)
    v2 = [c for c in header if c in V2_POST_COLUMNS]
    if v2 and acc and acc.get("schema") == "rea-viral/account@1":
        rep.warn("account.json:schema", "posts.csv has shape-2 columns (%s): write \"schema\": \"rea-viral/account@2\"" % ", ".join(v2))
    if any(c not in header for c in REQUIRED_POST_COLUMNS):
        return {}
    try:
        read_at = parse_time(acc.get("read_at")) if acc else None
    except ShapeError:
        read_at = None
    seen = {}
    no_date = 0
    for i, r in enumerate(rows):
        n = i + 2
        where = "posts.csv:row %d" % n
        pid = (r.get("post_id") or "").strip()
        if not pid:
            rep.err(where + ":post_id", "empty; every post needs its id as the network gives it")
        elif pid in seen:
            rep.err(where + ":post_id", "%r repeats row %d; one row per post" % (pid, seen[pid]))
        else:
            seen[pid] = n
        url = (r.get("url") or "").strip()
        if not url:
            rep.err(where + ":url", "empty; the post's public link")
        elif not re.match(r"^https?://", url):
            rep.err(where + ":url", "%r is not an http(s) link" % url)
        try:
            pub = parse_time(r.get("published_at"))
            if pub is None:
                no_date += 1
            elif read_at is not None and pub > read_at:
                rep.err(where + ":published_at", "%s is after account.json read_at" % r.get("published_at"))
        except ShapeError as e:
            rep.err(where + ":published_at", str(e))
        t = (r.get("type") or "").strip().lower()
        if t == "":
            rep.err(where + ":type", "empty; one of %s" % ", ".join(POST_TYPES))
        elif t not in POST_TYPES:
            hint = ""
            if t in ("reel", "reels", "short", "shorts", "tiktok", "clip"):
                hint = " (a reel, short or TikTok is type video)"
            elif t in ("photo", "picture"):
                hint = " (a single picture is type image)"
            elif t in ("post", "tweet", "status", "note", "note_tweet", "long"):
                hint = " (words with no picture or video are type text; with one picture, image; see data-shape.md)"
            elif t in ("quote_tweet", "quoted", "qt"):
                hint = " (a post that quotes another is type quote)"
            elif t in ("sidecar", "album", "slideshow", "slides"):
                hint = " (several pictures in one post are type carousel)"
            elif t in ("retweet", "repost", "rt", "reply"):
                hint = " (another account's post shared, or a reply to someone else, is not this account's post: leave it out)"
            rep.err(where + ":type", "%r is not one of %s%s" % (t, ", ".join(POST_TYPES), hint))
        counts = {}
        for c in COUNT_COLUMNS:
            if c not in header:
                continue
            try:
                counts[c] = parse_count(r.get(c), c)
            except ShapeError as e:
                rep.err(where + ":" + c, str(e))
        v, lk = counts.get("views"), counts.get("likes")
        if v == 0 and lk:
            rep.warn(where + ":views", "views 0 but likes %d: if the views are unknown, leave the cell empty" % lk)
        elif v is not None and lk is not None and v > 0 and lk > v:
            rep.warn(where + ":likes", "more likes (%d) than views (%d): check the columns are not swapped" % (lk, v))
        if "duration_s" in header:
            try:
                parse_float(r.get("duration_s"), "duration_s")
            except ShapeError as e:
                rep.err(where + ":duration_s", str(e))
        for c in ("is_pinned", "is_paid"):
            if c in header:
                try:
                    parse_bool(r.get(c), c)
                except ShapeError as e:
                    rep.err(where + ":" + c, str(e))
        if "read_at" in header:
            try:
                parse_time(r.get("read_at"))
            except ShapeError as e:
                rep.err(where + ":read_at", str(e))
        for c in ("cover_file", "video_file", "transcript_file"):
            f = (r.get(c) or "").strip()
            if f:
                if os.path.isabs(f):
                    rep.err(where + ":" + c, "%r must be relative to the run folder (e.g. covers/%s.jpg)" % (f, pid or "id"))
                elif not os.path.exists(os.path.join(folder, f)):
                    rep.warn(where + ":" + c, "%r does not exist; clear the cell if the file was not saved" % f)
        for c in ("caption", "sound"):
            s = (r.get(c) or "").strip()
            if s.lower() in UNKNOWN_WORDS and s:
                rep.warn(where + ":" + c, "%r: leave the cell empty when unknown" % s)
        # Shape 2: the text networks' columns.
        parts = None
        if "parts" in header:
            try:
                parts = parse_parts(r.get("parts"))
            except ShapeError as e:
                rep.err(where + ":parts", str(e))
            if parts is not None:
                cap = (r.get("caption") or "").strip()
                if len(parts) < 2:
                    rep.warn(where + ":parts", "one part only: leave parts empty for a single post")
                elif cap and parts[0].strip() != cap:
                    rep.warn(where + ":parts", "the first part should be the caption (the text people see first)")
                if t and t in POST_TYPES and t != "thread" and len(parts) >= 2:
                    rep.warn(where + ":type", "the row has %d parts: a thread is type thread" % len(parts))
        if t == "thread" and parts is None:
            rep.warn(where + ":parts", "type thread with no parts: write the parts' texts as a JSON list")
        if "author_replies" in header:
            try:
                parse_author_replies(r.get("author_replies"))
            except ShapeError as e:
                rep.err(where + ":author_replies", str(e))
        if "quoted_url" in header:
            q = (r.get("quoted_url") or "").strip()
            if q and not re.match(r"^https?://", q):
                rep.err(where + ":quoted_url", "%r is not an http(s) link to the quoted post" % q)
        if "lang" in header:
            lg = (r.get("lang") or "").strip()
            if lg and not re.fullmatch(r"[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})*", lg):
                rep.err(where + ":lang", "%r is not a language tag (write en, es, pt-BR; empty when the network gives none)" % lg)
        cap = r.get("caption") or ""
        if re.search(r"https://t\.co/\w+\s*$", cap) and t in ("image", "video", "carousel", "quote"):
            rep.warn(where + ":caption", "ends with a t.co link on a post with media or a quote: on X that link is the "
                                         "attachment, not a link out. Remove it (data-shape.md, text networks)")
    if rows and no_date:
        msg = "%d of %d posts have no published_at; they are left out of baselines and the timeline" % (no_date, len(rows))
        if no_date * 2 > len(rows):
            msg += ". Most rows have no date: read the posts with a source whose rows carry dates"
        rep.warn("posts.csv:published_at", msg)
    if acc and acc.get("private") and rows:
        rep.warn("account.json:private", "the account is marked private but posts.csv has rows")
    return seen


# ---------------------------------------------------------------------------------------------- comments.csv

def check_comments(folder, acc, posts, rep):
    path = os.path.join(folder, "comments.csv")
    if not os.path.exists(path):
        return
    header, rows = read_csv(path)
    for c in REQUIRED_COMMENT_COLUMNS:
        if c not in header:
            rep.err("comments.csv:header", "column %r is missing" % c)
    for c in header:
        if c not in COMMENT_COLUMNS:
            rep.warn("comments.csv:header", "column %r is not in the shape; it is ignored" % c)
    if any(c not in header for c in REQUIRED_COMMENT_COLUMNS):
        return
    cr = (acc or {}).get("comments_read") or {}
    if cr.get("replies_read") is None:
        rep.warn("account.json:comments_read.replies_read",
                 "say whether replies were read (true/false); without it the reply rate is reported as unknown")
    ids = {}
    parents = []
    for i, r in enumerate(rows):
        n = i + 2
        where = "comments.csv:row %d" % n
        pid = (r.get("post_id") or "").strip()
        cid = (r.get("comment_id") or "").strip()
        if not pid:
            rep.err(where + ":post_id", "empty")
        elif posts and pid not in posts:
            rep.warn(where + ":post_id", "%r is not in posts.csv" % pid)
        if not cid:
            rep.err(where + ":comment_id", "empty")
        elif cid in ids:
            rep.err(where + ":comment_id", "%r repeats row %d" % (cid, ids[cid]))
        else:
            ids[cid] = n
        par = (r.get("parent_id") or "").strip()
        if par:
            parents.append((n, par))
            if par == cid:
                rep.err(where + ":parent_id", "a comment cannot answer itself")
        try:
            parse_time(r.get("created_at"))
        except ShapeError as e:
            rep.err(where + ":created_at", str(e))
        for c in ("likes", "reply_count"):
            if c in header:
                try:
                    parse_count(r.get(c), c)
                except ShapeError as e:
                    rep.err(where + ":" + c, str(e))
        for c in ("author_is_creator", "is_pinned", "is_hearted", "created_at_exact"):
            if c in header:
                try:
                    parse_bool(r.get(c), c)
                except ShapeError as e:
                    rep.err(where + ":" + c, str(e))
    for n, par in parents:
        if par not in ids:
            rep.warn("comments.csv:row %d:parent_id" % n, "%r is not a comment in this file (the reply's parent was not read)" % par)
    if "author_is_creator" not in header:
        rep.warn("comments.csv:header", "no author_is_creator column: the creator's own comments and replies cannot be counted")


# ---------------------------------------------------------------------------------------------- formats.json

def check_formats(folder, posts, rep):
    path = os.path.join(folder, "formats.json")
    if not os.path.exists(path):
        return
    try:
        doc = read_json(path)
    except ValueError as e:
        rep.err("formats.json", "not valid JSON: %s" % e)
        return
    fm = doc.get("formats")
    if not isinstance(fm, list):
        rep.err("formats.json:formats", "a list of formats")
        return
    owner = {}
    ids = set()
    for i, f in enumerate(fm):
        where = "formats.json:formats[%d]" % i
        if not isinstance(f, dict):
            rep.err(where, "an object")
            continue
        fid = f.get("id")
        if not isinstance(fid, str) or not SLUG.match(fid):
            rep.err(where + ".id", "a short slug of a-z, 0-9 and - (got %r)" % (fid,))
        elif fid in ids:
            rep.err(where + ".id", "%r repeats" % fid)
        else:
            ids.add(fid)
        if not str(f.get("name") or "").strip():
            rep.err(where + ".name", "missing")
        for k in ("hook", "structure", "look", "length"):
            if not str(f.get(k) or "").strip():
                rep.warn(where + "." + k, "empty; a format is a container: hook, structure, look and length")
        if f.get("effort") not in EFFORTS:
            rep.err(where + ".effort", "one of low, medium, high (got %r)" % (f.get("effort"),))
        plist = f.get("posts")
        if not isinstance(plist, list) or not plist:
            rep.err(where + ".posts", "the post ids that use this format")
            continue
        for p in plist:
            if posts and p not in posts:
                rep.err(where + ".posts", "%r is not a post_id in posts.csv" % (p,))
            elif p in owner and owner[p] != fid:
                rep.err(where + ".posts", "%r is already in format %r; a post belongs to one format" % (p, owner[p]))
            else:
                owner[p] = fid
    for i, s in enumerate(doc.get("series") or []):
        where = "formats.json:series[%d]" % i
        if not isinstance(s, dict) or not isinstance(s.get("posts"), list) or len(s.get("posts")) < 2:
            rep.err(where, 'an object {"id", "name", "posts": [at least two ids, in order]}')
            continue
        for p in s["posts"]:
            if posts and p not in posts:
                rep.err(where + ".posts", "%r is not a post_id in posts.csv" % (p,))


# ---------------------------------------------------------------------------------------------- findings.json

def _resolve(doc, keypath):
    """Follow a.b.c through dicts; in a list, a part matches an item's id (radar.json#formats.<id>.lift) or index.
    An id may hold dots (a handle like studio.mira: trends.json#creators.youtube-studio.mira.hits), so the longest run
    of parts that names a key or an id wins."""
    parts = keypath.split(".")
    cur, i = doc, 0
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
            return False
        cur, i = step
    return True


def _texts_by_post(folder):
    """Captions, thread parts, the author's later replies, comment texts and the first lines written down from the
    videos, per post, lower case: what a quoted claim is checked against. A niche folder: every creator folder's."""
    if os.path.exists(os.path.join(folder, "niche.json")):
        from common import niche_creator_dirs
        merged = {}
        for d in niche_creator_dirs(folder):
            for pid, texts in _texts_by_post(os.path.join(folder, d)).items():
                merged.setdefault(pid, []).extend(texts)
        return merged
    out = {}
    for name, key in (("posts.csv", "caption"), ("comments.csv", "text")):
        p = os.path.join(folder, name)
        if os.path.exists(p):
            _, rows = read_csv(p)
            for r in rows:
                pid = (r.get("post_id") or "").strip()
                out.setdefault(pid, []).append((r.get(key) or "").lower())
                if name == "posts.csv":
                    try:
                        out[pid].extend(x.lower() for x in (parse_parts(r.get("parts")) or []))
                        out[pid].extend((x.get("text") or "").lower() for x in (parse_author_replies(r.get("author_replies")) or []))
                    except ShapeError:
                        pass
    vdir = os.path.join(folder, "videos")
    if os.path.isdir(vdir):
        for pid in os.listdir(vdir):
            n = os.path.join(vdir, pid, "notes.json")
            if os.path.exists(n):
                try:
                    line = ((read_json(n).get("seen") or {}).get("first_line") or "")
                except ValueError:
                    line = ""
                if isinstance(line, str) and line:
                    out.setdefault(pid, []).append(line.lower())
    return out


def _norm_quote(q):
    return re.sub(r"\s+", " ", (q or "").replace("\u2019", "'").replace("\u2018", "'").strip().lower())


def check_claim(c, where, folder, rep, need_text=True, texts=None):
    if not isinstance(c, dict):
        rep.err(where, "a claim object {text, evidence, ...}")
        return
    if need_text and not str(c.get("text") or "").strip():
        rep.err(where + ".text", "missing")
    ev = c.get("evidence")
    if ev not in EVIDENCE:
        rep.err(where + ".evidence", "one of MEASURED, SEEN, INFERRED (got %r)" % (ev,))
        return
    if ev == "SEEN" and not (c.get("posts") or c.get("links")):
        rep.err(where, "SEEN needs what shows it: posts (ids) or links")
    if ev == "INFERRED" and not str(c.get("basis") or "").strip():
        rep.err(where + ".basis", "INFERRED needs its basis written out")
    if ev == "MEASURED":
        frm = c.get("from")
        if not frm:
            rep.err(where + ".from", 'MEASURED needs the number\'s source, e.g. "radar.json#formats.three-mistakes.lift"')
        else:
            f, _, keypath = str(frm).partition("#")
            if f and not os.path.exists(os.path.join(folder, f)):
                rep.err(where + ".from", "%r: the file %r does not exist" % (frm, f))
            elif f.endswith(".json") and keypath:
                try:
                    doc = read_json(os.path.join(folder, f))
                except ValueError:
                    doc = None
                if doc is not None and not _resolve(doc, keypath):
                    rep.err(where + ".from", "%r: %s has no key %r (cite a key the script wrote)" % (frm, f, keypath))
    for p in c.get("posts") or []:
        if not isinstance(p, str):
            rep.err(where + ".posts", "post ids are strings")
    quotes = c.get("quote")
    if quotes:
        if texts is None:
            texts = _texts_by_post(folder)
        for q in (quotes if isinstance(quotes, list) else [quotes]):
            nq = _norm_quote(q)
            hay = [_norm_quote(t) for pid in (c.get("posts") or []) for t in texts.get(pid, [])]
            if not any(nq in h for h in hay):
                rep.err(where + ".quote", "%r is not in a caption or comment of the cited posts %s" % (q, c.get("posts") or []))


def check_findings(folder, posts, rep):
    path = os.path.join(folder, "findings.json")
    if not os.path.exists(path):
        return
    try:
        doc = read_json(path)
    except ValueError as e:
        rep.err("findings.json", "not valid JSON: %s" % e)
        return
    texts = _texts_by_post(folder)
    if doc.get("headline") is not None:
        check_claim(doc["headline"], "findings.json:headline", folder, rep, texts=texts)
    # account runs: mechanisms (what worked), did_not_work, comment_tactics, timeline_notes, writing; a niche adds
    # formats, hooks, creators; every way can write did_not_work
    for sec in ("mechanisms", "did_not_work", "comment_tactics", "timeline_notes", "writing", "formats", "hooks", "creators"):
        for i, c in enumerate(doc.get(sec) or []):
            check_claim(c, "findings.json:%s[%d]" % (sec, i), folder, rep, texts=texts)
            for p in (c.get("posts") or []) if isinstance(c, dict) else []:
                if posts and p not in posts:
                    rep.warn("findings.json:%s[%d].posts" % (sec, i), "%r is not in posts.csv" % p)
    plays = doc.get("plays") or []
    if len(plays) > 10:
        rep.err("findings.json:plays", "ten plays at most (got %d)" % len(plays))
    for i, p in enumerate(plays):
        where = "findings.json:plays[%d]" % i
        if not isinstance(p, dict):
            rep.err(where, "an object")
            continue
        if not str(p.get("title") or "").strip():
            rep.err(where + ".title", "missing")
        check_claim(p, where, folder, rep, need_text=False, texts=texts)
        if p.get("effort") not in EFFORTS:
            rep.err(where + ".effort", "one of low, medium, high")
        if not str(p.get("prompt") or "").strip():
            rep.err(where + ".prompt", "a ready prompt the user can paste")
        if not str(p.get("dont_copy") or "").strip():
            rep.warn(where + ".dont_copy", "say what not to copy (a face, an authority the user does not have), or 'nothing'")
    for i, n in enumerate(doc.get("not_read") or []):
        if not isinstance(n, dict) or not n.get("what") or not n.get("why"):
            rep.err("findings.json:not_read[%d]" % i, "an object {what, why}")


# ---------------------------------------------------------------------------------------------- videos/*/notes.json

def check_notes(folder, posts, rep):
    vdir = os.path.join(folder, "videos")
    if not os.path.isdir(vdir):
        return
    for name in sorted(os.listdir(vdir)):
        path = os.path.join(vdir, name, "notes.json")
        if not os.path.exists(path):
            continue
        where = "videos/%s/notes.json" % name
        try:
            n = read_json(path)
        except ValueError as e:
            rep.err(where, "not valid JSON: %s" % e)
            continue
        if n.get("post_id") != name:
            rep.err(where + ":post_id", "must be %r (the folder name)" % name)
        if posts and name not in posts:
            rep.warn(where, "%r is not in posts.csv" % name)
        if n.get("read") is True:
            seen = n.get("seen") or {}
            for k in SEEN_FIELDS:
                v = seen.get(k)
                if v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, dict) and not str(v.get("text") or "").strip()):
                    rep.err(where + ":seen." + k, 'not filled. Write what you saw, or "none" when there is none')
        elif n.get("read") is False:
            if not str(n.get("not_read_reason") or "").strip():
                rep.err(where + ":not_read_reason", "say why the video was not read")
        else:
            rep.err(where + ":read", "true once you looked at the frames, false with not_read_reason")


# ---------------------------------------------------------------------------------------------- cost.csv

def check_cost(folder, acc, rep):
    path = os.path.join(folder, "cost.csv")
    if not os.path.exists(path):
        return
    header, rows = read_csv(path)
    need = ["at", "step", "what", "calls", "unit_usd", "total_usd"]
    for c in need:
        if c not in header:
            rep.err("cost.csv:header", "column %r is missing (write it with ledger.py)" % c)
            return
    total = 0.0
    for i, r in enumerate(rows):
        try:
            total += parse_float(r.get("total_usd"), "total_usd") or 0.0
        except ShapeError as e:
            rep.err("cost.csv:row %d:total_usd" % (i + 2), str(e))
    ceiling = (acc or {}).get("spend_ceiling_usd")
    if isinstance(ceiling, (int, float)) and total > ceiling + 1e-9:
        rep.err("cost.csv", "spent $%.4f, over the ceiling $%.2f" % (total, ceiling))


def check_post_json(folder, posts, rep):
    """A post run (one link): post.json names the post the run is about; it must be a row of posts.csv."""
    path = os.path.join(folder, "post.json")
    try:
        doc = read_json(path)
    except ValueError as e:
        rep.err("post.json", "not valid JSON: %s" % e)
        return
    pid = str(doc.get("post_id") or "").strip()
    if not pid:
        rep.err("post.json:post_id", 'missing; the id of the post the user gave, e.g. {"post_id": "abc123", "url": "https://..."}')
    elif posts is not None and pid not in posts:
        rep.err("post.json:post_id", "%r is not a row of posts.csv: read the post itself into posts.csv too" % pid)


# ---------------------------------------------------------------------------------------------- a niche run

class _Prefixed(object):
    """Collects another Report's lines under a creator folder's path."""

    def __init__(self, rep, prefix):
        self.rep, self.prefix = rep, prefix

    def err(self, where, msg):
        self.rep.err(self.prefix + where, msg)

    def warn(self, where, msg):
        self.rep.warn(self.prefix + where, msg)


def check_niche(folder, rep):
    path = os.path.join(folder, "niche.json")
    try:
        n = read_json(path)
    except ValueError as e:
        rep.err("niche.json", "not valid JSON: %s" % e)
        return None
    if not isinstance(n, dict):
        rep.err("niche.json", "must be one JSON object")
        return None
    w = "niche.json"
    if n.get("schema") != "rea-viral/niche@1":
        rep.warn(w + ":schema", 'write "schema": "rea-viral/niche@1"')
    if not str(n.get("name") or "").strip():
        rep.err(w + ":name", "missing; the niche in a few words, e.g. \"AI video editing tools\"")
    if not (n.get("words") or n.get("tags") or n.get("seed_accounts")):
        rep.warn(w + ":words", "say how the niche was searched: words, tags or seed_accounts")
    try:
        if parse_time(n.get("read_at")) is None:
            rep.err(w + ":read_at", "missing; when the posts were read, ISO 8601 UTC")
    except ShapeError as e:
        rep.err(w + ":read_at", str(e))
    win = n.get("window")
    if not isinstance(win, dict):
        rep.warn(w + ":window", 'missing; write {"from": "2026-10-17", "to": "2026-11-16"}. The scripts use the 30 days before read_at')
    else:
        for k in ("from", "to"):
            try:
                if parse_time(win.get(k)) is None:
                    rep.err(w + ":window." + k, "missing; an ISO date")
            except ShapeError as e:
                rep.err(w + ":window." + k, str(e))
    nets = n.get("networks")
    if not isinstance(nets, list) or not nets:
        rep.warn(w + ":networks", "list the networks searched, e.g. [\"youtube\"]")
    ceiling = n.get("spend_ceiling_usd")
    if ceiling is not None and (not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling < 0):
        rep.err(w + ":spend_ceiling_usd", "a number of dollars, 0 or more")
    if not isinstance(n.get("sources"), list) or not n.get("sources"):
        rep.warn(w + ":sources", 'list what was read with what, e.g. [{"what": "search", "via": "yt-dlp", "cost_usd": 0}]')
    return n


def check_found(folder, ids, rep):
    path = os.path.join(folder, "found.csv")
    if not os.path.exists(path):
        return
    header, rows = read_csv(path)
    for c in ("post_id", "url", "found_by"):
        if c not in header:
            rep.err("found.csv:header", "column %r is missing (post_id, url, network, account, found_by, query)" % c)
            return
    missing = 0
    for i, r in enumerate(rows):
        where = "found.csv:row %d" % (i + 2)
        if not (r.get("post_id") or "").strip():
            rep.err(where + ":post_id", "empty")
        elif r["post_id"].strip() not in ids:
            missing += 1
        fb = (r.get("found_by") or "").strip()
        if fb not in ("search", "tag", "trending", "seed_account", "user_list", "other"):
            rep.err(where + ":found_by", "one of search, tag, trending, seed_account, user_list, other (got %r)" % fb)
    if missing:
        rep.warn("found.csv", "%d found posts are in no creator folder: their creators' posts were not read, so they "
                              "cannot be scored against their own usual" % missing)


def validate_niche(folder, inputs_only, rep):
    from common import niche_creator_dirs
    n = check_niche(folder, rep)
    dirs = niche_creator_dirs(folder)
    if not dirs:
        rep.err("accounts/", "no creator folder: write accounts/<network>-<handle>/account.json and posts.csv for each "
                             "creator (references/niche.md)")
    ids = {}
    for d in dirs:
        sub = _Prefixed(rep, d + "/")
        cf = os.path.join(folder, d)
        acc = check_account(cf, sub)
        posts = check_posts(cf, acc, sub)
        if acc:
            want = "%s-%s" % (acc.get("network"), str(acc.get("handle") or "").lstrip("@").lower())
            if d.split("/", 1)[1] != want:
                rep.warn(d, "the folder should be named accounts/%s (network-handle)" % want)
        for pid in posts:
            if pid in ids:
                rep.err(d + "/posts.csv:post_id", "%r is also a post of %s: a post id must be unique across the niche" % (pid, ids[pid]))
            else:
                ids[pid] = d
        if not inputs_only:
            check_comments(cf, acc, posts, sub)
            check_notes(cf, posts, sub)
    check_found(folder, ids, rep)
    check_formats(folder, ids, rep)
    if not inputs_only:
        check_findings(folder, ids, rep)
        check_cost(folder, n, rep)
    return rep


def validate(folder, inputs_only=False):
    """inputs_only: check only what the number scripts read (account, posts, comments, formats), so your later files
    (findings, notes, cost) never block a re-run of the numbers. build_report.py and the command line check all.
    A niche folder (niche.json) checks niche.json and every creator folder under accounts/ the same way."""
    rep = Report()
    if not os.path.isdir(folder):
        rep.err(folder, "not a folder")
        return rep
    if os.path.exists(os.path.join(folder, "niche.json")):
        return validate_niche(folder, inputs_only, rep)
    acc = check_account(folder, rep)
    posts = check_posts(folder, acc, rep)
    check_comments(folder, acc, posts, rep)
    check_formats(folder, posts, rep)
    if os.path.exists(os.path.join(folder, "post.json")):
        check_post_json(folder, posts, rep)
    if not inputs_only:
        check_findings(folder, posts, rep)
        check_notes(folder, posts, rep)
        check_cost(folder, acc, rep)
    return rep


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    rep = validate(folder)
    if "--json" in argv:
        print(json.dumps({"ok": not rep.errors, "errors": rep.errors, "warnings": rep.warnings}, indent=2))
    else:
        for e in rep.errors:
            print("ERROR   %s: %s" % (e["where"], e["problem"]))
        for w in rep.warnings:
            print("warning %s: %s" % (w["where"], w["problem"]))
        print("%s: %d error(s), %d warning(s)" % ("OK" if not rep.errors else "NOT OK", len(rep.errors), len(rep.warnings)))
    return 0 if not rep.errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
