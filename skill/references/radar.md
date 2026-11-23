# Formats: one account's Format map and the formats of a niche

Two views, one file shape (`radar.json`), one recipe shape (`formats/<id>.md`):

- **The Format map** is what an account run (and a post run) draws: **that account's own formats**, each against the
  account's own baseline. `radar.json` `scope: "account"`. Its chart is "Format map" in the Account report.
- **The formats of a niche** are the many-creators view of a niche run: which formats are working NOW across the
  niche, each post against its own creator's usual, each format with the creators behind it. `radar.json`
  `scope: "shared"`. Its chart is "Formats of the niche" in the Niche report.

Both come from `radar.py`, which picks the scope from the folder (`niche.json` present: shared). The file name, the
keys and `scope: "shared"` stay as they are, so older run folders and the planners that read this shape still read
it. ("Format Radar" is not a name in this skill: it is the GreenLight Pulse planner's tab, where formats can be saved,
`connections.md`.)

## What a format is

A repeatable container: a kind of **hook**, a **structure**, a **look** and a **length**. "Three mistakes, talking
head over a screenshot, 25 s" is a format. "A video about pricing" is a topic, not a format. On a text network the
container is written: "a short reaction line quoting an older post of its own", "a numbered playbook of 5 phases,
1,500+ characters", "an article with a 'dense guide' title".

Group the window's posts after the deep read, with the covers sheet beside you. Name a format only for something the
account repeats; leave one-offs out (they show as "belong to no format"). A numbered series (Part 1, Episode 2) is a
format of its own and also goes under `series` in `formats.json`. Write in each format's `basis` what showed you the
container (which frames, which covers).

**Check the grouping before you measure it** (0.4.1). Give each format its `examples` (the post ids that show it best)
and, when its first line or its words say it, a `match` (`data-shape.md`, formats.json), then:

```
python3 SKILL_DIR/scripts/formats_check.py <run>            # --write takes each match's posts; --json for the file
```

It prints, per format, its posts, what its `match` takes and three sample posts with their first lines; the posts two
formats both take; the posts in no format with the openers they repeat (a format you missed, or one-offs); and it
fails when an example does not fit its own format. Fix what it shows (move a post, sharpen a match, name the missed
format), run it again, then `radar.py`. It is a tool for your judgement, not a classifier: the grouping stays yours,
and a format whose container is in the frames, not the words, needs no `match`.

## The Format map: what radar.py measures on one account (MEASURED, per format)

| Key | Meaning |
|---|---|
| `posts_total`, `share` | Its posts in the window, and their share of the window's posts |
| `lift` | The median of its posts' ratios (each against its own baseline) |
| `hit_rate` | The share of its posts at 2× or more |
| `direction` | Median ratio of its last third ÷ its first third (by date; 6+ scored posts), `rising` ≥ 1.33, `fading` < 0.75, else `steady` |
| `follower_pull` | MEASURED: followers above the usual pace in the 72 h after its posts, when half or more of them are measured; else ESTIMATED: the mean estimated score (INFERRED); else unknown |
| `effort` | Your call in `formats.json`: low, medium, high |
| `length_s_median`, `probe` | Its posts' median length; median cuts per 10 s, words per minute and first cut of its watched videos |
| `examples` | Its three best posts, with links and covers |

## The four corners, and the direction

The chart: across = how often (split at 15% of the window's posts); up = lift (split at 1×, the account's own usual);
bubble size = follower pull; arrow = direction. **A corner says only where the format sits** (how often, how much it
lifts); **the direction says where it is going** (`rising`, `steady`, `fading`). The two never mix: a format in
Scale it can be fading, a format in Overused can be rising.

| Corner | Where it sits | Reads as |
|---|---|---|
| **Scale it** | often and lift ≥ 1 | Make more of it (unless it is fading: then say so with it) |
| **Underused** | rare and lift ≥ 1 | It works when used: test it more |
| **Overused** | often and lift < 1 | Used a lot, lifting little: refresh it or use it less |
| **Drop** | rare and lift < 1 | Stop, unless it serves another goal |

Words that changed in 0.4.1: the corner "Fading" is now **Overused** (`quadrant: "overused"`), and it no longer takes
a lifting format whose later posts did worse (that one stays in its corner with the direction `fading`); the
direction "weakening" is now **fading**. `rising`, `steady` and `fading` are only ever the direction, on the chart,
the legends, the chips, `ACCOUNT.md`, `NICHE.md`, `brief.json` and `radar_rows.json`. An older `radar.json` with the
old words is read in the new ones (the corner from its share and lift); it is never rewritten.

