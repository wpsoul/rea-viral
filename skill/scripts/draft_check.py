#!/usr/bin/env python3
"""Check a draft post against the account's voice sheet before anyone sees it.

    python3 draft_check.py <run folder> <draft.md> [<draft.md> ...] [--json]
    python3 draft_check.py <run folder> --all [--json]          every drafts/*.md of the run
    python3 draft_check.py <folder> <draft.md> --general [--json]  the user's own draft with no reference studied:
                                                                general craft only (length, one ask that fits, no
                                                                marks of machine-written text, a covered language)

A draft is a small file (references/writing.md, "Write like it"):

    ---
    for: the user's account or niche
    network: x                  # the network the draft is for (default: the voice sheet's)
    purpose: followers          # followers, replies, saves, reach, clicks, leads or sales
    ask: follow                 # the one ask: follow, reply, save, share, click, dm or buy
    ask_in: post                # post (default) or reply: where the ask sits
    openings: [opens_number]    # the measured openings it uses (ids from writing.json)
    format: three-mistakes      # optional: the format recipe it follows
    long_posts: false           # true when the user's X account can post past 280 characters
    ---
    The post. A line that is only --- starts the next part of a thread.

    === reply ===
    Optional: the reply the user posts under it.

Checks, each pass or fail with the reason (a failed draft is rewritten, never shipped with a warning):
  front       the header names a purpose, one ask that fits it, and its openings
  length      every part and the reply fit the network's limit (X counts a link as 23 and an emoji as 2)
  first_line  the first line's length is inside the voice sheet's range
  shape       the whole length (links left out) is inside the voice sheet's range
  paragraphs  no paragraph is longer than the voice sheet allows
  openings    each opening it names was measured for this account and is really there in the first line
  ask         the named ask is found where the header says, and the post has one kind of ask at most
  avoid       nothing the account's own numbers say sinks (voice sheet rules.avoid)
  reuse       no 7 words in a row and no sentence of 5+ words taken from the reference account's posts
  machine     none of the usual marks of machine-written text, unless the account's own posts use that mark
  language    the draft is in a language the word lists cover
Exit 0 = every draft passed, 1 = one failed, 2 = the run or a draft could not be read.
"""
import glob
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, load_posts  # noqa: E402
import text_probe as tp  # noqa: E402

NGRAM = 7
MIN_SENTENCE_WORDS = 5
OWN_MARK_SHARE = 0.10     # a machine mark the account itself uses in this share of its posts (and 2+ posts) is its voice
LONG_POST_LIMIT = {"x": 25000}


def parse_draft(path):
    text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    front = {}
    body = text
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if m:
        for line in m.group(1).split("\n"):
            line = line.split("#", 1)[0].rstrip() if not line.strip().startswith("for:") else line.rstrip()
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            v = v.strip().strip('"').strip("'")
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
            elif v.lower() in ("true", "false"):
                v = v.lower() == "true"
            front[k.strip()] = v
        body = m.group(2)
    reply = None
    rm = re.search(r"^=== reply ===\s*$", body, re.M)
    if rm:
        reply = body[rm.end():].strip("\n")
        body = body[:rm.start()]
    parts = [p.strip("\n") for p in re.split(r"^---\s*$", body, flags=re.M)]
    parts = [p.strip() for p in parts if p.strip()]
    return front, parts, (reply.strip() if reply else None)


def x_length(text):
    """X's own count (twitter-text v3): a link is 23, an emoji 2, CJK and most other scripts 2, Latin 1."""
    n = 0
    t = tp.URL_RE.sub(lambda m: "\u0000" * 1, text)
    n += 23 * t.count("\u0000")
    t = t.replace("\u0000", "")
    t = tp.EMOJI_JOINERS.sub("", t)
    for ch in t:
        if tp.EMOJI_RE.match(ch):
            n += 2
            continue
        c = ord(ch)
        if c <= 0x10FF or 0x2000 <= c <= 0x200D or 0x2010 <= c <= 0x201F or 0x2032 <= c <= 0x2037:
            n += 1
        else:
            n += 2
    return n


