/* Viewer for Fahad's private WRF runs over Saudi Arabia.
   Data layout (written by server/post/postprocess.py):
     data/runs.json                       list of runs, newest first
     data/runs/<run>/manifest.json        domains, frames, bounds, legends
     data/runs/<run>/meteo.json           city time series
     data/runs/<run>/<dom>/<prod>/<hhh>.png   (daily products: <YYYYMMDD>.png)
     data/status.json                     install / cycle progress                          */
(function () {
  "use strict";

  const DATA = window.SWRF_DATA || "data/";
  const TZ = "Asia/Riyadh";
  const LOC = "ar-SA-u-nu-arab-ca-gregory";
  const nf = (d) => new Intl.NumberFormat(LOC, { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const num = (v, d = 0) => (v == null || !isFinite(v) ? "—" : nf(d).format(v));
  const fmtWhen = new Intl.DateTimeFormat(LOC, { timeZone: TZ, weekday: "long", hour: "numeric" });
  const fmtDay = new Intl.DateTimeFormat(LOC, { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
  const fmtDayShort = new Intl.DateTimeFormat(LOC, { timeZone: TZ, weekday: "short" });
  const fmtStamp = new Intl.DateTimeFormat(LOC, { timeZone: TZ, day: "numeric", month: "long", hour: "numeric", minute: "2-digit" });
  const arDigits = (t) => String(t ?? "").replace(/[0-9]/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]).replace(/\b(\d{10})\b/g, "$1");
  const HOURLY = ["refl", "rain1h", "rainacc", "t2", "wind", "wup"];
  const DAILY = ["refl_day", "rain_day"];
  const NO_H0 = new Set(["rain1h", "wind", "wup"]);

  const $ = (id) => document.getElementById(id);
  const store = {
    get(k) { try { return localStorage.getItem("swrf." + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("swrf." + k, v); } catch (e) { /* private mode */ } },
  };

  const S = { runs: [], run: null, man: null, meteo: null, dom: store.get("dom") || "d02", prod: store.get("prod") || "refl",
              frames: [], idx: 0, playing: null, overlay: null, rects: [], cityLayer: null };

  async function getJSON(url) {
    const r = await fetch(url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  // ------------------------------------------------------------------ map
  const map = L.map("map", { zoomControl: false, attributionControl: true, minZoom: 4, maxZoom: 13 }).setView([23.5, 44], 5);
  // basemaps: dark by default, place names drawn above the model colours
  map.createPane("labels"); map.getPane("labels").style.zIndex = 650; map.getPane("labels").style.pointerEvents = "none";
  const carto = "© OpenStreetMap · © CARTO";
  const dark = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", { maxZoom: 19, attribution: carto, subdomains: "abcd" });
  const light = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", { maxZoom: 19, attribution: carto, subdomains: "abcd" });
  const topo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenStreetMap, SRTM · OpenTopoMap" });
  const shade = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 13, opacity: 0.45, attribution: "Esri" });
  const labelsDark = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png", { pane: "labels", subdomains: "abcd", maxZoom: 19 });
  const bases = { "داكنة": dark, "فاتحة": light, "تضاريس": topo };
  const baseKey = store.get("base2") || "داكنة";
  (bases[baseKey] || dark).addTo(map);
  if (store.get("shade") !== "0") shade.addTo(map);
  if (store.get("labels") !== "0") labelsDark.addTo(map);
  L.control.layers(bases, { "ظلال التضاريس": shade, "أسماء الأماكن": labelsDark }, { position: "topleft" }).addTo(map);
  map.on("baselayerchange", (e) => { store.set("base2", e.name); document.body.classList.toggle("light-map", e.name !== "داكنة"); });
  document.body.classList.toggle("light-map", baseKey !== "داكنة");
  map.on("overlayadd overlayremove", (e) => {
    const on = e.type === "overlayadd" ? "1" : "0";
    if (e.layer === shade) store.set("shade", on);
    if (e.layer === labelsDark) store.set("labels", on);
  });
  L.control.zoom({ position: "topleft" }).addTo(map);
  map.attributionControl.setPrefix(false);
  map.on("zoomend", () => map.getContainer().classList.toggle("hide-labels", map.getZoom() < 7));

  function frameURL(i) {
    const f = S.frames[i];
    if (!f) return null;
    const name = DAILY.includes(S.prod) ? f.date : String(f.h).padStart(3, "0");
    return `${DATA}runs/${S.run}/${S.dom}/${S.prod}/${name}.png`;
  }

  const cache = new Map();
  function preload(i) {
    const u = frameURL(i);
    if (u && !cache.has(u)) { const im = new Image(); im.src = u; cache.set(u, im); if (cache.size > 120) cache.delete(cache.keys().next().value); }
  }

  // two image layers that cross-fade, so playback looks continuous
  const fade = { layers: [], front: 0, token: 0 };
  function overlayTo(url, bounds) {
    const b = L.latLngBounds(bounds);
    if (!fade.layers.length) {
      for (let k = 0; k < 2; k++) {
        const lay = L.imageOverlay(url, b, { interactive: false, zIndex: 300, opacity: k === 0 ? 1 : 0, className: "wx-layer" }).addTo(map);
        fade.layers.push(lay);
      }
      return;
    }
    const tok = ++fade.token;
    const back = fade.layers[1 - fade.front], front = fade.layers[fade.front];
    back.setBounds(b);
    const img = new Image();
    img.onload = img.onerror = () => {
      if (tok !== fade.token) return;
      back.setUrl(url);
      back.setOpacity(1); front.setOpacity(0);
      fade.front = 1 - fade.front;
    };
    img.src = url;
  }
  function clearOverlay() { fade.layers.forEach((l) => map.removeLayer(l)); fade.layers = []; fade.front = 0; }

  function showFrame() {
    const d = S.man && S.man.domains[S.dom];
    if (!d || !S.frames.length) { clearOverlay(); $("timeLabel").textContent = "—"; return; }
    S.idx = Math.max(0, Math.min(S.idx, S.frames.length - 1));
    overlayTo(frameURL(S.idx), d.bounds);
    $("timeRange").max = S.frames.length - 1;
    $("timeRange").value = S.idx;
    $("timeLabel").textContent = frameLabel(S.frames[S.idx]);
    for (let k = 1; k <= 4; k++) preload(S.idx + k);
    if (S.pointPopup && S.pointPopup.isOpen()) S.pointPopup.setContent(pointHTML(S.pointPopup._pt));
  }

  function frameLabel(f) {
    if (f.date) {
      const t = new Date(Date.UTC(+f.date.slice(0, 4), +f.date.slice(4, 6) - 1, +f.date.slice(6, 8), 9));
      return fmtDay.format(t) + (f.hours < 24 ? ` · ${num(f.hours)} ساعة فقط` : "");
    }
    const t = new Date(Date.parse(S.man.init) + f.h * 3600e3);
    return `${fmtWhen.format(t)} · ساعة ${num(f.h)}`;
  }

  function buildFrames(keepTime) {
    const d = S.man && S.man.domains[S.dom];
    const prevKey = keepTime && S.frames[S.idx] ? S.frames[S.idx] : null;
    if (!d) { S.frames = []; return; }
    if (DAILY.includes(S.prod)) S.frames = (d.days || []).map((x) => ({ date: x.date, hours: x.hours }));
    else S.frames = d.hours.filter((h) => !(NO_H0.has(S.prod) && h === 0)).map((h) => ({ h }));
    if (prevKey) {
      let k = -1;
      if (prevKey.h != null && !DAILY.includes(S.prod)) k = S.frames.findIndex((f) => f.h === prevKey.h);
      S.idx = k >= 0 ? k : Math.min(S.idx, S.frames.length - 1);
    }
  }

  const rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${(Math.max(a, 90) / 255).toFixed(2)})`;
  function drawLegend() {
    const p = S.man && S.man.products[S.prod];
    if (!p) { $("legend").innerHTML = ""; return; }
    const lg = p.legend;
    const grad = lg.stops.map((x) => `${rgba(x.c, x.a)} ${(x.p * 100).toFixed(1)}%`).join(", ");
    const step = lg.stops.length > 7 ? 2 : 1;
    const ticks = lg.stops.map((x, i) => (i % step === 0 || i === lg.stops.length - 1)
      ? `<span style="left:${(x.p * 100).toFixed(1)}%">${num(x.v, x.v < 1 ? 1 : 0)}</span>` : "").join("");
    $("legend").innerHTML = `<div class="legend-title"><span>${p.label}</span><span>${p.unit}</span></div>
      <div class="legend-bar" style="background:linear-gradient(to right, ${grad})"></div><div class="legend-ticks">${ticks}</div>`;
  }

  // colour of a value on a product's scale (for the small charts)
  function colorAt(prod, v) {
    const p = S.man && S.man.products[prod];
    if (!p || v == null || v < p.legend.vmin) return null;
    const st = p.legend.stops;
    for (let k = st.length - 1; k >= 0; k--) if (v >= st[k].v) return st[k].c;
    return null;
  }

  function drawChips() {
    const box = $("domChips");
    box.innerHTML = "";
    const ids = ["d01", "d02", "d03"];
    for (const id of ids) {
      const d = S.man && S.man.domains[id];
      if (!d) continue;
      const b = document.createElement("button");
      b.className = "chip" + (id === S.dom ? " active" : "");
      b.innerHTML = `${d.name}<small>${d.res}</small>`;
      b.onclick = () => setDomain(id, true);
      box.appendChild(b);
    }
  }

  function drawProducts() {
    const sel = $("prodSelect");
    const P = (S.man && S.man.products) || {};
    const opt = (k) => (P[k] ? `<option value="${k}">${P[k].label}</option>` : "");
    sel.innerHTML = `<optgroup label="كل ساعة">${HOURLY.map(opt).join("")}</optgroup>
                     <optgroup label="خلاصة اليوم">${DAILY.map(opt).join("")}</optgroup>`;
    if (!P[S.prod]) S.prod = "refl";
    sel.value = S.prod;
  }

  function drawRects() {
    S.rects.forEach((r) => map.removeLayer(r));
    S.rects = [];
    if (!S.man) return;
    for (const [id, d] of Object.entries(S.man.domains)) {
      if (id === S.dom || !d.bounds) continue;
      const r = L.rectangle(d.bounds, { color: "#f2b552", weight: 1.5, dashArray: "5 5", fill: false, interactive: true })
        .bindTooltip(`${d.name} · ${d.res}`, { sticky: true, direction: "top" })
        .on("click", () => setDomain(id, true));
      r.addTo(map); S.rects.push(r);
    }
  }

  function setDomain(id, fit) {
    if (!S.man || !S.man.domains[id]) id = Object.keys((S.man && S.man.domains) || {})[0] || "d01";
    S.dom = id; store.set("dom", id);
    buildFrames(true);
    drawChips(); drawRects(); showFrame();
    const d = S.man && S.man.domains[id];
    if (fit && d && d.bounds) map.fitBounds(d.bounds, { padding: [10, 10] });
  }

  function setProduct(p) {
    S.prod = p; store.set("prod", p);
    buildFrames(true);
    drawLegend(); showFrame();
  }

  // ------------------------------------------------------------------ time controls
  function stop() { if (S.playing) { clearInterval(S.playing); S.playing = null; $("btnPlay").textContent = "▶"; } }
  $("btnPlay").onclick = () => {
    if (S.playing) return stop();
    $("btnPlay").textContent = "❚❚";
    S.playing = setInterval(() => { S.idx = (S.idx + 1) % Math.max(1, S.frames.length); showFrame(); }, 750);
  };
  $("btnPrev").onclick = () => { stop(); S.idx = Math.max(0, S.idx - 1); showFrame(); };
  $("btnNext").onclick = () => { stop(); S.idx = Math.min(S.frames.length - 1, S.idx + 1); showFrame(); };
  $("timeRange").oninput = (e) => { stop(); S.idx = +e.target.value; showFrame(); };
  $("prodSelect").onchange = (e) => setProduct(e.target.value);

  // ------------------------------------------------------------------ cities
  function series(c, key) { return (c.series && c.series[key]) || []; }

  function reflColor(v) { return v >= 10 ? colorAt("refl", v) : null; }

  function cityChart(c) {
    const W = 340, H = 128, padL = 6, padR = 26, top = 8, bot = 30;
    const t2 = series(c, "t2").filter((x) => x[1] != null);
    const rain = series(c, "rain").filter((x) => x[1] != null);
    const refl = series(c, "refl").filter((x) => x[1] != null);
    const all = t2.map((x) => x[0]);
    if (!all.length) return "";
    const maxH = Math.max(...all, 1);
    const X = (h) => padL + (W - padL - padR) * (h / maxH);
    const tv = t2.map((x) => x[1]);
    let tmin = Math.floor(Math.min(...tv) - 1), tmax = Math.ceil(Math.max(...tv) + 1);
    const plotH = H - top - bot - 10;
    const Y = (t) => top + plotH * (1 - (t - tmin) / Math.max(1, tmax - tmin));
    const rmax = Math.max(5, ...rain.map((x) => x[1]));
    const RY = (r) => top + plotH - plotH * 0.85 * (r / rmax);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" direction="ltr">`;
    // local midnights
    const init = Date.parse(S.man.init);
    for (let h = 0; h <= maxH; h++) {
      const t = new Date(init + h * 3600e3);
      const hr = +new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "numeric", hour12: false }).format(t);
      if (hr === 0 || hr === 24) {
        s += `<line x1="${X(h)}" x2="${X(h)}" y1="${top}" y2="${H - bot + 12}" stroke="currentColor" stroke-opacity=".15"/>`;
      }
      if (hr === 12) s += `<text x="${X(h)}" y="${H - 4}" text-anchor="middle">${fmtDayShort.format(t)}</text>`;
    }
    const bw = Math.max(1.5, (W - padL - padR) / maxH - 0.8);
    for (const [h, r] of rain) if (r >= 0.1) s += `<rect x="${X(h) - bw}" y="${RY(r)}" width="${bw}" height="${top + plotH - RY(r)}" fill="#2a7fdc" opacity=".8"/>`;
    const sy = H - bot + 2;
    for (const [h, v] of refl) { const col = reflColor(v); if (col) s += `<rect x="${X(h) - bw}" y="${sy}" width="${bw + 0.6}" height="7" fill="${col}"/>`; }
    s += `<rect x="${padL}" y="${sy}" width="${W - padL - padR}" height="7" fill="none" stroke="currentColor" stroke-opacity=".12"/>`;
    s += `<polyline fill="none" stroke="#e2502a" stroke-width="2" points="${t2.map(([h, v]) => `${X(h).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")}"/>`;
    s += `<text x="${W - 2}" y="${Y(tmax) + 9}" text-anchor="end">${num(tmax)}°</text><text x="${W - 2}" y="${Y(tmin)}" text-anchor="end">${num(tmin)}°</text>`;
    return s + "</svg>";
  }

  function citySummary(c) {
    const acc = series(c, "acc").filter((x) => x[1] != null);
    const refl = series(c, "refl").filter((x) => x[1] != null).map((x) => x[1]);
    const t2 = series(c, "t2").filter((x) => x[1] != null).map((x) => x[1]);
    const total = acc.length ? acc[acc.length - 1][1] - acc[0][1] : 0;
    const parts = [];
    if (t2.length) parts.push(`${num(Math.min(...t2))}° إلى ${num(Math.max(...t2))}°`);
    parts.push(total >= 0.1 ? `مطر ${num(total, 1)} ملم` : "بلا مطر يُذكر");
    if (refl.length && Math.max(...refl) >= 35) parts.push(`انعكاسية حتى ${num(Math.max(...refl))}`);
    return parts.join(" · ");
  }

  function drawCities() {
    const box = $("cityList");
    if (!S.meteo || !S.meteo.cities.length) { box.innerHTML = `<p class="muted">لا توجد بيانات مدن لهذا التشغيل بعد.</p>`; return; }
    const q = $("cityFilter").value.trim();
    const res = { d01: "٩ كم", d02: "٣ كم", d03: "٦٠٠ م" };
    box.innerHTML = S.meteo.cities.filter((c) => !q || c.name.includes(q)).map((c) => `
      <div class="city"><div class="city-head"><span class="city-name">${c.name}</span>
      <span class="city-sum">${res[c.domain] || ""}</span></div>
      <div class="city-sum">${citySummary(c)}</div>${cityChart(c)}</div>`).join("");
  }
  $("cityFilter").oninput = drawCities;

  function drawCityMarkers() {
    if (S.cityLayer) map.removeLayer(S.cityLayer);
    S.cityLayer = L.layerGroup().addTo(map);
    if (!S.meteo) return;
    for (const c of S.meteo.cities) {
      L.circleMarker([c.lat, c.lon], { bubblingMouseEvents: false, radius: 4, color: "#0b1d2c", weight: 1.5, fillColor: "#ffffff", fillOpacity: 1 })
        .bindTooltip(c.name, { permanent: true, direction: "right", offset: [6, 0], className: "city-label" })
        .bindPopup(() => `<strong>${c.name}</strong><div class="city-sum">${citySummary(c)}</div>${cityChart(c)}`, { maxWidth: 360, minWidth: 280 })
        .addTo(S.cityLayer);
    }
  }

  // ------------------------------------------------------------------ tap anywhere
  function lccForward(pr, lon, lat) {
    const r = Math.PI / 180, R = pr.R;
    const p1 = pr.truelat1 * r, p2 = pr.truelat2 * r, p0 = pr.ref_lat * r, l0 = pr.stand_lon * r;
    const t = (p) => Math.tan(Math.PI / 4 + p / 2);
    const n = Math.log(Math.cos(p1) / Math.cos(p2)) / Math.log(t(p2) / t(p1));
    const F = Math.cos(p1) * Math.pow(t(p1), n) / n;
    const rho = R * F / Math.pow(t(lat * r), n), rho0 = R * F / Math.pow(t(p0), n);
    const th = n * (lon * r - l0);
    return [rho * Math.sin(th), rho0 - rho * Math.cos(th)];
  }
  async function pointData(dom) {
    const d = S.man.domains[dom];
    if (!d || !d.points) return null;
    const key = S.run + dom + d.points.hours.length;
    if (!S.points[key]) {
      S.points[key] = fetch(`${DATA}runs/${S.run}/${d.points.file}?n=${d.points.hours.length}`)
        .then((r) => (r.ok ? r.arrayBuffer() : null)).then((b) => (b ? new Uint8Array(b) : null)).catch(() => null);
    }
    return { info: d.points, bytes: await S.points[key] };
  }
  const DECODE = { rain1h: (c) => (c / 25) ** 2, refl: (c) => c / 3, t2: (c) => c / 4 - 10, wind: (c) => c / 2 };
  async function pointSeries(lat, lon) {
    // finest domain that contains the point
    const order = Object.keys(S.man.domains).sort((a, b) => b.localeCompare(a));
    for (const dom of order) {
      const pd = await pointData(dom);
      if (!pd || !pd.bytes) continue;
      const P = pd.info, [x, y] = lccForward(S.man.proj, lon, lat);
      const i = Math.round((x - P.x00) / P.dx), j = Math.round((y - P.y00) / P.dx);
      if (i < 1 || j < 1 || i > P.nx - 2 || j > P.ny - 2) continue;
      const nh = P.hours.length, series = {};
      P.vars.forEach((v, k) => {
        series[v] = P.hours.map((h, hi) => [h, DECODE[v](pd.bytes[((k * nh + hi) * P.ny + j) * P.nx + i])]);
      });
      series.rain = series.rain1h.map(([h, v]) => [h, h === 0 ? null : Math.round(v * 10) / 10]);
      let acc = 0;
      series.acc = series.rain.map(([h, v]) => [h, (acc += v || 0)]);
      series.wind = series.wind.map(([h, v]) => [h, h === 0 ? null : v]);
      return { dom, series, lat, lon };
    }
    return null;
  }
  function pointHTML(pt) {
    if (!pt) return `<div class="muted">خارج مجالات النموذج</div>`;
    const f = S.frames[S.idx];
    const h = f && f.h != null ? f.h : null;
    const at = (v) => { const r = (pt.series[v] || []).find((x) => x[0] === h); return r ? r[1] : null; };
    const res = { d01: "٩ كم", d02: "٣ كم", d03: "٦٠٠ م" }[pt.dom] || "";
    const now = h == null ? "" : `<div class="pt-now">
        <span><b>${num(at("rain"), 1)}</b> ملم</span><span><b>${num(at("refl"))}</b> ديسيبل</span>
        <span><b>${num(at("t2"))}</b>°</span><span><b>${num(at("wind"))}</b> كم/س</span></div>`;
    return `<div class="pt-head"><strong>${num(pt.lat, 2)}° ش، ${num(pt.lon, 2)}° ق</strong><small>${res}</small></div>
      ${now}<div class="city-sum">${citySummary(pt)}</div>${cityChart(pt)}`;
  }
  map.on("click", async (e) => {
    if (!S.man) return;
    const pop = L.popup({ maxWidth: 360, minWidth: 290 }).setLatLng(e.latlng).setContent(`<div class="muted">جارٍ التحميل…</div>`).openOn(map);
    const pt = await pointSeries(e.latlng.lat, e.latlng.lng);
    pop._pt = pt; S.pointPopup = pop;
    pop.setContent(pointHTML(pt));
  });

  // ------------------------------------------------------------------ runs
  function runName(r) {
    const t = new Date(Date.UTC(+r.slice(0, 4), +r.slice(4, 6) - 1, +r.slice(6, 8), +r.slice(8, 10)));
    return `تشغيل ${fmtStamp.format(t)}`;
  }

  async function loadRun(run, first) {
    S.run = run;
    try { S.man = await getJSON(`${DATA}runs/${run}/manifest.json`); } catch (e) { S.man = null; }
    try { S.meteo = await getJSON(`${DATA}runs/${run}/meteo.json`); } catch (e) { S.meteo = null; }
    if (S.man) for (const p of Object.values(S.man.products)) {
      if (Array.isArray(p.legend)) {  // runs made before the gradient colours
        const n = p.legend.length;
        p.legend = { vmin: p.legend[0].v ?? -99, stops: p.legend.map((x, i) => ({ p: i / Math.max(1, n - 1), v: x.v ?? -99, c: x.c, a: 235 })) };
      }
    }
    S.points = {};
    const has = S.man && Object.keys(S.man.domains).length;
    $("mapEmpty").hidden = !!has;
    if (!has) return;
    const st = S.man.status === "running" ? " · جارٍ" : S.man.status === "failed" ? " · ناقص" : "";
    $("runLabel").textContent = `${runName(run)} من جي إف إس${st}`;
    drawProducts(); drawLegend();
    if (first) { buildFrames(false); S.idx = 0; }
    setDomain(S.dom, first);
    drawCityMarkers();
    if (!$("p-cities").hidden) drawCities();
  }

  async function refreshRuns(first) {
    let idx;
    try { idx = await getJSON(DATA + "runs.json"); } catch (e) { idx = { runs: [] }; }
    S.runs = idx.runs || [];
    const sel = $("runSelect");
    sel.hidden = S.runs.length < 2;
    sel.innerHTML = S.runs.map((r) => `<option value="${r.run}">${runName(r.run)}${r.status === "running" ? " (جارٍ)" : ""}</option>`).join("");
    if (!S.runs.length) { $("mapEmpty").hidden = false; return; }
    if (first || !S.run) {
      const complete = S.runs.find((r) => r.status === "complete");
      const newest = S.runs[0];
      // prefer the newest run once it has at least a day of the 3 km domain
      const pick = newest.status === "running" && complete && ((newest.hours || {}).d02 || 0) < 24 ? complete : newest;
      sel.value = pick.run;
      await loadRun(pick.run, true);
    } else {
      sel.value = S.run;
      const cur = S.runs.find((r) => r.run === S.run);
      if (cur && (cur.status === "running" || (S.man && S.man.status === "running"))) await loadRun(S.run, false);
    }
  }
  $("runSelect").onchange = (e) => { stop(); loadRun(e.target.value, true); };

  // ------------------------------------------------------------------ status
  const PH = { install: ["جارٍ التثبيت", "run"], cycle: ["دورة قيد التشغيل", "run"], idle: ["جاهز", "ok"], error: ["متوقف بخطأ", "err"] };
  const STATE = { pending: ["بانتظار", "wait"], running: ["جارٍ", "run"], done: ["تم", "ok"], error: ["خطأ", "err"], skipped: ["تُخطّي", "wait"] };
  function ago(iso) {
    if (!iso) return "";
    const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
    if (m < 1) return "الآن";
    if (m < 60) return `قبل ${num(m)} دقيقة`;
    return `قبل ${num(Math.floor(m / 60))} ساعة و${num(m % 60)} دقيقة`;
  }
  function dur(a, b) {
    if (!a) return "";
    const m = Math.round(((b ? Date.parse(b) : Date.now()) - Date.parse(a)) / 60000);
    return m < 60 ? `${num(m)} د` : `${num(Math.floor(m / 60))} س ${num(m % 60)} د`;
  }
  async function refreshStatus() {
    let s;
    try { s = await getJSON(DATA + "status.json"); } catch (e) {
      $("statusCard").innerHTML = `<p class="muted">لم تصل حالة الخادم بعد.</p>`; return;
    }
    const [ph, cls] = PH[s.phase] || [s.phase, "wait"];
    $("statusDot").className = "dot " + cls;
    const steps = (s.steps || []).map((x) => {
      const [lab, c] = STATE[x.state] || [x.state, "wait"];
      const note = x.note && !/-\d/.test(x.note) ? arDigits(x.note) : "";
      return `<li><span>${x.label}${note ? ` <small>${note}</small>` : ""}</span>
        <span><small>${x.state === "running" || x.state === "done" ? dur(x.started, x.ended) : ""}</small> <span class="pill ${c}">${lab}</span></span></li>`;
    }).join("");
    const what = (s.cycle || "").length !== 10 ? "التثبيت" : `الدورة: ${runName(s.cycle)}`;
    $("statusCard").innerHTML = `<div class="phase"><span class="pill ${cls}">${ph}</span></div>
      <div>${arDigits((s.message || "").replace(/\s*\d{10}\s*/, " "))}</div><div class="muted" style="font-size:.8rem">${what} · آخر تحديث ${ago(s.updated)}</div>
      <ul class="steps">${steps}</ul>`;
    $("historyList").innerHTML = (s.history || []).length ? s.history.map((h) => `<div class="hist">
      <span>${runName(h.cycle)}</span><span class="pill ${h.ok ? "ok" : "err"}">${h.ok ? "اكتملت" : "ناقصة"}</span>
      <span class="muted">${dur(new Date(Date.parse(h.finished) - h.minutes * 60000).toISOString(), h.finished)}</span></div>`).join("")
      : `<p class="muted">لا دورات مكتملة بعد.</p>`;
    if (!S.runs.length) $("mapEmptyMsg").textContent = `${ph}${s.message ? ": " + s.message : ""}. التفاصيل في تبويب الحالة.`;
  }

  // ------------------------------------------------------------------ tabs
  document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    for (const p of ["map", "cities", "status"]) $("p-" + p).hidden = p !== b.dataset.tab;
    if (b.dataset.tab === "map") setTimeout(() => map.invalidateSize(), 50);
    if (b.dataset.tab === "cities") drawCities();
    if (b.dataset.tab === "status") refreshStatus();
  });

  document.querySelectorAll("[data-log]").forEach((a) => { a.href = `${DATA}logs/${a.dataset.log}.txt`; });

  (async function start() {
    map.getContainer().classList.toggle("hide-labels", map.getZoom() < 7);
    await Promise.all([refreshRuns(true), refreshStatus()]);
    setInterval(refreshStatus, 60e3);
    setInterval(() => refreshRuns(false), 5 * 60e3);
  })();
})();
