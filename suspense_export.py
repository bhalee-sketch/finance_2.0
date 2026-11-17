"""Group-contiguous audit workbooks and comparison against a supplied baseline."""
from collections import defaultdict,Counter
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill
from suspense_data import FIELDS, read_sheet, sheet_names, compact, text, amount, parse_date

EXTRA=('대차차액','매칭번호','판정','매칭유형','매칭근거','원본행','예적금명','회계단위','정산 대상 월·기간','신뢰도','전표확인 여부','row_id','배분 정산금액','차변 잔여','대변 잔여','탐색 상태')


def ordered_group(group,byid):
    key=lambda i:(byid[i].day,byid[i].voucher,byid[i].row,i)
    return sorted(group.credits,key=key)+sorted(group.debits,key=key)


def result_rows(result,groups=None,unmatched=False):
    ledger=result['ledger'];byid={t.row_id:t for t in ledger['rows']};validation=result['validation'];out=[]
    used=set().union(*(c.ids for c in result['groups'])) if result['groups'] else set()
    def line(t,group=None):
        residual=validation['residual'][t.row_id]
        state=group.state if group else '탐색 미완료' if t.row_id in result['incomplete'] else '미매칭'
        return [t.voucher,t.day.isoformat(),t.department,t.counterparty,t.debit,t.credit,t.description,
                t.debit-t.credit,group.id if group else '',state,group.kind if group else '',
                ' / '.join(group.reasons if group else t.warnings),t.row,t.account,t.unit,
                str(t.months or t.period or ''),group.score if group else '', '사용자 승인' if group and group.state=='사용자 승인' else '필요' if state!='자동매칭' else '자동 판정',
                t.row_id,validation['allocations'].get(t.row_id,0),residual[0],residual[1],result.get('search_status',{}).get(group.id,'') if group else state]
    if unmatched:
        for t in ledger['rows']:
            d,c=validation['residual'][t.row_id]
            if t.row_id not in used or d or c:out.append(line(t))
        return out
    for group in result['groups'] if groups is None else groups:
        for identity in ordered_group(group,byid):out.append(line(byid[identity],group))
        alloc=dict(group.allocations) if group.allocations else {i:byid[i].value for i in group.ids}
        d=sum(alloc[i] for i in group.debits);c=sum(alloc[i] for i in group.credits)
        out.append(['그룹 정산합계','','','',d,c,'배분 정산금액 기준',d-c,group.id,group.state])
    return out


def department_rows(result):
    values=defaultdict(lambda:[0,0,0,0])
    for t in result['ledger']['rows']:
        d,c=result['validation']['residual'][t.row_id]
        v=values[t.department];v[0]+=1;v[1]+=d;v[2]+=c;v[3]+=bool(d or c)
    return [(dept,*v,v[1]-v[2]) for dept,v in sorted(values.items())]


def summary(result):
    rows=result['ledger']['rows'];groups=result['groups'];v=result['validation'];counts=Counter()
    used=set()
    for group in groups:counts[group.state]+=len(group.ids);used.update(group.ids)
    residual_count=sum(bool(d or c) for d,c in v['residual'].values())
    return [('규칙 버전',result['version']),('입력 SHA256',result['ledger']['hash']),('원본 거래 건수',len(rows)),('선택 시트 전체 행',result['ledger'].get('source_count',len(rows))),('계정 추출 기준',result['ledger'].get('account_filter','선택 시트 전체')),
            ('자동매칭 행 수',counts['자동매칭']),('조건부매칭 행 수',counts['조건부매칭']),('사용자 승인 행 수',counts['사용자 승인']),
            ('검토후보 그룹 수',len(result['suggestions'])),('미매칭 고유 행 수',len(rows)-len(used)),('잔여 금액이 있는 행 수',residual_count),
            ('정산 그룹 수',len(groups)),('전체 연결률(조건부 포함)',f'{len(used)/max(1,len(rows))*100:.2f}%'),
            ('원본 차변합계',v['debit']),('원본 대변합계',v['credit']),('잔여 순대차잔액(차변−대변)',v['net']),
            ('탐색 미완료 행',len(result['incomplete'])),('검산','통과' if v['ok'] else '실패'),
            ('처리 상태','탐색 미완료·검토 필요' if result['incomplete'] else '검산 완료·조건부는 확정 아님')]


