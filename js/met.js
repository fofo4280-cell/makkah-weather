// Thermodynamics and kinematics used by the panels. Formulas are documented on the
// Sources page so every derived number can be traced.

const RD = 287.04, CP = 1005.7, LV = 2.501e6, EPS = 0.622, G = 9.80665;
const rad = (d) => (d * Math.PI) / 180;

export function satVap(tC) { return 6.112 * Math.exp((17.67 * tC) / (tC + 243.5)); } // hPa (Bolton 1980)
export function dewpoint(tC, rh) {
  if (tC == null || rh == null || rh <= 0) return null;
  const a = 17.625, b = 243.04; const g = Math.log(Math.min(rh, 100) / 100) + (a * tC) / (b + tC);
  return (b * g) / (a - g); // Magnus (Alduchov & Eskridge 1996)
}
export function mixingRatio(tdC, pHpa) { const e = satVap(tdC); return (EPS * e) / (pHpa - e); } // kg/kg
export function specHum(tdC, pHpa) { const w = mixingRatio(tdC, pHpa); return w / (1 + w); }

export function uv(speed, dirFrom) {
  if (speed == null || dirFrom == null) return [null, null];
  return [-speed * Math.sin(rad(dirFrom)), -speed * Math.cos(rad(dirFrom))];
}
export function dirFromUV(u, v) { return (Math.atan2(-u, -v) * 180 / Math.PI + 360) % 360; }
export function speedUV(u, v) { return Math.hypot(u, v); }

// Bolton (1980) LCL temperature; pressure from Poisson; height ~ 125 m/K.
export function lcl(tC, tdC, pHpa) {
  if (tC == null || tdC == null) return null;
  const T = tC + 273.15, Td = tdC + 273.15;
  const Tl = 1 / (1 / (Td - 56) + Math.log(T / Td) / 800) + 56;
  const p = pHpa != null ? pHpa * Math.pow(Tl / T, 1 / 0.2857) : null;
  return { tC: Tl - 273.15, p, zAgl: Math.max(0, 125 * (tC - tdC)) };
}

// Pseudo-adiabatic lapse rate dT/dp (K/hPa).
function moistDTdp(TK, pHpa) {
  const rs = mixingRatio(TK - 273.15, pHpa);
  const num = (RD * TK + LV * rs) / pHpa;
  const den = CP + (LV * LV * rs * EPS) / (RD * TK * TK);
  return num / den;
}

// Surface parcel: dry adiabat to LCL, then moist adiabat. Returns [{p, tC}].
export function parcelPath(tC, tdC, pSfc, pTop = 250) {
  const L = lcl(tC, tdC, pSfc);
  if (!L || L.p == null) return [];
  const out = [];
  const T0 = tC + 273.15;
  for (let p = pSfc; p > L.p; p -= 10) out.push({ p, tC: T0 * Math.pow(p / pSfc, 0.2857) - 273.15 });
  out.push({ p: L.p, tC: L.tC });
  let T = L.tC + 273.15, p = L.p;
  while (p > pTop) {
    const dp = Math.min(5, p - pTop);
    // midpoint integration
    const k1 = moistDTdp(T, p);
    const Tm = T - k1 * dp / 2;
    const k2 = moistDTdp(Tm, p - dp / 2);
    T -= k2 * dp; p -= dp;
    out.push({ p, tC: T - 273.15 });
  }
  return out;
}

const pick = (h, key, i) => (h[key] && h[key][i] != null ? h[key][i] : null);

