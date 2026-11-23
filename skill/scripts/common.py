"""Shared helpers for the REA Viral scripts.

Standard library only, Python 3.8 or newer. Every script puts its own folder on sys.path before it imports this
file, so the scripts also run with `python3 -I`.

The file shapes these helpers read are documented in references/data-shape.md. Nothing here knows about any data
provider: the scripts read only the normalised rows.
"""
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
import tempfile
import urllib.error
import urllib.request

SKILL_VERSION = "0.4.1"  # 0.4.1 (2026-11-23): every cover on the sheet, own videos only, covers fetched like a browser, corner names that describe position
# Shape version 2 (2026-11-16) adds the text networks. It only ADDS: new networks, new post types and new optional
# columns. A version-1 run (account.json "rea-viral/account@1", the old posts.csv header) is read exactly as before.
NETWORKS = ("instagram", "tiktok", "youtube", "x", "threads", "linkedin")
TEXT_NETWORKS = ("x", "threads", "linkedin")
POST_TYPES = ("video", "carousel", "image", "text", "thread", "article", "quote", "live", "other")
ACCOUNT_SCHEMAS = ("rea-viral/account@1", "rea-viral/account@2")
EVIDENCE = ("MEASURED", "SEEN", "INFERRED")

POST_COLUMNS = [
    "post_id", "url", "published_at", "type", "duration_s", "caption",
    "views", "likes", "comments", "shares", "saves",
    "cover_url", "cover_file", "video_file", "transcript_file",
    "sound", "is_pinned", "is_paid", "collaborators", "read_at", "source",
    # shape 2: text networks (all optional)
    "reposts", "quotes", "bookmarks", "lang", "parts", "author_replies", "quoted_url",
    # 0.4.1 (optional): the post's OWN media, never a quoted or reposted post's; whom a row replies to
    "own_media", "reply_to", "reply_to_id",
]
V2_POST_COLUMNS = ["reposts", "quotes", "bookmarks", "lang", "parts", "author_replies", "quoted_url", "own_media",
                   "reply_to", "reply_to_id"]
OWN_MEDIA = ("video", "images", "image", "none")
VIDEO_NETWORKS = ("youtube", "tiktok", "instagram")
REQUIRED_POST_COLUMNS = ["post_id", "url", "published_at", "type"]
COUNT_COLUMNS = ["views", "likes", "comments", "shares", "saves", "reposts", "quotes", "bookmarks"]
# Language tags a network gives when a post has no words to tell by (X: zxx, und, qme, qht, qam, qct, qst).
NO_LANGUAGE_TAGS = {"", "zxx", "und", "qme", "qht", "qam", "qct", "qst", "art"}


def share_like(p):
    """Shares where the network counts them, else reposts (X, Threads, LinkedIn). None when neither is known."""
    return p.get("shares") if p.get("shares") is not None else p.get("reposts")


def save_like(p):
    """Saves where the network counts them, else bookmarks (X). None when neither is known."""
    return p.get("saves") if p.get("saves") is not None else p.get("bookmarks")

COMMENT_COLUMNS = [
    "post_id", "comment_id", "parent_id", "author", "author_is_creator", "text",
    "likes", "created_at", "created_at_exact", "is_pinned", "is_hearted", "reply_count",
]
REQUIRED_COMMENT_COLUMNS = ["post_id", "comment_id", "text"]

# Words that people write for "unknown". The shape says: unknown is an EMPTY cell. The validator names these.
UNKNOWN_WORDS = {"n/a", "na", "null", "none", "nil", "-", "--", "?", "unknown", "nan", "undefined"}

# What new followers write. Lower case; matched as whole phrases.
FOLLOW_PHRASES = [
    "just followed", "new follower", "followed you", "i followed", "instant follow", "earned a follow",
    "earned my follow", "got a new follower", "found you", "found your page", "found your account",
    "just subscribed", "subscribed", "just subbed", "new sub", "new subscriber", "here from", "came from",
    "first video i", "first time seeing", "you popped up", "on my fyp", "on my for you",
]
FOLLOW_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(p) for p in FOLLOW_PHRASES) + r")(?![a-z])", re.I)


class ShapeError(Exception):
    """A value that does not fit the documented shape."""