def export_result(result,path,baseline=None):
    book=Workbook();book.remove(book.active)
    def sheet(name,headers,rows):
        ws=book.create_sheet(name);ws.append(list(headers))
        for row in rows:ws.append(list(row))
        ws.freeze_panes='H2' if list(headers)[:7]==list(FIELDS) else 'A2'
        ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='D9E7F3')
        for row in ws:
            for cell in row:
                if isinstance(cell.value,str):cell.data_type='s'
                elif isinstance(cell.value,(int,float)):cell.number_format='#,##0'
        from openpyxl.utils import get_column_letter
        for i,header in enumerate(headers,1):ws.column_dimensions[get_column_letter(i)].width=48 if header in ('적요','매칭근거') else 23
        return ws
    columns=FIELDS+EXTRA
    sheet('전체 매칭',columns,result_rows(result))
    for title in ('자동매칭','조건부매칭','사용자 승인'):
        sheet(title,columns,result_rows(result,[g for g in result['groups'] if g.state==title]))
    sheet('미매칭 잔여',columns,result_rows(result,unmatched=True))
    byid={t.row_id:t for t in result['ledger']['rows']}
    checks=[]
    for g in result['groups']:
        amounts=dict(g.allocations) if g.allocations else {i:byid[i].value for i in g.ids}
        c=sum(amounts[i] for i in g.credits);d=sum(amounts[i] for i in g.debits)
        checks.append((g.id,g.state,g.kind,len(g.ids),d,c,d-c,g.score,' / '.join(g.reasons)))
    sheet('매칭 그룹검산',('매칭번호','판정','유형','행 수','차변','대변','차이','점수','근거'),checks)
    sheet('부서별 미매칭',('부서','거래 수','차변 잔여','대변 잔여','잔여 건수','순잔액'),department_rows(result))
    sheet('추가 검토후보',('후보번호','유형','점수','판정','대변 row_id','차변 row_id','근거'),[(c.id,c.kind,c.score,c.state,','.join(c.credits),','.join(c.debits),' / '.join(c.reasons)) for c in result['suggestions']])
    sheet('후보 원본행 명세',('후보번호','row_id','원본행','구분','금액'),[(c.id,i,byid[i].row,byid[i].side,byid[i].value) for c in result['suggestions'] for i in ordered_group(c,byid)])
    sheet('단계별 매칭실적',('단계','건수'),result['stages'])
    sheet('재배정 이력',('동작','원본 row_id','근거'),result['history'])
    sheet('검증요약',('항목','값'),summary(result)+[(name,'통과' if ok else '실패') for name,ok in result['validation']['checks']])
    sheet('원본 데이터 보존',('원본 행',)+tuple(f'열{i+1}' for i in range(max(map(len,result['ledger']['raw_rows']),default=0))),[(i,*row) for i,row in enumerate(result['ledger']['raw_rows'],1)])
    sheet('입력 제외 표시행',('원본 행','사유'),result['ledger']['excluded'])
    import json
    sheet('승인·예외 설정',('구분','설정 JSON'),[(key,json.dumps(value,ensure_ascii=False,default=str)) for key in ('aliases','actions','alias_events') for value in result['settings'].get(key,[])])
    if baseline:sheet('기존 결과 비교',('항목','기존','신규','상세'),baseline)
    path=Path(path)
    if path.resolve()==Path(result['ledger']['path']).resolve():raise ValueError('원본 원장에는 저장할 수 없습니다.')
    book.save(path);book.close();return path


