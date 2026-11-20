// Data access. All sources are public, key-free, and called from the browser.
import { getJSON, qs, store, FetchError } from './util.js';
import { ENDPOINTS, MODELS, SURFACE_VARS, LEVEL_VARS, LEVELS, VV_LEVELS, GRID_VARS, GRID_SFC_VARS, GRID_LEVEL_VARS, GRIDS } from './config.js';

export const POINT_VARS = [
  ...SURFACE_VARS,
  ...LEVELS.flatMap((p) => LEVEL_VARS.map((v) => `${v}_${p}hPa`)),
  ...VV_LEVELS.map((p) => `vertical_velocity_${p}hPa`),
];

const idMemo = store.get('modelIds', {});
const badVars = store.get('badVars', {});

function invalidValue(reason) {
  const m = /invalid String value\s+([A-Za-z0-9_]+)/i.exec(reason || '');
  return m ? m[1] : null;
}

// Request one Open-Meteo endpoint, trying model ids in order and dropping
// variables the API rejects. Remembers what worked on this device.
async function omRequest(endpoint, slotKey, ids, params, vars, opts = {}) {
  const order = idMemo[slotKey] ? [idMemo[slotKey], ...ids.filter((x) => x !== idMemo[slotKey])] : ids;
  let lastErr;
  for (const id of order) {
    let list = vars.filter((v) => !(badVars[id] || []).includes(v));
    for (let guard = 0; guard < 8; guard++) {
      const url = `${endpoint}?${qs({ ...params, hourly: list.join(','), models: id })}`;
      const nLoc = Array.isArray(params.latitude) ? params.latitude.length : 1;
      const perLoc = endpoint === ENDPOINTS.ensemble ? 5 : Math.max(1, list.length / 10);
      try {
        const res = await getJSON(url, { ...opts, weight: nLoc * perLoc });
        idMemo[slotKey] = id; store.set('modelIds', idMemo);
        return { ...res, id, vars: list };
      } catch (e) {
        lastErr = e;
        if (!(e instanceof FetchError) || e.status !== 400) throw e;
        const bad = invalidValue(e.reason);
        if (bad && list.includes(bad)) {
          list = list.filter((v) => v !== bad);
          badVars[id] = [...new Set([...(badVars[id] || []), bad])]; store.set('badVars', badVars);
          continue;
        }
        break; // most likely an unknown model id: try the next one
      }
    }
  }
  throw lastErr || new FetchError('لا يتوفر هذا النموذج من المصدر');
}

// One model family at one point; slots merged per variable, source recorded.
export async function fetchModelPoint(key, lat, lon, { force = false } = {}) {
  const m = MODELS[key];
  const params = { latitude: lat.toFixed(4), longitude: lon.toFixed(4), forecast_days: 3, timezone: 'Asia/Riyadh', timeformat: 'unixtime', wind_speed_unit: 'ms' };
  let base = null; const sourceOf = {}; const errors = []; let stale = false; let fetchedAt = Date.now(); const ids = [];
  for (const slot of m.sources) {
    const need = base ? POINT_VARS.filter((v) => !hasData(base.hourly[v])) : POINT_VARS;
    if (!need.length) break;
    try {
      const r = await omRequest(ENDPOINTS.forecast, `${key}:${slot.label}`, slot.ids, params, need, { force, ttl: 15 * 60 * 1000 });
      ids.push(r.id); stale = stale || r.stale; fetchedAt = Math.min(fetchedAt, r.fetchedAt);
      const h = r.data.hourly || {};
      if (!base) {
        base = { hourly: { time: (h.time || []).map((t) => t * 1000) }, units: { ...(r.data.hourly_units || {}) }, elevation: r.data.elevation, lat: r.data.latitude, lon: r.data.longitude };
      }
      const idx = new Map(((h.time || [])).map((t, k) => [t * 1000, k]));
      for (const v of need) {
        if (!hasData(h[v])) continue;
        base.hourly[v] = base.hourly.time.map((t) => { const k = idx.get(t); return k == null ? null : h[v][k]; });
        base.units[v] = (r.data.hourly_units || {})[v];
        sourceOf[v] = `${slot.label} (${r.id})`;
      }
    } catch (e) { errors.push(`${slot.label}: ${e.reason || e.message}`); }
  }
  if (!base) throw new FetchError(errors.join(' | ') || 'تعذر جلب النموذج');
  return { key, ...base, sourceOf, errors, ids, stale, fetchedAt };
}

export function hasData(arr) { return Array.isArray(arr) && arr.some((x) => x != null); }

