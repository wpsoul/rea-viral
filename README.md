# REA Viral

**Reverse engineer what goes viral: what worked for an account and what did not, why a post blew up, which formats
and hooks work now in a niche, and how to make the format yourself.**

REA Viral is an agent skill: written instructions plus small Python scripts that an AI agent follows. You ask your
agent a question about social media content; it reads public posts with whatever reading tools it has, measures each
post against its own creator's usual, watches the videos that matter, and hands you a report you open in a browser,
plus the files behind it. YouTube Shorts, TikTok, Instagram, X, Threads and LinkedIn. It never asks you for a key or a
password, and it posts nothing.

## Four ways in

There is no menu. The skill picks the way from what you wrote; when it cannot tell, it asks one line, an account
first.

| You give | It answers | What comes out |
|---|---|---|
| **An account** (the main way): a handle or a profile link | What worked and what did not, and why it grows | The **Account report**: its formats (its Format map) and the ones that sit under its usual or fade, its flops and what the watched ones show, how it writes (a voice sheet) and what sinks in its words, how it runs its comments, which posts brought followers (measured from counts, or estimated and never written as a count), the plays |
| **A post**: one link | Why this one worked against its own creator's usual | The **Post report**: the post beside its creator's usual (from how many posts), what in it sits under that usual, its words taken apart, whether the creator repeats the format and whether it lifts each time, its recipe |
| **A niche**: a few words or tags, a list of accounts, or "what works now in X" | Which video formats and hooks work now across many creators | The **Niche report**: the formats of the niche (each by how many creators use it and how far it lifts them, rising or fading), which fade, a gallery of the formats with the posts that prove each, the posts that beat their own creator's usual, the hooks the winning posts open with, who to watch, a recipe per format |
| **Words only**: "how do they write", "what hooks work in X", or a draft | How an account or a niche writes | A voice sheet or the niche's hooks; drafts in that voice, each checked; your own draft checked against general craft |

## What comes out

Each run writes a folder `rea-viral/<the run>/` beside your own files:

- **`report.html`**: the report, one HTML file that opens anywhere, with what worked beside what did not. The pictures
  it shows (covers, the first seconds of watched videos) are small copies inside it, each linked to the original
  post; no video is embedded. It stays under 3 MB.
- **`report-light.html`**: the same report with no pictures, for a chat app that passes a page as text.
- **`ACCOUNT.md`, `POST.md` or `NICHE.md`**: the same findings for agents, in layers (the answer, where each answer is,
  the detail).
- **The data files** the numbers come from (`analysis.json`, `radar.json`, `trends.json`, `writing.json`, …), a recipe
  per format (`formats/<id>.md`), and the voice sheet or the niche's hooks.
- **The planner files**: `report_record.json` (the report's record), `brief.json` (its short view: the answer, a few
  numbers, what worked, what did not, the plays) and `radar_rows.json` (its formats as rows).

## How it stays honest

- **A trend is a post that beats its own creator's usual**, never the biggest number. A small creator's post at five
  times its usual outranks a big creator's ordinary post with more views.
- **What did not work is said beside what worked**, under the same rules: the formats under the usual or fading, the
  flops (a flop shows what was there, never on its own why it flopped), the words that sink.
- **A format of a niche needs 3 creators or more.** What one creator does is that creator's habit, shown and marked.
- **Scripts do every number.** Every claim is labelled MEASURED (a script computed it), SEEN (a frame, comment or row
  shows it, linked) or INFERRED (reasoned, with the basis written). "Not enough data" is said when it is true.
- **It watches the videos**: cuts, the first three seconds frame by frame, words per minute, the words on screen.
- **Nothing of another creator is copied.** Covers and frame sheets are small pictures linked to the original post,
  and a remake uses your footage, face and words only.
- **No data provider is built in.** The agent uses the data tools it already has, free readers first, reads a paid
  tool's price before calling it, and stops at your spend ceiling. `skill/scripts/readers/ytdlp_reader.py` is one free
  example reader (YouTube).

## Install

The skill is the folder `skill/`. Copy it where your agent looks for skills:

```bash
# Claude Code
mkdir -p ~/.claude/skills && cp -R skill ~/.claude/skills/rea-viral
# Codex and other agents that read ~/.agents/skills
mkdir -p ~/.agents/skills && cp -R skill ~/.agents/skills/rea-viral
```

In a chat app that takes skills as uploads, zip the `skill` folder and upload the zip. Then ask, for example: "Why
does @<account> grow on TikTok, and what doesn't work for it?", "Why did <link> blow up?", or "What works now in AI
video editing on YouTube Shorts?"

## What it needs

| Need | For | Without it |
|---|---|---|
| Python 3.8+ (standard library only) | All the numbers, the reports, Watch | Required |
| A way to read posts: a social data connector in your agent, or `yt-dlp` for YouTube | The posts | The skill says what is missing and what it costs in depth; it never asks for a key |
| `ffmpeg` | Cutting and measuring videos, the covers sheet, the small pictures in the report | Covers and captions only; videos are marked "not read"; the report keeps only pictures that are already small |
| `yt-dlp` | Free YouTube reading (hashtag pages, search, channels), video and subtitle downloads | Use your data connector's links |
| Node 18+, Playwright, Chrome or Edge | The Basic way to make a format | Use another way |
| The HyperFrames agent skills | The HyperFrames way to make a format | Use GreenLight Motion or Basic |
| A planner connector (optional) | Keeping the reports, the formats and the trends in your planner | The files are the hand-over |

