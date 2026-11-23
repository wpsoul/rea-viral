#!/usr/bin/env python3
"""Check a remake's pacing against its format recipe: length, cuts, beat times, words per minute.

    python3 remake_check.py <remake.mp4> <formats/<id>.md> [--words words.json] [--scene 0.3] [--json]

Reads the recipe's ```json rea-recipe block: length_s, cuts_per_10s, words_per_minute, beats (a beat with "cut": true
is a hard cut the remake must have within tolerance.cut_s), and tolerance {length_pct, cut_s, cuts_per_10s,
words_per_minute_pct}. Measures the remake with ffmpeg (the same cut detection as video_probe.py).
Prints each check with the number and the tolerance; exit 0 = all pass, 1 = a check failed, 2 = could not run.
What it does not check: whether the remake looks like the format. Look at its frames (video_probe.py on the file).
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, read_json  # noqa: E402
from video_probe import detect_cuts, ffprobe, need  # noqa: E402

RECIPE_RE = re.compile(r"```json rea-recipe\s*\n(.*?)\n```", re.S)


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 2
    need("ffmpeg")
    need("ffprobe")
    video, recipe_path = argv[1], argv[2]
    text = open(recipe_path, encoding="utf-8").read()
    m = RECIPE_RE.search(text)
    if not m:
        die("%s has no ```json rea-recipe block" % recipe_path)
    rec = json.loads(m.group(1))
    tol = {"length_pct": 10, "cut_s": 0.25, "cuts_per_10s": 1.0, "words_per_minute_pct": 15}
    tol.update(rec.get("tolerance") or {})
    threshold = float(argv[argv.index("--scene") + 1]) if "--scene" in argv else 0.3
    info = ffprobe(video)
    length = info["length_s"] or 0.0
    cuts = [c for c in detect_cuts(video, threshold) if 0.05 < c < length - 0.05]
    checks = []

    def add(name, ok, got, want, note=""):
        checks.append({"check": name, "pass": bool(ok), "got": got, "want": want, "note": note})

    if rec.get("length_s"):
        want = float(rec["length_s"])
        add("length", abs(length - want) <= want * tol["length_pct"] / 100.0, round(length, 2),
            "%.2f s +-%d%%" % (want, tol["length_pct"]))
    if rec.get("cuts_per_10s") is not None and length:
        got = len(cuts) / length * 10.0
        add("cuts per 10 s", abs(got - float(rec["cuts_per_10s"])) <= tol["cuts_per_10s"], round(got, 2),
            "%.2f +-%.1f" % (float(rec["cuts_per_10s"]), tol["cuts_per_10s"]))
    for b in rec.get("beats") or []:
        if not b.get("cut"):
            continue
        at = float(b["at"])
        near = min(cuts, key=lambda c: abs(c - at)) if cuts else None
        add("cut at %.2f s (%s)" % (at, b.get("what") or "beat"), near is not None and abs(near - at) <= tol["cut_s"],
            near, "%.2f s +-%.2f" % (at, tol["cut_s"]))
    notes = []
    if "--words" in argv and rec.get("words_per_minute") is None:
        # A recipe whose videos had no subtitles has no speech rate: nothing to check it against, never a 0.
        notes.append("words per minute not checked: the recipe has none (its videos had no subtitles)")
    if "--words" in argv and rec.get("words_per_minute"):
        words = read_json(argv[argv.index("--words") + 1]).get("words") or []
        if words:
            span = max(0.5, words[-1]["end"] - words[0]["start"])
            got = len(words) / (span / 60.0)
            want = float(rec["words_per_minute"])
            add("words per minute", abs(got - want) <= want * tol["words_per_minute_pct"] / 100.0, round(got, 1),
                "%.0f +-%d%%" % (want, tol["words_per_minute_pct"]))
    ok = all(c["pass"] for c in checks) and bool(checks)
    out = {"ok": ok, "video": video, "recipe": recipe_path, "measured": {"length_s": length, "cuts": cuts}, "checks": checks,
           "notes": notes}
    if "--json" in argv:
        print(json.dumps(out, indent=2))
    else:
        for c in checks:
            print("%s %-34s got %-8s want %s" % ("ok  " if c["pass"] else "FAIL", c["check"], c["got"], c["want"]))
        if not checks:
            print("FAIL nothing to check: the recipe has no length_s, cuts_per_10s or beats with \"cut\": true")
        print("measured cuts: %s" % ", ".join("%.2f" % c for c in cuts))
        for n in notes:
            print("note " + n)
        print("OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
