#!/bin/bash
# Run every REA Viral test. Usage: tests/run_all.sh [work dir]   (default: a new temp folder)
# Exit 1 if any part fails; a part that cannot run (no ffmpeg, node or Playwright) fails, never passes.
# Needs Python 3.8+, ffmpeg and ffprobe, Node 18+ with Playwright (npm install --prefix tests, then
# npx --prefix tests playwright install chromium; or REA_PLAYWRIGHT=<a playwright folder>). Google Chrome adds the MP4
# render check. PULSE_MODEL=<the Pulse connector's model.mjs> adds the planner check against the connector's own model.
set -u
export PYTHONDONTWRITEBYTECODE=1   # the tests leave no __pycache__ in the skill
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
WORK="${1:-$(mktemp -d -t rea-viral-all)}"
SK="$REPO/skill/scripts"
mkdir -p "$WORK"
fail=0
step() { echo; echo "== $1"; }
check() { if [ "$1" -ne 0 ]; then echo "FAILED: $2"; fail=1; fi; }

step "scripts against known answers and edge cases"
python3 "$HERE/test_scripts.py"; check $? test_scripts.py
step "how it writes: text_probe and draft_check against known answers"
python3 "$HERE/test_writing.py"; check $? test_writing.py
step "Scout and Watch"
python3 "$HERE/test_watch.py"; check $? test_watch.py
step "the other ways in: a niche (its formats across creators) and one post, against planted answers"
python3 "$HERE/test_niche.py"; check $? test_niche.py
step "cases a real run met (0.4.1): covers sheets, own videos, speech rate, names, replies, corner words, formats_check, fetching, seeds, what was not read"
python3 "$HERE/test_field_cases.py"; check $? test_field_cases.py
step "growth mode (0.5.0): growth.py on a made-up X account with planted answers, its files, its checks, the reply draft"
python3 "$HERE/test_growth.py"; check $? test_growth.py
step "post cards: post_card.py rules, standalone HTML, all 10 layouts and 7 styles at 1080x1350, fit step"
python3 "$HERE/test_post_card.py" --work "$WORK/post-card"; check $? test_post_card.py
step "Basic remake renderer: frame-exact (WebM clip, Playwright's Chromium)"
python3 "$HERE/test_render.py" --work "$WORK/render-webm"; check $? "test_render.py webm"
if [ -d "/Applications/Google Chrome.app" ] || command -v google-chrome >/dev/null 2>&1; then
  step "Basic remake renderer: frame-exact (MP4 clip, Google Chrome)"
  python3 "$HERE/test_render.py" --work "$WORK/render-mp4" --browser chrome --clip mp4; check $? "test_render.py mp4"
else
  echo "note: no Google Chrome here; the MP4 (H.264) clip path was not run"
fi
step "the report page, headless from file:// (made-up account)"
python3 "$HERE/make_fixtures.py" --out "$WORK/fx" >/dev/null
M="$WORK/fx/main"
python3 -I "$SK/analyze.py" "$M" >/dev/null && python3 -I "$SK/radar.py" "$M" >/dev/null && \
  python3 -I "$SK/comment_tactics.py" "$M" >/dev/null && cp "$M/findings.example.json" "$M/findings.json" && \
  python3 -I "$SK/build_report.py" "$M" >/dev/null
check $? "build the made-up report"
node "$HERE/verify_report.mjs" "$M/report.html" "$WORK/shots-main" --radar 4 --timeline --not-working 6; check $? "verify_report main"
step "the Account report as ONE file with heavy pictures (142 covers up to 2 MB, 14 frame sheets), opened alone"
MP="$WORK/fx/main-pictures"; rm -rf "$MP"; cp -R "$WORK/fx/main" "$MP"
python3 "$HERE/add_pictures.py" "$MP" >/dev/null && python3 -I "$SK/analyze.py" "$MP" >/dev/null && \
  python3 -I "$SK/radar.py" "$MP" >/dev/null && python3 -I "$SK/comment_tactics.py" "$MP" >/dev/null && \
  python3 -I "$SK/build_report.py" "$MP" | grep "report.html:"
check $? "build the made-up report with pictures"
node "$HERE/verify_report.mjs" "$MP/report.html" "$WORK/shots-main-pictures" --radar 4 --timeline --not-working 6 --pictures 30
check $? "verify_report main with pictures"
step "the format map with five long names crowded near the bottom (made-up account): every name inside the chart, none over another"
C="$WORK/fx/crowded"
python3 -I "$SK/analyze.py" "$C" >/dev/null && python3 -I "$SK/radar.py" "$C" >/dev/null && \
  python3 -I "$SK/build_report.py" "$C" >/dev/null
