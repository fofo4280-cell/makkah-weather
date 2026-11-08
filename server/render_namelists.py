#!/usr/bin/env python3
"""Write namelist.wps or namelist.input from domains.json.

render_namelists.py wps   <start YYYYMMDDHH> <geog_path> <out>
render_namelists.py input <start YYYYMMDDHH> <num_metgrid_levels> <num_metgrid_soil_levels> <out> [max_dom]
render_namelists.py geohash                    print a hash of the grid design (to know when to rerun geogrid)
"""
import hashlib, json, os, sys
from datetime import datetime, timedelta

CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "domains.json")))


def doms(max_dom=None):
    d = CFG["domains"]
    return d[: max_dom or len(d)]


def row(key, vals, fmt="{}"):
    return f" {key:<26}= " + ", ".join(fmt.format(v) for v in vals) + ","


def wps(start, geog, max_dom=None):
    D = doms(max_dom)
    t0 = datetime.strptime(start, "%Y%m%d%H")
    t1 = t0 + timedelta(hours=D[0]["hours"])
    fmt = "%Y-%m-%d_%H:%M:%S"
    m = CFG["map"]
    L = ["&share", " wrf_core = 'ARW',", f" max_dom = {len(D)},",
         row("start_date", [t0.strftime(fmt)] * len(D), "'{}'"),
         # nests need only their first time; the parent needs the whole period for boundaries
         row("end_date", [t1.strftime(fmt)] + [t0.strftime(fmt)] * (len(D) - 1), "'{}'"),
         " interval_seconds = 10800,", " io_form_geogrid = 2,", "/", "",
         "&geogrid",
         row("parent_id", [max(1, x["parent"]) for x in D]),
         row("parent_grid_ratio", [x["ratio"] for x in D]),
         row("i_parent_start", [x["ips"] for x in D]),
         row("j_parent_start", [x["jps"] for x in D]),
         row("e_we", [x["e_we"] for x in D]),
         row("e_sn", [x["e_sn"] for x in D]),
         row("geog_data_res", [x["geog"] for x in D], "'{}'"),
         f" dx = {D[0]['dx']},", f" dy = {D[0]['dx']},",
         f" map_proj = '{m['map_proj']}',", f" ref_lat = {m['ref_lat']},", f" ref_lon = {m['ref_lon']},",
         f" truelat1 = {m['truelat1']},", f" truelat2 = {m['truelat2']},", f" stand_lon = {m['stand_lon']},",
         f" geog_data_path = '{geog}',", "/", "",
         "&ungrib", " out_format = 'WPS',", " prefix = 'FILE',", "/", "",
         "&metgrid", " fg_name = 'FILE',", " io_form_metgrid = 2,", "/", ""]
    return "\n".join(L)


def tf(b):
    return ".true." if b else ".false."


