"""The post run's hand-over: the Post report (a short report.html) and POST.md, plus the planner files
(report_record.json; radar_rows.json, the post's own format). Called by build_report.py on a folder with post.json.

It draws post_probe.json (the numbers), findings.json (your reading), the post's notes.json and frame sheet (the deep
read) and its format's recipe, and the mirror of what worked: what in this post sits under its creator's usual (the
format's repeats under it, the words its creator's weaker posts share). Refuses to build while validate.py finds
errors or post_probe.json is older than its inputs. The creator's video is never embedded: its cover or frame sheet
is a small picture inside the page, linked to the post.
"""
import json
import os
import re

from common import SKILL_VERSION, die, iso, now_utc, read_csv, read_json, write_text
from analyze import input_fingerprint
import brief
import hand_over
import page_kit


def _load(folder, name):
    p = os.path.join(folder, name)
    return read_json(p) if os.path.exists(p) else None


def page_data(folder, light=False):
    pp = _load(folder, "post_probe.json")
    if pp is None:
        die("no post_probe.json: run post_probe.py first", 1)
    was = pp.get("inputs") or {}
    have = input_fingerprint(folder, tuple(was.keys()))
    changed = sorted(k for k in was if have.get(k) != was.get(k))
    if changed:
        die("post_probe.json was made before %s changed: run post_probe.py again" % ", ".join(changed), 1)
    acc = read_json(os.path.join(folder, "account.json"))
    pid = pp["post"]["post_id"]
    notes = _load(folder, os.path.join("videos", pid, "notes.json"))
    probe = _load(folder, os.path.join("videos", pid, "probe.json"))
    recipe = None
    if pp.get("recipe") and os.path.exists(os.path.join(folder, pp["recipe"])):
        m = re.search(r"```json rea-recipe\s*\n(.*?)\n```", open(os.path.join(folder, pp["recipe"]), encoding="utf-8").read(), re.S)
        if m:
            try:
                recipe = json.loads(m.group(1))
            except ValueError:
                recipe = None
    cost = {"rows": [], "total_usd": 0.0}
    cp = os.path.join(folder, "cost.csv")
    if os.path.exists(cp):
        _, rows = read_csv(cp)
        cost = {"rows": rows, "total_usd": round(sum(float(r.get("total_usd") or 0) for r in rows), 4)}
    # One picture, inside the page: the first seconds when the video was cut, else the cover.
    pics = page_kit.Pictures(folder, light=light)
    sheet = pics.get(page_kit.existing(folder, "videos/%s/first.jpg" % pid), "sheet")
    cover = None if sheet else pics.get(page_kit.existing(folder, pp["post"].get("cover_file")), "cover")
    return {
        "skill_version": SKILL_VERSION, "built_at": iso(now_utc()),
        "probe": pp, "findings": _load(folder, "findings.json") or {},
        "notes": notes, "measured_video": (probe or {}).get("measured") if (probe or {}).get("read") else None,
        "sheet": sheet, "cover": cover,
        "recipe": recipe, "recipe_file": pp.get("recipe"),
        "not_working": not_working(pp),
        "limits": page_kit.dedupe_limits(page_kit.run_limits("post", folder, focus=pid), _load(folder, "findings.json") or {}),
        "sources": acc.get("sources") or [], "cost": cost,
        "pictures": pics.summary(),
    }


