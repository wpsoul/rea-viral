# Way in: a niche (its formats across creators)

The user gives a niche in words, keywords or tags, a list of accounts, or asks "what works now in X". The run answers,
in the **Niche report**: **which video formats and hooks are working NOW across the niche**, over many creators (the
niche's formats, drawn as the chart "Formats of the niche"), which of them fade, the trends behind them, a recipe per
format, the hooks of the winning posts, and who to watch. Our own format research uses this way too: a niche's
formats are what a planner's saved formats are made from (`radar_rows.json`, below).

Two rules make it honest:

- **A trend is a post that beats ITS OWN CREATOR's usual**, never the biggest number in the list. A small creator's
  post at 5× its usual is a trend; a big creator's ordinary post with more views is not.
- **A format of the niche needs posts from 3 creators or more.** Two can be one copying the other, or one team; three
  is the smallest count that is a pattern of the niche and not of a pair, and it stays reachable with 8 to 12 creators
  read. What one creator does is that creator's habit: it is shown, marked, and never called a format of the niche.

The run folder is `rea-viral/niche-<slug>/` (the slug from the niche's words: `niche-ai-video-editing`).

## Step 0: Setup, one message

Look at your tools first (step 1), so the message can say what you can read. Then ask once, skip what the user
already said, and wait:

> To find what works now in <niche> I need:
> 1. The niche: the words and tags I will search (I propose: <2-4 words>, <2-3 tags>; correct them), and any
>    accounts you already know in it (they are read too).
> 2. The network: one to start (YouTube Shorts, TikTok, Instagram, X, Threads or LinkedIn).
> 3. The window: the last 30 days, unless you want another.
> 4. How wide: up to 10 creators and their 25 most recent posts each (250 posts at most), unless you want less.
> 5. Only when a paid reader will be used: a spend ceiling (default $3).
> 6. Optional: your own account, so the plays and drafts are written for you.

Propose the words and tags yourself when the user gave none: the niche's own words, and tags written as people write
them on the network (lower case, no spaces: `aivideoediting`). A niche can mean two things ("AI video editing": tools
that edit, or videos made by AI): name the one you will search in the proposal.

Write `niche.json` (`data-shape.md`, "A niche run"): the name, the question, the words and tags, the seed accounts,
the networks, `read_at`, the window, the caps, the ceiling, the sources.

## Step 1: Connections, and what a free reader can do here

Look at your tools first (SKILL.md, "Connections before keys"). For a niche you need two kinds of reading: **finding**
posts by words, tags or a trending list, and **each creator's recent posts** for their usual.

| Network | Free (no key, no sign-in) | Needs a data connector |
|---|---|---|
| YouTube Shorts, with `yt-dlp` | A hashtag's Shorts page (`https://www.youtube.com/hashtag/<tag>/shorts`): Shorts only, but each row is only an id and a rounded view count, with no creator, date or title, so every found post is read once on its own. A search by words (`ytsearch<N>:<words>`) returns mostly long videos with no dates in the list (in a check on
2026-11-16, 30 of 30 results for an editing-tools search were over 3 minutes): find Shorts through tags and seed
accounts. A channel's Shorts list: ids only, then one read per post (exact views, likes, comments, length, time). No niche trending list | Nothing more is needed for YouTube; a connector only saves time |
| TikTok | Usually nothing: `yt-dlp` is often refused without a sign-in, and search and tag pages are not served | Search by words and tags, a creator's videos, sometimes a trending list |
| Instagram | Nothing: profiles, tags and reels need a sign-in | Search by tags, a creator's reels |
| X, Threads, LinkedIn | One post at a time by its id (X's free embed record); no search, no list | Search by words, an account's posts |

Say in two or three lines what that means for this run, for example: "I can read YouTube Shorts free: hashtag pages
to find posts, then each creator's recent Shorts for their usual. TikTok would need a data connector: without one I
can't search it." Never ask for a key. Read every paid tool's price before its first call (`ledger.py <niche> check`).

## Step 2: Find the posts, then the creators

1. **Find** with every way you have, in this order: the seed accounts' recent posts, the niche's tags, its words, a
   trending list where a reader gives one. Keep only the window's posts. Write each found post to `found.csv`
   (`post_id,url,network,account,found_by,query`; `found_by` is `search`, `tag`, `trending`, `seed_account`,
   `user_list` or `other`). With `yt-dlp` on YouTube one command does this step, reading each found Short once (a tag
   in the link has no `#`):

   ```
   python3 SKILL_DIR/scripts/readers/ytdlp_reader.py find <niche> "https://www.youtube.com/hashtag/<tag>/shorts" --max 40
   python3 SKILL_DIR/scripts/readers/ytdlp_reader.py find <niche> "ytsearch30:<words> #shorts" --max 30 --shorts-only
   python3 SKILL_DIR/scripts/readers/ytdlp_reader.py find <niche> "https://www.youtube.com/@<seed handle>/shorts" --max 25
   ```

   It prints the creators found, most found posts first, each with the link of its Shorts (`account_url` in
   `found.csv`). Each read takes 1 to 3 seconds: run a long read in the background, never under a short timeout.
2. **Pick the creators** up to the cap: the seed accounts, then the creators with the most found posts, keeping small
   and big ones (a small creator's outlier is the kind of trend this run is for). **Read the found titles first:** a
   tag is a community, not the niche. In a real run (2026-11-16) `#motiondesign` Shorts were mostly one wave of
   animated "cute shape creature" clips, `#aftereffects` was fan edits and `#aivideoediting` was tiny accounts posting
   AI comedy clips. Keep the creators whose posts belong to the niche the user meant, leave out accounts that only
   repost others' clips, and write in `findings.json` `not_read` which communities each tag brought and what you left
   out.
3. **Read each creator's recent posts** into `accounts/<network>-<handle>/` (an account folder: `account.json` and
   `posts.csv` in the shape of `data-shape.md`): their latest 25 posts, and the found post itself if it is older.
   A creator's usual needs **9 settled recent posts or more** (the window and the 30 days before it; each post is
   compared with the median of the other 8 or more); with fewer, its posts are scored on views per follower, a weaker
   basis, and never count toward a format.
   With `yt-dlp` (the link is the creator's `account_url` from `found.csv` plus `/shorts`):

   ```
   python3 SKILL_DIR/scripts/readers/ytdlp_reader.py posts <niche>/accounts/youtube-<handle> "https://www.youtube.com/@<handle>/shorts" --max 25 --spread 75
   ```

   `--spread 75` lists the creator's latest 75 posts (one request) and reads 25 of them, evenly spread. Without it, a
   creator who posts twice a day is read for its last 12 days only, its last 7 days are too new to score, and the
   early half of the window holds none of its posts, so no direction can be measured (seen on a real run). Say in the
   report how far back each creator's reads reach (`trends.json` `creators[].span`).

   Covers are saved at once into each creator folder (`covers/`). Add each reader you used to `niche.json`
   `sources`.
4. `python3 SKILL_DIR/scripts/validate.py <niche>`: it checks `niche.json`, every creator folder, that a post id is
   unique across the niche, and `found.csv`. Go on only at 0 errors.

## Step 3: The trends

```
python3 SKILL_DIR/scripts/trends.py <niche>
```

Writes `trends.json`, `trends.csv` (every post with its ratio and its basis, best first), `watchlist.csv` and
`planner_rows.json`. Definitions: `numbers.md`, "A niche". Read `status` first:

| Status | What you may say |
|---|---|
| `ok` | Trends, formats and hooks of the niche |
| `too_few_creators` | Under 3 creators have their own usual: list the trends, call no format of the niche, say "not enough creators" |
| `too_few_posts` | Under 20 posts are scored against their own creator: list them, call no format, say "not enough posts" |
| `empty` | Nothing was read: say why, and what reader would fix it |

## Step 4: Look at the posts

```
python3 SKILL_DIR/scripts/covers_sheet.py <niche> --sort ratio
```

Every cover of the window on one numbered sheet, best first, each tile naming its creator. Then watch the videos
`trends.json` `deep_read` picked: the top trends, **at most 2 per creator** so one creator cannot fill the reading,
3 ordinary posts (near 1×) and 2 flops, of different creators. Each is cut in its creator's folder:

```
python3 SKILL_DIR/scripts/video_probe.py <niche> --picks --fetch          # or name post ids instead of --picks
```

Fill each `notes.json` as in `deep-read.md`. A video that could not be read is "not read", never described from its
caption.

## Step 5: The formats, across creators

Group the window's posts into formats from the covers sheet and the videos you watched, and write `formats.json` at
the niche folder (the same shape as an account's; a post id from any creator folder; each post in at most one
format). A format is a container (hook, structure, look, length), never a topic. Name one when you see it at more
than one creator; list a single creator's series too: `radar.py` marks it as that creator's habit. Write in `basis`
what showed you the container, at which creators. Then:

```
python3 SKILL_DIR/scripts/radar.py <niche>
```

It measures each format across creators (`radar.md`, "The formats of a niche") and writes `radar.json`
(`scope: "shared"`), the recipe skeletons `formats/<id>.md` and the watchlist's formats column. Fill each recipe of a
format of the niche from watched videos of **at least two different creators**; a beat seen at one creator only is
that creator's, not the format's.

## Step 6: The hooks

```
python3 SKILL_DIR/scripts/text_probe.py <niche>
```

The same measures as an account's words (`writing.md`), each post against its own creator's usual. A feature lifts
or sinks for the niche only when its posts come from 3 creators or more; one creator's habit comes out "few
creators". The best and worst first lines hold at most 2 of any creator. It writes `writing.json`, `posts_text.csv`
and `hooks.md`, the niche's twin of a voice sheet: fill its prose with real first lines of at least two creators and
their numbers (SEEN, post ids).

## Step 7: Your reading, and the hand-over

Test every "why" against the posts where it did not work: the same format's flops, and, when one creator posted the
same clip twice, both uploads (on a real run one did 19× its usual and the other 0.07×: what made the gap is not in
the video, and the report must say so).

Write `findings.json` (`handover.md`): `headline` (what works now, in one or two sentences), `formats` (your reading
of each format, with `"format": "<id>"` when it is about one), `did_not_work` (the formats of the niche under their
creators' usual or fading, what the flops you watched show, what sinks in the words across creators; the same rules as
an account's, `account-run.md`, step 8), `hooks`, `creators` (who to watch and why), at most ten `plays`, and
`not_read` (networks, creators, videos and days you could not read, and why). Every claim carries its label. Then:

```
python3 SKILL_DIR/scripts/build_report.py <niche>
```

It writes the Niche report (`report.html`, one file: the chart of the formats of the niche, the gallery of the
formats with small pictures of the posts that prove each, each linked to its original and never a video, what did not
work, the trends, the hooks, who to watch), `NICHE.md` for agents, and the planner files (`report_record.json`; `brief.json`, the report's short view; and
`radar_rows.json`: one row per format of the niche, 3 creators or more, with its recipe and the links of the posts
that prove it). Tell the user: the path, three lines (what works now; the strongest format of the niche with its
creators, lift and direction; what fades, or the hook that lifts, or "nothing in the words lifts across creators"),
what was not read, and the cost.

## A planner connector

Known by its tools, not its name (`connections.md`, "A planner connector"): a tool that keeps reports, one that keeps
formats, one that scores posts against their author's usual and saves trend rows, one that adds a post draft. One
example: the GreenLight Pulse connector (`save_report`, `save_formats`, `score_posts`, `save_trends`, `add_post`).
When one is connected, right after the hand-over:

- **Save the report**: `report_record.json` and the page (`connections.md` has the call).
- **Save the formats of the niche**: send `radar_rows.json` `rows` to its formats tool (Pulse: `save_formats`, which
  fills its Format Radar tab, Saved), with the report's id from the save before. Each row is one format of the niche
  that passed the 3-creator rule: its name, creators, lift, rising or fading, the recipe's beats and hook, the links
  of the posts that prove it, and its best proof post as the row's face (link only: the planner keeps the media).
- **Save the trends there**: send `planner_rows.json` `rows` to its save tool, at most 60 a call. Each row is one
  post in the shape those tools take: `url`, `text`, `author` (`@handle`), `followers`, `posted_at`, `views`, `likes`,
  `comments`, `shares`, `saves`, `has_video`, `author_recent_views` (the creator's other posts, so the planner can
  compare the post with its own creator's usual too), `pattern` (the format's name), `why` (the ratio and the posts
  behind it) and `hook` (the first line).
- **A format can become drafts** with the niche's hooks (`writing.md`, "Write like it"): checked by `draft_check.py
  <niche> --all`, then added as drafts, never scheduled or posted.

A tool the connector does not have is skipped (an older connector may have only the trend tools); without a
connector, the files are the hand-over.

## Scout and Watch

`watchlist.csv` lists the creators worth following (a post at 2× their usual or more, or a rising format), each with
its `watch_command`. To watch them all: `python3 SKILL_DIR/scripts/watch.py add rea-viral --from <niche>/watchlist.csv`
(they join as Scout candidates; `watch.md`).

## The offer (one question, asked once, never in an unattended run)

It starts from **one format of the niche**: the strongest format of the niche whose recipe has beats from watched
videos (Scale it or Underused first). One message, the user answers once; when the report went to a planner, the
message opens with what was saved:

> Saved to Pulse: the report (Reports) and 2 formats (Format Radar).
> The strongest format here is <format> (<N> creators, <lift> their usual, <direction>). Want me to:
> (a) make it as a video with your own content: Basic (an HTML page rendered to MP4), Standard (an editable video:
>     GreenLight Motion or HyperFrames, your pick) or Advanced (GreenLight Dash's Rebuild by Style);
> (b) draft <5> posts with the niche's hooks for your account;
> (c) go deeper into @<creator>, who owns this format (the full account run)?

(c) starts `account-run.md` from that creator's folder: copy `accounts/<network>-<handle>/` to
`rea-viral/<network>-<handle>/` and read the rest of its window there. With no format worth making, offer only what
applies; with nothing, ask nothing.
