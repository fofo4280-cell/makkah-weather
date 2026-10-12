// Small helpers: storage, fetching with timeout/retry/cache, formatting.

export const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem('mwx:' + key); return v == null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('mwx:' + key, JSON.stringify(value)); return true; }
    catch { return false; }
  },
  del(key) { try { localStorage.removeItem('mwx:' + key); } catch { /* ignore */ } },
};

const memCache = new Map();

export class FetchError extends Error {
  constructor(message, { status = 0, reason = '', url = '' } = {}) {
    super(message); this.status = status; this.reason = reason; this.url = url;
  }
}

// Open-Meteo's free tier allows 600 weighted calls per minute per device (each location
// in a multi-point request counts, and more than 10 variables counts extra). Requests
// that would pass ~540 wait for the minute to roll over instead of failing with 429.
const PER_MIN = 540; const spent = [];
let budgetHook = () => {};
export function setBudgetHook(fn) { budgetHook = fn; }
async function budget(w) {
  let waited = false;
  for (;;) {
    const now = Date.now(); while (spent.length && now - spent[0][0] > 61000) spent.shift();
    const used = spent.reduce((a, b) => a + b[1], 0);
    if (!spent.length || used + w <= PER_MIN) { spent.push([now, w]); if (waited) budgetHook(false); return; }
    waited = true; budgetHook(true, Math.ceil((61000 - (now - spent[0][0])) / 1000));
    await sleep(Math.min(61000 - (now - spent[0][0]) + 250, 5000));
  }
}

// GET JSON with timeout, limited retries on network/5xx errors, and an in-memory
// cache. Open-Meteo 400 errors carry {reason}; they are not retried.
export async function getJSON(url, { timeout = 20000, retries = 1, ttl = 10 * 60 * 1000, force = false, weight = 0 } = {}) {
  const hit = memCache.get(url);
  if (!force && hit && Date.now() - hit.t < ttl) return { data: hit.data, fromCache: true, fetchedAt: hit.t, stale: false };
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (weight) await budget(weight);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(url, { signal: ctrl.signal, cache: force ? 'reload' : 'default' });
      clearTimeout(timer);
      const swStale = res.headers.get('x-mwx-offline') === '1';
      const text = await res.text();
      let data = null;
      try { data = JSON.parse(text); } catch { /* not JSON */ }
      if (!res.ok) {
        const reason = res.status === 429 ? 'تجاوز حد الطلبات المجاني لـOpen-Meteo؛ أعد المحاولة بعد دقيقة' : (data && (data.reason || data.error)) || text.slice(0, 200);
        const err = new FetchError(`HTTP ${res.status}`, { status: res.status, reason: String(reason), url });
        if (res.status >= 400 && res.status < 500) throw err;
        lastErr = err; continue;
      }
      if (data == null) throw new FetchError('استجابة غير صالحة', { status: res.status, url });
      const fetchedAt = swStale ? Number(res.headers.get('x-mwx-time')) || Date.now() : Date.now();
      memCache.set(url, { t: fetchedAt, data });
      return { data, fromCache: swStale, fetchedAt, stale: swStale };
    } catch (e) {
      clearTimeout(timer);
      if (e instanceof FetchError && e.status >= 400 && e.status < 500) throw e;
      lastErr = e.name === 'AbortError' ? new FetchError('انتهت مهلة الاتصال', { url }) : (e instanceof FetchError ? e : new FetchError('تعذر الاتصال بالمصدر', { url }));
      if (attempt < retries) await sleep(800 * (attempt + 1));
    }
  }
  if (hit) return { data: hit.data, fromCache: true, fetchedAt: hit.t, stale: true, error: lastErr };
  throw lastErr;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function qs(params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${Array.isArray(v) ? v.map(encodeURIComponent).join(',') : encodeURIComponent(v)}`)
    .join('&');
}

// Gregorian calendar with Latin digits, Riyadh time.
const fmtCache = {};
function fmt(opts) {
  const k = JSON.stringify(opts);
  if (!fmtCache[k]) fmtCache[k] = new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn', { timeZone: 'Asia/Riyadh', ...opts });
  return fmtCache[k];
}
export const fmtTime = (ms) => fmt({ hour: '2-digit', minute: '2-digit', hour12: false }).format(ms);
export const fmtDayHour = (ms) => `${fmt({ weekday: 'short' }).format(ms)} ${fmt({ hour: '2-digit', hour12: false }).format(ms).padStart(2, '0')}:00`;
export const fmtDateTime = (ms) => fmt({ weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).format(ms);
export const fmtDay = (ms) => fmt({ weekday: 'long', day: 'numeric', month: 'short' }).format(ms);
export function riyadhHour(ms) { return Number(fmt({ hour: '2-digit', hour12: false }).format(ms)) % 24; }
export function fmtUTC(ms) {
  const d = new Date(ms);
  return `${String(d.getUTCHours()).padStart(2, '0')}Z ${d.getUTCDate()}/${d.getUTCMonth() + 1}`;
}
export function ago(ms) {
  const m = Math.round((Date.now() - ms) / 60000);
  if (m < 1) return 'الآن';
  if (m < 60) return `قبل ${m} د`;
  const h = Math.round(m / 60);
  if (h < 48) return `قبل ${h} س`;
  return `قبل ${Math.round(h / 24)} يوم`;
}

// Numbers are wrapped in Unicode isolates so signs and units stay in order inside Arabic text.
export function num(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return '—';
  return `\u2066${Number(v).toFixed(digits).replace('-', '−')}\u2069`;
}
export function rawNum(v, digits = 0) { return v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(digits); }

export const COMPASS_AR = ['شمالية', 'شمالية شرقية', 'شرقية', 'جنوبية شرقية', 'جنوبية', 'جنوبية غربية', 'غربية', 'شمالية غربية'];
export const TOWARD_AR = ['الشمال', 'الشمال الشرقي', 'الشرق', 'الجنوب الشرقي', 'الجنوب', 'الجنوب الغربي', 'الغرب', 'الشمال الغربي'];
export const dirName = (deg) => (deg == null ? '—' : COMPASS_AR[Math.round(((deg % 360) + 360) % 360 / 45) % 8]);
export const towardName = (deg) => (deg == null ? '—' : TOWARD_AR[Math.round(((deg % 360) + 360) % 360 / 45) % 8]);

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

export function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function sum(arr) { let s = 0, n = 0; for (const v of arr) if (v != null && !Number.isNaN(v)) { s += v; n++; } return n ? s : null; }
export function max(arr) { let m = null; for (const v of arr) if (v != null && !Number.isNaN(v) && (m == null || v > m)) m = v; return m; }
export function min(arr) { let m = null; for (const v of arr) if (v != null && !Number.isNaN(v) && (m == null || v < m)) m = v; return m; }
export function mean(arr) { const xs = arr.filter((v) => v != null && !Number.isNaN(v)); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; }