// Build a profile from Open-Meteo hourly arrays (single model) at index i.
// Levels below the model surface pressure are flagged and excluded from analysis.
export function buildProfile(h, i, levels, elevation) {
  const psfc = pick(h, 'surface_pressure', i);
  const sfc = {
    p: psfc, z: elevation,
    tC: pick(h, 'temperature_2m', i), rh: pick(h, 'relative_humidity_2m', i),
    tdC: pick(h, 'dew_point_2m', i),
    ws: pick(h, 'wind_speed_10m', i), wd: pick(h, 'wind_direction_10m', i), gust: pick(h, 'wind_gusts_10m', i),
  };
  if (sfc.tdC == null && sfc.tC != null && sfc.rh != null) sfc.tdC = dewpoint(sfc.tC, sfc.rh);
  const lv = levels.map((p) => {
    const tC = pick(h, `temperature_${p}hPa`, i), rh = pick(h, `relative_humidity_${p}hPa`, i);
    const ws = pick(h, `wind_speed_${p}hPa`, i), wd = pick(h, `wind_direction_${p}hPa`, i);
    const [u, v] = uv(ws, wd);
    return {
      p, z: pick(h, `geopotential_height_${p}hPa`, i), tC, rh, tdC: dewpoint(tC, rh), ws, wd, u, v,
      vv: pick(h, `vertical_velocity_${p}hPa`, i),
      under: psfc != null ? p > psfc - 5 : false,
    };
  });
  return {
    sfc, levels: lv,
    cape: pick(h, 'cape', i), cin: pick(h, 'convective_inhibition', i), li: pick(h, 'lifted_index', i),
    fzl: pick(h, 'freezing_level_height', i), blh: pick(h, 'boundary_layer_height', i),
    pw: pick(h, 'total_column_integrated_water_vapour', i),
    precip: pick(h, 'precipitation', i), cloud: pick(h, 'cloud_cover', i),
  };
}

export function level(profile, p) { return profile.levels.find((l) => l.p === p) || null; }
const above = (l) => l && !l.under && l.tC != null;

// Derived diagnostics for one profile. Every field may be null.
export function diagnostics(pr) {
  const d = {};
  const L7 = level(pr, 700), L6 = level(pr, 600), L5 = level(pr, 500), L85 = level(pr, 850), L92 = level(pr, 925);
  d.t500 = above(L5) ? L5.tC : null;
  d.t700 = above(L7) ? L7.tC : null;
  d.z700 = L7 && !L7.under ? L7.z : null;
  d.rh = {}; for (const l of pr.levels) d.rh[l.p] = !l.under ? l.rh : null;
  d.dd700 = above(L7) && L7.tdC != null ? L7.tC - L7.tdC : null;
  d.dd500 = above(L5) && L5.tdC != null ? L5.tC - L5.tdC : null;
  d.lapse75 = above(L7) && above(L5) && L7.z != null && L5.z != null ? ((L7.tC - L5.tC) / (L5.z - L7.z)) * 1000 : null;

  const s = pr.sfc;
  const L = s.tC != null && s.tdC != null ? lcl(s.tC, s.tdC, s.p) : null;
  d.lclAgl = L ? L.zAgl : null;
  d.lclMsl = L && s.z != null ? L.zAgl + s.z : null;
  d.lclP = L ? L.p : null;

  // Freezing level: model field, else interpolated from levels.
  d.fzl = pr.fzl;
  d.fzlSource = pr.fzl != null ? 'model' : null;
  if (d.fzl == null) {
    const ls = pr.levels.filter((l) => !l.under && l.tC != null && l.z != null).sort((a, b) => a.z - b.z);
    for (let k = 1; k < ls.length; k++) {
      if (ls[k - 1].tC >= 0 && ls[k].tC < 0) {
        const f = ls[k - 1].tC / (ls[k - 1].tC - ls[k].tC);
        d.fzl = ls[k - 1].z + f * (ls[k].z - ls[k - 1].z); d.fzlSource = 'interp'; break;
      }
    }
  }

  // Moist layer: deepest contiguous block of above-ground levels with RH >= 70 %.
  const ls = pr.levels.filter((l) => !l.under && l.rh != null && l.z != null).sort((a, b) => a.z - b.z);
  let best = null, cur = null;
  for (const l of ls) {
    if (l.rh >= 70) { cur = cur ? { ...cur, top: l } : { bot: l, top: l }; }
    else { if (cur && (!best || cur.top.z - cur.bot.z > best.top.z - best.bot.z)) best = cur; cur = null; }
  }
  if (cur && (!best || cur.top.z - cur.bot.z > best.top.z - best.bot.z)) best = cur;
  d.moist = best ? { depth: best.top.z - best.bot.z, botP: best.bot.p, topP: best.top.p, single: best.top === best.bot } : null;

  // Precipitable water: model column value, else integral of q dp/g over levels.
  d.pw = pr.pw; d.pwSource = pr.pw != null ? 'model' : null;
  if (d.pw == null && s.p != null) {
    const pts = [{ p: s.p, q: s.tdC != null ? specHum(s.tdC, s.p) : null }]
      .concat(pr.levels.filter((l) => !l.under && l.tdC != null).map((l) => ({ p: l.p, q: specHum(l.tdC, l.p) })))
      .filter((x) => x.q != null).sort((a, b) => b.p - a.p);
    if (pts.length >= 3) {
      let w = 0; for (let k = 1; k < pts.length; k++) w += ((pts[k - 1].q + pts[k].q) / 2) * (pts[k - 1].p - pts[k].p) * 100 / G;
      d.pw = w; d.pwSource = 'levels';
    }
  }

  // Steering: mean wind of above-ground 700, 600, 500 hPa.
  const st = [L7, L6, L5].filter((l) => l && !l.under && l.u != null);
  if (st.length) {
    const u = st.reduce((a, l) => a + l.u, 0) / st.length, v = st.reduce((a, l) => a + l.v, 0) / st.length;
    d.steer = { u, v, speed: speedUV(u, v), dirFrom: dirFromUV(u, v), toward: (dirFromUV(u, v) + 180) % 360, n: st.length };
  } else d.steer = null;

  // Bulk shear, 10 m to 500 hPa.
  const [u0, v0] = uv(s.ws, s.wd);
  d.shear = u0 != null && L5 && L5.u != null ? speedUV(L5.u - u0, L5.v - v0) : null;

  // Low-level moisture flux magnitude q*V (g/kg * m/s) at 925 and 850 hPa when above ground.
  d.qflux = {};
  for (const l of [L92, L85]) {
    if (l && !l.under && l.tdC != null && l.ws != null) {
      d.qflux[l.p] = { q: specHum(l.tdC, l.p) * 1000, flux: specHum(l.tdC, l.p) * 1000 * l.ws, dirFrom: l.wd };
    }
  }
  d.vv = { 850: L85 && !L85.under ? L85.vv : null, 700: L7 && !L7.under ? L7.vv : null, 500: L5 ? L5.vv : null };
  d.cape = pr.cape; d.cin = pr.cin; d.li = pr.li; d.blh = pr.blh;
  d.sfc = s;
  return d;
}

