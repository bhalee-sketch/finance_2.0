# 재무제표 SQLite 자료

- `statements.sqlite3`: 2025회계연도 변환 데이터
- `originals/2025회계연도.xlsx`: 변경하지 않은 원본
- `2025-import-report.json`: 시트별 행·열·셀 수와 숫자 열 합계 대조 결과

`workbooks`는 연도·원본 SHA-256, `sheets`는 시트 순서·이름·크기·병합 범위,
`cells`는 1부터 시작하는 행·열 좌표, JSON 값, Excel 자료형·숫자 서식·수식의 캐시 값을 저장합니다.
빈 셀은 저장하지 않으며 시트 크기를 기준으로 복원합니다. 첫 행도 원본 그대로 저장합니다.
숫자는 JSON 숫자이며 식별용 문자열은 문자열로 유지합니다. 전체 Excel 서식은 원본 파일에서 확인합니다.
열 합계는 변환 대조용이며, 소계·합계 행을 포함하므로 업무상 총액을 뜻하지 않습니다.

저장소 루트에서 재실행:

```bash
python scripts/import_statement_db.py data/statements/originals/2025회계연도.xlsx data/statements/statements.sqlite3 --year 2025
```

같은 파일의 재실행은 중복을 만들지 않으며, 같은 연도의 다른 파일은 덮어쓰지 않습니다.
Python과 requirements.txt의 openpyxl이 필요합니다.
재무제표 조회 화면은 프로그램 폴더의 `data/statements/statements.sqlite3`에서
연도 목록과 조회 자료를 읽습니다. 원본 Excel 및 PC 바탕화면 경로는 조회에 필요하지 않습니다.
현재 화면 Excel 저장은 DB 조회 결과를 사용하고, 연도 전체 Excel 저장은 DB에서 만든
임시 Excel을 기존 출력 서식 처리기에 전달한 뒤 임시 파일을 삭제합니다.
프로그램을 다른 PC로 복사하거나 패키징할 때 이 DB 파일도 같은 상대 경로에 포함해야 합니다.
기존 EXE 빌드는 이번 변경에 포함되지 않습니다. 별도의 검증·분석 메뉴의 외부 파일 입력은 그대로입니다.

연결 검증: `python tests/test_statement_database.py`
원본과 표시 자료 일치, 12개 시트 조회·출력, 분리 범위, 원본 접근 없는 DB 조회와
전체 Excel 저장, Qt 조회 화면 전환을 확인합니다.
