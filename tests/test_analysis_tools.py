import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
import app
import analysis_runtime as runtime


class AnalysisToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=runtime.load_analysis_history()
        cls.audit=runtime.load_audit_sources(Path(tempfile.gettempdir())/'no-finance-settings','2025')

    def test_bundled_history_without_pc_files(self):
        history,issues,paths=self.history
        self.assertEqual(set(history),{str(y) for y in range(2019,2026)})
        self.assertEqual(issues,[])
        for year,record in history.items():
            self.assertTrue(record['datasets'],year)
            self.assertTrue(paths[year].is_file())
        from statement_catalog import discover_appendices
        self.assertTrue(all(discover_appendices(paths['2025']).values()))

    def test_audit_reads_entire_ledger_and_preserves_provenance(self):
        self.assertEqual(len(self.audit['reviews']),164509)
        self.assertEqual(self.audit['ledger_years'],['2025','2024'])
        self.assertFalse(self.audit['issues'])
        record=self.audit['reviews'][0]['record']
        self.assertEqual(record['_file_year'],'2025')
        self.assertTrue(record['_source_file'].endswith('.sqlite3'))
        self.assertGreater(record['_source_row'],0)
        self.assertIn('2024',self.audit['history'])

    def test_reserve_review_uses_ledger_database(self):
        from decimal import Decimal
        sample={'목':'등록금회계전입금','대변':Decimal('1234')}
        source=Path('bundled.sqlite3')
        with patch.object(runtime,'program_ledger_paths',return_value={'2025':source}),patch.object(runtime,'load_program_ledger',return_value=[sample]):
            result=runtime.load_program_reserves(Path(tempfile.gettempdir())/'no-finance-settings','2025',self.history[2]['2025'])
        self.assertEqual(result['values']['transfer'],Decimal('1234'))
        self.assertEqual(result['sources']['transfer_file'],str(source))

    def test_database_analysis_matches_excel_values_and_provenance(self):
        from financial_analysis import load_history
        self.assertEqual(runtime.load_analysis_history(materialize_sources=False),
                         load_history(runtime.statement_folder()))

    def test_composition_panel_fit_coalesces_resize_events(self):
        from financial_analysis_ui import open_financial_analysis

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        root=q.Tk()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.object(q.Toplevel,'after_idle') as idle, \
                    patch('statement_ui.Jobs.run'):
                open_financial_analysis(root,lambda:Path(folder),app.center_window,lambda path:None)
                window=next(child for child in root.winfo_children() if isinstance(child,q.Toplevel))
                view=next(widget for widget in descendants(window) if isinstance(widget,q.Canvas)
                          and any(widget.type(item)=='window' for item in widget.find_all()))
                quadrants=view.winfo_children()[0]
                tree=next(widget for widget in descendants(quadrants) if isinstance(widget,q.Treeview))
                panel=tree.master.master
                toolbar,=[widget for widget in panel.winfo_children() if widget is not tree.master]
                q.application().processEvents()

                tree._analysis_widths=[110,120,130,140]
                with patch.object(tree,'xview',return_value=(0,.1)):
                    view.event_generate('<Configure>')
                    quadrants.event_generate('<Configure>')
                    view.event_generate('<Configure>')
                    idle.assert_called_once()
                    fit_panels=idle.call_args.args[0]
                    fit_panels()
                expected=max(sum(tree._analysis_widths)+48,toolbar.winfo_reqwidth()+24)
                self.assertEqual(quadrants._q.layout().columnMinimumWidth(1),expected)
                self.assertEqual(panel.cget('width'),expected)

                with patch.object(quadrants,'columnconfigure',wraps=quadrants.columnconfigure) as resize_column, \
                        patch.object(view,'itemconfigure',wraps=view.itemconfigure) as resize_canvas:
                    fit_panels()
                    resize_column.assert_not_called()
                    resize_canvas.assert_not_called()
        finally:root.destroy()

    def test_analysis_menus_create_real_views(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            folder=Path(folder)
            stack.enter_context(patch.object(app,'desktop',return_value=folder))
            stack.enter_context(patch('result_paths.desktop_dir',return_value=folder))
            stack.enter_context(patch('startup_update.check_on_start'))
            stack.enter_context(patch.object(q.Tk,'mainloop'))
            stack.enter_context(patch('financial_analysis_ui.load_history',return_value=self.history))
            stack.enter_context(patch('audit_ui.load_sources',return_value=self.audit))
            def immediate(jobs,work,done):done(work())
            stack.enter_context(patch('statement_ui.Jobs.run',immediate))
            app.main();root=q._default_root;errors=[]
            root.report_callback_exception=lambda *args:errors.append(str(args))
            try:
                launcher=root._launcher
                titles=['재무분석','결산검토','계정과목 검토','차입금관리','임대사항']
                self.assertEqual([name for name,_ in launcher.groups[1][1]],titles)
                workspace=launcher.workspace
                for key,(title,_) in workspace.commands.items():
                    if not key.startswith('g1'):continue
                    workspace.open(key)
                    end=time.monotonic()+.25
                    while time.monotonic()<end:q.application().processEvents();time.sleep(.005)
                    window=workspace.tabs[key]
                    self.assertEqual(window.title(),title)
                    self.assertTrue(window._q.findChildren(q.W.QPushButton),title)
                    self.assertFalse(any(label.text()=='준비 중' for label in window._q.findChildren(q.W.QLabel)))
                    if title=='계정과목 검토':
                        table=window._q.findChild(q.W.QTableView)
                        self.assertGreater(table.model().rowCount(),0)
                        self.assertLess(table.verticalHeader().defaultSectionSize(),32)
                        self.assertLessEqual(table.horizontalHeader().length(),table.viewport().width())
                self.assertFalse(errors)
            finally:root.destroy()

if __name__=='__main__':unittest.main()
