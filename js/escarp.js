// Escarpment & valleys panel: where cells form on the crest, whether they stand or move,
// and whether the valleys south of Makkah benefit. Plus basalt heating over the harrat.
import { ESCARP, ESCARP_DEFAULTS, MODELS, MODEL_KEYS } from './config.js';
import { fetchMulti, fetchElevation } from './api.js';
import { buildProfile, uv, dirFromUV, speedUV, parcelCapeCin, convectiveTemp, basaltWarming, warmProfile, mlTop } from './met.js';
import { el, num, fmtDay, fmtDayHour, fmtDateTime, riyadhHour, dirName, towardName, store, ago } from './util.js';
import { timeSeries } from './charts.js';

const LV = [850, 700, 600, 500, 400, 300];
const VARS = [
  'temperature_2m', 'dew_point_2m', 'relative_humidity_2m', 'surface_pressure', 'wind_speed_10m', 'wind_direction_10m',
  'precipitation', 'cape', 'convective_inhibition', 'shortwave_radiation', 'boundary_layer_height',
  ...LV.flatMap((p) => ['temperature', 'relative_humidity', 'wind_speed', 'wind_direction', 'geopotential_height'].map((v) => `${v}_${p}hPa`)),
];

function boxPoints(b, n) {
  const pts = [];
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    pts.push([b.lat0 + (b.lat1 - b.lat0) * (j + 0.5) / n, b.lon0 + (b.lon1 - b.lon0) * (i + 0.5) / n]);
  }
  return pts;
}
const LAYOUT = (() => {
  const crest = ESCARP.crests.map((c) => [c.lat, c.lon]);
  const valleys = boxPoints(ESCARP.boxes.valleys, 2);
  const harrat = boxPoints(ESCARP.boxes.harrat, 3);
  const ref = boxPoints(ESCARP.boxes.ref, 2);
  const all = [...crest, ...valleys, ...harrat, ...ref];
  let k = 0; const idx = {};
  for (const [name, arr] of Object.entries({ crest, valleys, harrat, ref })) { idx[name] = arr.map(() => k++); }
  return { all, idx, harratPts: harrat, refPts: ref };
})();

export const CLASSES = {
  valley: { label: 'تنشأ على الحافة وتنزلق غربًا نحو الأودية', short: 'للأودية', color: 'var(--c-valley)' },
  drift: { label: 'تنجرف غربًا دون تغذية قوية على الحافة', short: 'غربًا', color: 'var(--c-drift)' },
  anchor: { label: 'ثابتة فوق الحافة (تغذية صاعدة ورياح توجيه ضعيفة)', short: 'ثابتة', color: 'var(--c-anchor)' },
  weak: { label: 'بطيئة الحركة قرب مكان النشوء', short: 'بطيئة', color: 'var(--c-weak)' },
  along: { label: 'تتحرك موازية للحافة', short: 'موازية', color: 'var(--c-along)' },
  east: { label: 'تُدفع شرقًا نحو الهضبة', short: 'شرقًا', color: 'var(--c-east)' },
  fast: { label: 'سريعة الحركة', short: 'سريعة', color: 'var(--c-fast)' },
  none: { label: 'لا نشوء متوقع', short: '', color: 'var(--surface-2)' },
};

let cache = null; // { at, models: {key: {blocks, id}}, grads, elev, errors }
let ui = { day: 0, sel: null };

export function escarpBoxes() { return ESCARP.boxes; }

