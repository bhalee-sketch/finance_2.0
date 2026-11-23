import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook
from PySide6.QtTest import QTest
import qt_ui as q
from audit_review import AccountOrder, AUDIT_VISIBLE_HEADERS, export_review, inspect_record
from audit_ui import open_audit
from finance_data import LEDGER_COLUMNS


def review(subject, memo):
    record = dict.fromkeys(LEDGER_COLUMNS, '')
    record.update(년도='2025', 목=subject, 적요=memo, 차변=1000, 대변=0)
    return inspect_record(record)


class AuditReviewTests(unittest.TestCase):
    def test_candidates_require_concrete_evidence_in_the_narrative(self):
        for subject, memo, candidate in [
            ('차량유지비', '차량 보험료 납부', '보험료'),
            ('지급수수료', '결산 회계감사 대금', '일반용역비'),
            ('여비교통비', '복사용지 구입', '소모품비'),
            ('임대료수입', '임대 보증금 수납', '임대보증금수입'),
        ]:
            with self.subTest(subject=subject):
                result = review(subject, memo)
                self.assertEqual(result['state'], '분류 의심')
                self.assertIn(result['clue'], memo)
                self.assertEqual(result['candidate'], candidate)
        for subject, memo in [('회의비', '교원인사위원회 식대'), ('회의비', '부서 회의'),
                              ('소모품비', 'LED 책상조명 구매'), ('소모품비', '노트북 수리'),
                              ('교내장학금', '성적 장학금 지급')]:
            self.assertEqual(review(subject, memo)['state'], '탐지 사항 없음')
        self.assertEqual(review('회의비', '직원 회식')['state'], '분류 의심')
        self.assertEqual(review('회의비', '비용 지급')['state'], '적요 불충분')
        self.assertEqual(review('여비교통비', '토너 구입 취소')['state'], '원거래 확인')
        self.assertEqual(review('새 과목', '토너 구입')['state'], '규칙 미등록')

    def test_filtered_table_drag_paging_and_export(self):
        candidate = review('여비교통비', '복사용지 구입')
        items = [candidate] * 201 + [review('회의비', '비용 지급'), review('회의비', '부서 회의')]
        data = dict(order=AccountOrder(records=[i['record'] for i in items]),
                    reviews=items, ledger_years=['2025'], issues=[], sources=[])
        root = q.Tk()
        try:
            with tempfile.TemporaryDirectory() as directory, \
                    patch('audit_ui.program_ledger_paths', return_value={'2025': Path(directory)}), \
                    patch('audit_ui.load_sources', return_value=data):
                window = open_audit(root, lambda: Path(directory), lambda w,x,y: w.geometry('1200x700'), lambda p: None)
                table = window._q.findChild(q.W.QTableView)
                for _ in range(100):
                    QTest.qWait(25)
                    if table.model().rowCount() == 200:
                        break
                self.assertEqual(table.model().rowCount(), 200)
                col = AUDIT_VISIBLE_HEADERS.index('적요')
                header = table.horizontalHeader()
                header.setOffsetToSectionPosition(col)
                width = header.sectionSize(col)
                handle = q.C.QPoint(header.sectionViewportPosition(col) + width - 1, header.height() // 2)
                button = q.C.Qt.MouseButton.LeftButton
                QTest.mousePress(header.viewport(), button, pos=handle)
                QTest.mouseMove(header.viewport(), handle + q.C.QPoint(30, 0))
                QTest.mouseRelease(header.viewport(), button, pos=handle + q.C.QPoint(30, 0))
                adjusted = header.sectionSize(col)
                self.assertGreater(adjusted, width)
                buttons = {b.text(): b for b in window._q.findChildren(q.W.QPushButton)}
                buttons['다음'].click()
                self.assertEqual(table.model().rowCount(), 1)
                self.assertEqual(header.sectionSize(col), adjusted)
                box = next(b for b in window._q.findChildren(q.W.QComboBox) if b.currentText() == '분류 의심')
                box.setCurrentIndex(box.findText('적요 불충분'))
                box.activated.emit(box.currentIndex())
                self.assertEqual(table.model().index(0, col).data(), '비용 지급')
                self.assertEqual(header.sectionSize(col), adjusted)
                self.assertNotIn('확인할 증빙', AUDIT_VISIBLE_HEADERS)
                target = Path(directory) / 'review.xlsx'
                export_review(data, [candidate], {}, target)
                book = load_workbook(target, read_only=True)
                try:
                    headings, row = book.active.values
                    values = dict(zip(headings, row))
                    self.assertEqual(values['걸린 표현'], '복사용지')
                    self.assertEqual(values['검토할 과목'], '소모품비')
                    self.assertEqual(values['현재 과목'], '여비교통비')
                finally:
                    book.close()
        finally:
            root.destroy()
