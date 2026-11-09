#!/usr/bin/env python3
"""Extract the pricing-actions section tables from a built dashboard index.html.
Writes section_data.json consumed by gen_actions.js. Reuses the dashboard's own
feed loader so product links and IDs reconcile exactly with the dashboard.

Usage: python3 extract_sections.py <index.html> <uploads_dir> <previous_index.html>
"""
import sys, json, statistics, collections
from urllib.parse import urlparse

HTML = sys.argv[1] if len(sys.argv) > 1 else '/mnt/user-data/outputs/index.html'
U    = sys.argv[2] if len(sys.argv) > 2 else '/home/claude/run_uploads'
PREV = sys.argv[3] if len(sys.argv) > 3 else None

sys.path.insert(0, '/home/claude/skill_bundle/jd-pricing-dashboard/scripts')
import rebuild  # reuse loaders / slug helper

html = open(HTML, encoding='utf-8').read()

def extract_from(text, name):
    i = text.find(f'const {name} =')
    if i < 0: return None
    eq = text.find('=', i); j = eq + 1
    while text[j] in ' \t\r\n': j += 1
    oc = text[j]; cc = ']' if oc == '[' else '}'
    d = 0; ins = False; sc = ''; esc = False; k = j
    while k < len(text):
        c = text[k]
        if esc: esc = False
        elif ins:
            if c == '\\': esc = True
            elif c == sc: ins = False
        else:
            if c in '"\'': ins = True; sc = c
            elif c == oc: d += 1
            elif c == cc:
                d -= 1
                if d == 0: return json.loads(text[j:k+1])
        k += 1
    return None

def extract(name): return extract_from(html, name)

import re
_bl = re.search(r'const CVR_BASELINE = ([0-9.]+);', html)
BASE = float(_bl.group(1)) if _bl else 0.014

PRODUCTS = extract('PRODUCTS'); PERF = extract('PERF'); VARIANTS = extract('VARIANTS')
CHANGES = extract('CHANGES'); METRICS = extract('METRICS')
MKT = extract('MARKET_CHANGES') or []; SNAPS = extract('POSITION_SNAPSHOTS') or []

# benchmark window from header meta
_hm = re.search(r'id="header-meta-content">([^<]*)<', html)
bench_period = ''
if _hm:
    _bp = re.search(r'Benchmark window:\s*(.+?)\s{2,}', _hm.group(1))
    bench_period = _bp.group(1).strip() if _bp else ''

# previous universe size (for a correct week-over-week comparison)
prev_total = None
if PREV:
    try:
        ptxt = open(PREV, encoding='utf-8').read()
        pm = extract_from(ptxt, 'METRICS')
        prev_total = pm.get('total') if pm else None
    except Exception:
        prev_total = None

feed, _ = rebuild.load_feed(U)
linkof = {pid: (f.get('link') or '') for pid, f in feed.items()}

prod_by_id = {p['id']: p for p in PRODUCTS}
perf_by_id = {r['id']: r for r in PERF}

# group clicks + id->group via VARIANTS membership
group_clicks = {}; id_to_group = {}
for g, members in VARIANTS.items():
    tot = 0
    for m in members:
        pid = m['pid']; id_to_group[pid] = g
        pr = prod_by_id.get(pid)
        if pr: tot += pr.get('c', 0) or 0
    group_clicks[g] = tot

def gap(r):
    return (r['p'] - r['m']) / r['m'] if r.get('m') else None

def url_for_group(r):
    lp = r.get('lp', '') or ''
    return ('https://jdsports.ca' + lp) if lp.startswith('/') else ''

def sess_disp(r):
    return r['sl7'] if (r.get('sl7') or 0) > 0 else None

def cvr_disp(r):
    return r.get('cl7') if (r.get('sl7') or 0) > 0 else None

