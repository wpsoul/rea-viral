#!/usr/bin/env python3
"""Give a made-up account run real, heavy pictures, so the one-file report is tested the way a real run fills it.

    python3 tests/add_pictures.py <account run folder>

Needs ffmpeg. Writes covers/<post_id>.jpg for EVERY post (noisy 1080 x 1920 JPEGs, a few hundred KB each, the way
covers saved from the networks weigh; four distinct pictures hard-linked, so 140 covers cost four files of disk), a
small cover (about 15 KB, under the page's cap even without ffmpeg) for the top outliers, and, for the deep-read picks
analyze.py makes, videos/<id>/first.jpg (a noisy frame sheet of the real sheet's size), probe.json and a filled
notes.json; and the account's own picture (covers/_profile.jpg, account.json picture_file). Sets posts.csv
cover_file. Run it before analyze.py; it prints what it wrote as JSON.
"""
import csv
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.join(os.path.dirname(HERE), "skill", "scripts")
sys.dont_write_bytecode = True


def ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + list(args),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed: " + r.stderr.decode("utf-8", "replace")[-400:])


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    run = os.path.abspath(argv[1])
    if not shutil.which("ffmpeg"):
        sys.stderr.write("add_pictures.py needs ffmpeg\n")
        return 2
    sys.path.insert(0, os.path.abspath(SK))
    import analyze  # noqa: E402  (the skill's own picks, so the sheets land on the posts the page draws)
    picks = analyze.run(run)["deep_read"]
    os.makedirs(os.path.join(run, "covers"), exist_ok=True)
    src = os.path.join(run, "covers", ".src")
    os.makedirs(src, exist_ok=True)
    looks = []
    for i, pattern in enumerate(("testsrc2", "rgbtestsrc", "smptehdbars", "testsrc")):
        p = os.path.join(src, "big%d.jpg" % i)
        ffmpeg("-f", "lavfi", "-i", "%s=s=1080x1920" % pattern, "-vf", "noise=alls=%d:allf=t" % (18 + 4 * i),
               "-frames:v", "1", "-q:v", "3", p)
        looks.append(p)
    small = os.path.join(src, "small.jpg")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=200x356", "-frames:v", "1", "-q:v", "4", small)
    path = os.path.join(run, "posts.csv")
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        header, rows = rd.fieldnames, list(rd)
    for k, r in enumerate(rows):
        dest = os.path.join(run, "covers", r["post_id"] + ".jpg")
        if os.path.exists(dest):
            os.remove(dest)
        os.link(small if r["post_id"] in picks["outliers"] else looks[k % len(looks)], dest)
        r["cover_file"] = "covers/%s.jpg" % r["post_id"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    # The account's own picture (account.json picture_file): it becomes the report's cover for a planner.
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=800x800", "-frames:v", "1", "-q:v", "3", os.path.join(run, "covers", "_profile.jpg"))
    ap = os.path.join(run, "account.json")
    with open(ap, encoding="utf-8") as f:
        acc = json.load(f)
    acc["picture_file"] = "covers/_profile.jpg"
    with open(ap, "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2)
    sheet = os.path.join(src, "sheet.jpg")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1110x1460", "-vf", "noise=alls=20:allf=t", "-frames:v", "1", "-q:v", "3", sheet)
    ids = picks["outliers"] + picks["ordinary"] + picks["flops"]
    for pid in ids:
        vdir = os.path.join(run, "videos", pid)
        os.makedirs(vdir, exist_ok=True)
        dest = os.path.join(vdir, "first.jpg")
        if os.path.exists(dest):
            os.remove(dest)
        os.link(sheet, dest)
        with open(os.path.join(vdir, "probe.json"), "w", encoding="utf-8") as f:
            json.dump({"schema": "rea-viral/probe@1", "post_id": pid, "read": True,
                       "measured": {"length_s": 24.0, "cuts_per_10s": 2.5, "first_cut_s": 1.2, "words_per_minute": 170},
                       "files": {"sheet_first": "videos/%s/first.jpg" % pid}}, f, indent=2)
        flop = pid in picks["flops"]
        with open(os.path.join(vdir, "notes.json"), "w", encoding="utf-8") as f:
            json.dump({"post_id": pid, "read": True, "not_read_reason": None,
                       "measured": {"length_s": 24.0, "cuts_per_10s": 2.5},
                       "seen": {"hook": {"text": "a slow wide shot, no words for 3 s" if flop else "the number on screen at once",
                                         "at": 0.0},
                                "first_frame": "a desk", "text_on_screen": "none" if flop else "a big number",
                                "sound": "voice", "turn": {"text": "none" if flop else "the first mistake named", "at": 2.0},
                                "ask": {"text": "none", "at": None}},
                       "beats": [], "cover": "a person at a desk"}, f, indent=2)
    print(json.dumps({"covers": len(rows), "distinct_cover_files": len(looks) + 1, "sheets": len(ids),
                      "big_cover_bytes": os.path.getsize(looks[0]), "sheet_bytes": os.path.getsize(sheet),
                      "small_cover_bytes": os.path.getsize(small)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
