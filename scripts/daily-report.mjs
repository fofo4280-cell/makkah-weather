// Daily model rain report for Makkah Region. Run by GitHub Actions every day near 12:00
// Riyadh time (see .github/workflows/daily-report.yml). Writes reports/latest.json,
// reports/<date>.json and reports/index.json. Uses only free, key-free Open-Meteo APIs.
//
// What it does: for ECMWF, GFS and ICON, sums forecast rain from 12:00 to 24:00 Riyadh
// time on a 0.2° grid inside an approximate outline of Makkah Province, then ranks the
// places where the models agree most. It reports model opinion, not observations.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MODELS, MODEL_KEYS } from '../js/config.js';
import { MAKKAH_REGION, inPolygon, describe, distKm } from '../js/geo.js';

const FORECAST = 'https://api.open-meteo.com/v1/forecast';
const ENSEMBLE = 'https://ensemble-api.open-meteo.com/v1/ensemble';
const META = (p) => `https://api.open-meteo.com/data/${p}/static/meta.json`;
const STEP = 0.2;
const RAIN_MM = 1;        // "the model shows rain here" in the 12-hour window
const SEP_KM = 45;        // minimum distance between listed places
const CHUNK = 100;        // locations per request
const IDS = { ecmwf: ['ecmwf_ifs', 'ecmwf_ifs025'], gfs: MODELS.gfs.sources[0].ids, icon: MODELS.icon.sources[0].ids };
const H = 3600 * 1000;

const median = (a) => { const s = [...a].sort((x, y) => x - y); const n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
const r1 = (x) => (x == null ? null : Math.round(x * 10) / 10);

// Open-Meteo's free tier allows 600 weighted calls per minute; each location counts as
// one call (more with >10 variables). Stay well under it and wait out any 429.
const PER_MIN = 400;
const spent = [];
let sleepFn = (ms) => new Promise((r) => setTimeout(r, ms));
async function budget(w) {
  for (;;) {
    const now = Date.now(); while (spent.length && now - spent[0][0] > 61000) spent.shift();
    const used = spent.reduce((a, b) => a + b[1], 0);
    if (!spent.length || used + w <= PER_MIN) { spent.push([now, w]); return; }
    await sleepFn(61000 - (now - spent[0][0]) + 250);
  }
}
const log = [];
async function getJSON(fetchFn, url, tries = 3, weight = 1) {
  let last;
  for (let k = 0; k < tries; k++) {
    await budget(weight);
    try {
      const res = await fetchFn(url, { headers: { 'user-agent': 'makkah-weather-daily-report (github actions)' } });
      const body = await res.json().catch(() => ({}));
      if (res.ok) return body;
      last = Object.assign(new Error(body.reason || `HTTP ${res.status}`), { status: res.status });
      log.push(`${res.status} ${String(body.reason || '').slice(0, 160)} ← ${url.split('?')[0]}`);
      if (res.status === 400) throw last;
    } catch (e) { last = e; if (e.status === 400) throw e; if (!e.status) log.push(`network: ${e.message}`); }
    await sleepFn(last && last.status === 429 ? 65000 : 3000 * (k + 1));
  }
  throw last;
}

function riyadhDay(now) {
  const d = new Date(now + 3 * H); // Saudi Arabia has no daylight saving: UTC+3 all year
  const y = d.getUTCFullYear(), m = d.getUTCMonth(), day = d.getUTCDate();
  const date = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  return { date, start: Date.UTC(y, m, day, 12) - 3 * H, end: Date.UTC(y, m, day, 24) - 3 * H };
}

function buildGrid() {
  const lats = [], lons = [];
  for (let la = 18.4; la <= 23.8 + 1e-9; la += STEP) lats.push(+la.toFixed(2));
  for (let lo = 38.6; lo <= 43.4 + 1e-9; lo += STEP) lons.push(+lo.toFixed(2));
  const inside = lats.map((la) => lons.map((lo) => inPolygon(la, lo)));
  // Fetch a one-cell ring outside the outline as well, so neighbourhoods at the edge are complete.
  const want = lats.map((_, j) => lons.map((__, i) => { for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) if (inside[j + dj] && inside[j + dj][i + di]) return true; return false; }));
  const pts = []; lats.forEach((la, j) => lons.forEach((lo, i) => { if (want[j][i]) pts.push({ j, i, lat: la, lon: lo }); }));
  return { lats, lons, inside, pts };
}

