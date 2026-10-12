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
  { name: 'الشعيبة', lat: 20.680, lon: 39.523 },
  { name: 'قيا', lat: 21.070, lon: 41.008 },
];

// Area the daily report analyses, as Fahad defined it: Makkah, Taif, Al-Jumum, Jeddah,
// Al-Shafa, Al-Hada and As-Sayl; the harrat north to Rahat and Al-Kamil; the coast north
// to Thuwal and Khulais and south to Al-Shu'aybah; east of Taif to the Hadhn road and
// Ushayrah; south of Taif to Qiya. Hand-drawn and approximate (edges ±10 km); it is drawn
// on the map with the report so it can be checked. Sea cells are dropped separately.
export const REPORT_AREA = [
  [22.42, 38.95], [22.48, 39.60], [22.50, 40.45], [22.05, 40.85], [21.85, 41.18], [21.25, 41.22],
  [20.92, 41.12], [20.88, 40.30], [20.55, 39.75], [20.50, 39.35], [21.30, 38.95],
];
export const REPORT_AREA_LABEL = 'مكة والطائف والجموم وجدة والشفا والهدا والسيل، والحرات حتى رهاط والكامل، والساحل من ثول وخليص إلى الشعيبة، وشرق الطائف حتى طريق حضن وعشيرة، وجنوبه حتى قيا';
export const MAKKAH_REGION = REPORT_AREA;

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
