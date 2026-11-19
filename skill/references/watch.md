# Scout and Watch: catch the jump when it happens

Watch notes the follower count of every watched account on a schedule, keeps it, and spots a jump the day it happens,
so the user can make something like the post behind it while it still works. Scout finds accounts worth watching.
A skill wakes only when an agent calls it, so Watch is a small script (`scripts/watch.py`, plain Python, no model)
plus a schedule you set up once, with the user's yes.

## Set it up

Use one Watch for all accounts: `rea-viral/watch/` beside the run folders (the analysis of `rea-viral/<network>-<handle>/`
reads `../watch/counts.csv` too, so a watched account's posts become MEASURED over time).

1. **The reader** (how counts are read; no provider is built in):
   - **A command** that prints one JSON object per account: `{"followers": 12345, "exact": true, "posts_count": 321,
     "profile": {"bio": "…", "link": "…"}, "recent_posts": [{"post_id", "url", "published_at", "views"}],
     "cost_usd": 0.001}` (only `followers` is required). Free for YouTube:
     `python3 SKILL_DIR/scripts/watch.py init rea-viral --reader-command "python3 SKILL_DIR/scripts/readers/ytdlp_reader.py followers {network} {handle}"`.
     Any script of the user's that calls their data tool works the same way.
   - **A file**, when the counts come from your own scheduled runs (a chat or cloud agent whose connector a script
     cannot call): `watch.py init rea-viral --reader-file watch/inbox.csv`. Each scheduled run appends rows
     `read_at,network,handle,followers,exact,posts_count,source` and then runs `watch.py run`.
2. **The list:** `watch.py add rea-viral tiktok examplebrand` (the user's own list: competitors, accounts they admire),
   or `--source scout` for candidates.
3. **The first read:** `watch.py run rea-viral --all`, and `watch.py status rea-viral`.
4. **The schedule**, the user picks one:
   - **The computer's own scheduler** (reads only while the computer is awake):
     `watch.py schedule rea-viral --print launchd` (macOS), `--print cron` (Linux), `--print schtasks` (Windows) show
     exactly what will be installed and how to take it down. Install only after the user says yes:
     `watch.py schedule rea-viral --install launchd --yes` (or `cron`). Windows: run the printed `schtasks` line.
   - **The agent's own scheduled runs** (reads with the computer off, uses the agent's connector):
     `watch.py schedule rea-viral --print agent` prints the task text to schedule in the agent's scheduler.
   It runs hourly; each account is read only when it is due.
5. **Taking it down:** `watch.py schedule rea-viral --remove launchd --yes` (or `cron`), the printed `schtasks /Delete`
   line, or delete the agent's scheduled task. Tell the user how, when you set it up.

## What it does on each run

- Reads the accounts that are due and appends `watch/counts.csv` (`ok`, `error`, or `gap` for a read missed by more
  than 1.5× its pace; a gap is never filled with a guess).
- Keeps every profile it reads (`watch/profiles/`), so bio and link changes show.
- **The jump rule:** the day's gain (now against the reading 20 to 36 hours before, scaled to 24 h) is at least
  3× the usual daily gain (the median rate of the last 14 days, the last day left out; 3 days of history needed),
  at least the usual gain plus 4× the day-to-day wobble (a robust standard deviation of the daily gains, so a small
  account's noise does not fire it), and at least the floor: max(50, 0.1% of followers, 2× the rounding of a rounded
  count). One alert per account per
  24 h unless the gain grows by half again. The numbers live in `watch/config.json`; tune them from the first weeks of
  real counts.
- **The pace:** once a day; every 4 hours for 24 h after a jump, or while a post under 48 h old runs at 3× the median
  of the account's other recent posts.
- **On a jump:** writes `watch/jumps/<date>-<network>-<handle>.md` (who, how much against the usual, the posts of the
  last 72 hours against the account's older posts, profile changes) and a line in `watch/alerts.jsonl`, runs the
  user's `notify` command (`config.json`: `{"notify": {"command": ["osascript", "-e", "display notification \"{handle} jumped\""]}}`),
  runs `on_jump` if set (a command that wakes the user's agent), and exits 10.

## When you are woken by a jump

Read the jump file. Name the cause at the MEASURED level: the post or posts whose timing and views fit the gain. When
nothing was posted, look at the other actions: a collaboration, a mention, an ad in the ad libraries, the bio or link
change in the file. Deep-read that post (steps 4 and 5 of the run), write its recipe, and draft a version for the
user. An unattended run asks nothing: it writes the files and stops.

## Scout: accounts worth watching

Candidates, cheapest first: small accounts behind posts far above their size in trend searches the user already runs;
creator search tools by niche and size (they give candidates, not growth); the user's own list. Add them with
`--source scout`. After 7 days of counts, `watch.py prune rea-viral --days 7 --keep 0.1` keeps the top tenth by
relative gain and drops the rest. Nothing sells "fast-growing accounts" for these networks: the watch is the filter.

## Cost and limits

A profile read costs about $0.001 on a paid reader (free with the yt-dlp reader on YouTube): 100 accounts read four
times a day is about $0.40 a day. Big accounts show rounded counts (12.3M moves in 100,000s), so only a large jump
shows there; small and mid accounts have exact counts. The delay of an alert is the reading interval plus the time the
platform takes to count followers.
