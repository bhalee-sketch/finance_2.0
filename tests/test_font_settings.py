import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from launcher import Launcher, DEFAULTS


class FontSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'launcher.json'
        self.families = sorted(set(q.font.families()))
        self.assertGreater(len(self.families), 2)
        self.first, self.second = self.families[:2]
        self.preferences = dict(DEFAULTS, font=self.first, registered_fonts=[self.first])
        self.path.write_text(json.dumps(self.preferences))
        self.root = q.Tk()
        self.launcher = Launcher(self.root, [], self.path)
        self.launcher.customize()
        self.window = self.launcher.settings_window
        q.application().processEvents()

    def tearDown(self):
        self.root.destroy()
        q.application().processEvents()
        self.temp.cleanup()

    def pump(self):
        end = time.monotonic() + .2
        while time.monotonic() < end:
            q.application().processEvents()
            time.sleep(.005)

    def click(self, parent, label):
        button = next(w for w in parent._q.findChildren(q.W.QPushButton) if w.text() == label)
        button.click()
        self.pump()

    def choices(self):
        return {w.accessibleName(): [w.itemText(i) for i in range(w.count())]
                for w in self.window._q.findChildren(q.W.QComboBox) if w.accessibleName()}

    def add_font(self):
        self.click(self.window, '글꼴 추가')
        picker = next(w for w in self.window.children.values() if isinstance(w, q.Toplevel))
        self.assertTrue(picker._q.isVisible())
        items = picker._q.findChild(q.W.QListWidget)
        index = next(i for i in range(items.count()) if items.item(i).text() == self.second)
        items.setCurrentRow(index)
        self.click(picker, '선택한 글꼴 추가')
        self.assertFalse(picker.winfo_exists())
        self.assertIs(self.window.grab_current(), self.window)

    def test_add_save_reopen(self):
        self.assertEqual(self.choices()['화면 글꼴'], [self.first])
        self.assertEqual(self.choices()['그래프 글꼴'], ['화면 글꼴과 동일', self.first])
        self.add_font()
        for values in self.choices().values():
            self.assertIn(self.second, values)
        labels = [w.text() for w in self.window._q.findChildren(q.W.QLabel)]
        self.assertFalse(any('가수금' in x or '적용 글꼴' in x for x in labels))
        self.click(self.window, '저장')
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['font'], self.second)
        self.assertEqual(set(saved['registered_fonts']), {self.first, self.second})
        self.launcher.customize()
        self.window = self.launcher.settings_window
        self.assertEqual(set(self.choices()['화면 글꼴']), {self.first, self.second})
        self.click(self.window, '취소')

    def test_add_cancel_restores_preferences(self):
        self.add_font()
        self.click(self.window, '취소')
        self.assertEqual(self.launcher.preferences['registered_fonts'], [self.first])
        self.assertEqual(self.launcher.preferences['font'], self.first)
        self.assertEqual(json.loads(self.path.read_text()), self.preferences)

    def test_migrate_old_full_catalogue(self):
        self.click(self.window, '취소')
        self.launcher.preferences['registered_fonts'] = self.families
        self.launcher.customize()
        self.window = self.launcher.settings_window
        self.assertEqual(self.choices()['화면 글꼴'], [self.first])
        self.click(self.window, '취소')


if __name__ == '__main__':
    unittest.main()
