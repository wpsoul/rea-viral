# The remake: three levels

| Level | Ways | What the user gets |
|---|---|---|
| **Basic** | An HTML page rendered in the browser | The format as a plain page, rendered frame-exact to MP4; the page stays to change and render again |
| **Standard** | **GreenLight Motion** or **HyperFrames**, the user's pick | An editable video project built from the recipe, checked and rendered |
| **Advanced** | GreenLight Dash's Rebuild by Style | The reference post's style studied frame by frame and rebuilt for the user's product |

## When to ask

Once, after the hand-over, and only when a format worth making was found (Scale it or Underused, with beats from
watched videos). Name the format and show its recipe: "Try to make <format> as a video? Basic (an HTML page rendered
to MP4), Standard (an editable video: GreenLight Motion or HyperFrames, your pick), or Advanced (GreenLight Dash's
Rebuild by Style)." It shares one message with the other offers of the run (SKILL.md, "The offer"), so the user
answers once. An unattended run never asks: it leaves the recipe and stops.

**It remakes the format with the user's content**: their clips, product, words and voice. Never the creator's
footage, face, mascot, voice or words. The recipe's "what not to copy" is binding. The result is a template the user
fills again and again.

All three start from the same recipe (`formats/<id>.md`), and every result is checked the same way:

```
python3 SKILL_DIR/scripts/remake_check.py <remake.mp4> <run>/formats/<id>.md
```

It measures the remake's length, cuts per 10 s and the time of every beat marked `"cut": true`, against the recipe's
tolerance (and words per minute with `--words words.json`). Then look at its frames:
`video_probe.py` works on any file you place as `videos/<name>/video.mp4`.

## Basic: an HTML page, rendered in the browser

The format as a plain HTML page; a script plays it in a headless browser frame by frame on a clock it controls and
saves the frames; ffmpeg only joins them and lays the sound. The page stays, so the user or you can change it and
render again.

1. Copy `SKILL_DIR/templates/basic-format.html` into `<run>/remake/` with the user's files beside it.
2. Edit only its two JSON blocks: `rea-render` (size, fps, duration, sound) and `timeline` (scenes from the recipe's
   beats: a scene ends where the next starts, which is a hard cut; chips, a product card, captions, the user's
   footage as `media`). Replace the stand-in character with the user's own footage or product.
3. Render: `node SKILL_DIR/scripts/render_page.mjs <run>/remake/basic-format.html --out <run>/remake/remake.mp4`
4. Check the pacing (above) and look at the frames.

**The page contract** (for a page you write yourself):

- `<script type="application/json" id="rea-render">{"width":1080,"height":1920,"fps":30,"duration":9,
  "audio":[{"src":"beat.wav","at":0,"in":0,"gain_db":0}]}</script>`
- Animate with CSS animations or transitions, the Web Animations API, or `requestAnimationFrame` code that reads its
  time from the callback or `performance.now()`. All of them follow the render clock. `setTimeout` does not: never
  time animation with it.
- Optional `window.reaSeek = (seconds) => { … }`: draw the page at that time (canvas, WebGL). It may return a promise.
- Video clips: `<video src="clip.mp4" data-start="2.5" data-in="0" data-sound="on" data-volume="1" muted>`: shown
  from 2.5 s on the page's timeline, from 0 s into the file; sought to the exact frame for every frame; its sound is
  laid at 2.5 s. MP4 (H.264) needs Google Chrome or Edge, which the script uses when found; Playwright's own Chromium
  plays WebM (VP9).
- Frame N shows the page at time N / fps exactly (tested: a page's CSS animation, delayed animation, rAF drawing and
  a video clip all land on the right frame on all 120 frames of the test).

**Needs:** Node 18+, ffmpeg, Playwright and a Chromium browser. When Playwright is missing, install it once outside any
project: `npm install --prefix ~/.cache/rea-viral playwright-core@1.49.1` (the script looks there), and use Google
Chrome or Edge. A Basic result says in one line what Standard adds: options the user can change on a page, an editor
file, the engine's effects and transitions.

## Standard: two ways, the user's pick

Both give an editable video project built from the same recipe, checked the same way (`remake_check.py`). Offer both
in one line and let the user pick; when they do not care, use the one you can run here.

| | GreenLight Motion | HyperFrames |
|---|---|---|
| What it is | The GreenLight Dash Video Editor's own engine | An open framework that renders HTML to video, with its own agent skills and command line |
| What the user keeps | A page with a preview, options to change and a Render button; a file that opens in GreenLight Dash | A folder of HTML scenes they or an agent keep editing, with HyperFrames' own preview and desktop app |
| What you need | Its chat connector, or `npx greenlight-motion` in a terminal | The HyperFrames agent skills (`hyperframes`, `hyperframes-cli`) and `npx hyperframes` (Node 22+, ffmpeg) |

### Standard, way 1: GreenLight Motion

An editable video built from the recipe in GreenLight Motion, the GreenLight Dash Video Editor's own engine. The user
gets a page with a preview, options to change and a Render button; the project also opens in GreenLight Dash. Nothing
to buy, no sign-in.

- **In a chat app** with the GreenLight Motion connector: read its `get_motion_guide`, write the scene script below,
  `build_video`, then `look_at_video` and fix, then `render_video` for the MP4 (or `share_video` for a link).
