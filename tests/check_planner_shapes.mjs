// The planner files a REA Viral run writes, checked by the GreenLight Pulse connector's OWN model (not a copy of its
// rules), so a shape the planner would refuse fails here first.
//
//   PULSE_MODEL=<path to the connector's model.mjs> node tests/check_planner_shapes.mjs <run folder> [...]
//
// The connector's source is not part of this repository and nothing of it is copied here: without PULSE_MODEL (or
// with a path that is not there) the check says it is skipped and exits 0. With it: every row of radar_rows.json as
// a `formats` record (with the stamp and report id the planner adds), and report_record.json's `report` (its brief
// included) as a `reports` record, through the model's checkRecord(). Always (with or without the model): brief.json
// equals report.brief; beats carry a text time; the summary and the brief's answer are not empty; the light page and
// the cover named in the record exist with the sizes written. Exit 1 on any problem.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const model = process.env.PULSE_MODEL || '';
let checkRecord = null;
if (model && fs.existsSync(model)) ({ checkRecord } = await import(pathToFileURL(path.resolve(model)).href));
else console.log('skipped: the Pulse connector\'s model is not here (set PULSE_MODEL to its model.mjs to check the rows '
  + 'and records against it); the files are still checked against each other');

const folders = process.argv.slice(2);
if (!folders.length) { console.error('usage: check_planner_shapes.mjs <run folder> [...]'); process.exit(2); }
const now = new Date().toISOString();
let bad = 0;
const read = (d, f) => JSON.parse(fs.readFileSync(path.join(d, f), 'utf8'));
for (const d of folders) {
  const errs = [];
  const rows = read(d, 'radar_rows.json').rows || [];
  let beats = 0;
  for (const row of rows) {
    const rec = { ...row, saved_at: now, report: 'p_000000000000' };
    if (checkRecord) for (const e of checkRecord('formats', rec, rec.key)) errs.push('row ' + e);
    for (const b of (row.format && row.format.beats) || []) { beats++; if (typeof b.t !== 'string') errs.push(`row ${row.key}: beat t ${JSON.stringify(b.t)} is not text`); }
  }
  const rr = read(d, 'report_record.json');
  const rep = { ...rr.report, id: 'p_000000000000', created_at: now };
  if (checkRecord) for (const e of checkRecord('reports', rep, rep.id)) errs.push('report ' + e);
  const brief = read(d, 'brief.json');
  const { schema, ...b } = brief;
  if (JSON.stringify(b) !== JSON.stringify(rr.report.brief)) errs.push('brief.json differs from report_record.json report.brief');
  for (const [k, f] of [['file', rr.file], ['light', rr.light], ['cover', rr.cover]]) {
    if (!f) continue;
    const p = path.join(d, f.path);
    if (!fs.existsSync(p)) errs.push(`${k}: ${f.path} is named but not there`);
    else if (fs.statSync(p).size !== f.size) errs.push(`${k}: ${f.path} is ${fs.statSync(p).size} bytes, the record says ${f.size}`);
  }
  if (!rr.light) errs.push('light: report-light.html is not named in the record');
  if (!rr.report.summary || !brief.answer) errs.push('the summary or the brief\'s answer is empty');
  if (errs.length) { bad++; console.log(`FAIL ${d}`); errs.slice(0, 20).forEach((e) => console.log('     ' + e)); }
  else console.log(`ok   ${path.basename(d)}: ${rows.length} row(s), ${beats} beat(s), report ${rr.report.kind}${rr.cover ? ', cover ' + rr.cover.path : ''}, light ${rr.light.size} bytes`);
}
console.log(bad ? `NOT OK: ${bad} folder(s)` : 'OK');
process.exit(bad ? 1 : 0);
