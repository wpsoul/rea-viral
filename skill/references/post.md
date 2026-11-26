# The post picture: 1080 × 1350 cards for X, Threads and Instagram

Turn any REA Viral run — growth-mode teardown, niche report, topic check, post review, format recipe, plain account run,
draft check, voice/writing sheet, comment tactics, or head-to-head comparison — into a shareable 4:5 (1080 × 1350) PNG
card, plus a standalone `post-card.html` (its fonts and icon inside, opens anywhere).

- **Interactive design lab (all 22 layouts × 7 styles):** open `SKILL_DIR/templates/post/card.html` in any browser
  (or `html/INTERFACE/rea-post-card-lab/index.html` in the repo). Switch between `All new (12)`, every report family,
  all 7 styles / `All styles`, and `Real runs` / `Long text (fit test)` / `Fewer items`; click any card to inspect full
  1080 × 1350 size.
- **Command:**

```
python3 SKILL_DIR/scripts/post_card.py <run> [--type ...] [--layout ...] [--skin cobalt] [--out post-card.png]
```

Default style: `cobalt`. Default layout comes from `card.json`'s `layout`, else auto-detected from `--type` or the run
folder (`t1` teardown, `r2` niche report, `r6` topic check, `p1` post review, `f1` format recipe, `a1` account without
growth, `d1` draft check, `w1` writing/voice, `c1` comment tactics, `x1` compare two). Pick the layout from what the
run actually proves, not at random.

## Layouts (22 layouts across 9 report types)

### Account teardown (`t1`–`t5`) — `--type teardown`, needs `growth.json`

| ID | Name | When to pick it |
|---|---|---|
| `t1` | **Scorecard** (default, growth mode reply card) | Clean profile header (name, handle, followers, window) + 3–4 number-led rows + what doesn't work. Best all-rounder. |
| `t2` | **2×2 numbers** | Four equal stat cards (big number, clean unit label, short plain line) + a bottom strip for what doesn't work. |
| `t3` | **Hero number + checklist** | One giant gradient headline number (e.g. monthly views jump) + short checklist with pill tags. Needs `hero`. |
| `t4` | **The proof post** | Mock post card with the winning post's own words, highlighted phrases (`mark`) and stats + 3 number chips below. Needs `proof`. |
| `t5` | **Numbered editorial** | `01`–`04` + `✕` editorial rows with quotes/sub-lines and right-aligned numbers. |

### Niche report & Topic check (`r1`–`r6`) — `--type report` / `--type topic`

| ID | Name | Needs | When to pick it |
|---|---|---|---|
| `r1` | **Diverging bars** | `radar.json` | Horizontal bars left and right of the `1×` usual line when you have both working (≥ 1×) and non-working (< 1×) formats. |
| `r2` | **Works \| Doesn't** (default) | `radar.json` (+ optional `writing.json`) | Two side-by-side columns + bottom banner for a lifting writing habit (`tip`). |
| `r3` | **Ranked, number first** | `radar.json` | Ranked list from highest lift to lowest when format names are longer. |
| `r4` | **The winner + the rest** | `radar.json` | Big `#1 format` hero card + 2-column grid of the rest when one format clearly leads. |
| `r5` | **Dot plot** | `radar.json` | Log-scale dot plot around `1×` when lifts span a wide range (`0.5×` to `10×+`). |
| `r6` | **Topic check** (`--type topic`) | `topic_check.json` | Verdict banner (`WORTH POSTING` / `TIGHT WINDOW` / `SATURATED` / `EARLY`) + 3 metric boxes (Saturation, 6h Momentum, Lateness) + top 3 breakouts + what to post next. |

### Post review (`p1`–`p3`) — `--type post`, needs `post_probe.json`

| ID | Name | When to pick it |
|---|---|---|
| `p1` | **Proof post + chips** (default) | Big `N× usual` hero vs creator's usual, mock proof post with highlighted hook/phrases (`<mark>`), stats strip, and 3 why-it-worked chips. Auto-badges fresh posts (< 3d / < 7d) with `Still growing · so far`. |
| `p2` | **Hook breakdown** | Exact opening line + annotated hook & structure features with lift/sink multipliers against this creator's own baseline. |
| `p3` | **Vs author median** | Side-by-side comparison bars of this post vs the creator's median (views, likes, reposts, bookmarks) + repeat-rate footer. |

### Format recipe (`f1`–`f2`) — `--type format --format <id>`, needs `radar.json` + `formats/<id>.md`

| ID | Name | When to pick it |
|---|---|---|
| `f1` | **Recipe blueprint** (default) | Format title + lift/share/hit-rate/direction chips (`Scale it` / `Underused` / `Overused` / `Drop`), Hook / Structure / Look / Length / Effort blueprint, and best 3 proof posts. |
| `f2` | **Scorecard + examples** | Compact format scorecard + top proof post tiles with multipliers. Labels small samples (`< 6` posts) honestly. |

