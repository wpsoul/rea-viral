# The post picture: 1080 × 1350 cards for X, Threads and Instagram

Turn an account teardown (growth mode) or a niche run into a shareable 4:5 (1080 × 1350) PNG card, plus a standalone
`post-card.html` (its fonts and icon inside, opens anywhere).

- **Preview all 10 layouts × 7 styles:** open `SKILL_DIR/templates/post/card.html` in any browser (switch type, style,
  and sample vs long-text stress data; click a card for full size).
- **Command:**

```
python3 SKILL_DIR/scripts/post_card.py <run> [--layout t1..t5|r1..r5|all] [--skin cobalt] [--out post-card.png]
```

Default style: `cobalt`. Default layout: `card.json`'s `layout`, else `t1` (teardown) or `r2` (niche report). Pick the
layout from what the run actually proves, not at random.

## Layouts (5 per type)

### Account teardown (`t1`–`t5`) — needs `growth.json`

| ID | Name | When to pick it |
|---|---|---|
| `t1` | **Scorecard** (default) | Clean profile header (name, handle, followers, window) + 3–4 number-led rows + what doesn't work. Best all-rounder. |
| `t2` | **2×2 numbers** | Four equal stat cards + a bottom strip for what doesn't work. Best when 4 mechanisms each have one punchy number. |
| `t3` | **Hero number + checklist** | One giant gradient headline number (e.g. monthly views jump) + short checklist with pill tags. Best when one big number carries the story. Needs `hero`. |
| `t4` | **The proof post** | Mock post card with the winning post's own words, highlighted phrases (`mark`) and stats + 3 number chips below. Best when one post proves how the account grows. Needs `proof`. |
| `t5` | **Numbered editorial** | `01`–`04` + `✕` editorial rows with quotes/sub-lines and right-aligned numbers. Best when short quotes or explanations sell each point. |

### Niche report (`r1`–`r5`) — needs `radar.json` (and optional `writing.json`)

| ID | Name | When to pick it |
|---|---|---|
| `r1` | **Diverging bars** | Horizontal bars left and right of the `1×` usual line. Best when you have both working (≥ 1×) and non-working (< 1×) formats. |
| `r2` | **Works \| Doesn't** (default) | Two side-by-side columns + a bottom banner for a lifting writing habit (`tip`). Best all-rounder when a writing feature also lifts. |
| `r3` | **Ranked, number first** | Ranked list from highest lift to lowest. Best when format names are slightly longer and need easy scanning. |
| `r4` | **The winner + the rest** | Big `#1 format` hero card + 2-column grid of the rest. Best when one format clearly beats everything else. |
| `r5` | **Dot plot** | Log-scale dot plot around `1×`. Best when lifts span a wide range (e.g. `0.5×` to `10×+`). |

## Styles (skins), 7

| ID | Name | Look | Icons |
|---|---|---|---|
| `cobalt` | **Cobalt** (default) | Deep blue glow, Poppins | Blue glass icons |
| `redword` | **Red Word** | Dark obsidian + crimson accent, Red Hat Display | Red glass icons |
| `night` | **Night Notes** | Dark charcoal + light violet gradient & accent, Inter Tight | Violet-tinted glass icons |
| `holo` | **Holo Card** | Dark slate + iridescent conic foil border, Archivo | None |
| `paper` | **Paper Pin** | Off-white graph-paper grid, lime highlighter bold, white cards with shadows, Inter Tight | None |
| `warm` | **Warm Studio** | Warm cream dot-grid, terracotta accent, cream cards with shadows, Inter Tight | None |
| `glass` | **Glass Studio** | Soft frosted blue-grey glassmorphism, translucent cards with deep shadows, Inter Tight | None |

## Writing `card.json`

Run `python3 SKILL_DIR/scripts/post_card.py <run>` once with no `card.json` and it writes a draft `<run>/card.json`
from `growth.json` / `radar.json`, then renders it. Rewrite the draft's lines into plain, humanized sentences before
sharing — never leave raw mechanism titles or bare numbers.

### Account teardown (`card.json`)

Every number uses the same `{key}` and `{key:fmt}` placeholders as `findings.json#growth` (`growth.md`, step 4: `n`,
`full`, `pct`, `x`, `date`, `min`, `raw`). Use `**bold**` where you want emphasis (e.g. the title or hero sub-line).
Any item (or the top-level object) can take per-layout overrides (`"t4": {...}`, `"t5": {...}`).

