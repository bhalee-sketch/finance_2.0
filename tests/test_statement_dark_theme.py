import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from appearance import set_appearance
from statement_grid import StatementGrid,ROW_COLORS,DARK_ROW_COLORS

class StatementDarkTests(unittest.TestCase):
    def test_semantic_row_colors_and_text_follow_theme(self):
        root=q.Tk()
        try:
            tree=StatementGrid(root,columns=['0','1']);tree.pack()
            for tag,color in ROW_COLORS.items():
                tree.tag_configure(tag,background=color,foreground='#172638')
                tree.insert('','end',values=[tag,'1,234'],tags=(tag,))
            for theme in ('light','dark','light'):
                set_appearance(root,theme,q.font.families()[0]);q.application().processEvents()
                for row,(tag,color) in enumerate(ROW_COLORS.items()):
                    index=tree.proxy.index(row,0)
                    background=index.data(q.C.Qt.ItemDataRole.BackgroundRole).name()
                    foreground=index.data(q.C.Qt.ItemDataRole.ForegroundRole).name()
                    self.assertEqual(background,(DARK_ROW_COLORS[color] if theme=='dark' else color).lower())
                    self.assertEqual(foreground,'#eae5f4' if theme=='dark' else '#172638')
                self.assertIn('#231F30' if theme=='dark' else '#FFFFFF',tree._q.styleSheet())
        finally:root.destroy()

if __name__=='__main__':unittest.main()