async function fetchModel(fetchFn, key, grid, win) {
  let lastErr;
  for (const id of IDS[key]) {
    try {
      const out = { id, P: grid.lats.map(() => grid.lons.map(() => null)), C: grid.lats.map(() => grid.lons.map(() => null)), peak: grid.lats.map(() => grid.lons.map(() => null)), elev: grid.lats.map(() => grid.lons.map(() => null)) };
      for (let k = 0; k < grid.pts.length; k += CHUNK) {
        const chunk = grid.pts.slice(k, k + CHUNK);
        const q = new URLSearchParams({ latitude: chunk.map((p) => p.lat).join(','), longitude: chunk.map((p) => p.lon).join(','), hourly: 'precipitation,cape', models: id, forecast_days: '2', timezone: 'GMT', timeformat: 'unixtime' });
        const body = await getJSON(fetchFn, `${FORECAST}?${q}`, 4, chunk.length);
        const arr = Array.isArray(body) ? body : [body];
        chunk.forEach((p, n) => {
          const b = arr[n]; if (!b || !b.hourly) return;
          const t = b.hourly.time || [], pr = b.hourly.precipitation || [], cp = b.hourly.cape || [];
          let s = 0, have = 0, cmax = null, pk = null, pv = 0;
          for (let h = 0; h < t.length; h++) {
            const ms = t[h] * 1000; if (ms < win.start || ms >= win.end) continue;
            if (pr[h] != null) { s += pr[h]; have++; if (pr[h] > pv) { pv = pr[h]; pk = ms; } }
            if (cp[h] != null) cmax = cmax == null ? cp[h] : Math.max(cmax, cp[h]);
          }
          out.P[p.j][p.i] = have ? s : null; out.C[p.j][p.i] = cmax; out.peak[p.j][p.i] = pv >= 0.1 ? pk : null; out.elev[p.j][p.i] = b.elevation ?? null;
        });
      }
      if (!out.P.some((r) => r.some((v) => v != null))) throw new Error('لا قيم مطر في الاستجابة');
      return out;
    } catch (e) { lastErr = e; if (e.status && e.status !== 400) break; }
  }
  throw lastErr || new Error('تعذر الجلب');
}

async function fetchInit(fetchFn, key) {
  for (const p of MODELS[key].meta) {
    try { const d = await getJSON(fetchFn, META(p), 1); if (d && d.last_run_initialisation_time) return d.last_run_initialisation_time * 1000; } catch { /* next */ }
  }
  return null;
}

async function fetchEnsembleProbs(fetchFn, key, pts, win) {
  for (const id of MODELS[key].ens) {
    try {
      const q = new URLSearchParams({ latitude: pts.map((p) => p.lat).join(','), longitude: pts.map((p) => p.lon).join(','), hourly: 'precipitation', models: id, forecast_days: '2', timezone: 'GMT', timeformat: 'unixtime' });
      const body = await getJSON(fetchFn, `${ENSEMBLE}?${q}`, 2, pts.length * 10);
      const arr = Array.isArray(body) ? body : [body];
      return pts.map((_, n) => {
        const h = (arr[n] && arr[n].hourly) || {}; const t = h.time || [];
        const members = Object.keys(h).filter((k) => k === 'precipitation' || k.startsWith('precipitation_member')).map((k) => h[k]).filter((a) => Array.isArray(a) && a.some((x) => x != null));
        if (!members.length) return null;
        const sums = members.map((a) => { let s = 0; for (let k = 0; k < t.length; k++) { const ms = t[k] * 1000; if (ms >= win.start && ms < win.end && a[k] != null) s += a[k]; } return s; });
        return { id, members: sums.length, p1: sums.filter((s) => s >= 1).length / sums.length, p5: sums.filter((s) => s >= 5).length / sums.length };
      });
    } catch { /* try next id */ }
  }
  return pts.map(() => null);
}

function pickSeparated(cands, n) {
  const out = [];
  for (const c of cands) { if (out.every((o) => distKm(o, c) >= SEP_KM)) out.push(c); if (out.length >= n) break; }
  return out;
}

