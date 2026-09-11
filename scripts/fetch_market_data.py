#!/usr/bin/env python3
import html, json, os, re, statistics, time
from datetime import datetime, timezone
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "market.json")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 AIStockRadar/3.0"
FTSE_ALL_SHARE_URL = "https://www.lse.co.uk/indices/ftse-all-share/constituents.html"
EXPECTED_CONSTITUENTS = 534
TOP_N = 30
BATCH_SIZE = 35


def get_text(url, timeout=35):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def get_json(url, timeout=35):
    return json.loads(get_text(url, timeout=timeout))


def clamp(n, a, b):
    return max(a, min(b, n))


def rsi14(closes):
    if len(closes) < 15:
        return None
    seq = closes[-15:]
    gains, losses = [], []
    for a, b in zip(seq[:-1], seq[1:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains) / 14
    al = sum(losses) / 14
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def volatility20(closes):
    if len(closes) < 3:
        return None
    tail = closes[-21:]
    rs = [(b / a - 1) * 100 for a, b in zip(tail[:-1], tail[1:]) if a]
    return statistics.pstdev(rs) if len(rs) > 1 else 0.0


def score_row(change, mom5, vol_ratio, sma20, rsi):
    score = 45
    score += clamp(change * 3.0, -15, 18)
    score += clamp(mom5 * 1.4, -10, 16)
    score += clamp((vol_ratio - 1) * 9, -5, 12)
    score += clamp(sma20 * 0.8, -6, 8)
    if rsi is not None and rsi > 75:
        score -= 5
    if rsi is not None and rsi < 30:
        score -= 2
    return round(clamp(score, 0, 100), 1)


def yahoo_symbol(lse_code):
    # Yahoo uses e.g. BP.L / AV.L / BT-A.L for LSE shares.
    base = lse_code.strip().rstrip(".").replace(".", "-")
    return base + ".L"


def fetch_ftse_all_share_universe():
    page = get_text(FTSE_ALL_SHARE_URL)
    marker = "The following shares make up the FTSE All-Share."
    if marker in page:
        page = page.split(marker, 1)[1]

    # Constituents link to SharePrice pages with shareprice=<LSE code>.
    rx = re.compile(r'<a[^>]+href=["\'][^"\']*shareprice=([^&"\']+)[^"\']*["\'][^>]*>(.*?)</a>', re.I | re.S)
    found = []
    seen = set()
    for raw_code, raw_name in rx.findall(page):
        code = unquote(raw_code).strip().upper()
        name = html.unescape(re.sub(r"<[^>]+>", "", raw_name)).strip()
        name = re.sub(r"\s+", " ", name)
        if not code or code in seen:
            continue
        # Ignore obvious non-LSE noise if any appears below the constituent table.
        if len(code) > 8 or not re.fullmatch(r"[A-Z0-9.]+", code):
            continue
        seen.add(code)
        found.append({"ticker": yahoo_symbol(code), "lseCode": code, "nameHint": name, "market": "UK"})

    if len(found) < 500:
        raise RuntimeError(f"Only discovered {len(found)} FTSE All-Share constituents")

    # The official LSE overview currently reports 534 constituents. The table is ordered
    # as a contiguous block, so cap any unrelated links that might appear later in the page.
    return found[:EXPECTED_CONSTITUENTS]


def parse_yahoo_response(response, item):
    meta = response.get("meta", {})
    q = ((response.get("indicators", {}).get("quote") or [{}])[0])
    timestamps = response.get("timestamp") or []
    closes = q.get("close") or []
    volumes = q.get("volume") or []

    rows = []
    for i, ts in enumerate(timestamps):
        c = closes[i] if i < len(closes) else None
        v = volumes[i] if i < len(volumes) else 0
        if c is not None:
            rows.append((int(ts), float(c), float(v or 0)))
    if len(rows) < 21:
        raise RuntimeError("Not enough Yahoo history")

    cs = [r[1] for r in rows]
    vs = [r[2] for r in rows]
    price = float(meta.get("regularMarketPrice") or cs[-1])
    prev = float(cs[-2])
    change = (price / prev - 1) * 100 if prev else 0
    mom5 = (price / cs[-6] - 1) * 100 if len(cs) >= 6 and cs[-6] else 0
    prev_vols = [v for v in vs[-21:-1] if v > 0]
    avgvol = sum(prev_vols) / len(prev_vols) if prev_vols else 0
    vr = (vs[-1] / avgvol) if avgvol and vs[-1] else 1
    sma = sum(cs[-20:]) / 20
    sma20 = (price / sma - 1) * 100 if sma else 0
    high90 = max(cs[-66:])  # roughly 90 calendar days of trading sessions
    high90pct = (price / high90 - 1) * 100 if high90 else 0
    rsi = rsi14(cs)
    vola = volatility20(cs)
    history = [
        {"date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"), "close": round(close, 4)}
        for ts, close, _ in rows
    ]

    row = {
        "ticker": item["ticker"],
        "lseCode": item["lseCode"],
        "name": meta.get("longName") or meta.get("shortName") or item.get("nameHint") or item["lseCode"],
        "market": "UK",
        "currency": meta.get("currency") or "GBp",
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName") or "LSE",
        "price": round(price, 4),
        "previousClose": round(prev, 4),
        "change": round(change, 2),
        "mom5": round(mom5, 2),
        "volRatio": round(vr, 2),
        "rsi": round(rsi, 1) if rsi is not None else None,
        "sma20": round(sma20, 2),
        "volatility": round(vola, 2) if vola is not None else None,
        "high90": round(high90pct, 2),
        "history": history,
        "timestamp": datetime.fromtimestamp(rows[-1][0], timezone.utc).isoformat(),
        "source": "Yahoo Finance chart data",
        "sourceUrl": f"https://finance.yahoo.com/quote/{quote(item['ticker'])}",
        "official": {
            "source": "UK official sources",
            "lseUrl": "https://www.londonstockexchange.com/",
            "companiesHouseUrl": "https://find-and-update.company-information.service.gov.uk/"
        }
    }
    row["score"] = score_row(row["change"], row["mom5"], row["volRatio"], row["sma20"], row["rsi"])
    return row


