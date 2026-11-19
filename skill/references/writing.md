# How posts are written: hooks, voice, drafts (from every way in)

Hook lists and writing rules are everywhere, and a list of rules is not evidence. This part measures how posts are
written against their own results: which openings, lengths, line shapes and asks sit on the outliers and which on the
flops, each post against its own creator's usual. It works from every way in:

| Way in | Run | What you get |
|---|---|---|
| An account | `text_probe.py <account folder>` | Its voice sheet, `voice.md`: how this account writes, against its own results |
| A niche | `text_probe.py <niche folder>` | `hooks.md`: what the niche's winning posts open with, across creators (below) |
| A post | `post_probe.py <post folder>` | The post's words beside its creator's usual (`post_probe.json#words`) |
| Words only | Any of the above, or the user's own draft with `draft_check.py --general` | See "Words only" at the end |

Then, on request, drafts in that voice or with those hooks, each checked before anyone sees it.

## Run it

```
python3 SKILL_DIR/scripts/text_probe.py <run>
```

It reads each post's words: the caption; for a text post, the post itself; a thread's parts; the author's own later
replies; and a watched video's first line on screen when the deep read wrote it down (`notes.json`
`seen.first_line`). It recomputes the numbers first, then writes `writing.json`, `posts_text.csv` (every post's
features, to check any number by hand) and, the first time, a skeleton `voice.md`.

## What it measures (writing.json, MEASURED)

