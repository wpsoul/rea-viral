#!/usr/bin/env python3
"""How an account writes, measured against its own results.

    python3 text_probe.py <run folder>

Reads posts.csv (the caption; for a text post the post itself; a thread's parts; the author's own later replies),
videos/*/notes.json (`seen.first_line`, the first words on screen, where the deep read wrote them down) and the word
lists in data/writing-words.json. Recomputes the numbers with analyze.py first, so they are never stale.

Writes:
- writing.json: every feature of the words (the first line, the shape, the voice, the ask, the signals the text
  pulls) with the lift of the posts that have it over the account's baseline, measured exactly as a format is
  (the median of their posts' ratios), beside the posts without it, with counts. MEASURED.
- posts_text.csv: each post's features, so any number can be checked by hand.
- voice.md: a skeleton voice sheet the first time (its `measured` block and table are rewritten on every run; the
  rest is the agent's).

Rules it keeps: a feature with fewer than 6 scored posts is "few posts" and never a finding; a word-based feature in a
language the word lists do not cover is unknown (null), never a guess; a count the network does not give is unknown,
never 0. It finds what goes with what; it does not say why. Two features that travel together on the same posts
cannot be told apart by these numbers (writing.json `overlaps` lists them).
"""
import json
import math
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    NO_LANGUAGE_TAGS, SKILL_VERSION, die, iso, median, now_utc, read_json, rnd, save_like, share_like, write_csv,
    write_json, write_text,
)
import analyze  # noqa: E402

WORDS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "writing-words.json")

SETTINGS = {
    "min_posts": 6,            # fewer scored posts with a feature: "few posts", never a finding
    "lift_ratio": 1.25,        # "lifts": its posts' median ratio is at least this, and this times the posts without it
    "sink_ratio": 0.8,         # "sinks": at most this, and at most this times the posts without it
    "short_line_chars": 50,    # a line this long or shorter counts as short
    "max_chance": 0.01,        # ... and a difference that big comes from posts sorted at random under 1 time in 100
    "false_find_rate": 0.05,   # ... and it survives the count of all features checked (Benjamini-Hochberg)
    "overlap_share": 0.7,      # two features on the same posts this often are reported as travelling together
    "reply_at_once_minutes": 10,  # the author's own reply this soon after the post was planned with it (a link, a
                                  # credit); a later one may have been added because the post was already doing well
}

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
MENTION_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{1,30}")
HASHTAG_RE = re.compile(r"(?<![\w#&])#(?!\d+\b)[^\s#.,!?;:()\"'’]+")
EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F3FA\U0001F400-\U0001F64F\U0001F680-\U0001F6FF\U0001F700-\U0001F7FF"
    "\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF☀-⛿✀-➿⭐⭕"
    "⬅-⬇⌚⌛⏩-⏺Ⓜ〰〽㊗㊙]")
EMOJI_JOINERS = re.compile("[️‍\U0001F3FB-\U0001F3FF]")
WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.U)
NUMBER_RE = re.compile(r"(?<![\w])[#$€£+~]?\d[\d,.]*(?:%|[kKmMbB]\b|x\b|\+)?")
LIST_LINE_RE = re.compile(r"^\s*(?:\d{1,2}[.)]|\(\d{1,2}\)|[-•*–—▪◦·→>]|<)\s*\S")
THREAD_NUMBER_RE = re.compile(r"^\s*\d{1,2}\s*/\s*\d{0,2}\s")
QUOTE_OPEN = "\"“”‘’'«„"
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
MONEY_RE = re.compile(r"[$€£]\s?\d|\d[\d,.]*\s?(?:%|percent\b)|\b\d+(?:\.\d+)?x\b|\b\d[\d,.]*\s?[kKmMbB]\+?(?=\W|$)")

# What each purpose of a post asks for (draft_check.py uses it too).
PURPOSE_ASKS = {
    "followers": ["follow"],
    "replies": ["reply"],
    "saves": ["save"],
    "reach": ["share", "reply"],
    "clicks": ["click"],
    "leads": ["dm", "reply", "click"],
    "sales": ["buy", "click", "dm"],
}
ASK_KINDS = ["follow", "reply", "save", "share", "click", "dm", "buy"]


# ---------------------------------------------------------------------------------------------- words

_WORDS_CACHE = {}


def load_words(path=WORDS_FILE):
    if path not in _WORDS_CACHE:
        if not os.path.exists(path):
            die("the word lists are missing: %s" % path)
        doc = read_json(path)
        langs = {}
        for code, L in (doc.get("languages") or {}).items():
            langs[code] = compile_language(L)
        _WORDS_CACHE[path] = {"version": doc.get("version"), "languages": langs, "covered": sorted(langs)}
    return _WORDS_CACHE[path]


def _norm_word(w):
    return w.lower().replace("’", "'")


def _phrase_re(phrase):
    parts = []
    for tok in phrase.split():
        if tok == "*":
            parts.append(r"[^\s]+")
        elif tok.endswith("*") and len(tok) > 1:
            parts.append(re.escape(tok[:-1]) + r"[^\s]+")
        else:
            parts.append(re.escape(_norm_word(tok)))
    return r"(?<![\w@#])" + r"\s+".join(parts) + r"(?![\w])"


def compile_language(L):
    c = {"name": L.get("name")}
    for k in ("detect", "you", "i", "we", "negation_openers", "time_units", "result_nouns", "result_modifiers",
              "imperative_verbs", "not_names", "contractions"):
        c[k] = set(_norm_word(w) for w in L.get(k) or [])
    c["how_openers"] = [_norm_word(p) for p in L.get("how_openers") or []]
    c["time_phrases_re"] = re.compile("|".join(_phrase_re(p) for p in L.get("time_phrases") or []) or r"(?!x)x")
    c["asks"] = {}
    for kind, phrases in (L.get("asks") or {}).items():
        c["asks"][kind] = [(p, re.compile(_phrase_re(p))) for p in phrases]
    mm = L.get("machine_marks") or {}
    c["machine_phrases"] = [(p, re.compile(_phrase_re(p))) for p in mm.get("phrases") or []]
    c["machine_patterns"] = [(name, re.compile(rx, re.I)) for name, rx in (mm.get("patterns") or {}).items()]
    return c


def words_of(text):
    return [_norm_word(w) for w in WORD_RE.findall(text)]


def detect_language(text, tag, words):
    """(code or None, how). The network's own tag wins when it names a language; else the 'detect' lists."""
    tag = (tag or "").strip().lower().replace("_", "-")
    if tag and tag not in NO_LANGUAGE_TAGS:
        base = tag.split("-")[0]
        return (base if base in words["languages"] else base), "network tag"
    # Hashtags and @handles carry no language: a YouTube description with 20 hashtags under two English sentences
    # read as "not told apart" before they were left out (real niche run, 2026-11-16).
    ws = words_of(MENTION_RE.sub(" ", HASHTAG_RE.sub(" ", URL_RE.sub(" ", text or ""))))
    ws = [w for w in ws if not w.isdigit()]
    if not ws:
        return None, "no words"
    best, best_hits, best_share = None, 0, 0.0
    for code, L in words["languages"].items():
        hits = sum(1 for w in ws if w in L["detect"])
        share = hits / float(len(ws))
        enough = hits >= 2 or (hits >= 1 and len(ws) < 8)
        if enough and share >= 0.2 and (hits, share) > (best_hits, best_share):
            best, best_hits, best_share = code, hits, share
    if best is None:
        by_lines = _language_by_lines(text, words)
        if by_lines:
            return by_lines, "word lists, line by line"
        return None, "not told apart by the word lists (too few of their common words)"
    return best, "word lists"


def _language_by_lines(text, words):
    """When the whole text is undecided (a YouTube description: a bare title, two sentences, twenty hashtags),
    judge each line that can be judged (6+ words, or one of the lists' common words) by the same rule, and take a
    language only when it holds 2 of every 3 judged lines (learned on a real niche run, 2026-11-16)."""
    votes, judged = {}, 0
    for line in re.split(r"\n+|(?<=[.!?])\s+", URL_RE.sub(" ", text or "")):
        ws = [w for w in words_of(MENTION_RE.sub(" ", HASHTAG_RE.sub(" ", line))) if not w.isdigit()]
        if not ws:
            continue
        hit_any = any(w in L["detect"] for L in words["languages"].values() for w in ws)
        if len(ws) < 6 and not hit_any:
            continue
        judged += 1
        for code, L in words["languages"].items():
            hits = sum(1 for w in ws if w in L["detect"])
            if (hits >= 2 or (hits >= 1 and len(ws) < 8)) and hits / float(len(ws)) >= 0.2:
                votes[code] = votes.get(code, 0) + 1
                break
    if not judged:
        return None
    code, n = max(votes.items(), key=lambda kv: kv[1]) if votes else (None, 0)
    return code if code and n * 3 >= judged * 2 else None