def norm_tokens(text):
    return [w.lower().replace("’", "'") for w in tp.WORD_RE.findall(tp.URL_RE.sub(" ", text))]


def corpus(folder):
    """The reference account's own words: every caption, thread part and later reply, per post. For a niche: every
    creator's, so a draft written with the niche's hooks takes no sentence from any of them."""
    if os.path.exists(os.path.join(folder, "niche.json")):
        from common import niche_creator_dirs
        out = []
        for d in niche_creator_dirs(folder):
            out += corpus(os.path.join(folder, d))
        return out
    out = []
    for p in load_posts(folder):
        texts = list(p.get("parts") or []) or [p.get("caption") or ""]
        for r in p.get("author_replies") or []:
            texts.append(r.get("text") or "")
        out.append((p["post_id"], "\n\n".join(t for t in texts if t)))
    return out


def corpus_index(corp):
    grams = {}
    sents = {}
    for pid, text in corp:
        toks = norm_tokens(text)
        for i in range(len(toks) - NGRAM + 1):
            grams.setdefault(tuple(toks[i:i + NGRAM]), pid)
        for s in tp.SENTENCE_SPLIT.split(text):
            st = tuple(norm_tokens(s))
            if len(st) >= MIN_SENTENCE_WORDS:
                sents.setdefault(st, pid)
    return grams, sents


def own_marks(corp, words):
    """How many of the account's posts use each machine mark."""
    counts = {}
    for _, text in corp:
        for name, _ in tp.machine_marks(text, words):
            counts[name] = counts.get(name, 0) + 1
    return counts


