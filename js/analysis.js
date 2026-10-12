// Rule-based Arabic analysis. Separates observation, forecast and interpretation.
// Thresholds are first guesses for a dry, high-cloud-base environment and are
// editable in Settings; every statement says which level it belongs to.
import { buildProfile, diagnostics } from './met.js';
import { LEVELS, MODELS, MODEL_KEYS } from './config.js';
import { fmtDayHour, riyadhHour, dirName, towardName, num, max, min, mean } from './util.js';

// Summary of one model over the next `hours` from now.
export function summarizeModel(md, th, hours = 24) {
  if (!md) return null;
  const T = md.hourly.time; const now = Date.now();
  const i0 = Math.max(0, T.findIndex((t) => t >= now - 30 * 60000));
  const i1 = Math.min(T.length, i0 + hours);
  const rows = [];
  for (let i = i0; i < i1; i++) rows.push({ t: T[i], d: diagnostics(buildProfile(md.hourly, i, LEVELS, md.elevation)), p: md.hourly.precipitation ? md.hourly.precipitation[i] : null });
  if (!rows.length) return null;
  const capeRows = rows.filter((r) => r.d.cape != null);
  const peak = capeRows.length ? capeRows.reduce((a, b) => (b.d.cape > a.d.cape ? b : a)) : rows[Math.min(rows.length - 1, 6)];
  const precip = rows.map((r) => r.p);
  const firstRain = rows.find((r) => r.p != null && r.p >= 0.2);
  const wettest = rows.reduce((a, b) => ((b.p || 0) > (a.p || 0) ? b : a), rows[0]);
  const vv700 = rows.map((r) => r.d.vv[700]).filter((v) => v != null);
  const vvUnit = md.units['vertical_velocity_700hPa'] || '';
  // Convert to w (m/s, positive up). If the source gives omega in Pa/s, use
  // w ≈ -omega / (rho g) with rho ≈ 0.9 kg/m³ at 700 hPa.
  const toW = /pa/i.test(vvUnit) ? (x) => -x / 8.8 : (x) => x;
  const favourable = rows.filter((r) => r.d.cape != null && r.d.cape >= th.capeWeak && (r.d.cin == null || Math.abs(r.d.cin) < th.cinCap));
  return {
    key: md.key, label: MODELS[md.key].label,
    capeMax: peak.d.cape, capeT: peak.t, cinAtPeak: peak.d.cin, liMin: min(rows.map((r) => r.d.li)),
    pw: peak.d.pw, rh700: peak.d.rh[700], rh500: peak.d.rh[500], rh850: peak.d.rh[850], dd700: peak.d.dd700, dd500: peak.d.dd500,
    lapse: peak.d.lapse75, steer: peak.d.steer, shear: peak.d.shear, lcl: peak.d.lclAgl, moist: peak.d.moist,
    t500: peak.d.t500, fzl: peak.d.fzl, sfc: peak.d.sfc, qflux: peak.d.qflux,
    precip24: precip.some((v) => v != null) ? precip.reduce((a, v) => a + (v || 0), 0) : null,
    precipMax1h: max(precip), firstRain: firstRain ? firstRain.t : null, wettestT: (wettest && wettest.p) ? wettest.t : null,
    vvUpMax: vv700.length ? max(vv700.map(toW)) : null, vvUnit,
    favHours: favourable.map((r) => r.t),
    missing: ['cape', 'convective_inhibition', 'lifted_index'].filter((v) => !md.hourly[v] || md.hourly[v].every((x) => x == null)),
  };
}

const pct = (x) => `${Math.round(x * 100)}٪`;

export function ensembleProb(ens, thresholdMm, hours = 24) {
  if (!ens || !ens.members.length) return null;
  const now = Date.now();
  const i0 = Math.max(0, ens.times.findIndex((t) => t >= now - 30 * 60000)); const i1 = Math.min(ens.times.length, i0 + hours);
  let yes = 0;
  for (const m of ens.members) { let s = 0; for (let i = i0; i < i1; i++) s += m[i] || 0; if (s >= thresholdMm) yes++; }
  return yes / ens.members.length;
}

function hoursRange(ts) {
  if (!ts.length) return null;
  const hrs = ts.map((t) => riyadhHour(t));
  const counts = new Array(24).fill(0); hrs.forEach((h) => counts[h]++);
  // most common contiguous block
  let best = null;
  for (let a = 0; a < 24; a++) if (counts[a]) {
    let b = a; while (b + 1 < 24 && counts[b + 1]) b++;
    const w = counts.slice(a, b + 1).reduce((x, y) => x + y, 0);
    if (!best || w > best.w) best = { a, b, w };
    a = b;
  }
  return best ? `${String(best.a).padStart(2, '0')}:00–${String((best.b + 1) % 24).padStart(2, '0')}:00` : null;
}