def compare_baseline(result,path):
    """Compare row IDs when available; otherwise use full evidence multisets, flagging duplicates."""
    import hashlib
    names=sheet_names(path);name='전체 매칭' if '전체 매칭' in names else names[0]
    data=read_sheet(path,name);header=None
    for i,row in enumerate(data[:50]):
        cols={compact(v):j for j,v in enumerate(row)}
        if '매칭번호' in cols and all(compact(k) in cols for k in FIELDS):header=i;break
    if header is None:return [('비교 불가','','','기존 파일에 첫 7개 원장 필드와 매칭번호가 필요합니다. 건수만으로 성공 처리하지 않습니다.')]
    source=result['ledger']['rows'];byid={t.row_id:t for t in source};byrow={t.row:t for t in source}
    exact='rowid' in cols
    optional=[key for key in ('예적금명','회계단위') if compact(key) in cols]
    def signature(t):
        base=(t.voucher,t.day.isoformat(),t.department,t.counterparty,t.debit,t.credit,t.description)
        return base+tuple(t.account if key=='예적금명' else t.unit for key in optional)
    pools=defaultdict(list)
    for t in source:pools[signature(t)].append(t)
    def token(t):
        if exact:return t.row_id
        return '거래내용:'+hashlib.sha256(repr(signature(t)).encode()).hexdigest()[:20]
    old=defaultdict(list);states={};errors=[];seen_rows=Counter();seen_signatures=Counter();matched_evidence=[];unmatched_tokens=[]
    def parse(rows,head,matching):
        mapping={compact(v):j for j,v in enumerate(head)}
        for row in rows:
            def get(key):
                col=mapping.get(compact(key));return row[col] if col is not None and col<len(row) else None
            if text(get('전표정보'))=='그룹 정산합계':continue
            group=text(get('매칭번호'))
            if matching and not group:continue
            try:
                sig=(text(get('전표정보')),parse_date(get('회계일자')).isoformat(),text(get('부서명')),text(get('거래선')),amount(get('차변')),amount(get('대변')),text(get('적요')))+tuple(text(get(key)) for key in optional)
            except ValueError as exc:errors.append(('기존 원본값 확인',group,'',str(exc)));continue
            identity=text(get('rowid'));possible=pools.get(sig,[])
            if exact and identity in byid:
                t=byid[identity]
                if (sig[4],sig[5])!=(t.debit,t.credit):errors.append(('원본 금액 불일치',str(sig[4:6]),str((t.debit,t.credit)),identity))
                if sig!=signature(t):errors.append(('원본값 불일치',group,'',identity))
            elif exact or not possible:
                errors.append(('원본 식별 불가',group,'',repr(sig)));continue
            else:t=possible[0]  # Only its content token is used; duplicate row identity remains unresolved.
            key=token(t);seen_signatures[key]+=1
            original=text(get('원본행') or get('원본행번호') or identity)
            if original:seen_rows[original]+=1
            if matching:
                old[group].append(key);states[group]=text(get('판정'));matched_evidence.append(sig)
            else:unmatched_tokens.append(key)
    parse(data[header+1:],data[header],True)
    if '미매칭 잔여' in names:
        unmatched=read_sheet(path,'미매칭 잔여');parse(unmatched[1:],unmatched[0],False)
    expected=Counter(token(t) for t in source)
    duplicates=sum(n-1 for n in seen_rows.values() if n>1)
    original_checks=[('원본 거래 건수',sum(seen_signatures.values()),len(source),'매칭+미매칭 전체 검증'),
                     ('중복 원본행',duplicates,0,'기존 결과의 원본행 번호 기준'),
                     ('원본 거래 내용 누락',sum((expected-seen_signatures).values()),0,'중복 거래 개수 포함'),
                     ('원본 거래 내용 초과',sum((seen_signatures-expected).values()),0,'중복 거래 개수 포함')]
    ambiguous=sum(len(values) for values in pools.values() if len(values)>1) if not exact else 0
    new=defaultdict(list);oldsets=defaultdict(list)
    for g in result['groups']:new[tuple(sorted(token(byid[i]) for i in g.ids))].append(g)
    for group,ids in old.items():oldsets[tuple(sorted(ids))].append(group)
    report=[('대조 방식','row_id' if exact else '전표·날짜·부서·거래선·금액·적요·계좌·회계단위','', '행 번호가 바뀐 파일은 거래내용과 중복 개수로 대조합니다.'),
            ('원본행 식별 유의',ambiguous,'','동일 내용 복수 행은 개별 행 연결을 확정하지 않습니다.'),
            ('그룹 수',len(old),len(result['groups']),'그룹별 거래 집합·중복 개수 비교')]+original_checks+errors
    same=0
    for ids in sorted(set(oldsets)|set(new)):
        before=sorted(oldsets.get(ids,[]));after=sorted(new.get(ids,[]),key=lambda g:g.id)
        same+=min(len(before),len(after))
        for i in range(max(len(before),len(after))):
            oldid=before[i] if i<len(before) else '';g=after[i] if i<len(after) else None
            if not oldid or not g or states.get(oldid,'')!=g.state:
                report.append(('연결·판정 차이',oldid+':'+states.get(oldid,''),g.id+':'+g.state if g else '',','.join(ids)))
    report.insert(3,('동일 거래집합 그룹',same,same,'중복 내용 거래는 개별 행 동등성 미확정'))
    oldused=Counter(key for ids in old.values() for key in ids);newused=Counter(token(byid[i]) for g in result['groups'] for i in g.ids)
    report.append(('미매칭 원본행',repr(sorted((expected-oldused).items())),repr(sorted((expected-newused).items())),'거래 토큰·건수 목록'))
    return report