def check_draft(path, folder, voice, words, idx, marks, n_posts, general=False):
    front, parts, reply = parse_draft(path)
    rules = (voice or {}).get("rules") or {}
    checks = []

    def add(cid, ok, msg):
        checks.append({"id": cid, "ok": ok, "message": msg})

    full = "\n\n".join(parts)
    if not parts:
        add("front", False, "the draft has no text")
        return {"draft": path, "ok": False, "checks": checks}
    net = front.get("network") or (voice or {}).get("network") or "x"
    purpose = front.get("purpose")
    ask = front.get("ask")
    ask_in = front.get("ask_in") or "post"
    openings = front.get("openings") or []
    if isinstance(openings, str):
        openings = [x.strip() for x in openings.split(",") if x.strip()]
    probs = []
    if purpose not in tp.PURPOSE_ASKS:
        probs.append("purpose must be one of %s (got %r)" % (", ".join(tp.PURPOSE_ASKS), purpose))
    if ask not in tp.ASK_KINDS:
        probs.append("ask must be one of %s (got %r)" % (", ".join(tp.ASK_KINDS), ask))
    elif purpose in tp.PURPOSE_ASKS and ask not in tp.PURPOSE_ASKS[purpose]:
        probs.append("a %s ask does not fit a post for %s (fits: %s)" % (ask, purpose, ", ".join(tp.PURPOSE_ASKS[purpose])))
    if ask_in not in ("post", "reply"):
        probs.append("ask_in is post or reply (got %r)" % ask_in)
    if ask_in == "reply" and not reply:
        probs.append("ask_in is reply but the draft has no === reply === part")
    if not openings and not general:
        probs.append("name the measured openings it uses: openings: [id, ...]")
    add("front", not probs, "; ".join(probs) or "purpose %s, ask %s in the %s, openings %s" % (purpose, ask, ask_in, ", ".join(openings)))

    f = tp.text_features(parts, None, words, [{"text": reply, "minutes_after": None}] if reply else None)
    lang = f.get("language")
    if lang not in words["languages"]:
        add("language", False, "the draft's language is not covered by the word lists (%s): its words cannot be "
                               "checked. Write it in a covered language or check it by hand" % ", ".join(words["covered"]))
    else:
        add("language", True, "%s (%s)" % (lang, f.get("language_how")))

    # length
    long_posts = bool(front.get("long_posts", rules.get("long_posts", False)))
    limit = LONG_POST_LIMIT.get(net) if long_posts and net in LONG_POST_LIMIT else tp.NETWORK_LIMITS.get(net, 2200)
    count = x_length if net == "x" else len
    over = []
    for i, p in enumerate(parts + ([reply] if reply else [])):
        n = count(p)
        if n > limit:
            over.append("%s is %d of %d" % ("the reply" if reply and i == len(parts) else "part %d" % (i + 1), n, limit))
    add("length", not over, "; ".join(over) or "every part fits %d characters on %s%s" % (
        limit, net, " (X's count)" if net == "x" else ""))

    # first line
    rng = rules.get("first_line_chars")
    fl = f.get("first_line_chars")
    if not rng:
        add("first_line", True, "not checked: the voice sheet has no first-line range (too few posts measured)")
    else:
        ok = rng[0] <= fl <= rng[1]
        add("first_line", ok, "first line %d characters; the voice sheet's range is %d to %d (%s)" % (
            fl, rng[0], rng[1], rules.get("first_line_basis") or "voice.md"))

    # shape: the whole length, links left out, inside the account's range
    cr = rules.get("chars")
    if cr:
        n = f.get("chars")
        add("shape", cr[0] <= n <= cr[1], "%d characters (links left out); the voice sheet's range is %d to %d" % (n, cr[0], cr[1]))
    else:
        add("shape", True, "not checked: the voice sheet sets no length range")

    # paragraphs
    mp = rules.get("max_paragraph_lines")
    lp = f.get("longest_paragraph_lines")
    if mp:
        add("paragraphs", lp <= mp, "longest paragraph %d lines; the voice sheet allows %d" % (lp, mp))
    else:
        add("paragraphs", True, "not checked: the voice sheet sets no paragraph limit")

    # openings
    allowed = set(rules.get("openings") or [])
    bad = []
    for o in openings:
        if o not in f:
            bad.append("%s is not an opening text_probe.py measures" % o)
        elif allowed and o not in allowed:
            bad.append("%s is not among the voice sheet's openings (%s)" % (o, ", ".join(sorted(allowed)) or "none"))
        elif f.get(o) is not True:
            bad.append("the first line does not %s" % o.replace("opens_", "open with ").replace("_", " "))
    add("openings", not bad, "; ".join(bad) or "%s, found in the first line" % ", ".join(openings))

    # the ask
    if lang in words["languages"]:
        L = words["languages"][lang]
        kinds_post = []
        for a in tp.find_asks(full, L):
            if a[2] not in kinds_post:
                kinds_post.append(a[2])
        kinds_reply = []
        for a in tp.find_asks(reply or "", L):
            if a[2] not in kinds_reply:
                kinds_reply.append(a[2])
        where = kinds_reply if ask_in == "reply" else kinds_post
        probs = []
        if ask in tp.ASK_KINDS and ask not in where:
            probs.append("no %s ask found in the %s (found: %s)" % (ask, ask_in, ", ".join(where) or "none"))
        if len(kinds_post) > 1:
            probs.append("the post asks for %d things (%s): keep one" % (len(kinds_post), ", ".join(kinds_post)))
        add("ask", not probs, "; ".join(probs) or "one %s ask, in the %s" % (ask, ask_in))
    # avoid
    hits = []
    for fid in rules.get("avoid") or []:
        if f.get(fid) is True:
            hits.append(fid)
    add("avoid", not hits, ("has %s, which sinks on this account (voice.md rules.avoid)" % ", ".join(hits)) if hits
        else "nothing the account's numbers say sinks")

    # reuse
    grams, sents = idx
    found = []
    seen_pids = set()
    for text in parts + ([reply] if reply else []):
        toks = norm_tokens(text)
        for i in range(len(toks) - NGRAM + 1):
            g = tuple(toks[i:i + NGRAM])
            if g in grams and (" ".join(g), grams[g]) not in seen_pids:
                seen_pids.add((" ".join(g), grams[g]))
                found.append('"%s" (post %s)' % (" ".join(g), grams[g]))
        for s in tp.SENTENCE_SPLIT.split(text):
            st = tuple(norm_tokens(s))
            if len(st) >= MIN_SENTENCE_WORDS and st in sents:
                found.append('the sentence "%s" (post %s)' % (" ".join(st), sents[st]))
    add("reuse", not found, ("takes the reference account's words: " + "; ".join(found[:4])) if found
        else "no %d words in a row and no sentence of %d+ words from the reference posts" % (NGRAM, MIN_SENTENCE_WORDS))

    # machine marks
    mm = tp.machine_marks("\n".join(parts + ([reply] if reply else [])), words, lang if lang in words["languages"] else "en")
    flagged, allowed_m = [], []
    for name, n in mm:
        used = marks.get(name, 0)
        if n_posts and used >= 2 and used >= OWN_MARK_SHARE * n_posts:
            allowed_m.append("%s (the account uses it in %d of %d posts)" % (name, used, n_posts))
        else:
            flagged.append("%s x%d" % (name, n))
    add("machine", not flagged, ("marks of machine-written text: %s" % ", ".join(flagged)) if flagged else
        ("none" + ("; allowed as the account's own voice: " + ", ".join(allowed_m) if allowed_m else "")))
    if general:
        for c in checks:
            if c["id"] in ("first_line", "shape", "paragraphs", "openings", "avoid", "reuse"):
                c["ok"], c["message"] = True, "not checked: no voice sheet or reference posts (general craft only)"
            elif c["id"] == "front":
                c["message"] = c["message"].replace(", openings ", "").rstrip()
    ok = all(c["ok"] for c in checks)
    return {"draft": path, "ok": ok, "checks": checks,
            "measured": {k: f.get(k) for k in ("first_line", "first_line_chars", "longest_paragraph_lines", "chars",
                                               "lines", "ask_kinds", "language")}}


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 2
    folder = argv[1]
    as_json = "--json" in argv
    if "--all" in argv:
        paths = sorted(glob.glob(os.path.join(folder, "drafts", "*.md")))
    else:
        paths = [a for a in argv[2:] if not a.startswith("--")]
    if not paths:
        die("no drafts to check (write them as %s)" % os.path.join(folder, "drafts", "<n>.md"))
    general = "--general" in argv
    voice = None if general else tp.read_voice(folder)
    if voice is None and not general:
        die("no voice sheet: run text_probe.py %s first (it writes voice.md; hooks.md for a niche), or check the "
            "user's own draft with --general (general craft only)" % folder)
    words = tp.load_words()
    corp = [] if general else corpus(folder)
    idx = corpus_index(corp)
    marks = own_marks(corp, words)
    results = []
    for p in paths:
        if not os.path.exists(p):
            die("no such draft: %s" % p)
        results.append(check_draft(p, folder, voice, words, idx, marks, len(corp), general))
    if as_json:
        print(json.dumps({"ok": all(r["ok"] for r in results), "drafts": results}, indent=2, ensure_ascii=False))
    else:
        for r in results:
            print("%s %s" % ("PASS" if r["ok"] else "FAIL", os.path.relpath(r["draft"], folder)))
            for c in r["checks"]:
                print("  %-4s %-10s %s" % ("ok" if c["ok"] else "FAIL", c["id"], c["message"]))
        print("%d of %d drafts passed%s" % (sum(1 for r in results if r["ok"]), len(results),
                                            " (general craft only: no voice sheet, nothing measured about an account)" if general else ""))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
