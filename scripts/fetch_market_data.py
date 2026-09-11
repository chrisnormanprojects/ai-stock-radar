#!/usr/bin/env python3
import json, math, os, statistics, time
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "market.json")
UA = "AIStockRadar/2.0 (+https://github.com/chrisnormanprojects/ai-stock-radar; chrisnormanprojects@users.noreply.github.com)"

SYMBOLS = [
    {"ticker":"NVDA","market":"US"}, {"ticker":"PLTR","market":"US"},
    {"ticker":"AAPL","market":"US"}, {"ticker":"MSFT","market":"US"},
    {"ticker":"AMZN","market":"US"}, {"ticker":"GOOGL","market":"US"},
    {"ticker":"META","market":"US"}, {"ticker":"TSLA","market":"US"},
    {"ticker":"RR.L","market":"UK"}, {"ticker":"VOD.L","market":"UK"},
    {"ticker":"SHEL.L","market":"UK"}, {"ticker":"LLOY.L","market":"UK"},
    {"ticker":"BARC.L","market":"UK"}, {"ticker":"IAG.L","market":"UK"}
]

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
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range=6mo&interval=1d&includePrePost=false&events=div%2Csplits"
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
    if len(rows)<6: raise RuntimeError("Not enough Yahoo history")
    cs=[r[1] for r in rows]; vs=[r[2] for r in rows]
    price=float(meta.get("regularMarketPrice") or cs[-1])
    prev=float(meta.get("chartPreviousClose") or (cs[-2] if len(cs)>1 else price))
    change=(price/prev-1)*100 if prev else 0
    mom5=(price/cs[-6]-1)*100 if len(cs)>=6 and cs[-6] else 0
    avgvol=sum(vs[-21:-1])/max(1,len(vs[-21:-1]))
    vr=(vs[-1]/avgvol) if avgvol else 1
    sma=sum(cs[-20:])/min(20,len(cs)); sma20=(price/sma-1)*100 if sma else 0
    high90=max(cs[-90:]); high90pct=(price/high90-1)*100 if high90 else 0
    rsi=rsi14(cs); vola=volatility20(cs)
    return {
        "ticker":ticker,
        "name":meta.get("longName") or meta.get("shortName") or ticker,
        "currency":meta.get("currency"), "exchange":meta.get("exchangeName") or meta.get("fullExchangeName"),
        "price":round(price,4), "previousClose":round(prev,4), "change":round(change,2),
        "mom5":round(mom5,2), "volRatio":round(vr,2), "rsi":round(rsi,1) if rsi is not None else None,
        "sma20":round(sma20,2), "volatility":round(vola,2) if vola is not None else None,
        "high90":round(high90pct,2), "timestamp":datetime.fromtimestamp(rows[-1][0],timezone.utc).isoformat(),
        "source":"Yahoo Finance chart data", "sourceUrl":f"https://finance.yahoo.com/quote/{quote(ticker)}"
    }

def cik_map():
    data=get_json("https://www.sec.gov/files/company_tickers.json")
    out={}
    for item in data.values(): out[item.get("ticker","").upper()]=int(item["cik_str"])
    return out

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

def sec_company(ticker,cik):
    cik10=f"{cik:010d}"
    sub=get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    rec=sub.get("filings",{}).get("recent",{})
    forms=rec.get("form",[]); dates=rec.get("filingDate",[]); accs=rec.get("accessionNumber",[]); docs=rec.get("primaryDocument",[])
    filing=None
    preferred=("10-Q","10-K","8-K")
    for wanted in preferred:
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
        "assets":latest_fact(facts,["Assets"],"USD"),
        "liabilities":latest_fact(facts,["Liabilities"],"USD"),
        "eps":latest_fact(facts,["EarningsPerShareDiluted","EarningsPerShareBasic"],"USD/shares")
    }

def main():
    generated=datetime.now(timezone.utc).isoformat()
    cmap={}
    try: cmap=cik_map()
    except Exception as e: print("SEC ticker map failed:",e)
    stocks=[]; errors=[]
    for item in SYMBOLS:
        t=item["ticker"]
        try:
            y=yahoo_chart(t); y["market"]=item["market"]
            y["score"]=score_row(y["change"],y["mom5"],y["volRatio"],y["sma20"],y["rsi"])
            if item["market"]=="US" and t in cmap:
                try: y["official"]=sec_company(t,cmap[t])
                except Exception as e: errors.append({"ticker":t,"source":"SEC","error":str(e)})
            else:
                y["official"]={"source":"UK official sources","lseUrl":"https://www.londonstockexchange.com/","companiesHouseUrl":"https://find-and-update.company-information.service.gov.uk/"}
            stocks.append(y)
        except Exception as e:
            errors.append({"ticker":t,"source":"Yahoo","error":str(e)})
        time.sleep(0.25)
    stocks.sort(key=lambda x:x.get("score",0),reverse=True)
    payload={
        "generatedAt":generated,
        "keyless":True,
        "providers":[
            {"name":"Yahoo Finance","type":"market prices/history","authentication":"none","note":"Unofficial endpoint; may change or rate-limit."},
            {"name":"SEC EDGAR","type":"US primary filings/XBRL facts","authentication":"none","note":"Official SEC public data."}
        ],
        "stocks":stocks,"errors":errors
    }
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,indent=2,ensure_ascii=False)
    print(f"wrote {len(stocks)} stocks, {len(errors)} errors")

if __name__=="__main__": main()