# ---------- SECTION 1: recovery (volume-led) ----------
s1 = []
for r in PERF:
    if r.get('av') != 1: continue
    g = gap(r)
    if g is None or g >= -0.05: continue
    if group_clicks.get(r['id'], 0) < 50: continue
    if (r.get('ol7') or 0) <= 0 and (r.get('sl7') or 0) <= 0: continue
    headroom = r['m'] - r['p']
    score = (r.get('ol7', 0) or 0) * headroom  # velocity x per-unit headroom
    s1.append({'t': r['t'], 'url': url_for_group(r), 'b': r['b'], 'p': r['p'], 'm': r['m'],
               'gap': g, 'headroom': headroom, 'ol7': r.get('ol7', 0), 'rl7': r.get('rl7', 0),
               'sess': sess_disp(r), 'cvr': cvr_disp(r), 'nv': r.get('nv', 0), 'score': score})
seen = set(); s1d = []
for x in sorted(s1, key=lambda z: -z['score']):
    if x['t'] in seen: continue
    seen.add(x['t']); s1d.append(x)
s1_total = len(s1d); s1_top = s1d[:30]

# ---------- SECTION 1B: over-market drag ----------
s1b = []
for r in PERF:
    if r.get('av') != 1: continue
    g = gap(r)
    if g is None or g <= 0.05: continue
    if (r.get('sl7') or 0) < 100: continue
    if r.get('cl7') is None or r['cl7'] >= BASE: continue
    s1b.append({'t': r['t'], 'url': url_for_group(r), 'b': r['b'], 'p': r['p'], 'm': r['m'],
                'gap': g, 'ol7': r.get('ol7', 0), 'sess': r['sl7'], 'cvr': r['cl7'], 'nv': r.get('nv', 0)})
s1b = sorted(s1b, key=lambda z: -z['sess']); s1b_total = len(s1b); s1b_top = s1b[:20]

# ---------- SECTION 2: what worked ----------
chg_by_group = {}
for c in CHANGES:
    g = id_to_group.get(c['id'])
    if g is None: continue
    chg_by_group.setdefault(g, []).append(c)

def group_markdown(g):
    cs = [c for c in chg_by_group.get(g, []) if c.get('pct', 0) < 0]
    if not cs: return None
    cs.sort(key=lambda c: c.get('date', ''))
    return cs[-1]['pct']

s2 = []
for r in PERF:
    if r.get('av') != 1: continue
    md = group_markdown(r['id'])
    if md is None: continue
    if (r.get('ol7') or 0) < 5: continue
    if (r.get('sl7') or 0) < 100: continue
    if r.get('doo') is None: continue
    bonus = min(max(r['doo'], 0) * 5, 10)
    score = r['ol7'] * 2 + bonus
    s2.append({'t': r['t'], 'url': url_for_group(r), 'b': r['b'], 'md': md / 100.0,
               'ol7': r['ol7'], 'doo': r.get('doo'), 'rl7': r.get('rl7', 0), 'dr': r.get('dr'),
               'sess': sess_disp(r), 'ds': r.get('ds'), 'cvr': cvr_disp(r), 'dc': r.get('dc'),
               'score': score})
s2 = sorted(s2, key=lambda z: -z['score']); s2_total = len(s2); s2_top = s2[:30]

# ---------- SECTIONS 3/4: variant over/below market ----------
def cvr_for_pid(pid):
    g = id_to_group.get(pid)
    if g is None: return None
    r = perf_by_id.get(g)
    if r is None: return None
    return r.get('cl7') if (r.get('sl7') or 0) > 0 else None

over = []; below = []
for p in PRODUCTS:
    if p.get('av') != 1: continue
    if not p.get('m'): continue
    g = (p['p'] - p['m']) / p['m']
    if (p.get('c', 0) or 0) < 50: continue
    row = {'t': p['t'], 'url': linkof.get(p['id'], ''), 'b': p['b'], 'p': p['p'], 'm': p['m'],
           'gap': g, 'cvr': cvr_for_pid(p['id']), 'clicks': p['c']}
    if g > 0.05: over.append(row)
    elif g < -0.05: below.append(row)
