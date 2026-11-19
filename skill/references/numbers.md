# The numbers (analyze.py)

Every number below is computed by `analyze.py` from `posts.csv`, `account.json`, `comments.csv`, `formats.json` and
Watch counts. It is MEASURED; cite it as `analysis.json#<key>`.

## Which posts count

| Status | Meaning |
|---|---|
| `scored` | In the window, at least 7 days old, has the metric, has a baseline |
| `no_baseline` | Fewer than 5 dated posts before it, or the earlier posts' median is 0 |
| `too_new` | Younger than the network's settling time at `read_at`: its numbers are still growing. Left out of scores and baselines. 7 days; 3 days on X and Threads, where a post gets most of its views in its first day or two (INFERRED from how those feeds work; `--min-age-days N` changes it, and `settings.min_age_days` records it) |
| `no_date` | No `published_at`: left out of baselines and the timeline |
| `no_metric` | The metric (views) is unknown |
| `warmup` | Before the window: feeds the first baselines only |

The metric is `views` when at least 80% of dated posts have views, else `likes` (and a warning says so).

## Baseline, ratio, hits

- **Baseline** of a post = the median metric of the up to 20 eligible posts published before it (at least 5).
  Local, so an account that grew tenfold is judged against its own recent level, not its early one.
- **Ratio** = the post's metric ÷ its baseline. **Hit** = ratio ≥ 2 (also called an outlier). **Flop** = ratio ≤ 0.5.
- `baseline.median_ratio`: the median ratio of scored posts (near 1 for a steady account).

## Rates

Per view: `like`, `comment`, `share`, `save`, `repost`, `quote`, `bookmark`, `engagement` (all known interactions ÷
views, each counted once). Where a network has no shares or saves (X, Threads, LinkedIn), `share` reads reposts and
`save` reads bookmarks, so the follower signals mean the same on every network. Account medians in `rates`. A rate is
unknown when views are unknown or 0.

How the account writes (its openings, shape, voice and asks against its results) is measured by `text_probe.py`:
`writing.md`.

## Buckets

`by_length` (under 10 s, 10-15, 15-30, 30-60, 60 and over), `by_weekday_utc` and `by_type`: posts, median ratio,
hits and flops in each. Use them instead of eyeballing "short videos do better".

## Timeline

- `months`: posts, types, median views, median ratio and hits per month.
- `weeks`: posts per week.
- `marks` (MEASURED changes): **pace** = the 4 weeks after a week boundary post at least twice (or at most half) as
  often as the 4 weeks before, by at least one post a week; **mix** = the month's most common type changed (3+ posts
  in both months). `radar.py` adds **format** marks (a format's first post, when it starts after the window's first
  month) and **series** marks.
- `rhythm`: posts per week, median hours between posts, posts per weekday and per hour (UTC).

## Which posts brought followers

No public source says which post a follower came from. The level says what the claim stands on.

**MEASURED** (or **Watched**, when the counts are our own Watch readings): follower counts cover the post's 72 hours
with no gap over 48 h. The gain between two readings is spread evenly over that interval, and each stretch of it is
split between the posts whose 72 hours are running, in proportion to their views (a post without views weighs its
baseline). Per post: `gain_72h`, `excess_72h` (minus the account's usual pace: the median daily gain of all reading
intervals), `share_of_gain`. Account level: `followers.usual_daily_gain`, `gaps` (never filled), the five biggest days,
and `gain_with_no_post_running` (gain while no post was in its first 72 h: the back catalogue, a collaboration, ads).
Write it as "N followers in the 72 h after the post, split by views", never as "the post brought N followers".

**ESTIMATED** (evidence INFERRED), when no counts cover the post. A score from 0 to 1, the mean of the signals known:

