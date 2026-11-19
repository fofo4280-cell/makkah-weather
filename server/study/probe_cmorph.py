import re, urllib.request
def get(u): return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"climate-study/1.0"}),timeout=120).read()
def ls(u):
    try: return re.findall(r'href="([^"?#/][^"]*)"', get(u).decode("latin-1"))
    except Exception as e: print("fail",u,e); return []
B="https://ftp.cpc.ncep.noaa.gov/precip/"
for u in [B+"CMORPH_RT/GLOBE/data/2026/202609/", B+"CMORPH2/CMORPH2NRT/DATA/", B+"CMORPH_RT/ICDR/", B+"CMORPH_RT/BLD/"]:
    f=ls(u); print(u,len(f),f[:10],f[-6:],flush=True)
    for s in [x for x in f if x.endswith("/")][-3:]:
        g=ls(u+s); print("  ",u+s,len(g),g[:6],g[-6:],flush=True)
        for t in [x for x in g if x.endswith("/")][-2:]:
            h=ls(u+s+t); print("    ",u+s+t,len(h),h[:6],h[-4:],flush=True)
print(get(B+"CMORPH2/CMORPH2NRT/readme_CMORPH2x_NRT.txt").decode("latin-1")[:4000])