export async function buildReport({ fetchFn = globalThis.fetch, now = Date.now(), sleep } = {}) {
  if (sleep) sleepFn = sleep;
  const win = riyadhDay(now);
  const grid = buildGrid();
  const models = {}; const data = {}; const errors = [];
  for (const k of MODEL_KEYS) {
    const [res, init] = await Promise.allSettled([fetchModel(fetchFn, k, grid, win), fetchInit(fetchFn, k)]);
    const initMs = init.status === 'fulfilled' ? init.value : null;
    if (res.status === 'fulfilled') { data[k] = res.value; models[k] = { label: MODELS[k].label, id: res.value.id, init: initMs, ok: true }; }
    else { models[k] = { label: MODELS[k].label, id: null, init: initMs, ok: false, error: String(res.reason && res.reason.message || res.reason) }; errors.push(`${MODELS[k].label}: ${models[k].error}`); }
  }
  const avail = MODEL_KEYS.filter((k) => data[k]);
  if (!avail.length) throw Object.assign(new Error(`تعذر جلب أي نموذج: ${errors.join(' | ')}`), { log });

  const { lats, lons } = grid;
  const nb = (k, j, i) => { let m = null; for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) { const v = data[k].P[j + dj] && data[k].P[j + dj][i + di]; if (v != null) m = m == null ? v : Math.max(m, v); } return m; };
  const land = (j, i) => avail.some((k) => { const e = data[k].elev[j][i]; return e != null && e > 0; });

  const cands = [];
  lats.forEach((la, j) => lons.forEach((lo, i) => {
    if (!grid.inside[j][i] || !land(j, i)) return;
    const per = {}; const nbs = [], pts = [];
    for (const k of avail) {
      const p = data[k].P[j][i]; const n = nb(k, j, i); if (p == null || n == null) continue;
      per[k] = { sum: r1(p), nb: r1(n), peak: data[k].peak[j][i], capeMax: data[k].C[j][i] == null ? null : Math.round(data[k].C[j][i]) };
      nbs.push(n); pts.push(p);
    }
    if (!nbs.length) return;
    const agree = nbs.filter((v) => v >= RAIN_MM).length;
    cands.push({ lat: la, lon: lo, j, i, agree, med: median(nbs), mean: pts.reduce((a, b) => a + b, 0) / pts.length, models: per });
  }));
  // Only rain centres can be listed: the multi-model mean at the cell must be the highest
  // among its neighbours. Otherwise the edge of one big rain area would fill all three places.
  const S = lats.map(() => lons.map(() => null)); for (const c of cands) S[c.j][c.i] = c.mean;
  const isPeak = (c) => { for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) { if (!dj && !di) continue; const v = S[c.j + dj] && S[c.j + dj][c.i + di]; if (v != null && v > c.mean) return false; } return true; };
  cands.sort((a, b) => b.agree - a.agree || b.med - a.med || b.mean - a.mean);
  const winners = pickSeparated(cands.filter((c) => c.agree >= 1 && c.mean >= 0.1 && isPeak(c)), 3);

  const ensBy = {};
  if (winners.length) for (const k of avail) ensBy[k] = await fetchEnsembleProbs(fetchFn, k, winners, win);

  const n = avail.length;
  const top = winners.map((c, idx) => {
    const where = describe(c.lat, c.lon);
    const rainy = avail.filter((k) => c.models[k] && c.models[k].nb >= RAIN_MM);
    const conf = c.agree >= 3 ? 'جيدة نسبيًا' : c.agree === 2 ? 'متوسطة' : 'ضعيفة';
    const notes = [];
    if (where.tags.includes('حرة رهط') && rainy.length === 1 && rainy[0] === 'ecmwf') notes.push('مطر الحرة هنا من ECMWF وحده، وECMWF يميل إلى نشر مطر واسع غير دقيق فوق الحرات.');
    if (where.tags.some((t) => t.startsWith('حافة'))) notes.push('قرب حافة الجرف: راجع تبويب «الجرف» لمعرفة هل تقف الخلايا على الحافة أم تنجرف غربًا نحو الأودية.');
    if (where.tags.includes('أودية جنوب مكة')) notes.push('أودية جنوب مكة تستفيد عادة حين تقف الخلايا على الحافة مع حركة رياح جيدة نحو الغرب؛ راجع تبويب «الجرف».');
    const ens = {}; for (const k of avail) { const e = ensBy[k] && ensBy[k][idx]; if (e) ens[k] = { id: e.id, members: e.members, p1: Math.round(e.p1 * 100), p5: Math.round(e.p5 * 100) }; }
    const line = `${c.agree} من ${n} نماذج تعطي ≥${RAIN_MM} مم في الخلية أو ما حولها · الوسيط ${r1(c.med)} مم`;
    return { rank: idx + 1, lat: c.lat, lon: c.lon, where, agree: c.agree, nModels: n, median: r1(c.med), confidence: conf, rainyModels: rainy, models: c.models, ens, notes, line };
  });

  const perModel = {};
  for (const k of avail) {
    const peakK = (c) => { for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) { const v = data[k].P[c.j + dj] && data[k].P[c.j + dj][c.i + di]; if (v != null && v > data[k].P[c.j][c.i]) return false; } return true; };
    const list = cands.filter((c) => c.models[k] && c.models[k].sum >= 0.5 && peakK(c)).sort((a, b) => b.models[k].sum - a.models[k].sum);
    perModel[k] = pickSeparated(list, 3).map((c) => ({ lat: c.lat, lon: c.lon, sum: c.models[k].sum, where: describe(c.lat, c.lon) }));
  }
  let maxAny = null;
  for (const c of cands) for (const k of avail) { const s = c.models[k] && c.models[k].sum; if (s != null && (!maxAny || s > maxAny.sum)) maxAny = { model: k, label: MODELS[k].label, sum: s, lat: c.lat, lon: c.lon }; }
  if (maxAny) maxAny.where = describe(maxAny.lat, maxAny.lon);

  let summary;
  if (top.length) {
    summary = `أفضل الأماكن للمطر من الظهر حتى منتصف الليل حسب النماذج: ${top.map((t) => `${t.rank}) ${t.where.text} (${t.agree} من ${n} نماذج)`).join('، ')}.`;
    if (top[0].agree < 2) summary += ' لا يوجد اتفاق بين نموذجين على أي مكان، فالثقة ضعيفة.';
  } else if (maxAny && maxAny.sum >= 0.5) {
    summary = `لا يتوقع أي نموذج ${RAIN_MM} مم أو أكثر في منطقة مكة من الظهر حتى منتصف الليل. أعلى قيمة ${maxAny.sum} مم في ${maxAny.label} ${maxAny.where.text}.`;
  } else summary = 'النماذج الثلاثة جافة تقريبًا في منطقة مكة من الظهر حتى منتصف الليل.';
  if (errors.length) summary += ` (تعذر جلب: ${MODEL_KEYS.filter((k) => !data[k]).map((k) => MODELS[k].label).join('، ')})`;

  return {
    version: 1, issuedAt: now, date: win.date,
    window: { start: win.start, end: win.end, label: 'من 12:00 ظهرًا حتى منتصف الليل بتوقيت مكة' },
    grid: { step: STEP, points: cands.length, rainMm: RAIN_MM, sepKm: SEP_KM },
    models, top, perModel, maxAny, summary,
    method: `شبكة ${STEP}° (نحو 22 كم) داخل حدود تقريبية لمنطقة مكة الإدارية. لكل نموذج يُجمع المطر من 12:00 إلى 24:00 بتوقيت مكة. يُعدّ النموذج متوقعًا للمطر في مكان إذا أعطى ${RAIN_MM} مم أو أكثر في خليته أو الخلايا الملاصقة (نحو 20 كم)، لأن موضع المطر في النماذج العالمية ينزاح عادة عشرات الكيلومترات. الترتيب: عدد النماذج المتفقة، ثم وسيط كميات المطر، مع مسافة ${SEP_KM} كم على الأقل بين الأماكن. احتمالات المجموعات عند النقطة نفسها بدقة نحو 25 كم.`,
    region: MAKKAH_REGION, errors, log: log.slice(-20),
  };
}

