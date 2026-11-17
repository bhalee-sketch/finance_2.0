import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest
from unittest.mock import patch
from contextlib import ExitStack
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from finance_data import LEDGER_COLUMNS
from ledger_view import open_ledger


class LedgerViewTests(unittest.TestCase):
    def test_explicit_query_continuous_scroll_period_and_last_total(self):
        root=q.Tk();errors=[];root.report_callback_exception=lambda *args:errors.append(str(args))
        records=[]
        for row in range(850):
            record=dict.fromkeys(LEDGER_COLUMNS,'')
            record.update(년도='2025',회계일자='2025-03-01' if row%2 else '2025-04-01',회계단위='교비',관='지출',항='관리비',목='소모품비',차변=Decimal('10.25'),대변=Decimal('2'),적요=f'검색 {row}')
            records.append(record)
        def wait(predicate):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                q.application().processEvents()
                if errors:self.fail(str(errors))
                if predicate():return
                time.sleep(.01)
            self.fail('Timed out')
        try:
            with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
                stack.enter_context(patch('ledger_database.discover_years',return_value={'2025':Path(folder)/'ledger.sqlite3'}))
                stack.enter_context(patch('analysis_runtime.load_program_ledger',return_value=records))
                stack.enter_context(patch('analysis_runtime.program_statement_paths',return_value={'2025':Path(folder)/'finance statement'/'2025.xlsx'}))
                stack.enter_context(patch('audit_review.load_statement_history',return_value=({},[],{})))
                window=open_ledger(root,lambda:Path(folder),lambda w,x,y:w.geometry(f'{x}x{y}'),lambda p:None)
                wait(lambda:window._work_status.get().startswith('원장 준비 완료'))
                model=window._ledger_model;view=window._ledger_table
                self.assertEqual(model.rowCount(),0)
                buttons={button.text():button for button in window._q.findChildren(q.W.QPushButton)}
                self.assertNotIn('이전',buttons);self.assertNotIn('다음',buttons)
                buttons['조회'].click();wait(lambda:model.rowCount()==851)
                self.assertEqual(model.index(850,0).data(),'전체 합계')
                debit=model.columns.index('차변')
                self.assertEqual(model.index(850,debit).data(q.C.Qt.ItemDataRole.UserRole),Decimal('8712.50'))
                view.scrollToBottom();q.application().processEvents()
                self.assertGreaterEqual(view.rowAt(0),300)
                start,end=window._ledger_dates
                self.assertTrue(start.calendarPopup());self.assertTrue(end.calendarPopup())
                from PySide6.QtTest import QTest
                start.lineEdit().setFocus();QTest.keyClicks(start.lineEdit(),'20250301');start.interpretText()
                end.lineEdit().setText('20250331');end.interpretText()
                self.assertEqual(start.value(),'2025-03-01');self.assertEqual(end.value(),'2025-03-31')
                buttons['조회'].click();wait(lambda:model.rowCount()==426)
                self.assertEqual(len(model.records),425)
                query=next(entry for entry in window._q.findChildren(q.W.QLineEdit) if entry.accessibleName()=='거래선·적요 등')
                label=next(label for label in window._q.findChildren(q.W.QLabel) if label.text()=='거래선·적요 등')
                self.assertLessEqual(abs(query.mapToGlobal(query.rect().center()).y()-label.mapToGlobal(label.rect().center()).y()),2)
                buttons['조건 초기화'].click();wait(lambda:model.rowCount()==0)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
