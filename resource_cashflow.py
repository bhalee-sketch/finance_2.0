"""Classify ledger postings against the published cash statement's 관·항·목."""
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from time import sleep
from zipfile import ZipFile, ZIP_DEFLATED

from finance_data import money, rows, text
from release_update import atomic_json, read_json
from statement_analysis import normalize

SCHOLARSHIP_GROUP = '교육부(국가장학금)'
ACCOUNT_LEVELS = ('관', '항', '목')
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
    scholarship_funds: frozenset = frozenset()

    def _postings(self, fund):
        selected = None
        if fund is not None:
            selected = {fund} if isinstance(fund, str) else set(fund)
        for (source, project, side, path), amount in self.amounts.items():
            if selected is None or source in selected:
                label = SCHOLARSHIP_GROUP if source in self.scholarship_funds else source
                yield (label, project, side, path), amount

    def fund_statement(self, fund=None, level='목'):
        """Roll up each fund to the selected account level in cash statement order."""
        depth = ACCOUNT_LEVELS.index(level) + 1
        accounts = defaultdict(lambda: defaultdict(Decimal))
        funds = set()
        for (source, _, side, path), amount in self._postings(fund):
            accounts[side, *path[:depth]][source] += amount
            funds.add(source)
        funds = sorted(funds, key=lambda name: (not name, name))
        ranked_groups = dict.fromkeys(key[:depth + 1] for key in self.ranks)
        order = [key for key in ranked_groups if key in accounts]
        names = Counter((key[0], key[-1]) for key in order)
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
                label = key[-1]
                if names[side, label] > 1:
                    label = f"{label} ({' / '.join(key[1:-1])})"
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


def read_scholarship_funds(folder, year):
    try:
        members = read_json(folder / f'{year}-scholarship.json')
    except FileNotFoundError:
        return frozenset()
    if not isinstance(members, list) or not all(isinstance(name, str) for name in members):
        raise ValueError(f'{year}회계연도 재원 묶음 설정을 확인하세요.')
    return frozenset(members)


def save_scholarship_funds(folder, year, members):
    atomic_json(folder / f'{year}-scholarship.json', sorted(members))


def _retry_file_lock(operation, *args, filename):
    for delay in (0.2, 0.5, 1.0, 2.0, None):
        try:
            return operation(*args)
        except OSError as error:
            if getattr(error, 'winerror', None) not in (32, 33):
                raise
            if delay is None:
                raise PermissionError(
                    f'{filename} 파일이 사용 중입니다. 파일을 닫거나 동기화가 끝난 뒤 다시 시도하세요.'
                ) from error
            sleep(delay)


def store_cashflow(folder, year, source, history):
    if len(year) != 4 or not year.isascii() or not year.isdigit():
        raise ValueError('회계연도를 선택하세요.')
    source = Path(source)
    folder.mkdir(parents=True, exist_ok=True)
    # Only the archive needs to be on the destination volume for atomic replacement.
    with TemporaryDirectory(dir=folder, ignore_cleanup_errors=True) as staging:
        archive = Path(staging) / 'report.zip'
        with TemporaryDirectory(prefix='workspace-ledger-', ignore_cleanup_errors=True) as local:
            workbook = Path(local) / ('workbook' + source.suffix.lower())
            _retry_file_lock(copyfile, source, workbook, filename=source.name)
            report = analyze_cashflow(workbook, history, fiscal_year=year)
            summary = dict(filename=source.name, year=report.year, basis=report.basis,
                           included=report.included, excluded=report.excluded, ranks=list(report.ranks),
                           amounts=[[fund, project, side, path, str(amount)]
                                    for (fund, project, side, path), amount in report.amounts.items()])
            with ZipFile(archive, 'w') as output:
                output.write(workbook, workbook.name)
                output.writestr('summary.json', json.dumps(summary, ensure_ascii=False), compress_type=ZIP_DEFLATED)
        report.scholarship_funds = read_scholarship_funds(folder, year)
        target = folder / f'{year}.zip'
        _retry_file_lock(archive.replace, target, filename=target.name)
    return source.name, report


def read_cashflow(folder, year):
    with ZipFile(folder / f'{year}.zip') as archive:
        data = json.loads(archive.read('summary.json'))
    amounts = {(fund, project, side, tuple(path)): Decimal(amount)
               for fund, project, side, path, amount in data['amounts']}
    ranks = {tuple(key): i for i, key in enumerate(data['ranks'])}
    return data['filename'], Cashflow(data['year'], data['basis'], data['included'], data['excluded'], amounts, ranks,
                                     read_scholarship_funds(folder, year))