async function load(force) {
  if (!force && cache && Date.now() - cache.at < 20 * 60 * 1000) return cache;
  const c = { at: Date.now(), models: {}, errors: {}, grads: [], elev: {} };
  const d = 0.04;
  const demPts = ESCARP.crests.flatMap((p) => [[p.lat + d, p.lon], [p.lat - d, p.lon], [p.lat, p.lon + d], [p.lat, p.lon - d], [p.lat, p.lon]]);
  const jobs = MODEL_KEYS.map((k) => fetchMulti(k, LAYOUT.all, VARS, { days: 3 })
    .then((r) => { c.models[k] = r; })
    .catch((e) => { c.errors[k] = e.reason || e.message; }));
  jobs.push(fetchElevation(demPts).then((e) => {
    const R = 6371000, rad = Math.PI / 180;
    ESCARP.crests.forEach((p, n) => {
      const [hN, hS, hE, hW, h0] = e.slice(n * 5, n * 5 + 5);
      c.elev[p.id] = h0;
      if ([hN, hS, hE, hW].some((x) => x == null)) { c.grads.push(null); return; }
      const gx = (hE - hW) / (R * Math.cos(p.lat * rad) * 2 * d * rad), gy = (hN - hS) / (R * 2 * d * rad);
      const g = Math.hypot(gx, gy) || 1;
      c.grads.push({ x: gx / g, y: gy / g, slope: g, uphillFrom: (Math.atan2(gx, gy) * 180 / Math.PI + 360) % 360 });
    });
  }).catch(() => { ESCARP.crests.forEach(() => c.grads.push(null)); }));
  await Promise.allSettled(jobs);
  cache = c;
  return c;
}

function crestDiag(block, i, grad, th, eth) {
  const pr = buildProfile(block.hourly, i, LV, null);
  const h = block.hourly;
  const at = (v) => (h[v] ? h[v][i] : null);
  const cape = at('cape'), cin = at('convective_inhibition'), rh700 = pr.levels.find((l) => l.p === 700);
  const [u10, v10] = uv(at('wind_speed_10m'), at('wind_direction_10m'));
  const inflow = grad && u10 != null ? u10 * grad.x + v10 * grad.y : null;
  const st = pr.levels.filter((l) => [700, 600, 500].includes(l.p) && !l.under && l.u != null);
  const steer = st.length ? (() => { const u = st.reduce((a, l) => a + l.u, 0) / st.length, v = st.reduce((a, l) => a + l.v, 0) / st.length; return { u, v, speed: speedUV(u, v), dirFrom: dirFromUV(u, v) }; })() : null;
  const down = steer && grad ? -(steer.u * grad.x + steer.v * grad.y) : null;
  const sw = at('shortwave_radiation');
  let init = null;
  if (cape != null) {
    if (cape < th.capeWeak) init = 0;
    else {
      init = 1;
      const cinOK = cin == null || Math.abs(cin) < th.cinCap;
      const moist = rh700 && !rh700.under && rh700.rh != null ? rh700.rh >= th.rh700Dry : true;
      if (cinOK && moist) init++;
      if ((inflow != null && inflow >= eth.inflowMin) || (sw != null && sw > 600 && inflow != null && inflow > 0)) init++;
    }
  }
  let cls = 'none';
  if (init != null && init >= 1 && steer) {
    if (steer.speed > eth.steerFast) cls = 'fast';
    else if (down != null && down <= -eth.downMin) cls = 'east';
    else if (steer.speed < eth.steerWeak) cls = inflow != null && inflow >= eth.inflowMin ? 'anchor' : 'weak';
    else if (down != null && down >= eth.downMin) cls = inflow != null && inflow >= eth.inflowMin ? 'valley' : 'drift';
    else cls = 'along';
  }
  return { cape, cin, rh700: rh700 && !rh700.under ? rh700.rh : null, inflow, steer, down, init, cls, precip: at('precipitation'), sw };
}

function dayKey(t) { return fmtDay(t); }

