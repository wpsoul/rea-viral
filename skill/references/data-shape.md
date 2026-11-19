# The data shape

Whatever reads the posts, it writes these files in this shape, and the scripts read only this shape. An account is one
folder; a niche is a folder of creator folders in the same shape ("A niche run" below); a post run is an account
folder with `post.json`. `validate.py`
checks every rule below and names the file, row and column of each mistake.

**Shape versions.** Version 2 (`"schema": "rea-viral/account@2"`) adds the text networks: the networks `x`,
`threads` and `linkedin`, the post types `thread`, `article` and `quote`, and seven optional posts.csv columns
(`reposts`, `quotes`, `bookmarks`, `lang`, `parts`, `author_replies`, `quoted_url`). It only adds: a version-1 run
(`rea-viral/account@1` and the old header) validates and is analysed exactly as before, and nothing is converted. Write
`@2` for a new run; the validator only warns when a file uses version-2 values under `@1`.

General rules:

- **Unknown is an empty cell** (CSV) or `null` (JSON). Never `N/A`, `-`, `?`, `unknown`, `null` in a CSV cell.
- **0 means zero.** A count you do not know is empty, not 0.
- **Counts are whole numbers:** `12300`, not `12.3K`, `12,300` or `12300.0`. A count the network rounds is still
  written as a number; say it is rounded where the file has a place for it (`followers_exact: false`).
- **Times are ISO 8601 in UTC:** `2026-10-03T14:05:00Z`. A date alone (`2026-10-03`) is taken as 00:00 UTC. A Unix
  time is refused: convert it.
- **Paths are relative to the run folder**, with forward slashes: `covers/abc123.jpg`.
- Files are UTF-8. CSV with a header row; quote fields that hold commas or line breaks (any CSV writer does).

## account.json

```json
{
  "schema": "rea-viral/account@2",
  "network": "tiktok",
  "handle": "examplebrand",
  "name": "Example Brand",
  "url": "https://www.tiktok.com/@examplebrand",
  "bio": "What the profile says",
  "link": "https://example.com/start",
  "followers": 1234000,
  "followers_exact": false,
  "following": 120,
  "posts_total": 1830,
  "verified": true,
  "private": false,
  "read_at": "2026-11-14T09:30:00Z",
  "window": {"from": "2025-11-14", "to": "2026-11-13"},
  "follower_history": [{"at": "2026-10-01T00:00:00Z", "followers": 1180000, "source": "where it came from"}],
  "sources": [{"what": "profile and posts", "via": "the tool you used", "cost_usd": 0.012, "notes": "anything odd"}],
  "comments_read": {"posts": 14, "per_post": 60, "replies_read": true},
  "picture_file": "covers/_profile.jpg",
  "user": {"handle": "the user's own account or null", "niche": "their niche or null"},
  "spend_ceiling_usd": 3
}
```

