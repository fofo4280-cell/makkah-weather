# Fahad's weather project — handoff for a new Claude session

Last updated: 14 Nov 2026 (evening). Written for Claude, to continue the work without the long history.

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
- **Cycles:** 00 and 12 UTC (Fahad wanted 22:00 and 10:00 Makkah). In practice:
  - 12Z finishes about 01–02 Makkah.
  - 00Z finishes about 12–13 Makkah.
  - GFS 00Z f033 is on AWS about 03:45 UTC; 12Z about 15:45 UTC.
- **Jobs** (`wrf-job.yml`, called by `saudi-model.yml`): each grid runs in two parts.
  - Part 1 runs to hour 15, then a restart handover; part 2 runs to 33.
  - Time budget is 335 min from job start, then it publishes what is done.
- **Watchdog** (`run_cycle.sh`): if the WRF log is silent for 25 min, restart WRF once; the second time, stop. Added after the 12 Nov west part-2 hang.
- **Gate** (`saudi-model.yml`):
  - Skips if `runs.json` already has the cycle.
  - Waits up to 280 min for the GFS f033 file **on AWS** before starting jobs. Since 13 Nov a schedule fired hours early waits here, not inside the jobs.
  - Concurrency group `saudi-model`, no cancel.
- **Schedules:** GitHub crons are unreliable (often missed or hours late). The crons are 47 2, 13 3, 41 3, 7 4 and 47 14, 13 15, 41 15, 7 16 (UTC).
- **Keeper** (`keeper.yml`): runs continuously and checks every 5 min. It re-dispatches itself every 5 h 40 min, with an hourly cron revival. It starts whatever is missing:
  - model cycle 00 between 03:50 and 11:00 UTC, and 12 between 15:50 and 23:00;
  - the night climate run between 21:00 and 23:59 UTC.
- **Rain map `rain24`:** hours 9-33, i.e. 12 to 12 Makkah time (midnight to midnight in the 12Z run, noon to noon in the 00Z run); label «المطر التراكمي من ١٢ إلى ١٢» (Fahad, 14 Nov 2026).
- **Maps:** PNG with banded palettes. The REFL palette is 5 dBZ bands, blue → green → yellow → red → purple. Model page assets are versioned `v=2026111xx`.

## 4. Reports pipeline (`server/climate`)

- `climate.yml` runs nightly. Crons 33 20, 7 21, 43 21 UTC, plus the keeper.
  - Its `check` job skips if `mjo.json` cycle == `date -u -d '12 hours ago'` + `12`. This was fixed on 13 Nov, after late firings after midnight re-ran it.
  - It runs `daily.py`: MJO/RMM, filtered MJO component (`mjofilt.py`), warm/cold event, Rossby waves, PW, troughs, ingredients index, the `diag.py` diagnosis, and the report (`bigreport.py`).
  - Since 14 Nov: **tropical waves in chi200** (`wkfilt.py`, Wheeler-Kiladis by wavenumber, period and phase speed): Kelvin family (eastward, 2-30 d, 8-60 m/s, k 1-9) and Rossby family (westward, 5-90 d, 0.5-25 m/s, k 1-9). It needs the long chi history, so `HIST_DAYS` = 400. Output in `mjo.json`: `tw` (`kel_ksa`, `ros_ksa` over the Kingdom box, cores, `*_ref` = past std) and `marks` (MJO core, warm and cold event longitude per forecast day).
  - Belt maps (`figures.draw_belt`): one frame 0-360, 35S-35N, 3000 px, coastlines/borders 1:50m, marker lines, for `wc`, `wcd`, `mjoz`, `mjop`, `kel`, `ros` (with divergent-wind arrows). The page's «اللوحة الاستوائية الشاملة» card stacks wc, mjoz, kel, ros, scrolling together.
  - The Rossby family is the sixth driver in `bigreport.strength` (0..1 = -ros/(2 ref)), total capped at 5 (Fahad, 14 Nov). Kelvin is only named in the text (for/against), not scored: over the Kingdom box it showed no relation to rain.
  - Compute takes about 15 min (was 8).
  - Its last step waits for the 12Z 3 km runs (until about 02:45 UTC) and rebuilds the report from them.
- **The noon update was stopped on 14 Nov 2026 (Fahad): the midnight report is the only daily report.** The keeper no longer starts it and `rain-noon.yml` has no schedule; it stays for a run by hand.
- `rain-noon.yml` (`refresh_report.py`) has inputs `mode=noon|midnight`, `publish`, and `wait=yes|no`.
  - Noon: waits for the 00Z 3 km runs, unless `wait=no`, which publishes at once from what is out.
  - Midnight: rewrites the night rain table from the evening runs.
  - It **shares the concurrency group with climate.yml**. A dispatched update queues behind a climate run that is waiting for the 3 km runs. Open issue: separate them without letting both overwrite `climate-data`.
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

## 8. Open items and decisions (state on 14 Nov)

- **Waiting for Fahad's answer:** keep only one daily cycle? Claude recommended **12Z** (past spin-up for the next day's afternoon, ready by about 02:00, fewer failure points). Alternative: 18Z.
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
