#!/usr/bin/env python3
"""Scout and Watch: note the follower counts of a watchlist on a schedule, and catch the jump when it happens.

Plain Python, no model, no provider built in. Counts come through a reader the agent sets up once (watch/config.json):
  {"type": "command", "command": ["python3", "my_reader.py", "{network}", "{handle}"]}
      a program that prints one JSON object: {"followers": 12345, "exact": true, "posts_count": 321,
      "profile": {"bio": "...", "link": "..."}, "recent_posts": [{"post_id", "url", "published_at", "views"}],
      "cost_usd": 0.001}. Only "followers" is required. A failure or bad JSON is a missed read, never a guess.
  {"type": "file", "path": "watch/inbox.csv"}
      another job (for example the agent's own scheduled run, using its data connector) appends rows
      read_at,network,handle,followers,exact,posts_count,source to that file; each run takes the new rows in.

Commands (DIR is the folder that holds watch/):
  watch.py init DIR (--reader-command "python3 r.py {network} {handle}" | --reader-file watch/inbox.csv)
  watch.py add DIR NETWORK HANDLE [--source user|scout] [--note TEXT]
  watch.py add DIR --from <niche run>/watchlist.csv      (every creator on a niche's watchlist, as Scout candidates)
  watch.py run DIR [--now ISO] [--all]     read the accounts that are due, apply the jump rule, write alerts
  watch.py status DIR                      every account: last count, usual daily gain, next read
  watch.py prune DIR [--days 7] [--keep 0.1]   Scout: after 7 days of counts keep the top tenth by relative gain
  watch.py schedule DIR --print launchd|cron|schtasks|agent
  watch.py schedule DIR --install launchd|cron --yes [--dry-run]     only after the user said yes
  watch.py schedule DIR --remove launchd|cron --yes [--dry-run]

Files in DIR/watch/: config.json, watchlist.csv, counts.csv (read_at,network,handle,followers,exact,posts_count,
source,status,note; status ok | gap | error), state.json, profiles/<network>-<handle>.jsonl, jumps/<date>-<network>-
<handle>.md, alerts.jsonl.

The jump rule (numbers in config.json, to be tuned from the first weeks of real counts):
  the day's gain (now against the reading closest to 24 h before, 20 to 36 h old, scaled to 24 h) is at least
  `factor` (3) times the usual daily gain (the median rate of the last 14 days, the last day left out; 3 days of
  history needed), AND at least the usual gain plus `noise_k` (4) times the day-to-day wobble (1.4826 x the median
  absolute deviation of the daily rates), AND at least the floor: max(min_gain 50, min_share 0.1% of followers, 2x
  the rounding of a rounded count). One alert per account per 24 h unless the gain grows by half again.
The pace: every `quiet_hours` (24); every `hot_hours` (4) for 24 h after a jump, or while a post under 48 h old runs
at 3x the median of the reader's other recent posts. A read missed by more than 1.5x its pace writes a gap row.
Exit codes of run: 0 = read, no jump; 10 = at least one jump (the alert files are written); 1 = every read failed.
"""
import csv
import datetime as dt
import json
import math
import os
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    ShapeError, iso, median, norm_handle, now_utc, parse_bool, parse_count, parse_time, read_csv, read_json, rnd,
    write_json, write_text,
)

COUNT_HEADER = ["read_at", "network", "handle", "followers", "exact", "posts_count", "source", "status", "note"]
LIST_HEADER = ["network", "handle", "added_at", "status", "source", "note"]
DEFAULT_CONFIG = {
    "schema": "rea-viral/watch-config@1",
    "reader": None,
    "jump": {"factor": 3.0, "noise_k": 4.0, "min_gain": 50, "min_share": 0.001, "min_days": 3, "lookback_days": 14},
    "cadence": {"quiet_hours": 24, "hot_hours": 4, "hot_post_ratio": 3.0, "gap_factor": 1.5},
    "notify": None,
    "on_jump": None,
}
LABEL = "com.rea-viral.watch"
MARK = "# rea-viral-watch"


def wdir(d):
    return os.path.join(d, "watch")


def load_config(d):
    p = os.path.join(wdir(d), "config.json")
    if not os.path.exists(p):
        die("no watch/config.json in %s: run watch.py init first" % d)
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(read_json(p))
    for k in ("jump", "cadence"):
        merged = dict(DEFAULT_CONFIG[k])
        merged.update(cfg.get(k) or {})
        cfg[k] = merged
    return cfg