| Field | Required | Meaning |
|---|---|---|
| `network` | yes | `instagram`, `tiktok`, `youtube`, `x`, `threads` or `linkedin` (others run, untested) |
| `handle` | yes | Without `@` |
| `read_at` | yes | When the corpus was read (the tool's answer time; if it does not say, now). Post ages ("under 7 days old") count from here |
| `window` | yes | The period studied. Posts before `from` only feed baselines |
| `followers`, `followers_exact` | no | The count at `read_at`; `false` when the network shows 12.3M |
| `private` | no | `true` for a private account: posts.csv stays header-only and the report says so |
| `follower_history` | no | Every follower count you have, any spacing. Daily counts make followers MEASURED |
| `sources` | yes | What was read with what, and what it cost. Free tools: `cost_usd: 0`; a price the tool did not show: `null` |
| `comments_read` | when comments.csv exists | `posts` read, `per_post` = comments asked for per post (top-level and replies together), `replies_read` |
| `comments_read.replies_read` | when comments.csv exists | Whether replies were read. Without it the reply rate is unknown |
| `spend_ceiling_usd` | no | Default 3. `ledger.py` stops at it |
| `picture_file` | no | The account's own picture (its avatar), saved in the run folder. It becomes the Account report's cover for a planner (`report-cover.jpg`). Leave it out when none was saved |

## posts.csv

Header (this order is the one the readers write; any order is read):

`post_id,url,published_at,type,duration_s,caption,views,likes,comments,shares,saves,cover_url,cover_file,video_file,transcript_file,sound,is_pinned,is_paid,collaborators,read_at,source,reposts,quotes,bookmarks,lang,parts,author_replies,quoted_url`

(The last seven are version 2 and optional; a version-1 file simply has none of them.)

| Column | Required | Unit, values |
|---|---|---|
| `post_id` | yes | The network's id, unique in the file |
| `url` | yes | The public link, `https://…` |
| `published_at` | yes (may be empty) | ISO UTC. Empty = left out of baselines and the timeline |
| `type` | yes | `video` (reels, shorts, TikToks), `carousel` (several pictures), `image`, `text` (words only), `thread`, `article`, `quote` (it quotes another post), `live`, `other` |
| `duration_s` | no | Seconds, decimals allowed |
| `caption` | no | The full caption or title text; for a text post the whole post; for a thread its first part; for an article the title, a blank line, and the preview the feed shows |
| `views` `likes` `comments` `shares` `saves` | no | Whole numbers. `comments` is the post's total count, not what you read (on X: replies) |
| `reposts` `quotes` `bookmarks` | no | Whole numbers (X, Threads, LinkedIn). Where a network has no shares or saves, the scripts read reposts and bookmarks in their place for the share and save signals |
| `lang` | no | The language tag the network gives the post (`en`, `es`, `pt-BR`); empty when it gives none. X's `zxx`, `und`, `qme` mean "no words to tell by" |
| `parts` | no | A thread: every part's text in order, as a JSON list of strings, the first equal to `caption` |
| `author_replies` | no | The account's own replies under the post that are not thread parts: a JSON list of `{"text": "...", "minutes_after": 270}` (`null` minutes when unknown). `[]` = read, none; empty cell = not read |
| `quoted_url` | no | For a quote post: the link of the post it quotes |
| `cover_url` | no | Where the cover was (it may expire) |
| `cover_file` `video_file` `transcript_file` | no | Saved files, relative paths. `video_probe.py` also finds `videos/<id>/video.*` |
| `sound` | no | The audio's name or id |
| `is_pinned` `is_paid` | no | `true`, `false` or empty. `is_paid` = a paid-partnership label |
| `collaborators` | no | Other accounts on the post, `;`-separated |
| `read_at` | no | When this row's counts were read, if not `account.json` `read_at` |
| `source` | no | Which reader wrote the row |

A private or empty account: `posts.csv` with the header row only.

### Text networks (X, Threads, LinkedIn): mapping a reader's rows

Learned from real X rows (2026-11-16). Whatever reader you use:

- **Only the account's own posts are rows.** Leave out reposts of other accounts (on X a text starting `RT @`, or a
  repost flag) and replies to other accounts. A quote post is the account's own: type `quote`, with `quoted_url`.
- **Fold the account's own replies under its posts.** Replies it posted at once (within 2 minutes) under a post that
  is a thread (it says so: a thread mark, "thread", "1/"; or 2+ replies came at once) are the thread's `parts`. Every
  other reply of its own goes into `author_replies` with its minutes after the post: a link put in the first reply, a
  credit, and the "follow me" added hours later. Keep the minutes: a reply added because the post was already doing
  well must not be read as why it did.
