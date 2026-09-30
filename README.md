# AI Stock Radar

A mobile-first UK stock research app for momentum, unusual volume, technical signals, watchlists and paper trading.

## Important
This app is a research tool, not financial advice and not an automated trading system.

A high score does **not** mean a share will rise.

## Files
- `index.html` — the app
- `manifest.webmanifest` — installable web-app settings
- `service-worker.js` — offline shell/cache support
- `assets/` — app icons

## Put it on GitHub Pages

1. Create a new GitHub repository, for example:
   `ai-stock-radar`

2. Make the repository **Public**.

3. Upload **all the files and the `assets` folder** from this package into the root of the repository.

Your repository should look like:

```text
ai-stock-radar/
├── index.html
├── manifest.webmanifest
├── service-worker.js
├── README.md
└── assets/
    ├── icon-180.png
    ├── icon-192.png
    └── icon-512.png
```

4. Open the repository's:
   **Settings → Pages**

5. Under **Build and deployment** choose:
   **Deploy from a branch**

6. Select:
   - Branch: `main`
   - Folder: `/ (root)`

7. Press **Save**.

Your site will normally appear at:

```text
https://YOUR-USERNAME.github.io/ai-stock-radar/
```

## Install it on iPhone

After GitHub Pages is live:

1. Open the website in **Safari**.
2. Tap **Share**.
3. Tap **Add to Home Screen**.
4. Tap **Add**.

It will then launch much more like a normal iPhone app.

## Live stock data

The scheduled GitHub Action builds `data/market.json` on weekdays every two hours.

Current data flow:

- **London South East (lse.co.uk)** — FTSE All-Share constituent discovery, cross-checked against FTSE 100, FTSE 250 and FTSE SmallCap pages.
- **Yahoo Finance** — daily prices, volume and one-year history.
- **London Stock Exchange** — official FTSE All-Share constituent-count reference used as a quality diagnostic.
- **Companies House** — manual company verification link only; it is not a live ranking feed.

The generator calculates daily change, 5-day momentum, relative volume, RSI-14, 20-day moving-average position, 20-day volatility and distance from the recent high, then ranks the top 30 with the Radar Score.

There is currently **no Alpha Vantage feed and no live news feed** in the production scanner.

### Data-quality safeguards

A refresh is refused if the discovered universe is implausibly small/large, changes sharply from the last known-good dataset, or Yahoo quote coverage falls below 97%. The official LSE constituent count is deliberately treated as a diagnostic rather than a fixed publish threshold because it changes at index reviews.

### Security
Do **not** paste an OpenAI API key directly into `index.html`, JavaScript, GitHub, or any other public client-side file.

If ChatGPT/OpenAI analysis is added later, it should go through a secure server-side or serverless function.

## Current features

- FTSE All-Share radar scoring
- Top 30 ranked results
- Fast movers
- 30D / 90D / 6M / 12M price charts
- RSI, relative volume, moving-average and volatility analytics
- Watchlist
- Paper trading
- Mobile-first/iPhone interface
- Installable PWA
- Offline app shell

## Suggested next version

A production-quality v2 should add:

- add an independent second constituent-list provider to close any gap between the public discovery source and the official FTSE reference
- MACD and additional indicators
- unusual-volume alerts
- signal history
- automated outcome tracking after 1 hour / 1 day / 5 days / 20 days
- backtesting
- a secure news/catalyst feed
- a secure OpenAI analysis endpoint
- push notifications for high-scoring signals

