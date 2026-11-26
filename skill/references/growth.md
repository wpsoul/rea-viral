# Growth mode: why an account grows, and what to copy

An account run answers "which formats beat this creator's usual". Growth mode adds "WHY is this account growing, and
what can I copy": the growth mechanisms with their evidence, not only the formats' multipliers.

**Trigger phrases** (any of them is an account run plus growth mode; no setup question beyond the account run's own):

- "REA Viral: why is @handle growing" (the main phrase)
- "REA Viral growth @handle", "why is @handle growing (REA Viral)", the short alias `/rea-viral growth @handle`

**Out**: `GROWTH.md` (why it grows: 3 to 5 numbered mechanisms, each one plain sentence, one example post and 1 or 2
real numbers; what doesn't move: 1 or 2, with the reason; copy this: 3 takeaways; a ready-to-paste reply draft and its
follow-up line), a "Why it grows" block in the Account report (`report.html`) and `growth.json` (every number).

## Step 1: the account run

`account-run.md` up to `radar.py`: the corpus, `validate.py`, `analyze.py`, the covers, the videos, the comments,
`text_probe.py`, `formats.json`, `formats_check.py`, `radar.py`. Growth mode needs the formats (the weakest one is
explained) and analysis.json (the change in posting pace, the posts under 3 days old, the outliers left out).

## Step 2: the growth reads (cheap, and said when a sample)

Run `python3 SKILL_DIR/scripts/growth.py <run>` once: it measures what the corpus already holds and prints `read next:`
lines, the exact posts to read. Then read, with your data connector (`connections.md`, "Growth reads"):

| File | What | How much |
|---|---|---|
| `reposters.csv` | Who reposted (or quoted) the top posts: handle, followers, bio | The posts growth.py names (the 5 most reposted since the change point), **one page each**. List them in `account.json` `growth_read.reposters.posts`, a page that came back empty included |
| `comments.csv` | The replies under the crowd calls, with the author's own (`author_is_creator`) | One page under each crowd call growth.py names; set `comments_read` |
| `replies_out.csv` | The account's own replies to other accounts: when, to whom (followers, bio when a profile read is cheap), in which thread | **One window**: the newest one or two pages of its posts and replies. `growth_read.replies_out.windows`: 1 (a sample) |
| `originals.csv` | The originals of its quotes (and of its replies to big accounts): when posted, views, the author's followers | Each quote of the period; replies to accounts of 100,000 followers or more |

Shapes: `data-shape.md`, "The growth files". Log every paid call with `ledger.py` as always. Never read more than one
page of reposters per post, nor every reply the account ever wrote. Then `validate.py <run>` and go on at 0 errors.

## Step 3: the numbers

```
python3 SKILL_DIR/scripts/growth.py <run>
```

It writes `growth.json` (cite it as `growth.json#<key>`) and `GROWTH.md`. Every number is MEASURED; the posts with
views 1000x the followers or more (`analysis.json#suspect_reach`) are left out of every sum and named.

| Part | Key | What is measured |
|---|---|---|
| Posting cadence | `cadence` | Posts a week (`weeks`, the week still running marked `partial`), per month: posts, views, median views, median replies, posts under 3 days old (`months.<YYYY-MM>`). The change point: analysis.json's strongest rise in pace, 4 weeks after against 4 before (`change_point.at`, `.before`, `.after`), and the real pace since (`change_point.since`). The window's posts before and after it (`before_after`) |
| Concentration | `concentration` | Since the change point (else the last 30 days): the share of views in the top posts (`top_slice`: the top 15% of the period's posts, 3 at least; `curve` for 1, 3, 5, 10; `half`: how many posts make half the views), and what those posts carry (`in_common`: crowd calls, questions, tags, quotes, own video, one-line captions, under 3 days old). What they have in common beyond that is your reading |
| Crowd calls | `crowd_calls` | A post whose first line names a crowd ("AI video creators, ...", "If you're into AI ...") or that promises to reply ("I'll reply to everyone", "let's connect"), with an ask to the reader. Per post: views, replies, the rows of replies read and the author's own among them; `top` is the biggest. The word lists: `data/growth-words.json` (English) |
| Kinds of post | `kinds` | Crowd calls, questions to the reader (not crowd calls), tagged posts, quotes, one-line captions: with against without (scored posts' median ratio, hits; `few_posts` under 6 on a side) and their share of the period's views |
| Tags and credits | `tags` | @mentions in the post and in the author's first self-reply (the earliest of `author_replies`): which posts tag, who is tagged most |
| Repost graph | `repost_graph` | Per post read: the reposters (followers, bio, `big`: 10,000 followers or more and 10x the account's own; `tagged`; `replied_to`), the tagged accounts that reposted (`tagged_reposted` of `tagged`); `best_tagged`, `biggest`, `repeat_reposters` (on 2 posts or more). The account's reposts of itself are left out and counted |
| Replies to others | `replies_out` | How many in the window read, its minutes and the rate an hour, how many accounts, in its own threads, to big accounts, to its circle (accounts that reposted it or that it tagged), by the size of the account answered. `sample: true` when one window was read |
| Speed on big posts | `speed` | Per quote or reply with its original: minutes after the original, the original's views and author, its own views; `big` = 100,000 views or an author with 100,000 followers; `top` = the big quote with the most views |
| The weakest format | `flops` | The format under the usual with 6 scored posts or more and the lowest lift (`radar.json`): its posts against the account's others (tags, crowd calls, asks, quotes, own video, one-line captions, caption length); `lacks` = what the others carry (15% or more) that it has at half or less. "Nothing of its own" (found clips, no own work) is SEEN from its covers or videos, never measured |
| Followers | `followers` | The gain over the follower history when it spans a day or more; else "cannot be measured" (offer Watch) |
| Samples | `limits`, `reads` | What is a sample or was not read, and what to read next |

## Step 4: your reading (findings.json "growth")

Write the sentences; the script fills the numbers. Each number is a placeholder `{key}` or `{key:fmt}` naming a key of
growth.json (`fmt`: `n` 12.1K, the default; `full` 12,061; `pct` 63%; `x` 0.58x; `date` Nov 2; `min` 77; `raw`):

```json
"growth": {
  "why_it_grows": [
    {"title": "Crowd calls",
     "text": "The biggest post names a crowd, asks one open question and promises to answer everyone: {crowd_calls.top.views} views, {crowd_calls.top.replies} replies.",
     "reply": "Your best posts ask one group a question (\"AI video creators, what's your go-to right now?\") and promise to answer everyone. That one got {crowd_calls.top.views} views and {crowd_calls.top.replies} replies.",
     "evidence": "MEASURED", "from": "growth.json#crowd_calls.top",
     "posts": ["<the example post>"], "quote": ["words from that post"]}
  ],
  "doesnt_move": [{"title": "...", "text": "...", "reply": "The meme clips with one-line captions don't land: ...", "evidence": "MEASURED", "from": "growth.json#flops.format", "posts": ["..."]}],
  "copy_this": ["a practical takeaway", "...", "..."]
}
```

- **why_it_grows**: 3 to 5 mechanisms, best first. Each: a `title`, one plain sentence (`text`), its example
  (`posts`, with a `quote` of its words: checked against the post's caption, parts and the author's replies), 1 or 2
  numbers as placeholders, and a short `reply` line for the reply draft: humanized, the numbers with plain words
  around them, written the way a person would say it to the author ("you"), not a bare list of numbers.
  Labelled like every claim (`handover.md`): MEASURED with the growth.json key, SEEN with the posts, INFERRED with the basis.
- **doesnt_move**: 1 or 2, with the reason: the weakest format and what it lacks (`flops`), or a kind of post with
  nothing to show for it.
- **copy_this**: 3 practical takeaways for the reader's own account, from the mechanisms above.
- **Interpretations are INFERRED, with their basis**: "the same circle of tool ambassadors" is inferred from bios and
  repost lists, not measured; say so in `basis`. What the top posts have in common, beyond what `in_common` counts, is
  your reading. A mechanism the flops share too is not why it grows.
- **Only real numbers**: never type a number; write its key. Mark what is a sample and the posts under 3 days old:
  the page and GROWTH.md add a note beside every claim that cites them; in the reply, say "in a 2-hour window" when
  the number is a sample.

## Step 5: the reply draft and the hand-over

Run `growth.py <run>` again. It fills your sentences, builds the reply draft and checks it:

```
Ran your account through REA Viral (free open-source skill for AI agents). Here's what's actually driving your growth:

1. <why_it_grows[0].reply>
2. ...
N. <doesnt_move[0].reply>   (what doesn't work, said in its own words)

Try it on yours: install REA Viral and tell your agent "REA Viral: why is @<their handle> growing".
```

English, 600 to 1,200 characters, the first and the last line exactly as above, no link inside. The link goes in a
separate follow-up line: `github.com/wpsoul/rea-viral`. A draft that fails says why (`NOT READY: ...`, exit 1): fix the
reply lines and run it again. Then `findings.json` (headline, mechanisms, `did_not_work`, plays: `handover.md`) and
`build_report.py <run>`: the Account report gains the "Why it grows" block (the mechanisms, what doesn't move, copy
this, the reply with a Copy button, and the measured parts), `ACCOUNT.md` a line, and `GROWTH.md` is written again.

Tell the user: the path of `GROWTH.md` and `report.html`, the mechanisms in one line each, the reply draft and its
follow-up line, what was a sample or not read, and the cost (`ledger.py <run> total`). GROWTH.md ends with the phrase
that runs it again. To also turn the teardown into a 1080 × 1350 post picture (`post-card.png`), see `post.md`.

## When something goes wrong

| What happens | What to do |
|---|---|
| No change in posting pace | The period is the last 30 days; volume is not a mechanism unless the numbers say so |
| `growth.json was made before ... changed` | Run `growth.py` again (after `analyze.py` and `radar.py` when posts.csv changed) |
| A placeholder has no key | Use a key growth.json has (`validate.py` names it); never type the number |
| `NOT READY: the reply is ... characters` | Shorten or add to the `reply` lines, not the first or last line |
| The reposters of a post cannot be read (a network that shows none) | Leave the post out of `growth_read`; the repost graph says "not read" |
| Only the newest replies can be read | That is one window: `windows: 1`; every reply number is "a sample" |
| A post in the top is under 3 days old | Its numbers are still growing: the note says so; never rank it as a hit |
| No follower history | "Follower growth cannot be measured"; offer Watch (`watch.md`) |
| The account posts in another language | The crowd and question word lists are English (`data/growth-words.json`): say the crowd calls may be missed |