| Signal | 0 | 1 |
|---|---|---|
| `outlier` | ratio ≤ 1 | ratio ≥ 8 (log scale between) |
| `stranger_reach` (views ÷ followers at the time) | ≤ 1 | ≥ 8 |
| `share_rate`, `save_rate` (against the account's median) | ≤ median | ≥ 4× the median |
| `follow_comments` ("just followed", "found you…") | none | 3 or more (only when its comments were read) |
| `raised_baseline` (median of the next 5 posts ÷ this post's baseline) | ≤ 1 | ≥ 2.8 |
| `part2_holds` (a series' first part whose part 2 reached its baseline) | no | yes |

`likely brought followers` = score ≥ 0.5 with 3+ signals; `may have brought followers` = score ≥ 0.3 with 2+ signals;
otherwise no label (an empty `estimate_label` in posts_scored.csv means "no sign", not "unknown"). It is never written
as a count. The followers at a post's time come from the nearest readings
(linear between two within 7 days), else the current count (said so in `followers_at_post.how`).

Measured posts also carry `estimate_for_comparison`, so the estimate can be checked against real gains.

## The deep-read picks

`deep_read`: the top 8 hits by ratio, 4 ordinary posts (ratio 0.75-1.33, closest to 1, spread over the window) and
2 flops (ratio ≤ 0.5, else < 0.75). Watching all three kinds keeps every "this is why it works" honest.

## Statuses of the whole run

`ok`; `private`; `empty`; `no_dates` (no post has a date); `too_few_posts` (under 20 dated posts in the window: the
posts are listed, no pattern is called).

## A niche (trends.py)

Every post of every creator folder, each against **its own creator's usual**:

- **A creator's usual** = the median of that creator's OTHER settled **recent** posts, at least 8 (so 9 settled
  recent posts are needed). Recent = published in the window or the 30 days before it (`usual_since`); older posts
  read are left out (`older_posts_left_out`), because an old era of a channel (another format, before it took off)
  must not set the bar for this month (seen on a real run: a channel's posts from 2025 made this month's posts look
  30 times its usual). It leaves the post itself out, so an outlier does not raise its own bar; how many posts it is
  from is written beside every ratio (`baseline_n`). A post run counts as recent the creator's posts from 60 days
  before the post on.
- **Ratio** = the post's views (likes when fewer than 8 in 10 of the creator's posts show views) over that usual.
  **A trend** (a hit) = 2× or more. The ranked list (`ranked`) is by ratio, never by views: a small creator's real
  outlier ranks above a big creator's ordinary post.
- **The weaker basis**: a creator with fewer settled posts read has its posts measured as views per follower, labelled
  weaker, ranked apart (`leads_weaker_basis`; 2× its followers or more is a lead), and never counted toward a format
  or a hook of the niche.
- **Too new**: younger than the settling time (7 days; 3 on X and Threads). Not scored and not in any usual; its ratio
  so far is shown as a floor (views only grow).
- Only the window's posts are scored; older read posts only feed the usual (`baseline_only`).
- **Statuses**: `ok`; `too_few_creators` (under 3 creators with their own usual); `too_few_posts` (under 20 scored
  posts in the window); `empty`. In the last three no format or hook of the niche is called.

The formats across creators are measured by `radar.py` (`radar.md`, "The formats of a niche") and the words
by `text_probe.py`, with one more rule: a feature lifts or sinks for the niche only when its posts come from 3
creators or more (else "few creators").

## A post (post_probe.py)

The post against its creator's usual exactly as above (the median of the creator's other settled posts from 60 days
before the post on, 8 or more),
its rank among the creator's scored posts, and:

- **its words beside the creator's usual**: every yes/no feature of `text_probe.py` the post has (or that the creator
  usually has and this post lacks), with how many of the creator's other posts have it and the creator's posts' median
  ratio with and without it; every number feature with the creator's median and usual range (8 in 10 of its posts).
  With one creator's posts most of these are leads: under 6 posts on a side is marked so.
- **repeats**: the other posts of its format (your `formats.json`), how many were scored, how many sat above the
  creator's usual (1× or more) and how many at 2× or more, and their median.
