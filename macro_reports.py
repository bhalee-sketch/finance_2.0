"""원본 VBA의 분류 규칙을 적용하는 세 가지 보고서. 매크로는 실행하지 않는다."""
from result_paths import result_path
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from verifier import excel_rows
from account_verifier import amount

TITLES = {'expense':'지출계좌별 재원코드 검증', 'donation':'기부금계좌잔액 검증', 'fund':'임의기금 지출 재원별 검증'}
FOLDERS = {'expense':'expense verification','donation':'donation verification','fund':'fund verification'}
def text(v):
    return '' if v is None else str(v).strip()
def norm(v):
    return text(v).replace(' ', '')
def read_source(path, kind):
    rows=list(excel_rows(Path(path),1))
    if not rows: raise ValueError('빈 파일입니다.')
    required={'재원','관','목','차변','대변'} if kind=='fund' else set()
    header=None
    for i,row in enumerate(rows[:50]):
        labels=[text(v) for v in row]
        if required and required.issubset(labels): header=i; break
        if not required and any(labels): header=i; break
    if header is None: raise ValueError('필수 열(재원, 관, 목, 차변, 대변)을 찾을 수 없습니다.')
    labels=[text(v) for v in rows[header]]
    if kind == 'donation' and not any(re.search(r'[가-힣]', h) for h in labels):
        raise ValueError('기부금 자료의 한글 열 제목을 읽을 수 없습니다. 원본 XLS 파일을 선택하거나 Excel에서 XLSX로 다시 저장한 뒤 선택하세요.')
    minimum={'expense':22,'donation':16,'fund':1}[kind]
    if len(labels)<minimum: raise ValueError(f'원본은 최소 {minimum}열이 필요합니다. 다운로드한 원자료를 선택하세요.')
    data=[list(r)+[None]*max(0,len(labels)-len(r)) for r in rows[header+1:] if any(text(v) for v in r)]
    return labels,data

def expense_accounts(path):
    _,rows=read_source(path,'expense')
    return sorted({text(r[21]) for r in rows if text(r[21])})

def classify(kind, headers, rows, mode='교비비등록금', accounts=(), exclude_unpaid=False, account_unit=None):
    groups={}; stats=Counter(); sums=[]; hidden=set()
    if kind=='expense':
        if not accounts: raise ValueError('처리할 계좌를 하나 이상 선택하세요.')
        if '재원' not in headers: raise ValueError('원본에 재원 열이 없습니다.')
        drop={'계정코드','대사업','중사업','소사업','사업코드','거래선코드','예적금코드','재원구분','전표구분'}
        keep=[i for i,h in enumerate(headers) if h not in drop]
        hidden={'세목','계정명','거래선명','적요'}
        account_col=next((headers.index(h) for h in ('예적금명','계좌명') if h in headers),21)
        if account_unit is not None and '회계단위' not in headers:
            raise ValueError('원본에 회계단위 열이 없어 선택한 회계단위를 확인할 수 없습니다.')
        for row in rows:
            if account_unit is not None and text(row[headers.index('회계단위')]) != account_unit:
                stats['선택 외 회계단위']+=1;continue
            if text(row[account_col]) not in accounts: stats['선택 외 계좌']+=1; continue
            if not text(row[headers.index('재원')]).replace('\xa0',''): stats['재원 없음']+=1; continue
            groups.setdefault(text(row[account_col]),[]).append([row[i] for i in keep])
        out=[headers[i] for i in keep]
        for values in groups.values(): values.sort(key=lambda r:text(r[out.index('재원')]))
    elif kind=='fund':
        required={'재원','관','목','차변','대변'}
        if not required.issubset(headers): raise ValueError('재원, 관, 목, 차변, 대변 열이 필요합니다.')
        drop={'번호','전표구분','계정코드','사업코드','대사업','중사업','소사업','거래처코드','예적금코드','재원구분'}
        keep=[i for i,h in enumerate(headers) if h and h not in drop];out=[headers[i] for i in keep]
        groups={f'임의_{s}':[] for s in ('연구','건축','장학','기타')}
        for row in rows:
            if any(s in text(row[headers.index('관')]) for s in ('유동자산','투자와기타자산','교육연수','기본금','기본금을적립')): stats['제외 관']+=1;continue
            fund=text(row[headers.index('재원')]);category=next((s for s in ('연구','건축','장학','기타') if s in fund and '임의' in fund),None)
            if category is None: stats['미분류']+=1;continue
            if exclude_unpaid and any(s in text(row[headers.index('목')]) for s in ('미지급금','각종세금예수금','가수금')): stats['미지급 등 제외']+=1;continue
            groups['임의_'+category].append([row[i] for i in keep])
        sums=[out.index('차변')]
    else:
        grad='대학원' in mode
        names=('국제법률장학금','국제법률대여장학금','국제법률기타수익','대학원기부금') if grad else ('교비일반장학','CCF후원','공시학부','연구소기부','비서실','지정기부금','대학교회','캐피탈캠페인','현물기부금')
        groups={s:[] for s in names};keep=[i for i in range(len(headers)) if i not in (16,11,9,8,5,4)];out=[headers[i] for i in keep];sums=[10]
        for row in rows:
            if not text(row[15]): stats['잔액 공란']+=1;continue
            k,m=norm(row[10]),norm(row[12]);values=[row[i] for i in keep]
            get=lambda i:norm(values[i]) if i<len(values) else ''
            if grad:
                category='국제법률장학금' if m=='국제법률대학원' else '대학원기부금'
                donor=get(1)
                if any(s in donor for s in ('이용지','김혜언','윤정민')): category='국제법률대여장학금'
                elif '법무법인' in donor and '화우' in donor: category='국제법률기타수익'
            else:
                category='지정기부금'
                if '현물기부금' in k: category='현물기부금'
                else:
                    for needle,target in (('산학연구지원팀','연구소기부'),('학생지원팀','교비일반장학'),('비서실','비서실'),('공간환경시스템공학부','공시학부'),('대학교회','대학교회')):
                        if needle in m: category=target;break
                if category=='교비일반장학':
                    if get(13) in ('(지정)기타지정기부금','(지정)총학생회기부금'): category='지정기부금'
                    elif get(13)=='(지정)장학기부금(CCF)': category='CCF후원'
                if category=='지정기부금' and '현물기부금' in get(12): category='현물기부금'
                # 최종 지정기부금만 계정과목 접두사로 재분류한다.
                account_col = next((i for i,h in enumerate(out) if norm(h)=='계정과목'), 11)
                account = text(values[account_col]) if account_col < len(values) else ''
                if category=='지정기부금' and account.startswith(('캐피탈_', '캐피탈캠페인_')):
                    category='캐피탈캠페인'
            groups[category].append(values)
        for values in groups.values(): values.sort(key=lambda r:text(r[3]))
    return out,groups,stats,sums,hidden

