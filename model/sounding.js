// Skew-T reading of a tapped point at the hour the map shows, from GFS and ECMWF (Fahad, 28 Nov 2026: «في كل
// الخرائط لما اضغط على نقطة ما عليه ان يكتب تفاصيل تلك النقطة… على هيئة قراءة Skwet لتلك الساعة المتوقفه فيها
// الخريطة من النموذجين الأمريكي والاوروبي»). The profiles come from Open-Meteo (key-free, called from the browser,
// the same source as the main site): GFS 0.25 and ECMWF IFS 0.25, the newest run each one has. One request per model
// and point covers all the page's days, so moving the map's hour only redraws.
// The two models are drawn on one diagram and never averaged: GFS solid, ECMWF dashed.
(function () {
  "use strict";
  const OM = "https://api.open-meteo.com/v1/forecast";
  const LV = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200];
  const MODELS = [
    { key: "gfs", name: "الأمريكي", ids: ["gfs_seamless", "gfs_global"], dash: [] },
    { key: "ec", name: "الأوروبي", ids: ["ecmwf_ifs025", "ecmwf_ifs"], dash: [6, 4] },
  ];
  const VARS = LV.flatMap((p) => ["temperature", "relative_humidity", "wind_speed", "wind_direction", "geopotential_height"].map((v) => `${v}_${p}hPa`))
    .concat(["temperature_2m", "dew_point_2m", "surface_pressure", "wind_speed_10m", "wind_direction_10m"]);
  const AR = (t) => String(t).replace(/\d/g, (c) => "٠١٢٣٤٥٦٧٨٩"[c]).replace(".", "٫").replace("-", "−");
  const cache = new Map();

  async function fetchModel(m, lat, lon) {
    const key = `${m.key}:${lat.toFixed(2)}:${lon.toFixed(2)}`;
    if (cache.has(key)) return cache.get(key);
    const p = (async () => {
      let err;
      for (const id of m.ids) {
        let vars = VARS.slice();
        for (let guard = 0; guard < 8; guard++) {   // a variable the model lacks is dropped (as the main site does)
          const q = new URLSearchParams({ latitude: lat.toFixed(3), longitude: lon.toFixed(3), hourly: vars.join(","), models: id,
            timezone: "Asia/Riyadh", timeformat: "unixtime", wind_speed_unit: "ms", past_days: "1", forecast_days: "16" });
          try {
            const r = await fetch(`${OM}?${q}`);
            if (!r.ok) {
              err = new Error(String(r.status));
              let reason = ""; try { reason = (await r.json()).reason || ""; } catch (_) { /* */ }
              const bad = /invalid String value\s+([A-Za-z0-9_]+)/i.exec(reason);
              if (r.status === 400 && bad && vars.includes(bad[1])) { vars = vars.filter((v) => v !== bad[1]); continue; }
              break;
            }
            const j = await r.json();
            if (!j.hourly || !j.hourly.time) { err = new Error("empty"); break; }
            return { id, h: j.hourly, elev: j.elevation };
          } catch (e) { err = e; break; }
        }
      }
      throw err || new Error("unavailable");
    })();
    cache.set(key, p);
    p.catch(() => cache.delete(key));
    return p;
  }

  const satVap = (t) => 6.112 * Math.exp((17.67 * t) / (t + 243.5));
  const dewOf = (t, rh) => { if (t == null || rh == null) return null; const g = Math.log(Math.max(rh, 1) / 100) + (17.67 * t) / (t + 243.5); return (243.5 * g) / (17.67 - g); };
  const mixr = (td, p) => { const e = satVap(td); return 0.622 * e / (p - e); };

  // the profile at time t (unix s): the nearest hour (within 90 min), levels under the ground left out
  function profile(res, t) {
    const T = res.h.time; let i = 0, best = 1e12;
    for (let k = 0; k < T.length; k++) { const d = Math.abs(T[k] - t); if (d < best) { best = d; i = k; } }
    if (best > 5400) return null;
    const g = (v) => { const a = res.h[v]; return a && a[i] != null ? a[i] : null; };
    const sp = g("surface_pressure");
    const sfc = { p: sp, t: g("temperature_2m"), td: g("dew_point_2m"), ws: g("wind_speed_10m"), wd: g("wind_direction_10m"), z: res.elev };
    const lev = LV.map((p) => {
      const t = g(`temperature_${p}hPa`), rh = g(`relative_humidity_${p}hPa`);
      return { p, t, rh, td: dewOf(t, rh), ws: g(`wind_speed_${p}hPa`), wd: g(`wind_direction_${p}hPa`), z: g(`geopotential_height_${p}hPa`) };
    }).filter((l) => l.t != null && (sp == null || l.p < sp - 5));
    if (!lev.length || sfc.t == null || sp == null) return null;
    return { sfc, lev, time: T[i] };
  }

  // env T and Td at pressure p (linear in log p), from the surface up
  function envAt(pr, p, key) {
    const pts = [{ p: pr.sfc.p, v: key === "t" ? pr.sfc.t : pr.sfc.td }].concat(pr.lev.map((l) => ({ p: l.p, v: l[key] }))).filter((q) => q.v != null);
    for (let k = 0; k < pts.length - 1; k++) {
      const a = pts[k], b = pts[k + 1];
      if (p <= a.p && p >= b.p) { const f = Math.log(a.p / p) / Math.log(a.p / b.p); return a.v + f * (b.v - a.v); }
    }
    return null;
  }
  // moist (pseudo-adiabatic) lapse dT/dp in K/hPa
  function moistDT(t, p) {
    const T = t + 273.15, es = satVap(t), rs = 0.622 * es / (p - es), Lv = 2.501e6, Rd = 287.04, cp = 1005.7, eps = 0.622;
    const num = (Rd * T + Lv * rs) / p, den = cp + (Lv * Lv * rs * eps) / (Rd * T * T);
    return num / den;
  }
  // surface parcel: path, LCL, CAPE and CIN (virtual temperature)
  function parcel(pr) {
    const { p: p0, t: t0, td: d0 } = pr.sfc; if (td0Bad(d0, t0)) return null;
    const w = mixr(d0, p0);
    const tlclK = 1 / (1 / (d0 + 273.15 - 56) + Math.log((t0 + 273.15) / (d0 + 273.15)) / 800) + 56;
    const plcl = p0 * Math.pow(tlclK / (t0 + 273.15), 3.5);
    const path = []; let cape = 0, cin = 0, t = t0, lfc = null, prevB = null, el = null;
    for (let p = p0; p >= 200; p -= 5) {
      let tp;
      if (p >= plcl) tp = (t0 + 273.15) * Math.pow(p / p0, 0.2857) - 273.15;
      else { t -= moistDT(t, p + 2.5) * 5; tp = t; }
      if (p >= plcl) t = tp;
      path.push({ p, t: tp });
      const te = envAt(pr, p, "t"), tde = envAt(pr, p, "td"); if (te == null) continue;
      const wp = p >= plcl ? w : mixr(tp, p), we = tde != null ? mixr(tde, p) : 0;
      const tvp = (tp + 273.15) * (1 + 0.61 * wp), tve = (te + 273.15) * (1 + 0.61 * we);
      const b = 287.04 * (tvp - tve) * Math.log((p + 5) / p);
      if (b > 0) { cape += b; if (lfc == null) lfc = p; el = p; }
      else if (lfc == null) cin += b;
      prevB = b;
    }
    return { path, plcl, tlcl: tlclK - 273.15, cape: Math.round(cape), cin: Math.round(cin), lfc, el };
  }
  const td0Bad = (d, t) => d == null || t == null;

  function diag(pr) {
    const pc = parcel(pr) || {};
    const lclM = pr.sfc.td != null ? Math.max(0, 125 * (pr.sfc.t - pr.sfc.td)) : null;
    let frz = null;   // freezing level (m above sea level)
    const L = [{ t: pr.sfc.t, z: pr.sfc.z }].concat(pr.lev.map((l) => ({ t: l.t, z: l.z })));
    for (let k = 0; k < L.length - 1; k++) if (L[k].t > 0 && L[k + 1].t <= 0 && L[k].z != null && L[k + 1].z != null) { frz = L[k].z + (L[k].t / (L[k].t - L[k + 1].t)) * (L[k + 1].z - L[k].z); break; }
    let pw = 0;      // precipitable water (mm), surface to 300 hPa
    const Q = [{ p: pr.sfc.p, q: pr.sfc.td != null ? mixr(pr.sfc.td, pr.sfc.p) : null }].concat(pr.lev.filter((l) => l.p >= 300).map((l) => ({ p: l.p, q: l.td != null ? mixr(l.td, l.p) : null })));
    for (let k = 0; k < Q.length - 1; k++) if (Q[k].q != null && Q[k + 1].q != null) pw += ((Q[k].q + Q[k + 1].q) / 2) * (Q[k].p - Q[k + 1].p) * 100 / 9.81;
    const uv = (ws, wd) => [-ws * Math.sin(wd * Math.PI / 180), -ws * Math.cos(wd * Math.PI / 180)];
    const l5 = pr.lev.find((l) => l.p === 500);
    const sh = l5 && pr.sfc.ws != null && l5.ws != null ? (() => { const a = uv(pr.sfc.ws, pr.sfc.wd), b = uv(l5.ws, l5.wd); return Math.hypot(b[0] - a[0], b[1] - a[1]); })() : null;
    const rh = (p) => { const l = pr.lev.find((x) => x.p === p); return l ? l.rh : null; };
    const t5 = pr.lev.find((l) => l.p === 500), t8 = pr.lev.find((l) => l.p === 850);
    return { pc, lclM, frz, pw, sh, rh7: rh(700), rh5: rh(500), t5: t5 ? t5.t : null, lapse: t5 && t8 && t5.z && t8.z ? (t8.t - t5.t) / ((t5.z - t8.z) / 1000) : null };
  }

  function draw(cv, prs) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth || 340, H = Math.round(W * 1.12);
    cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); cv.dir = "ltr"; c.direction = "ltr";
    const pBot = 1050, pTop = 200, padL = 34, padR = 44, padT = 8, padB = 22, tMin = -40, tMax = 45, skew = 75;
    const fr = (p) => Math.log(pBot / p) / Math.log(pBot / pTop);
    const yP = (p) => padT + (H - padT - padB) * fr(p);
    const xT = (t, p) => padL + (W - padL - padR) * ((t + skew * fr(p)) - tMin) / (tMax - tMin);
    c.fillStyle = "#11161d"; c.fillRect(0, 0, W, H);
    c.save(); c.beginPath(); c.rect(padL, padT, W - padL - padR, H - padT - padB); c.clip();
    c.lineWidth = 1;
    for (const p of [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200]) { c.strokeStyle = "#252d38"; c.beginPath(); c.moveTo(padL, yP(p)); c.lineTo(W, yP(p)); c.stroke(); }
    for (let t = -110; t <= 50; t += 10) { c.strokeStyle = t === 0 ? "rgba(90,150,230,.75)" : "#252d38"; c.beginPath(); c.moveTo(xT(t, pBot), yP(pBot)); c.lineTo(xT(t, pTop), yP(pTop)); c.stroke(); }
    c.strokeStyle = "rgba(200,130,70,.22)";
    for (let th = 250; th <= 450; th += 10) { c.beginPath(); for (let p = pBot; p >= pTop; p -= 10) { const t = th * Math.pow(p / 1000, 0.2857) - 273.15; p === pBot ? c.moveTo(xT(t, p), yP(p)) : c.lineTo(xT(t, p), yP(p)); } c.stroke(); }
    c.strokeStyle = "rgba(90,180,120,.18)";
    for (const t0 of [0, 8, 16, 24, 32]) { let t = t0; c.beginPath(); for (let p = 1000; p >= 250; p -= 10) { if (p !== 1000) t -= moistDT(t, p + 5) * 10; p === 1000 ? c.moveTo(xT(t, p), yP(p)) : c.lineTo(xT(t, p), yP(p)); } c.stroke(); }
    const sp = Math.max(...prs.filter(Boolean).map((x) => x.pr.sfc.p));
    if (isFinite(sp)) { c.fillStyle = "rgba(120,100,80,.18)"; c.fillRect(padL, yP(sp), W, H); }
    const line = (pts, col, w, dash) => { c.strokeStyle = col; c.lineWidth = w; c.setLineDash(dash); c.beginPath(); let f = true; for (const q of pts) { if (q.t == null) continue; f ? c.moveTo(xT(q.t, q.p), yP(q.p)) : c.lineTo(xT(q.t, q.p), yP(q.p)); f = false; } c.stroke(); c.setLineDash([]); };
    prs.forEach((x, k) => {
      if (!x) return;
      const { pr, d, m } = x;
      if (d.pc.path) line(d.pc.path, k ? "rgba(220,220,220,.55)" : "rgba(220,220,220,.8)", 1.2, k ? [2, 3] : [5, 4]);
      line([{ p: pr.sfc.p, t: pr.sfc.td }].concat(pr.lev.map((l) => ({ p: l.p, t: l.td }))), "#3ccf7a", 2.4, m.dash);
      line([{ p: pr.sfc.p, t: pr.sfc.t }].concat(pr.lev.map((l) => ({ p: l.p, t: l.t }))), "#ff5a4f", 2.4, m.dash);
    });
    c.restore();
    c.fillStyle = "#8f9aa7"; c.font = "11px system-ui"; c.textAlign = "right";
    for (const p of [1000, 850, 700, 500, 300, 200]) c.fillText(AR(p), padL - 4, yP(p) + 4);
    c.textAlign = "center";
    for (let t = -30; t <= 40; t += 10) { const X = xT(t, pBot); if (X > padL + 6 && X < W - padR) c.fillText(AR(t) + "°", X, H - 6); }
    // wind arrows, one column per model (toward where the wind blows)
    prs.forEach((x, k) => {
      if (!x) return;
      const X = W - padR + 12 + k * 18;
      c.fillStyle = "#8f9aa7"; c.font = "9px system-ui"; c.fillText(k ? "أوروبي" : "أمريكي", X, padT + 8);
      c.strokeStyle = "#e6ebf0"; c.lineWidth = 1.3; c.setLineDash(x.m.dash.length ? [3, 2] : []);
      for (const l of [{ p: x.pr.sfc.p, ws: x.pr.sfc.ws, wd: x.pr.sfc.wd }].concat(x.pr.lev)) {
        if (l.ws == null || l.p < pTop) continue;
        const a = (l.wd + 180) * Math.PI / 180, len = Math.min(15, 4 + l.ws * 0.5), dx = Math.sin(a) * len, dy = -Math.cos(a) * len, Y = yP(l.p);
        c.beginPath(); c.moveTo(X - dx / 2, Y - dy / 2); c.lineTo(X + dx / 2, Y + dy / 2); c.stroke();
        c.beginPath(); c.arc(X + dx / 2, Y + dy / 2, 1.7, 0, 7); c.fillStyle = "#e6ebf0"; c.fill();
      }
      c.setLineDash([]);
    });
  }

  const n0 = (v, d = 0) => v == null || !isFinite(v) ? "—" : `<span dir="ltr">${AR((d ? v.toFixed(d) : Math.round(v)).toString())}</span>`;

  // host: the card's sounding box; at: {d: "YYYY-MM-DD", h: Makkah hour}
  async function show(host, lat, lon, at) {
    host.hidden = false;
    const t = Date.UTC(+at.d.slice(0, 4), +at.d.slice(5, 7) - 1, +at.d.slice(8, 10), at.h - 3) / 1000;
    host.dataset.k = `${lat}:${lon}`;
    if (!host.querySelector("canvas")) host.innerHTML = `<div class="snd-h"></div><canvas></canvas><div class="snd-k"></div><table class="snd-t"></table><p class="snd-n"></p>`;
    const H = host.querySelector(".snd-h");
    H.innerHTML = `<b>قراءة الطبقات (سكيو تي)</b> عند خط العرض ${AR(lat.toFixed(2))} وخط الطول ${AR(lon.toFixed(2))}`;
    host.querySelector(".snd-n").textContent = "جارٍ جلب النموذجين…";
    const res = await Promise.all(MODELS.map((m) => fetchModel(m, lat, lon).catch(() => null)));
    if (host.dataset.k !== `${lat}:${lon}`) return;   // another point was tapped meanwhile
    const prs = res.map((r, k) => { const pr = r && profile(r, t); return pr ? { pr, d: diag(pr), m: MODELS[k] } : null; });
    draw(host.querySelector("canvas"), prs);
    host.querySelector(".snd-k").innerHTML = `<span><i style="border-top:2px solid #ff5a4f"></i>الحرارة</span><span><i style="border-top:2px solid #3ccf7a"></i>نقطة الندى</span><span>الأمريكي خط متصل، والأوروبي متقطع</span><span>الرمادي مسار جسيم من السطح</span>`;
    const row = (name, f) => `<tr><td>${name}</td>${prs.map((x) => `<td>${x ? f(x.d, x.pr) : "—"}</td>`).join("")}</tr>`;
    host.querySelector(".snd-t").innerHTML = `<tr><th></th><th>الأمريكي</th><th>الأوروبي</th></tr>`
      + row("طاقة عدم الاستقرار من السطح (جول/كجم)", (d) => n0(d.pc.cape))
      + row("الكبح (جول/كجم)", (d) => n0(-d.pc.cin))
      + row("قاعدة السحب فوق السطح (م)", (d) => n0(d.lclM))
      + row("الماء القابل للهطول (ملم)", (d) => n0(d.pw))
      + row("الرطوبة ٧٠٠ و٥٠٠ (٪)", (d) => `${n0(d.rh7)} و${n0(d.rh5)}`)
      + row("حرارة ٥٠٠ (م°)", (d) => n0(d.t5))
      + row("التناقص ٨٥٠–٥٠٠ (م° لكل كم)", (d) => n0(d.lapse, 1))
      + row("مستوى التجمد (م)", (d) => n0(d.frz))
      + row("القص من السطح إلى ٥٠٠ (م/ث)", (d) => n0(d.sh));
    const miss = prs.map((x, k) => x ? null : MODELS[k].name).filter(Boolean);
    host.querySelector(".snd-n").textContent = (miss.length ? `لم يتوفر النموذج ${miss.join(" و")} لهذه الساعة. ` : "")
      + "قراءة من أحدث تشغيل لكل نموذج (دقة ٠٫٢٥ درجة) عن طريق خدمة أوبن ميتيو، للساعة المعروضة على الخريطة، ولا يُدمج النموذجان. المنطقة البنية تحت سطح الأرض. تتغير القراءة مع تحريك الخريطة.";
  }
  window.SKEWT = { show };
})();