# ---------------------------------------------------------------------------------------------- values

def parse_time(value):
    """ISO 8601 to an aware UTC datetime. Empty → None. A bad value raises ShapeError.

    Accepted: 2026-10-03T14:05:00Z, 2026-10-03T14:05:00+02:00, 2026-10-03 14:05:00 (taken as UTC),
    2026-10-03 (taken as 00:00 UTC). A Unix time in seconds is refused: write it as ISO.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    if s.lower() in UNKNOWN_WORDS:
        raise ShapeError("write an empty cell for an unknown time, not %r" % s)
    if re.fullmatch(r"\d{9,11}(\.\d+)?", s):
        raise ShapeError("%r looks like a Unix time: write ISO 8601 UTC, e.g. 2026-10-03T14:05:00Z" % s)
    t = s.replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} \d", s) else s
    if t.endswith("Z") or t.endswith("z"):
        t = t[:-1] + "+00:00"
    # Python < 3.11 does not read fractions other than 3 or 6 digits; trim them.
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)(.*)$", t)
    if m:
        t = m.group(1) + "." + (m.group(2) + "000000")[:6] + m.group(3)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
            d = dt.datetime.strptime(t, "%Y-%m-%d")
        else:
            d = dt.datetime.fromisoformat(t)
    except ValueError:
        raise ShapeError("%r is not an ISO 8601 time, e.g. 2026-10-03T14:05:00Z" % s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def iso(d):
    if d is None:
        return None
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day(d):
    return None if d is None else d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")


def parse_count(value, name="count"):
    """A whole number ≥ 0. Empty → None. '12.3K', '1,200', '-1' and words raise ShapeError."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    if s.lower() in UNKNOWN_WORDS:
        raise ShapeError("%s: write an empty cell for unknown, not %r" % (name, s))
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d+\.0+", s):
        return int(float(s))
    if re.fullmatch(r"[\d.,]+\s*[kKmMbB]", s):
        raise ShapeError("%s: %r is abbreviated; write the whole number (12.3K → 12300)" % (name, s))
    if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
        raise ShapeError("%s: %r has thousands separators; write %s" % (name, s, s.replace(",", "")))
    if re.fullmatch(r"-\d+", s):
        raise ShapeError("%s: %r is negative; a count is 0 or more (unknown = empty)" % (name, s))
    raise ShapeError("%s: %r is not a whole number" % (name, s))


def parse_float(value, name="number"):
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    if s.lower() in UNKNOWN_WORDS:
        raise ShapeError("%s: write an empty cell for unknown, not %r" % (name, s))
    try:
        v = float(s)
    except ValueError:
        raise ShapeError("%s: %r is not a number" % (name, s))
    if math.isnan(v) or math.isinf(v) or v < 0:
        raise ShapeError("%s: %r must be a number 0 or more" % (name, s))
    return v


def parse_bool(value, name="flag"):
    if value is None:
        return None
    s = str(value).strip().lower()
    if s == "":
        return None
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    raise ShapeError("%s: %r must be true, false or empty" % (name, value))


def median(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return statistics.median(xs)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def rank_chance(a, b):
    """How often posts sorted at random would differ this much: the two-sided p of a Mann-Whitney rank test (normal
    approximation, ties averaged). None when a side is empty. Used for words (text_probe.py) and buckets (analyze.py)."""
    n1, n2 = len(a), len(b)
    if not n1 or not n2:
        return None
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks = [0.0] * len(allv)
    ties = 0.0
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    u = r1 - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    var = n1 * n2 / 12.0 * ((n + 1) - ties / float(n * (n - 1))) if n > 1 else 0
    if var <= 0:
        return 1.0
    z = (abs(u - n1 * n2 / 2.0) - 0.5) / math.sqrt(var)
    return max(0.0, min(1.0, 2 * (1 - 0.5 * (1 + math.erf(max(z, 0) / math.sqrt(2))))))


def rnd(x, n=3):
    if x is None:
        return None
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return round(x, n)
    return x


def now_utc():
    """The run's clock. REA_NOW=<ISO> fixes it (tests, re-runs of an old corpus)."""
    forced = os.environ.get("REA_NOW")
    if forced:
        return parse_time(forced)
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


# ---------------------------------------------------------------------------------------------- files

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    """Write atomically, so a reader never sees half a file."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def write_text(path, text):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_csv(path):
    """Rows as dicts of strings, plus the header. A BOM is ignored."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        header = list(r.fieldnames or [])
        rows = []
        for row in r:
            rows.append({k: (v if v is not None else "") for k, v in row.items() if k is not None})
        return header, rows


def write_csv(path, header, rows):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in header})
    os.replace(tmp, path)