def die(msg, code=2):
    sys.stderr.write("watch: " + msg + "\n")
    sys.exit(code)


def append_csv(path, header, rows):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in header})


def key(network, handle):
    return "%s:%s" % (network, norm_handle(handle))


# ---------------------------------------------------------------------------------------------- counts

def load_counts(d):
    p = os.path.join(wdir(d), "counts.csv")
    out = {}
    if not os.path.exists(p):
        return out
    _, rows = read_csv(p)
    for r in rows:
        k = key(r.get("network"), r.get("handle"))
        try:
            t = parse_time(r.get("read_at"))
        except ShapeError:
            continue
        rec = {"at": t, "status": r.get("status") or "ok", "followers": None, "exact": None}
        if rec["status"] == "ok":
            try:
                rec["followers"] = parse_count(r.get("followers"))
                rec["exact"] = parse_bool(r.get("exact"))
            except ShapeError:
                continue
            if rec["followers"] is None:
                continue
        out.setdefault(k, []).append(rec)
    for k in out:
        out[k].sort(key=lambda r: r["at"])
    return out


def resolution(followers, exact):
    """The step of a rounded count: 12,300,000 shown as 12.3M moves in 100,000s."""
    if exact is not False or not followers:
        return 1
    digits = len(str(int(followers)))
    return 10 ** max(0, digits - 3)


def judge(readings, cfg, now_reading):
    """Apply the jump rule to the newest reading. Returns a dict with the numbers and 'jump': bool."""
    J = cfg["jump"]
    ok = [r for r in readings if r["status"] == "ok"]
    res = {"jump": False, "gain_day": None, "usual_daily": None, "floor": None, "learning": False}
    if not ok:
        return res
    t = now_reading["at"]
    prev = [r for r in ok if dt.timedelta(hours=20) <= t - r["at"] <= dt.timedelta(hours=36)]
    if not prev:
        res["learning"] = True
        res["why"] = "no reading 20 to 36 hours before this one"
        return res
    p = min(prev, key=lambda r: abs((t - r["at"]).total_seconds() - 86400))
    hours = (t - p["at"]).total_seconds() / 3600.0
    gain_day = (now_reading["followers"] - p["followers"]) * 24.0 / hours
    res["gain_day"] = rnd(gain_day, 1)
    hist = [r for r in ok if t - dt.timedelta(days=J["lookback_days"]) <= r["at"] <= p["at"]]
    if not hist or (p["at"] - hist[0]["at"]) < dt.timedelta(days=J["min_days"]):
        res["learning"] = True
        res["why"] = "fewer than %d days of counts before the last day" % J["min_days"]
        return res
    rates = []
    for a, b in zip(hist, hist[1:]):
        h = (b["at"] - a["at"]).total_seconds() / 3600.0
        if 3 <= h <= 48:
            rates.append((b["followers"] - a["followers"]) * 24.0 / h)
    usual = median(rates)
    if usual is None:
        res["learning"] = True
        res["why"] = "no usable intervals (3 to 48 h) in the history"
        return res
    res["usual_daily"] = rnd(usual, 1)
    # The day-to-day wobble: 1.4826 x the median absolute deviation is a standard deviation that one odd day does
    # not inflate. A small account that swings +-60 a day around +5 must not fire on a +65 day.
    spread = 1.4826 * (median([abs(r - usual) for r in rates]) or 0.0)
    res["noise_daily"] = rnd(spread, 1)
    f = now_reading["followers"]
    floor = max(J["min_gain"], J["min_share"] * f, 2 * resolution(f, now_reading.get("exact")))
    res["floor"] = rnd(float(floor), 1)
    threshold = max(J["factor"] * max(usual, 0.0), usual + J["noise_k"] * spread, floor)
    res["threshold"] = rnd(threshold, 1)
    res["jump"] = gain_day >= threshold
    return res


# ---------------------------------------------------------------------------------------------- readers

