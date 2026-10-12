// Application shell: state, loading, tabs and panels.
import { SITE, PLACES, PROFILES, DEFAULT_PROFILE, MODELS, MODEL_KEYS, LEVELS, DEFAULT_THRESHOLDS, GRIDS, METAR_STATIONS, ENDPOINTS } from './config.js';
import { store, el, num, fmtTime, fmtDateTime, fmtDayHour, fmtDay, fmtUTC, ago, dirName, towardName, escapeHTML, sum, max } from './util.js';
import { fetchModelPoint, fetchEnsemble, fetchMeta, fetchElevation, fetchMulti, fetchPreviousDay1, fetchMetars, POINT_VARS } from './api.js';
import { buildProfile, diagnostics, parcelPath, uv, lcl } from './met.js';
import { timeSeries, timeHeight, skewT, crossSection } from './charts.js';
import { buildAnalysis, ensembleProb } from './analysis.js';
import { WxMap, FIELDS, LEGENDS, BASES, SAT_LAYERS } from './map.js';
import { renderEscarp, escarpBoxes } from './escarp.js';
import { ESCARP, ESCARP_DEFAULTS } from './config.js';
import { basaltWarming, convectiveTemp, parcelCapeCin, warmProfile, mlTop } from './met.js';

// ---------------------------------------------------------------- state
const state = {
  place: store.get('place', PLACES[0]),
  favs: store.get('favs', PLACES.filter((p) => p.fav).map((p) => p.id)),
  customs: store.get('customs', []),
  settings: { wind: 'kmh', theme: 'auto', saver: false, ...store.get('settings', {}) },
  th: { ...DEFAULT_THRESHOLDS, ...store.get('th', {}) },
  data: { models: {}, ens: {}, meta: {}, errors: {}, ensErrors: {}, elev: null, grad: null, loadedAt: null, loading: false },
  convModel: store.get('convModel', 'ecmwf'),
  validTime: null,
  tab: 'map',
  mapUI: { field: null, model: 'ecmwf', grid: 'near', ti: null, win: 3, obs: {} },
  metars: null,
};
let wxmap = null;
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- formatting
function windParts(ms) {
  if (ms == null) return ['—', ''];
  if (state.settings.wind === 'kt') return [num(ms * 1.94384), 'عقدة'];
  if (state.settings.wind === 'ms') return [num(ms, 1), 'م/ث'];
  return [num(ms * 3.6), 'كم/س'];
}
function vvParts(v, unit) {
  if (v == null) return [NA, ''];
  if (/^m\/s$/i.test(unit || '')) return [num(v * 100, 1), 'سم/ث'];
  return [num(v, 2), unit || ''];
}
function windText(ms) {
  if (ms == null) return '—';
  if (state.settings.wind === 'kt') return `${num(ms * 1.94384)} عقدة`;
  if (state.settings.wind === 'ms') return `${num(ms, 1)} م/ث`;
  return `${num(ms * 3.6)} كم/س`;
}
const pill = (text, level) => el('span', { class: `pill pill-${level}` }, text);

function card(label, value, unit, opts = {}) {
  const c = el('div', { class: `card${opts.na ? ' card-na' : ''}` },
    el('div', { class: 'card-label' }, label),
    el('div', { class: 'card-value' }, el('span', { class: 'v' }, value), unit ? el('span', { class: 'u' }, unit) : null),
  );
  if (opts.pill) c.append(pill(opts.pill[0], opts.pill[1]));
  if (opts.sub) c.append(el('div', { class: 'card-sub' }, opts.sub));
  return c;
}
const NA = 'غير متاح';

