"""The look and the small helpers shared by the Niche report and the Post report (report_niche.py, report_post.py),
and the pictures every report keeps inside itself (build_report.py uses those too).

The Account report (build_report.py) keeps its own copy of the same look, unchanged since version 1. Every report:
ONE file that opens from file:// with no other file beside it (a planner keeps it as one file), dark by default with a
Light button, no script from anywhere, fonts from Google Fonts when online, every claim with its evidence label, and
no other creator's video embedded or re-hosted: covers and frame sheets are small pictures inside the page (data URIs,
each under a cap, all under one budget), each linked to the original post.
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile

HEAD = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0c0e11;--panel:#14171c;--panel2:#1a1e24;--line:#262b33;--text:#e9ecef;--muted:#98a2ad;--faint:#6c7580;
--accent:#33efab;--accent-text:#0f1115;--measured:#33efab;--seen:#7db9ff;--inferred:#f3c56b;--bad:#ff7a7a;
--scale:#33efab;--under:#7db9ff;--fading:#f3c56b;--drop:#ff8f8f;--radius:12px}
:root[data-theme="light"]{--bg:#f6f7f9;--panel:#ffffff;--panel2:#f0f2f5;--line:#dfe3e8;--text:#14171c;--muted:#56606b;
--faint:#7d8792;--measured:#0f9e6e;--seen:#2f6fd0;--inferred:#a7700b;--bad:#c93c3c;--scale:#0f9e6e;--under:#2f6fd0;
--fading:#a7700b;--drop:#c93c3c}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text)}
body{font-family:Manrope,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;
-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
a{color:inherit;text-decoration:underline;text-decoration-color:var(--faint);text-underline-offset:2px}
a:hover{text-decoration-color:var(--accent)}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header.top{display:flex;gap:16px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
header.top>div:first-child{min-width:0;flex:1 1 320px}
.kicker{color:var(--muted);font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
h1{font-size:34px;line-height:1.1;margin:6px 0 6px;font-weight:800;letter-spacing:-.02em;overflow-wrap:anywhere}
h2{font-size:20px;margin:0 0 4px;font-weight:800;letter-spacing:-.01em}
h3{font-size:15px;margin:0 0 6px;font-weight:700}
.sub{color:var(--muted);overflow-wrap:anywhere}
.btn{font:inherit;font-size:13px;font-weight:700;border-radius:8px;padding:7px 14px;cursor:pointer;border:1px solid var(--line);
background:var(--panel2);color:var(--text)}
.btn.primary{background:var(--accent);color:var(--accent-text);border-color:transparent}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:20px 0 6px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.stat .v{font-size:22px;font-weight:800}
.stat .l{color:var(--muted);font-size:12px}
section{margin-top:34px}
.sec-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px;overflow-x:auto}
.grid2{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:14px}
@media (max-width:860px){.grid2{grid-template-columns:minmax(0,1fr)}}
.grid2>*{min-width:0}
.ev{display:inline-block;font-size:10.5px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;margin-right:6px;
border:1px solid currentColor;vertical-align:1px;white-space:nowrap}
.ev.MEASURED{color:var(--measured)}.ev.SEEN{color:var(--seen)}.ev.INFERRED{color:var(--inferred)}.ev.NONE{color:var(--faint)}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin-top:10px}
.claim{padding:10px 0;border-top:1px solid var(--line)}
.claim:first-child{border-top:none}
.claim .basis{color:var(--muted);font-size:13px;margin-top:3px;overflow-wrap:anywhere}
.answer{font-size:19px;font-weight:700;line-height:1.4}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--muted);font-weight:700;font-size:12px;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.num{text-align:right;white-space:nowrap}
.q{display:inline-block;font-size:11.5px;font-weight:800;border-radius:999px;padding:1px 8px;color:var(--accent-text);white-space:nowrap}
.q.scale_it{background:var(--scale)}.q.underused{background:var(--under)}.q.overused,.q.fading{background:var(--fading)}.q.drop{background:var(--drop)}
.q.too_few,.q.post{background:var(--faint)}
svg text{font-family:inherit;fill:var(--muted);font-size:11px}
svg .axis{stroke:var(--line)}
svg .split{stroke:var(--faint);stroke-dasharray:4 4}
.chart{width:100%;height:auto;display:block}
.muted{color:var(--muted)}.small{font-size:12.5px}
.prompt{white-space:pre-wrap;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:13.5px;margin:8px 0}
.play{border-top:1px solid var(--line);padding:14px 0}
.play:first-child{border-top:none;padding-top:0}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.pill{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:1px 8px;color:var(--muted)}
.status{border-left:3px solid var(--inferred);padding:10px 14px;background:var(--panel);border-radius:8px;margin-top:16px}
.empty{color:var(--faint);font-size:13.5px}
.quote{border-left:2px solid var(--line);padding-left:10px;margin:6px 0;font-size:13.5px;overflow-wrap:anywhere}
footer{margin-top:48px;color:var(--faint);font-size:12.5px}
.v-lifts{color:var(--measured);font-weight:800}.v-sinks{color:var(--bad);font-weight:800}.v-other{color:var(--muted)}
.fl{border-top:1px solid var(--line);padding:9px 0;display:grid;grid-template-columns:64px minmax(0,1fr);gap:10px;align-items:baseline}
.fl:first-of-type{border-top:none}
.fl .r{font-weight:800;text-align:right;white-space:nowrap}
.fl .t{overflow-wrap:anywhere}
details.more{margin-top:12px}
details.more summary{cursor:pointer;color:var(--muted);font-size:13px;font-weight:700}
.voice h3{margin-top:12px}
.voice p{margin:4px 0;font-size:13.5px;overflow-wrap:anywhere}
.rules{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 4px}
.kv{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;font-size:13px}
.kv .k{color:var(--muted)}
.gallery{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}
.fcard{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px;min-width:0}
.fcard.not{opacity:.78}
.fcard .head{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.fcard .head h3{margin:0;font-size:17px}
.proof{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:10px;margin-top:12px}
.proof a{text-decoration:none;color:var(--muted);font-size:12px;min-width:0}
.proof img,.proof .ph{width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:8px;background:var(--panel2);display:block;margin-bottom:4px}
.proof img.sheet{aspect-ratio:auto;object-fit:contain}
.proof .who{color:var(--text);font-weight:700;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hero{display:grid;grid-template-columns:minmax(0,220px) minmax(0,1fr);gap:16px;align-items:start}
@media (max-width:640px){.hero{grid-template-columns:minmax(0,1fr)}}
.hero img{width:100%;border-radius:10px;background:var(--panel2);display:block}
.levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.level{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.level h3{margin:0 0 4px}
/*__STACK_CSS__*/
</style>
</head>
<body>
<div class="wrap" id="app"><noscript>This page draws itself with JavaScript. __MD__ beside it holds the same findings as text.</noscript></div>
<script type="application/json" id="rea-data">__DATA__</script>
"""

