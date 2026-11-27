"""Tie the closing debt note to statement accounts, then match registered schedules."""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zipfile import BadZipFile

from appendix_data import load_sheet
from dashboard_finance import SCOPES, complete_sum, year_end
from loan_manager import active_loan_archive, find_loan_files, parse_date, read_rows, uploaded_loan_sources
from statement_analysis import optional_money, normalize

NOTE_DB = Path(__file__).resolve().parent/'data'/'appendices'/'balance.sqlite3'


def iso(value):
    return value.date() if isinstance(value, datetime) else value if isinstance(value, date) else parse_date(value)


def schedules(archive):
    result = []
    with uploaded_loan_sources(archive) as folder:
        for path in find_loan_files(folder):
            rows, epoch = read_rows(path)
            dates = []
            for row in rows:
                due = parse_date(row[1], epoch)
                if due:
                    dates.append((due, optional_money(row[2]), optional_money(row[5]), parse_date(row[10], epoch)))
            # The source's final principal row (C + P), also used by loan_manager.analyze.
            total = next((complete_sum((optional_money(r[2]), optional_money(r[15])))
                          for r in reversed(rows) if not r[0] and not r[1] and r[2] is not None), None)
            if dates and total is not None:
                result.append((path.stem, total, max(r[0] for r in dates), dates))
    return result


def read_note(year):
    values = load_sheet(NOTE_DB, '단기(장기)차입금명세서', str(year))
    titles = [normalize(x).replace('/','') for x in values['headers']]
    columns = {title: index for index, title in enumerate(titles)}
    for required in ('계정과목', '기말잔액'):
        if required not in columns:
            raise ValueError(f'차입금명세서에서 {required} 열을 찾지 못했습니다.')
    rows = []
    for rec in values['records']:
        def cell(label):
            return rec['values'][columns[label]] if label in columns else None

        account = normalize(cell('계정과목'))
        if account not in ('유동성장기부채', '단기차입금', '장기차입금'):
            continue
        rows.append(dict(permit=cell('허가근거'), lender=cell('차입처'), account=account,
                         issued=iso(cell('차입내역연월일')), principal=optional_money(cell('차입내역금액')),
                         balance=optional_money(cell('기말잔액')), rate=cell('지급이자율'), note_name=cell('항목'),
                         term=iso(cell('상환기한')), maturity=iso(cell('만기일')), scope=normalize(cell('상환회계'))))
    return rows


def detail_for(data, year, scope, storage):
    archive = active_loan_archive(storage)
    parts = tuple(data.periods.get((year,s)).balance.loan_parts if data.periods.get((year,s))
                  and data.periods[year,s].balance else (None,None) for s in SCOPES)
    archive_stamp = archive.stat().st_mtime_ns if archive.exists() else None
    note_stamp = NOTE_DB.stat().st_mtime_ns if NOTE_DB.exists() else None
    return _detail(year, scope, parts, archive, archive_stamp, note_stamp)


@lru_cache(maxsize=12)
def _detail(year, scope, all_parts, archive, archive_stamp, note_stamp):
    cutoff = year_end(year)
    home = complete_sum(all_parts[SCOPES.index(scope)])
    if note_stamp is None:
        return [], [], {}, None, ['차입금 부속명세서 자료 없음']
    try:
        note = read_note(year)
    except ValueError as exc:
        if str(exc) == '저장된 부속명세서가 없습니다.':
            return [], [], {}, None, ['해당 연도 차입금 부속명세서 자료 없음']
        raise
    if not note:
        return [], [], {}, None, ['해당 연도 차입금 명세가 없습니다.']
    amounts = tuple(complete_sum(r['balance'] for r in note if (r['account']=='장기차입금')==long)
                    for long in (False,True))
    alerts = []
    contracts = []
    # Current portions and long-term residuals are different closing balances.
    # Group only when permit, lender, repayment term and account scope identify one loan.
    def key(r):
        return r['permit'], r['lender'], r['term'], r['scope']
    for r in note:
        family = [entry for entry in note if key(entry)==key(r)]
        heads = [x for x in family if x['account']=='장기차입금']
        portions = [x for x in family if x['account']=='유동성장기부채']
        paired = bool(r['permit'] and r['lender'] and r['term']) and len(heads)==len(portions)==1
        if paired and r['account']=='유동성장기부채':
            continue
        components = [r]
        if paired and r is heads[0]:
            components.extend(portions)
        included = []
        for item in components:
            account = 1 if item['account']=='장기차입금' else 0
            if scope!='전체' and item['scope'] not in (scope,scope+'회계'):
                if item['scope'] in ('등록금','비등록금','등록금회계','비등록금회계'):
                    continue
                if item['scope'] not in ('교비','교비회계','전체'):
                    if '상환회계 미등록 · 회계별 귀속 확인 필요' not in alerts:
                        alerts.append('상환회계 미등록 · 회계별 귀속 확인 필요')
                    continue
                # Allocate unlabelled individual loans only when one account owns
                # the entire reconciled, nonnegative account and the other is zero.
                own = all_parts[SCOPES.index(scope)][account]
                other = all_parts[2 if scope=='등록금' else 1][account]
                nonnegative = all(n['balance'] is not None and n['balance'] >= 0 for n in note)
                if nonnegative and own == 0 and other is not None and other == amounts[account] == all_parts[0][account]:
                    continue
                if own is None or own != amounts[account] or own != all_parts[0][account] or other != 0 or not nonnegative:
                    if '명세서의 상환회계가 교비로만 등록되어 회계별 귀속 확인이 필요합니다.' not in alerts:
                        alerts.append('명세서의 상환회계가 교비로만 등록되어 회계별 귀속 확인이 필요합니다.')
                    continue
            included.append(item['balance'])
        if included:
            contracts.append(dict(r, balance=complete_sum(included)))
    scope_incomplete = bool(alerts)
    files = []
    if contracts:
        if archive_stamp is None:
            alerts.append('상환 원자료 미등록')
        else:
            try:
                files = schedules(archive)
            except (BadZipFile, OSError, ValueError) as exc:
                alerts.append(f'상환일정 조회 실패 · {exc}')
    matches = []
    for c in contracts:
        matches.append([f for f in files if f[1]==c['principal'] and
                        ((c['issued'] and c['issued'].isoformat() in f[0]) or (c['term'] and f[2]==c['term']))])
    grouped = defaultdict(list)
    upcoming = []
    unmatched = False
    for c, candidates in zip(contracts,matches):
        c['name'] = c['note_name'] or '미등록'
        if len(candidates)==1 and sum(candidates[0] in others for others in matches)==1:
            name, _, _, entries = candidates[0]
            c['name'] = name
            for due, principal, interest, paid in entries:
                if due > cutoff and (not paid or paid > cutoff):
                    upcoming.append((due, c['lender'] or '미등록', name, principal, interest, complete_sum((principal,interest))))
        else:
            unmatched = True
        grouped[c['lender'] or '미등록'].append(c['balance'])
    by_lender = {k:complete_sum(v) for k,v in grouped.items()}
    total = complete_sum(by_lender.values()) if by_lender else Decimal(0) if home==0 and not alerts else None
    if scope_incomplete:
        total = None
    if unmatched:
        alerts.append('차입 건 매칭 불가 · 해당 건의 상환일정 미등록')
    if any(c['maturity'] and c['term'] and c['term']!=c['maturity'] for c in contracts):
        alerts.append('명세서의 만기일과 상환기한이 다른 건이 있어 두 날짜를 함께 표시합니다.')
    return contracts, sorted(upcoming,key=lambda r:r[0]), by_lender, total, alerts
