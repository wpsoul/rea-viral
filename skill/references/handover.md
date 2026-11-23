# Your reading (findings.json) and the hand-over: the reports

Every way in ends the same way: your claims in `findings.json`, then `build_report.py <run>`, which picks the report
from the folder: the **Account report** (an account folder), the **Post report** (`post.json`) or the **Niche report**
(`niche.json`). Each is `report.html`, ONE file, with what worked beside what did not; beside it a layered file for
agents and the files a planner connector takes. A planner shows a report two ways: its short brief (`brief.json`) in
its own panel, and the page itself, opened in the browser as the Extended report.

## findings.json

The account run's sections are below. **A niche run** uses `headline`, `formats` (your reading of each format; add
`"format": "<id>"` when a claim is about one), `did_not_work`, `hooks`, `creators` (who to watch, and why), `plays`
and `not_read`. **A post run** uses `headline` (why this one worked), `mechanisms` (each reason), `did_not_work`,
`writing` (its words) and `not_read`. Every section takes the same claim shape and the same checks.

```json
{
  "schema": "rea-viral/findings@1",
  "headline": {"text": "…", "evidence": "INFERRED", "basis": "…", "posts": ["…"]},
  "mechanisms": [{"title": "Short wins", "text": "…", "evidence": "MEASURED", "from": "analysis.json#by_length"}],
  "did_not_work": [{"title": "The diary fades", "text": "…", "evidence": "MEASURED", "from": "radar.json#formats.founder-diary.direction"},
                   {"text": "The two flops watched open on a slow wide shot with no words for 3 s", "evidence": "SEEN", "posts": ["…", "…"]}],
  "writing": [{"text": "…", "evidence": "MEASURED", "from": "writing.json#features.opens_number.with.lift"}],
  "comment_tactics": [{"text": "…", "evidence": "SEEN", "posts": ["…"], "quote": ["the comment's words"]}],
  "timeline_notes": [{"text": "…", "evidence": "MEASURED", "from": "analysis.json#timeline.rhythm"}],
  "plays": [{"title": "…", "what": "…", "evidence": "SEEN", "posts": ["…"], "effort": "low",
             "first_result": "what to look for, and when", "dont_copy": "…", "prompt": "a ready prompt"}],
  "plan_14d": [{"day": 1, "do": "…"}],
  "not_read": [{"what": "Follower history", "why": "no source gives daily counts for this network"}]
}
```

`did_not_work` is optional, and new in version 0.4.0: a folder without it builds exactly as before.

### A claim

| evidence | needs | example |
|---|---|---|
| `MEASURED` | `from`: the file and key a script wrote | `"from": "radar.json#formats.three-mistakes.lift"` |
| `SEEN` | `posts` (ids) or `links`; `quote` when you quote words | a frame, a comment, a caption |
| `INFERRED` | `basis`: what you reasoned from | "the format's lift and the frames of 4 outliers" |

`validate.py` (and so `build_report.py`) refuses a claim without its label, a MEASURED claim whose file does not
exist, a SEEN claim without posts or links, an INFERRED claim without a basis, and a `quote` that is not in a comment
or caption of the cited posts. The same for every section, `did_not_work` included.

### What to write

- **headline**: the answer in one or two sentences. Usually INFERRED, with the measured basis named. It becomes the
  report's summary for a planner (600 characters at most, with the first `did_not_work` line after it when it fits).
- **mechanisms** (what worked): the account as a system: the promise in the bio, where the link leads, the formats,
  series, rhythm, how the comments are run, cross-posting, collaborations, and paid pushes when an ad library was
  read. Each names the posts that show it. Test each against the ordinary posts and flops you watched: a mechanism the
  flops share too is not why it grows.
- **did_not_work** (what did not work, a part of its own): the formats under the usual or fading (MEASURED), what the
  flops you watched show (SEEN, never a cause from one flop), what sinks in the words (MEASURED for what
  `writing.json` marks `sinks`; else say nothing sinks, and give leads as leads), and "not enough data" where it is
  the truth. The report draws the measured part by itself (below); write what you read in it, best evidence first.
- **writing**: how it writes (`writing.md`): MEASURED only for what `writing.json` marks `lifts` or `sinks`
  (or a usage count); SEEN for what the outliers' and flops' texts show, with the posts and the words quoted; INFERRED
  for the rest. A lead that did not pass (few posts, chance too high) is written as a lead, with its numbers.