STACK_CSS = r"""
/* Tables on a phone (0.4.2): at 480 px or less a table of three columns or more becomes a list of rows. The row's
   title (its first column, or the one data-lead names) comes first, with its number when the table has a # column;
   every other cell follows under its own column's name, three to a line in even columns (a cell whose chip needs more
   room takes it); a long cell takes the whole line.
   Nothing is dropped, nothing scrolls sideways, no text in any table is under 12 px (its chips too). stackTables()
   marks the tables. */
@media (max-width:480px){
table.stk,table.stk tbody{display:block;width:100%}
table.stk tr.hd{display:none}
table.stk tr{display:flex;flex-wrap:wrap;align-items:flex-start;gap:6px 14px;padding:10px 0;border-bottom:1px solid var(--line)}
table.stk tr:last-child{border-bottom:none}
table.stk td{display:block;flex:0 0 calc((100% - 28px) / 3);padding:0;border:none;text-align:left;white-space:normal;overflow-wrap:anywhere;width:auto!important}
table.stk td[data-label]::before{content:attr(data-label);display:block;color:var(--muted);font-size:12px;font-weight:700;line-height:1.35}
table.stk td.lead{flex:1 1 100%;font-weight:700;order:-1}
table.stk tr.has-rn td.lead{flex-basis:calc(100% - 48px)}
table.stk td.rn{flex:0 0 auto;font-weight:800;order:-2}
table.stk td:empty{display:none}
table.stk td.wide{flex-basis:100%}
table .q,table .ev{font-size:12px}
table.stk .small{font-size:12.5px}
}
"""

STACK_JS = r"""
/* Marks every table of three columns or more for the phone layout (STACK_CSS): its header row, its # cells, each row's
   title cell (data-lead on the table names its column; a row whose title cell is empty takes its first filled cell),
   and every other cell's column name (data-label). A cell of more than 40 characters takes a whole line. */
function stackTables(){
  Array.prototype.forEach.call(document.querySelectorAll('table'), function(t){
    var rows = Array.prototype.slice.call(t.rows), head = null;
    rows.forEach(function(r){ if (!head && r.querySelector('th')) head = r; });
    if (!head || head.cells.length < 3) return;
    var labels = Array.prototype.map.call(head.cells, function(c){ return c.textContent.trim(); });
    var rn = labels.indexOf('#');
    var lead = t.getAttribute('data-lead') != null ? Number(t.getAttribute('data-lead')) : (rn === 0 ? 1 : 0);
    t.classList.add('stk');
    head.classList.add('hd');
    rows.forEach(function(r){
      if (r === head) return;
      var cells = Array.prototype.slice.call(r.cells), L = lead;
      var filled = function(i){ return cells[i] && i !== rn && cells[i].textContent.trim() !== ''; };
      if (!filled(L)) for (var i = 0; i < cells.length; i++) if (filled(i)) { L = i; break; }
      cells.forEach(function(c, i){
        if (i === rn) { c.classList.add('rn'); if (c.textContent.trim()) r.classList.add('has-rn'); return; }
        if (i === L) { c.classList.add('lead'); return; }
        if (labels[i]) c.setAttribute('data-label', labels[i]);
        if (c.textContent.length > 40) c.classList.add('wide');
      });
    });
  });
}
"""

