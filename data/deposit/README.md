# 원금 이체계좌 DB

`regular_accounts.sqlite3`에 첨부 regular account.xls의 원금 이체계좌 42개를 저장했습니다.
계좌번호는 선행 0과 원래 표시 형식을 유지하는 TEXT로 저장합니다.
은행명·계좌명·검색용 계좌번호 키·원본 순서를 함께 보관합니다.
`originals/regular account.xls`는 변경하지 않은 원본이며 `import-report.json`에 SHA-256과 검증 결과가 있습니다.

정기예금 해지계획표는 기본적으로 이 DB를 읽습니다. 정기예금 출금계좌 자료는 기존 방식으로 별도 선택합니다.
PC의 regular account.xls가 없어도 원금 이체계좌 목록은 사용할 수 있습니다.
자료 설정에서 외부 Excel을 지정하면 해당 실행에서는 지정 파일을 사용할 수 있습니다.
배포 시 이 DB 파일도 같은 상대 경로로 포함해야 합니다.

검증: `python tests/test_deposit_account_database.py`

## 월별 정기예금 원본 갱신

`fixed_accounts.sqlite3`에는 첨부 원본 FIXED.xls를 정규화한 초기 75개 계좌를 담았습니다.
fixed-reference.xls와 계좌번호·은행·회계단위·계좌명·원금을 대조해 모두 일치함을 확인했습니다.
원본의 사용 중 정기예금 가운데 법인 계좌·해약 계좌·원금 없음/0원 계좌를 제외합니다.
은행명은 하나·국민·공제회 등으로, 회계단위는 코드 제거 및 비등록금→비로 정리합니다.
원본 파일은 변경하지 않습니다.

화면의 '자료 설정'에서 매달 원본 파일을 선택합니다. 원본 또는 이미 정리된 fixed 형식을 지원합니다.
사용자 바탕화면의 settings/deposit plan/fixed_accounts.sqlite3에 월별 스냅샷을 저장하고
최근 업로드 목록을 활성화합니다. 이전 스냅샷과 업로드 원본 사본은 보존합니다.
잘못된 원본은 기존 활성 목록을 바꾸지 않습니다. 작성 중인 해지 항목이 있으면
자료 갱신 전에 항목을 정리하도록 안내합니다.

새로고침 버튼은 제거했으며 같은 자리에 계획표 생성 버튼을 배치했습니다.
검증: `python tests/test_fixed_deposit_updates.py`