# ---------------------------------------------------------------------------------------------- one text

def clean_line(s):
    return URL_RE.sub("", s).strip()


def strip_lead(s):
    """The line without leading emoji, spaces and decorative marks (what the first word is read from)."""
    s = EMOJI_JOINERS.sub("", s)
    i = 0
    while i < len(s) and (EMOJI_RE.match(s[i]) or s[i] in " \t*_~|→>-•·"):
        i += 1
    return s[i:]


def emoji_count(text):
    return len(EMOJI_RE.findall(EMOJI_JOINERS.sub("", text)))


def paragraphs_of(text):
    paras = []
    cur = []
    for line in text.split("\n"):
        if line.strip():
            cur.append(line)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return paras


def find_asks(text, L, offset=0):
    """Every ask phrase found: [(start, end, kind, phrase)], a match inside a longer one of another kind dropped."""
    low = _norm_word(text)
    found = []
    for kind, plist in L["asks"].items():
        for phrase, rx in plist:
            for m in rx.finditer(low):
                found.append((m.start() + offset, m.end() + offset, kind, phrase))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    keep = []
    for f in found:
        if any(k[0] <= f[0] and f[1] <= k[1] and (k[1] - k[0]) > (f[1] - f[0]) for k in keep):
            continue
        if any(k[0] == f[0] and k[1] == f[1] for k in keep):
            continue
        keep.append(f)
    return keep


def opening_kinds(first, lang_code, words):
    """Each opening as True / False / None (None = the language is not covered, so a word-based test cannot say no)."""
    L = words["languages"].get(lang_code) if lang_code else None
    covered = L is not None
    lead = strip_lead(first)
    toks = lead.split()
    first_tok = toks[0] if toks else ""
    wl = words_of(lead)
    w0 = wl[0] if wl else ""

    def word_based(hit):
        if hit:
            return True
        return False if covered else None

    out = {}
    out["opens_number"] = bool(re.match(r"^[#$€£+~]?\d", first_tok))
    m = re.match(r"[^.!?]*[.!?]", first)
    out["opens_question"] = bool(m and m.group(0).endswith("?")) or (not m and first.rstrip().endswith("?"))
    out["opens_quote"] = bool(lead) and lead[0] in QUOTE_OPEN and not re.match(r"^['’]\d", lead)
    out["opens_you"] = word_based(covered and w0 in L["you"])
    out["opens_i"] = word_based(covered and w0 in L["i"])
    name = False
    if first_tok.startswith("@"):
        name = True
    elif covered and len(toks) >= 1:
        t0 = re.sub(r"[^\w'’&.-]", "", toks[0])
        t1 = re.sub(r"[^\w'’&.-]", "", toks[1]) if len(toks) > 1 else ""

        contr = set(L.get("contractions") or [])

        def cap(t):
            # A capitalised word that is not a sentence opener, a contraction ("Let's", "It's", "I'm": 0.4.1, they
            # were read as a name's possessive), a common word or a command.
            n = _norm_word(t)
            return len(t) > 1 and t[0].isupper() and not t.isupper() and n not in contr \
                and re.sub(r"'s$", "", n) not in L["not_names"] and n not in L["detect"] and n not in L["imperative_verbs"]
        # A line in Title Case (most words capitalised, as YouTube titles are: "Adorable Circular Creatures") says
        # nothing about names; only a possessive or an @handle does there (real niche run, 2026-11-16).
        alpha = [t for t in toks if re.match(r"[^\W\d_]", t)]
        title_case = len(alpha) >= 3 and sum(1 for t in alpha if t[0].isupper()) >= 0.75 * len(alpha)
        if cap(t0) and re.search(r"['’]s$", t0):
            name = True
        elif cap(t0) and cap(t1) and not title_case:
            name = True
    out["opens_name"] = True if name else (False if covered else None)
    out["opens_negation"] = word_based(covered and w0 in L["negation_openers"])
    low = _norm_word(lead)
    how = False
    if covered:
        how = (w0 == "how") or any(low.startswith(p + " ") for p in L["how_openers"] if " " in p)
    out["opens_how"] = word_based(how)
    ts = False
    if covered:
        ws = words_of(first)
        for i, w in enumerate(ws[:-1]):
            if re.fullmatch(r"\d[\d,.]*\+?", w) and ws[i + 1] in L["time_units"]:
                ts = True
        if re.search(r"\b\d+\s?(?:d|wk|mo|yr)s?\b", _norm_word(first)):
            ts = True
        if L["time_phrases_re"].search(_norm_word(first)):
            ts = True
    out["opens_time_span"] = word_based(ts)
    res = bool(MONEY_RE.search(first))
    if not res and covered:
        ws = words_of(first)
        for i, w in enumerate(ws):
            if not re.fullmatch(r"\d[\d,.]*[km]?\+?", w):
                continue
            nxt = ws[i + 1:i + 3]
            if nxt and (nxt[0] in L["result_nouns"] or
                        (len(nxt) > 1 and nxt[0] in L["result_modifiers"] and nxt[1] in L["result_nouns"])):
                res = True
    out["opens_result_number"] = True if res else (False if covered else None)
    out["opens_imperative"] = word_based(covered and w0 in L["imperative_verbs"])
    return out


OPENING_KEEP = ("first_line", "language", "language_covered", "lang", "empty")


def first_part_only(p):
    """A thread whose reader gave only its first part (no parts, or one): 0.4.1 says so on the post."""
    return (p.get("type") or "") == "thread" and len(p.get("parts") or []) < 2


def mark_first_part_only(p, f):
    """On a thread read as its first part only, keep what that part says (its opening) and make every whole-post
    feature (length, lines, lists, voice counts, the ask) unknown: one part cannot say them."""
    if not first_part_only(p):
        return f
    for k in list(f.keys()):
        if k.startswith("opens_") or k.startswith("first_line") or k in OPENING_KEEP:
            continue
        f[k] = None
    f["first_part_only"] = True
    return f


