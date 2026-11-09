# Input File Schemas

All four inputs land in `/mnt/user-data/uploads/`. Match by filename prefix — dates in filenames vary week to week.

## 1. Price Benchmarks CSV (CANONICAL)

**Filename**: `Your_most_popular_products_with_price_benchmarks_YYYY-MM-DD_HH-MM-SS.csv`

**Structure**: 2 preamble lines + 1 header line + data.

```
L0: Name: Your most popular products with price benchmarks
L1: "Time period: Apr 22, 2026 - May 19, 2026"
L2: Title,Brand,Product ID,Your price,Your price currency,Benchmark,Benchmark currency,Price gap,Clicks
L3+: data rows
```

**Skip 2 lines before reading header.** Capture L1 as the benchmark window for the dashboard header.

**Columns**:
- `Title` — product title (may repeat across Product IDs)
- `Brand` — lowercase brand name (`nike`, `adidas`, `new balance`, `salomon`, etc.)
- `Product ID` — numeric string; the canonical join key. Maps to `id` in the feed and `Product variant ID` in sales.
- `Your price` — JD's price as reported to Google. **Not used as canonical** — use the feed instead.
- `Your price currency` — always `CAD` for JD CA.
- `Benchmark` — **Market Price** (click-weighted median competitor price). Float, may have many decimals.
- `Benchmark currency` — always `CAD`.
- `Price gap` — Google's pre-computed gap as decimal (e.g. `-0.05624` = -5.62%). Use this OR recompute from prices — they agree.
- `Clicks` — 28-day click count (the benchmark window).

**Row count**: ~10–11k rows typically.

## 2. Sale Price Suggestions CSV

**Filename**: `Sale_price_suggestions_with_highest_performance_impact_YYYY-MM-DD_HH-MM-SS.csv`

**Structure**: 1 preamble line + 1 header line + data.

```
L0: Name: Sale price suggestions with highest performance impact
L1: Product ID,Title,Brand,Category,Your price,Suggested price,Price currency,Click uplift,Conversion uplift,Effectiveness
L2+: data rows
```

**Skip 1 line before reading header.**

**Columns**:
- `Product ID` — join key
- `Title`, `Brand`, `Category`
- `Your price` — may disagree with Price Benchmarks export. **Discard; use the Benchmarks value.**
- `Suggested price` — simulated discount price
- `Price currency` — CAD
- `Click uplift` — decimal multiplier of % growth (1.71 = +171%)
- `Conversion uplift` — same format
- `Effectiveness` — `High` / `Medium` / `Low` (Google's confidence in the simulation)

**Row count**: ~11k rows typically; ~22% of catalogue. **~1,249 rows commonly reference Product IDs not in the current Price Benchmarks window — exclude these from the dashboard universe** but log the count.

## 3. Product Feed TSV (inside zip)

**Filename**: `products_YYYY-MM-DD_HH-MM-SS.zip` containing `products_YYYY-MM-DD_HH-MM-SS.tsv`

**Structure**: 1 header line + data rows. Tab-delimited.

**Header columns** (in order):
```
title, id, price, sale price, condition, availability, channel, feed label,
language, additional image link, adwords grouping, age group, brand, color,
cost of goods sold, custom label 0, custom label 1, custom label 2,
custom label 3, custom label 4, description, gender, google product category,
gtin, image link, item group id, link, mpn, product type, promotion id,
shipping(country), size
```

**Key columns we use**:
- `id` — join key (matches Product ID in benchmarks/SPS). **Filter empty rows** — feed has many blank-id continuation rows for multiline descriptions.
- `title`, `brand`
- `price` — format `"130.00 CAD"`. Strip currency suffix, parse as float.
- `sale price` — same format, may be empty
- `availability` — `in stock` / `out of stock` / `preorder`
- `feed label` — `CA` for English, `fr` for French. **Use English (`CA`) rows as primary, dedupe by `id`** — French rows have IDs prefixed like `8145984323766_00042422|blk|8|na` while EN rows have plain numeric IDs.
- `item group id` — links variants of same style
- `image link` — used in the row-detail panel
- `link` — product page URL
- `condition` — typically `new`

**Effective price logic**:
```python
effective_price = parse_price(row['sale price']) if row['sale price'] else parse_price(row['price'])
is_on_sale = bool(row['sale price'] and row['sale price'].strip())
```

**Row count**: ~50–60k rows; filter to non-empty `id` + English locale yields ~25–30k unique Product IDs.

## 4. Shopify exports (three CSVs)

### 4a. Daily Product Sales by SKU (full history)

**Filename**: `RC_-_Daily_Product_Sales_by_SKU_-_YYYY-MM-DD_-_YYYY-MM-DD.csv`

**Columns** (quoted CSV):
```
Day, Product title, Product variant SKU, Product variant ID,
Total sales (last click), Net sales (last click), Orders (last click),
Customers (last click), Net items sold (last click),
Average order value (last click), New customers (last click),
Returning customers (last click), Returning customer rate (last click)
```

- `Day` — `YYYY-MM-DD`
- `Product variant ID` — join key (matches Product ID in benchmarks). **This is the link from Shopify to Google's universe.**
- `Product variant SKU` — Shopify SKU code (format `00030333|PUR|MED|NA`); not used for joining, useful for display only.
- `Orders (last click)` — int, may be negative (returns)
- `Net sales (last click)` — float, CAD
- `Net items sold (last click)` — int

**Use for**: L7 vs prior-7 aggregates, YTD weekly trend per Product ID.

**Size**: ~100MB+ — stream/chunk; do not load fully into memory unnecessarily.

### 4b. Daily Product Sales by SKU with Landing Page

**Filename**: `RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_YYYY-MM-DD_-_YYYY-MM-DD.csv`

**Columns**:
```
Day, Product title, Product variant SKU, Product variant ID,
Order landing page path, Average order value (last click)
```

**Use for**: Linking Product variant ID → landing page path (so we can attribute sessions/CVR). Build a mapping `{variant_id: most_common_landing_page}` from the last 28 days.

### 4c. Landing Page Performance

**Filename**: `RC_-_Landing_Page_Performance_-_YYYY-MM-DD_-_YYYY-MM-DD.csv`

**Columns**:
```
Day, Landing page type, Landing page path, Sessions, Bounce rate,
Added to cart rate, Conversion rate, Sessions with cart additions,
Sessions that reached checkout, Sessions that completed checkout
```

- `Landing page type` — filter to `Product`
- `Landing page path` — e.g. `/products/nike-air-force-1-07-white`
- `Sessions`, `Conversion rate` — used for the Sessions and CVR columns on Product Performance tab.

**Use for**: Per-product session and CVR figures, aggregated to L7 + prior-7 windows.

**Site CVR baseline** = aggregate sessions-weighted CVR across all Product landing pages in L7 window (typically ~1.4%). Display this in the Product Performance tab header.

## Join chain summary

```
Price Benchmarks.Product ID
  = Sale Price Suggestions.Product ID
  = Feed.id
  = Daily Sales.Product variant ID
                       │
                       └─► Daily Sales with LP.Order landing page path
                                                   │
                                                   └─► Landing Page Performance.Landing page path
```
