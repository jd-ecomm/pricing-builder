#!/usr/bin/env python3
"""Split a rebuilt single-file dashboard into index.html + data/part1-4.js for GitHub (each part <10 MB),
compacting SERIES day indexes to d0. Usage: split_for_github.py <built.html> <out_dir> <yyyymmdd>"""
import re,json,os,sys
src,out,ver=sys.argv[1:4]
lines=open(src,encoding='utf-8').read().split('\n')
start=next(i for i,l in enumerate(lines) if l.startswith('const PRODUCTS = '));end=start
while end<len(lines) and re.match(r'^const [A-Z_]+ = ',lines[end]): end+=1
D={re.match(r'^const ([A-Z_]+)',l).group(1):l for l in lines[start:end]}
S=json.loads(D['SERIES'][len('const SERIES = '):-1])
for v in S.values():
    di=v.get('di')
    if di and all(di[j]==di[0]+j for j in range(len(di))): v['d0']=di[0]; del v['di']
D['SERIES']='const SERIES = '+json.dumps(S,separators=(',',':'))+';'
G=[['PRODUCTS','BRANDS','METRICS','PH_DATES','PRICE_HISTORY','MH_DATES'],['MARKET_HISTORY','CHANGES','PERF'],['VARIANTS','SERIES','CVR_BASELINE','MC_DATES','MARKET_CHANGES','TITLES'],['MARKDOWNS','MD_BY_GROUP','COMP_BY_GROUP']]
assert set(sum(G,[]))==set(D),set(D)^set(sum(G,[]))
os.makedirs(out+'/data',exist_ok=True)
for i,g in enumerate(G,1): open(f'{out}/data/part{i}.js','w',encoding='utf-8').write('// DATA\n'+'\n'.join(D[n] for n in g)+'\n')
pre='\n'.join(lines[:start]);post='\n'.join(lines[end:]).lstrip('\n')
m=re.search(r'<script>\s*// =+\s*// DATA\s*// =+\s*$',pre);pre=pre[:m.start()]
if 'Rebuild compact SERIES' not in post:
    post="// Rebuild compact SERIES day indexes (stored as start 'd0' to keep the file small)\nfor (const _k in SERIES) { const _v = SERIES[_k]; if (!_v.di && _v.d0 != null) { const _n = (_v.o || _v.r || []).length; _v.di = Array.from({length: _n}, (_, i) => _v.d0 + i); } }\n"+post
open(out+'/index.html','w',encoding='utf-8').write(pre+'\n'.join(f'<script src="data/part{i}.js?v={ver}"></script>' for i in range(1,5))+'\n<script>\n\n'+post)
print('ok')
