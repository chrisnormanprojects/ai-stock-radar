#!/usr/bin/env python3
import json, os, statistics, time
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "market.json")
UA = "AIStockRadar/2.4 (+https://github.com/chrisnormanprojects/ai-stock-radar; chrisnormanprojects@users.noreply.github.com)"

# 50 liquid, widely followed US and UK shares. This is intentionally curated rather
# than attempting to scrape an entire exchange in one GitHub Actions run.
SYMBOLS = [
    # US (30)
    {"ticker":"NVDA","market":"US"}, {"ticker":"PLTR","market":"US"},
    {"ticker":"AAPL","market":"US"}, {"ticker":"MSFT","market":"US"},
    {"ticker":"AMZN","market":"US"}, {"ticker":"GOOGL","market":"US"},
    {"ticker":"META","market":"US"}, {"ticker":"TSLA","market":"US"},
    {"ticker":"AVGO","market":"US"}, {"ticker":"AMD","market":"US"},
    {"ticker":"NFLX","market":"US"}, {"ticker":"ORCL","market":"US"},
    {"ticker":"CRM","market":"US"}, {"ticker":"JPM","market":"US"},
    {"ticker":"BAC","market":"US"}, {"ticker":"WMT","market":"US"},
    {"ticker":"COST","market":"US"}, {"ticker":"DIS","market":"US"},
    {"ticker":"UBER","market":"US"}, {"ticker":"INTC","market":"US"},
    {"ticker":"QCOM","market":"US"}, {"ticker":"MU","market":"US"},
    {"ticker":"ARM","market":"US"}, {"ticker":"COIN","market":"US"},
    {"ticker":"HOOD","market":"US"}, {"ticker":"SOFI","market":"US"},
    {"ticker":"NKE","market":"US"}, {"ticker":"BA","market":"US"},
    {"ticker":"CAT","market":"US"}, {"ticker":"XOM","market":"US"},
    # UK (20)
    {"ticker":"RR.L","market":"UK"}, {"ticker":"VOD.L","market":"UK"},
    {"ticker":"SHEL.L","market":"UK"}, {"ticker":"LLOY.L","market":"UK"},
    {"ticker":"BARC.L","market":"UK"}, {"ticker":"IAG.L","market":"UK"},
    {"ticker":"HSBA.L","market":"UK"}, {"ticker":"BP.L","market":"UK"},
    {"ticker":"AZN.L","market":"UK"}, {"ticker":"GSK.L","market":"UK"},
    {"ticker":"ULVR.L","market":"UK"}, {"ticker":"DGE.L","market":"UK"},
    {"ticker":"NG.L","market":"UK"}, {"ticker":"BT.A.L","market":"UK"},
    {"ticker":"SBRY.L","market":"UK"}, {"ticker":"TSCO.L","market":"UK"},
    {"ticker":"EZJ.L","market":"UK"}, {"ticker":"WIZZ.L","market":"UK"},
    {"ticker":"CCL.L","market":"UK"}, {"ticker":"MKS.L","market":"UK"}
]

CIKS = {
    "AAPL": 320193, "MSFT": 789019, "NVDA": 1045810, "TSLA": 1318605,
    "AMZN": 1018724, "GOOGL": 1652044, "META": 1326801, "PLTR": 1321655,
}

