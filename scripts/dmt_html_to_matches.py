#!/usr/bin/env python3
"""Rebuild the competitor match CSV from the Daily Markdown Tracker dashboard.

The DMT run saves JD_DMT_dashboard_<date>.html to Downloads every day. Its
embedded DATA blob holds every matched row in the same column order as the
all_competitor_matches_<date>.csv export, so the CSV export step is not needed.

Usage: python3 dmt_html_to_matches.py <JD_DMT_dashboard_YYYY-MM-DD.html> <out_dir>
Writes all_competitor_matches_<date>.csv into out_dir and prints per-competitor counts.
"""
import csv, json, re, sys
from pathlib import Path

COLS = ['competitor', 'brand', 'name', 'colour', 'comp_code', 'comp_was', 'comp_now',
        'strike_pct', 'elig', '_', 'match', 'jd_title', 'jd_price', 'jd_disc_pct',
        'undercut', 'map_flag', 'comp_url', 'jd_url', 'pid', 'map_reason', 'first_seen']

def main(src, out_dir):
    s = Path(src).read_text(encoding='utf-8')
    m = re.search(r'(?:const|let|var)\s+DATA\s*=\s*', s)
    if not m:
        sys.exit('No DATA blob found in ' + src)
    data, _ = json.JSONDecoder().raw_decode(s[m.end():])
    date = data.get('date')
    out = Path(out_dir) / f'all_competitor_matches_{date}.csv'
    n = 0
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for c in data['competitors']:
            rows = [r for r in c['products'] if r[9] in ('E', 'M')]  # matched rows only
            for r in rows:
                w.writerow([c['name']] + list(r[0:20]))
                n += 1
            ex = sum(1 for r in rows if r[9] == 'E')
            print(f"  {c['name']}: {len(rows)} matched ({ex} exact)")
    print(f'Wrote {out} ({n} rows, tracker date {date})')
    return out

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
