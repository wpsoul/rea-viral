// Open a REA Viral report.html headless from file:// and check it, the way a person would open it.
//
//   node tests/verify_report.mjs <report.html> <screenshot dir> [--radar N] [--timeline] [--writing N]
//        [--gallery N] [--hooks N] [--watchlist N] [--trends N] [--post]
//
// Checks: no console error and no page error (a failed Google Fonts request is reported, not fatal: the page must
// work offline), no dialog (captions and comments are data), only the page's own two scripts, the charts drew
// (--radar N = that many bubbles; on every format chart, at both widths, each name label inside the plot, none over
// another, a number in every bubble; --timeline = at least one dot), the How it writes section (--writing N = that many
// lifting or sinking features, and at least one first line on each side), every play has a Copy button, no monospace font
// anywhere, no sideways scroll at phone width (390 px). At 390 and 360 px (0.4.2): nothing inside the report wider than
// the window, no box that holds a table (or may scroll) scrolling sideways, every table cell with content shown, no text
// under 12 px in a table. Writes desktop.png (full page) and phone.png.
// Niche page: --gallery N format cards, each picture in it loaded; --hooks N lifting features across creators and first
// lines; --watchlist N rows; --trends N ranked rows at least. Post page: --post (the post, its words, its repeats).
// Every page: no <video>, <iframe>, <embed> or <object> (no other creator's video is embedded or re-hosted); a "What
// did not work" section (--not-working N = at least N items drawn in it); and ONE FILE: the page copied ALONE into an
// empty folder opens with no error, asks for no file but itself, and every picture on it loads (--pictures N = at
// least N pictures inside it); its size is printed and must stay under 3 MB.
// Exit 1 on any failure. Every wait has a timeout.
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
// Playwright: REA_PLAYWRIGHT (a playwright folder), else tests/node_modules (npm install --prefix tests), else the
// skill's own place for it (~/.cache/rea-viral), else wherever Node finds it.
function loadPlaywright() {
  const tries = [process.env.REA_PLAYWRIGHT, path.join(here, 'node_modules', 'playwright'),
    path.join(os.homedir(), '.cache', 'rea-viral', 'node_modules', 'playwright-core'), 'playwright', 'playwright-core'].filter(Boolean);
  for (const t of tries) { try { return require(t); } catch (e) { /* next */ } }
  console.error('FAIL no Playwright: run `npm install --prefix tests` and `npx --prefix tests playwright install chromium`, or set REA_PLAYWRIGHT');
  process.exit(1);
}
const { chromium } = loadPlaywright();

const args = process.argv.slice(2);
const report = args[0];
const outDir = args[1];
if (!report || !outDir) { console.error('usage: verify_report.mjs <report.html> <screenshot dir> [--radar N] [--timeline]'); process.exit(2); }
const wantRadar = args.includes('--radar') ? Number(args[args.indexOf('--radar') + 1]) : null;
const wantTimeline = args.includes('--timeline');
const wantWriting = args.includes('--writing') ? Number(args[args.indexOf('--writing') + 1]) : null;
const numArg = (k) => (args.includes(k) ? Number(args[args.indexOf(k) + 1]) : null);
const wantGallery = numArg('--gallery');
const wantHooks = numArg('--hooks');
const wantWatch = numArg('--watchlist');
const wantTrends = numArg('--trends');
const wantPost = args.includes('--post');
const wantNotWorking = numArg('--not-working');
const wantPictures = numArg('--pictures');
fs.mkdirSync(outDir, { recursive: true });

const fails = [];
const notes = [];
const fail = (m) => { fails.push(m); console.log('FAIL ' + m); };
const pass = (m) => console.log('ok   ' + m);