function harratDay(block, times, dayIdx, th, eth) {
  // Peak afternoon hour (12-15 LT) with the strongest sunshine at the box centre.
  const centre = LAYOUT.idx.harrat[4];
  const H = block.blocks;
  const hrs = times.map(riyadhHour);
  const days = [...new Set(times.map(dayKey))];
  const dk = days[dayIdx]; if (!dk) return null;
  const inDay = times.map((t, i) => (dayKey(t) === dk ? i : -1)).filter((i) => i >= 0);
  const cand = inDay.filter((i) => hrs[i] >= 12 && hrs[i] <= 15);
  if (!cand.length) return null;
  const swC = H[centre].hourly.shortwave_radiation || [];
  const peak = cand.reduce((a, b) => ((swC[b] || 0) > (swC[a] || 0) ? b : a), cand[0]);
  const rows = LAYOUT.idx.harrat.map((pi) => {
    const b = H[pi]; const hh = b.hourly;
    const warm = hh.shortwave_radiation ? basaltWarming(hh.shortwave_radiation, hh.boundary_layer_height || null, hrs, eth)[peak] : null;
    const pr = buildProfile(hh, peak, LV, null);
    const sfc = pr.sfc;
    const blhP = hh.boundary_layer_height ? hh.boundary_layer_height[peak] : null;
    const mlTopP = mlTop(sfc.p, blhP);
    const base = parcelCapeCin(sfc, pr.levels, { mlTopP });
    const wp = warmProfile(pr, warm, blhP);
    const adj = wp ? parcelCapeCin(wp.sfc, wp.levels, { mlTopP }) : null;
    const tc = convectiveTemp(sfc, pr.levels, 15, { mlTopP });
    const pAft = inDay.filter((i) => hrs[i] >= 11 && hrs[i] <= 19).reduce((a, i) => a + ((hh.precipitation && hh.precipitation[i]) || 0), 0);
    return { t2: sfc.tC, warm, base, adj, tc, pAft, cape: pr.cape, rh700: (pr.levels.find((l) => l.p === 700) || {}).rh };
  });
  const refT = LAYOUT.idx.ref.map((pi) => { const hh = H[pi].hourly; return hh.temperature_2m ? hh.temperature_2m[peak] : null; }).filter((v) => v != null);
  const avg = (f) => { const xs = rows.map(f).filter((v) => v != null && Number.isFinite(v)); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
  const t2 = avg((r) => r.t2), warm = avg((r) => r.warm), tc = avg((r) => r.tc);
  const out = {
    t: times[peak], t2, warm, tc, refT2: refT.length ? refT.reduce((a, b) => a + b, 0) / refT.length : null,
    capeBase: avg((r) => r.base && r.base.cape), cinBase: avg((r) => r.base && r.base.cin),
    capeAdj: avg((r) => r.adj && r.adj.cape), cinAdj: avg((r) => r.adj && r.adj.cin),
    modelCape: avg((r) => r.cape), rh700: avg((r) => r.rh700),
    cover: rows.filter((r) => r.pAft >= 1).length / rows.length, coverAny: rows.filter((r) => r.pAft >= 0.2).length / rows.length,
    n: rows.length, swMissing: rows.every((r) => r.warm == null),
  };
  // Verdict (interpretation)
  const reach = out.t2 != null && out.warm != null && out.tc != null ? out.t2 + out.warm - out.tc : null;
  const moistLow = out.rh700 != null && out.rh700 < th.rh700Dry;
  if (out.tc == null || out.t2 == null) out.verdict = ['لا يمكن الحكم: بيانات المقطع ناقصة.', 'none'];
  else if (moistLow && (out.capeAdj ?? 0) < 100) out.verdict = ['الرطوبة المتوسطة غير كافية؛ تسخين البازلت لا يكفي لنشوء خلايا ممطرة.', 'ok'];
  else if (out.t2 >= out.tc) out.verdict = ['الطبقة المانعة مكسورة أصلًا في النموذج؛ تسخين البازلت يزيد قوة الحمل ويقدّم توقيته فوق الحرة.', 'alert'];
  else if (reach != null && reach >= 0) out.verdict = ['تسخين البازلت يكفي على الأرجح لبلوغ حرارة الحمل: احتمال النشوء فوق الحرة أعلى مما تُظهره النماذج.', 'alert'];
  else if (reach != null && reach > -2) out.verdict = ['تسخين البازلت يقرّب الهواء من حرارة الحمل دون بلوغها؛ يكفي أي رفع إضافي (تقارب أو حافة) لإطلاق خلايا.', 'watch'];
  else out.verdict = ['حتى مع تسخين البازلت تبقى الطبقة المانعة قوية؛ النشوء فوق الحرة غير مرجّح.', 'ok'];
  return out;
}

function dayVerdict(rows) {
  // rows: diagnostics for afternoon hours (both crests)
  const strong = rows.filter((r) => r.init != null && r.init >= 2);
  if (!rows.some((r) => r.init != null)) return { text: 'CAPE غير متاح من هذا النموذج', level: 'none', cls: 'none' };
  if (!strong.length) return { text: 'لا نشوء واضح على الحافة', level: 'ok', cls: 'none' };
  const count = {}; for (const r of strong) count[r.cls] = (count[r.cls] || 0) + 1;
  const grp = { valley: (count.valley || 0) + (count.drift || 0), anchor: (count.anchor || 0) + (count.weak || 0), east: count.east || 0, fast: count.fast || 0, along: count.along || 0 };
  const top = Object.entries(grp).sort((a, b) => b[1] - a[1])[0][0];
  const map = {
    valley: ['يوم أودية: نشوء على الحافة وانزلاق نحو الغرب', 'alert', 'valley'],
    anchor: ['المطر يبقى على القمم؛ الأودية تستفيد من جريان أعالي المساقط فقط', 'watch', 'anchor'],
    east: ['النشوء يُدفع شرقًا نحو الهضبة؛ لا استفادة للأودية', 'info', 'east'],
    fast: ['خلايا سريعة الحركة؛ مطر قصير في مسارها', 'info', 'fast'],
    along: ['خلايا تتحرك موازية للحافة', 'info', 'along'],
  };
  const [text, level, cls] = map[top];
  return { text, level, cls, hours: strong.length };
}

function numInput(id, label, obj, key, onChange) {
  return el('label', { class: 'field' }, el('span', {}, label), el('input', { id, type: 'number', step: 'any', inputmode: 'decimal', value: obj[key], onchange: (e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) { obj[key] = v; onChange(); } } }));
}