def text_features(parts, lang_tag, words, author_replies=None, short_chars=SETTINGS["short_line_chars"]):
    """The features of one post's words. `parts`: the caption, or a thread's parts. Unknown = None."""
    parts = [p for p in (parts or []) if p is not None]
    full = "\n\n".join(parts)
    lang, how = detect_language(full, lang_tag, words)
    L = words["languages"].get(lang) if lang else None
    covered = L is not None
    f = {"language": lang, "language_how": how, "language_covered": covered}
    if not full.strip():
        f["empty"] = True
        return f
    f["empty"] = False
    first = ""
    for line in parts[0].split("\n") if parts else []:
        if clean_line(line):
            first = clean_line(line)
            break
    f["first_line"] = first
    f["first_line_chars"] = len(first)
    f["first_line_words"] = len(WORD_RE.findall(first))
    f.update(opening_kinds(first, lang, words))
    body = URL_RE.sub(" ", full)
    lines = [clean_line(x) for x in full.split("\n")]
    lines = [x for x in lines if x]
    ws = WORD_RE.findall(body)
    nwords = len(ws)
    f["chars"] = len(re.sub(r"[ \t]+", " ", body).strip())
    f["words"] = nwords
    f["lines"] = len(lines)
    paras = []
    for p in parts:
        paras.extend(paragraphs_of(p))
    f["paragraphs"] = len(paras)
    f["longest_paragraph_lines"] = max([len([x for x in pp if clean_line(x)]) for pp in paras] or [0])
    sents = [s for s in SENTENCE_SPLIT.split(body) if WORD_RE.search(s)]
    f["sentences"] = len(sents)
    f["avg_sentence_words"] = rnd(nwords / float(len(sents)), 2) if sents else None
    f["short_lines_share"] = rnd(sum(1 for x in lines if len(x) <= short_chars) / float(len(lines)), 3) if lines else None
    list_lines = [x for p in parts for x in p.split("\n") if LIST_LINE_RE.match(x) and not THREAD_NUMBER_RE.match(x)]
    emoji_led = [x for p in parts for x in p.split("\n") if x.strip() and EMOJI_RE.match(EMOJI_JOINERS.sub("", x.strip())[:1] or " ")
                 and len(x.strip()) > 3]
    f["has_list"] = len(list_lines) >= 2 or len(emoji_led) >= 3
    f["has_line_breaks"] = "\n" in full.strip()
    f["parts"] = len(parts) if len(parts) > 1 else None
    # voice
    if covered:
        lw = [_norm_word(w) for w in ws]
        yu = sum(1 for w in lw if w in L["you"])
        me = sum(1 for w in lw if w in L["i"]) + sum(1 for w in lw if w in L["we"])
        f["you_words"], f["i_we_words"] = yu, me
        f["voice_you"] = yu > me
        f["voice_i"] = me > yu
        imp = 0
        for s in sents:
            sw = words_of(strip_lead(s))
            if sw and sw[0] in L["imperative_verbs"]:
                imp += 1
        f["imperatives"] = imp
        f["has_imperative"] = imp > 0
    else:
        for k in ("you_words", "i_we_words", "voice_you", "voice_i", "imperatives", "has_imperative"):
            f[k] = None
    f["questions"] = len(re.findall(r"\?+", body))
    f["has_question"] = f["questions"] > 0
    nums = NUMBER_RE.findall(body)
    f["numbers"] = len(nums)
    f["has_number"] = len(nums) > 0
    f["numbers_per_100_words"] = rnd(100.0 * len(nums) / nwords, 2) if nwords else None
    f["emoji"] = emoji_count(full)
    f["has_emoji"] = f["emoji"] > 0
    f["hashtags"] = len(HASHTAG_RE.findall(full))
    f["has_hashtag"] = f["hashtags"] > 0
    f["links"] = len(URL_RE.findall(full))
    f["has_link"] = f["links"] > 0
    f["mentions"] = len(MENTION_RE.findall(URL_RE.sub(" ", full)))
    f["has_mention"] = f["mentions"] > 0
    # the ask
    if covered:
        asks = find_asks(full, L)
        kinds = []
        for a in asks:
            if a[2] not in kinds:
                kinds.append(a[2])
        f["ask_kinds"] = kinds
        f["has_ask"] = bool(asks)
        f["ask_phrases"] = [full[a[0]:a[1]] for a in asks][:6]
        if asks:
            pos = asks[0][0] / float(max(1, len(full)))
            f["ask_where"] = "first_third" if pos < 1 / 3.0 else ("middle" if pos < 2 / 3.0 else "end")
            if len(parts) > 1:
                bounds, acc = [], 0
                for p in parts:
                    bounds.append(acc)
                    acc += len(p) + 2
                part_of = max(i for i, b in enumerate(bounds) if b <= asks[0][0])
                f["ask_part"] = part_of + 1
        else:
            f["ask_where"] = None
        for k in ASK_KINDS:
            f["ask_" + k] = k in kinds
        f["ask_at_end"] = f["ask_where"] == "end"
        later = []
        for r in later_replies(author_replies):
            for a in find_asks(r.get("text") or "", L):
                if a[2] not in later:
                    later.append(a[2])
        f["later_reply_ask_kinds"] = later
        f["ask_in_later_reply"] = bool(later) if author_replies is not None else None
    else:
        for k in ["ask_kinds", "has_ask", "ask_phrases", "ask_where", "ask_at_end", "later_reply_ask_kinds",
                  "ask_in_later_reply"] + ["ask_" + k for k in ASK_KINDS]:
            f[k] = None
    f["has_later_reply"] = bool(later_replies(author_replies)) if author_replies is not None else None
    f["link_in_own_reply"] = (any(URL_RE.search(r.get("text") or "") for r in author_replies
                                  if r.get("minutes_after") is not None and r["minutes_after"] <= SETTINGS["reply_at_once_minutes"])
                              if author_replies is not None else None)
    return f


def later_replies(author_replies):
    """The author's replies posted more than reply_at_once_minutes after the post (or at an unknown time)."""
    return [r for r in author_replies or [] if r.get("minutes_after") is None or r["minutes_after"] > SETTINGS["reply_at_once_minutes"]]


def machine_marks(text, words, lang="en"):
    """The usual marks of machine-written text found in `text`: [(name, count)]."""
    L = words["languages"].get(lang)
    if L is None:
        return []
    low = _norm_word(text)
    out = []
    for p, rx in L["machine_phrases"]:
        n = len(rx.findall(low))
        if n:
            out.append((p, n))
    for name, rx in L["machine_patterns"]:
        n = len(rx.findall(text))
        if n:
            out.append((name, n))
    return out


# ---------------------------------------------------------------------------------------------- the account

BOOL_FEATURES = [
    # id, group, label, needs the word lists
    ("opens_number", "opening", "Opens with a number", False),
    ("opens_result_number", "opening", "Opens with a result in numbers ($, %, 10x, 10k followers)", "partly"),
    ("opens_time_span", "opening", "Opens with a time span (in 30 days, last year)", True),
    ("opens_question", "opening", "Opens with a question", False),
    ("opens_how", "opening", "Opens with \"how\" (how to, how I, how it works)", True),
    ("opens_you", "opening", "Opens with \"you\"", True),
    ("opens_i", "opening", "Opens with \"I\" or \"my\"", True),
    ("opens_name", "opening", "Opens with a name or @handle", "partly"),
    ("opens_quote", "opening", "Opens with a quote mark", False),
    ("opens_negation", "opening", "Opens with a negation (stop, don't, never, no)", True),
    ("opens_imperative", "opening", "Opens with a command (write, build, stop ...)", True),
    ("has_list", "shape", "Has a list (numbered or bulleted)", False),
    ("quotes_own_post", "shape", "Quotes one of the account's own earlier posts", False),
    ("has_line_breaks", "shape", "Has line breaks", False),
    ("voice_you", "voice", "Says \"you\" more than \"I/we\"", True),
    ("voice_i", "voice", "Says \"I/we\" more than \"you\"", True),
    ("has_question", "voice", "Asks a question anywhere", False),
    ("has_imperative", "voice", "Has a command anywhere", True),
    ("has_number", "voice", "Has a number anywhere", False),
    ("has_emoji", "voice", "Has emoji", False),
    ("has_hashtag", "voice", "Has hashtags", False),
    ("has_link", "voice", "Has a link", False),
    ("has_mention", "voice", "Mentions an @account", False),
    ("has_ask", "ask", "Asks for something (any ask)", True),
    ("ask_follow", "ask", "Asks to follow", True),
    ("ask_reply", "ask", "Asks for a reply or comment", True),
    ("ask_save", "ask", "Asks to save or bookmark", True),
    ("ask_share", "ask", "Asks to share or repost", True),
    ("ask_click", "ask", "Asks to click a link", True),
    ("ask_dm", "ask", "Asks for a DM", True),
    ("ask_buy", "ask", "Asks to buy or sign up", True),
    ("ask_at_end", "ask", "Puts its ask at the end", True),
    ("link_in_own_reply", "voice", "Its link sits in the author's own reply, posted at once", False),
    ("has_later_reply", "ask", "The author replied under it later (10+ minutes after)", False),
    ("ask_in_later_reply", "ask", "An ask in the author's later reply", True),
]
NUM_FEATURES = [
    ("first_line_chars", "opening", "First line, characters"),
    ("first_line_words", "opening", "First line, words"),
    ("chars", "shape", "Length, characters (links left out)"),
    ("lines", "shape", "Lines"),
    ("paragraphs", "shape", "Paragraphs"),
    ("longest_paragraph_lines", "shape", "Longest paragraph, lines"),
    ("avg_sentence_words", "shape", "Words per sentence"),
    ("short_lines_share", "shape", "Share of short lines (50 characters or fewer)"),
    ("numbers_per_100_words", "voice", "Numbers per 100 words"),
    ("parts", "shape", "Thread parts"),
]
SIGNALS = [
    # key, label, numerator getter
    ("save", "saves per like", lambda p: save_like(p)),
    ("reply", "replies per like", lambda p: p.get("comments")),
    ("share", "shares per like", lambda p: share_like(p)),
    ("quote", "quotes per like", lambda p: p.get("quotes")),
]


def per_like(p, getter):
    lk = p.get("likes")
    x = getter(p)
    if lk is None or lk <= 0 or x is None:
        return None
    return x / float(lk)


