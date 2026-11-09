#!/usr/bin/env python3
"""
JD Sports Canada — Online Shopping Market Pricing Dashboard rebuild
====================================================================

This script injects fresh weekly data into the REAL template that lives in
`template/template_part1.html` + `template/template_part2.html`. The template
is the actual dashboard source — never reconstruct it from scratch.

Usage:
  python3 rebuild.py \
      --uploads /mnt/user-data/uploads \
      --previous /path/to/current/index.html \
      --output   /path/to/new/index.html

If --previous is supplied, the script extracts the existing
POSITION_SNAPSHOTS and PRICE_HISTORY blocks and appends the new week.
Otherwise both start fresh with just this week's data point.

Input files (auto-discovered by filename prefix in --uploads):
  Your_most_popular_products_with_price_benchmarks_*.csv
  Sale_price_suggestions_with_highest_performance_impact_*.csv
  products_*.zip
  RC_-_Daily_Product_Sales_by_SKU_-_*.csv
  RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_*.csv
  RC_-_Landing_Page_Performance_-_*.csv

Output: a single self-contained index.html
"""

import argparse, csv, gzip, json, os, re, sys, zipfile
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent / 'template'
TEMPLATE_P1 = TEMPLATE_DIR / 'template_part1.html'
TEMPLATE_P2 = TEMPLATE_DIR / 'template_part2.html'

CURRENCY = 'CAD'
AT_MARKET_BAND = 0.02
TODAY = date.fromisoformat(__import__("os").environ["RUN_DATE"]) if __import__("os").environ.get("RUN_DATE") else date.today()
# Rolling window for the cumulative logs and per-product history. Keeps the
# self-contained HTML bounded in size. History currently spans ~18 weeks, so a
# 26-week window costs nothing today and caps future growth.
HISTORY_WEEKS = 520  # keep full change history (no trimming)
HISTORY_CUTOFF = (TODAY - timedelta(weeks=HISTORY_WEEKS)).isoformat()

# ─── Helpers ─────────────────────────────────────────────────────────────
def find_one(uploads_dir, pattern, required=True):
    matches = sorted(Path(uploads_dir).glob(pattern))
    if not matches:
        if required:
            sys.exit(f"❌ Missing input matching: {pattern} in {uploads_dir}")
        return None
    return matches[-1]

def parse_money(s):
    if not s or not str(s).strip(): return None
    s = str(s).strip().split()[0].replace(',', '').replace('$', '')
    try: return float(s)
    except ValueError: return None

def parse_date(s):
    try: return datetime.strptime(s, '%Y-%m-%d').date()
    except (ValueError, TypeError): return None

def round_to_cents(v):
    return round(v, 2) if v is not None else None

# ─── Load inputs ─────────────────────────────────────────────────────────
_SHOPIFY_ID = re.compile(r'^shopify_[A-Z]{2}_\d+_(\d+)$')

def norm_pid(raw):
    """Map Merchant Center's Shopify-app ids (shopify_ZZ_<product>_<variant>)
    to the plain variant id used by the feed and Shopify sales."""
    raw = (raw or '').strip()
    m = _SHOPIFY_ID.match(raw)
    return m.group(1) if m else raw

def load_price_benchmarks(uploads_dir):
    path = find_one(uploads_dir, 'Your_most_popular_products_with_price_benchmarks_*.csv')
    print(f"📊 Price benchmarks: {path.name}")
    out = {}
    time_period = None
    with open(path, encoding='utf-8') as f:
        f.readline()
        tp = f.readline().strip().strip('"')
        if tp.lower().startswith('time period'):
            time_period = tp.split(':', 1)[1].strip()
        reader = csv.DictReader(f)
        dup = 0
        for row in reader:
            pid = norm_pid(row['Product ID'])
            if not pid: continue
            rec = {
                'title': row['Title'].strip(),
                'brand': row['Brand'].strip().lower(),
                'your_price': parse_money(row['Your price']),
                'market': parse_money(row['Benchmark']),
                'clicks': int(float(row['Clicks'])) if row['Clicks'] else 0,
            }
            # Oct 2026: Merchant Center carries the same variant from two sources
            # (feed id '4365…' and Shopify app id 'shopify_ZZ_<product>_<variant>')
            # plus French-language rows. Merge them: keep the benchmark/title of
            # the listing with the most clicks, and sum clicks across listings.
            if pid in out:
                dup += 1
                cur = out[pid]
                total = cur['clicks'] + rec['clicks']
                if rec['clicks'] > cur['clicks']:
                    out[pid] = rec
                out[pid]['clicks'] = total
            else:
                out[pid] = rec
    print(f"   → {len(out):,} benchmarks ({dup:,} duplicate listings merged)")
    return out, time_period

def load_sps(uploads_dir):
    path = find_one(uploads_dir, 'Sale_price_suggestions_with_highest_performance_impact_*.csv')
    print(f"💡 Sale price suggestions: {path.name}")
    out = {}
    with open(path, encoding='utf-8') as f:
        f.readline()
        reader = csv.DictReader(f)
        for row in reader:
            pid = norm_pid(row['Product ID'])
            if not pid: continue
            out[pid] = {
                'sp': parse_money(row['Suggested price']),
                'cu': float(row['Click uplift']) if row['Click uplift'] else None,
                'vu': float(row['Conversion uplift']) if row['Conversion uplift'] else None,
                'ef': row['Effectiveness'].strip() or None,
            }
    print(f"   → {len(out):,} simulations")
    return out

def load_feed(uploads_dir):
    zpath = find_one(uploads_dir, 'products_*.zip')
    print(f"🛒 Product feed: {zpath.name}")
    out = {}
    feed_dt = None
    m = re.search(r'products_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', zpath.name)
    if m:
        feed_dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", '%Y-%m-%d %H-%M-%S')
    with zipfile.ZipFile(zpath) as zf:
        tname = [n for n in zf.namelist() if n.endswith('.tsv')][0]
        text = zf.read(tname).decode('utf-8', errors='replace')
    lines = text.splitlines()
    shopify_src = {}   # Oct 2026: second Merchant Center source (Shopify app)
    for row in csv.DictReader(lines, delimiter='\t'):
        raw = (row.get('id') or '').strip()
        if not raw: continue
        # Skip French composite-id rows
        if '_' in raw and '|' in raw: continue
        pid = norm_pid(raw)
        if pid != raw:
            # Shopify-app source row: English only, used to fill gaps after the
            # main feed is read (these rows carry no style id / cost).
            if (row.get('language') or '').strip().lower() == 'en' and pid not in shopify_src:
                shopify_src[pid] = row
            continue
        if pid in out: continue
        price = parse_money(row.get('price'))
        sale = parse_money(row.get('sale price'))
        effective = sale if sale is not None else price
        out[pid] = {
            'title': (row.get('title') or '').strip(),
            'brand': (row.get('brand') or '').strip().lower(),
            'price': price,         # regular price
            'sale_price': sale,
            'effective': effective,
            'is_on_sale': sale is not None,
            'availability': (row.get('availability') or '').strip(),
            'gtin': (row.get('gtin') or '').strip(),
            'image': (row.get('image link') or '').strip(),
            'link': (row.get('link') or '').strip(),
            'cost': parse_money(row.get('cost of goods sold')),
            'style_id': ((row.get('custom label 1') or '').split('|')[0].strip()
                         if '|' in (row.get('custom label 1') or '') else ''),
        }
    filled = 0
    for pid, row in shopify_src.items():
        if pid in out: continue
        price = parse_money(row.get('price')); sale = parse_money(row.get('sale price'))
        out[pid] = {
            'title': (row.get('title') or '').strip(),
            'brand': (row.get('brand') or '').strip().lower(),
            'price': price, 'sale_price': sale,
            'effective': sale if sale is not None else price,
            'is_on_sale': sale is not None,
            'availability': (row.get('availability') or '').strip(),
            'gtin': (row.get('gtin') or '').strip(),
            'image': (row.get('image link') or '').strip(),
            'link': (row.get('link') or '').strip(),
            'cost': parse_money(row.get('cost of goods sold')),
            'style_id': '',
        }
        filled += 1
    print(f"   → {len(out):,} unique EN-locale feed products ({filled:,} filled from the Shopify-app source)")
    return out, feed_dt

def _col(row, *candidates, required=True):
    """Return the value of the first matching column name present in `row`.
    Schema-tolerant: Shopify renames columns between export versions
    (e.g. 'Orders (last click)' vs 'Orders'). Pass all known aliases.
    """
    for name in candidates:
        if name in row:
            return row[name]
    if required:
        raise KeyError(
            f"None of these columns found: {candidates}. "
            f"Available: {list(row.keys())}")
    return None

def _lp_path(value):
    """Normalise a landing page reference to a path.
    Accepts a bare path ('/products/x') or a full URL
    ('https://jdsports.ca/products/x') and returns '/products/x'.
    """
    if not value:
        return ''
    v = value.strip()
    if v.startswith('http://') or v.startswith('https://'):
        # Strip scheme + host
        rest = v.split('://', 1)[1]
        slash = rest.find('/')
        v = rest[slash:] if slash >= 0 else '/'
    # Drop query string / fragment
    for ch in ('?', '#'):
        if ch in v:
            v = v.split(ch, 1)[0]
    # Strip /fr locale prefix so French URLs are comparable to English
    if v.startswith('/fr/'):
        v = v[3:]
    return v