check $? "build the crowded report"
node "$HERE/verify_report.mjs" "$C/report.html" "$WORK/shots-crowded" --radar 5; check $? "verify_report crowded"
step "the covers sheets of the account with 142 covers (numbered, paged, each sheet checked against its tiles)"
python3 -I "$SK/covers_sheet.py" "$MP" --sort ratio | tail -1; check ${PIPESTATUS[0]} "covers_sheet main with pictures"
step "the report page with How it writes (made-up X account: 1 lift, 1 sink)"
W="$WORK/fx/writing_x"
python3 -I "$SK/text_probe.py" "$W" >/dev/null && python3 -I "$SK/build_report.py" "$W" >/dev/null
check $? "build the writing report"
node "$HERE/verify_report.mjs" "$W/report.html" "$WORK/shots-writing" --timeline --writing 2; check $? "verify_report writing"
step "the Account report with the growth block (made-up X account: 4 mechanisms, the posts-a-week bars, the reply draft)"
GX="$(python3 "$HERE/test_growth.py" --make "$WORK/gfx")" && python3 -I "$SK/build_report.py" "$GX" >/dev/null
check $? "build the growth report"
node "$HERE/verify_report.mjs" "$GX/report.html" "$WORK/shots-growth" --timeline --growth 4; check $? "verify_report growth"
node "$HERE/verify_report.mjs" "$GX/report-light.html" "$WORK/shots-growth-light" --growth 4 | tail -1
check ${PIPESTATUS[0]} "verify_report growth light"
step "the niche page, headless from file:// (made-up niche: 2 formats of the niche, 1 creator habit, 2 lifting openings)"
python3 "$HERE/make_niche_fixtures.py" --out "$WORK/nfx" >/dev/null
N="$WORK/nfx/niche_main"
python3 -I "$SK/radar.py" "$N" >/dev/null && python3 -I "$SK/text_probe.py" "$N" >/dev/null && \
  cp "$N/findings.example.json" "$N/findings.json" && python3 -I "$SK/build_report.py" "$N" >/dev/null
check $? "build the made-up niche report"
node "$HERE/verify_report.mjs" "$N/report.html" "$WORK/shots-niche" --radar 2 --gallery 3 --hooks 2 --watchlist 10 --trends 20 --not-working 2 --pictures 10
check $? "verify_report niche"
step "the post page, headless from file:// (made-up post at 3.4x its creator's usual)"
P="$WORK/nfx/post_c3"
python3 -I "$SK/post_probe.py" "$P" >/dev/null && python3 -I "$SK/build_report.py" "$P" >/dev/null
check $? "build the made-up post page"
node "$HERE/verify_report.mjs" "$P/report.html" "$WORK/shots-post" --post --pictures 1; check $? "verify_report post"
step "the light pages (no pictures, for a chat planner), headless from file:// and alone"
for x in "fx/main:6" "nfx/niche_main:4" "nfx/post_c3:0"; do   # the folder, and the items its "What did not work" draws
  node "$HERE/verify_report.mjs" "$WORK/${x%%:*}/report-light.html" "$WORK/shots-light-$(basename "${x%%:*}")" --not-working "${x##*:}" | tail -1
  check ${PIPESTATUS[0]} "verify_report light ${x%%:*}"
done
step "the planner files against each other (and against the Pulse connector's own model when PULSE_MODEL names it)"
node "$HERE/check_planner_shapes.mjs" $(find "$WORK" -name report_record.json -not -path "*/alone/*" -exec dirname {} \; | sort)
check $? "check_planner_shapes"
step "every report page built here: its sizes (the full page under 3 MB; the light page for a chat) and its planner files"
for f in $(find "$WORK" -name report.html -not -path "*/alone/*" | sort); do   # the made-up runs only
  d="$(dirname "$f")"
  python3 - "$d" <<'PY'
import json, os, sys
d = sys.argv[1]
n = os.path.getsize(os.path.join(d, "report.html"))
b = json.load(open(os.path.join(d, "brief.json"))) if os.path.exists(os.path.join(d, "brief.json")) else {}
r = json.load(open(os.path.join(d, "radar_rows.json"))) if os.path.exists(os.path.join(d, "radar_rows.json")) else {}
rec = json.load(open(os.path.join(d, "report_record.json"))) if os.path.exists(os.path.join(d, "report_record.json")) else {}
k = (rec.get("report") or {}).get("kind", "-")
lt = (rec.get("light") or {}).get("size") or 0
cv = "cover" if rec.get("cover") else "-"
print("  %-8s full %7.2f MB  light %4d KB  %-5s %-28s brief %d worked / %d did not  rows %d" % (
      k, n / 1e6, lt // 1000, cv, os.path.relpath(d, os.path.dirname(os.path.dirname(d)))[:28],
      len(b.get("worked") or []), len(b.get("not_worked") or []), len(r.get("rows") or [])))
PY
done
step "no __pycache__ left in the skill or the tests"
left="$(find "$REPO/skill" "$HERE" -name __pycache__ -type d -not -path "*/node_modules/*" 2>/dev/null)"
if [ -n "$left" ]; then echo "FAILED: __pycache__ left: $left"; fail=1; else echo "none"; fi
echo
echo "work folder (screenshots, renders): $WORK"
if [ $fail -ne 0 ]; then echo "NOT OK"; exit 1; fi
echo "ALL OK"