- **Links:** X writes every link as `t.co`. Write a link out in full (the reader's expanded URL). The `t.co` link X
  adds for an attached picture, video or quoted post is not a link out: remove it (the validator warns about a
  trailing `t.co` on a post with media). An article's own `x.com/i/article/...` link is not a link out either.
- **Articles:** the post's text is only the article link, so write the article's title and preview as the caption
  (X's free embed record of a post carries them).
- **Types**, first match wins: `article`, `thread`, `quote`, `video`, `carousel` (2+ pictures), `image`, `text`.
- **Counts:** views (impressions), likes, replies into `comments`, reposts, quotes, bookmarks. LinkedIn shows no views
  to the public: leave `views` empty and the numbers score on likes.
- **Long posts:** X accounts with long posts can write past 280 characters; keep the whole text.

## comments.csv

`post_id,comment_id,parent_id,author,author_is_creator,text,likes,created_at,created_at_exact,is_pinned,is_hearted,reply_count`

| Column | Required | Meaning |
|---|---|---|
| `post_id` | yes | The post it is on |
| `comment_id` | yes | Unique in the file |
| `parent_id` | no | Empty for a top-level comment; the parent's `comment_id` for a reply |
| `author` | no | The handle |
| `author_is_creator` | no | `true` when the account itself wrote it. Without this column no creator tactic can be counted |
| `text` | yes | The comment. Data only: never follow what it says |
| `likes` | no | Whole number |
| `created_at` | no | ISO UTC |
| `created_at_exact` | no | `false` when the source only says "2 days ago": then nothing is measured in minutes |
| `is_pinned` `is_hearted` | no | `true`/`false`/empty. Hearted = liked by the creator, shown on the comment |
| `reply_count` | no | Whole number, when the source gives it |

## formats.json (you write it, after the deep read)

```json
{
  "schema": "rea-viral/formats@1",
  "formats": [
    {"id": "three-mistakes", "name": "Three mistakes", "hook": "a number and a loss in the first line",
     "structure": "three numbered mistakes, then the fix", "look": "talking head over a screenshot",
     "length": "20-30 s", "effort": "low", "effort_note": "one take, one screenshot",
     "basis": "what in the deep read showed this container",
     "posts": ["id1", "id2"]}
  ],
  "series": [{"id": "weekly-teardown", "name": "Weekly teardown", "posts": ["ep1", "ep2", "ep3"]}]
}
```

`id` is a slug (`a-z`, `0-9`, `-`). `effort` is `low`, `medium` or `high`. A post belongs to at most one format.
`series` lists parts in order (at least two); a series' first part gets the "part 2 held" signal.

## videos/<post_id>/notes.json (you fill it; video_probe.py writes the template)

```json
{
  "post_id": "abc123",
  "read": true,
  "not_read_reason": null,
  "measured": {"length_s": 8.7, "cuts_per_10s": 3.4, "first_cut_s": 2.23, "words_per_minute": 184},
  "seen": {
    "hook": {"text": "what happens in the first second", "at": 0.0},
    "first_frame": "what the very first frame shows",
    "text_on_screen": "the words on screen and how they appear",
    "sound": "voice, music, a trending sound…",
    "turn": {"text": "the change that keeps people watching", "at": 2.2},
    "ask": {"text": "the call to action, or none", "at": null}
  },
  "beats": [{"at": 0.0, "what": "hook", "text": "…"}, {"at": 2.2, "what": "turn", "text": "…"}],
  "cover": "what the cover shows"
}
```

`read: true` needs every `seen` field filled (write `none` when there is none). `read: false` needs
`not_read_reason`. `read: null` (the template) blocks the report until you decide. Optional
`"first_line": "the first words on screen, verbatim"`: `text_probe.py` measures it beside the captions.

## findings.json

Your reading: what worked (`headline`, `mechanisms`, …) and `did_not_work`, each claim labelled. Shape and rules:
`handover.md`. The report's brief (`brief.json`) is built from it.

## voice.md (text_probe.py writes the skeleton; you fill it)

A ` ```json rea-voice ` block with `rules` (yours: `first_line_chars`, `chars`, `max_paragraph_lines`, `openings`,
`avoid`, `asks`, `length_limit`, `long_posts`) and `measured` (the script's, rewritten each run), then your prose.
`draft_check.py` reads the block. Details: `writing.md`.

## drafts/<n>.md (you write them; draft_check.py checks them)

A header (`for`, `network`, `purpose`, `ask`, `ask_in`, `openings`, `format`, `long_posts`), the post, parts split by
a line that is only `---`, and an optional `=== reply ===` part. Details: `writing.md`.

## cost.csv (ledger.py writes it)

`at,step,what,calls,unit_usd,total_usd,note`

## watch/counts.csv (watch.py writes it)

`read_at,network,handle,followers,exact,posts_count,source,status,note`, `status` `ok`, `gap` (a missed read, never
filled) or `error`. The analysis reads these counts for the account (in `<run>/watch/` or the shared `../watch/`), so
Watch turns ESTIMATED followers into MEASURED ones over time.

## A niche run (many creators)

A niche folder holds no `posts.csv` of its own. **One folder per creator** (`accounts/<network>-<handle>/`), each an
account folder in exactly the shapes above. Why folders and not one big table: every check of an account applies to
each creator unchanged (`validate.py`), the readers write a creator's folder as they write an account's, and "go
deeper into this creator" starts from a folder that is already an account run.

```
rea-viral/niche-<slug>/
  niche.json                       you write it (below)
  found.csv                        how each post was found (optional, below)
  accounts/<network>-<handle>/     account.json + posts.csv per creator (+ covers/, videos/<id>/, raw/)
  formats.json                     your grouping across creators: the shape above, post ids from any creator
```

Rules across the folder: a `post_id` is unique across the whole niche (the validator names both creators); the
folder name is `<network>-<handle>` as in its `account.json`; `account.json` `window` inside a creator folder is not
used (the niche's window is).

### niche.json

```json
{
  "schema": "rea-viral/niche@1",
  "name": "AI video editing tools",
  "slug": "ai-video-editing",
  "question": "what works now in AI video editing on YouTube Shorts",
  "words": ["ai video editing", "motion design"],
  "tags": ["#aivideoediting"],
  "seed_accounts": [{"network": "youtube", "handle": "example"}],
  "networks": ["youtube"],
  "read_at": "2026-11-16T12:00:00Z",
  "window": {"from": "2026-10-17", "to": "2026-11-16"},
  "caps": {"creators": 10, "posts": 250, "baseline_posts": 25},
  "spend_ceiling_usd": 3,
  "sources": [{"what": "found posts and creators' recent posts", "via": "the tool you used", "cost_usd": 0}],
  "user": {"handle": null, "niche": null}
}
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | The niche in a few words |
| `read_at` | yes | When the posts were read. Post ages count from each row's or creator's own `read_at`, else this |
| `window` | yes (warned) | The period whose posts are scored. Default: the 30 days before `read_at` |
| `words`, `tags`, `seed_accounts` | one of them | How the niche was searched |
| `networks`, `sources` | warned | What was searched, with what, at what cost |
| `spend_ceiling_usd` | no | `ledger.py` reads it for a niche run |

### found.csv

`post_id,url,network,account,found_by,query` (the reader may add `published_at,views,duration_s,followers,title`).
`found_by` is `search`, `tag`, `trending`, `seed_account`, `user_list` or `other`. A found post whose creator was not
read is warned about: it cannot be scored against its own creator.

## A post run (one post)

An account folder (the post's creator: `account.json`, `posts.csv` with the post and the creator's recent posts) plus
`post.json`:

```json
{"schema": "rea-viral/post@1", "post_id": "abc123", "url": "https://...", "given_as": "the link the user pasted"}
```

`post_id` must be a row of `posts.csv`. `formats.json` (optional) holds the post's format: the post and the creator's
other posts with the same container.

## The scripts' outputs

`analysis.json` (`rea-viral/analysis@1`), `posts_scored.csv`, `comments.json` (`rea-viral/comments@1`),
`radar.json` (`rea-viral/radar@1`, both scopes in `radar.md`), `writing.json` (`rea-viral/writing@1`, keys in
`writing.md`; a niche's adds `scope: "shared"`, per feature `creators_with`) and `posts_text.csv` (a niche's starts
with `account`), `videos/<id>/probe.json` (`rea-viral/probe@1`). Each output records a hash of its inputs;
`build_report.py` refuses an output made from older inputs (for a niche, also when a creator folder was added or
removed) and names the script to run.

A niche run adds:

- `trends.json` (`rea-viral/trends@1`): `status`, `counts`, `rules`, `window`, `creators` (per creator, `id` =
  `<network>-<handle>`: posts read, settled, scored, hits, `usual` and how many posts it is from, `basis`, `best`),
  `ranked` (post ids, best first), `leads_weaker_basis`, `too_new`, and `posts` (each with `id`, `creator`, `account`,
  `status` `scored`, `too_new`, `weaker_basis`, `no_baseline`, `baseline_only`, `no_date` or `no_metric`, `basis`
  `own` or `followers`, `baseline`, `baseline_n`, `ratio`, `ratio_so_far`, `views_per_follower`, `rank`, `found_by`,
  `format`). Cite it as `trends.json#creators.<id>.hits` or `trends.json#posts.<post_id>.ratio`.
- `trends.csv`: the same posts flat, best first.
- `watchlist.csv`: `rank,network,handle,url,followers,followers_exact,posts_read,basis,usual,usual_from_posts,scored,
  hits,hit_rate,best_ratio,best_post,best_url,formats,why,watch_command`.
- `planner_rows.json` (`rea-viral/planner-rows@1`): `rows` for a planner connector's trend tools (`niche.md`).
- `hooks.md`: the niche's voice sheet (the same `rea-voice` block, so `draft_check.py` reads it).
- `NICHE.md` and `report.html`.

A post run adds `post_probe.json` (`rea-viral/post-probe@1`: `status`, `post` with its `ratio`, `usual`,
`usual_from_posts`, `rank_among_creator`; `creator`; `words` with `flags` and `numbers` beside the creator's usual;
`repeats`; `creator_posts`), `POST.md` and a short `report.html`.

## Hand-over files (build_report.py writes them; a planner connector takes them)

Every report (`report.html`, one file with its pictures inside) gets its light page (`report-light.html`: no
pictures, only the data it draws), a cover when the run has a picture of its own (`report-cover.jpg`, from
`account.json` `picture_file` or the post's cover) and three files, all rewritten at every build:

- `report_record.json` (`rea-viral/report-record@1`): `report`, the record a tool that keeps reports takes: `kind`
  (`account`, `post`, `niche`; `words` you set yourself), `title` (160 characters at most), `subject` (`network`,
  `handle`, `url`, `niche`; 300 each), `summary` (600 at most), `read` (`posts`, `creators`), `provider` (60 at most),
  `cost_usd` (as reported; null when unknown), `skill` (`name`, `version`), `brief` (below). Beside it: `file` (the
  page: `path`, a suggested `name`, `type`, `size`), `light` (the light page, the same fields), `cover`
  (`path`, `name`, `type`, `size`, `from`, or null), `brief_file`, `formats` (`radar_rows.json` and how many rows).
  You add `by` and `took_s`; the planner adds the id, the file references and the dates.
- `brief.json` (`rea-viral/brief@1`): the short view of the report a planner's panel draws, built by `brief.py`
  from `findings.json` and the measured numbers, never by hand, all plain text: `answer` (400 characters at most),
  `numbers` (6 at most of `{label (24), value (16)}`), `worked` and `not_worked` (6 at most each of `{title (80),
  stat (40), note (240), label: MEASURED | SEEN | INFERRED, format?}`; `format` is the key of a row of
  `radar_rows.json`), `plays` (5 at most of `{title (80), note (240)}`). The measured items come first (the formats,
  the flops, what lifts or sinks), then your claims; an empty part says "Not enough data" or "Nothing measured under
  the usual".
- `radar_rows.json` (`rea-viral/radar-rows@1`): `kind`, `note` (why there are no rows, when there are none) and
  `rows` (60 at most), each in the planner's saved-format shape: `key` (`f_` and 12 hex for a format, the same on
  every build; `<network>:<post_id>` for a post run's own format), `source: "report"`, `url`, `platform`, `post_id`,
  `creator` (`@handle`), `title`, `text` (the face post's caption, 5,000 at most), `state: "link"`, `numbers`
  (`views`, `likes`, `comments`, `shares`, `saves`, `followers`, `at`), and `format`: `name`, `niche`, `creators`,
  `lift`, `trend` (`rising`, `fading`, `steady`), `beats` (`[{t, d, what}]` from the recipe: `t` is TEXT, minutes and
  seconds, `"0:02.2"`; `d` the seconds until the next beat; `what` "hook: …"), `hook`, `proof` (the links of the posts
  that prove it, 20 at most). The planner adds the report's id, the dates and the kept media.