```json
{
  "schema": "rea-viral/card@1",
  "type": "teardown",
  "layout": "t3",
  "skin": "cobalt",
  "items": [
    {
      "n": "{cadence.change_point.before} → {cadence.change_point.after}",
      "unit": "posts a week",
      "line": "They post almost every day",
      "sub": "Since {cadence.change_point.at:date}. November: {cadence.months.2026-11.posts} posts, {cadence.months.2026-11.views} views",
      "short": "Posts almost every day",
      "tag": "{cadence.change_point.before} → {cadence.change_point.after} / wk",
      "t4": {"n": "{cadence.change_point.after}", "chip": "posts a week, up from {cadence.change_point.before}"}
    }
  ],
  "miss": {
    "n": "{flops.format.lift:x}",
    "unit": "{flops.format.hits} hits in {flops.format.posts} posts",
    "line": "Meme clips don’t work",
    "sub": "One-line caption, nobody tagged, nothing to answer",
    "short": "Meme clips with one line",
    "tag": "{flops.format.lift:x}",
    "say": "Meme clips with a one-line caption don’t work: {flops.format.hits} hits in {flops.format.posts} posts."
  },
  "hero": {
    "n": "{cadence.months.2026-11.views}",
    "line": "views in November, from **{cadence.months.2026-10.views}** in October"
  },
  "proof": {
    "post": "<post_id from growth.json>",
    "mark": ["exact phrase from the post", "second exact phrase"],
    "caption": "Name one crowd, ask one question, promise to answer: their best post.",
    "chips": [1, 3, 4]
  }
}
```

### Niche report (`card.json`)

Each entry names a `format` (an `id` in `radar.json`) or a `feature` (an `id` in `writing.json`); the script fills in
its lift and sorts `works` and `doesnt` highest first. Labels may use `{posts}`, `{creators}`, `{lift:x}`, `{without:x}`
and `{direction}`.

```json
{
  "schema": "rea-viral/card@1",
  "type": "report",
  "layout": "r2",
  "skin": "cobalt",
  "works": [
    {"format": "revenue-line-1", "label": "Own revenue number in line 1"},
    {"format": "list-post", "label": "List post: a colon line, one item per line"}
  ],
  "doesnt": [
    {"format": "short-quote", "label": "Quote with a short take ({posts} posts)", "r4": {"label": "Quote with a short take"}},
    {"format": "one-liner", "label": "One-liner"}
  ],
  "tip": {
    "feature": "has_list",
    "label": "Any post with a list in it ({posts} posts, {creators} creators). Without one: {without:x}.",
    "r4": {"label": "Has a list anywhere in it"}
  },
  "winner": "Put your own revenue number in line 1"
}
```

## Rules checked by `post_card.py`

A failing rule prints `FIX: ...` and exits 1 (no PNG written):

1. **Real numbers only.** Big number slots (`n`, `tag`, `hero.n`) accept placeholders only — typing a raw digit fails.
   A typed digit in body text prints a warning.
2. **Exact quotes.** Anything inside `"..."` / `“...”` and every `proof.mark` phrase must appear in the run's
   `posts.csv` (`caption`, `parts` or `author_replies`).
3. **Humanized short lines.** Never write bare-number lines without plain words around them, and never write vague lines
   without numbers.
4. **No gendered pronouns for the account owner.** `he`, `him`, `his`, `she`, `her` outside quotes are rejected — say
   `they`, `their` or `the account`.
5. **Honest niche thresholds.** A niche card allows only formats of the niche (`niche_format: true`, 3 creators or more,
   not `few_posts`) and writing features in 6 posts and 3 creators or more. `works` holds lifts `>= 1×`; `doesnt` holds
   lifts `< 1×`.

## Options and rendering

- `--check` — check `card.json` rules only, write nothing.
- `--html-only` — write the standalone HTML (fonts + icon embedded) without running a browser.
- `--layout all` / `--skin all` — render every layout or every style into `<run>/post-cards/<skin>-<layout>.png` (or
  into `--out <dir>`).
- `--scale 2` — 2× pixel density (`2160 × 2700`).
- `--browser chrome|chromium|<path>` — pick the headless browser.

Each card runs a **fit step** before the screenshot is taken: text wider than its box shrinks automatically, and if the
body still nears the footer it scales down cleanly. If anything still overflows or touches the footer, `post_card.py`
exits 1 with `DOES NOT FIT` (shorten the lines or drop an item and re-run).

**Needs** (for the PNG): Node 18+ and Playwright (`playwright` or `playwright-core`) with Chrome, Edge or Playwright's
Chromium — the same setup as `remake.md` (`npm install --prefix ~/.cache/rea-viral playwright-core@1.49.1`). Without
them, `post_card.py` still writes the self-contained HTML so it opens in any browser.
