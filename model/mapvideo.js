// Day-slider maps of the oscillation page as an MP4 video (Fahad, 23 Nov 2026: «اصنع لي خيار اي خريطة اختارها من صفحتنا
// تتحول الى فيديو mp4 مع تحديد التواريخ فقط»).
// A camera button next to the play buttons of every day slider opens a small panel: «من» and «إلى» (the slider's own day
// names) and one button. The video is made in the browser from the frames the page already shows: the slider is stepped
// day by day (each card's own oninput draws its map, layer, hour and arrows as on screen), the visible pictures and
// canvases of the card's map are copied onto one canvas under a title strip (card title, chosen layer, day and date), and
// the frames are encoded to H.264 MP4 (WebCodecs + mp4-muxer, vendor/mp4-muxer, loaded only when a video is made;
// MediaRecorder MP4 as fallback). Nothing is fetched before the person asks for a video. One day = one second.
(function () {
  "use strict";
  const P = document.getElementById("p-mjo");
  if (!P) return;
  const AR = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
  // WhatsApp-friendly (25 Nov 2026, Fahad: the video was sharp on the phone but poor once sent on WhatsApp): long side at
  // most 1280 px (WhatsApp's own HD size, so it is not scaled down again), sides multiples of 16, H.264 High 4.0 4:2:0,
  // 10 frames a second with a key frame at every day, modest bitrate, moov at the start (fastStart).
  const SEC_PER_DAY = 1, FPS = 10, MAXSIDE = 1280;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const CAM = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="6" width="13" height="12" rx="2"/><path d="M15 10l6-3v10l-6-3z"/></svg>';
  let busy = false;

  const css = document.createElement("style");
  css.textContent = `
.vid-panel { margin-top: 10px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; direction: rtl; font-size: .88rem; }
.vid-panel h4 { margin: 0 0 8px; font-size: .92rem; }
.vid-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.vid-row label { display: flex; gap: 8px; align-items: center; flex: 1 1 100%; min-width: 0; }
.vid-row label > span { width: 2.2em; flex: none; }
.vid-row select { flex: 1; min-width: 0; height: 34px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface-2); color: var(--ink); font: inherit; font-size: .82rem; padding: 0 6px; }
.vid-go, .vid-act { border: 0; border-radius: 10px; background: var(--sea); color: #fff; font: inherit; font-size: .86rem; padding: 7px 14px; text-decoration: none; display: inline-block; }
.vid-act.alt { background: transparent; border: 1px solid var(--line); color: var(--ink); }
.vid-go:disabled { opacity: .5; }
.vid-msg { color: var(--muted); font-size: .82rem; margin: 6px 0 0; }
.vid-out video { width: 100%; border-radius: 10px; margin-top: 8px; background: #000; display: block; }
.vid-out .vid-row { margin-top: 8px; }
.pl-btns .icon-btn.vid-btn { display: inline-flex; align-items: center; justify-content: center; }
.pl-btns .icon-btn.vid-btn.on { background: var(--sea); border-color: transparent; color: #fff; }`;
  document.head.appendChild(css);

  function setup() {
    P.querySelectorAll(".mjo-time").forEach((row) => {
      const r = row.querySelector("input[type=range]");
      const box = row.querySelector(".pl-btns");
      if (!r || !box || box.querySelector(".vid-btn")) return;
      const b = document.createElement("button");
      b.type = "button"; b.className = "icon-btn vid-btn"; b.innerHTML = CAM;
      b.setAttribute("aria-label", "صنع فيديو"); b.title = "صنع فيديو";
      b.onclick = () => toggle(row, r, b);
      box.appendChild(b);
    });
  }

  const lab = (row) => row.querySelector('span[id$="DayLabel"]');
  const figRoot = (card) => card.querySelector(".ksa-map, .figwrap, #beltPanels");

  // the slider's day names, read by stepping the slider without letting the browser paint (the pictures set on the way are
  // replaced before they are fetched); the slider is put back where it was
  async function dayNames(row, r) {
    const l = lab(row), v0 = +r.value, out = [];
    // no picture is fetched while the names are read: setting a picture's address does nothing for that moment (also
    // the neighbour preloads the cards start when the browser is idle)
    const D = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
    try {
      Object.defineProperty(HTMLImageElement.prototype, "src", { configurable: true, enumerable: D.enumerable, get: D.get, set() {} });
      for (let i = +r.min; i <= +r.max; i++) {
        r.value = i; r.dispatchEvent(new Event("input"));
        out.push(((l && l.textContent) || "").trim() || `اليوم ${AR(i + 1)}`);
      }
      r.value = v0; r.dispatchEvent(new Event("input"));
      await new Promise((ok) => (window.requestIdleCallback || ((f) => setTimeout(f, 0)))(() => ok(), { timeout: 600 }));
      await wait(350);
    } finally {
      Object.defineProperty(HTMLImageElement.prototype, "src", D);
    }
    r.value = v0; r.dispatchEvent(new Event("input"));
    return out;
  }

  async function toggle(row, r, btn) {
    const card = row.closest(".card");
    let pan = card.querySelector(".vid-panel");
    if (pan) { if (busy && pan.dataset.busy) return; pan.remove(); btn.classList.remove("on"); return; }
    if (btn.dataset.wait) return;
    btn.dataset.wait = "1";
    let names;
    try { names = await dayNames(row, r); } finally { delete btn.dataset.wait; }
    pan = document.createElement("div");
    pan.className = "vid-panel";
    const opts = names.map((n, i) => `<option value="${i}">${n}</option>`).join("");
    pan.innerHTML = `<h4>صنع فيديو من هذه الخريطة</h4>
      <div class="vid-row"><label><span>من</span><select class="vid-from">${opts}</select></label><label><span>إلى</span><select class="vid-to">${opts}</select></label></div>
      <div class="vid-row"><button type="button" class="vid-go">اصنع الفيديو</button></div>
      <p class="vid-msg">يظهر الفيديو بالطبقة المختارة الآن في الخريطة، كل يوم ثانية واحدة.</p>
      <div class="vid-out"></div>`;
    row.after(pan);
    btn.classList.add("on");
    const f = pan.querySelector(".vid-from"), t = pan.querySelector(".vid-to");
    f.value = String(Math.max(+r.min, Math.min(+r.max, +r.value)));
    t.value = String(+r.max);
    pan.querySelector(".vid-go").onclick = () => make(card, row, r, pan, +f.value, +t.value, names);
  }

  // every picture or canvas shown in the card's map, with its place in CSS pixels
  function layers(root) {
    const els = [...root.querySelectorAll("img, canvas")].filter((e) => {
      if (!e.offsetParent && getComputedStyle(e).position !== "fixed") return false;
      const s = getComputedStyle(e);
      if (s.visibility === "hidden" || s.display === "none" || +s.opacity < 0.5) return false;
      if (e.tagName === "IMG" && !(e.currentSrc || e.src)) return false;
      const b = e.getBoundingClientRect();
      return b.width > 20 && b.height > 20;
    });
    return els.map((e) => {
      const r = e.getBoundingClientRect();
      let b = { left: r.left, top: r.top, width: r.width, height: r.height };
      // a picture drawn with object-fit: contain fills only part of its box
      if (e.tagName === "IMG" && getComputedStyle(e).objectFit === "contain" && e.naturalWidth) {
        const k = Math.min(r.width / e.naturalWidth, r.height / e.naturalHeight);
        const w = e.naturalWidth * k, h = e.naturalHeight * k;
        b = { left: r.left + (r.width - w) / 2, top: r.top + (r.height - h) / 2, width: w, height: h };
      }
      b.right = b.left + b.width; b.bottom = b.top + b.height;
      const pan = e.closest(".tw-panel");
      const h4 = pan && pan.querySelector("h4");
      return { e, b, tag: h4 ? h4.textContent.trim() : "" };
    });
  }

  async function settled(root) {
    const t0 = Date.now();
    let ok = 0;
    while (Date.now() - t0 < 25000) {
      const imgs = layers(root).filter((x) => x.e.tagName === "IMG");
      const all = [...root.querySelectorAll("img")].filter((i) => i.offsetParent);
      const done = all.every((i) => !i.src || i.complete);
      if (done && imgs.length && imgs.every((x) => x.e.naturalWidth > 0)) { if (++ok >= 2) break; } else ok = 0;
      await wait(120);
    }
    await wait(650);   // the cross-fade of the wave maps ends
  }

  const bmCache = new Map();
  async function bitmapOf(el) {
    if (el.tagName === "CANVAS") return el;
    const u = el.currentSrc || el.src;
    if (bmCache.has(u)) return bmCache.get(u);
    const res = await fetch(u, { mode: "cors" });
    if (!res.ok) throw new Error("frame " + res.status);
    const bm = await createImageBitmap(await res.blob());
    bmCache.set(u, bm);
    return bm;
  }

  function strip(ctx, W, H0, title, sub) {
    ctx.fillStyle = "#111111"; ctx.fillRect(0, 0, W, H0);
    ctx.direction = "rtl"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
    const fam = getComputedStyle(document.body).fontFamily || "sans-serif";
    const fit = (txt, px, weight) => {
      let s = px; ctx.font = `${weight} ${s}px ${fam}`;
      while (s > 10 && ctx.measureText(txt).width > W * 0.94) { s -= 1; ctx.font = `${weight} ${s}px ${fam}`; }
    };
    fit(title, Math.round(H0 * 0.30), 700); ctx.fillStyle = "#ffffff"; ctx.fillText(title, W * 0.97, H0 * 0.34);
    fit(sub, Math.round(H0 * 0.25), 500); ctx.fillStyle = "#b8b8b8"; ctx.fillText(sub, W * 0.97, H0 * 0.73);
  }

  async function compose(card, root, title, sub, size) {
    const L = layers(root);
    if (!L.length) throw new Error("no map");
    const x0 = Math.min(...L.map((q) => q.b.left)), y0 = Math.min(...L.map((q) => q.b.top));
    const x1 = Math.max(...L.map((q) => q.b.right)), y1 = Math.max(...L.map((q) => q.b.bottom));
    if (!size.W) {
      // natural sharpness of the biggest picture, then kept within WhatsApp's HD size (long side 1280 px)
      const im = L.filter((q) => q.e.tagName === "IMG").sort((a, b) => b.b.width - a.b.width)[0];
      let s = im ? im.e.naturalWidth / im.b.width : 2;
      s = Math.max(1, Math.min(s, 4));
      let W = (x1 - x0) * s, Hm = (y1 - y0) * s;
      const H0 = Math.max(70, Math.round(W * 0.075));
      const k = Math.min(1, MAXSIDE / W, MAXSIDE / (Hm + H0));
      const r16 = (v) => Math.max(16, Math.ceil(v / 16) * 16);   // macroblock size: no padded edges after re-encoding
      size.s = s * k; size.W = Math.min(MAXSIDE, r16(W * k)); size.H0 = Math.round(H0 * k / 2) * 2;
      size.H = Math.min(MAXSIDE, r16(size.H0 + Hm * k));
      size.cv = document.createElement("canvas");
      size.cv.width = size.W; size.cv.height = size.H;
    }
    // this frame's layout fitted into the video's fixed size (a picture can change shape once it has loaded)
    const sc = Math.min(size.s, size.W / (x1 - x0), (size.H - size.H0) / (y1 - y0));
    const ox = (size.W - (x1 - x0) * sc) / 2, oy = size.H0 + ((size.H - size.H0) - (y1 - y0) * sc) / 2;
    const X = (v) => ox + (v - x0) * sc, Y = (v) => oy + (v - y0) * sc;
    const ctx = size.cv.getContext("2d");
    ctx.fillStyle = "#111111"; ctx.fillRect(0, 0, size.W, size.H);
    for (const q of L) {
      const src = await bitmapOf(q.e);
      ctx.drawImage(src, X(q.b.left), Y(q.b.top), q.b.width * sc, q.b.height * sc);
    }
    // the panel names (Kelvin / Rossby) over their own picture
    const fam = getComputedStyle(document.body).fontFamily || "sans-serif";
    for (const q of L) {
      if (!q.tag) continue;
      const px = Math.max(14, Math.round(size.H0 * 0.24));
      ctx.font = `700 ${px}px ${fam}`; ctx.direction = "rtl"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      const w = ctx.measureText(q.tag).width + px, xr = X(q.b.right) - px * 0.5, yt = Y(q.b.top) + px * 0.4;
      ctx.fillStyle = "rgba(17,17,17,.82)"; ctx.fillRect(xr - w, yt, w, px * 1.6);
      ctx.fillStyle = "#fff"; ctx.fillText(q.tag, xr - px * 0.5, yt + px * 0.8);
    }
    strip(ctx, size.W, size.H0, title, sub);
    return size.cv;
  }

  function loadMuxer() {
    if (window.Mp4Muxer) return Promise.resolve();
    return new Promise((ok, no) => {
      const s = document.createElement("script");
      s.src = "../vendor/mp4-muxer/mp4-muxer.js"; s.onload = ok; s.onerror = no;
      document.head.appendChild(s);
    });
  }

  async function avcConfig(W, H) {
    for (const codec of ["avc1.640028", "avc1.4d0028", "avc1.42002a"]) {
      const c = { codec, width: W, height: H, bitrate: Math.min(3.5e6, W * H * 3), framerate: FPS, latencyMode: "quality", avc: { format: "avc" } };
      try { const r = await VideoEncoder.isConfigSupported(c); if (r.supported) return c; } catch (e) {}
    }
    return null;
  }

  // the canvas as I420 in the usual TV range (16-235, BT.709): a canvas handed to the encoder as it is comes out
  // full range (yuvj420p), which WhatsApp and some players treat badly
  const CS = { primaries: "bt709", transfer: "bt709", matrix: "bt709", fullRange: false };
  function i420(cv) {
    const W = cv.width, H = cv.height, d = cv.getContext("2d").getImageData(0, 0, W, H).data;
    const buf = new Uint8Array(W * H * 3 / 2), U = W * H, V = U + U / 4;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const o = (y * W + x) * 4;
      buf[y * W + x] = 16 + ((47 * d[o] + 157 * d[o + 1] + 16 * d[o + 2]) >> 8);
    }
    for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2) {
      let r = 0, g = 0, bl = 0;
      for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) { const o = ((y + dy) * W + x + dx) * 4; r += d[o]; g += d[o + 1]; bl += d[o + 2]; }
      r /= 4; g /= 4; bl /= 4;
      const k = (y / 2) * (W / 2) + x / 2;
      buf[U + k] = Math.max(16, Math.min(240, Math.round(128 + (-0.1006 * r - 0.3386 * g + 0.4392 * bl))));
      buf[V + k] = Math.max(16, Math.min(240, Math.round(128 + (0.4392 * r - 0.3989 * g - 0.0403 * bl))));
    }
    return buf;
  }

  // WebCodecs path: frames are encoded as they are drawn
  async function webcodecs(size, frames, onFrame) {
    if (!("VideoEncoder" in window)) return null;
    await loadMuxer().catch(() => {});
    if (!window.Mp4Muxer) return null;
    // the first day that loads fixes the video size
    let i = 0, cv = null;
    while (i < frames && !(cv = await onFrame(i))) i++;
    if (!cv) throw new Error("no frames");
    const cfg = await avcConfig(size.W, size.H);
    if (!cfg) { size.first = i; return null; }
    const muxer = new Mp4Muxer.Muxer({ target: new Mp4Muxer.ArrayBufferTarget(), video: { codec: "avc", width: size.W, height: size.H }, fastStart: "in-memory" });
    let err = null;
    const enc = new VideoEncoder({ output: (c, m) => muxer.addVideoChunk(c, m), error: (e) => { err = e; } });
    enc.configure(cfg);
    let n = 0;
    const step = 1e6 / FPS;
    for (; i < frames; i++) {
      if (!cv) cv = await onFrame(i);
      if (!cv) continue;
      const reps = (i === frames - 1 ? 2 : 1) * SEC_PER_DAY * FPS;   // the last day stays a little longer
      let yuv = null;
      try { yuv = i420(cv); } catch (e) {}
      for (let k = 0; k < reps; k++) {
        const vf = yuv
          ? new VideoFrame(yuv, { format: "I420", codedWidth: size.W, codedHeight: size.H, colorSpace: CS, timestamp: Math.round(n * step), duration: Math.round(step) })
          : new VideoFrame(cv, { timestamp: Math.round(n * step), duration: Math.round(step) });
        enc.encode(vf, { keyFrame: k === 0 });
        vf.close(); n++;
        if (err) throw err;
      }
      cv = null;
      while (enc.encodeQueueSize > 10) await wait(20);
    }
    await enc.flush();
    if (err) throw err;
    enc.close();
    muxer.finalize();
    return new Blob([muxer.target.buffer], { type: "video/mp4" });
  }

  // MediaRecorder path (browsers without H.264 WebCodecs): the frames are played onto a canvas in real time
  async function recorder(size, frames, onFrame, msg) {
    const mime = ["video/mp4;codecs=avc1", "video/mp4"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m));
    if (!mime) return null;
    const pics = [];
    for (let i = 0; i < frames; i++) {
      const cv = await onFrame(i);
      if (cv) pics.push(await createImageBitmap(cv));
    }
    msg("جارٍ تسجيل الفيديو…");
    const out = document.createElement("canvas"); out.width = size.W; out.height = size.H;
    const ctx = out.getContext("2d");
    ctx.drawImage(pics[0], 0, 0);
    const st = out.captureStream(FPS);
    const rec = new MediaRecorder(st, { mimeType: mime, videoBitsPerSecond: 3.5e6 });
    const parts = [];
    rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
    const done = new Promise((r) => { rec.onstop = r; });
    rec.start(250);
    for (let i = 0; i < pics.length; i++) {
      const t0 = performance.now(), dur = (i === pics.length - 1 ? 2 : 1) * SEC_PER_DAY * 1000;
      while (performance.now() - t0 < dur) { ctx.drawImage(pics[i], 0, 0); await wait(1000 / FPS); }
    }
    rec.stop(); await done;
    return new Blob(parts, { type: "video/mp4" });
  }

  const dateOnly = (s) => (s.includes(":") ? s.split(":").slice(1).join(":") : s).trim();

  async function make(card, row, r, pan, a, b, names) {
    if (busy) return;
    if (a > b) [a, b] = [b, a];
    const go = pan.querySelector(".vid-go"), msgEl = pan.querySelector(".vid-msg"), out = pan.querySelector(".vid-out");
    const msg = (t) => { msgEl.textContent = t; };
    const root = figRoot(card);
    if (!root) { msg("لا توجد خريطة في هذه البطاقة."); return; }
    busy = true; pan.dataset.busy = "1"; go.disabled = true; out.innerHTML = "";
    const v0 = +r.value;
    root.querySelectorAll("img[loading=lazy]").forEach((i) => { i.loading = "eager"; });
    const h3 = (card.querySelector("h3") || {}).textContent || "";
    const segs = [...card.querySelectorAll(".seg button.on")].filter((x) => x.offsetParent).map((x) => x.textContent.trim());
    const head = card.querySelector(".map-head small");
    const title = [h3.trim(), segs.join("، ")].filter(Boolean).join(" — ") + (head && head.textContent ? ` — ${head.textContent.trim()}` : "");
    const size = {};
    const frames = b - a + 1;
    let skipped = 0;
    const onFrame = async (i) => {
      msg(`جارٍ تجهيز اليوم ${AR(i + 1)} من ${AR(frames)}…`);
      r.value = a + i; r.dispatchEvent(new Event("input"));
      await settled(root);
      try { return await compose(card, root, title, dateOnly(names[a + i] || ""), size); }
      catch (e) { skipped++; return null; }
    };
    let blob = null, why = "";
    try {
      blob = await webcodecs(size, frames, onFrame);
      if (!blob) {
        bmCache.clear(); skipped = 0;
        blob = await recorder(size, frames, onFrame, msg);
      }
      if (!blob) why = "متصفحك لا يدعم صنع الفيديو، حدّث المتصفح ثم حاول مرة أخرى.";
    } catch (e) {
      why = "تعذّر صنع الفيديو، حاول مرة أخرى.";
      console.error("[mapvideo]", e);
    }
    bmCache.clear();
    r.value = v0; r.dispatchEvent(new Event("input"));
    busy = false; delete pan.dataset.busy; go.disabled = false;
    if (!blob || !size.W) { msg(why || "تعذّر صنع الفيديو."); return; }
    const name = `${(h3.trim() || "خريطة").replace(/[\\/:*?"<>|]+/g, " ")} ${dateOnly(names[a])} - ${dateOnly(names[b])}.mp4`;
    const url = URL.createObjectURL(blob);
    const file = (() => { try { return new File([blob], name, { type: "video/mp4" }); } catch (e) { return null; } })();
    const canShare = file && navigator.canShare && navigator.canShare({ files: [file] });
    out.innerHTML = `<video controls playsinline muted loop src="${url}"></video>
      <div class="vid-row">${canShare ? '<button type="button" class="vid-act vid-share">مشاركة أو حفظ</button>' : ""}
      <a class="vid-act ${canShare ? "alt" : ""}" href="${url}" download="${name.replace(/"/g, "")}">تنزيل الفيديو</a></div>
      <p class="vid-msg vid-tip">للإرسال في واتساب بأعلى جودة: نزّل الفيديو، ثم في المحادثة اختر «＋» ثم «مستند» واختر الملف، فيصل كما هو دون ضغط. وإن أرسلته فيديو عاديًا فاختر الجودة العالية قبل الإرسال.</p>`;
    if (canShare) out.querySelector(".vid-share").onclick = () => navigator.share({ files: [file], title: name.replace(/\.mp4$/, "") }).catch(() => {});
    const mb = blob.size / 1048576;
    msg(`جاهز: ${AR(frames - skipped)} ${frames - skipped > 10 ? "يومًا" : "أيام"} في ${AR(Math.round((frames - skipped + 1) * SEC_PER_DAY))} ${Math.round((frames - skipped + 1) * SEC_PER_DAY) > 10 ? "ثانية" : "ثوانٍ"}، الحجم ${AR(mb < 10 ? mb.toFixed(1).replace(".", "٫") : Math.round(mb))} ميغابايت.${skipped ? ` تعذّر تحميل ${AR(skipped)} من الأيام فتُركت.` : ""}`);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup); else setup();
  setTimeout(setup, 1500);
})();
