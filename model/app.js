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
  // the Kingdom-wide 9 km run is made on its own server in parallel and kept on its own branch
  const DATA_SA = window.SWRF_DATA_SA || DATA.replace("/model-data/", "/model-data-sa/");
  // the 1 km nest over Jeddah, Makkah and Taif runs on a third server and is kept on its own branch
  const DATA_1K = window.SWRF_DATA_1K || DATA.replace("/model-data/", "/model-data-1km/");
  const base = (d) => (d && d.base) || DATA;
  const TZ = "Asia/Riyadh";
  const LOC = "ar-SA-u-nu-arab-ca-gregory";
  const nf = (d) => new Intl.NumberFormat(LOC, { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const num = (v, d = 0) => (v == null || !isFinite(v) ? "—" : nf(d).format(v));
  const fmtWhen = new Intl.DateTimeFormat(LOC, { timeZone: TZ, weekday: "long", hour: "numeric" });
  const fmtDay = new Intl.DateTimeFormat(LOC, { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
  const fmtDayShort = new Intl.DateTimeFormat(LOC, { timeZone: TZ, weekday: "short" });
  const fmtStamp = new Intl.DateTimeFormat(LOC, { timeZone: TZ, day: "numeric", month: "long", hour: "numeric", minute: "2-digit" });
  const arDigits = (t) => String(t ?? "").replace(/[0-9]/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]).replace(/\b(\d{10})\b/g, "$1");
  const HOURLY = ["refl", "rain1h", "conv925"];
  // products drawn with wind arrows on top: folder of the arrow files and the speed of a full-length arrow
  const VEC = { ivt: { dir: "ivt_vec", ref: 700 }, conv925: { dir: "conv_vec", ref: 12 } };
  const DAILY = ["refl_day"];
  // current names, also for runs made before an option was renamed
  const LABELS = { refl_day: "أقصى انعكاسية لكل يوم", rain24: "المطر التراكمي +٢٤", ivt: "تدفق الأنهار الجوية" };
  const SINGLE = ["rain24", "tsprob"];   // one map for the whole run
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
  // Esri's grey canvas tiles need no key (CARTO started requiring one and stamps its tiles otherwise)
  const esri = (svc) => `https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`;
  const esriAttr = "© Esri, HERE, Garmin, © OpenStreetMap";
  const dark = L.tileLayer(esri("Canvas/World_Dark_Gray_Base"), { maxZoom: 19, maxNativeZoom: 16, attribution: esriAttr });
  const light = L.tileLayer(esri("Canvas/World_Light_Gray_Base"), { maxZoom: 19, maxNativeZoom: 16, attribution: esriAttr });
  const topo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenStreetMap, SRTM · OpenTopoMap" });
  const shade = L.tileLayer(esri("Elevation/World_Hillshade_Dark"), { maxZoom: 13, opacity: 0.45, attribution: "Esri" });
  const labelsDark = L.tileLayer(esri("Canvas/World_Dark_Gray_Reference"), { pane: "labels", maxZoom: 19, maxNativeZoom: 16 });
  const bases = { "داكنة": dark, "فاتحة": light, "تضاريس": topo };
  const baseKey = store.get("base2") || "داكنة";
  (bases[baseKey] || dark).addTo(map);
  if (store.get("shade") !== "0") shade.addTo(map);
  if (store.get("labels") !== "0") labelsDark.addTo(map);
  // boundaries of the Kingdom's 13 regions (Natural Earth), above the model colours and below the lightning
  map.createPane("regions"); map.getPane("regions").style.zIndex = 630; map.getPane("regions").style.pointerEvents = "none";
  const regionStyle = (f) => {
    const darkMap = !document.body.classList.contains("light-map");
    const col = darkMap ? "rgba(235,238,242,0.62)" : "rgba(40,44,52,0.6)";
    return f && f.properties.k === "border" ? { color: col, weight: 1.4, opacity: 1, fill: false, interactive: false }
      : { color: col, weight: 1, opacity: 1, dashArray: "5 4", fill: false, interactive: false };
  };
  const regions = L.geoJSON(null, { pane: "regions", style: regionStyle, interactive: false });
  if (store.get("regions") !== "0") regions.addTo(map);
  fetch("sa_regions.json?v=1").then((r) => r.json()).then((g) => regions.addData(g)).catch(() => {});
  L.control.layers(bases, { "حدود المناطق": regions, "ظلال التضاريس": shade, "أسماء الأماكن": labelsDark }, { position: "topleft" }).addTo(map);
  map.on("baselayerchange", (e) => {
    store.set("base2", e.name); document.body.classList.toggle("light-map", e.name !== "داكنة");
    regions.setStyle(regionStyle);
  });
  document.body.classList.toggle("light-map", baseKey !== "داكنة");
  map.on("overlayadd overlayremove", (e) => {
    const on = e.type === "overlayadd" ? "1" : "0";
    if (e.layer === shade) store.set("shade", on);
    if (e.layer === labelsDark) store.set("labels", on);
    if (e.layer === regions) store.set("regions", on);
  });
  L.control.zoom({ position: "topleft" }).addTo(map);
  map.attributionControl.setPrefix(false);
  map.on("zoomend", () => map.getContainer().classList.toggle("hide-labels", map.getZoom() < 7));

  function frameURL(i) {
    const f = S.frames[i];
    if (!f) return null;
    const name = f.single ? "main" : DAILY.includes(S.prod) ? f.date : String(f.h).padStart(3, "0");
    return `${base(S.man.domains[S.dom])}runs/${S.run}/${S.dom}/${S.prod}/${name}.png`;
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

  // arrows of water vapour transport, drawn over the colours
  const VecLayer = L.Layer.extend({
    initialize(opts) { this._ref = (opts && opts.ref) || 700; },
    onAdd(m) {
      this._c = L.DomUtil.create("canvas", "leaflet-zoom-hide");
      m.getPane("lightning").appendChild(this._c);
      m.on("moveend zoomend resize", this.redraw, this);
      this.redraw();
    },
    onRemove(m) { m.off("moveend zoomend resize", this.redraw, this); L.DomUtil.remove(this._c); },
    setData(v) { this._v = v; this.redraw(); },
    redraw() {
      const m = this._map; if (!m) return;
      const size = m.getSize(), dpr = window.devicePixelRatio || 1, c = this._c;
      c.width = size.x * dpr; c.height = size.y * dpr; c.style.width = size.x + "px"; c.style.height = size.y + "px";
      L.DomUtil.setPosition(c, m.containerPointToLayerPoint([0, 0]));
      const ctx = c.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, size.x, size.y);
      if (!this._v) return;
      const z = m.getZoom(), every = z <= 4 ? 2 : 1, used = new Set(), cell = z <= 5 ? 26 : 34;
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      this._v.forEach(([lat, lon, u, v], i) => {
        if (i % every) return;
        const p = m.latLngToContainerPoint([lat, lon]);
        if (p.x < -10 || p.y < -10 || p.x > size.x + 10 || p.y > size.y + 10) return;
        const key = Math.floor(p.x / cell) * 10000 + Math.floor(p.y / cell);
        if (used.has(key)) return; used.add(key);
        const mag = Math.hypot(u, v), len = Math.min(26, 8 + 18 * mag / this._ref), a = Math.atan2(-v, u);
        const x2 = p.x + Math.cos(a) * len / 2, y2 = p.y + Math.sin(a) * len / 2, x1 = p.x - Math.cos(a) * len / 2, y1 = p.y - Math.sin(a) * len / 2;
        for (const [col, w] of [["rgba(255,255,255,.75)", 3.2], ["#141a22", 1.5]]) {
          ctx.strokeStyle = col; ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
          ctx.moveTo(x2 - 6 * Math.cos(a - 0.45), y2 - 6 * Math.sin(a - 0.45)); ctx.lineTo(x2, y2);
          ctx.lineTo(x2 - 6 * Math.cos(a + 0.45), y2 - 6 * Math.sin(a + 0.45)); ctx.stroke();
        }
      });
    },
  });
  const vec = { layer: null, url: null };
  async function showVectors() {
    const f = S.frames[S.idx], d = S.man && S.man.domains[S.dom];
    const vc = VEC[S.prod];
    if (!vc || !f || f.h == null || !d) { if (vec.layer) { map.removeLayer(vec.layer); vec.layer = null; } vec.url = null; return; }
    const url = `${base(d)}runs/${S.run}/${S.dom}/${vc.dir}/${String(f.h).padStart(3, "0")}.json`;
    if (vec.layer && vec.ref !== vc.ref) { map.removeLayer(vec.layer); vec.layer = null; }
    if (!vec.layer) { vec.layer = new VecLayer({ ref: vc.ref }); vec.ref = vc.ref; vec.layer.addTo(map); }
    if (vec.url === url) return;
    vec.url = url;
    try { const j = await getJSON(url); if (vec.url === url && vec.layer) vec.layer.setData(j.v); } catch (e) { if (vec.layer) vec.layer.setData(null); }
  }

  function showFrame() {
    if (LX.on) return liShow();
    showVectors();
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
    if (f.single) {
      const a = new Date(Date.parse(S.man.init) + f.from * 3600e3), b = new Date(Date.parse(S.man.init) + f.to * 3600e3);
      return `من ${fmtWhen.format(a)} إلى ${fmtWhen.format(b)}` + (f.to - f.from < 24 ? " (حتى الآن)" : "");
    }
    if (f.date) {
      const t = new Date(Date.UTC(+f.date.slice(0, 4), +f.date.slice(4, 6) - 1, +f.date.slice(6, 8), 9));
      return fmtDay.format(t) + (f.hours < 24 ? ` · ${num(f.hours)} ساعة فقط` : "");
    }
    const t = new Date(Date.parse(S.man.init) + f.h * 3600e3);
    return `${fmtWhen.format(t)} · ساعة ${num(f.h)}`;
  }

  function buildFrames(keepTime) {
    if (LX.on) return;
    const d = S.man && S.man.domains[S.dom];
    const prevKey = keepTime && S.frames[S.idx] ? S.frames[S.idx] : null;
    if (!d) { S.frames = []; return; }
    // a domain may not have every product (the 1 km nest has hourly maps only)
    if (S.prod !== "lightning" && d.products && !d.products.includes(S.prod)) { S.prod = "refl"; $("prodSelect").value = "refl"; drawLegend(); }
    if (SINGLE.includes(S.prod)) { const r = d[S.prod]; S.frames = r ? [{ single: true, from: r.from, to: r.to }] : []; S.idx = 0; return; }
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
    if (LX.on) return liLegend();
    const p = S.man && S.man.products[S.prod];
    if (!p) { $("legend").innerHTML = ""; return; }
    const lg = p.legend;
    const grad = lg.stops.map((x) => `${rgba(x.c, x.a)} ${(x.p * 100).toFixed(1)}%`).join(", ");
    const step = lg.stops.length > 7 ? 2 : 1;
    const ticks = lg.stops.map((x, i) => (i % step === 0 || i === lg.stops.length - 1)
      ? `<span style="left:${(x.p * 100).toFixed(1)}%">${num(x.v, x.v < 1 ? 1 : 0)}</span>` : "").join("");
    $("legend").innerHTML = `<div class="legend-title"><span>${LABELS[S.prod] || p.label}</span><span>${p.unit}</span></div>
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

  // the domains as one drop-down list, next to the options list
  function drawChips() {
    const box = $("domChips");
    const ids = ["sa", "d02", "d03"].filter((id) => S.man && S.man.domains[id]);  // the Kingdom-wide run replaces the western 9 km parent
    if (!ids.length) { box.innerHTML = ""; return; }
    let sel = $("domSelect");
    if (!sel) {
      box.innerHTML = `<select id="domSelect" class="prod-select dom-select" aria-label="المجال"></select>`;
      sel = $("domSelect");
      sel.onchange = () => setDomain(sel.value, true);
    }
    sel.innerHTML = ids.map((id) => { const d = S.man.domains[id]; return `<option value="${id}">${d.name} ${d.res}</option>`; }).join("");
    sel.value = ids.includes(S.dom) ? S.dom : ids[0];
  }

  function drawProducts() {
    const sel = $("prodSelect");
    const P = (S.man && S.man.products) || {};
    const opt = (k) => (P[k] ? `<option value="${k}">${LABELS[k] || P[k].label}</option>` : "");
    // one flat list, live lightning first
    sel.innerHTML = `<option value="lightning">رادار البرق المباشر</option>` + [...HOURLY, ...SINGLE, ...DAILY].map(opt).join("");
    const listed = [...HOURLY, ...SINGLE, ...DAILY].includes(S.prod);
    if ((!P[S.prod] || !listed) && S.prod !== "lightning") S.prod = "refl";
    sel.value = S.prod;
  }

  function drawRects() {
    S.rects.forEach((r) => map.removeLayer(r));
    S.rects = [];
    return;  // the domain buttons are enough; the dashed outlines were clutter
    // eslint-disable-next-line no-unreachable
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
    if (id === "d01") id = S.man && S.man.domains.sa ? "sa" : "d02";
    if (LX.on) { if (S.man && S.man.domains[id]) S.dom = id; return; }
    if (!S.man || !S.man.domains[id]) id = ["d02", "sa", "d03"].find((k) => S.man && S.man.domains[k]) || Object.keys((S.man && S.man.domains) || {})[0] || "d01";
    S.dom = id; store.set("dom", id);
    buildFrames(true);
    drawChips(); drawRects(); showFrame();
    const d = S.man && S.man.domains[id];
    if (fit && d && d.bounds) map.fitBounds(d.bounds, { padding: [10, 10] });
  }

  // the current domain if it has the product, otherwise the first that does
  function domFor(p) {
    const has = (k) => { const d = S.man && S.man.domains[k]; return d && (!d.products || d.products.includes(p)); };
    if (p === "lightning" || has(S.dom)) return S.dom;
    return ["sa", "d02", "d03", "d01"].find(has) || S.dom;
  }

  function setProduct(p) {
    S.prod = p; store.set("prod", p);
    if (p === "lightning") { if (!LX.on) liEnter(); return; }
    if (LX.on) liExit();
    // a product made only on some domains (water vapour transport: the Kingdom run) moves there
    const k = domFor(p);
    if (k !== S.dom) { drawLegend(); setDomain(k, true); return; }
    setDomain(S.dom, false);
    drawLegend();
  }


  // ------------------------------------------------------------------ observed lightning
  // Flashes seen by the lightning imager on the European geostationary satellite (third generation,
  // over 0°): every 5 minutes EUMETSAT publishes the area covered by flashes. Each lit pixel of that
  // image becomes a bolt; bolts are coloured by age over the last hour.
  const LI_WMS = "https://view.eumetsat.int/geoserver/wms";
  const LI_BOX = { s: 12, n: 34, w: 32, e: 60, res: 0.04 };
  const LI_STEP = 5 * 60e3, LI_WIN = 60 * 60e3, LI_BACK = 100 * 60e3;
  const LI_AGES = [[10, "#fff45c"], [20, "#ffd23a"], [40, "#f6a21e"], [60, "#c8641a"]];
  const fmtClock = new Intl.DateTimeFormat(LOC, { timeZone: TZ, hour: "numeric", minute: "2-digit" });
  const LX = { on: false, got: new Map(), timer: null, layer: null, busy: false, failed: false, shown: 0 };
  map.createPane("lightning"); map.getPane("lightning").style.zIndex = 640; map.getPane("lightning").style.pointerEvents = "none";

  function boltPath(ctx, x, y, h) {
    const P = [[-0.02, -0.5], [0.3, -0.5], [0.1, -0.1], [0.3, -0.1], [-0.22, 0.5], [-0.04, 0.04], [-0.24, 0.04]];
    ctx.beginPath();
    P.forEach(([a, b], i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, x + a * h, y + b * h));
    ctx.closePath();
  }
  function ageColor(min) { for (const [m, c] of LI_AGES) if (min <= m) return c; return LI_AGES[LI_AGES.length - 1][1]; }

  const BoltLayer = L.Layer.extend({
    onAdd(m) {
      this._c = L.DomUtil.create("canvas", "leaflet-zoom-hide");
      m.getPane("lightning").appendChild(this._c);
      m.on("moveend zoomend resize", this.redraw, this);
      this.redraw();
    },
    onRemove(m) { m.off("moveend zoomend resize", this.redraw, this); L.DomUtil.remove(this._c); },
    redraw() {
      const m = this._map; if (!m) return;
      const size = m.getSize(), dpr = window.devicePixelRatio || 1, c = this._c;
      c.width = size.x * dpr; c.height = size.y * dpr; c.style.width = size.x + "px"; c.style.height = size.y + "px";
      L.DomUtil.setPosition(c, m.containerPointToLayerPoint([0, 0]));
      const ctx = c.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, size.x, size.y);
      const f = LX.on && S.frames[S.idx];
      LX.shown = 0;
      if (!f) return;
      const end = f.t, start = end - LI_WIN, cell = 16, grid = new Map();
      for (const [t, arr] of LX.got) {
        if (t > end || t <= start) continue;
        for (let i = 0; i < arr.length; i += 2) {
          const p = m.latLngToContainerPoint([arr[i], arr[i + 1]]);
          if (p.x < -20 || p.y < -20 || p.x > size.x + 20 || p.y > size.y + 20) continue;
          const k = Math.floor(p.x / cell) * 100000 + Math.floor(p.y / cell);
          const g = grid.get(k);
          if (!g || g.t < t) grid.set(k, { x: p.x, y: p.y, t });
        }
      }
      const items = [...grid.values()].sort((a, b) => a.t - b.t);  // newest drawn on top
      const h = m.getZoom() >= 9 ? 28 : m.getZoom() >= 7 ? 24 : 20;
      ctx.lineJoin = "round"; ctx.lineWidth = 1.3; ctx.strokeStyle = "rgba(25,16,0,.9)";
      ctx.shadowColor = "rgba(0,0,0,.45)"; ctx.shadowBlur = 3;
      for (const it of items) {
        boltPath(ctx, it.x, it.y, h);
        ctx.fillStyle = ageColor((end - it.t) / 60e3);
        ctx.fill(); ctx.stroke();
      }
      LX.shown = items.length;
    },
  });

  function liTimeISO(t) { return new Date(t).toISOString().replace(/\.\d+Z$/, "Z"); }

  const LI_W = Math.round((LI_BOX.e - LI_BOX.w) / LI_BOX.res), LI_H = Math.round((LI_BOX.n - LI_BOX.s) / LI_BOX.res);
  function liPoints(idx) {  // lit pixel numbers -> lat, lon pairs
    const out = new Float32Array(idx.length * 2);
    for (let k = 0; k < idx.length; k++) {
      const y = Math.floor(idx[k] / LI_W), x = idx[k] - y * LI_W;
      out[2 * k] = LI_BOX.n - (y + 0.5) * LI_BOX.res; out[2 * k + 1] = LI_BOX.w + (x + 0.5) * LI_BOX.res;
    }
    return out;
  }

  async function liFetch(t) {
    const B = LI_BOX, W = LI_W, H = LI_H;
    const url = `${LI_WMS}?service=WMS&request=GetMap&version=1.3.0&layers=mtg_fd:li_afa&styles=&crs=EPSG:4326` +
      `&bbox=${B.s},${B.w},${B.n},${B.e}&width=${W}&height=${H}&format=image/png&transparent=true&time=${liTimeISO(t)}`;
    const r = await fetch(url, { mode: "cors" });
    if (!r.ok || !(r.headers.get("content-type") || "").startsWith("image/")) return null;
    const blob = await r.blob();
    if (!blob.size) return null;
    const bmp = await createImageBitmap(blob);
    const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const cx = cv.getContext("2d", { willReadFrequently: true });
    cx.drawImage(bmp, 0, 0, W, H);
    const d = cx.getImageData(0, 0, W, H).data, idx = [];
    for (let k = 0, n = W * H; k < n; k++) if (d[k * 4 + 3] > 8) idx.push(k);
    return idx;
  }

  // what was fetched stays in this browser, so reopening the page shows the last hour at once
  const LI_CACHE = "swrf.li1";
  function liCacheLoad() {
    try {
      const c = JSON.parse(localStorage.getItem(LI_CACHE) || "{}");
      const old = Date.now() - LI_BACK - LI_WIN;
      for (const [t, idx] of Object.entries(c)) if (+t > old && !LX.got.has(+t)) LX.got.set(+t, liPoints(idx));
      LX.raw = c;
    } catch (e) { LX.raw = {}; }
  }
  function liCacheSave() {
    try {
      const keep = {};
      for (const t of LX.got.keys()) if (LX.raw[t]) keep[t] = LX.raw[t];
      LX.raw = keep;
      localStorage.setItem(LI_CACHE, JSON.stringify(keep));
    } catch (e) { /* storage full or blocked: fine */ }
  }

  function liFrames() {
    if (!LX.on) return;
    const times = [...LX.got.keys()].sort((a, b) => a - b);
    const newest = times.length ? times[times.length - 1] : 0;
    const atEnd = S.idx >= S.frames.length - 1;
    S.frames = times.filter((t) => t >= newest - LI_WIN).map((t) => ({ t }));
    if (atEnd || !S.playing) S.idx = S.frames.length - 1;
    drawLegend(); showFrame();
  }

  async function liLoad() {
    if (LX.busy) return;
    LX.busy = true;
    if (!LX.raw) liCacheLoad();
    // images appear about 10 minutes after their time; ask newest first and draw as each one arrives
    const top = Math.floor((Date.now() - 5 * 60e3) / LI_STEP) * LI_STEP, want = [];
    for (let t = top; t > top - LI_BACK; t -= LI_STEP) if (!LX.got.has(t)) want.push(t);
    let next = 0, since = 0;
    const worker = async () => {
      while (next < want.length) {
        const t = want[next++];
        try {
          const idx = await liFetch(t);
          if (idx) {
            LX.got.set(t, liPoints(idx)); LX.raw[t] = idx;
            if (++since >= 2 || LX.got.size <= 2) { since = 0; liFrames(); }
          }
        } catch (e) { /* not published yet, or offline */ }
      }
    };
    await Promise.all(Array.from({ length: 7 }, worker));  // the server allows 8 at once
    const times = [...LX.got.keys()].sort((a, b) => a - b);
    const newest = times.length ? times[times.length - 1] : 0;
    for (const t of times) if (t < newest - LI_WIN - LI_STEP) LX.got.delete(t);
    LX.failed = !LX.got.size;
    LX.busy = false;
    liCacheSave();
    liFrames();
  }

  function liEnter() {
    LX.on = true;
    if (vec.layer) { map.removeLayer(vec.layer); vec.layer = null; vec.url = null; }
    stop(); clearOverlay();
    S.rects.forEach((r) => map.removeLayer(r)); S.rects = [];
    $("domChips").hidden = true; $("mapEmpty").hidden = true;
    if (!LX.layer) LX.layer = new BoltLayer();
    LX.layer.addTo(map);
    if (!LX.raw) liCacheLoad();
    S.frames = []; S.idx = 0;
    liFrames();
    liLoad();
    clearInterval(LX.timer); LX.timer = setInterval(liLoad, 2.5 * 60e3);
  }
  function liExit() {
    LX.on = false;
    clearInterval(LX.timer); LX.timer = null;
    stop();
    if (LX.layer) map.removeLayer(LX.layer);
    $("domChips").hidden = false;
    $("mapEmpty").hidden = !!(S.man && Object.keys(S.man.domains).length);
  }

  function liShow() {
    S.idx = Math.max(0, Math.min(S.idx, S.frames.length - 1));
    const f = S.frames[S.idx];
    $("timeRange").max = Math.max(0, S.frames.length - 1);
    $("timeRange").value = S.idx;
    $("timeLabel").textContent = f ? `البرق في الساعة المنتهية ${fmtClock.format(f.t)}`
      : LX.busy ? "جارٍ جلب رصد البرق…" : "تعذّر جلب رصد البرق، سيُعاد المحاولة";
    if (LX.layer) LX.layer.redraw();
    const n = $("liCount"); if (n) n.textContent = f ? (LX.shown ? `مواضع البرق: ${num(LX.shown)}` : "لا برق في هذه الساعة") : "";
  }

  function liLegend() {
    const svg = (c) => `<svg viewBox="-6 -6 12 12" width="13" height="13"><path d="M-0.1,-5 L3,-5 L1,-1 L3,-1 L-2.2,5 L-0.4,0.4 L-2.4,0.4 Z" fill="${c}" stroke="#1a1000" stroke-width=".7" stroke-linejoin="round"/></svg>`;
    const keys = LI_AGES.map(([m, c], i) => `<span>${svg(c)}${i === 0 ? `آخر ${num(m)} د` : `حتى ${num(m)} د`}</span>`).join("");
    $("legend").innerHTML = `<div class="legend-title"><span>البرق المرصود من القمر الأوروبي، يتحدث كل ٥ دقائق</span><span id="liCount">${LX.shown ? `مواضع البرق: ${num(LX.shown)}` : ""}</span></div>
      <div class="bolt-key">${keys}</div>`;
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
  // the places shown on the map and in the cities tab (older runs carry a longer list)
  const CITY_KEEP = new Set(["makkah", "jumum", "taif", "jeddah", "rabigh", "khulais", "kamil", "lith", "qunfudhah", "madinah"]);
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
    const res = Object.fromEntries(Object.entries((S.man && S.man.domains) || {}).map(([k, d]) => [k, d.res]));
    box.innerHTML = S.meteo.cities.filter((c) => !q || c.name.includes(q)).map((c) => `
      <div class="city"><div class="city-head"><span class="city-name">${c.name}</span>
      <span class="city-sum">${res[c.domain] || ""}</span></div>
      <div class="city-sum">${citySummary(c)}</div>${cityChart(c)}</div>`).join("");
  }
  $("cityFilter").oninput = drawCities;

  function drawCityMarkers() {
    if (S.cityLayer) map.removeLayer(S.cityLayer);
    S.cityLayer = L.layerGroup().addTo(map);
    return;  // the base map already names the cities; the extra dots and Arabic labels were clutter
    // eslint-disable-next-line no-unreachable
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
      S.points[key] = fetch(`${base(d)}runs/${S.run}/${d.points.file}?n=${d.points.hours.length}`)
        .then((r) => (r.ok ? r.arrayBuffer() : null)).then((b) => (b ? new Uint8Array(b) : null)).catch(() => null);
    }
    return { info: d.points, bytes: await S.points[key] };
  }
  const DECODE = { rain1h: (c) => (c / 25) ** 2, refl: (c) => c / 3, t2: (c) => c / 4 - 10, wind: (c) => c / 2 };
  async function pointSeries(lat, lon) {
    // every domain that contains the point, coarse first; finer domains replace the hours they cover
    const dxOf = (k) => { const d = S.man.domains[k]; return d.dx || (d.points && d.points.dx) || 0; };
    const order = Object.keys(S.man.domains).sort((a, b) => dxOf(b) - dxOf(a) || a.localeCompare(b));
    const merged = {};
    let best = null;
    for (const dom of order) {
      const pd = await pointData(dom);
      if (!pd || !pd.bytes) continue;
      const P = pd.info, [x, y] = lccForward(S.man.domains[dom].proj || S.man.proj, lon, lat);
      const i = Math.round((x - P.x00) / P.dx), j = Math.round((y - P.y00) / P.dx);
      if (i < 1 || j < 1 || i > P.nx - 2 || j > P.ny - 2) continue;
      best = dom;
      const nh = P.hours.length;
      P.vars.forEach((v, k) => {
        const m = merged[v] || (merged[v] = new Map());
        P.hours.forEach((h, hi) => {
          // the first hour of a domain has no rain or gust yet
          if (hi === 0 && (v === "rain1h" || v === "wind")) { if (!m.has(h)) m.set(h, null); return; }
          m.set(h, DECODE[v](pd.bytes[((k * nh + hi) * P.ny + j) * P.nx + i]));
        });
      });
    }
    if (!best) return null;
    const series = {};
    for (const [v, m] of Object.entries(merged)) series[v] = [...m.entries()].sort((p, q) => p[0] - q[0]);
    series.rain = series.rain1h.map(([h, v]) => [h, v == null ? null : Math.round(v * 10) / 10]);
    let acc = 0;
    series.acc = series.rain.map(([h, v]) => [h, (acc += v || 0)]);
    return { dom: best, series, lat, lon };
  }
  function pointHTML(pt) {
    if (!pt) return `<div class="muted">خارج مجالات النموذج</div>`;
    const f = S.frames[S.idx];
    const h = f && f.h != null ? f.h : null;
    const at = (v) => { const r = (pt.series[v] || []).find((x) => x[0] === h); return r ? r[1] : null; };
    const res = (S.man.domains[pt.dom] || {}).res || "";
    const now = h == null ? "" : `<div class="pt-now">
        <span><b>${num(at("rain"), 1)}</b> ملم</span><span><b>${num(at("refl"))}</b> ديسيبل</span>
        <span><b>${num(at("t2"))}</b>°</span><span><b>${num(at("wind"))}</b> كم/س</span></div>`;
    return `<div class="pt-head"><strong>${num(pt.lat, 2)}° ش، ${num(pt.lon, 2)}° ق</strong><small>${res}</small></div>
      ${now}<div class="city-sum">${citySummary(pt)}</div>${cityChart(pt)}`;
  }
  map.on("click", async (e) => {
    if (!S.man || LX.on) return;
    const pop = L.popup({ maxWidth: 360, minWidth: 290 }).setLatLng(e.latlng).setContent(`<div class="muted">جارٍ التحميل…</div>`).openOn(map);
    const pt = await pointSeries(e.latlng.lat, e.latlng.lng);
    pop._pt = pt; S.pointPopup = pop;
    pop.setContent(pointHTML(pt));
  });

  // ------------------------------------------------------------------ runs
  const fmtRun = new Intl.DateTimeFormat(LOC, { timeZone: TZ, day: "numeric", month: "long", hour: "numeric" });
  function runShort(r) {
    return fmtRun.format(new Date(Date.UTC(+r.slice(0, 4), +r.slice(4, 6) - 1, +r.slice(6, 8), +r.slice(8, 10))));
  }
  function runName(r) {
    const t = new Date(Date.UTC(+r.slice(0, 4), +r.slice(4, 6) - 1, +r.slice(6, 8), +r.slice(8, 10)));
    return `تشغيل ${fmtStamp.format(t)}`;
  }

  async function loadRun(run, first) {
    S.run = run;
    try { S.man = await getJSON(`${DATA}runs/${run}/manifest.json`); } catch (e) { S.man = null; }
    try { S.meteo = await getJSON(`${DATA}runs/${run}/meteo.json`); } catch (e) { S.meteo = null; }
    try {  // add the Kingdom-wide 9 km domain from its own branch when that run exists
      const sa = await getJSON(`${DATA_SA}runs/${run}/manifest.json`);
      if (!S.man) S.man = { ...sa, domains: {} };
      for (const [k, d] of Object.entries(sa.domains || {})) S.man.domains[k] = { ...d, base: DATA_SA, proj: sa.proj };
      S.man.products = { ...(sa.products || {}), ...(S.man.products || {}) };
    } catch (e) { /* not made for this run */ }
    try {  // the 1 km nest (only its own grid; the 9 and 3 km grids there just feed it)
      const k1 = await getJSON(`${DATA_1K}runs/${run}/manifest.json`);
      if (S.man && k1.domains && k1.domains.d03) {
        S.man.domains.d03 = { ...k1.domains.d03, base: DATA_1K, proj: k1.proj };
        S.man.products = { ...(k1.products || {}), ...(S.man.products || {}) };
      }
    } catch (e) { /* not made for this run */ }
    if (S.meteo && S.meteo.cities) S.meteo.cities = S.meteo.cities.filter((c) => CITY_KEEP.has(c.id));
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
    $("runLabel").textContent = `تطوير فهد متعب العيسي${st}`;
    drawProducts(); drawLegend();
    if (first && !LX.on) { S.dom = domFor(S.prod); buildFrames(false); S.idx = 0; }
    setDomain(S.dom, first);
    drawCityMarkers();
    if (!$("p-cities").hidden) drawCities();
  }

  async function refreshRuns(first) {
    let idx;
    try { idx = await getJSON(DATA + "runs.json"); } catch (e) { idx = { runs: [] }; }
    S.runs = idx.runs || [];
    const sel = $("runSelect");
    sel.hidden = !S.runs.length;  // the run time lives here, so it shows even with one run
    sel.innerHTML = S.runs.map((r) => `<option value="${r.run}">${runShort(r.run)}${r.status === "running" ? " · جارٍ" : ""}</option>`).join("");
    if (!S.runs.length) { $("mapEmpty").hidden = false; return; }
    if (first || !S.run) {
      const complete = S.runs.find((r) => r.status === "complete");
      const newest = S.runs[0];
      // prefer the newest run once it has at least a day of the 3 km domain
      // a running run is shown once it covers the day through 6 pm (hour 15); before that, the last complete one
      const pick = newest.status === "running" && complete && ((newest.hours || {}).d02 || 0) < 15 ? complete : newest;
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


  // ------------------------------------------------------------------ MJO and warm/cold events
  const CL = window.SWRF_CLIMATE || DATA.replace("/model-data/", "/climate-data/");
  const M = { st: null, map: null, layer: "wc", day: 0, img: null, vec: null, vecs: null, loaded: 0 };
  const AR_AREA = { 1: "غرب نصف الكرة الغربي وأفريقيا", 2: "غرب المحيط الهندي", 3: "شرق المحيط الهندي", 4: "القارة البحرية (إندونيسيا)",
                    5: "القارة البحرية (إندونيسيا)", 6: "غرب المحيط الهادئ", 7: "غرب المحيط الهادئ", 8: "نصف الكرة الغربي وأفريقيا" };
  const fmtDayD = new Intl.DateTimeFormat(LOC, { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" });
  const fmtDM = new Intl.DateTimeFormat(LOC, { timeZone: "UTC", day: "numeric" });
  const dOf = (s) => new Date(s + "T00:00:00Z");
  const strength = (a) => (a < 1 ? "ضعيف" : a < 1.5 ? "متوسط" : a < 2.5 ? "قوي" : "قوي جدًا");

  function scaleColor(lg, v) {
    const st = lg.stops, p = Math.max(0, Math.min(1, (v - lg.vmin) / (lg.vmax - lg.vmin)));
    let k = 0; while (k < st.length - 2 && st[k + 1].p < p) k++;
    const a = st[k], b = st[k + 1], t = b.p > a.p ? (p - a.p) / (b.p - a.p) : 0;
    const h = (c, i) => parseInt(c.slice(i, i + 2), 16);
    return `rgb(${[1, 3, 5].map((i) => Math.round(h(a.c, i) + (h(b.c, i) - h(a.c, i)) * t)).join(",")})`;
  }

  async function mjoOpen() {
    if (!M.st || Date.now() - M.loaded > 30 * 60e3) {
      try { M.st = await getJSON(CL + "mjo.json"); M.loaded = Date.now(); } catch (e) {
        $("mjoNow").innerHTML = `<p class="muted">لم تُحسب بيانات التذبذب بعد. تتحدث مرة كل يوم صباحًا.</p>`; return;
      }
      mjoText(); mjoPhase(); mjoPwTable();
    }
    mjoMap(); aoChart(); waveCard(); riverCard();
  }

  function mjoText() {
    const st = M.st, obsNow = st.rmm_now, now = st.rmm_today || st.rmm_now;
    const r = st.report;
    $("mjoReport").hidden = !r;
    const para = (l, i, sec) => /^(المصادر|الخلاصة)/.test(l) ? `<p class="${l.startsWith("المصادر") ? "src" : "sum"}">${l}</p>`
      : `<p${i === 0 && sec === 0 ? ' class="lead"' : ""}>${l}</p>`;
    if (r) $("mjoReport").innerHTML = `<h3>${r.title}</h3>` + (r.sections && r.sections.length
      ? r.sections.map((s, k) => `<details class="rsec" open><summary>${s.heading}</summary>${s.lines.map((l, i) => para(l, i, k)).join("")}</details>`).join("")
      : r.lines.map((l) => `<p>${l}</p>`).join("")) +
      `<p class="hint">يصدر هذا التقرير وكل ما في هذه الصفحة كل ليلة قرابة منتصف الليل بتوقيت مكة بعد اكتمال تشغيل نموذجنا للمملكة، ويُعاد بناء قسمي المملكة ومنطقة مكة حين يكتمل تشغيل ٣ كم قبل الرابعة والنصف فجرًا${r.issued ? ` · صدر ${fmtStamp.format(new Date(r.issued))}` : ""}.</p>`;
    let html = "";
    if (now) {
      const wet = [1, 2, 7, 8].includes(now.phase), season = st.wet_season;
      html += `<div class="mjo-big"><span>التذبذب الآن في <b>الطور ${num(now.phase)}</b></span><span>بشدة ${num(now.amp, 1)} (${strength(now.amp)})</span></div>
        <div class="mjo-row"><span>الحمل العميق المصاحب</span><span>${AR_AREA[now.phase]}</span></div>
        <div class="mjo-row"><span>أثره على المملكة</span><span class="${season ? (wet ? "wet" : "dry") : ""}">${
          now.amp < 1 ? "ضعيف التأثير لأن التذبذب ضعيف" : !season ? "خارج موسم الأمطار، تأثيره محدود" : wet ? "طور رطب: يدعم الأمطار" : "طور جاف: يكبت الأمطار"}</span></div>
        <div class="mjo-row"><span>${st.rmm_today ? "اليوم (تقدير من جي إف إس)" : "آخر رصد"}</span><span>${fmtDayD.format(dOf(now.d))}</span></div>` +
        (st.rmm_today && obsNow ? `<div class="mjo-row"><span>آخر رصد رسمي</span><span>${fmtDayD.format(dOf(obsNow.d))}: الطور ${num(obsNow.phase)} بشدة ${num(obsNow.amp, 1)}</span></div>` : "");
    }
    html += `<div class="mjo-row"><span>الحدث الدافئ الآن</span><span>${st.warm.region}</span></div>
      <div class="mjo-row"><span>الحدث البارد الآن</span><span>${st.cold.region}</span></div>`;
    if (st.rmm_fc && st.rmm_fc.length) {
      const f = st.rmm_fc[Math.min(9, st.rmm_fc.length - 1)];
      html += `<div class="mjo-row"><span>بعد عشرة أيام تقريبًا</span><span>الطور ${num(f.phase)} بشدة ${num(f.amp, 1)}</span></div>`;
    }
    $("mjoNow").innerHTML = `<h3>التذبذب المداري (مادن-جوليان)</h3>` + html;
    $("mjoUpdated").textContent = `آخر تحديث: ${fmtStamp.format(new Date(st.updated))} · توقع جي إف إس لدورة ${fmtDayD.format(dOf(st.cycle.slice(0, 4) + "-" + st.cycle.slice(4, 6) + "-" + st.cycle.slice(6, 8)))}` +
      (st.fit ? ` · توافق الإسقاط مع الرصد ${num(st.fit.r1, 2)} و${num(st.fit.r2, 2)}` : "");
  }

  // RMM phase diagram drawn like the Bureau of Meteorology chart (English labels, white panel)
  function mjoPhase() {
    const st = M.st, R = 4, S = 44, PL = 46, PT = 50, PR = 14, PB = 44;
    const W = PL + 2 * R * S + PR, H = PT + 2 * R * S + PB;
    const X = (x) => PL + (x + R) * S, Y = (y) => PT + (R - y) * S;
    const clip = (v) => Math.max(-R, Math.min(R, v));
    const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const dm = (d) => `${+d.slice(8)}${MON[+d.slice(5, 7) - 1]}`;
    const init = st.cycle ? `${+st.cycle.slice(6, 8)} ${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][+st.cycle.slice(4, 6) - 1]} ${st.cycle.slice(0, 4)}` : "";
    let g = `<svg viewBox="0 0 ${W} ${H + 26}" direction="ltr" font-family="Helvetica, Arial, sans-serif" style="background:#fff;border-radius:8px">`;
    g += `<text x="${W / 2}" y="20" text-anchor="middle" font-size="15" fill="#111">MJO Index Forecast initialised: ${init}</text>`;
    g += `<text x="${W / 2}" y="37" text-anchor="middle" font-size="11" fill="#333">Model: GFS (projection, calibrated on BoM RMM)</text>`;
    g += `<rect x="${X(-R)}" y="${Y(R)}" width="${2 * R * S}" height="${2 * R * S}" fill="#fff" stroke="#111" stroke-width="1"/>`;
    // axes through the centre and the diagonals, dotted
    const dot = `stroke="#444" stroke-width="0.8" stroke-dasharray="1.5 3"`;
    g += `<line x1="${X(-R)}" y1="${Y(0)}" x2="${X(R)}" y2="${Y(0)}" ${dot}/><line x1="${X(0)}" y1="${Y(-R)}" x2="${X(0)}" y2="${Y(R)}" ${dot}/>`;
    g += `<line x1="${X(-R)}" y1="${Y(-R)}" x2="${X(R)}" y2="${Y(R)}" ${dot}/><line x1="${X(-R)}" y1="${Y(R)}" x2="${X(R)}" y2="${Y(-R)}" ${dot}/>`;
    g += `<circle cx="${X(0)}" cy="${Y(0)}" r="${S}" fill="none" stroke="#111" stroke-width="0.7"/>`;
    for (let t = -R; t <= R; t++) {
      g += `<line x1="${X(t)}" y1="${Y(-R)}" x2="${X(t)}" y2="${Y(-R) + 4}" stroke="#111"/><text x="${X(t)}" y="${Y(-R) + 16}" text-anchor="middle" font-size="10" fill="#111">${t < 0 ? "−" + -t : t}</text>`;
      g += `<line x1="${X(-R) - 4}" y1="${Y(t)}" x2="${X(-R)}" y2="${Y(t)}" stroke="#111"/><text x="${X(-R) - 7}" y="${Y(t) + 3.5}" text-anchor="end" font-size="10" fill="#111">${t < 0 ? "−" + -t : t}</text>`;
    }
    g += `<text x="${X(0)}" y="${Y(-R) + 33}" text-anchor="middle" font-size="13" fill="#111">RMM1</text>`;
    g += `<text x="14" y="${Y(0)}" text-anchor="middle" font-size="13" fill="#111" transform="rotate(-90 14 ${Y(0)})">RMM2</text>`;
    // phase numbers and regions
    const ph = { 1: [-3.4, -2.4], 2: [-2.4, -3.4], 3: [2.4, -3.4], 4: [3.4, -2.4], 5: [3.4, 2.6], 6: [2.6, 3.4], 7: [-2.6, 3.4], 8: [-3.4, 2.6] };
    for (const [k, [x, y]] of Object.entries(ph)) g += `<text x="${X(x)}" y="${Y(y) + 6}" text-anchor="middle" font-size="16" fill="#111">${k}</text>`;
    g += `<text x="${X(0)}" y="${Y(3.55)}" text-anchor="middle" font-size="13" fill="#111"><tspan x="${X(0)}">Western</tspan><tspan x="${X(0)}" dy="15">Pacific</tspan></text>`;
    g += `<text x="${X(0)}" y="${Y(-3.15)}" text-anchor="middle" font-size="13" fill="#111"><tspan x="${X(0)}">Indian</tspan><tspan x="${X(0)}" dy="15">Ocean</tspan></text>`;
    g += `<text x="${X(-3.45)}" y="${Y(0)}" text-anchor="middle" font-size="13" fill="#111" transform="rotate(-90 ${X(-3.45)} ${Y(0)})"><tspan x="${X(-3.45)}" dy="-7">West. Hem.</tspan><tspan x="${X(-3.45)}" dy="15">and Africa</tspan></text>`;
    g += `<text x="${X(3.45)}" y="${Y(0)}" text-anchor="middle" font-size="13" fill="#111" transform="rotate(90 ${X(3.45)} ${Y(0)})"><tspan x="${X(3.45)}" dy="-7">Maritime</tspan><tspan x="${X(3.45)}" dy="15">Continent</tspan></text>`;
    const obs = (st.rmm_obs || []).slice(-40), fc = st.rmm_fc || [];
    const label = (o, dx, dy, w) => `<text x="${X(clip(o.r1)) + dx}" y="${Y(clip(o.r2)) + dy}" font-size="10" ${w ? 'font-weight="700"' : ""} fill="#111" stroke="#fff" stroke-width="2.5" paint-order="stroke">${dm(o.d)}</text>`;
    if (obs.length) {
      g += `<polyline fill="none" stroke="#9a9a9a" stroke-width="3.2" stroke-linejoin="round" points="${obs.map((o) => `${X(clip(o.r1))},${Y(clip(o.r2))}`).join(" ")}"/>`;
      obs.forEach((o, i) => {
        if ((obs.length - 1 - i) % 7 === 0) {
          const x = X(clip(o.r1)), y = Y(clip(o.r2));
          g += `<path d="M${x},${y - 5} L${x + 3.5},${y} L${x},${y + 5} L${x - 3.5},${y} Z" fill="#111"/>`;
          if (i !== obs.length - 1) g += label(o, 6, -5);
        }
      });
      const o1 = obs[obs.length - 1];
      g += `<circle cx="${X(clip(o1.r1))}" cy="${Y(clip(o1.r2))}" r="4" fill="#111"/>` + label({ ...o1, d: o1.d }, -8, 14, true).replace(">" + dm(o1.d) + "<", ">INITIAL<");
      if (fc.length) {
        g += `<polyline fill="none" stroke="#111" stroke-width="2.6" stroke-linejoin="round" points="${[o1, ...fc].map((o) => `${X(clip(o.r1))},${Y(clip(o.r2))}`).join(" ")}"/>`;
        const n = fc.length, marks = [...new Set([Math.round(n / 3) - 1, Math.round(2 * n / 3) - 1, n - 1])].filter((i) => i >= 0);
        for (const i of marks) {
          const f = fc[i];
          g += `<circle cx="${X(clip(f.r1))}" cy="${Y(clip(f.r2))}" r="4" fill="#111"/>` + label(f, 6, 14, true);
        }
      }
    }
    // legend
    const ly = H + 8;
    g += `<line x1="${PL}" y1="${ly}" x2="${PL + 26}" y2="${ly}" stroke="#9a9a9a" stroke-width="3.2"/><text x="${PL + 32}" y="${ly + 4}" font-size="11" fill="#111">Observed (BoM)</text>`;
    g += `<line x1="${PL + 150}" y1="${ly}" x2="${PL + 176}" y2="${ly}" stroke="#111" stroke-width="2.6"/><text x="${PL + 182}" y="${ly + 4}" font-size="11" fill="#111">Forecast (GFS)</text>`;
    $("mjoPhase").innerHTML = g + "</svg>";
  }

  function mjoMap() {
    if (!M.st) return;
    if (!M.bound) {
      M.bound = true;
      document.querySelectorAll("#mjoLayer button").forEach((b) => b.onclick = () => {
        document.querySelectorAll("#mjoLayer button").forEach((x) => x.classList.toggle("on", x === b));
        M.layer = b.dataset.l; mjoShow();
      });
      $("mjoDay").oninput = (e) => { M.day = +e.target.value; mjoShow(); };
    }
    $("mjoDay").max = (M.st.days || []).length - 1;
    mjoShow();
  }

  function mjoShow() {
    const st = M.st, k = M.day, lay = M.layer, kk = String(k).padStart(2, "0");
    const figs = st.figs || {};
    const url = `${CL}fig/${lay}_${kk}.png?v=${encodeURIComponent(st.updated)}`;
    $("mjoFig").src = url; $("mjoFigLink").href = url;
    $("mjoFigWrap").classList.toggle("fit", lay === "pw");
    const d = st.days[k];
    $("mjoDayLabel").textContent = d ? (k === 0 ? `اليوم: ${fmtDayD.format(dOf(d))}` : `+${num(k)} · ${fmtDayD.format(dOf(d))}`) : "";
    const lg = figs[lay];
    if (!lg) { $("mjoLegend").innerHTML = ""; return; }
    const grad = lg.stops.map((x) => `${x.c} ${(x.p * 100).toFixed(1)}%`).join(", ");
    const ticks = lg.ticks.map((v) => `<span style="left:${((v - lg.vmin) / (lg.vmax - lg.vmin) * 100).toFixed(1)}%">${num(v)}</span>`).join("");
    $("mjoLegend").innerHTML = `<div class="legend-title"><span>${lg.label}</span><span>${lg.unit}</span></div>
      <div class="legend-bar" style="background:linear-gradient(to right, ${grad})"></div><div class="legend-ticks">${ticks}</div>`;
  }

  function mjoHov() {
    const st = M.st, h = st.hov, cv = $("mjoHov");
    if (!h || !h.v.length) return;
    const w = cv.clientWidth || 340, rowH = 4, top = 18, left = 46, H = top + h.v.length * rowH + 4;
    const dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = H * dpr; cv.style.height = H + "px";
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const lg = (st.figs && st.figs.wc) || st.legends.wc, n = h.v[0].length, cw = (w - left - 4) / n;
    h.v.forEach((row, j) => row.forEach((v, i) => { c.fillStyle = scaleColor(lg, v); c.fillRect(left + i * cw, top + j * rowH, cw + 0.6, rowH + 0.6); }));
    const fcRow = h.days.indexOf(h.first_fc);
    c.font = "10px Readex Pro, sans-serif"; c.fillStyle = getComputedStyle(document.body).color; c.textAlign = "center";
    for (let lon = 0; lon < 360; lon += 60) {
      const x = left + (lon / h.dlon) * cw;
      c.fillText(lon === 0 ? "٠" : lon <= 180 ? `${num(lon)}ش` : `${num(360 - lon)}غ`, x, 11);
      c.strokeStyle = "rgba(255,255,255,.25)"; c.beginPath(); c.moveTo(x, top); c.lineTo(x, H - 4); c.stroke();
    }
    c.textAlign = "right";
    h.days.forEach((d, j) => { if (j % 10 === 0 || j === fcRow) c.fillText(`${num(+d.slice(8))}/${num(+d.slice(5, 7))}`, left - 4, top + j * rowH + 8); });
    if (fcRow >= 0) {
      c.setLineDash([5, 4]); c.strokeStyle = "#ffffff"; c.lineWidth = 1.2;
      c.beginPath(); c.moveTo(left, top + fcRow * rowH); c.lineTo(w - 4, top + fcRow * rowH); c.stroke(); c.setLineDash([]);
    }
  }

  // Rossby waves at 500 hPa: daily figure, and the troughs near the Kingdom
  function legendHTML(lg) {
    const grad = lg.stops.map((x) => `${x.c} ${(x.p * 100).toFixed(1)}%`).join(", ");
    const ticks = lg.ticks.map((v) => `<span style="left:${((v - lg.vmin) / (lg.vmax - lg.vmin) * 100).toFixed(1)}%">${v < 0 ? "−" + num(-v) : num(v)}</span>`).join("");
    return `<div class="legend-title"><span>${lg.label}</span><span>${lg.unit}</span></div>
      <div class="legend-bar" style="background:linear-gradient(to right, ${grad})"></div><div class="legend-ticks">${ticks}</div>`;
  }
  // atmospheric rivers from the Indian Ocean to Arabia: one figure a day for 12 days, and the tracks in words
  function riverCard() {
    const r = M.st && M.st.ar;
    if (!r || !(r.frames || []).length) { $("arCard").hidden = true; return; }
    $("arCard").hidden = false;
    const show = (k) => {
      const pad = r.frames.length > 20 ? 3 : 2;   // a frame every 3 hours (older runs: one a day)
      const url = `${CL}fig/ar_${String(k).padStart(pad, "0")}.png?v=${encodeURIComponent(M.st.updated)}`;
      $("arFig").src = url; $("arLink").href = url;
      const t = new Date(r.frames[k].replace("Z", ":00Z"));
      const h = Math.round((t - new Date(r.frames[0].replace("Z", ":00Z"))) / 3600e3);
      $("arDayLabel").textContent = (k === 0 ? "الآن: " : `+${num(h)} س · `) + fmtWhen.format(t);
    };
    $("arDay").max = r.frames.length - 1;
    $("arDay").oninput = (e) => show(+e.target.value);
    show(Math.min(+$("arDay").value || 0, r.frames.length - 1));
    $("arList").innerHTML = (r.lines || []).map((l) => `<p>${l.replace(/كغ\/م\/ث/g, '<span class="nw">كغ/م/ث</span>')}</p>`).join("");
  }

  function waveCard() {
    const st = M.st, rows = st.waves || [];
    if (!rows.length) { $("waveList").innerHTML = `<p class="muted">غير متاح اليوم.</p>`; return; }
    const show = (k) => {
      const url = `${CL}fig/wave_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
      $("waveFig").src = url; $("waveLink").href = url;
      const d = rows[k] && rows[k].d;
      $("waveDayLabel").textContent = d ? (k === 0 ? `اليوم: ${fmtDayD.format(dOf(d))}` : `+${num(k)} · ${fmtDayD.format(dOf(d))}`) : "";
    };
    $("waveDay").max = rows.length - 1;
    $("waveDay").oninput = (e) => show(+e.target.value);
    show(+$("waveDay").value || 0);
    if (st.figs && st.figs.wave) $("waveLegend").innerHTML = legendHTML(st.figs.wave);
    const items = rows.slice(0, 8).filter((r) => r.trough).map((r) =>
      `<div class="wave-row"><span>${fmtDayD.format(dOf(r.d))}</span><span>أخدود فوق ${r.trough.area} بعمق <b>${num(Math.abs(r.trough.v))}</b> م</span></div>`);
    $("waveList").innerHTML = items.length ? `<h4 class="sub">الأخاديد القريبة من المملكة</h4>` + items.join("")
      : `<p class="muted">لا أخاديد واضحة قرب المملكة في الأيام السبعة القادمة.</p>`;
  }

  // where air meets at 925 hPa, one map a day at 3 pm Makkah time
  function convCard() {
    const st = M.st, rows = st.conv || [];
    if (!rows.length) { $("convDayLabel").textContent = "غير متاح اليوم"; return; }
    const show = (k) => {
      const url = `${CL}fig/conv_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
      $("convFig").src = url; $("convLink").href = url;
      const r = rows[k];
      $("convDayLabel").textContent = r ? (r.t ? fmtWhen.format(new Date(r.t.replace("Z", ":00Z"))) : fmtDayD.format(dOf(r.d))) : "";
    };
    $("convDay").max = rows.length - 1;
    $("convDay").oninput = (e) => show(+e.target.value);
    show(+$("convDay").value || 0);
    if (st.figs && st.figs.conv) $("convLegend").innerHTML = legendHTML(st.figs.conv);
  }

  // Arctic Oscillation: observed bars and the ensemble forecast
  function aoChart() {
    const ao = M.st && M.st.ao;
    if (!ao || !ao.obs.length) { $("aoChart").innerHTML = `<p class="muted">غير متاح اليوم.</p>`; $("aoNow").innerHTML = ""; return; }
    const obs = ao.obs, fc = ao.fc.filter((f) => f.d > obs[obs.length - 1].d);
    const days = [...obs.map((o) => o.d), ...fc.map((f) => f.d)];
    const W = 360, H = 190, L = 26, R = 6, T = 10, B = 24, n = days.length;
    const X = (i) => L + (W - L - R) * i / Math.max(1, n - 1), Y = (v) => T + (H - T - B) * (1 - (Math.max(-4, Math.min(4, v)) + 4) / 8);
    const css = getComputedStyle(document.body), sea = css.getPropertyValue("--sea").trim() || "#45c3e6", amber = css.getPropertyValue("--amber").trim() || "#f2b552";
    let g = `<svg viewBox="0 0 ${W} ${H}" direction="ltr" font-family="Readex Pro, sans-serif" font-size="9">`;
    for (const v of [-3, -2, -1, 0, 1, 2, 3]) {
      g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="currentColor" stroke-opacity="${v === 0 ? 0.45 : 0.1}"/>`;
      g += `<text x="${L - 4}" y="${Y(v) + 3}" text-anchor="end" fill="currentColor" fill-opacity=".6">${v < 0 ? "−" + num(-v) : num(v)}</text>`;
    }
    const bw = Math.max(1, (W - L - R) / n - 0.6);
    obs.forEach((o, i) => {
      const y0 = Y(0), y = Y(o.v);
      g += `<rect x="${X(i) - bw / 2}" y="${Math.min(y0, y)}" width="${bw}" height="${Math.abs(y - y0)}" fill="${o.v >= 0 ? amber : sea}" fill-opacity=".85"/>`;
    });
    if (fc.length) {
      const k0 = obs.length;
      const band = fc.map((f, j) => `${X(k0 + j)},${Y(f.p90)}`).join(" ") + " " + fc.slice().reverse().map((f, j) => `${X(k0 + fc.length - 1 - j)},${Y(f.p10)}`).join(" ");
      g += `<polygon points="${band}" fill="currentColor" fill-opacity=".13"/>`;
      const line = [obs[obs.length - 1].v, ...fc.map((f) => f.mean)].map((v, j) => `${X(k0 - 1 + j)},${Y(v)}`).join(" ");
      g += `<polyline points="${line}" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="5 4"/>`;
      g += `<line x1="${X(k0 - 0.5)}" x2="${X(k0 - 0.5)}" y1="${T}" y2="${H - B}" stroke="currentColor" stroke-opacity=".35" stroke-dasharray="2 3"/>`;
      g += `<text x="${X(k0 - 0.5) + 4}" y="${T + 9}" fill="currentColor" fill-opacity=".7">توقع</text>`;
    }
    days.forEach((d, i) => {
      if (+d.slice(8) === 1 || +d.slice(8) === 15) g += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle" fill="currentColor" fill-opacity=".65">${num(+d.slice(8))}/${num(+d.slice(5, 7))}</text>`;
    });
    $("aoChart").innerHTML = g + "</svg>";
    const now = obs[obs.length - 1], f10 = fc[Math.min(9, fc.length - 1)];
    const word = (v) => (v <= -2 ? "سالب قوي" : v <= -1 ? "سالب" : v < -0.5 ? "سالب ضعيف" : v < 0.5 ? "قريب من الحياد" : v < 1 ? "موجب ضعيف" : v < 2 ? "موجب" : "موجب قوي");
    const sgn = (v) => (v < 0 ? "−" : "") + num(Math.abs(v), 1);
    $("aoNow").innerHTML = `<span>آخر رصد (${fmtDM.format(dOf(now.d))}/${num(+now.d.slice(5, 7))}): <b>${sgn(now.v)}</b> ${word(now.v)}</span>` +
      (f10 ? `<span>بعد عشرة أيام تقريبًا: <b>${sgn(f10.mean)}</b> ${word(f10.mean)}</span>` : "");
  }

  function mjoPwTable() {
    const st = M.st, rows = (st.pw || []).slice(1, 11);
    if (!rows.length) return;
    const names = { west: "الحجاز والغرب", southwest: "الجنوب الغربي", central: "الوسط", east: "الشرق", north: "الشمال" };
    const lg = (st.figs && st.figs.pw) || st.legends.pw;
    let t = `<table class="pwt"><tr><th></th>${rows.map((r) => `<th>${fmtDM.format(dOf(r.d))}</th>`).join("")}</tr>`;
    for (const k of Object.keys(names)) {
      t += `<tr><td>${names[k]}</td>` + rows.map((r) => {
        const v = r[k].pct, bg = v >= 110 ? scaleColor(lg, v) : "transparent", fg = v >= 175 ? "#fff" : "inherit";
        return `<td style="background:${bg};color:${fg}">${num(v)}</td>`;
      }).join("") + "</tr>";
    }
    $("mjoPw").innerHTML = t + "</table>";
  }

  // ------------------------------------------------------------------ tabs
  document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    for (const p of ["map", "mjo", "status"]) $("p-" + p).hidden = p !== b.dataset.tab;
    $("p-cities").hidden = true;
    if (b.dataset.tab === "mjo") mjoOpen();
    if (b.dataset.tab === "map") setTimeout(() => map.invalidateSize(), 50);
    if (b.dataset.tab === "cities") drawCities();
    if (b.dataset.tab === "status") refreshStatus();
  });

  document.querySelectorAll("[data-log]").forEach((a) => { a.href = `${DATA}logs/${a.dataset.log}.txt`; });

  (async function start() {
    map.getContainer().classList.toggle("hide-labels", map.getZoom() < 7);
    if (S.prod === "lightning") {  // show lightning straight away; the model data loads behind it
      $("prodSelect").innerHTML = `<option value="lightning">رادار البرق المباشر</option>`; $("prodSelect").value = "lightning";
      liEnter();
    } else {
      setTimeout(liLoad, 2000);  // fetch quietly so switching to lightning is instant
    }
    await Promise.all([refreshRuns(true), refreshStatus()]);
    setInterval(refreshStatus, 60e3);
    setInterval(() => refreshRuns(false), 5 * 60e3);
  })();
})();
