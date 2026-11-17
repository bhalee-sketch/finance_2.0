import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from hometax_ui import ask_certificate_password

class CertificateDialogTests(unittest.TestCase):
    def test_compact_masked_submit_and_cancel(self):
        root=q.Tk();root.geometry('800x600+0+0')
        try:
            for submit in (False,True):
                def interact(dialog):
                    q.application().processEvents()
                    self.assertTrue(dialog._q.isVisible())
                    self.assertGreaterEqual(dialog._q.width(),400)
                    self.assertLess(dialog._q.width(),550)
                    self.assertLess(dialog._q.height(),340)
                    center=root._q.mapToGlobal(root._q.rect().center())
                    self.assertLess(abs(dialog._q.geometry().center().x()-center.x()),5)
                    self.assertLess(abs(dialog._q.geometry().center().y()-center.y()),5)
                    entry=dialog._q.findChild(q.W.QLineEdit)
                    self.assertEqual(entry.echoMode(),q.W.QLineEdit.EchoMode.Password)
                    entry.setText('test-only-password')
                    label='로그인 시작' if submit else '취소'
                    next(b for b in dialog._q.findChildren(q.W.QPushButton) if b.text()==label).click()
                    self.assertFalse(dialog.winfo_exists())
                with patch.object(root,'wait_window',side_effect=interact):
                    result=ask_certificate_password(root)
                if submit:
                    self.assertEqual(result.take(),'test-only-password')
                    self.assertEqual(result.take(),'')
                else:self.assertIsNone(result)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
