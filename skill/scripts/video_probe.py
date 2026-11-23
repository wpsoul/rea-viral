#!/usr/bin/env python3
"""Cut and measure a video so the agent can look at it: frames, cuts, the first seconds, the words.

    python3 video_probe.py <run folder> <post_id> [<post_id> ...] [--fetch] [--scene 0.3]
    python3 video_probe.py <run folder> --picks [--fetch]      # every post analyze.py picked for the deep read
    python3 video_probe.py <niche folder> --picks [--fetch]    # trends.py's picks, each cut in its creator's folder
    python3 video_probe.py <run folder> --picks --not-read "no network to download videos"
                    # no video can be had: marks each picked post read: false with that reason, in one go

Needs ffmpeg and ffprobe on PATH. --fetch also needs yt-dlp: it downloads the post's video (720p at most) and any
subtitles into videos/<post_id>/ first. Without --fetch the video is looked for in posts.csv video_file, then
videos/<post_id>/video.*.

Writes videos/<post_id>/:
  probe.json        MEASURED: length, fps, size, cut times (ffmpeg scene change), cuts per 10 s, first cut, average
                    shot, words and words per minute (from subtitles, when there are any), the words of the first 3 s,
                    the share of the sound that is not silence, loudness
  first/            12 frames of the first 3 seconds (every 0.25 s) and first.jpg, a contact sheet of them
  shots/            one frame just after each cut (at most 24) and shots.jpg, a contact sheet
  notes.json        the fixed list for the agent to fill after looking (hook, first frame, text on screen, sound,
                    the turn, the ask, beats); written once, never overwritten. A video that could not be had (the
                    downloader found none: "No video", a 403, a removed post) is marked read: false with why at once,
                    and the run goes on to the next pick; a later read of that video replaces only that mark

Only a post that carries its OWN video is cut (common.own_video, references/data-shape.md "own_media"): a text, thread
or article post goes to the words (text_probe.py) and gets no video folder; a picture post to its cover; a quote's or a
repost's video belongs to the other post and is never fetched for this one. A video or quote row that does not say whose
video it is (on X, Threads, LinkedIn without own_media) is marked read: false, "not read: the row does not say ...",
so the report says the video was not read instead of describing another post's video.

The script cuts and measures. It does not look: on-screen text, the hook and the turn are the agent's to write.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True  # imports leave no __pycache__ in the skill folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, load_posts, median, own_video, read_json, rnd, write_json  # noqa: E402

FIRST_SECONDS = 3.0
FIRST_STEP = 0.25
MAX_SHOTS = 24
TIMEOUT = 300


def need(tool):
    p = shutil.which(tool)
    if not p:
        die("%s is not on PATH. Install it (macOS: brew install ffmpeg; Windows: winget install ffmpeg; "
            "Linux: apt install ffmpeg), or read covers and captions only and say the videos were not read." % tool)
    return p


def sh(cmd, timeout=TIMEOUT):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ds" % timeout
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def ffprobe(path):
    code, out, err = sh(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path], 60)
    if code != 0:
        raise RuntimeError("ffprobe failed: " + err.strip()[-300:])
    d = json.loads(out)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    if v is None:
        raise RuntimeError("no video stream in " + path)
    num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else None
    dur = float(d.get("format", {}).get("duration") or v.get("duration") or 0)
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    return {"length_s": rnd(dur, 3), "fps": rnd(fps, 3), "width": w, "height": h, "has_audio": a is not None,
            "video_codec": v.get("codec_name"), "audio_codec": a.get("codec_name") if a else None}


def detect_cuts(path, threshold):
    code, _, err = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
                       "scale=320:-2,select='gt(scene,%s)',showinfo" % threshold, "-f", "null", "-"])
    if code != 0:
        raise RuntimeError("cut detection failed: " + err.strip()[-300:])
    times = [float(m.group(1)) for m in re.finditer(r"pts_time:([0-9.]+)", err)]
    # Two changes within 0.2 s are one cut (a flash or a fast transition).
    cuts = []
    for t in sorted(times):
        if not cuts or t - cuts[-1] > 0.2:
            cuts.append(round(t, 3))
    return cuts


def audio_numbers(path, length):
    out = {"non_silent_share": None, "loudness_lufs": None}
    code, _, err = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                       "silencedetect=n=-35dB:d=0.3,ebur128", "-f", "null", "-"])
    if code != 0:
        return out
    silent = 0.0
    for m in re.finditer(r"silence_duration: ([0-9.]+)", err):
        silent += float(m.group(1))
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start: ([0-9.\-]+)", err)]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end: ([0-9.]+)", err)]
    if len(starts) > len(ends) and length:
        silent += max(0.0, length - starts[-1])  # silence that runs to the end
    if length:
        out["non_silent_share"] = rnd(max(0.0, 1.0 - silent / length), 3)
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", err)
    if m:
        out["loudness_lufs"] = float(m[-1])
    return out


def grab(path, t, dest, width=540):
    code, _, err = sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % t, "-i", path,
                       "-frames:v", "1", "-vf", "scale=%d:-2" % width, "-q:v", "3", dest], 60)
    return code == 0 and os.path.exists(dest)


def sheet(pattern, count, cols, dest, labels=None):
    """A contact sheet from numbered frames. Labels (times) are drawn when this ffmpeg can draw text."""
    if count <= 0:
        return None
    rows = (count + cols - 1) // cols
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "1", "-start_number", "1", "-i", pattern]
    tile = "scale=270:-2,tile=%dx%d:padding=6:margin=6:color=0x111111" % (cols, rows)
    if labels:
        # The frame number n (1-based) maps to its label through a drawtext expression per frame is not possible
        # without a font file on every system, so the label is drawn from the file's own index: t = labels[n-1].
        lab = "drawtext=text='%{eif\\:n+1\\:d}':x=8:y=8:fontsize=22:fontcolor=white:box=1:boxcolor=0x000000AA"
        code, _, _ = sh(base + ["-vf", "scale=270:-2," + lab + "," + tile.split(",", 1)[1], "-frames:v", "1", dest], 120)
        if code == 0 and os.path.exists(dest):
            return dest
    code, _, _ = sh(base + ["-vf", tile, "-frames:v", "1", dest], 120)
    return dest if code == 0 and os.path.exists(dest) else None


# ---------------------------------------------------------------------------------------------- subtitles

TS = r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}"


def ts(s):
    s = s.replace(",", ".")
    parts = s.split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def parse_subs(path):
    """Words with times from a WebVTT or SRT file. Inline word times (YouTube's auto captions) are used when present;
    otherwise each cue's words are spread over the cue. Repeated rolling lines are dropped."""
    text = open(path, encoding="utf-8", errors="replace").read()
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, l in enumerate(lines):
            m = re.match(r"\s*(" + TS + r")\s*-->\s*(" + TS + r")", l)
            if m:
                cues.append((ts(m.group(1)), ts(m.group(3)), lines[i + 1:]))
                break
    words = []
    tagged = any("<c>" in "".join(c[2]) or re.search(r"<" + TS + r">", "".join(c[2])) for c in cues)
    last_line = None
    for start, end, lines in cues:
        if tagged:
            for l in lines:
                if not re.search(r"<" + TS + r">", l):
                    continue
                pieces = re.split(r"<(" + TS + r")>", l)
                # pieces: text0, ts1, (group), text1, ts2, (group), text2, ...
                t = start
                cur = pieces[0]
                seq = [(t, cur)]
                k = 1
                while k < len(pieces):
                    t = ts(pieces[k])
                    seq.append((t, pieces[k + 2] if k + 2 < len(pieces) else ""))
                    k += 3
                for j, (t0, chunk) in enumerate(seq):
                    clean = re.sub(r"<[^>]+>", "", chunk).strip()
                    t1 = seq[j + 1][0] if j + 1 < len(seq) else end
                    for w in clean.split():
                        words.append({"w": w, "start": round(t0, 3), "end": round(t1, 3)})
        else:
            body = " ".join(re.sub(r"<[^>]+>", "", l).strip() for l in lines).strip()
            if not body or body == last_line:
                continue
            last_line = body
            ws = body.split()
            step = (end - start) / max(1, len(ws))
            for j, w in enumerate(ws):
                words.append({"w": w, "start": round(start + j * step, 3), "end": round(start + (j + 1) * step, 3)})
    return words


def find_subs(folder, pid, post):
    cands = []
    if post and post.get("transcript_file"):
        cands.append(os.path.join(folder, post["transcript_file"]))
    vdir = os.path.join(folder, "videos", pid)
    cands += sorted(glob.glob(os.path.join(vdir, "*.vtt")) + glob.glob(os.path.join(vdir, "*.srt")))
    for c in cands:
        if os.path.exists(c) and c.lower().endswith((".vtt", ".srt")):
            # prefer English, then the first
            return c
    return None


# ---------------------------------------------------------------------------------------------- per video

def fetch(folder, pid, url):
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return None, "yt-dlp is not on PATH"
    vdir = os.path.join(folder, "videos", pid)
    os.makedirs(vdir, exist_ok=True)
    base = [ytdlp, "--no-update", "--no-playlist", "--no-progress", "--retries", "2", "--socket-timeout", "20",
            "-o", os.path.join(vdir, "video.%(ext)s")]
    # The video first, on its own: a failed subtitle request (HTTP 429 is common) must not cost the video.
    err = ""
    for fmt in ("bv*[height<=720]+ba/b[height<=720]/bv*+ba/b", "18/b"):  # 18 = a plain 360p MP4, when 720p gets a 403
        code, out, err = sh(base + ["-f", fmt, "--merge-output-format", "mp4", url], 600)
        vids = [p for p in glob.glob(os.path.join(vdir, "video.*")) if not p.endswith((".vtt", ".srt", ".part", ".json", ".ytdl"))]
        if vids:
            break
    if not vids:
        return None, "yt-dlp: " + (err.strip().splitlines() or ["failed"])[-1][:300]
    # Then the words, if there are any; a failure here only means the words were not read.
    sh(base + ["--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en,-live_chat",
               "--sub-format", "vtt", "--sleep-subtitles", "2", url], 300)
    time.sleep(2.0)  # polite between videos
    return vids[0], None


def find_video(folder, pid, post):
    if post and post.get("video_file"):
        p = os.path.join(folder, post["video_file"])
        if os.path.exists(p):
            return p
    vids = [p for p in glob.glob(os.path.join(folder, "videos", pid, "video.*"))
            if not p.endswith((".vtt", ".srt", ".part", ".json", ".ytdl"))]
    return vids[0] if vids else None


def probe_one(folder, pid, post, threshold, do_fetch):
    vdir = os.path.join(folder, "videos", pid)
    os.makedirs(vdir, exist_ok=True)
    video = find_video(folder, pid, post)
    why = None
    if video is None and do_fetch and post and post.get("url"):
        video, why = fetch(folder, pid, post["url"])
    res = {"schema": "rea-viral/probe@1", "post_id": pid, "url": (post or {}).get("url")}
    if video is None:
        res.update({"read": False, "not_read_reason": why or "no video file (run with --fetch, or save it as videos/%s/video.mp4)" % pid})
        write_json(os.path.join(vdir, "probe.json"), res)
        write_notes(vdir, pid, res)
        return res
    info = ffprobe(video)
    cuts = [c for c in detect_cuts(video, threshold) if 0.05 < c < (info["length_s"] or 1e9) - 0.05]
    length = info["length_s"] or 0.0
    shots = len(cuts) + 1
    m = dict(info)
    m.update({
        "cuts": cuts, "shots": shots,
        "cuts_per_10s": rnd(len(cuts) / length * 10.0, 2) if length else None,
        "first_cut_s": cuts[0] if cuts else None,
        "average_shot_s": rnd(length / shots, 2) if length else None,
        "scene_threshold": threshold,
    })
    m.update(audio_numbers(video, length) if info["has_audio"] else {"non_silent_share": 0.0, "loudness_lufs": None})
    subs = find_subs(folder, pid, post)
    if subs:
        words = parse_subs(subs)
        if words:
            span = max(0.5, words[-1]["end"] - words[0]["start"])
            m["words"] = len(words)
            m["words_per_minute"] = rnd(len(words) / (span / 60.0), 1)
            m["first_words_3s"] = " ".join(w["w"] for w in words if w["start"] < FIRST_SECONDS)
            m["first_word_at_s"] = words[0]["start"]
            m["transcript_file"] = os.path.relpath(subs, folder).replace(os.sep, "/")
            write_json(os.path.join(vdir, "words.json"), {"source": m["transcript_file"], "words": words})
    else:
        m["words"] = None
        m["words_per_minute"] = None
        m["transcript_note"] = "no subtitles found; the words were not read"
    files = {"video": os.path.relpath(video, folder).replace(os.sep, "/"), "first_seconds": [], "shots": []}
    fdir = os.path.join(vdir, "first")
    sdir = os.path.join(vdir, "shots")
    for d in (fdir, sdir):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    n = 0
    t = 0.0
    while t < min(FIRST_SECONDS, length) - 1e-6:
        n += 1
        dest = os.path.join(fdir, "f%02d.jpg" % n)
        if grab(video, t, dest):
            files["first_seconds"].append({"t": round(t, 2), "file": os.path.relpath(dest, folder).replace(os.sep, "/")})
        t += FIRST_STEP
    s_times = [0.0] + cuts
    if len(s_times) > MAX_SHOTS:
        step = len(s_times) / float(MAX_SHOTS)
        s_times = [s_times[int(i * step)] for i in range(MAX_SHOTS)]
    for i, t in enumerate(s_times):
        dest = os.path.join(sdir, "s%02d.jpg" % (i + 1))
        tt = min(t + 0.12, max(0.0, length - 0.05))
        if grab(video, tt, dest):
            files["shots"].append({"t": round(tt, 2), "cut_at": t, "file": os.path.relpath(dest, folder).replace(os.sep, "/")})
    a = sheet(os.path.join(fdir, "f%02d.jpg"), len(files["first_seconds"]), 4, os.path.join(vdir, "first.jpg"), True)
    b = sheet(os.path.join(sdir, "s%02d.jpg"), len(files["shots"]), 6, os.path.join(vdir, "shots.jpg"), True)
    files["sheet_first"] = os.path.relpath(a, folder).replace(os.sep, "/") if a else None
    files["sheet_shots"] = os.path.relpath(b, folder).replace(os.sep, "/") if b else None
    res.update({"read": True, "measured": m, "files": files,
                "how_to_read": "Sheets are numbered from 1 in time order; first.jpg tile n is at (n-1)*0.25 s, shots.jpg "
                               "tile n is files.shots[n-1].t."})
    write_json(os.path.join(vdir, "probe.json"), res)
    write_notes(vdir, pid, res)
    return res


AUTO = "video_probe.py"   # notes.json "not_read_by": a "not read" this script wrote, replaced when the video is read later


def write_notes(vdir, pid, probe):
    """The template to fill after looking. A video that could not be had (the downloader found none, "No video",
    a 403) is marked read false with why at once, so the run goes on; your own notes are never overwritten."""
    path = os.path.join(vdir, "notes.json")
    if os.path.exists(path):
        try:
            old = read_json(path)
        except ValueError:
            old = {}
        if not (old.get("read") is False and old.get("not_read_by") == AUTO and probe.get("read")):
            return
    if not probe.get("read"):
        write_json(path, {"post_id": pid, "read": False, "not_read_reason": probe.get("not_read_reason"),
                          "not_read_by": AUTO, "seen": {}, "beats": []})
        return
    m = probe.get("measured") or {}
    notes = {
        "post_id": pid,
        "read": None,
        "not_read_reason": None,
        "measured": {k: m.get(k) for k in ("length_s", "cuts_per_10s", "first_cut_s", "average_shot_s",
                                           "words_per_minute", "first_words_3s", "non_silent_share")},
        "seen": {
            "hook": {"text": "", "at": 0.0},
            "first_frame": "",
            "text_on_screen": "",
            "sound": "",
            "turn": {"text": "", "at": None},
            "ask": {"text": "", "at": None},
        },
        "beats": [],
        "cover": "",
        "_fill": "After looking at first.jpg, shots.jpg and the words: set read to true and fill every seen field "
                 "(\"none\" when there is none). beats: [{\"at\": seconds, \"what\": \"hook|setup|turn|proof|ask|...\", "
                 "\"text\": \"...\"}]. If the video could not be read: read false and not_read_reason.",
    }
    write_json(path, notes)


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 2
    if os.path.exists(os.path.join(argv[1], "niche.json")):
        return niche_main(argv)
    folder = argv[1]
    need("ffmpeg")
    need("ffprobe")
    threshold = 0.3
    if "--scene" in argv:
        threshold = float(argv[argv.index("--scene") + 1])
    do_fetch = "--fetch" in argv
    not_read = argv[argv.index("--not-read") + 1] if "--not-read" in argv else None
    posts = dict((p["post_id"], p) for p in load_posts(folder))
    try:
        network = read_json(os.path.join(folder, "account.json")).get("network")
    except (OSError, ValueError):
        network = None
    ids = []
    if "--picks" in argv:
        ap = os.path.join(folder, "analysis.json")
        if not os.path.exists(ap):
            die("no analysis.json: run analyze.py first")
        dr = read_json(ap).get("deep_read") or {}
        for k in ("outliers", "ordinary", "flops"):
            ids += [i for i in dr.get(k) or [] if i not in ids]
    skip = False
    for a in argv[2:]:
        if skip:
            skip = False
            continue
        if a in ("--scene", "--not-read"):
            skip = True
            continue
        if a.startswith("--"):
            continue
        if a not in ids:
            ids.append(a)
    if not ids:
        die("name the post ids, or --picks")
    bad = 0
    tried = 0
    for pid in ids:
        if pid not in posts:
            print("%s: not in posts.csv, skipped" % pid)
            bad += 1
            continue
        own = own_video(posts[pid], network)
        kind = posts[pid].get("type") or "other"
        if own is False:
            # Not a video of its own: its words or its pictures are read elsewhere; nothing is fetched or cut.
            print("%s: %s %s post with no video of its own, not cut (%s)" % (
                pid, "an" if kind[:1] in "aeiou" else "a", kind, "its words: text_probe.py" if kind in ("text", "thread", "article", "quote") else "its cover: covers_sheet.py"))
            continue
        if own is None:
            why = ("not read: the row does not say whether the video is this post's own (own_media); a quoted or "
                   "reposted post's video is not this post's, so none was fetched")
            mark_not_read(folder, pid, posts[pid], why)
            print("%s: %s" % (pid, why))
            continue
        tried += 1
        if not_read:
            vdir = os.path.join(folder, "videos", pid)
            os.makedirs(vdir, exist_ok=True)
            res = {"schema": "rea-viral/probe@1", "post_id": pid, "url": posts[pid].get("url"), "read": False,
                   "not_read_reason": not_read}
            write_json(os.path.join(vdir, "probe.json"), res)
            npath = os.path.join(vdir, "notes.json")
            n = read_json(npath) if os.path.exists(npath) else None
            if n is None or n.get("read") is None:
                write_json(npath, {"post_id": pid, "read": False, "not_read_reason": not_read, "seen": {}, "beats": []})
            print("%s: marked not read (%s)" % (pid, not_read))
            continue
        try:
            r = probe_one(folder, pid, posts[pid], threshold, do_fetch)
        except RuntimeError as e:
            print("%s: not read: %s" % (pid, e))
            bad += 1
            continue
        if r.get("read"):
            m = r["measured"]
            print("%s: %.1f s, %d cuts (%.1f per 10 s), first cut %s, words/min %s -> videos/%s/" % (
                pid, m["length_s"] or 0, len(m["cuts"]), m["cuts_per_10s"] or 0,
                m["first_cut_s"] if m["first_cut_s"] is not None else "none", m.get("words_per_minute"), pid))
        else:
            print("%s: not read: %s" % (pid, r.get("not_read_reason")))
            bad += 1
    if not_read:
        return 0
    if not tried:
        print("no post among these carries a video of its own: nothing to cut (their words: text_probe.py)")
        return 0
    if bad >= tried:
        print("none of the videos could be read: each is marked not read with why (videos/<id>/notes.json). Go on "
              "with covers and captions (exit 1 only says so).")
    elif bad:
        print("%d of %d videos could not be read: marked not read with why; the run goes on" % (bad, tried))
    return 0 if bad < tried else 1


def mark_not_read(folder, pid, post, why):
    """A picked post whose video is not known to be its own: read false, with why (the report shows it)."""
    vdir = os.path.join(folder, "videos", pid)
    os.makedirs(vdir, exist_ok=True)
    write_json(os.path.join(vdir, "probe.json"), {"schema": "rea-viral/probe@1", "post_id": pid, "url": (post or {}).get("url"),
                                                  "read": False, "not_read_reason": why})
    npath = os.path.join(vdir, "notes.json")
    n = read_json(npath) if os.path.exists(npath) else None
    if n is None or n.get("read") is None or n.get("not_read_by") == AUTO:
        write_json(npath, {"post_id": pid, "read": False, "not_read_reason": why, "not_read_by": AUTO, "seen": {}, "beats": []})


def niche_main(argv):
    """A niche folder: each post is cut in its own creator's folder (accounts/<network>-<handle>/videos/<id>/).
    --picks takes trends.json's deep_read: the top trends (at most 2 per creator), ordinary posts and flops."""
    folder = argv[1]
    tp = os.path.join(folder, "trends.json")
    if not os.path.exists(tp):
        die("no trends.json: run trends.py first")
    tr = read_json(tp)
    creator = dict((p["post_id"], p["creator"]) for p in tr.get("posts") or [])
    ids = []
    if "--picks" in argv:
        dr = tr.get("deep_read") or {}
        for k in ("trends", "ordinary", "flops"):
            ids += [i for i in dr.get(k) or [] if i not in ids]
    flags, skip = [], False
    for i, a in enumerate(argv[2:]):
        if skip:
            skip = False
            continue
        if a in ("--scene", "--not-read"):
            flags += [a, argv[2 + i + 1]]
            skip = True
        elif a.startswith("--"):
            if a != "--picks":
                flags.append(a)
        elif a not in ids:
            ids.append(a)
    if not ids:
        die("name the post ids, or --picks")
    groups = {}
    for pid in ids:
        if pid not in creator:
            print("%s: not a post of this niche, skipped" % pid)
            continue
        groups.setdefault(creator[pid], []).append(pid)
    codes = []
    for c, pids in sorted(groups.items()):
        print("== %s" % c)
        codes.append(main([argv[0], os.path.join(folder, "accounts", c)] + pids + flags))
    return 0 if any(x == 0 for x in codes) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
