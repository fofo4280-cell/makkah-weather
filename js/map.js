// Leaflet map: base maps, reference layers, observations, forecast grids.
/* global L */
import { PLACES, TERRAIN_LABELS, ENDPOINTS, METAR_STATIONS } from './config.js';
import { fetchRadarFrames, fetchSatTime, fetchGrid, fetchElevation, gridPoints, fetchMetars } from './api.js';
import { divergence, orographicW, uv, specHum, dewpoint } from './met.js';
import { rhColor } from './charts.js';
import { fmtTime, fmtDateTime, num, dirName, sum } from './util.js';

export const BASES = {
  topo: { label: 'تضاريس (OpenTopoMap)', url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', opts: { maxZoom: 17, subdomains: 'abc', attribution: 'خريطة: © OpenTopoMap (CC-BY-SA)، بيانات © OpenStreetMap، ارتفاعات SRTM' } },
  sat: { label: 'قمر صناعي (Esri)', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', opts: { maxZoom: 18, attribution: 'صور: Esri, Maxar, Earthstar Geographics' } },
  shade: { label: 'ظل تضاريسي (Esri)', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}', opts: { maxZoom: 16, attribution: 'ظل تضاريسي: Esri' } },
  osm: { label: 'شوارع (OpenStreetMap)', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', opts: { maxZoom: 19, attribution: '© OpenStreetMap' } },
};

export const FIELDS = {
  precip: { label: 'الهطول المتوقع', unit: 'مم', group: 'rain' },
  cape: { label: 'CAPE', unit: 'J/kg', group: 'inst' },
  li: { label: 'Lifted Index', unit: '', group: 'inst' },
  cin: { label: 'CIN (القيمة المطلقة)', unit: 'J/kg', group: 'inst' },
  rh700: { label: 'الرطوبة النسبية 700 hPa', unit: '٪', group: 'moist' },
  rh925: { label: 'الرطوبة النسبية 925 hPa', unit: '٪', group: 'moist' },
  qflux: { label: 'تدفق الرطوبة 925 hPa', unit: 'غ/كغ·م/ث', group: 'moist' },
  wind10: { label: 'رياح 10 م', unit: 'كم/س', group: 'wind' },
  wind925: { label: 'رياح 925 hPa', unit: 'كم/س', group: 'wind' },
  conv: { label: 'التقارب/التباعد قرب السطح', unit: '×10⁻⁵ ث⁻¹', group: 'lift' },
  vv700: { label: 'الحركة الرأسية 700 hPa', unit: '', group: 'lift' },
  oro: { label: 'الرفع التضاريسي (رياح 10 م × ميل الأرض)', unit: 'سم/ث', group: 'lift' },
  agree: { label: 'اتفاق النماذج على المطر', unit: 'نماذج', group: 'rain' },
};

const scales = {
  precip: [[0.1, '#cfe8f3'], [0.5, '#8cc9e6'], [1, '#4aa3d8'], [2, '#2f6fc0'], [5, '#4d3fb0'], [10, '#8a2fa8'], [20, '#c0268a'], [50, '#e0245e']],
  cape: [[100, '#f6eab0'], [300, '#f3d06a'], [600, '#f0a33c'], [1000, '#e2622a'], [1500, '#c4302b'], [2500, '#8e1a5c']],
  cin: [[25, '#d9d9d9'], [50, '#b3b3b3'], [100, '#7f7f7f'], [200, '#4d4d4d']],
  agree: [[1, '#9fd3c7'], [2, '#3c9d9b'], [3, '#1d4e89']],
};
function stepColor(scale, v) { let c = null; for (const [t, col] of scale) if (v >= t) c = col; return c; }
function liColor(v) { if (v == null || v > 1) return null; if (v > -1) return '#f6eab0'; if (v > -3) return '#f0a33c'; if (v > -5) return '#e2622a'; if (v > -7) return '#c4302b'; return '#8e1a5c'; }
function divColor(d) { if (d == null) return null; const x = d * 1e5; if (x <= -3) return '#b2182b'; if (x <= -1.5) return '#ef8a62'; if (x <= -0.5) return '#fddbc7'; if (x >= 3) return '#2166ac'; if (x >= 1.5) return '#67a9cf'; if (x >= 0.5) return '#d1e5f0'; return null; }
function wColor(w) { if (w == null) return null; if (w >= 0.2) return '#b2182b'; if (w >= 0.08) return '#ef8a62'; if (w >= 0.03) return '#fddbc7'; if (w <= -0.2) return '#2166ac'; if (w <= -0.08) return '#67a9cf'; if (w <= -0.03) return '#d1e5f0'; return null; }

export const LEGENDS = {
  precip: scales.precip.map(([t, c]) => [c, `≥${t}`]),
  cape: scales.cape.map(([t, c]) => [c, `≥${t}`]),
  cin: scales.cin.map(([t, c]) => [c, `≥${t}`]),
  li: [['#f6eab0', '≤1'], ['#f0a33c', '≤-1'], ['#e2622a', '≤-3'], ['#c4302b', '≤-5'], ['#8e1a5c', '≤-7']],
  rh700: [[rhColor(20), '20'], [rhColor(40), '40'], [rhColor(60), '60'], [rhColor(80), '80'], [rhColor(95), '95']],
  rh925: [[rhColor(20), '20'], [rhColor(40), '40'], [rhColor(60), '60'], [rhColor(80), '80'], [rhColor(95), '95']],
  conv: [['#b2182b', 'تقارب قوي'], ['#ef8a62', 'تقارب'], ['#67a9cf', 'تباعد'], ['#2166ac', 'تباعد قوي']],
  vv700: [['#b2182b', 'صعود ≥0.2 م/ث'], ['#ef8a62', 'صعود'], ['#67a9cf', 'هبوط'], ['#2166ac', 'هبوط ≥0.2']],
  oro: [['#b2182b', 'صعود منحدر قوي'], ['#ef8a62', 'صعود منحدر'], ['#67a9cf', 'نزول منحدر'], ['#2166ac', 'نزول قوي']],
  agree: [['#9fd3c7', 'نموذج'], ['#3c9d9b', 'نموذجان'], ['#1d4e89', '3 نماذج']],
  qflux: [['var(--sea)', 'طول السهم = شدة التدفق']],
  wind10: [['var(--ink)', 'سهم نحو اتجاه الهبوب']],
  wind925: [['var(--ink)', 'سهم نحو اتجاه الهبوب']],
};

const SAT_LAYERS = {
  ir_iodc: { label: 'أشعة تحت حمراء 10.8 – Meteosat (المحيط الهندي)', layer: 'msg_iodc:ir108' },
  ir_mtg: { label: 'أشعة تحت حمراء 10.5 – MTG (0°)', layer: 'mtg_fd:ir105_hrfi' },
  cth: { label: 'ارتفاع قمم السحب – Meteosat (المحيط الهندي)', layer: 'msg_iodc:cth' },
  lightning: { label: 'البرق – MTG Lightning Imager (مساحة الومضات المتراكمة)', layer: 'mtg_fd:li_afa' },
};
export { SAT_LAYERS };

export class WxMap {
  constructor(el, { onPick, onStatus }) {
    this.onPick = onPick; this.onStatus = onStatus || (() => {});
    this.map = L.map(el, { zoomControl: false, attributionControl: true, minZoom: 5, maxZoom: 15, tap: true }).setView([21.5, 40.0], 8);
    L.control.zoom({ position: 'topleft' }).addTo(this.map);
    this.map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
    this.renderer = L.canvas({ padding: 0.3 });
    this.bases = {}; for (const [k, b] of Object.entries(BASES)) this.bases[k] = L.tileLayer(b.url, b.opts);
    this.base = 'topo'; this.bases.topo.addTo(this.map);
    this.overlays = {
      ref: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: 'حدود وأسماء: Esri' }),
      shade: L.tileLayer(BASES.shade.url, { ...BASES.shade.opts, opacity: 0.35 }),
      places: this._placesLayer(),
      labels: this._terrainLabels(),
    };
    this.overlays.places.addTo(this.map);
    this.obs = {}; this.sat = {}; this.satTimes = {};
    this.field = null; this.fieldLayer = L.layerGroup().addTo(this.map); this.arrowLayer = L.layerGroup().addTo(this.map);
    this.pickMarker = null; this.grids = {}; this.dem = {};
    this.map.on('click', (e) => this._click(e));
  }

  _placesLayer() {
    const g = L.layerGroup();
    for (const p of PLACES) {
      L.circleMarker([p.lat, p.lon], { radius: 5, color: '#fff', weight: 2, fillColor: '#0f6e7a', fillOpacity: 1 })
        .bindTooltip(p.name, { permanent: true, direction: 'top', offset: [0, -6], className: 'map-label' })
        .on('click', (e) => { L.DomEvent.stopPropagation(e); this.onPick({ ...p }); })
        .addTo(g);
    }
    return g;
  }
  _terrainLabels() {
    const g = L.layerGroup();
    for (const t of TERRAIN_LABELS) L.marker([t.lat, t.lon], { icon: L.divIcon({ className: 'terrain-label', html: `<span>${t.name}</span>`, iconSize: null }) , interactive: false }).addTo(g);
    return g;
  }

  setBase(k) { if (k === this.base) return; this.map.removeLayer(this.bases[this.base]); this.bases[k].addTo(this.map); this.bases[k].bringToBack(); this.base = k; }
  toggleOverlay(k, on) { const l = this.overlays[k]; if (!l) return; if (on) l.addTo(this.map); else this.map.removeLayer(l); }

  // ---------- observations ----------
  async toggleRadar(on, { coverage = false } = {}) {
    if (this.radarTimer) { clearInterval(this.radarTimer); this.radarTimer = null; }
    for (const l of [this.obs.radar, this.obs.radarCov]) if (l) this.map.removeLayer(l);
    this.obs.radar = this.obs.radarCov = null;
    if (!on) return null;
    const r = await fetchRadarFrames({ force: true });
    if (!r.frames.length) throw new Error('لا توجد إطارات رادار حديثة');
    this.radar = r; this.radarIdx = r.frames.length - 1;
    this.obs.radar = L.tileLayer(this._radarUrl(this.radarIdx), { opacity: 0.8, maxNativeZoom: 7, maxZoom: 15, attribution: 'رادار: RainViewer' }).addTo(this.map);
    if (coverage) this.obs.radarCov = L.tileLayer(`${r.host}/v2/coverage/0/256/{z}/{x}/{y}/0/0_0.png`, { opacity: 0.35, maxNativeZoom: 7, maxZoom: 15 }).addTo(this.map);
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
    const layer = L.tileLayer.wms(ENDPOINTS.eumetview, { layers: def.layer, format: 'image/png', transparent: true, version: '1.3.0', opacity: key === 'lightning' ? 0.95 : 0.7, attribution: 'أقمار: EUMETSAT EUMETView', maxZoom: 15 });
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

  // ---------- forecast grids ----------
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

  // Compute a 2-D array for a field at time index ti (window = hours for precip).
  async computeField(name, gridKey, modelKey, ti, windowH, th) {
    if (name === 'agree') {
      const grids = await Promise.allSettled(['ecmwf', 'gfs', 'icon'].map((m) => this.loadGrid(gridKey, m)));
      const ok = grids.filter((g) => g.status === 'fulfilled').map((g) => g.value);
      if (!ok.length) throw new Error('تعذر جلب أي نموذج');
      const G = ok[0];
      const vals = G.lats.map((_, j) => G.lons.map((__, i) => {
        let n = 0, have = 0;
        for (const g of ok) { const a = g.fields.precipitation && g.fields.precipitation[j][i]; if (!a) continue; have++; if (sum(a.slice(ti, ti + windowH)) >= th.rainAgree) n++; }
        return have ? n : null;
      }));
      return { G, vals, note: `${ok.length} من 3 نماذج متاحة؛ عتبة ${th.rainAgree} مم خلال ${windowH} ساعة` };
    }
    const G = await this.loadGrid(gridKey, modelKey);
    const F = G.fields; const at = (v, j, i) => (F[v] && F[v][j][i] ? F[v][j][i][ti] : null);
    const ps = (j, i) => at('surface_pressure', j, i);
    const above = (p, j, i) => { const s = ps(j, i); return s == null || s > p + 5; };
    let vals, arrows = null, note = '';
    const map2 = (fn) => G.lats.map((_, j) => G.lons.map((__, i) => fn(j, i)));
    switch (name) {
      case 'precip': vals = map2((j, i) => (F.precipitation && F.precipitation[j][i] ? sum(F.precipitation[j][i].slice(ti, ti + windowH)) : null)); note = `مجموع ${windowH} ساعة يبدأ من الوقت المختار`; break;
      case 'cape': vals = map2((j, i) => at('cape', j, i)); break;
      case 'li': vals = map2((j, i) => at('lifted_index', j, i)); break;
      case 'cin': vals = map2((j, i) => { const v = at('convective_inhibition', j, i); return v == null ? null : Math.abs(v); }); break;
      case 'rh700': vals = map2((j, i) => (above(700, j, i) ? at('relative_humidity_700hPa', j, i) : null)); break;
      case 'rh925': vals = map2((j, i) => (above(925, j, i) ? at('relative_humidity_925hPa', j, i) : null)); note = 'الخلايا الفارغة: 925 hPa تحت سطح الأرض'; break;
      case 'wind10': case 'wind925': {
        const lv = name === 'wind10' ? '10m' : '925hPa';
        arrows = map2((j, i) => (name === 'wind925' && !above(925, j, i) ? null : { s: at(`wind_speed_${lv}`, j, i), d: at(`wind_direction_${lv}`, j, i) }));
        vals = null; break;
      }
      case 'qflux': {
        arrows = map2((j, i) => {
          if (!above(925, j, i)) return null;
          const t = at('temperature_925hPa', j, i), rh = at('relative_humidity_925hPa', j, i), s = at('wind_speed_925hPa', j, i), d = at('wind_direction_925hPa', j, i);
          if ([t, rh, s, d].some((x) => x == null)) return null;
          const q = specHum(dewpoint(t, rh), 925) * 1000; return { s: q * s, d, q };
        });
        vals = null; note = 'q × سرعة الرياح عند 925 hPa'; break;
      }
      case 'conv': {
        const useLv = gridKey === 'region' ? '925hPa' : '10m';
        const U = map2((j, i) => (useLv === '925hPa' && !above(925, j, i) ? null : uv(at(`wind_speed_${useLv}`, j, i), at(`wind_direction_${useLv}`, j, i))[0]));
        const V = map2((j, i) => (useLv === '925hPa' && !above(925, j, i) ? null : uv(at(`wind_speed_${useLv}`, j, i), at(`wind_direction_${useLv}`, j, i))[1]));
        vals = divergence(U, V, G.lats, G.lons);
        note = `محسوب من رياح ${useLv === '10m' ? '10 م' : '925 hPa'} بفروق مركزية على شبكة ${G.lats.length > 1 ? (G.lats[1] - G.lats[0]).toFixed(2) : ''}°`;
        break;
      }
      case 'vv700': {
        const unit = G.units['vertical_velocity_700hPa'] || '';
        const conv = /pa/i.test(unit) ? (x) => -x / 8.8 : (x) => x;
        vals = map2((j, i) => { const v = at('vertical_velocity_700hPa', j, i); return v == null || !above(700, j, i) ? null : conv(v); });
        note = `w موجب = صعود (الوحدة الأصلية من المصدر: ${unit || 'غير محددة'})`; break;
      }
      case 'oro': {
        const H = await this.loadDem(gridKey);
        const U = map2((j, i) => uv(at('wind_speed_10m', j, i), at('wind_direction_10m', j, i))[0]);
        const V = map2((j, i) => uv(at('wind_speed_10m', j, i), at('wind_direction_10m', j, i))[1]);
        vals = orographicW(U, V, H, G.lats, G.lons);
        note = 'w = V₁₀ · ∇h، الارتفاعات من Copernicus DEM على شبكة الحقل نفسها (تقدير خشن)'; break;
      }
      default: vals = null;
    }
    return { G, vals, arrows, note };
  }

  colorFor(name, v, th) {
    if (v == null) return null;
    switch (name) {
      case 'precip': return stepColor(scales.precip, v);
      case 'cape': return stepColor(scales.cape, v);
      case 'cin': return stepColor(scales.cin, v);
      case 'li': return liColor(v);
      case 'rh700': case 'rh925': return rhColor(v);
      case 'conv': return divColor(v);
      case 'vv700': case 'oro': return wColor(v);
      case 'agree': return v ? stepColor(scales.agree, v) : null;
      default: return null;
    }
  }

  drawField(name, res, th, units) {
    this.fieldLayer.clearLayers(); this.arrowLayer.clearLayers();
    this.current = { name, res };
    const { G, vals, arrows } = res; const half = (G.lats[1] - G.lats[0]) / 2;
    if (vals) {
      G.lats.forEach((la, j) => G.lons.forEach((lo, i) => {
        const v = vals[j][i]; const c = this.colorFor(name, v, th); if (!c) return;
        L.rectangle([[la - half, lo - half], [la + half, lo + half]], { renderer: this.renderer, stroke: false, fillColor: c, fillOpacity: 0.55, interactive: false }).addTo(this.fieldLayer);
      }));
    }
    if (arrows) {
      const maxS = Math.max(1, ...arrows.flat().filter(Boolean).map((a) => a.s || 0));
      G.lats.forEach((la, j) => G.lons.forEach((lo, i) => {
        const a = arrows[j][i]; if (!a || a.s == null || a.d == null) return;
        const len = 10 + 22 * Math.min(1, a.s / maxS);
        const rot = (a.d + 180) % 360; // blowing toward
        const color = name === 'qflux' ? 'var(--sea)' : 'var(--ink)';
        const html = `<svg width="40" height="40" viewBox="-20 -20 40 40" style="transform:rotate(${rot}deg)"><line x1="0" y1="${len / 2}" x2="0" y2="${-len / 2}" style="stroke:${color};stroke-width:2.2"/><path d="M0 ${-len / 2 - 2} l-4 7 h8z" style="fill:${color}"/></svg>`;
        L.marker([la, lo], { icon: L.divIcon({ className: 'arrow', html, iconSize: [40, 40], iconAnchor: [20, 20] }), interactive: false }).addTo(this.arrowLayer);
      }));
    }
  }
  clearField() { this.fieldLayer.clearLayers(); this.arrowLayer.clearLayers(); this.current = null; }

  valueAt(lat, lon) {
    if (!this.current) return null;
    const { G, vals, arrows } = this.current.res;
    const j = Math.round((lat - G.lats[0]) / (G.lats[1] - G.lats[0])), i = Math.round((lon - G.lons[0]) / (G.lons[1] - G.lons[0]));
    if (j < 0 || i < 0 || j >= G.lats.length || i >= G.lons.length) return null;
    return { v: vals ? vals[j][i] : null, a: arrows ? arrows[j][i] : null, la: G.lats[j], lo: G.lons[i] };
  }

  _click(e) {
    const { lat, lng } = e.latlng;
    if (this.pickMarker) this.map.removeLayer(this.pickMarker);
    this.pickMarker = L.circleMarker([lat, lng], { radius: 7, color: '#fff', weight: 2, fillColor: '#c2410c', fillOpacity: 1 }).addTo(this.map);
    this.onPick({ id: 'custom', name: `نقطة ${lat.toFixed(2)}°ش ${lng.toFixed(2)}°ق`, lat, lon: lng, custom: true }, { fromMap: true, latlng: e.latlng });
  }
  popup(latlng, html) { L.popup({ maxWidth: 260 }).setLatLng(latlng).setContent(html).openOn(this.map); }
  invalidate() { setTimeout(() => this.map.invalidateSize(), 50); }
  flyTo(lat, lon, z) { this.map.setView([lat, lon], z || this.map.getZoom()); }
  addLine(latlngs) { if (this.line) this.map.removeLayer(this.line); this.line = L.polyline(latlngs, { color: '#c2410c', weight: 3, dashArray: '6 6' }).addTo(this.map); }
}

export { fmtTime, fmtDateTime };
