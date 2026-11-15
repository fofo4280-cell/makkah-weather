# Fahad's weather project — handoff for a new Claude session

Last updated: 15 Nov 2026 (evening). Written for Claude, to continue the work without the long history.

## 1. How to work with Fahad (hard rules)

- **Reply in Arabic only, every message.** Use Arabic-Indic digits (٠١٢٣…) and no Latin letters or English words. Mixed scripts flip the right-to-left text on his phone. File contents and code may use Latin.
- He works from a **phone only**. Do every technical step end to end. Name only the step that needs him.
- **Stability phase** (decided 12 Nov 2026): fix and stabilise, no new features unless he asks explicitly.
- Weather questions are for **understanding**. Give deep, mechanism-level answers with numbers. A question is not a build request.
- In Makkah analyses, always account for **Makkah's own mountains** (Nour, Thawr, Arafat/Kabkab ridges), not only the escarpment.
- **Place names** in reports must be well known (سوق عكاظ، العرفاء، طريق حضن، عشيرة، وادي جليل…). Never use obscure districts.
- A wave's **strongest day is its most widespread rain day**, judged from the oscillation drivers merged with the forecast rain spread.
- **Tweets** he asks for: lively, field-observer tone, a reading rather than a decision. Always end by attributing to God, e.g. «والأمر كله لله». Usually ≤150 characters.
- **Never accept an accuracy loss for speed.** The split-grid idea was rejected.
- No zip files. Deliver single files.

## 2. Where things are

- Repo: `fofo4280-cell/makkah-weather` (public). Site: https://fofo4280-cell.github.io/makkah-weather/ (GitHub Pages from `main`). Model page `/model/`, oscillation/report page on the main site.
- `main`: the site and all workflows (`.github/workflows`).
- `saudi-wrf`: all code (`server/…`). `saudi-wrf-next` is a force-pushed mirror of it. **Push code to both.**
- Data branches:
  - `model-data` (west d01 9 km + d02 3 km), `model-data-sa` (Kingdom 9 km), and `model-data-nw|n|c|e|se` (regional 3 km grids). Each holds `runs.json` and `status.json`.
  - `climate-data` holds `mjo.json`, the report and the figures.
  - Others: `ingr-data`, `case-study`; `model-data-test-*` and `speed*` are old tests.
- Dispatch workflows only via REST:
  `gh api -X POST repos/fofo4280-cell/makkah-weather/actions/workflows/<file>/dispatches -f ref=main -f 'inputs[x]=y'`
  (GraphQL is blocked). Artifacts cannot be downloaded through the proxy, so data goes through branches.
- **Pushing `climate.yml` to main starts a Climate run** (push paths). Cancel it at once.

## 3. The model (WRF 4.7.1 on free GitHub runners)

- **Grids:**
  - The **Kingdom at 3 km** = west d02 plus nw, n, c, e, se. This is what the maps and all reports use (decided 13 Nov).
  - The 9 km grids (sa, west d01) still run but are hidden. Their only remaining role: the gate and keeper read `model-data-sa/runs.json` to know whether a cycle exists.
- **Cycles:** **12 UTC only since 15 Nov 2026 (Fahad).** The 00 UTC (daytime) cycle is stopped: no crons, the keeper never starts it, and the gate refuses a schedule firing before 12 UTC. It can still be run by hand (`saudi-model.yml` dispatch with `cycle=YYYYMMDD00`), only if Fahad asks.
  - 12Z finishes about 01–02 Makkah.
  - (00Z, when it ran, finished about 12–13 Makkah.)
  - GFS 00Z f033 is on AWS about 03:45 UTC; 12Z about 15:45 UTC.
- **Jobs** (`wrf-job.yml`, called by `saudi-model.yml`): each grid runs in two parts.
  - Part 1 runs to hour 15, then a restart handover; part 2 runs to 33.
  - Time budget is 335 min from job start, then it publishes what is done.
