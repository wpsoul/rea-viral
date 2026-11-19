#!/usr/bin/env python3
"""Prove the Basic remake renderer is frame-exact: frame N of the MP4 shows the page at time N/fps.

    python3 tests/test_render.py [--work DIR] [--browser chromium|chrome] [--clip webm|mp4]

Builds a 640x360, 30 fps, 4 s test page whose every layer encodes the frame it shows:
  - a 10-bit barcode drawn by requestAnimationFrame code from performance.now()   -> must read N
  - a bar moved by a CSS animation, 600 px over 4 s                               -> its left edge must be 5N px (+-1)
  - a square that a CSS animation with a 1.5 s delay turns on                      -> on exactly from frame 45
  - a video clip (its own frame index burned in as a barcode) placed at 1.0 s     -> must read clamp(N-30, 0, 59)
  - sound: the clip's 1 kHz tone from 1.0 to 3.0 s, a 440 Hz tone at 3.2 s        -> energy and pitch where expected
Renders it with skill/scripts/render_page.mjs, decodes every frame with ffmpeg and checks each one.
Fails loudly when anything cannot run (no ffmpeg, no node, no Playwright).
"""
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RENDER = os.path.join(REPO, "skill", "scripts", "render_page.mjs")
# Playwright: REA_PLAYWRIGHT (a playwright folder), else tests/node_modules (npm install --prefix tests), else the
# skill's own place for it (~/.cache/rea-viral, see skill/references/remake.md).
PLAYWRIGHT = next((p for p in (os.environ.get("REA_PLAYWRIGHT"), os.path.join(HERE, "node_modules", "playwright"),
                               os.path.join(os.path.expanduser("~"), ".cache", "rea-viral", "node_modules", "playwright-core"))
                   if p and os.path.isdir(p)), os.path.join(HERE, "node_modules", "playwright"))
W, H, FPS, DUR = 640, 360, 30, 4.0
CLIP_START, CLIP_FRAMES = 1.0, 60

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#000;width:640px;height:360px;overflow:hidden}
#bar{position:absolute;left:0;top:60px;width:10px;height:40px;background:#fff;animation:move 4s linear forwards}
@keyframes move{from{transform:translateX(0)}to{transform:translateX(600px)}}
#late{position:absolute;left:600px;top:120px;width:30px;height:30px;background:#fff;opacity:0;animation:on 0.01s steps(1,start) 1.5s forwards}
@keyframes on{from{opacity:0}to{opacity:1}}
#clip{position:absolute;left:0;top:200px;width:320px;height:32px}
canvas{position:absolute;left:0;top:0}
#label{position:absolute;left:340px;top:200px;color:#888;font:24px Arial,sans-serif}
</style></head><body>
<script type="application/json" id="rea-render">{"width":640,"height":360,"fps":30,"duration":4,
 "audio":[{"src":"tone440.wav","at":3.2,"gain_db":0}]}</script>
