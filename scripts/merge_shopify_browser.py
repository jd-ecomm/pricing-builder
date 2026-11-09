#!/usr/bin/env python3
"""Append a browser ShopifyQL pull onto the running Shopify history files.

The Shopify connector is not used (IT flagged it). Instead the weekly run pulls
ShopifyQL through Ryan's logged-in Shopify admin in Chrome (Admin GraphQL
2025-10 `shopifyqlQuery`) and saves one JSON file to Downloads:
    shopify_pull_<start>_<end>.json  ->  {sales, lp, margin, *Cols, counts}
Rows are objects keyed by ShopifyQL column name.

Usage:
  python3 merge_shopify_browser.py <pull.json> <prev_build_dir> <out_dir>

prev_build_dir holds last week's merged files (RC_-_Daily_Product_Sales_by_SKU_-_*.csv,
RC_-_Landing_Page_Performance_*.csv, Net_Sales_&_Gross_Margin_by_Product_-_*.csv,
RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_*.csv). Days already present in
the history are replaced by the pull (late returns/edits), never duplicated.
"""
import csv, json, sys, glob, os, shutil
from pathlib import Path

def latest(d, pat):
    m = sorted(glob.glob(os.path.join(d, pat)))
    if not m:
        sys.exit(f'missing {pat} in {d}')
    return m[-1]

def rewrite(src, dst, new_rows, day_col_idx, pull_days):
    """Copy src to dst dropping rows for days in the pull, then append new rows."""
    kept = 0
    with open(src, newline='', encoding='utf-8') as fi, open(dst, 'w', newline='', encoding='utf-8') as fo:
        r = csv.reader(fi); w = csv.writer(fo, quoting=csv.QUOTE_MINIMAL)
        hdr = next(r); w.writerow(hdr)
        for row in r:
            if row and row[day_col_idx] in pull_days:
                continue
            w.writerow(row); kept += 1
        for row in new_rows:
            w.writerow(row)
    return kept

def main(pull_path, prev_dir, out_dir):
    p = json.load(open(pull_path))
    days = sorted({r['day'] for r in p['sales']} | {r['day'] for r in p['lp']} | {r['day'] for r in p['margin']})
    start, end = days[0], days[-1]
    pd = set(days)
    os.makedirs(out_dir, exist_ok=True)
    g = lambda r, k: '' if r.get(k) is None else r.get(k)

    # 1 Daily sales by SKU (same header as the RC export)
    sales_rows = []
    for r in p['sales']:
        net = float(r.get('net_sales') or 0); gp = r.get('gross_profit')
        gm = (float(gp) / net) if (net and gp not in (None, '')) else ''
        sales_rows.append([r['day'], g(r, 'product_title'), g(r, 'product_variant_sku'), g(r, 'product_id'),
                           g(r, 'product_variant_id'), g(r, 'total_sales'), g(r, 'net_sales'), g(r, 'orders'), '',
                           g(r, 'net_items_sold'), '', '', '', '', gm, g(r, 'gross_profit')])
    src = latest(prev_dir, 'RC_-_Daily_Product_Sales_by_SKU_-_*.csv')
    dst = os.path.join(out_dir, f'RC_-_Daily_Product_Sales_by_SKU_-_2025-12-28_-_{end}.csv')
    k = rewrite(src, dst, sales_rows, 0, pd)
    print(f'sales: kept {k:,} + appended {len(sales_rows):,} ({start}..{end})')

    # 2 Landing page performance (Day, path, visitors, sessions, bounce, ATC, CVR)
    lp_rows = [[r['day'], g(r, 'landing_page_path'), g(r, 'online_store_visitors'), g(r, 'sessions'),
                g(r, 'bounce_rate'), g(r, 'added_to_cart_rate'), g(r, 'conversion_rate')] for r in p['lp']]
    src = latest(prev_dir, 'RC_-_Landing_Page_Performance*.csv')
    dst = os.path.join(out_dir, f'RC_-_Landing_Page_Performance_(Market_Pricing_Dashboard)_-_2025-12-28_-_{end}.csv')
    k = rewrite(src, dst, lp_rows, 0, pd)
    print(f'landing pages: kept {k:,} + appended {len(lp_rows):,}')

    # 3 Net sales & gross margin by product title
    m_rows = [[r['day'], g(r, 'product_title_at_time_of_sale'), g(r, 'product_type'), g(r, 'gross_margin'),
               g(r, 'net_sales'), g(r, 'quantity_ordered'), g(r, 'gross_profit'), g(r, 'cost_of_goods_sold')]
              for r in p['margin']]
    src = latest(prev_dir, 'Net_Sales*Gross_Margin*.csv')
    dst = os.path.join(out_dir, f'Net_Sales_&_Gross_Margin_by_Product_-_2025-12-28_-_{end}.csv')
    k = rewrite(src, dst, m_rows, 0, pd)
    print(f'margin: kept {k:,} + appended {len(m_rows):,}')

    # 4 LP-Link (fallback mapping only) carried forward unchanged
    src = latest(prev_dir, 'RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_*.csv')
    shutil.copy(src, os.path.join(out_dir, os.path.basename(src)))

    tot = {}
    for r in p['sales']:
        tot[r['day']] = tot.get(r['day'], 0) + float(r.get('net_sales') or 0)
    print('net sales by day (check against Shopify Analytics):', {d: round(v, 2) for d, v in sorted(tot.items())})

if __name__ == '__main__':
    main(*sys.argv[1:4])