LABELS_JS = r"""
/* A chart's labels (0.4.1): each bubble carries its number (the same as in the table beside the chart), and its name
   goes beside it where it fits: inside the plot, clear of the other names, the other bubbles and the corner names.
   Tried in turn: the side facing the middle, the other side, then a line up or down at a time, then above and below.
   A name that fits nowhere is left off (the number says which format it is) and returned, so the page lists it. */
function bubbleNumber(g, cx, cy, n, r, arrow){
  // the bubble's number, on the side away from its direction arrow (the arrow starts at the centre), so neither hides the other
  var dy = (arrow && Math.abs(arrow) > 3) ? (arrow > 0 ? 1 : -1) * Math.max(7, (r || 9) * 0.45) : 0;
  g.appendChild(sv('text', {x: cx, y: cy + dy + 4, 'text-anchor': 'middle', text: String(n), 'class': 'bnum', fill: 'var(--text)', 'font-weight': 800, 'font-size': 11})); }
function placeLabels(labels, plot, avoid){
  var LH = 15, CW = 6.9, taken = (avoid || []).slice(), off = [];
  function box(x, y, w, a){ var x0 = a === 'end' ? x - w : (a === 'middle' ? x - w / 2 : x); return {x0: x0, y0: y - 11, x1: x0 + w, y1: y + 4}; }
  function fits(b, self){
    if (b.x0 < plot.x0 + 3 || b.x1 > plot.x1 - 3 || b.y0 < plot.y0 + 3 || b.y1 > plot.y1 - 3) return false;
    if (taken.some(function(t){ return b.x0 < t.x1 + 3 && t.x0 < b.x1 + 3 && b.y0 < t.y1 + 1 && t.y0 < b.y1 + 1; })) return false;
    return !labels.some(function(o){ if (o === self) return false;
      var nx = Math.max(b.x0, Math.min(o.cx, b.x1)), ny = Math.max(b.y0, Math.min(o.cy, b.y1));
      return (nx - o.cx) * (nx - o.cx) + (ny - o.cy) * (ny - o.cy) < (o.r + 1) * (o.r + 1); });
  }
  labels.forEach(function(l){
    var w = l.name.length * CW, c = [], k;
    var sides = l.cx > (plot.x0 + plot.x1) / 2 ? [[-1, 'end'], [1, 'start']] : [[1, 'start'], [-1, 'end']];
    [0, -1, 1, -2, 2, -3, 3].forEach(function(s){ sides.forEach(function(sd){ c.push([l.cx + sd[0] * (l.r + 6), l.cy + 4 + s * LH, sd[1]]); }); });
    c.push([l.cx, l.cy - l.r - 6, 'middle']); c.push([l.cx, l.cy + l.r + 14, 'middle']);
    for (k = 0; k < c.length; k++){
      var b = box(c[k][0], c[k][1], w, c[k][2]);
      if (fits(b, l)){ taken.push(b); l.g.appendChild(sv('text', {x: c[k][0], y: c[k][1], 'text-anchor': c[k][2], text: l.name, 'class': 'lbl', fill: 'var(--text)', 'font-weight': 700, 'font-size': 12})); break; }
    }
    if (k === c.length) off.push(l);
  });
  return off;
}
function cornerBox(x, y, text, a){ var w = text.length * 8; var x0 = a === 'end' ? x - w : x; return {x0: x0, y0: y - 12, x1: x0 + w, y1: y + 4}; }
"""

