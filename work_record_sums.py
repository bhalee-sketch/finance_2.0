"""SUM references are local to the visible task sheet, using A1 coordinates."""
from decimal import Decimal
from graphlib import CycleError, TopologicalSorter
from openpyxl.utils.cell import column_index_from_string
import re

_AMOUNT = re.compile(r'([+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*원?')
_SUM = re.compile(r'=\s*SUM\b', re.I)
_ARGUMENTS = re.compile(r'=\s*SUM\s*\(([^()]*)\)', re.I)
_CELL = re.compile(r'\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})', re.I)
_EXPRESSION = re.compile(r'=\s*(\$?[A-Z]{1,3}\$?[1-9]\d*)(?:\s*[+-]\s*\$?[A-Z]{1,3}\$?[1-9]\d*)*\s*', re.I)
_TERM = re.compile(r'([+-]?)\s*(\$?[A-Z]{1,3}\$?[1-9]\d*)', re.I)


def _address(text, columns):
    match = _CELL.fullmatch(text.strip())
    if not match:
        raise ValueError('#REF!')
    column = column_index_from_string(match[1]) - 1
    row = int(match[2])
    if column >= columns or row > 1048576:
        raise ValueError('#REF!')
    return row - 1, column


def _ranges(formula, height, columns):
    match = _ARGUMENTS.fullmatch(formula)
    if not match or not match[1].strip():
        raise ValueError('#VALUE!')
    for argument in match[1].split(','):
        first, separator, last = argument.partition(':')
        row, column = _address(first, columns)
        end_row, end_col = _address(last, columns) if separator else (row, column)
        yield (min(row, end_row), min(height, max(row, end_row) + 1),
               min(column, end_col), max(column, end_col) + 1)


def _references(rect, candidates):
    top, bottom, left, right = rect
    if (bottom - top) * (right - left) > len(candidates):
        for row, column in candidates:
            if top <= row < bottom and left <= column < right:
                yield row, column
    else:
        for row in range(top, bottom):
            for column in range(left, right):
                if (row, column) in candidates:
                    yield row, column


def sheet_values(rows):
    cells = {(r, c): raw for r, row in enumerate(rows) for c, raw in enumerate(row) if raw}
    return calculate_cells(cells, len(rows), max(map(len, rows), default=0))


def calculate_cells(cells, height, columns, *, arithmetic=False):
    values = {}
    formulas = {}
    for key, raw in cells.items():
        text = raw.strip()
        try:
            if _SUM.match(text):
                formulas[key] = [(1, rect, False) for rect in _ranges(text, height, columns)]
            elif arithmetic and text.startswith('='):
                if not _EXPRESSION.fullmatch(text):
                    raise ValueError('#VALUE!')
                terms = []
                for sign, address in _TERM.findall(text[1:]):
                    row, col = _address(address, columns)
                    terms.append((-1 if sign == '-' else 1, (row, row+1, col, col+1), True))
                formulas[key] = terms
            else:
                match = _AMOUNT.fullmatch(text)
                if match:
                    values[key] = Decimal(match[1].replace(',', ''))
        except ValueError as error:
            values[key] = str(error)

    order = TopologicalSorter()
    for key, terms in formulas.items():
        order.add(key, *(ref for _, rect, _ in terms for ref in _references(rect, formulas)))
    try:
        order.prepare()
    except CycleError:
        pass  # Unrelated formulas can still be calculated.
    while order.is_active():
        for key in order.get_ready():
            total = Decimal(0)
            for sign, rect, direct in formulas[key]:
                for ref in _references(rect, cells):
                    value = values.get(ref)
                    if isinstance(value, str) or (direct and value is None):
                        total = value or '#VALUE!'
                        break
                    if value is not None:
                        total += sign * value
                if isinstance(total, str):
                    break
            values[key] = total
            order.done(key)
    for key in formulas.keys() - values.keys():
        values[key] = '#순환참조!'
    return values