def die(msg, code=2):
    sys.stderr.write("rea-viral: " + msg.rstrip() + "\n")
    sys.exit(code)


# ---------------------------------------------------------------------------------------------- loading

def load_account(folder):
    path = os.path.join(folder, "account.json")
    if not os.path.exists(path):
        die("no account.json in %s (see references/data-shape.md)" % folder)
    acc = read_json(path)
    return acc


def account_read_at(acc):
    t = parse_time(acc.get("read_at")) if acc.get("read_at") else None
    return t or now_utc()


def account_window(acc):
    w = acc.get("window") or {}
    lo = parse_time(w.get("from")) if w.get("from") else None
    hi = parse_time(w.get("to")) if w.get("to") else None
    if hi is not None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(w.get("to")).strip()):
        hi = hi + dt.timedelta(days=1) - dt.timedelta(seconds=1)  # a date-only "to" includes that day
    return lo, hi


REPLY_RE = re.compile(r"^\s*@([A-Za-z0-9_.]{1,40})\b")


def reply_kind(p, own_handle, network):
    """"other" for a reply to another account, "self" for the account's own reply under its post (a thread
    continuation), None for a post. The reader's reply_to (a handle) decides; without it, on X and Threads, a text
    that opens with @handle is a reply (their replies start with the handle they answer)."""
    rt = norm_handle(p.get("reply_to"))
    if not rt and network in ("x", "threads"):
        m = REPLY_RE.match(p.get("caption") or "")
        rt = norm_handle(m.group(1)) if m else ""
    if not rt:
        return None
    return "self" if own_handle and rt == norm_handle(own_handle) else "other"


def load_posts(folder, keep_replies=False):
    """Typed post rows. Unparseable cells become None here; validate.py is the strict reader.

    Replies are not posts (references/data-shape.md, "Replies"): a reply to another account is left out; the account's
    own reply under one of its posts is folded into that post when the row names it (reply_to_id): a thread part
    when it came within 2 minutes, else one of the author's later replies with its minutes; one that names no post it
    belongs to is left out. replies_left_out(folder) counts them. keep_replies=True gives every row (validate)."""
    rows_all = _load_rows(folder)
    if keep_replies:
        return rows_all
    try:
        acc = read_json(os.path.join(folder, "account.json"))
    except (OSError, ValueError):
        acc = {}
    own, net = acc.get("handle"), acc.get("network")
    by_id = dict((p["post_id"], p) for p in rows_all)
    out = []
    for p in rows_all:
        k = reply_kind(p, own, net)
        p["reply"] = k
        if k is None:
            out.append(p)
    for p in rows_all:
        if p["reply"] != "self":
            continue
        parent = by_id.get(p.get("reply_to_id") or "")
        if not parent or parent.get("reply") is not None:
            continue
        text = REPLY_RE.sub("", p.get("caption") or "", count=1).strip()
        mins = None
        if parent.get("published_at") and p.get("published_at"):
            mins = round((p["published_at"] - parent["published_at"]).total_seconds() / 60.0, 1)
        if mins is not None and 0 <= mins <= 2:
            parent["parts"] = (parent.get("parts") or [parent.get("caption") or ""]) + [text]
            if parent.get("type") in ("text", "image", "carousel", "video", "other"):
                parent["type"] = "thread"
        else:
            parent["author_replies"] = (parent.get("author_replies") or []) + [{"text": text, "minutes_after": mins}]
        p["reply"] = "folded"
    return out