- **plays**: ten at most, best first. Each: the evidence, the effort, the first result to look for, what not to copy,
  and a prompt the user can paste into their own agent. Write them for the user's account when they gave one.
- **plan_14d**: only when the user gave their own account.
- **not_read**: every source, video, network or period you could not read, and why. The page shows it. Beside yours,
  every report adds the run's own "not read" lines, MEASURED, from what happened in this run and only then: no
  follower history read, threads that came as their first part only, carousels read by their cover only, watched
  videos with no subtitles (words per minute not measured), picked posts whose video was not known to be their own,
  covers not saved (with their status), replies left out of the numbers, creators read as a sample, and in a niche the
  seed accounts not found or with no posts in the window. A line you already wrote yourself is not repeated.

## What did not work, as the reports draw it

The scripts' part, MEASURED (and SEEN from the notes of the watched flops), drawn by every report under the heading
"What did not work", with your `did_not_work` claims on top:

| Report | What it lists | From |
|---|---|---|
| Account | The formats under 1× the account's usual or fading (corner, lift, direction, how many of the flops are in it, its three lowest posts; `few posts` marked); the flops (`ratio` 0.5 or under: how many, by format) and the lowest posts the deep read picked, with what the watched ones show; the features of the words that `sinks`, else the leads; the worst first lines | `radar.json`, `analysis.json#flops`, `videos/<id>/notes.json`, `writing.json` |
| Post | The post itself when it sits under its creator's usual; the format's repeats under the usual; the words this post has or lacks where the creator's posts with them do worse (a lead under 6 posts a side) | `post_probe.json` |
| Niche | The formats of the niche under their creators' usual or fading, with their lowest posts; the flops (each under its own creator's usual) and the deep read's lowest picks; what sinks across 3 creators or more | `radar.json`, `trends.json`, `writing.json` |

Each part says "not enough data", "not measured" or "nothing … sinks" when that is the truth. The words: a corner
(Scale it, Underused, Overused, Drop) says where a format sits; `rising`, `steady` and `fading` say only where it is
going (`radar.md`). A format in a lifting corner that is fading is listed here with its direction, never put first
among what to make.

## build_report.py

Writes, for an account:

- **report.html** (the Account report): ONE file that opens from `file://` with no other file beside it: a planner
  keeps it as one file, and a person opens it from a download. Dark (a Light button switches), no scripts from
  anywhere (fonts from Google Fonts when online). The pictures it draws (the formats' proof posts, the watched videos'
  first seconds, the posts of what did not work) are inside it as small data URIs: with `ffmpeg` on PATH smaller JPEG
  copies (covers 240 px wide, frame sheets 720 px), each under its cap (45 KB, 160 KB), all under one budget, so the
  page stays under 3 MB; without `ffmpeg` only the saved files already under the cap. A picture that does not fit is
  a grey tile, still linked to its post, and the build names it; it stays in the run folder. No video, ever. The
  build prints the page's size. Sections: what worked (why it grows), what did not work, the timeline (each post
  against its baseline, follower counts, measured changes), its Format map with each format's proof posts and recipe,
  which posts brought followers (with the level), how it writes (what lifts and sinks with counts, the best and worst
  first lines side by side, the asks, the voice sheet), the watched videos, the comment tactics, the plays with a Copy
  button, sources, what was not read, and the cost. It draws a copy of the data, so it needs no server; rebuild after
  any change.
- **ACCOUNT.md**: for agents, in layers: Layer 0 the answer in a few lines (what worked, what did not); Layer 1 a
  table of questions with short answers and the file that holds each; Layer 2 the detail (formats table, what did not
  work, claims, plays, not read, files).
- **report-light.html**: the same Account report with no picture inside (each grey tile links to its post) and only
  the data the page draws: the page a chat app sends to a planner as text. `build_report.py <run> --light` writes it
  (and the planner files) alone, with no picture work.