# Keyword tokenisation for LP-vs-canonical-slug matching.
# Slugs look like: 'puma-womens-speedcat-full-leather-black-white'.
# We tokenise on hyphens, drop short stopwords, and use Jaccard overlap.
_SLUG_STOPWORDS = {
    'the', 'and', 'with', 'a', 'an', 'of', 's',
    'mens', 'womens', 'kids', 'juniors', 'children', 'childrens',
    'infants', 'toddler', 'youth', 'gs', 'ps', 'td',
}

def _slug_tokens(slug):
    """Tokenise a product slug, dropping stopwords and short fragments."""
    if not slug:
        return set()
    toks = [t for t in slug.lower().split('-') if t]
    return {t for t in toks if len(t) >= 3 and t not in _SLUG_STOPWORDS}


def _extract_product_slug(path):
    """Pull the product slug out of a path, accepting both
       /products/<slug>                           (canonical PDP)
       /collections/<anything>/products/<slug>    (collection-scoped PDP)
    Returns the slug string, or None if the path isn't a product page."""
    if not path:
        return None
    # Direct /products/<slug>
    if path.startswith('/products/'):
        slug = path[len('/products/'):].split('/', 1)[0]
        return slug or None
    # /collections/.../products/<slug>
    if path.startswith('/collections/'):
        i = path.find('/products/')
        if i >= 0:
            slug = path[i + len('/products/'):].split('/', 1)[0]
            return slug or None
    return None

def build_sku_to_id_map(uploads_dir):
    """The plain Daily Sales export dropped its 'Product variant ID' column
    in the May 2026 schema change, but the LP-Link export still carries BOTH
    'Product variant SKU' and 'Product variant ID'. Build the SKU -> ID lookup
    from the LP-Link file so we can backfill IDs onto the plain Daily Sales rows.
    """
    path = find_one(uploads_dir, 'RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_*.csv')
    sku_to_id = {}
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sku = _col(row, 'Product variant SKU', required=False)
            vid = _col(row, 'Product variant ID', 'Product ID', required=False)
            if not sku or not vid: continue
            sku = sku.strip(); vid = vid.strip()
            if sku and vid and sku not in sku_to_id:
                sku_to_id[sku] = vid
    print(f"   → SKU→ID map: {len(sku_to_id):,} pairs (from LP-Link file)")
    return sku_to_id

def load_daily_sales(uploads_dir, pb_ids):
    path = find_one(uploads_dir, 'RC_-_Daily_Product_Sales_by_SKU_-_*.csv')
    print(f"💰 Daily sales: {path.name}")

    # The plain Daily Sales file may not carry 'Product variant ID' (schema
    # change). Detect this and, if missing, backfill from the LP-Link file.
    with open(path, encoding='utf-8') as f:
        header = next(csv.reader(f))
    has_vid = ('Product variant ID' in header) or ('Product ID' in header)
    sku_to_id = {} if has_vid else build_sku_to_id_map(uploads_dir)
    if not has_vid:
        print(f"   → 'Product variant ID' absent — backfilling via SKU")

    daily = defaultdict(lambda: {'o': 0, 'r': 0.0})
    sku_map = {}
    max_date = None
    rows_kept = 0
    rows_unmatched_sku = 0
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sku = (_col(row, 'Product variant SKU', required=False) or '').strip()
            if has_vid:
                vid = (_col(row, 'Product variant ID', 'Product ID') or '').strip()
            else:
                vid = sku_to_id.get(sku, '')
                if not vid:
                    rows_unmatched_sku += 1
                    continue
            if vid not in pb_ids: continue
            d = parse_date(_col(row, 'Day', 'Date'))
            if d is None: continue
            if max_date is None or d > max_date: max_date = d
            orders = int(float(_col(row, 'Orders (last click)', 'Orders') or 0))
            net = float(_col(row, 'Net sales (last click)', 'Net sales') or 0)
            daily[(vid, d)]['o'] += orders
            daily[(vid, d)]['r'] += net
            if vid not in sku_map and sku:
                sku_map[vid] = sku
            rows_kept += 1
    if rows_unmatched_sku:
        print(f"   → {rows_unmatched_sku:,} rows skipped (SKU not in LP-Link map)")
    print(f"   → {rows_kept:,} rows; latest sales date {max_date}")
    return daily, sku_map, max_date


def load_sales_with_lp(uploads_dir, pb_ids, products=None, lookback=28):
    """Build a variant_id -> landing-page-path mapping.

    Smarter matching (June 2026): a customer's actual landing page is often
    DIFFERENT from the product they ended up buying (cross-product browsing,
    search→category→PDP journeys, etc.). Naive 'most common LP' produces
    phantom buckets where unrelated variants share a junk key.

    This version uses each variant's canonical slug (from feed `link`) and
    only keeps LPs whose extracted slug shares ≥50% of canonical keyword
    tokens. Accepts both /products/<slug> and /collections/.../products/<slug>.
    Falls back to None (so the grouping layer uses the title key) when no LP
    matches confidently.
    """
    path = find_one(uploads_dir, 'RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_*.csv')
    print(f"🔗 Sales w/ LP: {path.name}")
    # Detect granularity
    with open(path, encoding='utf-8') as f:
        header = next(csv.reader(f))
    is_monthly = 'Month' in header and 'Day' not in header
    date_col = 'Month' if is_monthly else 'Day'
    if is_monthly:
        print("   ⚠ WARNING: this is the MONTHLY LP-Link export.")
        print("   ⚠ Variant→LP mapping will use all available months (cannot apply 28d cutoff).")
        print("   ⚠ Re-export with date dimension Day for more granular mapping.")

    # Build canonical-slug map from products
    canonical_slug = {}    # vid -> canonical slug string
    canonical_tokens = {}  # vid -> set of keyword tokens
    if products:
        for p in products:
            link = p.get('_link', '')
            from urllib.parse import urlparse
            path_str = urlparse(link).path if link else ''
            slug = _extract_product_slug(path_str)
            if slug:
                canonical_slug[p['id']] = slug
                canonical_tokens[p['id']] = _slug_tokens(slug)

    # Aggregate LP votes per variant
    cnt = defaultdict(Counter)
    cutoff = TODAY - timedelta(days=lookback)
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            vid = (_col(row, 'Product variant ID', 'Product ID', required=False) or '').strip()
            if vid not in pb_ids: continue
            d = parse_date(_col(row, date_col, 'Date'))
            if d is None: continue
            if not is_monthly and d < cutoff: continue
            lp = _lp_path(_col(row, 'Order landing page path',
                               'Landing page URL', 'Landing page path',
                               required=False))
            if lp: cnt[vid][lp] += 1

    # Path matching (June 2026): map each variant directly to its own canonical
    # product path (/products/<slug>) taken from the feed link. This is a clean
    # path-to-path join with the session data (which load_lp_perf also collapses
    # onto the canonical slug), so it captures every PDP-entry session regardless
    # of whether the buyer landed on the canonical or a collection-scoped path,
    # and it does not depend on the variant appearing in the order-landing data.
    mapping = {}
    stats = {'canonical_match': 0, 'order_path_fallback': 0, 'no_match': 0}
    # 1) Canonical match for every product that has a feed-link slug
    for vid, slug in canonical_slug.items():
        mapping[vid] = '/products/' + slug
        stats['canonical_match'] += 1
    # 2) Fallback for variants with no feed-link slug: most common product path
    #    seen in their order-landing data
    for vid, lp_counts in cnt.items():
        if vid in mapping: continue
        chosen = None
        for lp, _votes in lp_counts.most_common():
            s = _extract_product_slug(lp)
            if s:
                chosen = '/products/' + s
                break
        if chosen:
            mapping[vid] = chosen
            stats['order_path_fallback'] += 1
        else:
            stats['no_match'] += 1

    print(f"   → {len(mapping):,} variants → LP path")
    print(f"      canonical (feed-link) match: {stats['canonical_match']:,}")
    print(f"      order-path fallback:         {stats['order_path_fallback']:,}")
    print(f"      no match (title fallback):   {stats['no_match']:,}")
    return mapping


def load_lp_perf(uploads_dir, window_start, window_end):
    path = find_one(uploads_dir, 'RC_-_Landing_Page_Performance*.csv')
    print(f"📈 Landing page perf: {path.name}")

    # Detect granularity. The daily export has a 'Day' column; the monthly
    # export has 'Month'. Sessions/CVR timeseries needs the daily file.
    with open(path, encoding='utf-8') as f:
        header = next(csv.reader(f))
    is_daily = 'Day' in header
    is_monthly = 'Month' in header and not is_daily
    if is_monthly:
        print("   ⚠ WARNING: this is the MONTHLY Landing Page export.")
        print("   ⚠ Sessions/CVR will be monthly, not daily — the YTD chart")
        print("   ⚠ overlay and L7 CVR depend on the DAILY export. Re-export")
        print("   ⚠ from Shopify with the date dimension set to 'Day'.")

    lp_daily = defaultdict(lambda: {'sess': 0, 'compl': 0})
    L7_start = window_end - timedelta(days=6)
    site_sess = site_compl = 0
    granularity = 'monthly' if is_monthly else 'daily'
    # Some filtered exports (e.g. the <10-sessions-removed variant) drop the
    # 'Landing page type' column entirely. When that column is absent we can't
    # gate on type == 'Product', so fall back to product-path detection.
    has_type_col = 'Landing page type' in header
    has_compl_col = 'Sessions that completed checkout' in header
    if not has_type_col:
        print("   ℹ No 'Landing page type' column — gating on /products/ path instead")
    if not has_compl_col:
        print("   ℹ No completed-checkout column — deriving completions from Conversion rate × Sessions")
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            raw = _lp_path(_col(row, 'Landing page path', 'Landing page URL',
                                required=False))
            if has_type_col:
                lptype = (_col(row, 'Landing page type', required=False) or '').strip()
                if lptype != 'Product': continue
            # Path matching: collapse every landing path to its canonical
            # product slug so /products/<slug> and /collections/.../products/<slug>
            # aggregate onto one key — the same key the variant→LP mapping uses.
            slug = _extract_product_slug(raw)
            if slug is None: continue
            lp = '/products/' + slug
            d = parse_date(_col(row, 'Day', 'Month', 'Date'))
            if d is None or d < window_start or d > window_end: continue
            s = int(float(_col(row, 'Sessions') or 0))
            if has_compl_col:
                c = int(float(_col(row, 'Sessions that completed checkout') or 0))
            else:
                cr = float(_col(row, 'Conversion rate', required=False) or 0)
                c = int(round(s * cr))
            lp_daily[(lp, d)]['sess'] += s
            lp_daily[(lp, d)]['compl'] += c
            if d >= L7_start:
                site_sess += s
                site_compl += c
    cvr = (site_compl / site_sess) if site_sess else 0
    print(f"   → site L7 CVR {cvr*100:.2f}% ({granularity} source)")
    return lp_daily, cvr, granularity

