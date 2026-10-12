// Static configuration: places, models, data endpoints, default thresholds.
// Coordinates are town/landmark centres (approximate, ±2 km). Elevations are NOT
// hard-coded: they are read live from the Copernicus DEM via Open-Meteo.

export const SITE = {
  name: 'موقع فهد العيسي لمتابعة الأحوال الجوية في محيط مكة المكرمة ومنطقة مكة المكرمة',
  short: 'طقس منطقة مكة',
  tz: 'Asia/Riyadh',
};

export const PLACES = [
  { id: 'makkah', name: 'مكة المكرمة', lat: 21.4225, lon: 39.8262, fav: true },
  { id: 'jumum', name: 'الجموم', lat: 21.617, lon: 39.698, fav: true },
  { id: 'bahrah', name: 'بحرة', lat: 21.400, lon: 39.450 },
  { id: 'taif', name: 'الطائف', lat: 21.270, lon: 40.416, fav: true },
  { id: 'hada', name: 'الهدا', lat: 21.366, lon: 40.281 },
  { id: 'shafa', name: 'الشفا', lat: 21.072, lon: 40.355 },
  { id: 'jeddah', name: 'جدة', lat: 21.543, lon: 39.173, fav: true },
  { id: 'rabigh', name: 'رابغ', lat: 22.799, lon: 39.035 },
  { id: 'khulais', name: 'خليص', lat: 22.137, lon: 39.330 },
  { id: 'lith', name: 'الليث', lat: 20.150, lon: 40.270 },
  { id: 'qunfudhah', name: 'القنفذة', lat: 19.127, lon: 41.079 },
  { id: 'turabah', name: 'تربة', lat: 21.214, lon: 41.633 },
  { id: 'khurmah', name: 'الخرمة', lat: 21.920, lon: 42.040 },
  { id: 'ranyah', name: 'رنية', lat: 21.257, lon: 42.849 },
  { id: 'muwayh', name: 'المويه', lat: 22.433, lon: 41.758 },
];

// Labels only. Real extents are visible as dark basalt in the satellite basemap.
export const TERRAIN_LABELS = [
  { name: 'حرة رهط (موضع تسمية تقريبي)', lat: 22.6, lon: 40.0 },
  { name: 'حرة كشب (موضع تسمية تقريبي)', lat: 22.85, lon: 41.35 },
  { name: 'جرف الحجاز / السراة (تسمية تقريبية)', lat: 20.75, lon: 40.55 },
];

// Static profile per place: terrain and the local factors that matter for weather.
// Descriptive text, not measured data.
export const PROFILES = {
  makkah: {
    terrain: 'حوض منخفض تحيط به سلاسل جرانيتية متقطعة (جبال مكة المحلية)، وتصب فيه أودية أبرزها وادي إبراهيم، وإلى الشرق وادي عرنة ثم وادي نعمان الصاعد نحو الهدا.',
    factors: ['جبال مكة المحلية أضيق من خلية أي نموذج عالمي، فلا تظهر في النماذج؛ أثرها تقارب صغير وتسخين للمنحدرات المشمسة.', 'يصل النسيم البحري من الغرب والشمال الغربي بعد الظهر عبر بحرة والجموم.', 'تيارات الهبوط الباردة من خلايا الهدا والشفا تندفع غربًا نحو الحوض عند توجيه شرقي أو جنوبي شرقي.', 'سيول سريعة في الأودية الحضرية حتى مع أمطار قصيرة المدة.'],
  },
  jumum: {
    terrain: 'على وادي فاطمة شمال غرب مكة، في ممر منخفض نسبيًا بين السهل الساحلي والداخل.',
    factors: ['ممر للنسيم البحري والرطوبة الدنيا نحو الداخل.', 'منطقة محتملة لالتقاء النسيم بالتدفق الشمالي أو الشرقي.', 'جريان وادي فاطمة يتأثر بأمطار المرتفعات شرقه.'],
  },
  bahrah: {
    terrain: 'سهل منخفض بين جدة ومكة.',
    factors: ['يصله النسيم البحري مبكرًا قبل مكة.', 'رطوبة سطحية أعلى من مكة غالبًا.'],
  },
  taif: {
    terrain: 'هضبة مرتفعة خلف جرف الحجاز، تنحدر تدريجيًا شرقًا نحو نجد.',
    factors: ['ضغط السطح أقل من 850 hPa تقريبًا، فقيم 925 و850 hPa فوقها مستقرأة لا حقيقية.', 'تسخين نهاري سريع وتقارب مع الرياح الصاعدة على الجرف.', 'خلايا الظهيرة تتحرك مع رياح التوجيه 700–500 hPa.'],
  },
  hada: {
    terrain: 'حافة جرف الحجاز بين مكة والطائف، بانحدار حاد غربًا نحو وادي نعمان.',
    factors: ['رفع قسري للتدفق الغربي والجنوبي الغربي الرطب.', 'المنحدرات المشمسة تسخن صباحًا وتطلق رياحًا صاعدة.', 'كثيرًا ما تكون أول مكان يظهر فيه الركام المتطور.'],
  },
  shafa: {
    terrain: 'أعلى أجزاء المرتفعات جنوب الطائف.',
    factors: ['نشوء مبكر للخلايا مع رطوبة كافية ورياح صاعدة.', 'قيم 850 hPa فوقها تحت سطح الأرض.'],
  },
  jeddah: {
    terrain: 'سهل ساحلي منخفض (تهامة) يحده البحر الأحمر غربًا والمرتفعات شرقًا، وتعبره أودية تنحدر من الشرق.',
    factors: ['رطوبة دنيا عالية وتأثير مباشر للبحر الأحمر.', 'أمطارها الغزيرة ارتبطت بأنظمة منظمة وخطوط قص مع منخفض البحر الأحمر.', 'سيول الأودية القادمة من الشرق.'],
  },
  rabigh: { terrain: 'ساحل شمال جدة.', factors: ['تأثير بحري ونسيم.', 'تتأثر أحيانًا بامتداد منطقة التقارب نحو الشمال.'] },
  khulais: { terrain: 'سهل وأودية داخلية بين الساحل والمرتفعات شمال شرق جدة.', factors: ['تقارب محتمل بين النسيم والتدفقات الداخلية.'] },
  lith: { terrain: 'ساحل جنوب جدة تقترب منه المرتفعات.', factors: ['قرب المرتفعات من الساحل يقرّب الرفع التضاريسي من مصدر الرطوبة.'] },
  qunfudhah: { terrain: 'ساحل جنوبي المنطقة.', factors: ['أقرب إلى منطقة تقارب البحر الأحمر (نحو 18–19 درجة شمالًا) في الخريف والشتاء.'] },
  turabah: { terrain: 'هضبة داخلية شرق الطائف.', factors: ['حمل حراري نهاري على الهضبة مع رطوبة متوسطة كافية.'] },
  khurmah: { terrain: 'هضبة داخلية.', factors: ['رطوبة دنيا أقل عادة؛ خطر رياح هابطة جافة مع قاعدة سحاب مرتفعة.'] },
  ranyah: { terrain: 'هضبة داخلية جنوب شرق المنطقة.', factors: ['تتأثر بالتدفقات الجنوبية القادمة من المرتفعات الجنوبية.'] },
  muwayh: { terrain: 'هضبة داخلية شمال شرق الطائف.', factors: ['تسخين نهاري قوي؛ قاعدة سحاب مرتفعة غالبًا.'] },
};