def signal_names(posts):
    """What the network calls each signal, from which column carries it ('bookmarks per like' on X)."""
    names = {}
    has = lambda col: any(p.get(col) is not None for p in posts)  # noqa: E731
    names["save"] = "saves per like" if has("saves") else ("bookmarks per like" if has("bookmarks") else "saves per like")
    names["share"] = "shares per like" if has("shares") else ("reposts per like" if has("reposts") else "shares per like")
    names["reply"] = "replies per like" if not has("shares") and has("reposts") else "comments per like"
    names["quote"] = "quotes per like"
    return names


def group_stats(ps, hit_ratio, flop_ratio):
    rs = [p["ratio"] for p in ps]
    return {"posts": len(ps), "lift": rnd(median(rs), 3) if rs else None,
            "hit_rate": rnd(sum(1 for r in rs if r >= hit_ratio) / float(len(rs)), 3) if rs else None,
            "flops": sum(1 for r in rs if r <= flop_ratio)}


def signal_stats(ps):
    out = {}
    for key, _, getter in SIGNALS:
        vals = [per_like(p, getter) for p in ps]
        vals = [v for v in vals if v is not None]
        out[key] = {"median": rnd(median(vals), 3) if vals else None, "posts_known": len(vals)}
    return out


def chance(a, b):
    """How often posts sorted at random would differ this much: the two-sided p of a Mann-Whitney rank test (normal
    approximation, ties averaged). None when a side is empty."""
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


def verdict(w, wo, s, rw, rwo, usual):
    """lifts / sinks only when all three hold: its posts' median ratio is 1.25x the account's usual post (the median
    ratio of all scored posts) or more (0.8x or less), 1.25x the posts without it or more (0.8x or less), and a
    difference this large comes from posts sorted at random less than 1 time in 100 (`chance`)."""
    if w["posts"] + wo["posts"] == 0:
        return "unknown", None
    if w["posts"] == 0:
        return "never", None
    if wo["posts"] == 0:
        return "always", None
    if w["posts"] < s["min_posts"]:
        return "few posts", None
    if wo["posts"] < s["min_posts"]:
        return "nearly always", None
    a, b = w["lift"], wo["lift"]
    if a is None or b is None or not usual:
        return "unknown", None
    p = chance(rw, rwo)
    rel = a / b if b else None
    sure = p is not None and p < s["max_chance"]
    if a >= s["lift_ratio"] * usual and rel is not None and rel >= s["lift_ratio"] and sure:
        return "lifts", p
    if a <= s["sink_ratio"] * usual and rel is not None and rel <= s["sink_ratio"] and sure:
        return "sinks", p
    return "no clear difference", p


