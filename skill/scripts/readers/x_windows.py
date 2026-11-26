#!/usr/bin/env python3
"""Date-window collector helper for connectors whose cursor pagination stops early (e.g. X get_users_posts returning
empty after page 2).

    python3 x_windows.py plan --from 2026-09-01 --to 2026-11-26 [--step-days 14]
    python3 x_windows.py next-end <posts.csv | raw.json> [--backoff-seconds 1]
    python3 x_windows.py merge <out.csv> <page1.csv> [<page2.csv> ...]

Why this exists (0.5.1, learned on the @b1rkh0ff run):
Some X data connectors' `get_users_posts` pagination returns an empty page after page 2 even when the account has
hundreds of older posts. Instead of stopping at ~40 posts:
  1. Call `get_users_posts` normally while cursor pagination returns new rows.
  2. When a cursor page comes back empty (or repeats only already-seen post_ids) before reaching `window.from`,
     switch to the `end_time` window fallback: pass `end_time` = 1 second before the oldest `published_at` collected
     so far (or iterate backward in date windows from `x_windows.py plan`).
  3. Repeat until `oldest <= window.from`, the target post cap is reached, or two consecutive date windows return zero
     new posts. Deduplicate by `post_id`.

Also exposes `collect_with_end_time_fallback(fetch_page, ...)` so Python collectors can call it directly.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common import POST_COLUMNS, iso, parse_time, read_csv, write_csv  # noqa: E402


def plan_windows(start_iso, end_iso, step_days=14):
    """Return newest-first [{"start_time", "end_time"}] ISO UTC windows covering [start_iso, end_iso]."""
    lo = parse_time(start_iso)
    hi = parse_time(end_iso)
    if lo is None or hi is None:
        raise ValueError("start and end must be ISO 8601 dates/times")
    if len(str(end_iso).strip()) == 10:
        hi = hi + dt.timedelta(days=1) - dt.timedelta(seconds=1)
    if lo > hi:
        lo, hi = hi, lo
    step = dt.timedelta(days=max(1, int(step_days)))
    windows = []
    cur_end = hi
    while cur_end >= lo:
        cur_start = max(lo, cur_end - step + dt.timedelta(seconds=1))
        windows.append({"start_time": iso(cur_start), "end_time": iso(cur_end)})
        if cur_start <= lo:
            break
        cur_end = cur_start - dt.timedelta(seconds=1)
    return windows


def next_end_time(timestamps, backoff_seconds=1):
    """Given ISO timestamps or datetimes of rows already collected, return the next `end_time` ISO string
    just before the oldest row, or None when no valid timestamp is present."""
    parsed = []
    for t in timestamps:
        if isinstance(t, dt.datetime):
            parsed.append(t.astimezone(dt.timezone.utc))
        elif t:
            try:
                p = parse_time(t)
                if p is not None:
                    parsed.append(p)
            except Exception:
                pass
    if not parsed:
        return None
    return iso(min(parsed) - dt.timedelta(seconds=max(1, int(backoff_seconds))))


def collect_with_end_time_fallback(fetch_page, start_time=None, end_time=None, max_posts=200, max_calls=30,
                                   step_days=14, empty_window_limit=2):
    """Collect posts using cursor pagination first, automatically falling back to `end_time` date windows when
    cursor pagination returns empty (e.g. `get_users_posts` after page 2).

    `fetch_page(cursor=None, end_time=None, start_time=None)` must return a dict:
      {"posts": [{"post_id" or "id": ..., "published_at" or "created_at": ISO, ...}, ...], "next_cursor": str|None}

    Returns {"posts": [...deduped newest-first...], "calls": int, "used_end_time_fallback": bool,
             "stop_reason": str}.
    """
    lo = parse_time(start_time) if start_time else None
    cur_end = end_time
    seen = {}
    calls = 0
    cursor = None
    mode = "cursor"
    used_fallback = False
    empty_windows = 0
    stop_reason = "done"

    def post_id(p):
        return str(p.get("post_id") or p.get("id") or "").strip()

    def post_time(p):
        raw = p.get("published_at") or p.get("created_at") or p.get("at")
        if isinstance(raw, dt.datetime):
            return raw.astimezone(dt.timezone.utc)
        try:
            return parse_time(raw)
        except Exception:
            return None

    while calls < max_calls and len(seen) < max_posts:
        calls += 1
        resp = fetch_page(cursor=cursor if mode == "cursor" else None,
                          end_time=cur_end if mode == "end_time" else None,
                          start_time=start_time if mode == "end_time" else None) or {}
        batch = resp.get("posts") or []
        nxt = resp.get("next_cursor") or resp.get("cursor")
        new_rows = []
        for p in batch:
            pid = post_id(p)
            if pid and pid not in seen:
                seen[pid] = p
                new_rows.append(p)
        oldest_all = None
        for p in seen.values():
            pt = post_time(p)
            if pt and (oldest_all is None or pt < oldest_all):
                oldest_all = pt
        if lo and oldest_all and oldest_all <= lo:
            stop_reason = "reached_start_time"
            break
        if len(seen) >= max_posts:
            stop_reason = "reached_max_posts"
            break

        if mode == "cursor":
            if batch and new_rows and nxt:
                cursor = nxt
                continue
            # Cursor pagination dried up early (empty page, missing cursor, or only duplicates):
            # switch to end_time date-window fallback if we have an anchor time to step backward from.
            anchor = next_end_time([post_time(p) for p in seen.values()]) or cur_end
            if not anchor:
                stop_reason = "empty_first_page"
                break
            mode = "end_time"
            used_fallback = True
            cur_end = anchor
            cursor = None
            continue

        # end_time window mode
        if new_rows:
            empty_windows = 0
            # Step just before the oldest newly seen post (or oldest overall)
            batch_times = [post_time(p) for p in new_rows if post_time(p)]
            step_to = next_end_time(batch_times) if batch_times else None
            if not step_to or (cur_end and step_to >= cur_end):
                # Advance by step_days to avoid spinning on an identical timestamp
                t_end = parse_time(cur_end) if cur_end else None
                if not t_end:
                    stop_reason = "no_timestamp"
                    break
                cur_end = iso(t_end - dt.timedelta(days=max(1, int(step_days))))
            else:
                cur_end = step_to
        else:
            empty_windows += 1
            if empty_windows >= empty_window_limit:
                stop_reason = "empty_windows"
                break
            t_end = parse_time(cur_end) if cur_end else None
            if not t_end:
                stop_reason = "no_timestamp"
                break
            nxt_end = t_end - dt.timedelta(days=max(1, int(step_days)))
            if lo and nxt_end < lo:
                stop_reason = "reached_start_time"
                break
            cur_end = iso(nxt_end)
    else:
        if calls >= max_calls:
            stop_reason = "reached_max_calls"

    ordered = sorted(seen.values(), key=lambda p: (post_time(p) is None, post_time(p) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
    return {"posts": ordered[:max_posts], "calls": calls, "used_end_time_fallback": used_fallback, "stop_reason": stop_reason}


def merge_csvs(out_path, paths):
    """Merge multiple window CSVs into one deduplicated posts.csv (newest first)."""
    seen = {}
    header = list(POST_COLUMNS)
    for p in paths:
        h, rows = read_csv(p)
        for col in h:
            if col not in header:
                header.append(col)
        for r in rows:
            pid = (r.get("post_id") or "").strip()
            if pid and pid not in seen:
                seen[pid] = r
    rows = sorted(seen.values(), key=lambda r: (r.get("published_at") or ""), reverse=True)
    write_csv(out_path, header, rows)
    return len(rows)


def main(argv):
    ap = argparse.ArgumentParser(description="Date-window fallback helper for get_users_posts pagination.")
    sub = ap.add_subparsers(dest="cmd")
    p_plan = sub.add_parser("plan", help="Generate newest-first end_time date windows")
    p_plan.add_argument("--from", dest="start", required=True)
    p_plan.add_argument("--to", dest="end", required=True)
    p_plan.add_argument("--step-days", type=int, default=14)
    p_next = sub.add_parser("next-end", help="Compute next end_time from a CSV or JSON file")
    p_next.add_argument("path")
    p_next.add_argument("--backoff-seconds", type=int, default=1)
    p_merge = sub.add_parser("merge", help="Merge deduplicated posts CSV pages")
    p_merge.add_argument("out")
    p_merge.add_argument("pages", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        print(json.dumps(plan_windows(a.start, a.end, a.step_days), indent=2))
        return 0
    if a.cmd == "next-end":
        if a.path.endswith(".json"):
            doc = json.load(open(a.path, encoding="utf-8"))
            items = doc if isinstance(doc, list) else (doc.get("posts") or doc.get("data") or [])
            ts = [x.get("published_at") or x.get("created_at") or x.get("at") for x in items if isinstance(x, dict)]
        else:
            _, rows = read_csv(a.path)
            ts = [r.get("published_at") for r in rows]
        ne = next_end_time(ts, a.backoff_seconds)
        if not ne:
            sys.stderr.write("no timestamps found in %s\n" % a.path)
            return 1
        print(ne)
        return 0
    if a.cmd == "merge":
        n = merge_csvs(a.out, a.pages)
        print("merged %d unique posts -> %s" % (n, a.out))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
