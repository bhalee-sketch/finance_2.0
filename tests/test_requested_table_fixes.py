import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from PySide6.QtTest import QTest
from deposit_ui import open_deposit
from appendix_view import open_appendix_view,SOURCES,list_sheets
from appendix_data import load_sheet
from appendix_model import display_value
from appearance import set_appearance


class TableFixTests(unittest.TestCase):
    def setUp(self):
        self.root=q.Tk();self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(str(args))
    def tearDown(self):self.root.destroy()
    def wait(self,predicate):
        end=time.monotonic()+15
        while time.monotonic()<end:
            q.application().processEvents()
            if self.errors:self.fail(str(self.errors))
            if predicate():return
            time.sleep(.01)
        self.fail('Timed out')

    def test_deposit_dropdowns_search_selection_focus_and_return(self):
        with tempfile.TemporaryDirectory() as folder:
            opened=[]
            from deposit_accounts import store_accounts
            interest_db=Path(folder)/'settings'/'deposit plan'/'interest_accounts.sqlite3'
            store_accounts(interest_db,{'00099':{'account':'000-99','bank':'테스트은행','name':'이자 계좌'}},'테스트')
            open_deposit(self.root,lambda:Path(folder),lambda w,x,y:w.geometry(f'{x}x{y}'),opened.append)
            window=next(w for w in self.root.children.values() if isinstance(w,q.Toplevel))
            self.wait(lambda:any('정기 75개' in label.text() for label in window._q.findChildren(q.W.QLabel)))
            boxes={b.accessibleName():b for b in window._q.findChildren(q.W.QComboBox) if b.accessibleName()}
            check=next(w for w in window._q.findChildren(q.W.QCheckBox) if w.text()=='이자 별도 이체')
            check.setChecked(True)
            expected={'출금할 정기예금 계좌':75,'원금 이체 계좌':42,'이자 이체 계좌':1}
            for name,count in expected.items():
                box=boxes[name];box.showPopup();self.assertEqual(box.count(),count);box.hidePopup()
                box.setCurrentIndex(0);box.activated.emit(0)
                # Focus loss must never require a keyboard-only attribute.
                q.application().sendEvent(box,q.G.QFocusEvent(q.C.QEvent.Type.FocusOut))
                self.assertFalse(self.errors)
            fixed=boxes['출금할 정기예금 계좌'];label=fixed.itemText(0)
            fixed.lineEdit().setFocus();fixed.lineEdit().selectAll()
            account=label.split(' · ')[0]
            QTest.keyClicks(fixed.lineEdit(),account)
            QTest.keyClick(fixed.lineEdit(),q.C.Qt.Key.Key_Return)
            self.assertEqual(fixed.currentText(),label)
            self.assertTrue(any('원금:' in label.text() for label in window._q.findChildren(q.W.QLabel)))
            fields={entry.accessibleName():entry for entry in window._q.findChildren(q.W.QLineEdit) if entry.accessibleName()}
            for field in ('세전이자','법인세','지방소득세'):fields[field].setText('0')
            buttons={button.text():button for button in window._q.findChildren(q.W.QPushButton)}
            with patch('result_paths.desktop_dir',return_value=Path(folder)):
                buttons['목록에 추가  →'].click()
                buttons['계획표 생성'].click()
                self.wait(lambda:bool(opened))
            self.assertEqual(len(opened),1)
            self.assertTrue(Path(opened[0]).is_file())
            # A non-matching value followed by Tab was the reported crash.
            fixed.setEditText('no matching account')
            q.application().sendEvent(fixed,q.G.QFocusEvent(q.C.QEvent.Type.FocusOut))
            self.assertFalse(self.errors)

    def test_tab_overflow_navigation_and_close(self):
        from launcher import Launcher
        def workflow():
            window=q.Toplevel(self.root);window.title('작업');q.ttk.Label(window,text='작업 화면').pack()
        with tempfile.TemporaryDirectory() as folder:
            self.root.geometry('1050x650')
            launcher=Launcher(self.root,[('업무',[(f'테스트 작업 메뉴 {index}',workflow) for index in range(12)])],Path(folder)/'settings.json')
            workspace=launcher.workspace
            for index in range(12):workspace.open(f'g0c{index}')
            q.application().processEvents()
            tabs=workspace.top_tabs
            arrows=[button for button in tabs.findChildren(q.W.QToolButton) if button.objectName() in ('ScrollLeftButton','ScrollRightButton')]
            self.assertEqual(len(arrows),2)
            self.assertTrue(all(button.isVisible() for button in arrows))
            before=tabs.tabRect(0).x()
            left=next(button for button in arrows if button.objectName()=='ScrollLeftButton')
            left.click();q.application().processEvents()
            self.assertNotEqual(tabs.tabRect(0).x(),before)
            self.assertLessEqual(workspace.local_badge.mapTo(self.root._q,q.C.QPoint()).x()+workspace.local_badge.width(),self.root._q.width())
            close=tabs.tabButton(0,q.W.QTabBar.ButtonPosition.RightSide)
            self.assertGreaterEqual(close.width(),22)
            self.assertFalse(close.icon().isNull())
            close.click();q.application().processEvents()
            self.assertEqual(tabs.count(),11)

    def test_total_spans_never_cover_data_and_theme_changes(self):
        found=0
        for category,database in SOURCES.items():
            for name in list_sheets(category):
                sheet=load_sheet(database,name)
                for row,start,span,label in sheet['spans']:
                    found+=1;values=sheet['records'][row]['values']
                    self.assertTrue(all(column==label or values[column] in (None,'') for column in range(start,start+span)))
                    self.assertIn(row,sheet['totals'])
        self.assertGreater(found,20)
        window=open_appendix_view(self.root,lambda w,x,y:w.geometry(f'{x}x{y}'))
        self.wait(lambda:window._work_status.get().endswith('건'))
        model=window._appendix_model;view=window._appendix_table
        for theme in ('dark','light'):
            set_appearance(self.root,theme,q.font.families()[0]);q.application().processEvents()
            for row in model.sheet['totals']:
                index=model.index(row,0)
                self.assertTrue(index.data(q.C.Qt.ItemDataRole.FontRole).bold())
                self.assertIsNotNone(index.data(q.C.Qt.ItemDataRole.BackgroundRole))
            for row,start,span,label in model.sheet['spans']:
                self.assertEqual(view.columnSpan(row,start),span)
                self.assertEqual(model.index(row,start).data(),display_value(model.sheet['records'][row]['values'][label]))
            for column,header in enumerate(model.sheet['headers']):
                if not any(word in header for word in ('내용','구분')):continue
                for row in range(model.rowCount()):
                    index=model.index(row,column)
                    metrics=q.G.QFontMetrics(index.data(q.C.Qt.ItemDataRole.FontRole))
                    self.assertGreaterEqual(view.columnWidth(column),metrics.horizontalAdvance(index.data())+20)

if __name__=='__main__':unittest.main()
