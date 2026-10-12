// Geography helpers shared by the map, the report tab and the daily report script.
// No browser APIs here: the GitHub Actions script imports this file with Node.
import { PLACES, ESCARP } from './config.js';

// Reference towns for naming locations ("12 كم شمال شرق الجموم"). Coordinates are
// town centres from GeoNames (via the Open-Meteo geocoder) or the site's place list.
export const GAZ = [
  ...PLACES.map(({ name, lat, lon }) => ({ name, lat, lon })),
  { name: 'عرفات', lat: 21.355, lon: 39.984 },
  { name: 'الزيمة', lat: 21.607, lon: 40.118 },
  { name: 'السيل الكبير', lat: 21.624, lon: 40.419 },
  { name: 'الكامل', lat: 22.261, lon: 39.797 },
  { name: 'ثول', lat: 22.283, lon: 39.112 },
  { name: 'مستورة', lat: 23.116, lon: 38.841 },
  { name: 'ظلم', lat: 22.725, lon: 42.171 },
  { name: 'الباحة', lat: 20.013, lon: 41.468 },
];

// Rough outline of Makkah Province, drawn by hand from border towns. Approximate:
// edges can be off by 10–30 km. Kept on the conservative side next to Al-Baha's Tihama
// so the report does not list places in Al-Baha Province. Used only by the daily report.
export const MAKKAH_REGION = [
  [23.65, 38.70], [23.55, 39.60], [23.25, 40.55], [23.10, 41.40], [23.25, 42.25], [22.70, 43.00],
  [21.70, 43.30], [20.95, 43.20], [20.90, 42.30], [20.65, 41.60], [20.40, 41.10], [20.05, 40.95],
  [19.70, 41.05], [19.35, 41.55], [18.75, 41.60], [18.45, 41.30], [18.70, 41.05], [19.20, 40.85], [20.10, 40.15],
  [20.80, 39.45], [21.40, 39.05], [22.00, 38.95], [22.70, 38.80], [23.20, 38.65],
];

export function inPolygon(lat, lon, poly = MAKKAH_REGION) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [yi, xi] = poly[i], [yj, xj] = poly[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

const rad = (d) => (d * Math.PI) / 180;
export function distKm(a, b) {
  const dLat = rad(b.lat - a.lat), dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}
export function bearingDeg(a, b) {
  const y = Math.sin(rad(b.lon - a.lon)) * Math.cos(rad(b.lat));
  const x = Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) - Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(rad(b.lon - a.lon));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}
const DIRS8 = ['شمال', 'شمال شرق', 'شرق', 'جنوب شرق', 'جنوب', 'جنوب غرب', 'غرب', 'شمال غرب'];
export const dir8 = (deg) => DIRS8[Math.round(deg / 45) % 8];

export function inBox(lat, lon, b) { return lat >= b.lat0 && lat <= b.lat1 && lon >= b.lon0 && lon <= b.lon1; }

// "8 كم شمال شرق الجموم" / "قرب الهدا", plus terrain context where it applies.
export function describe(lat, lon) {
  const p = { lat, lon };
  let best = null, bd = Infinity;
  for (const g of GAZ) { const d = distKm(g, p); if (d < bd) { bd = d; best = g; } }
  const d = Math.round(bd);
  const text = d <= 4 ? `قرب ${best.name}` : `${d} كم ${dir8(bearingDeg(best, p))} ${best.name}`;
  const tags = [];
  if (inBox(lat, lon, ESCARP.boxes.harrat)) tags.push('حرة رهط');
  if (inBox(lat, lon, ESCARP.boxes.valleys)) tags.push('أودية جنوب مكة');
  for (const c of ESCARP.crests) if (distKm(c, p) <= 20) tags.push(`حافة ${c.name}`);
  return { text, near: best.name, distKm: d, tags };
}
