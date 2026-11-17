"""Lossless ledger ingestion and deterministic comparison fields for suspense review."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import re
import unicodedata
from openpyxl import load_workbook
from verifier import open_legacy_workbook

VERSION = 'suspense-1.11'
FIELDS = ('전표정보','회계일자','부서명','거래선','차변','대변','적요')
ALIASES = {
 '전표정보': ('전표정보','전표번호','전표'), '회계일자': ('회계일자','거래일자','전표일자','일자','일자(회계)'),
 '부서명': ('부서명','부서','귀속부서','담당부서'), '거래선': ('거래선','거래선명','거래처','거래처명'),
 '차변': ('차변','차변금액','차변액'), '대변': ('대변','대변금액','대변액'),
 '적요': ('적요','거래적요','적요내용'), '예적금명': ('예적금명','예금명','계좌명','입출금계좌','계좌번호'),
 '회계단위': ('회계단위','회계구분'), '계정명': ('계정명','계정과목','계정과목명'), '목': ('목','목명','목계정명')}


def text(value):
    if value is None:return ''
    if isinstance(value,float) and value.is_integer():return str(int(value))
    return str(value).strip()


def compact(value):
    return re.sub(r'[^0-9a-z가-힣]', '', unicodedata.normalize('NFKC',text(value)).lower())


def party(value):
    value=unicodedata.normalize('NFKC',text(value)).lower()
    value=re.sub(r'농업회사법인|재단법인|사단법인|주식회사|\(주\)', '', value)
    value=re.sub(r'^\s*\d{5,}\s*','',value)
    return compact(value)


def purpose(value):
    value=text(value)
    for original,replacement in [('연체료','가산금'),('환수','반환'),('환불','반환'),('수입','입금'),('이체불능','계좌오류'),('집행금 반납','선집행'),('착오송금','오입금'),('계정 간 이체','이관')]:
        value=value.replace(original,replacement)
    value=re.sub(r'\d{4}년|\d{1,2}월(?:분)?|\d{1,2}일','',value)
    return compact(value)


def amount(value):
    raw=text(value).replace(',','').replace('원','').replace(' ','')
    if raw in ('','-'):return 0
    if raw.startswith('(') and raw.endswith(')'):raw='-'+raw[1:-1]
    try:
        number=Decimal(raw)
        if not number.is_finite() or number!=number.to_integral_value():raise ValueError('원 단위 정수가 아닙니다.')
        return int(number)
    except (InvalidOperation,ValueError):raise ValueError(f'금액 확인 필요: {value!r}')


def parse_date(value):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    raw=text(value)
    if re.fullmatch(r'\d{8}',raw):return datetime.strptime(raw,'%Y%m%d').date()
    match=re.fullmatch(r'(\d{4})[./년-]\s*(\d{1,2})[./월-]\s*(\d{1,2})(?:일|\.)?(?:\s+.*)?',raw)
    if match:return date(*map(int,match.groups()))
    if isinstance(value,(float,int)) and 1<=value<=100000:return date(1899,12,30)+timedelta(days=int(value))
    raise ValueError(f'회계일자 확인 필요: {value!r}')


@dataclass
class Transaction:
    row_id: str
    row: int
    sheet: str
    voucher: str
    day: date
    department: str
    counterparty: str
    debit: int
    credit: int
    description: str
    account: str = ''
    unit: str = ''
    raw: tuple = ()
    warnings: tuple = ()
    name: str = field(init=False)
    narrative: str = field(init=False)
    months: tuple = field(init=False)
    period: tuple = field(init=False)
    refund: bool = field(init=False)

    def __post_init__(self):
        self.name=party(self.counterparty);self.narrative=purpose(self.description)
        self.months=tuple(sorted(set(int(m) for m in re.findall(r'(?<!\d)(1[0-2]|[1-9])월',self.description))))
        self.refund=any(word in self.description for word in ('반환','환불','환수','착오송금','오입금'))
        self.period=()
        match=re.search(r'(\d{1,2})[./](\d{1,2})\.?\s*[~～∼–-]\s*(\d{1,2})[./](\d{1,2})',self.description)
        if match:
            m,d,m2,d2=map(int,match.groups())
            try:
                end=date(self.day.year,m2,d2);start=date(self.day.year-(m>m2),m,d)
                self.period=(start,end)
            except ValueError:pass

    @property
    def side(self):
        if self.debit>0 and self.credit==0:return 'D'
        if self.credit>0 and self.debit==0:return 'C'
        return ''

    @property
    def value(self):return self.debit if self.side=='D' else self.credit


def sheet_names(path):
    path=Path(path)
    if path.suffix.lower()=='.xls':
        book=open_legacy_workbook(path)
        try:return book.sheet_names()
        finally:book.release_resources()
    book=load_workbook(path,read_only=True,data_only=True)
    try:return book.sheetnames
    finally:book.close()


def read_sheet(path,sheet,preserve_formulas=False):
    if Path(path).suffix.lower()=='.xls':
        import xlrd
        book=open_legacy_workbook(path)
        try:
            ws=book.sheet_by_name(sheet);rows=[]
            for r in range(ws.nrows):
                row=[]
                for cell in ws.row(r):
                    if cell.ctype==xlrd.XL_CELL_ERROR:raise ValueError(f'{sheet} {r+1}행 Excel 오류 셀')
                    row.append(xlrd.xldate_as_datetime(cell.value,book.datemode) if cell.ctype==xlrd.XL_CELL_DATE else cell.value)
                rows.append(tuple(row))
            return rows
        finally:book.release_resources()
    book=load_workbook(path,read_only=True,data_only=not preserve_formulas)
    try:
        rows=[]
        for row in book[sheet].iter_rows():
            if any(c.data_type=='e' for c in row):raise ValueError(f'{sheet} {row[0].row}행 Excel 오류 셀')
            rows.append(tuple(c.value for c in row))
        return rows
    finally:book.close()


def load_ledger(path,sheet):
    path=Path(path)
    if path.suffix.lower() not in ('.xls','.xlsx'):raise ValueError('XLS 또는 XLSX 원장을 선택하세요.')
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest()
    rows=read_sheet(path,sheet);raw_rows=read_sheet(path,sheet,True) if path.suffix.lower()=='.xlsx' else rows
    if hashlib.sha256(path.read_bytes()).hexdigest()!=fingerprint:raise ValueError('읽는 동안 원본 파일이 변경되었습니다. 다시 실행하세요.')
    mapping={};header=None
    aliases={compact(v):key for key,values in ALIASES.items() for v in values}
    for index,row in enumerate(rows[:100]):
        found={};duplicates=set()
        for col,value in enumerate(row):
            key=aliases.get(compact(value))
            if key:
                if key in found:duplicates.add(key)
                found[key]=col
        if all(key in found for key in FIELDS):
            if duplicates:raise ValueError('중복된 필수/선택 열: '+', '.join(sorted(duplicates)))
            header=index;mapping=found;break
    if header is None:raise ValueError('필수 열을 찾지 못했습니다: '+', '.join(FIELDS))
    account_key='목' if '목' in mapping else '계정명' if '계정명' in mapping else None
    transactions=[];excluded=[]
    for index,row in enumerate(rows[header+1:],header+2):
        def get(key):
            col=mapping.get(key);return row[col] if col is not None and col<len(row) else None
        if not any(text(v) for v in row):continue
        if account_key and compact(get(account_key))!='가수금':
            excluded.append((index,f'가수금 외 {account_key}: '+text(get(account_key))));continue
        label=compact(get('전표정보')) or compact(get('적요'))
        if label in ('합계','총계','소계','월계','누계','전기이월','전월이월','이월') and not get('회계일자'):
            excluded.append((index,'합계·이월 표시행'));continue
        for key in ('차변','대변'):
            original=raw_rows[index-1][mapping[key]]
            if isinstance(original,str) and original.startswith('=') and get(key) is None:
                raise ValueError(f'{sheet} {index}행: 수식 계산값이 없습니다. Excel에서 계산 후 저장하세요.')
        try:
            debit,credit=amount(get('차변')),amount(get('대변'));day=parse_date(get('회계일자'))
        except ValueError as exc:raise ValueError(f'{sheet} {index}행: {exc}') from exc
        identity=hashlib.sha256(f'{fingerprint}|{sheet}|{index}'.encode()).hexdigest()[:24]
        warnings=() if (debit>0 and credit==0) or (credit>0 and debit==0) else ('음수·양변·0원 거래: 자동매칭 제외',)
        transactions.append(Transaction(identity,index,sheet,text(get('전표정보')),day,text(get('부서명')),text(get('거래선')),debit,credit,text(get('적요')),text(get('예적금명')),text(get('회계단위')),tuple(raw_rows[index-1]),warnings))
    if not transactions:raise ValueError('검증할 거래가 없습니다.')
    transactions.sort(key=lambda t:(t.day,t.voucher,t.row))
    return {'path':str(path),'hash':fingerprint,'sheet':sheet,'headers':rows[header], 'raw_rows':raw_rows,'rows':transactions,'excluded':excluded,'version':VERSION,'account_filter':f'{account_key}=가수금' if account_key else '계정 구분 열 없음: 선택 시트 전체','source_count':len(rows)-header-1}