def replies_left_out(folder):
    """{"other": replies to other accounts, "self": own replies that named no post, "folded": own replies folded}."""
    out = {"other": 0, "self": 0, "folded": 0}
    try:
        acc = read_json(os.path.join(folder, "account.json"))
    except (OSError, ValueError):
        acc = {}
    rows = load_posts(folder, keep_replies=True)
    by_id = dict((p["post_id"], p) for p in rows)
    for p in rows:
        k = reply_kind(p, acc.get("handle"), acc.get("network"))
        if k == "self" and (p.get("reply_to_id") or "") in by_id and reply_kind(by_id[p["reply_to_id"]], acc.get("handle"), acc.get("network")) is None:
            k = "folded"
        if k:
            out[k] += 1
    return out


def _load_rows(folder):
    path = os.path.join(folder, "posts.csv")
    if not os.path.exists(path):
        return []
    _, rows = read_csv(path)
    out = []
    for i, r in enumerate(rows):
        p = {"_row": i + 2}
        p["post_id"] = (r.get("post_id") or "").strip()
        p["url"] = (r.get("url") or "").strip()
        p["type"] = (r.get("type") or "").strip().lower() or "other"
        p["caption"] = r.get("caption") or ""
        for k in ("cover_url", "cover_file", "video_file", "transcript_file", "sound", "collaborators", "source"):
            p[k] = (r.get(k) or "").strip()
        for k in ("published_at", "read_at"):
            try:
                p[k] = parse_time(r.get(k))
            except ShapeError:
                p[k] = None
        for k in COUNT_COLUMNS:
            try:
                p[k] = parse_count(r.get(k), k)
            except ShapeError:
                p[k] = None
        try:
            p["duration_s"] = parse_float(r.get("duration_s"), "duration_s")
        except ShapeError:
            p["duration_s"] = None
        for k in ("is_pinned", "is_paid"):
            try:
                p[k] = parse_bool(r.get(k), k)
            except ShapeError:
                p[k] = None
        p["lang"] = (r.get("lang") or "").strip().lower()
        p["quoted_url"] = (r.get("quoted_url") or "").strip()
        p["own_media"] = (r.get("own_media") or "").strip().lower() or None
        p["reply_to"] = (r.get("reply_to") or "").strip().lstrip("@") or None
        p["reply_to_id"] = (r.get("reply_to_id") or "").strip() or None
        try:
            p["parts"] = parse_parts(r.get("parts"))
        except ShapeError:
            p["parts"] = None
        try:
            p["author_replies"] = parse_author_replies(r.get("author_replies"))
        except ShapeError:
            p["author_replies"] = None
        out.append(p)
    return out


def parse_parts(value):
    """A thread's parts: a JSON list of strings, in order, the first being the caption. Empty → None."""
    s = (value or "").strip()
    if not s:
        return None
    try:
        v = json.loads(s)
    except ValueError:
        raise ShapeError("parts: not JSON; write a JSON list of the parts' texts, e.g. [\"first\", \"second\"]")
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ShapeError("parts: a JSON list of strings (each part's text, in order)")
    return v


def parse_author_replies(value):
    """The author's own later replies under the post: a JSON list of {"text", "minutes_after"}. Empty → None."""
    s = (value or "").strip()
    if not s:
        return None
    try:
        v = json.loads(s)
    except ValueError:
        raise ShapeError('author_replies: not JSON; write [{"text": "...", "minutes_after": 270}]')
    if not isinstance(v, list) or not all(isinstance(x, dict) and isinstance(x.get("text"), str) for x in v):
        raise ShapeError('author_replies: a JSON list of objects {"text": "...", "minutes_after": number or null}')
    for x in v:
        m = x.get("minutes_after")
        if m is not None and (not isinstance(m, (int, float)) or isinstance(m, bool) or m < 0):
            raise ShapeError("author_replies: minutes_after is a number of minutes, 0 or more, or null")
    return v


def load_comments(folder):
    path = os.path.join(folder, "comments.csv")
    if not os.path.exists(path):
        return None
    _, rows = read_csv(path)
    out = []
    for i, r in enumerate(rows):
        c = {"_row": i + 2}
        for k in ("post_id", "comment_id", "parent_id", "author", "text"):
            c[k] = (r.get(k) or "").strip() if k != "text" else (r.get(k) or "")
        try:
            c["created_at"] = parse_time(r.get("created_at"))
        except ShapeError:
            c["created_at"] = None
        for k in ("likes", "reply_count"):
            try:
                c[k] = parse_count(r.get(k), k)
            except ShapeError:
                c[k] = None
        for k in ("author_is_creator", "is_pinned", "is_hearted", "created_at_exact"):
            try:
                c[k] = parse_bool(r.get(k), k)
            except ShapeError:
                c[k] = None
        if c["created_at_exact"] is False:
            c["created_at_day"] = c["created_at"]
            c["created_at"] = None  # "2 days ago" is not a time to measure minutes with
        out.append(c)
    return out


