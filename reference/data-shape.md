# Data Shape Reference

The template expects these global JavaScript constants. Field names are intentionally compact (single letters and short codes) to keep the embedded data blob small. Match these schemas exactly — the JS in `template_part2.html` reads them by name.

## `PRODUCTS` — array, full SKU-level universe (the Pricing Opportunity table)

One row per Product ID (every variant gets its own entry).

```js
[{
  id:  "44057564119222",   // Product ID (string) — Google's variant ID = Shopify Product variant ID
  t:   "Salomon XT-6 ...", // title
  b:   "salomon",          // brand (lowercase)
  p:   230.00,             // ecomm price (effective; sale_price else price)
  m:   230.06,             // market price (Benchmark column)
  c:   2773,               // clicks 28d
  os:  0,                  // on sale 1/0
  av:  1,                  // availability: 1 = in stock, 0 = out of stock
  rp:  150.00,             // regular price (only when os=1)
  sa:  100.00,             // sale price (only when os=1)
  sk:  "00009455|WHT|6.5|NA", // Shopify SKU code (from sales export, optional)
  gt:  "194502193046",     // GTIN (from feed)
  sp:  84.0,               // simulated price (only if SPS available)
  cu:  0.523,              // click uplift (decimal; 0.5 = +50%)
  vu:  0.502,              // conversion uplift (decimal)
  ef:  "High",             // effectiveness: "High" | "Medium" | "Low"
}, ...]
```

JS computes `p.gap = (p - m) / m` and `p.sim = p.sp != null ? 1 : 0` at load time, so don't pre-compute those.

## `BRANDS` — array of brand summary records (Brand Summary tab)

```js
[{ b: "nike", n: 2854, w: 2854, c: 153857, o: 432, a: 1330, u: 1092,
   hi: 269, md: 282, sim: 948, mg: -0.0037 }, ...]
```

`o`/`a`/`u` = over/at/under-market counts. `hi`/`md` = high/medium-effectiveness simulation counts. `mg` = median gap (decimal). Sort by `c` desc.

## `METRICS` — single object (KPI strip)

```js
{ total, with_sim, high_eff, med_eff, above, below, at, clicks, on_sale, oos, in_stock }
```

## `PRICE_HISTORY` — dict of per-Product-ID effective-price log

```js
{ "43754258399414": [
    { d: "2026-04-22", p: 165.0 },
    { d: "2026-04-27", p: 165.0 }, ...
  ], ... }
```

**Accumulates week over week.** The rebuild script extracts this from the previous build and appends today's price for every product.

## `MARKET_HISTORY` — dict of per-Product-ID Market Price log

Same shape as `PRICE_HISTORY` but tracks Market Price (Benchmark column). Used to diff into `MARKET_CHANGES`. Also accumulates across builds.

## `CHANGES` — array of effective-price change records (Price Changes tab)

```js
[{ date: "2026-05-11", id: "...", old: 70.0, new: 55.0,
   delta: -15.0, pct: -21.4,  // pct is a number (not decimal!) — -21.4 means -21.4%
   t: "...", b: "vans", sku: "00020171|BLK|9|NA" }, ...]
```

Sort by `date` desc.

## `MARKET_CHANGES` — array of Market Price change records

Same shape as `CHANGES`. Built by diffing the latest `MARKET_HISTORY` entry against the previous one for each product. Filtered to non-trivial moves (≥$1 AND ≥2%) since Market Prices wobble with Google's click-weighting.

## `PERF` — array, PRODUCT-LEVEL performance (Product Performance tab)

Each row is one product (a group of variants), keyed by landing page path (or `title:...` fallback).

```js
[{
  id:   "/products/nike-air-force-1-07-white", // group key: LP path OR "title:<brand>|<title>"
  t:    "Nike Air Force 1 '07 / White",        // representative title
  b:    "nike",                                 // brand
  sk:   "",                                     // empty at product level
  p:    150.0,    // median ecomm across variants in group
  m:    148.75,   // median market across variants in group
  av:   1,        // 1 if ANY variant in stock
  os:   1,        // 1 if ANY variant on sale
  has:  true,     // has activity (orders OR sessions) in L7
  hs:   true,     // has sales in L7
  ol7:  128,      // sum L7 orders across variants
  rl7:  19200.0,  // sum L7 revenue
  sl7:  2089,     // LP-level sessions in L7 (not summed across variants — already product-level)
  cl7:  0.0191,   // LP completed_checkout / LP sessions
  doo: 0.45, dr: 0.32, ds: 0.18, dc: 0.0024,   // WoW deltas (decimals)
  lift: 0,        // ≥30% WoW lift on baseline ≥10 orders OR ≥100 sessions
  hc:   1,        // 1 if ANY variant has High-confidence simulation
  nv:   21,       // number of variants in this product group
  lp:   "/products/nike-air-force-1-07-white",  // landing page (empty for title-fallback groups)
}, ...]
```

Sort by `ol7` desc.

## `VARIANTS` — dict of per-product variant breakdowns (drill-down on Product Performance)

```js
{
  "/products/nike-air-force-1-07-white": [
    { pid: "40524534808758", t: "...", sk: "00008225|WHT|10.5|NA",
      p: 150.0, m: 146.97, gap: 0.0206, av: 1, os: 0,
      ol7: 16, rl7: 2400.0 },
    ...sorted by L7 orders desc, then ecomm price asc
  ],
  ...
}
```

The key matches `PERF[i].id`. Rendered as a table inside the row's expanded detail.

## `SERIES` — dict of per-product daily timeseries (YTD)

Now keyed by **product group key** (matching PERF.id), not individual Product ID.

```js
{ "/products/...": { di: [0, 1, ..., n-1], o: [...], r: [...] }, ... }
```

`o` = orders/day, `r` = revenue/day (CAD). Day 0 = Jan 1 of the current year (max_sales_date.year). Only products with ≥1 order YTD are included to keep file size down.

The original template also embeds `s` (sessions), `c` (checkouts), and `l*` year-over-year arrays — those require per-SKU session data that's not cleanly available from the Shopify exports we have, so they're omitted. The chart fallbacks gracefully.

## `CVR_BASELINE` — single number

```js
const CVR_BASELINE = 0.0144;   // aggregate site L7 CVR
```

## `POSITION_SNAPSHOTS` — array (Catalogue Trend tab)

Lives in `template_part2.html`, not in the data blob. The rebuild script edits this array in place.

```js
const POSITION_SNAPSHOTS = [
  { d: '2026-04-27', total: 9179, above: 1603, at: 4279, below: 3297, onsale: 3000, oos: null },
  ...
];
```

**Accumulates week over week.** Each rebuild appends one entry (or replaces today's if already present).

## File size sanity check

A typical full rebuild produces ~11–17 MB. If it balloons past 25 MB, tighten:
- `SERIES`: bump `min_orders` from 1 to 5 or 10
- `PRICE_HISTORY`/`MARKET_HISTORY`: trim to last 12 weeks per product
- `CHANGES`: keep last 60 days only
