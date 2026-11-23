# Connections before keys

REA Viral has no data provider built in. You use what the user already gave you, and you know a tool by what it does.

## Look first

1. **Your tools.** List them. A tool that takes a handle or a profile link and returns posts with dates and counts is a
   data reader, whatever it is called. One that returns comments with their authors is a comments reader. One that
   returns a follower count is enough for Watch. Many such servers have a catalogue or search tool: search by the job
   ("instagram user reels", "tiktok video comments"), not by a vendor's name.
2. **A shell.** `yt-dlp --version`, `ffmpeg -version`, `python3 --version`, `node --version`.
3. **A browser tool.** It can open a public profile and show covers; it rarely gives a full, dated post list.
4. **Plain web reading.** Profiles and a few captions. Not enough for baselines on its own.

## What each kind gives, and what a missing one costs

| Reader | Posts with dates | Counts | Comments | Videos | Follower history | Typical cost |
|---|---|---|---|---|---|---|
| A social data connector (paid API behind an MCP server or a tool) | yes, paged | views, likes, comments, often shares and saves | yes, often with replies and the creator's flag | links (they expire) | rarely; some sell growth by quarter | about $0.001-0.01 a call |
| `yt-dlp` | YouTube yes; TikTok often refused; Instagram needs a sign-in | YouTube views, likes, comments (no shares, saves) | YouTube top comments and replies; times are "2 days ago" | yes, most public posts | no | free |
| A network's public embed record (X gives one per post, by id) | no list: one post at a time | likes, replies; no views, reposts or bookmarks | no | no | no | free |
| `ffmpeg` | - | - | - | cuts, frames, sound levels | - | free |
| A browser | partly | as shown on screen | as shown | covers and frames on screen | no | free |
| Plain web reading | rarely | rarely | no | no | no | free |

Say what is missing in one short paragraph, with what it costs in depth, for example: "I can read YouTube Shorts and
their comments free with yt-dlp. TikTok and Instagram need a social data connector; without one I can't read those
networks' posts or comments. No source here gives daily follower counts, so which posts brought followers will be
estimated, not measured." Only then name the kinds of choices.

## Examples of what exists (a list of choices, not a dependency)

Social data APIs that are often reached through an MCP server or a tool catalogue: ScrapeCreators, Apify actors,
treg, Bright Data, EnsembleData; creator analytics with growth history: Social Blade, CreatorDB, influencers.club;
the platforms' own analytics for the user's own account (the only daily follower figures that are exact). Names
change; check what the user can actually connect, and read each tool's own price.

**Never ask for a key.** If the user wants a paid source, they connect it to their agent themselves, the way that
agent connects tools. The skill only uses what is connected.

**X, Threads, LinkedIn.** A full, dated list of an account's posts needs a data connector; plain web reading gets
little (X shows nothing without a sign-in). On X, a free embed record per post id adds what list rows often lack:
which links are links out, the quoted post, an article's title. Checked 2026-11-16 on one X account: six pages of 20
rows cost $0.0027, and the rows mixed in reposts, replies to others and the author's own replies, so map them with the
rules in `data-shape.md` ("Text networks", "Replies") and below ("Own media and quoted media").

## Finding posts for a niche

A niche run reads in two ways: **finding** posts by words, tags or a trending list, then **each creator's recent
posts** for their usual. What a free reader can and cannot do per network is in `niche.md`, step 1. In short, checked
2026-11-16 with `yt-dlp`: YouTube Shorts can be found free through a hashtag's Shorts page (ids and rounded views
only, so each found post is read once on its own) and seed accounts; a search by words returned only long videos in
that check;
TikTok, Instagram, X, Threads and LinkedIn need a data connector to search. A data connector that searches by keyword
or tag, or gives a trending list, does it in one call: read its price first.

## A planner connector

Know it by its tools, not its name. One example: the GreenLight Pulse connector. Every run's hand-over writes the
files these tools take (`handover.md`, "The planner files"); send them right after the hand-over, unasked (it is the
user's own planner), and only to such a tool: nothing of the user's is sent anywhere else. A tool the connector does
not have is skipped (an older Pulse has only the trend and draft tools) and its file stays the hand-over.

- **Reports.** A tool that keeps a report: its record and its page (Pulse: `save_report({report, html?, upload?,
  run?})`). Send `report_record.json` `report` (it carries `brief`, the short view the planner's panel draws, the
  same as `brief.json`), with `by` set to your own name and `took_s` when you timed the run. Then the page, which
  comes two ways (`report_record.json` names both, with their sizes):
  - **With a planner connector in a chat app, send the light page inline**: `report-light.html` (`light`), the same
    report with no pictures inside (each grey tile links to its post), as the tool's `html` text. A chat passes text
    in a call, not files from your folder, and the full page with its pictures is too big for that (Pulse takes
    `html` up to 1 MB a call and says 64 KB is what passes with ease; a light page is 40 to 150 KB). If the tool
    refuses its size, save the record without a page: the user still sees the brief and the summary.
  - **With a local planner (on the user's own disk, or a tool that reads a path), send the full file by path**:
    `report.html` (`file`), the one with its pictures. A tool that gives an upload address instead takes the file
    there (Pulse: `upload: {size}`, then `attach_report_file({id, file_id})`).
  - **The cover**: `report-cover.jpg` (`cover`: the account's own picture or the post's cover; a niche has none) goes
    the same way as the full page: by path, or by the upload address the tool gives for it (Pulse: `upload.cover`
    `{type, size}`, then `attach_report_file({id, cover_id})`). In a chat that cannot send files, leave it out.
  Keep the saved report's id: the formats point to it. In Pulse the report lands in its Reports tab: the brief in a
  panel, the page opened in the browser as the Extended report.
- **Formats.** A tool that keeps the user's saved formats (Pulse: `save_formats({rows, report?})`, up to 60 rows,
  shown in its Format Radar tab, Saved). Send `radar_rows.json` `rows` with the report's id: a niche run's formats of
  the niche, an account run's strongest format, a post run's own format. Each row is `state: "link"` (the planner
  keeps the post's media itself, in the user's own storage).
- **Trends.** A tool that scores posts against their author's usual and one that saves trend rows (Pulse:
  `score_posts` and `save_trends`, at most 60 rows a call). A niche run writes those rows for you in
  `planner_rows.json` (`niche.md`, "A planner connector", has the row mapping).
