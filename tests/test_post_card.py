#!/usr/bin/env python3
"""Tests for the post card builder (post_card.py), its template (templates/post/card.html) and renderer (render_card.mjs).

    python3 tests/test_post_card.py [--work DIR]

Uses made-up fixture data only: the growth-mode account from test_growth.py --make, the niche from make_niche_fixtures.py,
plus a small synthetic niche with both working and non-working formats. Checks:
  - every text/number rule (placeholders, typed numbers, exact quotes, no gendered pronouns, proof mark, niche >= 3 creators,
    works >= 1x / doesnt < 1x, t3 needs hero, t4 needs proof);
  - draft card.json creation when absent;
  - standalone HTML (fonts inlined; icons present on cobalt/redword/night and absent on holo/paper/warm/glass);
  - headless PNG renders at 1080 x 1350 for all 10 layouts (t1..t5, r1..r5) and all 7 styles, with zero overflow or console errors;
  - the fit step: long names/labels shrink to fit (exit 0), and an impossibly long card fails loudly (exit 1).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SK = os.path.join(REPO, "skill", "scripts")
POST_CARD = os.path.join(SK, "post_card.py")
RENDER_CARD = os.path.join(SK, "render_card.mjs")
PLAYWRIGHT = next((p for p in (os.environ.get("REA_PLAYWRIGHT"), os.path.join(HERE, "node_modules", "playwright"),
                               os.path.expanduser("~/.cache/rea-viral/node_modules/playwright-core")) if p and os.path.isdir(p)), "")

PASS = 0
FAIL = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("FAIL:", msg)


def run_card(args, env=None):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if env:
        e.update(env)
    return subprocess.run([sys.executable, "-I", POST_CARD] + args, capture_output=True, text=True, env=e)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def make_synthetic_niche(folder):
    """A small made-up niche with 4 working formats, 4 under-1x formats, 1 creator habit, and 1 lifting writing feature."""
    os.makedirs(os.path.join(folder, "accounts", "x-a1"), exist_ok=True)
    write_json(os.path.join(folder, "niche.json"), {
        "schema": "rea-viral/niche@1",
        "name": "solo builders",
        "slug": "solo-builders",
        "networks": ["x"],
        "window": {"from": "2026-10-24", "to": "2026-11-23"},
    })
    with open(os.path.join(folder, "accounts", "x-a1", "posts.csv"), "w", encoding="utf-8") as f:
        f.write("post_id,caption,parts,author_replies\np1,Revenue hit 4k this month,,\n")
    write_json(os.path.join(folder, "radar.json"), {
        "schema": "rea-viral/radar@2",
        "scope": "niche",
        "subject": {"niche": "solo builders", "networks": ["x"]},
        "window": {"from": "2026-10-24", "to": "2026-11-23"},
        "counts": {"creators_scored": 12, "scored": 480},
        "formats": [
            {"id": "rev-open", "name": "Own revenue number in line 1", "lift": 2.71, "posts_scored": 28, "creators": 7, "niche_format": True, "few_posts": False, "direction_label": "rising", "hit_rate": 0.64},
            {"id": "list-post", "name": "List post: one item per line", "lift": 2.42, "posts_scored": 44, "creators": 9, "niche_format": True, "few_posts": False, "direction_label": "steady", "hit_rate": 0.55},
            {"id": "long-story", "name": "Long build story (600+ chars)", "lift": 1.62, "posts_scored": 31, "creators": 6, "niche_format": True, "few_posts": False, "direction_label": "steady", "hit_rate": 0.42},
            {"id": "ship-demo", "name": "Ship demo clip", "lift": 1.20, "posts_scored": 22, "creators": 5, "niche_format": True, "few_posts": False, "direction_label": "rising", "hit_rate": 0.36},
            {"id": "short-quote", "name": "Quote with a short take", "lift": 0.93, "posts_scored": 120, "creators": 11, "niche_format": True, "few_posts": False, "direction_label": "steady", "hit_rate": 0.14},
            {"id": "one-liner", "name": "One-liner", "lift": 0.89, "posts_scored": 85, "creators": 10, "niche_format": True, "few_posts": False, "direction_label": "fading", "hit_rate": 0.11},
            {"id": "short-q", "name": "Short question", "lift": 0.84, "posts_scored": 40, "creators": 8, "niche_format": True, "few_posts": False, "direction_label": "steady", "hit_rate": 0.10},
            {"id": "raw-clip", "name": "Clip without a launch", "lift": 0.78, "posts_scored": 19, "creators": 4, "niche_format": True, "few_posts": False, "direction_label": "fading", "hit_rate": 0.05},
            {"id": "one-creator", "name": "One creator's habit", "lift": 4.50, "posts_scored": 14, "creators": 1, "niche_format": False, "scope_status": "creator habit", "few_posts": False},
            {"id": "tiny-fmt", "name": "Too few posts", "lift": 2.10, "posts_scored": 4, "creators": 3, "niche_format": True, "few_posts": True},
        ],
    })
    write_json(os.path.join(folder, "writing.json"), {
        "schema": "rea-viral/writing@1",
        "settings": {"min_posts": 6, "min_creators": 3},
        "features": [
            {"id": "has_list", "label": "Has a list", "verdict": "lifts", "creators_with": 10,
             "with": {"posts": 52, "lift": 2.27}, "without": {"posts": 428, "lift": 0.95}},
            {"id": "rare_feat", "label": "Rare hook", "verdict": "few posts", "creators_with": 2,
             "with": {"posts": 4, "lift": 3.10}, "without": {"posts": 476, "lift": 1.00}},
        ],
    })


def main(argv):
    work = argv[argv.index("--work") + 1] if "--work" in argv else tempfile.mkdtemp(prefix="rea-post-card-")
    os.makedirs(work, exist_ok=True)
    if not shutil.which("node"):
        raise SystemExit("FAIL node is not on PATH: this test cannot run")
    if not os.path.isdir(PLAYWRIGHT):
        raise SystemExit("FAIL no Playwright at %s: this test cannot run" % PLAYWRIGHT)
    env = {"REA_PLAYWRIGHT": PLAYWRIGHT}

    # 1. Build made-up growth account fixture
    gfx_root = os.path.join(work, "gfx")
    r = subprocess.run([sys.executable, os.path.join(HERE, "test_growth.py"), "--make", gfx_root],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    ok(r.returncode == 0, "test_growth.py --make failed: " + r.stderr)
    gx = r.stdout.strip().splitlines()[-1]
    g = json.load(open(os.path.join(gx, "growth.json"), encoding="utf-8"))

    # Draft card.json when absent
    r = run_card([gx, "--html-only"])
    ok(r.returncode == 0, "draft teardown --html-only failed: " + r.stdout + r.stderr)
    ok(os.path.exists(os.path.join(gx, "card.json")), "draft card.json was written")
    ok(os.path.exists(os.path.join(gx, "post-card.html")), "post-card.html was written")

    # Teardown rule checks
    base_card = json.load(open(os.path.join(gx, "card.json"), encoding="utf-8"))

    def check_bad(spec, needle, label):
        p = os.path.join(work, "bad.json")
        write_json(p, spec)
        res = run_card([gx, "--card", p, "--check"])
        ok(res.returncode == 1 and needle in res.stdout, "%s: expected exit 1 with %r, got %d: %s" % (label, needle, res.returncode, res.stdout))

    # Unknown placeholder
    bad = json.loads(json.dumps(base_card))
    bad["items"][0]["n"] = "{cadence.no_such_key}"
    check_bad(bad, "no such key", "unknown placeholder")

    # Typed number in strict field (n)
    bad = json.loads(json.dumps(base_card))
    bad["items"][0]["n"] = "42"
    check_bad(bad, "is typed", "typed number in n")

    # Ungrounded quote
    bad = json.loads(json.dumps(base_card))
    bad["items"][0]["sub"] = '“words that never appeared anywhere”'
    check_bad(bad, "not in the posts' own words", "ungrounded quote")

    # Gendered pronoun outside quote
    bad = json.loads(json.dumps(base_card))
    bad["items"][0]["line"] = "He posts every day"
    check_bad(bad, "no he, his, she or her", "gendered pronoun")

    # Missing hero for t3
    bad = json.loads(json.dumps(base_card))
    bad.pop("hero", None)
    p = os.path.join(work, "no_hero.json")
    write_json(p, bad)
    res = run_card([gx, "--card", p, "--layout", "t3", "--check"])
    ok(res.returncode == 1 and 'needs "hero"' in res.stdout, "t3 without hero rejected: " + res.stdout)

    # Missing proof for t4
    bad = json.loads(json.dumps(base_card))
    bad.pop("proof", None)
    p = os.path.join(work, "no_proof.json")
    write_json(p, bad)
    res = run_card([gx, "--card", p, "--layout", "t4", "--check"])
    ok(res.returncode == 1 and 'needs "proof"' in res.stdout, "t4 without proof rejected: " + res.stdout)

    # Invalid proof.mark
    bad = json.loads(json.dumps(base_card))
    bad["proof"]["mark"] = ["phrase not in that post"]
    check_bad(bad, "proof.mark", "invalid proof.mark")

    # 2. Icon presence/absence in standalone HTML for all 7 styles
    for skin in ("cobalt", "redword", "night", "holo", "paper", "warm", "glass"):
        out_png = os.path.join(work, "html-check", skin + ".png")
        res = run_card([gx, "--layout", "t1", "--skin", skin, "--out", out_png, "--html-only"])
        ok(res.returncode == 0, "--html-only %s failed: %s" % (skin, res.stdout + res.stderr))
        html_text = open(out_png[:-4] + ".html", encoding="utf-8").read()
        ok("data:font/woff2;base64," in html_text, "%s HTML has inlined woff2 font" % skin)
        has_icon = '"icon": "data:image/png;base64,' in html_text
        want_icon = skin in ("cobalt", "redword", "night")
        ok(has_icon == want_icon, "%s icon rule: expected %s, got %s" % (skin, want_icon, has_icon))

    # 3. Render all 5 teardown layouts (t1..t5) on the made-up growth account
    td_out = os.path.join(work, "teardown-all")
    res = run_card([gx, "--layout", "all", "--skin", "cobalt", "--out", td_out], env=env)
    ok(res.returncode == 0, "teardown --layout all failed: " + res.stdout + res.stderr)
    for lid in ("t1", "t2", "t3", "t4", "t5"):
        p = os.path.join(td_out, "cobalt-%s.png" % lid)
        ok(os.path.exists(p) and png_size(p) == (1080, 1350), "teardown %s PNG is 1080x1350" % lid)

    # 4. Niche report rules on real make_niche_fixtures.py output + synthetic niche with works & doesnt
    nfx_root = os.path.join(work, "nfx")
    subprocess.run([sys.executable, os.path.join(HERE, "make_niche_fixtures.py"), "--out", nfx_root],
                   check=True, stdout=subprocess.DEVNULL, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    nm = os.path.join(nfx_root, "niche_main")
    subprocess.run([sys.executable, "-I", os.path.join(SK, "radar.py"), nm], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, "-I", os.path.join(SK, "text_probe.py"), nm], check=True, stdout=subprocess.DEVNULL)
    res = run_card([nm, "--html-only"])
    ok(res.returncode == 0, "niche_main draft --html-only failed: " + res.stdout + res.stderr)

    # Reject creator habit (< 3 creators) from niche_main
    bad_n = os.path.join(work, "bad_habit.json")
    write_json(bad_n, {"type": "report", "works": [{"format": "studio-desk-review"}, {"format": "before-after-split"}], "doesnt": []})
    res = run_card([nm, "--card", bad_n, "--check"])
    ok(res.returncode == 1 and "3 creators or more" in res.stdout, "creator habit rejected: " + res.stdout)

    # Synthetic niche: test wrong side, few_posts, rare feature, and render all 5 layouts (r1..r5) + all 7 styles
    sn = os.path.join(work, "niche_synth")
    make_synthetic_niche(sn)

    for label, spec, needle in (
        ("under 1x in works", {"type": "report", "works": [{"format": "short-quote"}, {"format": "rev-open"}], "doesnt": []}, "goes in doesnt"),
        ("over 1x in doesnt", {"type": "report", "works": [{"format": "rev-open"}], "doesnt": [{"format": "list-post"}]}, "goes in works"),
        ("few_posts format", {"type": "report", "works": [{"format": "tiny-fmt"}, {"format": "rev-open"}], "doesnt": []}, "few posts"),
        ("rare feature", {"type": "report", "works": [{"feature": "rare_feat"}, {"format": "rev-open"}], "doesnt": []}, "3 creators"),
    ):
        p = os.path.join(work, "bad_r.json")
        write_json(p, spec)
        res = run_card([sn, "--card", p, "--check"])
        ok(res.returncode == 1 and needle in res.stdout, "niche rule %s: %s" % (label, res.stdout))

    good_r = {
        "schema": "rea-viral/card@1",
        "type": "report",
        "layout": "r2",
        "skin": "cobalt",
        "works": [
            {"format": "rev-open", "label": "Own revenue number in line 1"},
            {"format": "list-post", "label": "List post: one item per line"},
            {"format": "long-story", "label": "Long build story ({posts} posts)"},
            {"format": "ship-demo", "label": "Ship demo clip, {direction}"},
        ],
        "doesnt": [
            {"format": "short-quote", "label": "Quote with a short take ({posts} posts)"},
            {"format": "one-liner", "label": "One-liner"},
            {"format": "short-q", "label": "Short question"},
            {"format": "raw-clip", "label": "Clip without a launch"},
        ],
        "tip": {"feature": "has_list", "label": "Any post with a list ({posts} posts, {creators} creators). Without one: {without:x}."},
    }
    write_json(os.path.join(sn, "card.json"), good_r)

    rp_out = os.path.join(work, "report-all")
    res = run_card([sn, "--layout", "all", "--skin", "cobalt", "--out", rp_out], env=env)
    ok(res.returncode == 0, "report --layout all failed: " + res.stdout + res.stderr)
    for lid in ("r1", "r2", "r3", "r4", "r5"):
        p = os.path.join(rp_out, "cobalt-%s.png" % lid)
        ok(os.path.exists(p) and png_size(p) == (1080, 1350), "report %s PNG is 1080x1350" % lid)

    # All 7 styles rendered on t5 (tests list-as-cards on paper/warm/glass, violet Night Notes, iconless Holo)
    sk_out = os.path.join(work, "skins-t5")
    res = run_card([gx, "--layout", "t5", "--skin", "all", "--out", sk_out], env=env)
    ok(res.returncode == 0, "t5 --skin all failed: " + res.stdout + res.stderr)
    for skin in ("cobalt", "redword", "night", "holo", "paper", "warm", "glass"):
        p = os.path.join(sk_out, "%s-t5.png" % skin)
        ok(os.path.exists(p) and png_size(p) == (1080, 1350), "skin %s t5 PNG is 1080x1350" % skin)

    # 5. Fit step: long text shrinks and passes; impossible text fails with DOES NOT FIT
    long_r = json.loads(json.dumps(good_r))
    long_r["title"] = "What works for **very long niche title with many extra words about building** on X right now"
    for w in long_r["works"] + long_r["doesnt"]:
        w["label"] = w["label"] + " with an extra long explanation of why creators keep trying this format"
    long_p = os.path.join(work, "long_r.json")
    write_json(long_p, long_r)
    res = run_card([sn, "--card", long_p, "--layout", "r2", "--skin", "paper", "--out", os.path.join(work, "long-r2.png")], env=env)
    ok(res.returncode == 0 and "text at" in res.stdout, "long text shrinks and passes: " + res.stdout + res.stderr)

    huge_r = json.loads(json.dumps(good_r))
    for w in huge_r["works"] + huge_r["doesnt"]:
        w["label"] = ("very long repeated explanation text that cannot possibly fit inside a 1080 by 1350 card " * 8).strip()
    huge_p = os.path.join(work, "huge_r.json")
    write_json(huge_p, huge_r)
    res = run_card([sn, "--card", huge_p, "--layout", "r2", "--skin", "cobalt", "--out", os.path.join(work, "huge-r2.png")], env=env)
    ok(res.returncode == 1 and "DOES NOT FIT" in res.stdout, "impossible overflow fails loudly: " + res.stdout + res.stderr)

    # 6. 0.5.1 bug fixes (#9 :x rounding, #10 safe <b>/<mark> tags, #11 @handle digits ignored, #12 t2 clean .u layout)
    sys.path.insert(0, SK)
    try:
        import post_card as pc
    finally:
        sys.path.remove(SK)
    ok(pc.fmt_x(510.88) == "511×", "Bug #9 fmt_x(510.88) -> 511×, got " + pc.fmt_x(510.88))
    ok(pc.fmt_x(10.0) == "10×", "Bug #9 fmt_x(10.0) -> 10×, got " + pc.fmt_x(10.0))
    ok(pc.fmt_x(2.71) == "2.7×", "Bug #9 fmt_x(2.71) -> 2.7×, got " + pc.fmt_x(2.71))
    ok(pc.fmt_x(0.97) == "0.97×", "Bug #9 fmt_x(0.97) -> 0.97×, got " + pc.fmt_x(0.97))

    md_out = pc.md("Why <b>@b1rkh0ff</b> <mark>wins</mark> **fast** <script>x</script>")
    ok("<b>@b1rkh0ff</b>" in md_out and "<mark>wins</mark>" in md_out and "<b>fast</b>" in md_out and "&lt;script&gt;" in md_out,
       "Bug #10 safe tags & bold: " + md_out)

    # Bug #11: @handle with digits (e.g. @b1rkh0ff) triggers zero typed-number warnings
    hcard = json.loads(json.dumps(base_card))
    hcard["title"] = "Why <b>@b1rkh0ff</b> is growing"
    hcard_p = os.path.join(work, "handle_digits.json")
    write_json(hcard_p, hcard)
    res = run_card([gx, "--card", hcard_p, "--check"])
    ok(res.returncode == 0 and "note:" not in res.stdout, "Bug #11 @b1rkh0ff emits zero typed-digit warnings: " + res.stdout)

    # Bug #12: t2 renders clean .u unit subtitle, never "unit: line" colon mashup
    t2_html_png = os.path.join(work, "t2-check.png")
    res = run_card([gx, "--layout", "t2", "--skin", "cobalt", "--out", t2_html_png, "--html-only"])
    ok(res.returncode == 0, "t2 --html-only failed: " + res.stdout + res.stderr)
    t2_src = open(t2_html_png[:-4] + ".html", encoding="utf-8").read()
    ok(".t2 .c .u{" in t2_src and "el('div', 'u', c.unit)" in t2_src, "Bug #12 t2 template uses .u unit div")

    # 7. All 12 new 0.5.1 card layouts end-to-end (post p1-p3, format f1-f2, account a1-a2, draft d1, writing w1, comments c1, compare x1, topic r6)
    fx_root = os.path.join(work, "fx_cards")
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_fixtures.py"), "--out", fx_root],
                   check=True, stdout=subprocess.DEVNULL, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    main_run = os.path.join(fx_root, "main")
    writing_run = os.path.join(fx_root, "writing_x")
    for s in ("analyze.py", "radar.py", "comment_tactics.py", "text_probe.py"):
        subprocess.run([sys.executable, "-I", os.path.join(SK, s), main_run], check=True, stdout=subprocess.DEVNULL)
    for s in ("analyze.py", "radar.py", "text_probe.py"):
        subprocess.run([sys.executable, "-I", os.path.join(SK, s), writing_run], check=True, stdout=subprocess.DEVNULL)
    post_run = os.path.join(nfx_root, "post_c3")
    subprocess.run([sys.executable, "-I", os.path.join(SK, "post_probe.py"), post_run], check=True, stdout=subprocess.DEVNULL)

    # Post review p1..p3
    post_out = os.path.join(work, "post-all")
    res = run_card([post_run, "--type", "post", "--layout", "all", "--skin", "cobalt", "--out", post_out], env=env)
    ok(res.returncode == 0, "post p1..p3 failed: " + res.stdout + res.stderr)
    for lid in ("p1", "p2", "p3"):
        p = os.path.join(post_out, "cobalt-%s.png" % lid)
        ok(os.path.exists(p) and png_size(p) == (1080, 1350), "post %s PNG is 1080x1350" % lid)

    # Format recipe f1..f2
    fmt_out = os.path.join(work, "fmt-all")
    res = run_card([main_run, "--type", "format", "--format", "three-mistakes", "--layout", "all", "--skin", "cobalt", "--out", fmt_out], env=env)
    ok(res.returncode == 0, "format f1..f2 failed: " + res.stdout + res.stderr)
    for lid in ("f1", "f2"):
        p = os.path.join(fmt_out, "cobalt-%s.png" % lid)
        ok(os.path.exists(p) and png_size(p) == (1080, 1350), "format %s PNG is 1080x1350" % lid)

    # Account without growth mode (a1..a2) — main_run has NO growth.json
    ok(not os.path.exists(os.path.join(main_run, "growth.json")), "main_run has no growth.json")
    acct_out = os.path.join(work, "acct-all")
    res = run_card([main_run, "--type", "account", "--layout", "all", "--skin", "paper", "--out", acct_out], env=env)
    ok(res.returncode == 0, "account a1..a2 failed: " + res.stdout + res.stderr)
    for lid in ("a1", "a2"):
        p = os.path.join(acct_out, "paper-%s.png" % lid)
        ok(os.path.exists(p) and png_size(p) == (1080, 1350), "account %s PNG is 1080x1350" % lid)

    # Draft check (d1) + explicit ESTIMATE rule enforcement
    draft_md = os.path.join(work, "sample_draft.md")
    with open(draft_md, "w", encoding="utf-8") as f:
        f.write("---\nfor: solo builders\nnetwork: x\npurpose: followers\nask: follow\nopenings: [opens_number]\n---\n"
                "7 pricing mistakes that cut revenue in half.\n\nCharge for outcomes, not hours.\n\nFollow for the next batch.\n")
    d1_png = os.path.join(work, "draft-d1.png")
    res = run_card([writing_run, "--type", "draft", "--draft", draft_md, "--layout", "d1", "--skin", "cobalt", "--out", d1_png], env=env)
    ok(res.returncode == 0 and os.path.exists(d1_png) and png_size(d1_png) == (1080, 1350),
       "draft d1 PNG is 1080x1350: " + res.stdout + res.stderr)
    bad_d1 = os.path.join(work, "bad_d1.json")
    write_json(bad_d1, {
        "schema": "rea-viral/card@1", "type": "draft", "layout": "d1", "draft_file": draft_md,
        "estimate": {"badge": "GUARANTEED", "range": "2x - 3x", "label": "Guaranteed outcome"},
    })
    res = run_card([writing_run, "--type", "draft", "--card", bad_d1, "--check"])
    ok(res.returncode == 1 and "estimate" in res.stdout.lower(), "d1 without explicit estimate rejected: " + res.stdout)

    # Writing / voice (w1)
    w1_png = os.path.join(work, "writing-w1.png")
    res = run_card([writing_run, "--type", "writing", "--layout", "w1", "--skin", "warm", "--out", w1_png], env=env)
    ok(res.returncode == 0 and os.path.exists(w1_png) and png_size(w1_png) == (1080, 1350),
       "writing w1 PNG is 1080x1350: " + res.stdout + res.stderr)

    # Comment tactics (c1)
    c1_png = os.path.join(work, "comments-c1.png")
    res = run_card([main_run, "--type", "comments", "--layout", "c1", "--skin", "redword", "--out", c1_png], env=env)
    ok(res.returncode == 0 and os.path.exists(c1_png) and png_size(c1_png) == (1080, 1350),
       "comments c1 PNG is 1080x1350: " + res.stdout + res.stderr)

    # Compare two (x1): two formats (--pair) AND two accounts (--vs)
    x1_pair = os.path.join(work, "compare-pair-x1.png")
    res = run_card([main_run, "--type", "compare", "--pair", "three-mistakes,long-story", "--layout", "x1", "--skin", "cobalt", "--out", x1_pair], env=env)
    ok(res.returncode == 0 and os.path.exists(x1_pair) and png_size(x1_pair) == (1080, 1350),
       "compare --pair x1 PNG is 1080x1350: " + res.stdout + res.stderr)
    x1_vs = os.path.join(work, "compare-vs-x1.png")
    res = run_card([main_run, "--type", "compare", "--vs", writing_run, "--layout", "x1", "--skin", "night", "--out", x1_vs], env=env)
    ok(res.returncode == 0 and os.path.exists(x1_vs) and png_size(x1_vs) == (1080, 1350),
       "compare --vs x1 PNG is 1080x1350: " + res.stdout + res.stderr)

    # 8. Template gallery smoke check across ALL 12 new layouts + core layouts in sample & long modes
    gal_out = os.path.join(work, "gallery")
    res = subprocess.run(["node", RENDER_CARD, "--gallery", gal_out, "--skins", "cobalt,paper",
                          "--layouts", "t1,t2,t5,r1,r5,r6,p1,p2,p3,f1,f2,a1,a2,d1,w1,c1,x1", "--content", "long"],
                         capture_output=True, text=True, env=dict(os.environ, **env))
    ok(res.returncode == 0, "gallery long smoke failed: " + res.stdout + res.stderr)

    print("post_card: %d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
