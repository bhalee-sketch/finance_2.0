import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,tempfile,unittest
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from openpyxl import Workbook,load_workbook
from statement_ui import open_statement_verify
from finance_ui import open_ledger
from finance_data import LEDGER_COLUMNS

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        self.root=q.Tk();self.errors=[];self.opened=[];self.stack=ExitStack()
        self.root.report_callback_exception=lambda *a:self.errors.append(str(a))
        self.stack.enter_context(patch.object(q.messagebox,'showerror',side_effect=lambda *a,**k:self.errors.append(str(a))))
        self.stack.enter_context(patch('statement_ui.output_path',return_value=self.folder/'result.xlsx'))
        self.stack.enter_context(patch('ledger_cache.cache_folder',return_value=self.folder/'cache'))
    def tearDown(self):
        self.root.destroy();self.stack.close();self.tmp.cleanup()
    def window(self):
        return next(w for w in self.root.children.values() if isinstance(w,q.Toplevel))
    def wait(self,predicate):
        end=time.monotonic()+20
        while time.monotonic()<end:
            q.application().processEvents()
            if self.errors:self.fail(str(self.errors))
            if predicate():return
            time.sleep(.01)
        self.fail('Timed out')
    def click(self,w,text):
        next(b for b in w._q.findChildren(q.W.QPushButton) if b.text()==text).click()
    def test_appendix_database_verification(self):
        with patch('statement_catalog.discover_years',side_effect=AssertionError('External discovery')):
            open_statement_verify(self.root,lambda:self.folder,lambda *a:None,self.opened.append,True)
            w=self.window()
            self.wait(lambda:'저장 자료를 연결' in w._work_status.get())
            self.click(w,'검증 · 결과 저장')
            self.wait(lambda:bool(self.opened))
        book=load_workbook(self.opened[0]);self.assertGreater(book.active.max_row,10)
        results=[r[5].value for r in list(book.active)[1:]]
        self.assertTrue(set(results)<={'일치','차이','확인필요'})
        print('Appendix results:',{s:results.count(s) for s in set(results)})
        book.close()
    def test_combined_verification(self):
        files=[]
        for name,values in [('combined',[['현금',None,100]]),('school',[['현금']+[None]*7+[100]])]:
            p=self.folder/(name+'.xlsx');b=Workbook()
            for row in values:b.active.append(row)
            b.save(p);b.close();files.append(str(p))
        open_statement_verify(self.root,lambda:self.folder,lambda *a:None,self.opened.append)
        w=self.window();buttons=[b for b in w._q.findChildren(q.W.QPushButton) if b.text()=='선택']
        for button,path in zip(buttons,files):
            with patch.object(q.filedialog,'askopenfilename',return_value=path):button.click()
        self.click(w,'검증 · 결과 저장');self.wait(lambda:bool(self.opened))
        self.assertIn('일치 1건',w._work_status.get())
    def test_ledger_file_selection(self):
        p=self.folder/'2025원장.xlsx';b=Workbook();s=b.active;s.append(LEDGER_COLUMNS)
        record=dict.fromkeys(LEDGER_COLUMNS,'');record.update(년도='2025',회계일자='20250301',차변=1234,대변=0,적요='거래 검증')
        s.append([record[k] for k in LEDGER_COLUMNS]);b.save(p);b.close()
        with patch('ledger_database.discover_years',return_value={}):
            open_ledger(self.root,lambda:self.folder,lambda *a:None,lambda *a:None)
            w=self.window();self.wait(lambda:'저장된 원장 없음' in [x.text() for x in w._q.findChildren(q.W.QLabel)])
        with patch.object(q.filedialog,'askopenfilename',return_value=str(p)):
            self.click(w,'원장 파일 선택')
        self.wait(lambda:w._work_status.get().startswith('조회 완료'))
        labels=[x.text() for x in w._q.findChildren(q.W.QLabel)]
        self.assertTrue(any('차변 1,234원' in x and '1건' in x for x in labels),labels)

if __name__=='__main__':unittest.main()