export async function renderEscarp(host, { th, windParts, force = false, onShowMap }) {
  const eth = { ...ESCARP_DEFAULTS, ...store.get('eth', {}) };
  if (!cache || force) { host.innerHTML = ''; host.append(el('div', { class: 'empty' }, el('div', { class: 'spinner' }), el('p', {}, 'جارٍ جلب نقاط الحافة والأودية والحرات من النماذج الثلاثة…'))); }
  const C = await load(force);
  host.innerHTML = '';
  const keys = MODEL_KEYS.filter((k) => C.models[k]);
  if (!keys.length) {
    host.append(el('div', { class: 'empty' }, el('p', {}, `تعذر جلب البيانات: ${Object.values(C.errors).join(' | ')}`), el('button', { class: 'btn', onclick: () => renderEscarp(host, { th, windParts, force: true, onShowMap }) }, 'أعد المحاولة')));
    return;
  }
  const times = C.models[keys[0]].blocks[0].hourly.time;
  const now = Date.now();
  const days = [...new Set(times.filter((t) => { const h = riyadhHour(t); return t >= now - 3600000 && h >= 11 && h <= 18; }).map(dayKey))];

  host.append(el('div', { class: 'panel-head' }, el('h2', {}, 'الجرف والأودية والحرات'),
    el('p', { class: 'meta' }, `النماذج: ${keys.map((k) => MODELS[k].label).join('، ')} · جُلبت ${ago(C.at)}${Object.keys(C.errors).length ? ` · تعذر: ${Object.keys(C.errors).map((k) => MODELS[k].label).join('، ')}` : ''}`)));

  // ---- per-day verdicts
  const diag = {}; // diag[k][crestIdx][i]
  for (const k of keys) {
    diag[k] = ESCARP.crests.map((_, ci) => times.map((__, i) => crestDiag(C.models[k].blocks[LAYOUT.idx.crest[ci]], i, C.grads[ci], th, eth)));
  }
  const dayCards = el('div', { class: 'days' });
  days.forEach((dk, di) => {
    const lines = keys.map((k) => {
      const rows = [];
      times.forEach((t, i) => { const h = riyadhHour(t); if (dayKey(t) === dk && h >= 11 && h <= 18 && t >= now - 3600000) diag[k].forEach((c) => rows.push(c[i])); });
      const v = rows.length ? dayVerdict(rows) : { text: 'انقضى وقت العصر', level: 'none', cls: 'none' };
      return el('div', { class: 'dv' }, el('span', { class: 'dv-m', style: `--mc:${MODELS[k].color}` }, MODELS[k].label.split(' ')[0]), el('span', { class: `dv-dot`, style: `background:${CLASSES[v.cls].color}` }), el('span', {}, v.text));
    });
    dayCards.append(el('button', { class: `day${ui.day === di ? ' on' : ''}`, onclick: () => { ui.day = di; ui.sel = null; renderEscarp(host, { th, windParts, onShowMap }); } },
      el('b', {}, di === 0 ? `اليوم · ${dk}` : dk), ...lines));
  });
  host.append(section('خلاصة العصر (11:00–18:00) لكل نموذج', dayCards,
    el('p', { class: 'meta' }, 'تفسير محسوب من النماذج وفق نموذجك المفاهيمي، وليس رصدًا. اضغط يومًا لعرض ساعاته.')));

  // ---- hourly grid for the selected day
  const dk = days[ui.day] || days[0];
  const hIdx = times.map((t, i) => (dayKey(t) === dk && riyadhHour(t) >= 8 && riyadhHour(t) <= 21 ? i : -1)).filter((i) => i >= 0);
  const table = el('table', { class: 'egrid' });
  table.append(el('thead', {}, el('tr', {}, el('th', {}, ''), ...hIdx.map((i) => el('th', {}, String(riyadhHour(times[i])).padStart(2, '0'))))));
  const tb = el('tbody');
  for (const k of keys) {
    ESCARP.crests.forEach((c, ci) => {
      tb.append(el('tr', {}, el('th', { class: 'rowh', style: `--mc:${MODELS[k].color}` }, `${MODELS[k].label.split(' ')[0]} · ${c.name}`),
        ...hIdx.map((i) => {
          const d = diag[k][ci][i];
          const op = d.init == null ? 0.25 : [0.15, 0.45, 0.75, 1][d.init];
          const isSel = ui.sel && ui.sel.k === k && ui.sel.ci === ci && ui.sel.i === i;
          return el('td', { class: `ec${isSel ? ' sel' : ''}`, onclick: () => { ui.sel = { k, ci, i }; renderEscarp(host, { th, windParts, onShowMap }); } },
            el('span', { class: 'ecb', style: `background:${CLASSES[d.cls].color};opacity:${op}` }), d.init ? el('i', {}, '•'.repeat(d.init)) : null);
        })));
    });
  }
  table.append(tb);
  const legend = el('div', { class: 'legend' }, ...Object.entries(CLASSES).filter(([k]) => k !== 'none').map(([, c]) => el('span', { class: 'lg' }, el('i', { style: `background:${c.color}` }), c.short)), el('span', { class: 'lg' }, 'النقاط = قوة احتمال النشوء (1–3)'));
  const detail = el('div', { class: 'edetail' });
  if (ui.sel && diag[ui.sel.k]) {
    const d = diag[ui.sel.k][ui.sel.ci][ui.sel.i];
    const c = ESCARP.crests[ui.sel.ci];
    const [sv, su] = d.steer ? windParts(d.steer.speed) : ['—', ''];
    detail.append(el('b', {}, `${MODELS[ui.sel.k].label} · ${c.name} · ${fmtDateTime(times[ui.sel.i])}`),
      el('p', {}, CLASSES[d.cls].label),
      el('ul', { class: 'bullets' },
        el('li', {}, `CAPE ${num(d.cape)} J/kg · CIN ${d.cin == null ? 'غير متاح' : num(Math.abs(d.cin))} · رطوبة 700 ${d.rh700 == null ? '—' : num(d.rh700)}٪`),
        el('li', {}, `التغذية الصاعدة على الحافة (رياح 10 م باتجاه أعلى المنحدر): ${d.inflow == null ? 'غير متاح' : `${num(d.inflow, 1)} م/ث`}`),
        el('li', {}, d.steer ? `رياح التوجيه ${dirName(d.steer.dirFrom)} ${sv} ${su}؛ مركّبتها نحو الأودية (غربًا أسفل المنحدر) ${num(d.down, 1)} م/ث` : 'رياح التوجيه غير متاحة'),
        el('li', {}, `مطر النموذج في الساعة عند ${c.name}: ${num(d.precip, 1)} مم`)));
  } else detail.append(el('p', { class: 'hint' }, 'اضغط أي خلية لعرض قيمها.'));
  host.append(section(`ساعات ${dk}`, el('div', { class: 'tbl-wrap' }, table), legend, detail));

  // ---- precipitation crest vs valleys
  const k0 = Math.max(0, times.findIndex((t) => t >= now - 3 * 3600000));
  const T = times.slice(k0, k0 + 72);
  const series = (pidxs) => keys.map((k) => ({ label: MODELS[k].label, color: MODELS[k].color, kind: 'bar', values: T.map((_, j) => { const xs = pidxs.map((pi) => { const p = C.models[k].blocks[pi].hourly.precipitation; return p ? p[k0 + j] : null; }).filter((v) => v != null); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; }) }));
  const hCrest = el('div', { class: 'chart' }), hVal = el('div', { class: 'chart' });
  host.append(section('مطر النماذج على الحافة (الهدا والشفا)', hCrest), section(`مطر النماذج في ${ESCARP.boxes.valleys.name} (متوسط 4 نقاط)`, hVal,
    el('p', { class: 'meta' }, 'مطر الأودية المباشر في النماذج العالمية ضعيف التمثيل؛ استفادة الأودية تأتي غالبًا من خلايا الحافة وجريان أعالي المساقط، فاقرأه مع التصنيف أعلاه.')));
  requestAnimationFrame(() => { timeSeries(hCrest, { times: T, unit: 'مم', series: series(LAYOUT.idx.crest) }); timeSeries(hVal, { times: T, unit: 'مم', series: series(LAYOUT.idx.valleys) }); });

  // ---- harrat basalt heating
  const hr = el('div', { class: 'cards cards-3' });
  for (const k of keys) {
    const H = harratDay(C.models[k], times, ui.day, th, eth);
    if (!H) { hr.append(el('div', { class: 'card card-na' }, el('div', { class: 'card-label' }, MODELS[k].label), el('div', { class: 'card-sub' }, 'لا توجد ساعات عصر لهذا اليوم'))); continue; }
    hr.append(el('div', { class: 'card model-card', style: `--mc:${MODELS[k].color}` },
      el('div', { class: 'card-label' }, `${MODELS[k].label} · ${fmtDayHour(H.t)}`),
      el('span', { class: `pill pill-${H.verdict[1]}` }, H.verdict[0]),
      el('div', { class: 'kv' },
        kv('حرارة 2 م في النموذج', H.t2 == null ? '—' : `${num(H.t2, 1)}°م`),
        kv('تسخين إضافي للبازلت', H.warm == null ? 'غير متاح' : `+${num(H.warm, 1)}°م`),
        kv('حرارة الحمل المطلوبة', H.tc == null ? '—' : `${num(H.tc, 1)}°م`),
        kv('CAPE (حسابنا)', H.capeBase == null ? '—' : `قبل ${num(H.capeBase)} · بعد ${num(H.capeAdj)}`),
        kv('CIN (حسابنا)', H.cinBase == null ? '—' : `قبل ${num(Math.abs(H.cinBase))} · بعد ${num(Math.abs(H.cinAdj ?? 0))}`),
        kv('الحرة ناقص أرض المقارنة', H.t2 != null && H.refT2 != null ? `${num(H.t2 - H.refT2, 1)}°م في النموذج` : '—'),
        kv('نقاط الحرة بمطر ≥1 مم عصرًا', `${Math.round(H.cover * 100)}٪ من ${H.n}`)),
      H.swMissing ? el('div', { class: 'card-sub' }, 'الإشعاع الشمسي غير متاح من هذا النموذج، فلم يُحسب التسخين الإضافي.') : null));
  }
  host.append(section(`الحرات: أثر البازلت على التسخين والحمل · ${dk}`, hr,
    el('ul', { class: 'bullets' },
      el('li', {}, 'نسبة النقاط الممطرة في النموذج اقرأها احتمالًا مساحيًا لخلية أو أكثر داخل الحرة، لا مطرًا على كل الحرة. هذا ما يحدث حين يُظهر ECMWF المطر على الحرات كلها.'),
      el('li', {}, 'حرارة الحمل: حرارة 2 م اللازمة ليرتفع الهواء السطحي حرًا دون طاقة إضافية. إذا بلغها النموذج مع تسخين البازلت، فالنشوء فوق الحرة أرجح مما يعرضه النموذج.'))));

  // ---- method and assumptions (editable)
  const save = () => { store.set('eth', eth); renderEscarp(host, { th, windParts, onShowMap }); };
  host.append(section('الطريقة والافتراضات',
    el('ul', { class: 'bullets' },
      el('li', {}, `اتجاه أعلى المنحدر عند كل نقطة حافة محسوب من نموذج الارتفاع (Copernicus 90 م) على بعد 4 كم: ${ESCARP.crests.map((c, i) => (C.grads[i] ? `${c.name} يرتفع نحو ${towardName(C.grads[i].uphillFrom)} (ارتفاع ${num(C.elev[c.id])} م)` : `${c.name}: غير متاح`)).join('؛ ')}.`),
      el('li', {}, 'التغذية الصاعدة = رياح 10 م مسقطة على اتجاه أعلى المنحدر. رياح التوجيه = متوسط 700 و600 و500 hPa، ومركّبتها نحو الأودية = إسقاطها على اتجاه أسفل المنحدر (غربًا).'),
      el('li', {}, 'تسخين البازلت: dθ/dt = fH × الإشعاع الهابط × (ألبيدو النموذج − ألبيدو البازلت) ÷ (ρ cp × عمق الطبقة الحدية)، يتراكم من الشروق. ثم يُعاد حساب CAPE وCIN لجسيم سطحي أدفأ بالمقدار نفسه وبالرطوبة نفسها. الطبقة المختلطة تُعامل كطبقة متجانسة محايدة، فيُحسب الفرق فوق قمتها فقط، حيث يواجه الجسيم الطبقة المانعة.'),
      el('li', {}, 'هذا تصحيح تقديري لا يعيد تشغيل النموذج. ألبيدو النموذج الفعلي فوق الحرة غير معلن في البيانات المفتوحة، فالقيمة الافتراضية افتراض قابل للتعديل. التحقق الحقيقي: مقارنة حرارة سطح الحرة المرصودة من الأقمار بحرارة النموذج.'),
      el('li', {}, 'النطاقات مستطيلات تقريبية؛ تحقق منها على خريطة القمر الصناعي.')),
    el('button', { class: 'btn ghost', onclick: onShowMap }, 'اعرض النطاقات على الخريطة'),
    el('details', {}, el('summary', {}, 'تعديل المعاملات'),
      numInput('e-inflow', 'أدنى تغذية صاعدة (م/ث)', eth, 'inflowMin', save),
      numInput('e-weak', 'توجيه ضعيف تحت (م/ث)', eth, 'steerWeak', save),
      numInput('e-fast', 'توجيه سريع فوق (م/ث)', eth, 'steerFast', save),
      numInput('e-down', 'أدنى مركّبة نحو الأودية (م/ث)', eth, 'downMin', save),
      numInput('e-am', 'ألبيدو النموذج المفترض فوق الحرة', eth, 'albModel', save),
      numInput('e-ab', 'ألبيدو البازلت', eth, 'albBasalt', save),
      numInput('e-fh', 'نسبة التسخين المحسوس fH', eth, 'fH', save),
      el('button', { class: 'btn ghost', onclick: () => { store.del('eth'); renderEscarp(host, { th, windParts, onShowMap }); } }, 'استعادة الافتراضي'))));
}

function kv(k, v) { return el('div', { class: 'kv-row' }, el('span', {}, k), el('b', {}, v)); }
function section(title, ...kids) { return el('section', { class: 'block' }, el('h3', {}, title), ...kids); }
