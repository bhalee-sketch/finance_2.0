import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from datetime import date
from suspense_data import Transaction


def tx(number,side,value):
    return Transaction(str(number),number+1,'원장',str(number),date(2025,6,1),'담당부서','거래처',
                       value if side=='D' else 0,value if side=='C' else 0,'정산 내역','계좌','교비',())


def ledger(rows):
    return {'rows':rows,'hash':'testhash','sheet':'원장','path':'test.xlsx','headers':[],'raw_rows':[],'excluded':[]}

from suspense_engine import validate
from suspense_manual import open_match,apply_manual_match
from suspense_ui import open_suspense

class SuspenseMatchingTests(unittest.TestCase):
    def test_select_balances_and_match_with_visible_top_action(self):
        root=q.Tk();root.geometry('1200x800')
        rows=[tx(1,'D',100),tx(2,'C',150)]
        result={'ledger':ledger(rows),'groups':[],'validation':validate(rows,[]),'history':[]}
        saved=[]
        try:
            dialog=open_match(root,result,{},lambda w,x,y:w.geometry(f'{x}x{y}'),lambda settings:saved.append(apply_manual_match(result,settings)))
            q.application().processEvents()
            buttons=dialog._q.findChildren(q.W.QPushButton)
            self.assertEqual({b.text() for b in buttons},{'매칭하기','취소'})
            match=next(b for b in buttons if b.text()=='매칭하기')
            self.assertFalse(match.isEnabled())
            for side,tree in dialog._match_trees.items():
                self.assertEqual(list(tree['columns']),['선택','회계일자','부서','거래선','잔액'])
                self.assertEqual(tree._q.horizontalScrollBarPolicy(),q.C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                check=tree._q.findChild(q.W.QCheckBox)
                self.assertIsNotNone(check);check.setChecked(True)
                self.assertIn('22px',check.styleSheet())
            self.assertTrue(match.isEnabled())
            self.assertIn('매칭 후 잔액 50원',dialog._match_totals.get())
            self.assertLess(match.mapToGlobal(q.C.QPoint()).y(),dialog._match_trees['D']._q.mapToGlobal(q.C.QPoint()).y())
            match.click()
            self.assertFalse(dialog.winfo_exists())
            self.assertTrue(saved[0]['validation']['ok'])
            self.assertEqual(saved[0]['validation']['residual']['2'],(0,50))
        finally:root.destroy()

    def test_main_actions_share_filter_row_and_no_stop(self):
        root=q.Tk()
        try:
            with tempfile.TemporaryDirectory() as folder:
                open_suspense(root,lambda:Path(folder),lambda w,x,y:w.geometry(f'{x}x{y}'),lambda *a:None)
                q.application().processEvents()
                window=next(w for w in root.children.values() if isinstance(w,q.Toplevel))
                buttons={b.text():b for b in window._q.findChildren(q.W.QPushButton)}
                self.assertNotIn('중단',buttons)
                residual=next(widget for widget in q._registry.values()
                              if hasattr(widget,'_columns') and '거래처코드' in widget._columns
                              and window._q.isAncestorOf(widget._q))
                self.assertNotIn('거래처코드',residual['displaycolumns'])
                for text in ['매칭내역 보기','현재화면 엑셀열기']:
                    self.assertIs(buttons[text].parent(),buttons['검색 초기화'].parent())
        finally:root.destroy()

if __name__=='__main__':unittest.main()