const browser = await chromium.launch({ headless: true });
const timer = setTimeout(() => { console.log('FAIL timed out after 60 s'); process.exit(1); }, 60000);
try {
  for (const [name, viewport] of [['desktop', { width: 1280, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
    const ctx = await browser.newContext({ viewport, colorScheme: 'dark' });
    const page = await ctx.newPage();
    const errors = [];
    page.on('console', (m) => {
      if (m.type() !== 'error') return;
      const loc = (m.location() || {}).url || '';
      if (/fonts\.(googleapis|gstatic)\.com/.test(loc) || /fonts\.(googleapis|gstatic)\.com/.test(m.text())) notes.push('font request failed: ' + m.text());
      else errors.push(m.text() + (loc ? ' @ ' + loc : ''));
    });
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('requestfailed', (r) => {
      const u = r.url();
      if (/fonts\.(googleapis|gstatic)\.com/.test(u)) notes.push('font request failed: ' + u);
      else if (!u.startsWith('file:')) errors.push('request failed: ' + u);
    });
    let dialog = null;
    page.on('dialog', async (d) => { dialog = d.message(); await d.dismiss(); });
    await page.goto(pathToFileURL(path.resolve(report)).href, { waitUntil: 'load', timeout: 20000 });
    await page.waitForFunction(() => window.__reaReport && window.__reaReport.ready === true, null, { timeout: 10000 });
    await page.evaluate(() => document.fonts ? document.fonts.ready.then(() => true) : true);
    const info = await page.evaluate(() => {
      const fams = new Set();
      document.querySelectorAll('body, body *').forEach((n) => fams.add(getComputedStyle(n).fontFamily));
      return {
        drawn: window.__reaReport.drawn,
        scripts: document.querySelectorAll('script').length,
        plays: document.querySelectorAll('#plays .play').length,
        copyButtons: document.querySelectorAll('#plays .play button').length,
        families: Array.from(fams),
        scrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        theme: document.documentElement.getAttribute('data-theme'),
        bg: getComputedStyle(document.body).backgroundColor,
        radarSvg: !!document.querySelector('svg[data-chart="radar"]'),
        timelineSvg: !!document.querySelector('svg[data-chart="timeline"]'),
        writingSection: !!document.querySelector('section#writing'),
        writingLabels: Array.from(document.querySelectorAll('section#writing .ev')).length,
        sections: Array.from(document.querySelectorAll('section h2')).map((h) => h.textContent),
        kind: window.__reaReport.kind || 'account',
        embeds: document.querySelectorAll('video, iframe, embed, object').length,
        galleryCards: document.querySelectorAll('#gallery .fcard').length,
        galleryImgs: Array.from(document.querySelectorAll('#gallery img')).map((i) => ({ src: i.getAttribute('src'), ok: i.complete && i.naturalWidth > 0 })),
        hooksSection: !!document.querySelector('section#hooks'),
        notWorking: !!document.querySelector('section#not-working'),
        // the chart's labels (0.4.1): each inside the plot, none over another, a number in every bubble
        chart: Array.from(document.querySelectorAll('svg[data-chart="radar"]')).map((svg) => {
          const plot = svg.querySelector('rect.plot');
          const p = plot ? plot.getBBox() : null;
          const labels = Array.from(svg.querySelectorAll('text.lbl')).map((t) => { const b = t.getBBox(); return { x0: b.x, y0: b.y, x1: b.x + b.width, y1: b.y + b.height, text: t.textContent }; });
          const out = p ? labels.filter((b) => b.x0 < p.x - 0.5 || b.y0 < p.y - 0.5 || b.x1 > p.x + p.width + 0.5 || b.y1 > p.y + p.height + 0.5).map((b) => b.text) : ['no plot'];
          const over = [];
          for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
            const a = labels[i]; const b = labels[j];
            if (a.x0 < b.x1 - 0.5 && b.x0 < a.x1 - 0.5 && a.y0 < b.y1 - 0.5 && b.y0 < a.y1 - 0.5) over.push(a.text + ' / ' + b.text);
          }
          return { bubbles: svg.querySelectorAll('g[data-format]').length, numbers: svg.querySelectorAll('g[data-format] text.bnum').length, labels: labels.length, out, over };
        }),
        clipped: Array.from(document.querySelectorAll('#gallery .fcard, .panel, .stat')).filter((n) => n.getBoundingClientRect().right > window.innerWidth + 1).length,
      };
    });
    const tag = `[${name}] `;
    if (errors.length) fail(tag + 'console or page errors: ' + errors.join(' | ')); else pass(tag + 'no console or page errors');
    if (dialog) fail(tag + 'a dialog opened: ' + dialog); else pass(tag + 'no dialog');
    if (info.scripts !== 2) fail(tag + `expected the page's 2 scripts, found ${info.scripts}`); else pass(tag + 'only the page\'s own scripts');
    if (wantRadar != null) {
      if (!info.radarSvg || info.drawn.radar !== wantRadar) fail(tag + `radar drew ${info.drawn.radar} bubbles, expected ${wantRadar}`);
      else pass(tag + `radar drew ${wantRadar} bubbles`);
    }
    if (wantTimeline) {
      if (!info.timelineSvg || !(info.drawn.timeline > 0)) fail(tag + 'timeline drew no dots'); else pass(tag + `timeline drew ${info.drawn.timeline} dots`);
    }
    if (wantWriting != null) {
      if (!info.writingSection) fail(tag + 'no How it writes section');
      else if (info.drawn.writing !== wantWriting) fail(tag + `How it writes drew ${info.drawn.writing} lifting or sinking features, expected ${wantWriting}`);
      else if (!(info.drawn.first_lines >= 2)) fail(tag + 'How it writes drew no first lines');
      else if (!(info.writingLabels > 0)) fail(tag + 'How it writes shows no evidence labels');
      else pass(tag + `How it writes: ${wantWriting} features, ${info.drawn.first_lines} first lines, every line labelled`);
    }
    if (info.embeds) fail(tag + `${info.embeds} embedded video or frame element(s): no creator's video may be embedded`); else pass(tag + 'no embedded video');
    if (info.clipped) fail(tag + `${info.clipped} panels or cards run past the window's right edge`); else pass(tag + 'nothing runs past the right edge');
    if (wantGallery != null) {
      const bad = info.galleryImgs.filter((i) => !i.ok);
      if (info.drawn.gallery !== wantGallery || info.galleryCards !== wantGallery) fail(tag + `gallery drew ${info.drawn.gallery} format cards, expected ${wantGallery}`);
      else if (!info.galleryImgs.length) fail(tag + 'the gallery shows no pictures');
      else if (bad.length) fail(tag + `${bad.length} gallery pictures did not load: ` + bad.slice(0, 3).map((i) => i.src).join(', '));
      else pass(tag + `gallery: ${wantGallery} format cards, ${info.galleryImgs.length} pictures, all loaded`);
    }
    if (wantHooks != null) {
      if (!info.hooksSection) fail(tag + 'no Hooks section');
      else if (info.drawn.writing !== wantHooks) fail(tag + `Hooks drew ${info.drawn.writing} lifting or sinking features, expected ${wantHooks}`);
      else if (!(info.drawn.first_lines >= 2)) fail(tag + 'Hooks drew no first lines');
      else pass(tag + `Hooks: ${wantHooks} features across creators, ${info.drawn.first_lines} first lines`);
    }
    if (wantWatch != null) {
      if (info.drawn.watchlist !== wantWatch) fail(tag + `watchlist drew ${info.drawn.watchlist} rows, expected ${wantWatch}`); else pass(tag + `watchlist: ${wantWatch} rows`);
    }
    if (wantTrends != null) {
      if (!(info.drawn.trends >= wantTrends)) fail(tag + `trends drew ${info.drawn.trends} rows, expected at least ${wantTrends}`); else pass(tag + `trends: ${info.drawn.trends} rows`);
    }
    if (wantPost) {
      if (info.kind !== 'post' || info.drawn.post !== 1) fail(tag + 'not a post page, or the post was not drawn');
      else if (!(info.drawn.words > 0)) fail(tag + 'the post page drew none of its words');
      else pass(tag + `post page: the post, ${info.drawn.words} lines of its words, ${info.drawn.repeats} repeats`);
    }
    for (const c of info.chart) {
      if (c.out.length) fail(tag + `chart labels outside the plot: ${c.out.join(' | ')}`);
      else if (c.over.length) fail(tag + `chart labels over each other: ${c.over.join(' | ')}`);
      else if (c.numbers !== c.bubbles) fail(tag + `${c.bubbles} bubbles but ${c.numbers} numbers`);
      else pass(tag + `chart: ${c.bubbles} bubbles numbered, ${c.labels} names placed inside the plot, none overlapping`);
    }
    if (!info.notWorking) fail(tag + 'no "What did not work" section');
    else if (wantNotWorking != null && !(info.drawn.not_working >= wantNotWorking)) fail(tag + `What did not work drew ${info.drawn.not_working} items, expected at least ${wantNotWorking}`);
    else pass(tag + `What did not work: ${info.drawn.not_working} items`);
    if (info.plays !== info.copyButtons) fail(tag + `${info.plays} plays but ${info.copyButtons} Copy buttons`); else pass(tag + `${info.plays} plays, each with a Copy button`);
    const mono = info.families.filter((f) => /mono|courier|consolas|menlo/i.test(f));
    if (mono.length) fail(tag + 'monospace font in use: ' + mono.join(', ')); else pass(tag + 'no monospace font');
    if (info.theme !== 'dark' || !/rgb\(12, 14, 17\)/.test(info.bg)) fail(tag + `not dark by default (${info.theme}, ${info.bg})`); else pass(tag + 'dark by default');
    if (info.scrollW > info.innerW + 1) fail(tag + `sideways scroll: ${info.scrollW}px wide in a ${info.innerW}px window`); else pass(tag + 'no sideways scroll');
    const shot = path.join(outDir, name + '.png');
    await page.screenshot({ path: shot, fullPage: true, timeout: 20000 });
    console.log('     sections: ' + info.sections.join(' · '));
    console.log('     screenshot: ' + shot);
    if (name === 'desktop') {
      // The theme button switches to light and back.
      await page.click('#theme', { timeout: 5000 });
      const t = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
      if (t !== 'light') fail(tag + 'the Light button did not switch the theme'); else pass(tag + 'Light button works');
      await page.screenshot({ path: path.join(outDir, 'desktop-light.png'), fullPage: false, timeout: 20000 });
    }
    await ctx.close();
  }
  // PHONES (0.4.2): at 390 and 360 px nothing inside the report is wider than the window, no box that holds a table (nor
  // any box that may scroll) scrolls sideways, every table cell with something in it is shown, and no text in a table
  // is under 12 px.
  for (const w of [390, 360]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: 'dark' });
    const page = await ctx.newPage();
    await page.goto(pathToFileURL(path.resolve(report)).href, { waitUntil: 'load', timeout: 20000 });
    await page.waitForFunction(() => window.__reaReport && window.__reaReport.ready === true, null, { timeout: 10000 });
    await page.evaluate(() => document.fonts ? document.fonts.ready.then(() => true) : true);
    const r = await page.evaluate(() => {
      const W = window.innerWidth, wide = [], scroll = [], hidden = [], small = [];
      const name = (n) => { const sec = n.closest('section'); return (sec ? '[' + sec.id + '] ' : '') + n.tagName.toLowerCase() + (n.className && typeof n.className === 'string' ? '.' + n.className.trim().split(/\s+/).join('.') : ''); };
      document.querySelectorAll('#app *').forEach((n) => {
        const b = n.getBoundingClientRect();
        if (b.width > 0 && (b.right > W + 1 || b.left < -1)) wide.push(name(n) + ' ' + Math.round(b.left) + '..' + Math.round(b.right));
        const o = getComputedStyle(n).overflowX;
        if ((o === 'auto' || o === 'scroll') && n.clientWidth && n.scrollWidth > n.clientWidth + 1) scroll.push(name(n) + ' ' + n.scrollWidth + '>' + n.clientWidth);
      });
      document.querySelectorAll('#app table').forEach((t) => {
        for (let c = t.parentElement; c && c.id !== 'app'; c = c.parentElement) {
          if (c.clientWidth && c.scrollWidth > c.clientWidth + 1) { scroll.push(name(c) + ' (holds a table) ' + c.scrollWidth + '>' + c.clientWidth); break; }
        }
        t.querySelectorAll('td').forEach((td) => {
          if (td.textContent.trim() && !td.getClientRects().length && !td.closest('details:not([open])')) hidden.push(name(td) + ' "' + td.textContent.trim().slice(0, 30) + '"');
        });
        t.querySelectorAll('td, td *').forEach((n) => {
          if (!n.getClientRects().length) return;
          const own = Array.prototype.some.call(n.childNodes, (x) => x.nodeType === 3 && x.textContent.trim());
          const fs = parseFloat(getComputedStyle(n).fontSize);
          if (own && fs < 12) small.push(name(n) + ' ' + fs + 'px "' + n.textContent.trim().slice(0, 20) + '"');
          const lab = n.matches('td[data-label]') ? parseFloat(getComputedStyle(n, '::before').fontSize) : 99;
          if (lab < 12) small.push(name(n) + '::before ' + lab + 'px');
        });
      });
      const u = (a) => Array.from(new Set(a));
      return { wide: u(wide), scroll: u(scroll), hidden: u(hidden), small: u(small), tables: document.querySelectorAll('#app table').length,
               stacked: document.querySelectorAll('#app table.stk').length };
    });
    const tag = `[${w} px] `;
    if (r.wide.length) fail(tag + `${r.wide.length} elements wider than the window: ` + r.wide.slice(0, 5).join(' | '));
    else pass(tag + 'nothing wider than the window');
    if (r.scroll.length) fail(tag + 'boxes that scroll sideways: ' + r.scroll.slice(0, 5).join(' | '));
    else pass(tag + `no box scrolls sideways (${r.tables} tables, ${r.stacked} of them as stacked rows)`);
    if (r.hidden.length) fail(tag + `${r.hidden.length} table cells with content not shown: ` + r.hidden.slice(0, 5).join(' | '));
    else pass(tag + 'every table cell with content is shown');
    if (r.small.length) fail(tag + 'text under 12 px in a table: ' + r.small.slice(0, 5).join(' | '));
    else pass(tag + 'no text under 12 px in a table');
    await ctx.close();
  }
  // ONE FILE: the page alone in an empty folder, the way a planner keeps it and a person opens a download.
  const size = fs.statSync(report).size;
  console.log(`     size: ${(size / 1e6).toFixed(2)} MB (${size} bytes)`);
  if (size > 3e6) fail(`the page is ${(size / 1e6).toFixed(2)} MB: over the 3 MB target`); else pass('under 3 MB');
  const alone = path.join(outDir, 'alone');
  fs.rmSync(alone, { recursive: true, force: true });
  fs.mkdirSync(alone, { recursive: true });
  const lone = path.join(alone, 'report.html');
  fs.copyFileSync(report, lone);
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'dark' });
    const page = await ctx.newPage();
    const errors = [];
    const files = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error' && !/fonts\.(googleapis|gstatic)\.com/.test(m.text() + ((m.location() || {}).url || ''))) errors.push(m.text()); });
    page.on('request', (r) => { const u = r.url(); if (u.startsWith('file:') && u !== pathToFileURL(lone).href) files.push(u); });
    await page.goto(pathToFileURL(lone).href, { waitUntil: 'load', timeout: 20000 });
    await page.waitForFunction(() => window.__reaReport && window.__reaReport.ready === true, null, { timeout: 10000 });
    // Draw every picture: scroll the whole page so lazy layout cannot hide one, then wait for each to settle.
    const pics = await page.evaluate(async () => {
      const imgs = Array.from(document.querySelectorAll('img'));
      await Promise.all(imgs.map((i) => (i.complete ? null : new Promise((ok) => { i.onload = i.onerror = ok; setTimeout(ok, 4000); }))));
      return imgs.map((i) => ({ src: (i.getAttribute('src') || '').slice(0, 40), ok: i.complete && i.naturalWidth > 0, inside: /^data:image\//.test(i.getAttribute('src') || '') }));
    });
    const bad = pics.filter((p) => !p.ok);
    const outside = pics.filter((p) => !p.inside);
    if (errors.length) fail('[alone] errors: ' + errors.join(' | ')); else pass('[alone] opens alone with no error');
    if (files.length) fail(`[alone] asks for ${files.length} other file(s): ` + files.slice(0, 3).join(', ')); else pass('[alone] asks for no other file');
    if (bad.length) fail(`[alone] ${bad.length} of ${pics.length} pictures did not load: ` + bad.slice(0, 3).map((p) => p.src).join(', '));
    else if (outside.length) fail(`[alone] ${outside.length} pictures are not inside the page`);
    else pass(`[alone] ${pics.length} pictures, all inside the page, all loaded`);
    if (wantPictures != null && !(pics.length >= wantPictures)) fail(`[alone] ${pics.length} pictures, expected at least ${wantPictures}`);
    await page.screenshot({ path: path.join(outDir, 'alone.png'), fullPage: false, timeout: 20000 });
    await ctx.close();
  }
} catch (e) {
  fail('error: ' + (e && e.stack || e));
} finally {
  clearTimeout(timer);
  await browser.close();
}
for (const n of [...new Set(notes)]) console.log('note ' + n);
console.log(fails.length ? `NOT OK: ${fails.length} failure(s)` : 'OK');
process.exit(fails.length ? 1 : 0);
