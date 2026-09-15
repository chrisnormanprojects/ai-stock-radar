# AI Stock Radar

A mobile-first UK share research scanner. Scores are momentum heuristics, not forecasts or investment advice. No API key is required.

## Data and coverage

The updater reads **every page** of Hargreaves Lansdown's FTSE All-Share constituent table, matching only labelled stock rows. It checks uniqueness, core members, pagination and large membership changes. This is provider-listed coverage, not independently certified FTSE Russell membership. Source and exclusions are visible in the app.

Yahoo Finance daily charts supply prices and volume. Each quote must match the latest FTSE 100 trading session and have at least 66 valid daily bars, a current quote timestamp and consistent price units. Suspicious quote/history discrepancies and large discontinuities are quarantined, not automatically rescaled. All calculations use the same price series. Zero volume is not replaced by average volume; flat-price RSI is neutral.

The snapshot retains all validated shares and their histories, plus the complete discovered membership and exclusion reasons. Radar defaults to 30; search, Movers, watchlists and paper positions use the full snapshot. Missing quotes are explicit. Legacy paper entries with unverified currency do not show invented returns.

A snapshot is published only when at least 90% of discovered members pass validation. Partial coverage is labelled, with every exclusion listed. If validation fails, the previous snapshot is retained and `data/status.json` reports failure. The interface warns about cached snapshots and snapshots older than six hours. Daily bars are not real-time prices.

## Updates and deployment

`.github/workflows/update-market-data.yml` requests an update at minute 17 of every hour Monday–Friday (UTC), on generator/test changes, or manually. GitHub may delay scheduled jobs. Runs are serialized. Tests precede retrieval and failed retrieval still commits health status, then marks the run failed. Monitor the Actions tab and the site's freshness banner; the schedule is not a timing guarantee.

GitHub Pages serves `main` at `/`. The offline shell is network-first for navigation; data is never replaced by HTML. Cached summaries omit histories to stay within mobile storage limits. Storage failure does not prevent fresh results from displaying.

Open the site in iPhone Safari and use Share → Add to Home Screen. Icons are in `assets/`.

## Development

```sh
python -m unittest discover -s tests -v
node tests/test-ui.cjs
python scripts/fetch_market_data.py
```

The generator uses the Python standard library only. Tests use synthetic fixtures and do not contact providers. Live refresh uses provider access and may exclude stale, discontinued or recently listed shares.
