import numpy as np, json, sys
from datetime import date, timedelta
from zones import ZONES, ALL
a=np.load('models_a.npz'); b=np.load('models_b.npz'); o=np.load(sys.argv[1] if len(sys.argv)>1 else 'obs.npz')
LAT,LON=a['lat'],a['lon']
days=[(date(2026,9,1)+timedelta(k)).isoformat() for k in range(45)]
def mod(m,l,d): return (b if (m,l)==('gfs','d0') else a)[f'{m}_{l}_{d}']
def regrid(x,res):
    ny,nx=x.shape; plat=24-res*(np.arange(ny)+.5); plon=39+res*(np.arange(nx)+.5)
    out=np.full((len(LAT),len(LON)),np.nan,np.float32)
    for j,c in enumerate(LAT):
        jj=np.abs(plat-c)<=0.125+1e-6
        for i,d in enumerate(LON):
            ii=np.abs(plon-d)<=0.125+1e-6
            if jj.any() and ii.any(): out[j,i]=np.nanmean(x[np.ix_(jj,ii)])
    return out
def pmax(x,res):  # max of fine pixels inside each 0.25 cell
    ny,nx=x.shape; plat=24-res*(np.arange(ny)+.5); plon=39+res*(np.arange(nx)+.5)
    out=np.full((len(LAT),len(LON)),np.nan,np.float32)
    for j,c in enumerate(LAT):
        jj=np.abs(plat-c)<=0.125+1e-6
        for i,d in enumerate(LON):
            ii=np.abs(plon-d)<=0.125+1e-6
            if jj.any() and ii.any(): out[j,i]=np.nanmax(x[np.ix_(jj,ii)])
    return out
SRC={'pdir':0.04,'ccs':0.04,'pers':0.25}
obs={}
for s,res in SRC.items():
    obs[s]={d:(regrid(o[f'{s}_{d}'],res),pmax(o[f'{s}_{d}'],res)) for d in days if f'{s}_{d}' in o.files}
    print(s,'days',len(obs[s]))
np.save('obs_grid.npy',obs,allow_pickle=True)
