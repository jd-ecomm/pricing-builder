# pricing-builder (private)

Builder, scripts and running state for the JD Sports Canada **Online Shopping Market Pricing** dashboard, published to
[jd-ecomm/online-shopping-market-pricing](https://github.com/jd-ecomm/online-shopping-market-pricing).

- How to run: [`SKILL.md`](SKILL.md) (weekly no-export run; read the "Nov 8, 2026 run" section at the end).
- `state/history/`: gzipped Shopify history since 2025-12-28 (daily sales by SKU, landing pages, margin, LP link). gunzip into the build folder, then `scripts/merge_shopify_browser.py` appends new days.
- `state/previous/index.html`: the last full build, passed to `rebuild.py --previous` (carries price, market and change history). `DATE` says which run it is.
- `data/markdowns.json`: Buying markdown events (add new weeks with `scripts/add_markdowns.py`).
- After each run: commit the new `state/history/*.gz` (replace the older dated files), `state/previous/index.html` + `DATE`, and `data/markdowns.json`. Downloads\jd-pricing-state on Ryan's work PC is a backup copy only.

Last state: 2026-11-08 run (Shopify through 2026-11-07, markdowns through the Nov 12 BFCM Phase 1 list).
