---
name: jd-pricing-dashboard
description: Rebuilds the JD Sports Canada Online Shopping Market Pricing dashboard at https://jd-ecomm.github.io/online-shopping-market-pricing/. Injects fresh weekly data into the actual template (stored in template/), preserving prior weekly history (POSITION_SNAPSHOTS and PRICE_HISTORY) from the previous build. Triggers when the user mentions JD pricing dashboard, Market Price, Pricing Opportunity, the jd-ecomm repo, online-shopping-market-pricing, or uploads the weekly Google Merchant Centre exports (Price Benchmarks CSV, Sale Price Suggestions CSV, products TSV/zip) together with the three Shopify exports (Daily Product Sales by SKU, the same with LP link, Landing Page Performance).
---

# JD Sports Canada — Pricing Dashboard Rebuilder

## What this skill does

The dashboard at `https://jd-ecomm.github.io/online-shopping-market-pricing/` is a single self-contained `index.html` (~17 MB) maintained in the `jd-ecomm/online-shopping-market-pricing` GitHub repo. The HTML template (CSS, layout, JS rendering logic) is **stable** — it doesn't change week to week. Only the embedded data blob changes.

This skill ships:

- **The real template**, split into two parts (`template/template_part1.html` and `template/template_part2.html`), with the data blob removed
- **A rebuild script** (`scripts/rebuild.py`) that ingests the weekly CSVs, computes the data blob in the exact shape the template expects, and injects it between the two template halves
- **History preservation**: pass the existing `index.html` as `--previous` and the script extracts the prior `POSITION_SNAPSHOTS` (catalogue position over time) and `PRICE_HISTORY` (per-SKU price log), appends the new week's data point, and writes them into the new build

This means: never reconstruct the template from scratch, never guess at the data schema. The template is the source of truth.

## When to use

User uploads the six weekly CSV files for JD and asks to refresh / rebuild the dashboard. Or mentions: JD pricing, Market Price, Pricing Opportunity, jd-ecomm repo, online-shopping-market-pricing.

## Required inputs

In `/mnt/user-data/uploads/` (or wherever you point `--uploads`):