def tertiles(items):
    """Split [(value, post)] into three groups by value, keeping equal values together."""
    items = sorted(items, key=lambda x: x[0])
    n = len(items)
    cuts = [n // 3, (2 * n) // 3]
    groups, start = [], 0
    for c in cuts + [n]:
        end = max(c, start)
        while 0 < end < n and items[end][0] == items[end - 1][0]:
            end += 1
        if end > start:
            groups.append(items[start:end])
        start = end
    return groups


def measure(scored, inwin, feats, s, hit_ratio, flop_ratio, names):
    usual = median([p["ratio"] for p in scored]) if scored else None
    out_bool = []
    for fid, group, label, words_dep in BOOL_FEATURES:
        w = [p for p in scored if feats[p["post_id"]].get(fid) is True]
        wo = [p for p in scored if feats[p["post_id"]].get(fid) is False]
        unk = [p for p in scored if feats[p["post_id"]].get(fid) is None]
        gw, gwo = group_stats(w, hit_ratio, flop_ratio), group_stats(wo, hit_ratio, flop_ratio)
        usage_known = [p for p in inwin if feats[p["post_id"]].get(fid) is not None]
        used = sum(1 for p in usage_known if feats[p["post_id"]].get(fid) is True)
        v, pch = verdict(gw, gwo, s, [p["ratio"] for p in w], [p["ratio"] for p in wo], usual)
        rec = {
            "id": fid, "group": group, "label": label, "kind": "flag",
            "needs_words": words_dep, "evidence": "MEASURED",
            "with": gw, "without": gwo, "unknown": len(unk),
            "vs_without": rnd(gw["lift"] / gwo["lift"], 3) if gw["lift"] and gwo["lift"] else None,
            "vs_usual": rnd(gw["lift"] / usual, 3) if gw["lift"] and usual else None,
            "chance": rnd(pch, 4) if pch is not None else None,
            "verdict": v, "claim_ok": v in ("lifts", "sinks"),
            "usage": {"posts": len(inwin), "known": len(usage_known), "with": used,
                      "share": rnd(used / float(len(usage_known)), 3) if usage_known else None},
            "signals": {"with": signal_stats(w), "without": signal_stats(wo)},
            "best": [p["post_id"] for p in sorted(w, key=lambda p: -p["ratio"])[:3]],
            "worst": [p["post_id"] for p in sorted(w, key=lambda p: p["ratio"])[:3]],
        }
        if v == "unknown" and len(unk) and not (gw["posts"] + gwo["posts"]):
            rec["unknown_why"] = "the word lists do not cover these posts' language"
        out_bool.append(rec)
    out_num = []
    for fid, group, label in NUM_FEATURES:
        items = [(feats[p["post_id"]].get(fid), p) for p in scored if feats[p["post_id"]].get(fid) is not None]
        all_vals = sorted(feats[p["post_id"]].get(fid) for p in inwin if feats[p["post_id"]].get(fid) is not None)
        rec = {"id": fid, "group": group, "label": label, "kind": "number", "evidence": "MEASURED",
               "scored_known": len(items), "usage": quantiles(all_vals), "groups": [], "verdict": None,
               "winning_range": None, "claim_ok": False}
        hits = [v for v, p in items if p["ratio"] >= hit_ratio]
        flops = [v for v, p in items if p["ratio"] <= flop_ratio]
        rec["hits_median"] = rnd(median(hits), 2) if hits else None
        rec["flops_median"] = rnd(median(flops), 2) if flops else None
        if len(items) < 3 * s["min_posts"] or len(set(v for v, _ in items)) < 3:
            rec["verdict"] = "few posts" if items else "unknown"
            out_num.append(rec)
            continue
        groups = tertiles(items)
        for gi, g in enumerate(groups):
            st = group_stats([p for _, p in g], hit_ratio, flop_ratio)
            st["range"] = [rnd(g[0][0], 2), rnd(g[-1][0], 2)]
            st["name"] = ("low", "middle", "high")[gi] if len(groups) == 3 else ("low", "high")[min(gi, 1)]
            st["signals"] = signal_stats([p for _, p in g])
            rec["groups"].append(st)
        ok = [g for g in rec["groups"] if g["posts"] >= s["min_posts"] and g["lift"] is not None]
        if len(ok) >= 2:
            best = max(ok, key=lambda g: g["lift"])
            worst = min(ok, key=lambda g: g["lift"])
            rel = best["lift"] / worst["lift"] if worst["lift"] else None
            bi_ = rec["groups"].index(best)
            in_best = [p["ratio"] for gi, g in enumerate(groups) for _, p in g if gi == bi_]
            rest = [p["ratio"] for gi, g in enumerate(groups) for _, p in g if gi != bi_]
            pch = chance(in_best, rest)
            if pch is not None:
                pch = min(1.0, pch * len(ok))   # the best of the groups was picked: its chance counts that many tries
            rec["chance"] = rnd(pch, 4) if pch is not None else None
            if rel is not None and rel >= s["lift_ratio"] and usual and best["lift"] >= s["lift_ratio"] * usual \
                    and pch is not None and pch < s["max_chance"]:
                # Next-door groups that do as well (within the same 1.25 margin) and also beat the weakest join it.
                gs = rec["groups"]
                bi = gs.index(best)
                lo_i = hi_i = bi

                def joins(g):
                    return (g["posts"] >= s["min_posts"] and g["lift"] is not None and g is not worst
                            and g["lift"] * s["lift_ratio"] >= best["lift"] and g["lift"] >= worst["lift"] * s["lift_ratio"])
                while lo_i - 1 >= 0 and joins(gs[lo_i - 1]):
                    lo_i -= 1
                while hi_i + 1 < len(gs) and joins(gs[hi_i + 1]):
                    hi_i += 1
                names_in = [g["name"] for g in gs[lo_i:hi_i + 1]]
                rec["verdict"] = "%s lift%s" % (" and ".join(names_in), "" if len(names_in) > 1 else "s")
                rec["winning_range"] = {"range": [gs[lo_i]["range"][0], gs[hi_i]["range"][1]], "lift": best["lift"],
                                        "posts": sum(g["posts"] for g in gs[lo_i:hi_i + 1]),
                                        "vs_lowest_group": rnd(rel, 3), "groups": names_in,
                                        "weakest": {"range": worst["range"], "lift": worst["lift"], "posts": worst["posts"]}}
                rec["claim_ok"] = True
            else:
                rec["verdict"] = "no clear difference"
        else:
            rec["verdict"] = "few posts"
        out_num.append(rec)
    false_finds(out_bool, out_num, s)
    return out_bool, out_num


def false_finds(bools, nums, s):
    """Many features are checked at once, so a few would pass the 1-in-100 test by luck alone. Keep a lift or sink
    only while it also passes the Benjamini-Hochberg rule across every feature that was tested (at most 1 in 20 of
    the kept findings may be luck); the others become "no clear difference" with a note."""
    tested = [r for r in bools + nums if r.get("chance") is not None]
    m = len(tested)
    if not m:
        return
    ranked = sorted(tested, key=lambda r: r["chance"])
    cut = 0.0
    for i, r in enumerate(ranked, 1):
        if r["chance"] <= s["false_find_rate"] * i / m:
            cut = r["chance"]
    for r in tested:
        strong = r.get("claim_ok")
        if strong and r["chance"] > cut:
            r["claim_ok"] = False
            r["verdict_before_count"] = r["verdict"]
            r["verdict"] = "no clear difference"
            r["note"] = "passed on its own, but not once all %d features checked are counted: likely luck" % m
            if r.get("kind") == "number":
                r["winning_range"] = None
    s["features_tested"] = m


def quantiles(vals):
    if not vals:
        return {"posts": 0, "median": None, "p10": None, "p25": None, "p75": None, "p90": None, "min": None, "max": None}
    v = sorted(vals)

    def q(x):
        i = (len(v) - 1) * x
        lo, hi = int(i), min(int(i) + 1, len(v) - 1)
        return v[lo] + (v[hi] - v[lo]) * (i - lo)
    return {"posts": len(v), "median": rnd(float(median(v)), 2), "p10": rnd(q(0.1), 2), "p25": rnd(q(0.25), 2),
            "p75": rnd(q(0.75), 2), "p90": rnd(q(0.9), 2), "min": rnd(float(v[0]), 2), "max": rnd(float(v[-1]), 2)}


def overlaps(bools, scored, feats, s):
    strong = [b for b in bools if b["verdict"] in ("lifts", "sinks")]
    out = []
    for a in strong:
        A = set(p["post_id"] for p in scored if feats[p["post_id"]].get(a["id"]) is True)
        for b in strong:
            if a["id"] >= b["id"]:
                continue
            B = set(p["post_id"] for p in scored if feats[p["post_id"]].get(b["id"]) is True)
            if not A or not B:
                continue
            both = len(A & B)
            share = both / float(min(len(A), len(B)))
            if share >= s["overlap_share"]:
                out.append({"a": a["id"], "b": b["id"], "posts_both": both, "share_of_smaller": rnd(share, 3),
                            "note": "these travel together on the same posts: the numbers cannot tell them apart"})
    return out


def on_screen_lines(folder, scored_by_id, words):
    """The first line on screen of watched videos (notes.json seen.first_line), with their openings."""
    vdir = os.path.join(folder, "videos")
    out = []
    if not os.path.isdir(vdir):
        return out
    for pid in sorted(os.listdir(vdir)):
        p = os.path.join(vdir, pid, "notes.json")
        if not os.path.exists(p):
            continue
        try:
            n = read_json(p)
        except ValueError:
            continue
        line = ((n.get("seen") or {}).get("first_line") or "").strip()
        if n.get("read") is not True or not line or line.lower() == "none":
            continue
        post = scored_by_id.get(pid) or {}
        lang, _ = detect_language(line, post.get("lang"), words)
        kinds = opening_kinds(line, lang, words)
        out.append({"post_id": pid, "first_line": line, "chars": len(line), "ratio": rnd(post.get("ratio"), 3),
                    "openings": [k for k, v in kinds.items() if v is True], "evidence": "SEEN"})
    out.sort(key=lambda x: -(x["ratio"] or 0))
    return out


def run(folder):
    from common import run_kind
    if run_kind(folder) == "niche":
        return run_niche(folder)
    words = load_words()
    an = analyze.run(folder)
    analyze.write_outputs(folder, an)
    from common import load_posts
    raw = dict((p["post_id"], p) for p in load_posts(folder))
    rows = an["posts"]
    feats = {}
    for r in rows:
        p = raw.get(r["post_id"]) or {}
        parts = p.get("parts") or [p.get("caption") or ""]
        feats[r["post_id"]] = mark_first_part_only(p, text_features(parts, p.get("lang"), words, p.get("author_replies")))
        q = (p.get("quoted_url") or "").lower()
        feats[r["post_id"]]["quotes_own_post"] = (("/%s/" % (an["account"]["handle"] or "").lower()) in q) if q else (
            False if r["type"] != "quote" else None)
        r["lang"] = p.get("lang")
        r["quoted_url"] = p.get("quoted_url")
    s = dict(SETTINGS)
    o = an["settings"]
    hit_ratio, flop_ratio = o["hit_ratio"], o["flop_ratio"]
    scored = [r for r in rows if r["status"] in ("scored", "fresh") and r["ratio"] is not None and not feats[r["post_id"]].get("empty")]
    settled_scored = [r for r in scored if r["status"] == "scored"]
    inwin = [r for r in rows if r["in_window"] and not feats[r["post_id"]].get("empty")]
    names = signal_names(rows)
    langs = {}
    hows = {}
    for r in inwin:
        f = feats[r["post_id"]]
        langs[f["language"] or "unknown"] = langs.get(f["language"] or "unknown", 0) + 1
        hows[f["language_how"]] = hows.get(f["language_how"], 0) + 1
    covered = load_words()["covered"]
    n_cov = sum(v for k, v in langs.items() if k in covered)
    out = {
        "schema": "rea-viral/writing@1",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": analyze.input_fingerprint(folder, analyze.INPUT_FILES + tuple(notes_files(folder))),
        "words": {"file": "data/writing-words.json", "version": words["version"], "covered": covered},
        "settings": s,
        "metric": an["metric"],
        "subject": {"network": an["account"]["network"], "handle": an["account"]["handle"]},
        "window": an["window"],
        "analysis_status": an["status"],
        "language": {
            "covered": covered, "posts_by_language": langs, "how": hows,
            "posts_covered": n_cov, "posts_in_window": len(inwin),
            "note": ("The word lists cover %s. Word-based features of posts in other languages are unknown (null), "
                     "never guessed; lengths, lines, numbers, questions, emoji, hashtags, links and mentions are "
                     "measured in every language." % ", ".join("%s (%s)" % (words["languages"][c]["name"] or c, c) for c in covered)),
        },
        "signal_names": names,
        "counts": {"posts": len(rows), "in_window_with_text": len(inwin), "scored_with_text": len(scored),
                   "empty_text": sum(1 for r in rows if feats[r["post_id"]].get("empty"))},
    }
    if not inwin:
        out["status"] = "no_text" if rows else an["status"]
        out["status_note"] = "No post in the window has words to read." if rows else an.get("status_note")
        out.update({"features": [], "numbers": [], "overlaps": [], "first_lines": {"best": [], "worst": []},
                    "asks": {}, "account_signals": {}, "on_screen": []})
        return out, rows, feats
    if an["status"] != "ok" or len(scored) < 2 * s["min_posts"]:
        out["status"] = "too_few_posts"
        out["status_note"] = ("%d scored posts with words; a feature needs %d posts with it and %d without, so only "
                              "how often each is used is reported, never a lift." % (len(scored), s["min_posts"], s["min_posts"]))
        scored_for_lift = []
    else:
        out["status"] = "ok"
        out["status_note"] = None
        scored_for_lift = scored
    bools, nums = measure(scored_for_lift, inwin, feats, s, hit_ratio, flop_ratio, names)
    out["features"] = bools
    out["numbers"] = nums
    out["overlaps"] = overlaps(bools, scored_for_lift, feats, s)
    out["account_signals"] = signal_stats(scored or inwin)

    def fl(r):
        f = feats[r["post_id"]]
        return {"post_id": r["post_id"], "url": r["url"], "ratio": rnd(r["ratio"], 3), "views": r["views"],
                "first_line": f.get("first_line"), "chars": f.get("first_line_chars"), "type": r["type"],
                "openings": [k for k, v in f.items() if k.startswith("opens_") and v is True],
                "first_part_only": bool(f.get("first_part_only")),
                "fresh": bool(r.get("fresh") or r.get("status") == "fresh")}
    by = sorted(scored, key=lambda r: -r["ratio"])
    out["first_lines"] = {"best": [fl(r) for r in by[:8]], "worst": [fl(r) for r in sorted(settled_scored, key=lambda r: r["ratio"])[:8]],
                          "evidence": "SEEN"}
    with_ask = [r for r in inwin if feats[r["post_id"]].get("has_ask") is True]
    known = [r for r in inwin if feats[r["post_id"]].get("has_ask") is not None]
    kinds = dict((k, sum(1 for r in with_ask if k in (feats[r["post_id"]].get("ask_kinds") or []))) for k in ASK_KINDS)
    where = {}
    for r in with_ask:
        w = feats[r["post_id"]].get("ask_where")
        where[w] = where.get(w, 0) + 1
    later = [r for r in inwin if feats[r["post_id"]].get("has_later_reply") is True]
    out["asks"] = {
        "posts_known": len(known), "posts_with_ask": len(with_ask),
        "share": rnd(len(with_ask) / float(len(known)), 3) if known else None,
        "kinds": kinds, "where": where,
        "later_replies": {"posts": len(later),
                          "with_ask": sum(1 for r in later if feats[r["post_id"]].get("ask_in_later_reply") is True),
                          "note": "The author's own replies posted after the post. One added because the post was "
                                  "already doing well cannot be why it did: never read its lift as a cause."},
        "examples": [{"post_id": r["post_id"], "phrases": feats[r["post_id"]].get("ask_phrases"),
                      "kinds": feats[r["post_id"]].get("ask_kinds"), "ratio": rnd(r["ratio"], 3)}
                     for r in sorted(with_ask, key=lambda r: -(r["ratio"] or 0))[:8]],
    }
    scored_by_id = dict((r["post_id"], r) for r in rows)
    out["on_screen"] = on_screen_lines(folder, scored_by_id, words)
    return out, rows, feats


def notes_files(folder):
    vdir = os.path.join(folder, "videos")
    if not os.path.isdir(vdir):
        return []
    return ["videos/%s/notes.json" % d for d in sorted(os.listdir(vdir)) if os.path.exists(os.path.join(vdir, d, "notes.json"))]


# ---------------------------------------------------------------------------------------------- across a niche
# The same measures, with each post's ratio against ITS OWN creator's usual (trends.py). One more rule: a feature
# lifts or sinks for the niche only when the posts with it come from at least 3 creators (NICHE_MIN_CREATORS); a
# habit of one or two creators is shown as "few creators", never a finding of the niche.

NICHE_MIN_CREATORS = 3


def _creator_rule(bools, nums, scored, feats):
    by_id = dict((r["post_id"], r) for r in scored)
    for f in bools:
        cs = sorted(set(r["creator"] for r in scored if feats[r["post_id"]].get(f["id"]) is True))
        f["creators_with"] = len(cs)
        if f.get("claim_ok") and len(cs) < NICHE_MIN_CREATORS:
            f["verdict_before_creators"] = f["verdict"]
            f["verdict"], f["claim_ok"] = "few creators", False
            f["note"] = "its posts come from %d creator%s: a habit, not a finding of the niche (%d creators needed)" % (
                len(cs), "" if len(cs) == 1 else "s", NICHE_MIN_CREATORS)
    for f in nums:
        w = f.get("winning_range")
        if not w:
            continue
        lo, hi = w["range"]
        cs = sorted(set(by_id[pid]["creator"] for pid in by_id
                        if feats[pid].get(f["id"]) is not None and lo <= feats[pid][f["id"]] <= hi))
        w["creators"] = len(cs)
        if len(cs) < NICHE_MIN_CREATORS:
            f["verdict_before_creators"] = f["verdict"]
            f["verdict"], f["claim_ok"], f["winning_range"] = "few creators", False, None
            f["note"] = "its winning posts come from %d creators: not a finding of the niche" % len(cs)


def run_niche(folder):
    import trends
    from common import load_posts, niche_creator_dirs
    words = load_words()
    tr = trends.run(folder)
    raw = {}
    for d in niche_creator_dirs(folder):
        for p in load_posts(os.path.join(folder, d)):
            raw[p["post_id"]] = p
    rows = [dict(p) for p in tr["posts"]]
    feats = {}
    for r in rows:
        p = raw.get(r["post_id"]) or {}
        parts = p.get("parts") or [p.get("caption") or ""]
        feats[r["post_id"]] = mark_first_part_only(p, text_features(parts, p.get("lang"), words, p.get("author_replies")))
        q = (p.get("quoted_url") or "").lower()
        feats[r["post_id"]]["quotes_own_post"] = (("/%s/" % r["account"]) in q) if q else (
            False if r["type"] != "quote" else None)
        r["lang"] = p.get("lang")
    s = dict(SETTINGS)
    s["min_creators"] = NICHE_MIN_CREATORS
    hit_ratio, flop_ratio = tr["rules"]["hit_ratio"], tr["rules"]["flop_ratio"]
    scored = [r for r in rows if r["status"] in ("scored", "fresh") and r["ratio"] is not None and not feats[r["post_id"]].get("empty")]
    settled_scored = [r for r in scored if r["status"] == "scored"]
    inwin = [r for r in rows if r["in_window"] and not feats[r["post_id"]].get("empty")]
    langs, hows = {}, {}
    for r in inwin:
        f = feats[r["post_id"]]
        langs[f["language"] or "unknown"] = langs.get(f["language"] or "unknown", 0) + 1
        hows[f["language_how"]] = hows.get(f["language_how"], 0) + 1
    covered = words["covered"]
    nets = tr["niche"].get("networks") or []
    out = {
        "schema": "rea-viral/writing@1",
        "scope": "shared",
        "skill_version": SKILL_VERSION,
        "generated_at": iso(now_utc()),
        "inputs": tr["inputs"],
        "words": {"file": "data/writing-words.json", "version": words["version"], "covered": covered},
        "settings": s,
        "metric": "views (each creator's own; likes where a creator's posts show no views)",
        "subject": {"niche": tr["niche"].get("name"), "network": nets[0] if nets else None, "handle": None,
                    "networks": nets},
        "window": tr["window"],
        "analysis_status": tr["status"],
        "language": {
            "covered": covered, "posts_by_language": langs, "how": hows,
            "posts_covered": sum(v for k, v in langs.items() if k in covered), "posts_in_window": len(inwin),
            "note": ("The word lists cover %s. Word-based features of posts in other languages are unknown (null), "
                     "never guessed." % ", ".join("%s (%s)" % (words["languages"][c]["name"] or c, c) for c in covered)),
        },
        "signal_names": signal_names(rows),
        "counts": {"posts": len(rows), "in_window_with_text": len(inwin), "scored_with_text": len(scored),
                   "empty_text": sum(1 for r in rows if feats[r["post_id"]].get("empty")),
                   "creators_scored": len(set(r["creator"] for r in scored))},
    }
    if not inwin:
        out["status"], out["status_note"] = "no_text", "No post in the window has words to read."
        out.update({"features": [], "numbers": [], "overlaps": [], "first_lines": {"best": [], "worst": []},
                    "asks": {}, "account_signals": {}, "on_screen": []})
        return out, rows, feats
    if tr["status"] != "ok" or len(scored) < 2 * s["min_posts"]:
        out["status"] = "too_few_posts"
        out["status_note"] = ("%s; only how often each feature is used is reported, never a lift." % (
            tr.get("status_note") or "%d scored posts with words" % len(scored)))
        scored_for_lift = []
    else:
        out["status"], out["status_note"] = "ok", None
        scored_for_lift = scored
    bools, nums = measure(scored_for_lift, inwin, feats, s, hit_ratio, flop_ratio, None)
    _creator_rule(bools, nums, scored_for_lift, feats)
    out["features"], out["numbers"] = bools, nums
    out["overlaps"] = overlaps(bools, scored_for_lift, feats, s)
    out["account_signals"] = signal_stats(scored or inwin)

    def fl(r):
        f = feats[r["post_id"]]
        return {"post_id": r["post_id"], "account": r["account"], "creator": r["creator"], "url": r["url"],
                "ratio": rnd(r["ratio"], 3), "views": r["views"], "first_line": f.get("first_line"),
                "chars": f.get("first_line_chars"), "type": r["type"],
                "openings": [k for k, v in f.items() if k.startswith("opens_") and v is True],
                "first_part_only": bool(f.get("first_part_only")),
                "fresh": bool(r.get("fresh") or r.get("status") == "fresh")}

    def spread(ps, n=8, per=2):
        """The first n, at most `per` of any one creator, so one creator's lines cannot fill the list."""
        out_, seen = [], {}
        for r in ps:
            if seen.get(r["creator"], 0) >= per:
                continue
            seen[r["creator"]] = seen.get(r["creator"], 0) + 1
            out_.append(fl(r))
            if len(out_) >= n:
                break
        return out_
    out["first_lines"] = {"best": spread(sorted(scored, key=lambda r: -r["ratio"])),
                          "worst": spread(sorted(settled_scored, key=lambda r: r["ratio"])), "evidence": "SEEN",
                          "note": "at most 2 lines of any one creator on each side"}
    with_ask = [r for r in inwin if feats[r["post_id"]].get("has_ask") is True]
    known = [r for r in inwin if feats[r["post_id"]].get("has_ask") is not None]
    kinds = dict((k, sum(1 for r in with_ask if k in (feats[r["post_id"]].get("ask_kinds") or []))) for k in ASK_KINDS)
    where = {}
    for r in with_ask:
        w = feats[r["post_id"]].get("ask_where")
        where[w] = where.get(w, 0) + 1
    out["asks"] = {"posts_known": len(known), "posts_with_ask": len(with_ask),
                   "share": rnd(len(with_ask) / float(len(known)), 3) if known else None, "kinds": kinds, "where": where,
                   "later_replies": {"posts": 0, "with_ask": 0, "note": ""},
                   "examples": [{"post_id": r["post_id"], "account": r["account"], "phrases": feats[r["post_id"]].get("ask_phrases"),
                                 "kinds": feats[r["post_id"]].get("ask_kinds"), "ratio": rnd(r["ratio"], 3)}
                                for r in sorted(with_ask, key=lambda r: -(r["ratio"] or 0))[:8]]}
    on = []
    by_id = dict((r["post_id"], r) for r in rows)
    for d in niche_creator_dirs(folder):
        for x in on_screen_lines(os.path.join(folder, d), by_id, words):
            x["account"] = (by_id.get(x["post_id"]) or {}).get("account")
            on.append(x)
    out["on_screen"] = sorted(on, key=lambda x: -(x["ratio"] or 0))
    return out, rows, feats


def write_hooks(folder, out):
    """hooks.md: the niche's hooks in place of a voice sheet. Same rea-voice block (draft_check.py reads it), its own prose."""
    path = os.path.join(folder, "hooks.md")
    net = out["subject"]["network"]
    measured = voice_measured(out)
    table = MEASURED_START + "\n" + measured_table(out) + "\n" + MEASURED_END
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        m = VOICE_RE.search(text)
        if m:
            try:
                rec = json.loads(m.group(1))
            except ValueError:
                die("%s: the rea-voice JSON block does not parse; fix it, then run text_probe.py again" % path, 1)
            rec["measured"] = measured
            if not rec.get("rules"):
                rec["rules"] = default_rules(out, net)
            text = text[:m.start()] + "```json rea-voice\n" + json.dumps(rec, indent=2, ensure_ascii=False) + "\n```" + text[m.end():]
        if MEASURED_START in text and MEASURED_END in text:
            a = text.index(MEASURED_START)
            b = text.index(MEASURED_END) + len(MEASURED_END)
            text = text[:a] + table + text[b:]
        write_text(path, text)
        return path, False
    rec = {"schema": "rea-viral/voice@1", "scope": "shared", "network": net, "niche": out["subject"]["niche"],
           "rules": default_rules(out, net), "measured": measured}
    body = [
        "# Hooks of the niche: %s" % (out["subject"]["niche"] or ""),
        "",
        "What the niche's winning posts open with, measured against each creator's own usual (a post is compared only",
        "with its own creator's other posts). It takes the place of a voice sheet: a niche run writes no voice.md (a voice",
        "is one account's; for one creator's, run words only or an account run on that creator). The JSON block is what",
        "`draft_check.py` reads for a draft written with these hooks; `measured` and the table between the markers are",
        "rewritten by `text_probe.py` on every run. A feature counts for the niche only when its posts come from 3",
        "creators or more.",
        "Every line below carries its label: MEASURED (writing.json#features.<id>), SEEN (post ids), INFERRED (basis).",
        "",
        "```json rea-voice",
        json.dumps(rec, indent=2, ensure_ascii=False),
        "```",
        "",
        table,
        "",
        "## Openings that work across creators",
        "",
        "(The agent: each measured opening that lifts, with real first lines of at least two different creators and",
        "their ratios, SEEN with the post ids. When nothing lifts, say so and show the openings used most.)",
        "",
        "## What the hits share, and what the flops share too",
        "",
        "## What only one creator does",
        "",
        "(Habits of one or two creators: theirs, not the niche's. writing.json marks them \"few creators\".)",
        "",
        "## Where the niche's numbers disagree with general advice",
        "",
    ]
    write_text(path, "\n".join(body))
    return path, True


# ---------------------------------------------------------------------------------------------- voice.md

VOICE_RE = re.compile(r"```json rea-voice\s*\n(.*?)\n```", re.S)
MEASURED_START = "<!-- rea:measured:start -->"
MEASURED_END = "<!-- rea:measured:end -->"
NETWORK_LIMITS = {"x": 280, "threads": 500, "linkedin": 3000, "instagram": 2200, "tiktok": 2200, "youtube": 5000,
                  "bluesky": 300, "mastodon": 500}


def feature(out, fid):
    for f in out.get("features", []) + out.get("numbers", []):
        if f["id"] == fid:
            return f
    return None


def voice_measured(out):
    """The short measured summary the voice sheet carries (text_probe.py owns it)."""
    if out.get("status") not in ("ok", "too_few_posts"):
        return {"status": out.get("status")}
    m = {"status": out["status"], "language": out["language"]["covered"], "scored_with_text": out["counts"]["scored_with_text"]}
    fl = feature(out, "first_line_chars")
    m["first_line_chars"] = {"usual": [fl["usage"]["p10"], fl["usage"]["p90"]], "median": fl["usage"]["median"],
                             "winning_range": (fl.get("winning_range") or {}).get("range"), "verdict": fl["verdict"]}
    ch = feature(out, "chars")
    m["chars"] = {"usual": [ch["usage"]["p10"], ch["usage"]["p90"]], "median": ch["usage"]["median"],
                  "winning_range": (ch.get("winning_range") or {}).get("range"), "verdict": ch["verdict"]}
    lp = feature(out, "longest_paragraph_lines")
    m["longest_paragraph_lines"] = {"usual": [lp["usage"]["p10"], lp["usage"]["p90"]], "max": lp["usage"]["max"],
                                    "winning_range": (lp.get("winning_range") or {}).get("range"), "verdict": lp["verdict"]}
    m["lifts"] = [f["id"] for f in out["features"] if f["verdict"] == "lifts"]
    m["sinks"] = [f["id"] for f in out["features"] if f["verdict"] == "sinks"]
    m["never"] = [f["id"] for f in out["features"] if f["usage"]["known"] and f["usage"]["with"] == 0]
    m["openings_used"] = sorted([f["id"] for f in out["features"] if f["group"] == "opening" and f["usage"]["with"]],
                                key=lambda i: -feature(out, i)["usage"]["with"])
    m["asks"] = {"share": out["asks"].get("share"), "kinds": dict((k, v) for k, v in (out["asks"].get("kinds") or {}).items() if v),
                 "where": out["asks"].get("where")}
    return m


def default_rules(out, net):
    m = voice_measured(out)
    if m.get("status") not in ("ok", "too_few_posts"):
        return {}
    fl = m["first_line_chars"]
    rng = fl["winning_range"] or fl["usual"]
    ch = m["chars"]
    lp = m["longest_paragraph_lines"]
    lp_max = (lp["winning_range"] or [None, None])[1] or lp["usual"][1] or lp["max"] or 1
    openings = list(m["lifts"] and [i for i in m["lifts"] if i.startswith("opens_")] or [])
    for i in m["openings_used"][:3]:
        if i not in openings and i not in m["sinks"]:
            openings.append(i)
    kinds = [k for k in (m["asks"]["kinds"] or {}) if "ask_" + k not in m["sinks"]]
    where = max((m["asks"]["where"] or {"end": 0}).items(), key=lambda kv: kv[1])[0] if m["asks"]["where"] else "end"
    return {
        "first_line_chars": [int(rng[0]), int(round(rng[1]))] if rng and rng[0] is not None else None,
        "first_line_basis": "measured winning range" if fl["winning_range"] else "the account's usual range (8 in 10 of its posts); no range measured to win",
        "chars": [int(ch["winning_range"][0]), int(round(ch["winning_range"][1]))] if ch["winning_range"] else
                 ([int(ch["usual"][0]), int(round(ch["usual"][1]))] if ch["usual"][0] is not None else None),
        "max_paragraph_lines": int(round(lp_max)),
        "openings": openings,
        "avoid": list(m["sinks"]),
        "asks": {"kinds": kinds, "where": where or "end"},
        "length_limit": NETWORK_LIMITS.get(net, 2200),
        "long_posts": False,
    }


def measured_table(out):
    if out.get("status") not in ("ok", "too_few_posts"):
        return "Status: %s. %s" % (out.get("status"), out.get("status_note") or "")
    L = ["| What | Measured | Verdict |", "|---|---|---|"]
    for f in out["features"]:
        if f["verdict"] in ("lifts", "sinks", "never", "always", "nearly always"):
            L.append("| %s | %s posts with it, lift %s; without it %s | %s |" % (
                f["label"], f["with"]["posts"], xr(f["with"]["lift"]), xr(f["without"]["lift"]), f["verdict"]))
    for f in out["numbers"]:
        if f.get("winning_range"):
            w = f["winning_range"]
            L.append("| %s | %s to %s: lift %s on %d posts | %s |" % (f["label"], fmt(w["range"][0]), fmt(w["range"][1]),
                                                                       xr(w["lift"]), w["posts"], f["verdict"]))
    if len(L) == 2:
        L.append("| Nothing | no feature lifts or sinks with 6+ posts on each side | - |")
    L.append("")
    L.append("All MEASURED by text_probe.py (writing.json): the median of each group's ratios (each post against the median "
             "of the 20 posts before it). %d scored posts with words. Status: %s." % (out["counts"]["scored_with_text"], out["status"]))
    return "\n".join(L)


def xr(v):
    return "-" if v is None else ("%.2f" % v).rstrip("0").rstrip(".") + "x"


def fmt(v):
    if v is None:
        return "-"
    return ("%d" % v) if float(v).is_integer() else ("%.2f" % v)


def write_voice(folder, out):
    path = os.path.join(folder, "voice.md")
    net = out["subject"]["network"]
    measured = voice_measured(out)
    table = MEASURED_START + "\n" + measured_table(out) + "\n" + MEASURED_END
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        m = VOICE_RE.search(text)
        if m:
            try:
                rec = json.loads(m.group(1))
            except ValueError:
                die("%s: the rea-voice JSON block does not parse; fix it, then run text_probe.py again" % path, 1)
            rec["measured"] = measured
            if not rec.get("rules"):
                rec["rules"] = default_rules(out, net)
            text = text[:m.start()] + "```json rea-voice\n" + json.dumps(rec, indent=2, ensure_ascii=False) + "\n```" + text[m.end():]
        if MEASURED_START in text and MEASURED_END in text:
            a = text.index(MEASURED_START)
            b = text.index(MEASURED_END) + len(MEASURED_END)
            text = text[:a] + table + text[b:]
        write_text(path, text)
        return path, False
    rec = {"schema": "rea-viral/voice@1", "network": net, "handle": out["subject"]["handle"],
           "rules": default_rules(out, net), "measured": measured}
    body = [
        "# Voice sheet: @%s on %s" % (out["subject"]["handle"], net),
        "",
        "How this account writes, measured against its own results: the writing twin of a format recipe. The JSON block",
        "is what `draft_check.py` reads. `rules` is yours: it starts from the measured values; change a rule only with a",
        "reason written below. `measured` and the table between the markers are rewritten by `text_probe.py` on every run.",
        "Every line below carries its label: MEASURED (writing.json#features.<id>), SEEN (post ids), INFERRED (basis).",
        "",
        "```json rea-voice",
        json.dumps(rec, indent=2, ensure_ascii=False),
        "```",
        "",
        table,
        "",
        "## Openings that work",
        "",
        "(The agent: each measured opening that lifts, with two or three of the account's real first lines and their",
        "ratios, SEEN with the post ids. Only openings writing.json measured; no list of hook types.)",
        "",
        "## Its shape",
        "",
        "## Its asks",
        "",
        "## What it never does",
        "",
        "## What flops when it tries",
        "",
        "## Where its numbers disagree with general advice",
        "",
        "(The account's numbers win here; the editor's pass in references/writing.md is general craft.)",
        "",
    ]
    write_text(path, "\n".join(body))
    return path, True


def read_voice(folder):
    """The voice sheet a draft is checked against: voice.md of an account or post run, hooks.md of a niche."""
    path = os.path.join(folder, "hooks.md" if os.path.exists(os.path.join(folder, "niche.json")) else "voice.md")
    if not os.path.exists(path):
        return None
    m = VOICE_RE.search(open(path, encoding="utf-8").read())
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------- outputs

TEXT_COLUMNS = ["post_id", "status", "ratio", "type", "language", "first_line", "first_line_chars", "first_line_words",
                "chars", "words", "lines", "paragraphs", "longest_paragraph_lines", "avg_sentence_words",
                "short_lines_share", "numbers_per_100_words", "parts"] + [b[0] for b in BOOL_FEATURES] + \
               ["ask_kinds", "ask_where", "later_reply_ask_kinds", "save_per_like", "reply_per_like", "share_per_like",
                "quote_per_like"]


def write_outputs(folder, out, rows, feats):
    write_json(os.path.join(folder, "writing.json"), out)
    recs = []
    shared = out.get("scope") == "shared"
    for r in rows:
        f = feats[r["post_id"]]
        rec = {"post_id": r["post_id"], "status": r["status"], "ratio": r["ratio"], "type": r["type"],
               "language": f.get("language") or ""}
        if shared:
            rec["account"] = r.get("account")
        for c in TEXT_COLUMNS[5:]:
            if c in rec:
                continue
            v = f.get(c)
            if isinstance(v, bool):
                v = "true" if v else "false"
            elif isinstance(v, list):
                v = ";".join(v)
            rec[c] = v
        for key, _, getter in SIGNALS:
            rec[key + "_per_like"] = rnd(per_like(r, getter), 4)
        recs.append(rec)
    write_csv(os.path.join(folder, "posts_text.csv"), (["account"] if shared else []) + TEXT_COLUMNS, recs)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    out, rows, feats = run(folder)
    write_outputs(folder, out, rows, feats)
    path, new = (write_hooks if out.get("scope") == "shared" else write_voice)(folder, out)
    print("writing.json: status %s (%s scored posts with words; languages %s)" % (
        out["status"], out["counts"]["scored_with_text"], out["language"]["posts_by_language"]))
    if out.get("status_note"):
        print("  " + out["status_note"])
    for f in out.get("features", []):
        if f["verdict"] in ("lifts", "sinks"):
            print("  %-22s %-6s with %2d posts lift %-6s without %2d posts lift %s" % (
                f["id"], f["verdict"], f["with"]["posts"], xr(f["with"]["lift"]), f["without"]["posts"], xr(f["without"]["lift"])))
    for f in out.get("numbers", []):
        if f.get("winning_range"):
            w = f["winning_range"]
            print("  %-22s %-11s %s to %s, lift %s on %d posts" % (f["id"], f["verdict"], fmt(w["range"][0]), fmt(w["range"][1]),
                                                                   xr(w["lift"]), w["posts"]))
    for o in out.get("overlaps", []):
        print("  together: %s + %s on %d posts" % (o["a"], o["b"], o["posts_both"]))
    print("  %s %s" % ("wrote" if new else "updated", os.path.relpath(path, folder)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