JS_HELPERS = r"""
var D = JSON.parse(document.getElementById('rea-data').textContent);
var SVGNS = 'http://www.w3.org/2000/svg';
function el(tag, attrs){
  var n = document.createElement(tag);
  attrs = attrs || {};
  for (var k in attrs){
    if (!Object.prototype.hasOwnProperty.call(attrs, k) || attrs[k] == null) continue;
    if (k === 'text') n.textContent = String(attrs[k]);
    else if (k === 'cls') n.className = attrs[k];
    else if (k === 'href'){ var u = safeHref(attrs[k]); if (u) { n.setAttribute('href', u); n.setAttribute('target', '_blank'); n.setAttribute('rel', 'noopener noreferrer'); } }
    else if (k === 'src'){ var s = safeSrc(attrs[k]); if (s) n.setAttribute('src', s); }
    else if (k.indexOf('on') === 0) n.addEventListener(k.slice(2), attrs[k]);
    else n.setAttribute(k, attrs[k]);
  }
  for (var i = 2; i < arguments.length; i++) add(n, arguments[i]);
  return n;
}
function add(n, c){
  if (c == null || c === false) return;
  if (Array.isArray(c)) { c.forEach(function(x){ add(n, x); }); return; }
  n.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
}
function sv(tag, attrs){
  var n = document.createElementNS(SVGNS, tag);
  for (var k in attrs || {}) { if (attrs[k] != null) { if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); } }
  return n;
}
/*__LABELS_JS__*/
function safeHref(u){ u = String(u || ''); return /^https?:\/\//i.test(u) ? u : (/^[\w./@-]+$/.test(u) && u.indexOf('..') < 0 ? u : null); }
function safeSrc(u){ u = String(u || ''); if (/^https:\/\//i.test(u) || /^data:image\/(jpeg|png|webp|gif);base64,[A-Za-z0-9+\/=]+$/.test(u)) return u; return (/^[\w./@-]+$/.test(u) && u.indexOf('..') < 0) ? u : null; }
function num(n){ if (n == null) return '—'; var a = Math.abs(n);
  if (a >= 1e9) return (n/1e9).toFixed(a >= 1e10 ? 0 : 1) + 'B'; if (a >= 1e6) return (n/1e6).toFixed(a >= 1e7 ? 0 : 1) + 'M';
  if (a >= 1e4) return (n/1e3).toFixed(0) + 'K'; if (a >= 1e3) return (n/1e3).toFixed(1) + 'K'; return String(Math.round(n)); }
function pct(x){ return x == null ? '—' : (x > 0 && x < 0.1 ? (x * 100).toFixed(1) : Math.round(x * 100)) + '%'; }
function xr(x){ if (x == null) return '—'; if (x >= 0.995 && x < 1.005 && x !== 1) return x.toFixed(3) + '×'; return (x >= 10 ? x.toFixed(0) : x.toFixed(2).replace(/0$/, '').replace(/\.$/, '')) + '×'; }
function date(s){ return s ? String(s).slice(0, 10) : '—'; }
var EVTIP = {MEASURED: 'Computed by the skill\'s scripts from the data files', SEEN: 'A frame, a comment or a row shows it (linked)', INFERRED: 'Reasoned, with the basis written out'};
function chip(ev){ return el('span', {cls: 'ev ' + (ev || 'NONE'), text: ev || 'UNKNOWN', title: EVTIP[ev] || 'not known'}); }
var QN = {scale_it: 'Scale it', underused: 'Underused', overused: 'Overused', fading: 'Overused', drop: 'Drop', too_few: 'Not placed', post: 'One post'};
var QC = {scale_it: 'var(--scale)', underused: 'var(--under)', overused: 'var(--fading)', fading: 'var(--fading)', drop: 'var(--drop)', too_few: 'var(--faint)'};
var app = document.getElementById('app');
var POSTS = {};
function postLink(id){ var p = POSTS[id]; return p ? el('a', {href: p.url, text: id}) : el('span', {text: id}); }
function postLinks(ids){ var out = []; (ids || []).forEach(function(id, i){ if (i) out.push(', '); out.push(postLink(id)); }); return out; }
function claim(c){
  if (!c) return null;
  var src = [];
  if (c.evidence === 'SEEN') { if (c.posts && c.posts.length) src.push('Seen in ', postLinks(c.posts)); (c.links || []).forEach(function(u, i){ src.push(i || src.length ? ' · ' : '', el('a', {href: u, text: u.replace(/^https?:\/\//, '').slice(0, 48)})); }); }
  if (c.evidence === 'INFERRED') src.push('Basis: ' + (c.basis || ''));
  if (c.evidence === 'MEASURED') src.push('From ' + (c.from || ''));
  if (c.evidence !== 'SEEN' && c.posts && c.posts.length) src.push(' · posts: ', postLinks(c.posts));
  return el('div', {cls: 'claim'},
    el('div', null, chip(c.evidence), c.title ? el('strong', {text: c.title + '. '}) : null, c.text || c.what || ''),
    src.length ? el('div', {cls: 'basis'}, src) : null);
}
function section(id, title, sub){ var s = el('section', {id: id}); s.appendChild(el('div', {cls: 'sec-head'}, el('div', null, el('h2', {text: title}), sub ? el('div', {cls: 'sub small', text: sub}) : null))); app.appendChild(s); return s; }
function stat(v, l){ return el('div', {cls: 'stat'}, el('div', {cls: 'v', text: v}), el('div', {cls: 'l', text: l})); }
function themeButton(){ return el('button', {cls: 'btn', id: 'theme', type: 'button', text: 'Light', onclick: function(e){
  var r = document.documentElement; var dark = r.getAttribute('data-theme') !== 'light';
  r.setAttribute('data-theme', dark ? 'light' : 'dark'); e.target.textContent = dark ? 'Dark' : 'Light'; }}); }
function legend(){ return el('div', {cls: 'legend'}, el('span', null, chip('MEASURED'), EVTIP.MEASURED), el('span', null, chip('SEEN'), EVTIP.SEEN), el('span', null, chip('INFERRED'), EVTIP.INFERRED)); }
function picturesLine(P){
  if (P && P.light) return 'The light page: no pictures inside, each grey tile links to its post. The full report (report.html) keeps the pictures.';
  if (!P || !(P.inside || P.left_out)) return null;
  return 'Pictures: ' + P.inside + ' inside this page' + (P.shrunk_with ? ' (smaller copies)' : '') + ', each linked to its post' +
    (P.left_out ? '; ' + P.left_out + ' left out to keep the page small (they stay in the run folder)' : '') + '.';
}
function waysToMake(intro){
  var s = section('make', 'Ways to make a format', intro || 'Asked once, after the report, for a format whose recipe has beats from watched videos. Each starts from the recipe and is checked against it.');
  var g = el('div', {cls: 'levels'});
  [['Basic', 'An HTML page rendered to MP4 in a browser, frame by frame. The page stays, to change and render again.'],
   ['Standard', 'An editable video project, your pick of two ways: GreenLight Motion (a page with options, opens in GreenLight Dash) or HyperFrames (HTML scenes, its own preview and editor).'],
   ['Advanced', 'GreenLight Dash\'s Rebuild by Style (PRO): the reference post\'s style studied frame by frame and rebuilt for your product.']].forEach(function(l){
    g.appendChild(el('div', {cls: 'level'}, el('h3', {text: l[0]}), el('div', {cls: 'small muted', text: l[1]}))); });
  s.appendChild(el('div', {cls: 'panel'}, g, el('div', {cls: 'small muted', style: 'margin-top:10px', text: 'With your own clips, product and words; never the creator\'s footage, face or voice. Every result is checked against the recipe\'s pacing (remake_check.py).'})));
}
function playsSection(plays){
  if (!plays || !plays.length) return;
  var s = section('plays', 'The plays', plays.length + ' plays, each with its evidence, the effort and what not to copy.');
  var p = el('div', {cls: 'panel'}); s.appendChild(p);
  plays.forEach(function(pl, i){
    p.appendChild(el('div', {cls: 'play'},
      el('div', {cls: 'row'}, el('h3', {text: (i + 1) + '. ' + pl.title, style: 'margin:0'}), el('span', {cls: 'pill', text: 'effort ' + pl.effort}), pl.first_result ? el('span', {cls: 'pill', text: 'first result: ' + pl.first_result}) : null),
      claim({evidence: pl.evidence, text: pl.text || pl.what || '', basis: pl.basis, posts: pl.posts, links: pl.links, from: pl.from}),
      pl.dont_copy ? el('div', {cls: 'small'}, el('strong', {text: 'Do not copy: '}), pl.dont_copy) : null,
      el('div', {cls: 'prompt', text: pl.prompt || ''}),
      el('button', {cls: 'btn primary', type: 'button', text: 'Copy prompt', onclick: function(e){ copy(pl.prompt || '', e.target); }})));
  });
  function copy(text, b){
    function ok(){ b.textContent = 'Copied'; setTimeout(function(){ b.textContent = 'Copy prompt'; }, 1400); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback); else fallback();
    function fallback(){ var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); ok(); } catch (e) {} document.body.removeChild(t); }
  }
}
function sourcesSection(sources, notRead, cost, extra, limits){
  var s = section('sources', 'What was read, with what, and what it cost');
  var p = el('div', {cls: 'grid2'}); s.appendChild(p);
  var left = el('div', {cls: 'panel'});
  left.appendChild(el('h3', {text: 'Sources'}));
  (sources || []).forEach(function(x){ left.appendChild(el('div', {cls: 'small', style: 'margin:4px 0'}, el('strong', {text: (x.what || '') + ': '}), (x.via || '') + (x.cost_usd != null ? ' · $' + x.cost_usd : '') + (x.notes ? ' · ' + x.notes : ''))); });
  left.appendChild(el('h3', {text: 'Not read', style: 'margin-top:12px'}));
  if (!(notRead || []).length && !(limits || []).length) left.appendChild(el('div', {cls: 'empty', text: 'Nothing listed.'}));
  (notRead || []).forEach(function(n){ left.appendChild(el('div', {cls: 'small', style: 'margin:4px 0'}, el('strong', {text: n.what + ': '}), n.why)); });
  (limits || []).forEach(function(n){ left.appendChild(el('div', {cls: 'small', style: 'margin:4px 0', 'data-limit': n.what}, chip('MEASURED'), el('strong', {text: n.what + ': '}), n.why)); });
  (extra || []).forEach(function(t){ left.appendChild(el('div', {cls: 'small muted', style: 'margin-top:6px', text: t})); });
  p.appendChild(left);
  var right = el('div', {cls: 'panel'});
  right.appendChild(el('h3', {text: 'Cost'}));
  var rows = (cost || {}).rows || [];
  if (!rows.length) right.appendChild(el('div', {cls: 'empty', text: 'No paid calls were made.'}));
  else { var t = el('table', {'data-lead': '1'}, el('tr', null, el('th', {text: 'Step'}), el('th', {text: 'What'}), el('th', {cls: 'num', text: 'Calls'}), el('th', {cls: 'num', text: '$'})));
    rows.forEach(function(r){ t.appendChild(el('tr', null, el('td', {text: r.step}), el('td', {text: r.what}), el('td', {cls: 'num', text: r.calls}), el('td', {cls: 'num', text: Number(r.total_usd).toFixed(4)}))); });
    t.appendChild(el('tr', null, el('td', {text: 'Total'}), el('td'), el('td'), el('td', {cls: 'num', text: '$' + ((cost || {}).total_usd || 0).toFixed(4)})));
    right.appendChild(t); }
  p.appendChild(right);
}
"""


