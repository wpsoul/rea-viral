#!/usr/bin/env python3
"""Put every saved cover on one numbered sheet, so the agent can look at the whole account at once.

    python3 covers_sheet.py <run folder> [--cols 10] [--sort date|ratio]

Reads posts.csv (cover_file) and analysis.json when present (the ratio to baseline). On a niche folder: the window's
posts of every creator folder, with the ratio against each post's own creator from trends.json. Writes covers_sheet.jpg and
covers_sheet.json: tile n (1-based, left to right, top to bottom) is posts[n-1], with its id, date, views and ratio.
Needs ffmpeg. Posts without a saved cover get a grey tile and are listed as "not read" in the JSON: a cover that was
not saved is never described from its caption.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, iso, load_posts, read_json, write_json  # noqa: E402

TILE_W, TILE_H = 180, 320


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    if not shutil.which("ffmpeg"):
        die("ffmpeg is not on PATH")
    cols = int(argv[argv.index("--cols") + 1]) if "--cols" in argv else 10
    sort = argv[argv.index("--sort") + 1] if "--sort" in argv else "date"
    ratio = {}
    if os.path.exists(os.path.join(folder, "niche.json")):
        # A niche: every creator's posts on one sheet, each cover path taken from its creator folder, the ratio
        # against its own creator from trends.json. Only the window's posts: the rest only feed the usual.
        from common import niche_creator_dirs
        tp = os.path.join(folder, "trends.json")
        tr = read_json(tp) if os.path.exists(tp) else {}
        inw = set(p["post_id"] for p in tr.get("posts") or [] if p.get("in_window"))
        ratio = dict((p["post_id"], p.get("ratio") if p.get("ratio") is not None else p.get("ratio_so_far"))
                     for p in tr.get("posts") or [])
        posts = []
        for d in niche_creator_dirs(folder):
            for p in load_posts(os.path.join(folder, d)):
                if inw and p["post_id"] not in inw:
                    continue
                p["cover_file"] = (d + "/" + p["cover_file"]) if p["cover_file"] else ""
                p["account"] = d.split("/", 1)[1]
                posts.append(p)
    else:
        posts = load_posts(folder)
    ap = os.path.join(folder, "analysis.json")
    if not ratio and os.path.exists(ap):
        ratio = dict((p["post_id"], p["ratio"]) for p in read_json(ap).get("posts") or [])
    if sort == "ratio":
        posts.sort(key=lambda p: -(ratio.get(p["post_id"]) or 0))
    else:
        posts.sort(key=lambda p: (p["published_at"] is None, p["published_at"]))
    if not posts:
        die("no posts")
    tmp = tempfile.mkdtemp(prefix="rea-covers-")
    index = []
    try:
        for i, p in enumerate(posts):
            dest = os.path.join(tmp, "%04d.png" % (i + 1))
            src = os.path.join(folder, p["cover_file"]) if p["cover_file"] else None
            ok = False
            if src and os.path.exists(src):
                vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d," % (TILE_W, TILE_H, TILE_W, TILE_H) +
                      "drawtext=text='%d':x=6:y=6:fontsize=22:fontcolor=white:box=1:boxcolor=0x000000AA" % (i + 1))
                for filt in (vf, vf.split(",drawtext")[0]):
                    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-vf", filt,
                                        "-frames:v", "1", dest], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if r.returncode == 0 and os.path.exists(dest):
                        ok = True
                        break
            if not ok:
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "color=0x333333:s=%dx%d" % (TILE_W, TILE_H), "-frames:v", "1", dest])
            index.append({"tile": i + 1, "post_id": p["post_id"], "account": p.get("account"), "published_at": iso(p["published_at"]),
                          "views": p["views"], "ratio": ratio.get(p["post_id"]), "cover": "read" if ok else "not read",
                          "caption": (p["caption"] or "")[:120]})
        rows = (len(posts) + cols - 1) // cols
        out = os.path.join(folder, "covers_sheet.jpg")
        r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", "1", "-i",
                            os.path.join(tmp, "%04d.png"), "-vf", "tile=%dx%d:padding=4:margin=4:color=0x111111" % (cols, rows),
                            "-frames:v", "1", "-q:v", "3", out], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            die("ffmpeg could not tile the covers: " + r.stderr.decode("utf-8", "replace")[-300:], 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    write_json(os.path.join(folder, "covers_sheet.json"), {"sort": sort, "cols": cols, "tiles": index})
    print("covers_sheet.jpg: %d covers (%d not read), %d per row, sorted by %s" % (
        len(index), sum(1 for t in index if t["cover"] != "read"), cols, sort))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
