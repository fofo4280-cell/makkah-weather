// Leaflet map: base maps, reference layers, observations, smooth forecast fields,
// animated wind particles and convergence centres.
/* global L */
import { PLACES, TERRAIN_LABELS, ENDPOINTS, METAR_STATIONS } from './config.js';
import { fetchRadarFrames, fetchSatTime, fetchGrid, fetchElevation, gridPoints, fetchMetars } from './api.js';
import { divergence, orographicW, uv, specHum, dewpoint } from './met.js';
import { describe } from './geo.js';
import { fmtTime, fmtDateTime, num, dirName, sum } from './util.js';

export const BASES = {
  shade: { label: 'تضاريس مظللة (Esri)', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}', opts: { maxZoom: 16, attribution: 'ظل تضاريسي: Esri' } },
  dark: { label: 'داكن (Esri)', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', opts: { maxZoom: 16, attribution: 'خريطة: Esri' } },
  topo: { label: 'تضاريس وأسماء (OpenTopoMap)', url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', opts: { maxZoom: 17, subdomains: 'abc', attribution: 'خريطة: © OpenTopoMap (CC-BY-SA)، بيانات © OpenStreetMap، ارتفاعات SRTM' } },
  sat: { label: 'قمر صناعي (Esri)', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', opts: { maxZoom: 18, attribution: 'صور: Esri, Maxar, Earthstar Geographics' } },
  osm: { label: 'شوارع (OpenStreetMap)', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', opts: { maxZoom: 19, attribution: '© OpenStreetMap' } },
};

// Which wind level drives the particles for each field.
export const FIELDS = {
  precip: { label: 'المطر المتوقع', short: 'مطر', unit: 'مم', wind: '10m' },
  agree: { label: 'اتفاق النماذج على المطر', short: 'اتفاق', unit: 'نماذج', wind: '10m' },
  rh2m: { label: 'الرطوبة النسبية قرب السطح (2 م)', short: 'رطوبة', unit: '٪', wind: '10m' },
  rh925: { label: 'الرطوبة النسبية 925 hPa', short: 'رطوبة 925', unit: '٪', wind: '925hPa' },
  rh700: { label: 'الرطوبة النسبية 700 hPa', short: 'رطوبة 700', unit: '٪', wind: '700hPa' },
  wind10: { label: 'الرياح 10 م', short: 'رياح', unit: 'كم/س', wind: '10m' },
  wind925: { label: 'الرياح 925 hPa', short: 'رياح 925', unit: 'كم/س', wind: '925hPa' },
  wind700: { label: 'الرياح 700 hPa (التوجيه)', short: 'رياح 700', unit: 'كم/س', wind: '700hPa' },
  conv: { label: 'التقاء الرياح (تقارب قرب السطح)', short: 'التقاء', unit: '×10⁻⁵ ث⁻¹', wind: '10m' },
  qflux: { label: 'تدفق الرطوبة 925 hPa', short: 'تدفق رطوبة', unit: 'غ/كغ·م/ث', wind: '925hPa' },
  cape: { label: 'CAPE', short: 'CAPE', unit: 'J/kg', wind: '10m' },
  li: { label: 'Lifted Index', short: 'LI', unit: '', wind: '10m' },
  cin: { label: 'CIN (القيمة المطلقة)', short: 'CIN', unit: 'J/kg', wind: '10m' },
  vv700: { label: 'الحركة الرأسية 700 hPa', short: 'صعود 700', unit: 'سم/ث', wind: '700hPa' },
  oro: { label: 'الرفع التضاريسي (رياح 10 م × ميل الأرض)', short: 'رفع تضاريسي', unit: 'سم/ث', wind: '10m' },
};
export const QUICK_FIELDS = ['precip', 'rh2m', 'wind10', 'conv', 'cape', 'agree', 'rh700'];

// ---------------------------------------------------------------- palettes
// Rain, humidity and wind follow the colour gradients of Windy's layers (matched by eye,
// so close but not guaranteed identical). Values are in the field's display unit.
const T = 0; // transparent alpha
export const PALETTES = {
  precip: [[0.1, [58, 116, 168, T]], [0.4, [58, 116, 168, 0.85]], [1, [60, 128, 178]], [3, [59, 161, 161]], [6, [59, 168, 92]], [8, [96, 172, 60]], [10, [140, 170, 58]], [15, [170, 165, 58]], [20, [176, 92, 60]], [31, [168, 58, 140]], [50, [185, 185, 185]]],
  rh: [[0, [173, 85, 56]], [30, [173, 110, 56]], [40, [173, 146, 56]], [50, [105, 173, 56]], [60, [56, 173, 121]], [70, [56, 174, 173]], [80, [56, 157, 173]], [87, [56, 135, 173]], [93, [56, 123, 173]], [97, [56, 98, 157]], [100, [56, 70, 114]]],
  wind: [[0, [98, 113, 183]], [1, [57, 97, 159]], [3, [74, 148, 169]], [5, [77, 141, 123]], [7, [83, 165, 83]], [9, [53, 159, 53]], [11, [167, 157, 81]], [13, [159, 127, 58]], [15, [161, 108, 92]], [17, [129, 58, 78]], [19, [175, 80, 136]], [21, [117, 74, 147]], [24, [109, 97, 163]], [27, [68, 105, 141]], [30, [92, 144, 152]]],
  cape: [[0, [90, 100, 120, T]], [80, [70, 110, 170, 0.75]], [250, [60, 150, 160]], [500, [90, 170, 90]], [800, [170, 170, 60]], [1200, [200, 130, 50]], [1800, [196, 70, 60]], [2600, [170, 50, 130]], [4000, [215, 190, 225]]],
  cin: [[0, [120, 120, 120, T]], [20, [150, 150, 150, 0.5]], [60, [120, 120, 120, 0.75]], [120, [90, 90, 90, 0.85]], [250, [55, 55, 55, 0.9]]],
  li: [[2, [120, 120, 120, T]], [0, [190, 190, 120, 0.7]], [-2, [200, 150, 60]], [-4, [205, 95, 55]], [-6, [180, 50, 70]], [-9, [150, 50, 150]]],
  conv: [[-12, [150, 40, 160]], [-7, [205, 45, 75]], [-4, [232, 105, 45]], [-2, [245, 170, 60, 0.85]], [-0.8, [250, 215, 120, 0.45]], [-0.3, [250, 230, 160, T]], [0.3, [150, 190, 230, T]], [1.5, [120, 165, 220, 0.35]], [5, [60, 100, 190, 0.6]]],
  vv: [[-20, [40, 90, 190, 0.75]], [-6, [110, 160, 220, 0.5]], [-1.5, [170, 200, 235, T]], [1.5, [250, 200, 150, T]], [6, [240, 140, 70, 0.6]], [20, [200, 50, 60, 0.85]], [60, [150, 40, 150, 0.9]]],
  agree: [[0.3, [111, 170, 200, T]], [0.8, [111, 170, 200, 0.7]], [1, [100, 175, 200]], [2, [60, 140, 175]], [3, [40, 75, 160]]],
  qflux: [[0, [98, 113, 183, T]], [20, [74, 148, 169, 0.7]], [50, [77, 160, 110]], [90, [160, 160, 70]], [140, [180, 100, 70]], [220, [160, 60, 140]]],
};
const PAL_OF = { precip: 'precip', agree: 'agree', rh2m: 'rh', rh925: 'rh', rh700: 'rh', wind10: 'wind', wind925: 'wind', wind700: 'wind', conv: 'conv', qflux: 'qflux', cape: 'cape', li: 'li', cin: 'cin', vv700: 'vv', oro: 'vv' };
// Display scaling from stored values (SI) to palette/legend units.
const SCALE = { conv: 1e5, vv700: 100, oro: 100 };

function makeColor(stops) {
  const S = stops.map(([v, c]) => [v, c[0], c[1], c[2], c.length > 3 ? c[3] : 1]);
  const asc = S[0][0] < S[S.length - 1][0];
  if (!asc) S.reverse();
  return (v) => {
    if (v == null || Number.isNaN(v)) return null;
    if (v <= S[0][0]) return S[0].slice(1);
    for (let k = 1; k < S.length; k++) {
      if (v <= S[k][0]) {
        const a = S[k - 1], b = S[k], f = (v - a[0]) / (b[0] - a[0]);
        return [a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * (b[3] - a[3]), a[4] + f * (b[4] - a[4])];
      }
    }
    return S[S.length - 1].slice(1);
  };
}
const COLORS = Object.fromEntries(Object.entries(PALETTES).map(([k, s]) => [k, makeColor(s)]));

// Legend: CSS gradient plus tick labels, in display units.
const TICKS = {
  precip: [1, 3, 6, 10, 20, 50], agree: [1, 2, 3], rh: [20, 40, 60, 80, 100], wind: [0, 3, 6, 9, 12, 15, 20, 25, 30],
  conv: [-8, -4, -2, 0, 2, 5], qflux: [20, 50, 100, 150, 200], cape: [100, 500, 1000, 2000, 3000], cin: [25, 50, 100, 200], li: [0, -2, -4, -6, -8], vv: [-10, -3, 0, 3, 10, 30],
};
export function legendFor(name, windUnit = 'kmh') {
  const pk = PAL_OF[name]; const stops = PALETTES[pk]; if (!stops) return null;
  const lo = stops[0][0], hi = stops[stops.length - 1][0];
  const min = Math.min(lo, hi), max = Math.max(lo, hi);
  // Rain uses a stretched scale so the light amounts stay readable.
  const pos = pk === 'precip' ? (v) => Math.sqrt((v - min) / (max - min)) : (v) => (v - min) / (max - min);
  const fn = COLORS[pk]; const parts = [];
  for (let k = 0; k <= 24; k++) {
    const f = k / 24; const v = pk === 'precip' ? min + f * f * (max - min) : min + f * (max - min);
    const c = fn(v); parts.push(`rgba(${c.slice(0, 3).map(Math.round).join(',')},${Math.max(0.12, c[3]).toFixed(2)}) ${(f * 100).toFixed(1)}%`);
  }
  const wconv = pk === 'wind' ? (windUnit === 'kt' ? 1.94384 : windUnit === 'ms' ? 1 : 3.6) : 1;
  const ticks = (TICKS[pk] || []).filter((v) => v >= min && v <= max).map((v) => ({ at: pos(v) * 100, label: num(v * wconv, Math.abs(v * wconv) < 1 && v !== 0 ? 1 : 0) }));
  return { gradient: `linear-gradient(to right, ${parts.join(', ')})`, ticks };
}

// ---------------------------------------------------------------- grid sampling
const clampI = (k, a, b) => (k < a ? a : k > b ? b : k);
function fillNulls(g) {
  const ny = g.length, nx = g[0].length; const out = g.map((r) => r.slice());
  if (!out.some((r) => r.some((v) => v != null))) return null;
  for (let pass = 0; pass < nx + ny; pass++) {
    let missing = 0; const next = out.map((r) => r.slice());
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      if (out[j][i] != null) continue;
      let s = 0, n = 0;
      for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) { const v = out[j + dj] && out[j + dj][i + di]; if (v != null) { s += v; n++; } }
      if (n) next[j][i] = s / n; else missing++;
    }
    for (let j = 0; j < ny; j++) out[j] = next[j];
    if (!missing) break;
  }
  return out;
}
function bilinear(g, fx, fy) {
  const ny = g.length, nx = g[0].length;
  fx = Math.max(0, Math.min(nx - 1, fx)); fy = Math.max(0, Math.min(ny - 1, fy));
  const i = Math.min(nx - 2, Math.floor(fx)), j = Math.min(ny - 2, Math.floor(fy)); const tx = fx - i, ty = fy - j;
  if (nx < 2 || ny < 2) return g[0][0];
  return (g[j][i] * (1 - tx) + g[j][i + 1] * tx) * (1 - ty) + (g[j + 1][i] * (1 - tx) + g[j + 1][i + 1] * tx) * ty;
}
const cubic = (p0, p1, p2, p3, t) => p1 + 0.5 * t * (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)));
// Catmull-Rom, clamped to the four surrounding grid values so it never invents peaks.
function bicubic(g, fx, fy) {
  const ny = g.length, nx = g[0].length;
  fx = Math.max(0, Math.min(nx - 1, fx)); fy = Math.max(0, Math.min(ny - 1, fy));
  const ix = Math.floor(fx), iy = Math.floor(fy), tx = fx - ix, ty = fy - iy;
  const at = (j, i) => g[clampI(j, 0, ny - 1)][clampI(i, 0, nx - 1)];
  const r = [-1, 0, 1, 2].map((m) => cubic(at(iy + m, ix - 1), at(iy + m, ix), at(iy + m, ix + 1), at(iy + m, ix + 2), tx));
  const v = cubic(r[0], r[1], r[2], r[3], ty);
  const a = at(iy, ix), b = at(iy, ix + 1), c = at(iy + 1, ix), d = at(iy + 1, ix + 1);
  const lo = Math.min(a, b, c, d), hi = Math.max(a, b, c, d);
  return v < lo ? lo : v > hi ? hi : v;
}
const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const invMerc = (y) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90;

