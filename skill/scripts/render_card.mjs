#!/usr/bin/env node
// The post card to PNG: open each card page (made by post_card.py) in a headless browser at 1080 x 1350 from file://,
// wait for its fonts and its fit step, read what the card says about itself, and save the picture.
//
//   node render_card.mjs <card.html> <out.png> [<card2.html> <out2.png> ...] [--scale 1] [--browser chrome|chromium|<path>]
//   node render_card.mjs --gallery <out dir> [--skins cobalt,night] [--layouts t1,r2] [--content sample|long|few]
//                                                       every sample card of the template (the design lab's data)
//
// Prints one JSON line per card: {"png", "ok", "zoom", "problems", "errors", "fonts"}. A card is not ok when its fit step
// left text past its box or content on the foot, or when the page logged an error. Exit 0 = every card ok, 1 = a card
// is not ok (its PNG is still saved, to look at), 2 = it cannot run (no Playwright, no browser).
// Needs Node 18+ and Playwright (`playwright` or `playwright-core`) with Chrome, Edge or Playwright's Chromium.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const opt = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const die = (m, code = 2) => { console.error('render_card: ' + m); process.exit(code); };
const VALUED = new Set(['--scale', '--browser', '--gallery', '--skins', '--layouts', '--content', '--timeout']);
const pos = argv.filter((a, i) => !a.startsWith('--') && !VALUED.has(argv[i - 1]));

if (!argv.length || argv.includes('-h') || argv.includes('--help')) {
  console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
  process.exit(argv.length ? 0 : 2);
}

function loadPlaywright() {
  const names = [];
  if (process.env.REA_PLAYWRIGHT) names.push(process.env.REA_PLAYWRIGHT);
  for (const base of [process.cwd(), here, path.join(os.homedir(), '.cache', 'rea-viral')]) {
    for (const n of ['playwright', 'playwright-core']) names.push(path.join(base, 'node_modules', n));
  }
  names.push('playwright', 'playwright-core');
  const req = createRequire(import.meta.url);
  for (const n of names) { try { return req(n); } catch (e) { /* next */ } }
  die('Playwright is not installed. Install it once, outside any project:\n' +
      '  npm install --prefix ~/.cache/rea-viral playwright-core@1.49.1\n' +
      'and use Google Chrome or Edge (found by itself), or set REA_PLAYWRIGHT to a playwright folder.');
}

async function launch(pw) {
  const want = opt('--browser', null), tries = [];
  if (want && !['chrome', 'chromium', 'msedge'].includes(want)) tries.push({ executablePath: want });
  else if (want === 'chromium') tries.push({});
  else if (want) tries.push({ channel: want });
  else tries.push({ channel: 'chrome' }, { channel: 'msedge' }, {});
  let last;
  for (const t of tries) {
    try { return await pw.chromium.launch({ headless: true, ...t }); } catch (e) { last = e; }
  }
  die('no browser could start: ' + (last && last.message || last));
}

const jobs = [];
const gallery = opt('--gallery', null);
if (gallery) {
  const tpl = path.join(here, '..', 'templates', 'post', 'card.html');
  const skins = opt('--skins', 'cobalt,redword,night,holo,paper,warm,glass').split(',');
  const want = opt('--layouts', 't1,t2,t3,t4,t5,r1,r2,r3,r4,r5').split(',');
  const content = opt('--content', 'sample');
  fs.mkdirSync(gallery, { recursive: true });
  for (const skin of skins) for (const id of want) {
    const kind = id[0] === 'r' ? 'report' : 'teardown';
    jobs.push({ url: pathToFileURL(tpl).href + `#${kind}&skin=${skin}&c=${content}&l=${id}`, png: path.join(gallery, `${skin}-${kind}-${id}${content === 'sample' ? '' : '-' + content}.png`), ready: kind, gallery: true });
  }
} else {
  if (!pos.length || pos.length % 2) die('give pairs: <card.html> <out.png>');
  for (let i = 0; i < pos.length; i += 2) {
    const html = path.resolve(pos[i]);
    if (!fs.existsSync(html)) die('no such page: ' + html);
    jobs.push({ url: pathToFileURL(html).href, png: path.resolve(pos[i + 1]), html });
  }
}

const pw = loadPlaywright();
const browser = await launch(pw);
const scale = Number(opt('--scale', '1'));
const killer = setTimeout(() => { console.error('render_card: timed out'); process.exit(2); }, Number(opt('--timeout', '300')) * 1000);
let bad = 0;
try {
  const ctx = await browser.newContext({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: scale });
  for (const j of jobs) {
    const page = await ctx.newPage(), errors = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', (e) => errors.push(String(e && e.message || e)));
    page.on('requestfailed', (r) => errors.push('could not load ' + r.url().slice(0, 120)));
    await page.goto(j.url, { waitUntil: 'load', timeout: 30000 });
    let r;
    try {
      if (j.gallery) {
        await page.waitForSelector(`body[data-ready="${j.ready}"]`, { state: 'attached', timeout: 20000 });
        r = await page.evaluate(() => {
          const c = document.querySelector('.box > .L'), cap = document.querySelector('figcaption');
          document.body.innerHTML = ''; document.body.className = 'one'; c.style.transform = 'none'; document.body.appendChild(c);
          return { ok: !cap.classList.contains('bad'), problems: cap.classList.contains('bad') ? [cap.textContent] : [], layout: c.dataset.l, skin: c.dataset.skin };
        });
      } else {
        await page.waitForSelector('body[data-ready]', { state: 'attached', timeout: 20000 });
        r = await page.evaluate(() => window.__reaCard);
      }
      await page.evaluate(() => Promise.all(Array.from(document.images).map((i) => (i.complete ? 0 : new Promise((res) => { i.onload = i.onerror = res; })))));
      // let the browser paint every tile of the final layout before the picture is taken
      await page.evaluate(() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(res, 120)))));
    } catch (e) {
      r = { ok: false, problems: ['the card never said it was ready: ' + String(e.message || e).split('\n')[0]] };
    }
    fs.mkdirSync(path.dirname(j.png), { recursive: true });
    await page.screenshot({ path: j.png, clip: { x: 0, y: 0, width: 1080, height: 1350 } });
    const out = { png: j.png, layout: r.layout, skin: r.skin, ok: !!r.ok && !errors.length, zoom: r.zoom, gap: r.gap,
      shrunk: r.shrunk || [], problems: r.problems || [], errors, fonts: r.fonts };
    if (!out.ok) bad++;
    console.log(JSON.stringify(out));
    await page.close();
  }
} finally {
  clearTimeout(killer);
  await browser.close().catch(() => {});
}
process.exit(bad ? 1 : 0);