export const DEFAULT_PROFILE = {
  terrain: 'نقطة اختيرت من الخريطة.',
  factors: ['الارتفاع مأخوذ من نموذج الارتفاع الرقمي، والطبيعة التضاريسية تُقرأ من طبقة التضاريس والقمر الصناعي.'],
};

// Model families. Each slot lists API identifiers to try in order (Open-Meteo has
// renamed identifiers over time). Variables missing from the first source are
// filled from the next one, and the page shows which source each value came from.
export const MODELS = {
  ecmwf: {
    label: 'ECMWF IFS', color: 'var(--m-ecmwf)',
    sources: [
      { ids: ['ecmwf_ifs'], label: 'IFS HRES 9 كم' },
      { ids: ['ecmwf_ifs025'], label: 'IFS 0.25°' },
    ],
    meta: ['ecmwf_ifs', 'ecmwf_ifs025'],
    ens: ['ecmwf_ifs025', 'ecmwf_ifs025_eps'],
    ensLabel: 'ECMWF ENS 0.25°',
  },
  gfs: {
    label: 'GFS', color: 'var(--m-gfs)',
    sources: [{ ids: ['gfs_global', 'ncep_gfs_global', 'gfs_seamless', 'ncep_gfs_seamless'], label: 'GFS 0.11°/0.25°' }],
    meta: ['ncep_gfs013', 'ncep_gfs025'],
    ens: ['gfs025', 'ncep_gefs025', 'gfs025_eps'],
    ensLabel: 'GEFS 0.25°',
  },
  icon: {
    label: 'ICON العالمي', color: 'var(--m-icon)',
    sources: [{ ids: ['icon_global', 'dwd_icon_global', 'icon_seamless', 'dwd_icon_seamless'], label: 'ICON 13 كم' }],
    meta: ['dwd_icon'],
    ens: ['icon_global', 'icon_seamless', 'icon_seamless_eps', 'dwd_icon_global_eps'],
    ensLabel: 'ICON-EPS 26 كم',
  },
};
export const MODEL_KEYS = ['ecmwf', 'gfs', 'icon'];

export const LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300];
export const SURFACE_VARS = [
  'temperature_2m', 'dew_point_2m', 'relative_humidity_2m', 'surface_pressure',
  'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m', 'precipitation', 'showers',
  'cloud_cover', 'cape', 'convective_inhibition', 'lifted_index', 'freezing_level_height',
  'boundary_layer_height', 'total_column_integrated_water_vapour', 'shortwave_radiation',
];
export const LEVEL_VARS = ['temperature', 'relative_humidity', 'wind_speed', 'wind_direction', 'geopotential_height'];
export const VV_LEVELS = [850, 700, 500];

