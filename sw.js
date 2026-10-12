// Service worker: offline app shell + last-known API responses.
const VERSION = 'mwx-v2';
const SHELL = ['./', 'index.html', 'css/app.css', 'js/app.js', 'js/config.js', 'js/util.js', 'js/api.js', 'js/met.js', 'js/charts.js', 'js/analysis.js', 'js/map.js', 'js/escarp.js', 'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];
const API_HOSTS = ['api.open-meteo.com', 'ensemble-api.open-meteo.com', 'previous-runs-api.open-meteo.com', 'api.rainviewer.com', 'aviationweather.gov'];

self.addEventListener('install', (e) => { e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== 'mwx-api').map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.origin === location.origin) {
    // network first for the shell so updates arrive; cache when offline
    e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request).then((r) => r || caches.match('index.html'))));
    return;
  }
  if (API_HOSTS.includes(url.hostname)) {
    e.respondWith((async () => {
      const cache = await caches.open('mwx-api');
      try {
        const r = await fetch(e.request);
        if (r.ok) {
          const body = await r.clone().arrayBuffer();
          const h = new Headers(r.headers); h.set('x-mwx-time', String(Date.now()));
          await cache.put(e.request, new Response(body, { status: 200, headers: h }));
        }
        return r;
      } catch (err) {
        const hit = await cache.match(e.request);
        if (!hit) throw err;
        const h = new Headers(hit.headers); h.set('x-mwx-offline', '1');
        return new Response(await hit.arrayBuffer(), { status: 200, headers: h });
      }
    })());
  }
});
