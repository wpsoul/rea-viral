#!/usr/bin/env node
// Basic remake: play an HTML page in a headless browser frame by frame, on a clock this script controls, and save
// the frames; ffmpeg only joins them and lays the sound under them.
//
//   node render_page.mjs <page.html> [--out remake.mp4] [--fps 30] [--width 1080 --height 1920] [--duration 12]
//                        [--frames <dir>] [--keep-frames] [--browser chrome|chromium|<path>] [--check]
//
// The page's contract (references/remake.md):
//   <script type="application/json" id="rea-render">{"width":1080,"height":1920,"fps":30,"duration":12,
//      "audio":[{"src":"assets/voice.m4a","at":0,"in":0,"gain_db":0}]}</script>      (flags win over it)
//   - animate with CSS animations / transitions, the Web Animations API, or requestAnimationFrame code that reads its
//     time from the callback or performance.now(): all of them follow the script's clock. setTimeout does not.
//   - optional window.reaSeek(seconds) (may return a promise): draw the page at that time (canvas, WebGL, ...).
//   - <video data-start="2.5" data-in="0" data-sound="on" data-volume="1">: shown from 2.5 s on the page's timeline,
//     from 0 s into its file; it is sought to the exact frame for every frame; its sound is laid at 2.5 s.
// What it checks: the page loads with no console error, every video can be played by this browser, every frame was
// written. What it does not check: how the page looks. Look at the frames.
//
// Needs Node 18+, ffmpeg, and Playwright (`playwright` or `playwright-core`) with Chrome, Edge or Playwright's Chromium.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const opt = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const flag = (k) => argv.includes(k);
const die = (m, code = 2) => { console.error('render_page: ' + m); process.exit(code); };

if (!argv[0] || flag('-h') || flag('--help')) {
  console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
  process.exit(argv[0] ? 0 : 2);
}
const pagePath = path.resolve(argv[0]);
if (!fs.existsSync(pagePath)) die('no such page: ' + pagePath);

function loadPlaywright() {
  const names = [];
  if (process.env.REA_PLAYWRIGHT) names.push(process.env.REA_PLAYWRIGHT);
  for (const base of [process.cwd(), here, path.join(os.homedir(), '.cache', 'rea-viral')]) {
    for (const n of ['playwright', 'playwright-core']) names.push(path.join(base, 'node_modules', n));
  }
  names.push('playwright', 'playwright-core');
  const req = createRequire(import.meta.url);
  for (const n of names) {
    try { return req(n); } catch (e) { /* next */ }
  }
  die('Playwright is not installed. Install it once, outside any project:\n' +
      '  npm install --prefix ~/.cache/rea-viral playwright-core@1.49.1\n' +
      'and use Google Chrome or Edge (found by itself), or set REA_PLAYWRIGHT to a playwright folder.');
}

function ffmpegOk() {
  const r = spawnSync('ffmpeg', ['-version'], { encoding: 'utf8' });
  if (r.status !== 0) die('ffmpeg is not on PATH (macOS: brew install ffmpeg; Windows: winget install ffmpeg)');
}

const CLOCK = `(() => {
  let now = 0;
  const t0 = Date.now();
  performance.now = () => now;
  Date.now = () => t0 + now;
  const q = new Map(); let id = 0;
  window.requestAnimationFrame = (cb) => { id += 1; q.set(id, cb); return id; };
  window.cancelAnimationFrame = (i) => { q.delete(i); };
  const born = new WeakMap();
  function setAnims(ms) {
    for (const a of document.getAnimations()) {
      if (!born.has(a)) born.set(a, ms);
      a.pause();
      a.currentTime = Math.max(0, ms - born.get(a));
    }
  }
  function seekVideo(v, t) {
    const start = parseFloat(v.dataset.start || '0'), inn = parseFloat(v.dataset.in || '0');
    let local = inn + (t - start);
    const dur = v.duration;
    if (local < 0) local = 0;
    if (isFinite(dur) && local > dur - 0.002) local = dur - 0.002;
    // A frame starts at its own time; ask 1 ms past it so rounding to microseconds never lands on the frame before.
    local += 0.001;
    v.pause();
    if (v.__reaAt === local && v.readyState >= 2) return null;
    v.__reaAt = local;
    return new Promise((res) => {
      let done = false;
      const fin = () => { if (!done) { done = true; v.removeEventListener('seeked', fin); res(); } };
      v.addEventListener('seeked', fin);
      setTimeout(() => { if (!done) { console.warn('rea: video seek timed out at ' + local); fin(); } }, 5000);
      v.currentTime = local;
    });
  }
  window.__reaClock = {
    async seek(ms) {
      now = ms;
      setAnims(ms);
      await Promise.all(Array.from(document.querySelectorAll('video')).map((v) => seekVideo(v, ms / 1000)));
      if (typeof window.reaSeek === 'function') await window.reaSeek(ms / 1000);
      for (let k = 0; k < 2; k++) {
        const cbs = Array.from(q.values()); q.clear();
        for (const cb of cbs) { try { cb(now); } catch (e) { console.error(e && e.stack || String(e)); } }
      }
      setAnims(ms);
    },
  };
})();`;

