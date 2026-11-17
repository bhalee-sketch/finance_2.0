import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from statement_ui import table
from suspense_table import configure_detail_table
from suspense_ui import residual_amount_totals

class DetailTableTests(unittest.TestCase):
    def test_filtered_amount_sums(self):
        items=[{'values':('',)*8+('1,500','500','1,000','')},
               {'values':('',)*8+('0','300','-300','')}]
        self.assertEqual(residual_amount_totals(items),(1500,800,700))
        self.assertEqual(residual_amount_totals(items[:1]),(1500,500,1000))
        self.assertEqual(residual_amount_totals([]),(0,0,0))

    def test_scroll_stops_at_last_data_row_and_grid_stays_visible(self):
        root=q.Tk();root.geometry('900x400')
        try:
            tree=table(root,['일자','거래선','잔액'])
            configure_detail_table(tree)
            for i in range(100):tree.insert('','end',values=['2025-06-01',f'거래처 {i}',i])
            q.application().processEvents();tree.refresh_numbers();q.application().processEvents()
            bar=tree._q.verticalScrollBar();bar.setValue(bar.maximum());q.application().processEvents()
            last=tree._q.visualRect(tree.proxy.index(99,0))
            self.assertLessEqual(abs(last.bottom()-(tree._q.viewport().height()-1)),2)
            self.assertTrue(tree._q.showGrid())
            self.assertIn('#C8BFD7',tree._q.styleSheet())
            self.assertLessEqual(bar.maximum(),tree._q.verticalHeader().length()-tree._q.viewport().height())
        finally:root.destroy()

if __name__=='__main__':unittest.main()
