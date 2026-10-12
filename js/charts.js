// Hand-drawn charts (SVG and canvas) so the site has no chart dependency.
import { fmtDayHour, riyadhHour, rawNum } from './util.js';

const NS = 'http://www.w3.org/2000/svg';
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
function s(tag, attrs = {}, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}

function niceRange(lo, hi, zeroBase) {
  if (lo == null || hi == null) return [0, 1];
  if (zeroBase) lo = Math.min(0, lo);
  if (hi - lo < 1e-9) { hi = lo + 1; }
  const span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / 4)));
  const st = [1, 2, 2.5, 5, 10].map((m) => m * step).find((x) => span / x <= 5) || step * 10;
  return [Math.floor(lo / st) * st, Math.ceil(hi / st) * st, st, Math.min(2, Math.max(0, -Math.floor(Math.log10(st))))];
}

// Scrollable time series. series: [{label, values, color, kind:'line'|'bar', dash}]
export function timeSeries(host, { times, series, height = 170, pxPerHour = 9, unit = '', zeroBase = true, now = Date.now(), title }) {
  host.innerHTML = '';
  const vals = series.flatMap((x) => x.values || []).filter((v) => v != null);
  if (!times.length || !vals.length) { host.append(Object.assign(document.createElement('p'), { className: 'na', textContent: 'لا توجد بيانات لهذا المتغير من النماذج المختارة.' })); return; }
  const [lo, hi, step, dec] = niceRange(Math.min(...vals), Math.max(...vals), zeroBase);
  const W = Math.max(times.length * pxPerHour, 280), H = height, padT = 10, padB = 34;
  const y = (v) => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo));
  const x = (k) => k * pxPerHour + pxPerHour / 2;

  const wrap = document.createElement('div'); wrap.className = 'ts'; wrap.dir = 'ltr';
  const axis = s('svg', { width: 40, height: H, class: 'ts-axis', 'aria-hidden': 'true' });
  for (let v = lo; v <= hi + 1e-9; v += step) {
    axis.append(s('text', { x: 36, y: y(v) + 4, 'text-anchor': 'end', class: 'ts-tick' }, rawNum(v, dec)));
  }
  axis.append(s('text', { x: 4, y: H - 6, class: 'ts-unit' }, unit));
  const scroller = document.createElement('div'); scroller.className = 'ts-scroll';
  const svg = s('svg', { width: W, height: H, role: 'img', 'aria-label': title || 'مخطط زمني' });
  for (let v = lo; v <= hi + 1e-9; v += step) svg.append(s('line', { x1: 0, x2: W, y1: y(v), y2: y(v), class: 'ts-grid' }));
  times.forEach((t, k) => {
    const hr = riyadhHour(t);
    if (hr === 0) svg.append(s('line', { x1: x(k) - pxPerHour / 2, x2: x(k) - pxPerHour / 2, y1: padT, y2: H - padB + 4, class: 'ts-day' }));
    if (hr % 6 === 0) svg.append(s('text', { x: x(k), y: H - padB + 16, 'text-anchor': 'middle', class: 'ts-tick' }, String(hr).padStart(2, '0')));
    if (hr === 12) svg.append(s('text', { x: x(k), y: H - 4, 'text-anchor': 'middle', class: 'ts-daylabel' }, fmtDayHour(t).split(' ')[0]));
  });
  const nowK = times.findIndex((t) => t > now);
  if (nowK > 0) svg.append(s('line', { x1: x(nowK - 1), x2: x(nowK - 1), y1: padT, y2: H - padB, class: 'ts-now' }));

  const bars = series.filter((x) => x.kind === 'bar');
  const bw = Math.max(2, (pxPerHour - 2) / Math.max(1, bars.length));
  bars.forEach((ser, b) => ser.values.forEach((v, k) => {
    if (v == null || v <= 0) return;
    svg.append(s('rect', { x: k * pxPerHour + 1 + b * bw, y: y(v), width: bw, height: Math.max(1, y(lo < 0 ? 0 : lo) - y(v)), fill: ser.color, opacity: 0.85 }));
  }));
  for (const ser of series.filter((x) => x.kind !== 'bar')) {
    let d = '', pen = false;
    ser.values.forEach((v, k) => { if (v == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(k).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
    if (d) svg.append(s('path', { d, fill: 'none', stroke: ser.color, 'stroke-width': 2, 'stroke-dasharray': ser.dash || null, 'stroke-linejoin': 'round' }));
  }
  scroller.append(svg);
  wrap.append(axis, scroller);
  const legend = document.createElement('div'); legend.className = 'legend';
  for (const ser of series) {
    const it = document.createElement('span'); it.className = 'lg';
    it.innerHTML = `<i style="background:${ser.color}"></i>${ser.label}`;
    legend.append(it);
  }
  host.append(wrap, legend);
  // start scrolled near "now"
  requestAnimationFrame(() => { scroller.scrollLeft = Math.max(0, (nowK - 3) * pxPerHour); });
}

// RH colour ramp (dry brown -> moist teal -> saturated blue)
export function rhColor(rh) {
  if (rh == null) return null;
  const stops = [[0, [150, 100, 60]], [30, [205, 170, 110]], [50, [215, 215, 190]], [70, [110, 190, 175]], [85, [40, 140, 170]], [100, [25, 75, 160]]];
  for (let k = 1; k < stops.length; k++) if (rh <= stops[k][0]) {
    const [a, ca] = stops[k - 1], [b, cb] = stops[k], f = (rh - a) / (b - a);
    return `rgb(${ca.map((c, i) => Math.round(c + f * (cb[i] - c))).join(',')})`;
  }
  return 'rgb(25,75,160)';
}

function setupCanvas(canvas, cssW, cssH) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = cssW * dpr; canvas.height = cssH * dpr;
  canvas.style.width = cssW + 'px'; canvas.style.height = cssH + 'px';
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

// Time-height section of RH (shaded), 0 °C line and wind arrows. profiles: [{t, levels}]
export function timeHeight(host, { times, profiles, levels, pxPerHour = 9 }) {
  host.innerHTML = '';
  if (!profiles.length) return;
  const H = 230, padL = 40, padB = 26, padT = 8, W = padL + times.length * pxPerHour;
  const wrap = document.createElement('div'); wrap.className = 'ts'; wrap.dir = 'ltr';
  const scroller = document.createElement('div'); scroller.className = 'ts-scroll';
  const canvas = document.createElement('canvas');
  scroller.append(canvas); wrap.append(scroller); host.append(wrap);
  const ctx = setupCanvas(canvas, W, H);
  const ink = css('--ink'), muted = css('--muted'), line = css('--line'), under = css('--under');
  const lp = (p) => Math.log(p);
  const yP = (p) => padT + (H - padT - padB) * (lp(1000) - lp(p)) / (lp(1000) - lp(300));
  ctx.font = '11px system-ui'; ctx.fillStyle = muted;
  // cells
  profiles.forEach((pr, k) => {
    levels.forEach((p, li) => {
      const L = pr.levels.find((l) => l.p === p); if (!L) return;
      const pTop = li < levels.length - 1 ? Math.sqrt(p * levels[li + 1]) : 300;
      const pBot = li > 0 ? Math.sqrt(p * levels[li - 1]) : 1000;
      ctx.fillStyle = L.under ? under : (rhColor(L.rh) || line);
      ctx.fillRect(padL + k * pxPerHour, yP(pBot), pxPerHour + 0.5, yP(pTop) - yP(pBot));
    });
  });
  // 0 °C isotherm
  ctx.strokeStyle = '#d33'; ctx.lineWidth = 1.5; ctx.beginPath(); let pen = false;
  profiles.forEach((pr, k) => {
    const ls = pr.levels.filter((l) => !l.under && l.tC != null).sort((a, b) => b.p - a.p);
    let pz = null;
    for (let j = 1; j < ls.length; j++) if (ls[j - 1].tC >= 0 && ls[j].tC < 0) {
      const f = ls[j - 1].tC / (ls[j - 1].tC - ls[j].tC); pz = Math.exp(lp(ls[j - 1].p) + f * (lp(ls[j].p) - lp(ls[j - 1].p))); break;
    }
    if (pz == null) { pen = false; return; }
    const X = padL + k * pxPerHour + pxPerHour / 2, Y = yP(pz);
    if (pen) ctx.lineTo(X, Y); else ctx.moveTo(X, Y); pen = true;
  });
  ctx.stroke();
  // wind arrows every 3 h (direction the wind blows toward)
  ctx.strokeStyle = ink; ctx.lineWidth = 1.1;
  profiles.forEach((pr, k) => {
    if (k % 3) return;
    for (const L of pr.levels) {
      if (L.under || L.u == null) continue;
      const X = padL + k * pxPerHour + pxPerHour / 2, Y = yP(L.p), len = Math.min(13, 3 + L.ws * 0.6);
      const sp = Math.hypot(L.u, L.v) || 1, dx = (L.u / sp) * len, dy = -(L.v / sp) * len;
      ctx.beginPath(); ctx.moveTo(X - dx / 2, Y - dy / 2); ctx.lineTo(X + dx / 2, Y + dy / 2); ctx.stroke();
      const a = Math.atan2(dy, dx); ctx.beginPath();
      ctx.moveTo(X + dx / 2, Y + dy / 2); ctx.lineTo(X + dx / 2 - 4 * Math.cos(a - 0.5), Y + dy / 2 - 4 * Math.sin(a - 0.5));
      ctx.moveTo(X + dx / 2, Y + dy / 2); ctx.lineTo(X + dx / 2 - 4 * Math.cos(a + 0.5), Y + dy / 2 - 4 * Math.sin(a + 0.5)); ctx.stroke();
    }
  });
  // axes
  ctx.fillStyle = css('--surface'); ctx.fillRect(0, 0, padL - 2, H);
  ctx.fillStyle = muted; ctx.textAlign = 'right';
  for (const p of levels) ctx.fillText(String(p), padL - 6, yP(p) + 4);
  ctx.textAlign = 'center';
  times.forEach((t, k) => { const hr = riyadhHour(t); if (hr % 6 === 0) ctx.fillText(String(hr).padStart(2, '0'), padL + k * pxPerHour + pxPerHour / 2, H - 8); });
  requestAnimationFrame(() => { const nowK = times.findIndex((t) => t > Date.now()); scroller.scrollLeft = Math.max(0, (nowK - 3) * pxPerHour); });
}

// Skew-T / log-p diagram for one profile, with a surface-parcel path.
export function skewT(host, { profile, parcel, title }) {
  host.innerHTML = '';
  const W = Math.min(host.clientWidth || 340, 520), H = Math.round(W * 1.05);
  const canvas = document.createElement('canvas'); host.dir = 'ltr'; host.append(canvas);
  const ctx = setupCanvas(canvas, W, H);
  const pBot = 1050, pTop = 250, padL = 34, padB = 22, padT = 8, padR = 8;
  // Isotherms lean 70 °C to the right between the bottom and the top of the plot.
  const tMin = -40, tMax = 50, skewC = 70;
  const frac = (p) => Math.log(pBot / p) / Math.log(pBot / pTop);
  const yP = (p) => padT + (H - padT - padB) * frac(p);
  const xT = (t, p) => padL + (W - padL - padR) * ((t + skewC * frac(p)) - tMin) / (tMax - tMin);
  const line = css('--line'), muted = css('--muted'), surface = css('--surface');
  ctx.fillStyle = surface; ctx.fillRect(0, 0, W, H);
  ctx.save(); ctx.beginPath(); ctx.rect(padL, padT, W - padL - padR, H - padT - padB); ctx.clip();
  // isobars
  ctx.strokeStyle = line; ctx.lineWidth = 1;
  for (const p of [1000, 925, 850, 700, 600, 500, 400, 300]) { ctx.beginPath(); ctx.moveTo(padL, yP(p)); ctx.lineTo(W - padR, yP(p)); ctx.stroke(); }
  // skewed isotherms
  for (let t = -100; t <= 50; t += 10) {
    ctx.strokeStyle = t === 0 ? 'rgba(80,140,220,.7)' : line; ctx.beginPath(); ctx.moveTo(xT(t, pBot), yP(pBot)); ctx.lineTo(xT(t, pTop), yP(pTop)); ctx.stroke();
  }
  // dry adiabats
  ctx.strokeStyle = 'rgba(190,120,60,.28)';
  for (let th = 250; th <= 450; th += 10) {
    ctx.beginPath(); let first = true;
    for (let p = pBot; p >= pTop; p -= 10) { const t = th * Math.pow(p / 1000, 0.2857) - 273.15; const X = xT(t, p), Y = yP(p); if (first) ctx.moveTo(X, Y); else ctx.lineTo(X, Y); first = false; }
    ctx.stroke();
  }
  // under-ground band
  if (profile.sfc.p) { ctx.fillStyle = css('--under'); ctx.fillRect(padL, yP(profile.sfc.p), W, H); }
  const plot = (pts, color, width, dash) => {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash || []); ctx.beginPath(); let first = true;
    for (const q of pts) { if (q.t == null) continue; const X = xT(q.t, q.p), Y = yP(q.p); if (first) ctx.moveTo(X, Y); else ctx.lineTo(X, Y); first = false; }
    ctx.stroke(); ctx.setLineDash([]);
  };
  const lv = profile.levels.filter((l) => !l.under).sort((a, b) => b.p - a.p);
  const sfcPt = profile.sfc.p ? [{ p: profile.sfc.p, t: profile.sfc.tC, d: profile.sfc.tdC }] : [];
  const tPts = sfcPt.map((q) => ({ p: q.p, t: q.t })).concat(lv.map((l) => ({ p: l.p, t: l.tC })));
  const dPts = sfcPt.map((q) => ({ p: q.p, t: q.d })).concat(lv.map((l) => ({ p: l.p, t: l.tdC })));
  if (parcel && parcel.length) plot(parcel.map((q) => ({ p: q.p, t: q.tC })), 'rgba(120,120,120,.9)', 1.5, [5, 4]);
  plot(dPts, css('--dew'), 2.5);
  plot(tPts, css('--temp'), 2.5);
  ctx.restore();
  // labels
  ctx.fillStyle = muted; ctx.font = '11px system-ui'; ctx.textAlign = 'right';
  for (const p of [1000, 850, 700, 500, 300]) ctx.fillText(String(p), padL - 4, yP(p) + 4);
  ctx.textAlign = 'center';
  for (let t = -30; t <= 40; t += 10) { const X = xT(t, pBot); if (X > padL && X < W - padR) ctx.fillText(`${t}°`, X, H - 6); }
  // wind column at right edge
  ctx.strokeStyle = css('--ink'); ctx.lineWidth = 1.2;
  for (const l of lv) {
    if (l.u == null) continue;
    const X = W - padR - 14, Y = yP(l.p), sp = Math.hypot(l.u, l.v) || 1, len = Math.min(14, 4 + l.ws * 0.6);
    const dx = (l.u / sp) * len, dy = -(l.v / sp) * len;
    ctx.beginPath(); ctx.moveTo(X - dx / 2, Y - dy / 2); ctx.lineTo(X + dx / 2, Y + dy / 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(X + dx / 2, Y + dy / 2, 1.8, 0, 7); ctx.fill();
  }
  if (title) { ctx.textAlign = 'left'; ctx.fillStyle = css('--ink'); ctx.fillText(title, padL + 6, padT + 12); }
}

// Vertical cross-section along a line: RH shading by height, terrain from the DEM.
export function crossSection(host, { dist, terrain, cols, labels }) {
  host.innerHTML = '';
  const W = Math.max(host.clientWidth || 340, 320), H = 260, padL = 40, padB = 30, padT = 8, padR = 8;
  const canvas = document.createElement('canvas'); host.dir = 'ltr'; host.append(canvas);
  const ctx = setupCanvas(canvas, W, H);
  const zMax = 7000, dMax = dist[dist.length - 1] || 1;
  const xD = (d) => padL + (W - padL - padR) * d / dMax;
  const yZ = (z) => padT + (H - padT - padB) * (1 - z / zMax);
  ctx.fillStyle = css('--surface'); ctx.fillRect(0, 0, W, H);
  // RH columns
  cols.forEach((c, k) => {
    const x0 = k === 0 ? 0 : (c.d + cols[k - 1].d) / 2, x1 = k === cols.length - 1 ? dMax : (c.d + cols[k + 1].d) / 2;
    const ls = c.levels.filter((l) => !l.under && l.z != null && l.rh != null).sort((a, b) => a.z - b.z);
    ls.forEach((l, j) => {
      const z0 = j === 0 ? 0 : (l.z + ls[j - 1].z) / 2, z1 = j === ls.length - 1 ? zMax : (l.z + ls[j + 1].z) / 2;
      ctx.fillStyle = rhColor(l.rh); ctx.fillRect(xD(x0), yZ(z1), xD(x1) - xD(x0) + 0.5, yZ(z0) - yZ(z1));
    });
  });
  // along-section wind arrows
  ctx.strokeStyle = css('--ink'); ctx.lineWidth = 1.2;
  cols.forEach((c) => c.levels.forEach((l) => {
    if (l.under || l.along == null || l.z == null || l.z > zMax) return;
    const X = xD(c.d), Y = yZ(l.z), len = Math.max(-16, Math.min(16, l.along * 0.9));
    ctx.beginPath(); ctx.moveTo(X - len / 2, Y); ctx.lineTo(X + len / 2, Y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(X + len / 2, Y); ctx.lineTo(X + len / 2 - Math.sign(len) * 4, Y - 3); ctx.moveTo(X + len / 2, Y); ctx.lineTo(X + len / 2 - Math.sign(len) * 4, Y + 3); ctx.stroke();
  }));
  // terrain
  ctx.fillStyle = css('--terrain'); ctx.beginPath(); ctx.moveTo(xD(0), yZ(0));
  dist.forEach((d, k) => ctx.lineTo(xD(d), yZ(Math.max(0, terrain[k] || 0))));
  ctx.lineTo(xD(dMax), yZ(0)); ctx.closePath(); ctx.fill();
  // axes
  ctx.fillStyle = css('--muted'); ctx.font = '11px system-ui'; ctx.textAlign = 'right';
  for (let z = 0; z <= zMax; z += 1000) ctx.fillText(`${z / 1000}`, padL - 5, yZ(z) + 4);
  ctx.save(); ctx.translate(10, H / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText('km', 0, 0); ctx.restore();
  ctx.textAlign = 'center'; ctx.fillStyle = css('--ink');
  for (const lb of labels || []) { const X = xD(lb.d); ctx.fillText(lb.name, Math.min(Math.max(X, padL + 20), W - 24), H - 10); ctx.fillRect(X - 0.5, yZ(0), 1, 4); }
}
