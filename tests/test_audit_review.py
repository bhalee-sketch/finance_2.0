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
from audit_review import AccountOrder, CAPITAL_REVIEW, AUDIT_VISIBLE_HEADERS, export_review, inspect_record
from audit_ui import open_audit
from finance_data import LEDGER_COLUMNS


def review(subject, memo, **fields):
    record = dict.fromkeys(LEDGER_COLUMNS, '')
    record.update(년도='2025', 목=subject, 적요=memo, 차변=1000, 대변=0)
    record.update(fields)
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

    def test_facility_capital_screening(self):
        for memo in ('본관 강의실 용도 변경 공사', '피난시설 설치 공사', '냉난방기 신규 설치',
                     '수변전설비 증설', '기계 내용연수 연장', '전소된 건물 복구', '실험실 환경개선공사', '닥트 설치공사'):
            with self.subTest(memo=memo):
                item = review('신규시설과목', memo, 항='시설관리비', 차변=10_000_000)
                self.assertEqual(item['candidate'], CAPITAL_REVIEW)
                self.assertIn(item['clue'], memo)
                self.assertEqual(item['state'], '분류 의심')
        for memo in ('외벽 도장', '파손 유리 교체', '승강기 유지보수', '기계 벨트 교체', '냉난방기 설치비 환입', '증축동 외벽 도장', '환경개선공사 중 외벽 도장'):
            self.assertNotEqual(review('건축물관리비', memo, 항='시설관리비', 차변=12_000_000)['candidate'], CAPITAL_REVIEW)
        for overrides in (dict(차변=9_999_999), dict(항='일반관리비'), dict(대변=10_000_000), dict(차변=-10_000_000)):
            fields = dict(항='시설관리비', 차변=10_000_000)
            fields.update(overrides)
            self.assertNotEqual(review('장비관리비', '설비 용량 증설', **fields)['candidate'], CAPITAL_REVIEW)

    def test_filtered_table_drag_scrolling_and_export(self):
        candidate = review('여비교통비', '복사용지 구입')
        last_suspect = review('장비관리비', '설비 용량 증설', 항='시설관리비', 차변=10_000_000)
        last_suspect['record']['거래선명'] = '자동차보험 거래처'
        long_memo = '위원회 회의비 지급 ' * 24
        long_voucher = '2025-ABCDEFGHIJKL-000000000123456789'
        normal = review('회의비', long_memo, 전표번호=long_voucher)
        items = [candidate] * 200 + [last_suspect, review('회의비', '비용 지급'), normal]
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
                    if table.model().rowCount() == 201 and table.verticalScrollBar().isVisible():
                        break
                self.assertEqual(table.model().rowCount(), 201)
                vertical = table.verticalScrollBar()
                horizontal = table.horizontalScrollBar()
                self.assertTrue(vertical.isVisible())
                self.assertFalse(horizontal.isVisible())
                col = AUDIT_VISIBLE_HEADERS.index('적요')
                header = table.horizontalHeader()
                headings = [table.model().headerData(i, q.C.Qt.Orientation.Horizontal)
                            for i in range(table.model().columnCount())]
                self.assertEqual(headings[headings.index('관'):headings.index('관') + 3], ['관', '항', '목'])
                self.assertNotIn('검토할 과목', headings)
                self.assertNotIn('근거 페이지', headings)
                self.assertNotIn('확인 상태', headings)
                self.assertNotIn('걸린 표현', headings)
                box = next(b for b in window._q.findChildren(q.W.QComboBox) if b.currentText() == '분류 의심')
                box.setCurrentIndex(box.findText('전체'))
                box.activated.emit(box.currentIndex())
                table.scrollToBottom()
                QTest.qWait(25)
                self.assertTrue(horizontal.isVisible())
                for heading, value in [('적요', long_memo), ('전표번호', long_voucher)]:
                    index = table.model().index(len(items) - 1, headings.index(heading))
                    metrics = q.G.QFontMetrics(index.data(q.C.Qt.ItemDataRole.FontRole))
                    self.assertGreaterEqual(header.sectionSize(index.column()), metrics.horizontalAdvance(value) + 6)
                box.setCurrentIndex(box.findText('분류 의심'))
                box.activated.emit(box.currentIndex())
                QTest.qWait(25)
                self.assertFalse(horizontal.isVisible())
                vendor = headings.index('거래선명')
                first_vendor_width = header.sectionSize(vendor)
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
                self.assertNotIn('다음', buttons)
                self.assertNotIn('이전', buttons)
                slider = q.W.QStyleOptionSlider()
                vertical.initStyleOption(slider)
                grip = vertical.style().subControlRect(q.W.QStyle.ComplexControl.CC_ScrollBar,
                    slider, q.W.QStyle.SubControl.SC_ScrollBarSlider, vertical).center()
                bottom = q.C.QPoint(grip.x(), vertical.height() - 1)
                QTest.mousePress(vertical, button, pos=grip)
                QTest.mouseMove(vertical, bottom)
                QTest.mouseRelease(vertical, button, pos=bottom)
                q.application().processEvents()
                self.assertEqual(vertical.value(), vertical.maximum())
                self.assertEqual(table.rowAt(table.viewport().height() - 1), 200)
                self.assertEqual(header.sectionSize(col), adjusted)
                self.assertGreater(header.sectionSize(vendor), first_vendor_width)
                cell = table.model().index(200, headings.index('목'))
                table.scrollTo(cell)
                pos = table.visualRect(cell).center()
                QTest.mouseClick(table.viewport(), button, pos=pos)
                QTest.mouseDClick(table.viewport(), button, pos=pos)
                popup = next(w for w in q.application().topLevelWidgets()
                             if w.windowTitle() == '계정과목 검토 · 거래 상세')
                detail = popup.findChild(q.W.QTextEdit).toPlainText()
                self.assertIn('근거 페이지: ' + last_suspect['reference'], detail)
                self.assertIn('목: 장비관리비', detail)
                self.assertIn('확인 상태: 분류 의심', detail)
                self.assertIn('걸린 표현: ' + last_suspect['clue'], detail)
                popup.close()
                box.setCurrentIndex(box.findText(CAPITAL_REVIEW))
                box.activated.emit(box.currentIndex())
                self.assertEqual(table.model().rowCount(), 1)
                QTest.qWait(25)
                self.assertFalse(vertical.isVisible())
                self.assertEqual(table.model().index(0, col).data(), '설비 용량 증설')
                box.setCurrentIndex(box.findText('적요 불충분'))
                box.activated.emit(box.currentIndex())
                self.assertEqual(table.model().index(0, col).data(), '비용 지급')
                self.assertEqual(header.sectionSize(col), adjusted)
                # Force real column overflow and check the last column is reachable.
                header.setMinimumSectionSize(table.viewport().width() // 4)
                for i in range(header.count()):
                    header.resizeSection(i, header.minimumSectionSize())
                QTest.qWait(25)
                self.assertTrue(horizontal.isVisible())
                horizontal.setValue(horizontal.maximum())
                self.assertEqual(table.columnAt(table.viewport().width() - 1), len(headings) - 1)
                self.assertNotIn('확인할 증빙', AUDIT_VISIBLE_HEADERS)
                target = Path(directory) / 'review.xlsx'
                export_review(data, [candidate], {}, target)
                book = load_workbook(target, read_only=True)
                try:
                    headings, row = book.active.values
                    values = dict(zip(headings, row))
                    self.assertEqual(values['걸린 표현'], '복사용지')
                    self.assertNotIn('검토할 과목', values)
                    self.assertNotIn('근거 페이지', values)
                    self.assertEqual(values['목'], '여비교통비')
                finally:
                    book.close()
        finally:
            root.destroy()