export async function fetchEnsemble(key, lat, lon, { force = false } = {}) {
  const m = MODELS[key];
  const params = { latitude: lat.toFixed(4), longitude: lon.toFixed(4), forecast_days: 3, timezone: 'Asia/Riyadh', timeformat: 'unixtime' };
  const r = await omRequest(ENDPOINTS.ensemble, `ens:${key}`, m.ens, params, ['precipitation'], { force, ttl: 30 * 60 * 1000 });
  const h = r.data.hourly || {};
  const members = Object.keys(h).filter((k) => k === 'precipitation' || k.startsWith('precipitation_member')).map((k) => h[k]).filter(hasData);
  return { key, id: r.id, label: m.ensLabel, times: (h.time || []).map((t) => t * 1000), members, fetchedAt: r.fetchedAt, stale: r.stale };
}

export async function fetchElevation(points) {
  const out = new Array(points.length).fill(null);
  for (let k = 0; k < points.length; k += 100) {
    const chunk = points.slice(k, k + 100);
    const url = `${ENDPOINTS.elevation}?${qs({ latitude: chunk.map((p) => p[0].toFixed(4)), longitude: chunk.map((p) => p[1].toFixed(4)) })}`;
    const r = await getJSON(url, { ttl: 7 * 24 * 3600 * 1000 });
    (r.data.elevation || []).forEach((e, i) => { out[k + i] = e; });
  }
  return out;
}

export async function fetchMeta(key) {
  for (const path of MODELS[key].meta) {
    try {
      const r = await getJSON(ENDPOINTS.meta(path), { retries: 0, timeout: 10000, ttl: 10 * 60 * 1000 });
      const d = r.data;
      if (d && d.last_run_initialisation_time) {
        return { path, init: d.last_run_initialisation_time * 1000, avail: d.last_run_availability_time ? d.last_run_availability_time * 1000 : null };
      }
    } catch { /* try next */ }
  }
  return null;
}

// Grid of points for map layers; one model per request.
export function gridPoints(gridKey) {
  const g = GRIDS[gridKey];
  const lats = [], lons = [];
  for (let la = g.lat0; la <= g.lat1 + 1e-6; la += g.step) lats.push(+la.toFixed(3));
  for (let lo = g.lon0; lo <= g.lon1 + 1e-6; lo += g.step) lons.push(+lo.toFixed(3));
  const pts = []; for (const la of lats) for (const lo of lons) pts.push([la, lo]);
  return { lats, lons, pts };
}

export async function fetchGrid(gridKey, key, { force = false } = {}) {
  const { lats, lons, pts } = gridPoints(gridKey);
  const m = MODELS[key];
  const params = { latitude: pts.map((p) => p[0]), longitude: pts.map((p) => p[1]), forecast_days: 2, timezone: 'Asia/Riyadh', timeformat: 'unixtime', wind_speed_unit: 'ms' };
  const opts = { force, ttl: 20 * 60 * 1000, timeout: 45000 };
  // ECMWF: surface fields from the 9 km HRES; pressure levels exist only on the 0.25° open data.
  const plan = key === 'ecmwf'
    ? [{ slot: 'grid:ecmwf:sfc', ids: ['ecmwf_ifs', 'ecmwf_ifs025'], vars: GRID_SFC_VARS }, { slot: 'grid:ecmwf', ids: ['ecmwf_ifs025', 'ecmwf_ifs'], vars: GRID_LEVEL_VARS }]
    : [{ slot: `grid:${key}`, ids: m.sources[0].ids, vars: GRID_VARS }];
  const fields = {}; const sourceOf = {}; const ids = []; let times = null, units = {}, fetchedAt = Date.now(), stale = false, elev = null;
  const take = (r, list) => {
    const arr = Array.isArray(r.data) ? r.data : [r.data];
    const t = ((arr[0] && arr[0].hourly && arr[0].hourly.time) || []).map((x) => x * 1000);
    if (!times) { times = t; elev = lats.map((_, j) => lons.map((__, i) => { const d = arr[j * lons.length + i]; return d ? d.elevation ?? null : null; })); }
    const ix = new Map(t.map((x, k) => [x, k]));
    for (const v of list) {
      const f = lats.map((_, j) => lons.map((__, i) => { const d = arr[j * lons.length + i]; const a = d && d.hourly && d.hourly[v]; return a ? times.map((x) => (ix.has(x) ? a[ix.get(x)] : null)) : null; }));
      if (!f.some((row) => row.some((a) => a && hasData(a)))) continue;
      fields[v] = f; sourceOf[v] = r.id; units[v] = (arr[0] && arr[0].hourly_units && arr[0].hourly_units[v]) || '';
    }
    ids.push(r.id); fetchedAt = Math.min(fetchedAt, r.fetchedAt); stale = stale || r.stale;
  };
  let lastErr = null;
  for (let k = 0; k < plan.length; k++) {
    const step = plan[k];
    // Anything the earlier request did not return is asked for again here.
    const want = [...new Set([...step.vars, ...(k ? plan.slice(0, k).flatMap((s) => s.vars) : [])])].filter((v) => !fields[v]);
    if (!want.length) continue;
    try { take(await omRequest(ENDPOINTS.forecast, step.slot, step.ids, params, want, opts), want); }
    catch (e) { lastErr = e; }
  }
  if (!times) throw lastErr || new FetchError('تعذر جلب الحقل');
  return { gridKey, key, id: [...new Set(ids)].join(' + '), lats, lons, times, fields, units, sourceOf, elev, fetchedAt, stale };
}