## Making a format

After the report the skill asks once whether you want to make one of the formats with your own content, only when a
format's recipe has beats from watched videos. Every result is checked against the recipe's timing
(`remake_check.py`).

- **Basic**: an HTML page rendered to MP4 in a headless browser, frame by frame. The page stays, to change and render
  again.
- **Standard**: an editable video project, your pick of two: [GreenLight Motion](https://www.npmjs.com/package/greenlight-motion) (the open [GreenLight Motion Engine](https://github.com/wpsoul/greenlight-motion-engine); also a chat connector at `https://mcp.greenlightdash.pro/motion`) (a page
  with options and a Render button; the project also opens in GreenLight Dash) or HyperFrames (HTML scenes, with its
  own agent skills and preview).
- **Advanced**: [GreenLight Dash](https://greenlightdash.pro/)'s Rebuild by Style (PRO): the reference post's style
  studied frame by frame and rebuilt for your product. The skill only checks whether the app is running on your
  computer and writes a brief for it; it never starts the app.

## With a planner connector

The skill knows a planner connector by its tools, not by its name, and works the same without one. The example is
**GreenLight Pulse**, a planner your agent works in: it keeps the reports, the saved formats (its Format Radar), the
trends, your drafts and your posting plan, and shows them on a page inside the chat.

- **The connector:** `https://mcp.greenlightdash.pro/pulse`. Add this address as a custom connector in Claude or
  ChatGPT (their connector settings, "Add custom connector"), then ask your agent to open Pulse. Looking around needs
  no sign-in; the first thing you save asks you to sign in with Google, and everything is kept in a folder of your own
  Google Drive, not on our server.
- **The app:** [GreenLight Dash](https://greenlightdash.pro/) has the same Pulse built in, with Format Radar and
  Reports, and stays in step with the chat planner.

What the skill hands to it:

| A tool that | Pulse's tool | What the skill sends |
|---|---|---|
| keeps a report | `save_report` | `report_record.json` (with its brief) and the page: in a chat app the light page as text, with a local planner the full `report.html` by path |
| keeps saved formats | `save_formats` (its Format Radar tab, Saved) | `radar_rows.json`: a niche's formats with 3 creators or more, an account's strongest format, a post's own format |
| keeps trends | `save_trends` | a niche run's `planner_rows.json` |
| adds a post draft | `add_post` | drafts that passed `draft_check.py`, as drafts, never scheduled or posted |

A tool the connector does not have is skipped and its file stays the hand-over. Nothing of yours is sent anywhere
else.

## Files

```
skill/SKILL.md          the map: pick the way in, the rules, the shared steps (start here)
skill/references/       account-run, post-run, niche, writing (hooks and words only), data shape, connections,
                        numbers, deep read, comments, radar (one account's Format map, the formats of a niche),
                        hand-over (the reports, what did not work, the planner files), remake, watch
skill/scripts/          validate, analyze, post_probe, trends, video_probe, covers_sheet, comment_tactics, text_probe,
                        draft_check, radar, build_report (+ report_post, report_niche, page_kit, brief, hand_over),
                        ledger, watch, render_page.mjs, remake_check, check_app, readers/ytdlp_reader
skill/data/             writing-words.json: the word lists (English today; one file to extend and translate)
skill/templates/        basic-format.html: a Basic page to start from
tests/                  the test suite and its made-up data
OVERVIEW.md             the two-minute read
```

## Running the tests

The tests use made-up accounts, niches and posts with planted answers, and check that the scripts find exactly
those answers, that every report page opens alone in a browser at desktop and phone width with no error, and that
the planner files fit each other.

```bash
npm install --prefix tests                      # Playwright, for the pages and the Basic renderer
npx --prefix tests playwright install chromium
tests/run_all.sh                                # needs Python 3.8+, ffmpeg and ffprobe, Node 18+
```

`REA_PLAYWRIGHT=<a playwright folder>` uses a Playwright you already have. Google Chrome adds the MP4 render check.
With the GreenLight Pulse connector's source at hand, `PULSE_MODEL=<its model.mjs>` also checks every planner row and
record against the connector's own model; without it that part says it is skipped.

## Status

0.4.0 (2026-11-19): one account is the main way in, and every run ends in a report: the Account report, the Post
report or the Niche report. Every report has a part of its own for what did not work, beside what worked, measured by
the scripts and read by the agent. The report is one file that opens alone, with a light copy beside it, and every
build writes the files a planner connector takes. Tested on made-up data with planted answers (112 tests in this
repository, every page opened alone in a browser). Earlier versions were also tried on real public data read free (a
YouTube Shorts niche, one of its Shorts, Duolingo's YouTube Shorts and an X account); those rows are not in this
repository.

Not proven yet:

- Saving into a real planner connector: the files match the shape agreed for Pulse's report and format tools, and no
  live planner was called.
- TikTok, Instagram, Threads and LinkedIn with a live paid data source (no paid call was made).
- A Standard remake made with HyperFrames end to end (the hand-off is written from HyperFrames' own instructions).
- Whether a format found rising this month keeps rising: that needs the same niche read again in a few weeks.

## Licence

Apache License 2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE). REA Viral is part of the REA family started by
morluto's REA (Reverse Engineer Anything), with rea-video and rea-growth.
