"""Classify ledger postings against the published cash statement's 관·항·목."""
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

from finance_data import money, rows, text
from statement_analysis import normalize

REQUIRED = ('년도', '관', '항', '목', '대사업', '재원', '차변', '대변')
# Ledger asset names describe the asset itself. A debit acquisition maps to
# the statement purchase line. A disposal's book value is not sale proceeds.
PURCHASES = {
    '토지': '토지매입비', '구축물': '구축물매입비', '기계기구': '기계기구매입비',
    '집기비품': '집기비품매입비', '차량운반구': '차량운반구매입비', '도서': '도서구입비',
}


def account_catalog(data):
    catalog = {}
    ranks = {}
    for (_, unit), dataset in data['datasets'].items():
        if unit != '합계':
            continue
        for item in dataset['items'].values():
            path = item['path']
            if len(path) != 3 or normalize(path[0]) in ('미사용전기이월자금', '미사용차기이월자금'):
                continue
            key = tuple(map(normalize, path))
            catalog.setdefault(key, {}).setdefault(item['section'], path)
            ranks.setdefault((item['section'], *path), len(ranks))
    return catalog, ranks


def match_cash_account(catalog, account):
    if account[0] == '교육외수입':
        return None, False
    purchase = (account not in catalog and account[:2] == ('고정자산', '유형고정자산')
                and account[2] in PURCHASES)
    if purchase:
        account = (*account[:2], PURCHASES[account[2]])
    sides = catalog.get(account)
    return sides, purchase


@dataclass
class Cashflow:
    year: str
    basis: str
    included: int
    excluded: int
    amounts: dict
    ranks: dict

    def _postings(self, fund):
        if fund is None:
            return self.amounts.items()
        selected = {fund} if isinstance(fund, str) else set(fund)
        return ((key, amount) for key, amount in self.amounts.items() if key[0] in selected)

    def fund_statement(self, fund=None):
        """Group fund amounts by full account path and show 목 in statement order."""
        accounts = defaultdict(lambda: defaultdict(Decimal))
        funds = set()
        for (source, _, side, path), amount in self._postings(fund):
            accounts[side, *path][source] += amount
            funds.add(source)
        funds = sorted(funds, key=lambda name: (not name, name))
        order = sorted(accounts, key=self.ranks.__getitem__)
        names = Counter((side, mok) for side, _, _, mok in order)
        rows = []
        totals = {}
        for side in ('수입', '지출'):
            rows.append((f'[{side}]', None))
            subtotal = [Decimal(0)] * len(funds)
            for key in order:
                if key[0] != side:
                    continue
                values = [accounts[key].get(source) for source in funds]
                for i, value in enumerate(values):
                    if value is not None:
                        subtotal[i] += value
                _, kwan, hang, mok = key
                label = f'{mok} ({kwan} / {hang})' if names[side, mok] > 1 else mok
                rows.append((label, values))
            rows.append((f'자금{side}총계', subtotal))
            totals[side] = subtotal
        rows.append(('수지차액', [a - b for a, b in zip(totals['수입'], totals['지출'])]))
        return funds, rows

    def report(self, view, fund=None):
        if view not in ('재원별 요약', '대사업별 요약'):
            raise ValueError(f'지원하지 않는 보기입니다. {view}')
        groups = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for (source, project, side, _), amount in self._postings(fund):
            key = source if view == '재원별 요약' else project
            groups[key][0 if side == '수입' else 1] += amount
        rows = []
        for key, (income, expense) in sorted(groups.items()):
            rows.append((key, income, expense, income - expense))
        return rows