A format with fewer than 3 scored posts is listed as "too few posts" and not placed; one with 3 to 5 is placed but
marked `few_posts: true` ("few posts" in the hand-over): show it, never call its corner a finding on its own. Under 20
dated posts in the window, `radar.py` lists the posts and calls no format (`status: too_few_posts`).

The arrow matters: an Underused or Scale it format that is fading is said with its direction, and never put first as
a thing to make more of. The grouping is yours (`grouping` in radar.json says so); the numbers of each group are
MEASURED.

On the chart each bubble carries a number and its name is placed beside it where it fits inside the plot, clear of
the other names and bubbles (on a phone too); a name with no room is listed under the chart by its number, and the
table beside the chart has the same numbers.

The formats under 1× (Overused, Drop) and the fading ones are also listed in the Account report's "What did not
work", each with its three lowest posts and how many of the account's flops it holds.

## radar.json (one shape for both scopes; nothing was renamed, so every older run folder still reads)

```json
{
  "schema": "rea-viral/radar@1",
  "scope": "account",
  "subject": {"network": "tiktok", "handle": "examplebrand", "url": "…"},
  "window": {"from": "2025-11-14", "to": "2026-11-13"},
  "generated_at": "…",
  "status": "ok",
  "rules": {"often_share": 0.15, "strong_lift": 1.0, "fading_direction": 0.75, "rising_direction": 1.33,
            "hit_ratio": 2.0, "min_posts_window": 20, "min_posts_format": 3, "min_posts_direction": 6},
  "axes": {"x": {"key": "share", "split": 0.15}, "y": {"key": "lift", "split": 1.0, "scale": "log2"},
           "size": {"key": "follower_pull.value"}, "arrow": {"key": "direction"}},
  "formats": [{
    "id": "founder-diary", "name": "Founder diary",
    "container": {"hook": "…", "structure": "…", "look": "…", "length": "35-45 s"},
    "recipe": "formats/founder-diary.md",
    "posts_total": 30, "posts_scored": 30, "share": 0.246, "lift": 0.94, "hit_rate": 0.0,
    "direction": 0.45, "direction_label": "fading",
    "follower_pull": {"level": "estimated", "evidence": "INFERRED", "value": 0.12, "unit": "…", "label": "…"},
    "effort": "medium", "quadrant": "overused", "quadrant_name": "Overused", "evidence": "MEASURED",
    "examples": [{"post_id": "…", "url": "…", "ratio": 1.71, "views": 48200, "published_at": "…", "cover_file": "…"}],
    "post_ids": ["…"]
  }],
  "unformatted": {"posts": 44, "share": 0.361, "post_ids": ["…"]},
  "timeline_marks": [{"at": "2026-06-24", "kind": "format", "evidence": "MEASURED", "text": "…"}]
}
```

`scope: "account"` is one account's Format map. `scope: "shared"` is the formats of a niche: the same fields,
with a `subject` that names the niche (`niche`, `slug`, `words`, `tags`, `networks`) and the fields below per format.
The schema name (`rea-viral/radar@1`) and the keys did not change, so version-1 and version-2 run folders validate,
analyse and build as before; only the corner `fading` became `overused` and the direction `weakening` became `fading`
(0.4.1), and an older file is read in those words.

## The formats of a niche (scope "shared")

`radar.py <niche folder>` first recomputes `trends.json` (each post against its own creator's usual, `numbers.md`, "A
niche"), then measures each format of `formats.json` from the window's posts **scored on their creator's own usual**
(posts on the weaker basis or too new are counted beside it, never in it):

| Key | Meaning |
|---|---|
| `creators`, `by_creator` | The creators with scored posts in it, and per creator: its posts, its median ratio, its hits, its best post |
| `creators_share` | `creators` over the niche's creators with scored posts: the chart's across |
| `lift` | The median of the creators' medians: each creator counts once, so one prolific creator cannot carry a format. `lift_posts` beside it is the median over posts |
| `hit_rate`, `creators_hit` | The share of its scored posts at 2× their own creator's usual or more; the creators with at least one such post |
| `direction`, `direction_label` | The median ratio of its posts in the later half of the window over the earlier half (3+ scored posts in each half): `rising` ≥ 1.33, `fading` < 0.75, else `steady`; null = not enough posts |
| `usage_direction`, `halves` | Its share of the niche's posts in the later half over the earlier half; the counts and lifts of each half |
| `first_seen`, `new`, `age_days` | Its first post in what was read (not the first ever made); `new` = first seen in the later half of the window |
| `niche_format`, `scope_status` | `niche format` with 3 creators or more (and 3 scored posts); else `few creators` (2), `creator habit` (1) or `not scored` |
| `examples`, `proof` | Each creator's best post of it, best first (the gallery's proof spans creators); every scored post, best first |
| `weaker_basis_posts`, `too_new_posts` | Its posts that could not be scored against their own creator, counted apart |
| `effort`, `probe`, `length_s_median` | As for an account; the probe numbers come from the watched videos in the creators' folders |