- **In a terminal:** `npx greenlight-motion@0.4.0 doctor`, write `<run>/remake-standard/script.json`, then
  `npx greenlight-motion@0.4.0 script <dir>`, `check <dir>` (fix all it lists), `stills <dir>` (look at the contact
  sheet), `render <dir> --out <dir>/remake.mp4`. `pack <dir> --glvideo` writes one file that opens in GreenLight Dash.
  The engine's own guide is its `skill/SKILL.md` and `skill/references/scene-script.md` (in the npm package
  `greenlight-motion`); follow it for everything not listed here.

**From recipe to scene script** (tried end to end on a real recipe: `check` clean, render, pacing check passed):

| Recipe | Scene script |
|---|---|
| The network's frame (Shorts, Reels, TikTok) | `"format": "9:16"` |
| `length_s` | The sum of the scenes' `duration` |
| A beat with `"cut": true` | A new scene with `"transition": "None"`. Every element on screen at the cut gets `"start": 0` and `"enter": "none"`: elements stagger in by default, and `check` reports the frame after the cut as blank |
| Word-bank chips or word-by-word captions | A `pill` and a `text` at the same `at`, `start` = the word's time in the scene, `"enter": "pop-overshoot"` |
| The user's clip / picture | `{"type": "video", "src": "asset:clip.mp4", "startAt": 0, "volume": 100}` / `{"type": "image", "src": "asset:photo.png"}` (files in `<dir>/assets/`) |
| A headline or the punch line | `text` with `role` (`headline`, `subhead`, `body`) and a `textAnimation` |
| The product's own interface as the caption | `rect` with `border` and `radius`, `text` on it; a picked state as a second `rect` with `start` |
| A static camera (most short formats) | `"camera": "none"` |
| The sound | Script-level `"music": {"src": "asset:beat.wav"}`; `"sound": "none"` keeps library sounds out |
| Labels the user may change | `label` on the element (it becomes an option on the page) |

### Standard, way 2: HyperFrames

HyperFrames renders a project of HTML scenes to video by stepping a paused timeline frame by frame. It has its own
agent skills and its own command line; this skill carries none of its rules and only hands it the recipe.

**When you have its skills** (a skill named `hyperframes` is among yours):

1. Load it and follow it: it holds the render contract and the work loop (check, look at frames, preview, render).
   For a vertical format read its part on vertical clips too.
2. **The recipe is the brief.** The format is already chosen, so you do not invent storylines or a new look: the
   beats are the shots with their times, `length_s` is the length, the hook is on screen from the first frame, and
   the recipe's "what not to copy" binds. The user's own clips, pictures, words and sound fill it.
3. Start the project inside the run folder: `npx hyperframes init <run>/remake-hyperframes --skip-skills --resolution
   portrait`. Always `--skip-skills` (adding skills is the user's step, never yours); `portrait` is 1080 × 1920, the
   frame of Shorts, Reels and TikTok. The user's files go in the project's `assets/`.
4. Build it from the mapping below, run its check until it reports no error, look at a frame of every beat, and show
   the user the preview. Render when the user approves it or asked for the file (its `render` command, to
   `<run>/remake-hyperframes/remake.mp4`).
5. Check the pacing like every remake: `remake_check.py <run>/remake-hyperframes/remake.mp4 <run>/formats/<id>.md`.
   A remake that fails is fixed and rendered again before the user gets it.

| Recipe | HyperFrames project |
|---|---|
| The network's frame (Shorts, Reels, TikTok) | `--resolution portrait` (1080 × 1920), 30 fps |
| `length_s` | The root composition's length (`data-duration`) |
| A beat | A scene that starts at the beat's `at` and lasts until the next beat |
| A beat with `"cut": true` | The next scene starts on that exact frame with no transition |
| `hook_pattern` | Frame 0 already shows the hook (the first frame is also the cover) |
| `caption_style`, `words_per_minute` | The user's words as captions, timed to their voice; see its captions guide |
| `sound` | The user's music or voice as its own audio track |
| The user's clip or picture | A file in `assets/`, placed in the beat's scene |

**When you do not have its skills:** say so in one line ("HyperFrames works through its own agent skills, which are
not installed here; you can add them once with `npx hyperframes skills`") and offer GreenLight Motion or Basic in the
same message. Never install skills yourself, and never write a HyperFrames project without its skills: its render
rules live there.

## Advanced: GreenLight Dash, Rebuild by Style

The creator's video studied frame by frame (shots, camera, type, colour, transitions, sound), then a new video in that
style for the user's product, as an editable Video Editor project. It lives in the GreenLight Dash app (PRO) as the
workflow `rebuild-by-style`. This skill carries none of that workflow.

1. `python3 SKILL_DIR/scripts/check_app.py` (asks the app's board API once; never starts the app).
2. **Running:** say in two lines what it adds and how to start it: "GreenLight Dash can rebuild the style of
   <post> for your product as an editable project: AI Workflows ▸ Rebuild by Style (PRO). I wrote what to give it in
   remake/advanced-brief.md." Write that file: the reference post's link and saved video path, the recipe's beats,
   the user's product and words.
3. **Not running:** two lines: what it adds, and where to get it (https://greenlightdash.pro/). Offer Standard.

It never blocks the run, and the skill never starts the workflow itself: today it starts only from inside the app.