- **Drafts.** A tool that adds a post draft with its words and, for a thread, its parts (Pulse: `add_post`, which
  takes `caption`, `thread`, `title` and `why`). Passing drafts go there as drafts, never scheduled or posted; the
  user approves them in the planner. Without one, the drafts stay as `drafts/<n>.md`.

Then the offer opens with one line of what was really saved, for example
"Saved to Pulse: the report (Reports) and 3 formats (Format Radar)". A refused save names the field: fix it and send
again; never change the report's findings to fit. A save that cannot be made (no network, no sign-in) is said in one
line, and the files stay.

## Own media and quoted media

A post's video is watched only when it is the post's OWN (`own_media: video`, `data-shape.md`). A quote post shows
the quoted post's video or pictures in the feed, and many readers hand that media back inside the row: never count
it as this post's. On a real X run (0.4.0) a quote post was described from the video it quoted. How to tell, per
reader:

- **X, a data connector's list of posts:** the row's own media list (`media`, `extendedEntities.media`,
  `attachments.media_keys`) is the post's own; the quoted post sits apart (`quoted_tweet`, `quotedStatus`,
  `referenced_tweets` of type `quoted`), with its own media. `own_media` comes from the row's own list only:
  a video or an animated GIF = `video`, 2+ photos = `images`, 1 photo = `image`, nothing = `none`.
- **X's free embed record** (one post by id): `mediaDetails` is the post's own media; `quoted_tweet.mediaDetails`
  is the quoted post's.
- **Threads, LinkedIn:** the same rule: the post's own attachments, never the reshared or quoted post's.
- **A reader that does not say which is which:** leave `own_media` empty. The post is then not watched, and the
  report says "video not read" for it rather than describing another post's video.

## Replies

Leave replies out of `posts.csv`: a reply to another account is not a post, and the account's own replies belong to
the post they sit under (a thread's parts, or `author_replies` with their minutes, `data-shape.md`, "Text networks").
On X a connector's row says so (`isReply`, `in_reply_to_status_id`, `inReplyToId`, `referenced_tweets` of type
`replied_to`), and the text of a reply opens with the handle it answers. When you cannot fold them, write the reply
rows with `reply_to` (the handle answered) and, for the account's own, `reply_to_id`: the scripts leave them out of
every number, fold the own ones into their post, and the report counts them ("12 replies left out of the numbers").

## Covers

Save covers with `covers_sheet.py <run> --fetch` (`common.save_picture`), not a script of your own: some picture
servers answer 403 to a script's own User-Agent or none, and the script asks like a browser (a browser's User-Agent
and Accept, redirects followed, a timeout). A cover that still answers 403 or 429 is kept as "not read" with that
status in `covers/not_read.json`, and the run goes on.

## Mapping a reader's rows to posts.csv

- Find the post's time: `create_time`, `taken_at`, `timestamp` (Unix: convert to ISO UTC), `upload_date` (a date).
  A row without any time stays empty; a source with no times at all is skipped for the corpus.
- Views: `play_count`, `view_count`, `video_view_count`. Instagram images may have no views: leave the cell empty.
- Reels, Shorts and TikToks are `video`; several pictures are `carousel`. `own_media` from the post's own
  attachments ("Own media and quoted media").
- Replies: left out, or marked with `reply_to` ("Replies").
- A listing that shows "38K views" is rounded: get each post's own read for exact counts when you can.
- Save the raw answers in `raw/<reader>/` (trim long format lists), so the run can be checked later.

## Reading prices

Before the first call of each kind: read the price where the tool shows it, then
`python3 SKILL_DIR/scripts/ledger.py <run> check <usd for the planned calls>`. After the calls:
`ledger.py <run> add --step 2 --what "posts, 4 pages (data connector)" --calls 4 --unit 0.002`. At `STOP` (exit 3),
finish with what you have and list what was skipped in `findings.json` `not_read`.