| Prefix | Source | What it provides |
|---|---|---|
| `Your_most_popular_products_with_price_benchmarks_*.csv` | Google Merchant Centre - Price Benchmarks | Canonical Product ID universe, Market Price (Benchmark column), Clicks (28d) |
| `Sale_price_suggestions_with_highest_performance_impact_*.csv` | Google Merchant Centre - Sale Price Suggestions | Discount simulation: Suggested price, Click and Conversion uplift, Effectiveness |
| `products_*.zip` (contains `.tsv`) | Google Merchant Centre - product feed | Effective Ecomm Price, sale flag, availability, GTIN, image, brand |
| `RC_-_Daily_Product_Sales_by_SKU_-_*.csv` | Shopify Analytics | Daily orders + revenue per Product variant ID (the join key to Google's Product ID) |
| `RC_-_Daily_Product_Sales_by_SKU_with_LP_Link_-_*.csv` | Shopify Analytics | Maps Product variant ID to landing page path (for session attribution) |
| `RC_-_Landing_Page_Performance_-_*.csv` | Shopify Analytics | Per-landing-page sessions + completed checkouts |

**Plus** (recommended): the existing `index.html` from the repo as `--previous`, so history is preserved.

## Workflow

1. Read this file fully, then `reference/file-schemas.md` and `reference/data-shape.md`.
2. Locate inputs under `/mnt/user-data/uploads/`. If any of the six files is missing, stop and tell the user exactly which is missing — do not fabricate.
3. Check whether the user provided their existing `index.html` (probably also under `/mnt/user-data/uploads/`). If so, pass it as `--previous`. If not, history starts fresh from this week.
4. Run the script:
   ```bash
   python3 scripts/rebuild.py \
     --uploads /mnt/user-data/uploads \
     --previous /mnt/user-data/uploads/index.html \
     --output /mnt/user-data/outputs/index.html
   ```
5. The script prints diagnostic counts at each stage — confirm they look sane (~10k products, the right number of position snapshots preserved + 1).
6. Present `/mnt/user-data/outputs/index.html` with `present_files`.
7. Tell the user the commit command: `cp index.html <repo>/index.html && git add . && git commit -m "Weekly refresh YYYY-MM-DD" && git push`.

## Weekly run (no exports, no uploads) — validated end to end Oct 19, 2026

Ryan wants the whole update pulled automatically. He only pushes the final index.html to GitHub himself. Needs: this session linked to his computer (device bridge on ~/Downloads, which has `device_bash`), Claude in Chrome connected, Gmail connector. The **Shopify connector is NOT used** (JD IT flagged it); Shopify comes through Chrome instead.

**0. Restore state.** From `~/Downloads/jd-pricing-state/` stage the four `*.csv.gz` history files and gunzip them into a fresh build folder (they are the running Shopify history since 2025-12-28). The previous dashboard is the newest `~/Downloads/market-pricing-dashboard_<date>/index.html`: stage it and pass it as `--previous` (it carries price, market and change history). Use `jd-pricing-dashboard-skill.zip` from the state folder if the skill bundle is missing.

**1. Competitor prices (Daily Markdown Tracker chat).**
- Read the tracker chat ("Matching Foot Locker sale products to our inventory") with conversation_search (`within_conversation_id` 349aefbc-e679-4cd9-867c-f7cc519542f6): confirm the date of the latest completed run and any data problem it flagged. Do not use a run it marked as wrong (e.g. the Oct 13 Champs promo-badge prices).
- Stage the newest `JD_DMT_dashboard_<date>.html` from Downloads and convert it: `python3 -I scripts/dmt_html_to_matches.py <html> <build_dir>` → `all_competitor_matches_<date>.csv`. Validated: identical matched rows and exact count to the tracker's own CSV export, so no CSV export is needed. Exact matches only are used.

**2. Buying markdowns (Gmail).**
- Gmail connector: `subject:("PRICE CHANGES" MARKDOWNS) has:attachment newer_than:21d`. Compare the go-live date in each subject ("LIVE ON OCT 15TH") with `max(go)` in data/markdowns.json.
- For each missing week, download in Chrome: open `https://mail.google.com/mail/?authuser=ryan.clarke@jdcanada.ca#all/<messageId>`, find "collapsed message from <sender>" and click it to expand, then JS: read `[download_url]` (format `mime:filename:url`), take the url, replace `disp=safe` with `disp=attd`, set `window.location.href` to it. The .xlsb lands in Downloads. (Gmail's own download button and "Add to Drive" do not work: the Drive connector is the personal account. The Gmail connector cannot download attachments; RAW is too large.)
- Convert with soffice, then `scripts/add_markdowns.py` (set FILES = [(path, 'YYYY-MM-DD')]). Sheet names may say "RETAIL + ECOM" (= All channels); the action column may be spelled "ACTON".

**3. Merchant Center (Chrome, account a=511095134).** Each download now shows a "Ready to download" toast that must be clicked with a real click (computer left_click on the toast's Download link; JS .click() on the toast does not start the download).
- Analytics → Pricing (`/mc/reporting/performance/pricing?a=511095134`): "View all your products" → price benchmarks; "View more details" → sale price suggestions. On each report: button aria-label "Open the report download menu" → ".csv" → click toast Download.
- Products (`/mc/items?a=511095134`): button aria-label "Download products" → wait up to ~2 min for the toast → click Download → `products_<ts>.zip`.
- **Oct 2026 change:** Merchant Center now has a second source (Shopify app). Benchmarks and feed contain ids `shopify_ZZ_<product>_<variant>` plus French rows. rebuild.py normalises these to the variant id, merges duplicate benchmark rows (benchmark from the highest-click listing, clicks summed) and only fills feed gaps from English Shopify-source rows. Expect "17k duplicate listings merged" and ~1k feed rows filled.

**4. Shopify (Chrome, ShopifyQL through Ryan's admin session).** Open `https://admin.shopify.com/store/jdsports-ca/analytics`, read the CSRF token (`meta[name=csrf-token]`, or the `"csrfToken"` value in the page HTML), and POST to `/store/jdsports-ca/admin/api/2025-10/graphql.json` with `query($q:String!){ shopifyqlQuery(query:$q){ tableData{ columns{name} rows } parseErrors } }`. For each day since the last history day, run:
   - `FROM sales SHOW total_sales, net_sales, orders, net_items_sold, gross_profit GROUP BY day, product_title, product_variant_sku, product_id, product_variant_id SINCE d UNTIL d LIMIT 100000`
   - `FROM sessions SHOW online_store_visitors, sessions, bounce_rate, added_to_cart_rate, conversion_rate GROUP BY day, landing_page_path WHERE landing_page_type = 'Product' SINCE d UNTIL d LIMIT 100000`
   - `FROM sales SHOW gross_margin, net_sales, quantity_ordered, gross_profit, cost_of_goods_sold GROUP BY day, product_title_at_time_of_sale, product_type SINCE d UNTIL d LIMIT 100000`
   Collect into `{sales, lp, margin}` (rows are objects) and save one Blob download `shopify_pull_<start>_<end>.json` (JS return values are too small for the data). Then `python3 -I scripts/merge_shopify_browser.py <pull.json> <restored_history_dir> <build_dir>`; it replaces any overlapping days and prints daily net sales. Check them against `FROM sales SHOW net_sales TIMESERIES day`. Only pull complete days (up to yesterday).

**5. Build and check.** Copy GMC files into the build folder with underscores for spaces, then `python3 scripts/rebuild.py --uploads <build_dir> --previous <prev index.html> --output <new.html>`. Check the log: universe ~11k, "Reconstructed N market changes" ≥ last run's total, markdowns include the newest week, competitor exact matches present, size under 25 MB. Load in headless Chromium (serve Chart.js from node_modules; the CDN is blocked in the sandbox) and click every tab plus a row in Pricing Opportunity and Product Performance: no errors.

**6. Deliver and save state.** Save the dashboard to `~/Downloads/market-pricing-dashboard_<date>/index.html` (Ryan pushes it to GitHub). Gzip the four Shopify history CSVs and save them over `~/Downloads/jd-pricing-state/` along with the updated skill zip. Files over ~20 MB must go through SendUserFile first and be committed by fileUuid.

**Device bridge quirks.** A freshly downloaded file can report "hardlinked" for a few seconds; wait and stage again. Never `cp` inside the mounted Downloads folder (it creates a hard link and the bridge cannot delete). The Downloads listing caps at 2,000 entries, so use `device_bash` (`ls -t`) to find new files.

## Hard rules

- **The template is sacred.** Don't regenerate it from scratch. The two template files in `template/` are the canonical source. Edit them directly only if the user explicitly wants a template change.
- **Data field names matter.** The JS in the template references specific compact field names: `id, t, b, p, m, c, os, rp, sa, sk, gt, av, sp, cu, vu, ef`. Use them verbatim in `PRODUCTS`. See `reference/data-shape.md` for every collection's schema.
- **Always work at Product ID level.** ~83% of titles span multiple Product IDs (size/colourway variants) with distinct Market Prices.
- **Ecomm Price = effective price from the feed** (sale_price if set, else price).
- **Market Price = `Benchmark` column from Price Benchmarks export**, unique per Product ID.
- **Currency is CAD throughout.**
- **History preservation is non-negotiable** if `--previous` is provided. POSITION_SNAPSHOTS and PRICE_HISTORY must accumulate week over week.

## Output

A single `index.html` (~17 MB), ready to drop into the `jd-ecomm/online-shopping-market-pricing` repo and serve via GitHub Pages.

## Files in this skill

- `SKILL.md` — this file
- `template/template_part1.html` — everything before the data blob (HTML head, CSS, body up to `// DATA`)
- `template/template_part2.html` — everything after the data blob (JS rendering logic + `</body>`)
- `scripts/rebuild.py` — ingests CSVs, builds data blob, injects into template
- `reference/file-schemas.md` — exact CSV column layouts + skip-row rules
- `reference/data-shape.md` — every embedded data collection's schema (PRODUCTS, BRANDS, METRICS, PERF, SERIES, PRICE_HISTORY, CHANGES, POSITION_SNAPSHOTS, MARKET_CHANGES)
- `reference/calculations.md` — formulas for gap, lift, position bands, week-over-week deltas

## Nov 8, 2026 run (done from the Control Bot chat, Windows PC, built-in browser for everything)
- Template now comes from the 1 Nov build (Inter Tight fonts, d0 SERIES loop); template_part1/2 in this zip are current.
- Set RUN_DATE=YYYY-MM-DD (Vancouver date) when running rebuild.py; otherwise it uses the container's UTC date.
- Merchant Center in the built-in browser: products feed downloads straight away; for the two reports use find ".csv" + a real click on the first option. The sale price suggestions CSV can arrive UTF-16 and tab separated: iconv -f UTF-16 -t UTF-8 and convert tabs to commas.
- Gmail in the built-in browser: [download_url] holds a doubled URL; take the substring from the last "https://".
- Competitor prices: dmt_html_to_matches.py on raw.githubusercontent.com/jd-ecomm/daily-markdown-tracker/main/index.html.
- Publish: scripts/split_for_github.py <built.html> <out_dir> <yyyymmdd>, copy index.html + data/part1-4.js into jd-ecomm/online-shopping-market-pricing and git push (cloud session with the repo attached).