export function buildAnalysis({ place, modelData, ens, oro, obs, th }) {
  const S = MODEL_KEYS.map((k) => summarizeModel(modelData[k], th)).filter(Boolean);
  const out = { obs: [], forecast: [], interp: [], confidence: null, uncertainties: [], verdict: null };

  // --- Observation level -------------------------------------------------------
  if (obs && obs.metars && obs.metars.length) {
    for (const m of obs.metars) out.obs.push(`${m.name}: ${num(m.temp)}°م، نقطة الندى ${num(m.dewp)}°م، الرياح ${m.wdir === 'VRB' ? 'متغيرة' : dirName(Number(m.wdir))} ${num(m.wspd)} عقدة${m.wx ? `، الطقس: ${m.wx}` : ''} (رصد ${m.timeText}).`);
  } else out.obs.push('لم تصل أرصاد المطارات (METAR) الآن؛ قد يمنعها المتصفح أو المصدر. افتح طبقة المحطات في الخريطة.');
  if (obs && obs.sat) out.obs.push(`آخر صورة قمر صناعي متاحة: ${obs.sat}. التحليل الآلي لا يقرأ الصور؛ افحص قمم السحب الباردة يدويًا في طبقة الأشعة تحت الحمراء.`);
  else out.obs.push('صور الأقمار والبرق متاحة كطبقات في الخريطة؛ التحليل الآلي لا يقرأها.');
  out.obs.push('الرادار عبر RainViewer يغطي فقط حيث تشارك محطات رادار؛ إن ظهرت المنطقة داكنة في طبقة التغطية فلا يوجد رصد رادار منه.');

  if (!S.length) { out.forecast.push('تعذر جلب أي نموذج الآن.'); out.verdict = { level: 'unknown', text: 'لا يمكن التقييم دون بيانات النماذج.' }; return { ...out, summaries: S }; }

  // --- Forecast level ----------------------------------------------------------
  for (const s of S) {
    const parts = [];
    parts.push(s.capeMax != null ? `أعلى CAPE ${num(s.capeMax)} J/kg (${fmtDayHour(s.capeT)})` : 'CAPE غير متاح');
    if (s.cinAtPeak != null) parts.push(`CIN ${num(Math.abs(s.cinAtPeak))}`);
    if (s.liMin != null) parts.push(`أدنى LI ${num(s.liMin, 1)}`);
    if (s.pw != null) parts.push(`ماء قابل للهطول ${num(s.pw)} مم`);
    if (s.rh700 != null) parts.push(`رطوبة 700 ${num(s.rh700)}٪`);
    parts.push(s.precip24 != null ? `مطر 24 ساعة ${num(s.precip24, 1)} مم` : 'المطر غير متاح');
    if (s.firstRain) parts.push(`أول مطر ${fmtDayHour(s.firstRain)}`);
    out.forecast.push(`${s.label}: ${parts.join('، ')}.`);
  }
  const ensLines = [];
  for (const k of MODEL_KEYS) {
    const e = ens && ens[k]; if (!e) continue;
    const p1 = ensembleProb(e, th.rainAgree), p5 = ensembleProb(e, 5);
    if (p1 != null) ensLines.push(`${e.label}: احتمال ≥${th.rainAgree} مم خلال 24 ساعة ${pct(p1)}، و≥5 مم ${pct(p5)}`);
  }
  if (ensLines.length) out.forecast.push(`المجموعات: ${ensLines.join('؛ ')}.`);

  // --- Interpretation level ----------------------------------------------------
  const med = (f) => { const xs = S.map(f).filter((v) => v != null).sort((a, b) => a - b); return xs.length ? xs[Math.floor(xs.length / 2)] : null; };
  const cape = med((s) => s.capeMax), cin = med((s) => (s.cinAtPeak == null ? null : Math.abs(s.cinAtPeak))), li = med((s) => s.liMin);
  const pw = med((s) => s.pw), rh700 = med((s) => s.rh700), dd700 = med((s) => s.dd700), dd500 = med((s) => s.dd500);
  const lapse = med((s) => s.lapse), shear = med((s) => s.shear), lclv = med((s) => s.lcl);
  const rainModels = S.filter((s) => s.precip24 != null && s.precip24 >= th.rainAgree);
  const steerU = mean(S.map((s) => s.steer && s.steer.u)), steerV = mean(S.map((s) => s.steer && s.steer.v));
  const steer = steerU != null ? { from: (Math.atan2(-steerU, -steerV) * 180 / Math.PI + 360) % 360, speed: Math.hypot(steerU, steerV) } : null;

  const unstable = (cape != null && cape >= th.capeWeak) || (li != null && li <= th.liUnstable);
  const strong = cape != null && cape >= th.capeStrong;
  const moistOK = (pw != null && pw >= th.pwLow) || (rh700 != null && rh700 >= th.rh700Moist);
  const moistHigh = pw != null && pw >= th.pwHigh;
  const dryMid = (dd700 != null && dd700 >= th.ddDry) || (dd500 != null && dd500 >= th.ddDry) || (rh700 != null && rh700 < th.rh700Dry);
  const capped = cin != null && cin >= th.cinCap;
  const liftModel = S.some((s) => s.vvUpMax != null && s.vvUpMax > 0.05);
  const oroUp = oro && oro.w != null && oro.w > 0.02;

  let ready;
  if (unstable && moistOK && !capped) ready = { level: strong ? 'high' : 'mid', text: strong ? 'البيئة مهيأة للحمل الحراري، وعدم الاستقرار قوي.' : 'البيئة مهيأة للحمل الحراري بدرجة متوسطة.' };
  else if (unstable && !moistOK) ready = { level: 'low', text: 'يوجد عدم استقرار، لكن الرطوبة غير كافية لنمو سحب ممطرة واسعة.' };
  else if (unstable && capped) ready = { level: 'low', text: 'يوجد عدم استقرار، لكن طبقة مانعة (CIN مرتفع) تحتاج رفعًا قويًا لكسرها.' };
  else ready = { level: 'none', text: 'البيئة غير مهيأة للحمل الحراري العميق في الـ24 ساعة القادمة وفق النماذج.' };
  out.verdict = ready;

  out.interp.push({ q: 'هل البيئة مهيأة للحمل الحراري؟', a: ready.text + (cape != null ? ` (وسيط أعلى CAPE بين النماذج ${num(cape)} J/kg${li != null ? `، LI ${num(li, 1)}` : ''}${lapse != null ? `، معدل التناقص 700–500 hPa ${num(lapse, 1)}°م/كم` : ''}).` : '') });
  out.interp.push({ q: 'هل الرطوبة كافية؟', a: moistHigh ? `الرطوبة عالية (ماء قابل للهطول نحو ${num(pw)} مم).` : moistOK ? `الرطوبة كافية بدرجة متوسطة${pw != null ? ` (نحو ${num(pw)} مم)` : ''}${rh700 != null ? `، ورطوبة 700 hPa نحو ${num(rh700)}٪` : ''}.` : `الرطوبة محدودة${pw != null ? ` (نحو ${num(pw)} مم)` : ''}${rh700 != null ? `، ورطوبة 700 hPa نحو ${num(rh700)}٪` : ''}.` });
  out.interp.push({ q: 'هل توجد طبقة جافة تحد من نمو السحب؟', a: dryMid ? `نعم، الطبقات المتوسطة جافة${dd700 != null ? ` (فرق الحرارة ونقطة الندى عند 700 hPa نحو ${num(dd700)}°م)` : ''}. الجفاف يضعف الخلايا بالخلط ويزيد التبخر والرياح الهابطة.` : 'لا يظهر جفاف واضح في الطبقات المتوسطة.' });
  const liftParts = [];
  if (liftModel) liftParts.push('النماذج تُظهر حركة صاعدة عند 700 hPa في بعض الساعات');
  if (oro && oro.w != null) liftParts.push(oro.w > 0.02 ? `الرياح القريبة من السطح تصعد المنحدر المحلي (رفع تضاريسي تقديري ${num(oro.w * 100, 0)} سم/ث)` : oro.w < -0.02 ? 'الرياح القريبة من السطح تنحدر مع الميل المحلي (هبوط تضاريسي)' : 'لا رفع تضاريسي يُذكر من الرياح القريبة من السطح عند هذه النقطة');
  out.interp.push({ q: 'هل يوجد رفع أو تقارب محتمل؟', a: liftParts.length ? liftParts.join('؛ ') + '. للتقارب الأفقي افتح طبقة «التقارب» في الخريطة.' : 'لا تتوفر مؤشرات رفع كافية عند هذه النقطة؛ راجع طبقتي التقارب والرفع التضاريسي.' });
  out.interp.push({ q: 'هل توجد آلية واضحة لبدء الحمل؟', a: (oroUp || liftModel) && unstable ? 'محتملة: تسخين نهاري مع رفع تضاريسي أو صعود ديناميكي. يبقى توقيت كسر الطبقة المانعة غير مؤكد.' : unstable ? 'الآلية الأرجح هي التسخين النهاري على المرتفعات والحرات، ولا يظهر رفع ديناميكي واضح.' : 'لا آلية واضحة.' });

  // Areas to watch (interpretation, not a forecast of exact cells)
  const areas = [];
  if (unstable && moistOK) {
    areas.push('المرتفعات: الهدا والشفا وجرف الطائف (نشوء نهاري مبكر غالبًا)');
    if (dryMid || (lclv != null && lclv > 1500)) areas.push('الحرات شمال وشمال شرق مكة (تسخين قوي، والخطر الأكبر رياح هابطة)');
    if (steer && steer.from >= 45 && steer.from <= 180) areas.push('حوض مكة والجموم: رياح التوجيه من الشرق أو الجنوب الشرقي قد تنقل الخلايا وتياراتها الهابطة من الجرف نحوهما');
    if (moistHigh) areas.push('السهل الساحلي وجدة إذا تعزز التدفق الجنوبي الرطب');
  }
  out.interp.push({ q: 'ما المناطق التي تستحق المراقبة؟', a: areas.length ? areas.join('؛ ') + '.' : 'لا مناطق بارزة في الـ24 ساعة القادمة.' });

  const favTs = S.flatMap((s) => s.favHours);
  const win = hoursRange(favTs);
  out.interp.push({ q: 'ما الفترة الأكثر ملاءمة لنشوء الخلايا؟', a: win ? `بتوقيت مكة: نحو ${win}، وهي الساعات التي يتجاوز فيها CAPE ${th.capeWeak} J/kg مع CIN منخفض في نموذج واحد على الأقل.` : 'لا توجد ساعات تتحقق فيها شروط عدم الاستقرار مع طبقة مانعة ضعيفة.' });

  let hazard;
  if (!unstable && rainModels.length) hazard = 'أمطار خفيفة أو طبقية أكثر من خلايا رعدية.';
  else if (!unstable) hazard = 'لا خطر حملي يُذكر.';
  else if (lclv != null && lclv >= th.lclHigh && dryMid) hazard = 'رياح هابطة جافة وإثارة غبار، مع أمطار قليلة؛ قاعدة السحاب مرتفعة والطبقة تحتها جافة.';
  else if (moistHigh && steer && steer.speed < 5) hazard = 'أمطار غزيرة محلية مع حركة بطيئة للخلايا، وخطر سيول في الأودية.';
  else if (strong && shear != null && shear >= th.shearOrg) hazard = 'خلايا رعدية منظمة قد تعمّر وتتحرك، مع رياح هابطة وبَرَد محتمل.';
  else hazard = 'خلايا رعدية متفرقة قصيرة العمر، مع أمطار محلية ورياح هابطة.';
  out.interp.push({ q: 'ما الخطر الأساسي؟', a: hazard });

  if (steer) out.interp.push({ q: 'اتجاه الحركة المحتمل', a: `رياح التوجيه (متوسط 700–500 hPa) ${dirName(steer.from)} بسرعة نحو ${num(steer.speed * 3.6)} كم/س، أي أن الخلايا تميل إلى التحرك نحو ${towardName(steer.from + 180)}. هذا محسوب من النماذج، وليس مسارًا مرصودًا.` });

  // Confidence
  let score = 0;
  const capeVals = S.map((s) => s.capeMax).filter((v) => v != null);
  if (capeVals.length >= 2) { const lo = Math.min(...capeVals), hi = Math.max(...capeVals); if (hi < 2 * lo + 200) score++; else out.uncertainties.push(`تباين كبير في CAPE بين النماذج (${num(lo)}–${num(hi)} J/kg).`); }
  if (rainModels.length === 0 || rainModels.length === S.length) score++;
  else out.uncertainties.push(`النماذج غير متفقة على المطر: ${rainModels.map((s) => s.label).join('، ')} ${rainModels.length === 1 ? 'يُظهره' : 'تُظهره'} وغيرها لا.`);
  const pE = MODEL_KEYS.map((k) => ens && ens[k] ? ensembleProb(ens[k], th.rainAgree) : null).filter((v) => v != null);
  if (pE.length) { const avg = pE.reduce((a, b) => a + b, 0) / pE.length; if (avg < 0.2 || avg > 0.7) score++; else out.uncertainties.push(`احتمال المجموعات في المنطقة الوسطى (نحو ${pct(avg)})، أي أن النتيجة غير محسومة.`); }
  const missing = S.flatMap((s) => s.missing.map((v) => `${s.label}: ${v}`));
  if (missing.length) out.uncertainties.push(`متغيرات غير متاحة من المصدر: ${missing.join('، ')}.`);
  out.uncertainties.push('النماذج العالمية (9–13 كم) لا تمثل جبال مكة المحلية ولا تيارات الهبوط الباردة، فموقع الخلية الدقيق غير قابل للتوقع منها.');
  if (S.some((s) => s.sfc && s.sfc.p != null && s.sfc.p < 870)) out.uncertainties.push('النقطة مرتفعة: قيم 925 و850 hPa تحت سطح الأرض واستُبعدت من التحليل.');
  out.confidence = score >= 3 ? 'مرتفعة نسبيًا' : score === 2 ? 'متوسطة' : 'منخفضة';
  out.summaries = S;
  out.place = place;
  return out;
}
