"""Classify ledger postings against the published cash statement's 관·항·목."""
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal

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


@dataclass
class Cashflow:
    year: str
    basis: str
    included: int
    excluded: int
    amounts: dict
    ranks: dict

    def project_statement(self, fund=None):
        """Roll up classified postings once, at the 관 level, in statement order."""
        accounts = defaultdict(lambda: defaultdict(Decimal))
        projects = set()
        for (source, project, side, path), amount in self.amounts.items():
            if fund is None or source == fund:
                accounts[side, path[0]][project] += amount
                projects.add(project)
        projects = sorted(projects, key=lambda name: (not name, name))
        order = dict.fromkeys((side, kwan) for side, kwan, _, _ in self.ranks)
        rows = []
        totals = {}
        for side in ('수입', '지출'):
            rows.append((f'[{side}]', None))
            subtotal = [Decimal(0)] * len(projects)
            for key in order:
                if key[0] != side or key not in accounts:
                    continue
                values = [accounts[key].get(project) for project in projects]
                for i, value in enumerate(values):
                    if value is not None:
                        subtotal[i] += value
                rows.append((key[1], values))
            rows.append((f'자금{side}총계', subtotal))
            totals[side] = subtotal
        rows.append(('수지차액', [a - b for a, b in zip(totals['수입'], totals['지출'])]))
        return projects, rows

    def report(self, view, fund=None):
        groups = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for (source, project, side, account), amount in self.amounts.items():
            if fund is not None and fund != source:
                continue
            if view == '재원별 요약':
                key = (source,)
            elif view == '대사업별 요약':
                key = (project,)
            else:
                key = (side, *account, project)
            pair = groups[key]
            pair[0 if side == '수입' else 1] += amount
        if view == '계정·대사업별 상세':
            keys = sorted(groups, key=lambda key: (key[0] != '수입', self.ranks[key[:-1]], key[-1]))
        else:
            keys = sorted(groups)
        rows = []
        for key in keys:
            income, expense = groups[key]
            rows.append((*key, income, expense, income - expense))
        return rows


def analyze_cashflow(path, history):
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
                basis = max((y for y in history if y <= year), default=None)
                if basis is None:
                    raise ValueError(f'{year}년도에 적용할 자금계산서 계정표가 없습니다.')
                catalog, ranks = account_catalog(history[basis])
                if not catalog:
                    raise ValueError(f'{basis}년도 자금계산서에 분석할 계정이 없습니다.')
            elif posting_year != year:
                raise ValueError(f'{number}행의 연도가 다릅니다. 한 회계연도의 원장을 선택하세요.')
            account = tuple(map(normalize, (kwan, hang, mok)))
            if account[0] == '교육외수입':
                excluded += 1
                continue
            purchase = (account not in catalog and account[:2] == ('고정자산', '유형고정자산')
                        and account[2] in PURCHASES)
            if purchase:
                account = (*account[:2], PURCHASES[account[2]])
            sides = catalog.get(account)
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