const pw = loadPlaywright();
ffmpegOk();

async function launch() {
  const want = opt('--browser', null);
  const tries = [];
  if (want && want !== 'chrome' && want !== 'chromium' && want !== 'msedge') tries.push({ executablePath: want });
  else if (want === 'chromium') tries.push({});
  else if (want) tries.push({ channel: want });
  else tries.push({ channel: 'chrome' }, { channel: 'msedge' }, {});
  let last;
  for (const t of tries) {
    try {
      const b = await pw.chromium.launch({ headless: true, ...t });
      return { browser: b, name: t.channel || (t.executablePath ? path.basename(t.executablePath) : 'playwright chromium') };
    } catch (e) { last = e; }
  }
  die('no browser could start: ' + (last && last.message || last));
}

const out = path.resolve(opt('--out', pagePath.replace(/\.html?$/i, '') + '.mp4'));
const { browser, name: browserName } = await launch();
let failed = null;
const killer = setTimeout(() => { console.error('render_page: timed out'); process.exit(1); }, Number(opt('--timeout', '1800')) * 1000);
try {
  const page0 = await browser.newPage();
  const errors = [];
  page0.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page0.on('pageerror', (e) => errors.push(e.message));
  await page0.goto(pathToFileURL(pagePath).href, { waitUntil: 'load', timeout: 30000 });
  const cfgPage = await page0.evaluate(() => { const s = document.getElementById('rea-render'); try { return s ? JSON.parse(s.textContent) : {}; } catch (e) { return { _bad: String(e) }; } });
  await page0.close();
  if (cfgPage._bad) die('the rea-render JSON does not parse: ' + cfgPage._bad);
  const cfg = {
    width: Number(opt('--width', cfgPage.width || 1080)), height: Number(opt('--height', cfgPage.height || 1920)),
    fps: Number(opt('--fps', cfgPage.fps || 30)), duration: Number(opt('--duration', cfgPage.duration || 0)),
    audio: cfgPage.audio || [],
  };
  if (!(cfg.duration > 0)) die('no duration: set "duration" in the rea-render JSON or pass --duration');
  if (!(cfg.fps > 0 && cfg.fps <= 120)) die('fps must be 1 to 120');
  if (cfg.width % 2 || cfg.height % 2) die('width and height must be even numbers (H.264)');
  const ctx = await browser.newContext({ viewport: { width: cfg.width, height: cfg.height }, deviceScaleFactor: 1 });
  await ctx.addInitScript({ content: CLOCK });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(pathToFileURL(pagePath).href, { waitUntil: 'load', timeout: 30000 });
  await page.evaluate(() => (document.fonts ? document.fonts.ready.then(() => true) : true));
  const vids = await page.evaluate(async () => {
    const vs = Array.from(document.querySelectorAll('video'));
    await Promise.all(vs.map((v) => (v.readyState >= 1 || v.error) ? null : new Promise((res) => {
      const t = setTimeout(res, 15000); v.addEventListener('loadedmetadata', () => { clearTimeout(t); res(); }, { once: true });
      v.addEventListener('error', () => { clearTimeout(t); res(); }, { once: true }); v.preload = 'auto'; v.load(); })));
    return vs.map((v) => ({ src: v.currentSrc || v.src, error: v.error ? v.error.code : null, ready: v.readyState, duration: v.duration,
      start: parseFloat(v.dataset.start || '0'), in: parseFloat(v.dataset.in || '0'), end: v.dataset.end ? parseFloat(v.dataset.end) : null,
      sound: (v.dataset.sound || 'on') !== 'off', volume: v.dataset.volume ? parseFloat(v.dataset.volume) : 1 }));
  });
  const bad = vids.filter((v) => v.error || v.ready < 1);
  if (bad.length) die('this browser (' + browserName + ') cannot play: ' + bad.map((v) => v.src).join(', ') +
    '\nMP4 (H.264) needs Google Chrome or Edge. Or convert: ffmpeg -i in.mp4 -c:v libvpx-vp9 -b:v 0 -crf 32 -c:a libopus out.webm', 1);
  if (errors.length) die('the page has console errors:\n  ' + errors.join('\n  '), 1);
  if (flag('--check')) {
    console.log(JSON.stringify({ ok: true, browser: browserName, config: cfg, videos: vids }, null, 2));
    process.exit(0);
  }
  const framesDir = path.resolve(opt('--frames', fs.mkdtempSync(path.join(os.tmpdir(), 'rea-frames-'))));
  fs.mkdirSync(framesDir, { recursive: true });
  for (const f of fs.readdirSync(framesDir)) if (/^\d{6}\.png$/.test(f)) fs.unlinkSync(path.join(framesDir, f));
  const total = Math.round(cfg.duration * cfg.fps);
  const t0 = Date.now();
  for (let n = 0; n < total; n++) {
    const ms = (n * 1000) / cfg.fps;
    await page.evaluate((v) => window.__reaClock.seek(v), ms);
    await page.screenshot({ path: path.join(framesDir, String(n + 1).padStart(6, '0') + '.png'), type: 'png', timeout: 30000,
      clip: { x: 0, y: 0, width: cfg.width, height: cfg.height } });
    if (n % Math.max(1, Math.round(cfg.fps)) === 0) process.stdout.write(`\rframe ${n + 1}/${total}`);
  }
  process.stdout.write(`\rframe ${total}/${total} in ${((Date.now() - t0) / 1000).toFixed(1)} s\n`);
  if (errors.length) die('the page logged errors while rendering:\n  ' + errors.join('\n  '), 1);
  await ctx.close();

  // ffmpeg: join the frames, lay the sound.
  const pageDir = path.dirname(pagePath);
  const toPath = (src) => (src.startsWith('file:') ? fileURLToPath(src) : path.resolve(pageDir, src));
  const sounds = [];
  for (const a of cfg.audio) sounds.push({ file: toPath(a.src), at: Number(a.at || 0), in: Number(a.in || 0), length: a.length != null ? Number(a.length) : null, gain: Number(a.gain_db || 0) });
  for (const v of vids) {
    if (!v.sound) continue;
    const file = toPath(v.src);
    const probe = spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', file], { encoding: 'utf8' });
    if (!probe.stdout.trim()) continue;
    sounds.push({ file, at: v.start, in: v.in, length: v.end != null ? v.end - v.start : null, gain: 20 * Math.log10(Math.max(1e-4, v.volume)) });
  }
  const args = ['-y', '-hide_banner', '-loglevel', 'error', '-framerate', String(cfg.fps), '-i', path.join(framesDir, '%06d.png')];
  sounds.forEach((s) => { args.push('-ss', String(s.in)); if (s.length != null) args.push('-t', String(s.length)); args.push('-i', s.file); });
  if (sounds.length) {
    const parts = sounds.map((s, i) => `[${i + 1}:a]aresample=48000,adelay=delays=${Math.round(s.at * 1000)}:all=1,volume=${s.gain}dB[a${i}]`);
    const mix = sounds.map((_, i) => `[a${i}]`).join('') + `amix=inputs=${sounds.length}:normalize=0:dropout_transition=0[aout]`;
    args.push('-filter_complex', parts.join(';') + ';' + mix, '-map', '0:v', '-map', '[aout]', '-c:a', 'aac', '-b:a', '192k');
  } else {
    args.push('-an');
  }
  args.push('-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', String(opt('--crf', '18')), '-preset', 'medium', '-r', String(cfg.fps),
    '-t', String(total / cfg.fps), '-movflags', '+faststart', out);
  const r = spawnSync('ffmpeg', args, { encoding: 'utf8' });
  if (r.status !== 0) die('ffmpeg failed: ' + (r.stderr || '').trim().slice(-600), 1);
  if (!flag('--keep-frames') && !argv.includes('--frames')) fs.rmSync(framesDir, { recursive: true, force: true });
  console.log(JSON.stringify({ ok: true, out, frames: total, fps: cfg.fps, duration: total / cfg.fps, width: cfg.width, height: cfg.height,
    browser: browserName, sounds: sounds.map((s) => ({ file: path.basename(s.file), at: s.at })), frames_dir: flag('--keep-frames') || argv.includes('--frames') ? framesDir : null }));
} catch (e) {
  failed = e;
} finally {
  clearTimeout(killer);
  await browser.close().catch(() => {});
}
if (failed) die(String(failed && failed.stack || failed), 1);