def fetch_batch(batch):
    symbols = ",".join(x["ticker"] for x in batch)
    url = "https://query1.finance.yahoo.com/v7/finance/spark?symbols=" + quote(symbols, safe=",.-") + "&range=1y&interval=1d&indicators=close&includeTimestamps=true&includePrePost=false"
    data = get_json(url, timeout=50)
    results = (data.get("spark", {}) or {}).get("result") or []
    by_symbol = {r.get("symbol"): r for r in results if r.get("symbol")}
    rows, errors = [], []
    for item in batch:
        try:
            r = by_symbol.get(item["ticker"])
            response = ((r or {}).get("response") or [None])[0]
            if not response:
                raise RuntimeError("No spark response")
            rows.append(parse_yahoo_response(response, item))
        except Exception as e:
            errors.append({"ticker": item["ticker"], "error": str(e)})
    return rows, errors


def fetch_one_chart(item):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(item['ticker'])}?range=1y&interval=1d&includePrePost=false&events=div%2Csplits"
    data = get_json(url)
    response = ((data.get("chart", {}) or {}).get("result") or [None])[0]
    if not response:
        raise RuntimeError("Yahoo returned no chart result")
    return parse_yahoo_response(response, item)


def main():
    generated = datetime.now(timezone.utc).isoformat()
    universe = fetch_ftse_all_share_universe()
    stocks, errors = [], []

    for pos in range(0, len(universe), BATCH_SIZE):
        batch = universe[pos:pos + BATCH_SIZE]
        try:
            rows, batch_errors = fetch_batch(batch)
            stocks.extend(rows)
            errors.extend(batch_errors)
        except Exception as e:
            errors.append({"batch": pos // BATCH_SIZE + 1, "error": f"spark batch failed: {e}"})
            # Slow fallback means one failed batch does not invalidate the whole scan.
            for item in batch:
                try:
                    stocks.append(fetch_one_chart(item))
                except Exception as inner:
                    errors.append({"ticker": item["ticker"], "error": str(inner)})
                time.sleep(0.08)
        time.sleep(0.15)

    stocks.sort(key=lambda x: (x.get("score", 0), x.get("change", 0)), reverse=True)
    top = stocks[:TOP_N]
    for i, row in enumerate(top, 1):
        row["rank"] = i

    payload = {
        "generatedAt": generated,
        "universe": "FTSE All-Share",
        "universeSource": FTSE_ALL_SHARE_URL,
        "universeSize": len(universe),
        "analysedCount": len(stocks),
        "displayCount": len(top),
        "ranking": "Radar score descending",
        "stocks": top,
        "errors": errors[-100:]
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"analysed {len(stocks)} of {len(universe)} FTSE All-Share constituents; published top {len(top)}; {len(errors)} errors")


if __name__ == "__main__":
    main()
