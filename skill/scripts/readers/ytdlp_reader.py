#!/usr/bin/env python3
"""An example reader: yt-dlp (free, no sign-in) into the normalised rows. The method does not depend on it.

    python3 ytdlp_reader.py posts <run folder> <profile url> [--max 60] [--spread N] [--no-covers] [--sleep 1]
    python3 ytdlp_reader.py find <niche folder> <hashtag page | ytsearchN:words | channel url> [--max 40] [--shorts-only]
    python3 ytdlp_reader.py comments <run folder> (<post_id> ... | --picks) [--per-post 60] [--replies 5]
    python3 ytdlp_reader.py followers <network> <handle>        (for watch.py: prints one JSON object)
    python3 ytdlp_reader.py seeds <niche folder>                  (checks each seed account before anything is read)

Works best on YouTube (a channel's Shorts tab: https://www.youtube.com/@handle/shorts). TikTok profile pages often
refuse yt-dlp without a sign-in, and Instagram almost always does: then use another reader and write the same rows.

What it writes:
  posts      posts.csv (one full read per post: exact views, likes, comments, length, exact time), covers/<id>.jpg, raw/ytdlp/<id>.json (the answer, trimmed of the format lists), and
             account.json when there is none.
  find       for a niche run: appends found.csv (one row per post found, read once on its own: its creator, time,
             exact views) and prints the creators found, most found posts first. A hashtag's Shorts page lists only ids
             and rounded views, and a search mixes long videos in, so every found post gets its own read; posts outside
             niche.json's window are left out; --shorts-only skips anything over 3 minutes.
  comments   comments.csv (appends; top comments and replies, with who is the creator, pinned, hearted) and updates
             account.json comments_read. YouTube gives comment times as "2 days ago": they are written with
             created_at_exact false, and nothing is measured in minutes from them.
  seeds      for a niche run, before anything else is read: each YouTube seed of niche.json is looked up (its Shorts
             list, then its newest Short's date) and marked in niche.json: found, not_found (the channel does not
             answer: a misspelt or gone handle) or inactive (no Short in the window). Nothing is guessed: a handle that
             is not found is never swapped for a near spelling. Seeds on other networks are checked with their own
             reader the same way (references/niche.md, step 2).
What it does not read: shares and saves (not public on YouTube), follower history (no free source).
Known traps (seen in a real run, 2026-11-14): the flat channel listing has no dates and rounded views, so every post
gets its own full read; with --write-comments yt-dlp sets comment_count to the number it fetched, so posts.csv takes
the count from the plain read only.
Needs yt-dlp on PATH. Polite by default: one request a second.
"""
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(HERE))
from common import (COMMENT_COLUMNS, POST_COLUMNS, iso, norm_handle, note_cover_not_read, now_utc, read_csv,  # noqa: E402
                    read_json, save_picture, write_csv, write_json)

TRIM = {"formats", "requested_formats", "thumbnails", "automatic_captions", "subtitles", "heatmap", "http_headers",
        "_format_sort_fields", "requested_subtitles", "storyboards", "fragments"}


def ytdlp():
    p = shutil.which("yt-dlp")
    if not p:
        sys.stderr.write("yt-dlp is not on PATH (pip install yt-dlp, or brew install yt-dlp)\n")
        sys.exit(2)
    return p


def run(args, timeout=300):
    try:
        r = subprocess.run([ytdlp(), "--no-update", "--no-warnings", "--socket-timeout", "20"] + args,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timed out"
    if r.returncode != 0:
        return None, (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["failed"])[-1][:300]
    return r.stdout.decode("utf-8", "replace"), None


def network_of(url):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    return "other"


def ts_iso(info):
    if info.get("timestamp"):
        return iso(dt.datetime.fromtimestamp(int(info["timestamp"]), dt.timezone.utc))
    d = info.get("upload_date")
    if d and re.fullmatch(r"\d{8}", d):
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:])
    return ""