| Group | Features |
|---|---|
| The first line | its length in characters and words; what it opens with: a number, a result in numbers ($, %, 10x, 10k followers), a time span, a question, "how", "you", "I"/"my", a name or @handle, a quote mark, a negation (stop, don't, never, no), a command |
| Shape | length (links left out), lines, paragraphs, the longest paragraph in lines, words per sentence, the share of lines of 50 characters or fewer, a list, line breaks at all, thread parts, quoting its own earlier post |
| Voice | "you" against "I/we", questions, commands, numbers per 100 words, emoji, hashtags, links, @mentions, a link put in its own reply at once |
| The ask | is there one, where (first third, middle, end), which kind (follow, reply or comment, save or bookmark, share or repost, click, DM, buy or sign up); an ask in the author's later reply |
| What the text pulls | saves (bookmarks on X) per like, replies per like, shares (reposts) per like, quotes per like: for the account, and for the posts with and without each feature |

The openings are the ones the script counts, nothing more. The word lists live in ONE file,
`SKILL_DIR/data/writing-words.json`, so they can be extended and translated.

**Languages.** The lists cover English. A post's language is the network's own tag when it gives one, else the
lists' common words. In any other language every word-based feature is unknown (`null`), never guessed; lengths,
lines, numbers, question marks, emoji, hashtags, links and mentions are measured in every language. Say which
languages were covered in the report (`writing.json#language`).

**Unknown is not zero.** A network that shows no saves or shares has those signals unknown, not 0.

### How each feature is judged

For a yes/no feature: the posts with it against the posts without it, each post's ratio being its views over the
median of the 20 posts before it (exactly as a format is measured). `with.lift` is the median ratio of the posts with
it. A number feature (a length, a share) is split into three groups of posts by its value (low, middle, high) and each
group measured the same way.

| Verdict | When |
|---|---|
| `lifts` / `sinks` | all of: 6+ scored posts on each side; their median ratio at least 1.25x the account's usual post and 1.25x the posts without it (at most 0.8x for sinks); a difference this large would come from posts sorted at random less than 1 time in 100 (`chance`, a rank test); and it still holds once every feature checked is counted (with 30 or more features checked at once, a few would pass the 1-in-100 test by luck) |
| `no clear difference` | tested, and one of those failed. `note` says when only the last one failed |
| `few posts` | under 6 scored posts with it: shown, never a finding |
| `nearly always`, `always`, `never` | under 6 posts without it, all posts, or none: nothing to compare, but `never` is what the account never does |
| `unknown` | the language is not covered, or the network gives no number for it |

A number feature that lifts carries a `winning_range` (the group or next-door groups that lift, with the weakest group
beside it).

**What the numbers cannot do.** They find what goes with what, never why. Two features on the same posts (an opening
that always comes with a list) cannot be told apart: `overlaps` lists them. A format can carry a feature (every post
of a lifting format opens with a number): read `radar.json` beside it. And the author's later reply is often added
because a post was already doing well: an ask in a reply posted hours later cannot be why the post took off, however
high its lift (`asks.later_replies`, and check `minutes_after` in posts.csv).

## Read the outliers and the flops side by side (SEEN)

`writing.json#first_lines` holds the 8 best and 8 worst first lines with their ratios. Read them, and the full texts of
the deep-read posts, side by side: what the hits share that the flops lack, and what both share (then it is not why).
Write what you see with the post ids. Keep three kinds of claim apart:

- **MEASURED:** a verdict or a number from `writing.json` (`"from": "writing.json#features.opens_number.with.lift"`).
- **SEEN:** what the texts show, with their post ids and the words quoted (`quote` is checked against the posts).
- **INFERRED:** your reasoning, with its basis: "the hits all quote an earlier post; 24 of 60 posts are quotes; the
  numbers cannot tell the quote from the hook apart".

Write them in `findings.json` under `writing` (same claim shape as `mechanisms`).

## The voice sheet (voice.md)

The writing twin of a format recipe: every format's recipe links to it. `text_probe.py` writes the skeleton once and
afterwards only rewrites its `measured` block and the table between the markers. You fill the rest.

The JSON block (`rea-voice`) is what `draft_check.py` reads. Its `rules` start from the measured values:

| Rule | Starts as |
|---|---|
| `first_line_chars` | the first line's winning range when one is measured; else the account's usual range (8 in 10 of its posts) |
| `chars` | the same for the whole length |
| `max_paragraph_lines` | the top of the winning range of the longest paragraph, else 9 in 10 of its posts |
| `openings` | the openings that lift, then the ones it uses most (and that do not sink) |
| `avoid` | every feature that sinks |
| `asks` | the kinds it uses that do not sink, and where it puts them |
| `length_limit`, `long_posts` | the network's limit for one post (X: 280; `long_posts: true` for an account that can post longer) |

Change a rule only with the reason written in the prose. Below the block, fill:

- **Openings that work:** each measured opening that lifts, with two or three of the account's real first lines and
  their ratios (SEEN, post ids). When none lifts, say so and show the openings it uses most, with their numbers.
- **Its shape:** length, lines, paragraphs, lists, from the measured usage.
- **Its asks:** how often, which kind, where; the later replies and what they cannot prove.
- **What it never does:** the `never` features.
- **What flops when it tries:** features that sink, with the flops' first lines.
- **Where its numbers disagree with general advice:** the account's numbers win. When the editor's pass below says
  one thing and the account's measured numbers say another, write it here, and the rules follow the numbers.

## The editor's pass (general craft, not a finding about this account)

A short checklist for any draft. It is general writing craft, written for this skill; it is not evidence about the
account, and wherever the account's measured numbers disagree, the numbers win and the voice sheet says so.

1. Write to one reader you can picture, not to "everyone".
2. One idea a post. If there are two, there are two posts.
3. Put the strongest line first; the first line has to earn the second.
4. Keep paragraphs short and give each its own line; white space is easier to read on a phone.
5. Plain words over clever ones; cut every word the sentence survives without.
6. End on something that lands: a result, a turn, a line worth repeating. Not a summary of what was just said.
7. At most one ask, and the one that fits what the post is for (followers: follow; a conversation: reply; a resource:
   save; a sale: the link or the DM).
8. Read it on a phone before it goes out.

## Write like it, for the user

Offered once, after the hand-over, in the same message as the other offers (SKILL.md, "The offer"): "Draft posts in this
voice for your account?" An unattended run never asks.

1. Read `voice.md`, the best format's recipe and the user's own account or niche (from setup). Never the reference
   account's words: its craft, never its sentences.
2. Write N drafts (5 unless the user says otherwise) as `drafts/<n>.md` in the run folder. Each names what it uses:

   ```
   ---
   for: the user's account or niche
   network: x
   purpose: followers          # followers, replies, saves, reach, clicks, leads or sales
   ask: follow                 # follow, reply, save, share, click, dm or buy: one, fitting the purpose
   ask_in: post                # or reply, when the voice sheet says asks in the post sink
   openings: [opens_number]    # the measured openings it uses (writing.json ids)
   format: <recipe id>         # optional
   long_posts: false           # true when the user's X account can post past 280 characters
   ---
   The post. A line that is only --- starts the next part of a thread.

   === reply ===
   Optional: the reply the user posts under it (a link, or the ask).
   ```

   Under each draft, in the message to the user, say in one line which measured openings and shape it uses and why.
3. Check every draft: `python3 SKILL_DIR/scripts/draft_check.py <run> --all`. It checks the first line against the
   voice sheet's range, the paragraph limit, the openings it names (measured, and really there), the ask (there, of
   the kind that fits, one only), nothing the account's numbers say sinks, the network's length limit (X's own count),
   no 7 words in a row or sentence of 5+ words from the reference account, the usual marks of machine-written text
   (unless the account's own posts use that mark), and a covered language. **A draft that fails is rewritten**, then
   checked again; never shipped with a warning.
4. Where the drafts go: if you have a **planner connector whose tools add a post draft**, add each passing draft
   there as a draft (never scheduled, never posted; the user approves in their planner) and still keep `drafts/`.
   Without one, the files are the hand-over: give the paths. Either way nothing is posted by you.

## Across a niche: the hooks (hooks.md)

`text_probe.py <niche folder>` measures every post of every creator folder the same way, each post against its own
creator's usual (`numbers.md`, "A niche"). Two differences from one account:

- **3 creators or more.** A feature lifts or sinks for the niche only when the posts with it come from at least 3
  creators. One creator who always opens with a number, and whose posts do well, comes out "few creators" (its
  `verdict_before_creators` says what it would have been): that creator's habit, never the niche's.
- **No line list filled by one creator.** The best and worst first lines hold at most 2 of any one creator.

`hooks.md` is the niche's voice sheet: the same `rea-voice` block (so `draft_check.py <niche folder>` checks drafts
written with the niche's hooks, and its reuse check covers every creator's posts), then your prose: the openings that
work, each with real first lines of at least two creators and their ratios (SEEN, post ids); what the hits share and
what the flops share too; what only one creator does; where the niche's numbers disagree with general advice.

## Words only

When the user asks about words and nothing else:

- **"How do they write?" about an account** → the account run's corpus (`account-run.md`, steps 1 to 3) and step 6
  only: `text_probe.py`, the voice sheet, no videos needed. A text network needs nothing more.
- **"What hooks work in X?"** → the niche run's corpus (`niche.md`, steps 1 to 3) and step 6 only: `text_probe.py`
  on the niche, `hooks.md`.
- **"Write posts like @x" or "with the niche's hooks"** → the above, then "Write like it" with that voice sheet.
- **The user's own draft to check** → with a voice sheet to check it against (their own account's, a creator's, or a
  niche's), `draft_check.py <that run> <draft.md>`. With none, the editor's pass above and
  `draft_check.py <any folder> <draft.md> --general`: the network's length limit, one ask that fits the purpose, no
  marks of machine-written text, a covered language. Say plainly that this is general craft: nothing about any
  account was measured.