<canvas id="c" width="320" height="32"></canvas>
<div id="bar"></div><div id="late"></div>
<video id="clip" src="CLIP" data-start="1.0" data-in="0" muted playsinline preload="auto"></video>
<div id="label"></div>
<script>
const ctx = document.getElementById('c').getContext('2d');
function draw(){
  const n = Math.round(performance.now() / 1000 * 30);
  for (let i = 0; i < 10; i++){ ctx.fillStyle = (n >> i) & 1 ? '#fff' : '#000'; ctx.fillRect(i * 32, 0, 32, 32); }
  document.getElementById('label').textContent = 'frame ' + n;
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script></body></html>
"""


def sh(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    if r.returncode != 0:
        raise SystemExit("FAIL command failed: %s\n%s" % (" ".join(cmd), r.stderr.decode("utf-8", "replace")[-1500:]))
    return r.stdout


def make_media(work, clip_kind):
    geq = "geq=lum='if(bitand(floor(N/pow(2,floor(X/32))),1),235,16)':cb=128:cr=128"
    clip = os.path.join(work, "clip." + clip_kind)
    vcodec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "20", "-c:a", "libopus"] if clip_kind == "webm" else \
             ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", "-c:a", "aac"]
    sh(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=320x32:r=30:d=2,format=yuv420p," + geq,
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=2", "-shortest"] + vcodec + [clip])
    sh(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
        os.path.join(work, "tone440.wav")])
    with open(os.path.join(work, "page.html"), "w") as f:
        f.write(PAGE.replace("CLIP", os.path.basename(clip)))


def bits(row, x0, n_bits=10, step=32):
    v = 0
    for i in range(n_bits):
        if row[x0 + i * step + step // 2] > 128:
            v |= 1 << i
    return v


def main(argv):
    work = argv[argv.index("--work") + 1] if "--work" in argv else tempfile.mkdtemp(prefix="rea-render-")
    browser = argv[argv.index("--browser") + 1] if "--browser" in argv else "chromium"
    clip_kind = argv[argv.index("--clip") + 1] if "--clip" in argv else "webm"
    os.makedirs(work, exist_ok=True)
    for tool in ("ffmpeg", "ffprobe", "node"):
        if not shutil.which(tool):
            raise SystemExit("FAIL %s is not on PATH: this test cannot run" % tool)
    if not os.path.isdir(PLAYWRIGHT):
        raise SystemExit("FAIL no Playwright at %s: this test cannot run" % PLAYWRIGHT)
    make_media(work, clip_kind)
    out = os.path.join(work, "out.mp4")
    env = dict(os.environ, REA_PLAYWRIGHT=PLAYWRIGHT)
    res = sh(["node", RENDER, os.path.join(work, "page.html"), "--out", out, "--browser", browser], env=env, timeout=600)
    summary = json.loads(res.decode().strip().splitlines()[-1])
    print("rendered: %s" % json.dumps(summary))
    fails = []
    info = json.loads(sh(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", out]))
    vs = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    aus = [s for s in info["streams"] if s["codec_type"] == "audio"]
    nframes = int(vs["nb_read_frames"])
    if nframes != int(DUR * FPS):
        fails.append("frame count %d, expected %d" % (nframes, DUR * FPS))
    if vs["r_frame_rate"] != "30/1":
        fails.append("frame rate %s, expected 30/1" % vs["r_frame_rate"])
    if not aus:
        fails.append("no audio stream")
    raw = sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", out, "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    size = W * H
    got = len(raw) // size
    bad_js = bad_css = bad_late = bad_clip = 0
    examples = []
    for n in range(got):
        fr = raw[n * size:(n + 1) * size]
        row_js = fr[16 * W:17 * W]
        js = bits(row_js, 0)
        row_bar = fr[80 * W:81 * W]
        left = next((x for x in range(W) if row_bar[x] > 128), None)
        late = fr[135 * W + 615] > 128
        row_clip = fr[216 * W:217 * W]
        clip = bits(row_clip, 0)
        want_clip = min(max(n - int(CLIP_START * FPS), 0), CLIP_FRAMES - 1)
        if js != n:
            bad_js += 1
        if left is None or abs(left - 5 * n) > 1:
            bad_css += 1
        if late != (n >= 45):
            bad_late += 1
        if clip != want_clip:
            bad_clip += 1
        if (js != n or clip != want_clip or left is None or abs(left - 5 * n) > 1) and len(examples) < 6:
            examples.append("frame %d: js %d, bar %s (want %d), clip %d (want %d)" % (n, js, left, 5 * n, clip, want_clip))
    for name, bad in (("rAF barcode", bad_js), ("CSS bar", bad_css), ("CSS delayed square", bad_late), ("video clip frame", bad_clip)):
        if bad:
            fails.append("%s wrong on %d of %d frames" % (name, bad, got))
        else:
            print("ok   %s right on all %d frames" % (name, got))
    for e in examples:
        print("     " + e)
    # Sound: silence before the clip, the clip's 1 kHz tone, the 440 Hz tone after it.
    pcm = sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", out, "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
    samples = struct.unpack("<%dh" % (len(pcm) // 2), pcm)

    def window(a, b):
        return samples[int(a * 48000):int(b * 48000)]

    def rms(xs):
        return math.sqrt(sum(x * x for x in xs) / max(1, len(xs)))

    def pitch(xs):
        z = sum(1 for i in range(1, len(xs)) if (xs[i - 1] < 0) != (xs[i] < 0))
        return z / 2.0 / (len(xs) / 48000.0)

    quiet, clip_w, tone_w = window(0.1, 0.9), window(1.2, 2.8), window(3.25, 3.65)
    if rms(quiet) > 50:
        fails.append("sound before 1.0 s (rms %.0f)" % rms(quiet))
    for name, w, f0 in (("clip tone 1 kHz", clip_w, 1000), ("440 Hz tone", tone_w, 440)):
        p = pitch(w)
        if rms(w) < 500 or abs(p - f0) > 0.05 * f0:
            fails.append("%s: rms %.0f, pitch %.0f Hz" % (name, rms(w), p))
        else:
            print("ok   %s at the right time (rms %.0f, %.0f Hz)" % (name, rms(w), p))
    if rms(quiet) <= 50:
        print("ok   silence before the clip starts")
    print("work folder: %s" % work)
    if fails:
        for f in fails:
            print("FAIL " + f)
        print("NOT OK")
        return 1
    print("OK: %d frames, every layer frame-exact (browser %s, clip %s)" % (got, summary.get("browser"), clip_kind))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