def export_unmatched(result,path):
    """One-sheet residual list only; preserves source amounts and separates search limits."""
    if not result['validation']['ok']:raise ValueError('검산 실패: 미매칭 목록을 정상 결과로 내보낼 수 없습니다.')
    path=Path(path)
    if path.resolve()==Path(result['ledger']['path']).resolve():raise ValueError('원본 원장에는 저장할 수 없습니다.')
    from openpyxl.styles import Alignment
    from openpyxl.comments import Comment
    from openpyxl.utils import get_column_letter
    v=result['validation'];used={i for g in result['groups'] for i in g.ids}
    candidate_counts=Counter(i for c in result['suggestions'] for i in c.ids)
    incomplete=set(result['incomplete'])
    rows=[t for t in result['ledger']['rows'] if t.row_id not in used or any(v['residual'][t.row_id])]
    rows.sort(key=lambda t:(t.department,t.day,t.voucher,t.row,t.row_id))
    book=Workbook();ws=book.active;ws.title='미매칭 잔여'
    columns=FIELDS+('잔여 차변','잔여 대변','판정','확인 사유','예적금명','회계단위','원본행','row_id')
    ws.append(list(columns))
    for t in rows:
        d,c=v['residual'][t.row_id]
        state='부분정산 잔여' if v['allocations'].get(t.row_id,0) else '탐색 미완료' if t.row_id in incomplete else '미매칭'
        reason=' / '.join(t.warnings)
        if state=='탐색 미완료':reason='탐색 범위·충돌 최적화 제한: 정산 불가로 확정한 거래가 아닙니다.'
        elif state=='부분정산 잔여':reason='승인 배분 후 남은 금액입니다.'
        elif not reason:reason='경쟁·미선택 후보가 있어 연결하지 않았습니다.' if candidate_counts[t.row_id] else '현재 조건에서 대응 거래를 찾지 못했습니다.'
        ws.append([t.voucher,t.day.isoformat(),t.department,t.counterparty,t.debit,t.credit,t.description,d,c,state,reason,t.account,t.unit,t.row,t.row_id])
    for row in ws:
        for cell in row:
            if isinstance(cell.value,str):cell.data_type='s'
            elif isinstance(cell.value,(int,float)):cell.number_format='#,##0;[Red]-#,##0;–'
            cell.alignment=Alignment(vertical='top')
    for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='243C57')
    widths=[25,14,25,25,18,18,65,18,18,19,65,30,18,12,28]
    for i,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=width
    for row in ws.iter_rows(min_row=2):
        if row[9].value=='탐색 미완료':row[9].fill=PatternFill('solid',fgColor='FFF0D4')
    ws.freeze_panes='E2';ws.auto_filter.ref=ws.dimensions
    ws['J1'].comment=Comment(f"규칙 {result['version']}\n입력 SHA256: {result['ledger']['hash']}\n미매칭/잔여 {len(rows):,}행. 탐색 미완료는 아직 검토가 필요한 거래입니다.\n매칭된 거래와 원본 전체는 이 파일에 포함하지 않았습니다.",'Work Space')
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.print_title_rows='1:1'
    book.save(path);book.close();return path


def export_visible_view(path,title,headers,rows):
    """Export the visible column order and all filtered rows, preserving codes as text."""
    import re
    from openpyxl.utils import get_column_letter
    book=Workbook();ws=book.active;ws.title=re.sub(r'[\\/*?:\[\]]','_',title)[:31] or '현재화면'
    ws.append(list(headers))
    numeric={'번호','원본행','금액','정산금액','잔액','차변','대변','배분','차변 잔여','대변 잔여','잔여 건수','순잔액(대변−차변)'}
    for values in rows:
        converted=[]
        for header,value in zip(headers,values):
            if header in numeric and isinstance(value,str) and re.fullmatch(r'-?\d[\d,]*',value):value=int(value.replace(',',''))
            converted.append(value)
        ws.append(converted)
    for row in ws:
        for cell in row:
            if isinstance(cell.value,str):cell.data_type='s'
            elif isinstance(cell.value,(int,float)):cell.number_format='#,##0;[Red]-#,##0;0'
    for cell in ws[1]:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='D9E7F3')
    from table_layout import format_excel
    format_excel(ws,headers)
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    book.save(path);book.close();return Path(path)