export const ENDPOINTS = {
  forecast: 'https://api.open-meteo.com/v1/forecast',
  ensemble: 'https://ensemble-api.open-meteo.com/v1/ensemble',
  elevation: 'https://api.open-meteo.com/v1/elevation',
  previous: 'https://previous-runs-api.open-meteo.com/v1/forecast',
  meta: (path) => `https://api.open-meteo.com/data/${path}/static/meta.json`,
  rainviewer: 'https://api.rainviewer.com/public/weather-maps.json',
  eumetview: 'https://view.eumetsat.int/geoserver/ows',
  eumetviewCaps: (ws) => `https://view.eumetsat.int/geoserver/${ws}/ows?service=WMS&version=1.3.0&request=GetCapabilities`,
  metar: (ids) => `https://aviationweather.gov/api/data/metar?ids=${ids}&format=json&hours=3`,
};

// Daily report files: raw GitHub first (updates within minutes of the noon commit),
// then the same folder on this site.
export const REPORT_BASES = [
  'https://raw.githubusercontent.com/Fofo4280-cell/makkah-weather/main/reports/',
  'reports/',
];

export const METAR_STATIONS = [
  { icao: 'OEJN', name: 'مطار الملك عبدالعزيز – جدة', lat: 21.68, lon: 39.16 },
  { icao: 'OETF', name: 'مطار الطائف', lat: 21.48, lon: 40.54 },
  { icao: 'OEMA', name: 'مطار المدينة المنورة', lat: 24.55, lon: 39.71 },
  { icao: 'OEYN', name: 'مطار ينبع', lat: 24.14, lon: 38.06 },
];

// Forecast grids for map layers (multi-location requests).
export const GRIDS = {
  fine: { label: 'مكة والجرف (0.1°)', lat0: 20.9, lat1: 22.1, lon0: 39.1, lon1: 40.6, step: 0.1 },
  near: { label: 'مكة – الطائف (0.2°)', lat0: 20.6, lat1: 22.6, lon0: 38.8, lon1: 41.0, step: 0.2 },
  region: { label: 'منطقة مكة كاملة (0.5°)', lat0: 18.5, lat1: 24.0, lon0: 38.0, lon1: 43.5, step: 0.5 },
};

export const GRID_SFC_VARS = [
  'precipitation', 'cape', 'lifted_index', 'convective_inhibition', 'surface_pressure',
  'wind_speed_10m', 'wind_direction_10m', 'relative_humidity_2m',
];
export const GRID_LEVEL_VARS = [
  'temperature_925hPa', 'relative_humidity_925hPa', 'wind_speed_925hPa', 'wind_direction_925hPa',
  'relative_humidity_700hPa', 'wind_speed_700hPa', 'wind_direction_700hPa', 'vertical_velocity_700hPa',
];
export const GRID_VARS = [...GRID_SFC_VARS, ...GRID_LEVEL_VARS];

// First-guess thresholds for a dry, high-cloud-base environment. Editable in Settings.
export const DEFAULT_THRESHOLDS = {
  pwLow: 20, pwHigh: 30,          // mm
  rh700Moist: 60, rh700Dry: 35,   // %
  ddDry: 10,                      // T - Td at 700/500 hPa, °C
  capeWeak: 300, capeStrong: 1000,// J/kg
  cinCap: 100,                    // |CIN| J/kg
  liUnstable: -2,
  lapseSteep: 7,                  // °C/km, 700-500 hPa
  shearOrg: 12.5,                 // m/s, 10 m to 500 hPa
  lclHigh: 2500,                  // m above ground
  rainAgree: 1,                   // mm in 24 h for "model shows rain"
};

// ---------------------------------------------------------------- escarpment & valleys
// Crest points where cells usually form. Boxes are approximate and drawn on the map so
// they can be checked against the satellite basemap.
export const ESCARP = {
  crests: [
    { id: 'hada', name: 'الهدا', lat: 21.366, lon: 40.281 },
    { id: 'shafa', name: 'الشفا', lat: 21.072, lon: 40.355 },
  ],
  boxes: {
    valleys: { name: 'مساقط الأودية جنوب مكة', lat0: 20.95, lat1: 21.35, lon0: 39.80, lon1: 40.20 },
    harrat: { name: 'حرة رهط (الجزء الجنوبي)', lat0: 22.10, lat1: 22.90, lon0: 39.70, lon1: 40.30 },
    ref: { name: 'أرض غير بازلتية للمقارنة', lat0: 22.10, lat1: 22.90, lon0: 40.55, lon1: 40.85 },
  },
};

export const ESCARP_DEFAULTS = {
  inflowMin: 1.5,   // m/s, upslope wind component at the crest that keeps feeding cells
  steerWeak: 4,     // m/s, steering below this lets cells stand over the crest
  steerFast: 12,    // m/s, steering above this moves cells quickly away
  downMin: 2,       // m/s, steering component toward the valleys (downslope, west)
  albModel: 0.30,   // surface albedo the global models are assumed to use over the harrat
  albBasalt: 0.13,  // dark basalt lava field
  fH: 0.5,          // share of the extra absorbed sunlight that becomes sensible heat
};
