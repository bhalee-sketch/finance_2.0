import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import date
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from suspense_exceptions import register_exception,open_registration
from suspense_store import save_settings,load_settings
from suspense_engine import scope_applies
from suspense_data import Transaction
from suspense_ui import open_suspense

class ExceptionTests(unittest.TestCase):
    def test_registration_scope_and_persistence(self):
        settings=register_exception({},'department','구 부서','대표 부서','','담당자','부서 통합')
        self.assertEqual(settings['aliases'][0]['kind'],'department')
        with self.assertRaises(ValueError):register_exception(settings,'department','대표 부서','구 부서','','담당자','순환')
        settings=register_exception(settings,'counterparty_exception','원본상호','대응상호','재무팀','담당자','명칭 변경','2025-01-01','2025-12-31')
        tx=lambda d:Transaction('1',1,'원장','1',date.fromisoformat(d),'재무팀','원본상호',0,100,'내용','계좌','교비',())
        rule=settings['aliases'][-1]
        self.assertTrue(scope_applies(rule,tx('2025-06-01'),tx('2025-06-02')))
        self.assertFalse(scope_applies(rule,tx('2026-06-01'),tx('2026-06-02')))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rules.json';save_settings(path,settings)
            self.assertTrue(all(rule in load_settings(path)['aliases'] for rule in settings['aliases']))

    def test_ui_removed_actions_and_rule_registration(self):
        root=q.Tk()
        try:
            with tempfile.TemporaryDirectory() as folder:
                folder=Path(folder);open_suspense(root,lambda:folder,lambda w,x,y:w.geometry(f'{x}x{y}'),lambda *a:None)
                window=next(w for w in root.children.values() if isinstance(w,q.Toplevel));q.application().processEvents()
                buttons={b.text():b for b in window._q.findChildren(q.W.QPushButton)}
                for name in ['선택 승인·변경','선택 해제','규칙 해제']:self.assertNotIn(name,buttons)
                self.assertIs(buttons['파일 선택'].parent(),buttons['정산검증 실행'].parent())
                buttons['예외규칙 등록'].click();q.application().processEvents()
                dialog=next(w for w in window.children.values() if isinstance(w,q.Toplevel))
                fields={e.accessibleName():e for e in dialog._q.findChildren(q.W.QLineEdit)}
                for key,value in {'원본 명칭':'원본부서','대응 명칭':'대표부서','등록자':'담당자','근거':'명칭 통합'}.items():fields[key].setText(value)
                next(b for b in dialog._q.findChildren(q.W.QPushButton) if b.text()=='등록').click()
                self.assertFalse(dialog.winfo_exists())
                self.assertTrue(any(rule['source']=='원본부서' for rule in load_settings(folder/'settings'/'suspense'/'approvals.json')['aliases']))
        finally:root.destroy()

if __name__=='__main__':unittest.main()