def load_formats(folder):
    path = os.path.join(folder, "formats.json")
    if not os.path.exists(path):
        return None
    return read_json(path)


def follower_readings(folder, acc):
    """All follower counts known for this account, oldest first: account.json's history plus our own Watch rows.

    Each reading: {"at": datetime, "followers": int, "source": str, "watch": bool}.
    """
    out = []
    for h in acc.get("follower_history") or []:
        try:
            t = parse_time(h.get("at"))
            f = parse_count(h.get("followers"), "followers")
        except ShapeError:
            continue
        if t is None or f is None:
            continue
        out.append({"at": t, "followers": f, "source": h.get("source") or "history", "watch": False})
    for counts in (os.path.join(folder, "watch", "counts.csv"), os.path.join(folder, "..", "watch", "counts.csv")):
        if not os.path.exists(counts):
            continue
        _, rows = read_csv(counts)
        handle = norm_handle(acc.get("handle"))
        for r in rows:
            if norm_handle(r.get("handle")) != handle or (r.get("network") or "") != (acc.get("network") or ""):
                continue
            if (r.get("status") or "ok") != "ok":
                continue
            try:
                t = parse_time(r.get("read_at"))
                f = parse_count(r.get("followers"), "followers")
            except ShapeError:
                continue
            if t is None or f is None:
                continue
            out.append({"at": t, "followers": f, "source": "watch", "watch": True})
    out.sort(key=lambda x: x["at"])
    # Two readings at the same moment: keep the first.
    dedup = []
    for r in out:
        if dedup and r["at"] == dedup[-1]["at"]:
            continue
        dedup.append(r)
    return dedup


def norm_handle(h):
    if h is None:
        return ""
    return str(h).strip().lstrip("@").lower()


# ---------------------------------------------------------------------------------------------- the ways in
# A run folder is one of three kinds (SKILL.md, "First: pick the way in"; words only uses any of them):
#   account  account.json + posts.csv                    one account (version 1 and 2 runs)
#   post     account.json + posts.csv + post.json        one post, beside its creator's recent posts
#   niche    niche.json + accounts/<network>-<handle>/   many creators; each creator folder is an account corpus

def run_kind(folder):
    if os.path.exists(os.path.join(folder, "niche.json")):
        return "niche"
    if os.path.exists(os.path.join(folder, "post.json")):
        return "post"
    return "account"


def load_niche(folder):
    path = os.path.join(folder, "niche.json")
    if not os.path.exists(path):
        die("no niche.json in %s (see references/data-shape.md, \"A niche run\")" % folder)
    return read_json(path)


def niche_creator_dirs(folder):
    """The creator folders of a niche run, sorted: accounts/<network>-<handle>/ that hold an account.json."""
    root = os.path.join(folder, "accounts")
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "account.json")):
            out.append("accounts/" + name)
    return out


def niche_input_files(folder):
    """Every file the niche numbers read, relative to the niche folder (for the stale-output check)."""
    files = ["niche.json", "found.csv", "formats.json"]
    for d in niche_creator_dirs(folder):
        files += [d + "/account.json", d + "/posts.csv"]
    return tuple(files)


def rel(folder, path):
    """A path relative to the run folder, with forward slashes (what the page and the files store)."""
    return os.path.relpath(path, folder).replace(os.sep, "/")


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------------------------- own video
# A post is watched as a video only when the post ITSELF carries a video by its own author (references/data-shape.md,
# "own_media"). A quoted or reposted post's video is that post's, never this one's.