function renderScalar(G, vals, color, px = 480) {
  const ny = G.lats.length, nx = G.lons.length;
  const dlat = G.lats[1] - G.lats[0], dlon = G.lons[1] - G.lons[0];
  const lat0 = G.lats[0] - dlat / 2, lat1 = G.lats[ny - 1] + dlat / 2, lon0 = G.lons[0] - dlon / 2, lon1 = G.lons[nx - 1] + dlon / 2;
  const filled = fillNulls(vals); if (!filled) return null;
  const mask = vals.map((r) => r.map((v) => (v == null ? 0 : 1)));
  const my0 = merc(lat0), my1 = merc(lat1);
  const W = px, H = Math.max(2, Math.round((W * (my1 - my0)) / (((lon1 - lon0) * Math.PI) / 180)));
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d'); const img = ctx.createImageData(W, H); const D = img.data;
  for (let py = 0; py < H; py++) {
    const lat = invMerc(my1 - ((py + 0.5) / H) * (my1 - my0)); const fy = (lat - G.lats[0]) / dlat;
    for (let qx = 0; qx < W; qx++) {
      const lon = lon0 + ((qx + 0.5) / W) * (lon1 - lon0); const fx = (lon - G.lons[0]) / dlon;
      const m = bilinear(mask, fx, fy); if (m < 0.3) continue;
      const c = color(bicubic(filled, fx, fy)); if (!c) continue;
      // soft fade over the outer few percent of the domain, so the grid edge is not a hard line
      const edge = Math.min(1, Math.min(qx + 0.5, W - qx - 0.5, py + 0.5, H - py - 0.5) / (0.035 * W));
      const a = c[3] * Math.min(1, (m - 0.3) / 0.4) * edge; const o = (py * W + qx) * 4;
      D[o] = c[0]; D[o + 1] = c[1]; D[o + 2] = c[2]; D[o + 3] = Math.round(a * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
  return { url: cv.toDataURL('image/png'), bounds: [[lat0, lon0], [lat1, lon1]] };
}

// Bilinear wind (u, v) at a point; null where too much of the cell is missing (e.g. under ground).
export function windAt(W, lat, lon) {
  if (!W) return null;
  const { lats, lons, U, V } = W; const dlat = lats[1] - lats[0], dlon = lons[1] - lons[0];
  const fx = (lon - lons[0]) / dlon, fy = (lat - lats[0]) / dlat;
  if (fx < -0.5 || fy < -0.5 || fx > lons.length - 0.5 || fy > lats.length - 0.5) return null;
  const cx = Math.max(0, Math.min(lons.length - 1.0001, fx)), cy = Math.max(0, Math.min(lats.length - 1.0001, fy));
  const i = Math.floor(cx), j = Math.floor(cy), tx = cx - i, ty = cy - j;
  let su = 0, sv = 0, sw = 0;
  for (const [dj, di, w] of [[0, 0, (1 - tx) * (1 - ty)], [0, 1, tx * (1 - ty)], [1, 0, (1 - tx) * ty], [1, 1, tx * ty]]) {
    const row = U[j + dj]; if (!row) continue; const u = row[i + di], v = V[j + dj][i + di];
    if (u == null || v == null) continue; su += u * w; sv += v * w; sw += w;
  }
  return sw < 0.5 ? null : [su / sw, sv / sw];
}

// 3×3 binomial smoothing that skips missing cells.
function smooth3(g) {
  const ny = g.length, nx = g[0].length; const K = [1, 2, 1];
  return g.map((row, j) => row.map((v, i) => {
    if (v == null) return null; let s = 0, w = 0;
    for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
      const x = g[j + dj] && g[j + dj][i + di]; if (x == null) continue; const k = K[dj + 1] * K[di + 1]; s += x * k; w += k;
    }
    return s / w;
  }));
}

// Local convergence maxima (divergence minima), refined to sub-grid position with a parabola fit.
export function convCentres(d, G, thr, max = 6) {
  const ny = G.lats.length, nx = G.lons.length; const out = [];
  const dlat = G.lats[1] - G.lats[0], dlon = G.lons[1] - G.lons[0];
  for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const v = d[j][i]; if (v == null || v > thr) continue;
    let isMin = true;
    for (let dj = -1; dj <= 1 && isMin; dj++) for (let di = -1; di <= 1; di++) { if (!dj && !di) continue; const x = d[j + dj][i + di]; if (x != null && x < v) { isMin = false; break; } }
    if (!isMin) continue;
    const off = (a, b) => { if (a == null || b == null) return 0; const den = a - 2 * v + b; return den > 0 ? Math.max(-0.5, Math.min(0.5, (0.5 * (a - b)) / den)) : 0; };
    out.push({ lat: G.lats[j] + off(d[j - 1][i], d[j + 1][i]) * dlat, lon: G.lons[i] + off(d[j][i - 1], d[j][i + 1]) * dlon, v });
  }
  out.sort((a, b) => a.v - b.v);
  return out.slice(0, max).map((c, k) => ({ ...c, rank: k + 1, where: describe(c.lat, c.lon) }));
}
const CONV_THR = { fine: -2e-5, near: -1.2e-5, region: -0.6e-5 };

// ---------------------------------------------------------------- particles
const ParticleLayer = !window.L ? null : L.Layer.extend({
  initialize(opts = {}) { this.opts = { density: 1 / 230, trail: 12, pane: 'particlePane', ...opts }; this.field = null; this.color = '255,255,255'; this.alpha = 0.9; },
  onAdd(map) {
    this._map = map;
    this._canvas = L.DomUtil.create('canvas', 'wx-particles');
    map.getPane(this.opts.pane).appendChild(this._canvas);
    this._ctx = this._canvas.getContext('2d');
    map.on('movestart zoomstart', this._hide, this); map.on('moveend resize', this._reset, this);
    this._reset();
    this._tick = this._tick.bind(this); this._raf = requestAnimationFrame(this._tick);
  },
  onRemove(map) { cancelAnimationFrame(this._raf); this._canvas.remove(); map.off('movestart zoomstart', this._hide, this); map.off('moveend resize', this._reset, this); },
  setField(f) { this.field = f; if (this._map) { this._buildVel(); if (!this.n) this._spawnAll(); } },
  setColor(rgb, alpha) { this.color = rgb; this.alpha = alpha; },
  _hide() { this._paused = true; this._canvas.style.opacity = 0; },
  _reset() {
    const map = this._map; const s = map.getSize(); const dpr = Math.min(2, window.devicePixelRatio || 1);
    this._w = s.x; this._h = s.y; this._dpr = dpr;
    this._canvas.width = s.x * dpr; this._canvas.height = s.y * dpr; this._canvas.style.width = `${s.x}px`; this._canvas.style.height = `${s.y}px`;
    L.DomUtil.setPosition(this._canvas, map.containerPointToLayerPoint([0, 0]));
    this._buildVel(); this._spawnAll();
    this._paused = false; this._canvas.style.opacity = 1;
  },
  _buildVel() {
    const C = 6; this._cell = C; const cols = Math.ceil(this._w / C) + 2, rows = Math.ceil(this._h / C) + 2;
    this._cols = cols; this._rows = rows; const vel = this._vel = new Float32Array(cols * rows * 2).fill(NaN);
    if (!this.field) return;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const ll = this._map.containerPointToLatLng([c * C, r * C]); const w = windAt(this.field, ll.lat, ll.lng); if (!w) continue;
      const sp = Math.hypot(w[0], w[1]); const k = sp > 0.05 ? (0.38 * Math.pow(sp, 0.75)) / sp : 0;
      vel[(r * cols + c) * 2] = w[0] * k; vel[(r * cols + c) * 2 + 1] = -w[1] * k;
    }
  },
  _velAt(x, y) {
    const C = this._cell, fx = x / C, fy = y / C; const c = Math.floor(fx), r = Math.floor(fy);
    if (c < 0 || r < 0 || c >= this._cols - 1 || r >= this._rows - 1) return null;
    const tx = fx - c, ty = fy - r, V = this._vel, cols = this._cols;
    const g = (rr, cc, k) => V[(rr * cols + cc) * 2 + k];
    const a = g(r, c, 0); if (Number.isNaN(a)) return null;
    const pick = (k) => { const v00 = g(r, c, k), v01 = g(r, c + 1, k), v10 = g(r + 1, c, k), v11 = g(r + 1, c + 1, k); if ([v01, v10, v11].some(Number.isNaN)) return v00; return (v00 * (1 - tx) + v01 * tx) * (1 - ty) + (v10 * (1 - tx) + v11 * tx) * ty; };
    return [pick(0), pick(1)];
  },
  _spawnAll() {
    const n = this.n = Math.max(200, Math.min(2200, Math.round(this._w * this._h * this.opts.density))); const T = this.opts.trail;
    this.tx = new Float32Array(n * T); this.ty = new Float32Array(n * T); this.len = new Uint8Array(n); this.age = new Uint16Array(n); this.maxAge = new Uint16Array(n);
    for (let p = 0; p < n; p++) this._spawn(p, true);
  },
  _spawn(p, initial) {
    const T = this.opts.trail;
    for (let tries = 0; tries < 12; tries++) {
      const x = Math.random() * this._w, y = Math.random() * this._h;
      if (this._velAt(x, y)) { this.tx[p * T] = x; this.ty[p * T] = y; this.len[p] = 1; this.age[p] = initial ? Math.floor(Math.random() * 80) : 0; this.maxAge[p] = 60 + Math.floor(Math.random() * 70); return; }
    }
    this.len[p] = 0; this.age[p] = 0; this.maxAge[p] = 10 + Math.floor(Math.random() * 30);
  },
  _tick() {
    this._raf = requestAnimationFrame(this._tick);
    if (this._paused || document.hidden || !this._map || !this._map.getContainer().offsetParent) return;
    const ctx = this._ctx, T = this.opts.trail, dpr = this._dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, this._w, this._h);
    if (!this.field || !this.n) return;
    for (let p = 0; p < this.n; p++) {
      const L0 = this.len[p];
      if (!L0 || ++this.age[p] > this.maxAge[p]) { this._spawn(p, false); continue; }
      const b = p * T + L0 - 1; const x = this.tx[b], y = this.ty[b]; const v = this._velAt(x, y);
      if (!v) { this.age[p] = this.maxAge[p]; continue; }
      if (L0 < T) { this.tx[b + 1] = x + v[0]; this.ty[b + 1] = y + v[1]; this.len[p] = L0 + 1; }
      else { this.tx.copyWithin(p * T, p * T + 1, p * T + T); this.ty.copyWithin(p * T, p * T + 1, p * T + T); this.tx[p * T + T - 1] = x + v[0]; this.ty[p * T + T - 1] = y + v[1]; }
    }
    ctx.lineWidth = 1.25; ctx.lineCap = 'round'; ctx.strokeStyle = `rgb(${this.color})`;
    const B = 4;
    for (let bk = 0; bk < B; bk++) {
      ctx.globalAlpha = this.alpha * ((bk + 1) / B) ** 1.3; ctx.beginPath();
      for (let p = 0; p < this.n; p++) {
        const n = this.len[p]; if (n < 2) continue; const o = p * T;
        for (let s = 0; s < n - 1; s++) {
          if (Math.min(B - 1, Math.floor(((s + T - n) * B) / (T - 1))) !== bk) continue;
          ctx.moveTo(this.tx[o + s], this.ty[o + s]); ctx.lineTo(this.tx[o + s + 1], this.ty[o + s + 1]);
        }
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },
});

// ---------------------------------------------------------------- observations
const SAT_LAYERS = {
  ir_iodc: { label: 'أشعة تحت حمراء 10.8 – Meteosat (المحيط الهندي)', layer: 'msg_iodc:ir108' },
  ir_mtg: { label: 'أشعة تحت حمراء 10.5 – MTG (0°)', layer: 'mtg_fd:ir105_hrfi' },
  cth: { label: 'ارتفاع قمم السحب – Meteosat (المحيط الهندي)', layer: 'msg_iodc:cth' },
  lightning: { label: 'البرق – MTG Lightning Imager (مساحة الومضات المتراكمة)', layer: 'mtg_fd:li_afa' },
};
export { SAT_LAYERS };

const AR_NUM = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
const arN = (n) => String(n).replace(/\d/g, (d) => AR_NUM[d]);

export class WxMap {
  constructor(el, { onPick, onStatus, base }) {
    this.onPick = onPick; this.onStatus = onStatus || (() => {});
    this.map = L.map(el, { zoomControl: false, attributionControl: true, minZoom: 5, maxZoom: 15, tap: true }).setView([21.5, 39.95], 8);
    L.control.zoom({ position: 'topleft' }).addTo(this.map);
    this.map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
    const pane = (name, z, cls) => { const p = this.map.createPane(name); p.style.zIndex = z; p.style.pointerEvents = 'none'; if (cls) p.classList.add(cls); return p; };
    pane('fieldPane', 340); pane('reliefPane', 350, 'relief-pane'); pane('obsPane', 360); pane('particlePane', 380); pane('markPane', 620);
    this.bases = {}; for (const [k, b] of Object.entries(BASES)) this.bases[k] = L.tileLayer(b.url, b.opts);
    this.base = BASES[base] ? base : 'shade'; this.bases[this.base].addTo(this.map);
    this.overlays = {
      ref: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, pane: 'markPane', attribution: 'حدود وأسماء: Esri' }),
      places: this._placesLayer(),
      labels: this._terrainLabels(),
    };
    this.relief = L.tileLayer(BASES.shade.url, { ...BASES.shade.opts, pane: 'reliefPane', opacity: 0.6 });
    this.reliefOn = true; this.fieldOpacity = 0.82;
    this.overlays.places.addTo(this.map);
    this.obs = {}; this.sat = {}; this.satTimes = {};
    this.fieldImg = null; this.markLayer = L.layerGroup().addTo(this.map);
    this.particles = new ParticleLayer(); this.particlesOn = true; // eslint-disable-line
    this.pickMarker = null; this.grids = {}; this.dem = {};
    this.map.on('click', (e) => this._click(e));
  }

  _placesLayer() {
    const g = L.layerGroup();
    for (const p of PLACES) {
      L.circleMarker([p.lat, p.lon], { radius: 4.5, color: '#fff', weight: 2, fillColor: '#0b1f2a', fillOpacity: 1 })
        .bindTooltip(p.name, { permanent: true, direction: 'top', offset: [0, -6], className: 'map-label' })
        .on('click', (e) => { L.DomEvent.stopPropagation(e); this.onPick({ ...p }); })
        .addTo(g);
    }
    return g;
  }
  _terrainLabels() {
    const g = L.layerGroup();
    for (const t of TERRAIN_LABELS) L.marker([t.lat, t.lon], { icon: L.divIcon({ className: 'terrain-label', html: `<span>${t.name}</span>`, iconSize: null }), interactive: false }).addTo(g);
    return g;
  }

  setBase(k) { if (k === this.base) return; this.map.removeLayer(this.bases[this.base]); this.bases[k].addTo(this.map); this.bases[k].bringToBack(); this.base = k; this._styleParticles(); }
  toggleOverlay(k, on) { const l = this.overlays[k]; if (!l) return; if (on) l.addTo(this.map); else this.map.removeLayer(l); }
  setRelief(on) { this.reliefOn = on; this._syncRelief(); }
  _syncRelief() { const want = this.reliefOn && !!this.fieldImg; if (want && !this.map.hasLayer(this.relief)) this.relief.addTo(this.map); if (!want && this.map.hasLayer(this.relief)) this.map.removeLayer(this.relief); }
  setFieldOpacity(o) { this.fieldOpacity = o; if (this.fieldImg) this.fieldImg.setOpacity(o); this._styleParticles(); }
  setParticles(on) {
    this.particlesOn = on;
    if (on && this.windField) { if (!this.map.hasLayer(this.particles)) this.particles.addTo(this.map); this.particles.setField(this.windField); }
    if (!on && this.map.hasLayer(this.particles)) this.map.removeLayer(this.particles);
  }
  _styleParticles() {
    const light = !this.fieldImg && (this.base === 'topo' || this.base === 'osm' || this.base === 'shade');
    this.particles.setColor(light ? '16,32,44' : '255,255,255', light ? 0.75 : 0.9);
  }

  // ---------- observations
  async toggleRadar(on, { coverage = false } = {}) {
    if (this.radarTimer) { clearInterval(this.radarTimer); this.radarTimer = null; }
    for (const l of [this.obs.radar, this.obs.radarCov]) if (l) this.map.removeLayer(l);
    this.obs.radar = this.obs.radarCov = null;
    if (!on) return null;
    const r = await fetchRadarFrames({ force: true });
    if (!r.frames.length) throw new Error('لا توجد إطارات رادار حديثة');
    this.radar = r; this.radarIdx = r.frames.length - 1;
    this.obs.radar = L.tileLayer(this._radarUrl(this.radarIdx), { pane: 'obsPane', opacity: 0.85, maxNativeZoom: 7, maxZoom: 15, attribution: 'رادار: RainViewer' }).addTo(this.map);
    if (coverage) this.obs.radarCov = L.tileLayer(`${r.host}/v2/coverage/0/256/{z}/{x}/{y}/0/0_0.png`, { pane: 'obsPane', opacity: 0.35, maxNativeZoom: 7, maxZoom: 15 }).addTo(this.map);
    return r.frames[this.radarIdx].time;
  }
  _radarUrl(i) { return `${this.radar.host}${this.radar.frames[i].path}/256/{z}/{x}/{y}/2/1_0.png`; }
  stepRadar(dir) {
    if (!this.obs.radar || !this.radar) return null;
    this.radarIdx = (this.radarIdx + dir + this.radar.frames.length) % this.radar.frames.length;
    this.obs.radar.setUrl(this._radarUrl(this.radarIdx));
    return this.radar.frames[this.radarIdx].time;
  }
  playRadar(onTick) {
    if (this.radarTimer) { clearInterval(this.radarTimer); this.radarTimer = null; return false; }
    this.radarTimer = setInterval(() => onTick(this.stepRadar(1)), 900); return true;
  }
  async toggleSat(key, on) {
    if (this.sat[key]) { this.map.removeLayer(this.sat[key]); delete this.sat[key]; }
    if (!on) return null;
    const def = SAT_LAYERS[key];
    const layer = L.tileLayer.wms(ENDPOINTS.eumetview, { layers: def.layer, format: 'image/png', transparent: true, version: '1.3.0', pane: 'obsPane', opacity: key === 'lightning' ? 0.95 : 0.7, attribution: 'أقمار: EUMETSAT EUMETView', maxZoom: 15 });
    layer.addTo(this.map); this.sat[key] = layer;
    try { const t = await fetchSatTime(def.layer); this.satTimes[key] = t; return t; } catch { this.satTimes[key] = null; return null; }
  }
  setSatTime(key, ms) { const l = this.sat[key]; if (l) l.setParams({ time: new Date(ms).toISOString().replace('.000', '') }); }
  async toggleMetar(on) {
    if (this.obs.metar) { this.map.removeLayer(this.obs.metar); this.obs.metar = null; }
    if (!on) return null;
    const r = await fetchMetars(METAR_STATIONS.map((s) => s.icao));
    const g = L.layerGroup();
    for (const m of r.list) {
      const st = METAR_STATIONS.find((s) => s.icao === m.icaoId) || { name: m.icaoId, lat: m.lat, lon: m.lon };
      L.circleMarker([m.lat ?? st.lat, m.lon ?? st.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#2a7d3f', fillOpacity: 1 })
        .bindPopup(`<b>${st.name}</b><br>${num(m.temp)}°م / ندى ${num(m.dewp)}°م<br>رياح ${m.wdir === 'VRB' ? 'متغيرة' : dirName(Number(m.wdir))} ${num(m.wspd)} عقدة<br><code dir="ltr">${m.rawOb || ''}</code>`)
        .addTo(g);
    }
    g.addTo(this.map); this.obs.metar = g;
    return r.list;
  }

  // ---------- forecast grids
  async loadGrid(gridKey, modelKey, force) {
    const k = `${gridKey}:${modelKey}`;
    if (!force && this.grids[k]) return this.grids[k];
    this.grids[k] = await fetchGrid(gridKey, modelKey, { force });
    return this.grids[k];
  }
  async loadDem(gridKey) {
    if (this.dem[gridKey]) return this.dem[gridKey];
    const { lats, lons, pts } = gridPoints(gridKey);
    const e = await fetchElevation(pts);
    this.dem[gridKey] = lats.map((_, j) => lons.map((__, i) => e[j * lons.length + i]));
    return this.dem[gridKey];
  }

  // Values in SI units at time index ti; precipitation summed over windowH hours.
  async computeField(name, gridKey, modelKey, ti, windowH, th) {
    let G;
    let vals = null, note = '', conv = null;
    if (name === 'agree') {
      const grids = await Promise.allSettled(['ecmwf', 'gfs', 'icon'].map((m) => this.loadGrid(gridKey, m)));
      const ok = grids.filter((g) => g.status === 'fulfilled').map((g) => g.value);
      if (!ok.length) throw new Error('تعذر جلب أي نموذج');
      G = ok.find((g) => g.key === modelKey) || ok[0];
      vals = G.lats.map((_, j) => G.lons.map((__, i) => {
        let n = 0, have = 0;
        for (const g of ok) { const a = g.fields.precipitation && g.fields.precipitation[j][i]; if (!a) continue; have++; if (sum(a.slice(ti, ti + windowH)) >= th.rainAgree) n++; }
        return have ? n : null;
      }));
      note = `${ok.length} من 3 نماذج متاحة؛ عتبة ${th.rainAgree} مم خلال ${windowH} ساعة`;
    } else G = await this.loadGrid(gridKey, modelKey);
    const F = G.fields; const at = (v, j, i) => (F[v] && F[v][j][i] ? F[v][j][i][ti] : null);
    const ps = (j, i) => at('surface_pressure', j, i);
    const above = (p, j, i) => { const s = ps(j, i); return s == null || s > p + 5; };
    const map2 = (fn) => G.lats.map((_, j) => G.lons.map((__, i) => fn(j, i)));
    const windGrid = (lv) => {
      const p = lv === '10m' ? null : parseInt(lv, 10);
      const ok = (j, i) => p == null || above(p, j, i);
      const U = map2((j, i) => (ok(j, i) ? uv(at(`wind_speed_${lv}`, j, i), at(`wind_direction_${lv}`, j, i))[0] : null));
      const V = map2((j, i) => (ok(j, i) ? uv(at(`wind_speed_${lv}`, j, i), at(`wind_direction_${lv}`, j, i))[1] : null));
      return { U, V };
    };
    let windLv = FIELDS[name] ? FIELDS[name].wind : '10m';
    if (name === 'conv' && gridKey === 'region') windLv = '925hPa';
    let W = windGrid(windLv);
    if (!W.U.some((r) => r.some((x) => x != null)) && windLv !== '10m') { windLv = '10m'; W = windGrid('10m'); }
    switch (name) {
      case 'agree': break;
      case 'precip': vals = map2((j, i) => (F.precipitation && F.precipitation[j][i] ? sum(F.precipitation[j][i].slice(ti, ti + windowH)) : null)); note = `مجموع ${windowH} ساعة يبدأ من الوقت المختار`; break;
      case 'cape': vals = map2((j, i) => at('cape', j, i)); break;
      case 'li': vals = map2((j, i) => at('lifted_index', j, i)); break;
      case 'cin': vals = map2((j, i) => { const v = at('convective_inhibition', j, i); return v == null ? null : Math.abs(v); }); break;
      case 'rh2m': vals = map2((j, i) => at('relative_humidity_2m', j, i)); break;
      case 'rh700': vals = map2((j, i) => (above(700, j, i) ? at('relative_humidity_700hPa', j, i) : null)); break;
      case 'rh925': vals = map2((j, i) => (above(925, j, i) ? at('relative_humidity_925hPa', j, i) : null)); note = 'المناطق الشفافة: مستوى 925 hPa تحت سطح الأرض'; break;
      case 'wind10': case 'wind925': case 'wind700': vals = map2((j, i) => (W.U[j][i] == null ? null : Math.hypot(W.U[j][i], W.V[j][i]))); break;
      case 'qflux': {
        vals = map2((j, i) => {
          if (!above(925, j, i)) return null;
          const t = at('temperature_925hPa', j, i), rh = at('relative_humidity_925hPa', j, i), s = at('wind_speed_925hPa', j, i);
          if ([t, rh, s].some((x) => x == null)) return null;
          return specHum(dewpoint(t, rh), 925) * 1000 * s;
        });
        note = 'q × سرعة الرياح عند 925 hPa'; break;
      }
      case 'conv': {
        const sm = gridKey === 'fine';
        const U = sm ? smooth3(W.U) : W.U, V = sm ? smooth3(W.V) : W.V;
        vals = divergence(U, V, G.lats, G.lons);
        conv = convCentres(vals, G, CONV_THR[gridKey] ?? -1e-5);
        note = `من رياح ${windLv === '10m' ? '10 م' : '925 hPa'} بفروق مركزية على شبكة ${(G.lats[1] - G.lats[0]).toFixed(1)}°${sm ? ' بعد تنعيم 3×3' : ''}. الأحمر والبرتقالي التقاء (تقارب)، والأزرق تباعد. الدوائر المرقمة أقوى مراكز الالتقاء`;
        break;
      }
      case 'vv700': {
        const unit = G.units['vertical_velocity_700hPa'] || '';
        const cv = /pa/i.test(unit) ? (x) => -x / 8.8 : (x) => x;
        vals = map2((j, i) => { const v = at('vertical_velocity_700hPa', j, i); return v == null || !above(700, j, i) ? null : cv(v); });
        note = `موجب = صعود (الوحدة الأصلية: ${unit || 'غير محددة'})`; break;
      }
      case 'oro': {
        const H = await this.loadDem(gridKey);
        const W10 = windLv === '10m' ? W : windGrid('10m');
        vals = orographicW(W10.U, W10.V, H, G.lats, G.lons);
        note = 'w = V₁₀ · ∇h، الارتفاعات من Copernicus DEM على شبكة الحقل نفسها (تقدير خشن)'; break;
      }
      default: vals = null;
    }
    const wind = { lats: G.lats, lons: G.lons, U: W.U, V: W.V, level: windLv };
    return { G, vals, wind, conv, note };
  }

  drawField(name, res) {
    this.clearField(true);
    this.current = { name, res };
    const pk = PAL_OF[name]; const sc = SCALE[name] || 1;
    if (res.vals && pk) {
      const disp = sc === 1 ? res.vals : res.vals.map((r) => r.map((v) => (v == null ? null : v * sc)));
      const img = renderScalar(res.G, disp, COLORS[pk]);
      if (img) this.fieldImg = L.imageOverlay(img.url, img.bounds, { pane: 'fieldPane', opacity: this.fieldOpacity, interactive: false, className: 'field-img' }).addTo(this.map);
    }
    this._syncRelief(); this._styleParticles();
    // Moving wind lines appear only on the wind layers; every other field stays still.
    this.windField = name.startsWith('wind') ? res.wind : null;
    if (this.particlesOn && this.windField) { if (!this.map.hasLayer(this.particles)) this.particles.addTo(this.map); this.particles.setField(this.windField); }
    else if (this.map.hasLayer(this.particles)) this.map.removeLayer(this.particles);
    if (res.conv) this._convMarks(res.conv);
  }
  _convMarks(list) {
    for (const c of list) {
      L.marker([c.lat, c.lon], { pane: 'markPane', icon: L.divIcon({ className: 'conv-mark', html: `<span>${arN(c.rank)}</span>`, iconSize: [30, 30], iconAnchor: [15, 15] }) })
        .bindPopup(`<div class="pop"><b>مركز التقاء ${arN(c.rank)}</b><div>${c.where.text}${c.where.tags.length ? ` · ${c.where.tags.join('، ')}` : ''}</div><div>التقارب: <b>${num(-c.v * 1e5, 1)}</b> ×10⁻⁵ ث⁻¹</div><div class="meta" dir="ltr">${c.lat.toFixed(3)}°N ${c.lon.toFixed(3)}°E</div></div>`)
        .addTo(this.markLayer);
    }
  }
  clearField(keepWind) {
    if (this.fieldImg) { this.map.removeLayer(this.fieldImg); this.fieldImg = null; }
    this.markLayer.clearLayers(); this.current = null;
    if (!keepWind) { this.windField = null; if (this.map.hasLayer(this.particles)) this.map.removeLayer(this.particles); }
    this._syncRelief(); this._styleParticles();
  }

  valueAt(lat, lon) {
    if (!this.current) return null;
    const { G, vals, wind } = this.current.res;
    const dlat = G.lats[1] - G.lats[0], dlon = G.lons[1] - G.lons[0];
    const fx = (lon - G.lons[0]) / dlon, fy = (lat - G.lats[0]) / dlat;
    if (fx < -0.5 || fy < -0.5 || fx > G.lons.length - 0.5 || fy > G.lats.length - 0.5) return null;
    let v = null;
    if (vals) { const j = Math.round(Math.max(0, Math.min(G.lats.length - 1, fy))), i = Math.round(Math.max(0, Math.min(G.lons.length - 1, fx))); if (vals[j][i] != null) { const f = fillNulls(vals); v = f ? bilinear(f, fx, fy) : null; } }
    const w = windAt(wind, lat, lon);
    return { v, w, level: wind && wind.level };
  }

  _click(e) {
    const { lat, lng } = e.latlng;
    if (this.pickMarker) this.map.removeLayer(this.pickMarker);
    this.pickMarker = L.circleMarker([lat, lng], { radius: 7, color: '#fff', weight: 2, fillColor: '#e0592a', fillOpacity: 1 }).addTo(this.map);
    this.onPick({ id: 'custom', name: `نقطة ${lat.toFixed(2)}°ش ${lng.toFixed(2)}°ق`, lat, lon: lng, custom: true }, { fromMap: true, latlng: e.latlng });
  }
  popup(latlng, html) { L.popup({ maxWidth: 260, autoPanPaddingTopLeft: [10, 64], autoPanPaddingBottomRight: [10, 230] }).setLatLng(latlng).setContent(html).openOn(this.map); }
  showBoxes(boxes, crests) {
    if (this.boxLayer) this.map.removeLayer(this.boxLayer);
    const g = L.layerGroup();
    const colors = { valleys: '#1f8a4c', harrat: '#7a3e9d', ref: '#8a7660' };
    for (const [k, b] of Object.entries(boxes)) {
      L.rectangle([[b.lat0, b.lon0], [b.lat1, b.lon1]], { color: colors[k] || '#333', weight: 2, fillOpacity: 0.08, dashArray: '6 4' })
        .bindTooltip(b.name, { permanent: true, direction: 'center', className: 'map-label' }).addTo(g);
    }
    for (const c of crests) L.circleMarker([c.lat, c.lon], { radius: 8, color: '#fff', weight: 2, fillColor: '#b06a10', fillOpacity: 1 }).bindTooltip(`حافة: ${c.name}`, { direction: 'top' }).addTo(g);
    g.addTo(this.map); this.boxLayer = g;
    this.map.fitBounds([[20.9, 39.6], [23.0, 40.9]]);
  }
  // Numbered markers for the daily report's top locations.
  showReport(items, area) {
    if (this.reportLayer) this.map.removeLayer(this.reportLayer);
    const g = L.layerGroup();
    if (area && area.length) L.polygon(area, { pane: 'markPane', color: '#f2b552', weight: 2, dashArray: '6 5', fill: false, interactive: false }).addTo(g);
    for (const it of items) {
      L.marker([it.lat, it.lon], { pane: 'markPane', icon: L.divIcon({ className: 'rep-mark', html: `<span>${arN(it.rank)}</span>`, iconSize: [34, 34], iconAnchor: [17, 17] }) })
        .bindPopup(`<div class="pop"><b>${arN(it.rank)}. ${it.where.text}</b><div>${it.line || ''}</div></div>`).addTo(g);
    }
    g.addTo(this.map); this.reportLayer = g;
    const pts = [...items.map((i) => [i.lat, i.lon]), ...(area || [])];
    if (pts.length) this.map.fitBounds(L.latLngBounds(pts).pad(0.05), { maxZoom: 9 });
  }
  invalidate() { setTimeout(() => this.map.invalidateSize(), 50); }
  flyTo(lat, lon, z) { this.map.setView([lat, lon], z || this.map.getZoom()); }
  addLine(latlngs) { if (this.line) this.map.removeLayer(this.line); this.line = L.polyline(latlngs, { color: '#c2410c', weight: 3, dashArray: '6 6' }).addTo(this.map); }
}

export { fmtTime, fmtDateTime, arN };
