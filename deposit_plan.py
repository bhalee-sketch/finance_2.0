"""정기예금 해지계획표: 계좌정보 조회 및 사용자 입력 금액으로 생성."""
from result_paths import result_path
import json
from copy import copy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from account_verifier import account_key
from verifier import excel_rows, number

SUPPORTED = ('.xls','.xlsx','.xlsm')


def period(year, month):
    try:
        y,m=int(year),int(month)
        if not 1900 <= y <= 9999: raise ValueError
        date(y,m,1)
        return y,m
    except (TypeError,ValueError):
        raise ValueError('연도와 월을 올바르게 선택하세요.')


def find_catalog(root, fixed):
    root=Path(root)
    names=('fixed account',) if fixed else ('regular accoount','regular account')
    if not root.is_dir():raise ValueError(f'계좌정보 폴더가 없습니다: {root}')
    candidates=[]
    for p in root.iterdir():
        if p.is_file() and p.stem.lower() in names and p.suffix.lower() in SUPPORTED:candidates.append(p)
        elif p.is_dir() and p.name.lower() in names:
            candidates.extend(f for f in p.iterdir() if f.is_file() and not f.name.startswith('~$') and f.suffix.lower() in SUPPORTED)
    if len(candidates)!=1:raise ValueError(f'{names[0]} 자료가 {len(candidates)}개입니다. Excel 파일을 하나만 두거나 직접 선택하세요.')
    return candidates[0]


def read_catalog(path, fixed):
    path=Path(path)
    if path.suffix.lower() not in SUPPORTED:raise ValueError('계좌정보는 .xls, .xlsx, .xlsm 파일이어야 합니다.')
    required={'bank':('은행명','은행','예치기관'), 'name':('통장명','계좌명','예적금명'), 'account':('출금계좌','계좌번호') if fixed else ('이체계좌','계좌번호')}
    if fixed:required.update({'unit':('회계단위',),'principal':('원금','예금액','계약금액')})
    rows=excel_rows(path,1);mapping=None;result={}
    try:
        for idx,row in enumerate(rows,1):
            if mapping is None:
                headers=[re.sub(r'\s+','',str(v or '')) for v in row]
                tentative={k:next((headers.index(a) for a in aliases if a in headers),None) for k,aliases in required.items()}
                if all(v is not None for v in tentative.values()):mapping=tentative;continue
                if idx>=10:break
                continue
            if not any(v is not None and str(v).strip() for v in row):continue
            get=lambda field:row[mapping[field]] if mapping[field]<len(row) else None
            raw=get('account')
            if raw is None or not str(raw).strip():continue
            if isinstance(raw,(int,float)) and raw==int(raw):raw=str(int(raw))
            key=account_key(raw)
            if not key:raise ValueError(f'{path.name} {idx}행: 계좌번호를 확인하세요.')
            if key in result:raise ValueError(f'{path.name} {idx}행: 중복 계좌입니다.')
            data={'account':str(raw).strip(),'bank':str(get('bank') or ''),'name':str(get('name') or '')}
            if fixed:
                value=get('principal')
                if value is None or str(value).strip()=='':raise ValueError(f'{path.name} {idx}행: 원금이 없습니다.')
                data.update(unit=str(get('unit') or ''),principal=number(value))
                if data['principal']<0:raise ValueError(f'{path.name} {idx}행: 원금이 음수입니다.')
            result[key]=data
    finally:rows.close()
    if mapping is None:raise ValueError(f'{path.name}: 필요한 열 제목을 찾지 못했습니다. '+', '.join(a[0] for a in required.values()))
    if not result:raise ValueError(f'{path.name}: 계좌정보가 없습니다.')
    return result


def plan_entry(fixed, regular, fixed_key, destination, interest_destination, interest, corporate_tax, local_tax, processing_date, year, month, *, interest_accounts=None):
    y,m=period(year,month)
    interest_accounts=regular if interest_accounts is None else interest_accounts
    if fixed_key not in fixed or destination not in regular or (interest_destination and interest_destination not in interest_accounts):raise ValueError('계좌 목록에서 출금·이체 계좌를 선택하세요.')
    try:d=date.fromisoformat(processing_date)
    except (ValueError,TypeError):raise ValueError('처리예정일자를 YYYY-MM-DD로 입력하세요.')
    if (d.year,d.month)!=(y,m):raise ValueError('처리예정일자는 선택한 연도·월 안에 있어야 합니다.')
    values=[]
    for raw in (interest,corporate_tax,local_tax):
        if raw is None or str(raw).strip()=='':raise ValueError('세전이자와 세금을 입력하세요. 없는 금액은 0을 입력하세요.')
        values.append(number(raw))
    gross,corp,local=values
    if min(values)<0 or corp+local>gross:raise ValueError('금액은 음수일 수 없으며 세금 합계가 세전이자를 넘을 수 없습니다.')
    return dict(fixed=fixed[fixed_key].copy(),destination=regular[destination].copy(),interest_destination=interest_accounts[interest_destination].copy() if interest_destination and interest_destination!=destination else None,gross=gross,corp=corp,local=local,date=d)