- **Watchdog** (`run_cycle.sh`): if the WRF log is silent for 25 min, restart WRF once; the second time, stop. Added after the 12 Nov west part-2 hang.
- **Gate** (`saudi-model.yml`):
  - Skips if `runs.json` already has the cycle.
  - Waits up to 280 min for the GFS f033 file **on AWS** before starting jobs. Since 13 Nov a schedule fired hours early waits here, not inside the jobs.
  - Concurrency group `saudi-model`, no cancel.
- **Schedules:** GitHub crons are unreliable (often missed or hours late). The crons are 47 14, 13 15, 41 15, 7 16 (UTC); the morning ones were removed on 15 Nov.
- **Keeper** (`keeper.yml`): runs continuously and checks every 5 min. It re-dispatches itself every 5 h 40 min, with an hourly cron revival. It starts whatever is missing:
  - model cycle 12 between 15:50 and 23:00 UTC (cycle 00 removed on 15 Nov: on 15 Nov it still started the 00Z run at 03:52 UTC, which is why Fahad saw a daytime run);
  - the night climate run between 21:00 and 23:59 UTC.
- **Rain map `rain24`:** hours 9-33, i.e. 12 to 12 Makkah time (midnight to midnight in the 12Z run, noon to noon in the 00Z run); label «المطر التراكمي من ١٢ إلى ١٢» (Fahad, 14 Nov 2026).
- **Basemap (model page, 15 Nov 2026, Fahad):** Esri World Imagery toned down by CSS (`.sat-dark`: navy sea, muted brown land) is the default (localStorage `swrf.base3`); OpenTopoMap removed. Light base = Esri World_Topo_Map, detailed base = CyclOSM (Fahad's picks, 15 Nov); the page's own Arabic names show only on the satellite and dark bases. Thin dark country borders from `model/borders.json` (Natural Earth 1:50m, Saudi view) in the «الحدود» overlay with the regions; Arabic names drawn by the page (countries and seas, main cities from zoom 6). Hillshade is off by default. The container cannot reach the tile hosts: previews are screenshotted on a GitHub runner (push-triggered workflow on a preview branch).
- **700 hPa humidity and instability maps (15 Nov 2026, Fahad):** hourly `rh700` (relative humidity at 700 hPa, green 10 % bands from 30 %) and `cape` (most-unstable CAPE: highest theta-e parcel in the lowest 300 hPa, pseudo-adiabatic, virtual temperature; sqrt scale 100-5000 J/kg, yellow → red → purple), computed in `products.rh700_cape_from_frame` on every grid of both runs. Checked against GFS MUCAPE: correlation 0.97, ours about 20 % lower. First run with them: the ECMWF-driven 12Z run of 15 Nov (the GFS run of that night started before the change). In Arabic call CAPE «طاقة عدم الاستقرار».
- **Maps:** PNG with banded palettes. The REFL palette is 5 dBZ bands, blue → green → yellow → red → purple. Model page assets are versioned `v=2026111xx`.

## 3b. The ECMWF-driven run (added 15 Nov 2026, Fahad: "accuracy first")

- `saudi-model-ec.yml`: the same six 3 km grids (west d02 + nw, n, c, e, se, each in its 9 km parent), driven by **ECMWF IFS open data** (`ic: ecmwf` → `server/ecmwf_ic.py` writes WPS intermediate files; ungrib not used). No 9 km Kingdom job. Concurrency group `saudi-model-ec`, so it never queues behind the GFS run.
- Data: 0.25° (~28 km), 13 pressure levels + surface + 4 soil layers, 3-hourly, downloaded from data.ecmwf.int (AWS fallback). The native 9 km IFS is not free (paid licence): 0.25° is the best freely available. Weakness: fewer low levels than GFS (no 975/950/900/800), so the marine layer starts coarser; WRF builds it in the first hours.
- Branches: `model-data-ec` (west) and `model-data-ec-<id>`. The reports, `ourmodel.load` and the climate run do **not** read them (comparison only, for now).
- 12 UTC cycle only. ECMWF hour 33 is on AWS about 19:34 UTC. Crons 18:47, 19:13, 19:41, 20:07 UTC; the gate waits up to 280 min for hour 33; the keeper starts it from 19:45 to 23:59 UTC if `model-data-ec/runs.json` lacks the cycle. Run ~6.5 h, so complete about 02:30 UTC (05:30 Makkah). 6 runners beside the GFS run's 7 (limit 20).
- First full test: cycle 2026111500, dispatched 11:15 UTC on 15 Nov (download 3 min, WPS + real under 1 min). 00Z runs are hidden on the page, so this test does not show there.
- Model page: two tabs **GFS / ECMWF** under the product list (`#modelTabs`, saved in localStorage `swrf.model`). Switching reloads runs, maps, cities and status from the chosen branches and keeps the same valid time. The 1 km nest is GFS-only.
- Plan: follow the 22-24 Nov Red Sea cut-off low with both; Fahad will judge which places the rain better (lesson: the GFS-driven run missed the 10 Nov stratiform rain over Jeddah/Makkah).

## 4. Reports pipeline (`server/climate`)

- `climate.yml` runs nightly. Crons 33 20, 7 21, 43 21 UTC, plus the keeper.
  - Its `check` job skips if `mjo.json` cycle == `date -u -d '12 hours ago'` + `12`. This was fixed on 13 Nov, after late firings after midnight re-ran it.
  - It runs `daily.py`: MJO/RMM, filtered MJO component (`mjofilt.py`), warm/cold event, Rossby waves, PW, troughs, ingredients index, the `diag.py` diagnosis, and the report (`bigreport.py`).
  - Since 14 Nov: **tropical waves in chi200** (`wkfilt.py`, Wheeler-Kiladis by wavenumber, period and phase speed): Kelvin family (eastward, 2-30 d, 8-60 m/s, k 1-9) and Rossby family (westward, 5-90 d, 0.5-25 m/s, k 1-9). It needs the long chi history, so `HIST_DAYS` = 400. Output in `mjo.json`: `tw` (`kel_ksa`, `ros_ksa` over the Kingdom box, cores, `*_ref` = past std) and `marks` (MJO core, warm and cold event longitude per forecast day).
  - Belt maps (`figures.draw_belt`): one frame 0-360, 35S-35N, 3000 px, coastlines/borders 1:50m, marker lines, for `wc`, `wcd`, `mjoz`, `mjop`, `kel`, `ros` (with divergent-wind arrows). The page's «اللوحة الاستوائية الشاملة» card stacks wc, mjoz, kel, ros, scrolling together.
  - The Rossby family is the sixth driver in `bigreport.strength` (0..1 = -ros/(2 ref)), total capped at 5 (Fahad, 14 Nov). Kelvin is only named in the text (for/against), not scored: over the Kingdom box it showed no relation to rain.
  - Compute takes about 15 min (was 8).
  - Its last step waits for the 12Z 3 km runs (until about 02:45 UTC) and rebuilds the report from them.
- **Everything daytime is gone (Fahad, 14–15 Nov 2026): the midnight report from the evening (12Z) runs is the only report.**
  - The 00Z model cycle no longer runs (section 3).
  - `ourmodel.load` skips every run whose id ends in `00`, so no report can read a daytime run, even an old one.
  - `refresh_report.py` accepts only `midnight`; the noon mode exits.
  - `rain-noon.yml` became `rain-midnight.yml`: by hand only, rewrites the night rain table from the evening runs (a repair; climate.yml does it nightly).
  - The model page (`model/app.js`) lists only 12Z runs and hides any old `rain_noon` section.
  - The main site's «التقرير» tab (the Open-Meteo ECMWF/GFS/ICON report written about noon) was removed with `daily-report.yml`, `scripts/daily-report.mjs` and `reports/`.
  - `rain-midnight.yml` **shares the concurrency group with climate.yml**. A dispatched rewrite queues behind a climate run that is waiting for the 3 km runs. Open issue: separate them without letting both overwrite `climate-data`.
- **Evening plains storms (`plains.py`, 15 Nov 2026, Fahad: "write it when the tools support it, even if our model misses it; no section of its own; nothing when nothing is found").** The pattern: afternoon storms on the mountains, their cold outflow runs down into the hot humid plain (with the sea breeze) and new cells start there between Maghrib and Isha; weak steering keeps them in place and the wadis bring the mountain flood down. Case: 15 Nov floods on the Al-Qunfudhah plains while our 3 km run had 0.3 mm there.
  - Five plains, each with its mountains just east (lat band boxes in `PLAINS`): Jazan Tihama (region جازان), Asir Tihama/Muhayil (عسير), Al-Qunfudhah + Baha Tihama, Al-Lith/Adham, Makkah/Al-Jumum/Bahra (all مكة المكرمة).
  - daily.py step 8c2 reads GFS 0.25 of the report day (09, 12, 15, 18, 21 UTC: PW, MUCAPE 180-0, RH700, winds 850/700/500/10 m, T/Td 2 m, APCP, terrain, land) into `mjo.json` `plains` {day, cycle, rows}.
  - Six enhancers: PW >= 130 % (page box: southwest south of 20N, west north of it) or >= 40 mm; Td >= 19 C (Al-Lith 18, Makkah 17); plain CAPE >= 1000; mountain storms (GFS rain >= 1 mm 12-18 Makkah, or mountain CAPE >= 300 with RH700 >= 60 %, or **our model's mountain rain >= 5 mm**); steering < 5 m/s or westward; plain wind toward the mountains. Named only with mountain storms + plain CAPE >= 500 + some moisture, and 4+ enhancers; confidence 4 low, 5 medium, 6 high.
  - `rainreport.plains_words` adds one sentence to that region's «منطقة …» line (a dry region gets its own line), and says «ولا يظهره نموذجنا على السهل» when our run has < 2 mm on the plain 17-24 Makkah.
  - Tested 1-15 Nov: silent on the dry days 1, 5, 8 Nov; names the southern plains on the wet days 10-15 Nov; on 15 Nov names Al-Qunfudhah (high) and Al-Lith (medium) where our run had nothing.
- `ourmodel.load`:
  - **3 km grids only** (dx > 5 km skipped).
  - For each grid, takes the newest run that covers ≥90 % of the hours of the best one.
- `rainreport.py` + `sa_geo.locate()` give rain places from the OSM gazetteer (`sa_osm.json`, built by `gazetteer.yml`). A known place within 10 km wins, then a village within 4 km, then a road or wadi within 1.5 km. Otherwise the text gives distance and direction («٢٧ كم غرب بيش»), and the table gives direction only («غرب بيش»).
- **Report sections (rewritten 14-15 Nov 2026, Fahad: concise, methodical, practical):** «الخلاصة» (today's kind and collision zones, current wave, next wave, strongest wave) → rain table (evening 12Z run alone, ~2 AM Makkah; Fahad chose this over a 06Z run, accuracy first) → «تشخيص اليوم» (storm kind from `pattern.py`, collision zones from `collide.py`, then `diag.py`: trough path, cold aloft, PW, winds by level, steering, back-building) → «قراءة العوامل» in a fixed order, slowest to fastest: MJO phase, component at 800, Rossby then Kelvin (chi200), warm event, moisture, troughs; then the current wave → «الموجات القادمة», ending with one «المصادر والمنهج» line.
  - `collide.py`: afternoon (08-14 UTC) convergence of the 850 hPa wind (10 m where the ground is above 870 hPa), GFS 0.25, smoothed ~40 km, ≥ 2e-5 /s with PW ≥ 20 mm, wide areas split into cores; up to 4 zones named with the winds that meet. Test on 24 wide-rain days: 62 % of named zones had GFS rain ≥2 mm within 50 km vs 26 % base (925 hPa and 10 m alone were worse). It replaced the 925 hPa map on the model page (removed 14 Nov) and the old 925 numbers.
  - `pattern.py` + `t500_clim.npz`: 500 hPa temperature at 12Z against a GFS normal (902 analyses 2021-2026, 3 harmonics; spread ~2 °C). ≤ -2 °C upper cooling, -1 to -2 mixed, else thermal convection.
  1. the drivers' movement over the whole data range: isolated MJO component (brake/support spans, extremes, envelope centre moving to a new cycle), warm event in or out of the favourable sector (250–55°E), MJO phases;
  2. every wave in range (`wave_list`): kind mixed/tropical/troughs, grade, peak, drivers for and against, regions reached; it says so when the strongest wave is not the nearest;
  3. the nearest wave in detail, with day-by-day scenario and nightly tracking (`wave_watch`).
- **Ingredients index** (`ingredients.py`, `ingr_coef.json`): logistic model of ≥5 mm on 1° GFS fields, quantile-mapped to rain-spread units. Weights against GFS rain: 0.7 up to 5 days, 0.5 up to 8, 0.3 beyond.

## 5. Study tools (print to the Actions log, publish nothing)

- `soundings.yml` (`soundings.py CYCLE FIRST LAST STEP`): GFS 0.25 soundings at 8 western points (sea W of Jeddah, Jeddah, Bahra, Jumum, Makkah, Sharaie, Hada, Taif). Gives SB/MU CAPE, CIN, LCL/LFC, lapse rates, RH by layer and the wind profile.
- `far-study.yml` (`europe_study.py FIRST LAST [LAT LON]`; Istanbul by default): GFS pattern (trough/ridge longitude, poyraz/lodos pressure difference, Black Sea minus T850), GEFS 31-member daily rain/T850 probabilities, and ECMWF open data (tries the ecmwf, azure, aws mirrors).
- `case-study.yml` (`case_study.py`): track of an upper low with maps.
- `ingr-backfill.yml`: refits the index.
- `server/ecmwf_ic.py`: ECMWF open data → WPS intermediate files. Built earlier for an ECMWF-driven test (branch `model-data-ecmwf`), then shelved by Fahad.

## 6. Lessons from the last days (do not repeat)

- GitHub schedules missed the morning model run and the noon update several days running. The keeper covers this. Always check that a run actually started.
- 12 Nov: the west part 2 hung for 5 h reading restart files, which delayed everything after it. Fixed by the watchdog.
- 13 Nov: a schedule fired at 12:06 UTC and its jobs gave up waiting for GFS 5 min before the files came. Fixed by the gate waiting on AWS.
- The noon table did not change because of a tie between runs. Fixed by choosing the newest run with ≥90 % coverage.
- Do not promise "within minutes" for an update that may queue behind the climate run.
- Background watchers in this environment die on container restarts and after 2 h. Re-check state instead of trusting them.

## 7. Meteorology learned with Fahad (use it)

- **Tihama-first regime** (13 Nov, verified by his photos):
  - Conditions: moist marine low levels, CIN ≈ 0 by midday, dry 650–450 hPa layer, cold aloft, SW mid-level steering.
  - Sequence: cumulus over the plains grows and collapses from mid-morning. Each generation moistens the mid-levels (self-preconditioning). The first tower breaks through about 12:30, and its top glaciates.
  - Cells form over the plains (Makkah/Jumum, Jazan to Makkah), rain heaviest on the eastern edges of the plains and the lower foothills, then climb to the harrat and Taif.
  - **Our 3 km model missed the plains start** and put rain on the plateau only. The likely cause is the gray-zone shallow cumulus not moistening the mid-levels. A shallow-cumulus option test is pending.
- Fahad observes the **evening (12Z) run places rain better than the morning (00Z) run**. Likely cause: 6–12 h spin-up, since the 00Z run's afternoon falls at hours 6–15. Log it for verification before acting.
- «العارض الشرقي» for Makkah: in the evening, 750–700 hPa winds turn E/SE, the sea breeze arrives from the west, and outflows descend from Hada/Sharaie. Convergence forms east of Makkah and propagates west. The window closes when T500 warms after about 21:00.
- Sea by day: the descending branch of the sea breeze, a shallow marine layer, and a lid from the land-air return flow. Sea and Jeddah convection come at night or dawn.

## 7b. Oscillation methodology checks (14 Nov 2026)

- Fahad's reference maps ("SCORPION ENGINE", Dr Khalid's method) put the MJO core at 38E on 13 Nov; ours 93E. Checked: our numbers reproduce exactly; no filter end delay (82 past days, perfect 15-day forecast: corr 0.90, amplitude 1.05, best at lag 0); no wavenumber/period/core definition gives 38E (82-118E). 38E is the Ethiopian highlands and his field (+-250 m, terrain detail) is not a pure MJO-filtered field. **Core and component left unchanged.**
- 24 wide rain days (>= 8 % of the Kingdom), Dec 2025-Nov 2026: component supportive 71 % (alternatives 58-75 %); **Rossby family over the Kingdom supportive 92 %** (base 52 %; rain 4.4 % vs 0.2 % of the Kingdom on strongly negative vs strongly positive days); Kelvin over the Kingdom 38 %.
- Our Kelvin panel reproduces his (13 Nov: equatorial minimum 43E, -5.9).

- **The 25-season test (15 Nov 2026, `tropics-study.yml` with long=yes, `tropics_long.py`; CHIRPS v2 via the IRI library, RMM, Nino 3.4, DMI, NCEP R1 500 hPa and PW via PSL THREDDS):**
  - Daily share explained (cross-validated, leave one season out): tropics 2-8 %, troughs+moisture 11-23 %, both 13-24 %. The tropics add 1-3 % beyond the troughs.
  - Monthly: correlation with the share of favourable-MJO days 0.12 (Hijaz) to 0.32 (north); tropics together explain 0-9 % cross-validated.
  - **Phase odds (amplitude >= 1), share of the mean daily spread.** Nov-Jan, Hijaz: phase 1 224 %, phase 8 169 %, phases 6-7 140 %, phases 3-5 35-49 %. Feb-Apr, centre: phase 1 200 %, phase 8 174 %, phases 3-5 20-35 %. Phase 2 is near or below normal: the wet phases are 8 and 1 (then 7); phase 6 is wet in Nov-Jan and dry in Feb-Apr except the north.
  - Whole seasons (25): correlation with IOD +0.49 (Hijaz +0.58), ENSO +0.41, favourable-MJO share +0.29. Wettest Kingdom seasons: 2025/26, 2018/19, 2022/23, 2023/24. Driest: 2007/08 (La Nina), 2014/15, 2002/03, 2011/12.
  - **Spring check (`tropics_spring.py`, long=spring on run 43657761748).** March and April are the Kingdom's wettest months: spread 4.0/3.6 % against 1.6-2.2 % in Nov-Jan. Centre and southwest peak sharply; the Hijaz has a Nov peak and a larger Mar-Apr peak in CHIRPS.
    - On spring wide-rain days, 500 hPa is below its running mean on 60-78 % of days: -10 to -20 m, or -16 to -25 m against the calendar. Troughs exist but are shallower than the winter troughs in the north.
    - Moisture dominates in spring: 51-58 % of the rain falls on PW-surge days (>= +3 mm), against 30-37 % on trough days. PW on wide days is 21-26 mm, against 16-20 mm on all days.
    - The folk saying (spring rain is the leftover of the winter cold) fits cut-off cold pools aloft over a hot ground, with no cold surge at the surface.
- **The full-method test (15 Nov 2026, `method-study.yml`: `hist_fetch.py` in 5 parallel chunks + `method_test.py`; NCEP R1 2000-Mar 2026 rebuilt exactly like daily.py; CHIRPS rain from the long test; hist chunks of run 43679904944 can be reused with input hist_run).**
  - Checks pass. The rebuilt warm-event centre moves with the RMM phase: 10E, 67, 75, 121, 147, 197, 308, 334E for phases 1-8. Last season's rebuilt Rossby family is negative on 92 % of wide days, the same as the daily system.
  - Lift (spread when on against off), Kingdom Nov-Jan / Feb-Apr:
    - PW >= 130 %: x4.7 / x3.8, on 80 % of wide days.
    - Trough (waves 4-8) <= -25 m: x1.8 / x1.8. In the parts: southwest x3.6-4.1, Hijaz x2.6.
    - MJO phases 8-1: x1.9 / x2.0; phases 7-8-1-2: x1.7 / x1.8.
    - Warm event in the sector: x0.9 / x1.5.
    - Cold event over 45E (w45 <= -4): x0.6 / x0.9.
    - Component: x1.2 / x1.3.
    - Kelvin: x1.1 / x1.2.
    - Rossby: x1.1 / x1.0. **Over 26 seasons the Rossby family has no stable effect:** negative on 48 % of wide days, against a base of 48 %. By season it runs from 22 % to 92 %; it was high in 2016, 2024 and 2025 and low in 2000-2002.
  - Day kinds, Kingdom: tropical + trough/moisture days give 58-64 % of the rain; trough/moisture alone 19-20 %; tropical alone 12-15 %; neither 5-7 %. Exception: in the Hijaz and the southwest, tropical-only days give a large share (Hijaz Nov-Jan 37 %, southwest 53 %).
  - The report's strength score works: P(wide day) for the Kingdom is 3 % at 0-1, 9-11 % at 1-2, 16-19 % at 2-3 and 23-33 % at 3-5.
  - A supportive component 10 days earlier means less rain later, because it moves on. Use its forecast arrival, not today's value.
  - Daily share explained: tropics 2-8 %, troughs+moisture 10-23 %, all 12-24 %.
  - Candidate changes, for Fahad to decide after the stability phase:
    - Rossby weight in strength().
    - MJO phases 8 and 1 instead of 7-8-1-2.
    - Warm event weighted in Feb-Apr only.
    - Cold event as a brake in Nov-Jan.
  - **Who brings the moisture (same run family, 15 Nov):** P(PW >= 130 %) by MJO phase.
    - Kingdom Feb-Apr: phase 8 66 %, phase 1 51 %, phase 4 15 %; the base is 38 %. North Feb-Apr: phase 8 27 %, phase 4 3 %. Hijaz: phase 8 25-28 %, phases 4-5 4-8 %.
    - Other drivers, as a multiple of the base chance: warm event x1.2-1.6 in Feb-Apr and x0.6-0.9 in Nov-Jan; cold event x0.5-0.9; Rossby, Kelvin and component x0.8-1.3; the part's own trough x0.7-1.4.
    - Moist days have a tropical driver on 72-82 % of days, against 65-68 % of all days.
    - Kingdom: moist days with a trough give 50 % of the rain; moist days without a trough give 16-17 %.
    - Reading: the MJO (phases 8-1) is the main moisture pump, and the trough gives the lift. Part of the "trough/moisture without tropics" rain is tropical through the moisture.
    - Caveat: the trough is measured over the part itself, which can miss the upstream trough that pumps the moisture.
  - **Reach of the moisture inland (15 Nov).** Days with the west or southwest at >= 130 % of normal: the centre is moist too on 58 % of them in Nov-Jan and 52 % in Feb-Apr.
    - Nov-Jan, by MJO phase: phase 1 86 %, phase 8 77 %, phases 5-6 38-45 %.
    - Nov-Jan, phases 8-1 by amplitude: below 1 50 %, 1-1.5 67 %, 1.5 and more 90 %. Amplitude matters only in phases 8-1 (phases 2-3 stay flat at 53-69 %).
    - Feb-Apr: no amplitude effect. The trough decides: 59-67 % with a trough over the north or centre, 41-45 % without.
    - 38 % of the centre's moist days come without a moist coast, from the Arabian Sea over the Rub al-Khali and from the Gulf.
  - **Moisture needed for rain (15 Nov).** PW as % of normal, with a trough (<= -25 m) over the part. "Start" = P(rain on 2 % of the part or more) about 45-50 %; "confident" = about 60-75 %.
    - Hijaz: Nov-Jan start 115, P stays near 50 % even at 130-150. Feb-Apr start 130, confident 150 (71 %).
    - Southwest: Nov-Jan rain rare whatever the moisture (33 % at most). Feb-Apr start 100 (58 %), confident 115 (75 %).
    - North: Nov-Jan start 130 (48 %), confident 150 (71 %). Feb-Apr start 130 (52 %), confident 150 (63 %).
    - Centre: Nov-Jan start 150 (61 %). Feb-Apr start 115 (54 %), confident 130 (71 %), 150 and more 85 %.
    - East: Nov-Jan start 150 (52 %). Feb-Apr start 130 (52 %), confident 150 (65 %).
    - Without a trough, P drops by about 10-30 points at the same PW.
    - MJO 8-1-2 on top of a trough adds little in most cells (small samples). The exception is the centre in Feb-Apr at 150-175 %: 88 %.
  - **Highlands and Tihama strips (`highland_test.py`, method-study extra=highlands; CHIRPS 2001-2024; NCEP PW at the middle of each strip).** P(10 mm or more somewhere on the strip).
    - Highlands, share of days by month: Nov 2 %, Dec 4 %, Jan 7 %, Feb 1 %, Mar 9 %, Apr 32 %. November is climatologically dry there, and strip PW above 150 % in November almost never occurred, so this week (150-190 %) was outside the historical range.
    - Highlands Nov: P rises from 0 to 8 % as PW goes from below 80 % to 130-150 %. Dec-Jan with a trough: 25 % at 150-175 %. Feb-Apr with MJO 8-1-2: 32 % at 115-130 %, 41 % at 130-150 %, 50 % at 150-175 %.
    - Tihama: low in every season (at most 19 % at 150-175 % in Dec-Jan). CHIRPS likely under-counts there.
    - Early season in the highlands needs exceptional moisture plus lift. The 22 Nov forecast (130-134 %) is below this week's level.
  - Reading: the tropics set the odds (x2 in phases 8/1, /2-4 in 3-5), and the troughs and moisture make the rain. This supports their weight for long range, not for day or place.

## 8. Open items and decisions (state on 14 Nov)

- **Decided (14–15 Nov):** one daily cycle, **12Z**. The 00Z model run was removed from the schedule and keeper on 15 Nov.
- **After the current spell, Fahad's two paths:**
  1. Improve the oscillation page and maps: a timeline strip of drivers and waves, a verification log of past waves, and an animated component/warm-event map. Ask him what bothers him in the current maps.
  2. A forecast driven by the **German ICON**, downscaled to 3 km or finer. Claude suggested a feasibility test outside production first, comparing ICON and ECMWF open data on the 13 Nov case (plains start missed). Check the data: levels, soil fields, the icosahedral grid needs remapping, about 1-day retention. A GFS + ICON pair could be a two-member ensemble in a single daily cycle.
- **Wave watch:**
  - 18–19 Nov: weak (the component brakes, warm event out of sector).
  - **21–25 Nov:** stronger, mixed. MJO phase 2 at amplitude about 2.4; warm event in sector 21–23; Red Sea trough digging to 17–20°N on 22–25; PW 150 % over the west on 25 Nov. Peak by drivers 23 Nov, by moisture and trough 25 Nov.
  - 28 Nov onward: the component turns supportive and a new MJO cycle approaches.
- **Istanbul trip analysis** (20–26 Nov):
  - Trough 19–20.
  - Poyraz 21–25: T850 about 0, highs 11–13, little rain.
  - Pattern flip and higher rain chance 25–26.
  - The same pattern drives the Red Sea trough above.
  - Daily updates until 19 Nov are scheduled in the *old* session at 08:20 UTC.
- The 9 km Kingdom run could be dropped once the gate and keeper read a 3 km grid's `runs.json` instead.

## 9. Fahad's verification log: evening (12Z) run against the morning (00Z) run

| Day | Better at placing the rain | Note |
|---|---|---|
| 13 Nov 2026 | evening run (12Z of the 12th) | both missed the start over the Tihama plains |
| 14 Nov 2026 | evening run (12Z of the 13th) | second day running, by Fahad's reading |
| week of 8–14 Nov 2026 | evening run | Fahad: about 90 % of the cases since the start of the week matched the evening run |

Keep adding a row each day he reports. If the pattern holds for about two weeks, act on it: either a single 12Z cycle, or keep 00Z only as a merged (lagged-ensemble) update instead of replacing the night table.
