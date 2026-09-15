import copy
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('market', Path(__file__).resolve().parents[1] / 'scripts/fetch_market_data.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    times = [int((now-timedelta(days=79-i)).timestamp()) for i in range(80)]
    item = {'ticker':'TEST.L','lseCode':'TEST','nameHint':'Test'}
    response = {'meta':{'symbol':'TEST.L','currency':'GBp','regularMarketPrice':100,'regularMarketTime':times[-1]},
                'timestamp':times,'indicators':{'quote':[{'close':[100.0]*80,'volume':[1000]*80}]}}
    return response, item, now.date().isoformat()


class MarketTests(unittest.TestCase):
    def test_sidebar_is_not_a_constituent(self):
        page = '''<a href="/shareprice.asp?shareprice=OMI">Orosur</a>
          <tr id="ls-row-BP.-L"><td>BP.</td><td><a data-s-name="BP &amp; Co">BP</a></td></tr>'''
        self.assertEqual(m.parse_constituent_page(page), [{'ticker':'BP.L','lseCode':'BP.','nameHint':'BP & Co'}])

    def test_changed_parser_fails_closed(self):
        with self.assertRaises(ValueError): m.parse_constituent_page('<a href="?shareprice=PPP">PPP</a>')
        with self.assertRaises(ValueError): m.parse_constituent_page('<tr id="ls-row-BP.-L"><td>WRONG</td><td data-s-name="BP"></td></tr>')

    def test_neutral_flat_rsi_and_real_zero_volume(self):
        r,i,d = fixture(); r['indicators']['quote'][0]['volume'][-1] = 0
        s = m.parse_yahoo_response(r,i,d)
        self.assertEqual(s['rsi'],50)
        self.assertEqual(s['volRatio'],0)
        self.assertEqual(s['change'],0)
        self.assertEqual(s['price'],s['history'][-1]['close'])

    def test_hundredfold_quote_rejected(self):
        r,i,d = fixture(); r['meta']['regularMarketPrice']=10000
        with self.assertRaisesRegex(ValueError,'units'): m.parse_yahoo_response(r,i,d)

    def test_mixed_history_units_rejected(self):
        r,i,d = fixture(); r['indicators']['quote'][0]['close'][30]=1
        with self.assertRaisesRegex(ValueError,'discontinuity'): m.parse_yahoo_response(r,i,d)

    def test_stale_history_and_quote_rejected(self):
        r,i,d = fixture()
        with self.assertRaisesRegex(ValueError,'Stale history'): m.parse_yahoo_response(r,i,'2099-01-01')
        r['meta']['regularMarketTime']-=86400
        with self.assertRaisesRegex(ValueError,'Stale quote'): m.parse_yahoo_response(r,i,d)

    def test_missing_volume_nan_duplicate_and_symbol(self):
        for kind in ['volume','nan','date','symbol']:
            r,i,d=fixture()
            if kind=='volume': r['indicators']['quote'][0].pop('volume')
            if kind=='nan': r['indicators']['quote'][0]['close'][20]=float('nan')
            if kind=='date': r['timestamp'][-1]=r['timestamp'][-2]
            if kind=='symbol': r['meta']['symbol']='WRONG.L'
            with self.subTest(kind=kind), self.assertRaises(ValueError): m.parse_yahoo_response(r,i,d)

    def test_same_series_used_for_changes(self):
        r,i,d=fixture();r['meta']['regularMarketPrice']=102
        s=m.parse_yahoo_response(r,i,d)
        self.assertEqual(s['price'],100)
        self.assertEqual(s['change'],0)

    def test_pagination_and_duplicate_page_protection(self):
        def row(code): return f'<tr id="ls-row-{code}-L"><td>{code}</td><td data-s-name="{code}"></td></tr>'
        codes=['HSBA','SHEL','AZN','III']+[f'T{i}' for i in range(450)]
        first=''.join(map(row,codes[:227]))+'<a href="?page=2">2</a>'
        second=''.join(map(row,codes[227:]))
        with TemporaryDirectory() as temp, patch.object(m,'OUT',Path(temp)/'absent.json'):
            with patch.object(m,'get_text',side_effect=[first,second]) as get:
                rows,meta=m.fetch_ftse_all_share_universe()
                self.assertEqual(len(rows),454);self.assertEqual(get.call_count,2)
            with patch.object(m,'get_text',side_effect=[first,first]):
                with self.assertRaisesRegex(ValueError,'Repeated'):m.fetch_ftse_all_share_universe()

    def test_coverage_gate(self):
        r,i,d=fixture();row=m.parse_yahoo_response(r,i,d);row['rank']=1
        payload={'stocks':[row],'constituents':[i,{'ticker':'MISSING.L'}],
                 'errors':[{'ticker':'MISSING.L','error':'stale'}],'analysedCount':1,'universeSize':2,'marketSession':d}
        with self.assertRaisesRegex(ValueError,'Only'):m.validate_payload(payload)
        payload.update(constituents=[i],errors=[],universeSize=1)
        m.validate_payload(payload)
        payload['stocks'][0]['price']=1
        with self.assertRaisesRegex(ValueError,'mismatch'):m.validate_payload(payload)

    def test_failure_preserves_previous_snapshot(self):
        with TemporaryDirectory() as temp:
            out=Path(temp)/'market.json';status=Path(temp)/'status.json'
            old='{"generatedAt":"previous","stocks":[1]}';out.write_text(old)
            with patch.object(m,'OUT',out),patch.object(m,'STATUS',status),patch.object(m,'fetch_ftse_all_share_universe',side_effect=ValueError('provider failure')):
                with self.assertRaises(ValueError):m.main()
            self.assertEqual(out.read_text(),old)
            self.assertEqual(m.json.loads(status.read_text())['state'],'failed')

if __name__=='__main__':unittest.main()