def analyze_cashflow(path, history, *, fiscal_year=None):
    amounts = defaultdict(Decimal)
    year = basis = None
    included = excluded = 0
    with closing(rows(path)) as stream:
        headers = [text(cell) for cell in next(stream, [])]
        invalid = [name for name in REQUIRED if headers.count(name) != 1]
        if invalid:
            raise ValueError('원장 첫 행에서 누락되거나 중복된 열을 확인하세요. ' + ', '.join(invalid))
        indices = [headers.index(name) for name in REQUIRED]
        for number, row in enumerate(stream, 2):
            values = [row[i] if i < len(row) else None for i in indices]
            if not any(text(cell) for cell in values):
                continue
            posting_year, kwan, hang, mok, project, fund, debit, credit = values
            posting_year = text(posting_year)
            if year is None:
                if len(posting_year) != 4 or not posting_year.isascii() or not posting_year.isdigit():
                    raise ValueError(f'{number}행의 회계연도를 확인하세요.')
                year = posting_year
                target = fiscal_year or year
                basis = max((y for y in history if y <= target), default=None)
                if basis is None:
                    raise ValueError(f'{target}년도에 적용할 자금계산서 계정표가 없습니다.')
                catalog, ranks = account_catalog(history[basis])
                if not catalog:
                    raise ValueError(f'{basis}년도 자금계산서에 분석할 계정이 없습니다.')
            elif posting_year != year:
                raise ValueError(f'{number}행의 연도가 다릅니다. 한 회계연도의 원장을 선택하세요.')
            account = tuple(map(normalize, (kwan, hang, mok)))
            sides, purchase = match_cash_account(catalog, account)
            if not sides:
                excluded += 1
                continue
            try:
                debit, credit = money(debit), money(credit)
            except ValueError as error:
                raise ValueError(f'{number}행 차변·대변 확인 · {error}') from error
            if purchase and (credit or '지출' not in sides):
                excluded += 1
                continue
            source = text(fund)
            business = text(project)
            if len(sides) == 2:
                # Some paths, e.g. 건설중인자산, are published on both sides.
                postings = [('수입', credit), ('지출', debit)]
            elif '수입' in sides:
                postings = [('수입', credit - debit)]
            else:
                postings = [('지출', debit - credit)]
            for side, amount in postings:
                if amount or len(postings) == 1:
                    amounts[source, business, side, sides[side]] += amount
            included += 1
    if year is None:
        raise ValueError('원장에 분석할 거래 행이 없습니다.')
    return Cashflow(year, basis, included, excluded, dict(amounts), ranks)


def saved_cashflow_years(folder):
    return sorted((p.stem for p in folder.glob('[0-9][0-9][0-9][0-9].zip') if p.is_file()), reverse=True)


def store_cashflow(folder, year, source, history):
    if len(year) != 4 or not year.isascii() or not year.isdigit():
        raise ValueError('회계연도를 선택하세요.')
    source = Path(source)
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder) as staging:
        workbook = Path(staging) / ('workbook' + source.suffix.lower())
        copyfile(source, workbook)
        report = analyze_cashflow(workbook, history, fiscal_year=year)
        summary = dict(filename=source.name, year=report.year, basis=report.basis,
                       included=report.included, excluded=report.excluded, ranks=list(report.ranks),
                       amounts=[[fund, project, side, path, str(amount)]
                                for (fund, project, side, path), amount in report.amounts.items()])
        archive = Path(staging) / 'report.zip'
        with ZipFile(archive, 'w') as output:
            output.write(workbook, workbook.name)
            output.writestr('summary.json', json.dumps(summary, ensure_ascii=False), compress_type=ZIP_DEFLATED)
        archive.replace(folder / f'{year}.zip')
    return source.name, report


def read_cashflow(folder, year):
    with ZipFile(folder / f'{year}.zip') as archive:
        data = json.loads(archive.read('summary.json'))
    amounts = {(fund, project, side, tuple(path)): Decimal(amount)
               for fund, project, side, path, amount in data['amounts']}
    ranks = {tuple(key): i for i, key in enumerate(data['ranks'])}
    return data['filename'], Cashflow(data['year'], data['basis'], data['included'], data['excluded'], amounts, ranks)