# ─── Extract prior state from existing index.html ─────────────────────────
def _extract_js_literal(text, const_name):
    """Find `const NAME = [...]` or `const NAME = {...}` and return the literal
    using bracket balancing (regex is fragile when literals are large or contain
    `];` substrings that don't actually close them).

    Returns the JS literal string (e.g. '[{...},{...}]'), or None if not found.
    """
    needle = f'const {const_name}'
    start_pos = text.find(needle)
    if start_pos < 0:
        return None
    eq = text.find('=', start_pos)
    if eq < 0: return None
    i = eq + 1
    while i < len(text) and text[i] in ' \t\r\n':
        i += 1
    if i >= len(text) or text[i] not in '[{':
        return None
    open_ch = text[i]
    close_ch = ']' if open_ch == '[' else '}'
    literal_start = i
    depth = 0
    in_str = False
    str_ch = ''
    escape = False
    while i < len(text):
        c = text[i]
        if escape:
            escape = False
        elif in_str:
            if c == '\\':
                escape = True
            elif c == str_ch:
                in_str = False
        else:
            if c in '"\'':
                in_str = True
                str_ch = c
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return text[literal_start:i + 1]
        i += 1
    return None


def reconstruct_market_history_from_prior(prev_html_path):
    """The prior dashboard didn't store a per-product MARKET_HISTORY constant,
    but it can be reconstructed from MARKET_CHANGES + PRODUCTS:

    - Each MARKET_CHANGES record has {date, id, old, new}.
    - For a given product, all `old` values are the SAME baseline (verified
      across 1,167 multi-change products: 100% consistent).
    - The baseline `old` corresponds to the FIRST snapshot date (Apr 22, the
      start of the historical period the prior file knew about).
    - Each `new` is the market price AT that change-date.
    - The live `m` value in PRODUCTS is the most recent snapshot's market
      price (typically the day the prior build was generated).

    Returns: {product_id: [{d: 'YYYY-MM-DD', p: price}, ...]}
    """
    if not prev_html_path or not Path(prev_html_path).exists():
        return {}
    text = Path(prev_html_path).read_text(encoding='utf-8')

    mc_js = _extract_js_literal(text, 'MARKET_CHANGES')
    prods_js = _extract_js_literal(text, 'PRODUCTS')
    if mc_js is None or prods_js is None:
        return {}
    try:
        mc = json.loads(mc_js)
        prods = json.loads(prods_js)
    except Exception as e:
        print(f"   ⚠ Could not parse prior PRODUCTS or MARKET_CHANGES: {e}")
        return {}

    # Look at PRICE_HISTORY for the SAME product to find which date the prior
    # build was generated (typically the latest PRICE_HISTORY date).
    ph_js = _extract_js_literal(text, 'PRICE_HISTORY')
    latest_date = None
    if ph_js is not None:
        try:
            ph = json.loads(ph_js)
            all_dates = set()
            for hist in ph.values():
                for entry in hist:
                    if entry.get('d'): all_dates.add(entry['d'])
            if all_dates:
                latest_date = max(all_dates)
                print(f"   → Prior dashboard latest snapshot date: {latest_date}")
        except Exception:
            pass

    # Find the baseline date — earliest date in PRICE_HISTORY
    baseline_date = None
    if ph_js is not None:
        try:
            ph = json.loads(ph_js)
            all_dates = set()
            for hist in ph.values():
                for entry in hist:
                    if entry.get('d'): all_dates.add(entry['d'])
            if all_dates:
                baseline_date = min(all_dates)
        except Exception:
            pass

    # Group MARKET_CHANGES by product
    changes_by_pid = defaultdict(list)
    for c in mc:
        changes_by_pid[c['id']].append(c)

    # Build market history per product
    market_history = {}
    by_id = {p['id']: p for p in prods}
    all_change_dates = sorted(set(c['date'] for c in mc))

    for pid, prod in by_id.items():
        if prod.get('m') is None: continue
        evs = sorted(changes_by_pid.get(pid, []), key=lambda x: x['date'])
        history = []
        if evs:
            # Product had at least one change. Baseline = first 'old' value.
            baseline = evs[0]['old']
            if baseline_date:
                history.append({'d': baseline_date, 'p': baseline})
            # Add each change date's 'new'
            for e in evs:
                history.append({'d': e['date'], 'p': e['new']})
            # Add the latest snapshot date with current PRODUCTS.m (if different
            # date from the last change)
            if latest_date and (not history or history[-1]['d'] != latest_date):
                history.append({'d': latest_date, 'p': prod['m']})
        else:
            # No changes recorded → market price was stable across all snapshots.
            # Just record current m at baseline + latest dates.
            if baseline_date:
                history.append({'d': baseline_date, 'p': prod['m']})
            if latest_date and latest_date != baseline_date:
                history.append({'d': latest_date, 'p': prod['m']})

        market_history[pid] = history

    print(f"   → Reconstructed market history for {len(market_history):,} products")
    return market_history


def _axis_encode(hist_dict):
    """{id:[{d,p}]} -> (shared sorted dates, {id:[values aligned to dates]}).
    Lossless: removes the repeated date strings/keys from every point."""
    dates = sorted({e['d'] for arr in hist_dict.values() for e in arr})
    didx = {d: i for i, d in enumerate(dates)}
    out = {}
    for pid, arr in hist_dict.items():
        vals = [None] * len(dates)
        for e in arr:
            vals[didx[e['d']]] = e['p']
        while vals and vals[-1] is None:
            vals.pop()
        out[pid] = vals
    return dates, out

def _axis_decode(text, hist_raw, dates_name):
    """Read either the axis form ({id:[values]} + a *_DATES const) or the old
    {id:[{d,p}]} form, returning the internal {id:[{d,p}]} working format."""
    if not hist_raw:
        return hist_raw
    sample = next((v for v in hist_raw.values() if v), None)
    if sample and isinstance(sample[0], dict):
        return hist_raw  # already {d,p}
    dates_js = _extract_js_literal(text, dates_name)
    dates = json.loads(dates_js) if dates_js else []
    out = {}
    for pid, vals in hist_raw.items():
        out[pid] = [{'d': dates[i], 'p': v} for i, v in enumerate(vals)
                    if v is not None and i < len(dates)]
    return out


def extract_prior_perf_prices(prev_html_path):
    """{group_id: median ecomm price} from the previous build's PERF, for the
    week-over-week Prev Price column."""
    if not prev_html_path or not Path(prev_html_path).exists():
        return {}
    js = _extract_js_literal(Path(prev_html_path).read_text(), 'PERF')
    if not js:
        return {}
    try:
        perf = json.loads(js)
    except Exception:
        return {}
    return {r['id']: r['p'] for r in perf if r.get('p') is not None}