def load_drafts(path):
    try:
        state=json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None,{}
    last=period(*state['period'])
    if not isinstance(state['drafts'],dict):raise ValueError('저장된 해지 목록 형식이 올바르지 않습니다.')
    for entries in state['drafts'].values():
        for entry in entries:
            entry['date']=date.fromisoformat(entry['date'])
            entry['fixed']['principal']=number(entry['fixed']['principal'])
            for key in ('gross','corp','local'):entry[key]=number(entry[key])
    return last,state['drafts']


def save_drafts(path,period_value,drafts):
    from release_update import atomic_json
    # Serialize exact Decimal amounts and ISO dates, including account snapshots.
    state=json.loads(json.dumps({'period':period_value,'drafts':drafts},default=str))
    atomic_json(path,state)


def save_plan(root,year,month,entries):
    y,m=period(year,month)
    if not str(root).strip():raise ValueError('저장할 기본 폴더를 선택하세요.')
    if not entries:raise ValueError('해지할 계좌를 먼저 추가하세요.')
    keys=[account_key(e['fixed']['account']) for e in entries]
    if len(keys)!=len(set(keys)):raise ValueError('같은 정기예금 계좌를 두 번 추가할 수 없습니다.')
    if any((e['date'].year,e['date'].month)!=(y,m) for e in entries):raise ValueError('목록의 처리예정일과 선택한 연월이 다릅니다. 목록을 다시 확인하세요.')
    wb=load_workbook(Path(__file__).parent/'templates/deposit_plan_style.xlsx');ws=wb.active
    body=[copy(ws.cell(6,c)._style) for c in range(1,16)];totalstyle=[copy(ws.cell(7,c)._style) for c in range(1,16)]
    for row in ws.iter_rows(min_row=6):
        for cell in row:cell.value=None
    ws['A1']=f'{y}년 {m:02}월 정기예금 해지 계획'
    r=6;totals=[Decimal(0)]*7
    def write(row, values):
        ws.row_dimensions[row].height=45
        for c,value in enumerate(values,1):
            cell=ws.cell(row,c,value);cell._style=copy(body[c-1])
            if isinstance(value,str):cell.data_type='s'
            if c in (4,13):cell.number_format='@'
            if c==15:cell.number_format='yyyy-mm-dd'
    for entry in sorted(entries,key=lambda e:e['date']):
        f=entry['fixed'];dest=entry['destination'];other=entry['interest_destination']
        gross,corp,local=entry['gross'],entry['corp'],entry['local'];net=gross-corp-local;total=f['principal']+net
        breakname=lambda s:s.replace('(','\n(',1)
        write(r,[f['bank'],f['unit'],breakname(f['name']),f['account'],f['principal'],gross,corp,local,net,total,dest['bank'],breakname(dest['name']),dest['account'],f['principal'] if other else total,entry['date']])
        if other:
            write(r+1,[None]*10+[other['bank'],breakname(other['name']),other['account'],net,None])
            for col in range(1,11):ws.merge_cells(start_row=r,start_column=col,end_row=r+1,end_column=col)
            ws.merge_cells(start_row=r,start_column=15,end_row=r+1,end_column=15)
        totals=[a+b for a,b in zip(totals,[f['principal'],gross,corp,local,net,total,total])]
        r+=2 if other else 1
    for c in range(1,16):ws.cell(r,c)._style=copy(totalstyle[c-1])
    ws.cell(r,1,'합     계');ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=4)
    for c,value in zip((5,6,7,8,9,10,14),totals):ws.cell(r,c,value)
    ws.row_dimensions[r].height=33
    ws.freeze_panes='E6';ws.print_area=f'A1:O{r}';ws.print_title_rows='1:5'
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    target=result_path('정기예금 해지계획표')
    wb.save(target);wb.close();return target
