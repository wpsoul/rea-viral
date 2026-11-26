# REA Viral in two minutes

## What it is

A skill: written instructions plus small scripts that an AI agent follows. You ask it something about social media
content; it reads public posts, measures them, watches the videos that matter, and hands you a report you can open in
a browser, plus the files behind it. It works with whatever reading tools your agent already has, and it never asks
you for a password or a key.

## Four ways in

You do not pick from a menu. The skill picks the way from what you wrote.

1. **An account** ("why does @someone grow?", "what works for my account and what doesn't?"). The main way. It reads
   the account's posts for up to a year and says what worked and what did not. Say "REA Viral: why is @someone
   growing" for **growth mode** on top: the 3 to 5 things that drive the growth (posting pace, questions to a named
   crowd, who reposts, replies, speed), each with an example and real numbers, what doesn't move, what to copy, and a
   reply you can paste (`GROWTH.md`). You can also turn any run into a 1080 × 1350 post picture (`post_card.py`,
   22 layouts across 9 report types × 7 styles).
2. **One post** (a link). It says why that post did better than the creator usually does, what in it did not, and
   whether the creator repeats the trick.
3. **A niche** ("what works now in AI video editing?", or "is `<topic>` still worth posting?"). It finds posts of the
   niche, reads each creator's recent posts, shows which video formats are working right now across many creators and
   which are fading, and can run a fast **Topic check** (`topic_check.py`) to judge whether a rising topic is still
   open or already saturated.
4. **Words only** ("how do they write?", or your own draft). It measures how posts open and are written, and checks
   drafts.

## What comes out of each: a report

| Way | Its report |
|---|---|
| An account | The **Account report**: what worked (its formats, its **Format map**, the posts that brought followers, how it writes, how it uses its comments) and what did not (the formats under its usual or fading, its flops and what the watched ones show, what sinks in its words), and a short list of plays |
| One post | The **Post report**: how far it beat the creator's usual, why (from watching it), what in it sits under the creator's usual, its words beside the creator's usual, whether the creator repeats it, its recipe; one short page |
| A niche | The **Niche report**: the formats of the niche, each placed by how many creators use it and how much it lifts them, rising or fading this month; what did not work; a gallery with the posts that prove each format; the posts that beat their own creator's usual; the opening lines of the winning posts; who to watch; a recipe for each format |
| Words only | A voice sheet or the niche's hooks, and drafts that pass a check (or your own draft checked for general craft) |

Each report is **one file**: you can send it, keep it, or open it from a download, and its pictures come with it
(small copies, each linked to the original post). If you use a planner that keeps reports, such as [GreenLight Pulse](https://greenlightdash.pro/),
the agent saves the report there (its short brief shows in the planner, the full page opens in the browser) and the
formats it found go to your saved formats (in Pulse, the Format Radar tab). Without a planner the files are the
hand-over.

## How it stays honest

- A post counts as a **trend only when it beats its own creator's usual**. A small creator's post at five times their
  normal views outranks a big creator's normal post, even with fewer views.
- **What did not work is said as plainly as what worked**, by the same rules. A flop shows what was in it, never on
  its own why it flopped.
- A format counts as **a format of the niche only when at least 3 creators use it**. One creator's habit is shown as
  theirs.
- **Every number comes from a script**, and every claim is marked: measured, seen (with a link), or reasoned (with
  the reason). When there is not enough data, the report says so.
- **Nobody's video is copied.** Reports show small covers that link to the original posts.

## Making a format yourself

After the report, the skill asks once whether you want to make one of the formats with your own clips:

- **Basic**: a simple web page turned into a video.
- **Standard**: an editable video project, in **[GreenLight Motion](https://greenlightdash.pro/)** or
  **HyperFrames** (your choice).
- **Advanced**: [GreenLight Dash](https://greenlightdash.pro/)'s Rebuild by Style, which rebuilds the style of a post
  for your product.

Each result is checked against the format's timing.

## What is proven and what is not

Version 0.4.1 (2026-11-23) fixes what a real run on an X niche showed: every cover now lands on numbered sheets that
are checked; only a post's own video is watched (never the video a post quotes); covers are fetched like a browser;
the chart's names stay inside it, on a phone too; the corner "Fading" is now "Overused", and rising, steady and fading
only ever say the direction; replies are left out and counted; "Let's connect" is no longer read as a name; a speech
rate without subtitles is "not measured"; seed accounts are checked first; a new check of the format grouping; and
every report says what its run did not read. Each fix has its own test on made-up data.

Proven by running it (2026-11-19, version 0.4.0; the tests rerun for 0.4.1):

- **Made-up data with planted answers**: an account where one format really lifts, one fades, and one sits under the
  usual and holds four of the five flops, and an X account whose posts with a link sink: the Account report's "What
  did not work" finds exactly those. A niche of 11 creators where one format really rises across five of them, one is a single
  creator's habit, one fades, one opening line really lifts, and a small creator's outlier must outrank a big
  creator's normal post. The same for one post, both when it beat its creator's usual and when it did not.
- **One file**: every report page is opened alone, in an empty folder, in a browser at desktop and phone width; all
  its pictures load from inside it. An account with 142 heavy covers (up to 2 MB each) and 14 frame sheets makes a
  2.4 MB page; without ffmpeg the big pictures are left out, named, and the page stays at 0.3 MB.
- **The planner files**: the report's record, its short brief within the planner's limits, and the formats as rows,
  checked field by field, the same keys on every rebuild.
- **All of it in this repository**: 131 tests on made-up data (`tests/run_all.sh`). Earlier versions were also tried
  on real public data read free (a YouTube Shorts niche, one of its Shorts, Duolingo's YouTube Shorts and an X
  account); those rows are not in this repository.

Not proven yet:

- Saving into a real planner connector: the files match the shape agreed for Pulse's report and format tools, and no
  live planner was called.
- TikTok, Instagram, Threads and LinkedIn with a live paid data source (no paid call was made).
- A Standard remake made with HyperFrames end to end (the hand-off is written from HyperFrames' own instructions).
- Whether a format found rising this month keeps rising: that needs the same niche read again in a few weeks.