def not_working(pp):
    """The mirror of why it worked (MEASURED, from post_probe.json): whether the post itself sits under its creator's
    usual, the format's repeats that sat under it, and the words this post has (or lacks) where the creator's posts
    with them do worse. With one creator's posts these are leads: under 6 posts on a side is marked so. Never a cause."""
    p, rp, w = pp.get("post") or {}, pp.get("repeats") or {}, pp.get("words") or {}
    out = {"status": pp.get("status"), "note": None, "post_below": None}
    if pp.get("status") != "ok":
        out["note"] = "Not enough data: %s" % (pp.get("status_note") or pp.get("status"))
    elif p.get("ratio") is not None and p["ratio"] < 1.0:
        out["post_below"] = {"ratio": p["ratio"], "usual": p.get("usual"), "from": "post_probe.json#post.ratio"}
    rep = {"format": rp.get("format"), "name": rp.get("name"), "scored": rp.get("scored") or 0, "below": [],
           "from": "post_probe.json#repeats", "note": None}
    if not rp.get("format"):
        rep["note"] = "Not measured: the post's format is not marked (formats.json), so its repeats are unknown."
    else:
        rep["below"] = [q for q in rp.get("posts") or [] if q.get("ratio") is not None and q["ratio"] < 1.0]
        if not rp.get("times"):
            rep["note"] = "The creator did not repeat the format in the posts read."
        elif not rep["scored"]:
            rep["note"] = "None of its repeats could be scored against the creator's usual."
        elif not rep["below"]:
            rep["note"] = "Every scored repeat sat at the creator's usual or over it."
    out["repeats"] = rep
    words, wnote = [], None
    if w.get("status") != "ok":
        wnote = w.get("note") or "No words to read."
    else:
        for f in w.get("flags") or []:
            a, b = (f.get("creator_with") or {}), (f.get("creator_without") or {})
            if a.get("lift") is None or b.get("lift") is None or not b["lift"]:
                continue
            if f.get("post") is True and a["lift"] <= 0.8 * b["lift"]:
                kind = "has"
            elif f.get("post") is False and b["lift"] <= 0.8 * a["lift"]:
                kind = "lacks"
            else:
                continue
            words.append({"id": f["id"], "label": f["label"], "kind": kind, "with": a, "without": b,
                          "few": a.get("posts", 0) < 6 or b.get("posts", 0) < 6,
                          "from": "post_probe.json#words.flags.%s" % f["id"]})
        words.sort(key=lambda x: (x["few"], (x["with"]["lift"] / x["without"]["lift"]) if x["kind"] == "has" else
                                  (x["without"]["lift"] / x["with"]["lift"])))
        if not words:
            wnote = "Nothing in its words goes with the creator's weaker posts."
    out["words"], out["words_note"] = words[:5], wnote
    return out


def _x(v):
    return "-" if v is None else ("%.2f" % v).rstrip("0").rstrip(".") + "x"


