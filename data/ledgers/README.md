# 계정별원장 DB

- ledgers.sqlite3: 2025회계연도 거래 164,509건
- ledgers-2024.sqlite3: 2024회계연도 거래 149,426건
- ledgers-2023.sqlite3: 2023회계연도 거래 140,413건
- originals: 변경하지 않은 Excel 원본(27개 열)
- 연도별 import-report.json에 원본 SHA-256, 열 목록, 건수·합계·전 행 대조 결과를 기록합니다.

조회 메뉴는 내장 DB에서 회계연도 목록과 거래를 읽습니다. 원본 Excel 없이도 조회됩니다.
화면에서는 기존 주요 거래 열·필터·상세·Excel 저장 기능을 사용합니다.
화면에 노출하지 않는 원본 열도 DB에 보존합니다.

DB imports에 파일 정보와 원본 열 순서를 저장합니다. entries에는 원본 행 번호,
정규화한 17개 조회 필드와 원본 전체 열을 각각 zlib 압축 UTF-8 JSON 배열(BLOB)로 저장합니다.
payload는 finance_data.LEDGER_COLUMNS 순서, raw_json은 imports.headers_json 순서입니다.
금액은 Decimal 문자열로 저장하며 SQLite 부동소수점 합산을 사용하지 않습니다.

재생성: 저장소 루트에서
`python ledger_database.py "data/ledgers/originals/2025회계연도 계정별원장.xlsx" --year 2025`

`python ledger_database.py "data/ledgers/originals/2024회계연도 계정별원장.xlsx" --year 2024 --database data/ledgers/ledgers-2024.sqlite3`

`python ledger_database.py "data/ledgers/originals/2023회계연도 계정별원장.xlsx" --year 2023 --database data/ledgers/ledgers-2023.sqlite3`
동일 파일 재실행은 중복을 만들지 않으며 같은 연도의 다른 파일은 덮어쓰지 않습니다.
설치본과 소스 배포본은 연도별 조회용 DB를 `data/ledgers`에 포함합니다.
'원장등록'으로 가져온 자료는 바탕화면 `settings/계정별원장.sqlite3`에 회계연도별로 저장합니다.
조회와 분석에서는 같은 연도에 등록한 자료를 우선 사용합니다. 기존 연도를 다시 등록하면 확인 후 해당 연도만 교체합니다.

단위 검증: `python tests/test_ledger_database.py`