// Several arbitrary points (cross-sections). Returns one hourly block per point.
export async function fetchMulti(key, pts, vars, { days = 3 } = {}) {
  const m = MODELS[key];
  const ids = key === 'ecmwf' ? ['ecmwf_ifs025', 'ecmwf_ifs'] : m.sources[0].ids;
  const params = { latitude: pts.map((p) => p[0].toFixed(3)), longitude: pts.map((p) => p[1].toFixed(3)), forecast_days: days, timezone: 'Asia/Riyadh', timeformat: 'unixtime', wind_speed_unit: 'ms' };
  const r = await omRequest(ENDPOINTS.forecast, `multi:${key}`, ids, params, vars, { ttl: 20 * 60 * 1000, timeout: 40000 });
  const arr = Array.isArray(r.data) ? r.data : [r.data];
  return { id: r.id, blocks: arr.map((d) => ({ hourly: { ...(d.hourly || {}), time: ((d.hourly && d.hourly.time) || []).map((t) => t * 1000) }, elevation: d.elevation })), fetchedAt: r.fetchedAt };
}

// Day-1 forecasts from earlier runs (for the verification log).
export async function fetchPreviousDay1(key, lat, lon, startDate, endDate) {
  const m = MODELS[key];
  const ids = key === 'ecmwf' ? ['ecmwf_ifs', 'ecmwf_ifs025'] : m.sources[0].ids;
  const params = { latitude: lat.toFixed(4), longitude: lon.toFixed(4), start_date: startDate, end_date: endDate, timezone: 'Asia/Riyadh', timeformat: 'unixtime' };
  const r = await omRequest(ENDPOINTS.previous, `prev:${key}`, ids, params, ['precipitation_previous_day1'], { ttl: 3 * 3600 * 1000 });
  const h = r.data.hourly || {};
  return { id: r.id, times: (h.time || []).map((t) => t * 1000), precip: h.precipitation_previous_day1 || [] };
}

export async function fetchRadarFrames({ force = false } = {}) {
  const r = await getJSON(ENDPOINTS.rainviewer, { force, ttl: 4 * 60 * 1000, retries: 0 });
  const past = (r.data.radar && r.data.radar.past) || [];
  return { host: r.data.host, frames: past.map((f) => ({ time: f.time * 1000, path: f.path })), fetchedAt: r.fetchedAt };
}

// Latest image time advertised by an EUMETView layer (GetCapabilities default).
export async function fetchSatTime(layer) {
  const [ws, name] = layer.split(':');
  const res = await fetch(ENDPOINTS.eumetviewCaps(ws), { cache: 'no-cache' });
  if (!res.ok) throw new FetchError(`HTTP ${res.status}`);
  const xml = new DOMParser().parseFromString(await res.text(), 'text/xml');
  for (const lyr of xml.getElementsByTagName('Layer')) {
    const n = lyr.getElementsByTagName('Name')[0];
    if (!n || (n.textContent !== name && n.textContent !== layer)) continue;
    const dim = [...lyr.getElementsByTagName('Dimension')].find((d) => d.getAttribute('name') === 'time');
    if (!dim) return null;
    const def = dim.getAttribute('default');
    const all = dim.textContent.trim();
    let times = [];
    if (all.includes('/')) {
      // start/end/period form
      const [s, e, per] = all.split(',').pop().split('/');
      const step = isoDurationMs(per) || 15 * 60000; const end = Date.parse(e);
      for (let k = 11; k >= 0; k--) times.push(end - k * step);
      times = times.filter((t) => t >= Date.parse(s));
    } else times = all.split(',').slice(-12).map((t) => Date.parse(t)).filter(Boolean);
    return { latest: def ? Date.parse(def) : times[times.length - 1], times };
  }
  return null;
}
function isoDurationMs(p) {
  const m = /PT?(?:(\d+)H)?(?:(\d+)M)?/.exec(p || ''); if (!m) return null;
  return ((+m[1] || 0) * 60 + (+m[2] || 0)) * 60000 || null;
}

export async function fetchMetars(icaos) {
  const r = await getJSON(ENDPOINTS.metar(icaos.join(',')), { ttl: 10 * 60 * 1000, retries: 0, timeout: 12000 });
  return { list: Array.isArray(r.data) ? r.data : [], fetchedAt: r.fetchedAt };
}
