from pathlib import Path
import sys,tempfile,unittest,sqlite3,zlib,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
from decimal import Decimal
from ledger_database import import_ledger,discover_years,load_records
from finance_data import LEDGER_COLUMNS,ledger_totals

class LedgerDatabaseTests(unittest.TestCase):
    def test_roundtrip_repeat_and_original_independence(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'2025.xlsx';db=folder/'ledger.sqlite3'
            b=Workbook();b.active.append(LEDGER_COLUMNS+['계정코드','세목'])
            for amount in ('1234.25','-12.5'):
                r=dict.fromkeys(LEDGER_COLUMNS,'');r.update(년도='2025',회계일자='20250301',차변=amount,대변='20.01')
                b.active.append([r[c] for c in LEDGER_COLUMNS]+['00123','세부계정'])
            b.save(source);b.close()
            first=import_ledger(source,'2025',db)
            self.assertEqual(first,import_ledger(source,'2025',db))
            with sqlite3.connect(db) as c:
                raw=c.execute('select raw_json from entries order by source_row').fetchone()[0]
                self.assertEqual(json.loads(zlib.decompress(raw))[-2:],['00123','세부계정'])
            source.unlink()
            self.assertEqual(list(discover_years(db)),['2025'])
            records=load_records(db,'2025')
            self.assertEqual(len(records),2)
            self.assertEqual(ledger_totals(records),{'차변':Decimal('1221.75'),'대변':Decimal('40.02')})
            b=Workbook();b.save(source);b.close()
            with self.assertRaises(ValueError):import_ledger(source,'2025',db)
            self.assertEqual(len(load_records(db,'2025')),2)

if __name__=='__main__':unittest.main()