def extract_prior_history(prev_html_path):
    """Returns (position_snapshots, price_history, market_history,
                prior_changes, prior_market_changes) from previous build."""
    if not prev_html_path or not Path(prev_html_path).exists():
        return [], {}, {}, [], []
    text = Path(prev_html_path).read_text(encoding='utf-8')

    # POSITION_SNAPSHOTS  (JS object literal, unquoted keys, possibly single-quoted strings)
    snaps = []
    js = _extract_js_literal(text, 'POSITION_SNAPSHOTS')
    if js is not None:
        try:
            json_str = re.sub(
                r'([{,]\s*)([A-Za-z_][A-Za-z_0-9]*)\s*:',
                r'\1"\2":',
                js
            )
            json_str = re.sub(r":\s*'([^']*)'", r': "\1"', json_str)
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            snaps = json.loads(json_str)
            print(f"   → Extracted {len(snaps)} prior position snapshots")
        except Exception as e:
            print(f"   ⚠ Could not parse POSITION_SNAPSHOTS: {e}")

    # PRICE_HISTORY
    ph = {}
    js = _extract_js_literal(text, 'PRICE_HISTORY')
    if js is not None:
        try:
            ph = _axis_decode(text, json.loads(js), 'PH_DATES')
            print(f"   → Extracted price history for {len(ph):,} products")
        except Exception as e:
            print(f"   ⚠ Could not parse PRICE_HISTORY: {e}")

    # MARKET_HISTORY (newer builds only — older files won't have it; reconstruct from MARKET_CHANGES)
    mh = {}
    js = _extract_js_literal(text, 'MARKET_HISTORY')
    if js is not None:
        try:
            mh = _axis_decode(text, json.loads(js), 'MH_DATES')
            print(f"   → Extracted market history for {len(mh):,} products")
        except Exception as e:
            print(f"   ⚠ Could not parse MARKET_HISTORY: {e}")
    else:
        print(f"   → No MARKET_HISTORY constant in prior file — reconstructing from MARKET_CHANGES + PRODUCTS")
        mh = reconstruct_market_history_from_prior(prev_html_path)

    # Prior CHANGES log (cumulative across runs)
    prior_changes = []
    js = _extract_js_literal(text, 'CHANGES')
    if js is not None:
        try:
            prior_changes = json.loads(js)
            print(f"   → Extracted {len(prior_changes):,} prior CHANGES records")
        except Exception as e:
            print(f"   ⚠ Could not parse CHANGES: {e}")

    # Prior MARKET_CHANGES log (cumulative across runs)
    prior_market_changes = []
    js = _extract_js_literal(text, 'MARKET_CHANGES')
    prior_titles = {}
    tj = _extract_js_literal(text, 'TITLES')
    if tj is not None:
        try: prior_titles = json.loads(tj)
        except Exception: prior_titles = {}
    if js is not None:
        try:
            raw = json.loads(js)
            # Slim format {d: index into MC_DATES, id, pct} -> restore 'date'
            mcd_js = _extract_js_literal(text, 'MC_DATES')
            mcd = json.loads(mcd_js) if mcd_js else []
            for c in raw:
                if 'date' not in c and 'd' in c and isinstance(c['d'], int) and c['d'] < len(mcd):
                    c = {'date': mcd[c['d']], 'id': c['id'], 'pct': c.get('pct', 0)}
                prior_market_changes.append(c)
            print(f"   → Extracted {len(prior_market_changes):,} prior MARKET_CHANGES records")
        except Exception as e:
            print(f"   ⚠ Could not parse MARKET_CHANGES: {e}")
    # Rebuild the full market-change log from MARKET_HISTORY (lossless source):
    # every consecutive pair of market prices that moved >= $1 and >= 2%.
    rec = 0
    for pid, hist in mh.items():
        prev = None
        for e in hist:
            if e.get('p') is None: continue
            if prev is not None:
                delta = e['p'] - prev['p']
                pct = (delta / prev['p']) * 100 if prev['p'] else 0
                if abs(delta) >= 1.0 and abs(pct) >= 2.0:
                    r = {'date': e['d'], 'id': pid, 'old': round(prev['p'], 2), 'new': e['p'],
                         'delta': round(delta, 2), 'pct': round(pct, 1), 'sku': ''}
                    t = prior_titles.get(pid)
                    if t: r['t'], r['b'] = t[0], t[1]
                    prior_market_changes.append(r); rec += 1
            prev = e
    print(f"   → Reconstructed {rec:,} market changes from MARKET_HISTORY")

    return snaps, ph, mh, prior_changes, prior_market_changes

# ─── Build dashboard data ────────────────────────────────────────────────
def build_products(pb, sps, feed):
    """Build PRODUCTS list. Field names match the template's JS:
       id, t, b, p, m, c, os, rp, sa, sk, gt, av, sp, cu, vu, ef"""
    products = []
    sps_excluded = 0
    for pid, b in pb.items():
        f = feed.get(pid)
        if not f: continue
        if f['effective'] is None or b['market'] is None or b['market'] == 0:
            continue
        rec = {
            'id': pid,
            't': b['title'] or f['title'],
            'b': b['brand'] or f['brand'],
            'p': round_to_cents(f['effective']),
            'm': round_to_cents(b['market']),
            'c': b['clicks'],
            'os': 1 if f['is_on_sale'] else 0,
            'av': 1 if f['availability'] == 'in stock' else 0,
            '_link': f.get('link', ''),  # internal use for LP matching (not emitted to PRODUCTS JS)
        }
        if f['is_on_sale'] and f['price'] is not None:
            rec['rp'] = round_to_cents(f['price'])
            rec['sa'] = round_to_cents(f['sale_price'])
        if f['gtin']: rec['gt'] = f['gtin']
        if f.get('cost') is not None: rec['co'] = round_to_cents(f['cost'])
        if f.get('style_id'): rec['si'] = f['style_id']
        s = sps.get(pid)
        if s:
            if s['sp'] is not None: rec['sp'] = round_to_cents(s['sp'])
            if s['cu'] is not None: rec['cu'] = round(s['cu'], 4)
            if s['vu'] is not None: rec['vu'] = round(s['vu'], 4)
            if s['ef']: rec['ef'] = s['ef']
        products.append(rec)
    sps_excluded = sum(1 for pid in sps if pid not in pb)
    return products, sps_excluded

def build_metrics(products):
    above = below = at = 0
    with_sim = high_eff = med_eff = 0
    clicks = on_sale = oos = in_stock = 0
    for p in products:
        if p['m']:
            gap = (p['p'] - p['m']) / p['m']
            if gap > AT_MARKET_BAND: above += 1
            elif gap < -AT_MARKET_BAND: below += 1
            else: at += 1
        if 'sp' in p: with_sim += 1
        if p.get('ef') == 'High': high_eff += 1
        if p.get('ef') == 'Medium': med_eff += 1
        clicks += p['c']
        if p['os']: on_sale += 1
        if p['av'] == 0: oos += 1
        else: in_stock += 1
    return {
        'total': len(products),
        'with_sim': with_sim,
        'high_eff': high_eff,
        'med_eff': med_eff,
        'above': above,
        'below': below,
        'at': at,
        'clicks': clicks,
        'on_sale': on_sale,
        'oos': oos,
        'in_stock': in_stock,
    }

def build_brands(products):
    """BRANDS fields: b, n, w (=n), c (clicks), o (over), a (at), u (below),
       hi (high eff), md (med eff), sim (with simulation), mg (median gap)."""
    by = defaultdict(lambda: {
        'n': 0, 'c': 0, 'o': 0, 'a': 0, 'u': 0,
        'hi': 0, 'md': 0, 'sim': 0, 'gaps': []
    })
    for p in products:
        b = by[p['b']]
        b['n'] += 1
        b['c'] += p['c']
        if p['m']:
            gap = (p['p'] - p['m']) / p['m']
            b['gaps'].append(gap)
            if gap > AT_MARKET_BAND: b['o'] += 1
            elif gap < -AT_MARKET_BAND: b['u'] += 1
            else: b['a'] += 1
        if 'sp' in p: b['sim'] += 1
        if p.get('ef') == 'High': b['hi'] += 1
        elif p.get('ef') == 'Medium': b['md'] += 1
    out = []
    for brand, v in by.items():
        gaps = sorted(v['gaps'])
        mg = gaps[len(gaps)//2] if gaps else 0.0
        out.append({
            'b': brand,
            'n': v['n'],
            'w': v['n'],
            'c': v['c'],
            'o': v['o'],
            'a': v['a'],
            'u': v['u'],
            'hi': v['hi'],
            'md': v['md'],
            'sim': v['sim'],
            'mg': round(mg, 4),
        })
    out.sort(key=lambda x: -x['c'])
    return out

def load_realized_margin(uploads_dir, l7_start, l7_end):
    """Realized gross margin per product over L7, from the Net Sales & Gross
    Margin export (joined by title). Returns {normalised_title: margin_fraction}."""
    path = find_one(uploads_dir, 'Net_Sales*Gross_Margin*.csv', required=False)
    if not path:
        return {}
    agg = defaultdict(lambda: [0.0, 0.0])  # title -> [net, cogs]
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('Day'))
            if d is None or d < l7_start or d > l7_end:
                continue
            t = _norm_title(row.get('Product title at time of sale'))
            try: net = float(row.get('Net sales') or 0)
            except: net = 0.0
            try: cogs = float(row.get('Cost of goods sold') or 0)
            except: cogs = 0.0
            agg[t][0] += net; agg[t][1] += cogs
    out = {}
    for t, (net, cogs) in agg.items():
        if net > 0:
            out[t] = round(1 - (cogs / net), 4)
    print(f"   \u2192 Realized L7 margin for {len(out):,} products (from Net Sales & Gross Margin)")
    return out


def _norm_title(t):
    return re.sub(r'\s+', ' ', (t or '').lower().replace('\u2019', "'")).strip()


_MD_STOP = {'the', 'and', 'with', 'of'}
def _title_tokens(t):
    ws = re.sub(r'[^a-z0-9 ]', ' ', (t or '').lower()).split()
    return frozenset(w for w in ws if w not in _MD_STOP)


