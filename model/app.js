/* Viewer for Fahad's private WRF runs over Saudi Arabia.
   Data layout (written by server/post/postprocess.py):
     data/runs.json                       list of runs, newest first
     data/runs/<run>/manifest.json        domains, frames, bounds, legends
     data/runs/<run>/meteo.json           city time series
     data/runs/<run>/<dom>/<prod>/<hhh>.png   (daily products: <YYYYMMDD>.png)
     data/status.json                     install / cycle progress                          */
(function () {
  "use strict";

  const DATA0 = window.SWRF_DATA || "data/";
  // the Kingdom-wide 9 km run is made on its own server in parallel and kept on its own branch
  const DATA_SA = window.SWRF_DATA_SA || DATA0.replace("/model-data/", "/model-data-sa/");
  // the 1 km nest over Jeddah, Makkah and Taif runs on a third server and is kept on its own branch
  const DATA_1K = window.SWRF_DATA_1K || DATA0.replace("/model-data/", "/model-data-1km/");
  // two drivers of the same 3 km model (15 Nov 2026): GFS (model-data, model-data-<id>) and ECMWF open data
  // (model-data-ec, model-data-ec-<id>); the two tabs under the product list switch every map between them
  const MODELS = { gfs: "", ec: "ec-" };   // (the morning GFS 00Z run was removed 19 Nov 2026, Fahad)
  let MODEL = MODELS[localStorage_get("model")] !== undefined ? localStorage_get("model") : "gfs";
  let DATA, REGIONS;
  function useModel(m) {
    MODEL = m;
    DATA = m === "gfs" ? DATA0 : DATA0.replace("/model-data/", `/model-data-${MODELS[m].slice(0, -1)}/`);
    // the five regional 3 km grids that, with the western highlands, cover the Kingdom; each on its own branch
    REGIONS = ["nw", "n", "c", "e", "se"].map((id) => [id, DATA0.replace("/model-data/", `/model-data-${MODELS[m]}${id}/`)]);
  }
  function localStorage_get(k) { try { return localStorage.getItem("swrf." + k); } catch (e) { return null; } }
  useModel(MODEL);
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
  const LIVE = (p) => p === "lightning" || p === "radar";   // live observations: the rain radar and lightning, separate entries (Fahad 18 Nov 2026)
  const HOURLY = ["refl", "rain1h"];   // 700 hPa humidity and instability layers removed from the menu 17 Nov 2026 (Fahad); the runs still write them
  // products drawn with wind arrows on top: folder of the arrow files and the speed of a full-length arrow
  const VEC = { ivt: { dir: "ivt_vec", ref: 700 } };   // (the 925 hPa convergence map was removed on 14 Nov 2026: the report names the meeting zones)
  const DAILY = [];   // the daily max reflectivity map was removed from the list (Fahad, 16 Nov 2026)
  // current names, also for runs made before an option was renamed
  const LABELS = { refl_day: "أقصى انعكاسية لكل يوم", rain24: "المطر التراكمي من ١٢ إلى ١٢", ivt: "تدفق الأنهار الجوية" };
  // the morning run's 24-hour map holds its hours 9-18: noon to 9 PM Makkah
  const lab = (k) => LABELS[k];
  const SINGLE = ["rain24", "tsprob"];   // one map for the whole run
  // chance of a severe storm, the next 8 Makkah days (Fahad, 22 Nov 2026): GFS 0.25 ingredients joined by a fit tested
  // against satellite rain (saudi-wrf server/climate/svrprob.py), made by the nightly climate run on climate-data
  // (svr.json + fig/svr_KK.png, pictures already in Web Mercator rows over EXTENT); the same for both model tabs
  const SVR = { j: null, p: null, at: 0 };
  const SVR_LABEL = "احتمال العاصفة الشديدة";
  function svrLoad() {
    if (SVR.j && Date.now() - SVR.at < 30 * 60e3) return Promise.resolve(SVR.j);
    if (SVR.failed && Date.now() - SVR.failed < 5 * 60e3) return Promise.resolve(SVR.j);
    if (!SVR.p) SVR.p = getJSON(CL + "svr.json").then((j) => {
      j.days.forEach((x) => { const b = atob(x.vals || ""); x.v = Uint8Array.from(b, (ch) => ch.charCodeAt(0)); });
      SVR.j = j; SVR.at = Date.now(); SVR.failed = 0; return j;
    }).catch(() => { SVR.failed = Date.now(); return SVR.j; }).finally(() => { SVR.p = null; });
    return SVR.p;
  }
  function svrAt(lat, lon) {   // the chance (%) at a point on the shown day, from the 0.25 degree values
    const f = S.frames[S.idx], j = SVR.j;
    if (!j || !f || f.svr == null) return null;
    const g = j.grid, x = j.days[f.svr];
    const r = Math.round((g.lat0 - lat) / g.d), c = Math.round((lon - g.lon0) / g.d);
    if (!x || !x.v || r < 0 || c < 0 || r >= g.ny || c >= g.nx) return null;
    return x.v[r * g.nx + c];
  }
  const NO_H0 = new Set(["rain1h", "wind", "wup"]);

  const $ = (id) => document.getElementById(id);
  const store = {
    get(k) { try { return localStorage.getItem("swrf." + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("swrf." + k, v); } catch (e) { /* private mode */ } },
  };

  const S = { runs: [], run: null, man: null, meteo: null, dom: "k3",  // always the whole Kingdom; the regions list was removed (Fahad, 16 Nov 2026)
    prod: store.get("prod") || "refl",
              frames: [], idx: 0, playing: null, overlay: null, rects: [], cityLayer: null };

  async function getJSON(url) {
    const r = await fetch(url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  // ------------------------------------------------------------------ map
  const map = L.map("map", { zoomControl: false, attributionControl: true, minZoom: 4, maxZoom: 16, zoomSnap: 0.25 }).setView([23.5, 44], 5);
  // basemaps: toned-down satellite relief by default, place names drawn above the model colours
  map.createPane("labels"); map.getPane("labels").style.zIndex = 650; map.getPane("labels").style.pointerEvents = "none";
  // Esri's grey canvas tiles need no key (CARTO started requiring one and stamps its tiles otherwise)
  const esri = (svc) => `https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`;
  const esriAttr = "© Esri, HERE, Garmin, © OpenStreetMap";
  const dark = L.tileLayer(esri("Canvas/World_Dark_Gray_Base"), { maxZoom: 19, maxNativeZoom: 16, attribution: esriAttr });
  // light: Esri World Topographic (soft relief, Fahad's pick on 15 Nov 2026)
  const light = L.tileLayer(esri("World_Topo_Map"), { maxZoom: 19, maxNativeZoom: 17, attribution: "© Esri, HERE, Garmin, USGS, © OpenStreetMap" });
  // modern relief (Fahad, 15 Nov 2026, replacing OpenTopoMap): Esri satellite imagery toned down to a dark
  // navy sea and muted brown land (CSS filter on .sat-dark), thin dark country borders and Arabic names
  const sat = L.tileLayer(esri("World_Imagery"), { maxZoom: 19, maxNativeZoom: 17, className: "sat-dark", attribution: "صور: Esri, Maxar, Earthstar Geographics" });
  // detailed: CyclOSM (OpenStreetMap with hill shading) carries the local (Arabic) names of villages, wadis,
  // mountains and landmarks when zoomed in (Fahad's pick on 15 Nov 2026, replacing the standard OSM style)
  const osm = L.tileLayer("https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png", { subdomains: "abc", maxZoom: 18, maxNativeZoom: 18, attribution: "© OpenStreetMap · CyclOSM" });
  const shade = L.tileLayer(esri("Elevation/World_Hillshade_Dark"), { maxZoom: 16, maxNativeZoom: 13, opacity: 0.45, attribution: "Esri" });
  // Arabic names above the model colours: countries and seas from zoom 4, the main cities from zoom 6
  const NAMES = [
    ["c", "السعودية", 24.3, 44.6], ["c", "العراق", 32.8, 43.6], ["c", "الأردن", 30.9, 36.9], ["c", "سوريا", 35.0, 38.6],
    ["c", "الكويت", 29.35, 47.6], ["c", "الإمارات", 23.6, 54.3], ["c small", "قطر", 25.3, 51.2], ["c small", "البحرين", 26.05, 50.55],
    ["c", "عُمان", 21.0, 57.0], ["c", "اليمن", 15.6, 47.5], ["c", "مصر", 26.5, 30.0], ["c", "السودان", 16.0, 30.5],
    ["c", "إريتريا", 15.4, 38.6], ["c", "إثيوبيا", 9.0, 39.5], ["c", "الصومال", 8.0, 47.5], ["c small", "جيبوتي", 11.7, 42.6],
    ["c", "إيران", 32.5, 54.0], ["c", "تركيا", 39.0, 35.0], ["c small", "لبنان", 33.9, 35.85], ["c small", "فلسطين", 31.4, 35.05],
    ["c", "ليبيا", 27.0, 18.0], ["c", "باكستان", 28.5, 66.5], ["c", "أفغانستان", 33.5, 65.5],
    ["s", "البحر الأحمر", 20.2, 38.6], ["s", "الخليج العربي", 27.5, 50.6], ["s", "بحر العرب", 15.0, 62.0],
    ["s", "خليج عدن", 12.4, 47.8], ["s", "البحر المتوسط", 33.8, 26.0], ["s", "خليج عُمان", 24.6, 58.6],
    ["p", "الرياض", 24.71, 46.68], ["p", "جدة", 21.54, 39.17], ["p b", "مكة المكرمة", 21.42, 39.83], ["p", "المدينة المنورة", 24.47, 39.61],
    ["p r", "الطائف", 21.27, 40.42], ["p", "أبها", 18.22, 42.51], ["p", "جازان", 16.89, 42.55], ["p", "نجران", 17.49, 44.13],
    ["p", "الباحة", 20.01, 41.47], ["p", "تبوك", 28.38, 36.57], ["p", "حائل", 27.52, 41.69], ["p", "بريدة", 26.33, 43.97],
    ["p", "الدمام", 26.42, 50.09], ["p", "سكاكا", 29.97, 40.21], ["p", "عرعر", 30.98, 41.04], ["p", "ينبع", 24.09, 38.06],
    ["p", "الأحساء", 25.38, 49.59], ["p", "وادي الدواسر", 20.47, 44.78], ["p", "شرورة", 17.47, 47.11], ["p", "العلا", 26.61, 37.92],
    // governorates (Fahad, 16 Nov 2026): the larger ones from zoom 6.5, the rest from 7.5; places from the OSM gazetteer
    ["p g g2", "الدرعية", 24.75, 46.57], ["p g", "الخرج", 24.15, 47.31], ["p g", "الدوادمي", 24.49, 44.38], ["p g", "المجمعة", 25.9, 45.35],
    ["p g", "القويعية", 24.07, 45.28], ["p g g2", "الزلفي", 26.3, 44.82], ["p g", "شقراء", 25.25, 45.25], ["p g", "حوطة بني تميم", 23.49, 46.88],
    ["p g", "عفيف", 23.9, 42.92], ["p g g2", "السليل", 20.46, 45.57], ["p g g2", "ضرما", 24.6, 46.13], ["p g g2", "المزاحمية", 24.47, 46.27],
    ["p g g2", "رماح", 25.57, 47.16], ["p g g2", "ثادق", 25.28, 45.86], ["p g g2", "حريملاء", 25.13, 46.12], ["p g g2", "الحريق", 23.63, 46.51],
    ["p g g2", "الغاط", 26.03, 44.95], ["p g g2", "مرات", 25.07, 45.46], ["p g g2", "الدلم", 24.0, 47.16], ["p g g2", "الرين", 23.54, 45.51],
    ["p g", "القنفذة", 19.13, 41.08], ["p g", "الليث", 20.15, 40.27], ["p g", "رابغ", 22.8, 39.03], ["p g g2", "خليص", 22.16, 39.32],
    ["p g g2", "الخرمة", 21.91, 42.03], ["p g g2", "رنية", 21.26, 42.85], ["p g g2", "تربة", 21.22, 41.63], ["p g g2", "الجموم", 21.62, 39.7],
    ["p g g2", "الكامل", 22.26, 39.8], ["p g g2", "المويه", 22.44, 41.76], ["p g g2", "ميسان", 20.74, 40.84], ["p g g2", "أضم", 20.45, 40.88],
    ["p g g2", "بحرة", 21.4, 39.45], ["p g g2", "الحناكية", 24.88, 40.52], ["p g g2", "بدر", 23.78, 38.79], ["p g g2", "خيبر", 25.7, 39.29],
    ["p g g2", "العيص", 25.06, 38.11], ["p g", "عنيزة", 26.09, 43.99], ["p g", "الرس", 25.87, 43.5], ["p g", "المذنب", 25.86, 44.22],
    ["p g g2", "البكيرية", 26.15, 43.67], ["p g g2", "البدائع", 25.99, 43.73], ["p g g2", "الأسياح", 26.8, 44.2],
    ["p g g2", "النبهانية", 25.86, 43.07], ["p g g2", "الشماسية", 26.32, 44.26], ["p g g2", "عيون الجواء", 26.49, 43.64],
    ["p g g2", "رياض الخبراء", 26.05, 43.56], ["p g g2", "عقلة الصقور", 25.83, 42.2], ["p g", "حفر الباطن", 28.43, 45.96],
    ["p g", "الجبيل", 27.0, 49.65], ["p g g2", "القطيف", 26.56, 50.01], ["p g", "الخبر", 26.3, 50.2], ["p g", "الخفجي", 28.42, 48.49],
    ["p g g2", "رأس تنورة", 26.71, 50.07], ["p g g2", "بقيق", 25.94, 49.67], ["p g g2", "النعيرية", 27.47, 48.48],
    ["p g g2", "قرية العليا", 27.56, 47.7], ["p g", "خميس مشيط", 18.3, 42.73], ["p g", "بيشة", 20.0, 42.6], ["p g", "النماص", 19.12, 42.13],
    ["p g g2", "سراة عبيدة", 18.09, 43.13], ["p g g2", "تثليث", 19.53, 43.5], ["p g g2", "رجال ألمع", 18.21, 42.27],
    ["p g g2", "أحد رفيدة", 18.18, 42.84], ["p g g2", "ظهران الجنوب", 17.66, 43.52], ["p g g2", "المجاردة", 19.13, 41.92],
    ["p g g2", "تنومة", 18.95, 42.17], ["p g g2", "البرك", 18.22, 41.54], ["p g g2", "بارق", 18.94, 41.95], ["p g g2", "الحرجة", 17.92, 43.37],
    ["p g", "الوجه", 26.24, 36.45], ["p g g2", "تيماء", 27.62, 38.54], ["p g g2", "أملج", 25.03, 37.26], ["p g g2", "حقل", 29.29, 34.95],
    ["p g g2", "البدع", 28.48, 35.01], ["p g g2", "بقعاء", 27.91, 42.39], ["p g g2", "الغزالة", 26.79, 41.32], ["p g g2", "الشنان", 27.18, 42.44],
    ["p g g2", "السليمي", 26.29, 41.36], ["p g g2", "الشملي", 26.86, 40.32], ["p g g2", "موقق", 27.39, 41.18], ["p g g2", "سميراء", 26.49, 42.12],
    ["p g", "رفحاء", 29.63, 43.52], ["p g", "طريف", 31.67, 38.66], ["p g g2", "العويقيلة", 30.36, 42.24], ["p g g2", "صبيا", 17.15, 42.62],
    ["p g", "أبو عريش", 16.97, 42.84], ["p g g2", "صامطة", 16.6, 42.94], ["p g", "بيش", 17.38, 42.54], ["p g g2", "الدرب", 17.73, 42.25],
    ["p g g2", "ضمد", 17.11, 42.78], ["p g g2", "الريث", 17.6, 42.86], ["p g g2", "فرسان", 16.7, 42.12], ["p g g2", "العارضة", 17.04, 43.08],
    ["p g g2", "أحد المسارحة", 16.71, 42.95], ["p g g2", "العيدابي", 17.24, 42.94], ["p g g2", "الطوال", 16.53, 42.97],
    ["p g g2", "حبونا", 17.85, 44.02], ["p g g2", "بدر الجنوب", 17.88, 43.72], ["p g g2", "يدمة", 18.53, 44.2], ["p g g2", "ثار", 17.97, 44.11],
    ["p g g2", "خباش", 17.55, 44.74], ["p g g2", "بلجرشي", 19.86, 41.56], ["p g g2", "المندق", 20.11, 41.28], ["p g g2", "المخواة", 19.78, 41.44],
    ["p g g2", "العقيق", 20.28, 41.66], ["p g g2", "الحجرة", 20.2, 41.07], ["p g g2", "بني حسن", 20.05, 41.37], ["p g", "القريات", 31.33, 37.34],
    ["p g", "دومة الجندل", 29.81, 39.87], ["p g", "طبرجل", 30.5, 38.22], ["p g", "الأفلاج", 22.29, 46.72], ["p g g2", "المهد", 23.5, 40.88],
    ["p g g2", "ضرية", 24.72, 42.93], ["p g", "محايل", 18.55, 42.05], ["p g", "ضباء", 27.35, 35.69], ["p g g2", "الدائر", 17.34, 43.13],
    ["p g g2", "فيفاء", 17.26, 43.11], ["p g g2", "قلوة", 19.94, 41.25], ["p g g2", "هروب", 17.44, 42.89],
  ];
  const names = L.layerGroup(NAMES.map(([k, t, la, lo]) => L.marker([la, lo], { pane: "labels", interactive: false, keyboard: false,
    icon: L.divIcon({ className: "map-name map-name-" + k.split(" ")[0] + " " + k.split(" ").slice(1).join(" "), html: `<span>${t}</span>`, iconSize: [0, 0] }) })));
  const bases = { "تضاريس (صور فضائية)": sat, "داكنة": dark, "فاتحة": light, "تفصيلية: القرى والمعالم (أسماء عربية)": osm };
  const DARK_BASES = new Set(["داكنة"]);
  const baseKey = bases[store.get("base3")] ? store.get("base3") : "تضاريس (صور فضائية)";
  bases[baseKey].addTo(map);
  if (store.get("shade") === "1") shade.addTo(map);
  if (store.get("labels") !== "0") names.addTo(map);
  // boundaries of the Kingdom's 13 regions (Natural Earth), above the model colours and below the lightning
  map.createPane("regions"); map.getPane("regions").style.zIndex = 630; map.getPane("regions").style.pointerEvents = "none";
  const regionStyle = (f) => {
    const darkMap = !document.body.classList.contains("light-map");
    const col = darkMap ? "rgba(235,238,242,0.62)" : "rgba(14,16,20,0.78)";
    return f && (f.properties.k === "border" || f.properties.k === "country") ? { color: col, weight: 1.2, opacity: 1, fill: false, interactive: false }
      : { color: col, weight: 0.8, opacity: 0.8, dashArray: "4 4", fill: false, interactive: false };
  };
  const regions = L.geoJSON(null, { pane: "regions", style: regionStyle, interactive: false });
  if (store.get("regions") !== "0") regions.addTo(map);
  fetch("sa_regions.json?v=1").then((r) => r.json()).then((g) => regions.addData(g)).catch(() => {});
  // the other countries' borders (Natural Earth 1:50m, the Saudi point of view)
  fetch("borders.json?v=1").then((r) => r.json()).then((g) => regions.addData(g)).catch(() => {});
  // the basemap / overlay choices live inside the map options panel (Fahad 18 Nov 2026), not on the map's left
  const layersCtl = L.control.layers(bases, { "الحدود": regions, "ظلال التضاريس": shade, "الأسماء": names }, { position: "topleft", collapsed: false }).addTo(map);
  $("mmBase").appendChild(layersCtl.getContainer());
  const setMapKind = (name) => {
    document.body.classList.toggle("light-map", !DARK_BASES.has(name));
    document.body.classList.toggle("sat-map", name === "تضاريس (صور فضائية)");
  };
  map.on("baselayerchange", (e) => { store.set("base3", e.name); setMapKind(e.name); regions.setStyle(regionStyle); });
  setMapKind(baseKey);
  const nameZoom = () => { const z = map.getZoom(), c = map.getContainer().classList; c.toggle("z-lt6", z < 6); c.toggle("z-lt65", z < 6.5); c.toggle("z-lt75", z < 7.5); c.toggle("z-ge8", z >= 8); };
  // a governorate name that would sit on another name is left out at that zoom: main cities first, then the larger governorates
  const nameRank = (k) => (k.includes("g2") ? 2 : k.includes(" g") ? 1 : 0);
  const nameOrder = names.getLayers().map((m, i) => [m, NAMES[i][0]]).filter(([, k]) => k.startsWith("p")).sort((a, b) => nameRank(a[1]) - nameRank(b[1]));
  function declutter() {
    const placed = [];
    for (const [m, k] of nameOrder) {
      const el = m.getElement(); if (!el) continue;
      el.classList.remove("hid");
      const sp = el.firstChild; if (!sp || !sp.offsetParent) continue;
      const r = sp.getBoundingClientRect();
      const hit = placed.some((q) => r.left < q.right + 3 && r.right > q.left - 3 && r.top < q.bottom + 1 && r.bottom > q.top - 1);
      if (hit && nameRank(k)) el.classList.add("hid"); else placed.push(r);
    }
  }
  // Towns, villages and hamlets (OpenStreetMap, Arabic names, about 10 000), drawn on one canvas under the main names and
  // revealed with zoom: towns from 7, villages from 8.25, hamlets from 9.5, districts from 10.5; a name that would touch
  // another is left out (Fahad 18 Nov 2026)
  const PLACE_ZOOM = [7, 8.25, 9.5, 10.5];
  const PlaceNames = L.Layer.extend({
    onAdd(m) {
      this._c = L.DomUtil.create("canvas", "leaflet-zoom-hide place-canvas");
      m.getPane("labels").appendChild(this._c);
      m.on("moveend zoomend resize", this.redraw, this);
      this.redraw();
    },
    onRemove(m) { m.off("moveend zoomend resize", this.redraw, this); L.DomUtil.remove(this._c); },
    getAttribution() { return "© OSM"; },
    redraw() {
      const m = this._map; if (!m) return;
      const z = m.getZoom(), size = m.getSize(), dpr = window.devicePixelRatio || 1, c = this._c;
      c.width = size.x * dpr; c.height = size.y * dpr; c.style.width = size.x + "px"; c.style.height = size.y + "px";
      L.DomUtil.setPosition(c, m.containerPointToLayerPoint([0, 0]));
      const cx = c.getContext("2d"); cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, size.x, size.y);
      if (z < PLACE_ZOOM[0] || (document.body.classList.contains("light-map") && !document.body.classList.contains("sat-map"))) return;
      if (!this._p) {
        if (!this._loading) this._loading = fetch("places.json?v=1").then((r) => r.json()).then((j) => { this._p = j.p; this.redraw(); }).catch(() => {});
        return;
      }
      // the main names already on the map keep their place
      const box = m.getContainer().getBoundingClientRect(), placed = [];
      m.getContainer().querySelectorAll(".map-name:not(.hid) span").forEach((sp) => {
        if (!sp.offsetParent) return;
        const r = sp.getBoundingClientRect();
        placed.push([r.left - box.left, r.top - box.top, r.right - box.left, r.bottom - box.top]);
      });
      const fam = getComputedStyle(document.body).fontFamily;
      const b = m.getBounds().pad(0.05);
      cx.textAlign = "right"; cx.textBaseline = "middle"; cx.direction = "rtl"; cx.lineJoin = "round";
      let shown = 0;
      for (const [n, la, lo, t] of this._p) {
        if (z < PLACE_ZOOM[t] || !b.contains([la, lo])) continue;
        const pt = m.latLngToContainerPoint([la, lo]), fs = t === 0 ? 11 : 10.5;
        cx.font = `400 ${fs}px ${fam}`;   // soft like the main names (Taif): regular weight, blurred halo, no outline
        const w = cx.measureText(n).width, r = [pt.x - w - 8, pt.y - fs * 0.7, pt.x + 3, pt.y + fs * 0.7];
        if (placed.some((q) => r[0] < q[2] + 3 && r[2] > q[0] - 3 && r[1] < q[3] + 1 && r[3] > q[1] - 1)) continue;
        placed.push(r);
        cx.shadowColor = "rgba(0,0,0,.85)"; cx.shadowBlur = 3;
        cx.fillStyle = "#fff"; cx.beginPath(); cx.arc(pt.x, pt.y, t === 0 ? 2 : 1.5, 0, 2 * Math.PI); cx.fill();
        cx.fillStyle = t === 0 ? "rgba(255,255,255,.92)" : t === 1 ? "rgba(255,255,255,.85)" : "rgba(236,240,245,.75)";
        cx.fillText(n, pt.x - 5, pt.y);
        cx.shadowBlur = 0;
        if (++shown > 600) break;
      }
    },
  });
  const places = new PlaceNames();
  names.addLayer(places);   // shown and hidden with the «الأسماء» choice
  map.on("baselayerchange", () => places.redraw());
  map.on("zoomend", nameZoom); nameZoom();
  map.on("zoomend overlayadd", () => requestAnimationFrame(() => { declutter(); places.redraw(); }));
  if (document.fonts) document.fonts.ready.then(() => requestAnimationFrame(declutter)); else setTimeout(declutter, 1000);
  map.on("overlayadd overlayremove", (e) => {
    const on = e.type === "overlayadd" ? "1" : "0";
    if (e.layer === shade) store.set("shade", on);
    if (e.layer === names) store.set("labels", on);
    if (e.layer === regions) store.set("regions", on);
  });
  // the folded colour key: a very small strip under the layers box; a tap opens the full key at the bottom
  const MiniLg = L.Control.extend({
    onAdd() {
      const d = L.DomUtil.create("div", "leaflet-control lg-mini-ctl");
      d.innerHTML = `<button type="button" id="lgMini" class="lg-mini" aria-label="مفتاح الألوان"></button>`;
      L.DomEvent.disableClickPropagation(d);
      return d;
    },
  });
  const miniCtl = new MiniLg({ position: "topleft" }).addTo(map);
  // the folded colour key sits at the bottom, just above the time bar (Fahad 18 Nov 2026)
  $("legend").parentNode.insertBefore(miniCtl.getContainer(), $("legend"));
  L.control.zoom({ position: "topleft" }).addTo(map);
  // "my location": a small button under the zoom buttons; a blue dot (with its accuracy ring) that follows the phone (Fahad 18 Nov 2026)
  map.createPane("me"); map.getPane("me").style.zIndex = 660; map.getPane("me").style.pointerEvents = "none";
  const ME = { dot: null, ring: null, watch: null, first: true };
  function meShow(pos) {
    const ll = [pos.coords.latitude, pos.coords.longitude], acc = Math.min(pos.coords.accuracy || 0, 5000);
    if (!ME.dot) {
      ME.ring = L.circle(ll, { radius: acc, pane: "me", color: "#4a86f5", weight: 1, opacity: 0.5, fillColor: "#4a86f5", fillOpacity: 0.12, interactive: false }).addTo(map);
      ME.dot = L.circleMarker(ll, { radius: 7, pane: "me", color: "#fff", weight: 2.5, fillColor: "#2f6ff0", fillOpacity: 1, interactive: false }).addTo(map);
    } else { ME.dot.setLatLng(ll); ME.ring.setLatLng(ll).setRadius(acc); }
    if (ME.first) { ME.first = false; map.flyTo(ll, Math.max(map.getZoom(), 9), { duration: 0.8 }); }
  }
  const Locate = L.Control.extend({
    onAdd() {
      const d = L.DomUtil.create("div", "leaflet-bar leaflet-control me-ctl");
      d.innerHTML = `<a href="#" role="button" id="meBtn" aria-label="موقعي" title="موقعي"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/><circle cx="12" cy="12" r="8"/></svg></a>`;
      L.DomEvent.disableClickPropagation(d);
      d.firstChild.addEventListener("click", (e) => {
        e.preventDefault();
        if (!navigator.geolocation) return;
        const btn = $("meBtn");
        if (ME.dot) { map.flyTo(ME.dot.getLatLng(), Math.max(map.getZoom(), 9), { duration: 0.8 }); return; }
        btn.classList.add("busy");
        ME.watch = navigator.geolocation.watchPosition((pos) => { btn.classList.remove("busy"); btn.classList.add("on"); meShow(pos); },
          () => { btn.classList.remove("busy"); if (ME.watch != null) { navigator.geolocation.clearWatch(ME.watch); ME.watch = null; } ME.first = true; },
          { enableHighAccuracy: true, maximumAge: 30000, timeout: 20000 });
      });
      return d;
    },
  });
  new Locate({ position: "topleft" }).addTo(map);
  map.attributionControl.setPrefix(false);
  map.on("zoomend", () => map.getContainer().classList.toggle("hide-labels", map.getZoom() < 7));

  function urlFor(dom, f) {
    const d = S.man.domains[dom];
    if (!d || !f) return null;
    if (d.products && !d.products.includes(S.prod)) return null;
    if (f.single) { if (!d[S.prod]) return null; }
    else if (f.date) { if (!(d.days || []).some((x) => x.date === f.date)) return null; }
    else if (!(d.hours || []).includes(f.h)) return null;
    const name = f.single ? "main" : f.date ? f.date : String(f.h).padStart(3, "0");
    return `${base(d)}runs/${S.run}/${dom}/${S.prod}/${name}.png`;
  }
  function frameURL(i) {
    const f = S.frames[i], d = S.man && S.man.domains[S.dom];
    if (!f || !d) return null;
    if (d.members) return null;
    const name = f.single ? "main" : DAILY.includes(S.prod) ? f.date : String(f.h).padStart(3, "0");
    return `${base(d)}runs/${S.run}/${S.dom}/${S.prod}/${name}.png`;
  }

  const cache = new Map();
  function preload(i) {
    if (S.prod === "svr") { const x = SVR.j && S.frames[i] && SVR.j.days[S.frames[i].svr]; if (x) loadImg(svrURL(x)); return; }
    const d = S.man && S.man.domains[S.dom];
    const us = d && d.members ? d.members.map((m) => urlFor(m, S.frames[i])) : [frameURL(i)];
    for (const u of us) if (u) loadImg(u);
    if (cache.size > 240) cache.delete(cache.keys().next().value);
    if (d && d.members) mosaicURL(d.members.map((m) => ({ id: m, url: urlFor(m, S.frames[i]) }))).catch(() => null);
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
  function clearOverlay() { fade.layers.forEach((l) => map.removeLayer(l)); fade.layers = []; fade.front = 0; clearMulti(); }
  // the combined 3 km view: one image per regional grid, each swapped when its new image has loaded
  const multi = new Map();
  function clearMulti() { multi.forEach((l) => map.removeLayer(l)); multi.clear(); }
  function overlayMany(items) {
    fade.layers.forEach((l) => map.removeLayer(l)); fade.layers = []; fade.front = 0;
    const keep = new Set(items.map((x) => x.id));
    multi.forEach((l, id) => { if (!keep.has(id)) { map.removeLayer(l); multi.delete(id); } });
    items.forEach(({ id, url, bounds }, k) => {
      let lay = multi.get(id);
      if (!url) { if (lay) lay.setOpacity(0); return; }
      if (!lay) {
        lay = L.imageOverlay(url, L.latLngBounds(bounds), { interactive: false, zIndex: 300 + k, opacity: 1, className: "wx-layer" }).addTo(map);
        multi.set(id, lay); return;
      }
      const img = new Image();
      img.onload = img.onerror = () => { lay.setUrl(url); lay.setBounds(L.latLngBounds(bounds)); lay.setOpacity(1); };
      img.src = url;
    });
  }

  // The Kingdom at 3 km as one seamless picture (16 Nov 2026, after Fahad found the humidity and instability maps
  // boxy): every grid's map is blended into one canvas, each pixel weighted by how far it lies inside its own grid
  // (the grid's boundary zone is left out, then the weight rises over ~40 km). Where grids overlap their colours are
  // averaged, so no seam; where only one grid reaches, its edge fades out instead of ending in a hard box.
  const MOS = { geo: null, urls: new Map(), token: 0 };
  const MOS_SKIP = 5, MOS_RAMP = 14, MOS_STEP = 0.018;   // grid cells left out and of the fade; mosaic pixel (deg)
  const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
  const invMercY = (y) => (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180 / Math.PI;
  function mosaicGeo(ids) {
    const key = S.run + MODEL + ids.join();
    if (MOS.geo && MOS.geo.key === key) return MOS.geo;
    const ds = ids.map((id) => S.man.domains[id]);
    if (ds.some((d) => !d || !d.bounds || !d.points || d.points.x00 == null || !(d.proj || S.man.proj))) return null;
    const s = Math.min(...ds.map((d) => d.bounds[0][0])), w = Math.min(...ds.map((d) => d.bounds[0][1]));
    const n = Math.max(...ds.map((d) => d.bounds[1][0])), e = Math.max(...ds.map((d) => d.bounds[1][1]));
    const ys = mercY(s), yn = mercY(n);
    const W = Math.ceil((e - w) / MOS_STEP), H = Math.ceil((yn - ys) / (MOS_STEP * Math.PI / 180));
    const px = (lon) => (lon - w) / (e - w) * W, py = (lat) => (yn - mercY(lat)) / (yn - ys) * H;
    const doms = ds.map((d, k) => {
      const P = d.points, pr = d.proj || S.man.proj;
      const fx0 = px(d.bounds[0][1]), fx1 = px(d.bounds[1][1]), fy0 = py(d.bounds[1][0]), fy1 = py(d.bounds[0][0]);
      const x0 = Math.max(0, Math.floor(fx0)), x1 = Math.min(W, Math.ceil(fx1)), y0 = Math.max(0, Math.floor(fy0)), y1 = Math.min(H, Math.ceil(fy1));
      const rw = x1 - x0, rh = y1 - y0, wt = new Float32Array(rw * rh);
      for (let y = 0; y < rh; y++) {
        const lat = invMercY(yn - (y0 + y + 0.5) / H * (yn - ys));
        for (let x = 0; x < rw; x++) {
          const lon = w + (x0 + x + 0.5) / W * (e - w);
          const [X, Y] = lccForward(pr, lon, lat);
          const i = (X - P.x00) / P.dx, j = (Y - P.y00) / P.dx;
          const edge = Math.min(i, P.nx - 1 - i, j, P.ny - 1 - j);
          // blend weight: tiny at the grid's edge, full ~40 km inside; zero outside the grid
          wt[y * rw + x] = edge < 1 ? 0 : 0.03 + 0.97 * Math.max(0, Math.min(1, (edge - MOS_SKIP) / MOS_RAMP));
        }
      }
      return { id: ids[k], fx0, fy0, fw: fx1 - fx0, fh: fy1 - fy0, x0, y0, rw, rh, wt };
    });
    // fade only at the outer edge of all the grids together (not where two grids meet): distance to the nearest
    // uncovered pixel (two-pass chamfer), in grid cells of 3 km
    // narrow gaps where two grids do not quite meet are closed (dilate then erode by ~16 km) and later filled from
    // their neighbours, so they neither show as a line nor start a fade
    const cov = new Uint8Array(W * H);
    doms.forEach((g) => { for (let y = 0; y < g.rh; y++) for (let x = 0; x < g.rw; x++) if (g.wt[y * g.rw + x] > 0) cov[(g.y0 + y) * W + g.x0 + x] = 1; });
    const morph = (src, r, grow) => {   // square max (grow) or min filter, separable
      const a = new Uint8Array(W * H), b = new Uint8Array(W * H);
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        let v = grow ? 0 : 1;
        for (let k = Math.max(0, x - r); k <= Math.min(W - 1, x + r); k++) { const q = src[y * W + k]; if (grow ? q : !q) { v = grow ? 1 : 0; break; } }
        a[y * W + x] = v;
      }
      for (let x = 0; x < W; x++) for (let y = 0; y < H; y++) {
        let v = grow ? 0 : 1;
        for (let k = Math.max(0, y - r); k <= Math.min(H - 1, y + r); k++) { const q = a[k * W + x]; if (grow ? q : !q) { v = grow ? 1 : 0; break; } }
        b[y * W + x] = v;
      }
      return b;
    };
    const R8 = 8, closed = morph(morph(cov, R8, true), R8, false);
    const gaps = [];
    for (let p = 0; p < W * H; p++) { if (cov[p]) closed[p] = 1; else if (closed[p]) gaps.push(p); }
    const dist = new Float32Array(W * H);
    for (let p = 0; p < W * H; p++) if (closed[p]) dist[p] = 1e9;
    const D1 = 1, D2 = Math.SQRT2;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const p = y * W + x; if (!dist[p]) continue;
      let v = dist[p];
      v = Math.min(v, x > 0 ? dist[p - 1] + D1 : 0, y > 0 ? dist[p - W] + D1 : 0, x > 0 && y > 0 ? dist[p - W - 1] + D2 : 0, x < W - 1 && y > 0 ? dist[p - W + 1] + D2 : 0);
      dist[p] = v;
    }
    for (let y = H - 1; y >= 0; y--) for (let x = W - 1; x >= 0; x--) {
      const p = y * W + x; if (!dist[p]) continue;
      let v = dist[p];
      v = Math.min(v, x < W - 1 ? dist[p + 1] + D1 : 0, y < H - 1 ? dist[p + W] + D1 : 0, x < W - 1 && y < H - 1 ? dist[p + W + 1] + D2 : 0, x > 0 && y < H - 1 ? dist[p + W - 1] + D2 : 0);
      dist[p] = v;
    }
    const cell = MOS_STEP * 111.32 * Math.cos(((s + n) / 2) * Math.PI / 180) / 3;   // mosaic pixel in 3 km cells
    const fade = new Float32Array(W * H);
    for (let p = 0; p < W * H; p++) fade[p] = Math.max(0, Math.min(1, (dist[p] * cell - MOS_SKIP) / MOS_RAMP));
    MOS.geo = { key, W, H, bounds: [[s, w], [n, e]], doms, fade, gaps: Int32Array.from(gaps) };
    return MOS.geo;
  }
  // Smooth palettes of the 700 hPa humidity and instability maps (the same stops as server/post/products.py since
  // the 16 Nov 12Z run). Runs drawn before that carry 10 % / banded colours: the page decodes each band back to a
  // value, blends and smooths the values, and paints them with these palettes, so every run looks the same.
  const NEWPAL = {
    rh700: { tf: "lin", stops: [[40, "#a6e39a", 0], [50, "#7fd36f", 120], [60, "#4fc052", 170], [70, "#25a843", 205], [80, "#138c39", 225], [90, "#086e2e", 238], [100, "#044a1f", 245]] },
    cape: { tf: "sqrt", stops: [[100, "#ffe680", 0], [250, "#ffd75a", 110], [500, "#ffbb38", 160], [1000, "#ff8a1c", 195], [1500, "#f2551c", 215], [2000, "#d62b3e", 228], [2500, "#b3187a", 236], [3000, "#7f22aa", 242], [4000, "#4c1a86", 248]] },
  };
  const tfv = (v, tf) => (tf === "sqrt" ? Math.sqrt(Math.max(v, 0)) : v);
  function newLegend(k) {
    const P = NEWPAL[k], t0 = tfv(P.stops[0][0], P.tf), t1 = tfv(P.stops[P.stops.length - 1][0], P.tf);
    return { tf: P.tf, vmin: P.stops[0][0], vmax: P.stops[P.stops.length - 1][0],
      stops: P.stops.map(([v, c, a]) => ({ p: +((tfv(v, P.tf) - t0) / (t1 - t0)).toFixed(4), v, c, a })) };
  }
  function palLUT(k) {   // 256 colours along the new palette, for painting values
    const P = NEWPAL[k], st = P.stops, t0 = tfv(st[0][0], P.tf), t1 = tfv(st[st.length - 1][0], P.tf);
    const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const lut = new Uint8ClampedArray(256 * 4);
    for (let i = 0; i < 256; i++) {
      const t = t0 + (t1 - t0) * i / 255;
      let k2 = 0; while (k2 < st.length - 2 && tfv(st[k2 + 1][0], P.tf) < t) k2++;
      const ta = tfv(st[k2][0], P.tf), tb = tfv(st[k2 + 1][0], P.tf), f = Math.max(0, Math.min(1, (t - ta) / (tb - ta)));
      const ca = hex(st[k2][1]), cb = hex(st[k2 + 1][1]);
      for (let c = 0; c < 3; c++) lut[i * 4 + c] = ca[c] + f * (cb[c] - ca[c]);
      lut[i * 4 + 3] = st[k2][2] + f * (st[k2 + 1][2] - st[k2][2]);
    }
    return { lut, t0, t1, tf: P.tf, vmin: st[0][0] };
  }
  function loadImg(u) {
    // read with CORS under its own address, so a copy cached earlier without CORS can never taint the canvas
    let im = cache.get(u);
    if (!im) { im = new Image(); im.crossOrigin = "anonymous"; im.src = u + (u.includes("?") ? "&" : "?") + "c=1"; cache.set(u, im); }
    if (im.complete && im.naturalWidth) return Promise.resolve(im);
    return new Promise((ok) => { im.addEventListener("load", () => ok(im)); im.addEventListener("error", () => ok(null)); if (im.complete) ok(im.naturalWidth ? im : null); });
  }
  function paintValues(geo, imgs, lg, prod, tmp, tc) {
    const { W, H } = geo, N = W * H, st = lg.stops;
    const cols = st.map((x) => [1, 3, 5].map((i) => parseInt(x.c.slice(i, i + 2), 16)));
    const mid = st.map((x, i) => (i < st.length - 1 ? (x.v + st[i + 1].v) / 2 : x.v));
    const below = st[0].v - (st[1].v - st[0].v) / 2;   // value given to clear pixels (below the scale)
    const V = new Float32Array(N), WS = new Float32Array(N);
    let any = false;
    geo.doms.forEach((g, k) => {
      const im = imgs[k];
      if (!im || !g.rw || !g.rh) return;
      any = true;
      tmp.width = g.rw; tmp.height = g.rh; tc.imageSmoothingEnabled = false; tc.clearRect(0, 0, g.rw, g.rh);
      tc.drawImage(im, g.fx0 - g.x0, g.fy0 - g.y0, g.fw, g.fh);
      const px = tc.getImageData(0, 0, g.rw, g.rh).data;
      for (let y = 0; y < g.rh; y++) {
        let p = (g.y0 + y) * W + g.x0, q = y * g.rw;
        for (let x = 0; x < g.rw; x++, p++, q++) {
          const wt = g.wt[q];
          if (wt <= 0) continue;
          let v = below;
          if (px[q * 4 + 3] > 8) {
            let best = 0, bd = 1e9;
            for (let b = 0; b < cols.length; b++) {
              const d = (px[q * 4] - cols[b][0]) ** 2 + (px[q * 4 + 1] - cols[b][1]) ** 2 + (px[q * 4 + 2] - cols[b][2]) ** 2;
              if (d < bd) { bd = d; best = b; }
            }
            v = mid[best];
          }
          V[p] += wt * v; WS[p] += wt;
        }
      }
    });
    if (!any) return null;
    for (let p = 0; p < N; p++) V[p] = WS[p] > 0 ? V[p] / WS[p] : NaN;
    for (const p of geo.gaps) V[p] = NaN;
    // fill the closed gaps, then smooth the bands away (two box passes of ~4 km), skipping the empty area
    for (let pass = 0; pass < 20; pass++) {
      let left = 0;
      for (const p of geo.gaps) {
        if (!isNaN(V[p])) continue;
        let s2 = 0, c = 0;
        for (const q of [p - 1, p + 1, p - W, p + W]) if (q >= 0 && q < N && !isNaN(V[q])) { s2 += V[q]; c++; }
        if (c) V[p] = s2 / c; else left++;
      }
      if (!left) break;
    }
    const blur = (src, r) => {
      const a = new Float32Array(N), out = new Float32Array(N);
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const p = y * W + x; if (isNaN(src[p])) { a[p] = NaN; continue; }
        let s2 = 0, c = 0; for (let k = Math.max(0, x - r); k <= Math.min(W - 1, x + r); k++) { const v = src[y * W + k]; if (!isNaN(v)) { s2 += v; c++; } }
        a[p] = s2 / c;
      }
      for (let x = 0; x < W; x++) for (let y = 0; y < H; y++) {
        const p = y * W + x; if (isNaN(a[p])) { out[p] = NaN; continue; }
        let s2 = 0, c = 0; for (let k = Math.max(0, y - r); k <= Math.min(H - 1, y + r); k++) { const v = a[k * W + x]; if (!isNaN(v)) { s2 += v; c++; } }
        out[p] = s2 / c;
      }
      return out;
    };
    const Vs = blur(blur(V, 2), 2);
    const L2 = palLUT(prod);
    const out = document.createElement("canvas"); out.width = W; out.height = H;
    const oc = out.getContext("2d"), od = oc.createImageData(W, H), o = od.data;
    for (let p = 0; p < N; p++) {
      const v = Vs[p];
      if (isNaN(v) || v < L2.vmin) continue;
      const i = Math.max(0, Math.min(255, Math.round((tfv(v, L2.tf) - L2.t0) / (L2.t1 - L2.t0) * 255)));
      o[p * 4] = L2.lut[i * 4]; o[p * 4 + 1] = L2.lut[i * 4 + 1]; o[p * 4 + 2] = L2.lut[i * 4 + 2];
      o[p * 4 + 3] = L2.lut[i * 4 + 3] * geo.fade[p];
    }
    oc.putImageData(od, 0, 0);
    return new Promise((ok) => out.toBlob((b) => ok(b ? { url: URL.createObjectURL(b), bounds: geo.bounds } : null), "image/png"));
  }
  function mosaicURL(items) {
    const ids = items.map((x) => x.id), key = items.map((x) => x.url || "-").join("|");
    if (MOS.urls.has(key)) return MOS.urls.get(key);
    const geo = mosaicGeo(ids);
    if (!geo) return Promise.resolve(null);
    const job = Promise.all(items.map((x) => (x.url ? loadImg(x.url) : null))).then((imgs) => {
      const { W, H } = geo, N = W * H;
      const R = new Float32Array(N), G = new Float32Array(N), B = new Float32Array(N), A = new Float32Array(N), WS = new Float32Array(N);
      const tmp = document.createElement("canvas"), tc = tmp.getContext("2d", { willReadFrequently: true });
      let any = false;
      const prod = ((items.find((x) => x.url) || {}).url || "").split("/").slice(-2)[0];
      const lg = S.man && S.man.products[prod] && S.man.products[prod].oldLegend;
      if (NEWPAL[prod] && lg && lg.bands) return paintValues(geo, imgs, lg, prod, tmp, tc);
      geo.doms.forEach((g, k) => {
        const im = imgs[k];
        if (!im || !g.rw || !g.rh) return;
        any = true;
        tmp.width = g.rw; tmp.height = g.rh; tc.clearRect(0, 0, g.rw, g.rh);
        tc.drawImage(im, g.fx0 - g.x0, g.fy0 - g.y0, g.fw, g.fh);
        const px = tc.getImageData(0, 0, g.rw, g.rh).data;   // throws if the image is not readable: caller falls back
        for (let y = 0; y < g.rh; y++) {
          let p = (g.y0 + y) * W + g.x0, q = y * g.rw;
          for (let x = 0; x < g.rw; x++, p++, q++) {
            const wt = g.wt[q];
            if (wt <= 0) continue;
            const a = px[q * 4 + 3] / 255, wa = wt * a;
            R[p] += wa * px[q * 4]; G[p] += wa * px[q * 4 + 1]; B[p] += wa * px[q * 4 + 2]; A[p] += wa; WS[p] += wt;
          }
        }
      });
      if (!any) return null;
      // per pixel: weighted mean of the grids (colour premultiplied by alpha); then fill the closed gaps
      for (let p = 0; p < N; p++) if (WS[p] > 0) { R[p] /= WS[p]; G[p] /= WS[p]; B[p] /= WS[p]; A[p] /= WS[p]; WS[p] = 1; }
      let left = geo.gaps;
      for (let pass = 0; pass < 20 && left.length; pass++) {
        const next = [], put = [];
        for (const p of left) {
          let r = 0, g2 = 0, b = 0, a = 0, c = 0;
          for (const q of [p - 1, p + 1, p - W, p + W]) if (q >= 0 && q < N && WS[q] === 1) { r += R[q]; g2 += G[q]; b += B[q]; a += A[q]; c++; }
          if (c) put.push([p, r / c, g2 / c, b / c, a / c]); else next.push(p);
        }
        for (const [p, r, g2, b, a] of put) { R[p] = r; G[p] = g2; B[p] = b; A[p] = a; WS[p] = 1; }
        left = next;
      }
      const out = document.createElement("canvas"); out.width = W; out.height = H;
      const oc = out.getContext("2d"), od = oc.createImageData(W, H), o = od.data;
      for (let p = 0; p < N; p++) {
        const a = A[p];
        if (!(a > 0)) continue;
        o[p * 4] = R[p] / a; o[p * 4 + 1] = G[p] / a; o[p * 4 + 2] = B[p] / a;
        o[p * 4 + 3] = 255 * a * geo.fade[p];
      }
      oc.putImageData(od, 0, 0);
      return new Promise((ok) => out.toBlob((b) => ok(b ? { url: URL.createObjectURL(b), bounds: geo.bounds } : null), "image/png"));
    });
    MOS.urls.set(key, job);
    job.catch(() => MOS.urls.delete(key));
    if (MOS.urls.size > 60) {
      const [k0, j0] = MOS.urls.entries().next().value;
      MOS.urls.delete(k0); j0.then((r) => r && setTimeout(() => URL.revokeObjectURL(r.url), 5000)).catch(() => null);
    }
    return job;
  }
  function showMosaic(items) {
    const tok = ++MOS.token;
    mosaicURL(items).then((r) => {
      if (tok !== MOS.token) return;
      if (r) { clearMulti(); overlayTo(r.url, r.bounds); } else overlayMany(items);
    }).catch(() => { if (tok === MOS.token) overlayMany(items); });
  }

  // arrows of water vapour transport, drawn over the colours
  const VecLayer = L.Layer.extend({
    initialize(opts) { this._ref = (opts && opts.ref) || 700; this._labels = !!(opts && opts.labels); },
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
      if (this._labels) {        // wind labels on the convergence areas, small and soft, never on top of each other
        ctx.font = "600 11px system-ui, -apple-system, 'Segoe UI', sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
        const boxes = [];
        this._v.forEach(([lat, lon, t]) => {
          const p = m.latLngToContainerPoint([lat, lon]);
          if (p.x < -40 || p.y < -10 || p.x > size.x + 40 || p.y > size.y + 10) return;
          const w = ctx.measureText(t).width + 8, h = 16;
          const b = [p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2];
          if (boxes.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) return;
          boxes.push(b);
          ctx.strokeStyle = "rgba(10,14,20,.78)"; ctx.lineWidth = 3; ctx.strokeText(t, p.x, p.y);
          ctx.fillStyle = "#ffffff"; ctx.fillText(t, p.x, p.y);
        });
        return;
      }
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
    const doms = (d.members || [S.dom]).filter((m) => (S.man.domains[m].hours || []).includes(f.h));
    const urls = doms.map((m) => `${base(S.man.domains[m])}runs/${S.run}/${m}/${vc.dir}/${String(f.h).padStart(3, "0")}.json`);
    const url = urls.join("|");
    if (vec.layer && vec.dir !== vc.dir) { map.removeLayer(vec.layer); vec.layer = null; }
    if (!vec.layer) { vec.layer = new VecLayer(vc); vec.dir = vc.dir; vec.layer.addTo(map); }
    if (vec.url === url) return;
    vec.url = url;
    const all = await Promise.all(urls.map((u) => getJSON(u).then((j) => (vc.labels ? j.l : j.v) || []).catch(() => [])));
    if (vec.url === url && vec.layer) vec.layer.setData(all.flat());
  }

  const svrURL = (x) => `${CL}fig/${x.file}?c=${SVR.j.cycle}`;
  function svrShow() {
    const f = S.frames[S.idx], x = f && SVR.j && SVR.j.days[f.svr];
    if (!x) {
      clearOverlay(); $("timeLabel").textContent = SVR.failed ? "لم تصدر الخريطة بعد" : "جارٍ التحميل…";
      if (!SVR.j) svrLoad().then((j) => { if (j && S.prod === "svr") { buildFrames(false); drawLegend(); showFrame(); } });
      return;
    }
    const e = SVR.j.extent;
    MOS.token++; clearMulti(); overlayTo(svrURL(x), [[e[2], e[0]], [e[3], e[1]]]);
    $("timeRange").max = S.frames.length - 1;
    $("timeRange").value = S.idx;
    const t = new Date(x.d + "T09:00:00Z");
    // a quiet day leaves the map almost empty: say so, so the layer never looks broken (Fahad, 23 Nov 2026)
    $("timeLabel").textContent = `${fmtDay.format(t)} · ` + (x.max >= 5 ? `أعلى احتمال ${num(x.max)}٪`
      : "لا عاصفة شديدة متوقعة");
    for (let k = 1; k <= 2; k++) preload(S.idx + k);
    rvSync();
    if (S.pointPopup && S.pointPopup.isOpen()) S.pointPopup.setContent(pointHTML(S.pointPopup._pt));
  }

  function showFrame() {
    if (LX.on) return liShow();
    showVectors();
    if (S.prod === "svr") return svrShow();
    const d = S.man && S.man.domains[S.dom];
    if (!d || !S.frames.length) { clearOverlay(); $("timeLabel").textContent = "—"; return; }
    S.idx = Math.max(0, Math.min(S.idx, S.frames.length - 1));
    if (d.members) showMosaic(d.members.map((m) => ({ id: m, url: urlFor(m, S.frames[S.idx]), bounds: S.man.domains[m].bounds })));
    else if (NEWPAL[S.prod] && d.points) showMosaic([{ id: S.dom, url: frameURL(S.idx), bounds: d.bounds }]);   // one grid, same smooth painting
    else { MOS.token++; clearMulti(); overlayTo(frameURL(S.idx), d.bounds); }
    $("timeRange").max = S.frames.length - 1;
    $("timeRange").value = S.idx;
    $("timeLabel").textContent = frameLabel(S.frames[S.idx]);
    for (let k = 1; k <= 4; k++) preload(S.idx + k);
    rvSync();
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
    if (S.prod === "svr") {   // one map per Makkah day, opening on today
      const j = SVR.j;
      S.frames = j ? j.days.map((x, i) => ({ svr: i, d: x.d })) : [];
      const today = new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
      if (!prevKey || prevKey.svr == null) S.idx = Math.max(0, S.frames.findIndex((f) => f.d >= today));
      return;
    }
    if (!d) { S.frames = []; return; }
    // a domain may not have every product (the 1 km nest has hourly maps only)
    if (!LIVE(S.prod) && d.products && !d.products.includes(S.prod)) { S.prod = "refl"; $("prodSelect").value = "refl"; drawLegend(); }
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
    const p = S.prod === "svr" ? SVR.j && { label: SVR_LABEL + " · النموذج الأمريكي", unit: "٪", legend: SVR.j.legend } : S.man && S.man.products[S.prod];
    if (!p) { $("legend").innerHTML = ""; return; }
    const lg = p.legend;
    const grad = lg.bands
      ? lg.stops.slice(0, -1).map((x, i) => `${rgba(x.c, x.a)} ${(x.p * 100).toFixed(1)}% ${(lg.stops[i + 1].p * 100).toFixed(1)}%`).join(", ")
      : lg.stops.map((x) => `${rgba(x.c, x.a)} ${(x.p * 100).toFixed(1)}%`).join(", ");
    const step = lg.stops.length > 7 ? 2 : 1;
    const ticks = lg.stops.map((x, i) => (i % step === 0 || i === lg.stops.length - 1)
      ? `<span style="left:${(x.p * 100).toFixed(1)}%">${num(x.v, x.v < 1 ? 1 : 0)}</span>` : "").join("");
    setMini(`linear-gradient(to right, ${grad})`);
    $("legend").innerHTML = `<div class="legend-title"><span>${lab(S.prod) || p.label}</span><span>${p.unit}</span></div>
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
    const ids = ["k3", "sa", "d02", "nw", "n", "c", "e", "se", "d03"].filter((id) => S.man && S.man.domains[id]);  // the Kingdom-wide run replaces the western 9 km parent
    if (!ids.length) { box.innerHTML = ""; return; }
    let sel = $("domSelect");
    if (!sel) {
      box.innerHTML = `<label class="mpill mpill-dom"><span class="mpill-txt" id="domTxt"></span><span class="mpill-caret">▾</span><select id="domSelect" class="prod-select dom-select" aria-label="المجال"></select></label>`;
      sel = $("domSelect");
      sel.onchange = () => setDomain(sel.value, true);
    }
    sel.innerHTML = ids.map((id) => { const d = S.man.domains[id]; return `<option value="${id}">${d.name} ${d.res}</option>`; }).join("")
      // the 1 km nest runs only in its window of hours: say so while it has not reached it yet
      + (S.k1wait && !ids.includes("d03") ? `<option value="" disabled>جدة ومكة والطائف ١ كم · يُحسب، تظهر خرائطه حين تبلغ ساعاته</option>` : "");
    sel.value = ids.includes(S.dom) ? S.dom : ids[0];
    syncPills();
  }

  // the two lists at the top are small pills that show only the chosen item; the list itself opens on a tap
  function syncPills() {
    for (const [s, t] of [["domSelect", "domTxt"], ["prodSelect", "prodTxt"]]) {
      const sel = $(s), txt = $(t);
      if (!sel || !txt) continue;
      const o = sel.selectedOptions && sel.selectedOptions[0];
      const v = o ? o.text : "";
      if (txt.textContent !== v) txt.textContent = v;
    }
  }
  setInterval(syncPills, 400);
  document.addEventListener("change", (e) => { if (e.target && (e.target.id === "domSelect" || e.target.id === "prodSelect")) syncPills(); });

  // the colour key: folded by default (only the small strip under the layers box); a tap on the strip opens the
  // full key at the bottom, a tap on either closes it again
  const LG = $("legend");
  try { if (localStorage.getItem("lgOpen") === "1") LG.classList.remove("mini"); } catch (e) { /* no storage */ }
  function lgToggle() {
    LG.classList.toggle("mini");
    try { localStorage.setItem("lgOpen", LG.classList.contains("mini") ? "0" : "1"); } catch (e) { /* no storage */ }
  }
  function setMini(bg) { const m = $("lgMini"); if (m) m.style.background = bg; }
  $("lgMini").addEventListener("click", lgToggle);
  LG.addEventListener("click", lgToggle);
  LG.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); lgToggle(); } });

  function drawProducts() {
    const sel = $("prodSelect");
    const P = (S.man && S.man.products) || {};
    const opt = (k) => (P[k] ? `<option value="${k}">${lab(k) || P[k].label}</option>` : "");
    // one flat list, live lightning first
    sel.innerHTML = `<option value="radar">الرادار</option><option value="lightning">البرق</option>` + [...HOURLY, ...SINGLE, ...DAILY].map(opt).join("")
      + `<option value="svr">${SVR_LABEL}</option>`;
    const listed = [...HOURLY, ...SINGLE, ...DAILY].includes(S.prod);
    if ((!P[S.prod] || !listed) && !LIVE(S.prod) && S.prod !== "svr") S.prod = "refl";
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
    if (!S.man || !S.man.domains[id]) id = ["k3", "d02", "sa", "d03"].find((k) => S.man && S.man.domains[k]) || Object.keys((S.man && S.man.domains) || {})[0] || "d01";
    S.dom = id; store.set("dom", id);
    buildFrames(true);
    drawChips(); drawRects(); showFrame();
    const d = S.man && S.man.domains[id];
    if (fit && d && d.bounds) map.fitBounds(d.bounds, { padding: [10, 10] });
  }

  // the current domain if it has the product, otherwise the first that does
  function domFor(p) {
    const has = (k) => { const d = S.man && S.man.domains[k]; return d && (!d.products || d.products.includes(p)); };
    if (LIVE(p)) return S.dom;
    return ["k3", "sa", "d02", "d03", "d01"].find(has) || S.dom;
  }

  function setProduct(p) {
    S.prod = p; store.set("prod", p);
    if (LIVE(p)) { if (!LX.on) liEnter(); else { S.frames = []; liFrames(); } return; }
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
      const f = LX.on && S.prod !== "radar" && S.frames[S.idx];   // the radar entry shows the radar alone
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

  // the newest time the satellite service actually has (its list of times); when it stops sending
  // (an outage on their side, e.g. 18-19 Nov 2026) the page shows the last hour it has and says so
  async function liLatest() {
    for (const u of [`${LI_WMS.replace("/wms", "/mtg_fd/li_afa/wms")}?service=WMS&request=GetCapabilities&version=1.3.0`,
                     `${LI_WMS}?service=WMS&request=GetCapabilities&version=1.3.0`]) {
      const ac = new AbortController(), kill = setTimeout(() => ac.abort(), 25e3);
      try {
        const r = await fetch(u, { cache: "no-store", signal: ac.signal });
        if (!r.ok) continue;
        const x = await r.text(), i = x.indexOf("li_afa");
        const m = i >= 0 && /<Dimension[^>]*name="time"[^>]*>([^<]+)</.exec(x.slice(i));
        if (!m) continue;
        const end = Date.parse(m[1].trim().split(",").pop().split("/")[1] || m[1].trim().split(",").pop());
        if (end) return end;
      } catch (e) { /* try the next address */ } finally { clearTimeout(kill); }
    }
    return 0;
  }

  async function liFetch(t) {
    const B = LI_BOX, W = LI_W, H = LI_H;
    const url = `${LI_WMS}?service=WMS&request=GetMap&version=1.3.0&layers=mtg_fd:li_afa&styles=&crs=EPSG:4326` +
      `&bbox=${B.s},${B.w},${B.n},${B.e}&width=${W}&height=${H}&format=image/png&transparent=true&time=${liTimeISO(t)}`;
    // a request that hangs (phone asleep, weak signal) must not block every later update
    const ac = new AbortController(), kill = setTimeout(() => ac.abort(), 20e3);
    let r;
    try { r = await fetch(url, { mode: "cors", cache: "no-store", signal: ac.signal }); } finally { clearTimeout(kill); }
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
    const atEnd = S.idx >= S.frames.length - 1;
    if (S.prod === "radar") S.frames = RV.frames.map((f) => ({ t: f.t }));   // the radar's last 12 hours (our archive) then the live 2 hours, every 10 minutes
    else {
      const times = [...LX.got.keys()].sort((a, b) => a - b);
      const newest = times.length ? times[times.length - 1] : 0;
      S.frames = times.filter((t) => t >= newest - LI_WIN).map((t) => ({ t }));
    }
    if (atEnd || !S.playing) S.idx = S.frames.length - 1;
    drawLegend(); showFrame();
  }

  async function liLoad() {
    if (LX.busy && Date.now() - LX.busy < 90e3) return;
    const run = LX.busy = Date.now();
    if (!LX.raw) liCacheLoad();
    // images appear about 10 minutes after their time and keep filling for a while after that, so the
    // newest 30 minutes are asked again on every update (an early empty answer is never kept for good)
    if (!LX.srcAt || Date.now() - LX.srcAt > 5 * 60e3) { const e = await liLatest(); if (e) { LX.srcEnd = e; LX.srcAt = Date.now(); } }
    const nowTop = Math.floor((Date.now() - 5 * 60e3) / LI_STEP) * LI_STEP;
    const top = LX.srcEnd && LX.srcEnd < nowTop ? Math.floor(LX.srcEnd / LI_STEP) * LI_STEP : nowTop, want = [];
    for (let t = top; t > top - LI_BACK; t -= LI_STEP) if (!LX.got.has(t) || t > top - 30 * 60e3) want.push(t);
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
    if (LX.busy === run) LX.busy = false;
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
    if (Date.now() - RV.got > 2 * 60e3) rvLoad();   // the radar list is fresh every time this mode opens
    clearInterval(LX.timer); LX.timer = setInterval(() => { if (!document.hidden) liLoad(); }, 2 * 60e3);
  }
  // the phone stops timers while the page is in the background: update at once on return
  document.addEventListener("visibilitychange", () => { if (!document.hidden && LX.on) liLoad(); });
  window.addEventListener("pageshow", (e) => { if (e.persisted && LX.on) liLoad(); });
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
    $("timeLabel").textContent = f ? (S.prod === "radar" ? `الرادار ${fmtClock.format(f.t)}` : `البرق في الساعة المنتهية ${fmtClock.format(f.t)}`)
      : S.prod === "radar" ? "جارٍ جلب صور الرادار…"
      : LX.busy ? "جارٍ جلب رصد البرق…" : "تعذّر جلب رصد البرق، سيُعاد المحاولة";
    if (LX.layer) LX.layer.redraw();
    rvSync();
    const n = $("liCount"); if (n && S.prod !== "radar") n.textContent = liLate() + (f ? (LX.shown ? `مواضع البرق: ${num(LX.shown)}` : "لا برق في هذه الساعة") : "");
  }
  function liLate() {
    return LX.srcEnd && Date.now() - LX.srcEnd > 40 * 60e3
      ? `مصدر البرق (القمر الأوروبي) متوقف منذ ${new Date(LX.srcEnd).toDateString() === new Date().toDateString() ? "" : "أمس "}${fmtClock.format(LX.srcEnd)}، المعروض آخر ما أرسله. ` : "";
  }

  function liLegend() {
    if (S.prod === "radar") return rvLegend();
    const svg = (c) => `<svg viewBox="-6 -6 12 12" width="13" height="13"><path d="M-0.1,-5 L3,-5 L1,-1 L3,-1 L-2.2,5 L-0.4,0.4 L-2.4,0.4 Z" fill="${c}" stroke="#1a1000" stroke-width=".7" stroke-linejoin="round"/></svg>`;
    const keys = LI_AGES.map(([m, c], i) => `<span>${svg(c)}${i === 0 ? `آخر ${num(m)} د` : `حتى ${num(m)} د`}</span>`).join("");
    setMini(`linear-gradient(to right, ${LI_AGES.map(([m, c]) => c).join(", ")})`);
    $("legend").innerHTML = `<div class="legend-title"><span>البرق المرصود من القمر الأوروبي، يتحدث كل ٥ دقائق</span><span id="liCount">${liLate()}${LX.shown ? `مواضع البرق: ${num(LX.shown)}` : ""}</span></div>
      <div class="bolt-key">${keys}</div>`;
  }

  // ------------------------------------------------------------------ live rain radar
  // Saudi weather radars (National Center for Meteorology) through the free RainViewer service:
  // the last two hours every 10 minutes, tiles up to zoom 7 (enlarged beyond). Free for personal use,
  // with the source named. In lightning mode the radar follows the lightning time; over the model
  // maps it shows the latest picture. A pill turns it on and off (remembered in this browser).
  const RV_API = "https://api.rainviewer.com/public/weather-maps.json";
  const RV_ARCH = (window.SWRF_DATA || "").replace("/model-data/", "/radar-archive/");
  var RV = { on: false, host: "", frames: [], layers: new Map(), cur: null, timer: null, got: 0 };
  map.createPane("radar"); map.getPane("radar").style.zIndex = 620; map.getPane("radar").style.pointerEvents = "none";
  async function rvLoad() {
    try {
      const r = await fetch(RV_API, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      RV.host = j.host || "https://tilecache.rainviewer.com";
      RV.live = ((j.radar && j.radar.past) || []).map((f) => ({ t: f.time * 1000, path: f.path, key: f.path }));
      RV.got = Date.now();
    } catch (e) { /* offline or service down: keep what we have */ }
    // our own archive keeps 12 hours (the free service only 2): older pictures come from it (Fahad 18 Nov 2026)
    try {
      const r = await fetch(`${RV_ARCH}index.json?t=${Math.floor(Date.now() / 300e3)}`);
      if (r.ok) RV.arch = await r.json();
    } catch (e) { /* no archive yet */ }
    // join both lists by time (the newest picture always last, whichever source has it); the free
    // service's pictures disappear after about 2 hours, so older times are drawn from our archive
    const now = Date.now(), by = new Map();
    for (const f of (RV.arch && RV.arch.frames) || []) by.set(f.t * 1000, { t: f.t * 1000, arch: true, key: "a" + f.t });
    for (const f of RV.live || []) if (now - f.t < 100 * 60e3 || !by.has(f.t)) by.set(f.t, f);
    RV.frames = [...by.values()].filter((f) => now - f.t < 12.2 * 3600e3).sort((a, b) => a.t - b.t);
    if (LX.on && S.prod === "radar") liFrames(); else rvSync();
  }
  // The free service sends one colour scheme ("Universal Blue"); each pixel is turned back into its
  // reflectivity (dBZ) and repainted in the classic radar colours used by the Saudi met service.
  const RV_UB = [[15, 0x88ddee], [16, 0x6cd1eb], [17, 0x51c5e8], [18, 0x36bae5], [19, 0x1baee2], [20, 0x00a3e0], [21, 0x009ad5], [22, 0x0091ca],
    [23, 0x0088bf], [24, 0x007fb4], [25, 0x0077aa], [26, 0x0070a3], [27, 0x00699c], [28, 0x006295], [29, 0x005b8e], [30, 0x005588],
    [31, 0x005180], [32, 0x004e78], [33, 0x004a70], [34, 0x004768], [35, 0xffee00], [36, 0xffe000], [37, 0xffd200], [38, 0xffc500],
    [39, 0xffb700], [40, 0xffaa00], [41, 0xff9f00], [42, 0xff9500], [43, 0xff8b00], [44, 0xff8100], [45, 0xff4400], [46, 0xf23600],
    [47, 0xe62800], [48, 0xd91b00], [49, 0xcd0d00], [50, 0xc10000], [51, 0xa80000], [52, 0x8f0000], [53, 0x760000], [54, 0x5d0000],
    [55, 0xffaaff], [56, 0xff9fff], [57, 0xff95ff], [58, 0xff8bff], [59, 0xff81ff], [60, 0xff77ff], [61, 0xff6cff], [62, 0xff62ff],
    [63, 0xff58ff], [64, 0xff4eff], [65, 0xffffff]];
  // the colours Fahad chose (18 Nov 2026, like the Yanbu radar page): light rain green, then blue, purple, pink,
  // yellow, orange and red for the heaviest cores; blended smoothly between these dBZ points
  // colours after the Yanbu radar page (Fahad 18 Nov 2026): weak echoes green, then blue, violet, magenta, pink,
  // yellow cores, orange and red for the strongest; blended smoothly between these dBZ points
  const RV_PAL = [[5, "#4cae4c"], [9, "#45a845"], [11, "#3a8be0"], [15, "#5367c9"], [17.5, "#8043c9"], [20, "#9c3ab5"], [22.5, "#c23fa4"],
    [25, "#c95197"], [27.5, "#cb6f98"], [30, "#ca878e"], [32.5, "#d49471"], [35, "#d9a35e"], [37.5, "#eaba57"], [40, "#f6ce56"],
    [42.5, "#fae144"], [45, "#f9ef3e"], [47.5, "#fbd650"], [50, "#f8b469"], [52, "#fa995d"], [54, "#e87d42"], [56, "#e96b38"],
    [58, "#e16145"], [60, "#de695f"], [62, "#c79796"], [66, "#c0c7cd"]];   // read off the Yanbu radar legend (Fahad's screenshots, 18 Nov 2026)
  const RV_RGB = RV_PAL.map(([d, c]) => [d, parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]);
  function rvColor(d) {
    if (d <= RV_RGB[0][0]) return RV_RGB[0];
    for (let k = 1; k < RV_RGB.length; k++) {
      const b = RV_RGB[k];
      if (d <= b[0]) { const a = RV_RGB[k - 1], t = (d - a[0]) / (b[0] - a[0]); return [d, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t]; }
    }
    return RV_RGB[RV_RGB.length - 1];
  }
  const rvMemo = new Map();
  function rvDbz(r, g, b, a) {
    // the weak echoes (below 15 dBZ) are a see-through beige whose opacity grows with dBZ
    if (r > 0x60 && Math.abs(r - g) < 0x18 && b < g && b > 0x50) return a < 0x64 ? -10 + (a - 0x14) / 5.3 : 5 + (a - 0x64) / 10;
    const k = (r << 16) | (g << 8) | b;
    let d = rvMemo.get(k);
    if (d === undefined) {
      let best = 1e9;
      for (const [z, c] of RV_UB) {
        const dr = r - (c >> 16), dg = g - ((c >> 8) & 255), db = b - (c & 255), e = dr * dr + dg * dg + db * db;
        if (e < best) { best = e; d = z; }
      }
      if (rvMemo.size < 50000) rvMemo.set(k, d);
    }
    return d;
  }
  // Each picture is read once at its own resolution (zoom 7 at most) as dBZ plus a weight (the see-through
  // edges), then every map tile is drawn at the map's zoom by bilinear blending of dBZ, so the echoes stay
  // smooth when zoomed in instead of showing the 1 km squares.
  const RV_SRC = new Map();
  const RV_AC = new Map();   // decoded archive pictures, the last few only (each is a few MB)
  function rvArch(t) {
    const key = "a" + t;
    if (RV_AC.has(key)) { const p = RV_AC.get(key); RV_AC.delete(key); RV_AC.set(key, p); return p; }
    const pr = new Promise((res) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        try {
          const cv = document.createElement("canvas"); cv.width = img.width; cv.height = img.height;
          const cx = cv.getContext("2d", { willReadFrequently: true });
          cx.drawImage(img, 0, 0);
          const p = cx.getImageData(0, 0, img.width, img.height).data, v = new Uint8Array(img.width * img.height);
          for (let k = 0; k < v.length; k++) v[k] = p[4 * k];
          res({ v, w: img.width, h: img.height });
        } catch (e) { res(null); }
      };
      img.onerror = () => res(null);
      img.src = `${RV_ARCH}f/${t}.png`;
    });
    RV_AC.set(key, pr);
    while (RV_AC.size > 6) RV_AC.delete(RV_AC.keys().next().value);
    return pr;
  }
  function rvSource(path, z, x, y) {
    const key = `${path}/${z}/${x}/${y}`;
    if (RV_SRC.has(key)) return RV_SRC.get(key);
    const pr = new Promise((res) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        try {
          const cv = document.createElement("canvas"); cv.width = cv.height = 256;
          const cx = cv.getContext("2d", { willReadFrequently: true });
          cx.drawImage(img, 0, 0, 256, 256);
          const p = cx.getImageData(0, 0, 256, 256).data, D = new Float32Array(65536), W = new Float32Array(65536);
          for (let k = 0; k < 65536; k++) {
            const a = p[4 * k + 3];
            if (a < 6) continue;
            const d = rvDbz(p[4 * k], p[4 * k + 1], p[4 * k + 2], a);
            if (d < 0) continue;
            const opaque = !(p[4 * k] > 0x60 && Math.abs(p[4 * k] - p[4 * k + 1]) < 0x18 && p[4 * k + 2] < p[4 * k + 1] && p[4 * k + 2] > 0x50);
            const w = opaque ? a / 255 : 1;
            D[k] = d * w; W[k] = w;
          }
          res({ D, W });
        } catch (e) { RV.cors = false; res(null); }
      };
      img.onerror = () => res(null);
      img.src = `${RV.host}${path}/256/${z}/${x}/${y}/2/1_0.png`;
    });
    RV_SRC.set(key, pr);
    if (RV_SRC.size > 400) RV_SRC.delete(RV_SRC.keys().next().value);
    return pr;
  }
  // One canvas over the whole map view (no tiles, so no seams): every screen pixel takes its dBZ by bilinear
  // blending of the four nearest radar pixels, then its colour.
  const RadarCanvas = L.Layer.extend({
    onAdd(m) {
      this._c = L.DomUtil.create("canvas", "leaflet-zoom-hide");
      m.getPane("radar").appendChild(this._c);
      m.on("moveend zoomend resize", this.redraw, this);
      this.redraw();
    },
    onRemove(m) { m.off("moveend zoomend resize", this.redraw, this); L.DomUtil.remove(this._c); },
    setFrame(f) { this.f = f; this.path = f.key; this.redraw(); },
    getAttribution() { return '<a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>'; },
    async redraw() {
      const m = this._map; if (!m || !this.f) return;
      const tok = this._tok = (this._tok || 0) + 1, fr = this.f, path = fr.path, A = fr.arch && RV.arch;
      const size = m.getSize(), zoom = m.getZoom(), z = A ? 7 : Math.max(0, Math.min(7, Math.ceil(zoom))), sc = 2 ** (z - zoom), n = 2 ** z;
      const tl = m.containerPointToLayerPoint([0, 0]), org = tl.add(m.getPixelOrigin());
      const gx0 = org.x * sc, gy0 = org.y * sc;
      const tx0 = Math.floor((gx0 - 1) / 256), tx1 = Math.floor((gx0 + size.x * sc + 1) / 256);
      const ty0 = Math.max(0, Math.floor((gy0 - 1) / 256)), ty1 = Math.min(n - 1, Math.floor((gy0 + size.y * sc + 1) / 256));
      const T = new Map(), jobs = [];
      let AV = null;
      if (A) jobs.push(rvArch(fr.t / 1000).then((x) => { AV = x; }));
      else for (let tx = tx0; tx <= tx1; tx++) for (let ty = ty0; ty <= ty1; ty++) {
        const wx = ((tx % n) + n) % n;
        jobs.push(rvSource(path, z, wx, ty).then((src) => { if (src) T.set(tx * 4096 + ty, src); }));
      }
      await Promise.all(jobs);
      if (tok !== this._tok || !this._map) return;
      const W = size.x, H = size.y, c = this._c;
      c.width = W; c.height = H; c.style.width = W + "px"; c.style.height = H + "px";
      L.DomUtil.setPosition(c, tl);
      const cx = c.getContext("2d"), im = cx.createImageData(W, H), q = im.data;
      let lastK = -1e9, src = null;
      const ax0 = A ? A.x0 : 0, ay0 = A ? A.y0 : 0, aw = A ? A.w : 0, ah = A ? A.h : 0;
      const at = A ? (X, Y, out) => {   // archive picture: one grey image, v = (dBZ + 10) * 3
        const x = X - ax0, y = Y - ay0;
        const v = AV && x >= 0 && y >= 0 && x < aw && y < ah ? AV.v[y * aw + x] : 0;
        if (!v) { out[0] = 0; out[1] = 0; return; }
        out[0] = v / 3 - 10; out[1] = 1;
      } : (X, Y, out) => {   // dBZ*weight and weight of one radar pixel (global pixel numbers at zoom z)
        const tx = Math.floor(X / 256), ty = Math.floor(Y / 256), k = tx * 4096 + ty;
        if (k !== lastK) { lastK = k; src = T.get(k) || null; }
        if (!src) { out[0] = 0; out[1] = 0; return; }
        const o = (Y - ty * 256) * 256 + (X - tx * 256);
        out[0] = src.D[o]; out[1] = src.W[o];
      };
      const a = [0, 0], b = [0, 0], e = [0, 0], f = [0, 0];
      for (let j = 0; j < H; j++) {
        const gy = gy0 + (j + 0.5) * sc - 0.5, Y0 = Math.floor(gy), ty = gy - Y0;
        if (Y0 < 0 || Y0 + 1 >= n * 256) continue;
        for (let i = 0; i < W; i++) {
          const gx = gx0 + (i + 0.5) * sc - 0.5, X0 = Math.floor(gx), tx = gx - X0;
          at(X0, Y0, a); at(X0 + 1, Y0, b); at(X0, Y0 + 1, e); at(X0 + 1, Y0 + 1, f);
          const k0 = (1 - tx) * (1 - ty), k1 = tx * (1 - ty), k2 = (1 - tx) * ty, k3 = tx * ty;
          const w = a[1] * k0 + b[1] * k1 + e[1] * k2 + f[1] * k3;
          if (w < 0.04) continue;
          const d = (a[0] * k0 + b[0] * k1 + e[0] * k2 + f[0] * k3) / w;
          if (d < 5) continue;
          const col = rvColor(d), o = 4 * (j * W + i);
          // weak (green) echoes see-through so the ground shows, rain from blue upward nearly solid
          const al = d < 10 ? 105 + (d - 5) * 9 : d < 12 ? 150 + (d - 10) * 25 : 205;
          q[o] = col[1]; q[o + 1] = col[2]; q[o + 2] = col[3]; q[o + 3] = al * Math.min(1, w * 1.6);
        }
      }
      cx.putImageData(im, 0, 0);
    },
  });
  function rvLegend() {
    const lo = RV_PAL[0][0], hi = RV_PAL[RV_PAL.length - 1][0], at = (d) => ((d - lo) / (hi - lo) * 100).toFixed(1);
    const grad = `linear-gradient(to right, ${RV_PAL.map(([d, c]) => `${c} ${at(d)}%`).join(", ")})`;
    setMini(grad);
    $("legend").innerHTML = `<div class="legend-title"><span>رادارات المركز الوطني للأرصاد، صورة كل ١٠ دقائق</span><span>ديسيبل</span></div>
      <div class="legend-bar" style="background:${grad}"></div>
      <div class="legend-ticks">${[10, 20, 30, 40, 50, 60].map((d) => `<span style="left:${at(d)}%">${num(d)}</span>`).join("")}</div>
      <div class="legend-title" style="margin-top:2px;direction:ltr"><span>رذاذ</span><span>خفيف</span><span>متوسط</span><span>غزير</span><span>برد</span></div>`;
  }
  function rvLayer() {
    if (!RV.canvas) RV.canvas = new RadarCanvas({ pane: "radar" });
    if (!map.hasLayer(RV.canvas)) RV.canvas.addTo(map);
    return RV.canvas;
  }
  function rvPick() {
    if (!RV.frames.length) return null;
    if (LX.on && S.frames[S.idx]) {   // the radar picture closest before the lightning time
      const t = S.frames[S.idx].t; let best = RV.frames[0];
      for (const f of RV.frames) if (f.t <= t + (S.prod === "radar" ? 0 : 5 * 60e3)) best = f;
      return best;
    }
    return RV.frames[RV.frames.length - 1];
  }
  function rvSync() {
    if (!RV) return;
    const btn = $("rvBtn"), forced = S.prod === "radar";
    if (btn) btn.hidden = forced;   // in the radar entry the radar is always on
    if (!RV.on && !forced) {
      if (RV.canvas) map.removeLayer(RV.canvas);
      RV.cur = null;
      if (btn) { btn.classList.remove("active"); btn.setAttribute("aria-pressed", "false"); btn.textContent = "الرادار"; }
      return;
    }
    if (btn) { btn.classList.add("active"); btn.setAttribute("aria-pressed", "true"); }
    const f = rvPick();
    if (!f) { if (btn) btn.textContent = "الرادار…"; return; }
    if (btn) btn.textContent = `الرادار ${fmtClock.format(f.t)}`;
    const l = rvLayer();
    if (RV.cur === f.key && l.path === f.key) return;
    RV.cur = f.key;
    l.setFrame(f);   // the previous picture stays until the new one is drawn
    // fetch the neighbours so sliding through time does not wait
    const i = RV.frames.indexOf(f), zoom = map.getZoom(), z = Math.max(0, Math.min(7, Math.ceil(zoom))), sc = 2 ** (z - zoom), n = 2 ** z;
    const pb = map.getPixelBounds(), x0 = Math.floor(pb.min.x * sc / 256), x1 = Math.floor(pb.max.x * sc / 256);
    const y0 = Math.max(0, Math.floor(pb.min.y * sc / 256)), y1 = Math.min(n - 1, Math.floor(pb.max.y * sc / 256));
    for (const k of [i - 1, i + 1]) if (RV.frames[k] && RV.frames[k].arch) rvArch(RV.frames[k].t / 1000);
    for (const k of [i - 1, i + 1, i + 2]) if (RV.frames[k] && !RV.frames[k].arch) for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) rvSource(RV.frames[k].path, z, ((x % n) + n) % n, y);
  }
  function rvToggle() {
    RV.on = !RV.on; store.set("rv", RV.on ? "1" : "0");
    if (RV.on && (!RV.frames.length || Date.now() - RV.got > 5 * 60e3)) rvLoad(); else rvSync();
  }
  rvLoad();
  // refresh every 2.5 minutes while the radar is on screen (also in the radar entry itself), and at once
  // when the phone comes back to the page, so a page left open never stays on an old picture
  const rvWanted = () => RV.on || S.prod === "radar" || LX.on;
  RV.timer = setInterval(() => { if (rvWanted() && !document.hidden) rvLoad(); }, 2.5 * 60e3);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && rvWanted() && Date.now() - RV.got > 60e3) rvLoad(); });
  window.addEventListener("pageshow", (e) => { if (e.persisted && rvWanted()) rvLoad(); });

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
    const key = base(d) + S.run + dom + d.points.hours.length;   // the branch too: never one model's points for the other
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
    const sv = S.prod === "svr" ? svrAt(pt.lat, pt.lon) : null;
    const now = S.prod === "svr" ? `<div class="pt-now"><span>${SVR_LABEL}: <b>${sv == null ? "—" : num(sv) + "٪"}</b></span></div>` : h == null ? "" : `<div class="pt-now">
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

  // each model keeps to its own files (Fahad, 19 Nov 2026: never mix GFS and ECMWF): a load started for one model
  // or run is dropped if the model or run changed while it was still reading, and every grid carries its own
  // branch address, so a map can never take one grid from one model and another grid from the other
  let loadTok = 0;
  async function loadRun(run, first) {
    const tok = ++loadTok, D = DATA, RG = REGIONS, M = MODEL;
    const stale = () => tok !== loadTok || M !== MODEL || D !== DATA;
    S.run = run;
    let man = null, meteo = null;
    try { man = await getJSON(`${D}runs/${run}/manifest.json`); } catch (e) { man = null; }
    try { meteo = await getJSON(`${D}runs/${run}/meteo.json`); } catch (e) { meteo = null; }
    if (stale()) return;
    if (man) for (const d of Object.values(man.domains || {})) if (!d.base) d.base = D;
    S.man = man; S.meteo = meteo;
    // the 9 km grids (the Kingdom-wide run and the western 9 km parent) are not shown: only 3 km (Fahad, 13 Nov 2026)
    S.k1wait = false;
    if (M === "gfs") try {  // the 1 km nest (GFS runs only) (only its own grid; the 9 and 3 km grids there just feed it)
      const k1 = await getJSON(`${DATA_1K}runs/${run}/manifest.json`);
      S.k1wait = !(k1.domains && k1.domains.d03) && k1.status === "running";
      if (S.man && k1.domains && k1.domains.d03) {
        S.man.domains.d03 = { ...k1.domains.d03, base: DATA_1K, proj: k1.proj };
        S.man.products = { ...(k1.products || {}), ...(S.man.products || {}) };
      }
    } catch (e) { S.k1wait = S.runs && S.runs[0] && S.runs[0].run === run && S.runs[0].status === "running"; }
    if (stale()) return;
    const regs = await Promise.all(RG.map(async ([id, B]) => {
      try { return [B, await getJSON(`${B}runs/${run}/manifest.json`)]; } catch (e) { return null; }
    }));
    if (stale()) return;
    for (const x of regs) {
      if (!x) continue;
      const [B, m] = x;
      {
        for (const [k, d] of Object.entries(m.domains || {})) {
          if (!S.man) S.man = { ...m, domains: {} };
          S.man.domains[k] = { ...d, base: B, proj: m.proj };
        }
        if (S.man) S.man.products = { ...(m.products || {}), ...(S.man.products || {}) };
      }
    }
    if (S.man) {   // the Kingdom at 3 km: the western highlands and the regional grids drawn together
      const dxOf = (d) => d.dx || (d.points && d.points.dx) || 0;
      for (const [k, d] of Object.entries(S.man.domains)) if (dxOf(d) > 5000 || k === "d01" || k === "sa") delete S.man.domains[k];
      const mem = ["d02", ...REGIONS.map((r) => r[0])].filter((k) => S.man.domains[k] && dxOf(S.man.domains[k]) === 3000);
      delete S.man.domains.k3;
      if (mem.length >= 2) {
        const ds = mem.map((k) => S.man.domains[k]);
        const hours = [...new Set(ds.flatMap((d) => d.hours || []))].sort((a, b) => a - b);
        const days = {};
        ds.forEach((d) => (d.days || []).forEach((x) => { days[x.date] = Math.max(days[x.date] || 0, x.hours); }));
        const b = ds.map((d) => d.bounds).filter(Boolean);
        const k3 = { name: "المملكة", res: "٣ كم", members: mem, hours, days: Object.keys(days).sort().map((k) => ({ date: k, hours: days[k] })),
          products: [...new Set(ds.flatMap((d) => d.products || []))],
          bounds: [[Math.min(...b.map((x) => x[0][0])), Math.min(...b.map((x) => x[0][1]))], [Math.max(...b.map((x) => x[1][0])), Math.max(...b.map((x) => x[1][1]))]] };
        for (const p of SINGLE) { const r = ds.find((d) => d[p]); if (r) k3[p] = r[p]; }
        S.man.domains.k3 = k3;
      }
    }
    if (S.meteo && S.meteo.cities) S.meteo.cities = S.meteo.cities.filter((c) => CITY_KEEP.has(c.id));
    if (S.man) for (const k of Object.keys(NEWPAL)) {   // old banded humidity/instability runs: show the new scale
      const p = S.man.products[k];
      if (p && p.legend && p.legend.bands) { p.oldLegend = p.legend; p.legend = newLegend(k); }
    }
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
    $("runState").textContent = st;
    drawProducts(); drawLegend();
    if (first && !LX.on) { S.dom = domFor(S.prod); buildFrames(false); S.idx = 0; }
    setDomain(S.dom, first);
    drawCityMarkers();
    if (!$("p-cities").hidden) drawCities();
  }

  async function refreshRuns(first) {
    let idx;
    try { idx = await getJSON(DATA + "runs.json"); } catch (e) { idx = { runs: [] }; }
    // evening (12Z) runs only: the daytime run was removed (Fahad, 15 Nov 2026); the morning tab lists its own 00Z runs (Fahad, 17 Nov 2026)
    S.runs = (idx.runs || []).filter((r) => !String(r.run).endsWith("00"));
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
  // the map options panel: one button, three choices; closes after a choice or a tap elsewhere
  function mapMenu(open) {
    $("mapMenu").hidden = !open; $("mapMenuBtn").setAttribute("aria-expanded", open ? "true" : "false");
  }
  $("mapMenuBtn").addEventListener("click", (e) => { e.stopPropagation(); mapMenu($("mapMenu").hidden); });
  $("mapMenu").addEventListener("click", (e) => e.stopPropagation());
  for (const id of ["runSelect", "prodSelect", "modelSelect"]) $(id).addEventListener("change", () => setTimeout(() => mapMenu(false), 150));
  document.addEventListener("click", () => { if (!$("mapMenu").hidden) mapMenu(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") mapMenu(false); });

  // GFS / ECMWF: the same model and grids, driven by either; switching reloads the newest run of the chosen one
  function drawModelTabs() {
    const sel = $("modelSelect"); sel.value = MODEL;
    $("modelTxt").textContent = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent : "";
  }
  $("modelSelect").onchange = async (e) => {
    const b = { dataset: { m: e.target.value } };   // one pill for the three runs (Fahad 17 Nov 2026)
    if (b.dataset.m === MODEL) return;
    // keep the same valid time (or day) on the map, so the two drivers compare at a glance
    const f0 = S.frames[S.idx], t0 = f0 && f0.h != null && S.man ? Date.parse(S.man.init) + f0.h * 3600e3 : null;
    stop(); useModel(b.dataset.m); store.set("model", MODEL); drawModelTabs(); setLogLinks();
    S.run = null; S.man = null; S.meteo = null; S.points = {};
    clearOverlay();
    await refreshRuns(true);
    if (!S.runs.length) $("mapEmptyMsg").textContent = MODEL === "ec"
      ? "تشغيل النموذج الأوروبي يبدأ قرابة ١٠:٤٥ مساءً بتوقيت مكة، وتظهر خرائطه هنا ساعة بساعة حتى يكتمل قرابة ٥:٣٠ فجرًا."
      : "النظام قيد التجهيز، ويمكنك متابعة التقدم من تبويب الحالة.";
    if (S.man && S.frames.length && f0) {
      let k = -1;
      if (t0 != null) k = S.frames.findIndex((f) => f.h != null && Date.parse(S.man.init) + f.h * 3600e3 === t0);
      else if (f0.date) k = S.frames.findIndex((f) => f.date === f0.date);
      if (k >= 0) { S.idx = k; showFrame(); }
    }
    if (!$("p-status").hidden) refreshStatus();
  };
  drawModelTabs();

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
  // the status tab always shows both evening runs (American then European), whichever model tab is selected on the map
  function statusBlock(s, title) {
    const [ph, cls] = PH[s.phase] || [s.phase, "wait"];
    const steps = (s.steps || []).map((x) => {
      const [lab, c] = STATE[x.state] || [x.state, "wait"];
      const note = x.note && !/-\d/.test(x.note) ? arDigits(x.note) : "";
      return `<li><span>${x.label}${note ? ` <small>${note}</small>` : ""}</span>
        <span><small>${x.state === "running" || x.state === "done" ? dur(x.started, x.ended) : ""}</small> <span class="pill ${c}">${lab}</span></span></li>`;
    }).join("");
    const what = (s.cycle || "").length !== 10 ? "التثبيت" : `الدورة: ${runName(s.cycle)}`;
    return `<h3>${title}</h3><div class="phase"><span class="pill ${cls}">${ph}</span></div>
      <div>${arDigits((s.message || "").replace(/\s*\d{10}\s*/, " "))}</div><div class="muted" style="font-size:.8rem">${what} · آخر تحديث ${ago(s.updated)}</div>
      <ul class="steps">${steps}</ul>`;
  }
  async function refreshStatus() {
    const GFS_DATA = DATA0, EC_DATA = DATA0.replace("/model-data/", "/model-data-ec/");
    const [g, e] = await Promise.all([GFS_DATA, EC_DATA].map((d) => getJSON(d + "status.json").catch(() => null)));
    const s = MODEL === "ec" ? e : g;
    if (!g && !e) { $("statusCard").innerHTML = `<p class="muted">لم تصل حالة الخادم بعد.</p>`; return; }
    const running = [g, e].some((x) => x && (x.phase === "cycle" || x.phase === "install"));
    const err = [g, e].some((x) => x && x.phase === "error");
    const cls = running ? "run" : err ? "err" : "ok";
    $("statusDot").className = "dot " + cls; $("menuDot").className = "dot " + cls;
    $("statusCard").innerHTML = [[g, "تشغيل النموذج الأمريكي"], [e, "تشغيل النموذج الأوروبي"]]
      .map(([x, t]) => x ? statusBlock(x, t) : `<h3>${t}</h3><p class="muted">لم تصل حالته بعد.</p>`)
      .join(`<div style="height:14px"></div>`);
    if (!s) return;
    const [ph] = PH[s.phase] || [s.phase];
    // each cycle runs in two parts, each logged on its own: one row per cycle with both parts' minutes; evening (12Z) cycles only
    const hist = [];
    for (const h of s.history || []) {
      if (!/12$/.test(h.cycle || "")) continue;
      const o = hist.find((x) => x.cycle === h.cycle);
      if (o) { o.minutes += h.minutes || 0; o.ok = o.ok && h.ok; } else hist.push({ cycle: h.cycle, ok: h.ok, minutes: h.minutes || 0 });
    }
    const mins = (m) => (m < 60 ? `${num(m)} د` : `${num(Math.floor(m / 60))} س ${num(m % 60)} د`);
    $("historyList").innerHTML = hist.length ? hist.map((h) => `<div class="hist">
      <span>${runName(h.cycle)}</span><span class="pill ${h.ok ? "ok" : "err"}">${h.ok ? "اكتملت" : "ناقصة"}</span>
      <span class="muted">${mins(h.minutes)}</span></div>`).join("")
      : `<p class="muted">لا دورات مكتملة بعد.</p>`;
    if (!S.runs.length) $("mapEmptyMsg").textContent = `${ph}${s.message ? ": " + s.message : ""}. التفاصيل في تبويب الحالة.`;
  }


  // ------------------------------------------------------------------ MJO and warm/cold events
  const CL = window.SWRF_CLIMATE || DATA0.replace("/model-data/", "/climate-data/");
  const M = { st: null, map: null, layer: "wc", day: 0, img: null, vec: null, vecs: null, loaded: 0 };
  const AR_AREA = { 1: "أفريقيا ونصف الكرة الغربي", 2: "غرب المحيط الهندي", 3: "شرق المحيط الهندي", 4: "القارة البحرية (إندونيسيا)",
                    5: "القارة البحرية (إندونيسيا)", 6: "غرب المحيط الهادئ", 7: "غرب المحيط الهادئ", 8: "نصف الكرة الغربي وأفريقيا" };
  const fmtDayD = new Intl.DateTimeFormat(LOC, { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" });
  const fmtDM = new Intl.DateTimeFormat(LOC, { timeZone: "UTC", day: "numeric" });
  const dOf = (s) => new Date(s + "T00:00:00Z");
  const strength = (a) => (a < 1 ? "ضعيف" : a < 1.5 ? "متوسط" : a < 2.5 ? "قوي" : "قوي جدًا");
  // the maps come from the evening run, so their first day is yesterday by the time the page is read (17 Nov 2026:
  // the page called the 16th "today" all day of the 17th). Days are named against today's date in Makkah.
  const todayISO = () => new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 10);
  const dayDiff = (d) => Math.round((dOf(d) - dOf(todayISO())) / 86400e3);
  function dayLab(d) {
    const k = dayDiff(d);
    const rel = k === 0 ? "اليوم" : k === -1 ? "أمس" : k < -1 ? (k === -2 ? "قبل يومين" : `قبل ${num(-k)} ${-k <= 10 ? "أيام" : "يومًا"}`) : after(k);
    return `${rel}: ${fmtDayD.format(dOf(d))}`;
  }
  const todayIdx = (days) => Math.max(0, (days || []).indexOf(todayISO()));

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
        $("mjoNow").innerHTML = `<p class="muted">لم تُحسب بيانات التذبذب بعد. تتحدث كل ليلة عند منتصف الليل بتوقيت مكة.</p>`; return;
      }
      mjoText(); mjoPhase(); mjoPwTable();
    }
    mjoMap(); pwMapCard(); olrCard(); setTimeout(dayBadges, 0); geoTapSetup(); ksaCard(); kwCard(); tcCard(); rsCard(); tpCard(); rivCard(); rstCard(); waveCard(); mjofCard(); twCard(); beltCard();
    mjoSec(M.sec || (() => { try { return localStorage.getItem("mjoSec"); } catch (e) { return null; } })() || "report", true);
  }

  // section tab bar (Fahad 17 Nov 2026): one section at a time instead of one long page
  function mjoSec(k, keepScroll) {
    setTimeout(() => document.querySelectorAll('#p-mjo span[id$="DayLabel"]').forEach((l) => l._badge && l._badge()), 60);
    const bar = $("mjoTabs"); if (!bar || !bar.querySelector(`[data-s="${k}"]`)) k = "report";
    M.sec = k;
    try { localStorage.setItem("mjoSec", k); } catch (e) {}
    bar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.s === k));
    document.querySelectorAll("#p-mjo [data-sec]").forEach((c) => c.classList.toggle("sec-off", c.dataset.sec !== k));
    const on = bar.querySelector("button.on"); if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "center" });
    if (!keepScroll) $("p-mjo").scrollTop = 0;
    if (k === "waves") ["twDay", "waveDay"].forEach((id) => { const el = $(id); if (el && el.oninput) el.dispatchEvent(new Event("input")); });  // neighbours of the shown day
  }
  if ($("mjoTabs")) $("mjoTabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-s]"); if (b) mjoSec(b.dataset.s); });

  function mjoText() {
    const st = M.st, obsNow = st.rmm_now;
    const fcToday = (st.rmm_fc || []).find((f) => f.d === todayISO());
    const now = fcToday || st.rmm_today || st.rmm_now;
    const r = st.report;
    $("mjoReport").hidden = !r;
    const para = (l, i, sec) => /^(المصادر|الخلاصة)/.test(l) ? `<p class="${l.startsWith("المصادر") ? "src" : "sum"}">${l}</p>`
      : `<p${i === 0 && sec === 0 ? ' class="lead"' : ""}>${l}</p>`;
    const rainTable = (rows) => {
      if (!rows || !rows.length) return "";
      const cell = (xs) => xs.length ? xs.map((x) => `<span>${x}</span>`).join("") : `<i>—</i>`;
      let t = `<div class="rtab-wrap"><table class="rtab"><colgroup><col class="r"><col class="d"><col class="w"><col class="c"><col class="c"><col class="c"></colgroup><thead><tr><th>المنطقة</th><th>اليوم</th><th>النافذة الزمنية</th>` +
        `<th class="h">غزير</th><th class="m">متوسط</th><th class="l">خفيف</th></tr></thead><tbody>`;
      rows.forEach((x, i) => {
        const first = i === 0 || rows[i - 1].region !== x.region;
        let span = 1;
        if (first) while (i + span < rows.length && rows[i + span].region === x.region) span++;
        t += `<tr class="${first ? "first" : ""}">` + (first ? `<th scope="row" rowspan="${span}">${x.region}</th>` : "") +
          `<td>${x.day}</td><td>${x.window}</td><td class="h">${cell(x.heavy)}</td><td class="m">${cell(x.moderate)}</td><td class="l">${cell(x.light)}</td></tr>`;
      });
      return t + "</tbody></table></div>";
    };
    // the report in Fahad's layout (17 Nov 2026, report2.py): sub-headings, paragraphs, lists and small tables
    const blocksHTML = (bs) => bs.map((b) => b.h ? `<h4 class="rsub">${b.h}</h4>` : b.p ? `<p>${b.p}</p>`
      : b.note ? `<p class="src">${b.note}</p>` : b.ul ? `<ul class="rlist">${b.ul.map((x) => `<li>${x}</li>`).join("")}</ul>`
      : b.table ? `<div class="rtab-wrap"><table class="rgen"><thead><tr>${b.table.head.map((x) => `<th>${x}</th>`).join("")}</tr></thead><tbody>${
          b.table.rows.map((r) => `<tr>${r.map((x, i) => i ? `<td>${x}</td>` : `<th scope="row">${x}</th>`).join("")}</tr>`).join("")}</tbody></table></div>` : "").join("");
    const secHTML = (s, k) => {
      if (s.blocks) return blocksHTML(s.blocks);
      if (!s.table || !s.table.length) return s.lines.map((l, i) => para(l, i, k)).join("");
      // the summary first, then the table, then region by region in words
      const j = s.lines.findIndex((l) => l.startsWith("منطقة "));
      const head = j < 0 ? s.lines : s.lines.slice(0, j), rest = j < 0 ? [] : s.lines.slice(j);
      return head.map((l, i) => para(l, i, k)).join("") + rainTable(s.table) +
        (rest.length ? `<h4 class="rsub">التفصيل منطقة منطقة</h4>` + rest.map((l) => para(l, 1, k)).join("") : "");
    };
    if (r && r.sections) r.sections = r.sections.filter((s) => s.kind !== "rain_noon");  // no noon update any more
    if (r) $("mjoReport").innerHTML = (r.v === 2 ? `<div class="rbrand"><b>${r.brand}</b><span dir="ltr">${r.credit}</span><span>${r.date}</span></div>`
      : `<h3>${r.title}</h3>`) + (r.sections && r.sections.length
      ? r.sections.map((s, k) => `<details class="rsec${s.kind ? " " + s.kind : ""}" open><summary>${s.heading}</summary>${secHTML(s, k)}</details>`).join("")
      : (r.lines || []).map((l) => `<p>${l}</p>`).join("")) +
      `<p class="hint">يصدر التقرير مرة كل يوم عند منتصف الليل بتوقيت مكة من تشغيل المساء، ومعه خرائط هذه الصفحة${r.updated || r.issued ? ` · آخر تحديث ${fmtStamp.format(new Date(r.updated || r.issued))}` : ""}.</p>`;
    let html = "";
    if (now) {
      // phase 2 is "weakly supportive" as in the report: the 25-season study found it near normal (16 Nov 2026)
      const wet = [1, 7, 8].includes(now.phase), weak = now.phase === 2, season = st.wet_season;
      html += `<div class="mjo-big"><span>التذبذب الآن في <b>الطور ${num(now.phase)}</b></span><span>بشدة ${num(now.amp, 1)} (${strength(now.amp)})</span></div>
        <div class="mjo-row"><span>الحمل العميق المصاحب</span><span>${AR_AREA[now.phase]}</span></div>
        <div class="mjo-row"><span>أثره على المملكة</span><span class="${season ? (wet || weak ? "wet" : "dry") : ""}">${
          now.amp < 1 ? "ضعيف التأثير لأن التذبذب ضعيف" : !season ? "خارج موسم الأمطار، تأثيره محدود" : wet ? "طور رطب: يدعم الأمطار"
          : weak ? "داعم ضعيف: أثر الطور ٢ قريب من المعتاد، والأقوى الطوران ٨ و١" : "طور جاف: يكبت الأمطار"}</span></div>
        <div class="mjo-row"><span>${now === st.rmm_now ? "آخر رصد" : now.d === todayISO() ? "اليوم (تقدير من جي إف إس)" : "تقدير جي إف إس"}</span><span>${fmtDayD.format(dOf(now.d))}</span></div>` +
        (st.rmm_today && obsNow ? `<div class="mjo-row"><span>آخر رصد رسمي</span><span>${fmtDayD.format(dOf(obsNow.d))}: الطور ${num(obsNow.phase)} بشدة ${num(obsNow.amp, 1)}</span></div>` : "");
    }
    html += `<div class="mjo-row"><span>الحدث الدافئ الآن</span><span>${st.warm.region}</span></div>
      <div class="mjo-row"><span>الحدث البارد الآن</span><span>${st.cold.region}</span></div>`;
    if (st.rmm_fc && st.rmm_fc.length) {
      const i0 = Math.max(0, st.rmm_fc.findIndex((x) => x.d === now.d));
      const f = st.rmm_fc[Math.min(i0 + 10, st.rmm_fc.length - 1)];
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

  // Arabia's precipitable water, moved from the warm-event card to «الرطوبة» under the table (Fahad, 20 Nov 2026)
  function pwMapCard() {
    const st = M.st, days = st.days || [];
    const show = (k) => {
      const url = `${CL}fig/pw_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
      $("pwFig").src = url; $("pwFigLink").href = url;
      $("pwDayLabel").textContent = days[k] ? dayLab(days[k]) : "";
      const lg = (st.figs || {}).pw;
      if (!lg) { $("pwLegend").innerHTML = ""; return; }
      const grad = lg.stops.map((x) => `${x.c} ${(x.p * 100).toFixed(1)}%`).join(", ");
      const ticks = lg.ticks.map((v) => `<span style="left:${((v - lg.vmin) / (lg.vmax - lg.vmin) * 100).toFixed(1)}%">${num(v)}</span>`).join("");
      $("pwLegend").innerHTML = `<div class="legend-title"><span>${lg.label}</span><span>${lg.unit}</span></div>
        <div class="legend-bar" style="background:linear-gradient(to right, ${grad})"></div><div class="legend-ticks">${ticks}</div>`;
    };
    $("pwDay").max = Math.max(0, days.length - 1);
    if (!pwMapCard.done) { $("pwDay").value = todayIdx(days); pwMapCard.done = true; }
    $("pwDay").oninput = (e) => show(+e.target.value);
    show(+$("pwDay").value || 0);
  }

  // the day and date written over every map that has a day slider, kept in step with the slider and the play button
  // (Fahad, 20 Nov 2026: «أي خريطة فيها تشغيل أيام في اعلى الصورة اكتب التاريخ واليوم»)
  // the title box over each day-slider map (Fahad, 20 Nov 2026: «التواريخ في الخرائط والأيام مع شرح بسيط أبيها
  // بالطريقة ذي»): 20 Nov morning: not over the map but a strip above it, like the drawn convection map (title with the day and
  // date, then one short line); it follows the slider and the play button. Maps that draw their own title are left alone.
  const MAP_BOX = {
    twDayLabel: () => ["موجات كلفن وعائلة روسبي عند ٢٠٠ هكتوباسكال — النموذج الأمريكي", "الأزرق فوق المملكة يدعم الأمطار، والأحمر يكبتها"],
    beltDayLabel: () => ["اللوحة الاستوائية الشاملة — النموذج الأمريكي", "حول الأرض من ٣٥ جنوبًا إلى ٣٥ شمالًا، والخطوط مراكز الموجات"],
    mjoDayLabel: () => (M.layer === "lw" || M.layer === "lwd") ? null
      : ["الحدث الدافئ والبارد عند ٢٠٠ هكتوباسكال — النموذج الأمريكي", "الأحمر حدث دافئ يدعم الحمل العميق، والأزرق حدث بارد يكبته"],
    mjofDayLabel: () => [($("mjofLayer").querySelector(".on") || {}).dataset?.l === "mjop"
      ? "الأمطار المرتبطة بالتذبذب — النموذج الأمريكي" : "مكوّن التذبذب المعزول عند ٨٠٠ هكتوباسكال — النموذج الأمريكي",
      "الأزرق يدعم الأمطار والأحمر يكبتها، فانظر إلى لون المملكة"],
    waveDayLabel: () => ["موجات روسبي عند ٥٠٠ هكتوباسكال — النموذج الأمريكي", "الأزرق أخدود منخفض والأحمر مرتفع، والأسهم اتجاه الرياح"],
    rivDayLabel: () => ["النهر الجوي — النموذج الأوروبي", ""],
    rstDayLabel: () => ["العواصف الرعدية على مسار النهر — النموذج الأوروبي", ""],
    pwDayLabel: () => [`رطوبة الجزيرة العربية — النموذج ${M.st && M.st.pw_model === "ecmwf" ? "الأوروبي" : "الأمريكي"}`, "الماء القابل للهطول نسبة إلى معدله: الأخضر والأزرق أرطب من المعتاد"],
  };
  function dayBadges() {
    document.querySelectorAll('#p-mjo span[id$="DayLabel"]').forEach((lab) => {
      const spec = MAP_BOX[lab.id];
      const card = lab.closest(".card");
      if (!spec || !card || card.dataset.badge) return;
      let fig = card.querySelector(".figwrap, #beltPanels");
      if (!fig) return;
      card.dataset.badge = "1";
      const b = document.createElement("div");
      b.className = "map-head";
      b.dir = "rtl";
      fig.parentNode.insertBefore(b, fig);
      const put = () => {
        const t = (lab.textContent || "").trim();
        const sp = spec();
        b.hidden = !t || !sp;
        if (b.hidden) { lab.style.display = ""; return; }
        // only what the card does not already say (Fahad, 20 Nov 2026: «لا تعيد تكرار ما هو موجود»): the card keeps
        // its title and legend, the strip gives the day, the date and the model
        const mdl = (sp[0].split(" — ")[1] || "").trim();
        b.innerHTML = `<b>${t}</b>${mdl ? `<small>${mdl}</small>` : ""}`;
        lab.style.display = "none";      // the strip above the map says it: no second copy under the slider
      };
      new MutationObserver(put).observe(lab, { childList: true, characterData: true, subtree: true });
      card.addEventListener("click", () => setTimeout(put, 50));
      put();
      lab._badge = put;
    });
  }

  // tap any map of the page for its latitude and longitude (Fahad, 20 Nov 2026: «واي خريطة اضغط على اي جزء منها يظهر
  // لي خطوط الطول والعرض»): mjo.json "geo" gives each picture's map panels (figure fractions + lon/lat extent); the
  // Kingdom maps keep their own tap (.ksa-map). A tap shows a pin and a box under the map with a copy button and a link
  // to the full picture.
  function geoTapSetup() {
    if (geoTapSetup.done) return;
    geoTapSetup.done = true;
    $("p-mjo").addEventListener("click", (ev) => {
      const img = ev.target.closest("img");
      if (!img || img.closest(".ksa-map")) return;
      const G = Object.assign({}, (M.st && M.st.geo) || {});
      const RX = M.st && M.st.rsflow && M.st.rsflow.extent;   // the Red Sea flow map fills its picture edge to edge
      if (RX && !G["rsf.png"]) G["rsf.png"] = [[0, 1, 0, 1, RX[0], RX[1], RX[2], RX[3]]];
      const file = (img.currentSrc || img.src || "").split("?")[0].split("/").pop() || "";
      const pans = G[file.replace(/(_\d+)+(?=\.png$)/, "")];
      if (!pans) return;
      const r = img.getBoundingClientRect();
      const fx = (ev.clientX - r.left) / r.width, fy = 1 - (ev.clientY - r.top) / r.height;
      const p = pans.find((q) => fx >= q[0] && fx <= q[1] && fy >= q[2] && fy <= q[3]);
      const a = img.closest("a");
      if (a) ev.preventDefault();
      const card = img.closest(".card");
      if (!card) return;
      let box = card.querySelector(".geo-coord");
      if (!box) {
        box = document.createElement("div");
        box.className = "ksa-coord geo-coord";
        const anchor = card.querySelector(".mjo-time") || card.lastElementChild;
        card.insertBefore(box, anchor);
      }
      let pin = card.querySelector(".geo-pin");
      if (!p) { box.hidden = true; if (pin) pin.hidden = true; return; }
      let lon = p[4] + (fx - p[0]) / (p[1] - p[0]) * (p[5] - p[4]);
      const lat = p[6] + (fy - p[2]) / (p[3] - p[2]) * (p[7] - p[6]);
      lon = ((lon + 540) % 360) - 180;
      const ns = lat >= 0 ? "شمالًا" : "جنوبًا", ew = lon >= 0 ? "شرقًا" : "غربًا";
      const txt = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
      box.hidden = false;
      box.innerHTML = `<span>خط العرض <b>${AR_DIG(Math.abs(lat).toFixed(2))}</b> ${ns}، خط الطول <b>${AR_DIG(Math.abs(lon).toFixed(2))}</b> ${ew}`
        + (a ? ` · <a href="${a.href}" target="_blank" rel="noopener">الصورة كاملة</a>` : "") + `</span><button type="button">نسخ</button>`;
      box.querySelector("button").onclick = async (e2) => {
        try { await navigator.clipboard.writeText(txt); e2.target.textContent = "نُسخت"; } catch (_) { e2.target.textContent = "تعذّر النسخ"; }
        setTimeout(() => { e2.target.textContent = "نسخ"; }, 1500);
      };
      // the pin, on the picture's own box (it scrolls with a wide map)
      const host = img.parentElement;
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      if (!pin || pin.parentElement !== host) {
        if (pin) pin.remove();
        pin = document.createElement("i");
        pin.className = "ksa-pin geo-pin";
        host.appendChild(pin);
      }
      const hr = host.getBoundingClientRect();
      pin.hidden = false;
      pin.style.left = (ev.clientX - hr.left) + "px";
      pin.style.top = (ev.clientY - hr.top) + "px";
    });
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
    if (!M.dayInit) { M.dayInit = true; M.day = todayIdx(M.st.days); $("mjoDay").value = M.day; }
    mjoShow();
  }

  // the Kingdom maps (Fahad, 17 Nov 2026): humidity at 700 and 500 hPa, where the surface winds meet with the surface
  // lows, and the 500 hPa temperature; GFS alone, 12 UTC (3 PM Makkah) of each day
  const KSA_HINT = {
    krh7: "الرطوبة النسبية عند ٧٠٠ هكتوباسكال (نحو ٣ كم فوق سطح البحر) من توقع جي إف إس. الأخضر رطوبة تكفي لنمو السحب الركامية (٦٠٪ فأكثر)، والبني هواء جاف يُضعف السحب أثناء نموها. الخطوط عند ٥٠ و٧٠ و٩٠٪.",
    krh5: "الرطوبة النسبية عند ٥٠٠ هكتوباسكال (نحو ٥٫٥ كم). رطوبة هذه الطبقة تسمح للسحاب بالنمو إلى ارتفاع كبير، وتُظهر السحب المتوسطة والعالية التي تصحب الأخاديد والمنخفضات. الخطوط عند ٥٠ و٧٠ و٩٠٪.",
    kconv: "الألوان مواضع تصادم الرياح السطحية (تقارب الرياح عند ١٠ أمتار بعد تنعيم نحو ٤٠ كم)، وفيها يُدفع الهواء إلى الصعود. الخطوط البيضاء اتجاه الرياح، والخطوط الداكنة الضغط عند سطح البحر كل هكتوباسكالين. «منخفض» تحيط به خطوط ضغط مغلقة، و«منخفض ضعيف» أقل من ذلك. لا يُعلَّم منخفض فوق أرض أعلى من ١٠٠٠ متر، لأن الضغط هناك محسوب لا مقاس. الخط الأزرق المتقطع أخدود البحر الأحمر: لسان الضغط المنخفض الممتد من السودان وجنوب البحر شمالًا، يحمل الرطوبة الجنوبية نحو جدة ومكة، والمثلث آخر امتداده. يُحكم عليه بمتوسط ضغط الثالثة عصرًا والثالثة فجرًا، لأن حرارة العصر تخفض الضغط فوق اليابسة فتخفيه.",
    kt5: "درجة الحرارة عند ٥٠٠ هكتوباسكال (نحو ٥٫٥ كم). البرودة في الأعلى (الأزرق) مع دفء السطح تزيد عدم الاستقرار، والدفء (البرتقالي والأحمر) يكبح نمو السحب. الخطوط كل درجة، والأعرض كل درجتين.",
  };
  // names over the Kingdom maps, written by the page at a constant small size (Fahad, 18 Nov 2026: the names drawn in the
  // pictures grew big and heavy when zoomed, and some sat away from their dots). [name, lat, lon, side, tier]; tier 2
  // shows from zoom 1.5, tier 3 from zoom 2. Seas and countries are faint and dotless.
  const KMAP_NAMES = [
    ["الرياض", 24.71, 46.68, "n", 1], ["جدة", 21.54, 39.17, "w", 1], ["مكة", 21.42, 39.83, "n", 1], ["المدينة", 24.47, 39.61, "n", 1],
    ["الدمام", 26.43, 50.10, "w", 1], ["أبها", 18.22, 42.50, "e", 1], ["جازان", 16.89, 42.55, "w", 1], ["تبوك", 28.38, 36.57, "n", 1],
    ["حائل", 27.52, 41.69, "n", 1], ["سكاكا", 29.97, 40.21, "n", 1],
    ["الطائف", 21.27, 40.42, "e", 2], ["بريدة", 26.33, 43.97, "n", 2], ["نجران", 17.49, 44.13, "e", 2], ["الباحة", 20.01, 41.47, "e", 2],
    ["ينبع", 24.09, 38.06, "w", 2], ["الأحساء", 25.38, 49.59, "s", 2], ["وادي الدواسر", 20.47, 44.78, "e", 2], ["عرعر", 30.98, 41.04, "n", 2],
    ["القنفذة", 19.13, 41.08, "w", 3], ["الليث", 20.15, 40.27, "w", 3], ["رابغ", 22.80, 39.03, "w", 3], ["العلا", 26.60, 37.92, "e", 3],
    ["الوجه", 26.23, 36.47, "w", 3], ["أملج", 25.05, 37.27, "w", 3], ["بيشة", 19.98, 42.60, "e", 3], ["شرورة", 17.47, 47.11, "n", 3],
    ["الخرج", 24.15, 47.30, "s", 3], ["الدوادمي", 24.50, 44.39, "n", 3], ["حفر الباطن", 28.43, 45.97, "n", 3], ["الجبيل", 27.00, 49.66, "w", 3],
    ["القريات", 31.33, 37.34, "n", 3], ["خميس مشيط", 18.30, 42.73, "s", 3],
    ["البحر الأحمر", 19.6, 38.5, "c", 0], ["الخليج العربي", 27.3, 51.4, "c", 0], ["اليمن", 15.6, 46.5, "c", 0], ["السودان", 16.5, 34.6, "c", 0],
    ["العراق", 32.4, 44.2, "c", 0], ["الأردن", 31.0, 36.4, "c", 0], ["الإمارات", 23.5, 54.3, "c", 0], ["إيران", 31.5, 53.0, "c", 0],
  ];
  function kmapNames(inner, ext) {
    if (inner.querySelector(".kmap-names")) return;
    const [w, e, s, n] = ext, box = document.createElement("div"); box.className = "kmap-names";
    for (const [name, lat, lon, side, tier] of KMAP_NAMES) {
      if (lon < w || lon > e || lat < s || lat > n) continue;
      const el = document.createElement("span");
      el.className = `kn kn-${side} t${tier}`; el.style.left = ((lon - w) / (e - w) * 100).toFixed(3) + "%"; el.style.top = ((n - lat) / (n - s) * 100).toFixed(3) + "%";
      el.innerHTML = (side === "c" ? "" : "<i></i>") + `<b>${name}</b>`;
      box.appendChild(el);
    }
    inner.appendChild(box); inner.dataset.z = 0;
  }
  // zoom buttons, and the coordinates of a tapped point (Fahad, 17 Nov 2026). The map is a plain latitude-longitude
  // picture of the extent [west, east, south, north], edge to edge, so a point's place in the picture gives its position.
  const AR_DIG = (t) => String(t).replace(/\d/g, (c) => "٠١٢٣٤٥٦٧٨٩"[c]).replace(".", "٫");
  // the Kingdom maps come from ECMWF since 19 Nov 2026 (Fahad), drawn in the card style: names, title, explanation and
  // legend are inside the picture, so the page adds no names or legend of its own over them (model set in mjo.json)
  const MODEL_AR = (m) => m === "gfs" ? "النموذج الأمريكي" : "النموذج الأوروبي";
  const CARDED = (o) => !!(o && o.model);
  const fixModel = (t, o) => !CARDED(o) ? t : t.replace(/توقع جي إف إس|النموذج الأمريكي/g, MODEL_AR(o.model));
  function ksaZoomSetup(ext) {
    if (ksaZoomSetup.done) { ksaZoomSetup.ext = ext; return; }
    ksaZoomSetup.done = true; ksaZoomSetup.ext = ext;
    const LV = [1, 1.5, 2, 3];
    let z = 0, pt = null;
    const sc = $("ksaScroll"), inner = $("ksaInner"), img = $("ksaFig");
    const zoom = (d) => {
      const nz = Math.max(0, Math.min(LV.length - 1, z + d)); if (nz === z) return;
      const cx = (sc.scrollLeft + sc.clientWidth / 2) / sc.scrollWidth, cy = (sc.scrollTop + sc.clientHeight / 2) / sc.scrollHeight;
      // the box keeps the map's height at zoom 1, so a zoomed map scrolls both ways inside it
      if (z === 0) sc.style.height = sc.clientHeight + "px";
      z = nz; inner.style.width = LV[z] * 100 + "%"; inner.dataset.z = z;
      if (z === 0) sc.style.height = "";
      // keep the tapped point (or the middle) in view
      const fx = pt ? pt[0] : cx, fy = pt ? pt[1] : cy;
      sc.scrollLeft = fx * sc.scrollWidth - sc.clientWidth / 2; sc.scrollTop = fy * sc.scrollHeight - sc.clientHeight / 2;
      $("ksaIn").disabled = z === LV.length - 1; $("ksaOut").disabled = z === 0;
    };
    $("ksaIn").onclick = () => zoom(1); $("ksaOut").onclick = () => zoom(-1);
    img.addEventListener("click", (ev) => {
      const r = img.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
      if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
      pt = [fx, fy];
      const pin = $("ksaPin"); pin.hidden = false; pin.style.left = fx * 100 + "%"; pin.style.top = fy * 100 + "%";
      ksaZoomSetup.pt = pt; ksaTapText();
    });
  }
  // a value of the 0.5 deg grids (ksa_vals.bin, ksa_wind.bin) at a point, bilinear
  function kGridAt(G, D, k, c, lat, lon) {
    if (!G || !D) return null;
    const fy = (G.lat0 - lat) / G.d, fx = (lon - G.lon0) / G.d, nc = G.order.length;
    if (fy < 0 || fx < 0 || fy > G.ny - 1 || fx > G.nx - 1) return null;
    const j = Math.min(G.ny - 2, Math.floor(fy)), i = Math.min(G.nx - 2, Math.floor(fx)), ty = fy - j, tx = fx - i;
    const at = (jj, ii) => D[((k * nc + c) * G.ny + jj) * G.nx + ii] * G.scale;
    return (at(j, i) * (1 - tx) + at(j, i + 1) * tx) * (1 - ty) + (at(j + 1, i) * (1 - tx) + at(j + 1, i + 1) * tx) * ty;
  }
  function ksaTapText() {
    const pt = ksaZoomSetup.pt; if (!pt) return;
    const [w, e, s, n] = ksaZoomSetup.ext, lon = w + pt[0] * (e - w), lat = n - pt[1] * (n - s);
    const K = M.st.ksa, k = +$("ksaDay").value || 0, G = K && K.vals;
    const v = (key) => G ? kGridAt(G, KSAV.data, k, G.order.indexOf(key), lat, lon) : null;
    const rh7 = v("rh7"), rh5 = v("rh5"), t5 = v("t5");
    const pc = (x) => AR_DIG(Math.round(Math.max(0, Math.min(100, x)))) + "٪";
    const vals = rh7 == null ? "" : `<div>الرطوبة: <b>${pc(rh7)}</b> عند ٧٠٠، و<b>${pc(rh5)}</b> عند ٥٠٠</div>
      <div>الحرارة عند ٥٠٠: <b>${t5 < 0 ? "−" : ""}${AR_DIG(Math.abs(Math.round(t5)))}° م</b></div>`;
    const txt = `${lat.toFixed(4)}, ${lon.toFixed(4)}`, box = $("ksaCoord"); box.hidden = false;
    box.innerHTML = `<span><div>خط العرض <b>${AR_DIG(lat.toFixed(2))}</b> شمالًا، خط الطول <b>${AR_DIG(lon.toFixed(2))}</b> شرقًا</div>${vals}</span><button type="button">نسخ</button>`;
    box.querySelector("button").onclick = async (e2) => {
      try { await navigator.clipboard.writeText(txt); e2.target.textContent = "نُسخت"; } catch (_) { e2.target.textContent = "تعذّر النسخ"; }
      setTimeout(() => { e2.target.textContent = "نسخ"; }, 1500);
    };
  }
  const KSAV = { data: null, v: null };
  function ksaCard() {
    const st = M.st, K = st.ksa;
    $("ksaCard").hidden = !(K && K.days && K.days.length);
    if ($("ksaCard").hidden) return;
    let lay = M.ksaLayer || "krh7";
    const show = () => {
      const k = +$("ksaDay").value || 0, kk = String(k).padStart(2, "0");
      const url = `${CL}fig/${lay}_${kk}.png?v=${encodeURIComponent(st.updated)}`;
      $("ksaFig").src = url;
      const d = K.days[k];
      $("ksaDayLabel").textContent = d ? dayLab(d) + "، الساعة ٣ عصرًا" : "";
      $("ksaLegend").innerHTML = st.figs && st.figs[lay] && !CARDED(K) ? legendHTML(st.figs[lay]) : "";
      $("ksaLegend").hidden = CARDED(K);
      $("ksaHint").textContent = fixModel(KSA_HINT[lay], K) + " كبّر الخريطة أو صغّرها بالزرين واسحبها، والمس أي موضع لترى إحداثياته والرطوبة والحرارة فيه.";
      ksaTapText();
      const box = $("ksaLow");
      // the surface-wind tab moved to the Taif collision card (Fahad, 17 Nov 2026); the Red Sea trough and the
      // surface lows stay under every layer
      box.hidden = false;
      {
        const L = K.lows[k], R = (K.rst || [])[k];
        const rs = R == null ? "" : R ? `<div><b>أخدود البحر الأحمر</b> يمتد شمالًا حتى ${R.reach}.</div>`
          : `<div>لا يمتد أخدود البحر الأحمر شمالًا في هذا اليوم.</div>`;
        box.innerHTML = rs + (L == null ? "<div>تحديد المنخفضات غير متاح لهذا اليوم.</div>"
          : !L.length ? "<div>لا يوجد منخفض سطحي مغلق فوق البحر الأحمر أو اليابسة في هذا اليوم.</div>"
          : L.map((x) => `<div><b>${x.closed ? "منخفض سطحي" : "منخفض سطحي ضعيف"}</b> ${x.where} (${String(x.p).replace(/\d/g, (c) => "٠١٢٣٤٥٦٧٨٩"[c])} هكتوباسكال)</div>`).join(""));
      }
    };
    document.querySelectorAll("#ksaLayer button").forEach((b) => b.onclick = () => {
      document.querySelectorAll("#ksaLayer button").forEach((x) => x.classList.toggle("on", x === b));
      lay = M.ksaLayer = b.dataset.l; show();
    });
    ksaZoomSetup(K.extent || [33, 57.5, 14, 33.5]);
    if (!CARDED(K)) kmapNames($("ksaInner"), K.extent || [33, 57.5, 14, 33.5]);
    if (K.vals && KSAV.v !== st.updated) {
      KSAV.v = st.updated;
      fetch(`${CL}${K.vals.file}?v=${encodeURIComponent(st.updated)}`).then((r) => r.arrayBuffer())
        .then((b) => { KSAV.data = new Int16Array(b); ksaTapText(); }).catch(() => { KSAV.data = null; });
    }
    $("ksaDay").max = Math.max(0, K.days.length - 1);
    if (!ksaCard.done) { $("ksaDay").value = todayIdx(K.days); ksaCard.done = true; }
    $("ksaDay").oninput = show;
    show();
  }

  // the winds at 700 and 500 hPa over the Kingdom (Fahad, 18 Nov 2026): the speed map comes from the nightly run, the
  // arrows are drawn here from ksa_wind.bin (0.5 deg, u and v), one every ~34 screen pixels, so zooming in shows more
  const KW = { lay: "7", z: 0, pt: null, data: null };
  const KW_DIRS = ["شمالية", "شمالية شرقية", "شرقية", "جنوبية شرقية", "جنوبية", "جنوبية غربية", "غربية", "شمالية غربية"];
  function kwAt(k, lev, lat, lon) {
    const W = M.st.ksa.wind, D = KW.data; if (!D) return null;
    const fy = (W.lat0 - lat) / W.d, fx = (lon - W.lon0) / W.d;
    if (fy < 0 || fx < 0 || fy > W.ny - 1 || fx > W.nx - 1) return null;
    const j = Math.min(W.ny - 2, Math.floor(fy)), i = Math.min(W.nx - 2, Math.floor(fx)), ty = fy - j, tx = fx - i;
    const c0 = lev === "7" ? 0 : 2, at = (c, jj, ii) => D[((k * 4 + c) * W.ny + jj) * W.nx + ii] * W.scale;
    const bil = (c) => (at(c, j, i) * (1 - tx) + at(c, j, i + 1) * tx) * (1 - ty) + (at(c, j + 1, i) * (1 - tx) + at(c, j + 1, i + 1) * tx) * ty;
    return [bil(c0), bil(c0 + 1)];
  }
  function kwDraw() {
    const cv = $("kwArrows"), inner = $("kwInner"), K = M.st && M.st.ksa;
    if (!K || !K.wind || !KW.data) return;
    const Wd = inner.clientWidth, Hd = $("kwFig").clientHeight || inner.clientHeight; if (!Wd || !Hd) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.round(Wd * dpr); cv.height = Math.round(Hd * dpr); cv.style.height = Hd + "px";
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, Wd, Hd);
    const [w, e, s, n] = K.extent || [33, 57.5, 14, 33.5], k = +$("kwDay").value || 0, top = KW.lay === "7" ? 20 : 35;
    const S = 34;
    c.lineCap = "round"; c.lineJoin = "round";
    for (let y = S / 2; y < Hd; y += S) for (let x = S / 2; x < Wd; x += S) {
      if (CARDED(K) && ((x > Wd * 0.45 && y < Hd * 0.18) || (x < Wd * 0.45 && y > Hd * 0.86))) continue;   // title and legend boxes of the picture
      const lat = n - (y / Hd) * (n - s), lon = w + (x / Wd) * (e - w), uv = kwAt(k, KW.lay, lat, lon); if (!uv) continue;
      const sp = Math.hypot(uv[0], uv[1]); if (sp < 0.5) continue;
      const dx = uv[0] / Math.cos(lat * Math.PI / 180), dy = -uv[1], m = Math.hypot(dx, dy);
      const L = S * (0.38 + 0.42 * Math.min(1, sp / top)), ux = dx / m, uy = dy / m;
      const x0 = x - ux * L / 2, y0 = y - uy * L / 2, x1 = x + ux * L / 2, y1 = y + uy * L / 2, h = 5.5;
      const path = () => { c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1);
        c.moveTo(x1 - ux * h - uy * h * 0.6, y1 - uy * h + ux * h * 0.6); c.lineTo(x1, y1); c.lineTo(x1 - ux * h + uy * h * 0.6, y1 - uy * h - ux * h * 0.6); };
      path(); c.strokeStyle = "rgba(10,14,20,.75)"; c.lineWidth = 3.4; c.stroke();
      path(); c.strokeStyle = "#ffffff"; c.lineWidth = 1.5; c.stroke();
    }
  }
  function kwTapText() {
    if (!KW.pt) return;
    const K = M.st.ksa, [w, e, s, n] = K.extent || [33, 57.5, 14, 33.5], [fx, fy] = KW.pt;
    const lon = w + fx * (e - w), lat = n - fy * (n - s), k = +$("kwDay").value || 0;
    const r = (a) => AR_DIG(Math.round(a));
    let wind = "";
    for (const lev of ["7", "5"]) {
      const uv = kwAt(k, lev, lat, lon); if (!uv) continue;
      const sp = Math.hypot(uv[0], uv[1]), from = KW_DIRS[Math.round((((Math.atan2(-uv[0], -uv[1]) * 180 / Math.PI) + 360) % 360) / 45) % 8];
      wind += `<div>الرياح عند ${lev === "7" ? "٧٠٠" : "٥٠٠"}: <b>${sp < 1 ? "هادئة" : `${from} ${r(sp)} م/ث`}</b></div>`;
    }
    const txt = `${lat.toFixed(4)}, ${lon.toFixed(4)}`, box = $("kwCoord"); box.hidden = false;
    box.innerHTML = `<span><div>خط العرض <b>${AR_DIG(lat.toFixed(2))}</b> شمالًا، خط الطول <b>${AR_DIG(lon.toFixed(2))}</b> شرقًا</div>${wind}</span><button type="button">نسخ</button>`;
    box.querySelector("button").onclick = async (e2) => {
      try { await navigator.clipboard.writeText(txt); e2.target.textContent = "نُسخت"; } catch (_) { e2.target.textContent = "تعذّر النسخ"; }
      setTimeout(() => { e2.target.textContent = "نسخ"; }, 1500);
    };
  }
  function kwSetup() {
    if (kwSetup.done) return; kwSetup.done = true;
    const LV = [1, 1.5, 2, 3], sc = $("kwScroll"), inner = $("kwInner"), img = $("kwFig");
    const zoom = (d) => {
      const nz = Math.max(0, Math.min(LV.length - 1, KW.z + d)); if (nz === KW.z) return;
      const cx = (sc.scrollLeft + sc.clientWidth / 2) / sc.scrollWidth, cy = (sc.scrollTop + sc.clientHeight / 2) / sc.scrollHeight;
      if (KW.z === 0) sc.style.height = sc.clientHeight + "px";
      KW.z = nz; inner.style.width = LV[KW.z] * 100 + "%"; inner.dataset.z = KW.z;
      if (KW.z === 0) sc.style.height = "";
      const fx = KW.pt ? KW.pt[0] : cx, fy = KW.pt ? KW.pt[1] : cy;
      sc.scrollLeft = fx * sc.scrollWidth - sc.clientWidth / 2; sc.scrollTop = fy * sc.scrollHeight - sc.clientHeight / 2;
      $("kwIn").disabled = KW.z === LV.length - 1; $("kwOut").disabled = KW.z === 0;
      kwDraw();
    };
    $("kwIn").onclick = () => zoom(1); $("kwOut").onclick = () => zoom(-1);
    img.addEventListener("load", kwDraw);
    if (window.ResizeObserver) new ResizeObserver(() => kwDraw()).observe(inner);
    img.addEventListener("click", (ev) => {
      const r = img.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
      if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
      KW.pt = [fx, fy];
      const pin = $("kwPin"); pin.hidden = false; pin.style.left = fx * 100 + "%"; pin.style.top = fy * 100 + "%";
      kwTapText();
    });
    document.querySelectorAll("#kwLayer button").forEach((b) => b.onclick = () => {
      document.querySelectorAll("#kwLayer button").forEach((x) => x.classList.toggle("on", x === b));
      KW.lay = b.dataset.l; kwShow();
    });
    $("kwDay").oninput = kwShow;
  }
  function kwShow() {
    const st = M.st, K = st.ksa, k = +$("kwDay").value || 0, kd = "kw" + KW.lay;
    $("kwFig").src = `${CL}fig/${kd}_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
    const d = K.days[k];
    $("kwDayLabel").textContent = d ? dayLab(d) + "، الساعة ٣ عصرًا" : "";
    $("kwLegend").innerHTML = st.figs && st.figs[kd] && !CARDED(K) ? legendHTML(st.figs[kd]) : "";
    $("kwLegend").hidden = CARDED(K);
    $("kwHint").textContent = fixModel(KW.lay === "7"
      ? "الرياح عند ٧٠٠ هكتوباسكال (نحو ٣ كم فوق سطح البحر) من توقع جي إف إس. هذه الطبقة توجّه السحب الركامية وتنقل الرطوبة إلى المرتفعات."
      : "الرياح عند ٥٠٠ هكتوباسكال (نحو ٥٫٥ كم) من توقع جي إف إس. هذه الطبقة تُظهر مسار الأخاديد والمنخفضات العلوية وتوجّه السحب العميقة.", { model: K.wind_model || K.model })
      + " الأسهم تشير إلى الجهة التي تهب نحوها الرياح، وطولها يزيد مع سرعتها، والألوان والخطوط سرعة الرياح كل ٥ م/ث. كبّر الخريطة فتظهر أسهم أكثر في المنطقة التي تنظر إليها، والمس أي موضع لترى إحداثياته واتجاه الرياح وسرعتها فيه.";
    kwDraw(); kwTapText();
  }
  async function kwCard() {
    const st = M.st, K = st.ksa;
    $("kwCard").hidden = !(K && K.wind && K.days && K.days.length);
    if ($("kwCard").hidden) return;
    kwSetup();
    if (!CARDED(K)) kmapNames($("kwInner"), K.extent || [33, 57.5, 14, 33.5]);
    $("kwDay").max = Math.max(0, K.days.length - 1);
    if (!kwCard.done) { $("kwDay").value = todayIdx(K.days); kwCard.done = true; }
    if (!KW.data || KW.v !== st.updated) {
      try {
        const r = await fetch(`${CL}${K.wind.file}?v=${encodeURIComponent(st.updated)}`);
        KW.data = new Int16Array(await r.arrayBuffer()); KW.v = st.updated;
      } catch (e) { KW.data = null; }
    }
    kwShow();
  }

  // where the afternoon winds collide around Taif (Fahad, 17 Nov 2026): the Al-Hada / Ash-Shafa edge or east and
  // north-east of Taif; 7 days before today, today and 7 after (taifconv.py on the nightly run)
  const TC_WHERE = { edge: "التصادم على حافة الهدا والشفا", east: "التصادم شرق الطائف وشماله الشرقي (السيل والهضبة)", weak: "التصادم ضعيف حول الطائف", eastdry: "التصادم شمال الطائف وشرقه، والطاقة أعلى على الحواف فتقوى السحب عليها مع تقدم النهار" };
  const TC_HINT = {
    line: "مؤشر واحد للمنطقة الغربية (الطائف ومكة وجدة والجموم والحرات وجنوب مكة والبحر الأحمر المجاور): أين أقوى تصادم للرياح السطحية بين ١١ صباحًا و١ ظهرًا. الموجب البرتقالي: التصادم على الطائف نفسه وهضبته وشماله الشرقي والحرات، فالسحب تنشأ فوق الهضبة ولا تنزل على الحافة. السالب الأزرق: التصادم على الحافة والجبال (الهدا والشفا وجبال جنوب مكة) وما تحتها من السهول (مكة والجموم). الفيروزي المموّج: التصادم فوق البحر نفسه، فالسحب بحرية تنشأ فوق البحر وقد تدخل على الساحل. النقطة الرمادية: لا تصادم يُذكر. الرقم فوق العمود قوة التصادم، والخط المتقطع اليوم وما بعده توقع من النموذج الأمريكي.",
    cape: "طاقة عدم الاستقرار السطحية في الساعة المختارة من النموذج الأمريكي، والخط المتقطع محور تصادم الرياح، والخطوط الباهتة اتجاه الرياح. التصادم فوق طاقة جيدة (٢٥٠ فأكثر) يعني سحبًا رعدية أقوى. انتقل بين الأيام بالسهمين، وكبّر الخريطة والمس أي موضع لترى إحداثياته وأقرب مكان له.",
    day: "البرتقالي والأحمر تصادم الرياح السطحية فوق المملكة في الساعة المختارة (١١ صباحًا وقت نشوء السحب على الحافة غالبًا، ثم ينزاح التصادم مع العصر)، والخط المتقطع محور منطقة التصادم، والخطوط البيضاء اتجاه الرياح، والكنتور الرمادي ارتفاع ٩٠٠ و١٥٠٠ متر. انتقل بين الأيام بالسهمين: ٧ أيام مضت واليوم و٧ قادمة، من النموذج الأمريكي. كبّر الخريطة على أي منطقة لترى أماكن التصادم فيها، والمس أي موضع لترى إحداثياته. والسطر تحت الخريطة قراءة حول الطائف.",
  };

  // zoom and tap on the Taif collision maps (Fahad, 17 Nov 2026): as the Kingdom map, and the tap also names the
  // nearest known place (tc_places.json: towns and known sites of the map box from the OSM gazetteer, then villages)
  const DIR8 = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"];
  function tcWhere(lat, lon) {
    const P = tcZoomSetup.places; if (!P || !P.length) return "";
    const km = (p) => { const dy = (p[1] - lat) * 111.2, dx = (p[2] - lon) * 111.2 * Math.cos(lat * Math.PI / 180); return Math.hypot(dx, dy); };
    let best = null, bd = 1e9, near = null, nd = 1e9;
    P.forEach((p) => { const d = km(p); if (p[3] && d < bd) { bd = d; best = p; } if (d < nd) { nd = d; near = p; } });
    if (near && nd <= 3 && (!best || bd > 3)) return `قرب ${near[0]}`;
    if (!best || bd > 60) return "";   // the map is the whole Kingdom now; the places list covers the Taif area
    if (bd <= 3) return `في ${best[0]} أو قربها`;
    const ang = Math.atan2((lon - best[2]) * Math.cos(lat * Math.PI / 180), lat - best[1]) * 180 / Math.PI;
    const dir = DIR8[Math.round(((ang + 360) % 360) / 45) % 8];
    return `${num(Math.round(bd))} كم ${dir} ${best[0]}` + (near && near !== best && nd < bd / 2 && nd <= 8 ? `، قرب ${near[0]}` : "");
  }
  function tcZoomSetup(ext) {
    tcZoomSetup.ext = ext;
    if (tcZoomSetup.done) return;
    tcZoomSetup.done = true;
    getJSON("tc_places.json").then((p) => { tcZoomSetup.places = p; }).catch(() => {});
    const LV = [1, 1.5, 2, 3];
    let z = 0, pt = null;
    const sc = $("tcScroll"), inner = $("tcInner"), img = $("tcFig");
    const zoom = (d) => {
      const nz = Math.max(0, Math.min(LV.length - 1, z + d)); if (nz === z) return;
      const cx = (sc.scrollLeft + sc.clientWidth / 2) / sc.scrollWidth, cy = (sc.scrollTop + sc.clientHeight / 2) / sc.scrollHeight;
      if (z === 0) sc.style.height = sc.clientHeight + "px";
      z = nz; inner.style.width = LV[z] * 100 + "%"; inner.dataset.z = z;
      if (z === 0) sc.style.height = "";
      const fx = pt ? pt[0] : cx, fy = pt ? pt[1] : cy;
      sc.scrollLeft = fx * sc.scrollWidth - sc.clientWidth / 2; sc.scrollTop = fy * sc.scrollHeight - sc.clientHeight / 2;
      $("tcIn").disabled = z === LV.length - 1; $("tcOut").disabled = z === 0;
    };
    tcZoomSetup.reset = () => { while (z > 0) zoom(-1); };
    $("tcIn").onclick = () => zoom(1); $("tcOut").onclick = () => zoom(-1);
    img.addEventListener("click", (ev) => {
      if (tcZoomSetup.off) return;
      const r = img.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
      if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
      pt = [fx, fy];
      const [w, e, s, n] = tcZoomSetup.ext, lon = w + fx * (e - w), lat = n - fy * (n - s);
      const pin = $("tcPin"); pin.hidden = false; pin.style.left = fx * 100 + "%"; pin.style.top = fy * 100 + "%";
      const txt = `${lat.toFixed(4)}, ${lon.toFixed(4)}`, where = tcWhere(lat, lon);
      const box = $("tcCoord"); box.hidden = false;
      box.innerHTML = `<span>${where ? `<b>${where}</b><br>` : ""}خط العرض <b>${AR_DIG(lat.toFixed(2))}</b> شمالًا، خط الطول <b>${AR_DIG(lon.toFixed(2))}</b> شرقًا</span><button type="button">نسخ</button>`;
      box.querySelector("button").onclick = async (e2) => {
        try { await navigator.clipboard.writeText(txt); e2.target.textContent = "نُسخت"; } catch (_) { e2.target.textContent = "تعذّر النسخ"; }
        setTimeout(() => { e2.target.textContent = "نسخ"; }, 1500);
      };
    });
  }
  function tcCard() {
    const st = M.st, T = st.taifc;
    $("tcCard").hidden = !(T && T.rows && T.rows.length);
    if ($("tcCard").hidden) return;
    // third view (Fahad, 19 Nov 2026: «ضعه هنا بجانب الخط الزمني ويكون تبويب ثالث»): the Red Sea flow toward the
    // coasts (ECMWF, redsea.py), its own days (today and 7 after), maps fig/rsf_NN.png with names drawn in
    const RS = null;   // the Red Sea flow has its own card in the «الحمل الحراري» tab since 20 Nov 2026 (Fahad)
    document.querySelector('#tcLayer button[data-l="sea"]').hidden = !RS;
    let lay = M.tcLayer === "line" ? "line" : M.tcLayer === "sea" && RS ? "sea" : "day";   // CAPE view moved to the humidity tab
    let seaK = RS ? todayIdx(RS.days) : 0, dayK = null;
    const showSea = () => {
      const k = Math.min(+$("tcDay").value || 0, RS.rows.length - 1), r = RS.rows[k] || {};
      seaK = k;
      $("tcHour").hidden = true; $("tcTime").hidden = false; $("tcLegend").hidden = true;
      tcZoomSetup.off = true; $("tcZoom").hidden = true;
      if (tcZoomSetup.reset) tcZoomSetup.reset(); $("tcPin").hidden = true; $("tcCoord").hidden = true;
      const nm = $("tcInner").querySelector(".kmap-names"); if (nm) nm.hidden = true;
      $("tcFig").src = `${CL}fig/rsf_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated + ((st.rsflow && st.rsflow.ver) || ""))}`;
      $("tcDayLabel").textContent = r.d ? dayLab(r.d) : "";
      $("tcHint").textContent = "خريطة ساحلية من النموذج الأوروبي، متوسط ١٢ ظهرًا إلى ٦ مساءً: الأسهم الرياح القريبة من السطح، الذهبي منها جنوبية تصعد مع البحر والأزرق شمالية، والألوان طاقة عدم الاستقرار ولسانها. الخط المتقطع حيث تلتقي الجنوبية بالشمالية فوق البحر، وما جنوبه يتغذى بهواء البحر الدافئ الرطب. هي لتوقع السواحل وليست مؤشرًا للحمل فوق الجبال.";
      $("tcNow").innerHTML = r.text ? `<div><b>${r.text[0]}${r.d && r.d > todayISO() ? " (توقع)" : ""}.</b></div>` + r.text.slice(1).map((x) => `<div>${x}.</div>`).join("")
        + (r.src === "gfs" ? "<div>(من النموذج الأمريكي لتعذّر الأوروبي)</div>" : "") : "<div>لا تتوفر بيانات لهذا اليوم.</div>";
    };
    const setSlider = () => {   // the two views have their own days
      if (lay === "sea") { if (dayK === null) dayK = +$("tcDay").value || 0; $("tcDay").max = RS.rows.length - 1; $("tcDay").value = seaK; }
      else { $("tcDay").max = Math.max(0, T.rows.length - 1); if (dayK !== null) { $("tcDay").value = dayK; dayK = null; } }
    };
    const show = () => {
      if (lay === "sea") { showSea(); return; }
      const k = +$("tcDay").value || 0, kk = String(k).padStart(2, "0");
      const hh = M.tcHour || "11";
      const name = lay === "line" ? "tconv_line" : `${lay === "cape" ? "tcape" : "tconv"}_${kk}_${hh}`;
      $("tcHour").hidden = lay === "line";
      document.querySelectorAll("#tcHour button").forEach((x) => x.classList.toggle("on", x.dataset.h === hh));
      $("tcFig").src = `${CL}fig/${name}.png?v=${encodeURIComponent(st.updated)}`;
      $("tcTime").hidden = lay === "line";
      tcZoomSetup.off = lay === "line"; $("tcZoom").hidden = lay === "line";
      if (lay === "line") { if (tcZoomSetup.reset) tcZoomSetup.reset(); $("tcPin").hidden = true; $("tcCoord").hidden = true; }
      const nm = $("tcInner").querySelector(".kmap-names"); if (nm) nm.hidden = lay === "line";   // names belong to the map only
      $("tcLegend").hidden = !(lay === "cape" && T.cape_legend) || CARDED(T);
      if (lay === "cape" && T.cape_legend) $("tcLegend").innerHTML = legendHTML(T.cape_legend);
      $("tcHint").textContent = fixModel(TC_HINT[lay], T);
      const r = lay !== "line" ? T.rows[k] : T.rows[Math.max(0, T.days.indexOf(todayISO()))];
      $("tcDayLabel").textContent = r ? dayLab(r.d) : "";
      if (!r || !r.where) { $("tcNow").innerHTML = "<div>لا تتوفر بيانات لهذا اليوم.</div>"; return; }
      const u = r.u850, wind = u <= T.u_east ? `شرقية ${num(-u, 1)} م/ث تُوقف هواء البحر عند الحافة`
        : u < 0 ? `شرقية ضعيفة ${num(-u, 1)} م/ث` : `غربية ${num(u, 1)} م/ث تدفع هواء البحر فوق الحافة`;
      if (lay === "line" && r.wz) {
        const W = { taif: "على الطائف وهضبته (موجب)", edge: "على الحافة والجبال وما تحتها (سالب)", sea: "فوق البحر الأحمر (بحري)", weak: "ضعيف في المنطقة الغربية" };
        const at = r.wat && r.wz !== "weak" ? tcWhere(r.wat[0], r.wat[1]) : "";
        $("tcNow").innerHTML = `<div><b>اليوم: التصادم ${W[r.wz]}${r.fc ? " (توقع)" : ""}${r.wz === "weak" ? "" : `، المؤشر ${num(r.wi, 1)}`}.</b></div>
        ${at ? `<div>أقوى نقطة: ${at}.</div>` : ""}<div>قوة التصادم: الطائف ${num(r.wt, 1)}، الحافة ${num(r.wg, 1)}، البحر ${num(r.ws, 1)}.</div>`;
        return;
      }
      $("tcNow").innerHTML = `<div><b>حول الطائف: ${TC_WHERE[r.where === "east" && r.fuel === false ? "eastdry" : r.where]}${r.fc ? " (توقع)" : ""}.</b></div>
        <div>الرياح فوق هضبة الطائف عند ٨٥٠: ${wind}. يصل هواء البحر عصرًا إلى خط طول ${num(r.front, 2)}.</div>
        <div>قوة التصادم بين ١١ صباحًا و١ ظهرًا: الحافة ${num(r.ce, 1)}، شرق الطائف ${num(r.cx, 1)}.</div>${r.cape_edge == null ? "" : `
        <div>طاقة عدم الاستقرار عند ١ ظهرًا: الحافة ${num(r.cape_edge)}، شرق الطائف ${num(r.cape_east)} جول/كجم.</div>`}${tcWest(r)}`;
    };
    // the rest of the western region (Fahad, 20 Nov 2026): a collision on the Red Sea in front of the coast (it serves
    // the outflows coming down from the mountains) or west of Makkah is named too; nothing when there is none
    const tcWest = (r) => {
      const MIN = 3, out = [];
      if (r.ws != null && r.ws >= MIN && r.wsat) {
        const C = [["جدة", 21.54, 39.17], ["رابغ", 22.8, 39.03], ["ثول", 22.28, 39.1], ["الليث", 20.15, 40.27], ["القنفذة", 19.13, 41.08]];
        const near = C.map((c) => [c[0], Math.hypot(c[1] - r.wsat[0], (c[2] - r.wsat[1]) * Math.cos(r.wsat[0] * Math.PI / 180))]).sort((a, b) => a[1] - b[1])[0][0];
        out.push(`<div>وعلى البحر الأحمر قبالة ${near}: تصادم بقوة ${num(r.ws, 1)} أمام الساحل، يخدم التخريجات النازلة من الجبال ويغذي السحب قرب الساحل.</div>`);
      }
      if (r.wm != null && r.wm >= MIN && r.wmat) {
        const at = tcWhere(r.wmat[0], r.wmat[1]);
        out.push(`<div>وغرب مكة${at ? " (" + at + ")" : ""}: تصادم بقوة ${num(r.wm, 1)} على السهول بين مكة وجدة.</div>`);
      }
      return out.join("");
    };
    document.querySelectorAll("#tcLayer button").forEach((b) => b.onclick = () => {
      document.querySelectorAll("#tcLayer button").forEach((x) => x.classList.toggle("on", x === b));
      lay = M.tcLayer = b.dataset.l; setSlider(); show();
    });
    // the hour of the map: 11 AM by default, when convective cells start on the rim (Fahad, 17 Nov 2026)
    document.querySelectorAll("#tcHour button").forEach((b) => b.onclick = () => { M.tcHour = b.dataset.h; show(); });
    tcZoomSetup(T.extent || [37.8, 41.8, 20.2, 23.3]);
    if (!CARDED(T)) kmapNames($("tcInner"), T.extent || [33, 57.5, 14, 33.5]);
    $("tcDay").max = Math.max(0, T.rows.length - 1);
    if (!tcCard.done) { $("tcDay").value = todayIdx(T.days); tcCard.done = true; if (lay === "sea") setSlider(); }
    $("tcDay").oninput = show;
    document.querySelectorAll("#tcLayer button").forEach((x) => x.classList.toggle("on", x.dataset.l === lay));
    show();
  }

  // the inland penetration of the Red Sea energy (Fahad, 19 Nov 2026: «توغل التدفق للحمل الحراري cape في قسم الرطوبة
  // بدلا عن تبويب عدم الاستقرار»): ECMWF maps fig/rsc_NN.png (redsea.py), today and 7 after, Dr. Khalid's colours
  // the Red Sea flow toward the coasts in the «الحمل الحراري» tab (Fahad, 19 Nov 2026 night: «اجعل لها تبويب خاص الحمل
  // الحراري بعد الرطوبة»), maps fig/rsf_NN.png from redsea.py, today and 7 after
  function rsCard() {
    const st = M.st, R = st.rsflow, rows = R && R.rows ? R.rows : [];
    $("rsCard").hidden = !rows.length;
    if ($("rsCard").hidden) return;
    const show = () => {
      const k = +$("rsDay").value || 0, r = rows[k] || {};
      $("rsFig").src = `${CL}fig/rsf_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated + ((st.rsflow && st.rsflow.ver) || ""))}`;
      $("rsDayLabel").textContent = r.d ? dayLab(r.d) : "";
      const mdl = r.src === "gfs" ? "النموذج الأمريكي" : "النموذج الأوروبي";
      $("rsHint").textContent = `خريطة ساحلية من ${mdl}، متوسط ١٢ ظهرًا إلى ٦ مساءً: الأسهم الرياح القريبة من السطح، الذهبي منها جنوبية تصعد مع البحر والأزرق شمالية، والألوان طاقة عدم الاستقرار ولسانها. الخط المتقطع حيث تلتقي الجنوبية بالشمالية فوق البحر، وما جنوبه يتغذى بهواء البحر الدافئ الرطب. هي لتوقع السواحل وليست مؤشرًا للحمل فوق الجبال.`;
      $("rsNow").innerHTML = r.text ? `<div><b>${r.text[0]}${r.d && r.d > todayISO() ? " (توقع)" : ""}.</b></div>` + r.text.slice(1).map((x) => `<div>${x}.</div>`).join("")
        : "<div>لا تتوفر بيانات لهذا اليوم.</div>";
    };
    if (!rsCard.done) {
      rsCard.done = true;
      $("rsDay").oninput = show;
      $("rsDay").max = Math.max(0, rows.length - 1); $("rsDay").value = todayIdx(R.days);
    }
    show();
  }
  // the atmospheric river from the Arabian Sea, ECMWF only (Fahad, 22 Nov 2026: «النهر المتدفق بلون مميز يتحرك بتقدم
  // الأيام بدون أسهم»): one picture per day (riv_KK.png), the day's line and the first arrival; only the shown day and
  // the next one are fetched (never all frames at once)
  function rivCard() {
    const st = M.st, R = st.river, rows = R && R.rows ? R.rows : [];
    $("rivCard").hidden = !rows.some((r) => r.g);
    const tab = document.querySelector('#mjoTabs [data-s="river"]'); if (tab) tab.hidden = $("rivCard").hidden;
    if ($("rivCard").hidden) return;
    const url = (k) => `${CL}fig/riv_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated + (R.ver || ""))}`;   // ver: a hand redraw
    const show = () => {
      const k = +$("rivDay").value || 0, r = rows[k] || {};
      $("rivFig").src = url(k);
      if (rows[k + 1]) { const n = new Image(); n.src = url(k + 1); }
      $("rivDayLabel").textContent = r.d ? dayLab(r.d) : "";
      const fut = r.d && r.d > todayISO() ? " (توقع)" : "";
      $("rivNow").innerHTML = (r.text ? `<div><b>${r.text}${fut}.</b></div>` : "<div>لا تتوفر بيانات لهذا اليوم.</div>")
        + (R.first_text ? `<div>${R.first_text}.</div>` : "");
    };
    if (!rivCard.done) {
      rivCard.done = true;
      $("rivDay").max = Math.max(0, rows.length - 1); $("rivDay").value = todayIdx(R.days);
      $("rivDay").oninput = show;
    }
    show();
  }
  // the thunderstorm outlook along the river (Fahad, 25 Nov 2026, after Dr. Khalid's "Atmospheric River Tracking -
  // Thunderstorm Outlook": «ضيفها لتبويب الجوي لكن باستخدام الأوروبي»): rst_KK.png per day, the chance around the core
  function rstCard() {
    const st = M.st, R = st.river, rows = R && R.rows ? R.rows : [];
    const n = rows.filter((r) => r.storm !== undefined).length ? rows.findLastIndex((r) => r.storm) + 1 : 0;
    $("rstCard").hidden = !n;
    if (!n) return;
    const AR = (t) => String(t).replace(/\d/g, (c) => "٠١٢٣٤٥٦٧٨٩"[c]).replace(".", "٫");
    const url = (k) => `${CL}fig/rst_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated + (R.ver || ""))}`;
    const show = () => {
      const k = +$("rstDay").value || 0, r = rows[k] || {};
      $("rstFig").src = url(k);
      if (k + 1 < n) { const im = new Image(); im.src = url(k + 1); }
      $("rstDayLabel").textContent = r.d ? dayLab(r.d) : "";
      const s = r.storm, c = r.core;
      $("rstNow").innerHTML = s ? `<div><b>حول قلب النهر: أعلى احتمال لعاصفة شديدة ${AR(s[0])}٪، ومتوسطه ${AR(s[1])}٪.</b></div>`
        : (c ? "<div>قلب النهر خارج منطقة الحساب في هذا اليوم.</div>" : "<div>لا نهر واضحًا في هذا اليوم.</div>");
    };
    if (!rstCard.done) {
      rstCard.done = true;
      $("rstDay").max = n - 1; $("rstDay").value = Math.min(n - 1, todayIdx(R.days));
      $("rstDay").oninput = show;
    }
    show();
  }
  function tpCard() {
    const st = M.st, R = st.rsflow, rows = R && R.rows ? R.rows : [];
    $("tpCard").hidden = !rows.some((r) => r.inland_share != null);
    if ($("tpCard").hidden) return;
    const ext = R.in_extent || [32.5, 51.5, 14, 32.5];
    const LV = { none: "الطاقة محصورة على البحر والساحل ولم تدخل الداخل", start: "بداية دخول لطاقة البحر نحو الداخل",
      clear: "توغّل واضح لطاقة البحر داخل الجزيرة، ومعه تزيد فرصة مطر واسع في الداخل" };
    const show = () => {
      const k = +$("tpDay").value || 0, r = rows[k] || {};
      $("tpFig").src = `${CL}fig/rsc_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated + ((st.rsflow && st.rsflow.ver) || ""))}`;
      $("tpDayLabel").textContent = r.d ? dayLab(r.d) : "";
      if (r.src === "gfs") $("tpHint").textContent = $("tpHint").textContent.replace("من النموذج الأوروبي", "من النموذج الأمريكي");
      $("tpNow").innerHTML = r.inland_share == null ? "<div>لا تتوفر خريطة لهذا اليوم.</div>"
        : `<div><b>${LV[r.inland] || ""}${r.d && r.d > todayISO() ? " (توقع)" : ""}.</b></div><div>الطاقة المتصلة بالبحر تغطي ${num(r.inland_share, 1)}٪ من نجد والقصيم والوسطى.</div>`;
    };
    if (!tpCard.done) {
      tpCard.done = true;
      $("tpDay").oninput = show;
      $("tpDay").max = Math.max(0, rows.length - 1); $("tpDay").value = todayIdx(R.days);
      const LVZ = [1, 1.5, 2, 3], sc = $("tpScroll"), inner = $("tpInner"), img = $("tpFig");
      let z = 0, pt = null;
      const zoom = (d) => {
        const nz = Math.max(0, Math.min(LVZ.length - 1, z + d)); if (nz === z) return;
        const cx = (sc.scrollLeft + sc.clientWidth / 2) / sc.scrollWidth, cy = (sc.scrollTop + sc.clientHeight / 2) / sc.scrollHeight;
        if (z === 0) sc.style.height = sc.clientHeight + "px";
        z = nz; inner.style.width = LVZ[z] * 100 + "%"; inner.dataset.z = z;
        if (z === 0) sc.style.height = "";
        const fx = pt ? pt[0] : cx, fy = pt ? pt[1] : cy;
        sc.scrollLeft = fx * sc.scrollWidth - sc.clientWidth / 2; sc.scrollTop = fy * sc.scrollHeight - sc.clientHeight / 2;
        $("tpIn").disabled = z === LVZ.length - 1; $("tpOut").disabled = z === 0;
      };
      $("tpIn").onclick = () => zoom(1); $("tpOut").onclick = () => zoom(-1);
      img.addEventListener("click", (ev) => {
        const r = img.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
        if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
        pt = [fx, fy];
        const [w, e, s, n] = ext, lon = w + fx * (e - w), lat = n - fy * (n - s);
        const pin = $("tpPin"); pin.hidden = false; pin.style.left = fx * 100 + "%"; pin.style.top = fy * 100 + "%";
        const txt = `${lat.toFixed(4)}, ${lon.toFixed(4)}`, box = $("tpCoord"); box.hidden = false;
        box.innerHTML = `<span>خط العرض <b>${AR_DIG(lat.toFixed(2))}</b> شمالًا، خط الطول <b>${AR_DIG(lon.toFixed(2))}</b> شرقًا</span><button type="button">نسخ</button>`;
        box.querySelector("button").onclick = async (e2) => {
          try { await navigator.clipboard.writeText(txt); e2.target.textContent = "نُسخت"; } catch (_) { e2.target.textContent = "تعذّر النسخ"; }
          setTimeout(() => { e2.target.textContent = "نسخ"; }, 1500);
        };
      });
    }
    show();
  }

  // "after 3 days" with the Arabic number agreement
  function after(k) { return k === 1 ? "بعد يوم" : k === 2 ? "بعد يومين" : k <= 10 ? `بعد ${num(k)} أيام` : `بعد ${num(k)} يومًا`; }

  const WC_HINT = "الأحمر: حدث دافئ يدعم الحمل العميق (تباعد هوائي في الأعلى). الأزرق: حدث بارد يكبت الحمل. الخطوط البيضاء: اتجاه التدفق في الأعلى عند ٢٠٠ هكتوباسكال. اسحب الخريطة يمينًا ويسارًا لترى بقية العالم، أو المسها لفتحها بحجم كامل.";
  const LW_HINT = "الحدث الدافئ والبارد قرب الأرض: حرارة الهواء ورطوبته معًا عند ٢ متر و٨٠٠ هكتوباسكال مقارنة بمعدل التاريخ (٢٠٢١-٢٠٢٥)، الثالثة عصرًا. الأحمر بيئة تهيئ للحمل العميق، والأزرق حدث بارد يكبته. اللوحة الثانية المؤشر مضروبًا في جذر طاقة عدم الاستقرار. اختُبر على ٣٨٢ يومًا حول مكة وتهامة والطائف: في الحدث البارد (١- أو أقل) لم يبلغ المطر ٢٠ ملم في أي يوم، فهو يلغي المطر في التقرير، أما الدافئ فمعزز يرفع الثقة مع المكونات الأخرى ولا يصنع مطرًا وحده.";
  const LWD_HINT = "تغير مؤشر الحدث الدافئ والبارد قرب الأرض خلال ٢٤ ساعة حتى الثالثة عصرًا. البرتقالي اشتداد الحدث الدافئ أو ضعف البارد، والأزرق العكس.";
  function mjoShow() {
    const st = M.st, k = M.day, lay = M.layer, kk = String(k).padStart(2, "0");
    const figs = st.figs || {};
    // the low-level warm event (Fahad, 19 Nov 2026, after Dr. Khalid's 2 m / 800 hPa maps): its own list of days
    const lw = st.lowwarm && st.lowwarm.days && st.lowwarm.days.length ? st.lowwarm : null;
    document.querySelectorAll('#mjoLayer [data-l="lw"], #mjoLayer [data-l="lwd"]').forEach((b) => { b.hidden = !lw; });
    let fk = kk;
    if (lay === "lw" || lay === "lwd") {
      const i = lw ? lw.days.indexOf(st.days[k]) : -1;
      fk = String(Math.max(0, i)).padStart(2, "0");
    }
    const url = `${CL}fig/${lay}_${fk}.png?v=${encodeURIComponent(st.updated)}`;
    $("mjoFig").src = url; $("mjoFigLink").href = url;
    $("mjoFigWrap").classList.toggle("fit", lay === "pw");
    $("mjoFigWrap").classList.toggle("lw-tall", lay === "lw");
    $("mjoFigWrap").classList.toggle("lw-mid", lay === "lwd");
    $("mjoHint").textContent = lay === "lw" ? LW_HINT : lay === "lwd" ? LWD_HINT : WC_HINT;
    const d = st.days[k];
    $("mjoDayLabel").textContent = d ? dayLab(d) : "";
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
    c.font = "10px -apple-system, \"IBM Plex Sans Arabic\", sans-serif"; c.fillStyle = getComputedStyle(document.body).color; c.textAlign = "center";
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

  // 19 Nov 2026 (Fahad: the site was very slow): the page fetched every frame of every map at once (about 44 MB when
  // the oscillation tab opened); now only the day shown and its neighbours, and only once the card is on screen
  const NEAR = new Set();
  function nearby(urls, el) {
    const go = () => (el && !el.offsetParent) || urls.forEach((u) => { if (NEAR.has(u)) return; NEAR.add(u); const im = new Image(); im.src = u; });
    (window.requestIdleCallback || ((f) => setTimeout(f, 300)))(go);
  }
  function waveCard() {
    const st = M.st, rows = st.waves || [];
    if (!rows.length) { $("waveList").innerHTML = `<p class="muted">غير متاح اليوم.</p>`; return; }
    const wurl = (k) => `${CL}fig/wave_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
    const show = (k) => {
      const url = wurl(k);
      const [a, b] = document.querySelectorAll("#waveWrap img");
      const front = a.classList.contains("on") ? a : b.classList.contains("on") ? b : null, back = front === a ? b : a;
      if (!front || front.dataset.u !== url) {
        back.onload = () => {
          back.classList.add("on"); if (front) front.classList.remove("on");
          const wr = $("waveWrap");
          if (!wr.dataset.s && wr.scrollWidth > wr.clientWidth) { wr.scrollLeft = (wr.scrollWidth * 0.44) - wr.clientWidth / 2; wr.dataset.s = 1; }
        };
        back.dataset.u = url; back.src = url;
      }
      $("waveLink").href = url;
      nearby([k - 1, k + 1].filter((i) => i >= 0 && i < rows.length).map(wurl), $("waveWrap"));
      const d = rows[k] && rows[k].d;
      $("waveDayLabel").textContent = d ? dayLab(d) : "";
    };
    $("waveDay").max = rows.length - 1;
    if (!waveCard.done) { $("waveDay").value = todayIdx(rows.map((r) => r.d)); waveCard.done = true; }
    $("waveDay").oninput = (e) => show(+e.target.value);
    show(+$("waveDay").value || 0);
    const items = rows.filter((r) => r.d >= todayISO()).slice(0, 8).filter((r) => r.trough).map((r) =>
      `<div class="wave-row"><span>${fmtDayD.format(dOf(r.d))}</span><span>أخدود فوق ${r.trough.area} بعمق <b>${num(Math.abs(r.trough.v))}</b> م</span></div>`);
    $("waveList").innerHTML = items.length ? `<h4 class="sub">الأخاديد القريبة من المملكة</h4>` + items.join("")
      : `<p class="muted">لا أخاديد واضحة قرب المملكة في الأيام السبعة القادمة.</p>`;
  }

  // the MJO component of the 800 hPa height and of the rain (Dr Khalid's method), and its line over the Kingdom
  // tropical convection with the MJO centre line (convmap.py, Fahad 19 Nov 2026)
  function olrCard() {
    const st = M.st || {};
    const ok = !!st.olr;
    $("olrCard").hidden = !ok;
    if (!ok) return;
    const days = st.olr.days || [st.olr.t1];
    const mk = (t) => new Date(Date.parse(t) + 3 * 3600e3).toISOString().slice(0, 10);   // Makkah date of the window end
    const show = () => {
      const k = Math.min(+$("olrDay").value || 0, days.length - 1);
      const url = `${CL}fig/olr_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
      $("olrFig").src = url; $("olrLink").href = url;
      $("olrDayLabel").textContent = (k === 0 ? "آخر ٢٤ ساعة، " : "متوقع، ") + dayLab(mk(days[k]));
    };
    $("olrTime").hidden = days.length < 2;
    $("olrDay").max = days.length - 1;
    $("olrDay").oninput = show;
    show();
  }

  function mjofCard() {
    const st = M.st, m = st.mjof;
    $("mjofCard").hidden = !m;
    if (!m) return;
    const days = st.days || [];
    let lay = M.mjofLayer || "mjoz";
    const show = () => {
      const k = +$("mjofDay").value || 0, kk = String(k).padStart(2, "0");
      const url = `${CL}fig/${lay}_${kk}.png?v=${encodeURIComponent(st.updated)}`;
      $("mjofFig").src = url; $("mjofLink").href = url;
      const d = days[k];
      $("mjofDayLabel").textContent = d ? dayLab(d) : "";
      if (st.figs && st.figs[lay]) $("mjofLegend").innerHTML = legendHTML(st.figs[lay]);
    };
    document.querySelectorAll("#mjofLayer button").forEach((b) => b.onclick = () => {
      document.querySelectorAll("#mjofLayer button").forEach((x) => x.classList.toggle("on", x === b));
      lay = M.mjofLayer = b.dataset.l; show();
    });
    $("mjofDay").max = Math.max(0, days.length - 1);
    if (!mjofCard.done) { $("mjofDay").value = todayIdx(days); mjofCard.done = true; }
    $("mjofDay").oninput = show;
    show();
    // the line: last 60 days and the forecast; bars: share of the Kingdom with 5 mm or more (GFS first day)
    const n = m.days.length, from = Math.max(0, n - 76);
    const D = m.days.slice(from), Z = m.z_ksa.slice(from), C = m.cover.slice(from);
    const W = 340, H = 150, L = 34, R = 6, T = 10, B = 22, iw = W - L - R, ih = H - T - B;
    const zr = Math.max(10, ...Z.map((v) => Math.abs(v))), x = (i) => L + (i + 0.5) * iw / D.length;
    const yz = (v) => T + ih / 2 - (v / zr) * ih / 2;
    const cmax = Math.max(0.2, ...C.filter((v) => v != null));
    const today = D.indexOf(days[0]);
    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="مكوّن التذبذب فوق المملكة ومساحة الأمطار">`;
    C.forEach((c, i) => { if (c != null && c > 0) { const h = (c / cmax) * ih; g += `<rect x="${x(i) - 1.6}" y="${T + ih - h}" width="3.2" height="${h}" fill="var(--sea)" opacity=".35"/>`; } });
    g += `<line x1="${L}" x2="${W - R}" y1="${yz(0)}" y2="${yz(0)}" stroke="currentColor" opacity=".3"/>`;
    if (today >= 0) g += `<line x1="${x(today)}" x2="${x(today)}" y1="${T}" y2="${T + ih}" stroke="currentColor" stroke-dasharray="3 3" opacity=".5"/>`;
    g += `<polyline fill="none" stroke="#2950d6" stroke-width="1.8" points="${Z.map((v, i) => `${x(i).toFixed(1)},${yz(v).toFixed(1)}`).join(" ")}"/>`;
    [zr, 0, -zr].forEach((v) => { g += `<text x="${L - 4}" y="${yz(v) + 3}" font-size="9" text-anchor="end" fill="currentColor" opacity=".7">${v < 0 ? "−" + num(Math.round(-v)) : num(Math.round(v))}</text>`; });
    D.forEach((d, i) => { if (+d.slice(8) === 1 || i === today) g += `<text x="${x(i)}" y="${H - 6}" font-size="9" text-anchor="middle" fill="currentColor" opacity=".7">${num(+d.slice(8))}/${num(+d.slice(5, 7))}</text>`; });
    $("mjofChart").innerHTML = g + "</svg>";
  }

  // the tropical belt, as the reference engine draws it: four maps on one frame (warm/cold event, the MJO component,
  // the Kelvin and the Rossby families of the 200 hPa velocity potential) with the same marker lines through them
  function lonTxt(x) {
    x = ((Math.round(x) % 360) + 360) % 360;
    return x === 0 || x === 180 ? `${num(x)}°` : x < 180 ? `${num(x)}° شرقًا` : `${num(360 - x)}° غربًا`;
  }
  // the Kelvin and Rossby maps as in Dr Khalid's charts: a week of analyses and the forecast, one frame a day,
  // each new frame faded in over the last so the waves move on smoothly
  function twCard() {
    const st = M.st, t = st.twf;
    $("twCard").hidden = !t;
    if (!t) return;
    const n = t.days.length, kinds = ["twr", "twk"];
    const url = (kd, k) => `${CL}fig/${kd}_${String(k).padStart(2, "0")}.png?v=${encodeURIComponent(st.updated)}`;
    const show = () => {
      const k = +$("twDay").value || 0, d = t.days[k];
      document.querySelectorAll("#twCard .tw-stage").forEach((sg) => {
        const [a, b] = sg.querySelectorAll("img"), front = a.classList.contains("on") ? a : b.classList.contains("on") ? b : null;
        const back = front === a ? b : a, u = url(sg.dataset.k, k);
        if (front && front.dataset.u === u) return;
        back.onload = () => { if (back.naturalWidth) sg.style.aspectRatio = `${back.naturalWidth} / ${back.naturalHeight}`; back.classList.add("on"); if (front) front.classList.remove("on"); };  // the stage takes the picture's own shape, so no empty strip at the side
        back.dataset.u = u; back.src = u;
      });
      nearby(kinds.flatMap((kd) => [k - 1, k + 1].filter((i) => i >= 0 && i < n).map((i) => url(kd, i))), $("twCard"));
      const dd = d ? dayDiff(d) : 0;
      const lab = k <= t.t0 ? "تحليل" : dd === 0 ? "اليوم" : "توقع";   // t0 is the evening analysis of yesterday
      $("twDayLabel").textContent = d ? `${lab}: ${fmtDayD.format(dOf(d))}` : "";
    };
    $("twDay").max = n - 1;
    if (!twCard.done) { const ti = t.days.indexOf(todayISO()); $("twDay").value = ti >= 0 ? ti : t.t0; twCard.done = true; }
    $("twDay").oninput = show;
    show();
  }
  function beltCard() {
    const st = M.st, days = st.days || [];
    // hidden on 14 Nov 2026 at Fahad's request: the maps are rebuilt one by one with him
    const have = false && !!(st.figs && st.figs.kel && st.marks);
    $("beltCard").hidden = !have;
    if (!have) return;
    // one chart of the four maps stacked, with their colour bars and the marker key inside (since 15 Nov 2026);
    // the separate maps for older data
    const stack = !!st.belt_stack;
    const panels = stack ? [["belt", "اللوحة الاستوائية الشاملة: أربع خرائط بإطار واحد"]] : [["wc", "مؤشر الحدث الدافئ والبارد (جهد السرعة عند ٢٠٠ هكتوباسكال)"],
      ["mjoz", "مكوّن التذبذب عند ٨٠٠ هكتوباسكال"],
      ["kel", "موجات كلفن المتجهة شرقًا: جهد السرعة عند ٢٠٠ هكتوباسكال"],
      ["ros", "عائلة روسبي المتجهة غربًا: جهد السرعة عند ٢٠٠ هكتوباسكال"]];
    // the four maps scroll together, so the longitudes stay under each other; a button fits them to the width
    $("beltPanels").innerHTML = `<div class="seg" id="beltZoom"><button data-z="wide" class="${M.beltFit ? "" : "on"}">مكبّرة (اسحب يمينًا ويسارًا)</button><button data-z="fit" class="${M.beltFit ? "on" : ""}">العالم كله</button></div>
      <div class="figwrap belt-scroll${M.beltFit ? " fit" : ""}" dir="ltr">` +
      panels.map(([k, t], i) => `<div class="belt-panel${stack ? " stack" : ""}">${stack ? "" : `<h4 dir="rtl">${num(i + 1)}. ${t}</h4>`}<a id="belt_${k}_a" target="_blank" rel="noopener"><img id="belt_${k}" alt="${t}"></a></div>`).join("") +
      `</div>` + (stack ? "" : panels.map(([k, t], i) => st.figs[k] ? `<div class="legend mjo-legend"><b>${num(i + 1)}.</b> ${legendHTML(st.figs[k])}</div>` : "").join(""));
    document.querySelectorAll("#beltZoom button").forEach((b) => b.onclick = () => {
      M.beltFit = b.dataset.z === "fit";
      document.querySelectorAll("#beltZoom button").forEach((x) => x.classList.toggle("on", x === b));
      document.querySelector(".belt-scroll").classList.toggle("fit", M.beltFit);
    });
    const show = () => {
      const k = +$("beltDay").value || 0, kk = String(k).padStart(2, "0");
      panels.forEach(([p]) => {
        const url = `${CL}fig/${p}_${kk}.png?v=${encodeURIComponent(st.updated)}`;
        $(`belt_${p}`).src = url; $(`belt_${p}_a`).href = url;
      });
      const d = days[k];
      $("beltDayLabel").textContent = d ? dayLab(d) : "";
      const m = st.marks[k] || {};
      const chip = (c, t, x) => x == null ? "" : `<span><i style="background:${c}"></i>${t} ${lonTxt(x)}</span>`;
      $("beltMarks").innerHTML = chip("#d9775a", "مركز التذبذب", m.core) + chip("#a3202a", "الحدث الدافئ", m.warm) + chip("#2b4a7f", "الحدث البارد", m.cold);
    };
    $("beltDay").max = Math.max(0, days.length - 1);
    $("beltDay").oninput = show;
    show();
    twChart();
  }

  // the Kelvin and Rossby families over the Kingdom: the last 60 days and the forecast; bars: the rain spread
  function twChart() {
    const st = M.st, t = st.tw, m = st.mjof;
    if (!t) { $("twChart").innerHTML = ""; return; }
    const days = st.days || [], n = t.days.length, from = Math.max(0, n - 76);
    const D = t.days.slice(from), K = t.kel_ksa.slice(from), R = t.ros_ksa.slice(from);
    const cov = {}; if (m) m.days.forEach((d, i) => { if (m.cover[i] != null) cov[d] = m.cover[i]; });
    const W = 340, H = 160, L = 26, Rm = 6, T = 22, B = 22, iw = W - L - Rm, ih = H - T - B;
    const vr = Math.max(3, ...K.map(Math.abs), ...R.map(Math.abs)), x = (i) => L + (i + 0.5) * iw / D.length;
    const y = (v) => T + ih / 2 - (v / vr) * ih / 2;
    const cs = D.map((d) => cov[d]), cmax = Math.max(0.2, ...cs.filter((v) => v != null));
    const today = D.indexOf(days[0]);
    let g = `<svg viewBox="0 0 ${W} ${H}" style="direction:ltr" role="img" aria-label="موجات كلفن وروسبي فوق المملكة">`;
    cs.forEach((c, i) => { if (c != null && c > 0) { const h = (c / cmax) * ih; g += `<rect x="${x(i) - 1.6}" y="${T + ih - h}" width="3.2" height="${h}" fill="var(--sea)" opacity=".3"/>`; } });
    g += `<line x1="${L}" x2="${W - Rm}" y1="${y(0)}" y2="${y(0)}" stroke="currentColor" opacity=".3"/>`;
    if (today >= 0) g += `<line x1="${x(today)}" x2="${x(today)}" y1="${T}" y2="${T + ih}" stroke="currentColor" stroke-dasharray="3 3" opacity=".5"/>`;
    const line = (A, c) => `<polyline fill="none" stroke="${c}" stroke-width="1.8" points="${A.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}"/>`;
    g += line(K, "#e0795a") + line(R, "#1f5fa8");
    [vr, 0, -vr].forEach((v) => { g += `<text x="${L - 4}" y="${y(v) + 3}" font-size="9" text-anchor="end" fill="currentColor" opacity=".7">${v < 0 ? "−" + num(Math.round(-v)) : num(Math.round(v))}</text>`; });
    D.forEach((d, i) => { if (+d.slice(8) === 1 || i === today) g += `<text x="${x(i)}" y="${H - 6}" font-size="9" text-anchor="middle" fill="currentColor" opacity=".7">${num(+d.slice(8))}/${num(+d.slice(5, 7))}</text>`; });
    g += `<rect x="${W - 18}" y="5" width="12" height="3" fill="#1f5fa8"/><text x="${W - 22}" y="10" font-size="9" text-anchor="end" fill="currentColor">روسبي</text>`;
    g += `<rect x="${W - 70}" y="5" width="12" height="3" fill="#e0795a"/><text x="${W - 74}" y="10" font-size="9" text-anchor="end" fill="currentColor">كلفن</text>`;
    g += `<text x="${L}" y="10" font-size="9" text-anchor="start" fill="currentColor" opacity=".7">فوق المملكة، السالب داعم</text>`;
    $("twChart").innerHTML = g + "</svg>";
  }




  function pwModelHints() {
    const w = (ec) => ec ? "من توقع النموذج الأوروبي" : "من توقع جي إف إس";
    document.querySelectorAll(".pw-src").forEach((x) => {
      x.textContent = w(x.dataset.f === "map" ? M.st && M.st.pw_model === "ecmwf" : M.st && !!M.st.pw_ec);
    });
  }

  function mjoPwTable() {
    pwModelHints();
    // ECMWF when the night's run had it (Fahad, 20 Nov 2026), 16 days; the report keeps reading GFS (st.pw)
    const st = M.st, rows = (st.pw_ec || st.pw || []).filter((r) => r.d >= todayISO()).slice(0, 16);
    if (!rows.length) return;
    const names = { west: "الحجاز والغرب", southwest: "الجنوب الغربي", central: "الوسط", east: "الشرق", north: "الشمال" };
    let t = `<table class="pwt${rows.length > 10 ? " wide" : ""}"><tr><th></th>${rows.map((r) => `<th>${fmtDM.format(dOf(r.d))}</th>`).join("")}</tr>`;
    for (const k of Object.keys(names)) {
      t += `<tr><td>${names[k]}</td>` + rows.map((r) => {
        // shades of the site's blue on the dark page (Fahad, 16 Nov 2026): faint at 110 %, full from about 180 %
        const v = r[k].pct, a = Math.min(1, Math.max(0.16, (v - 100) / 80));
        const bg = v >= 110 ? `rgba(74,134,245,${a.toFixed(2)})` : "transparent", fw = v >= 130 ? 700 : 400;
        return `<td style="background:${bg};color:#fff;font-weight:${fw}">${num(v)}</td>`;
      }).join("") + "</tr>";
    }
    $("mjoPw").innerHTML = t + "</table>";
  }

  // ------------------------------------------------------------------ tabs
  // previous / play / next under every day slider of the oscillation tab; they drive the slider, so each card's own oninput draws the frame
  const PL = { timer: null, btn: null };
  function plStop() { if (PL.timer) { clearInterval(PL.timer); PL.timer = null; PL.btn.textContent = "▶"; PL.btn.setAttribute("aria-label", "تشغيل"); } }
  function plStep(r, d) {
    const n = +r.max + 1; if (n < 2) return;
    r.value = (+r.value + d + n) % n; r.dispatchEvent(new Event("input"));
  }
  function addPlayers() {
    document.querySelectorAll(".mjo-time").forEach((row) => {
      if (row.querySelector(".pl-btns")) return;
      const r = row.querySelector("input[type=range]");
      const box = document.createElement("div"); box.className = "pl-btns"; box.dir = "ltr";
      box.innerHTML = `<button class="icon-btn" aria-label="السابق">‹</button><button class="icon-btn play" aria-label="تشغيل">▶</button><button class="icon-btn" aria-label="التالي">›</button>`;
      const [bp, bl, bn] = box.querySelectorAll("button");
      bp.onclick = () => { plStop(); if (+r.value > 0) plStep(r, -1); };
      bn.onclick = () => { plStop(); if (+r.value < +r.max) plStep(r, 1); };
      bl.onclick = () => {
        const mine = PL.timer && PL.btn === bl; plStop(); if (mine) return;
        PL.btn = bl; bl.textContent = "❚❚"; bl.setAttribute("aria-label", "إيقاف");
        if (+r.value >= +r.max) { r.value = -1; }
        plStep(r, 1); PL.timer = setInterval(() => plStep(r, 1), 1100);
      };
      r.addEventListener("pointerdown", plStop);
      row.prepend(box);
    });
  }
  addPlayers();

  // the sections live in a menu behind the button at the top corner (Fahad, 16 Nov 2026)
  function menuShow(on) {
    $("menu").hidden = !on; $("menuBtn").classList.toggle("open", on); $("menuBtn").setAttribute("aria-expanded", on);
  }
  $("menuBtn").onclick = () => menuShow($("menu").hidden);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") menuShow(false); });
  document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
    menuShow(false);
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    plStop();
    for (const p of ["map", "mjo", "status"]) $("p-" + p).hidden = p !== b.dataset.tab;
    $("p-cities").hidden = true;
    if (b.dataset.tab === "mjo") mjoOpen();
    if (b.dataset.tab === "map") setTimeout(() => map.invalidateSize(), 50);
    if (b.dataset.tab === "cities") drawCities();
    if (b.dataset.tab === "status") refreshStatus();
  });

  function setLogLinks() { document.querySelectorAll("[data-log]").forEach((a) => { a.href = `${DATA}logs/${a.dataset.log}.txt`; }); }
  setLogLinks();

  (async function start() {
    map.getContainer().classList.toggle("hide-labels", map.getZoom() < 7);
    if (LIVE(S.prod)) {  // show lightning / radar straight away; the model data loads behind it
      $("prodSelect").innerHTML = `<option value="radar">الرادار</option><option value="lightning">البرق</option>`; $("prodSelect").value = S.prod;
      liEnter();
    } else {
      setTimeout(liLoad, 2000);  // fetch quietly so switching to lightning is instant
    }
    await Promise.all([refreshRuns(true), refreshStatus()]);
    setInterval(refreshStatus, 60e3);
    setInterval(() => refreshRuns(false), 5 * 60e3);
  })();
})();
