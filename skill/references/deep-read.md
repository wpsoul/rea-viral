# Watching the videos (the deep read)

The script cuts and measures; you look. Watch the `deep_read` picks of `analysis.json`: outliers, ordinary posts and
flops. If money or time is short, keep at least the top 3 outliers, 1 ordinary post and 1 flop. What the watched
flops show goes into the report's "What did not work" (the page draws their hook and turn from `notes.json`; your
reading goes in `findings.json` `did_not_work`, SEEN with the post ids): what was there, never on its own why the post
flopped.

- **A niche:** the top trends of `trends.json`, at most 2 per creator, plus 3 ordinary posts and 2 flops of
  different creators (`trends.json` `deep_read`). `video_probe.py <niche> --picks --fetch` cuts each in its creator's
  folder (`accounts/<network>-<handle>/videos/<id>/`). A format's beats must be seen at two creators or more.
- **A post:** the post itself, plus one or two of its creator's ordinary posts: `video_probe.py <run> <post_id> --fetch`.

## Only the post's own video

A post is cut only when the video is its own (`own_media: video`, `data-shape.md`). A text post, a thread or an
article goes to its words (`text_probe.py`); a picture or carousel post to its cover and slides; a quote's or a
repost's video belongs to the other post and is never fetched for this one (on a real X run a quote post was described
from the video it quoted). On X, Threads and LinkedIn a video or quote row without `own_media` is not fetched: it is
marked `read: false` with "the row does not say whether the video is this post's own", and the report says the video
was not read. On YouTube, TikTok and Instagram a post of type `video` is its own.

## Get the files

```
python3 SKILL_DIR/scripts/video_probe.py <run> --picks --fetch
```

`--fetch` downloads each video with `yt-dlp` (720p at most) into `videos/<id>/video.mp4`, then its subtitles, in a
separate request: a refused subtitle request (HTTP 429 is common) costs only the words, never the video. A refused
video (HTTP 403) is retried once in another format; a video the downloader cannot find ("No video", a removed post)
or still refuses is marked `read: false` with its reason at once, and the run goes on to the next pick (a later read
of that video replaces only that mark). Without `yt-dlp`, save the file yourself
as `videos/<id>/video.mp4` (or set `video_file` in posts.csv) and run the same command without `--fetch`. Subtitles
can also come from your data reader: save them as `videos/<id>/<name>.vtt` or `.srt`.

## What the script writes, per video

- `probe.json` (MEASURED): `length_s`, `fps`, size, `cuts` (scene changes over 0.3, two within 0.2 s count once),
  `cuts_per_10s`, `first_cut_s`, `average_shot_s`, `words`, `words_per_minute` (over the spoken span),
  `first_words_3s`, `non_silent_share`, `loudness_lufs`.
- `first.jpg`: the first 3 seconds, a frame every 0.25 s, numbered 1-12 (tile n is at (n-1) × 0.25 s).
- `shots.jpg`: a frame 0.12 s after each cut, numbered; `probe.json` `files.shots[n-1].t` is tile n's time.
- `words.json`: every word with its start and end, when subtitles were found.

**No subtitles, no speech rate.** Without subtitles `words` and `words_per_minute` stay `null`: the report says "words
per minute not measured: no subtitles", and a missing rate is never read as 0 (the format's medians, the recipe's
`words_per_minute` and `remake_check.py` leave it out and say so). To measure it anyway, run a local speech-to-text
tool (a Whisper-style transcriber, on the user's machine, free) on `videos/<id>/video.mp4`, write its output as
`videos/<id>/<name>.vtt` or `.srt`, and run `video_probe.py <run> <id>` again: the words and the rate are read from it.
This is optional and costs nothing; never send the user's or a creator's video to a paid service for it without asking.
- `notes.json`: the template you fill.

## The fixed list (fill notes.json for every picked video)

| Field | Write down |
|---|---|
| `hook` | What happens in the first second, and at what time the viewer knows what the video is |
| `first_frame` | The very first frame: a face, text, motion, a blank |
| `text_on_screen` | The words on screen and how they appear (captions, chips, a title card) |
| `first_line` | Optional: the first words on screen, verbatim (`text_probe.py` measures them beside the captions) |
| `sound` | Voice, music, a trending sound; read `non_silent_share` and the words |
| `turn` | The change that keeps people watching, with its time (often the first cut) |
| `ask` | The call to action (follow, comment a word, a link), or `none` |
| cuts per 10 s, length | Measured: copy from `probe.json`; never count cuts by eye |
| `beats` | The beats with times: hook, setup, turn, proof, payoff, ask |

`read: true` only after you looked at both sheets. A video you could not open or did not look at: `read: false` and
the reason. Never fill a field from the caption.

## The covers

`covers_sheet.py <run> --sort ratio` puts every cover on numbered sheets of 50 (`covers_sheet.jpg`,
`covers_sheet-2.jpg` …; tile n is `covers_sheet.json` `tiles[n-1]`, with its sheet). It checks each sheet against its
tiles and prints "drew N of M on K sheets": look at every sheet, and when N is under M say which tiles are missing. Use
the sheets to group posts into formats and to see what the outliers share. A cover that was not saved shows grey and
is "not read", with why when `covers/not_read.json` has it (`--fetch` saves the missing covers like a browser and keeps
a 403 or 429 there).

## Carousels and text posts

Save each slide as `videos/<id>/slides/01.jpg …` and look at them in order; fill the same list (hook = slide 1, turn =
the slide that changes direction, ask = the last slide). A carousel whose slides were not saved is read by its cover
only, and the report says so ("Carousel slides"). For text posts the words are the post: `text_probe.py`
measures them for every post (the words step), and you read the deep-read posts' full texts side by side there
(`writing.md`), with no `notes.json` needed.

## When no video can be had

No shell, no network, or every download refused: say once that the videos cannot be watched, and what that costs: no
cut times, no first seconds frame by frame, no words per minute. Mark the picks in one go (with a shell):
`video_probe.py <run> --picks --not-read "no network to download videos"` (a video already read keeps its probe and notes); without a shell, write each
`videos/<id>/notes.json` as `{"post_id": "<id>", "read": false, "not_read_reason": "<why>"}`. Go on with covers and
captions, and keep every claim about the videos INFERRED with that basis. Recipes keep empty `beats`.