// Divergence on a regular lat/lon grid (s^-1), centred differences; edges null.
export function divergence(u, v, lats, lons) {
  const ny = lats.length, nx = lons.length, R = 6371000;
  const out = Array.from({ length: ny }, () => new Array(nx).fill(null));
  for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const uE = u[j][i + 1], uW = u[j][i - 1], vN = v[j + 1][i], vS = v[j - 1][i];
    if ([uE, uW, vN, vS].some((x) => x == null)) continue;
    const dx = R * Math.cos(rad(lats[j])) * rad(lons[i + 1] - lons[i - 1]);
    const dy = R * rad(lats[j + 1] - lats[j - 1]);
    out[j][i] = (uE - uW) / dx + (vN - vS) / dy;
  }
  return out;
}

// Terrain-forced vertical motion w = V . grad(h), h from a DEM (m/s).
export function orographicW(u, v, h, lats, lons) {
  const ny = lats.length, nx = lons.length, R = 6371000;
  const out = Array.from({ length: ny }, () => new Array(nx).fill(null));
  for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    if (u[j][i] == null || [h[j][i + 1], h[j][i - 1], h[j + 1][i], h[j - 1][i]].some((x) => x == null)) continue;
    const dx = R * Math.cos(rad(lats[j])) * rad(lons[i + 1] - lons[i - 1]);
    const dy = R * rad(lats[j + 1] - lats[j - 1]);
    out[j][i] = u[j][i] * (h[j][i + 1] - h[j][i - 1]) / dx + v[j][i] * (h[j + 1][i] - h[j - 1][i]) / dy;
  }
  return out;
}

// ---------------------------------------------------------------- own parcel diagnostics
// Environment temperature at pressure p, log-p interpolation over [{p, tC}] sorted by p descending.
function envAt(pts, p) {
  for (let k = 1; k < pts.length; k++) {
    const a = pts[k - 1], b = pts[k];
    if (p <= a.p && p >= b.p) {
      const f = Math.log(a.p / p) / Math.log(a.p / b.p);
      return a.tC + f * (b.tC - a.tC);
    }
  }
  return null;
}

