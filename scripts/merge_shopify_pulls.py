import csv, json, shutil, sys
T='/root/.claude/projects/-home-claude/c78858f9-292f-51b3-8f24-355b33de9fbb/tool-results/'
D='/mnt/user-data/uploads/Downloads/'
O='/home/claude/build_uploads/'
END='2026-10-12'
def rows(f): return json.load(open(T+f))['rows']
# 1 Daily sales
src=D+'RC - Daily Product Sales by SKU - 2025-12-28 - 2026-09-27.csv'
dst=O+f'RC_-_Daily_Product_Sales_by_SKU_-_2025-12-28_-_{END}.csv'
shutil.copy(src,dst)
with open(dst,'a',newline='') as fo:
    w=csv.writer(fo,quoting=csv.QUOTE_MINIMAL); n=0
    for f in ['mcp-Shopify-run-analytics-query-1791916792127.txt','mcp-Shopify-run-analytics-query-1791916796595.txt']:
        for d,t,sku,pid,vid,tot,net,o,items,gp in rows(f):
            net_f=float(net or 0); gm=(float(gp)/net_f) if (net_f and gp) else ''
            w.writerow([d,t,sku,pid,vid,tot,net,o,'',items,'','','','',gm,gp]); n+=1
print('sales appended',n)
# 2 LP link (monthly) copy as-is
shutil.copy(D+'RC - Daily Product Sales by SKU with LP Link - 2025-12-28 - 2026-09-27.csv', O+'RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_2025-12-28_-_2026-09-27.csv')
# 3 LP perf
dst=O+f'RC_-_Landing_Page_Performance_(Market_Pricing_Dashboard)_-_2025-12-28_-_{END}.csv'
shutil.copy(D+'RC - Landing Page Performance (Market Pricing Dashboard) - 2025-12-28 - 2026-09-27.csv', dst)
with open(dst,'a',newline='') as fo:
    w=csv.writer(fo); n=0
    for f in ['mcp-Shopify-run-analytics-query-1791916813094.txt','mcp-Shopify-run-analytics-query-1791916814938.txt','mcp-Shopify-run-analytics-query-1791916816735.txt']:
        for r in rows(f): w.writerow(r); n+=1
print('lp appended',n)
# 4 Net sales & GM
dst=O+f'Net_Sales_&_Gross_Margin_by_Product_-_2025-12-28_-_{END}.csv'
shutil.copy(D+'Net Sales & Gross Margin by Product - 2025-12-28 - 2026-09-27.csv', dst)
with open(dst,'a',newline='') as fo:
    w=csv.writer(fo); n=0
    for d,t,pt,gm,net,q,gp,cogs in rows('mcp-Shopify-run-analytics-query-1791916822661.txt'):
        w.writerow([d,t,pt,gm,net,q,gp,cogs]); n+=1
print('margin appended',n)