def get_json(url, ua=UA, timeout=25):
    req = Request(url, headers={"User-Agent":ua, "Accept":"application/json"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def clamp(n,a,b): return max(a,min(b,n))

def rsi14(closes):
    if len(closes) < 15: return None
    seq = closes[-15:]
    gains=[]; losses=[]
    for a,b in zip(seq[:-1],seq[1:]):
        d=b-a; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/14; al=sum(losses)/14
    if al == 0: return 100.0
    return 100 - 100/(1+ag/al)

def volatility20(closes):
    if len(closes) < 3: return None
    rs=[(b/a-1)*100 for a,b in zip(closes[-21:-1],closes[-20:]) if a]
    return statistics.pstdev(rs) if len(rs)>1 else 0.0

def score_row(change,mom5,vol_ratio,sma20,rsi):
    score=45
    score += clamp(change*3.0,-15,18)
    score += clamp(mom5*1.4,-10,16)
    score += clamp((vol_ratio-1)*9,-5,12)
    score += clamp(sma20*0.8,-6,8)
    if rsi is not None and rsi > 75: score -= 5
    if rsi is not None and rsi < 30: score -= 2
    return round(clamp(score,0,100),1)

def yahoo_chart(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range=1y&interval=1d&includePrePost=false&events=div%2Csplits"
    data=get_json(url)
    result=(data.get("chart",{}).get("result") or [None])[0]
    if not result: raise RuntimeError("Yahoo returned no chart result")
    meta=result.get("meta",{})
    q=((result.get("indicators",{}).get("quote") or [{}])[0])
    timestamps=result.get("timestamp") or []
    closes=q.get("close") or []; volumes=q.get("volume") or []
    rows=[]
    for ts,c,v in zip(timestamps,closes,volumes):
        if c is not None:
            rows.append((ts,float(c),float(v or 0)))
    if len(rows)<21: raise RuntimeError("Not enough Yahoo history")
    cs=[r[1] for r in rows]; vs=[r[2] for r in rows]
    price=float(meta.get("regularMarketPrice") or cs[-1])
    prev=float(cs[-2])
    change=(price/prev-1)*100 if prev else 0
    mom5=(price/cs[-6]-1)*100 if cs[-6] else 0
    avgvol=sum(vs[-21:-1])/max(1,len(vs[-21:-1]))
    vr=(vs[-1]/avgvol) if avgvol else 1
    sma=sum(cs[-20:])/20; sma20=(price/sma-1)*100 if sma else 0
    high90=max(cs[-90:]); high90pct=(price/high90-1)*100 if high90 else 0
    rsi=rsi14(cs); vola=volatility20(cs)
    history=[{"date":datetime.fromtimestamp(ts,timezone.utc).strftime("%Y-%m-%d"),"close":round(close,4)} for ts,close,_ in rows]
    return {
        "ticker":ticker,
        "name":meta.get("longName") or meta.get("shortName") or ticker,
        "currency":meta.get("currency"), "exchange":meta.get("exchangeName") or meta.get("fullExchangeName"),
        "price":round(price,4), "previousClose":round(prev,4), "change":round(change,2),
        "mom5":round(mom5,2), "volRatio":round(vr,2), "rsi":round(rsi,1) if rsi is not None else None,
        "sma20":round(sma20,2), "volatility":round(vola,2) if vola is not None else None,
        "high90":round(high90pct,2), "history":history,
        "timestamp":datetime.fromtimestamp(rows[-1][0],timezone.utc).isoformat(),
        "source":"Yahoo Finance chart data", "sourceUrl":f"https://finance.yahoo.com/quote/{quote(ticker)}"
    }

def latest_fact(facts, concepts, unit):
    us=facts.get("facts",{}).get("us-gaap",{})
    rows=[]
    for c in concepts:
        for x in us.get(c,{}).get("units",{}).get(unit,[]):
            if x.get("val") is not None and x.get("filed"):
                rows.append((x.get("filed"),x.get("end") or "",x.get("val"),c,x.get("form")))
    if not rows: return None
    filed,end,val,c,form=sorted(rows, reverse=True)[0]
    return {"value":val,"filed":filed,"end":end,"form":form,"concept":c}

def sec_company(cik):
    cik10=f"{cik:010d}"
    sub=get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    rec=sub.get("filings",{}).get("recent",{})
    forms=rec.get("form",[]); dates=rec.get("filingDate",[]); accs=rec.get("accessionNumber",[]); docs=rec.get("primaryDocument",[])
    filing=None
    for wanted in ("10-Q","10-K","8-K"):
        for i,form in enumerate(forms):
            if form==wanted:
                accession=accs[i].replace("-","")
                filing={"form":form,"date":dates[i],"url":f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{docs[i]}"}
                break
        if filing: break
    facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json")
    return {
        "source":"SEC EDGAR", "sourceUrl":f"https://www.sec.gov/edgar/browse/?CIK={cik}&owner=exclude",
        "latestFiling":filing,
        "revenue":latest_fact(facts,["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"],"USD"),
        "netIncome":latest_fact(facts,["NetIncomeLoss","ProfitLoss"],"USD"),
        "assets":latest_fact(facts,["Assets"],"USD"), "liabilities":latest_fact(facts,["Liabilities"],"USD"),
        "eps":latest_fact(facts,["EarningsPerShareDiluted","EarningsPerShareBasic"],"USD/shares")
    }

def main():
    generated=datetime.now(timezone.utc).isoformat(); stocks=[]; errors=[]
    for item in SYMBOLS:
        t=item["ticker"]
        try:
            y=yahoo_chart(t); y["market"]=item["market"]
            y["score"]=score_row(y["change"],y["mom5"],y["volRatio"],y["sma20"],y["rsi"])
            if item["market"]=="US" and t in CIKS:
                try: y["official"]=sec_company(CIKS[t])
                except Exception as e:
                    y["official"]={"source":"SEC EDGAR unavailable this run","sourceUrl":f"https://www.sec.gov/edgar/browse/?CIK={CIKS[t]}&owner=exclude"}
                    errors.append({"ticker":t,"source":"SEC","error":str(e)})
            elif item["market"]=="US":
                y["official"]={"source":"SEC EDGAR link","sourceUrl":"https://www.sec.gov/edgar/search/"}
            else:
                y["official"]={"source":"UK official sources","lseUrl":"https://www.londonstockexchange.com/","companiesHouseUrl":"https://find-and-update.company-information.service.gov.uk/"}
            stocks.append(y)
        except Exception as e:
            errors.append({"ticker":t,"source":"Yahoo","error":str(e)})
        time.sleep(0.25)
    stocks.sort(key=lambda x:x.get("change",0),reverse=True)
    payload={"generatedAt":generated,"keyless":True,"universeSize":len(SYMBOLS),"providers":[{"name":"Yahoo Finance","type":"market prices/history","authentication":"none","note":"Unofficial endpoint; may change or rate-limit."},{"name":"SEC EDGAR","type":"US primary filings/XBRL facts","authentication":"none","note":"Official SEC public data."}],"stocks":stocks,"errors":errors}
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,indent=2,ensure_ascii=False)
    print(f"wrote {len(stocks)} of {len(SYMBOLS)} stocks, {len(errors)} errors")

if __name__=="__main__": main()