def nml_input(start, nlev, nsoil, max_dom=None):
    D = doms(max_dom)
    n = len(D)
    t0 = datetime.strptime(start, "%Y%m%d%H")
    ends = [t0 + timedelta(hours=x["hours"]) for x in D]
    L = ["&time_control",
         f" run_days = 0,", f" run_hours = {D[0]['hours']},", " run_minutes = 0,", " run_seconds = 0,",
         row("start_year", [t0.year] * n), row("start_month", [f"{t0.month:02d}"] * n),
         row("start_day", [f"{t0.day:02d}"] * n), row("start_hour", [f"{t0.hour:02d}"] * n),
         row("end_year", [e.year for e in ends]), row("end_month", [f"{e.month:02d}" for e in ends]),
         row("end_day", [f"{e.day:02d}" for e in ends]), row("end_hour", [f"{e.hour:02d}" for e in ends]),
         " interval_seconds = 10800,",
         row("input_from_file", [".true."] * n),
         row("history_interval", [60] * n),
         row("frames_per_outfile", [1] * n),
         " restart = .false.,", " restart_interval = 100000,",
         " io_form_history = 2,", " io_form_restart = 2,", " io_form_input = 2,", " io_form_boundary = 2,",
         " nwp_diagnostics = 1,", " debug_level = 0,", "/", "",
         "&domains",
         f" time_step = {CFG['time_step']},", " time_step_fract_num = 0,", " time_step_fract_den = 1,",
         " use_adaptive_time_step = .true.,", " step_to_output_time = .true.,",
         row("target_cfl", [1.2] * n), row("target_hcfl", [0.84] * n),
         row("max_step_increase_pct", [5] + [51] * (n - 1)),
         row("starting_time_step", [-1] * n),
         row("max_time_step", [x["max_dt"] for x in D]),
         row("min_time_step", [x["min_dt"] for x in D]),
         " adaptation_domain = 1,",
         f" max_dom = {n},",
         row("e_we", [x["e_we"] for x in D]), row("e_sn", [x["e_sn"] for x in D]),
         row("e_vert", [CFG["e_vert"]] * n),
         f" p_top_requested = {CFG['p_top']},",
         f" num_metgrid_levels = {nlev},", f" num_metgrid_soil_levels = {nsoil},",
         row("dx", [x["dx"] for x in D]), row("dy", [x["dx"] for x in D]),
         row("grid_id", list(range(1, n + 1))),
         row("parent_id", [x["parent"] for x in D]),
         row("i_parent_start", [x["ips"] for x in D]), row("j_parent_start", [x["jps"] for x in D]),
         row("parent_grid_ratio", [x["ratio"] for x in D]),
         row("parent_time_step_ratio", [x["ratio"] for x in D]),
         " feedback = 1,", " smooth_option = 0,", "/", "",
         "&physics",
         row("mp_physics", [8] * n), " do_radar_ref = 1,",
         row("ra_lw_physics", [4] * n), row("ra_sw_physics", [4] * n), row("radt", [9] * n),
         row("sf_sfclay_physics", [5] * n), row("sf_surface_physics", [2] * n),
         row("bl_pbl_physics", [5] * n), row("bldt", [0] * n),
         row("cu_physics", [x["cu"] for x in D]), row("cudt", [0] * n),
         " isfflx = 1,", " ifsnow = 0,", " icloud = 1,", " surface_input_source = 3,",
         " num_soil_layers = 4,", " num_land_cat = 21,",
         row("sf_urban_physics", [0] * n), "/", "",
         "&fdda", "/", "",
         "&dynamics",
         " hybrid_opt = 2,", " etac = 0.2,", " w_damping = 1,",
         row("diff_opt", [1] * n), row("km_opt", [4] * n),
         row("diff_6th_opt", [2] * n), row("diff_6th_factor", [0.12] * n),
         " base_temp = 290.,", " damp_opt = 3,",
         row("zdamp", [5000.] * n), row("dampcoef", [0.2] * n),
         row("khdif", [0] * n), row("kvdif", [0] * n),
         row("non_hydrostatic", [".true."] * n),
         row("moist_adv_opt", [1] * n), row("scalar_adv_opt", [1] * n),
         row("gwd_opt", [x["gwd"] for x in D]),
         row("epssm", [0.5] * n), "/", "",
         "&bdy_control", " spec_bdy_width = 5,", " specified = .true.,", "/", "",
         "&grib2", "/", "",
         "&namelist_quilt", " nio_tasks_per_group = 0,", " nio_groups = 1,", "/", ""]
    return "\n".join(L)


def geohash():
    keys = ["map", "domains"]
    blob = json.dumps({k: CFG[k] for k in keys}, sort_keys=True)
    blob += open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "patch_geogrid_tbl.py")).read()
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "wps":
        open(a[4], "w").write(wps(a[2], a[3]))
    elif a[1] == "input":
        open(a[5], "w").write(nml_input(a[2], int(a[3]), int(a[4]), int(a[6]) if len(a) > 6 else None))
    elif a[1] == "geohash":
        print(geohash())
