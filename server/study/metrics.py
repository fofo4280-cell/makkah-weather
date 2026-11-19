import numpy as np, json
from zones import *
from datetime import date,timedelta
from scipy.stats import spearmanr, pearsonr
from scipy.ndimage import uniform_filter
obs=np.load('obs_grid.npy',allow_pickle=True).item(); a=np.load('models_a.npz'); b=np.load('models_b.npz'); LAT,LON=a['lat'],a['lon']
days=[(date(2026,9,1)+timedelta(k)).isoformat() for k in range(45)]
SRCS=[s for s in obs]  # pdir ccs pers (+cmorph)
def mod(m,l,d): return (b if (m,l)==('gfs','d0') else a)[f'{m}_{l}_{d}']
def box(z): S,N,W,E=z; return (LAT>=S-1e-6)&(LAT<=N+1e-6),(LON>=W-1e-6)&(LON<=E+1e-6)
def cons(d): return np.nanmedian(np.array([np.nan_to_num(obs[s][d][0]) for s in SRCS]),axis=0)
OB={'cons':{d:cons(d) for d in days}}
for s in SRCS: OB[s]={d:np.nan_to_num(obs[s][d][0]) for d in days}
R={}
def series(fld,z):
    J,I=box(z); return np.array([fld(d)[np.ix_(J,I)].mean() for d in days])
def ets(o,f):
    h=(o&f).sum(); m=(o&~f).sum(); fa=(~o&f).sum(); n=len(o); hr=(h+m)*(h+fa)/n
    return h,m,fa,(h-hr)/(h+m+fa-hr) if (h+m+fa-hr)>0 else np.nan
out=[]
for oname in ['cons']+SRCS:
  for l in ('d0','d1','d2'):
    for zn,z in list(ZONES.items())+[('all',ALL)]:
      os_=series(lambda d:OB[oname][d],z)
      row={'obs':oname,'lead':l,'zone':zn,'obs_tot':round(os_.sum(),1)}
      oe=os_>=1.0; row['obs_days']=int(oe.sum())
      for m in ('gfs','ec'):
        ms=series(lambda d:mod(m,l,d),z)
        row[m+'_tot']=round(ms.sum(),1)
        row[m+'_sp']=round(spearmanr(os_,ms)[0],2); row[m+'_r']=round(pearsonr(os_,ms)[0],2)
        # quantile-matched events: model's top-N days, N = obs event days
        n=oe.sum(); fe=np.zeros(len(ms),bool)
        if n>0: fe[np.argsort(-ms)[:n]]=True; fe&=ms>0.01
        h,mi,fa,e=ets(oe,fe); row[m+'_qhit']=int(h); row[m+'_qets']=round(e,2)
        fa_abs=ms>=0.2; h,mi,fa,e=ets(oe,fa_abs); row[m+'_ahit']=int(h); row[m+'_amiss']=int(mi); row[m+'_afa']=int(fa); row[m+'_aets']=round(e,2)
      out.append(row)
json.dump(out,open('metrics.json','w'),default=float)
# spatial on wet days
J,I=box(ALL)
def fss(o,f,q=0.8,nb=3):
    to=np.quantile(o,q); tf=np.quantile(f,q)
    if to<=0.2 or tf<=0.01: return np.nan
    po=uniform_filter((o>=to).astype(float),nb,mode='constant'); pf=uniform_filter((f>=tf).astype(float),nb,mode='constant')
    return 1-((po-pf)**2).mean()/((po**2).mean()+(pf**2).mean())
def centroid(x):
    LA,LO=np.meshgrid(LAT[J],LON[I],indexing='ij'); w=np.clip(x,0,None)
    if w.sum()<=0: return None
    return (LA*w).sum()/w.sum(),(LO*w).sum()/w.sum()
sp=[]
for l in ('d0','d1','d2'):
  for d in days:
    o=OB['cons'][d][np.ix_(J,I)]
    if (o>=1).mean()<0.15: continue
    r={'lead':l,'day':d,'obs_wet':round((o>=1).mean(),2)}
    co=centroid(o)
    for m in ('gfs','ec'):
      f=mod(m,l,d)[np.ix_(J,I)]
      r[m+'_pc']=round(np.corrcoef(o.ravel(),f.ravel())[0,1],2) if f.std()>0 else np.nan
      r[m+'_fss']=round(fss(o,f),2); r[m+'_fss5']=round(fss(o,f,nb=5),2)
      cf=centroid(f); r[m+'_cdist']=round(111*np.hypot(co[0]-cf[0],(co[1]-cf[1])*np.cos(np.radians(21))),0) if cf and f.max()>=0.3 else np.nan
      r[m+'_wet02']=round((f>=0.2).mean(),2); r[m+'_max']=round(float(f.max()),1)
    sp.append(r)
json.dump(sp,open('spatial.json','w'),default=float)
print(len(sp)//3,'wet days')