export function writeReport(rep, dir) {
  fs.mkdirSync(dir, { recursive: true });
  const json = JSON.stringify(rep);
  fs.writeFileSync(path.join(dir, `${rep.date}.json`), json);
  fs.writeFileSync(path.join(dir, 'latest.json'), json);
  const idxFile = path.join(dir, 'index.json');
  let idx = { dates: [] };
  try { idx = JSON.parse(fs.readFileSync(idxFile, 'utf8')); } catch { /* first run */ }
  const dates = [rep.date, ...(idx.dates || []).filter((d) => d !== rep.date)].sort().reverse().slice(0, 90);
  fs.writeFileSync(idxFile, JSON.stringify({ updated: rep.issuedAt, dates }));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const dir = path.join(root, 'reports');
  const status = (o) => { fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(path.join(dir, 'status.json'), JSON.stringify({ at: Date.now(), ...o }, null, 1)); };
  buildReport().then((rep) => {
    writeReport(rep, dir);
    status({ ok: true, date: rep.date, errors: rep.errors, log: rep.log });
    console.log(rep.summary);
    for (const t of rep.top) console.log(`${t.rank}. ${t.where.text} ${t.lat},${t.lon} agree ${t.agree}/${t.nModels}`);
    if (rep.errors.length) console.log('errors:', rep.errors.join(' | '));
  }).catch((e) => { console.error(e); status({ ok: false, error: String(e.message || e), log: (e.log || log).slice(-20) }); process.exit(1); });
}