def append(ws, values):
    ws.append(values)
    for cell in ws[ws.max_row]:
        if isinstance(cell.value,str): cell.data_type='s'

def run_report(path,kind,**options):
    path=Path(path);headers,rows=read_source(path,kind)
    out,groups,stats,sums,hidden=classify(kind,headers,rows,**options)
    wb=Workbook();summary=wb.active;summary.title='처리요약'
    for row in [('항목','내용'),('업무',TITLES[kind]),('원본',path.name),('원본 행',len(rows)),('결과 행',sum(map(len,groups.values()))),('안내','원본 매크로의 분류·집계 결과입니다. 계좌잔액 대사나 재원코드 정오 판정은 수행하지 않습니다.')]: append(summary,row)
    if kind=='expense':
        if options.get('account_unit') is not None:append(summary,('선택 회계단위',options['account_unit']))
        append(summary,('선택 계좌 수',len(options.get('accounts',()))))
        for account in options.get('accounts',()):
            if account not in groups:append(summary,(f'결과 없음: {account}',0))
    for name,count in stats.items():append(summary,(name,count))
    for name,values in groups.items():
        base=re.sub(r'[\\/*?:\[\]]','_',name).strip("'")[:31] or '계좌';candidate=base;n=2
        while candidate.lower() in {s.lower() for s in wb.sheetnames}:
            candidate=base[:31-len(str(n))-1]+'_'+str(n);n+=1
        ws=wb.create_sheet(candidate);append(ws,out);append(summary,(name,len(values)))
        for row in values:
            row=list(row)
            for i,value in enumerate(row):
                if out[i]=='전표번호': row[i]=str(int(value)) if isinstance(value,(float,int)) else text(value)
                elif out[i] in ('차변','대변') or (kind=='donation' and i in (6,8,9,10)):
                    number=amount(value)
                    if number is not None: row[i]=number
            append(ws,row)
        if values and sums:
            total=[None]*len(out)
            for col in sums:
                total[max(0,col-1)]='합계';total[col]=sum((amount(r[col]) or 0) for r in values)
            append(ws,total)
        for i,h in enumerate(out,1):
            if h in hidden: ws.column_dimensions[get_column_letter(i)].hidden=True
        if kind=='donation':
            for i,pixels in enumerate((160,240,120,82,90,100,110,200,105,132,90,228,88,180),1):ws.column_dimensions[get_column_letter(i)].width=pixels/7
            ws.sheet_view.zoomScale=85
        ws.auto_filter.ref=f'A1:{get_column_letter(len(out))}{len(values)+1}'
    for ws in wb:
        ws.freeze_panes='A2'
        for c in ws[1]:c.fill=PatternFill('solid',fgColor='D9E1F2');c.font=Font(bold=True)
        for col in ws.columns:
            letter=col[0].column_letter
            if letter not in ws.column_dimensions:ws.column_dimensions[letter].width=min(45,max(14,max(len(text(c.value)) for c in col)*1.5+2))
            for c in col[1:]:
                if c.data_type=='n':c.number_format='#,##0' if c.value is None or c.value == int(c.value) else '#,##0.##########'
    if kind=='expense':
        from expense_report_style import apply_expense_columns
        apply_expense_columns(wb)
    if kind=='donation':
        from donation_report_style import apply_donation_sample
        apply_donation_sample(wb)
    target=result_path(TITLES[kind]);wb.save(target);wb.close();return target