def embed(d):
    s = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")


def page(title, md_name, data, body_js):
    """One self-contained page: the head, the data, one script (helpers + the page's own drawing)."""
    html = HEAD.replace("__TITLE__", title.replace("&", "&amp;").replace("<", "&lt;")).replace("__MD__", md_name)
    html = html.replace("__DATA__", embed(data)).replace("/*__STACK_CSS__*/", STACK_CSS)
    return html + "<script>\n(function(){\n\"use strict\";\n" + JS_HELPERS.replace("/*__LABELS_JS__*/", LABELS_JS + STACK_JS) + body_js + "\n})();\n</script>\n</body>\n</html>\n"


def existing(folder, rel_path):
    if not rel_path:
        return None
    return rel_path if os.path.exists(os.path.join(folder, rel_path)) else None


# ---------------------------------------------------------------------------------------------- pictures inside the page
# A report is ONE file: a planner keeps it as one file, and a person opens it from anywhere. Every picture the page
# draws is put inside it as a data URI: with ffmpeg on PATH a smaller JPEG copy (covers 240 px wide, frame sheets
# 720 px), each under its cap; without ffmpeg the saved file itself when it is under the cap. All pictures together
# stay under one budget, so the page stays under 3 MB. A picture that does not fit is left out of the page (it shows
# as a grey tile, still linked to its post) and counted; it stays in the run folder. Only pictures: never a video.

