import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from statement_ui import table
from suspense_ui import fit_residual_columns,RESIDUAL_COLUMNS

class SuspenseColumnTests(unittest.TestCase):
    def test_reference_order_proportions_and_content_independence(self):
        root=q.Tk();root.geometry('1400x650')
        try:
            tree=table(root,('거래처코드',*RESIDUAL_COLUMNS))
            q.application().processEvents();fit_residual_columns(tree)
            before=[tree._q.columnWidth(i) for i in range(len(RESIDUAL_COLUMNS))]
            self.assertEqual(tree._visible_columns(),list(RESIDUAL_COLUMNS))
            self.assertNotIn('거래처코드',tree._visible_columns())
            self.assertGreater(before[6],2*before[5])
            self.assertGreater(before[10],before[7])
            self.assertEqual(sum(before),tree._q.viewport().width())
            tree.insert('','end',values=['0001',*['아주 긴 거래처와 적요 '*20]*len(RESIDUAL_COLUMNS)])
            fit_residual_columns(tree)
            self.assertEqual(before,[tree._q.columnWidth(i) for i in range(len(RESIDUAL_COLUMNS))])
            header=tree._q.horizontalHeader()
            self.assertFalse(header.sectionsMovable())
            self.assertTrue(all(header.sectionResizeMode(i)==q.W.QHeaderView.ResizeMode.Fixed for i in range(header.count())))
        finally:root.destroy()

if __name__=='__main__':unittest.main()