def post_md(d):
    import build_report
    pp, fi = d["probe"], d["findings"] or {}
    p, c = pp["post"], pp["creator"]
    nw = d.get("not_working") or {}
    L = ["# @%s's post %s: REA Viral, Post report" % (c.get("handle"), p["post_id"]), "",
         "For agents. The post against ITS OWN creator's usual (the median of the creator's other posts), its words "
         "beside the creator's usual, whether the creator repeats it, and its recipe. Built %s by REA Viral %s." % (
             d["built_at"], d["skill_version"]), "", "## Layer 0: the answer", ""]
    if pp.get("status") != "ok":
        L.append("- Status: %s. %s" % (pp.get("status"), pp.get("status_note") or ""))
    if p.get("ratio") is not None:
        L.append("- [MEASURED] %s its creator's usual: %s %s against the median %s of %d other posts; #%s of %d scored posts "
                 "(post_probe.json#post.ratio)." % (_x(p["ratio"]), p.get("views"), p.get("metric"), p.get("usual"),
                                                    p.get("usual_from_posts") or 0, p.get("rank_among_creator"), p.get("creator_scored")))
    elif p.get("ratio_so_far") is not None:
        L.append("- [MEASURED] %s its creator's usual so far (too new: a floor) (post_probe.json#post.ratio_so_far)." % _x(p["ratio_so_far"]))
    if fi.get("headline"):
        L.append("- " + build_report.claim_line(fi["headline"]))
    L.append("- [MEASURED] Repeats: %s (post_probe.json#repeats)." % pp["repeats"]["label"])
    L += ["", "## Layer 1: where each answer is", "", "| Question | Short answer | Read |", "|---|---|---|",
          "| How far did it beat its creator? | %s | post_probe.json#post |" % (_x(p.get("ratio")) if p.get("ratio") is not None else pp.get("status")),
          "| What do its words do differently? | %s | post_probe.json#words |" % (
              "; ".join("%s: %s" % (f["label"], f["differs"]) for f in (pp["words"].get("flags") or []) + (pp["words"].get("numbers") or [])
                        if f.get("differs")) or "nothing outside the creator's usual"),
          "| Does the creator repeat it? | %s | post_probe.json#repeats |" % pp["repeats"]["label"],
          "| The recipe | %s | %s |" % ("beats from the deep read" if (d.get("recipe") or {}).get("beats") else "no beats yet (watch the video)",
                                       d.get("recipe_file") or "not written (mark the format in formats.json)"),
          "| What did not work? | %s | post_probe.json#repeats, post_probe.json#words, findings.json#did_not_work |" % (
              not_working_short(nw).replace("|", "/")),
          "| What did it cost? | $%.4f | cost.csv |" % d["cost"]["total_usd"], ""]
    for sec, title in (("mechanisms", "Why this one worked, the agent's reading"), ("writing", "Its words, the agent's reading")):
        if fi.get(sec):
            L += ["## " + title, ""] + ["- " + build_report.claim_line(cl) for cl in fi[sec]] + [""]
    L += ["## What did not work (MEASURED by post_probe.py; leads under 6 posts a side)", ""]
    if nw.get("note"):
        L.append("- " + nw["note"])
    if nw.get("post_below"):
        L.append("- [MEASURED] The post itself sits under its creator's usual: %s (%s)." % (
            _x(nw["post_below"]["ratio"]), nw["post_below"]["from"]))
    rep = nw.get("repeats") or {}
    if rep.get("below"):
        L.append("- [MEASURED] %d of the format's %d scored repeats sat under the creator's usual: %s (%s)." % (
            len(rep["below"]), rep["scored"], ", ".join("%s %s" % (q["post_id"], _x(q["ratio"])) for q in rep["below"]),
            rep["from"]))
    elif rep.get("note"):
        L.append("- Repeats: " + rep["note"])
    for x in nw.get("words") or []:
        L.append("- [MEASURED]%s The post %s %s; the creator's posts with it sit at %s (%d posts), without it %s (%d) "
                 "(%s)." % (" A lead, few posts." if x["few"] else "", "has" if x["kind"] == "has" else "lacks",
                            x["label"].lower(), _x(x["with"]["lift"]), x["with"]["posts"], _x(x["without"]["lift"]),
                            x["without"]["posts"], x["from"]))
    if not nw.get("words") and nw.get("words_note"):
        L.append("- Its words: " + nw["words_note"])
    for cl in fi.get("did_not_work") or []:
        L.append("- " + build_report.claim_line(cl))
    L.append("")
    if fi.get("not_read") or d.get("limits"):
        L += ["## Not read", ""] + ["- %s: %s" % (n["what"], n["why"]) for n in fi.get("not_read") or []] + \
             ["- [MEASURED] %s: %s" % (n["what"], n["why"]) for n in d.get("limits") or []] + [""]
    L += ["## Files", "", "post.json (the link) · account.json, posts.csv (the creator's recent posts) · post_probe.json · "
          "videos/<id>/ (the deep read) · formats.json, formats/<id>.md (the recipe) · findings.json · report.html (the "
          "Post report, one file) · report_record.json and radar_rows.json (for a planner connector)", ""]
    return "\n".join(L)