// ---------------------------------------------------------------- theme
function applyTheme() {
  const t = state.settings.theme;
  if (t === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', t);
}

// ---------------------------------------------------------------- loading
function placeKey(p) { return `${p.lat.toFixed(3)},${p.lon.toFixed(3)}`; }

async function loadPlace(force = false) {
  const p = state.place; const key = placeKey(p);
  state.data = { models: {}, ens: {}, meta: {}, errors: {}, ensErrors: {}, elev: null, grad: null, loadedAt: null, loading: true, key };
  renderStatus(); renderActive();
  const D = state.data;
  const modelJobs = MODEL_KEYS.map((k) => fetchModelPoint(k, p.lat, p.lon, { force })
    .then((d) => { if (state.data === D) D.models[k] = d; })
    .catch((e) => { if (state.data === D) D.errors[k] = e.reason || e.message; }));
  const d = 0.03;
  const elevJob = fetchElevation([[p.lat, p.lon], [p.lat + d, p.lon], [p.lat - d, p.lon], [p.lat, p.lon + d], [p.lat, p.lon - d]])
    .then((e) => {
      D.elev = e[0];
      if (e.every((x) => x != null)) {
        const R = 6371000, rad = Math.PI / 180;
        D.grad = { dhdx: (e[3] - e[4]) / (R * Math.cos(p.lat * rad) * 2 * d * rad), dhdy: (e[1] - e[2]) / (R * 2 * d * rad) };
      }
    }).catch(() => {});
  await Promise.allSettled([...modelJobs, elevJob]);
  if (state.data !== D) return;
  D.loadedAt = Date.now(); D.loading = false;
  if (state.validTime == null) state.validTime = nearestHour();
  renderStatus(); renderActive();
  const rest = [
    ...MODEL_KEYS.map((k) => fetchEnsemble(k, p.lat, p.lon, { force }).then((e) => { D.ens[k] = e; }).catch((e) => { D.ensErrors[k] = e.reason || e.message; })),
    ...MODEL_KEYS.map((k) => fetchMeta(k).then((m) => { D.meta[k] = m; }).catch(() => {})),
  ];
  await Promise.allSettled(rest);
  if (state.data !== D) return;
  renderStatus(); renderActive();
}

function nearestHour() { const t = Date.now(); return Math.round(t / 3600000) * 3600000; }
function idxFor(md, t) {
  if (!md) return -1; const T = md.hourly.time; let best = 0;
  for (let i = 0; i < T.length; i++) if (Math.abs(T[i] - t) < Math.abs(T[best] - t)) best = i;
  return best;
}
const anyModel = () => MODEL_KEYS.map((k) => state.data.models[k]).find(Boolean);

// ---------------------------------------------------------------- status bar
function renderStatus() {
  const D = state.data;
  $('placeName').textContent = state.place.name;
  const bar = $('statusBar'); bar.innerHTML = '';
  if (D.loading) bar.append(el('span', { class: 'busy' }, 'جارٍ جلب بيانات النماذج…'));
  else if (D.loadedAt) bar.append(el('span', {}, `آخر تحديث ${fmtTime(D.loadedAt)}`));
  for (const k of MODEL_KEYS) {
    const md = D.models[k];
    const st = md ? (md.stale ? 'stale' : 'ok') : (D.errors[k] ? 'fail' : (D.loading ? 'wait' : 'fail'));
    const title = md ? `${MODELS[k].label}: ${md.ids.join(' + ')}${md.stale ? ' (نسخة مخزنة)' : ''}` : `${MODELS[k].label}: ${D.errors[k] || '…'}`;
    bar.append(el('span', { class: `src src-${st}`, title }, MODELS[k].label.split(' ')[0]));
  }
  if (!navigator.onLine) bar.append(el('span', { class: 'src src-fail' }, 'لا يوجد اتصال'));
}

// ---------------------------------------------------------------- tabs
const TABS = ['map', 'escarp', 'conv', 'models', 'analysis', 'more'];
function showTab(t) {
  if (!TABS.includes(t)) t = 'map';
  state.tab = t;
  for (const x of TABS) { $(`tab-${x}`).hidden = x !== t; document.querySelector(`[data-tab="${x}"]`).setAttribute('aria-current', x === t ? 'page' : 'false'); }
  if (t === 'map') { ensureMap(); wxmap && wxmap.invalidate(); }
  renderActive();
  try { history.replaceState(null, '', `#${t}`); } catch { /* ignore */ }
}
function renderActive() {
  try {
    if (state.tab === 'conv') renderConv();
    else if (state.tab === 'models') renderModels();
    else if (state.tab === 'analysis') renderAnalysis();
    else if (state.tab === 'more') renderMore();
    else if (state.tab === 'map') renderMapBars();
    else if (state.tab === 'escarp') renderEscarp($('tab-escarp'), { th: state.th, windParts, onShowMap: showEscarpBoxes });
  } catch (e) { console.error(e); }
}

// ---------------------------------------------------------------- place picker
function openPlaces() {
  const body = el('div', { class: 'sheet-body' });
  const mk = (p) => {
    const isFav = state.favs.includes(p.id);
    return el('div', { class: 'place-row' },
      el('button', { class: 'place-pick', onclick: () => { selectPlace(p); closeSheet(); } }, p.name),
      p.custom ? el('button', { class: 'icon-btn', 'aria-label': 'حذف النقطة', onclick: () => { state.customs = state.customs.filter((c) => c.id !== p.id); store.set('customs', state.customs); openPlaces(); } }, '✕')
        : el('button', { class: `icon-btn star${isFav ? ' on' : ''}`, 'aria-label': isFav ? 'إزالة من المفضلة' : 'إضافة إلى المفضلة', onclick: () => { toggleFav(p.id); openPlaces(); } }, isFav ? '★' : '☆'));
  };
  const favs = PLACES.filter((p) => state.favs.includes(p.id));
  body.append(el('h3', {}, 'المفضلة'), ...(favs.length ? favs.map(mk) : [el('p', { class: 'na' }, 'لا توجد مواقع مفضلة بعد.')]));
  if (state.customs.length) body.append(el('h3', {}, 'نقاط محفوظة'), ...state.customs.map(mk));
  body.append(el('h3', {}, 'كل المواقع'), ...PLACES.filter((p) => !state.favs.includes(p.id)).map(mk));
  body.append(el('p', { class: 'hint' }, 'لاختيار أي نقطة أخرى: افتح الخريطة واضغط على المكان.'));
  openSheet('اختيار الموقع', body);
}
function toggleFav(id) { state.favs = state.favs.includes(id) ? state.favs.filter((x) => x !== id) : [...state.favs, id]; store.set('favs', state.favs); }
function selectPlace(p) {
  state.place = { id: p.id, name: p.name, lat: p.lat, lon: p.lon, custom: !!p.custom };
  store.set('place', state.place);
  loadPlace();
}

// ---------------------------------------------------------------- sheet
function openSheet(title, content) {
  const sh = $('sheet'); sh.innerHTML = '';
  sh.append(el('div', { class: 'sheet-head' }, el('h2', {}, title), el('button', { class: 'icon-btn', 'aria-label': 'إغلاق', onclick: closeSheet }, '✕')), content);
  sh.hidden = false; $('scrim').hidden = false;
}
function closeSheet() { $('sheet').hidden = true; $('scrim').hidden = true; }

// ---------------------------------------------------------------- shared time control
function timeControl(onChange) {
  const md = anyModel(); if (!md) return el('div');
  const now = Date.now();
  const times = md.hourly.time.filter((t) => t >= now - 3600000).slice(0, 72);
  if (state.validTime == null || !times.includes(state.validTime)) state.validTime = times[0];
  const k = Math.max(0, times.indexOf(state.validTime));
  const label = el('output', { class: 'time-label' }, fmtDateTime(state.validTime));
  const input = el('input', { type: 'range', min: 0, max: times.length - 1, value: k, step: 1, id: 'timeRange', 'aria-label': 'وقت التوقع' });
  input.addEventListener('input', () => { state.validTime = times[+input.value]; label.textContent = fmtDateTime(state.validTime); });
  input.addEventListener('change', () => onChange());
  const step = (d) => { const v = Math.min(times.length - 1, Math.max(0, +input.value + d)); input.value = v; state.validTime = times[v]; onChange(); };
  return el('div', { class: 'time-ctl' },
    el('button', { class: 'icon-btn', 'aria-label': 'ساعة سابقة', onclick: () => step(-1) }, '›'),
    el('div', { class: 'time-mid' }, label, input),
    el('button', { class: 'icon-btn', 'aria-label': 'ساعة لاحقة', onclick: () => step(1) }, '‹'));
}
function runInfo(k, t) {
  const m = state.data.meta[k];
  if (!m) return 'وقت التشغيل غير متاح من المصدر';
  const lead = Math.round((t - m.init) / 3600000);
  return `تشغيل ${fmtUTC(m.init)} · مهلة +${lead} س`;
}

function emptyState(host, msg) {
  host.innerHTML = '';
  host.append(el('div', { class: 'empty' }, state.data.loading ? el('div', { class: 'spinner', 'aria-hidden': 'true' }) : null, el('p', {}, msg),
    state.data.loading ? null : el('p', { class: 'hint' }, 'تحقق من اتصال الجوال ثم اضغط زر التحديث أعلى الشاشة. إن استمر الخطأ فالمصدر متوقف مؤقتًا أو تجاوز الحد اليومي للطلبات.'),
    state.data.loading ? null : el('button', { class: 'btn', onclick: () => loadPlace(true) }, 'أعد المحاولة')));
}

// ---------------------------------------------------------------- convection panel
function renderConv() {
  const host = $('tab-conv');
  const D = state.data;
  const k = state.convModel; const md = D.models[k];
  if (!anyModel()) return emptyState(host, D.loading ? 'جارٍ تحميل النماذج…' : `تعذر جلب النماذج: ${Object.values(D.errors).join(' | ') || 'سبب غير معروف'}`);
  host.innerHTML = '';
  const seg = el('div', { class: 'seg', role: 'tablist' }, ...MODEL_KEYS.map((m) => el('button', { role: 'tab', 'aria-selected': String(m === k), class: D.models[m] ? '' : 'off', onclick: () => { state.convModel = m; store.set('convModel', m); renderConv(); } }, MODELS[m].label)));
  host.append(el('div', { class: 'panel-head' }, el('h2', {}, `لوحة الحمل الحراري · ${state.place.name}`), seg, timeControl(renderConv)));
  if (!md) { host.append(el('p', { class: 'warn' }, `${MODELS[k].label} غير متاح الآن: ${D.errors[k] || ''}`)); return; }
  const i = idxFor(md, state.validTime);
  const elevation = D.elev ?? md.elevation;
  const pr = buildProfile(md.hourly, i, LEVELS, elevation);
  const d = diagnostics(pr);
  const P = md.hourly.precipitation || [];
  const win = (h) => (P.length ? sum(P.slice(i, i + h)) : null);

  host.append(el('p', { class: 'meta' }, `${runInfo(k, state.validTime)} · ارتفاع النقطة ${num(D.elev)} م (Copernicus DEM) · ارتفاع خلية النموذج ${num(md.elevation)} م`));
  if (pr.sfc.p != null && pr.sfc.p < 930) host.append(el('p', { class: 'note' }, `ضغط السطح في النموذج ${num(pr.sfc.p)} hPa: المستويات الأعلى ضغطًا منه تحت سطح الأرض، وقيمها مستقرأة وغير معروضة في التحليل.`));

  // --- instability
  const th = state.th;
  const capeLv = d.cape == null ? null : d.cape >= th.capeStrong ? ['قوي', 'alert'] : d.cape >= th.capeWeak ? ['متوسط', 'watch'] : ['ضعيف', 'ok'];
  const cinAbs = d.cin == null ? null : Math.abs(d.cin);
  const g1 = el('div', { class: 'cards' },
    card('CAPE', d.cape == null ? NA : num(d.cape), d.cape == null ? '' : 'J/kg', { na: d.cape == null, pill: capeLv }),
    card('CIN', cinAbs == null ? NA : num(cinAbs), cinAbs == null ? '' : 'J/kg', { na: cinAbs == null, pill: cinAbs == null ? null : cinAbs >= th.cinCap ? ['غطاء قوي', 'watch'] : ['غطاء ضعيف', 'ok'], sub: 'القيمة المطلقة' }),
    card('Lifted Index', d.li == null ? NA : num(d.li, 1), '', { na: d.li == null, pill: d.li == null ? null : d.li <= -4 ? ['غير مستقر جدًا', 'alert'] : d.li <= th.liUnstable ? ['غير مستقر', 'watch'] : ['مستقر', 'ok'] }),
    card('حرارة 500 hPa', d.t500 == null ? NA : num(d.t500, 1), '°م', { na: d.t500 == null }),
    card('ارتفاع 700 hPa', d.z700 == null ? NA : num(d.z700), d.z700 == null ? '' : 'م', { na: d.z700 == null, sub: d.t700 == null ? null : `حرارة 700 hPa: ${num(d.t700, 1)}°م` }),
    card('معدل التناقص 700–500', d.lapse75 == null ? NA : num(d.lapse75, 1), '°م/كم', { na: d.lapse75 == null, pill: d.lapse75 == null ? null : d.lapse75 >= th.lapseSteep ? ['حاد', 'watch'] : ['معتدل', 'ok'] }),
  );
  // --- moisture
  const pwLv = d.pw == null ? null : d.pw >= th.pwHigh ? ['عالٍ', 'watch'] : d.pw >= th.pwLow ? ['متوسط', 'info'] : ['منخفض', 'ok'];
  const g2 = el('div', { class: 'cards' },
    card('الماء القابل للهطول', d.pw == null ? NA : num(d.pw), d.pw == null ? '' : 'مم', { na: d.pw == null, pill: pwLv, sub: d.pwSource === 'levels' ? 'محسوب من المستويات (تقريبي)' : null }),
    ...[925, 850, 700, 600, 500].map((p) => {
      const L = pr.levels.find((l) => l.p === p);
      if (!L || L.under) return card(`رطوبة ${p}`, 'تحت السطح', '', { na: true });
      return card(`رطوبة ${p} hPa`, L.rh == null ? NA : num(L.rh), L.rh == null ? '' : '٪', { na: L.rh == null, sub: L.tdC != null && L.tC != null ? `T−Td ${num(L.tC - L.tdC)}°م` : null });
    }),
    card('عمق الطبقة الرطبة', d.moist ? num(d.moist.depth) : 'لا توجد', d.moist ? 'م' : '', { na: !d.moist, sub: d.moist ? `RH≥70٪ بين ${d.moist.botP} و${d.moist.topP} hPa` : 'لا مستويات برطوبة ≥70٪' }),
    card('الجفاف المتوسط', d.dd700 == null ? NA : `${num(d.dd700)} / ${num(d.dd500)}`, '°م', { na: d.dd700 == null, sub: 'T−Td عند 700 / 500', pill: d.dd700 == null ? null : (d.dd700 >= th.ddDry || (d.dd500 ?? 0) >= th.ddDry) ? ['جاف', 'watch'] : ['رطب', 'ok'] }),
  );
  // --- surface and levels
  const s = pr.sfc;
  const g3 = el('div', { class: 'cards' },
    card('حرارة السطح', s.tC == null ? NA : num(s.tC, 1), '°م', { sub: s.tdC != null ? `نقطة الندى ${num(s.tdC, 1)}°م · رطوبة ${num(s.rh)}٪` : null }),
    card('رياح السطح', s.ws == null ? NA : windParts(s.ws)[0], windParts(s.ws)[1], { sub: s.wd != null ? `${dirName(s.wd)} (${num(s.wd)}°)${s.gust != null ? ` · هبات ${windText(s.gust)}` : ''}` : null }),
    card('مستوى التكاثف LCL', d.lclAgl == null ? NA : num(d.lclAgl), 'م فوق السطح', { na: d.lclAgl == null, pill: d.lclAgl != null && d.lclAgl >= th.lclHigh ? ['قاعدة مرتفعة', 'watch'] : null, sub: d.lclP ? `نحو ${num(d.lclP)} hPa · من حرارة ونقطة ندى 2 م` : null }),
    card('مستوى التجمد', d.fzl == null ? NA : num(d.fzl), 'م فوق سطح البحر', { na: d.fzl == null, sub: d.fzlSource === 'interp' ? 'مستوفى من المستويات' : null }),
    card('ارتفاع الطبقة الحدية', d.blh == null ? NA : num(d.blh), d.blh == null ? '' : 'م', { na: d.blh == null }),
  );
  // --- dynamics
  const vvUnit = md.units['vertical_velocity_700hPa'] || '';
  const g4 = el('div', { class: 'cards' },
    card('الحركة الرأسية 700', ...vvParts(d.vv[700], vvUnit), { na: d.vv[700] == null, sub: /pa/i.test(vvUnit) ? 'أوميغا: السالب صعود' : 'الموجب صعود' }),
    card('الحركة الرأسية 500', ...vvParts(d.vv[500], vvUnit), { na: d.vv[500] == null }),
    card('رياح التوجيه 700–500', ...(d.steer ? windParts(d.steer.speed) : [NA, '']), { na: !d.steer, sub: d.steer ? `رياح ${dirName(d.steer.dirFrom)}؛ الخلايا تميل للحركة نحو ${towardName(d.steer.toward)}` : null }),
    card('القص 10 م – 500 hPa', ...(d.shear == null ? [NA, ''] : windParts(d.shear)), { na: d.shear == null, pill: d.shear == null ? null : d.shear >= th.shearOrg ? ['يسمح بالتنظيم', 'watch'] : ['ضعيف', 'ok'] }),
    ...[925, 850].map((p) => {
      const q = d.qflux[p];
      if (!q) return card(`تدفق الرطوبة ${p}`, 'تحت السطح', '', { na: true });
      const fromSea = q.dirFrom >= 180 && q.dirFrom <= 315;
      return card(`تدفق الرطوبة ${p} hPa`, num(q.flux), 'غ/كغ·م/ث', { sub: `q ${num(q.q, 1)} غ/كغ · رياح ${dirName(q.dirFrom)}`, pill: fromSea ? ['من جهة البحر', 'info'] : ['من الداخل', 'none'] });
    }),
  );
  // --- precipitation
  const g5 = el('div', { class: 'cards' },
    card('هطول الساعة', win(1) == null ? NA : num(win(1), 1), 'مم'),
    card('3 ساعات', win(3) == null ? NA : num(win(3), 1), 'مم'),
    card('6 ساعات', win(6) == null ? NA : num(win(6), 1), 'مم'),
    card('24 ساعة', win(24) == null ? NA : num(win(24), 1), 'مم', { sub: (() => { const seg = P.slice(i, i + 24); const f = seg.findIndex((v) => v >= 0.2); if (f < 0) return 'لا مطر ≥0.2 مم/س'; let l = f; for (let j = f; j < seg.length; j++) if (seg[j] >= 0.2) l = j; return `من ${fmtDayHour(md.hourly.time[i + f])} إلى ${fmtDayHour(md.hourly.time[i + l] + 3600000)}`; })() }),
  );
  const oroW = D.grad && s.ws != null ? (() => { const [u, v] = uv(s.ws, s.wd); return u * D.grad.dhdx + v * D.grad.dhdy; })() : null;
  host.append(
    section('الاستقرار', g1), section('الرطوبة', g2), section('السطح والسحب', g3),
    section('الرياح والحركة الرأسية', g4, oroW != null ? el('p', { class: 'meta' }, `رفع تضاريسي تقديري عند النقطة: ${num(oroW * 100)} سم/ث (رياح 10 م × ميل الأرض من DEM على مسافة 3 كم؛ موجب = صعود منحدر).`) : null),
    section('الهطول المتوقع (من الوقت المختار)', g5),
    basaltSection(md, i, pr),
  );

  // Levels table
  const tbl = el('table', { class: 'lv' }, el('thead', {}, el('tr', {}, ...['hPa', 'ارتفاع م', 'T°', 'Td°', 'RH٪', 'الرياح'].map((h) => el('th', {}, h)))));
  const tb = el('tbody');
  for (const L of pr.levels) {
    tb.append(el('tr', { class: L.under ? 'under' : '' },
      el('td', {}, String(L.p)), el('td', {}, num(L.z)), el('td', {}, num(L.tC, 1)), el('td', {}, num(L.tdC, 1)), el('td', {}, num(L.rh)),
      el('td', {}, L.under ? 'تحت السطح' : L.ws == null ? '—' : `${dirName(L.wd)} ${windText(L.ws)}`)));
  }
  tbl.append(tb);
  host.append(section('المقطع الرأسي عند النقطة', el('div', { class: 'tbl-wrap' }, tbl)));

  // Skew-T
  const sk = el('div', { class: 'chart skew' });
  host.append(section('مخطط Skew-T (من النموذج، ليس سبرًا مرصودًا)', sk, el('p', { class: 'meta' }, 'الأحمر الحرارة، والأخضر نقطة الندى، والمتقطع مسار جسيم سطحي. المنطقة الرمادية تحت سطح الأرض. السبر المرصود الحقيقي يأتي من محطة الرصد العلوي بجدة ولا يتوفر له مصدر مفتوح مباشر هنا.')));
  requestAnimationFrame(() => skewT(sk, { profile: pr, parcel: s.tC != null && s.tdC != null && s.p ? parcelPath(s.tC, s.tdC, s.p) : null, title: `${MODELS[k].label} · ${fmtDayHour(md.hourly.time[i])}` }));

  // Time-height
  const T = md.hourly.time; const now = Date.now();
  const k0 = Math.max(0, T.findIndex((t) => t >= now - 3 * 3600000));
  const times = T.slice(k0, k0 + 72);
  const profs = times.map((_, j) => buildProfile(md.hourly, k0 + j, LEVELS, elevation));
  const th1 = el('div', { class: 'chart' });
  host.append(section('تغير الرطوبة والرياح مع الزمن', th1, el('p', { class: 'meta' }, 'الألوان: الرطوبة النسبية (بني جاف ← أزرق رطب). الخط الأحمر: مستوى الصفر المئوي. الأسهم: اتجاه هبوب الرياح كل 3 ساعات. الرمادي: تحت السطح.')));
  requestAnimationFrame(() => timeHeight(th1, { times, profiles: profs, levels: LEVELS }));

  // Series: CAPE and precip from all models
  const capeHost = el('div', { class: 'chart' }), prHost = el('div', { class: 'chart' });
  host.append(section('CAPE في النماذج الثلاثة', capeHost), section('الهطول الساعي في النماذج الثلاثة', prHost));
  const aligned = (key, v) => { const m = D.models[key]; if (!m || !m.hourly[v]) return times.map(() => null); const ix = new Map(m.hourly.time.map((t, j) => [t, j])); return times.map((t) => (ix.has(t) ? m.hourly[v][ix.get(t)] : null)); };
  requestAnimationFrame(() => {
    timeSeries(capeHost, { times, unit: 'J/kg', series: MODEL_KEYS.map((m) => ({ label: MODELS[m].label, color: MODELS[m].color, values: aligned(m, 'cape') })) });
    timeSeries(prHost, { times, unit: 'مم', series: MODEL_KEYS.map((m) => ({ label: MODELS[m].label, color: MODELS[m].color, kind: 'bar', values: aligned(m, 'precipitation') })) });
  });

  // Cross-section
  host.append(sectionCross(k));

  // Sources per variable
  const srcList = el('details', { class: 'sources' }, el('summary', {}, 'مصدر كل متغير'),
    el('ul', {}, ...Object.entries(groupSources(md.sourceOf)).map(([src, vars]) => el('li', {}, el('b', {}, src), `: ${vars.length} متغيرًا`))),
    el('p', { class: 'meta' }, `متغيرات لم يُرجعها المصدر لهذا النموذج: ${POINT_VARS.filter((v) => !md.sourceOf[v]).join('، ') || 'لا شيء'}`));
  host.append(srcList);
}
function groupSources(sourceOf) { const g = {}; for (const [v, s] of Object.entries(sourceOf)) (g[s] = g[s] || []).push(v); return g; }
function section(title, ...kids) { return el('section', { class: 'block' }, el('h3', {}, title), ...kids); }

const SECTIONS = {
  jt: { label: 'جدة ← بحرة ← مكة ← الهدا ← الطائف', pts: [[21.543, 39.173], [21.27, 40.416], [21.20, 40.75]], marks: [['جدة', 21.543, 39.173], ['مكة', 21.4225, 39.8262], ['الهدا', 21.366, 40.281], ['الطائف', 21.27, 40.416]] },
  ls: { label: 'الليث ← الشفا ← تربة', pts: [[20.15, 40.27], [21.072, 40.355], [21.214, 41.633]], marks: [['الليث', 20.15, 40.27], ['الشفا', 21.072, 40.355], ['تربة', 21.214, 41.633]] },
  jm: { label: 'رابغ ← خليص ← الجموم ← مكة', pts: [[22.799, 39.035], [22.137, 39.33], [21.617, 39.698], [21.4225, 39.8262]], marks: [['رابغ', 22.799, 39.035], ['خليص', 22.137, 39.33], ['الجموم', 21.617, 39.698], ['مكة', 21.4225, 39.8262]] },
};
function sampleLine(pts, n) {
  const R = 6371, rad = Math.PI / 180;
  const seg = []; let total = 0;
  for (let j = 1; j < pts.length; j++) {
    const [a, b] = [pts[j - 1], pts[j]];
    const dx = (b[1] - a[1]) * Math.cos(((a[0] + b[0]) / 2) * rad) * R * rad, dy = (b[0] - a[0]) * R * rad;
    const len = Math.hypot(dx, dy); seg.push({ a, b, len, ex: dx / len, ey: dy / len }); total += len;
  }
  const out = [];
  for (let q = 0; q < n; q++) {
    let dist = (total * q) / (n - 1), acc = 0;
    for (const sg of seg) {
      if (dist <= acc + sg.len + 1e-9) { const f = (dist - acc) / sg.len; out.push({ lat: sg.a[0] + f * (sg.b[0] - sg.a[0]), lon: sg.a[1] + f * (sg.b[1] - sg.a[1]), d: dist, ex: sg.ex, ey: sg.ey }); break; }
      acc += sg.len;
    }
  }
  return { samples: out, total };
}
function sectionCross(k) {
  const sel = el('select', { id: 'xsecSel', 'aria-label': 'اختيار المقطع' }, ...Object.entries(SECTIONS).map(([id, s]) => el('option', { value: id }, s.label)));
  sel.value = store.get('xsec', 'jt');
  const host = el('div', { class: 'chart' });
  const msg = el('p', { class: 'meta' }, 'يجلب 12 عمودًا من النموذج و80 نقطة ارتفاع حقيقية. اضغط «ارسم المقطع».');
  const btn = el('button', { class: 'btn', onclick: async () => {
    store.set('xsec', sel.value); btn.disabled = true; msg.textContent = 'جارٍ الجلب…';
    try {
      const S = SECTIONS[sel.value];
      const cols = sampleLine(S.pts, 12), terr = sampleLine(S.pts, 80);
      const vars = LEVELS.flatMap((p) => [`temperature_${p}hPa`, `relative_humidity_${p}hPa`, `wind_speed_${p}hPa`, `wind_direction_${p}hPa`, `geopotential_height_${p}hPa`]).concat(['surface_pressure']);
      const [mr, dem] = await Promise.all([fetchMulti(k, cols.samples.map((c) => [c.lat, c.lon]), vars), fetchElevation(terr.samples.map((c) => [c.lat, c.lon]))]);
      const t = state.validTime;
      const colData = cols.samples.map((c, j) => {
        const b = mr.blocks[j]; const ix = b.hourly.time.reduce((best, tt, q) => (Math.abs(tt - t) < Math.abs(b.hourly.time[best] - t) ? q : best), 0);
        const pr = buildProfile(b.hourly, ix, LEVELS, null);
        return { d: c.d, levels: pr.levels.map((L) => ({ ...L, along: L.u == null ? null : L.u * c.ex + L.v * c.ey })) };
      });
      const marks = S.marks.map(([name, la, lo]) => { let best = terr.samples[0]; for (const s of terr.samples) if (Math.hypot(s.lat - la, s.lon - lo) < Math.hypot(best.lat - la, best.lon - lo)) best = s; return { name, d: best.d }; });
      crossSection(host, { dist: terr.samples.map((s) => s.d), terrain: dem, cols: colData, labels: marks });
      msg.textContent = `${MODELS[k].label} (${mr.id}) · ${fmtDateTime(t)} · الطول ${num(cols.total)} كم. الأسهم: مركبة الرياح على امتداد المقطع (يمين = نحو نهاية المقطع). التضاريس من Copernicus DEM، والنموذج يرى تضاريس أنعم بكثير.`;
    } catch (e) { msg.textContent = `تعذر رسم المقطع: ${e.reason || e.message}`; }
    btn.disabled = false;
  } }, 'ارسم المقطع');
  return section('مقطع عرضي عبر التضاريس', el('div', { class: 'row' }, sel, btn), host, msg);
}

// ---------------------------------------------------------------- model comparison
function renderModels() {
  const host = $('tab-models'); const D = state.data;
  if (!anyModel()) return emptyState(host, D.loading ? 'جارٍ تحميل النماذج…' : 'تعذر جلب النماذج.');
  host.innerHTML = '';
  host.append(el('div', { class: 'panel-head' }, el('h2', {}, `مقارنة النماذج · ${state.place.name}`), timeControl(renderModels)));
  const t = state.validTime;
  const rows = {};
  const runCards = el('div', { class: 'cards cards-3' });
  for (const k of MODEL_KEYS) {
    const md = D.models[k];
    if (!md) { runCards.append(card(MODELS[k].label, 'غير متاح', '', { na: true, sub: D.errors[k] || '' })); continue; }
    const i = idxFor(md, t); const pr = buildProfile(md.hourly, i, LEVELS, D.elev ?? md.elevation); const d = diagnostics(pr);
    const P = md.hourly.precipitation || [];
    rows[k] = {
      t2: pr.sfc.tC, td2: pr.sfc.tdC, ws: pr.sfc.ws, wd: pr.sfc.wd, cape: d.cape, cin: d.cin == null ? null : Math.abs(d.cin), li: d.li, pw: d.pw,
      rh850: d.rh[850], rh700: d.rh[700], rh500: d.rh[500], t500: d.t500, steer: d.steer, p6: P.length ? sum(P.slice(i, i + 6)) : null, p24: P.length ? sum(P.slice(i, i + 24)) : null,
    };
    runCards.append(el('div', { class: 'card model-card', style: `--mc:${MODELS[k].color}` },
      el('div', { class: 'card-label' }, MODELS[k].label),
      el('div', { class: 'card-sub' }, runInfo(k, t)),
      el('div', { class: 'card-sub' }, `المعرّف: ${md.ids.join(' + ')}`),
      el('div', { class: 'card-sub' }, `جُلب ${ago(md.fetchedAt)}${md.stale ? ' (نسخة مخزنة)' : ''}`)));
  }
  host.append(section('آخر تشغيل وزمن التوقع', runCards));

  const VARS = [
    ['t2', 'حرارة 2 م', '°م', 1, 2], ['td2', 'نقطة الندى 2 م', '°م', 1, 3], ['ws', 'رياح 10 م', 'wind', 0, 3], ['cape', 'CAPE', 'J/kg', 0, null],
    ['cin', 'CIN (مطلق)', 'J/kg', 0, null], ['li', 'Lifted Index', '', 1, 2], ['pw', 'ماء قابل للهطول', 'مم', 0, 5], ['rh850', 'رطوبة 850', '٪', 0, 15],
    ['rh700', 'رطوبة 700', '٪', 0, 15], ['rh500', 'رطوبة 500', '٪', 0, 15], ['t500', 'حرارة 500', '°م', 1, 1.5], ['p6', 'مطر 6 ساعات', 'مم', 1, null], ['p24', 'مطر 24 ساعة', 'مم', 1, null],
  ];
  const list = el('div', { class: 'cmp' });
  for (const [key, label, unit, dg, tol] of VARS) {
    const vals = MODEL_KEYS.map((k) => (rows[k] ? rows[k][key] : null));
    const have = vals.filter((v) => v != null);
    let agree = null;
    if (have.length >= 2) {
      const spread = Math.max(...have) - Math.min(...have);
      if (key === 'cape') agree = spread < 300 + 0.5 * Math.min(...have);
      else if (key === 'cin') agree = spread < 50;
      else if (key === 'p6' || key === 'p24') { const yes = have.filter((v) => v >= state.th.rainAgree).length; agree = yes === 0 || yes === have.length; }
      else if (key === 'ws') agree = spread < 3;
      else agree = spread <= tol;
    }
    list.append(el('div', { class: 'cmp-row' },
      el('div', { class: 'cmp-label' }, label, agree == null ? null : pill(agree ? 'متفقة' : 'مختلفة', agree ? 'ok' : 'watch')),
      el('div', { class: 'cmp-vals' }, ...MODEL_KEYS.map((k, j) => el('div', { class: 'cmp-v', style: `--mc:${MODELS[k].color}` },
        el('span', { class: 'cmp-m' }, MODELS[k].label.split(' ')[0]),
        el('b', {}, vals[j] == null ? '—' : unit === 'wind' ? windText(vals[j]) : `${num(vals[j], dg)}${unit ? ' ' + unit : ''}`))))));
  }
  host.append(section(`أين تتفق النماذج وأين تختلف · ${fmtDateTime(t)}`, list));

  // Possible explanations (interpretation)
  const ex = [];
  const r = (k, f) => (rows[k] ? rows[k][f] : null);
  const capes = MODEL_KEYS.map((k) => r(k, 'cape')).filter((v) => v != null);
  if (capes.length >= 2 && Math.max(...capes) > 2 * Math.min(...capes) + 300) ex.push('فرق CAPE الكبير يأتي غالبًا من اختلاف حرارة ورطوبة الطبقة الحدية وقت الذروة، ومن اختلاف تعريف CAPE نفسه بين المراكز (جسيم سطحي، أو مختلط، أو الأكثر عدم استقرار).');
  const p24 = MODEL_KEYS.map((k) => r(k, 'p24'));
  if (r('ecmwf', 'p24') != null && r('ecmwf', 'p24') > 0 && r('ecmwf', 'p24') < 1 && p24.filter((v) => v === 0).length) ex.push('مطر ECMWF الخفيف (أقل من 1 مم) قد يعكس ميلًا موثقًا من ECMWF نفسه لتوقع مطر خفيف أكثر من الواقع؛ لا يكفي وحده دليلًا على حالة مطرية.');
  if (p24.some((v) => v != null && v >= state.th.rainAgree) && p24.some((v) => v != null && v < 0.2)) ex.push('اختلاف المطر مع تقارب الرطوبة يشير إلى اختلاف شروط إطلاق الحمل المعلمَن بين النماذج، وهذا ضعف مشترك في النماذج العالمية فوق تضاريس الحجاز.');
  const rh7 = MODEL_KEYS.map((k) => r(k, 'rh700')).filter((v) => v != null);
  if (rh7.length >= 2 && Math.max(...rh7) - Math.min(...rh7) > 25) ex.push('فرق رطوبة 700 hPa كبير: قد يأتي من اختلاف التحليل الأولي للرطوبة فوق منطقة قليلة الرصد العلوي؛ قارنه بصورة بخار الماء والرصد العلوي لجدة.');
  ex.push('GFS يعرض المستويات الضغطية على شبكة 0.25° وECMWF على 0.25° (المفتوحة)، بينما الحقول السطحية أدق؛ لذلك قد تختلف القيم العليا والسطحية في دقتها داخل النموذج نفسه.');
  host.append(section('تفسير محتمل للاختلافات (تفسير، وليس حقيقة مرصودة)', el('ul', { class: 'bullets' }, ...ex.map((x) => el('li', {}, x)))));

  // Time series
  const md0 = anyModel(); const now = Date.now();
  const k0 = Math.max(0, md0.hourly.time.findIndex((tt) => tt >= now - 3 * 3600000));
  const times = md0.hourly.time.slice(k0, k0 + 72);
  const aligned = (k, v, f) => { const m = D.models[k]; if (!m || !m.hourly[v]) return times.map(() => null); const ix = new Map(m.hourly.time.map((tt, j) => [tt, j])); return times.map((tt) => (ix.has(tt) ? (f ? f(m.hourly[v][ix.get(tt)]) : m.hourly[v][ix.get(tt)]) : null)); };
  const charts = [
    ['الهطول الساعي', 'مم', 'precipitation', 'bar'], ['CAPE', 'J/kg', 'cape'], ['الرطوبة النسبية 700 hPa', '٪', 'relative_humidity_700hPa'], ['حرارة 2 م', '°م', 'temperature_2m', null, false],
  ];
  for (const [title, unit, v, kind, zero] of charts) {
    const h = el('div', { class: 'chart' }); host.append(section(title, h));
    requestAnimationFrame(() => timeSeries(h, { times, unit, zeroBase: zero !== false, series: MODEL_KEYS.map((k) => ({ label: MODELS[k].label, color: MODELS[k].color, kind, values: aligned(k, v) })) }));
  }

  // Ensembles
  const ensBox = el('div', { class: 'ens' });
  for (const k of MODEL_KEYS) {
    const e = D.ens[k];
    if (!e) { ensBox.append(el('div', { class: 'ens-row' }, el('b', {}, MODELS[k].ensLabel), el('span', { class: 'na' }, D.ensErrors[k] ? `غير متاح: ${D.ensErrors[k]}` : 'جارٍ التحميل…'))); continue; }
    const cells = [[6, 1], [24, 1], [24, 5], [24, 10]].map(([h, mm]) => {
      const p = ensembleProbFrom(e, mm, h, t);
      return el('div', { class: 'prob' }, el('span', {}, `≥${mm} مم/${h}س`), el('div', { class: 'bar' }, el('i', { style: `width:${Math.round((p ?? 0) * 100)}%` })), el('b', {}, p == null ? '—' : `${Math.round(p * 100)}٪`));
    });
    ensBox.append(el('div', { class: 'ens-row' }, el('b', {}, e.label), el('span', { class: 'card-sub' }, `عدد الأعضاء: ${num(e.members.length)} · المعرّف: ${e.id}`), ...cells));
  }
  host.append(section('احتمالات المجموعات من الوقت المختار', ensBox, el('p', { class: 'meta' }, 'نسبة الأعضاء التي يتجاوز مجموعها العتبة عند النقطة. المجموعات أخشن من النماذج الحتمية (25–26 كم).')));

  host.append(section('الاختلاف المكاني', el('p', {}, 'اعرض على الخريطة عدد النماذج التي تتوقع مطرًا في كل خلية.'), el('button', { class: 'btn', onclick: () => { state.mapUI.field = 'agree'; state.mapUI.win = 24; showTab('map'); refreshField(); } }, 'خريطة اتفاق النماذج')));
}
function ensembleProbFrom(e, mm, hours, t0) {
  let i0 = e.times.findIndex((t) => t >= t0 - 1800000); if (i0 < 0) return null;
  const i1 = Math.min(e.times.length, i0 + hours); let yes = 0;
  for (const m of e.members) { let s = 0; for (let i = i0; i < i1; i++) s += m[i] || 0; if (s >= mm) yes++; }
  return e.members.length ? yes / e.members.length : null;
}

// ---------------------------------------------------------------- analysis
async function loadMetarsOnce() {
  if (state.metars !== null) return;
  state.metars = [];
  try {
    const r = await fetchMetars(METAR_STATIONS.map((s) => s.icao));
    state.metars = r.list.map((m) => ({ ...m, name: (METAR_STATIONS.find((s) => s.icao === m.icaoId) || {}).name || m.icaoId, timeText: m.obsTime ? fmtTime(m.obsTime * 1000) : '' }));
  } catch { state.metars = []; }
  if (state.tab === 'analysis') renderAnalysis();
}
function renderAnalysis() {
  const host = $('tab-analysis'); const D = state.data;
  if (!anyModel()) return emptyState(host, D.loading ? 'جارٍ تحميل النماذج…' : 'تعذر جلب النماذج.');
  loadMetarsOnce();
  host.innerHTML = '';
  const md = anyModel();
  let oro = null;
  if (D.grad) {
    const ws = MODEL_KEYS.map((k) => D.models[k]).filter(Boolean).map((m) => { const i = idxFor(m, Date.now() + 6 * 3600000); return uv(m.hourly.wind_speed_10m && m.hourly.wind_speed_10m[i], m.hourly.wind_direction_10m && m.hourly.wind_direction_10m[i]); }).filter((x) => x[0] != null);
    if (ws.length) { const u = ws.reduce((a, b) => a + b[0], 0) / ws.length, v = ws.reduce((a, b) => a + b[1], 0) / ws.length; oro = { w: u * D.grad.dhdx + v * D.grad.dhdy }; }
  }
  const sat = wxmap && Object.values(wxmap.satTimes).find(Boolean);
  const A = buildAnalysis({ place: state.place, modelData: D.models, ens: D.ens, oro, obs: { metars: state.metars, sat: sat && sat.latest ? fmtDateTime(sat.latest) : null }, th: state.th });
  const lvl = { high: 'alert', mid: 'watch', low: 'info', none: 'ok', unknown: 'none' }[A.verdict.level];
  host.append(el('div', { class: 'panel-head' }, el('h2', {}, `تحليل الحالة · ${state.place.name}`), el('p', { class: 'meta' }, `الـ24 ساعة القادمة · ${fmtDateTime(Date.now())}`)));
  host.append(el('div', { class: `verdict v-${lvl}` }, el('b', {}, A.verdict.text), el('span', {}, `درجة الثقة: ${A.confidence}`)));
  host.append(section('١. الرصد — ما يحدث الآن', el('ul', { class: 'bullets' }, ...A.obs.map((x) => el('li', {}, x)))));
  host.append(section('٢. التوقع — ما تقوله النماذج', el('ul', { class: 'bullets' }, ...A.forecast.map((x) => el('li', {}, x)))));
  host.append(section('٣. التفسير — تحليل احتمالي، وليس رصدًا', el('dl', { class: 'qa' }, ...A.interp.flatMap((x) => [el('dt', {}, x.q), el('dd', {}, x.a)]))));
  host.append(section('مصادر عدم اليقين', el('ul', { class: 'bullets' }, ...A.uncertainties.map((x) => el('li', {}, x)))));
  const prof = PROFILES[state.place.id] || DEFAULT_PROFILE;
  host.append(section(`ملف المنطقة · ${state.place.name}`,
    el('p', {}, `الارتفاع: ${D.elev != null ? `${num(D.elev)} م فوق سطح البحر (Copernicus DEM 90 م)` : 'غير متاح الآن'} · الإحداثيات ${state.place.lat.toFixed(3)}°ش، ${state.place.lon.toFixed(3)}°ق`),
    el('p', {}, prof.terrain), el('ul', { class: 'bullets' }, ...prof.factors.map((f) => el('li', {}, f))),
    el('p', { class: 'meta' }, 'الوصف التضاريسي نص ثابت معدّ مسبقًا، وليس بيانات مقيسة.')));
  host.append(el('p', { class: 'meta' }, 'العتبات المستخدمة أولية لبيئة جافة وقاعدة سحاب مرتفعة، ويمكن تعديلها من «المزيد ← الإعدادات».'));
}

function showEscarpBoxes() {
  showTab('map');
  if (wxmap) { wxmap.setBase('sat'); wxmap.showBoxes(escarpBoxes(), ESCARP.crests); }
}

// ---------------------------------------------------------------- basalt correction at a point
function inHarrat(p) { const b = ESCARP.boxes.harrat; return p.lat >= b.lat0 && p.lat <= b.lat1 && p.lon >= b.lon0 && p.lon <= b.lon1; }
function basaltOn() { const o = store.get('basalt', {}); const k = placeKey(state.place); return k in o ? o[k] : inHarrat(state.place); }
function basaltSection(md, i, pr) {
  const on = basaltOn();
  const toggle = el('label', { class: 'opt' }, el('input', { type: 'checkbox', checked: on ? 'checked' : null, onchange: (e) => { const o = store.get('basalt', {}); o[placeKey(state.place)] = e.target.checked; store.set('basalt', o); renderConv(); } }), el('span', {}, 'سطح بازلتي داكن (حرة) عند هذه النقطة', el('small', {}, inHarrat(state.place) ? 'النقطة داخل نطاق حرة رهط التقريبي' : 'فعّله إذا كانت النقطة على حرة، مثل حرة كشب')));
  if (!on) return section('تصحيح تسخين البازلت', toggle);
  const eth = { ...ESCARP_DEFAULTS, ...store.get('eth', {}) };
  const sw = md.hourly.shortwave_radiation;
  if (!sw) return section('تصحيح تسخين البازلت', toggle, el('p', { class: 'na' }, 'الإشعاع الشمسي غير متاح من هذا النموذج.'));
  const hrs = md.hourly.time.map(riyadhHourLocal);
  const warm = basaltWarming(sw, md.hourly.boundary_layer_height || null, hrs, eth)[i];
  const s = pr.sfc;
  const blhI = md.hourly.boundary_layer_height ? md.hourly.boundary_layer_height[i] : null;
  const mlTopP = mlTop(s.p, blhI);
  const wp = warmProfile(pr, warm, blhI);
  const base = parcelCapeCin(s, pr.levels, { mlTopP }), adj = wp ? parcelCapeCin(wp.sfc, wp.levels, { mlTopP }) : null;
  const tc = convectiveTemp(s, pr.levels, 15, { mlTopP });
  return section('تصحيح تسخين البازلت', toggle, el('div', { class: 'cards' },
    card('تسخين إضافي', warm == null ? NA : `+${num(warm, 1)}`, '°م', { sub: 'فوق ما يحسبه النموذج، عند الوقت المختار' }),
    card('حرارة الحمل المطلوبة', tc == null ? NA : num(tc, 1), '°م', { sub: s.tC != null ? `النموذج ${num(s.tC, 1)}° · مع البازلت ${num(s.tC + (warm || 0), 1)}°` : null, pill: tc == null || s.tC == null ? null : s.tC + (warm || 0) >= tc ? ['تُبلغ', 'alert'] : ['لا تُبلغ', 'ok'] }),
    card('CAPE حسابنا', base ? num(base.cape) : NA, 'J/kg', { sub: adj ? `مع البازلت ${num(adj.cape)}` : null }),
    card('CIN حسابنا', base ? num(Math.abs(base.cin)) : NA, 'J/kg', { sub: adj ? `مع البازلت ${num(Math.abs(adj.cin))}` : null })),
    el('p', { class: 'meta' }, 'تقدير طاقي مبسط لفرق الألبيدو بين البازلت وما يفترضه النموذج، وليس إعادة تشغيل للنموذج. المعاملات قابلة للتعديل من تبويب «الجرف».'));
}
function riyadhHourLocal(t) { return Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Riyadh', hour: '2-digit', hour12: false }).format(t)) % 24; }

// ---------------------------------------------------------------- map tab
function ensureMap() {
  if (wxmap) return;
  if (!window.L) { $('map').innerHTML = '<p class="warn">تعذر تحميل مكتبة الخريطة. تحقق من الاتصال ثم حدّث الصفحة.</p>'; return; }
  wxmap = new WxMap($('map'), { onPick: onMapPick });
}
function onMapPick(p, info) {
  if (!info || !info.fromMap) { selectPlace(p); toast(`تم اختيار ${p.name}`); return; }
  const v = wxmap.valueAt(p.lat, p.lon);
  const f = state.mapUI.field ? FIELDS[state.mapUI.field] : null;
  let val = '';
  if (v && f) {
    if (v.v != null) val = `<div>${f.label}: <b>${num(v.v * (state.mapUI.field === 'conv' ? 1e5 : state.mapUI.field === 'oro' ? 100 : 1), 1)}</b> ${f.unit}</div>`;
    else if (v.a) val = `<div>${f.label}: <b>${num(v.a.s * (state.mapUI.field === 'qflux' ? 1 : 3.6))}</b> ${f.unit} ${dirName(v.a.d)}</div>`;
  }
  const html = `<div class="pop"><b>${p.lat.toFixed(3)}°ش ${p.lon.toFixed(3)}°ق</b>${val}<button class="btn" id="popGo">حلّل هذه النقطة</button><button class="btn ghost" id="popSave">احفظها</button></div>`;
  wxmap.popup(info.latlng, html);
  setTimeout(() => {
    const go = document.getElementById('popGo'), sv = document.getElementById('popSave');
    if (go) go.onclick = () => { selectPlace(p); showTab('conv'); };
    if (sv) sv.onclick = () => { const id = `c${Date.now()}`; state.customs.push({ ...p, id, custom: true }); store.set('customs', state.customs); toast('حُفظت النقطة في قائمة المواقع'); };
  }, 0);
}

function openLayers() {
  ensureMap(); if (!wxmap) return;
  const ui = state.mapUI;
  const body = el('div', { class: 'sheet-body layers' });
  const radio = (name, value, label, checked, on) => el('label', { class: 'opt' }, el('input', { type: 'radio', name, value, checked: checked ? 'checked' : null, onchange: on }), el('span', {}, label));
  const check = (label, checked, on, note) => el('label', { class: 'opt' }, el('input', { type: 'checkbox', checked: checked ? 'checked' : null, onchange: (e) => on(e.target.checked) }), el('span', {}, label, note ? el('small', {}, note) : null));

  body.append(el('h3', {}, 'الخريطة الأساسية'), ...Object.entries(BASES).map(([k, b]) => radio('base', k, b.label, wxmap.base === k, () => wxmap.setBase(k))));
  body.append(el('h3', {}, 'طبقات مرجعية'),
    check('الحدود الإدارية والأسماء (Esri)', !!ui.obs.ref, (on) => { ui.obs.ref = on; wxmap.toggleOverlay('ref', on); }, 'حدود تقريبية لأغراض العرض، وليست حدودًا رسمية'),
    check('ظل التضاريس فوق الخريطة', !!ui.obs.shade, (on) => { ui.obs.shade = on; wxmap.toggleOverlay('shade', on); }),
    check('المحافظات والمواقع المختارة', ui.obs.places !== false, (on) => { ui.obs.places = on; wxmap.toggleOverlay('places', on); }),
    check('تسميات الحرات والجرف', !!ui.obs.labels, (on) => { ui.obs.labels = on; wxmap.toggleOverlay('labels', on); }, 'مواضع تقريبية للأسماء فقط؛ الامتداد الحقيقي للحرات يظهر داكنًا في خريطة القمر الصناعي، والأودية تظهر في خريطة التضاريس'));

  body.append(el('h3', {}, 'الرصد (ما حدث فعلًا)'));
  for (const [k, def] of Object.entries(SAT_LAYERS)) {
    body.append(check(def.label, !!ui.obs[k], async (on) => {
      ui.obs[k] = on;
      try { const t = await wxmap.toggleSat(k, on); ui.obs[`${k}Time`] = t; renderMapBars(); if (on && !t) toast('الطبقة تعمل، لكن تعذر التحقق من وقت آخر صورة.'); }
      catch { toast('تعذر تحميل الطبقة'); }
    }));
  }
  body.append(check('رادار الأمطار (RainViewer، آخر ساعتين)', !!ui.obs.radar, async (on) => {
    ui.obs.radar = on;
    try { ui.obs.radarTime = await wxmap.toggleRadar(on, { coverage: true }); renderMapBars(); }
    catch (e) { ui.obs.radar = false; toast(`الرادار غير متاح: ${e.message}`); }
  }, 'الطبقة الداكنة الخفيفة تعني عدم وجود تغطية رادارية'));
  body.append(check('أرصاد المطارات METAR', !!ui.obs.metar, async (on) => {
    ui.obs.metar = on;
    try { const l = await wxmap.toggleMetar(on); if (on && !l.length) toast('لا توجد أرصاد حديثة.'); }
    catch { ui.obs.metar = false; toast('تعذر جلب أرصاد المطارات من المتصفح'); }
  }));

  body.append(el('h3', {}, 'التوقع (من النماذج)'));
  const modelSel = el('select', { 'aria-label': 'النموذج', onchange: (e) => { ui.model = e.target.value; refreshField(); } }, ...MODEL_KEYS.map((k) => el('option', { value: k, selected: ui.model === k ? 'selected' : null }, MODELS[k].label)));
  const gridSel = el('select', { 'aria-label': 'النطاق', onchange: (e) => { ui.grid = e.target.value; refreshField(); } }, ...Object.entries(GRIDS).map(([k, g]) => el('option', { value: k, selected: ui.grid === k ? 'selected' : null }, g.label)));
  body.append(el('div', { class: 'row' }, modelSel, gridSel));
  body.append(radio('field', '', 'بلا حقل توقع', !ui.field, () => { ui.field = null; wxmap.clearField(); renderMapBars(); closeSheet(); }));
  for (const [k, f] of Object.entries(FIELDS)) body.append(radio('field', k, f.label, ui.field === k, () => { ui.field = k; if ((k === 'precip' || k === 'agree') && !ui.win) ui.win = 3; closeSheet(); refreshField(); }));
  body.append(el('p', { class: 'hint' }, 'حقول التوقع شبكة نقاط من النموذج (0.2° أو 0.5°)، وتُحمّل عند اختيارها فقط لتوفير البيانات.'));
  openSheet('طبقات الخريطة', body);
}

async function refreshField() {
  ensureMap(); if (!wxmap) return;
  const ui = state.mapUI; renderMapBars();
  if (!ui.field) { wxmap.clearField(); return; }
  $('mapBusy').hidden = false;
  try {
    const G = await wxmap.loadGrid(ui.grid, ui.field === 'agree' ? 'ecmwf' : ui.model);
    if (ui.ti == null || ui.ti >= G.times.length) { ui.ti = Math.max(0, G.times.findIndex((t) => t >= Date.now() - 1800000)); }
    ui.times = G.times;
    const res = await wxmap.computeField(ui.field, ui.grid, ui.model, ui.ti, ui.win || 3, state.th);
    wxmap.drawField(ui.field, res, state.th);
    ui.note = res.note; ui.srcId = res.G.id; ui.fetchedAt = res.G.fetchedAt;
  } catch (e) { toast(`تعذر تحميل الحقل: ${e.reason || e.message}`); ui.note = ''; }
  $('mapBusy').hidden = true;
  renderMapBars();
}

function renderMapBars() {
  const ui = state.mapUI; const box = $('mapBars'); if (!box) return; box.innerHTML = '';
  // observation strip
  const obsBits = [];
  for (const k of Object.keys(SAT_LAYERS)) if (ui.obs[k]) { const t = ui.obs[`${k}Time`]; obsBits.push(`${SAT_LAYERS[k].label.split('–')[0].trim()}: ${t && t.latest ? `${fmtTime(t.latest)} (${ago(t.latest)})` : 'آخر صورة لدى المصدر'}`); }
  if (ui.obs.radar && ui.obs.radarTime) obsBits.push(`رادار: ${fmtTime(ui.obs.radarTime)}`);
  if (obsBits.length) {
    const bar = el('div', { class: 'mbar obs' }, el('span', { class: 'tag tag-obs' }, 'رصد'), el('span', { class: 'mtxt' }, obsBits.join(' · ')));
    if (ui.obs.radar) bar.append(
      el('button', { class: 'icon-btn', 'aria-label': 'إطار رادار سابق', onclick: () => { ui.obs.radarTime = wxmap.stepRadar(-1); renderMapBars(); } }, '›'),
      el('button', { class: 'icon-btn', 'aria-label': 'تشغيل الرادار', onclick: () => { wxmap.playRadar((t) => { ui.obs.radarTime = t; const n = document.querySelector('.mbar.obs .mtxt'); if (n) n.textContent = `رادار: ${fmtTime(t)}`; }); } }, '▶'),
      el('button', { class: 'icon-btn', 'aria-label': 'إطار رادار لاحق', onclick: () => { ui.obs.radarTime = wxmap.stepRadar(1); renderMapBars(); } }, '‹'));
    box.append(bar);
  }
  if (ui.field && ui.times) {
    const f = FIELDS[ui.field];
    const label = el('output', { class: 'mtxt' }, fmtDateTime(ui.times[ui.ti]));
    const rng = el('input', { type: 'range', min: 0, max: ui.times.length - 1, value: ui.ti, 'aria-label': 'وقت الحقل' });
    rng.addEventListener('input', () => { label.textContent = fmtDateTime(ui.times[+rng.value]); });
    rng.addEventListener('change', () => { ui.ti = +rng.value; refreshField(); });
    const bar = el('div', { class: 'mbar fc' },
      el('div', { class: 'mrow' }, el('span', { class: 'tag tag-fc' }, 'توقع'), el('b', {}, f.label), el('span', { class: 'mtxt' }, ui.field === 'agree' ? 'كل النماذج' : `${MODELS[ui.model].label}${ui.srcId ? ` (${ui.srcId})` : ''}`)),
      el('div', { class: 'mrow' }, label, rng));
    if (ui.field === 'precip' || ui.field === 'agree') {
      bar.append(el('div', { class: 'mrow chips' }, ...[1, 3, 6, 24].map((h) => el('button', { class: `chip${ui.win === h ? ' on' : ''}`, onclick: () => { ui.win = h; refreshField(); } }, `${h} س`))));
    }
    const lg = LEGENDS[ui.field] || [];
    bar.append(el('div', { class: 'legend' }, ...lg.map(([c, t]) => el('span', { class: 'lg' }, el('i', { style: `background:${c}` }), t)), f.unit ? el('span', { class: 'lg' }, `(${f.unit})`) : null));
    if (ui.note) bar.append(el('div', { class: 'mnote' }, ui.note));
    box.append(bar);
  }
}

// ---------------------------------------------------------------- more: settings, verification, sources, WRF
function renderMore() {
  const host = $('tab-more'); host.innerHTML = '';
  host.append(el('div', { class: 'panel-head' }, el('h2', {}, 'المزيد')));
  // settings
  const s = state.settings;
  const sel = (label, key, opts) => el('label', { class: 'field' }, el('span', {}, label), el('select', { onchange: (e) => { s[key] = e.target.value; store.set('settings', s); if (key === 'theme') applyTheme(); renderActive(); } }, ...opts.map(([v, t]) => el('option', { value: v, selected: s[key] === v ? 'selected' : null }, t))));
  const thInputs = Object.entries({
    pwLow: 'ماء قابل للهطول: حد أدنى (مم)', pwHigh: 'ماء قابل للهطول: مرتفع (مم)', rh700Moist: 'رطوبة 700 رطبة (٪)', rh700Dry: 'رطوبة 700 جافة (٪)', ddDry: 'T−Td جاف عند 700/500 (°م)',
    capeWeak: 'CAPE متوسط من (J/kg)', capeStrong: 'CAPE قوي من (J/kg)', cinCap: 'CIN غطاء قوي من (J/kg)', liUnstable: 'LI غير مستقر حتى', lapseSteep: 'تناقص حاد من (°م/كم)', shearOrg: 'قص منظم من (م/ث)', lclHigh: 'LCL مرتفع من (م)', rainAgree: 'عتبة «النموذج يتوقع مطرًا» (مم/24س)',
  }).map(([k, label]) => el('label', { class: 'field' }, el('span', {}, label), el('input', { type: 'number', inputmode: 'decimal', step: 'any', value: state.th[k], id: `th-${k}`, onchange: (e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) { state.th[k] = v; store.set('th', state.th); } } })));
  host.append(section('الإعدادات',
    sel('المظهر', 'theme', [['auto', 'حسب الجهاز'], ['light', 'فاتح'], ['dark', 'ليلي']]),
    sel('وحدة الرياح', 'wind', [['kmh', 'كم/س'], ['kt', 'عقدة'], ['ms', 'م/ث']]),
    el('details', {}, el('summary', {}, 'عتبات التحليل الآلي'), ...thInputs, el('button', { class: 'btn ghost', onclick: () => { state.th = { ...DEFAULT_THRESHOLDS }; store.set('th', state.th); renderMore(); toast('أعيدت العتبات الافتراضية'); } }, 'استعادة الافتراضي'))));

  host.append(renderVerification());
  host.append(renderSources());
  host.append(renderWrf());
  host.append(section('تثبيت الموقع كتطبيق',
    el('p', {}, 'آيفون: افتح الموقع في Safari ← زر المشاركة ← «إضافة إلى الشاشة الرئيسية».'),
    el('p', {}, 'أندرويد: افتح القائمة ⋮ في Chrome ← «تثبيت التطبيق» أو «إضافة إلى الشاشة الرئيسية».'),
    installBtn ? el('button', { class: 'btn', onclick: async () => { installBtn.prompt(); installBtn = null; } }, 'تثبيت الآن') : null));
}

function renderVerification() {
  const log = store.get('verify', []);
  const date = el('input', { type: 'date', id: 'vDate', value: new Date(Date.now() - 86400000).toISOString().slice(0, 10) });
  const amt = el('input', { type: 'number', id: 'vAmt', inputmode: 'decimal', step: '0.1', min: '0', placeholder: 'مم' });
  const result = el('div', { id: 'vResult' });
  const add = el('button', { class: 'btn', onclick: () => {
    const v = parseFloat(amt.value); if (!date.value || Number.isNaN(v)) { toast('أدخل التاريخ وكمية المطر المرصودة (0 إن لم يمطر)'); return; }
    log.push({ id: Date.now(), date: date.value, place: state.place.name, lat: state.place.lat, lon: state.place.lon, obs: v });
    store.set('verify', log); renderMore();
  } }, 'إضافة');
  const list = el('ul', { class: 'vlist' }, ...log.slice().reverse().map((e) => el('li', {}, `${e.date} · ${e.place} · رُصد ${e.obs} مم`, el('button', { class: 'icon-btn', 'aria-label': 'حذف', onclick: () => { store.set('verify', log.filter((x) => x.id !== e.id)); renderMore(); } }, '✕'))));
  const run = el('button', { class: 'btn ghost', onclick: async () => {
    if (!log.length) { toast('أضف حالات أولًا'); return; }
    result.textContent = 'جارٍ جلب توقعات اليوم السابق لكل حالة…';
    const thr = state.th.rainAgree; const stats = {};
    for (const k of MODEL_KEYS) stats[k] = { a: 0, b: 0, c: 0, d: 0, n: 0, err: null };
    for (const e of log) {
      for (const k of MODEL_KEYS) {
        try {
          const r = await fetchPreviousDay1(k, e.lat, e.lon, e.date, e.date);
          const f = sum(r.precip); if (f == null) continue;
          const fy = f >= thr, oy = e.obs >= thr; const S = stats[k]; S.n++;
          if (fy && oy) S.a++; else if (fy && !oy) S.b++; else if (!fy && oy) S.c++; else S.d++;
        } catch (err) { stats[k].err = err.reason || err.message; }
      }
    }
    result.innerHTML = '';
    for (const k of MODEL_KEYS) {
      const S = stats[k];
      const pod = S.a + S.c ? S.a / (S.a + S.c) : null, far = S.a + S.b ? S.b / (S.a + S.b) : null, csi = S.a + S.b + S.c ? S.a / (S.a + S.b + S.c) : null;
      result.append(el('div', { class: 'vrow' }, el('b', {}, MODELS[k].label), el('span', {}, S.n ? `حالات ${S.n} · إصابة ${S.a} · إنذار كاذب ${S.b} · فائت ${S.c} · نفي صحيح ${S.d} · POD ${pod == null ? '—' : num(pod, 2)} · FAR ${far == null ? '—' : num(far, 2)} · CSI ${csi == null ? '—' : num(csi, 2)}` : `لا نتائج${S.err ? `: ${S.err}` : ''}`)));
    }
    result.append(el('p', { class: 'meta' }, `التوقع المستخدم: توقع اليوم السابق (مهلة يوم واحد) من أرشيف Open-Meteo، مجموع 24 ساعة بتوقيت مكة، والعتبة ${thr} مم. أقل من 30 حالة لا تكفي لحكم موثوق.`));
  } }, 'احسب الإحصاءات');
  return section('سجل التحقق من النماذج',
    el('p', {}, `سجّل المطر المرصود في الموقع المختار حاليًا (${state.place.name}) ليوم مضى، ثم احسب كيف أدى كل نموذج في توقع اليوم السابق.`),
    el('div', { class: 'row' }, date, amt, add), list, run, result);
}

function renderSources() {
  const S = [
    ['النماذج العددية', 'Open-Meteo Forecast API: ECMWF IFS (HRES 9 كم للسطح، و0.25° للمستويات الضغطية)، GFS (0.11° للسطح، و0.25° للمستويات)، ICON العالمي (نحو 13 كم). البيانات بترخيص CC-BY 4.0، والاستخدام المجاني لغير الأغراض التجارية بحدود 10,000 طلب يوميًا.', 'https://open-meteo.com/en/docs'],
    ['المجموعات', 'Open-Meteo Ensemble API: ECMWF ENS، وGEFS، وICON-EPS.', 'https://open-meteo.com/en/docs/ensemble-api'],
    ['الارتفاعات', 'Open-Meteo Elevation API، نموذج Copernicus DEM بدقة 90 م. يُستخدم لارتفاع النقاط ومقطع التضاريس والرفع التضاريسي.', 'https://open-meteo.com/en/docs/elevation-api'],
    ['أرشيف التوقعات', 'Open-Meteo Previous Runs API (توقع اليوم السابق) لسجل التحقق.', 'https://open-meteo.com/en/docs/previous-runs-api'],
    ['الأقمار الصناعية والبرق', 'EUMETSAT EUMETView (WMS): Meteosat فوق المحيط الهندي (IR 10.8، ارتفاع قمم السحب)، وMTG عند 0° (IR 10.5، وLightning Imager).', 'https://view.eumetsat.int'],
    ['الرادار', 'RainViewer: إطارات الساعتين الماضيتين للاستخدام الشخصي، بحد تكبير 7، وطبقة التغطية. التغطية فوق المملكة تعتمد على المحطات المشاركة وقد تكون معدومة.', 'https://www.rainviewer.com/api.html'],
    ['أرصاد المطارات', 'aviationweather.gov Data API (METAR). قد يمنع المصدر الطلب من المتصفح.', 'https://aviationweather.gov/data/api/'],
    ['الخرائط الأساسية', 'OpenTopoMap (تضاريس وخطوط كنتور من SRTM)، وEsri World Imagery وWorld Hillshade وطبقة الحدود والأسماء، وOpenStreetMap.', 'https://opentopomap.org'],
  ];
  const M = [
    'نقطة الندى من الحرارة والرطوبة: معادلة Magnus (a=17.625، b=243.04).',
    'مستوى التكاثف LCL: حرارة Bolton 1980، والارتفاع ≈ 125 م لكل درجة فرق بين الحرارة ونقطة الندى عند 2 م.',
    'الماء القابل للهطول: قيمة النموذج إن وُجدت، وإلا تكامل الرطوبة النوعية على المستويات فوق السطح (تقريبي).',
    'مستوى التجمد: قيمة النموذج، وإلا استيفاء خطي بين مستويين.',
    'عمق الطبقة الرطبة: أعمق كتلة متصلة من المستويات فوق السطح برطوبة ≥ 70٪.',
    'رياح التوجيه: متوسط متجهات 700 و600 و500 hPa فوق السطح. القص: فرق متجه الرياح بين 10 م و500 hPa.',
    'تدفق الرطوبة: الرطوبة النوعية (غ/كغ) × سرعة الرياح عند 925 و850 hPa.',
    'التقارب: تباعد الرياح (∂u/∂x + ∂v/∂y) بفروق مركزية على شبكة 0.2° أو 0.5°؛ القيم السالبة تقارب.',
    'الرفع التضاريسي: w = V · ∇h برياح 10 م وارتفاعات DEM على الشبكة نفسها؛ تقدير خشن لا يمثل الأودية الضيقة.',
    'المستويات التي ضغطها أعلى من ضغط السطح في النموذج تُعدّ تحت الأرض وتُستبعد.',
    'لا يُخترع أي متغير: ما لا يعيده المصدر يظهر «غير متاح».',
  ];
  return section('المصادر وطرق الحساب',
    el('ul', { class: 'bullets' }, ...S.map(([t, d, u]) => el('li', {}, el('b', {}, t), `: ${d} `, el('a', { href: u, target: '_blank', rel: 'noopener' }, 'المصدر')))),
    el('h4', {}, 'طرق الحساب'), el('ul', { class: 'bullets' }, ...M.map((m) => el('li', {}, m))),
    el('p', { class: 'meta' }, `آخر جلب لبيانات النقطة: ${state.data.loadedAt ? fmtDateTime(state.data.loadedAt) : '—'}`));
}

function renderWrf() {
  return section('حالة نموذج WRF الإقليمي',
    el('div', { class: 'verdict v-none' }, el('b', {}, 'غير مُشغّل. لا توجد في الموقع أي خريطة أو بيانات من WRF.')),
    el('p', {}, 'الإعداد المقترح (9 ← 3 ← 1 كم، و333 م اختياري) مصمم وجاهز في ملفات namelist، لكن تشغيله يحتاج موارد غير متوفرة في هذه الاستضافة:'),
    el('ul', { class: 'bullets' },
      el('li', {}, 'خادم حوسبة بنحو 64 نواة أو أكثر، يعمل يوميًا لعدة ساعات لكل تشغيل 48 ساعة.'),
      el('li', {}, 'تثبيت WRF وWPS وبيانات WPS الجغرافية (عشرات الغيغابايت).'),
      el('li', {}, 'تنزيل GFS 0.25° يوميًا للشروط الابتدائية والحدية، ونموذج ارتفاع أدق (SRTM أو Copernicus) لنطاق 333 م.'),
      el('li', {}, 'معالجة المخرجات إلى طبقات خرائط ورفعها لهذا الموقع.')),
    el('p', {}, 'البديل الأقرب: الوصول إلى مخرجات النظام العددي للمركز الوطني للأرصاد إن أُتيحت.'));
}

// ---------------------------------------------------------------- misc
let toastTimer;
function toast(msg) { const t = $('toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500); }
let installBtn = null;
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installBtn = e; });

function init() {
  applyTheme();
  document.title = SITE.name;
  for (const b of document.querySelectorAll('[data-tab]')) b.addEventListener('click', () => showTab(b.dataset.tab));
  $('placeBtn').addEventListener('click', openPlaces);
  $('refreshBtn').addEventListener('click', () => { loadPlace(true); if (state.mapUI.field && wxmap) { wxmap.grids = {}; refreshField(); } toast('جارٍ التحديث من المصادر'); });
  $('layersBtn').addEventListener('click', openLayers);
  $('scrim').addEventListener('click', closeSheet);
  window.addEventListener('online', renderStatus); window.addEventListener('offline', renderStatus);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });
  const start = (location.hash || '').slice(1);
  showTab(TABS.includes(start) ? start : 'map');
  loadPlace();
  if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('sw.js').catch(() => {});
  // Refresh automatically every 30 minutes while open.
  setInterval(() => { if (document.visibilityState === 'visible') loadPlace(); }, 30 * 60 * 1000);
}
init();
