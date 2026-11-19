"""OLR anomaly maps (convection) for given days, tropics; NOAA interpolated OLR daily from PSL (OPeNDAP)."""
import sys, numpy as np, netCDF4, datetime as dt
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, cartopy.crs as ccrs, cartopy.feature as cf
import arabic_reshaper
from bidi.algorithm import get_display
from matplotlib import font_manager as fm
fp = fm.FontProperties(fname=sys.argv[1])
A = lambda s: get_display(arabic_reshaper.reshape(s))
ARD = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
MON = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
import glob, os
# NOAA OLR daily CDR (NCEI, 1 degree): this year's preliminary file and the ten last years for the normal
files = sorted(glob.glob("ncei/*.nc"))
cur = [f for f in files if "_2026" in os.path.basename(f)]
nc = netCDF4.Dataset(cur[-1])
tv = nc["time"]; t = netCDF4.num2date(tv[:], tv.units)
days = [dt.date(x.year, x.month, x.day) for x in t]
print("last OLR day", days[-1], flush=True)
la, lo = nc["lat"][:], nc["lon"][:]
jj = np.where((la >= -30) & (la <= 40))[0]
if la[0] > la[-1]:
    pass
want = [dt.date(2026, 11, 10), days[-1]]
for d in want:
    i = days.index(d)
    clim = []
    for f in files:
        if f in cur:
            continue
        with netCDF4.Dataset(f) as c:
            ct = netCDF4.num2date(c["time"][:], c["time"].units)
            cd = [dt.date(x.year, x.month, x.day) for x in ct]
            for k, x in enumerate(cd):
                if x.month == d.month and abs(x.day - d.day) <= 2:
                    clim.append(np.ma.filled(c["olr"][k, jj[0]:jj[-1] + 1, :].astype(float), np.nan))
    clim = [np.nanmean(clim, 0)]
    print("normal from", len(files) - len(cur), "years", flush=True)
    # 5-day mean anomaly centred on the day where possible
    lo5 = max(i - 2, 0); hi5 = min(i + 3, len(days))
    an5 = np.ma.filled(nc["olr"][lo5:hi5, jj[0]:jj[-1] + 1, :].astype(float), np.nan).mean(0) - clim[0]
    fig = plt.figure(figsize=(14, 5.2), dpi=130)
    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=120))
    ax.set_extent([0, 359.9, -30, 40], ccrs.PlateCarree())
    lev = np.arange(-70, 71, 10)
    cm = ax.contourf(lo, la[jj], an5, levels=lev, cmap="RdBu_r", extend="both", transform=ccrs.PlateCarree())
    ax.coastlines(lw=.6, color="#333"); ax.add_feature(cf.BORDERS, lw=.3, color="#555")
    ax.plot([34, 56, 56, 34, 34], [16, 16, 32, 32, 16], color="k", lw=1.2, transform=ccrs.PlateCarree())
    cb = plt.colorbar(cm, orientation="horizontal", pad=.06, fraction=.05, aspect=50)
    cb.set_ticks(lev[::2]); cb.set_ticklabels([str(int(v)).translate(ARD) for v in lev[::2]])
    title = f"الحمل الحراري المداري: شذوذ الأشعة الطويلة الصادرة، متوسط خمسة أيام حول {str(d.day).translate(ARD)} {MON[d.month-1]} {str(d.year).translate(ARD)}"
    ax.set_title(A(title), fontproperties=fp, fontsize=14)
    cb.set_label(A("واط/م²   الأزرق = حمل حراري أنشط من المعتاد (سحب ركامية)   الأحمر = كبت وسماء صافية"), fontproperties=fp, fontsize=11)
    fig.savefig(f"olr_{d.isoformat()}.png", bbox_inches="tight"); plt.close(fig)
    print("saved", d, flush=True)