def not_working_short(nw):
    parts = []
    if nw.get("note"):
        parts.append(nw["note"])
    if nw.get("post_below"):
        parts.append("the post itself sits at %s its creator's usual" % _x(nw["post_below"]["ratio"]))
    rep = nw.get("repeats") or {}
    if rep.get("below"):
        parts.append("%d of %d scored repeats sat under the creator's usual" % (len(rep["below"]), rep["scored"]))
    elif rep.get("note"):
        parts.append(rep["note"][:1].lower() + rep["note"][1:])
    if nw.get("words"):
        parts.append("its words: " + "; ".join(("has " if x["kind"] == "has" else "lacks ") + x["label"].lower() +
                                               (" (lead)" if x["few"] else "") for x in nw["words"][:3]))
    return ". ".join(parts) or "nothing measured"


BODY = r"""
var drawn = {post: 0, words: 0, repeats: 0, not_working: 0};
window.__reaReport = {drawn: drawn, ready: false, kind: 'post'};
var PP = D.probe || {}, P = PP.post || {}, C = PP.creator || {}, F = D.findings || {}, Wd = PP.words || {}, Rp = PP.repeats || {};
(PP.creator_posts || []).forEach(function(q){ POSTS[q.post_id] = {url: q.url}; });
POSTS[P.post_id] = {url: P.url};

app.appendChild(el('header', {cls: 'top'},
  el('div', null,
    el('div', {cls: 'kicker', text: 'REA Viral · Post report · ' + (C.network || '') + ' · ' + date(P.published_at)}),
    el('h1', {text: '@' + (C.handle || '') + '\'s post'}),
    el('div', {cls: 'sub'}, el('a', {href: P.url, text: P.url}), Wd.first_line ? ' · "' + Wd.first_line + '"' : '')),
  el('div', {cls: 'row'}, themeButton())));
app.appendChild(el('div', {cls: 'stats'},
  stat(P.ratio != null ? xr(P.ratio) : (P.ratio_so_far != null ? xr(P.ratio_so_far) + ' so far' : '—'), 'its creator\'s usual'),
  stat(num(P.usual), 'usual ' + (P.metric || 'views') + ', the median of ' + (P.usual_from_posts || 0) + ' other posts'),
  stat(num(P.views), 'views'),
  stat(P.rank_among_creator ? '#' + P.rank_among_creator : '—', 'of ' + (P.creator_scored || 0) + ' scored posts of the creator'),
  stat(Rp.format ? (Rp.times + ' more') : '—', Rp.format ? 'times the creator made this format' : 'format not marked')));
app.appendChild(legend());
if (PP.status && PP.status !== 'ok') app.appendChild(el('div', {cls: 'status'}, el('strong', {text: 'Status: ' + PP.status + '. '}), PP.status_note || ''));

(function(){
  var s = section('answer', 'Why this one worked', 'Against its own creator\'s usual, not against the biggest numbers. Each line carries its evidence.');
  var pic = D.sheet ? el('img', {src: D.sheet, alt: 'The first three seconds'}) : (D.cover ? el('img', {src: D.cover, alt: 'The cover'}) : el('div', {cls: 'empty', text: D.light ? 'The light page keeps no picture: open the post.' : 'No cover or frames saved.'}));
  var right = el('div', null);
  if (F.headline) right.appendChild(el('div', {cls: 'answer'}, chip(F.headline.evidence), F.headline.text));
  right.appendChild(el('div', {cls: 'claim'}, chip('MEASURED'), P.ratio != null ? (xr(P.ratio) + ' its creator\'s usual: ' + num(P.views) + ' ' + (P.metric || 'views') + ' against the median ' + num(P.usual) + ' of ' + P.usual_from_posts + ' other posts.') : (PP.status_note || '')));
  (F.mechanisms || []).forEach(function(c){ right.appendChild(claim(c)); });
  var n = D.notes || {}, se = n.seen || {};
  if (n.read === true){
    var kv = el('div', {cls: 'kv', style: 'margin-top:10px'});
    var mv = D.measured_video;
    if (mv){ kv.appendChild(el('span', {cls: 'k', text: 'Measured'})); kv.appendChild(el('span', null, chip('MEASURED'),
      (mv.length_s != null ? mv.length_s.toFixed(1) + ' s' : '—') + (mv.cuts_per_10s != null ? ' · ' + mv.cuts_per_10s + ' cuts per 10 s' : '') +
      (mv.words_per_minute != null ? ' · ' + mv.words_per_minute + ' words/min' : ' · words/min not measured: no subtitles'))); }
    [['Hook', se.hook], ['First frame', se.first_frame], ['On screen', se.text_on_screen], ['Sound', se.sound], ['The turn', se.turn], ['The ask', se.ask]].forEach(function(r){
      var v = r[1] && typeof r[1] === 'object' ? (r[1].text || '') + (r[1].at != null ? ' (' + r[1].at + ' s)' : '') : (r[1] || '');
      kv.appendChild(el('span', {cls: 'k', text: r[0]})); kv.appendChild(el('span', null, chip('SEEN'), v || '—')); });
    right.appendChild(kv);
  } else right.appendChild(el('div', {cls: 'empty', style: 'margin-top:8px', text: n.read === false ? 'The video was not read: ' + (n.not_read_reason || '') : 'The video has not been watched yet.'}));
  s.appendChild(el('div', {cls: 'panel hero'}, el('a', {href: P.url, title: 'Open the post'}, pic), right));
  drawn.post = 1;
})();

(function(){
  var s = section('words', 'Its words beside the creator\'s usual', Wd.note || '');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (Wd.status !== 'ok'){ p.appendChild(el('div', {cls: 'empty', text: Wd.note || 'No words to read.'})); return; }
  var t = el('table', null, el('tr', null, el('th', {text: 'In its words'}), el('th', {text: 'This post'}), el('th', {text: 'The creator\'s other posts'}), el('th', {text: 'Different?'})));
  (Wd.flags || []).forEach(function(f){
    t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), f.label), el('td', {text: f.post === true ? 'yes' : (f.post === false ? 'no' : 'unknown')}),
      el('td', {cls: 'small', text: f.creator_known ? f.creator_uses + ' of ' + f.creator_known + (f.creator_with.posts ? '; with it ' + xr(f.creator_with.lift) + ', without ' + xr(f.creator_without.lift) : '') : 'unknown'}),
      el('td', {cls: 'small', text: f.differs || '—'}))); drawn.words++; });
  (Wd.numbers || []).forEach(function(f){
    t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), f.label), el('td', {text: String(f.post)}), el('td', {cls: 'small', text: 'median ' + f.creator_median + ' (usual ' + f.creator_usual[0] + '–' + f.creator_usual[1] + ')'}),
      el('td', {cls: 'small', text: f.differs || '—'}))); drawn.words++; });
  p.appendChild(t);
  (F.writing || []).forEach(function(c){ p.appendChild(claim(c)); });
})();

(function(){
  var s = section('repeats', 'Does the creator repeat it?', Rp.label || '');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (!Rp.format){ p.appendChild(el('div', {cls: 'empty', text: Rp.label})); return; }
  p.appendChild(el('div', {cls: 'small', style: 'margin-bottom:8px'}, chip('MEASURED'), Rp.label + '.'));
  var t = el('table', null, el('tr', null, el('th', {text: 'Post'}), el('th', {text: 'Date'}), el('th', {cls: 'num', text: 'Against its usual'})));
  (Rp.posts || []).forEach(function(q){ t.appendChild(el('tr', null, el('td', null, el('a', {href: q.url, text: q.post_id})), el('td', {text: date(q.published_at)}), el('td', {cls: 'num', text: q.ratio != null ? xr(q.ratio) : q.status.replace('_', ' ')}))); drawn.repeats++; });
  p.appendChild(t);
  var rc = D.recipe || {};
  var kv = el('div', {cls: 'kv', style: 'margin-top:12px'}, el('span', {cls: 'k', text: 'Recipe'}), el('span', null, D.recipe_file ? el('a', {href: D.recipe_file, text: D.recipe_file}) : 'not written'));
  if (rc.hook_pattern) { kv.appendChild(el('span', {cls: 'k', text: 'Hook'})); kv.appendChild(el('span', {text: rc.hook_pattern})); }
  if ((rc.beats || []).length) { kv.appendChild(el('span', {cls: 'k', text: 'Beats'})); kv.appendChild(el('span', {text: rc.beats.map(function(b){ return b.at + ' s ' + b.what + (b.text ? ': ' + b.text : ''); }).join(' → ')})); }
  else { kv.appendChild(el('span', {cls: 'k', text: 'Beats'})); kv.appendChild(el('span', {cls: 'muted', text: 'none yet: the beats come from watching the video'})); }
  p.appendChild(kv);
})();

(function(){
  var NW = D.not_working || {}, RP = NW.repeats || {};
  var s = section('not-working', 'What did not work', 'The mirror of why it worked: what in this post sits under its creator\'s usual. With one creator\'s posts these are leads; one post proves no cause.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  if (NW.note) p.appendChild(el('div', {cls: 'empty', style: 'margin-bottom:8px', text: NW.note}));
  (F.did_not_work || []).forEach(function(c){ p.appendChild(claim(c)); drawn.not_working++; });
  if (NW.post_below){ p.appendChild(el('div', {cls: 'claim'}, chip('MEASURED'), 'The post itself sits at ' + xr(NW.post_below.ratio) + ' its creator\'s usual.')); drawn.not_working++; }
  p.appendChild(el('h3', {text: 'Its repeats under the creator\'s usual', style: 'margin-top:10px'}));
  if ((RP.below || []).length){
    p.appendChild(el('div', {cls: 'small', style: 'margin-bottom:6px'}, chip('MEASURED'), RP.below.length + ' of the ' + RP.scored + ' scored repeats of ' + (RP.name || RP.format) + ' sat under the creator\'s usual. ', el('span', {cls: 'muted', text: 'From ' + RP.from})));
    RP.below.forEach(function(q){ p.appendChild(el('div', {cls: 'fl'}, el('div', {cls: 'r', text: xr(q.ratio)}), el('div', {cls: 't'}, el('a', {href: q.url, text: q.post_id}), ' · ' + date(q.published_at)))); drawn.not_working++; });
  } else p.appendChild(el('div', {cls: 'empty', text: RP.note || 'Every scored repeat sat at the creator\'s usual or over it.'}));
  p.appendChild(el('h3', {text: 'Its words beside the creator\'s weaker posts', style: 'margin-top:14px'}));
  if ((NW.words || []).length){
    var t = el('table', null, el('tr', null, el('th', {text: 'In its words'}), el('th', {text: 'This post'}), el('th', {cls: 'num', text: 'Creator\'s posts with it'}), el('th', {cls: 'num', text: 'Without it'})));
    NW.words.forEach(function(x){ t.appendChild(el('tr', null, el('td', null, chip('MEASURED'), x.label, x.few ? el('span', {cls: 'muted small', text: ' · a lead, few posts'}) : null), el('td', {text: x.kind === 'has' ? 'has it' : 'lacks it'}),
      el('td', {cls: 'num', text: x['with'].posts + ' posts · ' + xr(x['with'].lift)}), el('td', {cls: 'num', text: x.without.posts + ' posts · ' + xr(x.without.lift)}))); drawn.not_working++; });
    p.appendChild(t);
  } else p.appendChild(el('div', {cls: 'empty', text: NW.words_note || 'Nothing in its words goes with the creator\'s weaker posts.'}));
})();

waysToMake('Asked once, after this page: make this format (Basic, Standard or Advanced), draft posts with its hook, or take the creator\'s whole account or its niche.');
sourcesSection(D.sources, F.not_read, D.cost, [picturesLine(D.pictures)].filter(Boolean), D.limits);
app.appendChild(el('footer', null, 'Post report. Built ' + D.built_at + ' by REA Viral ' + D.skill_version + ' from post_probe.json, findings.json and the run\'s files; one file, its picture inside it.'));
stackTables();
window.__reaReport.ready = true;
"""


