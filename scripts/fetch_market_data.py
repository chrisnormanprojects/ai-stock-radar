#!/usr/bin/env python3
"""Publish a validated full-universe snapshot; retain the last good file on failure."""
import html
import json
import math
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/market.json'
STATUS = ROOT / 'data/status.json'
UNIVERSE_URL = 'https://www.hl.co.uk/shares/stock-market-summary/ftse-all-share'
UA = 'Mozilla/5.0 AIStockRadar/4.0'
TOP_N = 30
MIN_COVERAGE = 0.90
LONDON = ZoneInfo('Europe/London')


def get_text(url, timeout=25):
    with urlopen(Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/html'}), timeout=timeout) as response:
        return response.read().decode('utf-8')


def get_json(url):
    return json.loads(get_text(url))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def yahoo_symbol(code):
    return code.strip().rstrip('.').replace('.', '-') + '.L'


def parse_constituent_page(page):
    # Match ONLY provider-labelled stock rows. Navigation, adverts and share-chat
    # links must never become index members. Read every advertised page below.
    found = []
    for code, body in re.findall(r'<tr\b[^>]*\bid=["\']ls-row-([^"\']+)-L["\'][^>]*>(.*?)</tr>', page, re.S | re.I):
        cell = re.search(r'<td\b[^>]*>\s*([^<]+)\s*</td>', body, re.I)
        name = re.search(r'data-s-name=["\']([^"\']+)["\']', body)
        if not cell or not name or cell[1].strip() != code:
            raise ValueError('Constituent table format changed')
        if not re.fullmatch(r'[A-Z0-9.]+', code):
            raise ValueError(f'Invalid constituent code: {code}')
        found.append({'ticker': yahoo_symbol(code), 'lseCode': code, 'nameHint': html.unescape(name[1])})
    if not found:
        raise ValueError('No constituent table rows')
    return found


def fetch_ftse_all_share_universe():
    first = get_text(UNIVERSE_URL)
    pages = {1} | {int(n) for n in re.findall(r'\?page=(\d+)', first)}
    if max(pages) > 15 or pages != set(range(1, max(pages) + 1)):
        raise ValueError('Unexpected constituent pagination')
    rows = parse_constituent_page(first)
    counts = [len(rows)]
    for page in sorted(pages - {1}):
        batch = parse_constituent_page(get_text(f'{UNIVERSE_URL}?page={page}'))
        rows.extend(batch)
        counts.append(len(batch))
    symbols = [r['ticker'] for r in rows]
    if len(symbols) != len(set(symbols)):
        raise ValueError('Repeated constituents or repeated pagination')
    if not 450 <= len(rows) <= 650:
        raise ValueError(f'Constituent count outside safety bounds: {len(rows)}')
    if not {'HSBA.L', 'SHEL.L', 'AZN.L', 'III.L'}.issubset(symbols):
        raise ValueError('Core constituents missing')
    # Compare only against previous snapshots produced by this parser/schema.
    if OUT.exists():
        previous = json.loads(OUT.read_text())
        if previous.get('schemaVersion') == 2:
            previous_symbols = {r['ticker'] for r in previous.get('constituents', [])}
            if previous_symbols and len(previous_symbols ^ set(symbols)) / len(previous_symbols) > .10:
                raise ValueError('Constituent membership changed by more than 10%; review required')
    print(f'Constituent table pages: {counts}; total={len(rows)}', flush=True)
    return rows, {'provider': 'Hargreaves Lansdown', 'url': UNIVERSE_URL,
                  'pageCounts': counts, 'status': 'provider-list',
                  'note': 'All published constituent pages; not independently certified against a current FTSE Russell membership file.'}


def clamp(value, low, high):
    return max(low, min(high, value))


def rsi14(closes):
    deltas = [b-a for a, b in zip(closes[-15:-1], closes[-14:])]
    gain, loss = sum(max(d, 0) for d in deltas)/14, sum(max(-d, 0) for d in deltas)/14
    if gain == loss == 0:
        return 50.0
    return 100.0 if loss == 0 else 100 - 100/(1+gain/loss)


def volatility20(closes):
    return statistics.pstdev([(b/a-1)*100 for a, b in zip(closes[-21:-1], closes[-20:])])


def score_row(change, mom5, vol_ratio, sma20, rsi):
    score = 45 + clamp(change*3, -15, 18) + clamp(mom5*1.4, -10, 16)
    score += clamp((vol_ratio-1)*9, -5, 12) + clamp(sma20*.8, -6, 8)
    score -= 5 if rsi > 75 else 2 if rsi < 30 else 0
    return round(clamp(score, 0, 100), 1)


def chart(symbol, range_='1y'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range={range_}&interval=1d&includePrePost=false&events=div%2Csplits'
    data = get_json(url)
    result = (data.get('chart', {}).get('result') or [None])[0]
    if not result:
        raise ValueError('No Yahoo chart response')
    return result


def expected_session(now=None):
    # The index's latest daily bar supplies the trading date, including UK
    # holidays. No assumption that yesterday was a trading day.
    now = now or datetime.now(timezone.utc)
    result = chart('^FTSE', '1mo')
    times = result.get('timestamp') or []
    if not times:
        raise ValueError('No exchange-session reference')
    day = datetime.fromtimestamp(max(times), LONDON).date()
    age = (now.astimezone(LONDON).date() - day).days
    if not 0 <= age <= 5:
        raise ValueError('Exchange-session reference is stale or in the future')
    return day.isoformat()


def parse_yahoo_response(response, item, session):
    meta = response.get('meta', {})
    if meta.get('symbol') != item['ticker']:
        raise ValueError('Quote symbol does not match requested constituent')
    currency = meta.get('currency')
    if currency not in ('GBp', 'GBP', 'USD', 'EUR'):
        raise ValueError(f'Unsupported currency: {currency}')
    q = (response.get('indicators', {}).get('quote') or [{}])[0]
    times, closes, volumes = response.get('timestamp') or [], q.get('close') or [], q.get('volume') or []
    rows = []
    for i, stamp in enumerate(times):
        if i >= len(closes) or closes[i] is None:
            continue
        close = float(closes[i])
        if not math.isfinite(close) or close <= 0:
            raise ValueError('Invalid history price')
        volume = volumes[i] if i < len(volumes) else None
        if volume is None or not math.isfinite(float(volume)) or float(volume) < 0:
            raise ValueError('Missing or invalid volume')
        rows.append((datetime.fromtimestamp(stamp, LONDON).date().isoformat(), close, float(volume)))
    if len(rows) < 66:
        raise ValueError('Fewer than 66 trading days of history')
    dates = [r[0] for r in rows]
    if dates != sorted(set(dates)):
        raise ValueError('Duplicate or unordered history dates')
    if dates[-1] != session:
        raise ValueError(f'Stale history: {dates[-1]}; expected {session}')
    quote_time = meta.get('regularMarketTime')
    if not quote_time or datetime.fromtimestamp(quote_time, LONDON).date().isoformat() != session:
        raise ValueError('Stale quote timestamp')
    if quote_time > time.time() + 300:
        raise ValueError('Quote timestamp is in the future')
    cs, vs = [r[1] for r in rows], [r[2] for r in rows]
    live = float(meta.get('regularMarketPrice') or 0)
    if not math.isfinite(live) or live <= 0 or abs(live/cs[-1]-1) > .10:
        raise ValueError('Quote/history price units or values disagree')
    # Quarantine discontinuities instead of guessing a 100x adjustment. This
    # catches mixed GBP/GBp history and unhandled corporate actions alike.
    if any(b/a > 1.8 or b/a < .4 for a, b in zip(cs[:-1], cs[1:])):
        raise ValueError('History price discontinuity; unit/corporate-action review required')
    # Use one consistent daily-bar series for the displayed price AND metrics.
    price, prev = cs[-1], cs[-2]
    avg_volume = statistics.mean(vs[-21:-1])
    if avg_volume <= 0:
        raise ValueError('No recent trading volume')
    vr = vs[-1]/avg_volume
    history = [{'date': d, 'close': round(c, 6)} for d, c, _ in rows]
    row = {'ticker': item['ticker'], 'lseCode': item['lseCode'],
           'name': meta.get('longName') or meta.get('shortName') or item['nameHint'],
           'market': 'UK', 'currency': currency, 'exchange': meta.get('exchangeName') or 'LSE',
           'price': round(price, 6), 'previousClose': round(prev, 6),
           'change': round((price/prev-1)*100, 2), 'mom5': round((price/cs[-6]-1)*100, 2),
           'volRatio': round(vr, 2), 'volume': vs[-1], 'averageVolume20': avg_volume,
           'rsi': round(rsi14(cs), 1), 'sma20': round((price/statistics.mean(cs[-20:])-1)*100, 2),
           'volatility': round(volatility20(cs), 2), 'high90': round((price/max(cs[-66:])-1)*100, 2),
           'history': history, 'sessionDate': session,
           'timestamp': datetime.fromtimestamp(quote_time, timezone.utc).isoformat(),
           'source': 'Yahoo Finance daily chart', 'sourceUrl': f'https://finance.yahoo.com/quote/{quote(item["ticker"])}'}
    row['score'] = score_row(row['change'], row['mom5'], row['volRatio'], row['sma20'], row['rsi'])
    return row


def fetch_one(item, session):
    for attempt in range(3):
        try:
            return parse_yahoo_response(chart(item['ticker']), item, session), None
        except ValueError as error:
            return None, {'ticker': item['ticker'], 'error': str(error)}
        except Exception as error:
            if attempt == 2:
                return None, {'ticker': item['ticker'], 'error': f'Quote request failed: {error}'}
            time.sleep(attempt + 1)


def validate_payload(payload):
    stocks, constituents, excluded = payload['stocks'], payload['constituents'], payload['errors']
    symbols = {x['ticker'] for x in constituents}
    included = {x['ticker'] for x in stocks}
    rejected = {x['ticker'] for x in excluded}
    if len(symbols) != len(constituents) or len(included) != len(stocks):
        raise ValueError('Duplicate symbols')
    if included & rejected or included | rejected != symbols or len(rejected) != len(excluded):
        raise ValueError('Coverage accounting mismatch')
    if len(stocks) / len(constituents) < MIN_COVERAGE:
        raise ValueError(f'Only {len(stocks)}/{len(constituents)} valid quotes; keeping previous dataset')
    if payload['analysedCount'] != len(stocks) or payload['universeSize'] != len(constituents):
        raise ValueError('Dataset counts disagree')
    if stocks != sorted(stocks, key=lambda x:(x['score'], x['change'], x['ticker']), reverse=True):
        raise ValueError('Incorrect rank ordering')
    for rank, row in enumerate(stocks, 1):
        if row['rank'] != rank or row['sessionDate'] != payload['marketSession']:
            raise ValueError('Invalid rank or session')
        if abs(row['price'] / row['history'][-1]['close'] - 1) > .00001:
            raise ValueError('Published price/history mismatch')
        if any(not math.isfinite(row[k]) for k in ('price','change','mom5','score','volRatio','rsi','sma20','volatility','high90')):
            raise ValueError('Non-finite numeric value')
    json.dumps(payload, allow_nan=False)


def main():
    started = datetime.now(timezone.utc).isoformat()
    try:
        universe, discovery = fetch_ftse_all_share_universe()
        session = expected_session()
        stocks, errors = [], []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fetch_one, item, session) for item in universe]
            for count, future in enumerate(as_completed(futures), 1):
                row, error = future.result()
                if row is not None: stocks.append(row)
                else: errors.append(error)
                if count % 50 == 0: print(f'Checked {count}/{len(universe)} quotes', flush=True)
        stocks.sort(key=lambda x:(x['score'], x['change'], x['ticker']), reverse=True)
        errors.sort(key=lambda x:x['ticker'])
        for i, row in enumerate(stocks, 1): row['rank'] = i
        payload = {'schemaVersion': 2, 'generatedAt': datetime.now(timezone.utc).isoformat(),
                   'startedAt': started, 'marketSession': session, 'universe': 'FTSE All-Share',
                   'universeSource': UNIVERSE_URL, 'discovery': discovery, 'constituents': universe,
                   'universeSize': len(universe), 'analysedCount': len(stocks),
                   'displayCount': min(TOP_N, len(stocks)), 'excludedCount': len(errors),
                   'ranking': 'Radar score descending', 'stocks': stocks, 'errors': errors,
                   'quality': {'status': 'partial' if errors else 'complete',
                               'coveragePercent': round(100*len(stocks)/len(universe), 2)}}
        validate_payload(payload)
        atomic_json(OUT, payload)
        atomic_json(STATUS, {'state':'success','checkedAt':payload['generatedAt'],'lastSuccessAt':payload['generatedAt'],
                             'analysedCount':len(stocks),'universeSize':len(universe),'excludedCount':len(errors)})
        print(f'Published {len(stocks)}/{len(universe)} valid quotes for {session}; excluded {len(errors)}', flush=True)
        for error in errors: print(f'Excluded {error["ticker"]}: {error["error"]}')
    except Exception as error:
        previous = json.loads(OUT.read_text()) if OUT.exists() else {}
        atomic_json(STATUS, {'state':'failed','checkedAt':datetime.now(timezone.utc).isoformat(),
                             'lastSuccessAt':previous.get('generatedAt'),'error':str(error)})
        raise


if __name__ == '__main__':
    main()