PICTURE_SPECS = {"cover": {"width": 240, "cap": 45000}, "sheet": {"width": 720, "cap": 160000}}
PICTURE_BUDGET = 2300000     # bytes of data URIs, all pictures together
PAGE_TARGET = 3000000        # the whole page should stay under this; build_report.py prints the size


def _sniff(raw):
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


class Pictures(object):
    """The pictures one page keeps inside itself. get(rel, kind) gives a data URI or None (left out, counted).
    light=True: the light page (report-light.html), which keeps no picture at all."""

    def __init__(self, folder, budget=PICTURE_BUDGET, light=False):
        self.folder = folder
        self.budget = budget
        self.used = 0
        self.inside = 0
        self.left = []
        self.cache = {}
        self.light = light
        self.ffmpeg = None if light else shutil.which("ffmpeg")

    def _smaller(self, path, spec):
        fd, tmp = tempfile.mkstemp(prefix="rea-pic-", suffix=".jpg")
        os.close(fd)
        try:
            for width, q in ((spec["width"], 5), (spec["width"] * 3 // 4, 9), (spec["width"] // 2, 14)):
                try:
                    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-vf",
                                        "scale='min(%d,iw)':-2" % width, "-frames:v", "1", "-q:v", str(q), tmp],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                except (OSError, subprocess.TimeoutExpired):
                    return None
                if r.returncode != 0 or not os.path.exists(tmp):
                    return None
                with open(tmp, "rb") as f:
                    raw = f.read()
                if raw and len(raw) <= spec["cap"]:
                    return raw
            return None
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def get(self, rel, kind="cover"):
        if not rel:
            return None
        if self.light:
            return None
        key = (rel, kind)
        if key in self.cache:
            return self.cache[key]
        path = os.path.join(self.folder, rel)
        uri = None
        if os.path.isfile(path):
            spec = PICTURE_SPECS[kind]
            raw, mime, why = None, None, None
            if self.ffmpeg:
                raw = self._smaller(path, spec)
                mime = "image/jpeg" if raw else None
            if raw is None:
                with open(path, "rb") as f:
                    orig = f.read()
                mime = _sniff(orig)
                if mime and len(orig) <= spec["cap"]:
                    raw = orig
                else:
                    why = ("not a JPEG, PNG, WebP or GIF picture" if not mime else
                           "%d KB, over the %d KB cap%s" % (len(orig) // 1000, spec["cap"] // 1000,
                                                             "" if self.ffmpeg else "; no ffmpeg here to make it smaller"))
            if raw is not None:
                cand = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
                if self.used + len(cand) > self.budget:
                    why = "over the page's picture budget (%d KB)" % (self.budget // 1000)
                else:
                    uri = cand
                    self.used += len(cand)
                    self.inside += 1
            if uri is None:
                self.left.append({"file": rel, "why": why})
        self.cache[key] = uri
        return uri

    def summary(self):
        if self.light:
            return LIGHT_PICTURES
        return {"inside": self.inside, "left_out": len(self.left), "bytes": self.used, "budget": self.budget,
                "shrunk_with": "ffmpeg" if self.ffmpeg else None, "left": self.left[:20]}


# ---------------------------------------------------------------------------------------------- the light page
# report-light.html: the same report with no picture inside (each tile is a grey tile that links to its post) and
# only the data the page draws, for a planner in a chat app that takes a page as text in one call (Pulse: up to
# 1 MB a call, 64 KB practical). The full report.html stays the one to keep and to send by path.

LIGHT_PICTURES = {"inside": 0, "left_out": 0, "bytes": 0, "budget": 0, "shrunk_with": None, "left": [], "light": True}


def strip_pictures(obj):
    """A deep copy with every picture inside the page (a data URI) taken out."""
    if isinstance(obj, dict):
        return dict((k, strip_pictures(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return [strip_pictures(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("data:image/"):
        return None
    return obj


LIGHT_FEATURE_KEYS = ("id", "label", "kind", "verdict", "claim_ok", "usage", "note", "unknown_why")


def light_writing(w):
    """The writing view with only what the page draws: a feature that lifts or sinks whole; the others only as the
    line the "everything else measured" table shows."""
    if not w:
        return w
    w = dict(w)
    w["features"] = [f if f.get("claim_ok") else dict((k, f.get(k)) for k in LIGHT_FEATURE_KEYS)
                     for f in w.get("features") or []]
    w["numbers"] = [f if f.get("claim_ok") else dict((k, f.get(k)) for k in LIGHT_FEATURE_KEYS)
                    for f in w.get("numbers") or []]
    return w


def claim_post_ids(findings):
    """Every post id a claim of findings.json cites (the page links each)."""
    out = set()
    for v in (findings or {}).values():
        for c in v if isinstance(v, list) else [v]:
            if isinstance(c, dict):
                out |= set(x for x in c.get("posts") or [] if isinstance(x, str))
    return out


def light_data(d):
    out = strip_pictures(d)
    out["pictures"] = LIGHT_PICTURES
    out["light"] = True
    return out


# ---------------------------------------------------------------------------------------------- the report's cover
# A planner shows a report with a small picture: the account's own picture (account.json picture_file) or the post's
# own cover. It is written beside the page as report-cover.jpg (ffmpeg makes it 480 px wide) or, without ffmpeg, as a
# copy of the saved file when it is a picture under 300 KB. A run with neither has no cover.

COVER_NAME = "report-cover"
COVER_WIDTH = 480
COVER_CAP = 300000


def write_cover(folder, rel):
    """Write report-cover.<ext> from the picture at rel (relative to the run folder). Returns
    {path, type, size, from} or None; an older cover the skill wrote is removed first."""
    for ext in (".jpg", ".png", ".webp", ".gif"):
        old = os.path.join(folder, COVER_NAME + ext)
        if os.path.exists(old):
            os.remove(old)
    if not rel or not os.path.isfile(os.path.join(folder, rel)):
        return None
    src = os.path.join(folder, rel)
    dest = os.path.join(folder, COVER_NAME + ".jpg")
    if shutil.which("ffmpeg"):
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vf",
                                "scale='min(%d,iw)':-2" % COVER_WIDTH, "-frames:v", "1", "-q:v", "4", dest],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if r.returncode == 0 and os.path.exists(dest) and 0 < os.path.getsize(dest) <= COVER_CAP:
                return {"path": COVER_NAME + ".jpg", "type": "image/jpeg", "size": os.path.getsize(dest), "from": rel}
        except (OSError, subprocess.TimeoutExpired):
            pass
        if os.path.exists(dest):
            os.remove(dest)
    with open(src, "rb") as f:
        raw = f.read()
    mime = _sniff(raw)
    if not mime or len(raw) > COVER_CAP:
        return None
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}[mime]
    with open(os.path.join(folder, COVER_NAME + ext), "wb") as f:
        f.write(raw)
    return {"path": COVER_NAME + ext, "type": mime, "size": len(raw), "from": rel}


def kb(n):
    return ("%.2f MB" % (n / 1e6)) if n >= 1e6 else ("%d KB" % max(1, n // 1000))


def light_line(path):
    n = os.path.getsize(path)
    return "report-light.html: %s, no pictures (for a planner in a chat app that takes the page as text%s)" % (
        kb(n), "" if n <= LIGHT_INLINE else "; over 64 KB, more than a chat passes in one call with ease")


LIGHT_INLINE = 64 * 1024


def size_line(path, pictures):
    """The line build_report.py prints after a page is written: its size, its pictures, the 3 MB target."""
    n = os.path.getsize(path)
    p = pictures or {}
    k = p.get("inside", 0)
    return "report.html: %s, one file (%d picture%s inside%s%s)%s" % (
        ("%.2f MB" % (n / 1e6)) if n >= 1e6 else ("%d KB" % max(1, n // 1000)), k, "" if k == 1 else "s",
        ", smaller copies made with ffmpeg" if p.get("shrunk_with") and p.get("inside") else "",
        (", %d left out to stay small" % p["left_out"]) if p.get("left_out") else "",
        "" if n <= PAGE_TARGET else "; OVER the 3 MB target: fewer pictures would fit (see references/handover.md)")


# ---------------------------------------------------------------------------------------------- what the run did not read
# Every report says what this run did not read, from what happened in it (0.4.1), never as boilerplate: each line is
# there only when its case occurred, with its count. The agent's own not_read list stays beside these lines.

def _in_window_ids(folder, kind):
    from common import read_json
    if kind == "niche":
        p = os.path.join(folder, "trends.json")
        doc = read_json(p) if os.path.exists(p) else {}
        return set(x["post_id"] for x in doc.get("posts") or [] if x.get("in_window"))
    p = os.path.join(folder, "analysis.json")
    if os.path.exists(p):
        doc = read_json(p)
        return set(x["post_id"] for x in doc.get("posts") or [] if x.get("in_window"))
    return None


def run_limits(kind, folder, focus=None):
    """[{what, why, evidence}] for kind account / post / niche. focus: the post run's own post id."""
    from common import load_posts, niche_creator_dirs, read_json, replies_left_out
    out = []

    def add(what, why):
        out.append({"what": what, "why": why, "evidence": "MEASURED"})
    dirs = [os.path.join(folder, d) for d in niche_creator_dirs(folder)] if kind == "niche" else [folder]
    inw = _in_window_ids(folder, kind)
    threads, carousels, slides, speech_none, videos_read, not_own, sampled = [], [], 0, 0, 0, 0, []
    covers, replies = {}, 0
    for d in dirs:
        posts = load_posts(d)
        for q in posts:
            if kind == "post" and q["post_id"] != focus:
                continue
            if kind != "post" and inw is not None and q["post_id"] not in inw:
                continue
            if q.get("type") == "thread" and len(q.get("parts") or []) < 2:
                threads.append(q["post_id"])
            if q.get("type") == "carousel":
                carousels.append(q["post_id"])
                sd = os.path.join(d, "videos", q["post_id"], "slides")
                if os.path.isdir(sd) and os.listdir(sd):
                    slides += 1
        vdir = os.path.join(d, "videos")
        for pid in (sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []):
            if kind == "post" and pid != focus:
                continue
            pp, np_ = os.path.join(vdir, pid, "probe.json"), os.path.join(vdir, pid, "notes.json")
            try:
                pr = read_json(pp) if os.path.exists(pp) else {}
                nt = read_json(np_) if os.path.exists(np_) else {}
            except ValueError:
                continue
            if pr.get("read"):
                videos_read += 1
                if (pr.get("measured") or {}).get("words_per_minute") is None:
                    speech_none += 1
            if nt.get("read") is False and "does not say whether the video is this post's own" in (nt.get("not_read_reason") or ""):
                not_own += 1
        cp = os.path.join(d, "covers", "not_read.json")
        if os.path.exists(cp):
            try:
                for why in read_json(cp).values():
                    covers[why] = covers.get(why, 0) + 1
            except (ValueError, AttributeError):
                pass
        rl = replies_left_out(d)
        replies += rl["other"] + rl["self"]
        try:
            acc = read_json(os.path.join(d, "account.json"))
        except (OSError, ValueError):
            acc = {}
        sm = acc.get("sampled") or {}
        if sm.get("read") and sm.get("of") and sm["of"] > sm["read"]:
            sampled.append("@%s: %d of its latest %d posts, %s" % (acc.get("handle"), sm["read"], sm["of"],
                                                                   "spread across the window" if "spread" in (sm.get("how") or "") else sm.get("how") or "a sample"))
        if kind == "account" and not acc.get("follower_history"):
            an = os.path.join(folder, "analysis.json")
            readings = ((read_json(an).get("followers") or {}).get("readings") or 0) if os.path.exists(an) else 0
            if readings < 2:
                add("Follower history", "no follower counts over time were read: which posts brought followers is estimated "
                                        "from signals, never counted")
    if kind == "niche":
        add("Follower history", "not read across a niche: which posts brought followers is left to an account run")
    if threads:
        add("Threads", "%d thread%s came as %s first part only (%s): %s length and %s ask are not judged" % (
            len(threads), "" if len(threads) == 1 else "s", "its" if len(threads) == 1 else "their",
            ", ".join(threads[:6]) + (" …" if len(threads) > 6 else ""), "its" if len(threads) == 1 else "their",
            "its" if len(threads) == 1 else "their"))
    if carousels and slides < len(carousels):
        add("Carousel slides", "%d of %d carousel post%s read by %s cover only (the slides were not saved)" % (
            len(carousels) - slides, len(carousels), "" if len(carousels) == 1 else "s",
            "its" if len(carousels) - slides == 1 else "their"))
    if speech_none:
        add("Speech in videos", "%d of %d watched video%s had no subtitles: words per minute not measured (a local "
                                "speech-to-text tool can add them, references/deep-read.md)" % (
                                    speech_none, videos_read, "" if videos_read == 1 else "s"))
    if not_own:
        add("Videos not watched", "%d picked post%s: the row does not say the video is the post's own (own_media), so "
                                  "none was fetched" % (not_own, "" if not_own == 1 else "s"))
    if covers:
        add("Covers", "%d not saved: %s" % (sum(covers.values()), ", ".join("%s %d" % kv for kv in sorted(covers.items()))))
    if replies:
        add("Replies", "%d repl%s left out of the numbers (replies are not posts)" % (replies, "y" if replies == 1 else "ies"))
    if sampled:
        add("Sampled", "; ".join(sampled))
    if kind == "niche":
        tp = os.path.join(folder, "trends.json")
        seeds = (read_json(tp).get("seeds") or {}) if os.path.exists(tp) else {}
        for st, words in (("not_found", "not found"), ("inactive", "no posts in the window")):
            if seeds.get(st):
                add("Seed accounts", "%s: %s" % (words, ", ".join("@%s" % x["handle"] for x in seeds[st])))
    return out


def dedupe_limits(limits, findings):
    """The run's lines, less the ones the agent already wrote under the same name in findings.json not_read."""
    told = set(str(n.get("what") or "").strip().lower() for n in (findings or {}).get("not_read") or [] if isinstance(n, dict))
    return [x for x in limits or [] if x["what"].strip().lower() not in told]