over_total = len(over); below_total = len(below)
over_top = sorted(over, key=lambda z: -(z['gap'] * z['clicks']))[:20]
below_top = sorted(below, key=lambda z: -(abs(z['gap']) * z['clicks']))[:20]

# ---------- SECTION 5: high sessions, low CVR ----------
sessful = [r for r in PERF if (r.get('sl7') or 0) > 0]
p90 = statistics.quantiles([r['sl7'] for r in sessful], n=10)[-1] if len(sessful) >= 10 else 0
s5 = []
for r in sessful:
    if r['sl7'] < p90: continue
    if r.get('cl7') is None or r['cl7'] >= BASE: continue
    s5.append({'t': r['t'], 'url': url_for_group(r), 'b': r['b'], 'p': r['p'], 'm': r['m'],
               'gap': gap(r), 'sess': r['sl7'], 'cvr': r['cl7'], 'ol7': r.get('ol7', 0)})
s5 = sorted(s5, key=lambda z: -z['sess']); s5_total = len(s5); s5_top = s5[:20]

# ---------- SECTION 6: low sessions, high CVR ----------
s6 = []
for r in sessful:
    if r['sl7'] < 100: continue
    if r.get('cl7') is None or r['cl7'] <= 2 * BASE: continue
    if (r.get('ol7') or 0) < 2: continue
    s6.append({'t': r['t'], 'url': url_for_group(r), 'b': r['b'], 'p': r['p'], 'm': r['m'],
               'gap': gap(r), 'sess': r['sl7'], 'cvr': r['cl7'], 'ol7': r.get('ol7', 0)})
s6 = sorted(s6, key=lambda z: -z['cvr']); s6_total = len(s6); s6_top = s6[:20]

out = {
    'meta': {'total': METRICS['total'], 'groups': len(PERF), 'above': METRICS['above'],
             'at': METRICS['at'], 'below': METRICS['below'], 'on_sale': METRICS['on_sale'],
             'oos': METRICS['oos'], 'baseline': BASE, 'p90_sessions': round(p90),
             'sessful': len(sessful), 'changes_total': len(CHANGES), 'mkt_total': len(MKT),
             'snapshots': len(SNAPS), 'prev_total': prev_total, 'bench_period': bench_period},
    'counts': {'s1': s1_total, 's1b': s1b_total, 's2': s2_total, 'over': over_total,
               'below': below_total, 's5': s5_total, 's6': s6_total},
    's1': s1_top, 's1b': s1b_top, 's2': s2_top, 'over': over_top, 'below': below_top,
    's5': s5_top, 's6': s6_top,
}
json.dump(out, open('/home/claude/section_data.json', 'w'))

print("=== SANITY ===")
m = out['meta']; c = out['counts']
print(f"total {m['total']:,} (prev {m['prev_total']}) | groups {m['groups']:,} | on_sale {m['on_sale']:,} | oos {m['oos']:,}")
print(f"above {m['above']:,} / at {m['at']:,} / below {m['below']:,} | baseline {m['baseline']*100:.2f}% | bench {m['bench_period']}")
print(f"logs: changes {m['changes_total']:,} · market {m['mkt_total']:,} · snapshots {m['snapshots']}")
print(f"sessful {m['sessful']:,} of {m['groups']:,} | p90 sess {m['p90_sessions']}")
print(f"S1 {c['s1']} · S1B {c['s1b']} · S2 {c['s2']} · over {c['over']} · below {c['below']} · S5 {c['s5']} · S6 {c['s6']}")
print("S1 top 3:")
for x in s1_top[:3]:
    print(f"  {x['t'][:44]:44} ol7={x['ol7']} rev=${x['rl7']:.0f} gap={x['gap']*100:.0f}% sess={x['sess']} cvr={x['cvr']}")
