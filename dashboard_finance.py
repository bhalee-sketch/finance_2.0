"""Dashboard snapshots from the closing statements, in unrounded won."""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache

from closing_review import STATEMENT_TOTAL_CHECKS
from financial_analysis import ANALYSIS_SHEETS, SCOPES, parse_nonfund
from statement_analysis import normalize, optional_money
from statement_database import DATABASE, discover_statements, iter_analysis_sheets

SCOPE_NAMES = {'전체': '교비 합산', '등록금': '등록금회계', '비등록금': '비등록금회계'}
MILLION = Decimal(1_000_000)
LOAN_PATHS = (('유동부채', '단기차입금'), ('고정부채', '장기차입금'))


def year_end(year):
    return date(year + 1, 2, monthrange(year + 1, 2)[1])


def won(value):
    if value is None:
        return '자료 없음'
    amount = f'{value:,f}'
    if '.' in amount:
        amount = amount.rstrip('0').rstrip('.')
    return amount + '원'


def millions(value):
    return None if value is None else (value / MILLION).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def complete_sum(values):
    values = list(values)
    return sum(values) if values and None not in values else None


def difference(left, right):
    return None if left is None or right is None else left - right


def amount_row(rows, index, labels):
    found = [row[index] for row in rows if normalize(row[0]).strip('[]') in labels]
    return optional_money(found[0]) if len(found) == 1 else None


@dataclass
class Balance:
    accounts: list
    assets: list
    liabilities: list
    capital: list
    left_total: Decimal | None
    right_total: Decimal | None
    fund: Decimal | None
    loan_parts: tuple

    @property
    def debt(self):
        return complete_sum(v for _, v in self.liabilities)

    @property
    def equity(self):
        return complete_sum(v for _, v in self.capital)

    @property
    def capital_items(self):
        return [(p[-1], v) for _, p, v in self.accounts if len(p) == 2 and p[0] == '기본금']

    @property
    def checks(self):
        return {
            '자산총계 − 부채·기본금 소계': difference(self.left_total, complete_sum((self.debt, self.equity))),
            '양측 표시 총계 차이': difference(self.left_total, self.right_total),
            '자산총계 − 자산 항목 합계': difference(self.left_total, complete_sum(v for _, v in self.assets)),
        }

    @property
    def rounding_note(self):
        groups = [(self.assets, self.left_total), (self.liabilities, self.debt),
                  (self.capital_items, self.equity), ([('', self.debt), ('', self.equity)], self.right_total)]
        return any(complete_sum(v for _, v in rows) == total and total is not None
                   and sum(millions(v) for _, v in rows) != millions(total) for rows, total in groups)


def balance_sheet(title, rows, index):
    parsed = parse_nonfund(title, rows, index, '재무상태표')
    accounts = [(item['section'], item['path'], item['actual']) for item in parsed['items'].values()]
    paths = {path: value for _, path, value in accounts}
    assets = [(path[0], value) for section, path, value in accounts if section == '자산' and len(path) == 1]
    liabilities = [(path[0], value) for section, path, value in accounts
                   if section != '자산' and len(path) == 1 and path[0].endswith('부채')]
    # Present the basic-fund section's immediate children; its original subtotal also participates in validation.
    equity = [(path[0], value) for section, path, value in accounts
              if section != '자산' and path == ('기본금',)]
    return Balance(accounts, assets, liabilities, equity,
                   parsed['totals'].get('자산',(None,None))[1],
                   parsed['totals'].get('부채와기본금',(None,None))[1],
                   paths.get(('투자와기타자산','임의기금')), tuple(paths.get(p) for p in LOAN_PATHS))


@dataclass
class Period:
    cash: tuple = (None, None)
    operation: tuple = (None, None)
    balance: Balance | None = None
    errors: dict = field(default_factory=dict)


@dataclass
class DashboardData:
    years: tuple
    periods: dict

    def latest_balance(self, scope):
        return next(((year, period.balance) for (year, s), period in sorted(self.periods.items(), reverse=True)
                     if s == scope and period.balance is not None), (None, None))


@lru_cache(maxsize=1)
def _load(path, stamp, as_of=None):
    as_of = as_of or date.today()
    sources = discover_statements(path)
    if not sources:
        return DashboardData((), {})
    latest = max(map(int, sources))
    years = tuple(range(latest-4, latest+1))
    periods = {}
    for year_text, source in sources.items():
        year = int(year_text)
        if year_end(year) > as_of:
            # This archive records fiscal years but has no interim reporting date.
            for scope in SCOPES:
                periods[year, scope] = Period(errors=dict.fromkeys(
                    ('자금계산서', '재무상태표', '운영계산서'), '미확정 · 중간실적 기준일 미등록'))
            continue
        splits = {}
        for title, sheet, errors in iter_analysis_sheets(source, lambda n: normalize(n) in ANALYSIS_SHEETS):
            kind, scope = normalize(title)[:-1].split('(')
            period = periods.setdefault((year, scope), Period())
            try:
                headers = [normalize(v) for v in sheet[0]]
                rows = sheet[1:]
                column = '결산' if kind == '자금계산서' else '당기'
                index = headers.index(column)
                if kind == '자금계산서':
                    period.cash = tuple(amount_row(rows, index, labels) for labels in STATEMENT_TOTAL_CHECKS[0][2:])
                elif kind == '운영계산서':
                    period.operation = tuple(amount_row(rows, index, (name,)) for name in ('운영수익총계','운영비용총계'))
                else:
                    period.balance = balance_sheet(title, rows, index)
                    if scope == '전체':
                        for s in ('등록금','비등록금'):
                            if s in headers:
                                splits[s] = balance_sheet(title, rows, headers.index(s)).loan_parts
                if errors:
                    period.errors[kind] = '원본 오류 셀 ' + ', '.join(errors)
            except (ValueError, IndexError) as error:
                period.errors[kind] = str(error)
        # Some individual statements omit zero-balance accounts. Use only explicit
        # zero cells printed for that account/scope in the combined statement.
        for scope, split in splits.items():
            period = periods.get((year,scope))
            if period and period.balance:
                period.balance.loan_parts = tuple(Decimal(0) if value is None and corroborated == 0 else value
                                                  for value, corroborated in zip(period.balance.loan_parts,split))
    return DashboardData(years, periods)


def load_dashboard(path=DATABASE):
    return _load(path, path.stat().st_mtime_ns if path.exists() else None, date.today())