def build(folder, light_only=False):
    import validate
    rep = validate.validate(folder)
    if rep.errors:
        lines = ["%s: %s" % (e["where"], e["problem"]) for e in rep.errors[:30]]
        die("validate.py found %d error(s); the page is not built:\n  " % len(rep.errors) + "\n  ".join(lines), 1)
    d = page_data(folder, light=light_only)
    title = "@%s's post · Post report · REA Viral" % (d["probe"]["creator"].get("handle") or "")
    if not light_only:
        write_text(os.path.join(folder, "report.html"), page_kit.page(title, "POST.md", d, BODY))
    write_text(os.path.join(folder, "report-light.html"), page_kit.page(title, "POST.md", page_kit.light_data(d), BODY))
    write_text(os.path.join(folder, "POST.md"), post_md(d))
    d["hand_over"] = hand_over_files(folder, d)
    d["light_only"] = light_only
    return d


def hand_over_files(folder, d):
    """report_record.json and radar_rows.json (hand_over.py): the Post report's record, and the post's own format as
    one row keyed by the post itself (the planner's own key for a saved post), when its format is marked."""
    pp, fi = d["probe"], d["findings"] or {}
    p, c, rp = pp["post"], pp["creator"], pp.get("repeats") or {}
    net = c.get("network")
    rows, note = [], None
    if rp.get("format") and pp.get("status") in ("ok", "too_new", "weaker_basis"):
        rec = d.get("recipe") or {}
        fmt = {"id": rp["format"], "name": rp.get("name") or rec.get("name"),
               "lift": (rec.get("measured") or {}).get("lift"), "container": {"hook": rec.get("hook_pattern")}}
        face = {"url": p.get("url"), "network": net, "post_id": p.get("post_id"), "account": c.get("handle"),
                "caption": p.get("caption"),
                "numbers": hand_over.numbers_of(p, c.get("followers"), (pp.get("generated_at") or iso(now_utc())))}
        try:
            acc = read_json(os.path.join(folder, "account.json"))
            face["numbers"]["at"] = acc.get("read_at") or face["numbers"]["at"]
        except (OSError, ValueError):
            pass
        proof = [p.get("url")] + [q.get("url") for q in rp.get("posts") or [] if (q.get("ratio") or 0) >= 1.0]
        rows.append(hand_over.format_row(hand_over.post_key(net, p["post_id"]), fmt, rec, face, creators=1, proof=proof))
        note = "The post's own format, for the user's saved formats (keyed by the post)."
    elif not rp.get("format"):
        note = "No format to offer: the post's format is not marked (formats.json)."
    else:
        note = "No format to offer: %s" % (pp.get("status_note") or pp.get("status"))
    fallback = brief.measured_answer("post", d)      # never empty: findings.json may have no headline
    first = hand_over.first_line(p.get("caption"))
    br = brief.post(folder, d, rows[0]["key"] if rows else None, None)
    cover = page_kit.write_cover(folder, page_kit.existing(folder, p.get("cover_file")))
    rec_, _ = hand_over.write(folder, "post", {
        "title": first or "@%s's post on %s" % (c.get("handle"), hand_over.NETWORK_NAMES.get(net, net)),
        "subject": {"network": net, "handle": c.get("handle"), "url": p.get("url")},
        "summary": hand_over.summary_text(fi.get("headline"), fi.get("did_not_work"), fallback),
        "read": {"posts": c.get("posts_read"), "creators": 1},
        "sources": d.get("sources"), "cost": d.get("cost"),
        "page_path": os.path.join(folder, "report.html"), "run_name": os.path.basename(os.path.abspath(folder)),
    }, rows, note, brief=br, cover=cover)
    return {"record": rec_, "rows": len(rows), "brief": br}