**The corners** use the same four names, by position only; across is how many of the niche's creators use it, split
at 40%; up is the lift, split at 1× (each creator's own usual). The direction (`rising`, `steady`, `fading`) is the
arrow, never the corner:

| Corner | Where it sits | Reads as, for a niche |
|---|---|---|
| **Scale it** | 40%+ of the creators, lift ≥ 1 | Widely used and working: make it now (unless it is fading: say so) |
| **Underused** | under 40% of the creators, lift ≥ 1 | Works where it is used, few use it yet: an opening |
| **Overused** | 40%+ and lift < 1 | Everyone has it, it no longer lifts: refresh it or skip it |
| **Drop** | under 40%, lift < 1 | Skip it |

Only creators with posts in the window count, across and toward the 3 creators: a seed account that was not found or
had no post in the window is named in the report and counts nowhere (`niche.md`, step 2).

A format with fewer than 3 creators is not placed: `quadrant: "too_few"`, `quadrant_name: "Not a niche format:
creator habit"` (or `few creators`), listed under the chart and in the gallery, never called a format of the niche.
One with 3 to 5 scored posts is placed and marked `few_posts`. Under 3 creators with their own usual, or under 20
scored posts in the window, `radar.py` calls no format at all (`status: too_few_creators` or `too_few_posts`).
A format of the niche under 1× or fading is also listed in the Niche report's "What did not work", with its lowest
posts. Each format of the niche becomes one row of `radar_rows.json` for a planner (`handover.md`).

**Why 3 creators and 40%.** Two creators can be one copying the other, or one team on two channels; three is the
smallest count that reads as a pattern of the niche, and it stays reachable with the 8 to 12 creators a run reads. At
40% a format is used by 4 of 10 creators: common enough that a viewer of the niche sees it often.

## The recipe: formats/<id>.md

`radar.py` (and `post_probe.py` for a post run) writes a skeleton once and later replaces only its measured parts (the JSON block's `measured` object and
the table between the `rea:measured` markers). You fill the rest from the deep read. The JSON block is what a remake
and `remake_check.py` read:

```json rea-recipe
{
  "schema": "rea-viral/recipe@1",
  "id": "three-mistakes",
  "name": "Three mistakes",
  "length_s": 24,
  "beats": [
    {"at": 0.0, "what": "hook", "text": "the number and the loss on screen"},
    {"at": 2.2, "what": "turn", "text": "the first mistake, on a hard cut", "cut": true},
    {"at": 17.0, "what": "payoff", "text": "the fix"},
    {"at": 22.5, "what": "ask", "text": "comment a word"}
  ],
  "cuts_per_10s": 2.5,
  "words_per_minute": 170,
  "hook_pattern": "…", "caption_style": "…", "sound": "…", "ask": "…",
  "examples": ["post ids"],
  "voice": "voice.md",
  "tolerance": {"length_pct": 10, "cut_s": 0.25, "cuts_per_10s": 1.0, "words_per_minute_pct": 15},
  "measured": {"…": "radar.py owns this"}
}
```

`voice` links the account's voice sheet (`voice.md`), or for a niche format the niche's hooks (`hooks.md`): the recipe
holds the container, the voice sheet how its words are written; a draft or a remake follows both. A niche recipe's
`measured` also carries `scope: "shared"`, `creators`, `by_creator`, `direction_label`, `first_seen` and `new`, and its
beats must hold on watched posts of at least two different creators. Start `length_s` and `cuts_per_10s` from the measured medians; change
them only with a reason you write in the prose. Mark a beat `"cut": true` only when the watched videos show a hard cut there. Below the block, in prose: the
beats as seen (SEEN, with the posts), the caption style, the pace, the sound, and **what not to copy** (a face, a
mascot, a voice, an authority the user does not have).