def load_competitors(uploads_dir):
    """Competitor price matches (Foot Locker / Champs / Little Burgundy) from the
    Daily Markdown Tracker's matched export, keyed to JD by product URL. Returns
    {group_key(/products/slug): [ {c,now,was,disc,mt,pos,url}, ... ]}."""
    import glob as _glob
    path = find_one(uploads_dir, 'all_competitor_matches*.csv', required=False)
    paths = [path] if path else [Path(x) for x in _glob.glob(str(Path(uploads_dir)/'*_matches_*.csv'))]
    if not paths:
        print("   \u2139 No competitor matches file (all_competitor_matches*.csv)")
        return {}
    def _num(x):
        try: return round(float(x), 2)
        except: return None
    out = defaultdict(list); seen = set()
    for pth in paths:
        with open(pth, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                g = {(k or '').strip().lower(): v for k, v in row.items()}
                def gv(*names):
                    for n in names:
                        if g.get(n) not in (None, ''):
                            return g[n]
                    return None
                mt = (gv('match_type', 'match') or '').strip().lower()
                if not ('exact' in mt or mt == 'e'):
                    continue  # exact (same SKU) matches only
                jdurl = gv('jd_url') or ''
                m = re.search(r'/products/([a-z0-9\-]+)', jdurl.lower())
                if not m: continue
                key = '/products/' + m.group(1)
                comp = gv('competitor') or ''
                dk = (key, comp, gv('comp_sku', 'comp_code', 'pid') or '')
                if dk in seen: continue
                seen.add(dk)
                now = _num(gv('comp_now')); jdp = _num(gv('jd_price'))
                pos = gv('position')
                if not pos and now is not None and jdp is not None:
                    pos = 'Competitor cheaper' if now < jdp else ('JD cheaper' if now > jdp else 'Level')
                out[key].append({
                    'c': comp, 'now': now, 'was': _num(gv('comp_was')),
                    'disc': _num(gv('comp_disc_%', 'strike_pct')),
                    'pos': pos or '', 'url': gv('comp_url') or '',
                })
    rows = sum(len(v) for v in out.values())
    print(f"   \u2192 Competitor EXACT matches: {len(out):,} JD products, {rows:,} competitor rows")
    return dict(out)


def load_markdowns():
    """Load the parsed Buying markdown calendar bundled with the skill."""
    path = SCRIPT_DIR.parent / 'data' / 'markdowns.json'
    if not path.exists():
        print("   \u2139 No markdown calendar bundled (data/markdowns.json)")
        return []
    md = json.loads(path.read_text())
    print(f"   \u2192 Loaded {len(md):,} Buying markdown events (Apr\u2013Sep)")
    return md


def integrate_markdowns(markdowns, perf, variants, price_history):
    """Match markdown events to live product groups (Style ID first, then a
    colour-safe title match), attach supplier id, backfill price history with the
    authoritative Buying price points, and return (MARKDOWNS, MD_BY_GROUP)."""
    if not markdowns:
        return [], {}
    style_index = defaultdict(list)
    tset_index = defaultdict(list)
    for r in perf:
        if r.get('si'):
            style_index[r['si']].append(r['id'])
        tset_index[_title_tokens(r['t'])].append(r['id'])

    md_by_group = defaultdict(list)
    supplier_for_group = {}
    buying_changes = []
    out = []
    matched_events = 0
    _sell = sorted((r.get('ol7', 0) or 0) for r in perf if (r.get('ol7') or 0) > 0)
    _p33 = _sell[len(_sell)//3] if _sell else 0
    _p66 = _sell[2*len(_sell)//3] if _sell else 0
    _ol7 = {r['id']: (r.get('ol7') or 0) for r in perf}
    def _tier(gid):
        o = _ol7.get(gid, 0)
        if o <= 0: return None
        return 'H' if o >= _p66 else ('M' if o >= _p33 else 'L')
    for e in markdowns:
        gids = []
        if e.get('style') and e['style'] in style_index:
            gids = style_index[e['style']]
        else:
            ts = _title_tokens(e.get('name'))
            if ts and ts in tset_index:
                gids = tset_index[ts]
        matched = bool(gids)
        pf = _tier(gids[0]) if gids else None
        if matched:
            matched_events += 1
        for gid in gids:
            md_by_group[gid].append({'go': e['go'], 'newp': e['newp'],
                                     'msrp': e.get('msrp'), 'act': e.get('act'),
                                     'scope': e.get('scope'), 'typ': e.get('typ')})
            if e.get('supplier') and gid not in supplier_for_group:
                supplier_for_group[gid] = e['supplier']
            if e.get('go') and e.get('newp') is not None:
                old = e.get('cur') if e.get('cur') is not None else e.get('msrp')
                for v in variants.get(gid, []):
                    price_history.setdefault(v['pid'], []).append({'d': e['go'], 'p': e['newp']})
                    if old is not None:
                        dl = e['newp'] - old
                        buying_changes.append({
                            'date': e['go'], 'id': v['pid'], 'old': round(old, 2),
                            'new': round(e['newp'], 2), 'delta': round(dl, 2),
                            'pct': round((dl / old) * 100, 1) if old else 0,
                            'sku': v.get('sk', ''), 'src': 'buying', 'act': e.get('act'),
                        })
        out.append({'go': e['go'], 'until': e.get('until'), 'style': e.get('style'),
                    'name': e.get('name'), 'brand': e.get('brand'), 'dept': e.get('dept'),
                    'msrp': e.get('msrp'), 'newp': e.get('newp'),
                    'act': e.get('act'), 'typ': e.get('typ'), 'scope': e.get('scope'),
                    'on_site': 1 if e.get('on_site') else 0, 'm': 1 if matched else 0,
                    'perf': pf})
    # attach supplier + sort each group's journey by date
    for r in perf:
        if r['id'] in supplier_for_group:
            r['sup'] = supplier_for_group[r['id']]
    for gid in md_by_group:
        md_by_group[gid].sort(key=lambda x: x['go'] or '')
    print(f"   \u2192 Markdowns matched to live groups: {matched_events:,}/{len(markdowns):,} events; "
          f"{len(md_by_group):,} groups; {len(buying_changes):,} Buying change records")
    return out, dict(md_by_group), buying_changes


def build_perf_and_variants(products, daily_sales, variant_to_lp, lp_daily,
                            max_sales_date):
    """PRODUCT-LEVEL PERF + per-product VARIANTS breakdown.

    Grouping key precedence:
      1. Landing page path (from variant_to_lp mapping)  → most reliable
      2. Title fallback for variants without a recent LP mapping

    PERF row schema (same field names as before, but each row = a product group):
      id   — product key: LP path or 'title:<title>'
      t    — product title (representative)
      b    — brand
      p    — median ecomm price across variants in group
      m    — median market price across variants
      av   — 1 if ANY variant in stock, else 0
      os   — 1 if ANY variant on sale
      has  — has any activity (orders OR sessions) in L7
      hs   — has sales in L7
      ol7  — sum of L7 orders across variants
      rl7  — sum of L7 revenue across variants
      sl7  — LP-level sessions in L7 (already product-level, not summed)
      cl7  — LP completed / LP sessions
      doo/dr/ds/dc — WoW deltas
      lift — 1 if ≥30% WoW lift on baseline ≥10 orders or ≥100 sessions
      hc   — 1 if ANY variant has High-confidence simulation
      nv   — number of variants in this product group
      sk   — '' (not meaningful at product level)

    VARIANTS schema (a dict keyed by PERF row id):
      [{
        pid, t, b, sk, p, m, gap, av, os, ol7, rl7
      }, ...]
    """
    if not max_sales_date:
        return [], {}, None, None, None, None
    L7_end = max_sales_date
    L7_start = L7_end - timedelta(days=6)
    P7_end = L7_start - timedelta(days=1)
    P7_start = P7_end - timedelta(days=6)

    def win_sum(vid, start, end):
        o = r = 0
        d = start
        while d <= end:
            v = daily_sales.get((vid, d))
            if v:
                o += v['o']; r += v['r']
            d += timedelta(days=1)
        return o, r

    def lp_win_sum(lp, start, end):
        if not lp: return 0, 0
        s = c = 0
        d = start
        while d <= end:
            v = lp_daily.get((lp, d))
            if v:
                s += v['sess']; c += v['compl']
            d += timedelta(days=1)
        return s, c

    # Decide a group key for each product
    # Priority: LP path (only if it's a real product URL) → title-based fallback
    #
    # CRITICAL: variant_to_lp gives the most-common LANDING page customers
    # arrived on before buying — that can legitimately be '/' (homepage),
    # '/collections/...', '/search', etc. Those aren't product pages, and
    # using them as group keys merges unrelated variants into one phantom
    # row (e.g. 469 variants all keyed to '/'). Only accept '/products/*'
    # paths; everything else falls through to the title-based key.
    def is_product_lp(path):
        return bool(path) and path.startswith('/products/')

    group_for_product = {}
    for p in products:
        lp = variant_to_lp.get(p['id'])
        if is_product_lp(lp):
            group_for_product[p['id']] = lp
        else:
            # Fallback: title + brand
            group_for_product[p['id']] = f"title:{p['b']}|{p['t']}"

    # Consolidation pass: if any title-fallback variant shares its title with
    # variants that DID get an LP key, reassign it to that LP key. Prevents
    # the same product being split into an LP-keyed row and a title-keyed
    # row just because some variants lacked their own LP attribution data
    # (often dormant variants with no orders).
    title_to_lp = {}  # 'title:brand|title' -> chosen LP key
    for p in products:
        key = group_for_product[p['id']]
        if key.startswith('/products/'):
            tk = f"title:{p['b']}|{p['t']}"
            # Prefer the LP key with the most variants assigned to it
            title_to_lp.setdefault(tk, Counter())[key] += 1
    title_to_winner = {tk: c.most_common(1)[0][0] for tk, c in title_to_lp.items()}
    consolidated = 0
    for p in products:
        key = group_for_product[p['id']]
        if key.startswith('title:') and key in title_to_winner:
            group_for_product[p['id']] = title_to_winner[key]
            consolidated += 1
    if consolidated:
        print(f"   → Consolidated {consolidated:,} title-fallback variants into matching LP groups")

    # Build per-variant L7/P7 metrics first
    per_variant = {}
    for p in products:
        vid = p['id']
        ol7, rl7 = win_sum(vid, L7_start, L7_end)
        op7, rp7 = win_sum(vid, P7_start, P7_end)
        gap = (p['p'] - p['m']) / p['m'] if p['m'] else None
        per_variant[vid] = {
            'pid': vid,
            't':   p['t'],
            'b':   p['b'],
            'sk':  p.get('sk', ''),
            'p':   p['p'],
            'm':   p['m'],
            'gap': round(gap, 4) if gap is not None else None,
            'av':  p['av'],
            'os':  p['os'],
            'ef':  p.get('ef'),
            'ol7': ol7, 'rl7': round(rl7, 2),
            'op7': op7, 'rp7': round(rp7, 2),
            'co':  p.get('co'),
            'mg':  round((p['p'] - p['co']) / p['p'], 4) if (p.get('co') is not None and p['p']) else None,
            'si':  p.get('si', ''),
        }

    # Group variants by product key
    groups = defaultdict(list)
    for vid, v in per_variant.items():
        groups[group_for_product[vid]].append(v)

    perf = []
    variants_out = {}
    for group_key, vs in groups.items():
        # Representative title/brand: use most common
        titles = [v['t'] for v in vs]
        brands = [v['b'] for v in vs]
        t = Counter(titles).most_common(1)[0][0]
        b = Counter(brands).most_common(1)[0][0]
        # Aggregates
        ecomms = sorted([v['p'] for v in vs if v['p'] is not None])
        markets = sorted([v['m'] for v in vs if v['m'] is not None])
        median = lambda xs: xs[len(xs)//2] if xs else None
        p_median = median(ecomms)
        m_median = median(markets)
        mgs = sorted([v['mg'] for v in vs if v.get('mg') is not None])
        mg_group = median(mgs)
        si_group = Counter([v.get('si','') for v in vs if v.get('si')]).most_common(1)
        si_group = si_group[0][0] if si_group else ''
        any_in_stock = any(v['av'] == 1 for v in vs)
        any_on_sale = any(v['os'] == 1 for v in vs)
        any_hc = any(v['ef'] == 'High' for v in vs)
        ol7 = sum(v['ol7'] for v in vs)
        rl7 = sum(v['rl7'] for v in vs)
        op7 = sum(v['op7'] for v in vs)
        rp7 = sum(v['rp7'] for v in vs)
        # Sessions: LP-level. If group key IS an LP path, use it. Otherwise no sessions.
        if group_key.startswith('title:'):
            sl7, comp_l7 = 0, 0
            sp7, comp_p7 = 0, 0
            lp_used = ''
        else:
            sl7, comp_l7 = lp_win_sum(group_key, L7_start, L7_end)
            sp7, comp_p7 = lp_win_sum(group_key, P7_start, P7_end)
            lp_used = group_key
        cl7 = (comp_l7 / sl7) if sl7 else 0
        cp7 = (comp_p7 / sp7) if sp7 else 0
        # Deltas
        doo = ((ol7 - op7) / op7) if op7 > 0 else (None if ol7 == 0 else 1.0)
        dr  = ((rl7 - rp7) / rp7) if rp7 > 0 else (None if rl7 == 0 else 1.0)
        ds  = ((sl7 - sp7) / sp7) if sp7 > 0 else (None if sl7 == 0 else 1.0)
        dc  = (cl7 - cp7)
        # Activity / lift
        has_activity = (ol7 + sl7) > 0
        has_sales = ol7 > 0
        lift = 0
        if op7 >= 10 or sp7 >= 100:
            if op7 > 0 and (ol7 - op7) / op7 >= 0.30: lift = 1
            elif sp7 > 0 and (sl7 - sp7) / sp7 >= 0.30: lift = 1

        # Stable product key: hash of group_key, kept short
        # For LP groups: use the LP path itself (kept; valid as JS object key)
        # For title fallbacks: keep the 'title:...' string
        pid_out = group_key

        perf.append({
            'id': pid_out,
            't': t,
            'b': b,
            'sk': '',
            'p': round(p_median, 2) if p_median is not None else None,
            'm': round(m_median, 2) if m_median is not None else None,
            'av': 1 if any_in_stock else 0,
            'os': 1 if any_on_sale else 0,
            'has': 1 if has_activity else 0,
            'hs':  1 if has_sales else 0,
            'ol7': ol7,
            'rl7': round(rl7, 2),
            'sl7': sl7,
            'cl7': round(cl7, 4),
            'doo': round(doo, 3) if doo is not None else None,
            'dr':  round(dr, 3) if dr is not None else None,
            'ds':  round(ds, 3) if ds is not None else None,
            'dc':  round(dc, 4),
            'lift': lift,
            'hc':  1 if any_hc else 0,
            'nv':  len(vs),
            'lp':  lp_used,
            'mg':  round(mg_group, 4) if mg_group is not None else None,
            'si':  si_group,
        })

        # Variants list — sort by L7 orders desc, then ecomm price asc
        vs_sorted = sorted(vs, key=lambda v: (-(v['ol7'] or 0), v['p'] or 0))
        variants_out[pid_out] = [{
            'pid': v['pid'],
            't':   v['t'],
            'sk':  v['sk'],
            'p':   v['p'],
            'm':   v['m'],
            'gap': v['gap'],
            'av':  v['av'],
            'os':  v['os'],
            'ol7': v['ol7'],
            'rl7': v['rl7'],
            'mg':  v.get('mg'),
        } for v in vs_sorted]

    # Sort PERF default: highest L7 orders desc
    perf.sort(key=lambda r: -r['ol7'])
    return perf, variants_out, L7_start, L7_end, P7_start, P7_end

def build_series(products, daily_sales, max_sales_date, group_for_product,
                 lp_daily=None,
                 ytd_only=True, min_orders=1, min_revenue=0):
    """SERIES: per-PRODUCT-GROUP daily timeseries (keyed by the same group key
       used in PERF — LP path or 'title:...' fallback).

       Schema: {group_key: {di: [0..N], o: [...], r: [...], s: [...], c: [...]}}

       o = orders/day, r = revenue/day, s = sessions/day (landing-page level),
       c = completed checkouts/day. The chart in the template uses all four to
       render the YTD weekly trend with sessions and CVR overlays — critical
       for spotting the effect of price changes on traffic and conversion.

       Sessions (s) and checkouts (c) come from lp_daily, joined by the group
       key (which is the landing page path for LP-grouped products). For
       title-fallback groups, s/c stay 0 since no LP is associated.

       To keep file size reasonable:
         - YTD window only (Jan 1 of current year onwards)
         - Skip groups with 0 orders AND 0 revenue YTD
    """
    if not max_sales_date:
        return {}, None
    if ytd_only:
        earliest = date(max_sales_date.year, 1, 1)
    else:
        earliest = min((d for (_v, d) in daily_sales.keys()), default=max_sales_date)
    n_days = (max_sales_date - earliest).days + 1
    if n_days <= 0:
        return {}, earliest

    by_group = defaultdict(lambda: {
        'o': [0]*n_days, 'r': [0.0]*n_days,
        's': [0]*n_days, 'c': [0]*n_days
    })
    # Orders / revenue: aggregated from per-variant daily sales
    for (vid, d), agg in daily_sales.items():
        if d < earliest or d > max_sales_date: continue
        idx = (d - earliest).days
        group_key = group_for_product.get(vid)
        if not group_key: continue
        by_group[group_key]['o'][idx] += agg['o']
        by_group[group_key]['r'][idx] += agg['r']

    # Sessions / checkouts: from landing-page daily counts, keyed by LP path.
    # Only groups whose key IS an LP path (starts with /) get session data.
    if lp_daily:
        # Index lp_daily by (lp, date) for fast access — already shaped that way
        # We iterate the lp_daily dict and assign to matching group_keys
        # (which equal LP paths for LP-grouped products)
        # Build a set of LP-path group keys we actually care about
        lp_group_keys = {k for k in by_group.keys() if isinstance(k, str) and k.startswith('/')}
        # Also include groups that have an LP but no order activity yet
        for (lp, d), v in lp_daily.items():
            if lp not in lp_group_keys:
                # This LP might still be one of our groups even if no orders
                # showed in daily_sales — initialise it
                if lp in group_for_product.values():
                    # Touch the defaultdict to create entry
                    _ = by_group[lp]
                    lp_group_keys.add(lp)
        for (lp, d), v in lp_daily.items():
            if lp not in lp_group_keys: continue
            if d < earliest or d > max_sales_date: continue
            idx = (d - earliest).days
            by_group[lp]['s'][idx] += v.get('sess', 0)
            by_group[lp]['c'][idx] += v.get('compl', 0)

    out = {}
    for group_key, arrs in by_group.items():
        tot_o = sum(arrs['o']); tot_r = sum(arrs['r'])
        tot_s = sum(arrs['s'])
        # Include if there's meaningful activity in ANY of orders, revenue, or sessions
        if tot_o < min_orders and tot_r < min_revenue and tot_s < 50:
            continue
        out[group_key] = {
            'di': list(range(n_days)),
            'o': arrs['o'],
            'r': [round(x) for x in arrs['r']],
            's': arrs['s'],
            'c': arrs['c'],
        }
    return out, earliest


def build_position_snapshot(metrics):
    return {
        'd': TODAY.isoformat(),
        'total': metrics['total'],
        'above': metrics['above'],
        'at': metrics['at'],
        'below': metrics['below'],
        'onsale': metrics['on_sale'],
        'oos': metrics['oos'],
    }

def merge_position_snapshots(prior, new):
    """Append new snapshot, replacing any existing entry with same date."""
    merged = [s for s in prior if s.get('d') != new['d']]
    merged.append(new)
    merged.sort(key=lambda s: s.get('d', ''))
    return merged

def build_price_history(products, prior_history):
    """Append today's effective price to each product's history.
       Skip if today's date already present or price unchanged."""
    today = TODAY.isoformat()
    new_history = dict(prior_history)
    for p in products:
        pid = p['id']
        hist = list(new_history.get(pid, []))
        if hist and hist[-1].get('d') == today:
            # Same date already logged; update price in case it changed
            hist[-1]['p'] = p['p']
        else:
            hist.append({'d': today, 'p': p['p']})
        new_history[pid] = hist
    _trim_history(new_history)
    return new_history

def build_market_history(products, prior_history):
    """Same as build_price_history but for Market Price (Benchmark column)."""
    today = TODAY.isoformat()
    new_history = dict(prior_history)
    for p in products:
        pid = p['id']
        if p.get('m') is None: continue
        hist = list(new_history.get(pid, []))
        if hist and hist[-1].get('d') == today:
            hist[-1]['p'] = p['m']
        else:
            hist.append({'d': today, 'p': p['m']})
        new_history[pid] = hist
    _trim_history(new_history)
    return new_history

def _trim_history(hist):
    """Drop per-product history points older than the rolling window."""
    for pid in list(hist):
        kept = [e for e in hist[pid] if e.get('d', '') >= HISTORY_CUTOFF]
        if kept:
            hist[pid] = kept
        else:
            del hist[pid]

def detect_changes(products, prior_history):
    """Compare today's effective price to most recent prior entry.
       Returns CHANGES records: {date, id, old, new, delta, pct, t, b, sku}"""
    changes = []
    today = TODAY.isoformat()
    for p in products:
        hist = prior_history.get(p['id'], [])
        # Find most recent prior entry (not today)
        prev = None
        for entry in reversed(hist):
            if entry.get('d') != today:
                prev = entry; break
        if prev is None: continue
        if prev['p'] is None: continue
        delta = p['p'] - prev['p']
        if abs(delta) < 0.01: continue
        changes.append({
            'date': today,
            'id': p['id'],
            'old': prev['p'],
            'new': p['p'],
            'delta': round(delta, 2),
            'pct': round((delta / prev['p']) * 100, 1) if prev['p'] else 0,
            't': p['t'],
            'b': p['b'],
            'sku': p.get('sk', ''),
            'src': 'feed',
        })
    return changes

def detect_market_changes(products, prior_market_history,
                          threshold_pct=2.0, min_delta=1.0):
    """Same as detect_changes but for Market Price. Market price moves around
       a lot due to Google's click-weighting, so we filter out small wobbles:
         - require |delta| >= $1
         - require |pct| >= 2%
    """
    changes = []
    today = TODAY.isoformat()
    for p in products:
        if p.get('m') is None: continue
        hist = prior_market_history.get(p['id'], [])
        prev = None
        for entry in reversed(hist):
            if entry.get('d') != today:
                prev = entry; break
        if prev is None: continue
        if prev['p'] is None: continue
        delta = p['m'] - prev['p']
        if abs(delta) < min_delta: continue
        pct = (delta / prev['p']) * 100 if prev['p'] else 0
        if abs(pct) < threshold_pct: continue
        changes.append({
            'date': today,
            'id': p['id'],
            'old': round(prev['p'], 2),
            'new': p['m'],
            'delta': round(delta, 2),
            'pct': round(pct, 1),
            't': p['t'],
            'b': p['b'],
            'sku': p.get('sk', ''),
        })
    return changes

# ─── Inject into template ─────────────────────────────────────────────────
def render(part1, part2, *,
           products, brands, metrics, price_history, market_history, changes,
           perf, variants, series, cvr_baseline, market_changes,
           position_snapshots, series_start_date, header_meta, perf_intro, titles,
           markdowns=None, md_by_group=None, comp_by_group=None, market_dates=None):
    """Build the data block + replace the header meta line."""
    # Update header meta inside part1
    part1 = re.sub(
        r'<div class="header-meta" id="header-meta-content">[^<]*</div>',
        f'<div class="header-meta" id="header-meta-content">{header_meta}</div>',
        part1
    )
    # Last-updated timestamp (Pacific time) under the title
    if ZoneInfo is not None:
        _now = datetime.now(ZoneInfo('America/Los_Angeles'))
    else:
        _now = datetime.now()
    _updated = 'Last updated: ' + _now.strftime('%b %-d, %Y at %-I:%M %p %Z').strip()
    part1 = re.sub(
        r'<div class="last-updated" id="last-updated">[^<]*</div>',
        f'<div class="last-updated" id="last-updated">{_updated}</div>',
        part1
    )
    # Update Performance-tab intro — the L7/P7 window and CVR baseline are
    # dynamic; this paragraph was previously hard-coded and went stale.
    part1 = re.sub(
        r'(<div class="perf-intro" id="perf-intro-content">)[\s\S]*?(</div>)',
        lambda m: m.group(1) + perf_intro + m.group(2),
        part1, count=1
    )
    # Simulation-coverage figures in the static copy were hard-coded (~22% / 78%)
    # and went stale as Google expanded its Discount Price Simulations. Compute
    # the live figure and inject it so the prose matches the "with simulation" tile.
    _sim_n = sum(1 for p in products if p.get('sp') is not None)
    _sim_pct = round(100 * _sim_n / len(products)) if products else 0
    _nosim_pct = 100 - _sim_pct
    part1 = part1.replace('For ~22% of SKUs', f'For ~{_sim_pct}% of SKUs')
    part1 = part1.replace('Simulation coverage is approximately 22% of the catalogue',
                          f'Simulation coverage is approximately {_sim_pct}% of the catalogue')
    part2 = part2.replace('approximately 78% of the catalogue falls in this state',
                          f'approximately {_nosim_pct}% of the catalogue falls in this state')
    # Build the data block. Use compact separators to match the original.
    sep = (',', ':')
    data_block = []
    # Strip internal underscore fields (e.g. _link used for LP matching) before serialising
    products_out = [{k: v for k, v in p.items() if not k.startswith('_')} for p in products]
    data_block.append('const PRODUCTS = ' + json.dumps(products_out, separators=sep) + ';')
    data_block.append('const BRANDS = ' + json.dumps(brands, separators=sep) + ';')
    data_block.append('const METRICS = ' + json.dumps(metrics, separators=sep) + ';')
    _phd, _phv = _axis_encode(price_history)
    _mhd, _mhv = _axis_encode(market_history)
    data_block.append('const PH_DATES = ' + json.dumps(_phd, separators=sep) + ';')
    data_block.append('const PRICE_HISTORY = ' + json.dumps(_phv, separators=sep) + ';')
    data_block.append('const MH_DATES = ' + json.dumps(_mhd, separators=sep) + ';')
    data_block.append('const MARKET_HISTORY = ' + json.dumps(_mhv, separators=sep) + ';')
    data_block.append('const CHANGES = ' + json.dumps(changes, separators=sep) + ';')
    data_block.append('const PERF = ' + json.dumps(perf, separators=sep) + ';')
    data_block.append('const VARIANTS = ' + json.dumps(variants, separators=sep) + ';')
    data_block.append('const SERIES = ' + json.dumps(series, separators=sep) + ';')
    data_block.append(f'const CVR_BASELINE = {cvr_baseline:.4f};')
    # Market-change markers are derived in the page from MARKET_HISTORY (same
    # >=$1 and >=2% rule), so the separate MARKET_CHANGES log is not embedded:
    # it was a lossless duplicate of the history. Next build reconstructs it.
    data_block.append('const MC_DATES = [];')
    data_block.append('const MARKET_CHANGES = [];')
    data_block.append('const TITLES = ' + json.dumps(titles, separators=sep) + ';')
    data_block.append('const MARKDOWNS = ' + json.dumps(markdowns or [], separators=sep) + ';')
    data_block.append('const MD_BY_GROUP = ' + json.dumps(md_by_group or {}, separators=sep) + ';')
    data_block.append('const COMP_BY_GROUP = ' + json.dumps(comp_by_group or {}, separators=sep) + ';')
    # POSITION_SNAPSHOTS lives inside part2 — we need to inject it there too
    snaps_str = '[\n' + ',\n'.join(
        '  ' + json.dumps(s, separators=sep) for s in position_snapshots
    ) + '\n]'
    part2 = re.sub(
        r'const POSITION_SNAPSHOTS\s*=\s*\[.*?\];',
        f'const POSITION_SNAPSHOTS = {snaps_str};',
        part2, count=1, flags=re.DOTALL
    )
    return part1 + '\n'.join(data_block) + '\n' + part2

# ─── Main ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uploads', default='/mnt/user-data/uploads')
    parser.add_argument('--previous', default=None,
                        help='Path to existing index.html (to preserve history)')
    parser.add_argument('--output', default='/mnt/user-data/outputs/index.html')
    args = parser.parse_args()

    print(f"\n🏗️  JD Pricing Dashboard rebuild — {TODAY}\n" + "─" * 60)

    pb, time_period = load_price_benchmarks(args.uploads)
    sps = load_sps(args.uploads)
    feed, feed_dt = load_feed(args.uploads)

    print("\n🔗 Joining + building products...")
    products, sps_excluded = build_products(pb, sps, feed)
    pb_ids = {p['id'] for p in products}
    print(f"   → universe: {len(products):,} products")
    print(f"   → SPS rows excluded (no PB match): {sps_excluded:,}")

    daily_sales, sku_map, max_sales_date = load_daily_sales(args.uploads, pb_ids)
    variant_to_lp = load_sales_with_lp(args.uploads, pb_ids, products=products)
    if max_sales_date:
        lp_end = max_sales_date
        # Load LP perf for YTD window (Jan 1 of current year onwards) so that
        # SERIES can include daily sessions and checkouts for the full chart.
        lp_start = date(lp_end.year, 1, 1)
    else:
        lp_end = TODAY; lp_start = date(TODAY.year, 1, 1)
    lp_daily, cvr_baseline, lp_granularity = load_lp_perf(
        args.uploads, lp_start, lp_end)
    if lp_granularity == 'monthly':
        print("   ⚠ Proceeding with MONTHLY sessions — chart overlay will be coarse.")

    # Patch SKU codes onto products for PERF use
    for p in products:
        if p['id'] in sku_map:
            p['sk'] = sku_map[p['id']]

    print("\n📊 Computing metrics + brands...")
    metrics = build_metrics(products)
    brands = build_brands(products)
    print(f"   → above {metrics['above']:,} / at {metrics['at']:,} / below {metrics['below']:,}")
    print(f"   → {len(brands)} brands, top: {brands[0]['b']} ({brands[0]['n']:,})")

    print("\n🧮 Computing PERF (product-level) + VARIANTS + SERIES...")
    perf, variants, L7s, L7e, P7s, P7e = build_perf_and_variants(
        products, daily_sales, variant_to_lp, lp_daily, max_sales_date)

    # Realized L7 gross margin (actual, sales-weighted) joined by title
    realized = load_realized_margin(args.uploads, L7s, L7e) if (L7s and L7e) else {}
    for r in perf:
        r['mgr'] = realized.get(_norm_title(r['t']))

    # Build group_for_product map (same logic as inside build_perf_and_variants)
    group_for_product = {}
    for p in products:
        lp = variant_to_lp.get(p['id'])
        group_for_product[p['id']] = lp if lp else f"title:{p['b']}|{p['t']}"

    series, series_start = build_series(
        products, daily_sales, max_sales_date, group_for_product,
        lp_daily=lp_daily)
    print(f"   → PERF (product) rows: {len(perf):,} "
          f"(with activity: {sum(1 for r in perf if r['has']):,})")
    print(f"   → VARIANTS groups: {len(variants):,} "
          f"(avg {sum(len(v) for v in variants.values())/max(len(variants),1):.1f} variants/group)")
    print(f"   → SERIES groups: {len(series):,}")
    if L7s:
        print(f"   → L7 {L7s}–{L7e}  · P7 {P7s}–{P7e}")

    print("\n📷 Loading prior history from previous build...")
    prior_snaps, prior_history, prior_market_history, \
        prior_changes, prior_market_changes = extract_prior_history(args.previous)

    print("\n🔍 Detecting price changes...")
    new_changes = detect_changes(products, prior_history)
    print(f"   → {len(new_changes):,} new effective-price changes this run")

    new_market_changes = detect_market_changes(products, prior_market_history)
    print(f"   → {len(new_market_changes):,} new market-price changes this run "
          f"(≥$1 and ≥2%)")

    # Merge prior + new logs, dedupe by (date, id, sku)
    cur_ids = {p['id'] for p in products}
    def merge_changes(prior, new):
        seen = set()
        out = []
        for entry in prior + new:
            if entry.get('date', '') < HISTORY_CUTOFF: continue  # rolling window
            key = (entry.get('date'), entry.get('id'), entry.get('sku', ''))
            if key in seen: continue
            seen.add(key)
            # Drop repeated title/brand where the id is in the current product
            # universe (the change tabs look those up from PRODUCTS by id at
            # render). Keep them only for products that have since left the
            # benchmark, so those rows still show a name rather than a bare id.
            if entry.get('id') in cur_ids:
                out.append({k: v for k, v in entry.items() if k not in ('t', 'b')})
            else:
                out.append(entry)
        out.sort(key=lambda c: (c.get('date', ''), abs(c.get('delta', 0))),
                 reverse=True)
        return out

    # Compact title/brand lookup for products that appear in the change logs but
    # have since left the benchmark universe. Current products already carry
    # their name in PRODUCTS, so only these delisted ids need storing here (once).
    # This keeps every change-log row showing a real name while dropping the
    # title that was otherwise repeated on tens of thousands of records.
    cur_ids = {p['id'] for p in products}
    titles = {}
    for rec in prior_changes + prior_market_changes + new_changes + new_market_changes:
        i = rec.get('id')
        if i and i not in cur_ids and i not in titles and rec.get('t'):
            titles[i] = [rec['t'], rec.get('b', '')]
    print(f"   → TITLES lookup: {len(titles):,} delisted products referenced in logs")

    changes = merge_changes(prior_changes, new_changes)
    market_changes = merge_changes(prior_market_changes, new_market_changes)
    # Slim MARKET_CHANGES: only date/id/pct are read (per-product markers);
    # old/new prices already live in MARKET_HISTORY, so drop the redundant fields.
    _mcd = sorted({c['date'] for c in market_changes})
    _mci = {d: i for i, d in enumerate(_mcd)}
    market_changes = [{'d': _mci[c['date']], 'id': c['id'], 'pct': c.get('pct', 0)} for c in market_changes]
    market_dates = _mcd
    print(f"   → CHANGES log total: {len(changes):,} "
          f"(prior {len(prior_changes):,} + new {len(new_changes):,})")
    print(f"   → MARKET_CHANGES log total: {len(market_changes):,} "
          f"(prior {len(prior_market_changes):,} + new {len(new_market_changes):,})")

    # Update history with this week's prices
    price_history = build_price_history(products, prior_history)
    market_history = build_market_history(products, prior_market_history)

    # Buying markdown calendar: match, attach supplier, backfill price history
    markdowns = load_markdowns()
    MARKDOWNS, md_by_group, buying_changes = integrate_markdowns(markdowns, perf, variants, price_history)
    # Merge Buying changes into the price-change log as the PRIMARY source
    # (Buying first, so it wins any exact same-date/SKU collision); feed-detected
    # changes remain and fill the gaps Buying doesn't cover. Both are stored,
    # each carrying its own 'src' label.
    changes = merge_changes(buying_changes, changes)
    print(f"   \u2192 CHANGES total (Buying primary + feed gap-fill): {len(changes):,}")

    comp_by_group = load_competitors(args.uploads)
    for r in perf:
        if comp_by_group.get(r['id']):
            r['ct'] = 1
    for p in products:
        if group_for_product.get(p['id']) in comp_by_group:
            p['ct'] = 1

    # Previous-week price + WoW change per group (Prev Price column)
    prior_prices = extract_prior_perf_prices(args.previous) if args.previous else {}
    for r in perf:
        pp = prior_prices.get(r['id'])
        if pp and r.get('p'):
            r['pp'] = round(pp, 2)
            r['pc'] = round((r['p'] - pp) / pp, 4)
    # Snapshot
    new_snap = build_position_snapshot(metrics)
    position_snapshots = merge_position_snapshots(prior_snaps, new_snap)
    print(f"   → {len(position_snapshots)} position snapshots in history")

    # Header meta line
    fb_str = feed_dt.strftime('%b %d, %Y · %H:%M') if feed_dt else 'unknown'
    header_meta = (
        f"Benchmark window: {time_period or 'unknown'}  ·  "
        f"Feed exported: {fb_str}  ·  "
        f"Report generated: {TODAY.strftime('%b %d, %Y')}"
    )

    # Performance-tab intro (dynamic window + CVR baseline + filtered-basis note)
    def _d(dt):
        return dt.strftime('%b %-d') if dt else '?'
    if L7s and L7e:
        l7str = f"{_d(L7s)}-{_d(L7e)}"
        p7str = f"{_d(P7s)}-{_d(P7e)}"
    else:
        l7str = p7str = "n/a"
    perf_intro = (
        "Sales and session performance for dashboard products. Each row shows the last 7 days "
        f"(<strong>{l7str}</strong>) with delta vs the prior 7 days ({p7str}). "
        "<strong>Lift flag</strong> highlights products with \u226530% WoW lift on a baseline of "
        "\u226510 orders or \u2265100 sessions. Click any product to see its YTD weekly trend with "
        "price-change markers. Landing-page sessions count sessions that started on a product's "
        "page, matched by landing-page path (canonical and collection-scoped paths consolidated). "
        f"Aggregate site CVR baseline: <strong>{cvr_baseline*100:.2f}%</strong>."
    )

    print("\n📝 Rendering HTML...")
    part1 = TEMPLATE_P1.read_text(encoding='utf-8')
    part2 = TEMPLATE_P2.read_text(encoding='utf-8')
    html_out = render(
        part1, part2,
        products=products,
        brands=brands,
        metrics=metrics,
        price_history=price_history,
        market_history=market_history,
        changes=changes,
        perf=perf,
        variants=variants,
        series=series,
        cvr_baseline=cvr_baseline,
        market_changes=market_changes,
        position_snapshots=position_snapshots,
        series_start_date=series_start.isoformat() if series_start else None,
        header_meta=header_meta,
        perf_intro=perf_intro,
        titles=titles,
        markdowns=MARKDOWNS,
        md_by_group=md_by_group,
        comp_by_group=comp_by_group,
        market_dates=market_dates,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding='utf-8')
    size_mb = out.stat().st_size / (1024*1024)
    print(f"\n✅ Done: {out} ({size_mb:.1f} MB)")
    print(f"\n📤 Next: cp {out} <jd-ecomm/online-shopping-market-pricing>/index.html "
          f"&& git commit && git push")

if __name__ == '__main__':
    main()