def num(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def trim(info):
    return dict((k, v) for k, v in info.items() if k not in TRIM)


def fetch_cover(url, dest_stem):
    """Save a cover like a browser (common.save_picture). Returns (relative path or None, why not)."""
    got, why = save_picture(url, dest_stem)
    return got, why


def cmd_posts(folder, url, argv):
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 60
    # --spread N: list the latest N posts (one request) and read --max of them, evenly spread. For a creator who
    # posts several times a day, the latest 25 posts cover only days; spread reads reach back over the window
    # with the same number of reads (learned on a real niche run, 2026-11-16).
    spread = int(argv[argv.index("--spread") + 1]) if "--spread" in argv else 0
    sleep = float(argv[argv.index("--sleep") + 1]) if "--sleep" in argv else 1.0
    covers = "--no-covers" not in argv
    os.makedirs(os.path.join(folder, "raw", "ytdlp"), exist_ok=True)
    out, err = run(["-J", "--flat-playlist", "--playlist-items", "1-%d" % max(mx, spread), url])
    if err:
        sys.stderr.write("could not list %s: %s\n" % (url, err))
        return 1
    flat = json.loads(out)
    with open(os.path.join(folder, "raw", "ytdlp", "_profile.json"), "w", encoding="utf-8") as f:
        json.dump(trim(dict((k, v) for k, v in flat.items() if k != "entries")), f, ensure_ascii=False, indent=1)
    entries = [e for e in flat.get("entries") or [] if e.get("id")]
    listed = len(entries)
    if spread and len(entries) > mx:
        step = len(entries) / float(mx)
        entries = [entries[int(i * step)] for i in range(mx)]
    else:
        entries = entries[:mx]
    net = network_of(url)
    read_at = now_utc()
    rows = []
    failed = []
    for i, e in enumerate(entries):
        purl = e.get("url") or e.get("webpage_url")
        if purl and not purl.startswith("http"):
            purl = "https://www.youtube.com/shorts/" + e["id"] if net == "youtube" else purl
        o, err = run(["-j", "--skip-download", purl], timeout=120)
        if err:
            failed.append((e["id"], err))
            continue
        info = json.loads(o)
        with open(os.path.join(folder, "raw", "ytdlp", "%s.json" % info["id"]), "w", encoding="utf-8") as f:
            json.dump(trim(info), f, ensure_ascii=False, indent=1)
        cap = info.get("title") or ""
        desc = info.get("description") or ""
        if desc and desc.strip() != cap.strip():
            cap = (cap + "\n" + desc).strip()
        row = {
            "post_id": info["id"], "url": info.get("webpage_url") or purl, "published_at": ts_iso(info),
            "type": "video", "duration_s": info.get("duration"), "caption": cap[:2000],
            "views": num(info.get("view_count")), "likes": num(info.get("like_count")),
            "comments": num(info.get("comment_count")), "shares": num(info.get("repost_count")), "saves": None,
            "cover_url": info.get("thumbnail") or "", "sound": (info.get("track") or "") + (
                (" - " + info["artist"]) if info.get("artist") else ""),
            "read_at": iso(read_at), "source": "yt-dlp",
            # No "lang": YouTube's "language" is the audio language the uploader set, not the language of the title
            # (English titles came tagged "ja" in a real run, 2026-11-16), so the word lists decide instead.
        }
        if covers and row["cover_url"]:
            stem = os.path.join(folder, "covers", info["id"])
            have = [stem + e for e in (".jpg", ".png", ".webp", ".gif") if os.path.exists(stem + e)]
            got, why = (have[0], None) if have else fetch_cover(row["cover_url"], stem)
            if got:
                row["cover_file"] = "covers/" + os.path.basename(got)
            else:
                note_cover_not_read(folder, info["id"], why)      # the sheet and the report say "not read: HTTP 403"
        rows.append(row)
        sys.stdout.write("\r%d/%d read" % (i + 1, len(entries)))
        sys.stdout.flush()
        time.sleep(sleep)
    sys.stdout.write("\n")
    write_csv(os.path.join(folder, "posts.csv"), POST_COLUMNS, rows)
    acc_path = os.path.join(folder, "account.json")
    if not os.path.exists(acc_path):
        dates = sorted(r["published_at"] for r in rows if r["published_at"])
        handle = norm_handle(flat.get("uploader_id") or flat.get("channel") or "")
        acc = {
            "schema": "rea-viral/account@2", "network": net, "handle": handle,
            "name": flat.get("channel") or flat.get("uploader") or handle,
            "url": flat.get("channel_url") or url, "bio": (flat.get("description") or "")[:500], "link": None,
            "followers": num(flat.get("channel_follower_count")),
            "followers_exact": False if net == "youtube" else None,
            "following": None, "posts_total": None, "verified": None, "private": False, "read_at": iso(read_at),
            # The latest N posts: the oldest 20 only feed baselines when there are 40 or more.
            "window": {"from": (dates[20] if len(dates) >= 40 else (dates[0] if dates else ""))[:10] or None,
                       "to": dates[-1][:10] if dates else None},
            "follower_history": [],
            "sources": [{"what": "profile and posts", "via": "yt-dlp " + yver(), "cost_usd": 0,
                         "notes": "one full read per post; flat listing used only for the ids"}],
            "spend_ceiling_usd": 3,
        }
        write_json(acc_path, acc)
    if spread and listed > len(rows):
        # Say how the creator was sampled: the report shows it among what the run did not read in full.
        acc = read_json(acc_path)
        acc["sampled"] = {"read": len(rows), "of": listed, "how": "spread across its latest %d posts" % listed}
        write_json(acc_path, acc)
    print("posts.csv: %d rows%s" % (len(rows), ("; %d failed: %s" % (len(failed), "; ".join("%s %s" % f for f in failed[:5])))
                                    if failed else ""))
    return 0 if rows else 1


FOUND_COLUMNS = ["post_id", "url", "network", "account", "account_url", "found_by", "query", "published_at", "views",
                 "duration_s", "followers", "title"]


def cmd_find(folder, url, argv):
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 40
    sleep = float(argv[argv.index("--sleep") + 1]) if "--sleep" in argv else 1.0
    shorts_only = "--shorts-only" in argv
    lo = hi = None
    np_ = os.path.join(folder, "niche.json")
    if os.path.exists(np_):
        w = read_json(np_).get("window") or {}
        lo, hi = (w.get("from") or "")[:10] or None, (w.get("to") or "")[:10] or None
    found_by = "tag" if "/hashtag/" in url else ("search" if url.startswith("ytsearch") or "/results?" in url else (
        "seed_account" if "/@" in url or "/channel/" in url else "other"))
    out, err = run(["-J", "--flat-playlist", "--playlist-items", "1-%d" % mx, url])
    if err:
        sys.stderr.write("could not list %s: %s\n" % (url, err))
        return 1
    entries = [e for e in json.loads(out).get("entries") or [] if e.get("id")][:mx]
    path = os.path.join(folder, "found.csv")
    have = []
    if os.path.exists(path):
        _, have = read_csv(path)
    seen = set(r.get("post_id") for r in have)
    os.makedirs(os.path.join(folder, "raw", "ytdlp", "found"), exist_ok=True)
    new, skipped = [], {"long": 0, "outside window": 0, "failed": 0, "already found": 0}
    for i, e in enumerate(entries):
        if e["id"] in seen:
            skipped["already found"] += 1
            continue
        if shorts_only and isinstance(e.get("duration"), (int, float)) and e["duration"] > 180:
            skipped["long"] += 1
            continue
        purl = e.get("url") or "https://www.youtube.com/shorts/" + e["id"]
        o, err = run(["-j", "--skip-download", purl], timeout=120)
        time.sleep(sleep)
        if err:
            skipped["failed"] += 1
            continue
        info = json.loads(o)
        with open(os.path.join(folder, "raw", "ytdlp", "found", "%s.json" % info["id"]), "w", encoding="utf-8") as f:
            json.dump(trim(info), f, ensure_ascii=False, indent=1)
        if shorts_only and (info.get("duration") or 0) > 180:
            skipped["long"] += 1
            continue
        when = ts_iso(info)
        if lo and hi and when and not (lo <= when[:10] <= hi):
            skipped["outside window"] += 1
            continue
        new.append({"post_id": info["id"], "url": info.get("webpage_url") or purl, "network": network_of(purl),
                    "account": norm_handle(info.get("uploader_id") or info.get("channel_id") or ""),
                    "account_url": info.get("uploader_url") or info.get("channel_url") or "", "found_by": found_by,
                    "query": url, "published_at": when, "views": num(info.get("view_count")),
                    "duration_s": info.get("duration"), "followers": num(info.get("channel_follower_count")),
                    "title": (info.get("title") or "")[:200]})
        seen.add(info["id"])
        sys.stdout.write("\r%d/%d read" % (i + 1, len(entries)))
        sys.stdout.flush()
    sys.stdout.write("\n")
    write_csv(path, FOUND_COLUMNS, have + new)
    by = {}
    for r in have + new:
        by.setdefault(r["account"], []).append(r)
    print("found.csv: %d new posts (%d in all); left out: %s" % (len(new), len(have) + len(new), ", ".join(
        "%d %s" % (v, k) for k, v in skipped.items() if v) or "none"))
    for h, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print("  @%-26s %2d found  followers %-9s best %-9s %s" % (
            h[:26], len(rs), rs[0].get("followers") or "?",
            max((int(r["views"]) for r in rs if str(r.get("views") or "").isdigit()), default="?"),
            (rs[0].get("account_url") or "") + "/shorts"))
    return 0 if (have + new) else 1


def yver():
    o, _ = run(["--version"], 30)
    return (o or "").strip()


def cmd_comments(folder, argv):
    per = int(argv[argv.index("--per-post") + 1]) if "--per-post" in argv else 60
    reps = int(argv[argv.index("--replies") + 1]) if "--replies" in argv else 5
    ids = [a for a in argv if not a.startswith("--") and not re.fullmatch(r"\d+", a)]
    if "--picks" in argv:
        dr = read_json(os.path.join(folder, "analysis.json")).get("deep_read") or {}
        for k in ("outliers", "ordinary", "flops"):
            ids += [i for i in dr.get(k) or [] if i not in ids]
    _, prow = read_csv(os.path.join(folder, "posts.csv"))
    urls = dict((r["post_id"], r["url"]) for r in prow)
    path = os.path.join(folder, "comments.csv")
    have = []
    if os.path.exists(path):
        _, have = read_csv(path)
    done = set(r["post_id"] for r in have)
    new = []
    for pid in ids:
        if pid in done or pid not in urls:
            continue
        o, err = run(["-j", "--skip-download", "--write-comments", "--extractor-args",
                      "youtube:max_comments=%d,all,all,%d;comment_sort=top" % (per, reps), urls[pid]], timeout=300)
        if err:
            print("%s: comments not read: %s" % (pid, err))
            continue
        info = json.loads(o)
        os.makedirs(os.path.join(folder, "raw", "ytdlp"), exist_ok=True)
        with open(os.path.join(folder, "raw", "ytdlp", "comments-%s.json" % pid), "w", encoding="utf-8") as f:
            json.dump({"id": info.get("id"), "comment_count": info.get("comment_count"),
                       "comments": [dict((k, v) for k, v in c.items() if k != "author_thumbnail") for c in info.get("comments") or []]},
                      f, ensure_ascii=False, indent=1)
        for c in info.get("comments") or []:
            t = c.get("timestamp")
            new.append({
                "post_id": pid, "comment_id": c.get("id"), "parent_id": "" if c.get("parent") in (None, "root") else c.get("parent"),
                "author": c.get("author") or "", "author_is_creator": "true" if c.get("author_is_uploader") else "false",
                "text": (c.get("text") or "")[:2000], "likes": num(c.get("like_count")),
                "created_at": iso(dt.datetime.fromtimestamp(int(t), dt.timezone.utc)) if t else "",
                "created_at_exact": "false" if c.get("_time_text") else ("true" if t else ""),
                "is_pinned": "true" if c.get("is_pinned") else "false",
                "is_hearted": "true" if c.get("is_favorited") else "false", "reply_count": "",
            })
        print("%s: %d comments" % (pid, sum(1 for r in new if r["post_id"] == pid)))
        time.sleep(1.0)
    write_csv(path, COMMENT_COLUMNS, have + new)
    acc_path = os.path.join(folder, "account.json")
    acc = read_json(acc_path)
    posts_read = len(set(r["post_id"] for r in have + new))
    acc["comments_read"] = {"posts": posts_read, "per_post": per, "replies_read": reps > 0,
                            "how": "top comments first; at most %d replies a thread" % reps}
    srcs = acc.get("sources") or []
    if not any(s.get("what") == "comments" for s in srcs):
        srcs.append({"what": "comments", "via": "yt-dlp " + yver(), "cost_usd": 0,
                     "notes": "top comments; times are approximate ('2 days ago')"})
    acc["sources"] = srcs
    write_json(acc_path, acc)
    print("comments.csv: %d rows on %d posts" % (len(have + new), posts_read))
    return 0


def cmd_followers(network, handle):
    h = norm_handle(handle)
    if network == "youtube":
        url = "https://www.youtube.com/@%s/shorts" % h
    elif network == "tiktok":
        url = "https://www.tiktok.com/@%s" % h
    else:
        sys.stderr.write("no free yt-dlp reader for %s\n" % network)
        return 2
    o, err = run(["-J", "--flat-playlist", "--playlist-items", "1-12", url], timeout=120)
    if err:
        sys.stderr.write(err + "\n")
        return 1
    d = json.loads(o)
    f = num(d.get("channel_follower_count"))
    if f is None:
        sys.stderr.write("no follower count in the answer\n")
        return 1
    posts = [{"post_id": e.get("id"), "url": e.get("url"), "views": num(e.get("view_count")),
              "published_at": ts_iso(e) or None} for e in d.get("entries") or []]
    print(json.dumps({"followers": f, "exact": False if network == "youtube" else None, "source": "yt-dlp",
                      "profile": {"bio": d.get("description"), "name": d.get("channel")}, "recent_posts": posts,
                      "cost_usd": 0}))
    return 0


def cmd_seeds(folder):
    """Check each YouTube seed of niche.json: found, not_found or inactive, written back into niche.json."""
    from common import parse_time
    path = os.path.join(folder, "niche.json")
    if not os.path.exists(path):
        sys.stderr.write("no niche.json in %s\n" % folder)
        return 2
    niche = read_json(path)
    lo = parse_time((niche.get("window") or {}).get("from")) if (niche.get("window") or {}).get("from") else None
    nets = niche.get("networks") or []
    seeds = niche.get("seed_accounts") or []
    for s in seeds:
        net = s.get("network") or (nets[0] if len(nets) == 1 else None)
        h = norm_handle(s.get("handle"))
        if net != "youtube" or not h:
            print("  @%-24s %-10s not checked here (needs a reader for %s)" % (h, "-", net or "its network"))
            continue
        o, err = run(["-J", "--flat-playlist", "--playlist-items", "1-3", "https://www.youtube.com/@%s/shorts" % h], timeout=120)
        entries = (json.loads(o).get("entries") or []) if o else []
        if err or o is None:
            s.update({"status": "not_found", "note": "the channel did not answer: %s" % (err or "no answer")[:160]})
        elif not entries:
            s.update({"status": "inactive", "note": "no Shorts on the channel"})
        else:
            first = entries[0]
            o2, err2 = run(["-J", "--skip-download", first.get("url") or "https://www.youtube.com/shorts/%s" % first.get("id")], timeout=120)
            when = ts_iso(json.loads(o2)) if o2 else ""
            if when and lo and parse_time(when) < lo:
                s.update({"status": "inactive", "note": "the newest Short is from %s, before the window" % when[:10]})
            else:
                s.update({"status": "found", "note": ("the newest Short is from %s" % when[:10]) if when else "found"})
        s["checked_at"] = iso(now_utc())
        print("  @%-24s %-10s %s" % (h, s["status"], s.get("note") or ""))
    niche["seed_accounts"] = seeds
    write_json(path, niche)
    bad = [s for s in seeds if s.get("status") in ("not_found", "inactive")]
    if bad:
        print("say so in the setup answer, by name, and go on with the rest: %s" % ", ".join(
            "@%s (%s)" % (norm_handle(s.get("handle")), s["status"].replace("_", " ")) for s in bad))
    return 0


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 2
    if argv[1] == "posts":
        return cmd_posts(argv[2], argv[3], argv[4:])
    if argv[1] == "comments":
        return cmd_comments(argv[2], argv[3:])
    if argv[1] == "find":
        return cmd_find(argv[2], argv[3], argv[4:])
    if argv[1] == "followers":
        return cmd_followers(argv[2], argv[3])
    if argv[1] == "seeds":
        return cmd_seeds(argv[2])
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