def read_one(d, cfg, network, handle, now):
    r = cfg.get("reader") or {}
    if r.get("type") != "command":
        return None, "not a command reader"
    cmd = [str(x).replace("{network}", network).replace("{handle}", handle).replace("{dir}", d) for x in r.get("command") or []]
    if not cmd:
        return None, "reader.command is empty"
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=float(r.get("timeout_s") or 90), cwd=d)
    except subprocess.TimeoutExpired:
        return None, "the reader timed out"
    except OSError as e:
        return None, "the reader did not start: %s" % e
    if p.returncode != 0:
        return None, "the reader exited %d: %s" % (p.returncode, p.stderr.decode("utf-8", "replace").strip()[-200:])
    try:
        out = json.loads(p.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None, "the reader did not print one JSON object"
    f = out.get("followers")
    if not isinstance(f, int) or isinstance(f, bool) or f < 0:
        return None, "the reader's followers is not a whole number: %r" % (f,)
    return out, None


def take_inbox(d, cfg):
    """New rows from a file reader: everything after the line count taken last time."""
    r = cfg.get("reader") or {}
    path = os.path.join(d, r.get("path") or "watch/inbox.csv")
    if not os.path.exists(path):
        return []
    state = load_state(d)
    done = int(state.get("_inbox_rows") or 0)
    _, rows = read_csv(path)
    new = rows[done:]
    state["_inbox_rows"] = len(rows)
    save_state(d, state)
    return new


def load_state(d):
    p = os.path.join(wdir(d), "state.json")
    return read_json(p) if os.path.exists(p) else {}


def save_state(d, s):
    write_json(os.path.join(wdir(d), "state.json"), s)


def load_list(d):
    p = os.path.join(wdir(d), "watchlist.csv")
    if not os.path.exists(p):
        return []
    _, rows = read_csv(p)
    return rows


# ---------------------------------------------------------------------------------------------- run

def hot_post(out, cfg, now):
    posts = (out or {}).get("recent_posts") or []
    vals = []
    for p in posts:
        try:
            t = parse_time(p.get("published_at"))
            v = parse_count(str(p.get("views")) if p.get("views") is not None else "")
        except ShapeError:
            continue
        vals.append((t, v, p))
    fresh = [x for x in vals if x[0] and x[1] is not None and now - x[0] <= dt.timedelta(hours=48)]
    older = [x[1] for x in vals if x[1] is not None and x not in fresh]
    m = median(older)
    for t, v, p in fresh:
        if m and v >= cfg["cadence"]["hot_post_ratio"] * m:
            return p
    return None


def profile_change(d, network, handle, profile, now):
    if not profile:
        return None
    pdir = os.path.join(wdir(d), "profiles")
    os.makedirs(pdir, exist_ok=True)
    path = os.path.join(pdir, "%s-%s.jsonl" % (network, norm_handle(handle)))
    last = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        if lines:
            try:
                last = json.loads(lines[-1]).get("profile")
            except ValueError:
                last = None
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": iso(now), "profile": profile}, ensure_ascii=False) + "\n")
    if last is None:
        return None
    changed = dict((k, {"was": last.get(k), "now": profile.get(k)}) for k in set(last) | set(profile) if last.get(k) != profile.get(k))
    return changed or None


def write_jump(d, network, handle, reading, verdict, out, now, changes):
    jdir = os.path.join(wdir(d), "jumps")
    os.makedirs(jdir, exist_ok=True)
    path = os.path.join(jdir, "%s-%s-%s.md" % (now.strftime("%Y-%m-%d"), network, norm_handle(handle)))
    posts = []
    for p in (out or {}).get("recent_posts") or []:
        try:
            t = parse_time(p.get("published_at"))
        except ShapeError:
            t = None
        posts.append((t, p))
    recent = [(t, p) for t, p in posts if t and now - t <= dt.timedelta(hours=72)]
    others = [p.get("views") for t, p in posts if (t is None or now - t > dt.timedelta(hours=72)) and isinstance(p.get("views"), int)]
    base = median(others)
    L = ["# Jump: @%s on %s" % (norm_handle(handle), network), "",
         "- When: %s (MEASURED by watch.py)" % iso(reading["at"]),
         "- Followers now: %d%s" % (reading["followers"], "" if reading.get("exact") is not False else " (rounded by the network)"),
         "- The day's gain: %s, against a usual %s a day (factor %.1f, floor %s)" % (
             verdict["gain_day"], verdict["usual_daily"], verdict["gain_day"] / max(1.0, verdict["usual_daily"] or 1.0),
             verdict["floor"]),
         ""]
    L.append("## Posts of the last 72 hours")
    L.append("")
    if not out or "recent_posts" not in out:
        L.append("The reader returned no posts: read them with the data tool, then score them (analyze.py) before naming a cause.")
    elif not recent:
        L.append("Nothing was posted in the 72 hours before the jump. Look at the other actions: a collaboration, a mention, "
                 "an ad in the ad libraries, a bio or link change (below).")
    else:
        L.append("| Post | Published | Views | Against the median of the reader's older posts |")
        L.append("|---|---|---|---|")
        for t, p in sorted(recent, key=lambda x: x[0]):
            v = p.get("views")
            L.append("| [%s](%s) | %s | %s | %s |" % (p.get("post_id"), p.get("url") or "", iso(t), v if v is not None else "?",
                                                     ("%.1fx" % (v / float(base))) if (isinstance(v, int) and base) else "?"))
    L.append("")
    if changes:
        L.append("## Profile changes since the last read (SEEN)")
        L.append("")
        for k, c in sorted(changes.items()):
            L.append("- %s: %r → %r" % (k, c["was"], c["now"]))
        L.append("")
    L.append("## Next (for the agent)")
    L.append("")
    L.append("Name the cause at the Measured level: the post or posts whose timing and views fit the gain. Deep-read that "
             "post (video_probe.py, then look; its comments), write its recipe, and draft a version for the user. "
             "This file is the alert; nothing here is a claim about why.")
    write_text(path, "\n".join(L) + "\n")
    return path


def run_cmd(template, values, d):
    if not template:
        return
    cmd = [str(x).format(**values) for x in template]
    try:
        subprocess.run(cmd, cwd=d, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def cmd_run(d, now, read_all):
    cfg = load_config(d)
    lst = [r for r in load_list(d) if (r.get("status") or "active") in ("active", "candidate")]
    state = load_state(d)
    counts = load_counts(d)
    C = cfg["cadence"]
    rows_out = []
    results = []
    jumps = []
    failures = 0
    attempts = 0
    rtype = (cfg.get("reader") or {}).get("type")
    incoming = {}
    if rtype == "file":
        for r in take_inbox(d, cfg):
            k = key(r.get("network"), r.get("handle"))
            try:
                t = parse_time(r.get("read_at"))
                f = parse_count(r.get("followers"))
                ex = parse_bool(r.get("exact"))
            except ShapeError as e:
                rows_out.append({"read_at": r.get("read_at") or iso(now), "network": r.get("network"), "handle": r.get("handle"),
                                 "status": "error", "note": "inbox row: %s" % e})
                continue
            if t is None or f is None:
                continue
            incoming.setdefault(k, []).append({"at": t, "followers": f, "exact": ex, "posts_count": r.get("posts_count"),
                                               "source": r.get("source") or "inbox"})
    elif rtype != "command":
        die('watch/config.json has no reader: {"type": "command", ...} or {"type": "file", ...}')
    for item in lst:
        net, h = item.get("network"), norm_handle(item.get("handle"))
        k = key(net, h)
        st = state.get(k) or {}
        hist = counts.get(k, [])
        cadence_h = C["hot_hours"] if (st.get("hot_until") and parse_time(st["hot_until"]) > now) else C["quiet_hours"]
        last_ok = [r for r in hist if r["status"] == "ok"]
        # A read missed by more than gap_factor x its pace: say so, once.
        if last_ok and (now - last_ok[-1]["at"]) > dt.timedelta(hours=C["gap_factor"] * cadence_h) and not (
                hist and hist[-1]["status"] == "gap" and hist[-1]["at"] > last_ok[-1]["at"]):
            if not (rtype == "file" and incoming.get(k)):
                gap = {"read_at": iso(now), "network": net, "handle": h, "status": "gap",
                       "note": "no reading since %s" % iso(last_ok[-1]["at"])}
                rows_out.append(gap)
                hist.append({"at": now, "status": "gap", "followers": None})
        new_readings = []
        if rtype == "file":
            new_readings = incoming.get(k, [])
        else:
            due = parse_time(st["next_read_at"]) if st.get("next_read_at") else None
            if not read_all and due and due > now:
                continue
            attempts += 1
            out, err = read_one(d, cfg, net, h, now)
            if err:
                failures += 1
                rows_out.append({"read_at": iso(now), "network": net, "handle": h, "status": "error", "note": err})
                st["next_read_at"] = iso(now + dt.timedelta(hours=min(cadence_h, C["hot_hours"])))
                state[k] = st
                results.append((k, "error: " + err))
                continue
            new_readings = [{"at": now, "followers": out["followers"], "exact": out.get("exact"), "posts_count": out.get("posts_count"),
                             "source": out.get("source") or "command", "out": out}]
        for nr in new_readings:
            if any(r["at"] == nr["at"] for r in hist if r["status"] == "ok"):
                continue
            rows_out.append({"read_at": iso(nr["at"]), "network": net, "handle": h, "followers": nr["followers"],
                             "exact": "" if nr["exact"] is None else ("true" if nr["exact"] else "false"),
                             "posts_count": nr.get("posts_count"), "source": nr.get("source"), "status": "ok"})
            rec = {"at": nr["at"], "status": "ok", "followers": nr["followers"], "exact": nr["exact"]}
            hist.append(rec)
            hist.sort(key=lambda r: r["at"])
            verdict = judge([r for r in hist if r["at"] < nr["at"]], cfg, rec)
            out = nr.get("out")
            changes = profile_change(d, net, h, (out or {}).get("profile"), nr["at"]) if out else None
            hot = hot_post(out, cfg, nr["at"]) if out else None
            fire = verdict["jump"]
            if fire and st.get("last_jump_at"):
                lj = parse_time(st["last_jump_at"])
                if nr["at"] - lj < dt.timedelta(hours=24) and verdict["gain_day"] < 1.5 * float(st.get("last_jump_gain") or 0):
                    fire = False
                    verdict["suppressed"] = "an alert for this account went out in the last 24 h"
            if fire:
                path = write_jump(d, net, h, rec, verdict, out, nr["at"], changes)
                st["last_jump_at"] = iso(nr["at"])
                st["last_jump_gain"] = verdict["gain_day"]
                st["hot_until"] = iso(nr["at"] + dt.timedelta(hours=24))
                alert = {"at": iso(nr["at"]), "network": net, "handle": h, "followers": nr["followers"],
                         "gain_day": verdict["gain_day"], "usual_daily": verdict["usual_daily"], "file": os.path.relpath(path, d)}
                with open(os.path.join(wdir(d), "alerts.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(alert) + "\n")
                jumps.append(alert)
                vals = {"file": path, "handle": h, "network": net, "gain": verdict["gain_day"], "dir": d}
                run_cmd((cfg.get("notify") or {}).get("command") if isinstance(cfg.get("notify"), dict) else None, vals, d)
                run_cmd(cfg.get("on_jump"), vals, d)
            elif hot is not None:
                st["hot_until"] = iso(nr["at"] + dt.timedelta(hours=24))
            hot_now = bool(st.get("hot_until") and parse_time(st["hot_until"]) > nr["at"])
            st["next_read_at"] = iso(nr["at"] + dt.timedelta(hours=C["hot_hours"] if hot_now else C["quiet_hours"]))
            st["last"] = {"at": iso(nr["at"]), "followers": nr["followers"], "verdict": verdict}
            results.append((k, "jump" if fire else ("learning" if verdict.get("learning") else "quiet")))
        state[k] = st
    if rows_out:
        append_csv(os.path.join(wdir(d), "counts.csv"), COUNT_HEADER, rows_out)
    save_state(d, state)
    for k, what in results:
        print("%-40s %s" % (k, what))
    for j in jumps:
        print("JUMP %s:%s +%s a day (usual %s) -> %s" % (j["network"], j["handle"], j["gain_day"], j["usual_daily"], j["file"]))
    if attempts and failures == attempts:
        return 1
    return 10 if jumps else 0


# ---------------------------------------------------------------------------------------------- other commands

def cmd_init(d, argv):
    os.makedirs(wdir(d), exist_ok=True)
    p = os.path.join(wdir(d), "config.json")
    cfg = read_json(p) if os.path.exists(p) else dict(DEFAULT_CONFIG)
    if "--reader-command" in argv:
        cfg["reader"] = {"type": "command", "command": shlex.split(argv[argv.index("--reader-command") + 1]), "timeout_s": 90}
    elif "--reader-file" in argv:
        cfg["reader"] = {"type": "file", "path": argv[argv.index("--reader-file") + 1]}
    if not cfg.get("reader"):
        die("say how counts are read: --reader-command \"...\" or --reader-file watch/inbox.csv")
    write_json(p, cfg)
    lp = os.path.join(wdir(d), "watchlist.csv")
    if not os.path.exists(lp):
        append_csv(lp, LIST_HEADER, [])
    print("watch set up in %s (reader: %s)" % (wdir(d), cfg["reader"]["type"]))
    return 0


def cmd_add(d, argv):
    if "--from" in argv:
        # A niche run's watchlist.csv: every creator on it, as a Scout candidate.
        src_file = argv[argv.index("--from") + 1]
        _, rows = read_csv(src_file)
        for r in rows:
            if r.get("network") and r.get("handle"):
                cmd_add(d, [r["network"], r["handle"], "--source", "scout", "--note", (r.get("why") or "")[:200]])
        return 0
    if len(argv) < 2:
        die("add DIR NETWORK HANDLE")
    net, h = argv[0], norm_handle(argv[1])
    src = argv[argv.index("--source") + 1] if "--source" in argv else "user"
    note = argv[argv.index("--note") + 1] if "--note" in argv else ""
    have = set(key(r.get("network"), r.get("handle")) for r in load_list(d))
    if key(net, h) in have:
        print("already watched: %s:%s" % (net, h))
        return 0
    append_csv(os.path.join(wdir(d), "watchlist.csv"), LIST_HEADER, [{
        "network": net, "handle": h, "added_at": iso(now_utc()), "status": "candidate" if src == "scout" else "active",
        "source": src, "note": note}])
    print("watching %s:%s (%s)" % (net, h, src))
    return 0


def cmd_status(d):
    cfg = load_config(d)
    counts = load_counts(d)
    state = load_state(d)
    print("%-36s %-10s %12s %10s %8s  %s" % ("account", "status", "followers", "usual/day", "gaps", "next read"))
    for r in load_list(d):
        k = key(r.get("network"), r.get("handle"))
        hist = counts.get(k, [])
        ok = [x for x in hist if x["status"] == "ok"]
        v = judge(ok[:-1], cfg, ok[-1]) if ok else {}
        print("%-36s %-10s %12s %10s %8d  %s" % (k, r.get("status"), ok[-1]["followers"] if ok else "-",
                                                 v.get("usual_daily") if v.get("usual_daily") is not None else "-",
                                                 sum(1 for x in hist if x["status"] == "gap"), (state.get(k) or {}).get("next_read_at") or "now"))
    return 0


def cmd_prune(d, argv, now):
    days = float(argv[argv.index("--days") + 1]) if "--days" in argv else 7.0
    keep = float(argv[argv.index("--keep") + 1]) if "--keep" in argv else 0.1
    counts = load_counts(d)
    rows = load_list(d)
    scored = []
    for r in rows:
        if r.get("status") != "candidate":
            continue
        ok = [x for x in counts.get(key(r.get("network"), r.get("handle")), []) if x["status"] == "ok"]
        if len(ok) < 2 or (ok[-1]["at"] - ok[0]["at"]) < dt.timedelta(days=days):
            continue
        first = [x for x in ok if x["at"] >= ok[-1]["at"] - dt.timedelta(days=days)][0]
        rel = (ok[-1]["followers"] - first["followers"]) / float(max(1, first["followers"]))
        scored.append((rel, r))
    if not scored:
        print("no candidate has %g days of counts yet" % days)
        return 0
    scored.sort(key=lambda x: -x[0])
    n_keep = max(1, int(math.ceil(keep * len(scored))))
    for i, (rel, r) in enumerate(scored):
        r["status"] = "active" if i < n_keep else "dropped"
        r["note"] = ((r.get("note") or "") + " | %s: %+.2f%% in %g days" % (iso(now)[:10], 100 * rel, days)).strip(" |")
    path = os.path.join(wdir(d), "watchlist.csv")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LIST_HEADER, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)
    for rel, r in scored:
        print("%-8s %s:%s %+.2f%%" % (r["status"], r["network"], r["handle"], 100 * rel))
    return 0


def schedule_texts(d):
    py = sys.executable or "python3"
    me = os.path.abspath(__file__)
    d = os.path.abspath(d)
    log = os.path.join(wdir(d), "schedule.log")
    plist_path = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LABEL)
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>%s</string>
  <key>ProgramArguments</key>
  <array><string>%s</string><string>%s</string><string>run</string><string>%s</string></array>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardOutPath</key><string>%s</string>
  <key>StandardErrorPath</key><string>%s</string>
</dict>
</plist>
""" % (LABEL, py, me, d, log, log)
    cron = "0 * * * * %s %s run %s >> %s 2>&1 %s %s" % (shlex.quote(py), shlex.quote(me), shlex.quote(d), shlex.quote(log), MARK, d)
    sch = 'schtasks /Create /SC HOURLY /TN "REA Viral Watch" /TR "\\"%s\\" \\"%s\\" run \\"%s\\"" /F' % (py, me, d)
    agent = ("Every 4 hours: read the follower count (and the last few posts with their dates and views) of each account in "
             "%s/watch/watchlist.csv whose status is active or candidate, with the data tool you have; append one row per account "
             "to %s/watch/inbox.csv as read_at,network,handle,followers,exact,posts_count,source; then run: python3 %s run %s. "
             "If it exits 10, read the newest file in watch/jumps/ and follow its Next section." % (d, d, me, d))
    return {"launchd": (plist_path, plist), "cron": cron, "schtasks": sch, "agent": agent,
            "remove": {"launchd": "launchctl bootout gui/%d/%s; rm %s" % (os.getuid() if hasattr(os, "getuid") else 0, LABEL, plist_path),
                       "cron": "crontab -l | grep -v '%s %s' | crontab -" % (MARK, d),
                       "schtasks": 'schtasks /Delete /TN "REA Viral Watch" /F'}}


def cmd_schedule(d, argv):
    T = schedule_texts(d)
    dry = "--dry-run" in argv
    if "--print" in argv:
        what = argv[argv.index("--print") + 1]
        if what == "launchd":
            print("# save as %s, then: launchctl bootstrap gui/$(id -u) %s" % T["launchd"])
            print(T["launchd"][1])
            print("# take it down: " + T["remove"]["launchd"])
        elif what == "cron":
            print("# add with: (crontab -l 2>/dev/null; echo '<the line>') | crontab -")
            print(T["cron"])
            print("# take it down: " + T["remove"]["cron"])
        elif what == "schtasks":
            print(T["schtasks"])
            print("REM take it down: " + T["remove"]["schtasks"])
        elif what == "agent":
            print(T["agent"])
        else:
            die("--print launchd|cron|schtasks|agent")
        return 0
    for verb in ("--install", "--remove"):
        if verb in argv:
            what = argv[argv.index(verb) + 1]
            if "--yes" not in argv:
                die("installing or removing a schedule changes the user's computer: ask the user, then add --yes")
            if what == "launchd":
                path, plist = T["launchd"]
                if verb == "--install":
                    cmds = [["launchctl", "bootstrap", "gui/%d" % os.getuid(), path]]
                    if dry:
                        print("would write %s and run %s" % (path, " ".join(cmds[0])))
                        return 0
                    write_text(path, plist)
                    for c in cmds:
                        subprocess.run(c, check=False)
                else:
                    if dry:
                        print("would run: " + T["remove"]["launchd"])
                        return 0
                    subprocess.run(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), LABEL)], check=False)
                    if os.path.exists(path):
                        os.remove(path)
            elif what == "cron":
                if not shutil.which("crontab"):
                    die("no crontab on this computer")
                cur = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
                lines = [l for l in cur.splitlines() if "%s %s" % (MARK, os.path.abspath(d)) not in l]
                if verb == "--install":
                    lines.append(T["cron"])
                new = "\n".join(lines) + "\n"
                if dry:
                    print("would set the crontab to:\n" + new)
                    return 0
                subprocess.run(["crontab", "-"], input=new.encode(), check=True)
            else:
                die("%s launchd|cron (Windows: --print schtasks and run it)" % verb)
            print("%s: %s" % ("installed" if verb == "--install" else "removed", what))
            return 0
    die("schedule DIR --print launchd|cron|schtasks|agent, or --install/--remove launchd|cron --yes")


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 2
    cmd, d = argv[1], argv[2]
    rest = argv[3:]
    now = parse_time(rest[rest.index("--now") + 1]) if "--now" in rest else now_utc()
    if cmd == "init":
        return cmd_init(d, rest)
    if cmd == "add":
        return cmd_add(d, rest)
    if cmd == "run":
        return cmd_run(d, now, "--all" in rest)
    if cmd == "status":
        return cmd_status(d)
    if cmd == "prune":
        return cmd_prune(d, rest, now)
    if cmd == "schedule":
        return cmd_schedule(d, rest)
    die("unknown command %r" % cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