// Surface-based parcel CAPE and CIN (J/kg) on the model's own levels (dry-bulb buoyancy, coarse
// levels: indicative, used to compare scenarios, not to replace the model's own CAPE).
export function parcelCapeCin(sfc, levels, { mlTopP = null } = {}) {
  if (!sfc || sfc.tC == null || sfc.tdC == null || sfc.p == null) return null;
  const env = [{ p: sfc.p, tC: sfc.tC }]
    .concat(levels.filter((l) => !l.under && l.tC != null && l.p < sfc.p).map((l) => ({ p: l.p, tC: l.tC })))
    .sort((a, b) => b.p - a.p);
  if (env.length < 3) return null;
  const pTop = Math.max(250, env[env.length - 1].p);
  const path = parcelPath(sfc.tC, sfc.tdC, sfc.p, pTop);
  let cape = 0, cin = 0, lfc = null, el = null, positiveSeen = false;
  for (let k = 1; k < path.length; k++) {
    const p0 = path[k - 1].p, p1 = path[k].p;
    const te0 = envAt(env, p0), te1 = envAt(env, p1);
    if (te0 == null || te1 == null) continue;
    if (mlTopP != null && p1 >= mlTopP) continue; // inside the well-mixed layer: neutral by construction
    const b = ((path[k - 1].tC - te0) + (path[k].tC - te1)) / 2; // K
    const dE = RD * b * Math.log(p0 / p1);
    if (b > 0) { if (!positiveSeen) { lfc = p0; positiveSeen = true; } cape += dE; el = p1; }
    else if (!positiveSeen) cin += dE;
  }
  return { cape, cin, lfcP: lfc, elP: el };
}

// Convective temperature: the 2 m temperature (same moisture) at which a surface parcel
// rises freely (CAPE > 50 J/kg and CIN weaker than -10 J/kg).
export function convectiveTemp(sfc, levels, maxRise = 15, opts = {}) {
  if (!sfc || sfc.tC == null || sfc.tdC == null) return null;
  for (let d = 0; d <= maxRise; d += 0.25) {
    const r = parcelCapeCin({ ...sfc, tC: sfc.tC + d }, levels, opts);
    if (r && r.cape > 50 && r.cin > -10) return sfc.tC + d;
  }
  return null;
}

// Extra mixed-layer warming over dark basalt relative to the model's surface.
// dθ/dt = fH · SW↓ · (α_model − α_basalt) / (ρ cp h), accumulated from sunrise.
// sw: hourly mean downward shortwave (W/m²); blh: hourly mixed-layer depth (m) or null.
export function basaltWarming(sw, blh, hours, { albModel, albBasalt, fH }) {
  const rho = 1.08, cp = 1005;
  const out = []; let acc = 0;
  for (let i = 0; i < sw.length; i++) {
    const s = sw[i];
    if (s == null || s <= 5) { acc = hours[i] >= 18 || hours[i] < 5 ? 0 : acc; out.push(s == null ? null : acc); continue; }
    const h = Math.max(500, blh && blh[i] != null ? blh[i] : 1500);
    acc += (fH * s * (albModel - albBasalt) * 3600) / (rho * cp * h);
    out.push(acc);
  }
  return out;
}

// Mixed-layer top pressure from the model's boundary-layer height (1500 m if missing).
export function mlTop(sfcP, blh) { return sfcP == null ? null : sfcP * Math.exp(-(blh != null ? Math.max(300, blh) : 1500) / 8000); }

// Basalt scenario: the well-mixed layer warms by dθ (moisture unchanged), so the surface parcel is
// dθ warmer when it leaves the mixed layer; the free atmosphere above is the model's. Both the base
// and the warmed parcel are evaluated only above the mixed-layer top, so the comparison is consistent.
export function warmProfile(pr, dTheta, blh) {
  if (dTheta == null || !pr.sfc || pr.sfc.p == null || pr.sfc.tC == null) return null;
  return { sfc: { ...pr.sfc, tC: pr.sfc.tC + dTheta }, levels: pr.levels, mlTopP: mlTop(pr.sfc.p, blh) };
}
