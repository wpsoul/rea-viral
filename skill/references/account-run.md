# Way in: an account (the main way)

One account in: the user's own, a competitor, or one they look up to. Out: the **Account report**, what worked and
what did not: why it grows, **its formats** (the Format map: this account's own formats, measured), the ones that sit
under its usual or fade, its flops and what they show, how it writes (its voice sheet) and what sinks in its words,
its comment tactics, which posts brought followers at the best level the data allows, and the plays. The run folder
is `rea-viral/<network>-<handle>/` (network as in `account.json`: `instagram`, `tiktok`, `youtube`, `x`, `threads`,
`linkedin`; YouTube Shorts is `youtube`). One folder per account and network; a shared `rea-viral/watch/` holds
Watch for all of them.

What one account draws is its **Format map**. A niche run draws the formats of a niche across many creators
(`niche.md`).

## Step 0: Setup, one message

Ask once, in one message, and wait for the answer. Skip what the user already said.

> To reverse engineer the account I need:
> 1. The account: a link or handle, and its network (Instagram, TikTok, YouTube Shorts, X, Threads or LinkedIn).
>    Several networks of one creator are fine; each gets its own report.
> 2. The window: the last 12 months, up to 200 posts per network, unless you want less.
> 3. Optional: your own account or niche, so the plays (and any drafts) are written for you.
> 4. A spend ceiling for paid data (default $3; free readers are used first).
> 5. Only if you want Watch (alerts when the account jumps in followers): where alerts should go (a file, a desktop
>    notice, a bot of your own).

## Step 1: Connections before keys

SKILL.md, "Connections before keys", and `connections.md`. Write every source into `account.json` `sources`.

## Step 2: The corpus

Write `account.json`, `posts.csv` and later `comments.csv` (exact shape: `data-shape.md`). Unknown = an empty cell; a
count is a whole number (`12300`, never `12.3K`). On X, Threads and LinkedIn also the whole text, a thread's parts, the
author's own replies with their minutes, reposts, quotes, bookmarks and the language tag (`data-shape.md`, "Text
networks").

Read the window plus up to 20 earlier posts (they only feed the first baselines). When your reader gives "the latest N
posts" instead of a date range, set `window.from` to the date of the 21st oldest post you have and `window.to` to the
newest; say the real span in the report. `read_at` is when the posts were read. Save covers at once (TikTok and
Instagram links expire within hours): `covers_sheet.py <run> --fetch` saves every missing cover from its `cover_url`
the way a browser asks for it (a script's own request gets 403 from some picture servers), writes `cover_file`, and
keeps a cover that still answers 403 or 429 as "not read" with that status (`covers/not_read.json`), never a guess.
Write each post's own media in `own_media` and leave replies out (`data-shape.md`, "Own media" and "Replies"). On
YouTube with `yt-dlp`, one command does all of it:

```
python3 SKILL_DIR/scripts/readers/ytdlp_reader.py posts <run> "https://www.youtube.com/@<handle>/shorts" --max 200
```

Then always `python3 SKILL_DIR/scripts/validate.py <run>`: it names every wrong cell. Go on only at 0 errors. A source
whose rows have no dates cannot be used for baselines: read the posts again with one that has them. On X, if cursor
pagination stops empty after page 2 despite older posts existing, fall back to `end_time` date windows with
`scripts/readers/x_windows.py` (`connections.md`, "Paginated X readers stopping early").

## Step 3: The numbers

```
python3 SKILL_DIR/scripts/analyze.py <run>
```

Each post against the median of the 20 settled posts before it (an account that grew tenfold is not judged by its early
numbers; posts under 7 days old — 3 days on X and Threads — are kept out of baselines and flops so immature counts do
not skew medians, while still scored and marked `"fresh / still growing"` so fresh breakouts are never hidden), hits
(2× or more), flops, rates, length and weekday buckets, the timeline with measured changes, which posts brought
followers at the best level the data allows, and `deep_read`: the top 8 outliers, 4 ordinary posts and 2 flops to watch.
Definitions: `numbers.md`. Read `status` first: `private`, `empty`, `no_dates` or `too_few_posts` change what you may
say.

## Step 4: Watch the videos

```
python3 SKILL_DIR/scripts/covers_sheet.py <run> --sort ratio       # every cover on numbered sheets of 50
python3 SKILL_DIR/scripts/video_probe.py <run> --picks --fetch     # download, cut, measure the deep-read posts
```

`covers_sheet.py` prints "drew N of M on K sheets": look at every sheet it names, and if N is under M say so. Only a
post's own video is cut: a text, picture or carousel post goes to its words and its cover, and a quote's video belongs
to the other post. A pick whose video cannot be had (the downloader finds none, a 403) is marked not read with why and
the run goes on. Look at `videos/<id>/first.jpg` and `shots.jpg`, read `probe.json`, fill `videos/<id>/notes.json`
(`deep-read.md`). Set `read: true` only after looking. When no video can be had at all: `video_probe.py <run> --picks
--not-read "<why>"`.

## Step 5: The comments

Read the top comments and replies of the deep-read posts (on YouTube: `readers/ytdlp_reader.py comments <run>
--picks`), write `comments.csv`, set `comments_read.replies_read`, then `comment_tactics.py <run>` (`comments.md`).

## Step 6: How it writes

`text_probe.py <run>` measures every post's words against the account's own baseline and writes `writing.json`,
`posts_text.csv` and a skeleton voice sheet `voice.md`. Claim only what it marks `lifts` or `sinks`. Fill the voice
sheet's prose (`writing.md`).

## Step 7: Its formats (the Format map)

Group the window's posts into formats from what you watched and the covers sheet, write `formats.json` (with
`examples`, and a `match` where the words show the format), run `formats_check.py <run>` and fix the overlaps, the
examples that do not fit and the formats it shows you missed (`radar.md`, "Check the grouping"), then `radar.py
<run>`: each format's posts, share, lift, hit rate, direction (rising, steady, fading) and follower pull, its corner
(Scale it, Underused, Overused, Drop: where it sits, never where it is going), `radar.json` (`scope: "account"`) and a
recipe skeleton `formats/<id>.md` to fill from the deep read (`radar.md`). With no watched video, leave `beats` empty: a recipe without beats is not offered for a remake.

## Step 7b: Growth mode (when asked why it grows)

"REA Viral: why is @handle growing" (or "REA Viral growth @handle", "why is @handle growing (REA Viral)",
`/rea-viral growth @handle`) adds, here: the growth reads, `growth.py`, your reading in `findings.json` `growth`, the
reply draft, and the reply-ready `post-card.png` (`post_card.py <run> --layout t1 --skin cobalt`; `growth.md`). The
other steps stay as they are.

## Step 8: What worked, what did not, and the plays

Write `findings.json` (`handover.md`): the headline, the mechanisms (what worked), `did_not_work`, how it writes,
comment tactics, timeline notes, at most ten plays, a 14-day plan when the user gave their own account, and
`not_read`.

**What did not work** is a part of its own, under the same rules as what worked. The report already lays out what
the scripts measured (the formats under 1× or fading from `radar.json`, the flops from `analysis.json#flops` and
what the watched ones show, the features of the words that `sinks` in `writing.json`); `did_not_work` is your
reading of it:

- a format under the account's usual or fading: MEASURED (`radar.json#formats.<id>.lift` or `.direction`); a format
  with `few_posts` is shown, never a finding on its own;
- the flops you watched: SEEN, with the post ids, for what they show; never "it flopped because" from one post. A
  pattern the flops share is a lead only when the hits do not share it too;
- what sinks in its words: MEASURED for what `writing.json` marks `sinks`; with nothing marked, say so and give the
  leads as leads;
- "not enough data" when it is the truth (under 20 dated posts, no formats measured, no video watched, the words not
  measured).

## Step 9: The hand-over

`build_report.py <run>` writes the Account report (`report.html`, one file with its pictures inside), `ACCOUNT.md`,
and the planner files (`report_record.json`; `brief.json`, the report's short view, made from your `findings.json`;
`radar_rows.json` with the strongest format: Scale it or Underused, 6 posts or more). It prints the page's size (under 3 MB). Give the user the path and four lines (the answer, the
strongest format, what did not work, the follower evidence level), what was not read, and the cost
(`ledger.py <run> total`). With a planner connector, save the report and the format there (SKILL.md, "Handing the
report to a planner").

## Step 10: The offer (one question, asked once, never in an unattended run)

One message holds whichever offers apply; the user answers once ("a", "b", "c", several, or none). When the report
went to a planner, the message opens with what was saved:
"Saved to Pulse: the report (Reports) and 1 format (Format Radar)".

- **(a) Make a format as a video**: only when a format sits in Scale it or Underused with 6+ posts and its recipe has
  beats from watched videos. Basic, Standard (GreenLight Motion or HyperFrames, the user's pick) or Advanced
  (`remake.md`).
- **(b) Draft posts in this voice**: only when `writing.json` status is `ok` (`writing.md`, "Write like it").
- **(c) The niche run, in one line**: "Want the same across this account's niche: which formats work now for many
  creators, not only this one?" It starts `niche.md` with this account as a seed account and ends in a Niche report.