### Account without growth mode (`a1`–`a2`) — `--type account`, needs `analysis.json` + `radar.json`

| ID | Name | When to pick it |
|---|---|---|
| `a1` | **Account scorecard** (default) | Profile header + top formats by lift with `Scale it` / `Underused` / `Overused` / `Drop` pills + weakest format strip + writing tip. Works on any plain account run without `growth.json`. |
| `a2` | **Format bars + tip** | Horizontal format lift bars around `1×` usual + what is overused or dropped + one lifting writing habit from `writing.json`. |

### Draft check (`d1`) — `--type draft --draft <path>`, needs `draft_check.py` + `writing.json`/`voice.md`

| ID | Name | When to pick it |
|---|---|---|
| `d1` | **Draft check** | The draft's opening and score against the author's own habits: what lifts, what drags/fails, and the predicted range vs usual **explicitly labelled `ESTIMATE`**. |

### Writing / Voice sheet (`w1`) — `--type writing`, needs `writing.json`

| ID | Name | When to pick it |
|---|---|---|
| `w1` | **Writing & voice** | Opening lines, length bands, and asks measured against the account's usual (`×`), plus verbatim winning first lines. |

### Comment tactics (`c1`) — `--type comments`, needs `comments.json`

| ID | Name | When to pick it |
|---|---|---|
| `c1` | **Comment tactics** | Comments as a growth tactic with measured numbers (own comments, reply rate, response time, follow intent, echo prompts) + real example quote. |

### Compare two (`x1`) — `--type compare --pair <fmtA>,<fmtB>` or `--vs <other_run>`

| ID | Name | When to pick it |
|---|---|---|
| `x1` | **Compare two** | Split `A vs B` card comparing two formats in one run (`--pair fmtA,fmtB`) or two accounts (`--vs path/to/other_run`) across aligned metrics with the winner highlighted per row. |

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
   A typed digit in body text prints a warning (handles with digits like `@b1rkh0ff` are recognised as handles and never
   trigger a warning).
2. **Clean `:x` rounding.** Multipliers `>= 10×` round to whole integers (`510.88` → `511×`); multipliers `< 10×` keep
   1 decimal (`2.7×`), and values between `0.95` and `0.99` keep 2 decimals (`0.97×`) so they never round up to `1×`.
3. **Safe inline markup.** Use `**bold**`, `<b>...</b>`, or `<mark>...</mark>` for emphasis. All other HTML tags and
   attributes stay escaped so untrusted captions can never inject markup.
4. **Exact quotes.** Anything inside `"..."` / `“...”` and every `proof.mark` phrase must appear in the run's
   `posts.csv` (`caption`, `parts` or `author_replies`).
5. **Humanized short lines.** Never write bare-number lines without plain words around them, and never write vague lines
   without numbers.
6. **No gendered pronouns for the account owner.** `he`, `him`, `his`, `she`, `her` outside quotes are rejected — say
   `they`, `their` or `the account`.
7. **Honest thresholds & labels.**
   - Niche cards (`r1`–`r5`) allow only formats of the niche (`niche_format: true`, 3 creators or more, not `few_posts`)
     and writing features in 6 posts and 3 creators or more (`works >= 1×`, `doesnt < 1×`).
   - Fresh posts (< 3 days on X/Threads, < 7 days elsewhere) display `"Still growing · so far"`.
   - Small samples (`< 6` posts) carry an explicit small-sample badge.
   - Draft check (`d1`) ranges MUST include the explicit word `"estimate"` (failing `--check` otherwise).

## Options and rendering

- `--type teardown|report|topic|post|format|account|draft|writing|comments|compare` — override auto-detected card type.
- `--format <id>` — pick the format id for `f1` / `f2`.
- `--draft <path>` — path to a draft markdown file for `d1`.
- `--pair <fmtA>,<fmtB>` — compare two formats inside one run on `x1`.
- `--vs <other_run>` — compare two account runs head-to-head on `x1`.
- `--check` — check `card.json` rules only, write nothing.
- `--html-only` — write the standalone HTML (fonts + icon embedded) without running a browser.
- `--layout all` / `--skin all` — render every layout of the chosen type or every style into `<run>/post-cards/<skin>-<layout>.png` (or into `--out <dir>`).
- `--scale 2` — 2× pixel density (`2160 × 2700`).
- `--browser chrome|chromium|<path>` — pick the headless browser.

Each card runs a **fit step** before the screenshot is taken: text wider than its box shrinks automatically, and if the
body still nears the footer it scales down cleanly. If anything still overflows or touches the footer, `post_card.py`
exits 1 with `DOES NOT FIT` (shorten the lines or drop an item and re-run).

**Needs** (for the PNG): Node 18+ and Playwright (`playwright` or `playwright-core`) with Chrome, Edge or Playwright's
Chromium — the same setup as `remake.md` (`npm install --prefix ~/.cache/rea-viral playwright-core@1.49.1`). Without
them, `post_card.py` still writes the self-contained HTML so it opens in any browser.
