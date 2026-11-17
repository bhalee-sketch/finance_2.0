import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from appearance import set_appearance
from statement_grid import StatementGrid

class StatementNumberTests(unittest.TestCase):
    def test_long_bold_amounts_stay_single_line_at_all_text_sizes(self):
        root=q.Tk();root.geometry('1000x600')
        try:
            tree=StatementGrid(root,columns=['0','1','2'],show='headings');tree.pack(fill='both',expand=True)
            tree.column('0',anchor='w');tree.column('1',anchor='e');tree.column('2',anchor='e')
            tree.tag_configure('total',font=('sans-serif',10,'bold'))
            tree.insert('','end',values=['총계','33,988,234,000','-1,157,387,280'],tags=('total',))
            tree.insert('','end',values=['일반','0','97.60'])
            for scale in (80,110,150):
                set_appearance(root,'light',q.font.families()[0],numeric_font='sans-serif',text_scale=scale)
                q.application().processEvents()
                tree.fit_to_viewport({'0':300,'1':110,'2':110},0)
                for col in (1,2):
                    index=tree.proxy.index(0,col)
                    font=index.data(q.C.Qt.ItemDataRole.FontRole)
                    metrics=q.G.QFontMetrics(font)
                    self.assertGreaterEqual(tree._q.columnWidth(col),metrics.horizontalAdvance(index.data())+18)
                    option=q.W.QStyleOptionViewItem();option.initFrom(tree._q)
                    hint=tree._q.itemDelegate().sizeHint(option,index)
                    self.assertLessEqual(hint.height(),max(tree._q.verticalHeader().defaultSectionSize(),metrics.height()+7))
                before=[tree._q.columnWidth(i) for i in range(3)]
                root.geometry('1400x650');q.application().processEvents()
                tree.fit_to_viewport({'0':300,'1':110,'2':110},0)
                self.assertEqual(before,[tree._q.columnWidth(i) for i in range(3)])
        finally:root.destroy()

if __name__=='__main__':unittest.main()