def own_video(p, network):
    """True when the post's own media is a video; False when it is known not to be; None when the row does not say.
    own_media decides when the reader gave it. Without it: on YouTube, TikTok and Instagram a post of type video is
    its own video (those networks have no quotes); on X, Threads and LinkedIn the row does not say (a quote or a
    repost may show another post's video), so None: not probed, and the report says the video was not read."""
    om = (p.get("own_media") or "").strip().lower() if isinstance(p.get("own_media"), str) else p.get("own_media")
    if om:
        return om == "video"
    if (p.get("type") or "") in ("text", "thread", "article", "image", "carousel"):
        return False
    if network in VIDEO_NETWORKS or network not in TEXT_NETWORKS:
        return (p.get("type") or "") in ("video", "live")
    return None


# ---------------------------------------------------------------------------------------------- fetching over HTTP
# Every HTTP fetch of the scripts goes through here: a normal browser's User-Agent and Accept (some picture servers
# answer 403 to a script's own User-Agent or none), redirects followed (urllib does), a timeout, and an answer instead
# of an exception: the caller marks a cover "not read" with the status and goes on.

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def http_get(url, accept=None, timeout=20, max_bytes=25000000):
    """GET url like a browser. Returns (status, body, why): status is the HTTP code (None when nothing answered),
    body the bytes (None unless 2xx), why a short reason when it failed ("HTTP 403", "timed out", ...)."""
    headers = dict(BROWSER_HEADERS)
    if accept:
        headers["Accept"] = accept
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(max_bytes + 1)
            if len(body) > max_bytes:
                return r.status, None, "over %d MB" % (max_bytes // 1000000)
            return r.status, body, None
    except urllib.error.HTTPError as e:
        return e.code, None, "HTTP %d" % e.code
    except urllib.error.URLError as e:
        return None, None, "no answer (%s)" % (getattr(e, "reason", None) or e)
    except (OSError, ValueError) as e:
        return None, None, "no answer (%s)" % e


def picture_ext(body):
    """The file ending of a picture by its first bytes (.jpg, .png, .webp, .gif), or None when it is not one."""
    if body[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


def save_picture(url, dest_stem, timeout=20):
    """Fetch a picture (a cover, a profile picture) to dest_stem + its real ending. Returns (path, why): the saved
    path, or None and why it was not read ("HTTP 403", "not a picture", ...). Never raises."""
    status, body, why = http_get(url, timeout=timeout)
    if body is None:
        return None, why or "no answer"
    ext = picture_ext(body)
    if not ext or len(body) < 200:
        return None, "not a picture (HTTP %s, %d bytes)" % (status, len(body))
    path = dest_stem + ext
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return path, None


NOT_READ_COVERS = "covers/not_read.json"


def note_cover_not_read(folder, post_id, why):
    """Keep why a post's cover could not be saved (covers/not_read.json): the sheet and the report say "not read"
    with that reason, never a guess."""
    path = os.path.join(folder, NOT_READ_COVERS)
    doc = {}
    if os.path.exists(path):
        try:
            doc = read_json(path)
        except ValueError:
            doc = {}
    if why:
        doc[post_id] = why
    else:
        doc.pop(post_id, None)
    write_json(path, doc)


# ---------------------------------------------------------------------------------------------- older radar.json
# Before 0.4.1 the corner "used a lot, lifting little" was called "fading", and it also took a format that lifted but
# whose later posts did worse; an account's falling direction was "weakening". The corner is now where a format sits
# (share x lift) and nothing else, and rising / steady / fading are only the direction. An older file is read in
# today's words (it is not rewritten).

def upgrade_radar(doc):
    if not doc:
        return doc
    rules = doc.get("rules") or {}
    shared = doc.get("scope") == "shared"
    split_x = rules.get("often_creators_share" if shared else "often_share", 0.4 if shared else 0.15)
    split_y = rules.get("strong_lift", 1.0)
    names = {"scale_it": "Scale it", "underused": "Underused", "overused": "Overused", "drop": "Drop"}
    for f in doc.get("formats") or []:
        if f.get("direction_label") == "weakening":
            f["direction_label"] = "fading"
        q = f.get("quadrant")
        if q in (None, "too_few") or f.get("lift") is None:
            continue
        x = f.get("creators_share" if shared else "share")
        if x is None:
            continue
        often, strong = x >= split_x, f["lift"] >= split_y
        f["quadrant"] = ("scale_it" if often else "underused") if strong else ("overused" if often else "drop")
        f["quadrant_name"] = names[f["quadrant"]]
    return doc
