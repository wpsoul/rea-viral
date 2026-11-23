#!/usr/bin/env python3
"""Put every saved cover on numbered sheets, so the agent can look at the whole account at once.

    python3 covers_sheet.py <run folder> [--cols 10] [--per-sheet 50] [--sort date|ratio] [--fetch]

Reads posts.csv (cover_file, cover_url) and analysis.json when present (the ratio to baseline). On a niche folder: the
window's posts of every creator folder, with the ratio against each post's own creator from trends.json.

Writes covers_sheet.jpg, then covers_sheet-2.jpg, covers_sheet-3.jpg … (at most --per-sheet tiles each, 50 by
default: a sheet an agent can still read), and covers_sheet.json: tile n (1-based, counted across all sheets, the number
drawn on it) is tiles[n-1], with its sheet, post id, date, views and ratio. Every post gets a tile: a post whose
cover was not saved gets a grey tile and is listed "not read" (with why, when covers/not_read.json says), never
described from its caption. It prints "drew N of M on K sheets" and checks it: each sheet is compared with its tiles
and the run fails when a tile is missing from it.

Each tile is made in one size and one pixel format before the sheets are built, and each sheet is built from its own
few tiles: a covers folder that mixes JPEG, PNG and WebP (as X and Instagram give them) no longer restarts ffmpeg's
filter part-way, which left only the last tiles on one big sheet (0.4.0, a real run of several hundred covers).

--fetch first saves the covers that are missing from their cover_url (covers/<post_id>.<jpg|png|webp>), like a
browser (common.save_picture), and writes cover_file into posts.csv; a cover that answers 403, 429 or anything else is
kept in covers/not_read.json with that status and the run goes on. --fetch works without ffmpeg; the sheets need it.
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    NOT_READ_COVERS, die, iso, load_posts, note_cover_not_read, read_csv, read_json, save_picture, write_json,
)

TILE_W, TILE_H = 180, 320
PAD = 4
PER_SHEET = 50
BG = (0x11, 0x11, 0x11)


def ff(args, timeout=120):
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, b"", b"timed out"
    return r.returncode == 0, r.stdout, r.stderr


def make_tile(src, n, dest):
    """One tile: the cover cropped to 180 x 320, its number drawn when this ffmpeg can draw text, always RGB 24-bit
    (rgb24), so every tile of every sheet is the same kind of frame. Returns True when the cover was used."""
    base = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (TILE_W, TILE_H, TILE_W, TILE_H)
    label = "drawtext=text='%d':x=6:y=6:fontsize=22:fontcolor=white:box=1:boxcolor=0x000000AA" % n
    if src and os.path.exists(src):
        for vf in (base + "," + label + ",format=rgb24", base + ",format=rgb24"):
            ok, _, _ = ff(["-i", src, "-vf", vf, "-frames:v", "1", "-pix_fmt", "rgb24", dest], 60)
            if ok and os.path.exists(dest):
                return True
    for vf in (label + ",format=rgb24", "format=rgb24"):
        ok, _, _ = ff(["-f", "lavfi", "-i", "color=0x333333:s=%dx%d" % (TILE_W, TILE_H), "-vf", vf, "-frames:v", "1",
                       "-pix_fmt", "rgb24", dest], 60)
        if ok and os.path.exists(dest):
            return False
    die("ffmpeg could not make a tile", 1)


def build_sheet(tmp, first, count, cols, out):
    """A sheet from the tiles first .. first+count-1 (numbered files), with no more frames than it holds."""
    rows = (count + cols - 1) // cols
    ok, _, err = ff(["-framerate", "1", "-start_number", str(first), "-i", os.path.join(tmp, "%05d.png"),
                     "-frames:v", str(count), "-vf",
                     "tile=%dx%d:padding=%d:margin=%d:color=0x111111" % (cols, rows, PAD, PAD),
                     "-frames:v", "1", "-q:v", "3", out], 300)
    if not ok:
        die("ffmpeg could not tile the covers: " + err.decode("utf-8", "replace")[-300:], 1)
    return rows


def check_sheet(tmp, first, count, cols, rows, sheet):
    """How many of the sheet's tiles are really on it: each cell of the sheet against the tile meant for it."""
    # The tiles' own colours, in order (one frame each, read as a sequence starting at `first`).
    ok, out, _ = ff(["-framerate", "1", "-start_number", str(first), "-i", os.path.join(tmp, "%05d.png"),
                     "-frames:v", str(count), "-vf", "format=rgb24,scale=1:1:flags=area", "-f", "rawvideo",
                     "-pix_fmt", "rgb24", "pipe:1"])
    want = [tuple(out[i:i + 3]) for i in range(0, len(out) - 2, 3)] if ok else []
    # The sheet without its margin, cut into its cells by area (the 4 px gaps are a few % of a cell).
    w = cols * TILE_W + (cols - 1) * PAD
    h = rows * TILE_H + (rows - 1) * PAD
    ok, out, _ = ff(["-i", sheet, "-vf", "crop=%d:%d:%d:%d,format=rgb24,scale=%d:%d:flags=area" % (w, h, PAD, PAD, cols, rows),
                     "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
    got = [tuple(out[i:i + 3]) for i in range(0, len(out) - 2, 3)] if ok else []
    drawn = 0
    for k, c in enumerate(want):
        if k < len(got) and max(abs(a - b) for a, b in zip(c, got[k])) <= 28:
            drawn += 1
    return drawn


def fetch_missing(folder, dirs):
    """Save each missing cover from its cover_url (like a browser), set cover_file, and keep why a cover could not be
    read. Returns (saved, not_read, had)."""
    saved = failed = had = 0
    reasons = {}
    for d in dirs:
        cf = os.path.join(folder, d) if d else folder
        path = os.path.join(cf, "posts.csv")
        if not os.path.exists(path):
            continue
        header, rows = read_csv(path)
        if "cover_file" not in header:
            header.append("cover_file")
        changed = False
        for r in rows:
            pid, url = (r.get("post_id") or "").strip(), (r.get("cover_url") or "").strip()
            have = (r.get("cover_file") or "").strip()
            if have and os.path.exists(os.path.join(cf, have)):
                had += 1
                continue
            if not url:
                continue
            got, why = save_picture(url, os.path.join(cf, "covers", pid))
            if got:
                r["cover_file"] = os.path.relpath(got, cf).replace(os.sep, "/")
                note_cover_not_read(cf, pid, None)
                saved += 1
                changed = True
            else:
                note_cover_not_read(cf, pid, why)
                reasons[why] = reasons.get(why, 0) + 1
                failed += 1
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow(dict((k, r.get(k, "")) for k in header))
    return saved, failed, had, reasons


def not_read_reasons(folder):
    p = os.path.join(folder, NOT_READ_COVERS)
    try:
        return read_json(p) if os.path.exists(p) else {}
    except ValueError:
        return {}


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 else 2
    folder = argv[1]
    cols = int(argv[argv.index("--cols") + 1]) if "--cols" in argv else 10
    per = int(argv[argv.index("--per-sheet") + 1]) if "--per-sheet" in argv else PER_SHEET
    per = max(cols, per - per % cols)          # whole rows only
    sort = argv[argv.index("--sort") + 1] if "--sort" in argv else "date"
    niche = os.path.exists(os.path.join(folder, "niche.json"))
    ratio, why_not = {}, {}
    if niche:
        from common import niche_creator_dirs
        dirs = niche_creator_dirs(folder)
    else:
        dirs = [""]
    if "--fetch" in argv:
        saved, failed, had, reasons = fetch_missing(folder, dirs)
        print("covers: %d saved now, %d already saved, %d not read%s" % (
            saved, had, failed, (" (" + ", ".join("%s: %d" % kv for kv in sorted(reasons.items())) + ")") if reasons else ""))
    if not shutil.which("ffmpeg"):
        die("ffmpeg is not on PATH: the covers are saved (--fetch), the sheets need ffmpeg")
    if niche:
        # A niche: every creator's posts of the window on the sheets, each cover from its creator folder, the ratio
        # against its own creator from trends.json. Only the window's posts: the rest only feed the usual.
        tp = os.path.join(folder, "trends.json")
        tr = read_json(tp) if os.path.exists(tp) else {}
        inw = set(p["post_id"] for p in tr.get("posts") or [] if p.get("in_window"))
        ratio = dict((p["post_id"], p.get("ratio") if p.get("ratio") is not None else p.get("ratio_so_far"))
                     for p in tr.get("posts") or [])
        posts = []
        for d in dirs:
            reasons = not_read_reasons(os.path.join(folder, d))
            for p in load_posts(os.path.join(folder, d)):
                if inw and p["post_id"] not in inw:
                    continue
                p["cover_file"] = (d + "/" + p["cover_file"]) if p["cover_file"] else ""
                p["account"] = d.split("/", 1)[1]
                why_not[p["post_id"]] = reasons.get(p["post_id"])
                posts.append(p)
    else:
        posts = load_posts(folder)
        why_not = not_read_reasons(folder)
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
    index, sheets = [], []
    try:
        for i, p in enumerate(posts):
            src = os.path.join(folder, p["cover_file"]) if p["cover_file"] else None
            ok = make_tile(src, i + 1, os.path.join(tmp, "%05d.png" % (i + 1)))
            index.append({"tile": i + 1, "sheet": i // per + 1, "post_id": p["post_id"], "account": p.get("account"),
                          "published_at": iso(p["published_at"]), "views": p["views"], "ratio": ratio.get(p["post_id"]),
                          "cover": "read" if ok else "not read",
                          "why": None if ok else (why_not.get(p["post_id"]) or ("no cover saved" if not p["cover_file"] else "the file could not be read")),
                          "caption": (p["caption"] or "")[:120]})
        # Old sheets of an earlier, longer run would mislead: remove them first.
        for name in os.listdir(folder):
            if name.startswith("covers_sheet") and name.endswith(".jpg"):
                os.remove(os.path.join(folder, name))
        drawn = 0
        for k, first in enumerate(range(1, len(posts) + 1, per)):
            count = min(per, len(posts) - first + 1)
            name = "covers_sheet.jpg" if k == 0 else "covers_sheet-%d.jpg" % (k + 1)
            out = os.path.join(folder, name)
            rows = build_sheet(tmp, first, count, cols, out)
            got = check_sheet(tmp, first, count, cols, rows, out)
            drawn += got
            sheets.append({"file": name, "tiles": [first, first + count - 1], "drawn": got})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    write_json(os.path.join(folder, "covers_sheet.json"), {
        "sort": sort, "cols": cols, "per_sheet": per, "sheets": sheets, "drawn": drawn, "of": len(posts), "tiles": index})
    nr = sum(1 for t in index if t["cover"] != "read")
    print("covers_sheet: drew %d of %d on %d sheet%s (%s), %d per row, sorted by %s; %d covers not read" % (
        drawn, len(posts), len(sheets), "" if len(sheets) == 1 else "s", ", ".join(s["file"] for s in sheets), cols, sort, nr))
    if drawn < len(posts):
        print("NOT ALL TILES ARE ON THE SHEETS: %s" % "; ".join(
            "%s has %d of tiles %d-%d" % (s["file"], s["drawn"], s["tiles"][0], s["tiles"][1]) for s in sheets if s["drawn"] < s["tiles"][1] - s["tiles"][0] + 1))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
