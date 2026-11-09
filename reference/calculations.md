# Calculations Reference

All formulas used in the dashboard. Source of truth — never improvise.

## Core pricing math

### Ecomm Price (effective price)

```python
def effective_price(feed_row):
    sp = parse_money(feed_row.get('sale price'))
    p = parse_money(feed_row.get('price'))
    return sp if sp is not None else p

def is_on_sale(feed_row):
    return bool(feed_row.get('sale price', '').strip())

def parse_money(s):
    """Parse '130.00 CAD' or '130.00' → 130.00. Return None if empty/invalid."""
    if not s or not s.strip():
        return None
    s = s.strip().split()[0].replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None
```

### Market Price

Direct copy of `Benchmark` column from Price Benchmarks export. No rounding except for display (`$X.XX`).

### Price Gap %

```python
gap_pct = (ecomm_price - market_price) / market_price
gap_pct_display = f"{gap_pct * 100:+.2f}%"
```

### Position bands

```python
def position(gap_pct):
    if gap_pct > 0.02: return 'over'      # red
    if gap_pct < -0.02: return 'below'    # green
    return 'at'                            # neutral (±2%)
```

## Brand Summary tab

For each brand, count Product IDs (after PB ∩ feed join) by position:

```python
brand_summary[brand] = {
    'below': count_below,
    'at': count_at,
    'over': count_over,
    'total': count_below + count_at + count_over
}
# Bars rendered as proportions
```

Sort brands by total desc. Clicking a brand triggers a filter on the Pricing Opportunity tab.

## Discount Price Simulation fields

Pulled directly from Sale Price Suggestions:

```python
sim = {
    'sim_price': float(row['Suggested price']),
    'confidence': row['Effectiveness'],   # 'High'/'Medium'/'Low'
    'click_uplift_pct': float(row['Click uplift']) * 100,   # 1.71 → 171.0
    'conv_uplift_pct': float(row['Conversion uplift']) * 100,
}
```

Display: `+171%` (with sign). For uplift > +500% cap display to `+500%+` to avoid visual noise but keep underlying value for sorting.

## Product Performance tab

### Time windows

```python
from datetime import date, timedelta
today = max_date_in_sales_export   # use latest day with non-zero data
L7_end = today
L7_start = today - timedelta(days=6)
prev7_end = L7_start - timedelta(days=1)
prev7_start = prev7_end - timedelta(days=6)
```

Display in tab header: e.g. `Each row shows the last 7 days (May 13-19) with delta vs the prior 7 days (May 6-12)`.

### Per-Product-ID aggregates (L7 and prev7)

```python
# Sum across days in window, per Product variant ID
orders_l7      = sum of Orders(last click)
revenue_l7     = sum of Net sales(last click)
items_sold_l7  = sum of Net items sold(last click)
```

### Sessions and CVR

Sessions and CVR are landing-page-level, not SKU-level. Aggregate via the variant_id → landing_page mapping:

```python
# 1) Build mapping from sales-with-LP file (most common LP per variant in last 28 days)
variant_to_lp = most_common_landing_page_per_variant(sales_with_lp, last_n_days=28)

# 2) For each variant, sum sessions and weighted CVR from its LP rows in window
for variant_id, lp_path in variant_to_lp.items():
    rows = landing_page_perf[lp_path] in window
    sessions = sum(row.Sessions)
    completed = sum(row['Sessions that completed checkout'])
    cvr = completed / sessions if sessions else 0
```

**Important**: multiple variants can share a landing page (different sizes/colourways of same style). When summing sessions for a Product ID, do **not** double-count — sessions are per-LP, so we assign the full LP session count to each variant that maps to it, but mark it visually with a "shared LP" indicator if needed.

### Lift flag

```python
def has_lift(orders_l7, orders_prev7, sessions_l7, sessions_prev7):
    order_baseline = orders_prev7 >= 10
    session_baseline = sessions_prev7 >= 100
    if not (order_baseline or session_baseline):
        return False
    if orders_prev7 > 0:
        order_lift = (orders_l7 - orders_prev7) / orders_prev7
        if order_lift >= 0.30: return True
    if sessions_prev7 > 0:
        session_lift = (sessions_l7 - sessions_prev7) / sessions_prev7
        if session_lift >= 0.30: return True
    return False
```

### Site CVR baseline

```python
site_sessions = sum of Sessions across all Product LPs in L7
site_completed = sum of Sessions that completed checkout across all Product LPs in L7
site_cvr_baseline = site_completed / site_sessions   # display as % e.g. 1.44%
```

### YTD weekly trend (per Product ID, shown on row click)

Bucket daily sales into ISO weeks (Mon-Sun), summing orders + revenue. Overlay markers for any Price Changes detected for that Product ID. Render as a small inline sparkline / Plotly line.

## Price Changes tab

Diff this week's feed against the most recent snapshot in `snapshots/feed_*.csv.gz`:

```python
current = {id: effective_price for id in current_feed}
previous = load_snapshot(most_recent_snapshot)

changes = []
for id, new_price in current.items():
    old_price = previous.get(id)
    if old_price is None: continue   # new product — not a change
    if abs(new_price - old_price) < 0.01: continue   # noise
    changes.append({
        'date': today,
        'product_id': id,
        'title': ..., 'brand': ...,
        'previous': old_price,
        'new': new_price,
        'delta_$': new_price - old_price,
        'delta_pct': (new_price - old_price) / old_price,
    })
```

Plus all changes from prior snapshots already logged. Maintain a `snapshots/changes_log.csv` that accumulates week over week.

**Direction filter**: `markdowns` = delta_$ < 0; `markups` = delta_$ > 0.

## Catalogue Trend tab

Each weekly run appends a row to `snapshots/catalogue_history.csv`:

```
date, total_products, below, at, over, on_sale, out_of_stock,
total_clicks_28d, median_market_price, median_ecomm_price
```

Plotted as three Plotly line charts:
1. **Position Mix (%)** — below/at/over as proportions of total
2. **Counts** — below/at/over raw counts
3. **On Sale + Out of Stock** — raw counts of `is_on_sale=True` and `availability != 'in stock'`

## Dashboard universe

The set of Product IDs displayed on Pricing Opportunity / Brand Summary / Product Performance:

```python
universe = PB_ids ∩ feed_ids   # always 100% in practice — PB is a subset of feed
```

SPS rows whose Product ID is NOT in `universe` are **excluded** from the dashboard but their count is reported in the methodology footer (`~1,249 sale-price suggestions reference Product IDs not in the current benchmarks window`).

## Number formatting

- Currency: `$X.XX` (CAD, no symbol prefix beyond `$`)
- Percentages: 2 decimal places with sign for gaps (`-5.62%`, `+1.23%`), 0 decimals for uplift (`+171%`)
- Counts: thousands separator (`2,773`)
- Dates in copy: `May 13–19` style; in tables: `YYYY-MM-DD`