- **report-cover.jpg**: when the run has a picture of its own (`account.json` `picture_file`, the account's
  avatar; a post run: the post's cover), a small copy (480 px wide) for the planner to show beside the report.
- **report_record.json**, **brief.json** and **radar_rows.json**: the planner files (below).

It refuses to build while `validate.py` finds errors or while `analysis.json`, `radar.json`, `comments.json` or
`writing.json` were made from older inputs (it names the script to run again).

## The Niche report and the Post report

- **The Niche report** (`report.html`, `NICHE.md`): what works now (your reading); the chart "Formats of the niche"
  (across: how many of the niche's creators use a format; up: its lift over each creator's own usual; size:
  creators; arrow: the later half of the window against the earlier); the gallery of the formats (each creator's best
  post of each format, as a small picture of its cover or frame sheet, linked to the original post: no video is
  embedded or copied); what did not work; the formats that are one creator's habit, marked; the posts that beat their
  own creator's usual (ranked, with the usual and how many posts it is from; the weaker basis and the too-new posts
  apart); the hooks across creators; who to watch; the ways to make a format; the plays; sources and cost.
- **The Post report** (a short `report.html`, `POST.md`): the post and how far it beat its creator's usual (from how
  many posts), why it worked (your reading and the deep read), its words beside the creator's usual, whether the
  creator repeats it, what did not work, its recipe, the ways to make it, sources and cost.

Both are one file with their pictures inside, like the Account report, each with its light page beside it
(`report-light.html`; a Post report also with `report-cover.jpg`), and refuse to build while a claim lacks its label
or an output is older than its inputs.

## The planner files

Written beside every report, at every build, in the shape a planner connector's tools take (`connections.md`, "A
planner connector"; the fields in `data-shape.md`, "Hand-over files"):

- **report_record.json**: `report` is the record to send to a tool that keeps reports: `kind` (`account`, `post`,
  `niche`; set `words` yourself for a words-only run), `title` (`@handle · TikTok`, a post's first line, a niche's
  name), `subject`, `summary` (600 characters at most), `read` (posts, creators), `provider` (the sources' readers),
  `cost_usd` (the ledger's total, or the sources' costs; null when a price was unknown) and `skill`. Add `by` (your
  own name) and, when you timed the run, `took_s`. It also carries `brief`. Beside `report`: `file` (the full page,
  `report.html`, and its size), `light` (`report-light.html` and its size) and `cover` (`report-cover.jpg`, or null);
  which to send where: `connections.md`, "A planner connector".
- **brief.json**: the short view of the report a planner draws in its own panel (Pulse's sliding panel), built by
  `brief.py` from your `findings.json` and the measured numbers, never typed by hand, plain text under the planner's
  limits: `answer` (your headline, 400 characters at most; with no headline a measured line, "Measured: strongest
  format … weakest …", never empty), `numbers` (6 at most), `worked` and `not_worked` (6 at most each: the measured
  formats and words first, then your claims, each with its label and the number behind it; under `not_worked` the
  number says what is wrong: a fading format's later posts against its earlier ones, a lift under 1, the flops'
  ratio, never a multiple above 1 alone), `plays` (5 at most). So write `findings.json` well: the brief is made from
  it. The fields: `data-shape.md`, "Hand-over files".
- **radar_rows.json**: `rows` to send to a tool that keeps formats: a niche run's formats of the niche (3 creators or
  more, best corner first, 60 at most), an account run's strongest format (Scale it or Underused, 6 posts or more; one that is not fading first), a
  post run's own format (keyed by the post itself). Each row: `key` (stable across builds), `source: "report"`, the
  format's best post as its face (`url`, `platform`, `post_id`, `creator`, `text`, `numbers`), `title`, `state:
  "link"`, and `format` (`name`, `niche`, `creators`, `lift`, `trend` (`rising`, `steady`, `fading`: the direction,
  never the corner), `beats` from the recipe, `hook`, `proof`: the
  links of the posts that prove it). With nothing to offer, `rows` is empty and `note` says why.

## Telling the user

The path and a few lines:

1. The answer (the headline).
2. The strongest format, with its lift, corner and direction.
3. What did not work, in one line: the weakest format with its lift and corner, or what sinks, or "not enough data".
4. The follower evidence: MEASURED for N posts, or "estimated from signals: no daily counts".

Then: `open <run>/report.html`, what was not read, and what it cost (`ledger.py <run> total`). Save to a planner
connector when one is there (SKILL.md, "Handing the report to a planner"). Then the one offer (SKILL.md, "The offer"),
opening with what was saved. A niche run's lines: what works now; the strongest format of the niche with its
creators, lift and direction; what fades; the hook that lifts across creators (or "nothing in the words lifts across
creators"). A post run's: how far it beat its creator's usual and from how many posts; the one reason you can stand
behind; whether the creator repeats it, and whether the repeats lift.
