# AI Stock Radar

A mobile-first stock research app for momentum, unusual volume, news catalysts, watchlists and paper trading.

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

The app can use an Alpha Vantage API key.

Open:

**Settings → Alpha Vantage API key**

Paste your key and save it.

The key is stored in that browser's local storage.

### Security
Do **not** paste an OpenAI API key directly into `index.html`, JavaScript, GitHub, or any other public client-side file.

If ChatGPT/OpenAI analysis is added later, it should go through a secure server-side or serverless function.

## Current features

- Stock radar scoring
- Top opportunities list
- Early movers
- News catalyst view
- Watchlist
- Paper trading
- US/UK filtering
- Mobile-first/iPhone interface
- Installable PWA
- Offline app shell

## Suggested next version

A production-quality v2 should add:

- proper UK market discovery
- charts
- RSI / MACD / moving averages
- unusual-volume alerts
- signal history
- automated outcome tracking after 1 hour / 1 day / 5 days / 20 days
- backtesting
- a secure OpenAI analysis endpoint
- push notifications for high-scoring signals

