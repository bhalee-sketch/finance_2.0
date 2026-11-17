# tools/excel_export_tool.py
"""
재무제표 엑셀 내보내기 도구
"""

from pathlib import Path
import calendar
import pandas as pd
class Callback:
    def __init__(self):self.handlers=[]
    def connect(self,handler):self.handlers.append(handler)
    def emit(self,*args):
        for handler in self.handlers:handler(*args)



class ExcelExportWorker:
    """엑셀 내보내기 작업을 백그라운드에서 수행하는 워커 (RESULT 형식)"""
    # progress callback  # (진행률, 메시지)
    # finished callback  # (성공여부, 메시지)

    # 시트 순서 정의
    SHEET_ORDER = [
        "자금계산서(전체)", "재무상태표(전체)", "운영계산서(전체)", "합계잔액시산표(전체)",
        "자금계산서(등록금)", "재무상태표(등록금)", "운영계산서(등록금)", "합계잔액시산표(등록금)",
        "자금계산서(비등록금)", "재무상태표(비등록금)", "운영계산서(비등록금)", "합계잔액시산표(비등록금)",
    ]

    @staticmethod
    def _apply_print_margins(ws) -> None:
        # openpyxl page margins use inches; these values match the requested cm settings.
        ws.page_margins.top = 1.8 / 2.54
        ws.page_margins.header = 0.8 / 2.54
        ws.page_margins.left = 1 / 2.54
        ws.page_margins.right = 1 / 2.54
        ws.page_margins.bottom = 1.5 / 2.54
        ws.page_margins.footer = 0.8 / 2.54

    @staticmethod
    def _apply_print_layout(ws) -> None:
        ws.print_options.horizontalCentered = True
        ws.page_setup.paperSize = ws.PAPERSIZE_A4

    def __init__(self, source_file: Path, dest_file: str):
        self.progress=Callback();self.finished=Callback()
        self.source_file = source_file
        self.dest_file = dest_file
        self._is_cancelled = False
        # 파일명에서 회계연도 추출 (예: "2024회계연도.xlsx" -> 2024)
        self.fiscal_year = self._extract_fiscal_year()

    def _extract_fiscal_year(self) -> int:
        """파일명에서 회계연도 추출"""
        try:
            name = self.source_file.stem  # "2024회계연도"
            year_str = name.replace("회계연도", "").strip()
            return int(year_str)
        except (ValueError,TypeError):
            import re
            match=re.search(r'(20\d{2})',self.source_file.stem)
            if not match:raise ValueError('파일명에 회계연도(예: 2026회계연도.xlsx)가 필요합니다.')
            return int(match.group(1))

    def _get_last_day_of_feb(self, year: int) -> int:
        """해당 연도 2월의 마지막 날짜 반환 (윤년 고려)"""
        return calendar.monthrange(year, 2)[1]

    def _get_fiscal_dates(self) -> dict:
        """회계연도 기준 날짜 정보 반환"""
        year = self.fiscal_year
        # 당기: year.3.1 ~ (year+1).2.말일
        # 전기: (year-1).3.1 ~ year.2.말일
        danggi_end_day = self._get_last_day_of_feb(year + 1)
        jeongi_end_day = self._get_last_day_of_feb(year)
        jeongi_start_end_day = self._get_last_day_of_feb(year - 1)  # 전전기 종료일 (전기 시작 전)

        return {
            # 자금계산서/합계잔액시산표용
            "fund_period": f"({year}.3.1 부터 {year + 1}.2.{danggi_end_day}까지)",
            # 재무상태표용
            "balance_danggi": f"(당기 : {year + 1}.2.{danggi_end_day} 현재)",
            "balance_jeongi": f"(전기 : {year}.2.{jeongi_end_day} 현재)",
            # 운영계산서용
            "income_danggi": f"(당기 : {year}.3.1부터 {year + 1}.2.{danggi_end_day}까지)",
            "income_jeongi": f"(전기 : {year - 1}.3.1부터 {year}.2.{jeongi_end_day}까지)",
        }

    def cancel(self):
        self._is_cancelled = True

    def _get_category_label(self, category: str) -> str:
        """구분에 따른 레이블 반환"""
        if category == "전체":
            return "교비 전체"
        elif category == "등록금":
            return "등록금회계"
        else:
            return "비등록금회계"

    def _process_data(self, df: pd.DataFrame, sheet_type: str) -> pd.DataFrame:
        """데이터 전처리 (구분자 제거, 0인 행 제거)"""
        if len(df) == 0 or len(df.columns) == 0:
            return df

        # 구분자 행 제거
        first_col = df.iloc[:, 0].astype(str)
        mask = ~(first_col.str.startswith('[') & first_col.str.contains(']') & first_col.str.contains('-'))
        df = df[mask].copy()

        # 0인 행 제거 (합계잔액시산표 제외)
        if sheet_type != "합계잔액시산표" and len(df) > 0 and len(df.columns) > 1:
            numeric_data = df.iloc[:, 1:]

            def is_all_zero_row(row):
                try:
                    non_nan_values = [val for val in row if not pd.isna(val)]
                    if not non_nan_values:
                        return False
                    numeric_values = []
                    for val in non_nan_values:
                        try:
                            num = float(str(val).replace(',', ''))
                            numeric_values.append(num)
                        except:
                            return False
                    return all(v == 0 for v in numeric_values)
                except:
                    return False

            keep_mask = ~numeric_data.apply(is_all_zero_row, axis=1)
            df = df[keep_mask].copy()

        return df

    def _process_trial_balance(self, source_file: Path, sheet_name: str) -> pd.DataFrame:
        """합계잔액시산표 특별 처리"""
        df_raw = pd.read_excel(source_file, sheet_name=sheet_name, header=None)

        if df_raw.shape[1] <= 10:
            data_start = 6
            df = df_raw.iloc[data_start:, :6].copy()
        else:
            data_start = 9
            for i in range(min(15, len(df_raw))):
                val = df_raw.iloc[i, 1]
                if pd.notna(val) and isinstance(val, (int, float)):
                    data_start = i
                    break
            col_indices = [1, 4, 7, 11, 15, 19]
            df = df_raw.iloc[data_start:, col_indices].copy()

        df.columns = ["차변잔액", "차변합계", "코드", "과목", "대변합계", "대변잔액"]
        df = df[df["과목"].notna() & (df["과목"].astype(str).str.strip() != "")]
        df["코드"] = df["코드"].apply(lambda x: str(int(x)) if pd.notna(x) and x != '' else '')

        # 숫자 열 변환 (빈 값은 0으로 처리)
        for col in ["차변잔액", "차변합계", "대변합계", "대변잔액"]:
            def safe_int(x):
                if pd.isna(x) or x == '':
                    return 0  # 빈 값은 0으로
                try:
                    if isinstance(x, str):
                        x = x.replace(',', '')
                    return int(round(float(x)))
                except:
                    return 0
            df[col] = df[col].apply(safe_int)

        # A, B, E, F 열 (차변잔액, 차변합계, 대변합계, 대변잔액)이 모두 0인 행 삭제
        numeric_cols = ["차변잔액", "차변합계", "대변합계", "대변잔액"]
        df = df[~((df[numeric_cols] == 0).all(axis=1))].copy()

        return df

    def _filter_fund_columns(self, df: pd.DataFrame, category: str) -> pd.DataFrame:
        """자금계산서 열 필터링 (구분별)"""
        cols = list(df.columns)

        if category == "등록금" and len(cols) >= 14:
            # 등록금: 평생교육원(3), 생활관(4), 국고(5), 복지회(6) 제외
            # 과목(0), 교비(1), 대학원(2), 내부(7), 확정(8)~증감(13)
            keep_indices = [0, 1, 2, 7, 8, 9, 10, 11, 12, 13]
            df = df.iloc[:, keep_indices].copy()

        elif category == "비등록금" and len(cols) >= 14:
            # 비등록금: 모든 열 유지 (내부거래 포함)
            # 과목(0), 교비(1), 대학원(2), 평생교육원(3), 생활관(4), 국고(5), 복지회(6), 내부(7), 확정(8)~증감(13)
            keep_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
            df = df.iloc[:, keep_indices].copy()

        return df

    def _write_fund_statement(self, ws, df, category):
        """자금계산서 시트 작성"""
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.utils.dataframe import dataframe_to_rows
        from openpyxl.worksheet.pagebreak import Break

        thin = Side(style='thin')
        medium = Side(style='medium')
        border_bottom = Border(bottom=thin)
        border_all = Border(top=thin, bottom=thin, left=thin, right=thin)
        header_fill = PatternFill(start_color="DCEAFF", end_color="DCEAFF", fill_type="solid")
        gwan_fill = PatternFill(start_color="E5E5E5", end_color="E5E5E5", fill_type="solid")
        marker_fill = PatternFill(start_color="E9D7C3", end_color="E9D7C3", fill_type="solid")
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        code_fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        highlighted_codes = {
            "1110", "1120", "1220", "1240", "1260", "1310", "1320",
            "2110", "2120", "2130", "2140", "2210", "2220", "2410",
            "3110", "3120", "3130", "3160", "3170",
            "4110", "4120", "4210", "4220", "4230", "4240", "4250",
            "4310", "4320", "4330", "4410", "4420",
            "5110", "5120", "5210", "5220", "5230", "5240",
            "5310", "5320", "5330", "5410", "5420",
        }
        marker_fill = PatternFill(start_color="E9D7C3", end_color="E9D7C3", fill_type="solid")
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        marker_fill = PatternFill(start_color="E9D7C3", end_color="E9D7C3", fill_type="solid")
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        total_keywords = [
            "운영수입", "자산,부채 및 기본금수입", "자 금 수 입 총 계",
            "운  영  지  출", "자산 및 부채지출", "자 금 지 출 총 계",
            "자 산 총 계", "부채와기본금 총계",
            "[운영수익 총계]", "[운영비용 총계]", "비 용 총 계"
        ]

        cat_label = self._get_category_label(category)
        dates = self._get_fiscal_dates()

        # 행 높이 설정
        ws.row_dimensions[1].height = 30  # 40픽셀
        ws.row_dimensions[2].height = 30  # 40픽셀
        ws.row_dimensions[3].height = 30  # 1. 수입 행: 40픽셀

        # 구분별 열 수 결정
        if category == "비등록금":
            last_col = 'N'  # 14열
            last_col_num = 14
        else:
            last_col = 'J'  # 10열
            last_col_num = 10

        # 헤더 작성
        ws['A1'] = "자  금  계  산  서"
        ws.merge_cells(f'A1:{last_col}1')
        ws['A1'].font = Font(bold=True, size=20, underline='single')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')

        ws['A2'] = f"{dates['fund_period']}\n{cat_label}"
        ws.merge_cells(f'A2:{last_col}2')
        ws['A2'].font = Font(size=12)
        ws['A2'].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        ws['A3'] = "1. 수입"
        ws['A3'].font = Font(bold=True, size=12)
        ws['A3'].alignment = Alignment(horizontal='left', vertical='center')
        ws[f'{last_col}3'] = "(단위: 원)"
        ws[f'{last_col}3'].font = Font(bold=True, size=12)
        ws[f'{last_col}3'].alignment = Alignment(horizontal='right', vertical='center')

        # 4행 헤더 (구분별)
        ws['A4'] = "과        목"

        if category == "전체":
            # 전체: 등록금회계, 비등록금회계, 내부거래제거
            ws['B4'] = "등록금회계"
            ws['C4'] = "비등록금회계"
            ws['D4'] = "내부거래제거"
            ws['E4'] = "합 산 자 금 계 산 서"
            ws.merge_cells('B4:B5')
            ws.merge_cells('C4:C5')
            ws.merge_cells('D4:D5')
            ws.merge_cells('E4:J4')
            # 5행 헤더
            ws['A5'] = "(관  항  목)"
            ws['E5'] = "확정"
            ws['F5'] = "전용증감"
            ws['G5'] = "예비비"
            ws['H5'] = "예산액"
            ws['I5'] = "결산액"
            ws['J5'] = "증감액"

        elif category == "등록금":
            # 등록금: 교비, 대학원, 내부거래
            ws['B4'] = "교비"
            ws['C4'] = "대학원"
            ws['D4'] = "내부거래"
            ws['E4'] = "합 산 자 금 계 산 서"
            ws.merge_cells('B4:B5')
            ws.merge_cells('C4:C5')
            ws.merge_cells('D4:D5')
            ws.merge_cells('E4:J4')
            # 5행 헤더
            ws['A5'] = "(관  항  목)"
            ws['E5'] = "확정"
            ws['F5'] = "전용증감"
            ws['G5'] = "예비비"
            ws['H5'] = "예산액"
            ws['I5'] = "결산액"
            ws['J5'] = "증감액"

        else:  # 비등록금
            # 비등록금: 교비, 대학원, 평생교육원, 생활관, 국고, 복지회, 내부거래
            ws['B4'] = "교비"
            ws['C4'] = "대학원"
            ws['D4'] = "평생교육원"
            ws['E4'] = "생활관"
            ws['F4'] = "국고"
            ws['G4'] = "복지회"
            ws['H4'] = "내부거래"
            ws['I4'] = "합 산 자 금 계 산 서"
            ws.merge_cells('B4:B5')
            ws.merge_cells('C4:C5')
            ws.merge_cells('D4:D5')
            ws.merge_cells('E4:E5')
            ws.merge_cells('F4:F5')
            ws.merge_cells('G4:G5')
            ws.merge_cells('H4:H5')
            ws.merge_cells('I4:N4')
            # 5행 헤더
            ws['A5'] = "(관  항  목)"
            ws['I5'] = "확정"
            ws['J5'] = "전용증감"
            ws['K5'] = "예비비"
            ws['L5'] = "예산액"
            ws['M5'] = "결산액"
            ws['N5'] = "증감액"

        # 헤더 스타일 적용 (4-5행) - 전체 테두리 + 굵은 바깥쪽 테두리 + 배경색
        for row in range(4, 6):
            for col in range(1, last_col_num + 1):
                cell = ws.cell(row=row, column=col)
                cell.font = Font(bold=True)
                cell.fill = header_fill
                # A5는 왼쪽 정렬, 나머지는 가운데 정렬
                if row == 5 and col == 1:
                    cell.alignment = Alignment(horizontal='left', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='center', vertical='center')

                # 굵은 바깥쪽 테두리 + 얇은 내부 테두리
                top_side = medium if row == 4 else thin
                bottom_side = medium if row == 5 else thin
                left_side = medium if col == 1 else thin
                right_side = medium if col == last_col_num else thin
                cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # "보수" 행 인덱스 찾기
        bosu_idx = None
        df_values = list(dataframe_to_rows(df, index=False, header=False))
        for i, row in enumerate(df_values):
            if len(row) > 0 and str(row[0]).strip() == "보수":
                bosu_idx = i
                break

        # 데이터 작성
        start_row = 6
        current_row = start_row
        income_last_row = None  # 수입 표 마지막 행
        expense_header_start = None  # 지출 헤더 시작 행
        expense_data_start = None  # 지출 데이터 시작 행

        for data_idx, row in enumerate(df_values):
            # "보수" 행 앞에 지출 헤더 삽입
            if bosu_idx is not None and data_idx == bosu_idx:
                # 수입 표 마지막 행 기록
                income_last_row = current_row - 1

                # 5개 빈 행 중 3행은 헤더로 사용
                # 2개 빈 행
                current_row += 2

                # 페이지 나누기 추가 (2. 지출부터 새 페이지)
                ws.row_breaks.append(Break(id=current_row - 1))

                # "2. 지출" 헤더 (3행 복사) - 볼드 처리
                ws.cell(row=current_row, column=1).value = "2. 지출"
                ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
                ws.cell(row=current_row, column=1).alignment = Alignment(horizontal='left', vertical='center')
                ws.cell(row=current_row, column=last_col_num).value = "(단위: 원)"
                ws.cell(row=current_row, column=last_col_num).font = Font(bold=True, size=12)
                ws.cell(row=current_row, column=last_col_num).alignment = Alignment(horizontal='right', vertical='center')
                ws.row_dimensions[current_row].height = 30  # 2. 지출 행: 40픽셀
                current_row += 1

                # 4행 헤더 복사
                ws.cell(row=current_row, column=1).value = "과        목"
                if category == "전체":
                    ws.cell(row=current_row, column=2).value = "등록금회계"
                    ws.cell(row=current_row, column=3).value = "비등록금회계"
                    ws.cell(row=current_row, column=4).value = "내부거래제거"
                    ws.cell(row=current_row, column=5).value = "합 산 자 금 계 산 서"
                    ws.merge_cells(f'B{current_row}:B{current_row+1}')
                    ws.merge_cells(f'C{current_row}:C{current_row+1}')
                    ws.merge_cells(f'D{current_row}:D{current_row+1}')
                    ws.merge_cells(f'E{current_row}:J{current_row}')
                elif category == "등록금":
                    ws.cell(row=current_row, column=2).value = "교비"
                    ws.cell(row=current_row, column=3).value = "대학원"
                    ws.cell(row=current_row, column=4).value = "내부거래"
                    ws.cell(row=current_row, column=5).value = "합 산 자 금 계 산 서"
                    ws.merge_cells(f'B{current_row}:B{current_row+1}')
                    ws.merge_cells(f'C{current_row}:C{current_row+1}')
                    ws.merge_cells(f'D{current_row}:D{current_row+1}')
                    ws.merge_cells(f'E{current_row}:J{current_row}')
                else:  # 비등록금
                    ws.cell(row=current_row, column=2).value = "교비"
                    ws.cell(row=current_row, column=3).value = "대학원"
                    ws.cell(row=current_row, column=4).value = "평생교육원"
                    ws.cell(row=current_row, column=5).value = "생활관"
                    ws.cell(row=current_row, column=6).value = "국고"
                    ws.cell(row=current_row, column=7).value = "복지회"
                    ws.cell(row=current_row, column=8).value = "내부거래"
                    ws.cell(row=current_row, column=9).value = "합 산 자 금 계 산 서"
                    ws.merge_cells(f'B{current_row}:B{current_row+1}')
                    ws.merge_cells(f'C{current_row}:C{current_row+1}')
                    ws.merge_cells(f'D{current_row}:D{current_row+1}')
                    ws.merge_cells(f'E{current_row}:E{current_row+1}')
                    ws.merge_cells(f'F{current_row}:F{current_row+1}')
                    ws.merge_cells(f'G{current_row}:G{current_row+1}')
                    ws.merge_cells(f'H{current_row}:H{current_row+1}')
                    ws.merge_cells(f'I{current_row}:N{current_row}')

                # 지출 헤더 시작 행 기록
                expense_header_start = current_row

                # 4행 스타일 적용 - 굵은 바깥쪽 테두리 + 배경색
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    top_side = medium
                    bottom_side = thin
                    left_side = medium if col == 1 else thin
                    right_side = medium if col == last_col_num else thin
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
                current_row += 1

                # 5행 헤더 복사
                ws.cell(row=current_row, column=1).value = "(관  항  목)"
                if category == "비등록금":
                    ws.cell(row=current_row, column=9).value = "확정"
                    ws.cell(row=current_row, column=10).value = "전용증감"
                    ws.cell(row=current_row, column=11).value = "예비비"
                    ws.cell(row=current_row, column=12).value = "예산액"
                    ws.cell(row=current_row, column=13).value = "결산액"
                    ws.cell(row=current_row, column=14).value = "증감액"
                else:
                    ws.cell(row=current_row, column=5).value = "확정"
                    ws.cell(row=current_row, column=6).value = "전용증감"
                    ws.cell(row=current_row, column=7).value = "예비비"
                    ws.cell(row=current_row, column=8).value = "예산액"
                    ws.cell(row=current_row, column=9).value = "결산액"
                    ws.cell(row=current_row, column=10).value = "증감액"

                # 5행 스타일 적용 - 굵은 바깥쪽 테두리 + A열 왼쪽 정렬 + 배경색
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                    # A열은 왼쪽 정렬
                    if col == 1:
                        cell.alignment = Alignment(horizontal='left', vertical='center')
                    else:
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                    top_side = thin
                    bottom_side = medium
                    left_side = medium if col == 1 else thin
                    right_side = medium if col == last_col_num else thin
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
                current_row += 1
                expense_data_start = current_row

            # 데이터 행 작성
            # 관 행 여부 확인 (A열 값이 공백 없이 시작하면 관)
            first_col_value = str(row[0]) if len(row) > 0 and row[0] is not None else ''
            is_gwan = first_col_value and not first_col_value.startswith(' ') and first_col_value.strip() != ''
            # 항 행 여부 확인 (공백 5개로 시작하면 항)
            is_hang = first_col_value.startswith('     ') and not first_col_value.startswith('      ')
            # 합계 행 여부 확인
            is_total = first_col_value.strip() in total_keywords

            for col_idx, value in enumerate(row, 1):
                if col_idx > last_col_num:
                    break
                cell = ws.cell(row=current_row, column=col_idx)
                if isinstance(value, (int, float)) and not pd.isna(value):
                    cell.value = value
                    cell.number_format = '#,##0'
                    cell.alignment = Alignment(horizontal='right')
                else:
                    cell.value = value if not pd.isna(value) else ''
                cell.border = border_all
                if is_total:
                    cell.fill = total_fill
                    cell.font = Font(bold=True)
                    if col_idx == 1:  # A열만 가운데 정렬
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                elif is_gwan or is_hang:
                    cell.fill = gwan_fill
            ws.row_dimensions[current_row].height = 18  # 데이터 행: 24픽셀
            current_row += 1

        # 수입/지출 개별 표 굵은 바깥쪽 테두리 적용
        last_row = current_row - 1

        # 수입 표 굵은 바깥쪽 테두리 (4행 ~ income_last_row)
        if income_last_row:
            for row in range(4, income_last_row + 1):
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=row, column=col)
                    current_border = cell.border
                    top_side = medium if row == 4 else current_border.top
                    bottom_side = medium if row == income_last_row else current_border.bottom
                    left_side = medium if col == 1 else current_border.left
                    right_side = medium if col == last_col_num else current_border.right
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

            # 지출 표 굵은 바깥쪽 테두리 (expense_header_start ~ last_row)
            if expense_header_start:
                for row in range(expense_header_start, last_row + 1):
                    for col in range(1, last_col_num + 1):
                        cell = ws.cell(row=row, column=col)
                        current_border = cell.border
                        top_side = medium if row == expense_header_start else current_border.top
                        bottom_side = medium if row == last_row else current_border.bottom
                        left_side = medium if col == 1 else current_border.left
                        right_side = medium if col == last_col_num else current_border.right
                        cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
        else:
            # 지출이 없는 경우 전체를 하나의 표로 처리
            for row in range(4, last_row + 1):
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=row, column=col)
                    current_border = cell.border
                    top_side = medium if row == 4 else current_border.top
                    bottom_side = medium if row == last_row else current_border.bottom
                    left_side = medium if col == 1 else current_border.left
                    right_side = medium if col == last_col_num else current_border.right
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # 열 너비 설정 (A열 제외 130픽셀 = 약 18 width)
        ws.column_dimensions['A'].width = 33
        col_letters = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']
        for col in col_letters[:last_col_num - 1]:
            ws.column_dimensions[col].width = 18

        # 인쇄 설정: 가로 방향, 모든 열 한 페이지에 맞추기
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        self._apply_print_layout(ws)
        self._apply_print_margins(ws)

    def _write_balance_sheet(self, ws, df, category):
        """재무상태표 시트 작성"""
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.utils.dataframe import dataframe_to_rows
        from openpyxl.worksheet.pagebreak import Break

        thin = Side(style='thin')
        medium = Side(style='medium')
        border_all = Border(top=thin, bottom=thin, left=thin, right=thin)
        header_fill = PatternFill(start_color="DCEAFF", end_color="DCEAFF", fill_type="solid")
        gwan_fill = PatternFill(start_color="E5E5E5", end_color="E5E5E5", fill_type="solid")
        marker_fill = PatternFill(start_color="E9D7C3", end_color="E9D7C3", fill_type="solid")
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        code_fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        highlighted_codes = {
            "1110", "1120", "1220", "1240", "1260", "1310", "1320",
            "2110", "2120", "2130", "2140", "2210", "2220", "2410",
            "3110", "3120", "3130", "3160", "3170",
            "4110", "4120", "4210", "4220", "4230", "4240", "4250",
            "4310", "4320", "4330", "4410", "4420",
            "5110", "5120", "5210", "5220", "5230", "5240",
            "5310", "5320", "5330", "5410", "5420",
        }
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        total_keywords = [
            "운영수입", "자산,부채 및 기본금수입", "자 금 수 입 총 계",
            "운  영  지  출", "자산 및 부채지출", "자 금 지 출 총 계",
            "자 산 총 계", "부채와기본금 총계",
            "[운영수익 총계]", "[운영비용 총계]", "비 용 총 계"
        ]

        cat_label = self._get_category_label(category)
        dates = self._get_fiscal_dates()

        # 구분별 설정
        if category == "전체":
            # 전체: 6열 원본 → 7열 출력 (과목, 등록금회계, 비등록금회계, 내부거래제거, 당기, 전기, 증감)
            last_col_num = 7
            last_col = 'G'
            source_col_indices = [0, 1, 2, 3, 4, 5]  # 모든 6열 사용
            danggi_src_idx = 4  # 원본 당기 인덱스
            jeongi_src_idx = 5  # 원본 전기 인덱스
            headers_row5 = ["과        목", "등록금회계", "비등록금회계", "내부거래제거", "당기(A)", "전기(B)", "증감(A-B)"]
            merge_cols = ['B', 'C', 'D', 'E', 'F', 'G']
        elif category == "등록금":
            # 등록금: 10열 원본 중 0,1,2,8,9열 사용 → 6열 출력 (과목, 교비, 대학원, 당기, 전기, 증감)
            last_col_num = 6
            last_col = 'F'
            source_col_indices = [0, 1, 2, 8, 9]  # 과목, 교비, 대학원, 당기, 전기
            danggi_src_idx = 8  # 원본 당기 인덱스
            jeongi_src_idx = 9  # 원본 전기 인덱스
            headers_row5 = ["과        목", "교비", "대학원", "당기(A)", "전기(B)", "증감(A-B)"]
            merge_cols = ['B', 'C', 'D', 'E', 'F']
        else:  # 비등록금
            # 비등록금: 10열 원본 모두 사용 → 11열 출력 (과목, 교비, 대학원, 평생교육원, 생활관, 국고, 복지회, 내부거래, 당기, 전기, 증감)
            last_col_num = 11
            last_col = 'K'
            source_col_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]  # 모든 10열 사용
            danggi_src_idx = 8  # 원본 당기 인덱스
            jeongi_src_idx = 9  # 원본 전기 인덱스
            headers_row5 = ["과        목", "교비", "대학원", "평생교육원", "생활관", "국고", "복지회", "내부거래", "당기(A)", "전기(B)", "증감(A-B)"]
            merge_cols = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']

        # 행 높이 설정
        ws.row_dimensions[1].height = 30  # 40픽셀
        ws.row_dimensions[2].height = 30  # 40픽셀
        ws.row_dimensions[3].height = 18  # 24픽셀
        ws.row_dimensions[4].height = 30  # 1. 자산 행: 40픽셀

        # 헤더 작성
        ws['A1'] = "재   무   상   태   표"
        ws.merge_cells(f'A1:{last_col}1')
        ws['A1'].font = Font(bold=True, size=20, underline='single')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')

        ws['A2'] = f"{dates['balance_danggi']}\n{dates['balance_jeongi']}"
        ws.merge_cells(f'A2:{last_col}2')
        ws['A2'].font = Font(size=12)
        ws['A2'].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        ws['A3'] = cat_label
        ws.merge_cells(f'A3:{last_col}3')
        ws['A3'].alignment = Alignment(horizontal='center', vertical='center')

        ws['A4'] = "1. 자산"
        ws['A4'].font = Font(bold=True, size=12)
        ws['A4'].alignment = Alignment(horizontal='left', vertical='center')
        ws.cell(row=4, column=last_col_num).value = "(단위: 원)"
        ws.cell(row=4, column=last_col_num).font = Font(bold=True, size=12)
        ws.cell(row=4, column=last_col_num).alignment = Alignment(horizontal='right', vertical='center')

        # 5행 헤더
        for col_idx, header in enumerate(headers_row5, 1):
            ws.cell(row=5, column=col_idx).value = header

        for col in merge_cols:
            ws.merge_cells(f'{col}5:{col}6')

        # 6행 헤더
        ws['A6'] = "(관  항  목)"

        # 헤더 스타일 적용 (5-6행) - 굵은 바깥쪽 테두리 + 배경색
        for row in range(5, 7):
            for col in range(1, last_col_num + 1):
                cell = ws.cell(row=row, column=col)
                cell.font = Font(bold=True)
                cell.fill = header_fill
                # A6는 왼쪽 정렬
                if row == 6 and col == 1:
                    cell.alignment = Alignment(horizontal='left', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                # 굵은 바깥쪽 테두리
                top_side = medium if row == 5 else thin
                bottom_side = medium if row == 6 else thin
                left_side = medium if col == 1 else thin
                right_side = medium if col == last_col_num else thin
                cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # "유동부채" 행 인덱스 찾기
        liability_idx = None
        df_values = list(dataframe_to_rows(df, index=False, header=False))
        for i, row in enumerate(df_values):
            if len(row) > 0 and str(row[0]).strip() == "유동부채":
                liability_idx = i
                break

        # 데이터 작성
        start_row = 7
        current_row = start_row
        asset_last_row = None  # 자산 표 마지막 행
        liability_header_start = None  # 부채 헤더 시작 행

        for data_idx, row in enumerate(df_values):
            # "유동부채" 행 앞에 부채 헤더 삽입
            if liability_idx is not None and data_idx == liability_idx:
                # 자산 표 마지막 행 기록
                asset_last_row = current_row - 1

                # 2개 빈 행
                current_row += 2

                # 페이지 나누기 추가 (2. 부채와기본금부터 새 페이지)
                ws.row_breaks.append(Break(id=current_row - 1))

                # "2. 부채와기본금" 헤더
                ws.cell(row=current_row, column=1).value = "2. 부채와기본금"
                ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
                ws.cell(row=current_row, column=1).alignment = Alignment(horizontal='left', vertical='center')
                ws.cell(row=current_row, column=last_col_num).value = "(단위: 원)"
                ws.cell(row=current_row, column=last_col_num).font = Font(bold=True, size=12)
                ws.cell(row=current_row, column=last_col_num).alignment = Alignment(horizontal='right', vertical='center')
                ws.row_dimensions[current_row].height = 30  # 2. 부채와기본금 행: 40픽셀
                current_row += 1

                # 5행 헤더 복사
                for col_idx, header in enumerate(headers_row5, 1):
                    ws.cell(row=current_row, column=col_idx).value = header
                for col in merge_cols:
                    col_num = ord(col) - ord('A') + 1
                    ws.merge_cells(f'{col}{current_row}:{col}{current_row+1}')

                # 부채 헤더 시작 행 기록
                liability_header_start = current_row

                # 5행 스타일 적용 - 굵은 바깥쪽 테두리 + 배경색
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    top_side = medium
                    bottom_side = thin
                    left_side = medium if col == 1 else thin
                    right_side = medium if col == last_col_num else thin
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
                current_row += 1

                # 6행 헤더 복사
                ws.cell(row=current_row, column=1).value = "(관  항  목)"

                # 6행 스타일 적용 - 굵은 바깥쪽 테두리 + A열 왼쪽 정렬 + 배경색
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                    if col == 1:
                        cell.alignment = Alignment(horizontal='left', vertical='center')
                    else:
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                    top_side = thin
                    bottom_side = medium
                    left_side = medium if col == 1 else thin
                    right_side = medium if col == last_col_num else thin
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
                current_row += 1

            # 데이터 행 작성 (source_col_indices에 따라 매핑)
            # 관 행 여부 확인 (A열 값이 공백 없이 시작하면 관)
            first_col_value = str(row[0]) if len(row) > 0 and row[0] is not None else ''
            is_gwan = first_col_value and not first_col_value.startswith(' ') and first_col_value.strip() != ''
            # 항 행 여부 확인 (공백 5개로 시작하면 항)
            is_hang = first_col_value.startswith('     ') and not first_col_value.startswith('      ')
            # 합계 행 여부 확인
            is_total = first_col_value.strip() in total_keywords

            output_col_num = len(source_col_indices)  # 증감 제외 출력 열 수
            for out_idx, src_idx in enumerate(source_col_indices):
                cell = ws.cell(row=current_row, column=out_idx + 1)
                value = row[src_idx] if len(row) > src_idx else ''
                if isinstance(value, (int, float)) and not pd.isna(value):
                    cell.value = value
                    cell.number_format = '#,##0'
                    cell.alignment = Alignment(horizontal='right')
                else:
                    cell.value = value if not pd.isna(value) else ''
                cell.border = border_all
                if is_total:
                    cell.fill = total_fill
                    cell.font = Font(bold=True)
                    if out_idx + 1 == 1:  # A열만 가운데 정렬
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                elif is_gwan or is_hang:
                    cell.fill = gwan_fill

            # 마지막 열: 증감(A-B) 계산 = 당기 - 전기
            cell = ws.cell(row=current_row, column=last_col_num)
            try:
                danggi = row[danggi_src_idx] if len(row) > danggi_src_idx and isinstance(row[danggi_src_idx], (int, float)) and not pd.isna(row[danggi_src_idx]) else 0
                jeongi = row[jeongi_src_idx] if len(row) > jeongi_src_idx and isinstance(row[jeongi_src_idx], (int, float)) and not pd.isna(row[jeongi_src_idx]) else 0
                증감값 = danggi - jeongi
                cell.value = 증감값
                cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal='right')
            except:
                cell.value = ''
            cell.border = border_all
            if is_total:
                cell.fill = total_fill
                cell.font = Font(bold=True)
            elif is_gwan or is_hang:
                cell.fill = gwan_fill
            ws.row_dimensions[current_row].height = 18  # 데이터 행: 24픽셀
            current_row += 1

        # 자산/부채 개별 표 굵은 바깥쪽 테두리 적용
        last_row = current_row - 1

        if asset_last_row:
            # 자산 표 굵은 바깥쪽 테두리 (5행 ~ asset_last_row)
            for row in range(5, asset_last_row + 1):
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=row, column=col)
                    current_border = cell.border
                    top_side = medium if row == 5 else current_border.top
                    bottom_side = medium if row == asset_last_row else current_border.bottom
                    left_side = medium if col == 1 else current_border.left
                    right_side = medium if col == last_col_num else current_border.right
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

            # 부채 표 굵은 바깥쪽 테두리 (liability_header_start ~ last_row)
            if liability_header_start:
                for row in range(liability_header_start, last_row + 1):
                    for col in range(1, last_col_num + 1):
                        cell = ws.cell(row=row, column=col)
                        current_border = cell.border
                        top_side = medium if row == liability_header_start else current_border.top
                        bottom_side = medium if row == last_row else current_border.bottom
                        left_side = medium if col == 1 else current_border.left
                        right_side = medium if col == last_col_num else current_border.right
                        cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
        else:
            # 부채가 없는 경우 전체를 하나의 표로 처리
            for row in range(5, last_row + 1):
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=row, column=col)
                    current_border = cell.border
                    top_side = medium if row == 5 else current_border.top
                    bottom_side = medium if row == last_row else current_border.bottom
                    left_side = medium if col == 1 else current_border.left
                    right_side = medium if col == last_col_num else current_border.right
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # 열 너비 설정 (A열 제외 130픽셀 = 약 18 width)
        ws.column_dimensions['A'].width = 33
        col_letters = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
        for col in col_letters[:last_col_num - 1]:
            ws.column_dimensions[col].width = 18

        # 인쇄 설정: 가로 방향, 모든 열 한 페이지에 맞추기
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        self._apply_print_layout(ws)
        self._apply_print_margins(ws)

    def _write_income_statement(self, ws, df, category):
        """운영계산서 시트 작성"""
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.utils.dataframe import dataframe_to_rows
        from openpyxl.worksheet.pagebreak import Break

        thin = Side(style='thin')
        medium = Side(style='medium')
        border_all = Border(top=thin, bottom=thin, left=thin, right=thin)
        header_fill = PatternFill(start_color="DCEAFF", end_color="DCEAFF", fill_type="solid")
        gwan_fill = PatternFill(start_color="E5E5E5", end_color="E5E5E5", fill_type="solid")
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        total_keywords = [
            "운영수입", "자산,부채 및 기본금수입", "자 금 수 입 총 계",
            "운  영  지  출", "자산 및 부채지출", "자 금 지 출 총 계",
            "자 산 총 계", "부채와기본금 총계",
            "[운영수익 총계]", "[운영비용 총계]", "비 용 총 계"
        ]

        cat_label = self._get_category_label(category)
        dates = self._get_fiscal_dates()

        # 구분별 설정
        if category == "전체":
            # 전체: 6열 원본 → 7열 출력 (과목, 등록금회계, 비등록금회계, 내부거래제거, 당기, 전기, 증감)
            last_col_num = 7
            last_col = 'G'
            source_col_indices = [0, 1, 2, 3, 4, 5]  # 모든 6열 사용
            danggi_src_idx = 4  # 원본 당기 인덱스
            jeongi_src_idx = 5  # 원본 전기 인덱스
            headers_row5 = ["과        목", "등록금회계", "비등록금회계", "내부거래제거", "당기(A)", "전기(B)", "증감(A-B)"]
            merge_cols = ['B', 'C', 'D', 'E', 'F', 'G']
        elif category == "등록금":
            # 등록금: 10열 원본 중 0,1,2,8,9열 사용 → 6열 출력 (과목, 교비, 대학원, 당기, 전기, 증감)
            last_col_num = 6
            last_col = 'F'
            source_col_indices = [0, 1, 2, 8, 9]  # 과목, 교비, 대학원, 당기, 전기
            danggi_src_idx = 8  # 원본 당기 인덱스
            jeongi_src_idx = 9  # 원본 전기 인덱스
            headers_row5 = ["과        목", "교비", "대학원", "당기(A)", "전기(B)", "증감(A-B)"]
            merge_cols = ['B', 'C', 'D', 'E', 'F']
        else:  # 비등록금
            # 비등록금: 10열 원본 모두 사용 → 11열 출력 (과목, 교비, 대학원, 평생교육원, 생활관, 국고, 복지회, 내부거래, 당기, 전기, 증감)
            last_col_num = 11
            last_col = 'K'
            source_col_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]  # 모든 10열 사용
            danggi_src_idx = 8  # 원본 당기 인덱스
            jeongi_src_idx = 9  # 원본 전기 인덱스
            headers_row5 = ["과        목", "교비", "대학원", "평생교육원", "생활관", "국고", "복지회", "내부거래", "당기(A)", "전기(B)", "증감(A-B)"]
            merge_cols = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']

        # 행 높이 설정
        ws.row_dimensions[1].height = 30  # 40픽셀
        ws.row_dimensions[2].height = 30  # 40픽셀
        ws.row_dimensions[3].height = 18  # 24픽셀
        ws.row_dimensions[4].height = 30  # 1. 운영수익 행: 40픽셀

        # 헤더 작성
        ws['A1'] = "운   영   계   산   서"
        ws.merge_cells(f'A1:{last_col}1')
        ws['A1'].font = Font(bold=True, size=20, underline='single')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')

        ws['A2'] = f"{dates['income_danggi']}\n{dates['income_jeongi']}"
        ws.merge_cells(f'A2:{last_col}2')
        ws['A2'].font = Font(size=12)
        ws['A2'].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        ws['A3'] = cat_label
        ws.merge_cells(f'A3:{last_col}3')
        ws['A3'].alignment = Alignment(horizontal='center', vertical='center')

        ws['A4'] = "1. 운영수익"
        ws['A4'].font = Font(bold=True, size=12)
        ws['A4'].alignment = Alignment(horizontal='left', vertical='center')
        ws.cell(row=4, column=last_col_num).value = "(단위: 원)"
        ws.cell(row=4, column=last_col_num).font = Font(bold=True, size=12)
        ws.cell(row=4, column=last_col_num).alignment = Alignment(horizontal='right', vertical='center')

        # 5행 헤더
        for col_idx, header in enumerate(headers_row5, 1):
            ws.cell(row=5, column=col_idx).value = header

        for col in merge_cols:
            ws.merge_cells(f'{col}5:{col}6')

        # 6행 헤더
        ws['A6'] = "(관  항  목)"

        # 헤더 스타일 적용 (5-6행) - 굵은 바깥쪽 테두리 + 배경색
        for row in range(5, 7):
            for col in range(1, last_col_num + 1):
                cell = ws.cell(row=row, column=col)
                cell.font = Font(bold=True)
                cell.fill = header_fill
                # A6는 왼쪽 정렬
                if row == 6 and col == 1:
                    cell.alignment = Alignment(horizontal='left', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                # 굵은 바깥쪽 테두리
                top_side = medium if row == 5 else thin
                bottom_side = medium if row == 6 else thin
                left_side = medium if col == 1 else thin
                right_side = medium if col == last_col_num else thin
                cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # "보수" 행 인덱스 찾기 (운영비용 시작점)
        expense_idx = None
        df_values = list(dataframe_to_rows(df, index=False, header=False))
        for i, row in enumerate(df_values):
            if len(row) > 0 and str(row[0]).strip() == "보수":
                expense_idx = i
                break

        # 데이터 작성
        start_row = 7
        current_row = start_row
        revenue_last_row = None  # 수익 표 마지막 행
        expense_header_start = None  # 비용 헤더 시작 행

        for data_idx, row in enumerate(df_values):
            # "보수" 행 앞에 비용 헤더 삽입
            if expense_idx is not None and data_idx == expense_idx:
                # 수익 표 마지막 행 기록
                revenue_last_row = current_row - 1

                # 2개 빈 행
                current_row += 2

                # 페이지 나누기 추가 (2. 운영비용부터 새 페이지)
                ws.row_breaks.append(Break(id=current_row - 1))

                # "2. 운영비용" 헤더
                ws.cell(row=current_row, column=1).value = "2. 운영비용"
                ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
                ws.cell(row=current_row, column=1).alignment = Alignment(horizontal='left', vertical='center')
                ws.cell(row=current_row, column=last_col_num).value = "(단위: 원)"
                ws.cell(row=current_row, column=last_col_num).font = Font(bold=True, size=12)
                ws.cell(row=current_row, column=last_col_num).alignment = Alignment(horizontal='right', vertical='center')
                ws.row_dimensions[current_row].height = 30  # 2. 운영비용 행: 40픽셀
                current_row += 1

                # 5행 헤더 복사
                for col_idx, header in enumerate(headers_row5, 1):
                    ws.cell(row=current_row, column=col_idx).value = header
                for col in merge_cols:
                    col_num = ord(col) - ord('A') + 1
                    ws.merge_cells(f'{col}{current_row}:{col}{current_row+1}')

                # 비용 헤더 시작 행 기록
                expense_header_start = current_row

                # 5행 스타일 적용 - 굵은 바깥쪽 테두리 + 배경색
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    top_side = medium
                    bottom_side = thin
                    left_side = medium if col == 1 else thin
                    right_side = medium if col == last_col_num else thin
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
                current_row += 1

                # 6행 헤더 복사
                ws.cell(row=current_row, column=1).value = "(관  항  목)"

                # 6행 스타일 적용 - 굵은 바깥쪽 테두리 + A열 왼쪽 정렬 + 배경색
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                    if col == 1:
                        cell.alignment = Alignment(horizontal='left', vertical='center')
                    else:
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                    top_side = thin
                    bottom_side = medium
                    left_side = medium if col == 1 else thin
                    right_side = medium if col == last_col_num else thin
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
                current_row += 1

            # 데이터 행 작성 (source_col_indices에 따라 매핑)
            # 관 행 여부 확인 (A열 값이 공백 없이 시작하면 관)
            first_col_value = str(row[0]) if len(row) > 0 and row[0] is not None else ''
            is_gwan = first_col_value and not first_col_value.startswith(' ') and first_col_value.strip() != ''
            # 항 행 여부 확인 (공백 5개로 시작하면 항)
            is_hang = first_col_value.startswith('     ') and not first_col_value.startswith('      ')
            # 합계 행 여부 확인
            is_total = first_col_value.strip() in total_keywords

            for out_idx, src_idx in enumerate(source_col_indices):
                cell = ws.cell(row=current_row, column=out_idx + 1)
                value = row[src_idx] if len(row) > src_idx else ''
                if isinstance(value, (int, float)) and not pd.isna(value):
                    cell.value = value
                    cell.number_format = '#,##0'
                    cell.alignment = Alignment(horizontal='right')
                else:
                    cell.value = value if not pd.isna(value) else ''
                cell.border = border_all
                if is_total:
                    cell.fill = total_fill
                    cell.font = Font(bold=True)
                    if out_idx + 1 == 1:  # A열만 가운데 정렬
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                elif is_gwan or is_hang:
                    cell.fill = gwan_fill

            # 마지막 열: 증감(A-B) 계산 = 당기 - 전기
            cell = ws.cell(row=current_row, column=last_col_num)
            try:
                danggi = row[danggi_src_idx] if len(row) > danggi_src_idx and isinstance(row[danggi_src_idx], (int, float)) and not pd.isna(row[danggi_src_idx]) else 0
                jeongi = row[jeongi_src_idx] if len(row) > jeongi_src_idx and isinstance(row[jeongi_src_idx], (int, float)) and not pd.isna(row[jeongi_src_idx]) else 0
                증감값 = danggi - jeongi
                cell.value = 증감값
                cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal='right')
            except:
                cell.value = ''
            cell.border = border_all
            if is_total:
                cell.fill = total_fill
                cell.font = Font(bold=True)
            elif is_gwan or is_hang:
                cell.fill = gwan_fill
            ws.row_dimensions[current_row].height = 18  # 데이터 행: 24픽셀
            current_row += 1

        # 수익/비용 개별 표 굵은 바깥쪽 테두리 적용
        last_row = current_row - 1

        if revenue_last_row:
            # 수익 표 굵은 바깥쪽 테두리 (5행 ~ revenue_last_row)
            for row in range(5, revenue_last_row + 1):
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=row, column=col)
                    current_border = cell.border
                    top_side = medium if row == 5 else current_border.top
                    bottom_side = medium if row == revenue_last_row else current_border.bottom
                    left_side = medium if col == 1 else current_border.left
                    right_side = medium if col == last_col_num else current_border.right
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

            # 비용 표 굵은 바깥쪽 테두리 (expense_header_start ~ last_row)
            if expense_header_start:
                for row in range(expense_header_start, last_row + 1):
                    for col in range(1, last_col_num + 1):
                        cell = ws.cell(row=row, column=col)
                        current_border = cell.border
                        top_side = medium if row == expense_header_start else current_border.top
                        bottom_side = medium if row == last_row else current_border.bottom
                        left_side = medium if col == 1 else current_border.left
                        right_side = medium if col == last_col_num else current_border.right
                        cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)
        else:
            # 비용이 없는 경우 전체를 하나의 표로 처리
            for row in range(5, last_row + 1):
                for col in range(1, last_col_num + 1):
                    cell = ws.cell(row=row, column=col)
                    current_border = cell.border
                    top_side = medium if row == 5 else current_border.top
                    bottom_side = medium if row == last_row else current_border.bottom
                    left_side = medium if col == 1 else current_border.left
                    right_side = medium if col == last_col_num else current_border.right
                    cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # 열 너비 설정 (A열 제외 130픽셀 = 약 18 width)
        ws.column_dimensions['A'].width = 33
        col_letters = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
        for col in col_letters[:last_col_num - 1]:
            ws.column_dimensions[col].width = 18

        # 인쇄 설정: 가로 방향, 모든 열 한 페이지에 맞추기
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        self._apply_print_layout(ws)
        self._apply_print_margins(ws)

    def _write_trial_balance(self, ws, df, category):
        """합계잔액시산표 시트 작성"""
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.utils.dataframe import dataframe_to_rows

        thin = Side(style='thin')
        medium = Side(style='medium')
        border_all = Border(top=thin, bottom=thin, left=thin, right=thin)
        header_fill = PatternFill(start_color="DCEAFF", end_color="DCEAFF", fill_type="solid")
        gwan_fill = PatternFill(start_color="E5E5E5", end_color="E5E5E5", fill_type="solid")
        marker_fill = PatternFill(start_color="E9D7C3", end_color="E9D7C3", fill_type="solid")
        total_fill = PatternFill(start_color="E3F8D2", end_color="E3F8D2", fill_type="solid")
        code_fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        highlighted_codes = {
            "1110", "1120", "1220", "1240", "1260", "1310", "1320",
            "2110", "2120", "2130", "2140", "2210", "2220", "2410",
            "3110", "3120", "3130", "3160", "3170",
            "4110", "4120", "4210", "4220", "4230", "4240", "4250",
            "4310", "4320", "4330", "4410", "4420",
            "5110", "5120", "5210", "5220", "5230", "5240",
            "5310", "5320", "5330", "5410", "5420",
        }

        cat_label = self._get_category_label(category)
        dates = self._get_fiscal_dates()
        last_col_num = 6

        # 행 높이 설정
        ws.row_dimensions[1].height = 30  # 40픽셀
        ws.row_dimensions[2].height = 30  # 40픽셀
        ws.row_dimensions[3].height = 30  # 40픽셀

        # 헤더 작성
        ws['A1'] = "합 계 잔 액 시 산 표"
        ws.merge_cells('A1:F1')
        ws['A1'].font = Font(bold=True, size=20, underline='single')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')

        ws['A2'] = f"{dates['fund_period']}\n{cat_label}"
        ws.merge_cells('A2:F2')
        ws['A2'].font = Font(size=12)
        ws['A2'].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        ws['F3'] = "(단위: 원)"
        ws['F3'].font = Font(bold=True, size=12)
        ws['F3'].alignment = Alignment(horizontal='right')

        # 4행 헤더
        ws['A4'] = "차  변 ( 왼 쪽 )"
        ws['C4'] = "관  (항)  목"
        ws['E4'] = "대  변 ( 오 른 쪽 )"
        ws.merge_cells('A4:B4')
        ws.merge_cells('C4:D4')
        ws.merge_cells('E4:F4')

        # 5행 헤더
        ws['A5'] = "잔  액"
        ws['B5'] = "합  계"
        ws['C5'] = "코  드"
        ws['D5'] = "과  목"
        ws['E5'] = "합  계"
        ws['F5'] = "잔  액"

        # 헤더 스타일 적용 (4-5행) - 굵은 바깥쪽 테두리 + 배경색
        for row in range(4, 6):
            for col in range(1, 7):
                cell = ws.cell(row=row, column=col)
                cell.font = Font(bold=True)
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal='center', vertical='center')
                # 굵은 바깥쪽 테두리 + 얇은 내부 테두리
                top_side = medium if row == 4 else thin
                bottom_side = medium if row == 5 else thin
                left_side = medium if col == 1 else thin
                right_side = medium if col == last_col_num else thin
                cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # 데이터 작성
        start_row = 6
        df_values = list(dataframe_to_rows(df, index=False, header=False))
        current_row = start_row

        for row in df_values:
            # D열(과목, index 3)이 < 또는 (로 시작하는지 확인
            d_col_value = str(row[3]) if len(row) > 3 and row[3] is not None else ''
            is_category_row = d_col_value.startswith('<') or d_col_value.startswith('(')
            c_col_value = str(row[2]) if len(row) > 2 and row[2] is not None else ''
            is_highlighted_code_row = c_col_value.strip() in highlighted_codes

            for col_idx, value in enumerate(row, 1):
                cell = ws.cell(row=current_row, column=col_idx)
                if isinstance(value, (int, float)) and not pd.isna(value):
                    cell.value = value
                    cell.number_format = '#,##0'
                    cell.alignment = Alignment(horizontal='right')
                elif col_idx == 3:  # 코드 - 가운데 정렬
                    cell.value = value if not pd.isna(value) else ''
                    cell.alignment = Alignment(horizontal='center')
                elif col_idx == 4:  # 과목 - 가운데 정렬
                    cell.value = value if not pd.isna(value) else ''
                    cell.alignment = Alignment(horizontal='center')
                else:
                    cell.value = value if not pd.isna(value) else ''
                cell.border = border_all
                if is_category_row:
                    cell.fill = marker_fill
                elif is_highlighted_code_row:
                    cell.fill = code_fill
            ws.row_dimensions[current_row].height = 18  # 24픽셀
            current_row += 1

        # 표 전체 굵은 바깥쪽 테두리 적용 (4행 ~ 마지막 행)
        last_row = current_row - 1

        # 마지막 행 회색 배경 적용
        for col in range(1, last_col_num + 1):
            ws.cell(row=last_row, column=col).fill = total_fill

        for row in range(4, last_row + 1):
            for col in range(1, last_col_num + 1):
                cell = ws.cell(row=row, column=col)
                current_border = cell.border
                top_side = medium if row == 4 else current_border.top
                bottom_side = medium if row == last_row else current_border.bottom
                left_side = medium if col == 1 else current_border.left
                right_side = medium if col == last_col_num else current_border.right
                cell.border = Border(top=top_side, bottom=bottom_side, left=left_side, right=right_side)

        # 열 너비 설정 (140픽셀 ≈ 19, 100픽셀 ≈ 14, 240픽셀 ≈ 33)
        ws.column_dimensions['A'].width = 19  # 140픽셀
        ws.column_dimensions['B'].width = 19  # 140픽셀
        ws.column_dimensions['C'].width = 14  # 100픽셀
        ws.column_dimensions['D'].width = 33  # 240픽셀
        ws.column_dimensions['E'].width = 19  # 140픽셀
        ws.column_dimensions['F'].width = 19  # 140픽셀

        # 인쇄 설정: 가로 방향, 모든 열 한 페이지에 맞추기
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        self._apply_print_layout(ws)
        self._apply_print_margins(ws)

    def run(self):
        try:
            from openpyxl import Workbook

            excel_file = pd.ExcelFile(self.source_file)
            available_sheets = excel_file.sheet_names
            excel_file.close()

            sheets_to_process = [s for s in self.SHEET_ORDER if s in available_sheets]
            total_sheets = len(sheets_to_process)
            if not total_sheets:raise ValueError("지원되는 재무제표 시트를 찾지 못했습니다.")

            wb = Workbook()
            wb.remove(wb.active)

            for idx, sheet_name in enumerate(sheets_to_process):
                if self._is_cancelled:
                    self.finished.emit(False, "사용자가 취소했습니다.")
                    return

                self.progress.emit(int((idx / total_sheets) * 100), f"처리 중: {sheet_name}")

                # 시트 타입과 구분 추출
                if "자금계산서" in sheet_name:
                    sheet_type = "자금계산서"
                elif "재무상태표" in sheet_name:
                    sheet_type = "재무상태표"
                elif "운영계산서" in sheet_name:
                    sheet_type = "운영계산서"
                else:
                    sheet_type = "합계잔액시산표"

                # 비등록금을 먼저 체크해야 함 (등록금이 비등록금에 포함되므로)
                if "전체" in sheet_name:
                    category = "전체"
                elif "비등록금" in sheet_name:
                    category = "비등록금"
                else:
                    category = "등록금"

                ws = wb.create_sheet(title=sheet_name)

                # 데이터 로드 및 처리
                if sheet_type == "합계잔액시산표":
                    df = self._process_trial_balance(self.source_file, sheet_name)
                    self._write_trial_balance(ws, df, category)
                else:
                    df = pd.read_excel(self.source_file, sheet_name=sheet_name)
                    df = self._process_data(df, sheet_type)
                    if 'Rate' in df.columns:
                        df = df.drop(columns=['Rate'])

                    if sheet_type == "자금계산서":
                        # 자금계산서 열 필터링
                        df = self._filter_fund_columns(df, category)
                        self._write_fund_statement(ws, df, category)
                    elif sheet_type == "재무상태표":
                        self._write_balance_sheet(ws, df, category)
                    else:
                        self._write_income_statement(ws, df, category)

            for idx, ws in enumerate(wb.worksheets):
                if idx % 4 == 3:
                    ws.print_title_rows = '4:5'

            for sheet in wb:
                for row in sheet:
                    for cell in row:
                        if isinstance(cell.value,str) and cell.data_type=='f':cell.data_type='s'
            wb.save(self.dest_file);wb.close()

            self.progress.emit(100, "완료")
            self.finished.emit(True, f"파일이 저장되었습니다:\n{self.dest_file}\n\n포함된 시트: {total_sheets}개")

        except Exception as e:
            self.finished.emit(False, f"파일 저장 중 오류가 발생했습니다:\n{str(e)}")
