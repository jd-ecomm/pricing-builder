import openpyxl, json, sys
from collections import defaultdict, Counter
MD='/home/claude/skill_bundle/jd-pricing-dashboard/data/markdowns.json'
FILES=[('/home/claude/md_new/MARKDOWNS - NEW AND FURTHERS  - GO LIVE OCTOBER 1ST.xlsx','2026-10-01'),
       ('/home/claude/md_new/10082026 RETAIL + ECOM MARKDOWNS.xlsx','2026-10-08')]
def cl(n):
    n=n.lower()
    if 'all channel' in n or ('retail' in n and 'ecom' in n): ch='All'
    elif 'ecom' in n: ch='eCom'
    elif 'retail' in n: ch='Retail'
    else: ch=None
    typ='Temporary' if 'temp' in n else ('Permanent' if ('perm' in n) else None)
    return ch,typ
def mn(x):
    try:
        if x is None: return None
        return float(str(x).replace('$','').replace(',','').split()[0])
    except: return None
def na(a):
    a=str(a).strip().upper()
    return 'FURTHER' if 'FURTHER' in a else 'NEW' if 'NEW' in a else 'BTFP' if ('BTFP' in a or 'FULL PRICE' in a) else 'INCREASE' if ('INCREASE' in a or 'MARKUP' in a) else (a if a and a not in ('NAN','NONE') else None)
CM={'dept':['dept','department'],'brand':['brand'],'supplier':['supplier id'],'style':['style id'],'name':['style name'],'msrp':['msrp'],'current':['current sell retail'],'action':['action','acton'],'newprice':['new price'],'disc':['discount to msrp']}
def mc(hdr):
    low=[str(h).strip().lower() if h is not None else '' for h in hdr]; idx={}
    for k,cs in CM.items():
        for c in cs:
            if c in low: idx[k]=low.index(c); break
    return idx
def s(v): return '' if v is None else str(v).strip()
events=[]
for f,GO in FILES:
    wb=openpyxl.load_workbook(f,read_only=True,data_only=True)
    for ws in wb.worksheets:
        if ws.title.lower().startswith(('inventory','image')): continue
        ch,typ=cl(ws.title)
        if ch is None: continue
        if typ is None: typ='Permanent'
        idx=None; blank=0
        for row in ws.iter_rows(values_only=True):
            if idx is None:
                if row and any(s(x).upper()=='STYLE ID' for x in row): idx=mc(row)
                continue
            st=s(row[idx['style']]) if len(row)>idx['style'] else ''
            if not st:
                blank+=1
                if blank>200: break
                continue
            blank=0
            newp=mn(row[idx['newprice']])
            if newp is None: continue
            try: disc=float(row[idx['disc']]) if 'disc' in idx else None
            except: disc=None
            act=na(row[idx['action']]) if 'action' in idx else None
            if 'BTFP' in ws.title.upper() and not act: act='BTFP'
            events.append({'go':GO,'until':None,'style':st,'supplier':s(row[idx['supplier']]) if 'supplier' in idx else '',
              'brand':s(row[idx['brand']]) if 'brand' in idx else '','dept':s(row[idx['dept']]) if 'dept' in idx else '',
              'name':s(row[idx['name']]) if 'name' in idx else '','msrp':mn(row[idx['msrp']]) if 'msrp' in idx else None,
              'cur':mn(row[idx['current']]) if 'current' in idx else None,'newp':newp,'disc':disc,'act':act,'typ':typ,'ch':ch})
        print(f.split('/')[-1][:40], ws.title, sum(1 for e in events if e['go']==GO and e['ch']==ch))
grp=defaultdict(list)
for e in events: grp[(e['go'],e['style'])].append(e)
new=[]
for (go,st),evs in grp.items():
    chs=set(e['ch'] for e in evs)
    scope='Both' if ('All' in chs or {'eCom','Retail'}<=chs) else ('eCom' if chs=={'eCom'} else 'Retail')
    b=dict(sorted(evs,key=lambda e:(e['ch']=='Retail'))[0]); b.pop('ch'); b['scope']=scope; b['on_site']=scope in ('Both','eCom')
    new.append(b)
old=json.load(open(MD)); dates={e['go'] for e in new}
old=[e for e in old if e['go'] not in dates]
json.dump(old+new,open(MD,'w'))
print('new events',len(new),Counter((e['go'],e['scope'],e['act']) for e in new).most_common(12))
print('total',len(old)+len(new))
